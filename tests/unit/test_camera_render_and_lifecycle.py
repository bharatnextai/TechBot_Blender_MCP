from tests.unit.modeling_approval_fixture import approved
"""
Unit tests for Camera creation, Render Settings configuration, Object deletion,
Extended Primitives (cone, torus, monkey, grid), and Project File Saving in Universal MCP.
Tests schemas, input validation, permission enforcement, approval gating, and execution handlers.
"""

import unittest
import tempfile
import os
from typing import Dict, Any, Optional

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    AgentResult,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_CREATE_CAMERA,
    TOOL_CONFIGURE_RENDER_SETTINGS,
    TOOL_DELETE_OBJECT,
    TOOL_SAVE_BLEND_FILE,
    TOOL_CREATE_PRIMITIVE,
    TOOL_DEFINITIONS,
    PERMISSION_READ_ONLY,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_DESTRUCTIVE,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_create_camera,
    handle_configure_render_settings,
    handle_delete_object,
    handle_save_blend_file,
    handle_create_primitive,
    ALLOWED_PRIMITIVES,
)
from mcp_service.security.approval import ApprovalManager


class MockCameraObject:
    def __init__(self, name: str, data: Any):
        self.name = name
        self.type = "CAMERA"
        self.data = data
        self.location = (0.0, 0.0, 0.0)
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.users_collection = []


class MockCameraData:
    def __init__(self, name: str):
        self.name = name
        self.lens = 50.0
        self.clip_start = 0.1
        self.clip_end = 1000.0
        self.sensor_width = 36.0
        self.users = 1


class MockMeshObject:
    def __init__(self, name: str, data: Any):
        self.name = name
        self.type = "MESH"
        self.data = data
        self.location = (0.0, 0.0, 0.0)
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.dimensions = (1.0, 1.0, 1.0)
        self.users_collection = []


class MockMeshData:
    def __init__(self, name: str):
        self.name = name
        self.users = 1


class MockRenderSettings:
    def __init__(self):
        self.engine = "BLENDER_EEVEE_NEXT"
        self.resolution_x = 1920
        self.resolution_y = 1080
        self.resolution_percentage = 100
        self.fps = 24
        self.fps_base = 1.0
        self.filepath = "/tmp/render/"
        self.image_settings = self

    file_format = "PNG"


class MockSceneCollectionObjects:
    def __init__(self, scene):
        self.scene = scene

    def link(self, obj):
        self.scene.objects_in_scene[obj.name] = obj

    def unlink(self, obj):
        self.scene.objects_in_scene.pop(obj.name, None)


class MockSceneCollection:
    def __init__(self, scene):
        self.objects = MockSceneCollectionObjects(scene)


class MockScene:
    def __init__(self):
        self.camera = None
        self.render = MockRenderSettings()
        self.objects_in_scene: Dict[str, Any] = {}
        self.collection = MockSceneCollection(self)

    @property
    def objects(self):
        return list(self.objects_in_scene.values())


class MockCollectionProperty:
    def __init__(self, factory_fn=None):
        self._items: Dict[str, Any] = {}
        self._factory_fn = factory_fn

    def new(self, name: str, *args, **kwargs):
        if self._factory_fn:
            obj = self._factory_fn(name, *args, **kwargs)
        else:
            obj = MockCameraData(name)
        self._items[name] = obj
        return obj

    def get(self, name: str, default=None):
        return self._items.get(name, default)

    def remove(self, item, do_unlink=True):
        if hasattr(item, "name"):
            self._items.pop(item.name, None)
        else:
            self._items.pop(item, None)

    def __contains__(self, name: str):
        return name in self._items

    def __getitem__(self, name: str):
        return self._items[name]

    def __len__(self):
        return len(self._items)

    def values(self):
        return self._items.values()


class MockData:
    def __init__(self, scene: MockScene):
        self.scene = scene
        self.objects = MockCollectionProperty(factory_fn=self._create_object)
        self.cameras = MockCollectionProperty(factory_fn=lambda name, **kwargs: MockCameraData(name))
        self.meshes = MockCollectionProperty(factory_fn=lambda name, **kwargs: MockMeshData(name))

    def _create_object(self, name: str, object_data=None, *args, **kwargs):
        if isinstance(object_data, MockCameraData):
            obj = MockCameraObject(name, object_data)
        else:
            obj = MockMeshObject(name, object_data)
        return obj


class MockContext:
    def __init__(self, scene: MockScene):
        self.scene = scene
        self.active_object = None
        self.view_layer = self

    def update(self):
        pass

    class active_layer_collection:
        class collection:
            pass


class MockWM:
    def __init__(self):
        self.saved_files: Dict[str, bool] = {}

    def save_as_mainfile(self, filepath: str, check_existing: bool = True, compress: bool = True):
        self.saved_files[filepath] = True


class MockObjectOps:
    def select_all(self, action="DESELECT"):
        pass


class MockOps:
    def __init__(self, bpy):
        self.bpy = bpy
        self.wm = MockWM()
        self.mesh = self
        self.object = MockObjectOps()

    def _create_and_activate(self, name="NewMesh"):
        obj = MockMeshObject(name, MockMeshData(name))
        self.bpy.context.active_object = obj
        self.bpy.data.objects.new(name, obj.data)
        return obj

    def primitive_cone_add(self, **kwargs):
        return self._create_and_activate("TestCone")

    def primitive_torus_add(self, **kwargs):
        return self._create_and_activate("TestTorus")

    def primitive_monkey_add(self, **kwargs):
        return self._create_and_activate("Suzanne")

    def primitive_grid_add(self, **kwargs):
        return self._create_and_activate("TerrainGrid")

    def primitive_cube_add(self, **kwargs):
        return self._create_and_activate("Cube")


class MockBpy:
    def __init__(self):
        self.scene = MockScene()
        self.data = MockData(self.scene)
        self.context = MockContext(self.scene)
        self.context.active_layer_collection.collection = self.scene.collection
        self.ops = MockOps(self)
        self.data.filepath = ""
        self.data.is_dirty = False
        self.data.is_saved = False


class TestCameraRenderAndLifecycle(unittest.TestCase):
    def setUp(self):
        self.bpy = MockBpy()

    # ---------------------------------------------------------
    # TOOL_CREATE_CAMERA Tests
    # ---------------------------------------------------------

    def test_create_camera_default_params(self):
        result = handle_create_camera(self.bpy, {"name": "TestCam"})
        self.assertEqual(result["name"], "TestCam")
        self.assertEqual(result["focal_length"], 50.0)
        self.assertEqual(result["clip_start"], 0.1)
        self.assertEqual(result["clip_end"], 1000.0)
        self.assertIn("TestCam", self.bpy.data.objects)
        self.assertEqual(self.bpy.scene.camera.name, "TestCam")

    def test_create_camera_custom_params(self):
        params = {
            "name": "WideCam",
            "focal_length": 24.0,
            "clip_start": 0.5,
            "clip_end": 5000.0,
            "location": [1.0, 2.0, 3.0],
            "rotation_euler": [0.1, 0.2, 0.3],
            "set_active": False,
        }
        result = handle_create_camera(self.bpy, params)
        self.assertEqual(result["name"], "WideCam")
        self.assertEqual(result["focal_length"], 24.0)
        self.assertEqual(result["clip_start"], 0.5)
        self.assertEqual(result["clip_end"], 5000.0)
        self.assertEqual(result["location"], [1.0, 2.0, 3.0])
        self.assertEqual(result["rotation_euler"], [0.1, 0.2, 0.3])
        self.assertIsNone(self.bpy.scene.camera)

    def test_create_camera_missing_name(self):
        with self.assertRaises(ValueError) as ctx:
            handle_create_camera(self.bpy, {})
        self.assertIn("Camera 'name' is required", str(ctx.exception))

    def test_create_camera_name_collision(self):
        handle_create_camera(self.bpy, {"name": "CamA"})
        with self.assertRaises(ValueError) as ctx:
            handle_create_camera(self.bpy, {"name": "CamA"})
        self.assertIn("already exists", str(ctx.exception))

    def test_create_camera_invalid_clipping(self):
        with self.assertRaises(ValueError) as ctx:
            handle_create_camera(self.bpy, {"name": "BadClip", "clip_start": 10.0, "clip_end": 5.0})
        self.assertIn("strictly less than", str(ctx.exception))

    # ---------------------------------------------------------
    # TOOL_CONFIGURE_RENDER_SETTINGS Tests
    # ---------------------------------------------------------

    def test_configure_render_settings_all_fields(self):
        params = {
            "engine": "CYCLES",
            "resolution_x": 3840,
            "resolution_y": 2160,
            "resolution_percentage": 50,
            "fps": 60,
            "fps_base": 1.001,
            "output_format": "OPEN_EXR",
            "filepath": "/renders/output.exr",
        }
        res = handle_configure_render_settings(self.bpy, params)
        self.assertEqual(res["engine"], "CYCLES")
        self.assertEqual(res["resolution_x"], 3840)
        self.assertEqual(res["resolution_y"], 2160)
        self.assertEqual(res["resolution_percentage"], 50)
        self.assertEqual(res["fps"], 60)
        self.assertEqual(res["output_format"], "OPEN_EXR")
        self.assertEqual(res["output_path"], "/renders/output.exr")

    def test_configure_render_settings_invalid_engine(self):
        with self.assertRaises(ValueError) as ctx:
            handle_configure_render_settings(self.bpy, {"engine": "INVALID_ENGINE"})
        self.assertIn("Unsupported render engine", str(ctx.exception))

    def test_configure_render_settings_invalid_bounds(self):
        with self.assertRaises(ValueError) as ctx:
            handle_configure_render_settings(self.bpy, {"resolution_x": -100})
        self.assertIn("must be a positive integer", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_configure_render_settings(self.bpy, {"resolution_percentage": 0})
        self.assertIn("between 1 and 1000", str(ctx.exception))

    # ---------------------------------------------------------
    # TOOL_DELETE_OBJECT Tests
    # ---------------------------------------------------------

    def test_delete_object_success(self):
        handle_create_camera(self.bpy, {"name": "ToDelete", "set_active": True})
        self.assertIn("ToDelete", self.bpy.data.objects)
        self.assertEqual(self.bpy.scene.camera.name, "ToDelete")

        res = handle_delete_object(self.bpy, {"name": "ToDelete"})
        self.assertTrue(res["deleted"])
        self.assertEqual(res["name"], "ToDelete")
        self.assertNotIn("ToDelete", self.bpy.data.objects)
        self.assertIsNone(self.bpy.scene.camera)

    def test_delete_object_not_found(self):
        with self.assertRaises(ValueError) as ctx:
            handle_delete_object(self.bpy, {"name": "NonExistent"})
        self.assertIn("not found in scene", str(ctx.exception))

    # ---------------------------------------------------------
    # Extended Primitives Tests (cone, torus, monkey, grid)
    # ---------------------------------------------------------

    def test_create_primitive_cone(self):
        self.assertIn("cone", ALLOWED_PRIMITIVES)
        res = handle_create_primitive(self.bpy, approved('create_primitive',{
            "name": "TestCone",
            "primitive_type": "cone",
            "radius": 2.0,
            "depth": 3.0,
            "dimensions": [4.0, 4.0, 3.0],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }))
        self.assertTrue(res["created"])
        self.assertEqual(res["primitive_type"], "cone")
        self.assertEqual(res["dimensions"], [4.0, 4.0, 3.0])

    def test_create_primitive_torus(self):
        self.assertIn("torus", ALLOWED_PRIMITIVES)
        res = handle_create_primitive(self.bpy, approved('create_primitive',{
            "name": "TestTorus",
            "primitive_type": "torus",
            "radius": 1.5,
            "dimensions": [4.0, 4.0, 1.0],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }))
        self.assertTrue(res["created"])
        self.assertEqual(res["primitive_type"], "torus")
        self.assertEqual(res["dimensions"], [4.0, 4.0, 1.0])

    def test_create_primitive_monkey(self):
        self.assertIn("monkey", ALLOWED_PRIMITIVES)
        res = handle_create_primitive(self.bpy, approved('create_primitive',{
            "name": "Suzanne",
            "primitive_type": "monkey",
            "dimensions": [2.0, 2.0, 2.0],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }))
        self.assertTrue(res["created"])
        self.assertEqual(res["primitive_type"], "monkey")
        self.assertEqual(res["dimensions"], [2.0, 2.0, 2.0])

    def test_create_primitive_grid(self):
        self.assertIn("grid", ALLOWED_PRIMITIVES)
        res = handle_create_primitive(self.bpy, approved('create_primitive',{
            "name": "TerrainGrid",
            "primitive_type": "grid",
            "size": 10.0,
            "dimensions": [10.0, 10.0, 0.0],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }))
        self.assertTrue(res["created"])
        self.assertEqual(res["primitive_type"], "grid")
        self.assertEqual(res["dimensions"], [10.0, 10.0, 0.0])

    # ---------------------------------------------------------
    # TOOL_SAVE_BLEND_FILE Tests
    # ---------------------------------------------------------

    def test_save_blend_file_unsaved_no_path(self):
        self.bpy.data.filepath = ""
        with self.assertRaises(ValueError) as ctx:
            handle_save_blend_file(self.bpy, {})
        self.assertIn("Cannot save: No filepath specified", str(ctx.exception))

    def test_save_blend_file_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_save.blend")
            res = handle_save_blend_file(self.bpy, {"filepath": test_file})
            self.assertTrue(res["saved"])
            self.assertEqual(res["filepath"], test_file)
            self.assertIn(test_file, self.bpy.ops.wm.saved_files)

    def test_save_blend_file_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "existing.blend")
            with open(test_file, "w") as f:
                f.write("existing content")

            with self.assertRaises(FileExistsError) as ctx:
                handle_save_blend_file(self.bpy, {"filepath": test_file, "overwrite": False})
            self.assertIn("already exists", str(ctx.exception))

            res = handle_save_blend_file(self.bpy, {"filepath": test_file, "overwrite": True})
            self.assertTrue(res["saved"])

    # ---------------------------------------------------------
    # Permission & Security Gating Tests
    # ---------------------------------------------------------

    def test_permission_tiers(self):
        self.assertEqual(TOOL_DEFINITIONS[TOOL_CREATE_CAMERA]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_CONFIGURE_RENDER_SETTINGS]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_SAVE_BLEND_FILE]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_DELETE_OBJECT]["permission_tier"], PERMISSION_DESTRUCTIVE)

    def test_approval_manager_enforces_all_new_tools(self):
        app_mgr = ApprovalManager()
        self.assertTrue(app_mgr.requires_approval(TOOL_CREATE_CAMERA))
        self.assertTrue(app_mgr.requires_approval(TOOL_CONFIGURE_RENDER_SETTINGS))
        self.assertTrue(app_mgr.requires_approval(TOOL_SAVE_BLEND_FILE))
        self.assertTrue(app_mgr.requires_approval(TOOL_DELETE_OBJECT))

    def test_untrusted_approved_flag_rejected(self):
        test_inputs = [
            (TOOL_CREATE_CAMERA, {"name": "TestCam", "approved": True}),
            (TOOL_CONFIGURE_RENDER_SETTINGS, {"engine": "CYCLES", "approved": True}),
            (TOOL_SAVE_BLEND_FILE, {"filepath": "scene.blend", "approved": True}),
            (TOOL_DELETE_OBJECT, {"name": "Cube", "approved": True}),
        ]
        for tool, params in test_inputs:
            with self.assertRaises(PermissionError) as ctx:
                validate_tool_input(tool, params)
            self.assertIn("untrusted", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
