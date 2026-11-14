"""Atomic standalone face edits. Stage on a private mesh; never switch context."""
import math
import threading
from .approval_registry import get_approval_registry
from .mesh_topology import inspect_elements, assert_base_snapshot, validate_snapshot_id


def _snapshot(obj, context):
    return {**inspect_elements(obj, context, {"element_domain":"vertices", "limit":1}),
            "vertex_count":len(obj.data.vertices),"edge_count":len(obj.data.edges),"polygon_count":len(obj.data.polygons)}


def _verify_commit(obj, context, expected):
    actual = _snapshot(obj, context)
    if actual["snapshot_id"] != expected:
        raise RuntimeError("Committed mesh differs from staged geometry")
    return actual


def handle_face_edit(bpy, params, tool):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Mesh edits require Blender main thread")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok, reason = get_approval_registry().consume_approval(params.get("request_id"),params.get("approval_token"),tool,params)
        if not ok: raise PermissionError("Scene mutation denied: "+reason)
    allowed={"name","faces","expected_snapshot_id","approved","trusted_approval","request_id","approval_token","task_id","session_id","correlation_id"}
    allowed.update({"distance","direction","individual","dissolve_orthogonal_edges"} if tool in ("extrude_mesh","extrude_faces") else {"thickness","depth","use_individual","use_boundary","use_outset"})
    if set(params)-allowed:raise ValueError("Unknown mesh edit parameters")
    for key in ("individual","dissolve_orthogonal_edges","use_individual","use_boundary","use_outset"):
        if key in params and type(params[key]) is not bool:raise ValueError(key+" must be boolean")
    name=params.get("name")
    if not isinstance(name,str) or not name.strip(): raise ValueError("Object name is required")
    obj=bpy.context.scene.objects.get(name)
    if obj is None: raise ValueError(f"Object '{name}' not found in scene (active scene required)")
    if obj.type!="MESH" or obj.data is None: raise ValueError("Face editing target is not of type 'MESH'")
    before=_snapshot(obj,bpy.context)  # Object mode, active scene and resource bounds
    expected=params.get("expected_snapshot_id")
    faces=params.get("faces","selected")
    if isinstance(faces,(list,tuple)) and expected is None:
        raise ValueError("Explicit face indices require expected_snapshot_id from base topology inspection")
    if expected is not None: assert_base_snapshot(obj,bpy.context,expected)
    if obj.data.shape_keys is not None: raise ValueError("Topology editing shape-key meshes is not supported")
    operation="extrude" if tool in ("extrude_mesh","extrude_faces") else "inset"
    numbers={"distance":1.0} if operation=="extrude" else {"thickness":0.1,"depth":0.0}
    for key,default in numbers.items():
        value=params.get(key,default)
        if type(value) not in (int,float) or not math.isfinite(value): raise ValueError(key+" must be finite")
        if key=="thickness" and value<0: raise ValueError("thickness cannot be negative")
    direction=params.get("direction")
    if direction is not None and (not isinstance(direction,(list,tuple)) or len(direction)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in direction)):
        raise ValueError("direction must contain three finite numbers")
    import bmesh
    from mathutils import Vector
    from .mesh_atomic import run
    def mutate(bm):
        bm.faces.ensure_lookup_table();bm.normal_update()
        if isinstance(faces,(list,tuple)):
            if not faces or any(type(i) is not int for i in faces) or len(faces)!=len(set(faces)) or any(not 0<=i<len(bm.faces) for i in faces):
                raise ValueError("Face indices must be unique, nonempty and in range")
            chosen=[bm.faces[i] for i in faces]
        elif faces=="all":chosen=list(bm.faces)
        elif faces=="selected":chosen=[f for f in bm.faces if f.select]
        else:raise ValueError("faces must be selected, all or an index list")
        if not chosen:raise ValueError("No faces selected")
        count=len(chosen)
        if operation=="extrude":
            distance=float(params.get("distance",1))
            if not distance or direction is not None and not Vector(direction).length:raise ValueError("Extrusion distance/direction cannot be zero")
            if params.get("individual",False):
                result=bmesh.ops.extrude_discrete_faces(bm,faces=chosen)
                for face in result["faces"]:
                    vector=Vector(direction) if direction is not None else face.normal.copy()
                    bmesh.ops.translate(bm,verts=list(face.verts),vec=vector*distance)
            else:
                normal=sum((f.normal for f in chosen),Vector())
                if direction is None and normal.length==0:raise ValueError("Region normal is ambiguous; provide direction")
                vector=Vector(direction) if direction is not None else normal.normalized()
                result=bmesh.ops.extrude_face_region(bm,geom=chosen,use_dissolve_ortho_edges=params.get("dissolve_orthogonal_edges",False))
                # BMesh retains source faces when geom contains faces only. Remove
                # them (and orphaned internal edges) before committing the region.
                bmesh.ops.delete(bm,geom=chosen,context="FACES")
                vertices=[v for v in result["geom"] if isinstance(v,bmesh.types.BMVert) and v.is_valid]
                if not vertices:raise RuntimeError("Extrusion produced no vertices")
                bmesh.ops.translate(bm,verts=vertices,vec=vector*distance)
        else:
            options=dict(thickness=float(params.get("thickness",.1)),depth=float(params.get("depth",0)))
            if not options["thickness"] and not options["depth"]:raise ValueError("Inset must change thickness or depth")
            if params.get("use_individual",False):bmesh.ops.inset_individual(bm,faces=chosen,**options)
            else:bmesh.ops.inset_region(bm,faces=chosen,use_boundary=params.get("use_boundary",True),use_outset=params.get("use_outset",False),**options)
        return {"action":tool,"operation":operation,"faces_extruded" if operation=="extrude" else "faces_inset":count,
            "distance":float(params.get("distance",1)) if operation=="extrude" else None,
            "thickness":float(params.get("thickness",.1)) if operation=="inset" else None}
    def verify(obj,context,after):
        actual=_verify_commit(obj,context,after["snapshot_id"])
        if actual.get("state_id")!=after.get("state_id"):raise RuntimeError("Mesh attribute readback mismatch")
        return actual
    return run(bpy,obj,mutate,expected or before["snapshot_id"],verify=verify)


def handle_bevel_mesh(bpy, params, tool="bevel_mesh"):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Mesh edits require Blender main thread")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok, reason = get_approval_registry().consume_approval(params.get("request_id"), params.get("approval_token"), tool, params)
        if not ok: raise PermissionError("Scene mutation denied: " + reason)
    name = params.get("name") or params.get("target_object") or params.get("object_name")
    if not isinstance(name, str) or not name.strip(): raise ValueError("Object name is required")
    obj = bpy.context.scene.objects.get(name)
    if obj is None: raise ValueError(f"Object '{name}' not found in scene (active scene required)")
    if obj.type != "MESH" or obj.data is None: raise ValueError("Bevel target is not of type 'MESH'")
    if obj.data.shape_keys is not None: raise ValueError("Topology editing shape-key meshes is not supported")
    before = _snapshot(obj, bpy.context)
    expected = params.get("expected_snapshot_id")
    if expected is not None: assert_base_snapshot(obj, bpy.context, expected)

    offset = float(params.get("offset", 0.1))
    if not math.isfinite(offset) or offset < 0: raise ValueError("offset must be non-negative and finite")
    offset_type = str(params.get("offset_type", "OFFSET")).upper()
    segments = int(params.get("segments", 1))
    if segments < 1 or segments > 64: raise ValueError("segments must be between 1 and 64")
    profile = float(params.get("profile", 0.5))
    if not math.isfinite(profile) or not (0.0 <= profile <= 1.0): raise ValueError("profile must be between 0.0 and 1.0")
    affect = str(params.get("affect", "EDGES")).upper()
    if affect not in ("EDGES", "VERTICES"): raise ValueError("affect must be 'EDGES' or 'VERTICES'")
    clamp_overlap = bool(params.get("clamp_overlap", False))

    import bmesh
    from .mesh_atomic import run

    def mutate(bm):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        if affect == "VERTICES":
            v_param = params.get("vertices", "all")
            if isinstance(v_param, (list, tuple)):
                if expected is None: raise ValueError("Explicit vertex indices require expected_snapshot_id")
                geom = [bm.verts[i] for i in v_param]
            elif v_param == "selected": geom = [v for v in bm.verts if v.select]
            else: geom = list(bm.verts)
        else:
            e_param = params.get("edges", "all")
            if isinstance(e_param, (list, tuple)):
                if expected is None: raise ValueError("Explicit edge indices require expected_snapshot_id")
                geom = [bm.edges[i] for i in e_param]
            elif e_param == "selected": geom = [e for e in bm.edges if e.select]
            else: geom = list(bm.edges)
        if not geom: raise ValueError("No elements selected for bevel")
        bmesh.ops.bevel(bm, geom=geom, offset=offset, offset_type=offset_type, segments=segments, profile=profile, affect=affect, clamp_overlap=clamp_overlap)
        return {"action": tool, "operation": "bevel", "affect": affect, "offset": offset, "segments": segments, "profile": profile, "count": len(geom)}

    def verify(obj, context, after):
        actual = _verify_commit(obj, context, after["snapshot_id"])
        if actual.get("state_id") != after.get("state_id"): raise RuntimeError("Mesh attribute readback mismatch")
        return actual

    return run(bpy, obj, mutate, expected or before["snapshot_id"], verify=verify)


def handle_split_mesh(bpy, params, tool="split_mesh"):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Mesh edits require Blender main thread")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok, reason = get_approval_registry().consume_approval(params.get("request_id"), params.get("approval_token"), tool, params)
        if not ok: raise PermissionError("Scene mutation denied: " + reason)
    name = params.get("name") or params.get("target_object") or params.get("object_name")
    if not isinstance(name, str) or not name.strip(): raise ValueError("Object name is required")
    obj = bpy.context.scene.objects.get(name)
    if obj is None: raise ValueError(f"Object '{name}' not found in scene (active scene required)")
    if obj.type != "MESH" or obj.data is None: raise ValueError("Split target is not of type 'MESH'")
    if obj.data.shape_keys is not None: raise ValueError("Topology editing shape-key meshes is not supported")
    before = _snapshot(obj, bpy.context)
    expected = params.get("expected_snapshot_id")
    if expected is not None: assert_base_snapshot(obj, bpy.context, expected)

    method = str(params.get("method", "BISECT")).upper()
    if method not in ("BISECT", "SUBDIVIDE", "SPLIT_EDGES"):
        raise ValueError("method must be 'BISECT', 'SUBDIVIDE', or 'SPLIT_EDGES'")

    import bmesh
    from mathutils import Vector
    from .mesh_atomic import run

    def mutate(bm):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        if method == "BISECT":
            co = params.get("plane_co", [0.0, 0.0, 0.0])
            no = params.get("plane_no", [0.0, 0.0, 1.0])
            threshold = float(params.get("threshold", 0.0001))
            geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
            bmesh.ops.bisect_plane(
                bm, geom=geom, dist=threshold,
                plane_co=Vector(co), plane_no=Vector(no),
                clear_inner=bool(params.get("clear_inner", False)),
                clear_outer=bool(params.get("clear_outer", False))
            )
            return {"action": tool, "operation": "split", "method": "BISECT"}
        elif method == "SUBDIVIDE":
            cuts = int(params.get("cuts", 1))
            e_param = params.get("edges", "all")
            if isinstance(e_param, (list, tuple)):
                if expected is None: raise ValueError("Explicit edge indices require expected_snapshot_id")
                target_edges = [bm.edges[i] for i in e_param]
            elif e_param == "selected": target_edges = [e for e in bm.edges if e.select]
            else: target_edges = list(bm.edges)
            if not target_edges: raise ValueError("No edges to subdivide")
            bmesh.ops.subdivide_edges(bm, edges=target_edges, cuts=cuts, use_grid_fill=True)
            return {"action": tool, "operation": "split", "method": "SUBDIVIDE", "cuts": cuts, "count": len(target_edges)}
        elif method == "SPLIT_EDGES":
            e_param = params.get("edges", "selected")
            if isinstance(e_param, (list, tuple)):
                if expected is None: raise ValueError("Explicit edge indices require expected_snapshot_id")
                target_edges = [bm.edges[i] for i in e_param]
            elif e_param == "all": target_edges = list(bm.edges)
            else: target_edges = [e for e in bm.edges if e.select]
            if not target_edges: raise ValueError("No edges to split")
            bmesh.ops.split_edges(bm, edges=target_edges)
            return {"action": tool, "operation": "split", "method": "SPLIT_EDGES", "count": len(target_edges)}

    def verify(obj, context, after):
        actual = _verify_commit(obj, context, after["snapshot_id"])
        if actual.get("state_id") != after.get("state_id"): raise RuntimeError("Mesh attribute readback mismatch")
        return actual

    return run(bpy, obj, mutate, expected or before["snapshot_id"], verify=verify)


def handle_dissolve_mesh(bpy, params, tool="dissolve_mesh"):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Mesh edits require Blender main thread")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok, reason = get_approval_registry().consume_approval(params.get("request_id"), params.get("approval_token"), tool, params)
        if not ok: raise PermissionError("Scene mutation denied: " + reason)
    name = params.get("name") or params.get("target_object") or params.get("object_name")
    if not isinstance(name, str) or not name.strip(): raise ValueError("Object name is required")
    obj = bpy.context.scene.objects.get(name)
    if obj is None: raise ValueError(f"Object '{name}' not found in scene (active scene required)")
    if obj.type != "MESH" or obj.data is None: raise ValueError("Dissolve target is not of type 'MESH'")
    if obj.data.shape_keys is not None: raise ValueError("Topology editing shape-key meshes is not supported")
    before = _snapshot(obj, bpy.context)
    expected = params.get("expected_snapshot_id")
    if expected is not None: assert_base_snapshot(obj, bpy.context, expected)

    dtype = str(params.get("dissolve_type", "EDGES")).upper()
    indices = params.get("indices", "selected")
    use_verts = bool(params.get("use_verts", True))
    use_face_split = bool(params.get("use_face_split", False))

    import bmesh
    from .mesh_atomic import run

    def mutate(bm):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        if dtype == "EDGES":
            if isinstance(indices, (list, tuple)):
                if expected is None: raise ValueError("Explicit edge indices require expected_snapshot_id")
                target = [bm.edges[i] for i in indices]
            else: target = [e for e in bm.edges if e.select]
            if not target: raise ValueError("No edges selected to dissolve")
            bmesh.ops.dissolve_edges(bm, edges=target, use_verts=use_verts, use_face_split=use_face_split)
        elif dtype == "VERTICES":
            if isinstance(indices, (list, tuple)):
                if expected is None: raise ValueError("Explicit vertex indices require expected_snapshot_id")
                target = [bm.verts[i] for i in indices]
            else: target = [v for v in bm.verts if v.select]
            if not target: raise ValueError("No vertices selected to dissolve")
            bmesh.ops.dissolve_verts(bm, verts=target, use_face_split=use_face_split)
        elif dtype == "FACES":
            if isinstance(indices, (list, tuple)):
                if expected is None: raise ValueError("Explicit face indices require expected_snapshot_id")
                target = [bm.faces[i] for i in indices]
            else: target = [f for f in bm.faces if f.select]
            if not target: raise ValueError("No faces selected to dissolve")
            bmesh.ops.dissolve_faces(bm, faces=target, use_verts=use_verts)
        else:
            raise ValueError(f"Unknown dissolve_type '{dtype}'")
        return {"action": tool, "operation": "dissolve", "dissolve_type": dtype, "count": len(target)}

    def verify(obj, context, after):
        actual = _verify_commit(obj, context, after["snapshot_id"])
        if actual.get("state_id") != after.get("state_id"): raise RuntimeError("Mesh attribute readback mismatch")
        return actual

    return run(bpy, obj, mutate, expected or before["snapshot_id"], verify=verify)


def handle_merge_mesh(bpy, params, tool="merge_mesh"):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Mesh edits require Blender main thread")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok, reason = get_approval_registry().consume_approval(params.get("request_id"), params.get("approval_token"), tool, params)
        if not ok: raise PermissionError("Scene mutation denied: " + reason)
    name = params.get("name") or params.get("target_object") or params.get("object_name")
    if not isinstance(name, str) or not name.strip(): raise ValueError("Object name is required")
    obj = bpy.context.scene.objects.get(name)
    if obj is None: raise ValueError(f"Object '{name}' not found in scene (active scene required)")
    if obj.type != "MESH" or obj.data is None: raise ValueError("Merge target is not of type 'MESH'")
    if obj.data.shape_keys is not None: raise ValueError("Topology editing shape-key meshes is not supported")
    before = _snapshot(obj, bpy.context)
    expected = params.get("expected_snapshot_id")
    if expected is not None: assert_base_snapshot(obj, bpy.context, expected)

    mode = str(params.get("mode", "CENTER")).upper()
    v_param = params.get("vertices", "selected")

    import bmesh
    from mathutils import Vector
    from .mesh_atomic import run

    def mutate(bm):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        if isinstance(v_param, (list, tuple)):
            if expected is None: raise ValueError("Explicit vertex indices require expected_snapshot_id")
            target_verts = [bm.verts[i] for i in v_param]
        elif v_param == "all": target_verts = list(bm.verts)
        else: target_verts = [v for v in bm.verts if v.select]
        if not target_verts: raise ValueError("No vertices selected for merge")

        if mode == "DISTANCE":
            dist = float(params.get("distance_threshold", 0.001))
            bmesh.ops.remove_doubles(bm, verts=target_verts, dist=dist)
        else:
            if len(target_verts) < 2: raise ValueError("Merge requires at least 2 vertices")
            if mode == "CENTER":
                merge_co = sum((v.co for v in target_verts), Vector()) / len(target_verts)
            elif mode == "CURSOR":
                loc = params.get("target_location")
                if not loc: raise ValueError("target_location required for CURSOR merge")
                merge_co = Vector(loc)
            elif mode == "COLLAPSE":
                merge_co = target_verts[0].co.copy()
            else:
                raise ValueError(f"Unknown merge mode '{mode}'")
            bmesh.ops.pointmerge(bm, verts=target_verts, merge_co=merge_co)
        return {"action": tool, "operation": "merge", "mode": mode, "count": len(target_verts)}

    def verify(obj, context, after):
        actual = _verify_commit(obj, context, after["snapshot_id"])
        if actual.get("state_id") != after.get("state_id"): raise RuntimeError("Mesh attribute readback mismatch")
        return actual

    return run(bpy, obj, mutate, expected or before["snapshot_id"], verify=verify)


def handle_recalculate_normals(bpy, params, tool="recalculate_normals"):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Mesh edits require Blender main thread")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok, reason = get_approval_registry().consume_approval(params.get("request_id"), params.get("approval_token"), tool, params)
        if not ok: raise PermissionError("Scene mutation denied: " + reason)
    name = params.get("name") or params.get("target_object") or params.get("object_name")
    if not isinstance(name, str) or not name.strip(): raise ValueError("Object name is required")
    obj = bpy.context.scene.objects.get(name)
    if obj is None: raise ValueError(f"Object '{name}' not found in scene (active scene required)")
    if obj.type != "MESH" or obj.data is None: raise ValueError("Normal operation target is not of type 'MESH'")
    if obj.data.shape_keys is not None: raise ValueError("Topology editing shape-key meshes is not supported")
    before = _snapshot(obj, bpy.context)
    expected = params.get("expected_snapshot_id")
    if expected is not None: assert_base_snapshot(obj, bpy.context, expected)

    action = str(params.get("action", "RECALCULATE_OUTSIDE")).upper()
    faces_param = params.get("faces", "all")

    import bmesh
    from .mesh_atomic import run

    def mutate(bm):
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        if isinstance(faces_param, (list, tuple)):
            if expected is None: raise ValueError("Explicit face indices require expected_snapshot_id")
            target_faces = [bm.faces[i] for i in faces_param]
        elif faces_param == "selected": target_faces = [f for f in bm.faces if f.select]
        else: target_faces = list(bm.faces)
        if not target_faces: raise ValueError("No faces selected for normal operation")

        if action == "RECALCULATE_OUTSIDE":
            bmesh.ops.recalc_face_normals(bm, faces=target_faces)
        elif action == "RECALCULATE_INSIDE":
            bmesh.ops.recalc_face_normals(bm, faces=target_faces)
            bmesh.ops.reverse_faces(bm, faces=target_faces)
        elif action == "FLIP":
            bmesh.ops.reverse_faces(bm, faces=target_faces)
        else:
            raise ValueError(f"Unknown normal action '{action}'")
        bm.normal_update()
        return {"action": tool, "operation": "recalculate_normals", "normal_action": action, "count": len(target_faces), "allow_unchanged": True}

    def verify(obj, context, after):
        actual = _verify_commit(obj, context, after["snapshot_id"])
        if actual.get("state_id") != after.get("state_id"): raise RuntimeError("Mesh attribute readback mismatch")
        return actual

    return run(bpy, obj, mutate, expected or before["snapshot_id"], verify=verify)
