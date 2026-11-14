"""
Unit tests for Capability 9: Cameras Foundation in Universal MCP.
Tests schemas, input validation, permission enforcement, approval gating,
camera creation, camera configuration, depth of field, projection switching,
independent camera readback, and fail-closed error handling.
"""

import unittest
from typing import Dict, Any, Optional

from shared.schemas.tool_schemas import (
    TOOL_CREATE_CAMERA,
    TOOL_CONFIGURE_CAMERA,
    TOOL_EDIT_CAMERA,
    TOOL_SWITCH_CAMERA,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_create_camera,
    handle_configure_camera,
    handle_switch_camera,
    handle_get_object_details,
    handle_inspect_scene_data,
    ALL_HANDLERS,
    _LOCAL_TEST_TOOLS,
)
from blender_addon.universal_mcp.bridge.main_thread_queue import _QUEUE_TOKEN_GUARDS
from mcp_service.security.approval import ApprovalManager
from tests.unit.modeling_approval_fixture import approved


class MockConstraint:
    def __init__(self, c_type: str):
        self.type = c_type
        self.name = "Track To" if c_type == "TRACK_TO" else c_type
        self.target = None
        self.track_axis = "TRACK_NEGATIVE_Z"
        self.up_axis = "UP_Y"
        self.owner_space = "WORLD"
        self.target_space = "WORLD"


class MockConstraints(list):
    def new(self, type: str):
        c = MockConstraint(type)
        self.append(c)
        return c

    def remove(self, c):
        if c in self:
            super().remove(c)


class MockDOF:
    def __init__(self):
        self.use_dof = False
        self.focus_distance = 10.0
        self.aperture_fstop = 2.8
        self.focus_object = None


class MockCameraData:
    def __init__(self, name: str):
        self.name = name
        self.type = "PERSP"
        self.lens = 50.0
        self.ortho_scale = 6.0
        self.clip_start = 0.1
        self.clip_end = 1000.0
        self.sensor_width = 36.0
        self.sensor_height = 24.0
        self.sensor_fit = "AUTO"
        self.shift_x = 0.0
        self.shift_y = 0.0
        self.show_composition_thirds = False
        self.dof = MockDOF()
        self.users = 1


class MockCameraObject:
    def __init__(self, name: str, data: Any):
        self.name = name
        self.type = "CAMERA"
        self.data = data
        self.location = (0.0, -5.0, 2.0)
        self.rotation_euler = (1.1, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.dimensions = (0.0, 0.0, 0.0)
        self.parent = None
        self.users_collection = []
        self.material_slots = []
        self.modifiers = []
        self.constraints = MockConstraints()

    def keys(self):
        return []


class MockMeshObject:
    def __init__(self, name: str):
        self.name = name
        self.type = "MESH"
        self.data = type("MockMeshData", (), {"vertices": [1, 2, 3], "edges": [], "polygons": []})()
        self.location = (0.0, 0.0, 0.0)
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.dimensions = (2.0, 2.0, 2.0)
        self.parent = None
        self.users_collection = []
        self.material_slots = []
        self.modifiers = []
        self.constraints = MockConstraints()

    def keys(self):
        return []


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
        self.name = "Scene"
        self.camera = None
        self.objects_in_scene = {}
        self.collection = MockSceneCollection(self)
        self.umcp_require_scene_mutation_approval = False


class MockCamerasDataCollection:
    def __init__(self):
        self._cameras = {}

    def new(self, name: str):
        cam = MockCameraData(name)
        self._cameras[name] = cam
        return cam

    def get(self, name: str, default=None):
        return self._cameras.get(name, default)

    def __contains__(self, name: str):
        return name in self._cameras


class MockObjectsCollection:
    def __init__(self, scene):
        self.scene = scene

    def new(self, name: str, object_data: Any):
        obj = MockCameraObject(name, object_data)
        self.scene.objects_in_scene[name] = obj
        return obj

    def get(self, name: str, default=None):
        return self.scene.objects_in_scene.get(name, default)

    def __contains__(self, name: str):
        return name in self.scene.objects_in_scene

    def __iter__(self):
        return iter(self.scene.objects_in_scene.values())


class MockData:
    def __init__(self, scene):
        self.scene = scene
        self.cameras = MockCamerasDataCollection()
        self.objects = MockObjectsCollection(scene)
        self.scenes = [scene]


class MockContext:
    def __init__(self, scene):
        self.scene = scene


class MockBpy:
    def __init__(self):
        self.scene = MockScene()
        self.data = MockData(self.scene)
        self.context = MockContext(self.scene)


class TestCamerasFoundation(unittest.TestCase):
    def setUp(self):
        self.bpy = MockBpy()
        self.app_mgr = ApprovalManager()

    # -------------------------------------------------------------
    # 1. Schemas, Aliases & Permission Tiers
    # -------------------------------------------------------------

    def test_schema_and_alias_registration(self):
        """Ensure configure_camera and edit_camera are registered with proper tiers."""
        self.assertIn(TOOL_CREATE_CAMERA, TOOL_DEFINITIONS)
        self.assertIn(TOOL_CONFIGURE_CAMERA, TOOL_DEFINITIONS)
        self.assertIn(TOOL_EDIT_CAMERA, TOOL_DEFINITIONS)

        self.assertEqual(
            TOOL_DEFINITIONS[TOOL_CONFIGURE_CAMERA]["permission_tier"],
            PERMISSION_SCENE_MUTATION,
        )
        self.assertEqual(
            TOOL_DEFINITIONS[TOOL_EDIT_CAMERA]["permission_tier"],
            PERMISSION_SCENE_MUTATION,
        )

        # Queue guards and handler dispatch
        self.assertIn(TOOL_CONFIGURE_CAMERA, _QUEUE_TOKEN_GUARDS)
        self.assertIn(TOOL_EDIT_CAMERA, _QUEUE_TOKEN_GUARDS)
        self.assertIn(TOOL_CONFIGURE_CAMERA, ALL_HANDLERS)
        self.assertIn(TOOL_EDIT_CAMERA, ALL_HANDLERS)
        self.assertIn(TOOL_CONFIGURE_CAMERA, _LOCAL_TEST_TOOLS)
        self.assertIn(TOOL_EDIT_CAMERA, _LOCAL_TEST_TOOLS)

        # Approval manager enforces scene mutation
        self.assertTrue(self.app_mgr.requires_approval(TOOL_CONFIGURE_CAMERA))
        self.assertTrue(self.app_mgr.requires_approval(TOOL_EDIT_CAMERA))

    # -------------------------------------------------------------
    # 2. Parameter Validation & Security
    # -------------------------------------------------------------

    def test_validation_valid_parameters(self):
        """Validate sanitized parameters for configure_camera."""
        params = {
            "name": "MainCamera",
            "camera_type": "PERSP",
            "focal_length": 85.0,
            "clip_start": 0.2,
            "clip_end": 500.0,
            "sensor_width": 36.0,
            "sensor_height": 24.0,
            "sensor_fit": "AUTO",
            "shift_x": 0.05,
            "shift_y": -0.05,
            "dof": {
                "use_dof": True,
                "focus_distance": 2.5,
                "aperture_fstop": 1.4,
            },
            "location": [0.0, -4.0, 1.5],
            "rotation_euler": [1.2, 0.0, 0.0],
            "set_active": True,
        }
        san = validate_tool_input(TOOL_CONFIGURE_CAMERA, params, trusted_approval=True)
        self.assertEqual(san["name"], "MainCamera")
        self.assertEqual(san["camera_type"], "PERSP")
        self.assertEqual(san["focal_length"], 85.0)
        self.assertEqual(san["shift_x"], 0.05)
        self.assertTrue(san["dof"]["use_dof"])

    def test_validation_alias_normalization(self):
        """Ensure target_name and camera_name normalize to name."""
        san1 = validate_tool_input(TOOL_CONFIGURE_CAMERA, {"target_name": "Cam1"}, trusted_approval=True)
        self.assertEqual(san1["name"], "Cam1")

        san2 = validate_tool_input(TOOL_CONFIGURE_CAMERA, {"camera_name": "Cam2"}, trusted_approval=True)
        self.assertEqual(san2["name"], "Cam2")

    def test_validation_empty_name_rejected(self):
        """Empty camera name must raise ValueError."""
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": ""}, trusted_approval=True)

    def test_validation_unsupported_properties_rejected(self):
        """Unsupported camera properties fail closed."""
        for prop in ("stereoscopy", "stereo", "multi_view", "velocity", "fisheye_polynomial", "motion_blur"):
            with self.assertRaises(ValueError) as ctx:
                validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", prop: True}, trusted_approval=True)
            self.assertIn("Unsupported camera property", str(ctx.exception))

    def test_validation_invalid_bounds(self):
        """Invalid focal length, clipping, or camera type must be rejected."""
        # Non-positive focal length
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "focal_length": -10.0}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "focal_length": 6000.0}, trusted_approval=True)

        # Invalid clipping (start >= end)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "clip_start": 10.0, "clip_end": 5.0}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "clip_start": -1.0}, trusted_approval=True)

        # Invalid camera type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "camera_type": "FISHEYE"}, trusted_approval=True)

        # Invalid sensor fit
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "sensor_fit": "DIAGONAL"}, trusted_approval=True)

        # Invalid DOF f-stop
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "dof": {"aperture_fstop": -2.0}}, trusted_approval=True)

    def test_untrusted_approved_flag_rejected(self):
        """Client-injected approved=True without trusted human token must raise PermissionError."""
        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "Cam", "approved": True})
        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_EDIT_CAMERA, {"name": "Cam", "approved": True})

    # -------------------------------------------------------------
    # 3. Handler Execution: Creation & Configuration
    # -------------------------------------------------------------

    def test_create_camera_extended_parameters(self):
        """Create camera with extended parameters (projection, sensor, DOF, transform)."""
        params = {
            "name": "PortraitCam",
            "camera_type": "PERSP",
            "focal_length": 85.0,
            "ortho_scale": 8.0,
            "clip_start": 0.2,
            "clip_end": 800.0,
            "sensor_width": 36.0,
            "sensor_height": 24.0,
            "sensor_fit": "HORIZONTAL",
            "shift_x": 0.02,
            "shift_y": -0.01,
            "use_dof": True,
            "focus_distance": 3.0,
            "aperture_fstop": 1.8,
            "location": [0.0, -3.0, 1.6],
            "rotation_euler": [1.3, 0.0, 0.0],
            "set_active": True,
        }
        res = handle_create_camera(self.bpy, params)
        self.assertEqual(res["name"], "PortraitCam")
        self.assertEqual(res["focal_length"], 85.0)
        self.assertTrue(res["is_active"])
        self.assertTrue(res["verified"])
        self.assertIn("camera_details", res)

        cd = res["camera_details"]
        self.assertEqual(cd["type"], "PERSP")
        self.assertEqual(cd["lens"], 85.0)
        self.assertEqual(cd["shift_x"], 0.02)
        self.assertTrue(cd["dof"]["use_dof"])
        self.assertEqual(cd["dof"]["aperture_fstop"], 1.8)

    def test_configure_camera_focal_length_and_shift(self):
        """Configure lens and shift on existing camera."""
        handle_create_camera(self.bpy, {"name": "TestCam", "focal_length": 50.0})

        config_params = {
            "name": "TestCam",
            "focal_length": 105.0,
            "shift_x": 0.1,
            "shift_y": -0.05,
        }
        res = handle_configure_camera(self.bpy, config_params)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["verified"])

        cd = res["camera_details"]
        self.assertEqual(cd["focal_length"], 105.0)
        self.assertEqual(cd["shift_x"], 0.1)
        self.assertEqual(cd["shift_y"], -0.05)

    def test_configure_camera_switch_to_orthographic(self):
        """Switch camera projection to ORTHO and configure ortho_scale."""
        handle_create_camera(self.bpy, {"name": "OrthoCam", "focal_length": 50.0})

        res = handle_configure_camera(self.bpy, {
            "name": "OrthoCam",
            "camera_type": "ORTHO",
            "ortho_scale": 15.0,
        })
        self.assertEqual(res["camera_details"]["type"], "ORTHO")
        self.assertEqual(res["camera_details"]["ortho_scale"], 15.0)

    def test_configure_camera_switch_to_panoramic(self):
        """Switch camera projection to PANO."""
        handle_create_camera(self.bpy, {"name": "PanoCam"})

        res = handle_configure_camera(self.bpy, {
            "name": "PanoCam",
            "camera_type": "PANO",
        })
        self.assertEqual(res["camera_details"]["type"], "PANO")

    def test_configure_camera_depth_of_field(self):
        """Configure DOF settings with nested dict and flat params."""
        handle_create_camera(self.bpy, {"name": "DofCam"})

        res = handle_configure_camera(self.bpy, {
            "name": "DofCam",
            "dof": {
                "use_dof": True,
                "focus_distance": 4.2,
                "aperture_fstop": 2.0,
            },
        })
        dof = res["camera_details"]["dof"]
        self.assertTrue(dof["use_dof"])
        self.assertEqual(dof["focus_distance"], 4.2)
        self.assertEqual(dof["aperture_fstop"], 2.0)

    def test_configure_camera_set_active_toggle(self):
        """Toggle active camera assignment."""
        handle_create_camera(self.bpy, {"name": "CamA", "set_active": True})
        handle_create_camera(self.bpy, {"name": "CamB", "set_active": False})

        self.assertEqual(self.bpy.scene.camera.name, "CamA")

        # Switch active camera to CamB
        resB = handle_configure_camera(self.bpy, {"name": "CamB", "set_active": True})
        self.assertTrue(resB["camera_details"]["is_active_camera"])
        self.assertEqual(self.bpy.scene.camera.name, "CamB")

        # Deactivate CamB
        resB2 = handle_configure_camera(self.bpy, {"name": "CamB", "set_active": False})
        self.assertFalse(resB2["camera_details"]["is_active_camera"])
        self.assertIsNone(self.bpy.scene.camera)

    # -------------------------------------------------------------
    # 4. Inspection Readback & Error Gating
    # -------------------------------------------------------------

    def test_get_object_details_returns_camera_details(self):
        """Independent readback via get_object_details returns camera_details."""
        handle_create_camera(self.bpy, {
            "name": "InspectCam",
            "focal_length": 35.0,
            "clip_start": 0.05,
            "clip_end": 2000.0,
            "set_active": True,
        })

        details = handle_get_object_details(self.bpy, {"name": "InspectCam"})
        self.assertEqual(details["name"], "InspectCam")
        self.assertEqual(details["type"], "CAMERA")
        self.assertIsNotNone(details["camera_details"])

        cd = details["camera_details"]
        self.assertEqual(cd["focal_length"], 35.0)
        self.assertEqual(cd["clip_start"], 0.05)
        self.assertEqual(cd["clip_end"], 2000.0)
        self.assertTrue(cd["is_active_camera"])

    def test_configure_camera_non_existent_rejected(self):
        """Configuring non-existent camera raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            handle_configure_camera(self.bpy, {"name": "NoSuchCam"})
        self.assertIn("not found in scene", str(ctx.exception))

    def test_configure_camera_non_camera_object_rejected(self):
        """Attempting to configure a MESH object as CAMERA raises ValueError."""
        mesh_obj = MockMeshObject("Cube")
        self.bpy.data.objects.scene.objects_in_scene["Cube"] = mesh_obj

        with self.assertRaises(ValueError) as ctx:
            handle_configure_camera(self.bpy, {"name": "Cube", "focal_length": 50.0})
        self.assertIn("expected 'CAMERA'", str(ctx.exception))

    # -------------------------------------------------------------
    # 5. Capability 7.2 Phase 1: Framing, Composition & Optical Rigging
    # -------------------------------------------------------------

    def test_create_camera_with_tracking_focus_and_thirds(self):
        """Create camera with track_to_object, focus_object, and show_composition_thirds."""
        target_obj = MockMeshObject("Subject")
        self.bpy.data.objects.scene.objects_in_scene["Subject"] = target_obj

        res = handle_create_camera(self.bpy, {
            "name": "RiggedCam",
            "track_to_object": "Subject",
            "focus_object": "Subject",
            "show_composition_thirds": True,
        })
        self.assertEqual(res["name"], "RiggedCam")
        self.assertEqual(res["track_to_object"], "Subject")
        self.assertEqual(res["focus_object"], "Subject")
        self.assertTrue(res["show_composition_thirds"])

        cd = res["camera_details"]
        self.assertEqual(cd["track_to_object"], "Subject")
        self.assertEqual(cd["focus_object"], "Subject")
        self.assertTrue(cd["show_composition_thirds"])
        self.assertTrue(cd["dof"]["use_dof"])
        self.assertEqual(cd["dof"]["focus_object"], "Subject")

        # Verify underlying constraint
        cam_obj = self.bpy.data.objects.get("RiggedCam")
        self.assertEqual(len(cam_obj.constraints), 1)
        con = cam_obj.constraints[0]
        self.assertEqual(con.type, "TRACK_TO")
        self.assertEqual(con.target.name, "Subject")
        self.assertEqual(con.track_axis, "TRACK_NEGATIVE_Z")
        self.assertEqual(con.up_axis, "UP_Y")

    def test_configure_camera_tracking_focus_and_thirds_mutations(self):
        """Mutate track_to_object, focus_object, and show_composition_thirds on existing camera."""
        handle_create_camera(self.bpy, {"name": "MutateCam"})
        target1 = MockMeshObject("Target1")
        target2 = MockMeshObject("Target2")
        self.bpy.data.objects.scene.objects_in_scene["Target1"] = target1
        self.bpy.data.objects.scene.objects_in_scene["Target2"] = target2

        # Configure tracking to Target1 and thirds enabled
        res1 = handle_configure_camera(self.bpy, {
            "name": "MutateCam",
            "track_to_object": "Target1",
            "focus_object": "Target1",
            "show_composition_thirds": True,
        })
        self.assertEqual(res1["camera_details"]["track_to_object"], "Target1")
        self.assertEqual(res1["camera_details"]["focus_object"], "Target1")
        self.assertTrue(res1["camera_details"]["show_composition_thirds"])

        # Switch tracking and focus to Target2
        res2 = handle_configure_camera(self.bpy, {
            "name": "MutateCam",
            "track_to_object": "Target2",
            "focus_object": "Target2",
            "show_composition_thirds": False,
        })
        self.assertEqual(res2["camera_details"]["track_to_object"], "Target2")
        self.assertEqual(res2["camera_details"]["focus_object"], "Target2")
        self.assertFalse(res2["camera_details"]["show_composition_thirds"])

        cam_obj = self.bpy.data.objects.get("MutateCam")
        self.assertEqual(len(cam_obj.constraints), 1)
        self.assertEqual(cam_obj.constraints[0].target.name, "Target2")

    def test_configure_camera_remove_tracking_and_focus(self):
        """Passing empty string or None for track_to_object/focus_object unsets them."""
        target = MockMeshObject("Anchor")
        self.bpy.data.objects.scene.objects_in_scene["Anchor"] = target

        handle_create_camera(self.bpy, {
            "name": "ClearCam",
            "track_to_object": "Anchor",
            "focus_object": "Anchor",
            "show_composition_thirds": True,
        })

        cam_obj = self.bpy.data.objects.get("ClearCam")
        self.assertEqual(len(cam_obj.constraints), 1)

        # Clear tracking and focus
        res = handle_configure_camera(self.bpy, {
            "name": "ClearCam",
            "track_to_object": "",
            "focus_object": "",
        })
        self.assertIsNone(res["camera_details"]["track_to_object"])
        self.assertIsNone(res["camera_details"]["focus_object"])
        self.assertEqual(len(cam_obj.constraints), 0)
        self.assertIsNone(cam_obj.data.dof.focus_object)

    def test_validation_self_tracking_and_focus_rejected(self):
        """Camera cannot track or focus on itself (fail-closed validation)."""
        with self.assertRaises(ValueError) as ctx1:
            validate_tool_input(TOOL_CREATE_CAMERA, {"name": "SelfCam", "track_to_object": "SelfCam"}, trusted_approval=True)
        self.assertIn("Camera cannot track itself", str(ctx1.exception))

        with self.assertRaises(ValueError) as ctx2:
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "SelfCam", "focus_object": "SelfCam"}, trusted_approval=True)
        self.assertIn("Camera cannot focus on itself", str(ctx2.exception))

        with self.assertRaises(ValueError) as ctx3:
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "SelfCam", "dof": {"focus_object": "SelfCam"}}, trusted_approval=True)
        self.assertIn("Camera cannot focus on itself", str(ctx3.exception))

        with self.assertRaises(ValueError) as ctx4:
            validate_tool_input(TOOL_CONFIGURE_CAMERA, {"name": "SelfCam", "show_composition_thirds": "not_a_bool"}, trusted_approval=True)
        self.assertIn("must be a boolean", str(ctx4.exception))

    def test_handler_nonexistent_target_or_focus_rejected(self):
        """Handler rejects non-existent tracking or focus objects."""
        with self.assertRaises(ValueError) as ctx1:
            handle_create_camera(self.bpy, {"name": "CamA", "track_to_object": "MissingTarget"})
        self.assertIn("Target object 'MissingTarget' not found in scene", str(ctx1.exception))

        handle_create_camera(self.bpy, {"name": "CamB"})
        with self.assertRaises(ValueError) as ctx2:
            handle_configure_camera(self.bpy, {"name": "CamB", "focus_object": "MissingFocus"})
        self.assertIn("Focus object 'MissingFocus' not found in scene", str(ctx2.exception))

    def test_inspection_parity_for_framing_and_composition(self):
        """handle_get_object_details returns track_to_object, focus_object, show_composition_thirds."""
        target = MockMeshObject("InspTarget")
        self.bpy.data.objects.scene.objects_in_scene["InspTarget"] = target

        handle_create_camera(self.bpy, {
            "name": "FullInspectCam",
            "track_to_object": "InspTarget",
            "focus_object": "InspTarget",
            "show_composition_thirds": True,
        })

        details = handle_get_object_details(self.bpy, {"name": "FullInspectCam"})
        cd = details["camera_details"]
        self.assertEqual(cd["track_to_object"], "InspTarget")
        self.assertEqual(cd["focus_object"], "InspTarget")
        self.assertTrue(cd["show_composition_thirds"])
        self.assertEqual(cd["dof"]["focus_object"], "InspTarget")

    def test_switch_camera_schema_and_registration(self):
        """Capability 7.2 Phase 2: switch_camera schema and registry completeness."""
        self.assertIn(TOOL_SWITCH_CAMERA, TOOL_DEFINITIONS)
        schema = TOOL_DEFINITIONS[TOOL_SWITCH_CAMERA]
        self.assertEqual(schema["name"], "switch_camera")
        self.assertEqual(schema["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertIn("camera_name", schema["input_schema"]["properties"])
        self.assertTrue("required" in schema["input_schema"] or "anyOf" in schema["input_schema"])
        self.assertIn("switch_camera", ALL_HANDLERS)
        self.assertIn("switch_camera", _LOCAL_TEST_TOOLS)

        inspect_schema = TOOL_DEFINITIONS[TOOL_INSPECT_SCENE_DATA]
        enum_cats = inspect_schema["input_schema"]["properties"]["category"]["enum"]
        self.assertIn("cameras", enum_cats)
        self.assertIn("camera_settings", enum_cats)

    def test_switch_camera_validation(self):
        """Capability 7.2 Phase 2: switch_camera parameter normalization and validation."""
        # Standard input
        p1 = validate_tool_input(TOOL_SWITCH_CAMERA, {"camera_name": "MainCam"}, trusted_approval=True)
        self.assertEqual(p1["camera_name"], "MainCam")

        # Alias: name
        p2 = validate_tool_input(TOOL_SWITCH_CAMERA, {"name": "SecondaryCam"}, trusted_approval=True)
        self.assertEqual(p2["camera_name"], "SecondaryCam")

        # Alias: target_name
        p3 = validate_tool_input(TOOL_SWITCH_CAMERA, {"target_name": "TertiaryCam"}, trusted_approval=True)
        self.assertEqual(p3["camera_name"], "TertiaryCam")

        # Missing / empty camera_name
        with self.assertRaises(ValueError) as ctx1:
            validate_tool_input(TOOL_SWITCH_CAMERA, {}, trusted_approval=True)
        self.assertIn("camera_name", str(ctx1.exception))

        with self.assertRaises(ValueError) as ctx2:
            validate_tool_input(TOOL_SWITCH_CAMERA, {"camera_name": "   "}, trusted_approval=True)
        self.assertIn("cannot be empty", str(ctx2.exception))

        # Untrusted client approval flag rejected
        with self.assertRaises(PermissionError) as ctx3:
            validate_tool_input(TOOL_SWITCH_CAMERA, {"camera_name": "CamA", "approved": True}, trusted_approval=False)
        self.assertIn("untrusted", str(ctx3.exception).lower())

    def test_switch_camera_handler_execution(self):
        """Capability 7.2 Phase 2: switch_camera handler switches scene active camera."""
        handle_create_camera(self.bpy, {"name": "PerspectiveCam", "set_active": True})
        handle_create_camera(self.bpy, {"name": "IsometricCam", "set_active": False})
        handle_create_camera(self.bpy, {"name": "CinematicCam", "set_active": False})

        self.assertEqual(self.bpy.scene.camera.name, "PerspectiveCam")

        # Switch to IsometricCam
        res1 = handle_switch_camera(self.bpy, {"camera_name": "IsometricCam"})
        self.assertEqual(res1["status"], "success")
        self.assertEqual(res1["action"], "switch_camera")
        self.assertEqual(res1["previous_camera"], "PerspectiveCam")
        self.assertEqual(res1["active_camera"], "IsometricCam")
        self.assertTrue(res1["verified"])
        self.assertTrue(res1["is_active_camera"])
        self.assertEqual(self.bpy.scene.camera.name, "IsometricCam")

        # Switch to CinematicCam using alias 'name'
        res2 = handle_switch_camera(self.bpy, {"name": "CinematicCam"})
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["previous_camera"], "IsometricCam")
        self.assertEqual(res2["active_camera"], "CinematicCam")
        self.assertEqual(self.bpy.scene.camera.name, "CinematicCam")

    def test_switch_camera_rejects_missing_and_non_camera(self):
        """Capability 7.2 Phase 2: switch_camera fail-closed security checks."""
        handle_create_camera(self.bpy, {"name": "ValidCam"})
        mesh_obj = MockMeshObject("CubeMesh")
        self.bpy.data.objects.scene.objects_in_scene["CubeMesh"] = mesh_obj

        # Non-existent camera
        with self.assertRaises(ValueError) as ctx1:
            handle_switch_camera(self.bpy, {"camera_name": "NonExistentCam"})
        self.assertIn("not found in scene", str(ctx1.exception))

        # Non-camera object (mesh)
        with self.assertRaises(ValueError) as ctx2:
            handle_switch_camera(self.bpy, {"camera_name": "CubeMesh"})
        self.assertIn("expected 'CAMERA'", str(ctx2.exception))

        # Empty camera_name
        with self.assertRaises(ValueError) as ctx3:
            handle_switch_camera(self.bpy, {"camera_name": ""})
        self.assertIn("cannot be empty", str(ctx3.exception))

    def test_inspect_scene_data_cameras_category(self):
        """Capability 7.2 Phase 2: inspect_scene_data category='cameras' returns full multi-camera rig."""
        handle_create_camera(self.bpy, {"name": "CamAlpha", "lens": 35.0, "set_active": True})
        handle_create_camera(self.bpy, {"name": "CamBeta", "lens": 85.0, "set_active": False})
        handle_create_camera(self.bpy, {"name": "CamGamma", "lens": 135.0, "set_active": False})

        # Inspect all cameras in scene
        res = handle_inspect_scene_data(self.bpy, {"category": "cameras"})
        self.assertEqual(res["category"], "cameras")
        self.assertEqual(res["active_camera"], "CamAlpha")
        self.assertEqual(res["camera_count"], 3)
        cam_names = [c["name"] for c in res["cameras"]]
        self.assertIn("CamAlpha", cam_names)
        self.assertIn("CamBeta", cam_names)
        self.assertIn("CamGamma", cam_names)

        # Verify active status flag on individual cameras
        alpha_info = next(c for c in res["cameras"] if c["name"] == "CamAlpha")
        beta_info = next(c for c in res["cameras"] if c["name"] == "CamBeta")
        self.assertTrue(alpha_info["is_active_camera"])
        self.assertFalse(beta_info["is_active_camera"])
        self.assertEqual(alpha_info["lens"], 35.0)
        self.assertEqual(beta_info["lens"], 85.0)

        # Inspect specific camera by target_name
        target_res = handle_inspect_scene_data(self.bpy, {"category": "cameras", "target_name": "CamBeta"})
        self.assertIsNotNone(target_res["selected_camera"])
        self.assertEqual(target_res["selected_camera"]["name"], "CamBeta")
        self.assertEqual(target_res["selected_camera"]["lens"], 85.0)


if __name__ == "__main__":
    unittest.main()

