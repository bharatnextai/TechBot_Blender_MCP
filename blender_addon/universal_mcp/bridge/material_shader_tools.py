"""Main-thread-only typed Principled/Noise material data operations."""
import threading
from .approval_registry import get_approval_registry
from .material_shader_contract import PRINCIPLED, NOISE, validate_material_shader, verify_material_shader
from .shader_values import shader_value, shader_values_match


def _material(bpy, name):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Material access requires Blender's main thread")
    material = bpy.data.materials.get(name)
    if material is None:
        raise ValueError(f"Material '{name}' not found")
    return material


def _socket(sockets, name):
    matches = [socket for socket in sockets if socket.identifier == name]
    if len(matches) != 1:
        raise ValueError(f"Requested shader socket '{name}' not found uniquely")
    return matches[0]


def handle_inspect_material_shader(bpy_module=None, params=None):
    clean = validate_material_shader(params or {}, inspection=True)
    material = _material(bpy_module, clean["target_name"])
    nodes, links = [], []
    if material.use_nodes and material.node_tree is not None:
        for node in material.node_tree.nodes:
            specs = PRINCIPLED if node.bl_idname == "ShaderNodeBsdfPrincipled" else NOISE if node.bl_idname == "ShaderNodeTexNoise" else {}
            nodes.append({"name": node.name, "type": node.bl_idname, "active_output": bool(getattr(node, "is_active_output", False)),
                          "inputs": {name: shader_value(_socket(node.inputs, name).default_value) for name, _, _ in specs.values()}})
        links = [{"from_node": link.from_node.name, "from_socket": link.from_socket.identifier,
                  "to_node": link.to_node.name, "to_socket": link.to_socket.identifier} for link in material.node_tree.links]
    return {"success": True, "verified": True, "target_name": material.name,
            "use_nodes": bool(material.use_nodes), "nodes": nodes, "links": links}


def handle_configure_material_shader(bpy_module=None, params=None):
    params = params or {}
    clean = validate_material_shader(params)
    material = _material(bpy_module, clean["target_name"])
    from .handlers import is_approval_required
    if is_approval_required(bpy_module):
        ok, reason = get_approval_registry().consume_approval(params.get("request_id"), params.get("approval_token"), "configure_material_shader", params)
        if not ok:
            raise PermissionError(f"Material shader mutation denied: {reason}")
    if not material.use_nodes or material.node_tree is None:
        raise ValueError("Typed shader mutation requires an existing enabled material node tree")
    tree = material.node_tree
    bsdf = tree.nodes.get(clean["bsdf_node_name"])
    if bsdf is None or bsdf.bl_idname != "ShaderNodeBsdfPrincipled":
        raise ValueError("Requested Principled BSDF node not found with exact type")
    outputs = [node for node in tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial" and node.is_active_output]
    if len(outputs) != 1:
        raise ValueError("Typed shader contract requires one active Material Output")
    bsdf_output = _socket(bsdf.outputs, "BSDF")
    surface = _socket(outputs[0].inputs, "Surface")
    surface_links = [link for link in tree.links if link.to_socket == surface]
    if len(surface_links) != 1 or surface_links[0].from_socket != bsdf_output:
        raise ValueError("Principled BSDF must directly feed the active Material Output Surface")
    action = clean["action"]
    created = None
    original = []
    try:
        if action == "set_principled":
            assignments = [(_socket(bsdf.inputs, PRINCIPLED[key][0]), value) for key, value in clean["inputs"].items()]
        else:
            target = _socket(bsdf.inputs, "Base Color")
            noise = tree.nodes.get(clean["noise_node_name"])
            if action == "add_noise":
                if noise is not None:
                    raise ValueError("Noise node already exists")
                if target.is_linked:
                    raise ValueError("Base Color is already linked; existing graph was preserved")
                noise = tree.nodes.new("ShaderNodeTexNoise"); created = noise
                noise.name = clean["noise_node_name"]
                if noise.name != clean["noise_node_name"]:
                    raise RuntimeError("Noise node name readback mismatch")
            elif noise is None or noise.bl_idname != "ShaderNodeTexNoise":
                raise ValueError("Requested Noise node not found with exact type")
            color = _socket(noise.outputs, "Color")
            if action != "add_noise":
                related = [link for link in tree.links if link.from_node == noise or link.to_node == noise or link.to_socket == target]
                if len(related) != 1 or related[0].from_socket != color or related[0].to_socket != target:
                    raise ValueError("Noise graph has conflicting connections; no unrelated links changed")
            if action == "remove_noise":
                tree.nodes.remove(noise)
                if tree.nodes.get(clean["noise_node_name"]) is not None or target.is_linked:
                    raise RuntimeError("Noise removal postcondition failed")
                assignments = []
            else:
                assignments = [(_socket(noise.inputs, NOISE[key][0]), value) for key, value in clean["noise_inputs"].items()]
        if any(socket.is_linked for socket, _ in assignments):
            raise ValueError("Cannot change a linked shader input default as an effective value")
        original = [(socket, shader_value(socket.default_value)) for socket, _ in assignments]
        for socket, value in assignments:
            socket.default_value = value
            if not shader_values_match(shader_value(socket.default_value), value):
                raise RuntimeError(f"Shader socket '{socket.identifier}' readback mismatch")
        if action == "add_noise":
            tree.links.new(color, target)
        state = handle_inspect_material_shader(bpy_module, {"target_name": material.name})
        result = {"success": True, "verified": True, "target_name": material.name, "action": action, "state": state}
        if not verify_material_shader(clean, result, state):
            raise RuntimeError("Typed shader graph postcondition failed")
        return result
    except Exception as error:
        try:
            if created is not None:
                tree.nodes.remove(created)
            else:
                for socket, value in original:
                    socket.default_value = value
        except Exception as restore_error:
            raise RuntimeError(f"Shader mutation failed; restoration unverified: {restore_error}") from error
        raise
