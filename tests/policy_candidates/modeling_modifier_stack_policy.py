"""Detached extended modifier TEST HOST scope; production never imports this."""
from blender_addon.universal_mcp.bridge.advanced_modifier_contract import validate


def _same(a,b):
    return a is b or (a is not None and b is not None and a.as_pointer()==b.as_pointer())


def authorizes(bpy, tool, params, owned, planned):
    try:
        if tool != 'edit_modifier_stack' or params != planned:return False
        if params.get('approved',False) is not False:return False
        if any(k in params for k in ('trusted_approval','request_id','approval_token','task_id','session_id','correlation_id')):return False
        clean=validate(params)
        from blender_addon.universal_mcp.bridge.handlers import _local_test_autoapproval
        if not _local_test_autoapproval(bpy,'transform_object',{'name':clean['name'],'location':[0,0,0]}):return False
        obj=bpy.context.scene.objects.get(clean['name']);record=owned.get(clean['name'])
        if not record or not _same(obj,record[0]) or not _same(obj.data,record[1]) or obj.data.users!=1:return False
        if obj.type!='MESH' or obj.mode!='OBJECT' or bpy.context.mode!='OBJECT' or obj.library or obj.data.library or obj.override_library or obj.animation_data or obj.data.animation_data or obj.data.shape_keys:return False
        if len(obj.data.vertices)>1000 or len(obj.data.edges)>2000 or len(obj.data.polygons)>1000 or len(obj.modifiers)>8:return False
        if any(m.name not in record[2] or not _same(m,record[2][m.name]) for m in obj.modifiers):return False
        if clean['action']=='add' and obj.modifiers.get(clean['modifier_name']) is not None:return False
        if clean['action']!='add' and (obj.modifiers.get(clean['modifier_name']) is None or not _same(obj.modifiers.get(clean['modifier_name']),record[2].get(clean['modifier_name']))):return False
        props=clean.get('properties',{})
        if any(props.get(k,0)>2 for k in ('levels','render_levels','count')) or props.get('segments',1)>3:return False
        if abs(props.get('thickness',0))>.1 or props.get('width',0)>.1 or props.get('merge_threshold',0)>.001:return False
        if any(abs(x)>2 for key in ('relative_offset_displace','constant_offset_displace') for x in props.get(key,[])):return False
        if 'operand_name' in props:
            other=bpy.context.scene.objects.get(props['operand_name']);other_record=owned.get(props['operand_name'])
            if not other_record or not _same(other,other_record[0]) or not _same(other.data,other_record[1]) or other==obj or other.type!='MESH' or other.data.users!=1 or other.library or other.data.library or other.mode!='OBJECT' or len(other.modifiers)!=0:return False
            if len(other.data.vertices)>1000 or len(other.data.edges)>2000 or len(other.data.polygons)>1000:return False
        return True
    except (AttributeError,TypeError,ValueError,KeyError,ReferenceError):return False
