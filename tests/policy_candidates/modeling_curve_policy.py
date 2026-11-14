"""Detached curve/text TEST HOST scope; production never imports this module."""
from blender_addon.universal_mcp.bridge.curve_contract import validate


def _same(a,b):return a is b or (a is not None and b is not None and a.as_pointer()==b.as_pointer())


def authorizes(bpy,tool,params,owned,planned):
    try:
        if tool!='configure_curve_geometry' or params!=planned or params.get('approved',False) is not False:return False
        if any(k in params for k in ('trusted_approval','_trusted_test_override','request_id','approval_token','task_id','session_id','correlation_id')):return False
        clean=validate(params)
        from blender_addon.universal_mcp.bridge.handlers import _local_test_autoapproval
        if not _local_test_autoapproval(bpy,'transform_object',{'name':clean['name'],'location':[0,0,0]}):return False
        if clean['name'] not in owned:return False
        obj=bpy.context.scene.objects.get(clean['name']);record=owned[clean['name']]
        if clean['action']=='create':
            if record!=(None,None) or obj is not None or bpy.data.objects.get(clean['name']) is not None or bpy.data.curves.get(clean['name']) is not None:return False
        else:
            if obj is None or not _same(obj,record[0]) or not _same(obj.data,record[1]):return False
            if obj.type not in ('CURVE','FONT') or obj.mode!='OBJECT' or obj.data.users!=1 or obj.library or obj.override_library or obj.data.library or obj.animation_data or obj.data.animation_data or obj.data.shape_keys or len(obj.modifiers)!=0:return False
        if clean['action']=='copy_to_mesh':
            output=clean['output_name']
            if output not in owned or owned[output]!=(None,None) or bpy.data.objects.get(output) is not None:return False
        settings=clean.get('settings',{})
        if settings.get('extrude',0)>.1 or settings.get('bevel_depth',0)>.1 or settings.get('resolution_u',1)>12 or settings.get('bevel_resolution',0)>2 or settings.get('size',1)>2 or len(settings.get('body',''))>32:return False
        splines=clean.get('splines',[])
        if len(splines)>4 or sum(len(s['points']) for s in splines)>128:return False
        for spline in splines:
            for point in spline['points']:
                for key in ('co','handle_left','handle_right'):
                    if any(abs(x)>3 for x in point.get(key,[])):return False
                if point.get('weight',1)>2 or point.get('radius',1)>2 or abs(point.get('tilt',0))>3.142:return False
        return True
    except (AttributeError,TypeError,ValueError,KeyError,ReferenceError):return False
