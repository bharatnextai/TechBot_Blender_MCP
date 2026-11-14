"""
Unit tests for Bounded Multiresolution Mesh Refinement (v0.1.55).
Verifies:
1. Schema definition, permissions, properties, and constraints for refine_mesh_multiresolution.
2. Parameter validation (target_object, subdivision_type, subdivision_levels, limits, views, crop_box).
3. Fail-closed security against untrusted client approval flags (approved=True).
4. Pre-modification resource limit enforcement (rejection before mesh changes).
5. Transactional state snapshotting and rollback mechanics on failure or non-improvement.
6. Multi-view regression protection across protected views.
7. Predictable topology expansion and geometric detail improvement.
8. Backward-compatible delegation from optimize_mesh_silhouette.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

from shared.schemas.tool_schemas import (
    TOOL_REFINE_MESH_MULTIRESOLUTION,
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
    handle_refine_mesh_multiresolution,
    handle_optimize_mesh_silhouette,
    _LOCAL_TEST_TOOLS,
    ALL_HANDLERS,
)


class TestMultiresolutionRefinementUnit(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_ref_front = Path(self.tmp_dir.name) / "test_ref_front.png"
        self.tmp_ref_side = Path(self.tmp_dir.name) / "test_ref_side.png"

        img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        img.save(self.tmp_ref_front)
        img.save(self.tmp_ref_side)

        self.valid_params = {
            "target_object": "Suzanne",
            "views": [
                {
                    "view": "FRONT",
                    "reference_image_path": str(self.tmp_ref_front),
                    "weight": 1.0,
                    "max_regression_tolerance": 0.02,
                },
                {
                    "view": "SIDE",
                    "reference_image_path": str(self.tmp_ref_side),
                    "weight": 1.0,
                    "max_regression_tolerance": 0.02,
                },
            ],
            "subdivision_type": "CATMULL_CLARK",
            "subdivision_levels": 1,
            "max_vertex_count": 20000,
            "max_face_count": 20000,
            "max_displacement": 0.2,
            "max_iterations": 2,
            "step_size": 0.15,
            "tolerance": 0.001,
            "resolution": 256,
            "objective": "WEIGHTED_IOU",
            "rollback_on_failure": True,
        }

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_schema_registration_and_properties(self):
        """Tool must be properly registered in TOOL_DEFINITIONS and ALL_HANDLERS."""
        self.assertIn(TOOL_REFINE_MESH_MULTIRESOLUTION, TOOL_DEFINITIONS)
        tool_def = TOOL_DEFINITIONS[TOOL_REFINE_MESH_MULTIRESOLUTION]
        self.assertEqual(tool_def["name"], "refine_mesh_multiresolution")
        self.assertEqual(tool_def["permission_tier"], PERMISSION_SCENE_MUTATION)

        props = tool_def["input_schema"]["properties"]
        self.assertIn("target_object", props)
        self.assertIn("views", props)
        self.assertIn("subdivision_type", props)
        self.assertIn("subdivision_levels", props)
        self.assertIn("max_vertex_count", props)
        self.assertIn("max_face_count", props)
        self.assertIn("max_displacement", props)
        self.assertIn("max_iterations", props)
        self.assertIn("step_size", props)
        self.assertIn("tolerance", props)
        self.assertIn("resolution", props)
        self.assertIn("objective", props)
        self.assertIn("rollback_on_failure", props)

        req = tool_def["input_schema"]["required"]
        self.assertIn("target_object", req)

        self.assertIn("refine_mesh_multiresolution", ALL_HANDLERS)
        self.assertIn("refine_mesh_multiresolution", _LOCAL_TEST_TOOLS)
        self.assertIn(TOOL_REFINE_MESH_MULTIRESOLUTION, SUPPORTED_MODELING_TOOLS)

    def test_validate_tool_input_valid(self):
        """Valid inputs must pass validation when trusted_approval is True."""
        sanitized = validate_tool_input(
            TOOL_REFINE_MESH_MULTIRESOLUTION,
            self.valid_params,
            trusted_approval=True,
        )
        self.assertEqual(sanitized["target_object"], "Suzanne")
        self.assertEqual(len(sanitized["views"]), 2)
        self.assertEqual(sanitized["subdivision_type"], "CATMULL_CLARK")
        self.assertEqual(sanitized["subdivision_levels"], 1)
        self.assertEqual(sanitized["max_vertex_count"], 20000)

    def test_missing_required_parameters(self):
        """Missing target_object or reference inputs must fail validation."""
        p_no_target = dict(self.valid_params)
        p_no_target.pop("target_object")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_REFINE_MESH_MULTIRESOLUTION, p_no_target, trusted_approval=True)

        p_no_ref = dict(self.valid_params)
        p_no_ref.pop("views")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_REFINE_MESH_MULTIRESOLUTION, p_no_ref, trusted_approval=True)

    def test_subdivision_parameters_validation(self):
        """Invalid subdivision levels or types must be rejected."""
        p_bad_level = dict(self.valid_params, subdivision_levels=5)  # Cap is 4
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_REFINE_MESH_MULTIRESOLUTION, p_bad_level, trusted_approval=True)

        p_bad_type = dict(self.valid_params, subdivision_type="FRACTAL")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_REFINE_MESH_MULTIRESOLUTION, p_bad_type, trusted_approval=True)

    def test_resource_limits_validation(self):
        """Invalid vertex or face limit bounds must be rejected."""
        p_low_limit = dict(self.valid_params, max_vertex_count=50)  # Min is 100
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_REFINE_MESH_MULTIRESOLUTION, p_low_limit, trusted_approval=True)

        p_high_limit = dict(self.valid_params, max_face_count=200000)  # Max is 100,000
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_REFINE_MESH_MULTIRESOLUTION, p_high_limit, trusted_approval=True)

    def test_security_untrusted_approved_rejected_in_schema(self):
        """Model-supplied approved=True without trusted approval must raise PermissionError."""
        p_untrusted = dict(self.valid_params, approved=True)
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_REFINE_MESH_MULTIRESOLUTION, p_untrusted, trusted_approval=False)
        self.assertIn("untrusted", str(ctx.exception).lower())

    def test_security_untrusted_approved_rejected_in_agent(self):
        """ModelingAgent must reject untrusted approved=True fail-closed."""
        agent = ModelingAgent()
        mock_executor = MagicMock()
        task = AgentTask(
            task_id="test-task-untrusted-refine",
            task_type=TOOL_REFINE_MESH_MULTIRESOLUTION,
            required_capability=CAPABILITY_MODELING_OBJECT_OPS,
            input_params={"target_object": "Mesh", "views": self.valid_params["views"], "approved": True},
        )
        result = agent.execute_task(task, mock_executor)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("untrusted" in err.lower() for err in result.errors))

    def test_agent_task_input_validation(self):
        """ModelingAgent validate_task_input must check target_object and references."""
        agent = ModelingAgent()
        is_valid, err_code, msg = agent.validate_task_input(
            TOOL_REFINE_MESH_MULTIRESOLUTION,
            {"views": self.valid_params["views"]},
        )
        self.assertFalse(is_valid)
        self.assertEqual(err_code, "INVALID_PARAMS")
        self.assertIn("target_object", msg)

        is_valid, err_code, msg = agent.validate_task_input(
            TOOL_REFINE_MESH_MULTIRESOLUTION,
            {"target_object": "Suzanne", "subdivision_levels": 10},
        )
        self.assertFalse(is_valid)
        self.assertEqual(err_code, "INVALID_PARAMS")

    def test_handler_rejects_missing_object(self):
        """Handler must fail if target_object does not exist in scene."""
        mock_bpy = MagicMock()
        mock_bpy.data.objects = {}
        with self.assertRaises(ValueError) as ctx:
            handle_refine_mesh_multiresolution(mock_bpy, self.valid_params)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_handler_rejects_non_mesh_object(self):
        """Handler must fail if target_object is not a MESH."""
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = "LIGHT"
        mock_bpy.data.objects = {"Suzanne": mock_obj}
        with self.assertRaises(ValueError) as ctx:
            handle_refine_mesh_multiresolution(mock_bpy, self.valid_params)
        self.assertIn("not a mesh", str(ctx.exception).lower())

    def test_handler_rejects_precondition_limits_before_modification(self):
        """If predicted post-subdivision face/vertex count exceeds limits, handler must reject before modifying."""
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = "MESH"
        mock_obj.dimensions = [2.0, 2.0, 2.0]
        # 8 vertices, 6 quads. At level 3 subdivision, predicted quads = 6 * 4^3 = 384.
        v_list = [MagicMock() for _ in range(8)]
        p_list = [MagicMock() for _ in range(6)]
        mock_obj.data.vertices = v_list
        mock_obj.data.polygons = p_list
        mock_obj.data.edges = [MagicMock() for _ in range(12)]
        mock_bpy.data.objects = {"Suzanne": mock_obj}

        p_exceed = dict(self.valid_params, subdivision_levels=3, max_face_count=200)  # limit 200 < 384
        with self.assertRaises(ValueError) as ctx:
            handle_refine_mesh_multiresolution(mock_bpy, p_exceed)
        self.assertIn("limit exceeded", str(ctx.exception).lower())

    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_rollback_on_failed_refinement(self, mock_comp):
        """When candidate fails to achieve aggregate improvement, original mesh state is rolled back bit-for-bit."""
        base_front = {
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
        base_side = {
            "alignment_status": "PARTIALLY_ALIGNED",
            "iou": 0.45,
            "dice_coefficient": 0.62,
            "divergence_score": 0.55,
            "reference_foreground_pixels": 1000,
            "model_foreground_pixels": 800,
            "reference_centroid": [128.0, 128.0],
            "model_centroid": [120.0, 120.0],
            "reference_bounds": [50, 50, 200, 200],
            "model_bounds": [60, 60, 180, 180],
        }
        worse_front = dict(base_front, iou=0.35)
        worse_side = dict(base_side, iou=0.30)

        def _mock_side_effect(*args, **kwargs):
            v = kwargs.get("params", {}).get("view", "FRONT")
            if mock_comp.call_count <= 2:
                return base_front if v == "FRONT" else base_side
            return worse_front if v == "FRONT" else worse_side

        mock_comp.side_effect = _mock_side_effect

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

        res = handle_refine_mesh_multiresolution(mock_bpy, self.valid_params)

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "NO_IMPROVEMENT")
        self.assertTrue(res["rolled_back"])
        self.assertEqual(res["aggregate_improvement"], 0.0)
        self.assertEqual(list(mock_obj.location), [0.0, 0.0, 0.0])
        self.assertEqual(list(mock_obj.scale), [1.0, 1.0, 1.0])
        self.assertEqual(list(v1.co), [1.0, 0.0, 0.0])

    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_regression_protection_rejects_refinement_step(self, mock_comp):
        """If aggregate would improve but one protected view regresses beyond tolerance, candidate step is rejected."""
        base_front = {
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
        base_side = {
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
        cand_front = dict(base_front, iou=0.70)
        cand_side_regressed = dict(base_side, iou=0.40)

        def _mock_side_effect(*args, **kwargs):
            v = kwargs.get("params", {}).get("view", "FRONT")
            if mock_comp.call_count <= 2:
                return base_front if v == "FRONT" else base_side
            return cand_front if v == "FRONT" else cand_side_regressed

        mock_comp.side_effect = _mock_side_effect

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

        res = handle_refine_mesh_multiresolution(mock_bpy, self.valid_params)

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "NO_IMPROVEMENT")
        self.assertTrue(res["rolled_back"])
        self.assertEqual(list(mock_obj.location), [0.0, 0.0, 0.0])

    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_successful_multiresolution_refinement(self, mock_comp):
        """When candidate improves aggregate and protects all views, refinement is accepted."""
        base_front = {
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
        base_side = {
            "alignment_status": "PARTIALLY_ALIGNED",
            "iou": 0.42,
            "dice_coefficient": 0.59,
            "divergence_score": 0.58,
            "reference_foreground_pixels": 1000,
            "model_foreground_pixels": 800,
            "reference_centroid": [128.0, 128.0],
            "model_centroid": [120.0, 120.0],
            "reference_bounds": [50, 50, 200, 200],
            "model_bounds": [60, 60, 180, 180],
        }
        opt_front = dict(base_front, iou=0.68, dice_coefficient=0.81, divergence_score=0.32, alignment_status="ALIGNED")
        opt_side = dict(base_side, iou=0.70, dice_coefficient=0.82, divergence_score=0.30, alignment_status="ALIGNED")

        def _mock_side_effect(*args, **kwargs):
            v = kwargs.get("params", {}).get("view", "FRONT")
            if mock_comp.call_count <= 2:
                return base_front if v == "FRONT" else base_side
            return opt_front if v == "FRONT" else opt_side

        mock_comp.side_effect = _mock_side_effect

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

        res = handle_refine_mesh_multiresolution(mock_bpy, self.valid_params)

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "REFINED")
        self.assertFalse(res["rolled_back"])
        self.assertTrue(res["topology_refined"])
        self.assertAlmostEqual(res["initial_aggregate_score"], 0.41, places=3)
        self.assertAlmostEqual(res["final_aggregate_score"], 0.69, places=3)
        self.assertAlmostEqual(res["aggregate_improvement"], 0.28, places=3)
        self.assertIn("FRONT", res["final_per_view_metrics"])
        self.assertIn("SIDE", res["final_per_view_metrics"])

    @patch("blender_addon.universal_mcp.bridge.handlers.handle_refine_mesh_multiresolution")
    def test_backward_compatibility_delegation_from_optimize_mesh_silhouette(self, mock_refine):
        """optimize_mesh_silhouette must delegate to refine_mesh_multiresolution when subdivision_levels is passed."""
        mock_refine.return_value = {"success": True, "status": "REFINED"}
        mock_bpy = MagicMock()

        params = dict(self.valid_params, subdivision_levels=1)
        res = handle_optimize_mesh_silhouette(mock_bpy, params)

        self.assertTrue(res["success"])
        mock_refine.assert_called_once_with(bpy_module=mock_bpy, params=params)


if __name__ == "__main__":
    unittest.main()
