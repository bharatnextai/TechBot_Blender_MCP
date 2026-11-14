"""Bounded sculpt controls executed only by Blender's main-thread queue."""
import math
import threading
from .sculpt_contract import validate, SCULPT, INSPECT
from .mesh_topology import inspect_elements
from .approval_registry import get_approval_registry

def _main(bpy):
    if threading.current_thread() is not threading.main_thread(): raise RuntimeError("Sculpt tools require Blender main thread")

def _active(bpy,obj):
    for selected in list(bpy.context.selected_objects): selected.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj

def _mode(bpy,mode):
    if bpy.context.mode!=mode:
        target={"OBJECT":"OBJECT","SCULPT":"SCULPT"}.get(mode)
        if target is None: raise ValueError("Only Object and Sculpt modes are supported")
        if not bpy.ops.object.mode_set.poll(): raise RuntimeError(f"Cannot enter {target} mode in current Blender context")
        result=bpy.ops.object.mode_set(mode=target)
        if "FINISHED" not in result or bpy.context.mode!=mode: raise RuntimeError(f"Blender did not enter {target} mode")

def _snapshot(bpy,obj):
    was_sculpt=bpy.context.mode=="SCULPT"
    if was_sculpt:_mode(bpy,"OBJECT")
    try:return inspect_elements(obj,bpy.context,{"element_domain":"vertices","limit":1})
    finally:
        if was_sculpt:_mode(bpy,"SCULPT")

def inspect(bpy,params):
    _main(bpy);clean=validate(params,inspection=True);obj=bpy.context.scene.objects.get(clean["object_name"])
    if obj is None or obj.type!="MESH": raise ValueError("An active-scene mesh is required")
    result=_snapshot(bpy,obj)
    sculpt=bpy.context.scene.tool_settings.sculpt
    brush=getattr(sculpt,"brush",None)
    return {"success":True,"verified":True,"object_name":obj.name,"mode":obj.mode,
        "snapshot_id":result["snapshot_id"],"state_id":result["state_id"],"topology_source":result["topology_source"],
        "vertex_count":result["vertex_count"],"edge_count":result["edge_count"],"face_count":result["polygon_count"],
        "dyntopo_enabled":bool(obj.use_dynamic_topology_sculpting),
        "brush":({"name":brush.name,"size":int(brush.size),"strength":float(brush.strength)} if brush else None),
        "voxel_size":float(obj.data.remesh_voxel_size)}

def _activate_brush(bpy, sculpt, target_brush_or_name):
    if not target_brush_or_name:
        return False
    name = target_brush_or_name if isinstance(target_brush_or_name, str) else getattr(target_brush_or_name, "name", str(target_brush_or_name))
    if sculpt.brush and sculpt.brush.name == name:
        return True
    try:
        res = bpy.ops.brush.asset_activate(
            asset_library_type='ESSENTIALS',
            relative_asset_identifier=f'brushes/essentials_brushes-mesh_sculpt.blend/Brush/{name}'
        )
        if "FINISHED" in res and sculpt.brush and sculpt.brush.name == name:
            return True
    except Exception:
        pass
    brush = bpy.data.brushes.get(name)
    if brush:
        try:
            if not getattr(brush, "asset_data", None):
                brush.asset_mark()
            res = bpy.ops.brush.asset_activate(
                asset_library_type='LOCAL',
                relative_asset_identifier=f'Brush/{brush.name}'
            )
            if "FINISHED" in res and sculpt.brush and sculpt.brush.name == name:
                return True
        except Exception:
            pass
    if brush and getattr(brush, "use_paint_sculpt", False):
        try:
            sculpt.brush = brush
            if sculpt.brush and sculpt.brush.name == name:
                return True
        except Exception:
            pass
    return bool(sculpt.brush and sculpt.brush.name == name)

def _view3d_override(bpy,obj):
    wm=bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type=="VIEW_3D":
                region=next((r for r in area.regions if r.type=="WINDOW"),None)
                if region:return bpy.context.temp_override(window=window,area=area,region=region,active_object=obj,object=obj)
    raise RuntimeError("Sculpt stroke requires a usable Blender VIEW_3D window context")

def handle_sculpt_mesh(bpy_module=None,params=None):
    bpy=bpy_module;_main(bpy);clean=validate(params or {})
    if clean.get("action") in ("sculpt_organic_anatomy", "organic_anatomy"):
        from .handlers import handle_sculpt_organic_anatomy
        return handle_sculpt_organic_anatomy(bpy_module=bpy, params=params)
    if clean.get("action") in ("detail_surface_features", "surface_detail"):
        from .handlers import handle_detail_surface_features
        return handle_detail_surface_features(bpy_module=bpy, params=params)
    if clean.get("action") in ("symmetrize_mesh_geometry", "symmetrize"):
        from .handlers import handle_symmetrize_mesh_geometry
        return handle_symmetrize_mesh_geometry(bpy_module=bpy, params=params)
    obj=bpy.context.scene.objects.get(clean["object_name"])
    if obj is None or obj.type!="MESH" or obj.library or obj.data.library or obj.data.shape_keys or obj.data.animation_data:
        raise ValueError("Sculpt mutation requires a local, unanimated mesh without shape keys")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok,reason=get_approval_registry().consume_approval(params.get("request_id"),params.get("approval_token"),SCULPT,params)
        if not ok:raise PermissionError("Sculpt mutation denied: "+reason)
    original_mode=bpy.context.mode;original_active=bpy.context.view_layer.objects.active
    if original_mode=="SCULPT" and original_active is not obj:raise ValueError("Sculpt target must already be the active sculpt object")
    selected=list(bpy.context.selected_objects);original_data=obj.data;stage=None;action=clean["action"];geometry=action in {"stroke","voxel_remesh","set_dyntopo"}
    sculpt_settings=bpy.context.scene.tool_settings.sculpt;old_brush=getattr(sculpt_settings,"brush",None)
    old_detail=(sculpt_settings.detail_type_method,sculpt_settings.detail_size,obj.use_dynamic_topology_sculpting) if sculpt_settings else None
    old_brush_values={}
    if old_brush:
        old_brush_values={key:getattr(old_brush,key) for key in ("size","strength","use_frontface","use_accumulate","use_pressure_size","use_pressure_strength")}
    try:
        _active(bpy,obj)
        if bpy.context.mode not in {"OBJECT","SCULPT"}:raise ValueError("Sculpt tools support Object or Sculpt mode only")
        before=_snapshot(bpy,obj)
        if before["snapshot_id"]!=clean["expected_snapshot_id"]:raise ValueError("STALE_SCULPT_SNAPSHOT; inspect again")
        if geometry:
            if original_data.users>1:raise ValueError("Geometry sculpt operations reject shared mesh datablocks")
            if bpy.context.mode=="SCULPT":_mode(bpy,"OBJECT")
            stage=original_data.copy();obj.data=stage
            if action in {"stroke","set_dyntopo"}:_mode(bpy,"SCULPT")
        if action=="enter_sculpt":_mode(bpy,"SCULPT")
        elif action=="exit_sculpt":_mode(bpy,"OBJECT")
        elif action in {"set_brush","set_brush_settings"}:
            if bpy.context.mode!="SCULPT":raise ValueError("Brush operations require Sculpt Mode")
            sculpt=bpy.context.scene.tool_settings.sculpt;brush=sculpt.brush
            if action=="set_brush":
                brush_name=clean["brush_name"]
                ok=_activate_brush(bpy,sculpt,brush_name)
                if not ok or sculpt.brush is None or sculpt.brush.name!=brush_name:
                    raise ValueError(f"Named sculpt brush '{brush_name}' is unavailable")
            else:
                if brush is None:raise ValueError("No active sculpt brush")
                for key,value in clean["settings"].items():
                    setattr(brush,key,value)
                    val = getattr(brush, key)
                    if isinstance(value, float):
                        if not math.isclose(val, value, rel_tol=1e-4, abs_tol=1e-4):
                            raise RuntimeError("Brush setting readback failed: "+key)
                    elif val != value:
                        raise RuntimeError("Brush setting readback failed: "+key)
        elif action=="stroke":
            if bpy.context.mode!="SCULPT":raise ValueError("Stroke execution requires Sculpt Mode")
            override=_view3d_override(bpy,obj)
            with override:
                from bpy_extras import view3d_utils
                area=bpy.context.area;region=next(r for r in area.regions if r.type=="WINDOW")
                r3d=area.spaces.active.region_3d
                points=clean["points"]
                stroke=[]
                brush=sculpt_settings.brush
                bsize=float(getattr(brush,"size",50.0)) if brush else 50.0
                mat_inv = obj.matrix_world.inverted()
                for i,p in enumerate(points):
                    x=float(round(p["x"]*max(1,region.width-1)))
                    y=float(round(p["y"]*max(1,region.height-1)))
                    origin = view3d_utils.region_2d_to_origin_3d(region, r3d, (x, y))
                    direction = view3d_utils.region_2d_to_vector_3d(region, r3d, (x, y))
                    ray_origin = mat_inv @ origin
                    ray_dir = mat_inv.to_3x3() @ direction
                    hit, hit_loc, normal, index = obj.ray_cast(ray_origin, ray_dir)
                    loc_3d = (obj.matrix_world @ hit_loc) if hit else (origin[0] + direction[0] * 100.0, origin[1] + direction[1] * 100.0, origin[2] + direction[2] * 100.0)
                    stroke.append({
                        "name":"stroke",
                        "location":(float(loc_3d[0]),float(loc_3d[1]),float(loc_3d[2])),
                        "mouse":(x,y),
                        "mouse_event":(x,y),
                        "pressure":float(p.get("pressure",1.0)),
                        "size":bsize,
                        "x_tilt":0.0,
                        "y_tilt":0.0,
                        "time":float(i/60.0),
                        "is_start":bool(i==0)
                    })
                result=bpy.ops.sculpt.brush_stroke(stroke=stroke)
                if "FINISHED" not in result:raise RuntimeError("Blender sculpt stroke did not finish")
        elif action=="voxel_remesh":
            if bpy.context.mode!="OBJECT":raise ValueError("Voxel remesh requires Object Mode")
            obj.data.remesh_voxel_size=clean["voxel_size"]
            if not math.isclose(obj.data.remesh_voxel_size, clean["voxel_size"], rel_tol=1e-4, abs_tol=1e-4):
                raise RuntimeError("Voxel size readback mismatch")
            if not bpy.ops.object.voxel_remesh.poll():raise RuntimeError("Voxel remesh is unavailable in current context")
            if "FINISHED" not in bpy.ops.object.voxel_remesh():raise RuntimeError("Voxel remesh did not finish")
        elif action=="set_dyntopo":
            if bpy.context.mode!="SCULPT":raise ValueError("Dynamic topology controls require Sculpt Mode")
            sculpt=bpy.context.scene.tool_settings.sculpt
            if "detail_mode" in clean:sculpt.detail_type_method=clean["detail_mode"].upper()
            if "detail_size" in clean:sculpt.detail_size=clean["detail_size"]
            current=bool(obj.use_dynamic_topology_sculpting)
            if current!=clean["enabled"]:
                if not bpy.ops.sculpt.dynamic_topology_toggle.poll():raise RuntimeError("Dynamic topology toggle unavailable in current context")
                if "FINISHED" not in bpy.ops.sculpt.dynamic_topology_toggle():raise RuntimeError("Dynamic topology toggle did not finish")
            if bool(obj.use_dynamic_topology_sculpting)!=clean["enabled"]:raise RuntimeError("Dynamic topology state readback mismatch")
        if geometry:
            if bpy.context.mode=="SCULPT":_mode(bpy,"OBJECT")
            after=_snapshot(bpy,obj)
            if action in {"stroke","voxel_remesh"} and after["snapshot_id"]==before["snapshot_id"]:
                raise RuntimeError("Sculpt operation produced no verified mesh change")
        desired_mode="SCULPT" if action=="enter_sculpt" else "OBJECT" if action=="exit_sculpt" else original_mode
        if bpy.context.mode!=desired_mode:_mode(bpy,desired_mode)
        after=_snapshot(bpy,obj)
        sculpt_settings=bpy.context.scene.tool_settings.sculpt
        result={"success":True,"verified":True,"action":action,"object_name":obj.name,"mode":obj.mode,
            "before_snapshot_id":before["snapshot_id"],"snapshot_id":after["snapshot_id"],"state_id":after["state_id"],
            "topology_source":after["topology_source"],"vertex_count":after["vertex_count"],"edge_count":after["edge_count"],"face_count":after["polygon_count"],
            "dyntopo_enabled":bool(obj.use_dynamic_topology_sculpting),"brush":{"name":sculpt_settings.brush.name,"size":int(sculpt_settings.brush.size),"strength":float(sculpt_settings.brush.strength)} if sculpt_settings and sculpt_settings.brush else None,
            "voxel_size":float(obj.data.remesh_voxel_size),"transaction_status":"COMMITTED" if geometry else "VERIFIED"}
        return result
    except Exception as error:
        try:
            if bpy.context.mode=="SCULPT":_mode(bpy,"OBJECT")
            if old_brush is not None:
                _activate_brush(bpy,sculpt_settings,old_brush)
                for key,value in old_brush_values.items():setattr(old_brush,key,value)
            if stage is not None and obj.data==stage:obj.data=original_data
            if old_detail is not None:
                sculpt_settings.detail_type_method,sculpt_settings.detail_size=old_detail[:2]
            if old_detail is not None and bool(obj.use_dynamic_topology_sculpting)!=bool(old_detail[2]):
                _mode(bpy,"SCULPT")
                if not bpy.ops.sculpt.dynamic_topology_toggle.poll():raise RuntimeError("Cannot restore dynamic-topology state")
                bpy.ops.sculpt.dynamic_topology_toggle()
                _mode(bpy,"OBJECT")
            if stage is not None and stage.users==0:bpy.data.meshes.remove(stage)
            if obj.data!=original_data:raise RuntimeError("Original mesh data identity was not restored")
        except Exception as restore_error:raise RuntimeError(f"SCULPT_ROLLBACK_UNVERIFIED: {restore_error}; original error: {error}") from error
        raise RuntimeError(f"SCULPT_OPERATION_FAILED: {error}") from error
    finally:
        if original_active is not None and bpy.data.objects.get(original_active.name)==original_active:bpy.context.view_layer.objects.active=original_active
        for selected_obj in list(bpy.context.selected_objects):selected_obj.select_set(False)
        for selected_obj in selected:
            if bpy.data.objects.get(selected_obj.name)==selected_obj:selected_obj.select_set(True)
        if action not in {"enter_sculpt","exit_sculpt"} and bpy.context.mode!=original_mode:
            _mode(bpy,original_mode)

def handle_inspect_sculpt_state(bpy_module=None,params=None):return inspect(bpy_module,params or {})
