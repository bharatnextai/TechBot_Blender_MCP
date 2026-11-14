"""Bounded read-only base-mesh inspection. No bpy operators or dependencies."""
import hashlib
import math
import struct
import re
import threading

DOMAINS = ("vertices", "edges", "faces")
MAX_SNAPSHOT_ELEMENTS = 1_000_000
MAX_PAGE_INDICES = 10_000


def validate_topology_options(params, category):
    if any(key in params for key in ("element_domain", "mesh_source", "expected_snapshot_id")) and category != "mesh_topology":
        raise ValueError("element_domain is only valid for mesh_topology")
    if category != "mesh_topology":
        return
    for key, default, minimum, maximum in (("limit", 100, 1, 1000), ("offset", 0, 0, None)):
        value = params.get(key, default)
        if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f"{key} must be an integer in [{minimum}, {maximum if maximum is not None else 'unbounded'}]")
    target = params.get("target_name")
    if not isinstance(target, str) or not target.strip():
        raise ValueError("mesh_topology requires a non-empty target_name")
    if any(key in params for key in ("mesh_source", "expected_snapshot_id")) and "element_domain" not in params:
        raise ValueError("mesh_source/expected_snapshot_id require element_domain")
    if "mesh_source" in params and params["mesh_source"] not in ("base", "evaluated"):
        raise ValueError("mesh_source must be base or evaluated")
    if "expected_snapshot_id" in params:
        validate_snapshot_id(params["expected_snapshot_id"])
    if "element_domain" in params:
        if params.get("offset", 0) > 0 and "expected_snapshot_id" not in params:
            raise ValueError("Indexed pages after offset zero require expected_snapshot_id")
        if not isinstance(params["element_domain"], str) or params["element_domain"] not in DOMAINS:
            raise ValueError("element_domain must be vertices, edges or faces")
        allowed = {"category", "target_name", "element_domain", "limit", "offset", "include_parameters",
                   "session_id", "correlation_id", "request_id", "approval_token", "mesh_source", "expected_snapshot_id"}
        if set(params) - allowed:
            raise ValueError("Unknown indexed mesh inspection parameters")


def validate_snapshot_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("expected_snapshot_id must be sha256: followed by 64 lowercase hexadecimal characters")


def assert_base_snapshot(obj, context, expected):
    validate_snapshot_id(expected)
    actual = inspect_elements(obj, context, {"element_domain": "vertices", "limit": 1})["snapshot_id"]
    if actual != expected:
        raise ValueError("STALE_TOPOLOGY: base mesh changed; inspect again before editing")
    return actual


def inspect_elements(obj, context, params):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Mesh inspection requires Blender main thread")
    source = params.get("mesh_source", "base")
    if source not in ("base", "evaluated"):
        raise ValueError("mesh_source must be base or evaluated")
    if source == "base":
        return _inspect_elements(obj, context, params)
    if obj.type != "MESH" or obj.data is None or obj.mode != "OBJECT" or context.mode != "OBJECT" or obj.data.is_editmode:
        raise ValueError("Evaluated topology requires an Object Mode mesh; no mode switch was performed")
    if context.scene.objects.get(obj.name) != obj:
        raise ValueError("Indexed mesh target must belong to the active scene")
    graph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    try:
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        return _inspect_elements(obj, context, params, mesh=mesh, source="EVALUATED_MESH")
    finally:
        evaluated.to_mesh_clear()


def _inspect_elements(obj, context, params, mesh=None, source="BASE_MESH"):

    """Indices/fingerprint describe the supplied mesh snapshot, not stable edit IDs."""
    if obj.type != "MESH" or obj.data is None:
        raise ValueError("Indexed topology requires a mesh with geometry data")
    if getattr(obj, "mode", "OBJECT") != "OBJECT" or getattr(context, "mode", "OBJECT") != "OBJECT" or getattr(obj.data, "is_editmode", False):
        raise ValueError("Indexed mesh topology supports Object Mode only; no mode switch was performed")
    if context.scene.objects.get(obj.name) != obj:
        raise ValueError("Indexed mesh target must belong to the active scene")
    mesh = obj.data if mesh is None else mesh
    collections = {"vertices": mesh.vertices, "edges": mesh.edges, "faces": mesh.polygons}
    counts = [len(mesh.vertices), len(mesh.edges), len(mesh.polygons), len(mesh.loops)]
    if sum(counts) > MAX_SNAPSHOT_ELEMENTS:
        raise ValueError("Mesh exceeds indexed topology snapshot inspection budget")
    digest = hashlib.sha256(b"umcp-base-mesh-v1")
    if source != "BASE_MESH":
        digest.update(source.encode("ascii"))
    digest.update(struct.pack(">4Q", *counts))
    for vertex in mesh.vertices:
        coords = [float(c) for c in vertex.co]
        if len(coords) != 3 or not all(math.isfinite(c) for c in coords):
            raise ValueError("Mesh contains invalid vertex coordinates")
        digest.update(struct.pack(">Q3d", vertex.index, *coords))
    for collection in (mesh.edges, mesh.polygons):
        for item in collection:
            digest.update(struct.pack(">2Q", item.index, len(item.vertices)))
            for index in item.vertices:
                digest.update(struct.pack(">Q", index))
    state_digest=digest.copy()
    for collection in (mesh.vertices,mesh.edges,mesh.polygons):
        for item in collection:
            state_digest.update(bytes([bool(getattr(item,"select",False)),bool(getattr(item,"use_smooth",False))]))
    snapshot_id = "sha256:"+digest.hexdigest()
    if "expected_snapshot_id" in params:
        validate_snapshot_id(params["expected_snapshot_id"])
        if params["expected_snapshot_id"] != snapshot_id:
            raise ValueError("STALE_TOPOLOGY: snapshot changed between pages; restart inspection")
    domain = params["element_domain"]
    collection = collections[domain]
    offset, limit = params.get("offset", 0), params.get("limit", 100)
    start = min(offset, len(collection))
    page = collection[start:start+limit]
    if domain != "vertices" and sum(len(item.vertices) for item in page) > MAX_PAGE_INDICES:
        raise ValueError("Topology page exceeds connectivity budget; use a smaller limit")
    elements = [{"index": item.index, **({"co": [float(c) for c in item.co]} if domain == "vertices"
                else {"vertices": list(item.vertices), "material_index": int(getattr(item, "material_index", 0))} if domain == "faces"
                else {"vertices": list(item.vertices)})} for item in page]
    next_offset = offset+len(elements) if offset+len(elements) < len(collection) else None
    return {"element_domain": domain, "elements": elements, "offset": offset, "limit": limit,
            "total": len(collection), "returned": len(elements), "returned_count": len(elements), "next_offset": next_offset,
            "has_more": next_offset is not None, "coordinate_space": "LOCAL", "topology_source": source,
            "mode": "OBJECT", "snapshot_id": snapshot_id, "state_id":"sha256:"+state_digest.hexdigest(), "indices_are_snapshot_local": True,
            "vertex_count":counts[0],"edge_count":counts[1],"polygon_count":counts[2],"loop_count":counts[3]}
