"""Finite main-thread modifier stack transactions and evaluated readback."""
import hashlib
import json
from types import SimpleNamespace as NS
from .advanced_modifier_contract import PROPERTIES, validate
from .modifier_tools import _target
from . import modifier_checkpoint
from .mesh_topology import inspect_elements
from .shader_values import shader_value, shader_values_match
from .approval_registry import get_approval_registry


def _geometry(obj, context, source):
    result=inspect_elements(obj,context,{'element_domain':'vertices','limit':1,'mesh_source':source})
    return {k:result[k] for k in ('snapshot_id','state_id','vertex_count','edge_count','polygon_count')}


def inspect(bpy, name):
    obj=_target(bpy,{'name':name})
    entries=[]
    for mod in obj.modifiers:
        props={}
        for key in PROPERTIES.get(mod.type,{}):
            value=(mod.object.name if mod.object else None) if key=='operand_name' else shader_value(getattr(mod,key))
            props[key]=value
        entries.append({'name':mod.name,'type':mod.type,'properties':props,
                        'show_viewport':mod.show_viewport,'show_render':mod.show_render})
    result={'name':obj.name,'modifiers':entries,'base':_geometry(obj,bpy.context,'base'),
            'evaluated':_geometry(obj,bpy.context,'evaluated'),
            'matrix_world':[list(row) for row in obj.matrix_world]}
    result['snapshot_id']='sha256:'+hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return dict(result,success=True,verified=True)


def handle_inspect_modifier_stack(bpy_module=None,params=None):
    clean=validate(params or {},inspection=True)
    return inspect(bpy_module,clean['name'])


def _verify(bpy,obj,expected):
    actual=inspect(bpy,obj.name)
    if actual['snapshot_id']!=expected['snapshot_id']:
        raise RuntimeError('Modifier stack/evaluated geometry readback mismatch')
    return actual


def _apply_mesh(bpy,obj,mod):
    if list(obj.modifiers).index(mod)!=0 or not mod.show_viewport:
        raise ValueError('Apply requires the first, viewport-enabled modifier; reorder explicitly first')
    temp=None;mesh=None
    try:
        temp=obj.copy()
        for other in list(temp.modifiers)[1:]:temp.modifiers.remove(other)
        bpy.context.scene.collection.objects.link(temp)
        bpy.context.view_layer.update()
        graph=bpy.context.evaluated_depsgraph_get()
        mesh=bpy.data.meshes.new_from_object(temp.evaluated_get(graph),preserve_all_data_layers=True,depsgraph=graph)
        candidate=NS(name=obj.name,type='MESH',data=mesh,mode='OBJECT')
        context=NS(mode='OBJECT',scene=NS(objects={obj.name:candidate}))
        expected=_geometry(candidate,context,'base')
        if mesh.validate(verbose=False,clean_customdata=False):
            raise ValueError('Applied modifier produced invalid mesh geometry')
        return mesh,expected
    except Exception:
        if mesh is not None and mesh.users==0:bpy.data.meshes.remove(mesh)
        raise
    finally:
        if temp is not None:bpy.data.objects.remove(temp,do_unlink=True)


def handle_edit_modifier_stack(bpy_module=None,params=None,tool_name='edit_modifier_stack',original_params=None):
    bpy=bpy_module;params=params or {};approval_params=original_params if original_params is not None else params
    clean=validate(params)
    obj=_target(bpy,clean)
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok,reason=get_approval_registry().consume_approval(approval_params.get('request_id'),approval_params.get('approval_token'),tool_name,approval_params)
        if not ok:raise PermissionError('Modifier stack mutation denied: '+reason)
    if bpy.context.mode!='OBJECT' or obj.mode!='OBJECT' or obj.library or obj.data.library or obj.override_library:
        raise ValueError('Modifier transactions require a local Object-mode mesh')
    if obj.animation_data or obj.data.animation_data or obj.data.shape_keys:
        raise ValueError('Animated/shape-key targets are unsupported; nothing changed')
    if any(m.type not in PROPERTIES for m in obj.modifiers):
        raise ValueError('Stack includes an unsupported modifier; nothing changed')
    before=inspect(bpy,obj.name)
    if before['snapshot_id']!=clean['expected_snapshot_id']:raise ValueError('STALE_MODIFIER_STACK; inspect again')
    action=clean['action'];name=clean['modifier_name'];mod=obj.modifiers.get(name)
    if action=='add' and mod is not None:raise ValueError('Modifier name already exists')
    if action!='add' and (mod is None or mod.type!=clean['modifier_type']):raise ValueError('Modifier name/type mismatch')
    if action=='reorder' and clean['index']>=len(obj.modifiers):raise ValueError('Modifier index outside stack')
    operand=None
    if 'operand_name' in clean.get('properties',{}):
        operand=bpy.context.scene.objects.get(clean['properties']['operand_name'])
        if operand is None or operand==obj or operand.type!='MESH' or operand.library or operand.data.library or operand.mode!='OBJECT':
            raise ValueError('Boolean operand must be a different local active-scene Object-mode mesh')
    checkpoint=modifier_checkpoint.capture(obj,mod) if mod else None
    old_data=obj.data;old_data_name=old_data.name;staged=None;created=False
    old_active=obj.modifiers.active
    old_active_name=old_active.name if old_active else None
    old_names=[m.name for m in obj.modifiers]
    try:
        if action=='add':
            mod=obj.modifiers.new(name=name,type=clean['modifier_type']);created=True
            if mod.name!=name:raise RuntimeError('Modifier exact-name readback mismatch')
        for key,value in clean.get('properties',{}).items():
            setattr(mod,'object' if key=='operand_name' else key,operand if key=='operand_name' else value)
            actual=mod.object.name if key=='operand_name' and mod.object else shader_value(getattr(mod,key)) if key!='operand_name' else None
            if not shader_values_match(actual,value):raise RuntimeError('Modifier property readback mismatch: '+key)
        if action=='visibility':
            for key in ('show_viewport','show_render'):
                if key in clean:
                    setattr(mod,key,clean[key])
                    if getattr(mod,key)!=clean[key]:raise RuntimeError('Modifier visibility readback mismatch')
        if action=='reorder':
            obj.modifiers.move(list(obj.modifiers).index(mod),clean['index'])
            if list(obj.modifiers).index(mod)!=clean['index']:raise RuntimeError('Modifier order readback mismatch')
        if action=='apply':
            staged,expected_base=_apply_mesh(bpy,obj,mod)
            obj.data=staged
            obj.modifiers.remove(mod)
            if _geometry(obj,bpy.context,'base')!=expected_base:raise RuntimeError('Applied mesh independent readback mismatch')
        elif action=='remove':obj.modifiers.remove(mod)
        if action in ('remove','apply') and obj.modifiers.get(name) is not None:raise RuntimeError('Modifier removal readback mismatch')
        bpy.context.view_layer.update()
        after=inspect(bpy,obj.name)
        observed=_verify(bpy,obj,after)
        result={'success':True,'verified':True,'name':obj.name,'action':action,'modifier_name':name,
                'transaction_status':'COMMITTED','before_snapshot_id':before['snapshot_id'],**observed}
        if staged is not None and old_data.users==0:
            old_name=old_data.name;old_data.name=old_name+'_UMCP_CHECKPOINT';staged.name=old_name
            if staged.name!=old_name:raise RuntimeError('Applied mesh name restoration mismatch')
            bpy.data.meshes.remove(old_data)
        return result
    except Exception as error:
        try:
            obj.data=old_data
            old_data.name=old_data_name
            if staged is not None and staged.users==0:bpy.data.meshes.remove(staged)
            if created:
                if obj.modifiers.get(name):obj.modifiers.remove(obj.modifiers.get(name))
                obj.modifiers.active=obj.modifiers.get(old_active_name) if old_active_name else None
            elif checkpoint is not None:modifier_checkpoint.restore(obj,checkpoint)
            bpy.context.view_layer.update()
            restored=inspect(bpy,obj.name)
            if restored['snapshot_id']!=before['snapshot_id'] or old_names!=[m.name for m in obj.modifiers]:
                raise RuntimeError('Original modifier/evaluated geometry state differs')
        except Exception as restore_error:
            raise RuntimeError(f'ROLLBACK_UNVERIFIED: {restore_error}; original failure: {error}') from error
        raise RuntimeError(f'ROLLED_BACK_VERIFIED: {error}') from error
