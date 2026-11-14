"""Finite, stdlib-only modifier contract shared by service and Blender."""
import math

PROPERTY_SPECS = {
    "SUBSURF": {"levels": (int, 0, 6), "render_levels": (int, 0, 6)},
    "BEVEL": {"width": (float, 0, 100), "segments": (int, 1, 64)},
    "SOLIDIFY": {"thickness": (float, -10, 10)},
}
TRANSPORT_FIELDS = {"approved", "trusted_approval", "request_id", "approval_token", "task_id", "session_id", "correlation_id"}


def validate_modifier_params(params, inspection=False):
    if not isinstance(params, dict):
        raise ValueError("Modifier parameters must be an object")
    fields = {"name"} if inspection else {"name", "action", "modifier_name", "modifier_type", "properties"}
    if set(params) - fields - TRANSPORT_FIELDS:
        raise ValueError("Unknown modifier parameters")
    result = {}
    for key in (["name"] if inspection else ["name", "modifier_name"]):
        value = params.get(key)
        if not isinstance(value, str) or not value or value != value.strip() or len(value) > 63:
            raise ValueError(f"{key} must be a nonempty exact name of at most 63 characters")
        result[key] = value
    if inspection:
        return result
    action, kind = params.get("action"), params.get("modifier_type")
    if not isinstance(action, str) or action not in ("add", "update", "remove"):
        raise ValueError("Modifier action must be add, update or remove")
    if not isinstance(kind, str) or kind not in PROPERTY_SPECS:
        raise ValueError("Typed modifiers support only SUBSURF, BEVEL and SOLIDIFY")
    props = params.get("properties", {})
    if not isinstance(props, dict):
        raise ValueError("Modifier properties must be an object")
    if action == "remove" and props:
        raise ValueError("remove accepts no property assignments")
    if action != "remove" and not props:
        raise ValueError("add/update require explicit properties")
    for key, value in props.items():
        if key not in PROPERTY_SPECS[kind]:
            raise ValueError(f"Unsupported {kind} property '{key}'")
        numeric_type, low, high = PROPERTY_SPECS[kind][key]
        if type(value) not in (int, float) or (numeric_type is int and type(value) is not int):
            raise ValueError(f"Invalid numeric type for modifier property '{key}'")
        if not low <= value <= high or not math.isfinite(value):
            raise ValueError(f"Modifier property '{key}' outside {low}..{high}")
    return dict(result, action=action, modifier_type=kind, properties=dict(props))


def structured_policy_params(params):
    """Equivalent policy view only; original tool/parameters retain token binding."""
    clean = validate_modifier_params(params)
    values = {"modifier_name": clean["modifier_name"]}
    if clean["action"] == "add":
        values["modifier_type"] = clean["modifier_type"]
    if clean["action"] != "remove":
        values["properties"] = clean["properties"]
    return {"operations": [{"action": {"add": "add_modifier", "update": "modify_modifier", "remove": "remove_modifier"}[clean["action"]],
                             "target": clean["name"], "params": values}]}


def verify_modifier_readback(params, result, inspection):
    """Compare mutation receipt with a separate, current read-only stack query."""
    try:
        expected = validate_modifier_params(params)
        if not all(isinstance(value, dict) and value.get("success") is True and value.get("verified") is True
                   and value.get("name") == expected["name"] for value in (result, inspection)):
            return False
        for key in ("action", "modifier_name", "modifier_type"):
            if result.get(key) != expected[key]:
                return False
        entries = inspection.get("modifiers")
        if not isinstance(entries, list) or any(not isinstance(entry, dict) or not isinstance(entry.get("name"), str) for entry in entries):
            return False
        names = [entry["name"] for entry in entries]
        if len(names) != len(set(names)) or result.get("stack") != names:
            return False
        found = [entry for entry in entries if entry["name"] == expected["modifier_name"]]
        if expected["action"] == "remove":
            return not found and result.get("exists") is False and result.get("properties") == {}
        if len(found) != 1 or found[0].get("type") != expected["modifier_type"] or result.get("exists") is not True:
            return False
        if set(result.get("properties", {})) != set(expected["properties"]):
            return False
        for key, requested in expected["properties"].items():
            for actual in (result["properties"][key], found[0]["properties"][key]):
                if type(actual) not in (int, float) or not math.isclose(actual, requested, rel_tol=1e-6, abs_tol=1e-6):
                    return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
