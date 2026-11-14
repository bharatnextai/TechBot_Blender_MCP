"""Finite, fail-closed sculpt operation contract."""
import math
import re

SCULPT="sculpt_mesh"
INSPECT="inspect_sculpt_state"
_SNAPSHOT=re.compile(r"^sha256:[0-9a-f]{64}$")
_ACTIONS={"enter_sculpt","exit_sculpt","set_brush","set_brush_settings","stroke","voxel_remesh","set_dyntopo","sculpt_organic_anatomy","organic_anatomy"}
_BRUSH_SETTINGS={"size","strength","use_frontface","use_accumulate","use_pressure_size","use_pressure_strength"}

def _number(value,name,low,high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")

def validate(params,inspection=False):
    if not isinstance(params,dict): raise ValueError("Sculpt parameters must be an object")
    allowed={"object_name","target_object","expected_snapshot_id","action","brush_name","brush_type","radius","strength","settings","points","stroke_points","stroke_direction","max_displacement","iterations","preserve_topology","dynamic_topology","dynamic_topology_detail","max_vertex_count","max_face_count","views","view","reference_image_path","crop_box","coordinate_system","objective","min_aggregate_improvement","affected_region","rollback_on_failure","camera_name","voxel_size","enabled","detail_mode","detail_size","request_id","approval_token","task_id","session_id","correlation_id","trusted_approval"}
    if inspection: allowed={"object_name"}
    extra=set(params)-allowed
    if extra: raise ValueError("Unknown sculpt parameters: "+", ".join(sorted(extra)))
    name=params.get("object_name")
    if not isinstance(name,str) or not name.strip() or len(name)>63: raise ValueError("object_name must be a non-empty Blender name up to 63 characters")
    if inspection: return {"object_name":name}
    if params.get("action") not in _ACTIONS: raise ValueError("Unsupported sculpt action")
    if not isinstance(params.get("expected_snapshot_id"),str) or not _SNAPSHOT.fullmatch(params["expected_snapshot_id"]):
        raise ValueError("expected_snapshot_id must be a mesh topology snapshot id")
    action=params["action"]
    required={"set_brush":{"brush_name"},"set_brush_settings":{"settings"},"stroke":{"points"},"voxel_remesh":{"voxel_size"},"set_dyntopo":{"enabled","detail_mode","detail_size"}}
    if set(params)&{"brush_name","settings","points","voxel_size","enabled","detail_mode","detail_size"} - required.get(action,set()):
        raise ValueError("Parameters do not apply to this sculpt action")
    if action=="set_brush":
        if not isinstance(params.get("brush_name"),str) or not params["brush_name"].strip() or len(params["brush_name"])>63: raise ValueError("brush_name must be non-empty")
    if action=="set_brush_settings":
        settings=params.get("settings")
        if not isinstance(settings,dict) or not settings or set(settings)-_BRUSH_SETTINGS: raise ValueError("settings must contain supported sculpt brush properties")
        for key,value in settings.items():
            if key=="size":
                if type(value) is not int: raise ValueError("size must be an integer")
                _number(value,key,1,500)
            elif key=="strength": _number(value,key,0,1)
            elif type(value) is not bool: raise ValueError(f"{key} must be boolean")
    if action=="stroke":
        points=params.get("points")
        if not isinstance(points,list) or not 2<=len(points)<=256: raise ValueError("stroke requires 2..256 normalized points")
        for i,p in enumerate(points):
            if not isinstance(p,dict) or set(p)-{"x","y","pressure"} or not {"x","y"}<=set(p): raise ValueError(f"Invalid stroke point {i}")
            _number(p["x"],"x",0,1);_number(p["y"],"y",0,1);_number(p.get("pressure",1),"pressure",0,1)
    if action=="voxel_remesh": _number(params["voxel_size"],"voxel_size",0.001,1)
    if action=="set_dyntopo":
        if type(params["enabled"]) is not bool: raise ValueError("enabled must be boolean")
        dm = str(params.get("detail_mode", "RELATIVE")).upper()
        if dm not in {"RELATIVE", "CONSTANT"}:
            raise ValueError(f"detail_mode must be RELATIVE or CONSTANT, got {dm!r}")
        if "detail_size" in params: _number(params["detail_size"],"detail_size",0.001,100)
    return dict(params)
