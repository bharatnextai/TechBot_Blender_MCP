"""Finite transactional Geometry Nodes graph specification and output inspection."""
import hashlib,json
from .geometry_contract import NODE_INPUTS,validate
from .modifier_tools import _target
from .modifier_stack import _geometry
from .shader_values import shader_value,shader_values_match
from .modifier_checkpoint import _custom
from .approval_registry import get_approval_registry

SOCKET_TYPES={'FLOAT':'NodeSocketFloat','INT':'NodeSocketInt','VECTOR':'NodeSocketVector','BOOLEAN':'NodeSocketBool'}


def _inputs(mod):
    """Blender 5.2 typed interface; older versions use ID properties."""
    properties=getattr(mod,'properties',None)
    return getattr(properties,'inputs',None) if properties is not None else None


def _parameter_value(mod,identifier):
    inputs=_inputs(mod)
    return shader_value(getattr(inputs,identifier).value) if inputs is not None else shader_value(mod.get(identifier))


def _capture_parameters(mod):
    inputs=_inputs(mod)
    if inputs is None:return {'legacy':_custom(mod)}
    result={}
    if mod.node_group:
        for item in mod.node_group.interface.items_tree:
            if item.item_type=='SOCKET' and item.in_out=='INPUT' and item.socket_type!='NodeSocketGeometry':
                holder=getattr(inputs,item.identifier)
                result[item.identifier]={prop.identifier:shader_value(getattr(holder,prop.identifier))
                                         for prop in holder.bl_rna.properties if not prop.is_readonly}
    return {'typed':result}


def _restore_parameters(mod,saved):
    if 'legacy' in saved:
        for key in list(mod.keys()):del mod[key]
        for key,value in (saved['legacy'] or {}).items():mod[key]=value
    else:
        inputs=_inputs(mod)
        for identifier,values in saved['typed'].items():
            holder=getattr(inputs,identifier)
            for key,value in values.items():setattr(holder,key,value)
    if _capture_parameters(mod)!=saved:raise RuntimeError('Geometry parameter restoration readback mismatch')


def _socket(node,key,output=False):
    sockets=node.outputs if output else node.inputs
    matches=[s for s in sockets if (s.name if node.bl_idname in ('NodeGroupInput','NodeGroupOutput') else s.identifier)==key]
    if len(matches)!=1 or matches[0].is_unavailable or not matches[0].enabled:raise ValueError('Unknown/ambiguous/unavailable socket: '+node.name+'.'+key)
    return matches[0]


def inspect(bpy,name,modifier_name):
    obj=_target(bpy,{'name':name})
    if bpy.context.mode!='OBJECT' or obj.mode!='OBJECT':raise ValueError('Geometry graph inspection requires Object Mode')
    mod=obj.modifiers.get(modifier_name)
    if mod is not None and mod.type!='NODES':raise ValueError('Requested modifier is not Geometry Nodes')
    group=mod.node_group if mod else None
    result={'name':obj.name,'modifier_name':modifier_name,'group_name':group.name if group else None,
            'stack':[{'name':m.name,'type':m.type,'show_viewport':m.show_viewport,'show_render':m.show_render} for m in obj.modifiers],
            'base':_geometry(obj,bpy.context,'base'),'evaluated':_geometry(obj,bpy.context,'evaluated'),'nodes':[],'links':[],'parameters':[]}
    if group:
        if len(group.nodes)>34 or len(group.links)>64 or len(group.interface.items_tree)>18:raise ValueError('Geometry graph inspection budget exceeded')
        for node in sorted(group.nodes,key=lambda n:n.name):
            supported=node.bl_idname in NODE_INPUTS or node.bl_idname in ('NodeGroupInput','NodeGroupOutput')
            inputs={key:shader_value(_socket(node,key).default_value) for key in NODE_INPUTS.get(node.bl_idname,{})}
            result['nodes'].append({'name':node.name,'type':node.bl_idname,'supported':supported,'inputs':inputs,
                                   'input_sockets':[{'name':s.name,'identifier':s.identifier,'type':s.type} for s in node.inputs],
                                   'output_sockets':[{'name':s.name,'identifier':s.identifier,'type':s.type} for s in node.outputs]})
        for link in group.links:
            result['links'].append({'from_node':link.from_node.name,'from_socket':link.from_socket.identifier,
                                    'to_node':link.to_node.name,'to_socket':link.to_socket.identifier,
                                    'multi_input_sort_id':link.multi_input_sort_id,'valid':link.is_valid})
        result['links'].sort(key=lambda l:(l['to_node'],l['to_socket'],l['multi_input_sort_id'],l['from_node'],l['from_socket']))
        for item in group.interface.items_tree:
            if item.item_type=='SOCKET':
                entry={'name':item.name,'identifier':item.identifier,'direction':item.in_out,'type':item.socket_type}
                if item.socket_type!='NodeSocketGeometry':
                    entry['default']=shader_value(item.default_value)
                    entry['modifier_value']=_parameter_value(mod,item.identifier) if item.in_out=='INPUT' else None
                    if item.in_out=='INPUT' and _inputs(mod) is not None:
                        entry['mode']=getattr(_inputs(mod),item.identifier).type
                result['parameters'].append(entry)
    result['snapshot_id']='sha256:'+hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return dict(result,success=True,verified=True)


def handle_inspect_modeling_geometry(bpy_module=None,params=None):
    clean=validate(params or {},inspection=True)
    return inspect(bpy_module,clean['name'],clean['modifier_name'])


def _build(group,clean):
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    parameters=[]
    for spec in clean.get('parameters',[]):
        item=group.interface.new_socket(name=spec['name'],in_out='INPUT',socket_type=SOCKET_TYPES[spec['type']])
        item.default_value=spec['value']
        if not shader_values_match(item.default_value,spec['value']):raise RuntimeError('Geometry interface default readback mismatch')
        parameters.append((item.identifier,spec['value']))
    inp=group.nodes.new('NodeGroupInput');inp.name='Input'
    out=group.nodes.new('NodeGroupOutput');out.name='Output';out.is_active_output=True
    for spec in clean['nodes']:
        node=group.nodes.new(spec['type']);node.name=spec['name']
        if node.name!=spec['name']:raise RuntimeError('Geometry node exact-name readback mismatch')
        if spec['type']=='GeometryNodeTransform':
            _socket(node,'Mode').default_value='Components'
        if spec['type']=='GeometryNodeSetShadeSmooth':node.domain='FACE'
        for key,value in spec.get('inputs',{}).items():
            sock=_socket(node,key);sock.default_value=value
            if not shader_values_match(sock.default_value,value):raise RuntimeError('Geometry node input readback mismatch: '+key)
    occupied=set()
    assigned={(node['name'],key) for node in clean['nodes'] for key in node.get('inputs',{})}
    for spec in clean['links']:
        source=_socket(group.nodes[spec['from_node']],spec['from_socket'],True)
        target=_socket(group.nodes[spec['to_node']],spec['to_socket'])
        if source.type!=target.type:raise ValueError('Implicit socket type conversions are unsupported')
        key=(spec['to_node'],spec['to_socket'])
        if key in assigned:raise ValueError('A linked input cannot also request a literal assignment')
        if key in occupied and not target.is_multi_input:raise ValueError('Multiple links to a single input are forbidden')
        occupied.add(key);group.links.new(source,target)
    if len(group.links)!=len(clean['links']) or any(not link.is_valid for link in group.links):raise RuntimeError('Geometry link readback mismatch')
    return parameters


def _verify(bpy,obj,modifier_name,expected):
    actual=inspect(bpy,obj.name,modifier_name)
    if actual['snapshot_id']!=expected['snapshot_id']:raise RuntimeError('Geometry graph/evaluated output readback mismatch')
    return actual


def handle_configure_modeling_geometry(bpy_module=None,params=None):
    bpy=bpy_module;params=params or {};clean=validate(params);obj=_target(bpy,clean)
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok,reason=get_approval_registry().consume_approval(params.get('request_id'),params.get('approval_token'),'configure_modeling_geometry',params)
        if not ok:raise PermissionError('Geometry graph mutation denied: '+reason)
    if bpy.context.mode!='OBJECT' or obj.mode!='OBJECT' or obj.library or obj.override_library or obj.data.library or obj.animation_data or obj.data.animation_data or obj.data.shape_keys:
        raise ValueError('Geometry transactions require local unanimated Object-mode mesh without shape keys')
    mod=obj.modifiers.get(clean['modifier_name']);old_group=mod.node_group if mod and mod.type=='NODES' else None
    if clean['action']=='create' and mod is not None:raise ValueError('Modifier name already exists')
    if clean['action']=='update' and (mod is None or mod.type!='NODES' or old_group is None):raise ValueError('Existing Geometry Nodes group required')
    before=inspect(bpy,obj.name,clean['modifier_name'])
    if 'expected_snapshot_id' in clean and before['snapshot_id']!=clean['expected_snapshot_id']:raise ValueError('STALE_MODELING_GEOMETRY; inspect again')
    if old_group and (old_group.library or old_group.animation_data or any(not n['supported'] for n in before['nodes'])):raise ValueError('Existing group is outside finite editable contract')
    collision=bpy.data.node_groups.get(clean['group_name'])
    if collision is not None and collision!=old_group:raise ValueError('Group name already exists')
    if old_group and collision==old_group and old_group.users>1:raise ValueError('Shared source group requires a distinct new group_name')
    old_name=old_group.name if old_group else None;old_props=_capture_parameters(mod) if mod else None
    old_active=obj.modifiers.active;old_active_name=old_active.name if old_active else None
    inventory=set(bpy.data.node_groups.keys());original_mesh=obj.data
    group=None;created=False
    try:
        if old_group and collision==old_group:old_group.name=old_name+'_UMCP_CHECKPOINT'
        group=bpy.data.node_groups.new(clean['group_name'],'GeometryNodeTree')
        if group.name!=clean['group_name']:raise RuntimeError('Geometry group exact-name readback mismatch')
        parameter_values=_build(group,clean)
        if mod is None:
            mod=obj.modifiers.new(clean['modifier_name'],'NODES');created=True
            if mod.name!=clean['modifier_name']:raise RuntimeError('Geometry modifier exact-name readback mismatch')
        if old_group and _inputs(mod) is None:
            for item in old_group.interface.items_tree:
                if item.item_type=='SOCKET' and item.in_out=='INPUT':
                    for key in (item.identifier,item.identifier+'_use_attribute',item.identifier+'_attribute_name'):
                        if key in mod:del mod[key]
        mod.node_group=group
        for identifier,value in parameter_values:
            inputs=_inputs(mod)
            if inputs is not None:
                holder=getattr(inputs,identifier);holder.type='VALUE';holder.value=value
                if holder.type!='VALUE':raise RuntimeError('Geometry parameter mode readback mismatch')
            else:mod[identifier]=value
            if not shader_values_match(_parameter_value(mod,identifier),value):raise RuntimeError('Geometry modifier parameter readback mismatch')
        obj.update_tag();bpy.context.view_layer.update()
        actual=_verify(bpy,obj,clean['modifier_name'],inspect(bpy,obj.name,clean['modifier_name']))
        if obj.data!=original_mesh or actual['base']!=before['base']:raise RuntimeError('Geometry graph changed original mesh data')
        result={**actual,'action':clean['action'],'transaction_status':'COMMITTED'}
        if old_group and old_group.users==0:bpy.data.node_groups.remove(old_group)
        return result
    except Exception as error:
        try:
            if created:obj.modifiers.remove(mod)
            elif mod is not None:
                mod.node_group=old_group
                _restore_parameters(mod,old_props)
            if group is not None and group.users==0:bpy.data.node_groups.remove(group)
            if old_group:old_group.name=old_name
            obj.modifiers.active=obj.modifiers.get(old_active_name) if old_active_name else None
            obj.update_tag();bpy.context.view_layer.update()
            if obj.data!=original_mesh or inspect(bpy,obj.name,clean['modifier_name'])!=before or inventory!=set(bpy.data.node_groups.keys()):raise RuntimeError('Original graph/mesh/inventory differs')
        except Exception as restore_error:raise RuntimeError(f'ROLLBACK_UNVERIFIED: {restore_error}; original failure: {error}') from error
        raise RuntimeError(f'ROLLED_BACK_VERIFIED: {error}') from error
