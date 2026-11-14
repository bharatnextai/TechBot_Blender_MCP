"""
Unit tests for v0.1.60 Capability 1 Modeling Gaps Closure:
1. Procedural Texture & Normal Map Baking (bake_mesh_surface_map)
2. Automated Semantic Landmark Correspondence & Feature Detection (detect_semantic_landmarks)
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_DETECT_SEMANTIC_LANDMARKS,
    TOOL_BAKE_MESH_SURFACE_MAP,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    create_modeling_manifest,
    CAPABILITY_MODELING_LANDMARK_DETECTION,
    CAPABILITY_MODELING_SURFACE_BAKE,
    SUPPORTED_MODELING_TOOLS,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_detect_semantic_landmarks,
    handle_bake_mesh_surface_map,
    ALL_HANDLERS,
    _LOCAL_TEST_TOOLS,
)


class TestModelingGapsClosureSchemas(unittest.TestCase):
    """Verifies schema registration, validation rules, parameter bounds, and fail-closed security."""

    def test_tool_registration(self):
        self.assertIn(TOOL_DETECT_SEMANTIC_LANDMARKS, TOOL_DEFINITIONS)
        self.assertIn(TOOL_BAKE_MESH_SURFACE_MAP, TOOL_DEFINITIONS)
        self.assertIn(TOOL_DETECT_SEMANTIC_LANDMARKS, ALL_HANDLERS)
        self.assertIn(TOOL_BAKE_MESH_SURFACE_MAP, ALL_HANDLERS)
        self.assertIn(TOOL_DETECT_SEMANTIC_LANDMARKS, _LOCAL_TEST_TOOLS)
        self.assertIn(TOOL_BAKE_MESH_SURFACE_MAP, _LOCAL_TEST_TOOLS)
        self.assertIn(TOOL_DETECT_SEMANTIC_LANDMARKS, SUPPORTED_MODELING_TOOLS)
        self.assertIn(TOOL_BAKE_MESH_SURFACE_MAP, SUPPORTED_MODELING_TOOLS)

    def test_detect_landmarks_validation_success(self):
        params = {
            "target_object": "Dragon_Mesh",
            "detection_method": "CONTOUR_EXTREMA",
            "confidence_threshold": 0.6,
            "max_vertex_distance": 1.5,
            "enforce_symmetry": True,
            "store_on_mesh": True,
            "landmark_types": ["snout_tip", "horn_apex_left", "horn_apex_right"],
            "views": [
                {
                    "view": "FRONT",
                    "reference_image_path": "C:/images/dragon_ref.png",
                    "crop_box": [0.1, 0.1, 0.9, 0.9],
                }
            ],
        }
        sanitized = validate_tool_input(TOOL_DETECT_SEMANTIC_LANDMARKS, params, trusted_approval=True)
        self.assertEqual(sanitized["target_object"], "Dragon_Mesh")
        self.assertEqual(sanitized["detection_method"], "CONTOUR_EXTREMA")
        self.assertEqual(sanitized["confidence_threshold"], 0.6)
        self.assertEqual(len(sanitized["landmark_types"]), 3)
        self.assertEqual(len(sanitized["views"]), 1)

    def test_detect_landmarks_validation_alias_target(self):
        params = {
            "object_name": "Dragon_Mesh_Alias",
        }
        sanitized = validate_tool_input(TOOL_DETECT_SEMANTIC_LANDMARKS, params, trusted_approval=True)
        self.assertEqual(sanitized["target_object"], "Dragon_Mesh_Alias")
        self.assertEqual(sanitized["detection_method"], "CONTOUR_EXTREMA")
        self.assertTrue(sanitized["enforce_symmetry"])
        self.assertTrue(sanitized["store_on_mesh"])

    def test_detect_landmarks_rejects_missing_target(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_DETECT_SEMANTIC_LANDMARKS, {}, trusted_approval=True)

    def test_detect_landmarks_rejects_invalid_detection_method(self):
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_DETECT_SEMANTIC_LANDMARKS,
                {"target_object": "Dragon", "detection_method": "INVALID_METHOD"},
                trusted_approval=True,
            )

    def test_detect_landmarks_rejects_out_of_bounds_confidence(self):
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_DETECT_SEMANTIC_LANDMARKS,
                {"target_object": "Dragon", "confidence_threshold": 1.5},
                trusted_approval=True,
            )

    def test_detect_landmarks_rejects_untrusted_approval(self):
        with self.assertRaises(PermissionError):
            validate_tool_input(
                TOOL_DETECT_SEMANTIC_LANDMARKS,
                {"target_object": "Dragon", "approved": True},
                trusted_approval=False,
            )

    def test_bake_mesh_surface_map_validation_success(self):
        params = {
            "target_object": "Dragon_Retopo",
            "source_object": "Dragon_HighPoly",
            "map_type": "NORMAL",
            "width": 1024,
            "height": 1024,
            "margin": 16,
            "cage_extrusion": 0.08,
            "max_ray_distance": 0.5,
            "color_space": "Non-Color",
            "use_selected_to_active": True,
            "save_filepath": "C:/bake/normal.png",
        }
        sanitized = validate_tool_input(TOOL_BAKE_MESH_SURFACE_MAP, params, trusted_approval=True)
        self.assertEqual(sanitized["target_object"], "Dragon_Retopo")
        self.assertEqual(sanitized["source_object"], "Dragon_HighPoly")
        self.assertEqual(sanitized["map_type"], "NORMAL")
        self.assertEqual(sanitized["width"], 1024)
        self.assertEqual(sanitized["height"], 1024)
        self.assertEqual(sanitized["margin"], 16)
        self.assertEqual(sanitized["cage_extrusion"], 0.08)
        self.assertEqual(sanitized["save_filepath"], "C:/bake/normal.png")
        self.assertEqual(sanitized["color_space"], "Non-Color")

    def test_bake_mesh_surface_map_rejects_relative_filepath(self):
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_BAKE_MESH_SURFACE_MAP,
                {"target_object": "Dragon_Retopo", "save_filepath": "relative/path/bake.png"},
                trusted_approval=True,
            )

    def test_bake_mesh_surface_map_rejects_invalid_resolution(self):
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_BAKE_MESH_SURFACE_MAP,
                {"target_object": "Dragon_Retopo", "width": 32},  # min 64
                trusted_approval=True,
            )

    def test_bake_mesh_surface_map_rejects_untrusted_approval(self):
        with self.assertRaises(PermissionError):
            validate_tool_input(
                TOOL_BAKE_MESH_SURFACE_MAP,
                {"target_object": "Dragon_Retopo", "approved": True},
                trusted_approval=False,
            )


class TestModelingAgentGapsClosure(unittest.TestCase):
    """Verifies modeling agent manifest, capability descriptors, and execution routing."""

    def test_manifest_capabilities(self):
        manifest = create_modeling_manifest()
        self.assertGreaterEqual(len(manifest.capabilities), 30)
        caps = {c.capability_id: c for c in manifest.capabilities}
        self.assertIn(CAPABILITY_MODELING_LANDMARK_DETECTION, caps)
        self.assertIn(CAPABILITY_MODELING_SURFACE_BAKE, caps)

        cap_detect = caps[CAPABILITY_MODELING_LANDMARK_DETECTION]
        self.assertEqual(cap_detect.supported_task_types, [TOOL_DETECT_SEMANTIC_LANDMARKS])
        self.assertEqual(cap_detect.read_write, "SCENE_MUTATION")
        self.assertEqual(cap_detect.verification_status, "VERIFIED")

        cap_bake = caps[CAPABILITY_MODELING_SURFACE_BAKE]
        self.assertEqual(cap_bake.supported_task_types, [TOOL_BAKE_MESH_SURFACE_MAP])
        self.assertEqual(cap_bake.read_write, "SCENE_MUTATION")
        self.assertEqual(cap_bake.verification_status, "VERIFIED")

    def test_agent_can_handle(self):
        agent = ModelingAgent()
        task_detect = MagicMock(required_capability=CAPABILITY_MODELING_LANDMARK_DETECTION, task_type=TOOL_DETECT_SEMANTIC_LANDMARKS)
        task_bake = MagicMock(required_capability=CAPABILITY_MODELING_SURFACE_BAKE, task_type=TOOL_BAKE_MESH_SURFACE_MAP)
        self.assertTrue(agent.can_handle(task_detect))
        self.assertTrue(agent.can_handle(task_bake))

    def test_agent_routes_execution(self):
        agent = ModelingAgent()
        mock_executor = MagicMock()
        mock_resp = MagicMock(is_success=True, result={"status": "SUCCESS"})
        mock_executor.execute_tool.return_value = mock_resp

        task_detect = MagicMock(
            required_capability=CAPABILITY_MODELING_LANDMARK_DETECTION,
            task_type=None,
            task_id="detect_task_1",
            input_params={"target_object": "Dragon_Mesh"},
        )
        agent.execute_task(task_detect, executor=mock_executor, trusted_approval=True)
        self.assertTrue(mock_executor.execute_tool.called)
        self.assertEqual(mock_executor.execute_tool.call_args[0][0], TOOL_DETECT_SEMANTIC_LANDMARKS)

        task_bake = MagicMock(
            required_capability=CAPABILITY_MODELING_SURFACE_BAKE,
            task_type=None,
            task_id="bake_task_1",
            input_params={"target_object": "Dragon_Retopo", "map_type": "NORMAL"},
        )
        agent.execute_task(task_bake, executor=mock_executor, trusted_approval=True)
        self.assertEqual(mock_executor.execute_tool.call_args[0][0], TOOL_BAKE_MESH_SURFACE_MAP)


class TestMockHandlersGapsClosure(unittest.TestCase):
    """Verifies handlers behavior with mocked bpy."""

    def test_handle_detect_semantic_landmarks_mock(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = 'MESH'
        mock_obj.library = None
        mock_obj.data.library = None
        mock_obj.matrix_world = None

        # Dict backing for custom properties
        props = {}
        mock_obj.__setitem__.side_effect = props.__setitem__
        mock_obj.__getitem__.side_effect = props.__getitem__
        mock_obj.__contains__.side_effect = props.__contains__
        mock_obj.get.side_effect = props.get

        # Create vertices for a mock dragon mesh
        # Coords: forward along +Y, wings along +/-X, horns along +Z
        v_snout = MagicMock(co=[0.0, 2.0, 0.0])
        v_tail = MagicMock(co=[0.0, -2.0, 0.0])
        v_wing_l = MagicMock(co=[1.8, 0.0, 0.5])
        v_wing_r = MagicMock(co=[-1.8, 0.0, 0.5])
        v_horn_l = MagicMock(co=[0.5, -0.2, 1.5])
        v_horn_r = MagicMock(co=[-0.5, -0.2, 1.5])
        mock_obj.data.vertices = [v_snout, v_tail, v_wing_l, v_wing_r, v_horn_l, v_horn_r]
        mock_obj.data.polygons = [MagicMock(), MagicMock()]
        mock_bpy.data.objects = {"Dragon_Mock": mock_obj}

        with patch("blender_addon.universal_mcp.bridge.handlers.is_approval_required", return_value=False):
            res = handle_detect_semantic_landmarks(mock_bpy, {
                "target_object": "Dragon_Mock",
                "detection_method": "CONTOUR_EXTREMA",
                "store_on_mesh": True,
                "enforce_symmetry": True,
            })
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["target_object"], "Dragon_Mock")
            self.assertGreaterEqual(res["detected_count"], 4)
            self.assertTrue(res["stored_on_mesh"])
            self.assertIn("_umcp_semantic_landmarks", props)
            self.assertIn("umcp_landmarks", props)

    def test_handle_bake_mesh_surface_map_precondition_rejection(self):
        mock_bpy = MagicMock()
        mock_bpy.data.objects = {}  # Object not found
        with self.assertRaises(ValueError):
            handle_bake_mesh_surface_map(mock_bpy, {"target_object": "NonExistent"})


if __name__ == "__main__":
    unittest.main()
