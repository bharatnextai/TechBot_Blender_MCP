"""JSON-safe shader readback comparison; Blender standard library only."""
import math


def shader_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Shader value must be finite")
        return value
    try:
        return [shader_value(v) for v in value]
    except TypeError as exc:
        raise ValueError("Shader property is not a supported scalar or sequence") from exc


def shader_values_match(actual, expected):
    actual, expected = shader_value(actual), shader_value(expected)
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (float, int)) and isinstance(expected, (float, int)):
        return math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-6)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(shader_values_match(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected
