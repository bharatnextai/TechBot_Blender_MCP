"""
Offline Unit Tests for Read-Only Bridge Handlers.
Runs purely on CPU using a lightweight in-memory mock of Blender's scene model.
"""

import unittest
from blender_addon.universal_mcp.bridge.handlers import (
    handle_get_scene_summary,
    handle_list_objects,
    handle_get_object_details,
    handle_list_materials,
)


class MockCollection:
    def __init__(self, name):
        self.name = name


class MockModifier:
    def __init__(self, name, mod_type="SUBSURF"):
        self.name = name
        self.type = mod_type
        self.show_viewport = True


class MockMaterialSlot:
    def __init__(self, mat):
        self.material = mat


class MockObject:
    def __init__(self, name, obj_type="MESH", loc=(1.0, 2.0, 3.0), dim=(2.0, 2.0, 2.0)):
        self.name = name
        self.type = obj_type
        self.location = list(loc)
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.dimensions = list(dim)
        self.bound_box = [
            [-1.0, -1.0, -1.0], [1.0, -1.0, -1.0], [1.0, 1.0, -1.0], [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0], [1.0, -1.0, 1.0], [1.0, 1.0, 1.0], [-1.0, 1.0, 1.0]
        ]
        self.parent = None
        self.children = []
        self.users_collection = [MockCollection("Collection_1")]
        self.hide_viewport = False
        self.data = None
        self.material_slots = []
        self.modifiers = []
        self._custom_props = {}

    def keys(self):
        return list(self._custom_props.keys())

    def __getitem__(self, key):
        return self._custom_props[key]


class MockMaterial:
    def __init__(self, name, use_nodes=False, diffuse=(0.8, 0.2, 0.2, 1.0)):
        self.name = name
        self.use_nodes = use_nodes
        self.users = 1
        self.diffuse_color = list(diffuse)
        self.node_tree = None


class MockScene:
    def __init__(self, name="TestScene"):
        self.name = name
        self.frame_current = 1
        self.frame_start = 1
        self.frame_end = 250
        self.camera = None
        self.objects = []
        self.unit_settings = type("UnitSettings", (), {"system": "METRIC"})()
        self.render = type("Render", (), {"fps": 30})()


class MockBpy:
    def __init__(self):
        self.context = type("Context", (), {
            "scene": MockScene(),
            "active_object": None,
        })()
        self.data = type("Data", (), {
            "objects": {},
            "materials": [],
            "collections": [MockCollection("Collection_1"), MockCollection("Collection_2")],
        })()


class TestReadOnlyHandlers(unittest.TestCase):
    def setUp(self):
        self.bpy = MockBpy()
        # Create objects
        obj_cube = MockObject("Cube", "MESH", (0.0, 0.0, 0.0), (2.0, 2.0, 2.0))
        obj_cam = MockObject("Camera", "CAMERA", (0.0, -10.0, 5.0), (0.0, 0.0, 0.0))
        obj_light = MockObject("Light", "LIGHT", (4.0, 1.0, 6.0), (0.0, 0.0, 0.0))

        # Add modifier and material to Cube
        mat_red = MockMaterial("Red_Mat", use_nodes=False, diffuse=(0.9, 0.1, 0.1, 1.0))
        obj_cube.material_slots.append(MockMaterialSlot(mat_red))
        obj_cube.modifiers.append(MockModifier("Subsurf", "SUBSURF"))
        obj_cube._custom_props["prop_test"] = 123

        # Link to scene
        self.bpy.context.scene.objects = [obj_cube, obj_cam, obj_light]
        self.bpy.context.scene.camera = obj_cam
        self.bpy.context.active_object = obj_cube
        self.bpy.data.objects = {"Cube": obj_cube, "Camera": obj_cam, "Light": obj_light}
        self.bpy.data.materials = [mat_red]

    def test_handle_get_scene_summary(self):
        res = handle_get_scene_summary(self.bpy, {"include_collections": True})
        self.assertEqual(res["scene_name"], "TestScene")
        self.assertEqual(res["total_objects"], 3)
        self.assertEqual(res["object_counts_by_type"], {"MESH": 1, "CAMERA": 1, "LIGHT": 1})
        self.assertEqual(res["active_camera"], "Camera")
        self.assertEqual(res["active_object"], "Cube")
        self.assertEqual(res["fps"], 30)
        self.assertEqual(res["collection_count"], 2)
        self.assertIn("Collection_1", res["collections"])

    def test_handle_list_objects_all(self):
        res = handle_list_objects(self.bpy, {})
        self.assertEqual(res["total_matching"], 3)
        self.assertEqual(len(res["objects"]), 3)
        names = [o["name"] for o in res["objects"]]
        self.assertEqual(names, ["Cube", "Camera", "Light"])

    def test_handle_list_objects_filter_type(self):
        res = handle_list_objects(self.bpy, {"object_type": "CAMERA"})
        self.assertEqual(res["total_matching"], 1)
        self.assertEqual(res["objects"][0]["name"], "Camera")
        self.assertEqual(res["objects"][0]["type"], "CAMERA")

    def test_handle_list_objects_pagination(self):
        res = handle_list_objects(self.bpy, {"limit": 2, "offset": 1})
        self.assertEqual(res["total_matching"], 3)
        self.assertEqual(len(res["objects"]), 2)
        self.assertEqual(res["objects"][0]["name"], "Camera")
        self.assertEqual(res["objects"][1]["name"], "Light")

    def test_handle_get_object_details(self):
        res = handle_get_object_details(self.bpy, {"name": "Cube", "include_custom_properties": True})
        self.assertEqual(res["name"], "Cube")
        self.assertEqual(res["type"], "MESH")
        self.assertEqual(res["location"], [0.0, 0.0, 0.0])
        self.assertEqual(res["dimensions"], [2.0, 2.0, 2.0])
        self.assertEqual(len(res["bound_box"]), 8)
        self.assertEqual(res["materials"], ["Red_Mat"])
        self.assertEqual(len(res["modifiers"]), 1)
        self.assertEqual(res["modifiers"][0]["name"], "Subsurf")
        self.assertEqual(res["custom_properties"], {"prop_test": 123})

    def test_handle_get_object_details_missing(self):
        with self.assertRaises(ValueError) as ctx:
            handle_get_object_details(self.bpy, {"name": "NonExistentObject"})
        self.assertIn("not found", str(ctx.exception))

    def test_handle_list_materials(self):
        res = handle_list_materials(self.bpy, {})
        self.assertEqual(res["total_materials"], 1)
        mat_info = res["materials"][0]
        self.assertEqual(mat_info["name"], "Red_Mat")
        self.assertEqual(mat_info["use_nodes"], False)
        self.assertEqual(mat_info["diffuse_color"], [0.9, 0.1, 0.1, 1.0])


if __name__ == "__main__":
    unittest.main()
