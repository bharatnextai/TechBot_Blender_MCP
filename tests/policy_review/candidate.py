"""UNWIRED proposal. This predicate neither approves requests nor issues tokens.

Apply only after review, behind every existing local-test isolation guard.
Ownership sets must come from the host fixture ledger, never MCP arguments.
"""
from pathlib import Path


def permits(tool, params, *, root, objects, modifiers, images):
    """Reject everything except one bounded modifier operation or fresh bake."""
    if not isinstance(params, dict):
        return False
    if tool == "execute_blender_code":
        if set(params) != {"operations"}:
            return False
        operations = params["operations"]
        if not isinstance(operations, list) or len(operations) != 1:
            return False
        op = operations[0]
        if not isinstance(op, dict) or set(op) != {"action", "target", "params"}:
            return False
        target, action, values = op["target"], op["action"], op["params"]
        if not isinstance(target, str) or target not in objects or not isinstance(values, dict):
            return False
        if not isinstance(action, str):
            return False
        if action == "add_modifier":
            if set(values) != {"modifier_name", "modifier_type", "properties"}:
                return False
            name, kind = values["modifier_name"], values["modifier_type"]
            if not isinstance(name, str) or not name or not isinstance(kind, str):
                return False
            if (target, name) in modifiers:
                return False
        elif action in {"modify_modifier", "remove_modifier"}:
            expected = {"modifier_name", "properties"} if action == "modify_modifier" else {"modifier_name"}
            if set(values) != expected or not isinstance(values["modifier_name"], str):
                return False
            kind = modifiers.get((target, values["modifier_name"]))
        else:
            return False
        bounds = {
            "SUBSURF": {"levels": (0, 2, int), "render_levels": (0, 2, int)},
            "BEVEL": {"width": (0, 0.1, float), "segments": (1, 3, int)},
            "SOLIDIFY": {"thickness": (0.001, 0.1, float)},
        }
        if kind not in bounds:
            return False
        if action == "remove_modifier":
            return True
        props = values["properties"]
        if not isinstance(props, dict) or not props:
            return False
        for key, value in props.items():
            if key not in bounds[kind]:
                return False
            low, high, numeric_type = bounds[kind][key]
            if type(value) not in (int, float):
                return False
            if numeric_type is int and type(value) is not int:
                return False
            if not low <= value <= high:
                return False
        return True
    if tool == "bake_object_texture":
        expected = {"object_name", "image_name", "bake_type", "width", "height", "margin", "save_filepath"}
        if set(params) != expected:
            return False
        name, image, bake_type = params["object_name"], params["image_name"], params["bake_type"]
        if not all(isinstance(item, str) and item for item in (name, image, bake_type)):
            return False
        if name not in objects or image in images or bake_type not in {"EMIT", "ROUGHNESS"}:
            return False
        if any(type(params[key]) is not int for key in ("width", "height", "margin")):
            return False
        if not (16 <= params["width"] <= 256 and 16 <= params["height"] <= 256 and 0 <= params["margin"] <= 8):
            return False
        try:
            destination = Path(params["save_filepath"])
            base = Path(root).resolve(strict=True)
            if not destination.is_absolute() or destination.suffix.lower() != ".png":
                return False
            destination = destination.resolve()
            return base in destination.parents and destination.parent.is_dir() and not destination.exists()
        except (OSError, TypeError, ValueError, RuntimeError):
            return False
    return False
