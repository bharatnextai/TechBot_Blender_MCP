"""Detached TEST HOST proposal. Not imported or activated by production code."""
from blender_addon.universal_mcp.bridge.component_edit import validate


def authorizes(bpy,tool,params,owned):
    try:
        if tool!="edit_mesh" or any(k in params for k in ("trusted_approval","_trusted_test_override","request_id","approval_token","session_id","correlation_id","task_id")) or params.get("approved",False) is not False:return False
        from blender_addon.universal_mcp.bridge.handlers import _local_test_autoapproval
        clean=validate(params)
        # Reuse all existing background/fresh-root/user-directory/port/scene guards.
        # This does not change the production policy or authorize transform execution.
        if not _local_test_autoapproval(bpy,"transform_object",{"name":clean["name"],"location":[0,0,0]}):return False
        obj=bpy.context.scene.objects.get(clean["name"])
        recorded=owned.get(clean["name"])
        if not recorded or obj is not recorded[0] or obj.data is not recorded[1] or obj.type!="MESH" or obj.data.users!=1 or len(obj.modifiers)!=0:return False
        if bpy.context.mode!="OBJECT" or obj.data.shape_keys or getattr(obj,"library",None) or getattr(obj.data,"library",None):return False
        if len(obj.data.vertices)>10000 or len(obj.data.edges)>20000 or len(obj.data.polygons)>10000:return False
        if len(clean["operations"])>8:return False
        for op in clean["operations"]:
            if any(len(op.get(key,[]))>256 for key in ("vertices","edges","faces","points","edge_pairs","face_cycles")):return False
            if any(abs(x)>10 for point in op.get("points",[]) for x in point):return False
            if any(abs(x)>2 for x in op.get("delta",[])):return False
            if op.get("width",0)>.1 or op.get("thickness",0)>.2 or op.get("cuts",1)>2 or op.get("segments",1)>3 or op.get("proportional_radius",0)>2 or op.get("grid_size",0)>2 or op.get("threshold",0)>.001:return False
        return True
    except (ValueError,TypeError,AttributeError,KeyError):return False
