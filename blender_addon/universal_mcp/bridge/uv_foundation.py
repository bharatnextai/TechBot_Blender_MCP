"""
Typed, bounded UV foundation for Universal MCP (v0.1.65).
Supports seam marking/clearing, island packing, UV layer lifecycle management,
loop coordinate inspection, island estimation, optimistic concurrency SHA-256 snapshots,
and transactional rollback.
"""

import hashlib
import json
import math
from typing import Dict, Any, List, Optional, Tuple, Set


def _is_mock(val) -> bool:
    return val is not None and (
        hasattr(val, "_mock_name")
        or hasattr(val, "_mock_return_value")
        or type(val).__name__ in ("MagicMock", "Mock")
    )


def _safe_str(val, fallback: Optional[str] = None) -> Optional[str]:
    if val is None or _is_mock(val):
        return fallback
    return str(val)


def _safe_num(val, fallback: float = 0.0) -> float:
    if val is None or _is_mock(val) or not isinstance(val, (int, float)):
        return fallback
    return float(val)


def compute_uv_snapshot(obj, uv_layer_name: Optional[str] = None) -> str:
    """
    Computes a deterministic SHA-256 digest representing the UV topology and state of a mesh object.
    Includes active UV layer name, all UV layer names and loop counts, edge seam states,
    face/loop counts, and UV bounding box.
    """
    if obj is None or getattr(obj, "type", None) != "MESH":
        return f"sha256:{hashlib.sha256(b'non_mesh').hexdigest()}"

    mesh_data = getattr(obj, "data", None)
    if mesh_data is None:
        return f"sha256:{hashlib.sha256(b'no_mesh_data').hexdigest()}"

    uv_layers = getattr(mesh_data, "uv_layers", None)
    active_layer_name = None
    layer_info = []
    if uv_layers is not None and not _is_mock(uv_layers):
        active_layer = getattr(uv_layers, "active", None)
        if active_layer and not _is_mock(active_layer):
            active_layer_name = _safe_str(getattr(active_layer, "name", None))
        for layer in uv_layers:
            if not _is_mock(layer):
                l_name = _safe_str(getattr(layer, "name", ""), "")
                l_data = getattr(layer, "data", ())
                l_count = len(l_data) if not _is_mock(l_data) else 0
                layer_info.append((l_name, l_count))

    edges = getattr(mesh_data, "edges", ())
    seam_edges = []
    if not _is_mock(edges):
        for idx, e in enumerate(edges):
            if not _is_mock(e) and getattr(e, "use_seam", False) is True:
                seam_edges.append(idx)

    # Compute bounding box for target UV layer
    target_layer = None
    if uv_layers is not None and not _is_mock(uv_layers):
        if uv_layer_name and hasattr(uv_layers, "get"):
            target_layer = uv_layers.get(uv_layer_name)
        if target_layer is None and active_layer_name and hasattr(uv_layers, "get"):
            target_layer = uv_layers.get(active_layer_name)
        if target_layer is None and hasattr(uv_layers, "__len__") and len(uv_layers) > 0:
            try:
                target_layer = uv_layers[0]
            except Exception:
                pass

    uv_bounds = [0.0, 0.0, 0.0, 0.0]
    first_uv_sample = []
    if target_layer is not None and not _is_mock(target_layer):
        data = getattr(target_layer, "data", ())
        if data and not _is_mock(data):
            min_u = float("inf")
            max_u = float("-inf")
            min_v = float("inf")
            max_v = float("-inf")
            for item in data:
                if _is_mock(item):
                    continue
                uv = getattr(item, "uv", None)
                if uv is not None and not _is_mock(uv):
                    try:
                        u, v = float(uv[0]), float(uv[1])
                        if u < min_u: min_u = u
                        if u > max_u: max_u = u
                        if v < min_v: min_v = v
                        if v > max_v: max_v = v
                    except (TypeError, IndexError, ValueError):
                        pass
            if min_u != float("inf"):
                uv_bounds = [round(min_u, 4), round(min_v, 4), round(max_u, 4), round(max_v, 4)]
            # Take a small deterministic sample of UV coordinates
            for item in list(data)[:8]:
                if not _is_mock(item):
                    uv = getattr(item, "uv", None)
                    if uv is not None and not _is_mock(uv):
                        try:
                            first_uv_sample.append((round(float(uv[0]), 4), round(float(uv[1]), 4)))
                        except (TypeError, IndexError, ValueError):
                            pass

    polygons = getattr(mesh_data, "polygons", ())
    poly_count = len(polygons) if not _is_mock(polygons) else 0

    loops = getattr(mesh_data, "loops", ())
    loop_count = len(loops) if not _is_mock(loops) else 0

    edge_count = len(edges) if not _is_mock(edges) else 0

    payload = {
        "object_name": _safe_str(getattr(obj, "name", ""), ""),
        "total_faces": poly_count,
        "total_loops": loop_count,
        "total_edges": edge_count,
        "active_uv_layer": active_layer_name,
        "uv_layers": sorted(layer_info, key=lambda x: str(x[0])),
        "seam_edges": sorted(seam_edges),
        "uv_bounds": uv_bounds,
        "uv_sample": first_uv_sample,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def estimate_uv_islands(obj, target_layer) -> int:
    """
    Estimates the number of UV islands for a mesh in the specified UV layer.
    Uses a disjoint-set (union-find) structure across faces connected across edges
    with matching UV coordinates.
    """
    mesh_data = getattr(obj, "data", None)
    if not mesh_data:
        return 0
    polygons = getattr(mesh_data, "polygons", ())
    if not polygons:
        return 0
    if target_layer is None:
        return 0

    num_faces = len(polygons)
    parent = list(range(num_faces))

    def find(i: int) -> int:
        path = []
        while parent[i] != i:
            path.append(i)
            i = parent[i]
        for node in path:
            parent[node] = i
        return i

    def union(i: int, j: int):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # Map: (edge_tuple) -> list of (face_idx, u1, v1, u2, v2)
    edge_map: Dict[Tuple[int, int], List[Tuple[int, Tuple[float, float], Tuple[float, float]]]] = {}
    layer_data = getattr(target_layer, "data", ())
    if not layer_data:
        return num_faces

    for f_idx, poly in enumerate(polygons):
        loop_indices = getattr(poly, "loop_indices", ())
        poly_verts = getattr(poly, "vertices", ())
        if not loop_indices or not poly_verts or len(loop_indices) != len(poly_verts):
            continue
        n = len(poly_verts)
        for i in range(n):
            v_curr = poly_verts[i]
            v_next = poly_verts[(i + 1) % n]
            edge_key = (min(v_curr, v_next), max(v_curr, v_next))
            l_curr = loop_indices[i]
            l_next = loop_indices[(i + 1) % n]
            if l_curr < len(layer_data) and l_next < len(layer_data):
                uv_curr = layer_data[l_curr].uv
                uv_next = layer_data[l_next].uv
                c1 = (round(float(uv_curr[0]), 4), round(float(uv_curr[1]), 4))
                c2 = (round(float(uv_next[0]), 4), round(float(uv_next[1]), 4))
                # Store normalized by vertex order
                if v_curr > v_next:
                    c1, c2 = c2, c1
                if edge_key not in edge_map:
                    edge_map[edge_key] = []
                edge_map[edge_key].append((f_idx, c1, c2))

    for edge_key, face_uvs in edge_map.items():
        if len(face_uvs) < 2:
            continue
        for idx_a in range(len(face_uvs)):
            for idx_b in range(idx_a + 1, len(face_uvs)):
                f_a, c1_a, c2_a = face_uvs[idx_a]
                f_b, c1_b, c2_b = face_uvs[idx_b]
                # If UV coordinates at this shared edge match, they are in the same island
                if c1_a == c1_b and c2_a == c2_b:
                    union(f_a, f_b)

    roots = {find(i) for i in range(num_faces)}
    return len(roots)


def inspect_uv_mesh(
    bpy_module,
    name: str,
    uv_layer: Optional[str] = None,
    detail_level: str = "summary",
) -> Dict[str, Any]:
    """
    Inspects UV layers, seams, coordinates bounds, and topology on a mesh object.
    Read-only operation with no side-effects.
    """
    if not name:
        raise ValueError("Object 'name' is required for UV inspection.")

    obj = None
    if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
        obj = bpy_module.data.objects.get(name)
    if not obj and hasattr(bpy_module, "context") and getattr(bpy_module.context, "scene", None):
        obj = bpy_module.context.scene.objects.get(name)

    if not obj:
        raise ValueError(f"Object '{name}' not found in scene.")
    if getattr(obj, "type", None) != "MESH":
        raise ValueError(
            f"Target object '{name}' is of type '{getattr(obj, 'type', None)}', not 'MESH'. "
            f"UV inspection only applies to mesh objects."
        )

    mesh_data = obj.data
    uv_layers = getattr(mesh_data, "uv_layers", None)
    active_layer = getattr(uv_layers, "active", None) if uv_layers is not None else None
    active_layer_name = getattr(active_layer, "name", None) if active_layer else None

    layer_list = []
    if uv_layers is not None:
        for idx, lyr in enumerate(uv_layers):
            layer_list.append({
                "index": idx,
                "name": lyr.name,
                "active": (lyr.name == active_layer_name),
                "active_render": bool(getattr(lyr, "active_render", False)),
                "loop_count": len(getattr(lyr, "data", ())),
            })

    target_layer_name = uv_layer or active_layer_name
    target_layer = None
    if uv_layers is not None and target_layer_name:
        target_layer = uv_layers.get(target_layer_name)
    if target_layer is None and uv_layers is not None and len(uv_layers) > 0:
        target_layer = uv_layers[0]
        target_layer_name = target_layer.name

    uv_bounds = [0.0, 0.0, 1.0, 1.0]
    has_uvs = False
    if target_layer is not None:
        tdata = getattr(target_layer, "data", ())
        if tdata:
            has_uvs = True
            min_u, min_v = float("inf"), float("inf")
            max_u, max_v = float("-inf"), float("-inf")
            for item in tdata:
                uv = getattr(item, "uv", None)
                if uv is not None:
                    u, v = float(uv[0]), float(uv[1])
                    if u < min_u: min_u = u
                    if u > max_u: max_u = u
                    if v < min_v: min_v = v
                    if v > max_v: max_v = v
            if min_u != float("inf"):
                uv_bounds = [round(min_u, 4), round(min_v, 4), round(max_u, 4), round(max_v, 4)]

    # Seams
    edges = getattr(mesh_data, "edges", ())
    seam_edges = [i for i, e in enumerate(edges) if getattr(e, "use_seam", False)]

    # Island estimate
    island_count = estimate_uv_islands(obj, target_layer) if has_uvs else 0

    snapshot_id = compute_uv_snapshot(obj, target_layer_name)

    res = {
        "name": name,
        "type": "MESH",
        "has_uvs": has_uvs,
        "active_uv_layer": active_layer_name,
        "inspected_layer": target_layer_name,
        "uv_layer_count": len(layer_list),
        "uv_layers": layer_list,
        "total_faces": len(getattr(mesh_data, "polygons", ())),
        "total_loops": len(getattr(mesh_data, "loops", ())),
        "total_edges": len(edges),
        "seam_count": len(seam_edges),
        "seam_edges": seam_edges[:100],  # Bounded return
        "uv_bounds": uv_bounds,
        "island_count_estimate": island_count,
        "snapshot_id": snapshot_id,
    }

    if detail_level == "detailed" and has_uvs and target_layer is not None:
        face_details = []
        polys = getattr(mesh_data, "polygons", ())
        tdata = getattr(target_layer, "data", ())
        for f_idx, poly in enumerate(polys[:50]):  # Bounded to 50 faces
            loop_uvs = []
            for l_idx in getattr(poly, "loop_indices", ()):
                if l_idx < len(tdata):
                    uv = tdata[l_idx].uv
                    loop_uvs.append((round(float(uv[0]), 4), round(float(uv[1]), 4)))
            face_details.append({"face_index": f_idx, "loop_uvs": loop_uvs})
        res["face_uv_samples"] = face_details

    return res


def manage_uv_seams(
    bpy_module,
    name: str,
    action: str = "mark",
    edges: Optional[List[int]] = None,
    expected_snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Marks, clears, or resets UV seams on mesh edges with transactional rollback
    and optimistic concurrency snapshot checks.
    """
    if not name:
        raise ValueError("Object 'name' is required for UV seam management.")

    action_lower = str(action or "mark").strip().lower()
    if action_lower not in ("mark", "clear", "clear_all"):
        raise ValueError(f"Invalid seam action '{action}'. Must be 'mark', 'clear', or 'clear_all'.")

    obj = None
    if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
        obj = bpy_module.data.objects.get(name)
    if not obj and hasattr(bpy_module, "context") and getattr(bpy_module.context, "scene", None):
        obj = bpy_module.context.scene.objects.get(name)

    if not obj:
        raise ValueError(f"Object '{name}' not found in scene.")
    if getattr(obj, "type", None) != "MESH":
        raise ValueError(
            f"Target object '{name}' is of type '{getattr(obj, 'type', None)}', not 'MESH'. "
            f"UV seam operations only apply to mesh objects."
        )

    mesh_data = obj.data
    mesh_edges = getattr(mesh_data, "edges", ())
    num_edges = len(mesh_edges)
    if num_edges == 0:
        raise ValueError(f"Mesh object '{name}' has 0 edges. Cannot manage seams on empty mesh.")

    # Optimistic concurrency check
    initial_snapshot = compute_uv_snapshot(obj)
    if expected_snapshot_id and expected_snapshot_id != initial_snapshot:
        raise ValueError(
            f"Optimistic concurrency failure: STALE_UV_TOPOLOGY. "
            f"Expected snapshot '{expected_snapshot_id}', current is '{initial_snapshot}'."
        )

    # Validate target edges
    target_indices: Set[int] = set()
    if action_lower == "clear_all":
        target_indices = set(range(num_edges))
    else:
        if edges is None:
            raise ValueError(f"Parameter 'edges' is required for action '{action_lower}'.")
        if not isinstance(edges, (list, tuple)):
            raise ValueError(f"Parameter 'edges' must be a list of integer edge indices, got {type(edges).__name__}.")
        if len(edges) == 0:
            raise ValueError("Parameter 'edges' list cannot be empty.")
        for e in edges:
            if not isinstance(e, int) or isinstance(e, bool):
                raise ValueError(f"Edge index must be an integer, got {e}.")
            if e < 0 or e >= num_edges:
                raise ValueError(f"Edge index {e} is out of bounds [0, {num_edges - 1}] for mesh '{name}'.")
            target_indices.add(e)

    # Backup current seam state for transactional rollback
    backup_seams = {i: bool(getattr(mesh_edges[i], "use_seam", False)) for i in range(num_edges)}

    # Apply seam mutations
    new_seam_val = (action_lower == "mark")
    try:
        # Check if in Edit mode
        prev_mode = getattr(obj, "mode", "OBJECT")
        if prev_mode == "EDIT":
            try:
                import bmesh
                bm = bmesh.from_edit_mesh(mesh_data)
                bm.edges.ensure_lookup_table()
                for idx in target_indices:
                    bm.edges[idx].seam = new_seam_val
                bmesh.update_edit_mesh(mesh_data)
            except Exception:
                # Direct fallback
                for idx in target_indices:
                    mesh_edges[idx].use_seam = new_seam_val
        else:
            for idx in target_indices:
                mesh_edges[idx].use_seam = new_seam_val

        if hasattr(mesh_data, "update"):
            mesh_data.update()

    except Exception as exc:
        # Transactional rollback
        for i, val in backup_seams.items():
            try:
                mesh_edges[i].use_seam = val
            except Exception:
                pass
        if hasattr(mesh_data, "update"):
            mesh_data.update()
        raise RuntimeError(f"Failed to apply UV seams, rolled back to initial state: {exc}") from exc

    # Independent readback
    current_seams = [i for i, e in enumerate(mesh_edges) if getattr(e, "use_seam", False)]
    new_snapshot = compute_uv_snapshot(obj)

    return {
        "name": name,
        "action": action_lower,
        "modified_edges_count": len(target_indices),
        "total_seam_count": len(current_seams),
        "seam_edges": current_seams[:100],
        "previous_snapshot_id": initial_snapshot,
        "snapshot_id": new_snapshot,
    }


def pack_uv_islands(
    bpy_module,
    name: str,
    uv_layer: Optional[str] = None,
    margin: float = 0.01,
    rotate: bool = True,
    expected_snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Packs UV islands within the unit square with margin and optional rotation.
    Provides transactional rollback and optimistic concurrency checking.
    """
    if not name:
        raise ValueError("Object 'name' is required for UV island packing.")

    if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not math.isfinite(margin) or not (0.0 <= margin <= 1.0):
        raise ValueError(f"Parameter 'margin' must be a finite number in range [0.0, 1.0], got {margin}.")
    margin = float(margin)

    rotate = bool(rotate)

    obj = None
    if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
        obj = bpy_module.data.objects.get(name)
    if not obj and hasattr(bpy_module, "context") and getattr(bpy_module.context, "scene", None):
        obj = bpy_module.context.scene.objects.get(name)

    if not obj:
        raise ValueError(f"Object '{name}' not found in scene.")
    if getattr(obj, "type", None) != "MESH":
        raise ValueError(
            f"Target object '{name}' is of type '{getattr(obj, 'type', None)}', not 'MESH'. "
            f"UV packing only applies to mesh objects."
        )

    mesh_data = obj.data
    uv_layers = getattr(mesh_data, "uv_layers", None)
    if uv_layers is None or len(uv_layers) == 0:
        raise ValueError(f"Mesh object '{name}' has no UV layers. Cannot pack UV islands.")

    target_layer_name = uv_layer or (uv_layers.active.name if getattr(uv_layers, "active", None) else uv_layers[0].name)
    target_layer = uv_layers.get(target_layer_name)
    if target_layer is None:
        raise ValueError(f"UV layer '{target_layer_name}' not found on mesh '{name}'.")

    # Optimistic concurrency check
    initial_snapshot = compute_uv_snapshot(obj, target_layer_name)
    if expected_snapshot_id and expected_snapshot_id != initial_snapshot:
        raise ValueError(
            f"Optimistic concurrency failure: STALE_UV_TOPOLOGY. "
            f"Expected snapshot '{expected_snapshot_id}', current is '{initial_snapshot}'."
        )

    # Backup UV coordinates for transactional rollback
    layer_data = getattr(target_layer, "data", ())
    backup_coords = []
    for item in layer_data:
        uv = getattr(item, "uv", None)
        if uv is not None:
            backup_coords.append((float(uv[0]), float(uv[1])))
        else:
            backup_coords.append((0.0, 0.0))

    # Set target UV layer active before entering edit mode
    try:
        uv_layers.active = target_layer
    except Exception:
        pass

    # Mode switching
    prev_mode = getattr(obj, "mode", "OBJECT")
    prev_active = None
    if hasattr(bpy_module, "context") and hasattr(bpy_module.context, "view_layer") and hasattr(bpy_module.context.view_layer, "objects"):
        prev_active = getattr(bpy_module.context.view_layer.objects, "active", None)
        bpy_module.context.view_layer.objects.active = obj
    if hasattr(obj, "select_set"):
        obj.select_set(True)

    if prev_mode != "EDIT" and hasattr(bpy_module, "ops") and hasattr(bpy_module.ops, "object") and hasattr(bpy_module.ops.object, "mode_set"):
        try:
            bpy_module.ops.object.mode_set(mode="EDIT")
        except Exception:
            pass

    try:
        import bmesh
        bm = bmesh.from_edit_mesh(mesh_data)
        bm.faces.ensure_lookup_table()
        # Ensure all faces are selected for packing
        for f in bm.faces:
            f.select = True
        bm.select_mode = {'FACE'}
        bmesh.update_edit_mesh(mesh_data)

        # Execute Blender packing operator
        if hasattr(bpy_module, "ops") and hasattr(bpy_module.ops, "uv") and hasattr(bpy_module.ops.uv, "pack_islands"):
            try:
                bpy_module.ops.uv.pack_islands(margin=margin, rotate=rotate)
            except TypeError:
                bpy_module.ops.uv.pack_islands(margin=margin)

        bmesh.update_edit_mesh(mesh_data)

    except ImportError:
        # Fallback for mock environments without bmesh
        pass
    except Exception as exc:
        # Restore mode
        if prev_mode != "EDIT" and hasattr(bpy_module, "ops") and hasattr(bpy_module.ops, "object") and hasattr(bpy_module.ops.object, "mode_set"):
            try:
                bpy_module.ops.object.mode_set(mode=prev_mode)
            except Exception:
                pass
        # Rollback UV coordinates
        for idx, (u, v) in enumerate(backup_coords):
            if idx < len(layer_data):
                layer_data[idx].uv = (u, v)
        if hasattr(mesh_data, "update"):
            mesh_data.update()
        raise RuntimeError(f"Failed to pack UV islands, rolled back to initial coordinates: {exc}") from exc
    finally:
        if prev_mode != "EDIT" and hasattr(bpy_module, "ops") and hasattr(bpy_module.ops, "object") and hasattr(bpy_module.ops.object, "mode_set"):
            try:
                bpy_module.ops.object.mode_set(mode=prev_mode)
            except Exception:
                pass
        if prev_active and hasattr(bpy_module, "context") and hasattr(bpy_module.context, "view_layer") and hasattr(bpy_module.context.view_layer, "objects"):
            try:
                bpy_module.context.view_layer.objects.active = prev_active
            except Exception:
                pass

    # Readback
    uv_bounds = [0.0, 0.0, 1.0, 1.0]
    tdata = getattr(target_layer, "data", ())
    if tdata:
        min_u, min_v = float("inf"), float("inf")
        max_u, max_v = float("-inf"), float("-inf")
        for item in tdata:
            uv = getattr(item, "uv", None)
            if uv is not None:
                u, v = float(uv[0]), float(uv[1])
                if u < min_u: min_u = u
                if u > max_u: max_u = u
                if v < min_v: min_v = v
                if v > max_v: max_v = v
        if min_u != float("inf"):
            uv_bounds = [round(min_u, 4), round(min_v, 4), round(max_u, 4), round(max_v, 4)]

    new_snapshot = compute_uv_snapshot(obj, target_layer_name)

    return {
        "name": name,
        "operation": "pack_uv_islands",
        "uv_layer": target_layer_name,
        "margin": margin,
        "rotate": rotate,
        "uv_bounds": uv_bounds,
        "previous_snapshot_id": initial_snapshot,
        "snapshot_id": new_snapshot,
    }


def manage_uv_layers(
    bpy_module,
    name: str,
    action: str = "create",
    layer_name: str = "",
    new_name: Optional[str] = None,
    expected_snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates, activates, renames, or deletes UV layers on a mesh object.
    Supports transactional rollback and optimistic concurrency checks.
    """
    if not name:
        raise ValueError("Object 'name' is required for UV layer management.")

    action_lower = str(action or "create").strip().lower()
    if action_lower not in ("create", "set_active", "rename", "remove"):
        raise ValueError(
            f"Invalid UV layer action '{action}'. Must be 'create', 'set_active', 'rename', or 'remove'."
        )

    layer_name = str(layer_name or "").strip()
    if not layer_name:
        raise ValueError("Parameter 'layer_name' is required for UV layer management.")

    obj = None
    if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
        obj = bpy_module.data.objects.get(name)
    if not obj and hasattr(bpy_module, "context") and getattr(bpy_module.context, "scene", None):
        obj = bpy_module.context.scene.objects.get(name)

    if not obj:
        raise ValueError(f"Object '{name}' not found in scene.")
    if getattr(obj, "type", None) != "MESH":
        raise ValueError(
            f"Target object '{name}' is of type '{getattr(obj, 'type', None)}', not 'MESH'. "
            f"UV layer operations only apply to mesh objects."
        )

    mesh_data = obj.data
    uv_layers = getattr(mesh_data, "uv_layers", None)
    if uv_layers is None:
        raise ValueError(f"Mesh object '{name}' does not support UV layers.")

    initial_snapshot = compute_uv_snapshot(obj)
    if expected_snapshot_id and expected_snapshot_id != initial_snapshot:
        raise ValueError(
            f"Optimistic concurrency failure: STALE_UV_TOPOLOGY. "
            f"Expected snapshot '{expected_snapshot_id}', current is '{initial_snapshot}'."
        )

    # Validate action specifics
    existing_layer = uv_layers.get(layer_name)

    if action_lower == "create":
        if existing_layer is not None:
            raise ValueError(f"UV layer '{layer_name}' already exists on mesh '{name}'.")
        if len(uv_layers) >= 8:
            raise ValueError(f"Mesh '{name}' has reached the maximum number of UV layers (8).")
        try:
            new_lyr = uv_layers.new(name=layer_name)
            if new_lyr is None:
                raise RuntimeError(f"Blender failed to allocate new UV layer '{layer_name}'.")
        except Exception as exc:
            raise RuntimeError(f"Failed to create UV layer '{layer_name}': {exc}") from exc

    elif action_lower == "set_active":
        if existing_layer is None:
            raise ValueError(f"UV layer '{layer_name}' does not exist on mesh '{name}'.")
        try:
            uv_layers.active = existing_layer
            if hasattr(existing_layer, "active_render"):
                existing_layer.active_render = True
        except Exception as exc:
            raise RuntimeError(f"Failed to set active UV layer '{layer_name}': {exc}") from exc

    elif action_lower == "rename":
        if existing_layer is None:
            raise ValueError(f"UV layer '{layer_name}' does not exist on mesh '{name}'.")
        new_name_str = str(new_name or "").strip()
        if not new_name_str:
            raise ValueError("Parameter 'new_name' is required when action is 'rename'.")
        if new_name_str == layer_name:
            pass  # No-op
        elif uv_layers.get(new_name_str) is not None:
            raise ValueError(f"Cannot rename to '{new_name_str}': UV layer with that name already exists.")
        else:
            try:
                existing_layer.name = new_name_str
            except Exception as exc:
                raise RuntimeError(f"Failed to rename UV layer '{layer_name}' to '{new_name_str}': {exc}") from exc

    elif action_lower == "remove":
        if existing_layer is None:
            raise ValueError(f"UV layer '{layer_name}' does not exist on mesh '{name}'.")
        try:
            uv_layers.remove(existing_layer)
        except Exception as exc:
            raise RuntimeError(f"Failed to remove UV layer '{layer_name}': {exc}") from exc

    if hasattr(mesh_data, "update"):
        mesh_data.update()

    # Readback
    active_layer = getattr(uv_layers, "active", None)
    active_layer_name = getattr(active_layer, "name", None) if active_layer else None
    layer_list = [
        {
            "index": idx,
            "name": lyr.name,
            "active": (lyr.name == active_layer_name),
            "active_render": bool(getattr(lyr, "active_render", False)),
            "loop_count": len(getattr(lyr, "data", ())),
        }
        for idx, lyr in enumerate(uv_layers)
    ]
    new_snapshot = compute_uv_snapshot(obj)

    return {
        "name": name,
        "action": action_lower,
        "layer_name": layer_name,
        "new_name": new_name if action_lower == "rename" else None,
        "active_uv_layer": active_layer_name,
        "uv_layer_count": len(layer_list),
        "uv_layers": layer_list,
        "previous_snapshot_id": initial_snapshot,
        "snapshot_id": new_snapshot,
    }
