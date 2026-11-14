"""Typed data-API modifiers. Must be dispatched on Blender's main thread."""
import threading
from .approval_registry import get_approval_registry
from .modifier_contract import PROPERTY_SPECS, validate_modifier_params
from .shader_values import shader_value, shader_values_match
from . import modifier_checkpoint


def _verify_stack(obj, expected):
    if [item.name for item in obj.modifiers] != expected:
        raise RuntimeError("Modifier stack postcondition failed")


def _target(bpy, params):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Modifiers require Blender's main thread")
    obj = bpy.context.scene.objects.get(params["name"])
    if obj is None or obj.type != "MESH":
        raise ValueError("Modifier target must be an existing mesh in the active scene")
    return obj


def handle_inspect_modifiers(bpy_module=None, params=None):
    clean = validate_modifier_params(params or {}, inspection=True)
    obj = _target(bpy_module, clean)
    return {"success": True, "verified": True, "name": obj.name, "modifiers": [
        {"name": mod.name, "type": mod.type, "supported": mod.type in PROPERTY_SPECS,
         "properties": {key: shader_value(getattr(mod, key)) for key in PROPERTY_SPECS.get(mod.type, {})}}
        for mod in obj.modifiers]}


def handle_configure_modifier(bpy_module=None, params=None):
    params = params or {}
    clean = validate_modifier_params(params)
    obj = _target(bpy_module, clean)
    from .handlers import is_approval_required
    if is_approval_required(bpy_module):
        ok, reason = get_approval_registry().consume_approval(
            params.get("request_id"), params.get("approval_token"), "configure_modifier", params)
        if not ok:
            raise PermissionError(f"Modifier mutation denied: {reason}")
    if bpy_module.context.mode != "OBJECT":
        raise ValueError("Typed modifier mutation requires Object mode; no mode was changed")
    name, kind, action = clean["modifier_name"], clean["modifier_type"], clean["action"]
    mod = obj.modifiers.get(name)
    if action == "add" and mod is not None:
        raise ValueError(f"Modifier '{name}' already exists")
    if action != "add" and (mod is None or mod.type != kind):
        raise ValueError(f"Modifier '{name}' not found with requested type '{kind}'")
    before = [item.name for item in obj.modifiers]
    checkpoint = modifier_checkpoint.capture(obj, mod) if action == "remove" else None
    old = {key: shader_value(getattr(mod, key)) for key in clean["properties"]} if mod else {}
    created = False
    try:
        if action == "add":
            mod = obj.modifiers.new(name=name, type=kind)
            created = True
            if mod.name != name or mod.type != kind:
                raise RuntimeError("Modifier name/type readback mismatch")
        if action == "remove":
            obj.modifiers.remove(mod)
            actual = {}
        else:
            for key, value in clean["properties"].items():
                setattr(mod, key, value)
            actual = {key: shader_value(getattr(mod, key)) for key in clean["properties"]}
            if not shader_values_match(actual_values := list(actual.values()), list(clean["properties"].values())):
                raise RuntimeError(f"Modifier property readback mismatch: {actual_values}")
        expected = before + [name] if action == "add" else [item for item in before if item != name] if action == "remove" else before
        stack = [item.name for item in obj.modifiers]
        _verify_stack(obj, expected)
        if stack != expected or (action == "remove" and obj.modifiers.get(name) is not None):
            raise RuntimeError("Modifier stack postcondition failed")
        return {"success": True, "verified": True, **clean, "properties": actual,
                "exists": action != "remove", "stack": stack}
    except Exception as error:
        try:
            if created:
                obj.modifiers.remove(mod)
            elif action == "update":
                for key, value in old.items():
                    setattr(mod, key, value)
                if not all(shader_values_match(getattr(mod, key), value) for key, value in old.items()):
                    raise RuntimeError("Modifier property restoration readback mismatch")
            elif action == "remove":
                modifier_checkpoint.restore(obj, checkpoint)
            if [item.name for item in obj.modifiers] != before:
                raise RuntimeError("Modifier stack restoration mismatch")
        except Exception as restore_error:
            raise RuntimeError(f"Modifier failed; restoration unverified: {restore_error}") from error
        raise
