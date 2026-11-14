"""
Unit Tests for Extension Import Boundary, Inspect Categories, and AST Validation.
TASK-UMCP-0023.

Verifies:
1. Extension imports cleanly when repository root is absent from sys.path and 'shared' is blocked.
2. Inspect categories allowlist matches and all valid categories work while invalid ones are rejected.
3. Restricted-code AST validator accepts valid code and rejects all disallowed constructs.
4. Model-supplied approved=True cannot authorize scene mutations.
"""

import ast
import os
import sys
import unittest

from blender_addon.universal_mcp.bridge.ast_validator import (
    validate_restricted_code_ast,
    DISALLOWED_AST_NODES,
    BANNED_NAMES,
    ALLOWED_OPERATOR_PREFIXES,
    SAFE_BUILTIN_CALLS,
)
from blender_addon.universal_mcp.bridge.handlers import (
    ALLOWED_INSPECT_CATEGORIES,
    OBJECT_SPECIFIC_INSPECT_CATEGORIES,
    handle_inspect_scene_data,
)
from shared.schemas.tool_schemas import (
    ALLOWED_INSPECT_CATEGORIES as SHARED_ALLOWED_INSPECT_CATEGORIES,
    OBJECT_SPECIFIC_INSPECT_CATEGORIES as SHARED_OBJECT_SPECIFIC_CATEGORIES,
    validate_tool_input,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_EXECUTE_BLENDER_CODE,
)


class MockCollection:
    def __init__(self, name):
        self.name = name
        self.objects = []
        self.children = []


class MockModifier:
    def __init__(self, name, mod_type="SUBSURF"):
        self.name = name
        self.type = mod_type
        self.show_viewport = True
        self.show_render = True
        self.levels = 2
        self.render_levels = 3


class MockMaterialSlot:
    def __init__(self, mat):
        self.material = mat
        self.name = mat.name if mat else "EmptySlot"


class MockMesh:
    def __init__(self):
        self.vertices = [0] * 8
        self.edges = [0] * 12
        self.polygons = [0] * 6
        self.loops = [0] * 24
        self.has_custom_normals = False


class MockObject:
    def __init__(self, name, obj_type="MESH"):
        self.name = name
        self.type = obj_type
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.dimensions = [2.0, 2.0, 2.0]
        self.parent = None
        self.children = []
        self.hide_viewport = False
        self.data = MockMesh() if obj_type == "MESH" else None
        self.material_slots = []
        self.modifiers = []


class MockWorld:
    def __init__(self, name="World"):
        self.name = name
        self.use_nodes = True
        self.color = [0.05, 0.05, 0.05]


class MockScene:
    def __init__(self, name="TestScene"):
        self.name = name
        self.frame_current = 1
        self.frame_start = 1
        self.frame_end = 250
        self.render = type(
            "Render",
            (),
            {
                "engine": "BLENDER_EEVEE_NEXT",
                "resolution_x": 1920,
                "resolution_y": 1080,
                "resolution_percentage": 100,
                "fps": 24,
                "fps_base": 1.0,
                "filepath": "//render/",
                "image_settings": type("ImageSettings", (), {"file_format": "PNG"})(),
            },
        )()
        self.unit_settings = type("UnitSettings", (), {"system": "METRIC"})()
        self.camera = None
        self.world = MockWorld()
        self.objects = []


class MockBpyData:
    def __init__(self):
        self.objects = {}
        self.materials = {}
        self.collections = []
        self.filepath = ""
        self.is_saved = False
        self.is_dirty = False


class MockBpyContext:
    def __init__(self, scene):
        self.scene = scene
        self.active_object = None


class MockBpy:
    def __init__(self):
        self.scene = MockScene()
        self.data = MockBpyData()
        self.context = MockBpyContext(self.scene)
        self.app = type(
            "App",
            (),
            {
                "version_string": "5.2.2",
                "version": (5, 2, 2),
            },
        )()


class TestExtensionImportBoundary(unittest.TestCase):
    """
    Simulates importing the extension in an environment where repository root
    is NOT in sys.path, and any attempt to import 'shared' fails.
    """

    def test_extension_modules_import_without_shared(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        addon_parent = os.path.join(repo_root, "blender_addon")

        # Save sys.path and sys.modules
        old_path = list(sys.path)
        saved_shared_modules = {k: v for k, v in sys.modules.items() if k == "shared" or k.startswith("shared.")}

        try:
            # Remove repo_root from sys.path
            sys.path = [p for p in sys.path if os.path.abspath(p) != repo_root]
            if addon_parent not in [os.path.abspath(p) for p in sys.path]:
                sys.path.insert(0, addon_parent)

            # Block 'shared' so any runtime import from shared raises ModuleNotFoundError
            for k in list(sys.modules.keys()):
                if k == "shared" or k.startswith("shared."):
                    del sys.modules[k]
            sys.modules["shared"] = None

            # Verify that 'shared' cannot be imported
            with self.assertRaises((ModuleNotFoundError, ImportError)):
                import shared  # noqa: F401

            # Remove already imported universal_mcp modules to force re-import
            for k in list(sys.modules.keys()):
                if k == "universal_mcp" or k.startswith("universal_mcp."):
                    del sys.modules[k]

            # Import the extension and its bridge submodules
            import universal_mcp
            import universal_mcp.bridge.ast_validator as ext_ast
            import universal_mcp.bridge.handlers as ext_handlers
            import universal_mcp.bridge.approval_registry as ext_approval
            import universal_mcp.bridge.bridge_server as ext_server
            import universal_mcp.operators as ext_ops

            # Check that key symbols exist and functions run
            self.assertTrue(hasattr(ext_handlers, "handle_inspect_scene_data"))
            self.assertTrue(hasattr(ext_handlers, "handle_execute_blender_code"))
            self.assertTrue(hasattr(ext_ast, "validate_restricted_code_ast"))
            self.assertIn("scene_summary", ext_handlers.ALLOWED_INSPECT_CATEGORIES)

            # Test that validator runs within this isolated import
            ext_ast.validate_restricted_code_ast("x = 1 + 2\nprint(x)")

        finally:
            # Restore sys.path and sys.modules
            sys.path = old_path
            sys.modules.pop("shared", None)
            sys.modules.update(saved_shared_modules)


class TestInspectCategoriesAllowlist(unittest.TestCase):
    """
    Validates inspect category constants and runtime behavior across all categories.
    """

    def setUp(self):
        self.bpy = MockBpy()
        self.cube = MockObject("Cube", "MESH")
        self.cube.modifiers.append(MockModifier("Subsurf", "SUBSURF"))
        mat = type("Material", (), {
            "name": "CubeMat",
            "use_nodes": False,
            "diffuse_color": [0.8, 0.1, 0.1, 1.0],
            "roughness": 0.4,
            "metallic": 0.0,
            "node_tree": None,
        })()
        self.cube.material_slots.append(MockMaterialSlot(mat))

        self.camera = MockObject("Camera", "CAMERA")
        self.bpy.scene.objects = [self.cube, self.camera]
        self.bpy.data.objects = {"Cube": self.cube, "Camera": self.camera}
        self.bpy.context.active_object = self.cube

        col = MockCollection("MainCollection")
        col.objects = [self.cube]
        self.bpy.data.collections = [col]

    def test_category_constants_parity(self):
        self.assertEqual(ALLOWED_INSPECT_CATEGORIES, SHARED_ALLOWED_INSPECT_CATEGORIES)
        self.assertEqual(OBJECT_SPECIFIC_INSPECT_CATEGORIES, SHARED_OBJECT_SPECIFIC_CATEGORIES)
        expected_categories = {
            "scene_summary",
            "object_modifiers",
            "object_materials",
            "mesh_topology",
            "scene_hierarchy",
            "world_settings",
            "collection_tree",
            "render_settings",
            "blender_info",
            "uv_layers",
            "render_result",
            "compositor_pipeline",
            "compositor_settings",
        }
        self.assertEqual(set(ALLOWED_INSPECT_CATEGORIES), expected_categories)
        self.assertEqual(set(OBJECT_SPECIFIC_INSPECT_CATEGORIES), {"object_modifiers", "object_materials", "mesh_topology", "uv_layers"})

    def test_all_valid_categories_execute_successfully(self):
        expected_keys = {
            "scene_summary": "scene_name",
            "object_modifiers": "modifiers",
            "object_materials": "materials",
            "mesh_topology": "vertex_count",
            "scene_hierarchy": "hierarchy",
            "world_settings": "has_world",
            "collection_tree": "collections",
            "render_settings": "engine",
            "blender_info": "version",
            "uv_layers": "uv_layers",
            "render_result": "available",
            "compositor_pipeline": "compositor_active",
            "compositor_settings": "compositor_active",
        }
        for category in ALLOWED_INSPECT_CATEGORIES:
            target = "Cube" if category in OBJECT_SPECIFIC_INSPECT_CATEGORIES else None
            params = {"category": category}
            if target:
                params["target_name"] = target

            validated_params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, params)
            result = handle_inspect_scene_data(bpy_module=self.bpy, params=validated_params)
            self.assertIsInstance(result, dict)
            key = expected_keys[category]
            self.assertIn(key, result, f"Result for category '{category}' should contain '{key}'")

    def test_invalid_category_rejected(self):
        invalid_categories = ["eval_code", "arbitrary_eval", "", "system_info", "exec", "__class__"]
        for cat in invalid_categories:
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": cat})

            with self.assertRaises(ValueError) as ctx:
                handle_inspect_scene_data(bpy_module=self.bpy, params={"category": cat})
            self.assertIn("is not allowed", str(ctx.exception))

    def test_object_specific_category_without_target_rejected(self):
        for cat in OBJECT_SPECIFIC_INSPECT_CATEGORIES:
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": cat})

            with self.assertRaises(ValueError):
                handle_inspect_scene_data(bpy_module=self.bpy, params={"category": cat})


class TestASTSecurityValidator(unittest.TestCase):
    """
    Tests restricted-code AST validator acceptance and rejection behaviors.
    """

    def test_valid_blender_operations_pass(self):
        snippets = [
            "bpy.ops.object.shade_smooth()",
            "bpy.ops.object.shade_flat()",
            "bpy.ops.object.modifier_add(type='SUBSURF')",
            "bpy.ops.object.modifier_apply(modifier='Subsurf')",
            "bpy.ops.mesh.subdivide(number_cuts=2)",
            "bpy.ops.mesh.primitive_cube_add(size=2.0)",
            "bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0)",
            "bpy.ops.material.new()",
            "bpy.ops.ed.undo_push()",
            "x = len([1, 2, 3])\ny = min(x, 10)\nprint(y)",
            "total = 0\nfor i in range(10):\n    total += abs(float(i))\nprint(total)",
        ]
        for snippet in snippets:
            validate_restricted_code_ast(snippet)

    def test_disallowed_syntax_nodes_rejected(self):
        cases = [
            ("import os", "Import"),
            ("from sys import path", "ImportFrom"),
            ("class MyClass:\n    pass", "ClassDef"),
            ("try:\n    pass\nexcept:\n    pass", "Try"),
            ("global g_var\ng_var = 1", "Global"),
            ("del obj", "Delete"),
            ("async def foo():\n    pass", "AsyncFunctionDef"),
            ("def gen():\n    yield 1", "Yield"),
            ("def gen():\n    yield from [1]", "YieldFrom"),
            ("match 1:\n    case 1:\n        pass", "Match"),
        ]
        for snippet, node_name in cases:
            with self.assertRaises(ValueError, msg=f"Should reject {node_name}") as ctx:
                validate_restricted_code_ast(snippet)
            self.assertIn("is not allowed in modeling code", str(ctx.exception))

    def test_banned_identifiers_rejected(self):
        for banned in BANNED_NAMES:
            snippet = f"{banned}('test')"
            with self.assertRaises(ValueError, msg=f"Should reject banned identifier {banned}") as ctx:
                validate_restricted_code_ast(snippet)
            msg = str(ctx.exception)
            self.assertTrue(
                "prohibited" in msg or "permitted" in msg or "Disallowed" in msg or "restricted" in msg,
                f"Unexpected message for {banned}: {msg}",
            )

    def test_private_and_dunder_attributes_rejected(self):
        cases = [
            "x = obj.__class__",
            "x = obj.__subclasses__()",
            "x = obj.__dict__",
            "x = obj._internal_state",
            "obj._set_value(1)",
        ]
        for snippet in cases:
            with self.assertRaises(ValueError, msg=f"Should reject private attr: {snippet}") as ctx:
                validate_restricted_code_ast(snippet)
            self.assertIn("private or dunder attribute", str(ctx.exception))

    def test_disallowed_bpy_operators_rejected(self):
        cases = [
            "bpy.ops.wm.quit_blender()",
            "bpy.ops.wm.open_mainfile(filepath='evil.blend')",
            "bpy.ops.wm.save_as_mainfile(filepath='evil.blend')",
            "bpy.ops.wm.read_factory_settings()",
            "bpy.ops.script.python_file_run(filepath='evil.py')",
            "bpy.ops.preferences.addon_disable(module='universal_mcp')",
        ]
        for snippet in cases:
            with self.assertRaises(ValueError, msg=f"Should reject {snippet}") as ctx:
                validate_restricted_code_ast(snippet)
            self.assertIn("Disallowed operator call", str(ctx.exception))

    def test_oversized_code_rejected(self):
        large_code = "x = 1\n" * 5000  # > 16384 characters
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast(large_code)
        self.assertIn("exceeds maximum allowed limit", str(ctx.exception))


class TestApprovalTamperingProtection(unittest.TestCase):
    """
    Verifies that model-supplied approved=True cannot authorize scene mutations.
    """

    def test_model_supplied_approval_denied_for_create_primitive(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(
                TOOL_CREATE_PRIMITIVE,
                {"primitive_type": "cube", "name": "HackBox", "approved": True},
                trusted_approval=False,
            )
        self.assertIn("untrusted", str(ctx.exception))

    def test_model_supplied_approval_denied_for_transform_object(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(
                TOOL_TRANSFORM_OBJECT,
                {"name": "Cube", "location": [1.0, 1.0, 1.0], "approved": True},
                trusted_approval=False,
            )
        self.assertIn("untrusted", str(ctx.exception))

    def test_model_supplied_approval_denied_for_execute_blender_code(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(
                TOOL_EXECUTE_BLENDER_CODE,
                {"code": "bpy.ops.object.shade_smooth()", "approved": True},
                trusted_approval=False,
            )
        self.assertIn("untrusted", str(ctx.exception))

    def test_trusted_approval_succeeds(self):
        # When trusted_approval=True is supplied by the verified server boundary
        res = validate_tool_input(
            TOOL_CREATE_PRIMITIVE,
            {"primitive_type": "cube", "name": "ValidBox"},
            trusted_approval=True,
        )
        self.assertTrue(res["trusted_approval"])
        self.assertEqual(res["primitive_type"], "cube")


if __name__ == "__main__":
    unittest.main()
