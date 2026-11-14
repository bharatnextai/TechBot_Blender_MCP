"""Detached final modeling TEST HOST additions; production never imports this."""
from blender_addon.universal_mcp.bridge.object_controls import validate as validate_control
from blender_addon.universal_mcp.bridge.geometry_contract import validate as validate_graph


def _same(a,b):return a is b or (a is not None and b is not None and a.as_pointer()==b.as_pointer())


def authorizes(bpy,tool,params,owned,groups,planned):
    try:
        if tool not in ('configure_modeling_object','configure_modeling_geometry') or params!=planned or params.get('approved',False) is not False:return False
        if any(k in params for k in ('trusted_approval','_trusted_test_override','request_id','approval_token','task_id','session_id','correlation_id')):return False
        clean=(validate_control if tool=='configure_modeling_object' else validate_graph)(params)
        from blender_addon.universal_mcp.bridge.handlers import _local_test_autoapproval
        if not _local_test_autoapproval(bpy,'transform_object',{'name':clean['name'],'location':[0,0,0]}):return False
        if bpy.context.mode!='OBJECT' or len(owned)>8 or len(bpy.context.view_layer.objects)>32:return False
        obj=bpy.context.scene.objects.get(clean['name']);record=owned.get(clean['name'])
        if not record or not _same(obj,record[0]) or not _same(obj.data,record[1]):return False
        if obj.type!='MESH' or obj.mode!='OBJECT' or obj.library or obj.override_library or obj.animation_data or len(obj.constraints) or obj.data.library or obj.data.animation_data or obj.data.shape_keys or obj.data.users!=1:return False
        if len(obj.data.vertices)>1000 or len(obj.data.edges)>2000 or len(obj.data.polygons)>1000:return False
        if tool=='configure_modeling_object':
            if any(abs(x)>2 for x in clean.get('translation',[])) or any(abs(x)>3.142 for x in clean.get('rotation',[])) or any(abs(x)>3 for x in clean.get('pivot',[])) or any(not .5<=x<=2 for x in clean.get('scale',[])):return False
            if clean.get('deselect_all',False) and any(o.name not in owned for o in bpy.context.selected_objects):return False
            if clean['action']=='parent':
                other=bpy.context.scene.objects.get(clean['parent_name']);other_record=owned.get(clean['parent_name'])
                if not other_record or not _same(other,other_record[0]) or not _same(other.data,other_record[1]) or other==obj:return False
            return True
        if len(clean['nodes'])>8 or len(clean['links'])>16 or len(clean.get('parameters',[]))>4:return False
        if len(obj.modifiers)>1:return False
        mod=obj.modifiers.get(clean['modifier_name'])
        if clean['action']=='create':
            if mod is not None or len(obj.modifiers)!=0 or bpy.data.node_groups.get(clean['group_name']) is not None:return False
        else:
            entry=groups.get((obj.name,clean['modifier_name']))
            if not entry or not _same(mod,entry[0]) or not _same(mod.node_group,entry[1]) or mod.node_group.users!=1 or mod.node_group.library or mod.node_group.animation_data:return False
        for node in clean['nodes']:
            for key,value in node.get('inputs',{}).items():
                if isinstance(value,list):
                    bound=3.142 if key=='Rotation' else 2
                    if any(abs(x)>bound for x in value):return False
                    if key=='Scale' and any(not .5<=x<=2 for x in value):return False
                elif key.startswith('Vertices ') and value>4:return False
                elif type(value) in (int,float) and abs(value)>4:return False
        for parameter in clean.get('parameters',[]):
            value=parameter['value']
            if isinstance(value,list) and any(abs(x)>2 for x in value):return False
            if type(value) in (int,float) and abs(value)>4:return False
        return True
    except (AttributeError,TypeError,ValueError,KeyError,ReferenceError):return False
