"""
Unit tests for Bounded Iterative Silhouette-Guided Modeling (v0.1.53).
Verifies:
1. Schema definition, permissions, properties, and constraints for optimize_mesh_silhouette.
2. Parameter validation (target_object, reference_image_path, view, optimization_mode, crop_box, limits).
3. Fail-closed security against untrusted client approval flags (approved=True).
4. Agent capability registration and task validation.
5. Transactional state snapshotting and rollback mechanics on failure or non-improvement.
6. Topology preservation invariant verification.
"""

import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_OPTIMIZE_MESH_SILHOUETTE,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    SUPPORTED_MODELING_TOOLS,
    CAPABILITY_MODELING_OBJECT_OPS,
)
from shared.models.agent_contracts import AgentTask, TaskStatus
from blender_addon.universal_mcp.bridge.handlers import (
    handle_optimize_mesh_silhouette,
    _LOCAL_TEST_TOOLS,
    ALL_HANDLERS,
)


class TestSilhouetteGuidedModelingUnit(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_ref = Path(self.tmp_dir.name) / "test_ref.png"
        self.tmp_ref.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

        self.valid_params = {
            "target_object": "Suzanne",
            "reference_image_path": str(self.tmp_ref),
            "view": "FRONT",
            "optimization_mode": "BOUNDED_SCALE_TRANSLATE",
            "preserve_topology": True,
            "max_iterations": 5,
            "max_displacement": 0.5,
            "step_size": 0.2,
            "tolerance": 0.001,
            "resolution": 256,
        }

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_schema_registration_and_properties(self):
        """Tool must be properly registered in TOOL_DEFINITIONS and ALL_HANDLERS."""
        self.assertIn(TOOL_OPTIMIZE_MESH_SILHOUETTE, TOOL_DEFINITIONS)
        tool_def = TOOL_DEFINITIONS[TOOL_OPTIMIZE_MESH_SILHOUETTE]
        self.assertEqual(tool_def["name"], "optimize_mesh_silhouette")
        self.assertEqual(tool_def["permission_tier"], PERMISSION_SCENE_MUTATION)

        props = tool_def["input_schema"]["properties"]
        self.assertIn("target_object", props)
        self.assertIn("reference_image_path", props)
        self.assertIn("view", props)
        self.assertIn("optimization_mode", props)
        self.assertIn("preserve_topology", props)
        self.assertIn("max_iterations", props)
        self.assertIn("max_displacement", props)
        self.assertIn("step_size", props)
        self.assertIn("tolerance", props)
        self.assertIn("resolution", props)
        self.assertIn("rollback_on_failure", props)

        req = tool_def["input_schema"]["required"]
        self.assertIn("target_object", req)
        self.assertIn("reference_image_path", req)

        self.assertIn("optimize_mesh_silhouette", ALL_HANDLERS)
        self.assertIn("optimize_mesh_silhouette", _LOCAL_TEST_TOOLS)
        self.assertIn(TOOL_OPTIMIZE_MESH_SILHOUETTE, SUPPORTED_MODELING_TOOLS)

    def test_validate_tool_input_valid(self):
        """Valid inputs must pass sanitize/validation when trusted_approval is True."""
        sanitized = validate_tool_input(
            TOOL_OPTIMIZE_MESH_SILHOUETTE,
            self.valid_params,
            trusted_approval=True,
        )
        self.assertEqual(sanitized["target_object"], "Suzanne")
        self.assertEqual(sanitized["view"], "FRONT")
        self.assertEqual(sanitized["optimization_mode"], "BOUNDED_SCALE_TRANSLATE")
        self.assertEqual(sanitized["max_iterations"], 5)
        self.assertTrue(sanitized["preserve_topology"])

    def test_missing_required_parameters(self):
        """Missing target_object or reference_image_path must fail validation."""
        p_no_target = dict(self.valid_params)
        p_no_target.pop("target_object")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_no_target, trusted_approval=True)

        p_no_ref = dict(self.valid_params)
        p_no_ref.pop("reference_image_path")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_no_ref, trusted_approval=True)

    def test_invalid_view_and_mode_rejected(self):
        """Invalid orthographic views and optimization modes must be rejected."""
        p_bad_view = dict(self.valid_params, view="ISOMETRIC")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_bad_view, trusted_approval=True)

        p_bad_mode = dict(self.valid_params, optimization_mode="FREEFORM")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_bad_mode, trusted_approval=True)

    def test_crop_box_validation(self):
        """Crop box out-of-range, non-normalized, or inverted must be rejected."""
        p_out_range = dict(self.valid_params, crop_box=[-0.1, 0.0, 1.0, 1.0])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_out_range, trusted_approval=True)

        p_inverted = dict(self.valid_params, crop_box=[0.8, 0.0, 0.2, 1.0])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_inverted, trusted_approval=True)

    def test_numeric_limits_validation(self):
        """Displacement, iterations, and resolution limits must be enforced."""
        p_high_iter = dict(self.valid_params, max_iterations=50)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_high_iter, trusted_approval=True)

        p_low_res = dict(self.valid_params, resolution=16)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_low_res, trusted_approval=True)

        p_neg_disp = dict(self.valid_params, max_displacement=-1.0)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_neg_disp, trusted_approval=True)

    def test_security_untrusted_approved_rejected_in_schema(self):
        """Model-supplied approved=True without trusted approval must raise PermissionError."""
        p_untrusted = dict(self.valid_params, approved=True)
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_OPTIMIZE_MESH_SILHOUETTE, p_untrusted, trusted_approval=False)
        self.assertIn("untrusted", str(ctx.exception).lower())

    def test_security_untrusted_approved_rejected_in_agent(self):
        """ModelingAgent must reject untrusted approved=True fail-closed."""
        agent = ModelingAgent()
        mock_executor = MagicMock()
        task = AgentTask(
            task_id="test-task-untrusted",
            task_type=TOOL_OPTIMIZE_MESH_SILHOUETTE,
            required_capability=CAPABILITY_MODELING_OBJECT_OPS,
            input_params={"target_object": "Mesh", "reference_image_path": str(self.tmp_ref), "approved": True},
        )
        result = agent.execute_task(task, mock_executor)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("untrusted" in err.lower() for err in result.errors))

    def test_agent_task_input_validation(self):
        """ModelingAgent validate_task_input must check required fields."""
        agent = ModelingAgent()
        is_valid, err_code, msg = agent.validate_task_input(
            TOOL_OPTIMIZE_MESH_SILHOUETTE,
            {"reference_image_path": str(self.tmp_ref)},
        )
        self.assertFalse(is_valid)
        self.assertEqual(err_code, "INVALID_PARAMS")
        self.assertIn("target_object", msg)

    def test_handler_rejects_missing_object(self):
        """Handler must fail if target_object does not exist in scene."""
        mock_bpy = MagicMock()
        mock_bpy.data.objects = {}
        with self.assertRaises(ValueError) as ctx:
            handle_optimize_mesh_silhouette(mock_bpy, self.valid_params)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_handler_rejects_non_mesh_object(self):
        """Handler must fail if target_object is not a MESH (e.g. CAMERA, LIGHT, EMPTY)."""
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = "EMPTY"
        mock_bpy.data.objects = {"Suzanne": mock_obj}
        with self.assertRaises(ValueError) as ctx:
            handle_optimize_mesh_silhouette(mock_bpy, self.valid_params)
        self.assertIn("not a mesh", str(ctx.exception).lower())

    def test_handler_rejects_degenerate_geometry(self):
        """Handler must fail if mesh has fewer than 3 vertices or 0 polygons."""
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = "MESH"
        mock_obj.data.vertices = [MagicMock(), MagicMock()]  # only 2 vertices
        mock_obj.data.polygons = []
        mock_bpy.data.objects = {"Suzanne": mock_obj}
        with self.assertRaises(ValueError) as ctx:
            handle_optimize_mesh_silhouette(mock_bpy, self.valid_params)
        self.assertIn("degenerate geometry", str(ctx.exception).lower())


    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_rollback_on_failed_optimization(self, mock_comp):
        """When candidates fail to improve IoU, initial mesh state must be restored bit-for-bit."""
        baseline_res = {
            "alignment_status": "PARTIALLY_ALIGNED",
            "iou": 0.50,
            "dice_coefficient": 0.66,
            "divergence_score": 0.50,
            "reference_foreground_pixels": 1000,
            "model_foreground_pixels": 800,
            "reference_centroid": [128.0, 128.0],
            "model_centroid": [120.0, 120.0],
            "reference_bounds": [50, 50, 200, 200],
            "model_bounds": [60, 60, 180, 180],
        }
        worse_res = dict(baseline_res, iou=0.40, divergence_score=0.60)
        mock_comp.side_effect = [baseline_res, worse_res, worse_res, worse_res, worse_res, worse_res]

        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = "MESH"
        mock_obj.location = [0.0, 0.0, 0.0]
        mock_obj.rotation_euler = [0.0, 0.0, 0.0]
        mock_obj.scale = [1.0, 1.0, 1.0]
        mock_obj.dimensions = [2.0, 2.0, 2.0]

        v1 = MagicMock(); v1.co = [1.0, 0.0, 0.0]
        v2 = MagicMock(); v2.co = [0.0, 1.0, 0.0]
        v3 = MagicMock(); v3.co = [0.0, 0.0, 1.0]
        mock_obj.data.vertices = [v1, v2, v3]
        mock_obj.data.edges = [MagicMock(), MagicMock(), MagicMock()]
        mock_obj.data.polygons = [MagicMock()]
        mock_bpy.data.objects = {"Suzanne": mock_obj}

        res = handle_optimize_mesh_silhouette(mock_bpy, self.valid_params)

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "NO_IMPROVEMENT")
        self.assertTrue(res["rolled_back"])
        self.assertEqual(res["iou_improvement"], 0.0)
        self.assertEqual(list(mock_obj.location), [0.0, 0.0, 0.0])
        self.assertEqual(list(mock_obj.scale), [1.0, 1.0, 1.0])
        self.assertEqual(list(v1.co), [1.0, 0.0, 0.0])

    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_successful_optimization_with_topology_preservation(self, mock_comp):
        """When candidate improves IoU, state is kept and topology invariant is preserved."""
        baseline_res = {
            "alignment_status": "PARTIALLY_ALIGNED",
            "iou": 0.40,
            "dice_coefficient": 0.57,
            "divergence_score": 0.60,
            "reference_foreground_pixels": 1000,
            "model_foreground_pixels": 800,
            "reference_centroid": [128.0, 128.0],
            "model_centroid": [120.0, 120.0],
            "reference_bounds": [50, 50, 200, 200],
            "model_bounds": [60, 60, 180, 180],
        }
        improved_res = {
            "alignment_status": "ALIGNED",
            "iou": 0.72,
            "dice_coefficient": 0.83,
            "divergence_score": 0.28,
            "reference_foreground_pixels": 1000,
            "model_foreground_pixels": 950,
            "reference_centroid": [128.0, 128.0],
            "model_centroid": [128.0, 128.0],
            "reference_bounds": [50, 50, 200, 200],
            "model_bounds": [52, 52, 198, 198],
        }
        mock_comp.side_effect = [baseline_res, improved_res, improved_res, improved_res]

        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = "MESH"
        mock_obj.location = [0.0, 0.0, 0.0]
        mock_obj.rotation_euler = [0.0, 0.0, 0.0]
        mock_obj.scale = [1.0, 1.0, 1.0]
        mock_obj.dimensions = [2.0, 2.0, 2.0]

        v1 = MagicMock(); v1.co = [1.0, 0.0, 0.0]
        v2 = MagicMock(); v2.co = [0.0, 1.0, 0.0]
        v3 = MagicMock(); v3.co = [0.0, 0.0, 1.0]
        mock_obj.data.vertices = [v1, v2, v3]
        mock_obj.data.edges = [MagicMock(), MagicMock(), MagicMock()]
        mock_obj.data.polygons = [MagicMock()]
        mock_bpy.data.objects = {"Suzanne": mock_obj}

        res = handle_optimize_mesh_silhouette(mock_bpy, self.valid_params)

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "OPTIMIZED")
        self.assertFalse(res["rolled_back"])
        self.assertTrue(res["topology_preserved"])
        self.assertAlmostEqual(res["iou_improvement"], 0.32, places=3)
        self.assertAlmostEqual(res["divergence_reduction"], 0.32, places=3)
        self.assertEqual(res["final_metrics"]["iou"], 0.72)


if __name__ == "__main__":
    unittest.main()
