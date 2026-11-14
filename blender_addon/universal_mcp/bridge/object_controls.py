"""Finite object-space/world-space transform, selection and parenting controls."""
import hashlib,json,threading
from .modeling_validation import NAME,SNAPSHOT,VECTOR,tool_params
from .advanced_modifier_contract import enum
from .approval_registry import get_approval_registry
from .shader_values import shader_values_match

SCHEMA={'type':'object','additionalProperties':False,'required':['name','action','expected_snapshot_id'],'properties':{'name':NAME,'action':enum('transform','select','parent','clear_parent'),'expected_snapshot_id':SNAPSHOT,'space':enum('LOCAL','WORLD'),'translation':VECTOR,'rotation':VECTOR,'scale':VECTOR,'pivot':VECTOR,'parent_name':NAME,'state':{'type':'boolean'},'deselect_all':{'type':'boolean'},'make_active':{'type':'boolean'},'approved':{'type':'boolean','default':False}},'allOf':[]}
for action,extras in [('transform',{'space','translation','rotation','scale','pivot'}),('select',{'state','deselect_all','make_active'}),('parent',{'parent_name'}),('clear_parent',set())]:
    fields={'name','action','expected_snapshot_id','approved'}|extras
    SCHEMA['allOf'].append({'if':{'properties':{'action':{'const':action}}},'then':{'type':'object','additionalProperties':False,'properties':{key:SCHEMA['properties'][key] for key in fields}}})
INSPECTION={'type':'object','additionalProperties':False,'required':['name'],'properties':{'name':NAME}}


def validate(params,inspection=False):
    clean=tool_params(INSPECTION if inspection else SCHEMA,params)
    if inspection:return clean
    if clean['action']=='transform':
        if not any(key in clean for key in ('translation','rotation','scale')):raise ValueError('Explicit transform delta required')
        if any(abs(x)<1e-6 for x in clean.get('scale',[1,1,1])):raise ValueError('Transform scale cannot be singular')
    if clean['action']=='select' and 'state' not in clean:raise ValueError('Explicit selection state required')
    if clean['action']=='parent' and (not clean.get('parent_name','').strip() or clean['parent_name']!=clean['parent_name'].strip()):raise ValueError('Exact parent_name required')
    return clean


def _target(bpy,name):
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('Object controls require Blender main thread')
    if bpy.context.mode!='OBJECT':raise ValueError('Object controls require Object Mode; no mode changed')
    obj=bpy.context.scene.objects.get(name)
    if obj is None or obj.type not in ('MESH','CURVE','FONT','EMPTY') or obj.mode!='OBJECT' or name not in bpy.context.view_layer.objects:
        raise ValueError('Modeling object must be an Object-mode member of the active scene/view layer')
    return obj


def inspect(bpy,name):
    obj=_target(bpy,name)
    if len(bpy.context.view_layer.objects)>10000:raise ValueError('Selection inspection exceeds object budget')
    active=bpy.context.view_layer.objects.active
    result={'name':obj.name,'type':obj.type,'parent':obj.parent.name if obj.parent else None,'parent_type':obj.parent_type,
            'matrix_world':[list(row) for row in obj.matrix_world],'matrix_basis':[list(row) for row in obj.matrix_basis],
            'matrix_parent_inverse':[list(row) for row in obj.matrix_parent_inverse],
            'selected':obj.select_get(),'selected_objects':sorted(o.name for o in bpy.context.view_layer.objects if o.select_get()),'active_object':active.name if active else None}
    result['snapshot_id']='sha256:'+hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return dict(result,success=True,verified=True)


def handle_inspect_modeling_object(bpy_module=None,params=None):return inspect(bpy_module,validate(params or {},inspection=True)['name'])


def _verify(bpy,name,expected):
    actual=inspect(bpy,name)
    if actual['snapshot_id']!=expected['snapshot_id']:raise RuntimeError('Object controls independent state readback mismatch')
    return actual


def handle_configure_modeling_object(bpy_module=None,params=None):
    bpy=bpy_module;params=params or {};clean=validate(params);obj=_target(bpy,clean['name'])
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok,reason=get_approval_registry().consume_approval(params.get('request_id'),params.get('approval_token'),'configure_modeling_object',params)
        if not ok:raise PermissionError('Object-control mutation denied: '+reason)
    if obj.library or obj.override_library or obj.animation_data or len(obj.constraints) or obj.parent_type!='OBJECT':
        raise ValueError('Controls require local unanimated, unconstrained object parenting')
    before=inspect(bpy,obj.name)
    if before['snapshot_id']!=clean['expected_snapshot_id']:raise ValueError('STALE_MODELING_OBJECT; inspect again')
    original={'parent':obj.parent,'basis':obj.matrix_basis.copy(),'inverse':obj.matrix_parent_inverse.copy(),
              'world':obj.matrix_world.copy(),'selection':[(o,o.select_get()) for o in bpy.context.view_layer.objects],
              'active':bpy.context.view_layer.objects.active}
    action=clean['action'];desired=None;parent=None
    if action=='transform':
        from mathutils import Matrix,Euler,Vector
        pivot=Vector(clean.get('pivot',[0,0,0]));translation=Matrix.Translation(clean.get('translation',[0,0,0]))
        rotation=Euler(clean.get('rotation',[0,0,0]),'XYZ').to_matrix().to_4x4()
        scale=Matrix.Diagonal([*clean.get('scale',[1,1,1]),1])
        delta=translation@Matrix.Translation(pivot)@rotation@scale@Matrix.Translation(-pivot)
        desired=original['world']@delta if clean.get('space','LOCAL')=='LOCAL' else delta@original['world']
        if obj.parent is not None and abs(obj.parent.matrix_world.determinant())<1e-12:raise ValueError('Singular parent transform is unsupported')
        # Blender decomposes object transforms; do not silently lose shear.
        basis=(obj.matrix_parent_inverse.inverted()@obj.parent.matrix_world.inverted()@desired) if obj.parent else desired
        location,quat,scaling=basis.decompose();reconstructed=Matrix.LocRotScale(location,quat,scaling)
        if not shader_values_match([list(row) for row in basis],[list(row) for row in reconstructed]):raise ValueError('Requested transform needs unsupported object shear')
    if action=='parent':
        parent=_target(bpy,clean['parent_name'])
        cursor=parent;seen=set()
        while cursor:
            if cursor==obj or cursor.as_pointer() in seen:raise ValueError('Parent relationship would create a cycle')
            seen.add(cursor.as_pointer());cursor=cursor.parent
        if parent.library or parent.override_library or abs(parent.matrix_world.determinant())<1e-12:raise ValueError('Parent must be local and nonsingular')
    try:
        if action=='transform':
            obj.matrix_world=desired;bpy.context.view_layer.update()
            if not shader_values_match([list(row) for row in obj.matrix_world],[list(row) for row in desired]):raise RuntimeError('Requested world transform readback mismatch')
        elif action in ('parent','clear_parent'):
            from mathutils import Matrix
            obj.parent=parent;obj.matrix_parent_inverse=parent.matrix_world.inverted() if parent else Matrix.Identity(4)
            obj.matrix_world=original['world'];bpy.context.view_layer.update()
            if obj.parent!=parent or not shader_values_match([list(row) for row in obj.matrix_world],[list(row) for row in original['world']]):raise RuntimeError('World-preserving parent readback mismatch')
        else:
            select_after_approval(bpy,{key:clean[key] for key in ('name','state','deselect_all','make_active') if key in clean})
        actual=_verify(bpy,obj.name,inspect(bpy,obj.name))
        return {**actual,'action':action,'transaction_status':'COMMITTED'}
    except Exception as error:
        try:
            obj.parent=original['parent'];obj.matrix_parent_inverse=original['inverse'];obj.matrix_basis=original['basis']
            for o,state in original['selection']:o.select_set(state)
            bpy.context.view_layer.objects.active=original['active'];bpy.context.view_layer.update()
            if inspect(bpy,obj.name)!=before:raise RuntimeError('Original object/context state differs')
        except Exception as restore_error:raise RuntimeError(f'ROLLBACK_UNVERIFIED: {restore_error}; original failure: {error}') from error
        raise RuntimeError(f'ROLLED_BACK_VERIFIED: {error}') from error

def select_after_approval(bpy,params):
    """Private shared selection transaction; authorization belongs to entrypoints."""
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('Selection requires Blender main thread')
    clean=tool_params({'type':'object','additionalProperties':False,'required':['name'],'properties':{'name':NAME,'state':{'type':'boolean'},'deselect_all':{'type':'boolean'},'make_active':{'type':'boolean'}}},params)
    if bpy.context.mode!='OBJECT':raise ValueError('Selection supports Object Mode only')
    obj=bpy.context.scene.objects.get(clean['name']);collection=bpy.context.view_layer.objects
    if obj is None or clean['name'] not in collection:raise ValueError('Selection target must be in active scene/view layer')
    objects=list(collection)
    if len(objects)>10000:raise ValueError('Selection exceeds object budget')
    before=[(o,o.select_get()) for o in objects];active=collection.active
    expected={o.name:False if clean.get('deselect_all',False) else state for o,state in before}
    expected[obj.name]=clean.get('state',True);expected_active=active
    if expected[obj.name] and clean.get('make_active',True):expected_active=obj
    elif not expected[obj.name] and not clean.get('make_active',True) and active==obj:expected_active=None
    try:
        for o,state in before:
            if (o==obj or clean.get('deselect_all',False)) and state!=expected[o.name]:o.select_set(expected[o.name])
        collection.active=expected_active
        if any(o.select_get()!=expected[o.name] for o,_ in before) or collection.active!=expected_active:raise RuntimeError('Selection/active-object readback mismatch')
        return {'name':obj.name,'state':expected[obj.name],'is_selected':obj.select_get(),
                'is_active':collection.active==obj,'active_object':collection.active.name if collection.active else None,
                'selected_objects':sorted(o.name for o,_ in before if o.select_get()),'success':True,'verified':True,
                'transaction_status':'COMMITTED','action':'select_object'}
    except Exception as error:
        try:
            for o,state in before:
                if o.select_get()!=state:o.select_set(state)
            collection.active=active
            if any(o.select_get()!=state for o,state in before) or collection.active!=active:raise RuntimeError('Original selection/context differs')
        except Exception as restore_error:raise RuntimeError(f'ROLLBACK_UNVERIFIED: {restore_error}; original failure: {error}') from error
        raise RuntimeError(f'ROLLED_BACK_VERIFIED: {error}') from error
