"""
AST Security Validator for the Universal MCP Blender Add-on.
Pure Python standard library (ast only) — zero external dependencies.
Statically analyzes modeling scripts before execution inside Blender.
"""

import ast
from typing import Tuple, Set

# Disallowed AST Node Types
DISALLOWED_AST_NODES: Tuple[type, ...] = (
    ast.Import,
    ast.ImportFrom,
    ast.ClassDef,
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Delete,
    ast.Global,
    ast.Nonlocal,
    ast.Yield,
    ast.YieldFrom,
    ast.Try,
    getattr(ast, "Match", type(None)),
)

# Banned Names & Builtins
BANNED_NAMES: Set[str] = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "breakpoint",
    "exit",
    "quit",
    "input",
    "help",
    "memoryview",
    "super",
    "type",
    "__builtins__",
    "os",
    "sys",
    "subprocess",
    "io",
    "pathlib",
    "shutil",
    "ctypes",
    "socket",
    "urllib",
    "requests",
    "http",
    "driver_namespace",
    "execfile",
}

# Allowlisted Operator Prefixes
ALLOWED_OPERATOR_PREFIXES: Tuple[str, ...] = (
    "bpy.ops.object.modifier_add",
    "bpy.ops.object.modifier_apply",
    "bpy.ops.object.modifier_remove",
    "bpy.ops.object.shade_smooth",
    "bpy.ops.object.shade_flat",
    "bpy.ops.object.join",
    "bpy.ops.object.parent_set",
    "bpy.ops.object.parent_clear",
    "bpy.ops.object.select_all",
    "bpy.ops.mesh.primitive_",
    "bpy.ops.mesh.subdivide",
    "bpy.ops.material.new",
    "bpy.ops.ed.undo_push",
    "bpy.ops.ed.undo",
    "bpy.ops.uv.unwrap",
    "bpy.ops.uv.smart_project",
    "bpy.ops.uv.cube_project",
    "bpy.ops.object.duplicate",
    "bpy.ops.export_scene.gltf",
    "bpy.ops.export_scene.fbx",
    "bpy.ops.import_scene.gltf",
    "bpy.ops.import_scene.fbx",
    "bpy.ops.wm.usd_export",
    "bpy.ops.wm.usd_import",
    "bpy.ops.curve.",
    "bpy.ops.rigidbody.",
    "bpy.ops.object.bake",
)

# Permitted Builtin Functions
SAFE_BUILTIN_CALLS: Set[str] = {
    "abs", "min", "max", "round", "len", "range",
    "enumerate", "zip", "list", "dict", "set", "tuple",
    "str", "int", "float", "bool", "print",
}


def _get_call_chain(node: ast.AST) -> str:
    """Helper to reconstruct attribute chain from a Call func node."""
    parts = []
    curr = node
    while isinstance(curr, ast.Attribute):
        parts.append(curr.attr)
        curr = curr.value
    if isinstance(curr, ast.Name):
        parts.append(curr.id)
    return ".".join(reversed(parts))


def validate_restricted_code_ast(code: str) -> None:
    """
    Statically analyzes code to ensure it complies with security restrictions:
    - No imports or dunder/private attribute access.
    - No access to dangerous builtins or system modules.
    - Operator calls must strictly match allowlisted bpy.ops prefixes.
    Raises ValueError with descriptive reason if any violation is detected.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Code parameter must be a non-empty string.")

    if len(code) > 16384:
        raise ValueError(f"Code length exceeds maximum allowed limit of 16384 characters ({len(code)} characters).")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise ValueError(f"Syntax error in restricted code: {e}")

    for node in ast.walk(tree):
        # 1. Prohibit banned AST node types
        if isinstance(node, DISALLOWED_AST_NODES):
            raise ValueError(f"Prohibited syntax construct '{type(node).__name__}' is not allowed in modeling code.")

        # 2. Prohibit private and dunder attribute access
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError(f"Access to private or dunder attribute '{node.attr}' is prohibited.")

        # 3. Prohibit banned identifiers and private names
        if isinstance(node, ast.Name):
            if node.id in BANNED_NAMES or node.id.startswith("_"):
                raise ValueError(f"Use of restricted identifier '{node.id}' is prohibited.")

        # 4. Prohibit dangerous calls
        if isinstance(node, ast.Call):
            call_chain = _get_call_chain(node.func)
            if call_chain:
                if call_chain.startswith("bpy.ops."):
                    if not any(call_chain.startswith(prefix) for prefix in ALLOWED_OPERATOR_PREFIXES):
                        raise ValueError(f"Disallowed operator call '{call_chain}'. Operator is not in the safe allowlist.")
                elif "." not in call_chain:
                    if call_chain not in SAFE_BUILTIN_CALLS:
                        raise ValueError(f"Disallowed function call '{call_chain}'. Only safe built-in functions are permitted.")
