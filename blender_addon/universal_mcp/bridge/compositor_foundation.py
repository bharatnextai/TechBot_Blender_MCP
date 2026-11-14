"""
Compositor Pipelines Foundation for Universal MCP (Phase 2.1 - v0.1.74).
Provides typed, bounded, snapshot-verified configuration and inspection
of Blender 5.2.2 LTS compositing node graphs and render pass outputs.
"""

from typing import Dict, Any, List, Optional, Tuple, Union
import hashlib
import json
import logging
import os

logger = logging.getLogger("UniversalMCP.Compositor")

# Canonical aliases for the 9 whitelisted compositor nodes
WHITELISTED_COMPOSITOR_NODES = {
    # Render Layers
    "compositor_rlayers": "CompositorNodeRLayers",
    "render_layers": "CompositorNodeRLayers",
    "rlayers": "CompositorNodeRLayers",
    "compositornoderlayers": "CompositorNodeRLayers",
    "r_layers": "CompositorNodeRLayers",

    # Composite / Group Output (Blender 5.2 uses NodeGroupOutput inside compositing node groups)
    "composite": "NodeGroupOutput",
    "group_output": "NodeGroupOutput",
    "output": "NodeGroupOutput",
    "nodegroupoutput": "NodeGroupOutput",
    "compositornodecomposite": "NodeGroupOutput",
    "compositornodegroupoutput": "NodeGroupOutput",

    # Viewer
    "viewer": "CompositorNodeViewer",
    "compositornodeviewer": "CompositorNodeViewer",

    # Denoise
    "denoise": "CompositorNodeDenoise",
    "compositornodedenoise": "CompositorNodeDenoise",

    # Color Balance
    "color_balance": "CompositorNodeColorBalance",
    "colorbalance": "CompositorNodeColorBalance",
    "compositornodecolorbalance": "CompositorNodeColorBalance",

    # Blur
    "blur": "CompositorNodeBlur",
    "compositornodeblur": "CompositorNodeBlur",

    # Glare
    "glare": "CompositorNodeGlare",
    "compositornodeglare": "CompositorNodeGlare",

    # Alpha Over
    "alpha_over": "CompositorNodeAlphaOver",
    "alphaover": "CompositorNodeAlphaOver",
    "compositornodealphaover": "CompositorNodeAlphaOver",

    # Output File
    "output_file": "CompositorNodeOutputFile",
    "file_output": "CompositorNodeOutputFile",
    "compositornodeoutputfile": "CompositorNodeOutputFile",

    # Cryptomatte (Milestone 9.1B)
    "cryptomatte": "CompositorNodeCryptomatteV2",
    "cryptomatte_v2": "CompositorNodeCryptomatteV2",
    "cryptomattev2": "CompositorNodeCryptomatteV2",
    "compositornodecryptomatte": "CompositorNodeCryptomatteV2",
    "compositornodecryptomattev2": "CompositorNodeCryptomatteV2",

    # Color Correction Nodes (Milestone 9.1C)
    # RGB Curves / Curve Color
    "curve_color": "CompositorNodeCurveRGB",
    "curvecolor": "CompositorNodeCurveRGB",
    "curve_rgb": "CompositorNodeCurveRGB",
    "curvergb": "CompositorNodeCurveRGB",
    "rgb_curves": "CompositorNodeCurveRGB",
    "rgbcurves": "CompositorNodeCurveRGB",
    "curves": "CompositorNodeCurveRGB",
    "compositornodecurvecolor": "CompositorNodeCurveRGB",
    "compositornodecurvergb": "CompositorNodeCurveRGB",

    # Hue / Saturation / Value
    "hue_sat": "CompositorNodeHueSat",
    "huesat": "CompositorNodeHueSat",
    "hue_saturation": "CompositorNodeHueSat",
    "huesaturation": "CompositorNodeHueSat",
    "hue_saturation_value": "CompositorNodeHueSat",
    "hsv": "CompositorNodeHueSat",
    "compositornodehuesat": "CompositorNodeHueSat",

    # Exposure
    "exposure": "CompositorNodeExposure",
    "compositornodeexposure": "CompositorNodeExposure",

    # Tonemap
    "tonemap": "CompositorNodeTonemap",
    "tone_map": "CompositorNodeTonemap",
    "compositornodetonemap": "CompositorNodeTonemap",

    # Visual Effects Nodes (Milestone 9.1D)
    # Lens Distortion
    "lens_distortion": "CompositorNodeLensdist",
    "lensdistortion": "CompositorNodeLensdist",
    "lens_dist": "CompositorNodeLensdist",
    "lensdist": "CompositorNodeLensdist",
    "compositornodelensdist": "CompositorNodeLensdist",

    # Defocus
    "defocus": "CompositorNodeDefocus",
    "compositornodedefocus": "CompositorNodeDefocus",

    # Filter
    "filter": "CompositorNodeFilter",
    "compositornodefilter": "CompositorNodeFilter",

    # Geometric & ID Masks (Milestone 9.1E)
    # Box Mask
    "box_mask": "CompositorNodeBoxMask",
    "boxmask": "CompositorNodeBoxMask",
    "box": "CompositorNodeBoxMask",
    "compositornodeboxmask": "CompositorNodeBoxMask",

    # Ellipse Mask
    "ellipse_mask": "CompositorNodeEllipseMask",
    "ellipsemask": "CompositorNodeEllipseMask",
    "ellipse": "CompositorNodeEllipseMask",
    "circle_mask": "CompositorNodeEllipseMask",
    "circlemask": "CompositorNodeEllipseMask",
    "compositornodeellipsemask": "CompositorNodeEllipseMask",

    # ID Mask
    "id_mask": "CompositorNodeIDMask",
    "idmask": "CompositorNodeIDMask",
    "compositornodeidmask": "CompositorNodeIDMask",
}

ALLOWED_RENDER_PASSES = {
    # Geometry & auxiliary
    "z": "use_pass_z",
    "depth": "use_pass_z",
    "normal": "use_pass_normal",
    "mist": "use_pass_mist",
    "object_index": "use_pass_object_index",
    "object_id": "use_pass_object_index",
    "index_object": "use_pass_object_index",
    "indexob": "use_pass_object_index",
    "material_index": "use_pass_material_index",
    "material_id": "use_pass_material_index",
    "index_material": "use_pass_material_index",
    "indexma": "use_pass_material_index",
    # Shading & lighting color
    "diffuse": "use_pass_diffuse_color",
    "diffuse_color": "use_pass_diffuse_color",
    "glossy": "use_pass_glossy_color",
    "glossy_color": "use_pass_glossy_color",
    # Lighting & environment components (Milestone 9.1A)
    "ambient_occlusion": "use_pass_ambient_occlusion",
    "ambient occlusion": "use_pass_ambient_occlusion",
    "ao": "use_pass_ambient_occlusion",
    "shadow": "use_pass_shadow",
    "emission": "use_pass_emit",
    "emit": "use_pass_emit",
    "environment": "use_pass_environment",
    "env": "use_pass_environment",
    # Cryptomatte metadata generation passes (Milestone 9.1B)
    "cryptomatte_object": "use_pass_cryptomatte_object",
    "crypto_object": "use_pass_cryptomatte_object",
    "cryptomatte_material": "use_pass_cryptomatte_material",
    "crypto_material": "use_pass_cryptomatte_material",
    "cryptomatte_asset": "use_pass_cryptomatte_asset",
    "crypto_asset": "use_pass_cryptomatte_asset",
}

GLARE_TYPE_MAP = {
    "fog_glow": "Fog Glow",
    "fog glow": "Fog Glow",
    "fog": "Fog Glow",
    "bloom": "Bloom",
    "streaks": "Streaks",
    "ghosts": "Ghosts",
    "simple_star": "Simple Star",
    "simple star": "Simple Star",
    "sun_beams": "Sun Beams",
    "sun beams": "Sun Beams",
    "kernel": "Kernel",
}

QUALITY_MAP = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

TONEMAP_TYPE_MAP = {
    "rd_photoreceptor": "R/D Photoreceptor",
    "photoreceptor": "R/D Photoreceptor",
    "r/d photoreceptor": "R/D Photoreceptor",
    "rd": "R/D Photoreceptor",
    "rh_simple": "Rh Simple",
    "simple": "Rh Simple",
    "rh": "Rh Simple",
    "rh simple": "Rh Simple",
}

LENSDIST_TYPE_MAP = {
    "radial": "Radial",
    "horizontal": "Horizontal",
}

FILTER_TYPE_MAP = {
    "soften": "Soften",
    "box_sharpen": "Box Sharpen",
    "box sharpen": "Box Sharpen",
    "box": "Box Sharpen",
    "diamond_sharpen": "Diamond Sharpen",
    "diamond sharpen": "Diamond Sharpen",
    "diamond": "Diamond Sharpen",
    "sharpen": "Box Sharpen",
    "laplace": "Laplace",
    "sobel": "Sobel",
    "prewitt": "Prewitt",
    "kirsch": "Kirsch",
    "shadow": "Shadow",
}

DEFOCUS_BOKEH_MAP = {
    "circle": "CIRCLE",
    "octagon": "OCTAGON",
    "heptagon": "HEPTAGON",
    "hexagon": "HEXAGON",
    "pentagon": "PENTAGON",
    "square": "SQUARE",
    "triangle": "TRIANGLE",
}

MASK_OPERATION_MAP = {
    "add": "Add",
    "subtract": "Subtract",
    "sub": "Subtract",
    "multiply": "Multiply",
    "mul": "Multiply",
    "not": "Not",
    "invert": "Not",
}


def canonical_node_type(raw_type: str, bpy_module: Any = None) -> str:
    """Resolves node type aliases to the canonical Blender 5.2.2 LTS type."""
    cleaned = str(raw_type).strip().lower().replace(" ", "_")
    if cleaned in WHITELISTED_COMPOSITOR_NODES:
        resolved = WHITELISTED_COMPOSITOR_NODES[cleaned]
        if resolved == "NodeGroupOutput" and bpy_module and hasattr(bpy_module, "types"):
            if hasattr(bpy_module.types, "CompositorNodeComposite"):
                return "CompositorNodeComposite"
        if resolved == "CompositorNodeCryptomatteV2" and bpy_module and hasattr(bpy_module, "types"):
            if not hasattr(bpy_module.types, "CompositorNodeCryptomatteV2") and hasattr(bpy_module.types, "CompositorNodeCryptomatte"):
                return "CompositorNodeCryptomatte"
        if resolved == "CompositorNodeCurveRGB" and bpy_module and hasattr(bpy_module, "types"):
            if not hasattr(bpy_module.types, "CompositorNodeCurveRGB") and hasattr(bpy_module.types, "CompositorNodeCurveColor"):
                return "CompositorNodeCurveColor"
        return resolved

    no_under = cleaned.replace("_", "")
    if no_under in WHITELISTED_COMPOSITOR_NODES:
        resolved = WHITELISTED_COMPOSITOR_NODES[no_under]
        if resolved == "NodeGroupOutput" and bpy_module and hasattr(bpy_module, "types"):
            if hasattr(bpy_module.types, "CompositorNodeComposite"):
                return "CompositorNodeComposite"
        if resolved == "CompositorNodeCryptomatteV2" and bpy_module and hasattr(bpy_module, "types"):
            if not hasattr(bpy_module.types, "CompositorNodeCryptomatteV2") and hasattr(bpy_module.types, "CompositorNodeCryptomatte"):
                return "CompositorNodeCryptomatte"
        if resolved == "CompositorNodeCurveRGB" and bpy_module and hasattr(bpy_module, "types"):
            if not hasattr(bpy_module.types, "CompositorNodeCurveRGB") and hasattr(bpy_module.types, "CompositorNodeCurveColor"):
                return "CompositorNodeCurveColor"
        return resolved

    raise ValueError(
        f"Unsupported compositor node type '{raw_type}'. "
        f"Allowed whitelisted types: {sorted(set(WHITELISTED_COMPOSITOR_NODES.values()))}"
    )


def get_or_create_compositor_tree(bpy_module: Any, scene: Any) -> Any:
    """
    Resolves or creates the CompositorNodeTree for the scene in Blender 5.2.2 LTS.
    Handles scene.compositing_node_group and scene.use_nodes.
    """
    if hasattr(scene, "use_nodes"):
        try:
            scene.use_nodes = True
        except Exception as ex:
            logger.debug(f"Warning setting scene.use_nodes: {ex}")

    tree = getattr(scene, "compositing_node_group", None)
    if tree is None and hasattr(scene, "node_tree"):
        tree = scene.node_tree

    if tree is None and hasattr(bpy_module, "ops") and hasattr(bpy_module.ops, "node"):
        try:
            bpy_module.ops.node.new_compositing_node_group()
            if hasattr(bpy_module.data, "node_groups") and bpy_module.data.node_groups:
                tree = bpy_module.data.node_groups[-1]
                scene.compositing_node_group = tree
        except Exception as ex:
            logger.debug(f"Could not invoke new_compositing_node_group: {ex}")

    if tree is None and hasattr(bpy_module.data, "node_groups"):
        tree = bpy_module.data.node_groups.new(f"{scene.name}_Compositor", "CompositorNodeTree")
        scene.compositing_node_group = tree

    if tree is None:
        raise RuntimeError(f"Failed to resolve or create CompositorNodeTree for scene '{scene.name}'")

    return tree


def compute_compositor_snapshot(tree: Any, view_layer: Any = None) -> Tuple[str, Dict[str, Any]]:
    """
    Computes a deterministic cryptographic SHA-256 snapshot of the compositor tree
    including nodes, parameters, links, and enabled render passes.
    """
    nodes_info = []
    if hasattr(tree, "nodes"):
        for n in tree.nodes:
            inputs_summary = {}
            for s in getattr(n, "inputs", []):
                s_name = getattr(s, "name", "")
                if hasattr(s, "default_value"):
                    val = s.default_value
                    if isinstance(val, (int, float, bool, str)):
                        inputs_summary[s_name] = val
                    elif hasattr(val, "__iter__"):
                        try:
                            inputs_summary[s_name] = [round(float(v), 5) for v in list(val)[:4]]
                        except Exception:
                            pass

            props_summary = {}
            for prop in ("glare_type", "threshold", "streaks", "quality", "filter_type", "size_x", "size_y", "directory", "file_name", "source", "layer_name", "matte_id", "f_stop", "blur_max", "bokeh", "angle", "use_zbuffer", "z_scale"):
                if hasattr(n, prop):
                    p_val = getattr(n, prop)
                    if isinstance(p_val, (int, float, bool, str)):
                        props_summary[prop] = p_val

            if hasattr(n, "mapping") and hasattr(n.mapping, "curves"):
                curve_pts = []
                for c in n.mapping.curves:
                    pts = [[round(float(p.location[0]), 4), round(float(p.location[1]), 4)] for p in getattr(c, "points", [])]
                    curve_pts.append(pts)
                props_summary["curves"] = curve_pts

            nodes_info.append({
                "name": getattr(n, "name", ""),
                "type": getattr(n, "bl_idname", getattr(n, "type", "")),
                "inputs": inputs_summary,
                "properties": props_summary,
            })
    nodes_info.sort(key=lambda x: x["name"])

    links_info = []
    if hasattr(tree, "links"):
        for l in tree.links:
            fn = getattr(getattr(l, "from_node", None), "name", "")
            fs = getattr(getattr(l, "from_socket", None), "name", "")
            tn = getattr(getattr(l, "to_node", None), "name", "")
            ts = getattr(getattr(l, "to_socket", None), "name", "")
            links_info.append({"from_node": fn, "from_socket": fs, "to_node": tn, "to_socket": ts})
    links_info.sort(key=lambda x: (x["from_node"], x["from_socket"], x["to_node"], x["to_socket"]))

    passes_info = {}
    if view_layer:
        for pass_key, attr in ALLOWED_RENDER_PASSES.items():
            if hasattr(view_layer, attr):
                passes_info[attr] = bool(getattr(view_layer, attr))

    state_dict = {
        "tree_name": getattr(tree, "name", ""),
        "nodes": nodes_info,
        "links": links_info,
        "render_passes": passes_info,
    }
    raw_json = json.dumps(state_dict, sort_keys=True, separators=(",", ":"))
    snapshot_id = f"sha256:{hashlib.sha256(raw_json.encode('utf-8')).hexdigest()}"
    return snapshot_id, state_dict


def find_socket(node: Any, socket_name: str, is_output: bool = False) -> Any:
    """Finds socket by exact name, identifier, or standard alias."""
    sockets = getattr(node, "outputs" if is_output else "inputs", [])
    if not sockets:
        return None

    # 1. Exact match by name
    for s in sockets:
        if getattr(s, "name", "") == socket_name:
            return s

    # 2. Match by identifier
    for s in sockets:
        if getattr(s, "identifier", "") == socket_name:
            return s

    # 3. Case-insensitive match
    lower_name = str(socket_name).lower().strip()
    for s in sockets:
        s_n = getattr(s, "name", "").lower()
        s_id = getattr(s, "identifier", "").lower()
        if s_n == lower_name or s_id == lower_name:
            return s

    # 4. Standard alias matching
    alias_map = {
        "z": "Depth",
        "depth": "Depth",
        "normal": "Normal",
        "mist": "Mist",
        "diffuse": "Diffuse Color",
        "diffcol": "Diffuse Color",
        "diffuse_color": "Diffuse Color",
        "diffuse color": "Diffuse Color",
        "glossy": "Glossy Color",
        "glosscol": "Glossy Color",
        "glossy_color": "Glossy Color",
        "glossy color": "Glossy Color",
        "ao": "Ambient Occlusion",
        "ambient_occlusion": "Ambient Occlusion",
        "ambient occlusion": "Ambient Occlusion",
        "shadow": "Shadow",
        "emission": "Emission",
        "emit": "Emission",
        "environment": "Environment",
        "env": "Environment",
        "matte": "Matte",
        "pick": "Pick",
        "composite": "Image",
        "out": "Image",
        "in": "Image",
        # Color correction socket aliases (Milestone 9.1C)
        "fac": "Factor",
        "factor": "Factor",
        "hue": "Hue",
        "sat": "Saturation",
        "saturation": "Saturation",
        "val": "Value",
        "value": "Value",
        "exposure": "Exposure",
        "exp": "Exposure",
        "black_level": "Black Level",
        "black level": "Black Level",
        "black": "Black Level",
        "white_level": "White Level",
        "white level": "White Level",
        "white": "White Level",
        "type": "Type",
        "key": "Key",
        "gamma": "Gamma",
        "balance": "Balance",
        "intensity": "Intensity",
        "contrast": "Contrast",
        "light_adaptation": "Light Adaptation",
        "light adaptation": "Light Adaptation",
        "chromatic_adaptation": "Chromatic Adaptation",
        "chromatic adaptation": "Chromatic Adaptation",
        # Visual Effects socket aliases (Milestone 9.1D)
        "distortion": "Distortion",
        "distort": "Distortion",
        "dist": "Distortion",
        "dispersion": "Dispersion",
        "disperse": "Dispersion",
        "disp": "Dispersion",
        "jitter": "Jitter",
        "fit": "Fit",
        "filter_type": "Type",
        "filter": "Type",
        "bokeh": "Bokeh",
        # Geometric and ID Mask socket aliases (Milestone 9.1E)
        "operation": "Operation",
        "op": "Operation",
        "mask": "Mask",
        "mask_in": "Mask",
        "mask_input": "Mask",
        "position": "Position",
        "pos": "Position",
        "size": "Size",
        "scale": "Size",
        "rotation": "Rotation",
        "rot": "Rotation",
        "angle_deg": "Rotation",
        "id_value": "ID value",
        "id": "ID value",
        "id_val": "ID value",
        "index": "Index",
        "pass_index": "Index",
        "anti_alias": "Anti-Alias",
        "antialias": "Anti-Alias",
        "aa": "Anti-Alias",
        "alpha": "Alpha",
        "object_index": "Object Index",
        "material_index": "Material Index",
    }
    target_name = alias_map.get(lower_name)
    if target_name:
        for s in sockets:
            if getattr(s, "name", "") == target_name:
                return s

    # 5. Fallback for single socket or default "Image"
    if lower_name in ("", "image"):
        for s in sockets:
            if getattr(s, "name", "") == "Image":
                return s
        if sockets:
            return sockets[0]

    return None


def execute_compositor_action(bpy_module: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main execution engine for compositor operations.
    Supports enable, inspect (list_nodes), create_node, remove_node, connect,
    disconnect, set_property, configure_render_passes.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    action = str(params.get("action", "inspect")).strip().lower()
    if action == "list_nodes":
        action = "inspect"

    # Resolve scene and view_layer
    scene_name = params.get("scene_name")
    scene = None
    if scene_name and hasattr(bpy_module.data, "scenes"):
        scene = bpy_module.data.scenes.get(scene_name)
    if not scene and hasattr(bpy_module, "context"):
        scene = getattr(bpy_module.context, "scene", None)
    if not scene:
        raise ValueError("Active scene not found.")

    view_layer = getattr(bpy_module.context, "view_layer", None)
    if not view_layer and hasattr(scene, "view_layers") and scene.view_layers:
        view_layer = scene.view_layers[0]

    tree = get_or_create_compositor_tree(bpy_module, scene)
    current_snap, current_state = compute_compositor_snapshot(tree, view_layer)

    # Concurrency verification (stale-state protection)
    expected_snap = params.get("expected_snapshot_id")
    if expected_snap and expected_snap != current_snap:
        raise ValueError(
            f"STALE_COMPOSITOR_GRAPH: Snapshot mismatch. "
            f"Expected '{expected_snap}', current state is '{current_snap}'. Inspect again."
        )

    # 1. Action 'enable'
    if action == "enable":
        new_snap, new_state = compute_compositor_snapshot(tree, view_layer)
        return {
            "status": "success",
            "action": "enable",
            "enabled": True,
            "scene_name": scene.name,
            "tree_name": getattr(tree, "name", ""),
            "node_count": len(new_state["nodes"]),
            "snapshot_id": new_snap,
            "verified": True,
        }

    # 2. Action 'inspect'
    if action == "inspect":
        return {
            "status": "success",
            "action": "inspect",
            "scene_name": scene.name,
            "tree_name": getattr(tree, "name", ""),
            "enabled": getattr(scene, "use_nodes", True),
            "node_count": len(current_state["nodes"]),
            "link_count": len(current_state["links"]),
            "nodes": current_state["nodes"],
            "links": current_state["links"],
            "render_passes": current_state["render_passes"],
            "snapshot_id": current_snap,
            "verified": True,
        }

    # 3. Action 'create_node'
    if action == "create_node":
        raw_type = params.get("node_type")
        if not raw_type:
            raise ValueError("Parameter 'node_type' is required for action 'create_node'.")

        canonical_type = canonical_node_type(raw_type, bpy_module)
        created_node = tree.nodes.new(canonical_type)

        custom_name = params.get("node_name")
        if custom_name:
            created_node.name = str(custom_name).strip()

        location = params.get("location")
        if isinstance(location, (list, tuple)) and len(location) >= 2:
            created_node.location = (float(location[0]), float(location[1]))

        # Apply initial inputs if specified
        inputs = params.get("inputs")
        if isinstance(inputs, dict):
            for sock_name, val in inputs.items():
                s = find_socket(created_node, sock_name, is_output=False)
                if s and hasattr(s, "default_value"):
                    try:
                        s.default_value = val
                    except Exception as ex:
                        logger.debug(f"Could not set default_value on {sock_name}: {ex}")

        # Independent readback
        new_snap, new_state = compute_compositor_snapshot(tree, view_layer)
        assert any(n["name"] == created_node.name for n in new_state["nodes"]), "Created node missing in readback"

        return {
            "status": "success",
            "action": "create_node",
            "node_name": created_node.name,
            "node_type": canonical_type,
            "inputs": [getattr(s, "name", "") for s in created_node.inputs],
            "outputs": [getattr(s, "name", "") for s in created_node.outputs],
            "snapshot_id": new_snap,
            "verified": True,
        }

    # 4. Action 'remove_node'
    if action == "remove_node":
        node_name = str(params.get("node_name", "")).strip()
        if not node_name:
            raise ValueError("Parameter 'node_name' is required for action 'remove_node'.")

        node_obj = tree.nodes.get(node_name)
        if not node_obj:
            raise ValueError(f"Compositor node '{node_name}' not found.")

        tree.nodes.remove(node_obj)
        new_snap, new_state = compute_compositor_snapshot(tree, view_layer)
        assert all(n["name"] != node_name for n in new_state["nodes"]), "Removed node still present in readback"

        return {
            "status": "success",
            "action": "remove_node",
            "removed_node_name": node_name,
            "node_count": len(new_state["nodes"]),
            "snapshot_id": new_snap,
            "verified": True,
        }

    # 5. Action 'connect'
    if action == "connect":
        from_node = str(params.get("from_node", "")).strip()
        from_socket = str(params.get("from_socket", "")).strip()
        to_node = str(params.get("to_node", "")).strip()
        to_socket = str(params.get("to_socket", "")).strip()

        if not from_node or not to_node:
            raise ValueError("Parameters 'from_node' and 'to_node' are required for action 'connect'.")

        fn = tree.nodes.get(from_node)
        if not fn:
            raise ValueError(f"Source node '{from_node}' not found.")
        tn = tree.nodes.get(to_node)
        if not tn:
            raise ValueError(f"Destination node '{to_node}' not found.")

        out_s = find_socket(fn, from_socket or "Image", is_output=True)
        if not out_s:
            raise ValueError(f"Output socket '{from_socket}' not found on node '{from_node}'. Available: {[s.name for s in fn.outputs]}")

        in_s = find_socket(tn, to_socket or "Image", is_output=False)
        if not in_s:
            raise ValueError(f"Input socket '{to_socket}' not found on node '{to_node}'. Available: {[s.name for s in tn.inputs]}")

        new_link = tree.links.new(out_s, in_s)
        new_snap, new_state = compute_compositor_snapshot(tree, view_layer)

        return {
            "status": "success",
            "action": "connect",
            "from_node": from_node,
            "from_socket": getattr(out_s, "name", from_socket),
            "to_node": to_node,
            "to_socket": getattr(in_s, "name", to_socket),
            "link_count": len(new_state["links"]),
            "snapshot_id": new_snap,
            "verified": True,
        }

    # 6. Action 'disconnect'
    if action == "disconnect":
        from_node = str(params.get("from_node", "")).strip()
        to_node = str(params.get("to_node", "")).strip()
        from_socket = str(params.get("from_socket", "")).strip()
        to_socket = str(params.get("to_socket", "")).strip()

        to_remove = []
        for l in list(tree.links):
            fn = getattr(getattr(l, "from_node", None), "name", "")
            tn = getattr(getattr(l, "to_node", None), "name", "")
            fs = getattr(getattr(l, "from_socket", None), "name", "")
            ts = getattr(getattr(l, "to_socket", None), "name", "")

            if from_node and fn != from_node:
                continue
            if to_node and tn != to_node:
                continue
            if from_socket and fs != from_socket:
                continue
            if to_socket and ts != to_socket:
                continue
            to_remove.append(l)

        for l in to_remove:
            tree.links.remove(l)

        new_snap, new_state = compute_compositor_snapshot(tree, view_layer)
        return {
            "status": "success",
            "action": "disconnect",
            "removed_links": len(to_remove),
            "link_count": len(new_state["links"]),
            "snapshot_id": new_snap,
            "verified": True,
        }

    # 7. Action 'set_property'
    if action == "set_property":
        node_name = str(params.get("node_name", "")).strip()
        if not node_name:
            raise ValueError("Parameter 'node_name' is required for action 'set_property'.")

        node_obj = tree.nodes.get(node_name)
        if not node_obj:
            raise ValueError(f"Compositor node '{node_name}' not found.")

        prop_name = str(params.get("property_name", "")).strip()
        prop_val = params.get("property_value")

        # Specific property validation and Blender 5.2 input socket adaptation
        node_type_id = getattr(node_obj, "bl_idname", getattr(node_obj, "type", ""))
        is_glare = node_type_id in ("CompositorNodeGlare", "GLARE")
        is_tonemap = node_type_id in ("CompositorNodeTonemap", "TONEMAP")

        if prop_name == "glare_type" or (prop_name == "type" and is_glare):
            val_clean = str(prop_val).strip().lower()
            if val_clean not in GLARE_TYPE_MAP:
                raise ValueError(f"Invalid glare type '{prop_val}'. Allowed: {sorted(set(GLARE_TYPE_MAP.values()))}.")
            canon_type = GLARE_TYPE_MAP[val_clean]
            if hasattr(node_obj, "inputs") and "Type" in node_obj.inputs:
                node_obj.inputs["Type"].default_value = canon_type
            elif hasattr(node_obj, "glare_type"):
                node_obj.glare_type = canon_type.upper().replace(" ", "_")

        elif prop_name == "threshold":
            val_float = float(prop_val)
            if val_float < 0.0 or val_float > 1000.0:
                raise ValueError(f"Threshold must be between 0.0 and 1000.0, got {val_float}")
            if hasattr(node_obj, "inputs") and "Threshold" in node_obj.inputs:
                node_obj.inputs["Threshold"].default_value = val_float
            elif hasattr(node_obj, "threshold"):
                node_obj.threshold = val_float

        elif prop_name == "quality":
            val_clean = str(prop_val).strip().lower()
            if val_clean not in QUALITY_MAP:
                raise ValueError(f"Invalid quality '{prop_val}'. Allowed: {sorted(set(QUALITY_MAP.values()))}.")
            canon_q = QUALITY_MAP[val_clean]
            if hasattr(node_obj, "inputs") and "Quality" in node_obj.inputs:
                node_obj.inputs["Quality"].default_value = canon_q
            elif hasattr(node_obj, "quality"):
                node_obj.quality = canon_q.upper()

        elif prop_name in ("size_x", "size_y", "size"):
            if hasattr(node_obj, "inputs") and "Size" in node_obj.inputs:
                s_sock = node_obj.inputs["Size"]
                cur_val = list(s_sock.default_value) if hasattr(s_sock.default_value, "__iter__") else [float(s_sock.default_value), float(s_sock.default_value)]
                if prop_name == "size_x":
                    val_float = float(prop_val)
                    if not 0 <= val_float <= 1024:
                        raise ValueError(f"size_x must be between 0 and 1024, got {val_float}")
                    s_sock.default_value = (val_float, cur_val[1] if len(cur_val) > 1 else val_float)
                elif prop_name == "size_y":
                    val_float = float(prop_val)
                    if not 0 <= val_float <= 1024:
                        raise ValueError(f"size_y must be between 0 and 1024, got {val_float}")
                    s_sock.default_value = (cur_val[0] if len(cur_val) > 0 else val_float, val_float)
                else: # size
                    if isinstance(prop_val, (list, tuple)):
                        s_sock.default_value = (float(prop_val[0]), float(prop_val[1]))
                    else:
                        v = float(prop_val)
                        s_sock.default_value = (v, v)
            elif hasattr(node_obj, prop_name):
                setattr(node_obj, prop_name, int(prop_val))
            else:
                raise ValueError(f"Size property '{prop_name}' could not be applied to node '{node_name}'.")

        elif prop_name in ("directory", "base_path"):
            val_str = str(prop_val)
            if hasattr(node_obj, "directory"):
                node_obj.directory = val_str
            elif hasattr(node_obj, "base_path"):
                node_obj.base_path = val_str

        elif prop_name in ("layer_name", "matte_type", "cryptomatte_type"):
            if not hasattr(node_obj, "layer_name"):
                raise ValueError(f"Property '{prop_name}' not supported on node '{node_name}'.")
            val_str = str(prop_val).strip()
            target_clean = val_str.lower().replace("_", "").replace(" ", "")
            canonical_targets = {
                "object": "CryptoObject",
                "cryptoobject": "CryptoObject",
                "material": "CryptoMaterial",
                "cryptomaterial": "CryptoMaterial",
                "asset": "CryptoAsset",
                "cryptoasset": "CryptoAsset",
            }
            sub_target = canonical_targets.get(target_clean)
            if not sub_target:
                for k, v in (("cryptoobject", "CryptoObject"), ("cryptomaterial", "CryptoMaterial"), ("cryptoasset", "CryptoAsset")):
                    if target_clean.endswith(k):
                        sub_target = v
                        break
            if not sub_target:
                raise ValueError(
                    f"Invalid Cryptomatte layer selection '{prop_val}'. "
                    f"Allowed targets: ['CryptoObject', 'CryptoMaterial', 'CryptoAsset'] or ['object', 'material', 'asset']."
                )
            vl_name = getattr(view_layer, "name", "ViewLayer") if view_layer else "ViewLayer"
            resolved_layer = f"{vl_name}.{sub_target}"
            try:
                node_obj.layer_name = resolved_layer
            except TypeError:
                node_obj.layer_name = sub_target

        elif prop_name == "matte_id":
            if not hasattr(node_obj, "matte_id"):
                raise ValueError(f"Property 'matte_id' not supported on node '{node_name}'.")
            node_obj.matte_id = str(prop_val).strip()

        elif prop_name == "source":
            if not hasattr(node_obj, "source"):
                raise ValueError(f"Property 'source' not supported on node '{node_name}'.")
            val_clean = str(prop_val).strip().upper()
            if val_clean not in ("RENDER", "IMAGE"):
                raise ValueError(f"Invalid Cryptomatte source '{prop_val}'. Allowed: ['RENDER', 'IMAGE']")
            node_obj.source = val_clean

        elif prop_name == "file_name":
            if hasattr(node_obj, "file_name"):
                node_obj.file_name = str(prop_val)

        # Color Correction Properties (Milestone 9.1C)
        elif prop_name in ("exposure", "exposure_value"):
            val_float = float(prop_val)
            if not (-20.0 <= val_float <= 20.0):
                raise ValueError(f"Exposure must be between -20.0 and 20.0, got {val_float}")
            s = find_socket(node_obj, "Exposure", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float
            elif hasattr(node_obj, "exposure"):
                node_obj.exposure = val_float
            else:
                raise ValueError(f"Exposure property could not be applied to node '{node_name}'.")

        elif prop_name == "hue":
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1.0):
                raise ValueError(f"Hue must be between 0.0 and 1.0, got {val_float}")
            s = find_socket(node_obj, "Hue", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float
            else:
                raise ValueError(f"Hue socket could not be found on node '{node_name}'.")

        elif prop_name in ("saturation", "sat"):
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 2.0):
                raise ValueError(f"Saturation must be between 0.0 and 2.0, got {val_float}")
            s = find_socket(node_obj, "Saturation", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float
            else:
                raise ValueError(f"Saturation socket could not be found on node '{node_name}'.")

        elif prop_name in ("value", "val"):
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 2.0):
                raise ValueError(f"Value must be between 0.0 and 2.0, got {val_float}")
            s = find_socket(node_obj, "Value", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float
            else:
                raise ValueError(f"Value socket could not be found on node '{node_name}'.")

        elif prop_name in ("factor", "fac"):
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1.0):
                raise ValueError(f"Factor must be between 0.0 and 1.0, got {val_float}")
            s = find_socket(node_obj, "Factor", is_output=False) or find_socket(node_obj, "Fac", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float
            else:
                raise ValueError(f"Factor socket could not be found on node '{node_name}'.")

        elif prop_name in ("tonemap_type", "type") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeTonemap", "TONEMAP"):
            val_clean = str(prop_val).strip().lower().replace(" ", "_")
            if val_clean not in TONEMAP_TYPE_MAP:
                raise ValueError(f"Invalid Tonemap type '{prop_val}'. Allowed: {sorted(set(TONEMAP_TYPE_MAP.values()))}")
            canon_type = TONEMAP_TYPE_MAP[val_clean]
            s = find_socket(node_obj, "Type", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = canon_type
            elif hasattr(node_obj, "tonemap_type"):
                node_obj.tonemap_type = canon_type

        elif prop_name == "key":
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1.0):
                raise ValueError(f"Tonemap key must be between 0.0 and 1.0, got {val_float}")
            s = find_socket(node_obj, "Key", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float

        elif prop_name == "balance":
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1.0):
                raise ValueError(f"Tonemap balance must be between 0.0 and 1.0, got {val_float}")
            s = find_socket(node_obj, "Balance", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float

        elif prop_name == "gamma":
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 10.0):
                raise ValueError(f"Tonemap gamma must be between 0.0 and 10.0, got {val_float}")
            s = find_socket(node_obj, "Gamma", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float

        elif prop_name == "intensity":
            val_float = float(prop_val)
            if not (-10.0 <= val_float <= 10.0):
                raise ValueError(f"Tonemap intensity must be between -10.0 and 10.0, got {val_float}")
            s = find_socket(node_obj, "Intensity", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float

        elif prop_name == "contrast":
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1.0):
                raise ValueError(f"Tonemap contrast must be between 0.0 and 1.0, got {val_float}")
            s = find_socket(node_obj, "Contrast", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float

        elif prop_name in ("black_level", "blacklevel", "white_level", "whitelevel"):
            sock_name = "Black Level" if "black" in prop_name else "White Level"
            s = find_socket(node_obj, sock_name, is_output=False)
            if not s or not hasattr(s, "default_value"):
                raise ValueError(f"Socket '{sock_name}' not found on node '{node_name}'.")
            if isinstance(prop_val, (list, tuple)):
                parsed = [float(v) for v in prop_val]
                if not all(0.0 <= v <= 1.0 for v in parsed):
                    raise ValueError(f"{sock_name} values must be in [0.0, 1.0], got {prop_val}")
                s.default_value = parsed if len(parsed) >= 4 else (parsed + [1.0] * (4 - len(parsed)))
            else:
                v = float(prop_val)
                if not (0.0 <= v <= 1.0):
                    raise ValueError(f"{sock_name} must be in [0.0, 1.0], got {v}")
                s.default_value = (v, v, v, 1.0)

        elif prop_name in ("curve_point", "point", "curve_points"):
            if not hasattr(node_obj, "mapping") or not hasattr(node_obj.mapping, "curves"):
                raise ValueError(f"Node '{node_name}' does not support curve point manipulation.")
            curve_map = {"c": 0, "combined": 0, "rgb": 0, "r": 1, "red": 1, "g": 2, "green": 2, "b": 3, "blue": 3}
            if isinstance(prop_val, dict):
                c_idx_raw = prop_val.get("curve", 0)
                if isinstance(c_idx_raw, str):
                    c_idx = curve_map.get(c_idx_raw.strip().lower(), 0)
                else:
                    c_idx = int(c_idx_raw)
                coords = prop_val.get("point") or [prop_val.get("x", 0.5), prop_val.get("y", 0.5)]
            elif isinstance(prop_val, (list, tuple)):
                c_idx = 0
                coords = prop_val
            else:
                raise ValueError(f"Invalid curve point configuration: {prop_val}")

            if not (0 <= c_idx < len(node_obj.mapping.curves)):
                raise ValueError(f"Curve index {c_idx} out of range (0..{len(node_obj.mapping.curves)-1})")

            px = float(coords[0])
            py = float(coords[1])
            if not (0.0 <= px <= 1.0 and 0.0 <= py <= 1.0):
                raise ValueError(f"Curve point coordinates must be within [0.0, 1.0], got ({px}, {py})")

            curve = node_obj.mapping.curves[c_idx]
            updated = False
            for p in curve.points:
                if abs(p.location[0] - px) < 0.01:
                    p.location = (px, py)
                    updated = True
                    break
            if not updated:
                if hasattr(curve.points, "new"):
                    curve.points.new(px, py)
                elif hasattr(curve.points, "append"):
                    new_p = type("CurvePoint", (), {"location": (px, py)})()
                    curve.points.append(new_p)
            node_obj.mapping.update()

        # Visual Effects Properties (Milestone 9.1D)
        # Lens Distortion
        elif prop_name in ("distortion", "distort", "dist") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeLensdist", "LENSDIST"):
            val_float = float(prop_val)
            if not (-1.0 <= val_float <= 1.0):
                raise ValueError(f"Lens distortion must be between -1.0 and 1.0, got {val_float}")
            s = find_socket(node_obj, "Distortion", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float
            else:
                raise ValueError(f"Distortion socket not found on node '{node_name}'.")

        elif prop_name in ("dispersion", "disperse", "disp") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeLensdist", "LENSDIST"):
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1.0):
                raise ValueError(f"Lens dispersion must be between 0.0 and 1.0, got {val_float}")
            s = find_socket(node_obj, "Dispersion", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_float
            else:
                raise ValueError(f"Dispersion socket not found on node '{node_name}'.")

        elif prop_name in ("lensdist_type", "type") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeLensdist", "LENSDIST"):
            val_clean = str(prop_val).strip().lower().replace(" ", "_")
            if val_clean not in LENSDIST_TYPE_MAP:
                raise ValueError(f"Invalid Lensdist type '{prop_val}'. Allowed: {sorted(set(LENSDIST_TYPE_MAP.values()))}")
            canon_type = LENSDIST_TYPE_MAP[val_clean]
            s = find_socket(node_obj, "Type", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = canon_type

        elif prop_name in ("jitter", "use_jitter") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeLensdist", "LENSDIST"):
            val_bool = bool(prop_val)
            s = find_socket(node_obj, "Jitter", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_bool

        elif prop_name in ("fit", "use_fit") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeLensdist", "LENSDIST"):
            val_bool = bool(prop_val)
            s = find_socket(node_obj, "Fit", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = val_bool

        # Defocus Properties
        elif prop_name in ("f_stop", "fstop") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeDefocus", "DEFOCUS"):
            val_float = float(prop_val)
            if not (0.1 <= val_float <= 128.0):
                raise ValueError(f"Defocus f_stop must be between 0.1 and 128.0, got {val_float}")
            if hasattr(node_obj, "f_stop"):
                node_obj.f_stop = val_float
            else:
                raise ValueError(f"f_stop property not found on node '{node_name}'.")

        elif prop_name in ("blur_max", "max_blur", "blur") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeDefocus", "DEFOCUS"):
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1024.0):
                raise ValueError(f"Defocus blur_max must be between 0.0 and 1024.0, got {val_float}")
            if hasattr(node_obj, "blur_max"):
                node_obj.blur_max = val_float
            else:
                raise ValueError(f"blur_max property not found on node '{node_name}'.")

        elif prop_name in ("bokeh", "bokeh_type") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeDefocus", "DEFOCUS"):
            val_clean = str(prop_val).strip().lower()
            if val_clean not in DEFOCUS_BOKEH_MAP:
                raise ValueError(f"Invalid Defocus bokeh type '{prop_val}'. Allowed: {sorted(set(DEFOCUS_BOKEH_MAP.values()))}")
            canon_bokeh = DEFOCUS_BOKEH_MAP[val_clean]
            if hasattr(node_obj, "bokeh"):
                node_obj.bokeh = canon_bokeh
            else:
                raise ValueError(f"bokeh property not found on node '{node_name}'.")

        elif prop_name in ("angle", "bokeh_angle") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeDefocus", "DEFOCUS"):
            val_float = float(prop_val)
            if not (-360.0 <= val_float <= 360.0):
                raise ValueError(f"Defocus angle must be between -360.0 and 360.0, got {val_float}")
            if hasattr(node_obj, "angle"):
                node_obj.angle = val_float
            else:
                raise ValueError(f"angle property not found on node '{node_name}'.")

        elif prop_name in ("use_zbuffer", "zbuffer") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeDefocus", "DEFOCUS"):
            val_bool = bool(prop_val)
            if hasattr(node_obj, "use_zbuffer"):
                node_obj.use_zbuffer = val_bool
            else:
                raise ValueError(f"use_zbuffer property not found on node '{node_name}'.")

        elif prop_name in ("z_scale", "zscale") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeDefocus", "DEFOCUS"):
            val_float = float(prop_val)
            if not (0.0 <= val_float <= 1000.0):
                raise ValueError(f"Defocus z_scale must be between 0.0 and 1000.0, got {val_float}")
            if hasattr(node_obj, "z_scale"):
                node_obj.z_scale = val_float
            else:
                raise ValueError(f"z_scale property not found on node '{node_name}'.")

        # Filter Properties
        elif prop_name in ("filter_type", "type") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeFilter", "FILTER"):
            val_clean = str(prop_val).strip().lower().replace(" ", "_")
            if val_clean not in FILTER_TYPE_MAP:
                raise ValueError(f"Invalid Filter type '{prop_val}'. Allowed: {sorted(set(FILTER_TYPE_MAP.values()))}")
            canon_filter = FILTER_TYPE_MAP[val_clean]
            s = find_socket(node_obj, "Type", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = canon_filter
            elif hasattr(node_obj, "filter_type"):
                node_obj.filter_type = canon_filter

        # Mask Properties (Milestone 9.1E)
        # Box & Ellipse Mask Operations
        elif prop_name in ("mask_operation", "operation", "op") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeBoxMask", "CompositorNodeEllipseMask", "BOXMASK", "ELLIPSEMASK"):
            val_clean = str(prop_val).strip().lower()
            if val_clean not in MASK_OPERATION_MAP:
                raise ValueError(f"Invalid Mask operation '{prop_val}'. Allowed: {sorted(set(MASK_OPERATION_MAP.values()))}")
            canon_op = MASK_OPERATION_MAP[val_clean]
            s = find_socket(node_obj, "Operation", is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = canon_op
            else:
                raise ValueError(f"Operation socket not found on node '{node_name}'.")

        # Mask Position (2D Vector Factor)
        elif prop_name in ("position", "pos") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeBoxMask", "CompositorNodeEllipseMask", "BOXMASK", "ELLIPSEMASK"):
            s = find_socket(node_obj, "Position", is_output=False)
            if not s or not hasattr(s, "default_value"):
                raise ValueError(f"Position socket not found on node '{node_name}'.")
            if isinstance(prop_val, (list, tuple)) and len(prop_val) >= 2:
                px = float(prop_val[0])
                py = float(prop_val[1])
                if not (0.0 <= px <= 1.0 and 0.0 <= py <= 1.0):
                    raise ValueError(f"Mask position coordinates must be in [0.0, 1.0], got ({px}, {py})")
                s.default_value = (px, py)
            else:
                raise ValueError(f"Mask position must be a 2D list/tuple [x, y], got {prop_val}")

        # Mask Size (2D Vector Factor)
        elif prop_name in ("size", "scale") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeBoxMask", "CompositorNodeEllipseMask", "BOXMASK", "ELLIPSEMASK"):
            s = find_socket(node_obj, "Size", is_output=False)
            if not s or not hasattr(s, "default_value"):
                raise ValueError(f"Size socket not found on node '{node_name}'.")
            if isinstance(prop_val, (list, tuple)) and len(prop_val) >= 2:
                sx = float(prop_val[0])
                sy = float(prop_val[1])
                if not (0.0 <= sx <= 2.0 and 0.0 <= sy <= 2.0):
                    raise ValueError(f"Mask size dimensions must be in [0.0, 2.0], got ({sx}, {sy})")
                s.default_value = (sx, sy)
            elif isinstance(prop_val, (int, float)):
                s_val = float(prop_val)
                if not (0.0 <= s_val <= 2.0):
                    raise ValueError(f"Mask size must be in [0.0, 2.0], got {s_val}")
                s.default_value = (s_val, s_val)
            else:
                raise ValueError(f"Mask size must be a number or [sx, sy], got {prop_val}")

        # Mask Rotation (Angle in radians or degrees)
        elif prop_name in ("rotation", "rot", "angle") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeBoxMask", "CompositorNodeEllipseMask", "BOXMASK", "ELLIPSEMASK"):
            s = find_socket(node_obj, "Rotation", is_output=False)
            if not s or not hasattr(s, "default_value"):
                raise ValueError(f"Rotation socket not found on node '{node_name}'.")
            val_rot = float(prop_val)
            if not (-360.0 <= val_rot <= 360.0):
                raise ValueError(f"Mask rotation must be in [-360.0, 360.0], got {val_rot}")
            s.default_value = val_rot

        # Mask Value
        elif prop_name == "value" and getattr(node_obj, "bl_idname", "") in ("CompositorNodeBoxMask", "CompositorNodeEllipseMask", "BOXMASK", "ELLIPSEMASK"):
            s = find_socket(node_obj, "Value", is_output=False)
            if not s or not hasattr(s, "default_value"):
                raise ValueError(f"Value socket not found on node '{node_name}'.")
            val_v = float(prop_val)
            if not (0.0 <= val_v <= 1.0):
                raise ValueError(f"Mask value must be in [0.0, 1.0], got {val_v}")
            s.default_value = val_v

        # ID Mask Properties
        elif prop_name in ("index", "pass_index") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeIDMask", "IDMASK"):
            s = find_socket(node_obj, "Index", is_output=False)
            if not s or not hasattr(s, "default_value"):
                raise ValueError(f"Index socket not found on node '{node_name}'.")
            val_idx = int(prop_val)
            if not (0 <= val_idx <= 32767):
                raise ValueError(f"ID Mask index must be in [0, 32767], got {val_idx}")
            s.default_value = val_idx

        elif prop_name in ("anti_alias", "antialias", "aa") and getattr(node_obj, "bl_idname", "") in ("CompositorNodeIDMask", "IDMASK"):
            s = find_socket(node_obj, "Anti-Alias", is_output=False)
            if not s or not hasattr(s, "default_value"):
                raise ValueError(f"Anti-Alias socket not found on node '{node_name}'.")
            s.default_value = bool(prop_val)

        elif hasattr(node_obj, "inputs"):
            s = find_socket(node_obj, prop_name, is_output=False)
            if s and hasattr(s, "default_value"):
                s.default_value = prop_val
            elif hasattr(node_obj, prop_name):
                setattr(node_obj, prop_name, prop_val)
            else:
                raise ValueError(f"Property or socket '{prop_name}' could not be resolved on node '{node_name}'.")

        elif hasattr(node_obj, prop_name):
            setattr(node_obj, prop_name, prop_val)

        else:
            raise ValueError(f"Property '{prop_name}' not recognized on node '{node_name}'.")

        new_snap, new_state = compute_compositor_snapshot(tree, view_layer)
        return {
            "status": "success",
            "action": "set_property",
            "node_name": node_name,
            "property_name": prop_name,
            "property_value": prop_val,
            "snapshot_id": new_snap,
            "verified": True,
        }

    # 8. Action 'configure_render_passes'
    if action == "configure_render_passes":
        if not view_layer:
            raise ValueError("No active view layer found to configure render passes.")

        passes = params.get("passes", {})
        if not isinstance(passes, dict) or not passes:
            raise ValueError("Parameter 'passes' (dict) is required for action 'configure_render_passes'.")

        updated_passes = {}
        for p_key, enabled in passes.items():
            cleaned_key = str(p_key).strip().lower()
            if cleaned_key not in ALLOWED_RENDER_PASSES:
                raise ValueError(f"Unsupported render pass '{p_key}'. Allowed: {sorted(set(ALLOWED_RENDER_PASSES.keys()))}")
            attr_name = ALLOWED_RENDER_PASSES[cleaned_key]
            if not isinstance(enabled, bool):
                raise ValueError(f"Pass '{p_key}' value must be boolean, got {type(enabled).__name__}")
            setattr(view_layer, attr_name, enabled)
            updated_passes[cleaned_key] = enabled

        new_snap, new_state = compute_compositor_snapshot(tree, view_layer)
        return {
            "status": "success",
            "action": "configure_render_passes",
            "view_layer_name": getattr(view_layer, "name", ""),
            "updated_passes": updated_passes,
            "active_passes": new_state["render_passes"],
            "snapshot_id": new_snap,
            "verified": True,
        }

    raise ValueError(f"Unknown action '{action}' for compositor operation.")


def inspect_compositor_receipt(bpy_module: Any, scene: Any = None) -> Dict[str, Any]:
    """Generates structured verification receipt for compositor state."""
    if not scene and hasattr(bpy_module, "context"):
        scene = getattr(bpy_module.context, "scene", None)
    if not scene:
        return {"compositor_active": False}

    view_layer = getattr(bpy_module.context, "view_layer", None)
    tree = getattr(scene, "compositing_node_group", None) or getattr(scene, "node_tree", None)
    if not tree:
        return {"compositor_active": False}

    snap, state = compute_compositor_snapshot(tree, view_layer)
    active_passes = [k for k, v in state["render_passes"].items() if v]

    # Verify output connection (Group Output or Composite node)
    has_output_link = any(
        (l["to_node"].startswith("Group Output") or l["to_node"].startswith("Composite"))
        for l in state["links"]
    )

    return {
        "compositor_active": getattr(scene, "use_nodes", True),
        "tree_name": state["tree_name"],
        "node_count": len(state["nodes"]),
        "link_count": len(state["links"]),
        "nodes": [n["name"] for n in state["nodes"]],
        "active_passes": active_passes,
        "composite_output_connected": has_output_link,
        "snapshot_id": snap,
        "verified": True,
    }
