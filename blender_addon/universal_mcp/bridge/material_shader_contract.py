"""Finite material shader contract; standard library only."""
import math
from .shader_values import shader_values_match

PRINCIPLED = {"base_color": ("Base Color", 0, 1), "metallic": ("Metallic", 0, 1),
              "roughness": ("Roughness", 0, 1), "ior": ("IOR", 1, 3)}
NOISE = {"scale": ("Scale", 0, 1000), "detail": ("Detail", 0, 15),
         "roughness": ("Roughness", 0, 1), "distortion": ("Distortion", 0, 1000)}
METADATA = {"approved", "trusted_approval", "request_id", "approval_token", "task_id", "session_id", "correlation_id"}

SHADER_NODE_ALIASES = {
    "image": "ShaderNodeTexImage",
    "image_texture": "ShaderNodeTexImage",
    "tex_image": "ShaderNodeTexImage",
    "teximage": "ShaderNodeTexImage",
    "noise": "ShaderNodeTexNoise",
    "tex_noise": "ShaderNodeTexNoise",
    "texnoise": "ShaderNodeTexNoise",
    "voronoi": "ShaderNodeTexVoronoi",
    "tex_voronoi": "ShaderNodeTexVoronoi",
    "wave": "ShaderNodeTexWave",
    "tex_wave": "ShaderNodeTexWave",
    "color_ramp": "ShaderNodeValToRGB",
    "colorramp": "ShaderNodeValToRGB",
    "val_to_rgb": "ShaderNodeValToRGB",
    "math": "ShaderNodeMath",
    "vector_math": "ShaderNodeVectorMath",
    "vectormath": "ShaderNodeVectorMath",
    "mapping": "ShaderNodeMapping",
    "tex_coord": "ShaderNodeTexCoord",
    "texcoord": "ShaderNodeTexCoord",
    "principled": "ShaderNodeBsdfPrincipled",
    "principled_bsdf": "ShaderNodeBsdfPrincipled",
    "output_material": "ShaderNodeOutputMaterial",
    "material_output": "ShaderNodeOutputMaterial",
    "bump": "ShaderNodeBump",
    "normal_map": "ShaderNodeNormalMap",
    "normalmap": "ShaderNodeNormalMap",
    "mix": "ShaderNodeMix",
    "mix_rgb": "ShaderNodeMixRGB",
    "combine_xyz": "ShaderNodeCombineXYZ",
    "separate_xyz": "ShaderNodeSeparateXYZ",
    "background": "ShaderNodeBackground",
    "bg": "ShaderNodeBackground",
    "output_world": "ShaderNodeOutputWorld",
    "world_output": "ShaderNodeOutputWorld",
    "env_texture": "ShaderNodeTexEnvironment",
    "environment_texture": "ShaderNodeTexEnvironment",
    "tex_environment": "ShaderNodeTexEnvironment",
}


def validate_material_shader(params, inspection=False):
    if not isinstance(params, dict):
        raise ValueError("Material shader parameters must be an object")
    fields = {"target_name"} if inspection else {"target_name", "bsdf_node_name", "action", "inputs", "noise_node_name", "noise_inputs"}
    if set(params) - fields - METADATA:
        raise ValueError("Unknown material shader parameters")
    action = params.get("action")
    if not inspection and action not in ("set_principled", "add_noise", "update_noise", "remove_noise"):
        raise ValueError("Unsupported typed material shader action")
    names = ["target_name"] if inspection else ["target_name", "bsdf_node_name"]
    if not inspection and action != "set_principled":
        names.append("noise_node_name")
    result = {}
    for key in names:
        value = params.get(key)
        if not isinstance(value, str) or not value or value != value.strip() or len(value) > 63:
            raise ValueError(f"{key} must be an exact nonblank name of at most 63 characters")
        result[key] = value
    if inspection:
        return result
    result["action"] = action
    payload_key = "inputs" if action == "set_principled" else "noise_inputs"
    irrelevant = {"noise_node_name", "noise_inputs"} if action == "set_principled" else {"inputs"}
    if set(params) & irrelevant:
        raise ValueError("Parameters do not match the requested shader action")
    if action == "remove_noise":
        if "noise_inputs" in params:
            raise ValueError("remove_noise accepts no input assignments")
        return result
    values = params.get(payload_key)
    specs = PRINCIPLED if action == "set_principled" else NOISE
    if not isinstance(values, dict) or not values or set(values) - set(specs):
        raise ValueError(f"{payload_key} requires known, explicit socket assignments")
    for key, value in values.items():
        _, low, high = specs[key]
        numbers = value if key == "base_color" else [value]
        if key == "base_color" and (not isinstance(value, list) or len(value) != 4):
            raise ValueError("base_color must be a four-component array")
        for number in numbers:
            if type(number) not in (int, float) or not low <= number <= high or not math.isfinite(number):
                raise ValueError(f"Invalid finite numeric value for '{key}'")
    result[payload_key] = dict(values)
    return result


def verify_material_shader(params, receipt, inspection):
    try:
        expected = validate_material_shader(params)
        if not all(isinstance(value, dict) and value.get("success") is True and value.get("verified") is True
                   and value.get("target_name") == expected["target_name"] for value in (receipt, inspection)):
            return False
        if receipt.get("action") != expected["action"] or receipt.get("state") != inspection:
            return False
        nodes = inspection["nodes"]
        if not isinstance(nodes, list) or len({node["name"] for node in nodes}) != len(nodes):
            return False
        indexed = {node["name"]: node for node in nodes}
        bsdf = indexed[expected["bsdf_node_name"]]
        if bsdf["type"] != "ShaderNodeBsdfPrincipled":
            return False
        outputs = [node for node in nodes if node["type"] == "ShaderNodeOutputMaterial" and node.get("active_output") is True]
        if len(outputs) != 1 or {"from_node": expected["bsdf_node_name"], "from_socket": "BSDF",
                                "to_node": outputs[0]["name"], "to_socket": "Surface"} not in inspection["links"]:
            return False
        if expected["action"] == "set_principled":
            return all(shader_values_match(bsdf["inputs"][PRINCIPLED[key][0]], value) for key, value in expected["inputs"].items())
        noise = indexed.get(expected["noise_node_name"])
        if expected["action"] == "remove_noise":
            return noise is None
        if noise is None or noise["type"] != "ShaderNodeTexNoise":
            return False
        if not all(shader_values_match(noise["inputs"][NOISE[key][0]], value) for key, value in expected["noise_inputs"].items()):
            return False
        return {"from_node": expected["noise_node_name"], "from_socket": "Color", "to_node": expected["bsdf_node_name"], "to_socket": "Base Color"} in inspection["links"]
    except (KeyError, TypeError, ValueError):
        return False
