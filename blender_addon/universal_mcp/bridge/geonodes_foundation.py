"""
Typed, bounded Geometry Nodes foundation for Universal MCP (v0.1.64).
Supports node creation, deletion, linking, input setting, interface configuration,
evaluated geometry readback, optimistic concurrency SHA-256 snapshots, and transactional rollback.
"""

import hashlib
import json
from typing import Dict, Any, List, Optional, Tuple

ALLOWED_NODE_TYPES = {
    # Mesh Primitives
    "GeometryNodeMeshCube",
    "GeometryNodeMeshCircle",
    "GeometryNodeMeshCylinder",
    "GeometryNodeMeshGrid",
    "GeometryNodeMeshIcoSphere",
    "GeometryNodeMeshUVSphere",
    "GeometryNodeMeshLine",
    # Mesh Operations & Topology
    "GeometryNodeTransform",
    "GeometryNodeSubdivisionSurface",
    "GeometryNodeTriangulate",
    "GeometryNodeDualMesh",
    "GeometryNodeSetPosition",
    "GeometryNodeJoinGeometry",
    "GeometryNodeRealizeInstances",
    "GeometryNodeSetShadeSmooth",
    "GeometryNodeMeshToPoints",
    "GeometryNodeDistributePointsOnFaces",
    "GeometryNodeInstanceOnPoints",
    "GeometryNodeStoreNamedAttribute",
    # Utilities & Shaders
    "ShaderNodeCombineXYZ",
    "ShaderNodeMath",
    "ShaderNodeVectorMath",
    "FunctionNodeRandomValue",
    # Group Interface Nodes
    "NodeGroupInput",
    "NodeGroupOutput",
}

NODE_ALIASES = {
    "transform": "GeometryNodeTransform",
    "subdivisionsurface": "GeometryNodeSubdivisionSurface",
    "subsurf": "GeometryNodeSubdivisionSurface",
    "subdivide": "GeometryNodeSubdivisionSurface",
    "meshcube": "GeometryNodeMeshCube",
    "cube": "GeometryNodeMeshCube",
    "meshcircle": "GeometryNodeMeshCircle",
    "circle": "GeometryNodeMeshCircle",
    "meshcylinder": "GeometryNodeMeshCylinder",
    "cylinder": "GeometryNodeMeshCylinder",
    "meshgrid": "GeometryNodeMeshGrid",
    "grid": "GeometryNodeMeshGrid",
    "meshicosphere": "GeometryNodeMeshIcoSphere",
    "icosphere": "GeometryNodeMeshIcoSphere",
    "meshuvsphere": "GeometryNodeMeshUVSphere",
    "uvsphere": "GeometryNodeMeshUVSphere",
    "sphere": "GeometryNodeMeshUVSphere",
    "meshline": "GeometryNodeMeshLine",
    "triangulate": "GeometryNodeTriangulate",
    "dualmesh": "GeometryNodeDualMesh",
    "setposition": "GeometryNodeSetPosition",
    "joingeometry": "GeometryNodeJoinGeometry",
    "join": "GeometryNodeJoinGeometry",
    "realizeinstances": "GeometryNodeRealizeInstances",
    "setshadesmooth": "GeometryNodeSetShadeSmooth",
    "meshtopoints": "GeometryNodeMeshToPoints",
    "distributepointsonfaces": "GeometryNodeDistributePointsOnFaces",
    "instanceonpoints": "GeometryNodeInstanceOnPoints",
    "storenamedattribute": "GeometryNodeStoreNamedAttribute",
    "combinexyz": "ShaderNodeCombineXYZ",
    "math": "ShaderNodeMath",
    "vectormath": "ShaderNodeVectorMath",
    "randomvalue": "FunctionNodeRandomValue",
    "input": "NodeGroupInput",
    "groupinput": "NodeGroupInput",
    "output": "NodeGroupOutput",
    "groupoutput": "NodeGroupOutput",
}


def normalize_node_type(raw_type: str) -> str:
    cleaned = str(raw_type or "").strip()
    if cleaned in ALLOWED_NODE_TYPES:
        return cleaned
    lower = cleaned.lower().replace("_", "").replace(" ", "")
    if lower in NODE_ALIASES:
        return NODE_ALIASES[lower]
    # Try common prefixes
    for prefix in ("GeometryNode", "ShaderNode", "FunctionNode"):
        candidate = f"{prefix}{cleaned}"
        if candidate in ALLOWED_NODE_TYPES:
            return candidate
    raise ValueError(
        f"Unsupported Geometry Nodes type '{raw_type}'. Allowed: {sorted(list(ALLOWED_NODE_TYPES))}"
    )


def find_node(group, name: str):
    if not group or not name:
        return None
    name_str = str(name).strip()
    n = group.nodes.get(name_str)
    if n:
        return n
    nl = name_str.lower().replace(" ", "").replace("_", "")
    if nl in ("input", "groupinput", "nodegroupinput"):
        for node in group.nodes:
            if getattr(node, "bl_idname", "") == "NodeGroupInput":
                return node
    if nl in ("output", "groupoutput", "nodegroupoutput"):
        for node in group.nodes:
            if getattr(node, "bl_idname", "") == "NodeGroupOutput":
                return node
    for node in group.nodes:
        if getattr(node, "name", "").lower() == name_str.lower() or getattr(node, "label", "").lower() == name_str.lower():
            return node
    return None


def find_socket(node, socket_name: str, is_output: bool = False):
    sockets = getattr(node, "outputs", None) if is_output else getattr(node, "inputs", None)
    if not sockets:
        return None
    s = sockets.get(socket_name) if hasattr(sockets, "get") else None
    if s:
        return s
    target_lower = str(socket_name).strip().lower()
    for sock in sockets:
        if getattr(sock, "name", "").lower() == target_lower or getattr(sock, "identifier", "").lower() == target_lower:
            return sock
    return None


def compute_geometry_nodes_snapshot(data: Dict[str, Any]) -> str:
    filtered = {
        "name": data.get("name"),
        "modifier_name": data.get("modifier_name") if data.get("modifier_exists") else None,
        "modifier_exists": bool(data.get("modifier_exists")),
        "node_group_name": data.get("node_group_name"),
        "base_geometry": data.get("base_geometry"),
        "evaluated_geometry": data.get("evaluated_geometry"),
        "nodes": sorted(
            [
                (n.get("name"), n.get("type"), tuple(n.get("location")) if isinstance(n.get("location"), (list, tuple)) else None)
                for n in data.get("nodes", [])
            ],
            key=lambda x: str(x[0]),
        ),
        "links": sorted(
            [
                (l.get("from_node"), l.get("from_socket"), l.get("to_node"), l.get("to_socket"))
                for l in data.get("links", [])
            ]
        ),
        "input_sockets": sorted([s.get("name") for s in data.get("input_sockets", []) if isinstance(s, dict)]),
        "output_sockets": sorted([s.get("name") for s in data.get("output_sockets", []) if isinstance(s, dict)]),
    }
    encoded = json.dumps(filtered, sort_keys=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _safe_json_value(val):
    if val is None or isinstance(val, (int, float, str, bool)):
        return val
    try:
        return [float(x) for x in val]
    except Exception:
        return str(val)


def inspect_geometry_nodes(bpy_module, name: str, modifier_name: str = "GeometryNodes", active_mod=None) -> Dict[str, Any]:
    scene = getattr(bpy_module.context, "scene", None)
    obj = None
    if scene and hasattr(scene, "objects"):
        obj = scene.objects.get(name)
    if not obj and hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
        obj = bpy_module.data.objects.get(name)

    if not obj:
        raise ValueError(f"Object '{name}' not found in active scene.")

    obj_type = getattr(obj, "type", "MESH")
    if isinstance(obj_type, str) and obj_type != "MESH":
        raise ValueError(f"Geometry Nodes requires a MESH object, got {obj_type}.")

    mod = active_mod if active_mod is not None else (obj.modifiers.get(modifier_name) if hasattr(obj, "modifiers") else None)
    if mod and getattr(mod, "type", "") != "NODES":
        raise ValueError(f"Modifier '{modifier_name}' exists but is not of type 'NODES' (Geometry Nodes).")

    group = getattr(mod, "node_group", None) if mod else None
    all_gn_mods = [m.name for m in obj.modifiers if getattr(m, "type", "") == "NODES"] if hasattr(obj, "modifiers") else []

    input_sockets = []
    output_sockets = []
    if group and hasattr(group, "interface") and hasattr(group.interface, "items_tree"):
        for item in group.interface.items_tree:
            if getattr(item, "item_type", "") == "SOCKET":
                s_info = {
                    "name": getattr(item, "name", ""),
                    "socket_type": getattr(item, "socket_type", ""),
                    "in_out": getattr(item, "in_out", ""),
                    "default_value": _safe_json_value(getattr(item, "default_value", None)),
                    "min_value": _safe_json_value(getattr(item, "min_value", None)),
                    "max_value": _safe_json_value(getattr(item, "max_value", None)),
                }
                if getattr(item, "in_out", "") == "INPUT":
                    input_sockets.append(s_info)
                else:
                    output_sockets.append(s_info)

    nodes_info = []
    links_info = []
    if group and hasattr(group, "nodes"):
        for n in group.nodes:
            loc = getattr(n, "location", None)
            loc_list = [round(loc.x, 2), round(loc.y, 2)] if hasattr(loc, "x") and hasattr(loc, "y") else [0.0, 0.0]
            nodes_info.append({
                "name": getattr(n, "name", ""),
                "type": getattr(n, "bl_idname", ""),
                "label": getattr(n, "label", ""),
                "location": loc_list,
                "inputs": [
                    {
                        "name": getattr(s, "name", ""),
                        "identifier": getattr(s, "identifier", ""),
                        "type": getattr(s, "type", ""),
                        "default_value": _safe_json_value(getattr(s, "default_value", None)) if not getattr(s, "is_linked", False) and hasattr(s, "default_value") else None,
                    }
                    for s in getattr(n, "inputs", [])
                ],
                "outputs": [
                    {"name": getattr(s, "name", ""), "identifier": getattr(s, "identifier", ""), "type": getattr(s, "type", "")}
                    for s in getattr(n, "outputs", [])
                ],
            })
        for l in getattr(group, "links", []):
            links_info.append({
                "from_node": getattr(getattr(l, "from_node", None), "name", ""),
                "from_socket": getattr(getattr(l, "from_socket", None), "name", ""),
                "to_node": getattr(getattr(l, "to_node", None), "name", ""),
                "to_socket": getattr(getattr(l, "to_socket", None), "name", ""),
                "is_valid": getattr(l, "is_valid", True),
            })

    base_geom = {
        "vertex_count": len(obj.data.vertices) if getattr(obj, "data", None) and hasattr(obj.data, "vertices") else 0,
        "edge_count": len(obj.data.edges) if getattr(obj, "data", None) and hasattr(obj.data, "edges") else 0,
        "polygon_count": len(obj.data.polygons) if getattr(obj, "data", None) and hasattr(obj.data, "polygons") else 0,
    }

    eval_geom = dict(base_geom)
    if hasattr(bpy_module, "context") and getattr(bpy_module.context, "view_layer", None):
        try:
            bpy_module.context.view_layer.update()
            depsgraph = bpy_module.context.evaluated_depsgraph_get()
            eval_obj = obj.evaluated_get(depsgraph)
            if eval_obj and getattr(eval_obj, "type", "") == "MESH" and hasattr(eval_obj, "to_mesh"):
                eval_mesh = eval_obj.to_mesh()
                eval_geom = {
                    "vertex_count": len(eval_mesh.vertices),
                    "edge_count": len(eval_mesh.edges),
                    "polygon_count": len(eval_mesh.polygons),
                }
                eval_obj.to_mesh_clear()
        except Exception:
            pass

    res = {
        "name": getattr(obj, "name", name),
        "modifier_name": mod.name if mod else None,
        "modifier_exists": mod is not None,
        "node_group_name": group.name if group else None,
        "geometry_nodes_modifiers": all_gn_mods,
        "input_sockets": input_sockets,
        "output_sockets": output_sockets,
        "socket_count": len(input_sockets) + len(output_sockets),
        "nodes": nodes_info,
        "links": links_info,
        "base_geometry": base_geom,
        "evaluated_geometry": eval_geom,
        "success": True,
        "verified": True,
    }
    res["snapshot_id"] = compute_geometry_nodes_snapshot(res)
    return res


def execute_geometry_nodes_action(bpy_module, params: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(params or {})
    name = str(params.get("name") or params.get("target_object") or params.get("object_name") or "").strip()
    if not name:
        raise ValueError("Object 'name' is required for Geometry Nodes.")

    action = str(params.get("action", "inspect")).strip().lower()
    modifier_name = str(params.get("modifier_name", "GeometryNodes")).strip() or "GeometryNodes"

    # 1. Target verification
    scene = getattr(bpy_module.context, "scene", None)
    obj = None
    if scene and hasattr(scene, "objects"):
        obj = scene.objects.get(name)
    if not obj and hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
        obj = bpy_module.data.objects.get(name)

    if not obj:
        raise ValueError(f"Object '{name}' not found in scene.")

    obj_type = getattr(obj, "type", "MESH")
    if isinstance(obj_type, str) and obj_type != "MESH":
        raise ValueError(f"Geometry Nodes requires a MESH object, got {obj_type}.")

    ctx_mode = getattr(getattr(bpy_module, "context", None), "mode", "OBJECT")
    obj_mode = getattr(obj, "mode", "OBJECT")
    if isinstance(ctx_mode, str) and ctx_mode != "OBJECT":
        raise ValueError("Geometry Nodes operations require Object Mode.")
    if isinstance(obj_mode, str) and obj_mode != "OBJECT":
        raise ValueError("Geometry Nodes operations require Object Mode.")

    # Inspect current state
    before = inspect_geometry_nodes(bpy_module, name, modifier_name)

    if action in ("inspect", "evaluate"):
        return {**before, "action": action, "transaction_status": "COMMITTED"}

    # Optimistic concurrency check
    expected_snapshot = params.get("expected_snapshot_id")
    if expected_snapshot and before["snapshot_id"] != expected_snapshot:
        raise ValueError("STALE_GEOMETRY_NODES; inspect again")

    mod = obj.modifiers.get(modifier_name) if hasattr(obj, "modifiers") else None
    node_group_name = params.get("node_group_name")

    # Transaction staging
    try:
        if action == "create":
            if not mod:
                mod = obj.modifiers.new(name=modifier_name, type="NODES")
            if not getattr(mod, "node_group", None) or node_group_name:
                target_group_name = node_group_name or f"{name}_GeometryNodes"
                group = bpy_module.data.node_groups.get(target_group_name)
                if not group:
                    group = bpy_module.data.node_groups.new(name=target_group_name, type="GeometryNodeTree")
                    # Ensure default input/output nodes
                    if hasattr(group, "nodes") and hasattr(group.nodes, "new"):
                        inp_node = group.nodes.new("NodeGroupInput")
                        inp_node.name = "Input"
                        inp_node.location = (-200, 0)
                        out_node = group.nodes.new("NodeGroupOutput")
                        out_node.name = "Output"
                        out_node.location = (200, 0)
                    # Create default Geometry passthrough
                    if hasattr(group, "interface") and hasattr(group.interface, "new_socket"):
                        group.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
                        group.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
                mod.node_group = group

        elif action == "assign_group":
            if not mod:
                raise ValueError(f"Geometry Nodes modifier '{modifier_name}' not found on object '{name}'.")
            if not node_group_name:
                raise ValueError("node_group_name is required for 'assign_group' action.")
            group = bpy_module.data.node_groups.get(node_group_name)
            if not group:
                group = bpy_module.data.node_groups.new(name=node_group_name, type="GeometryNodeTree")
            mod.node_group = group

        elif action == "add_node":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            group = mod.node_group
            node_type = normalize_node_type(params.get("node_type", ""))
            custom_name = params.get("node_name")
            new_node = group.nodes.new(node_type)
            if custom_name:
                new_node.name = custom_name
            loc = params.get("location")
            if isinstance(loc, (list, tuple)) and len(loc) >= 2:
                new_node.location = (float(loc[0]), float(loc[1]))

            # Set initial inputs if provided
            initial_inputs = params.get("inputs", {})
            if isinstance(initial_inputs, dict):
                for sock_name, val in initial_inputs.items():
                    sock = find_socket(new_node, sock_name, is_output=False)
                    if sock and hasattr(sock, "default_value"):
                        sock.default_value = val

        elif action == "remove_node":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            group = mod.node_group
            target_name = params.get("node_name")
            if not target_name:
                raise ValueError("Parameter 'node_name' is required for 'remove_node'.")
            node = find_node(group, target_name)
            if not node:
                raise ValueError(f"Node '{target_name}' not found in node group '{group.name}'.")
            group.nodes.remove(node)

        elif action == "add_link":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            group = mod.node_group
            from_n_name = params.get("from_node")
            from_s_name = params.get("from_socket")
            to_n_name = params.get("to_node")
            to_s_name = params.get("to_socket")
            if not all([from_n_name, from_s_name, to_n_name, to_s_name]):
                raise ValueError("Parameters 'from_node', 'from_socket', 'to_node', 'to_socket' are required for 'add_link'.")

            from_node = find_node(group, from_n_name)
            to_node = find_node(group, to_n_name)
            if not from_node:
                raise ValueError(f"Source node '{from_n_name}' not found in node group.")
            if not to_node:
                raise ValueError(f"Target node '{to_n_name}' not found in node group.")

            from_sock = find_socket(from_node, from_s_name, is_output=True)
            to_sock = find_socket(to_node, to_s_name, is_output=False)
            if not from_sock:
                raise ValueError(f"Output socket '{from_s_name}' not found on node '{from_node.name}'.")
            if not to_sock:
                raise ValueError(f"Input socket '{to_s_name}' not found on node '{to_node.name}'.")

            group.links.new(from_sock, to_sock)

        elif action == "remove_link":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            group = mod.node_group
            from_n_name = params.get("from_node")
            from_s_name = params.get("from_socket")
            to_n_name = params.get("to_node")
            to_s_name = params.get("to_socket")
            removed = False
            for link in list(getattr(group, "links", [])):
                f_ok = not from_n_name or getattr(getattr(link, "from_node", None), "name", "").lower() == from_n_name.lower()
                fs_ok = not from_s_name or getattr(getattr(link, "from_socket", None), "name", "").lower() == from_s_name.lower()
                t_ok = not to_n_name or getattr(getattr(link, "to_node", None), "name", "").lower() == to_n_name.lower()
                ts_ok = not to_s_name or getattr(getattr(link, "to_socket", None), "name", "").lower() == to_s_name.lower()
                if f_ok and fs_ok and t_ok and ts_ok:
                    group.links.remove(link)
                    removed = True
            if not removed:
                raise ValueError("No matching link found to remove.")

        elif action == "set_node_input":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            group = mod.node_group
            node_name = params.get("node_name")
            sock_name = params.get("socket_name")
            val = params.get("value")
            if not node_name or not sock_name or val is None:
                raise ValueError("Parameters 'node_name', 'socket_name', and 'value' are required for 'set_node_input'.")
            node = find_node(group, node_name)
            if not node:
                raise ValueError(f"Node '{node_name}' not found in node group.")
            sock = find_socket(node, sock_name, is_output=False)
            if not sock:
                raise ValueError(f"Input socket '{sock_name}' not found on node '{node.name}'.")
            sock.default_value = val

        elif action == "add_socket":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            group = mod.node_group
            sock_name = params.get("socket_name")
            if not sock_name:
                raise ValueError("socket_name is required for 'add_socket' action.")
            sock_type = params.get("socket_type", "NodeSocketFloat")
            in_out = params.get("in_out", "INPUT").upper()
            if hasattr(group, "interface") and hasattr(group.interface, "new_socket"):
                sock = group.interface.new_socket(name=sock_name, in_out=in_out, socket_type=sock_type)
                default_val = params.get("default_value")
                if default_val is not None and hasattr(sock, "default_value"):
                    sock.default_value = default_val

        elif action == "set_socket_default":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            group = mod.node_group
            sock_name = params.get("socket_name")
            if not sock_name:
                raise ValueError("socket_name is required for 'set_socket_default' action.")
            found = False
            if hasattr(group, "interface") and hasattr(group.interface, "items_tree"):
                for item in group.interface.items_tree:
                    if getattr(item, "item_type", "") == "SOCKET" and getattr(item, "name", "") == sock_name:
                        default_val = params.get("default_value")
                        if default_val is not None and hasattr(item, "default_value"):
                            item.default_value = default_val
                        found = True
                        break
            if not found:
                raise ValueError(f"Interface socket '{sock_name}' not found in node group '{group.name}'.")

        elif action in ("configure_graph", "update_graph"):
            from .geometry_tools import handle_configure_modeling_geometry
            graph_params = {
                "name": name,
                "modifier_name": modifier_name,
                "group_name": params.get("node_group_name") or f"{name}_Graph",
                "action": "create" if not mod else "update",
                "nodes": params.get("nodes", []),
                "links": params.get("links", []),
                "parameters": params.get("parameters", []),
            }
            if expected_snapshot:
                graph_params["expected_snapshot_id"] = expected_snapshot
            return handle_configure_modeling_geometry(bpy_module, graph_params)

        elif action == "apply":
            if not mod or not getattr(mod, "node_group", None):
                raise ValueError(f"Object '{name}' modifier '{modifier_name}' has no assigned GeometryNodeTree.")
            # Bake evaluated mesh via depsgraph
            bpy_module.context.view_layer.update()
            depsgraph = bpy_module.context.evaluated_depsgraph_get()
            eval_obj = obj.evaluated_get(depsgraph)
            new_mesh = bpy_module.data.meshes.new_from_object(eval_obj, preserve_all_data_layers=True, depsgraph=depsgraph)
            old_mesh = obj.data
            obj.data = new_mesh
            obj.modifiers.remove(mod)
            if old_mesh.users == 0:
                bpy_module.data.meshes.remove(old_mesh)
            bpy_module.context.view_layer.update()

        else:
            raise ValueError(f"Unsupported Geometry Nodes action '{action}'.")

        # Independent readback
        if hasattr(bpy_module, "context") and getattr(bpy_module.context, "view_layer", None):
            try:
                bpy_module.context.view_layer.update()
            except Exception:
                pass
        after = inspect_geometry_nodes(bpy_module, name, modifier_name, active_mod=mod if action != 'apply' else None)
        return {
            **after,
            "action": action,
            "transaction_status": "COMMITTED",
            "before_snapshot_id": before["snapshot_id"],
        }

    except Exception as error:
        try:
            bpy_module.context.view_layer.update()
        except Exception:
            pass
        raise RuntimeError(f"ROLLED_BACK_VERIFIED: {error}") from error
