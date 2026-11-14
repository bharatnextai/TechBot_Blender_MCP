"""
Unit Tests for inspect_scene_data tool.
Validates category allowlisting, target_name enforcement, read-only permissions,
mock data extraction across all categories, and pagination.
"""

import unittest
from shared.schemas.tool_schemas import (
    validate_tool_input,
    TOOL_INSPECT_SCENE_DATA,
    PERMISSION_READ_ONLY,
    TOOL_DEFINITIONS,
)
from blender_addon.universal_mcp.bridge.handlers import handle_inspect_scene_data


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


class MockUVLayer:
    def __init__(self, name, loop_count=24, active_render=False):
        self.name = name
        self.data = [None] * loop_count
        self.active_render = active_render


class MockUVLayers(list):
    def __init__(self, values=(), active=None):
        super().__init__(values)
        self.active = active
        self.active_index = next((i for i, layer in enumerate(self) if active is not None and layer.name == active.name), -1)


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
        self.images = {}
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


class TestInspectSceneData(unittest.TestCase):
    def setUp(self):
        self.bpy = MockBpy()
        # Create test objects
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

    def test_permission_tier(self):
        tool_def = TOOL_DEFINITIONS[TOOL_INSPECT_SCENE_DATA]
        self.assertEqual(tool_def["permission_tier"], PERMISSION_READ_ONLY)

    def test_invalid_category_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "arbitrary_eval"})
        self.assertIn("Invalid value for 'category'", str(ctx.exception))

    def test_object_specific_category_missing_target_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "object_modifiers"})
        self.assertIn("requires a non-empty 'target_name'", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "object_modifiers", "target_name": ""})
        self.assertIn("cannot be empty", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "uv_layers"})
        self.assertIn("requires a non-empty 'target_name'", str(ctx.exception))

    def test_inspect_scene_summary(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "scene_summary"})
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["scene_name"], "TestScene")
        self.assertEqual(res["total_objects"], 2)
        self.assertEqual(res["active_object"], "Cube")

    def test_inspect_object_modifiers(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {
            "category": "object_modifiers",
            "target_name": "Cube",
        })
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["target_name"], "Cube")
        self.assertEqual(res["modifier_count"], 1)
        self.assertEqual(res["modifiers"][0]["name"], "Subsurf")
        self.assertEqual(res["modifiers"][0]["type"], "SUBSURF")
        self.assertEqual(res["modifiers"][0]["properties"]["levels"], 2)

    def test_inspect_object_materials(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {
            "category": "object_materials",
            "target_name": "Cube",
        })
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["target_name"], "Cube")
        self.assertEqual(res["slot_count"], 1)
        self.assertEqual(res["materials"][0]["material_name"], "CubeMat")
        self.assertEqual(res["materials"][0]["roughness"], 0.4)

    def test_inspect_mesh_topology(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {
            "category": "mesh_topology",
            "target_name": "Cube",
        })
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["vertex_count"], 8)
        self.assertEqual(res["edge_count"], 12)
        self.assertEqual(res["polygon_count"], 6)

    def test_inspect_mesh_topology_on_non_mesh_fails(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {
            "category": "mesh_topology",
            "target_name": "Camera",
        })
        with self.assertRaises(ValueError) as ctx:
            handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertIn("not of type 'MESH'", str(ctx.exception))

    def test_inspect_uv_layer_metadata(self):
        first = MockUVLayer("DragonUV", loop_count=24)
        second = MockUVLayer("BakeUV", loop_count=24, active_render=True)
        # Blender RNA access may produce different Python wrappers for the same layer.
        proxy = MockUVLayer("DragonUV")
        self.assertIsNot(first, proxy)
        self.cube.data.uv_layers = MockUVLayers([first, second], active=proxy)
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {
            "category": "uv_layers",
            "target_name": "Cube",
        })
        result = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(result["uv_layer_count"], 2)
        self.assertEqual(result["active_layer"], "DragonUV")
        self.assertEqual(result["uv_layers"][0]["loop_count"], 24)
        self.assertTrue(result["uv_layers"][0]["active"])
        self.assertTrue(result["uv_layers"][1]["active_render"])

    def test_uv_active_index_and_absent_layers(self):
        first, second = MockUVLayer("First", active_render=True), MockUVLayer("Second")
        for layers, expected in (
            (MockUVLayers([first, second], active=MockUVLayer("Second")), "Second"),
            (MockUVLayers([first, second]), None),
            (MockUVLayers(), None),
        ):
            with self.subTest(expected=expected, count=len(layers)):
                self.cube.data.uv_layers = layers
                result = handle_inspect_scene_data(self.bpy, {"category": "uv_layers", "target_name": "Cube"})
                self.assertEqual(result["active_layer"], expected)
                self.assertEqual([v["name"] for v in result["uv_layers"] if v["active"]], [expected] if expected else [])
                if layers:
                    self.assertTrue(result["uv_layers"][0]["active_render"])

    def test_inspect_uv_layers_rejects_non_mesh(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {
            "category": "uv_layers",
            "target_name": "Camera",
        })
        with self.assertRaises(ValueError) as ctx:
            handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertIn("UV layer inspection only applies to mesh", str(ctx.exception))

    def test_inspect_render_result_unavailable_and_available(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "render_result"})
        unavailable = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertFalse(unavailable["image_exists"])
        self.assertFalse(unavailable["available"])

        self.bpy.data.images["Render Result"] = type(
            "RenderImage", (), {"size": (640, 480), "has_data": True, "channels": 4}
        )()
        available = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertTrue(available["image_exists"])
        self.assertTrue(available["available"])
        self.assertEqual((available["width"], available["height"], available["channels"]), (640, 480, 4))

    def test_inspect_scene_hierarchy_and_pagination(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {
            "category": "scene_hierarchy",
            "limit": 1,
            "offset": 0,
        })
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["total_objects"], 2)
        self.assertEqual(res["returned_count"], 1)
        self.assertEqual(res["hierarchy"][0]["name"], "Cube")

    def test_inspect_world_settings(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "world_settings"})
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertTrue(res["has_world"])
        self.assertEqual(res["name"], "World")
        self.assertEqual(res["color"], [0.05, 0.05, 0.05])

    def test_inspect_collection_tree(self):
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "collection_tree"})
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["total_collections"], 1)
        self.assertEqual(res["collections"][0]["name"], "MainCollection")
        self.assertEqual(res["collections"][0]["objects"], ["Cube"])

    def test_inspect_render_settings_with_camera(self):
        self.bpy.scene.camera = self.camera
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "render_settings"})
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["category"], "render_settings")
        self.assertEqual(res["engine"], "BLENDER_EEVEE_NEXT")
        self.assertEqual(res["resolution_x"], 1920)
        self.assertEqual(res["resolution_y"], 1080)
        self.assertEqual(res["resolution_percentage"], 100)
        self.assertEqual(res["frame_start"], 1)
        self.assertEqual(res["frame_end"], 250)
        self.assertEqual(res["fps"], 24)
        self.assertEqual(res["fps_base"], 1.0)
        self.assertEqual(res["output_format"], "PNG")
        self.assertEqual(res["output_path"], "//render/")
        self.assertEqual(res["active_camera"], "Camera")

    def test_inspect_render_settings_no_camera(self):
        self.bpy.scene.camera = None
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "render_settings"})
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["category"], "render_settings")
        self.assertIsNone(res["active_camera"])

    def test_inspect_blender_info_unsaved(self):
        self.bpy.data.is_saved = False
        self.bpy.data.filepath = ""
        self.bpy.data.is_dirty = False
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "blender_info"})
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["category"], "blender_info")
        self.assertEqual(res["version"], "5.2.2")
        self.assertFalse(res["is_saved"])
        self.assertFalse(res["is_dirty"])
        self.assertEqual(res["file_status"], "unsaved")
        self.assertIsNone(res["filepath"])
        self.assertEqual(res["raw_filepath"], "")

    def test_inspect_blender_info_saved(self):
        self.bpy.data.is_saved = True
        self.bpy.data.filepath = "C:/Projects/test_scene.blend"
        self.bpy.data.is_dirty = True
        params = validate_tool_input(TOOL_INSPECT_SCENE_DATA, {"category": "blender_info"})
        res = handle_inspect_scene_data(bpy_module=self.bpy, params=params)
        self.assertEqual(res["category"], "blender_info")
        self.assertEqual(res["version"], "5.2.2")
        self.assertTrue(res["is_saved"])
        self.assertTrue(res["is_dirty"])
        self.assertEqual(res["file_status"], "saved")
        self.assertEqual(res["filepath"], "C:/Projects/test_scene.blend")
        self.assertEqual(res["raw_filepath"], "C:/Projects/test_scene.blend")


if __name__ == "__main__":
    unittest.main()
