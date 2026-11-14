"""Bounded modifier/bake test policy; no public tool can populate its ledger.

Called only behind the existing disposable-process isolation guards. Decisions
still use normal request hashes, expiry and single-use registry tokens.
"""
import os
import threading
from pathlib import Path

_scope = None


def _identity(value):
    return value.as_pointer()


def configure_fixture(bpy, root, objects, materials):
    """Host fixture bootstrap only, on Blender's main thread; never an MCP API."""
    global _scope
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Fixture ownership must be registered on the main thread")
    scope_kind = os.environ.get("UMCP_LOCAL_TEST_SCOPE")
    requires_background = scope_kind != "sculpt_v1"
    if (requires_background and not bpy.app.background) or bpy.data.filepath or _scope is not None:
        raise RuntimeError("A fresh disposable background process is required")
    records = {}
    for obj in objects:
        if obj.type != "MESH" or bpy.data.objects.get(obj.name) != obj:
            raise ValueError("Fixture requires actual owned mesh datablocks")
        records[obj.name] = (obj, obj.data, {
            mod.name: (mod, mod.type) for mod in obj.modifiers})
    _scope = (str(Path(root).resolve(strict=True)), records,
              {_identity(mat): mat for mat in materials})


def permits_owned(bpy, tool, params, root):
    """Identity and state preflight; fail closed without a matching host ledger."""
    if threading.current_thread() is not threading.main_thread():
        return False
    scope_kind = os.environ.get("UMCP_LOCAL_TEST_SCOPE")
    if scope_kind not in {"modifier_bake_v1", "sculpt_v1"} or _scope is None:
        return False
    try:
        scope_root, records, materials = _scope
        if str(Path(root).resolve(strict=True)) != scope_root:
            return False
        # Ignore only inert schema defaults in this policy view, never in the
        # request/hash/execution parameters. No true approval flag is accepted.
        view = dict(params)
        if any(view.get(key) is True for key in ("approved", "trusted_approval", "_trusted_approval", "_trusted_test_override")):
            return False
        if tool == "sculpt_mesh":
            if scope_kind != "sculpt_v1":
                return False
            if view.get("approved") is False:
                view.pop("approved")
            target = view.get("object_name")
            if not isinstance(target, str) or target not in records:
                return False
            obj = bpy.data.objects.get(target)
            owned_object, owned_mesh, owned_modifiers = records[target]
            if obj is None or _identity(obj) != _identity(owned_object):
                return False
            if obj.data is None or obj.data.library or obj.data.shape_keys or obj.data.animation_data:
                return False
            records[target] = (obj, obj.data, owned_modifiers)
            from .sculpt_contract import validate
            try:
                validate(view)
            except Exception:
                return False
            return True
        if scope_kind != "modifier_bake_v1":
            return False
        typed_kind = None
        if tool == "configure_modifier":
            if set(view) - {"name", "modifier_name", "modifier_type", "action", "properties", "approved"}:
                return False
            if any(view.get(key) is True for key in ("approved", "trusted_approval", "_trusted_approval", "_trusted_test_override")):
                return False
            from .modifier_contract import structured_policy_params
            typed_kind = view.get("modifier_type")
            # Same bounded operation and identity checks, not new test powers.
            view = structured_policy_params(view)
            tool = "execute_blender_code"
        if view.get("approved") is False:
            view.pop("approved")
        if tool == "execute_blender_code" and view.get("transactional") is True:
            view.pop("transactional")
        if tool == "bake_object_texture" and view.get("use_selected_to_active") is False:
            view.pop("use_selected_to_active")
        if tool == "execute_blender_code":
            operations = view.get("operations")
            if not isinstance(operations, list) or len(operations) != 1 or not isinstance(operations[0], dict):
                return False
            target = operations[0].get("target")
        else:
            target = view.get("object_name")
        if not isinstance(target, str) or target not in records:
            return False
        obj = bpy.data.objects.get(target)
        owned_object, owned_mesh, owned_modifiers = records[target]
        if obj is None or _identity(obj) != _identity(owned_object) or _identity(obj.data) != _identity(owned_mesh):
            return False
        current_modifiers = {}
        for mod in obj.modifiers:
            recorded = owned_modifiers.get(mod.name)
            if recorded and _identity(recorded[0]) == _identity(mod) and recorded[1] == mod.type:
                current_modifiers[(target, mod.name)] = mod.type
        if tool == "execute_blender_code":
            op = operations[0]
            values = op.get("params", {})
            if not isinstance(values, dict):
                return False
            existing = obj.modifiers.get(values.get("modifier_name", ""))
            if typed_kind and op.get("action") != "add_modifier" and (existing is None or existing.type != typed_kind):
                return False
            if op.get("action") == "add_modifier" and obj.modifiers.get(values.get("modifier_name", "")) is not None:
                return False
        elif tool == "bake_object_texture":
            if bpy.context.mode != "OBJECT" or bpy.context.view_layer.objects.active != obj:
                return False
            if list(bpy.context.selected_objects) != [obj] or not obj.data.uv_layers:
                return False
            assigned = list(obj.data.materials)
            if len(assigned) != 1 or any(
                mat is None or _identity(mat) not in materials
                or _identity(materials[_identity(mat)]) != _identity(mat) or not mat.use_nodes
                for mat in assigned
            ):
                return False
        return permits(tool, view, root=root, objects=frozenset({target}),
                       modifiers=current_modifiers, images=frozenset(bpy.data.images.keys()))
    except (AttributeError, ReferenceError, TypeError, ValueError, OSError, RuntimeError):
        return False


def record_fixture_modifier(bpy, obj, modifier):
    """Host-only enrollment after independent verification of a planned output.

    Not an MCP endpoint. Callers must use a fixed fixture plan, never an input-
    derived name allowlist. Existing object/mesh ownership cannot be expanded.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Fixture ownership must be recorded on the main thread")
    if _scope is None or not bpy.app.background or bpy.data.filepath:
        raise RuntimeError("No disposable fixture ledger")
    record = _scope[1].get(obj.name)
    if record is None or _identity(record[0]) != _identity(obj) or _identity(record[1]) != _identity(obj.data):
        raise ValueError("Cannot enroll a modifier on an unowned object")
    if modifier.type not in {"SUBSURF", "BEVEL", "SOLIDIFY"} or obj.modifiers.get(modifier.name) != modifier:
        raise ValueError("Cannot enroll unsupported or detached modifier")
    record[2][modifier.name] = (modifier, modifier.type)


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
