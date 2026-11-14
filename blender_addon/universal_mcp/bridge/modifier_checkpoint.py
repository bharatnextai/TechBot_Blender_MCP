"""Lossless checkpoints for the finite typed modifier removal contract."""
from .shader_values import shader_value, shader_values_match


def _custom(mod):
    try:
        return {key: mod[key].to_dict() if hasattr(mod[key], "to_dict") else shader_value(mod[key]) for key in mod.keys()}
    except TypeError:
        return None  # Blender's standard modifiers do not support IDProperties.


def _scalars(value):
    return {prop.identifier: shader_value(getattr(value, prop.identifier))
            for prop in value.bl_rna.properties if not prop.is_readonly}


def capture(obj, mod):
    if getattr(obj, "animation_data", None) is not None:
        raise ValueError("Modifier removal on animated objects is unsupported; nothing changed")
    if mod.type == "BEVEL" and mod.profile_type == "CUSTOM":
        raise ValueError("Custom bevel-profile removal is unsupported; nothing changed")
    profile = None
    if mod.type == "BEVEL":
        if len(mod.custom_profile.points) != 2:
            raise ValueError("Nondefault stored bevel-profile removal is unsupported; nothing changed")
        profile = {"values": _scalars(mod.custom_profile),
                   "points": [_scalars(point) for point in mod.custom_profile.points]}
    values = {}
    for prop in mod.bl_rna.properties:
        if prop.is_readonly:
            if prop.type in ("POINTER", "COLLECTION") and prop.identifier not in ("rna_type", "custom_profile"):
                raise ValueError(f"Cannot checkpoint modifier property {prop.identifier}")
            continue
        if prop.type not in ("BOOLEAN", "INT", "FLOAT", "STRING", "ENUM", "POINTER"):
            raise ValueError(f"Cannot checkpoint modifier property {prop.identifier}")
        value = getattr(mod, prop.identifier)
        values[prop.identifier] = value if prop.type == "POINTER" else sorted(value) if prop.type == "ENUM" and getattr(prop, "is_enum_flag", False) else shader_value(value)
    custom = _custom(mod)
    active = obj.modifiers.active
    return {"name": mod.name, "type": mod.type, "index": list(obj.modifiers).index(mod),
            "values": values, "pointers": {p.identifier for p in mod.bl_rna.properties if p.type == "POINTER" and not p.is_readonly},
            "enum_flags": {p.identifier for p in mod.bl_rna.properties if p.type == "ENUM" and getattr(p, "is_enum_flag", False) and not p.is_readonly},
            "custom": custom, "profile": profile, "active": active.name if active else None}


def restore(obj, checkpoint):
    mod = obj.modifiers.get(checkpoint["name"])
    if mod is None:
        mod = obj.modifiers.new(name=checkpoint["name"], type=checkpoint["type"])
    if mod.type != checkpoint["type"]:
        raise RuntimeError("Modifier restoration type mismatch")
    for key, value in checkpoint["values"].items():
        setattr(mod, key, set(value) if key in checkpoint["enum_flags"] else value)
    if checkpoint["custom"] is not None:
        for key in list(mod.keys()):
            del mod[key]
        for key, value in checkpoint["custom"].items():
            mod[key] = value
    profile = checkpoint["profile"]
    if profile is not None:
        for key, value in profile["values"].items():
            setattr(mod.custom_profile, key, value)
        if len(mod.custom_profile.points) != 2:
            raise RuntimeError("Modifier profile restoration point count mismatch")
        for point, values in zip(mod.custom_profile.points, profile["points"]):
            for key, value in values.items():
                setattr(point, key, value)
        mod.custom_profile.update()
        if not shader_values_match(list(_scalars(mod.custom_profile).values()), list(profile["values"].values())) or any(
                not shader_values_match(list(_scalars(point).values()), list(values.values()))
                for point, values in zip(mod.custom_profile.points, profile["points"])):
            raise RuntimeError("Modifier profile restoration readback mismatch")
    obj.modifiers.move(list(obj.modifiers).index(mod), checkpoint["index"])
    obj.modifiers.active = obj.modifiers.get(checkpoint["active"]) if checkpoint["active"] else None
    for key, expected in checkpoint["values"].items():
        actual = getattr(mod, key)
        if key in checkpoint["enum_flags"]:
            actual = sorted(actual)
        matches = actual == expected if key in checkpoint["pointers"] else shader_values_match(actual, expected)
        if not matches:
            raise RuntimeError(f"Modifier restoration readback mismatch: {key}")
    if _custom(mod) != checkpoint["custom"]:
        raise RuntimeError("Modifier custom-property restoration mismatch")
    if list(obj.modifiers).index(mod) != checkpoint["index"]:
        raise RuntimeError("Modifier restoration order mismatch")
    active = obj.modifiers.active
    if (active.name if active else None) != checkpoint["active"]:
        raise RuntimeError("Modifier restoration active-state mismatch")
