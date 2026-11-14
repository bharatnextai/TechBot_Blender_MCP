"""
Unit tests for Multi-View Simultaneous Silhouette Fitting (v0.1.54).
Verifies:
1. Schema definition, permissions, properties, and constraints for fit_multiview_silhouette.
2. Parameter validation (target_object, views list bounds [2..3], view names, weights, crop_box, regression tolerance, objectives).
3. Fail-closed security against untrusted client approval flags (approved=True).
4. Agent capability registration and task validation.
5. Multi-view regression protection (rejection when any protected view regresses beyond tolerance).
6. Transactional state snapshotting and rollback mechanics on failure or non-improvement.
7. Topology preservation invariant verification.
8. Backward-compatible delegation from optimize_mesh_silhouette when views parameter is passed.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_FIT_MULTIVIEW_SILHOUETTE,
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
    handle_fit_multiview_silhouette,
    handle_optimize_mesh_silhouette,
    _LOCAL_TEST_TOOLS,
    ALL_HANDLERS,
)


class TestMultiviewSilhouetteFittingUnit(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_ref_front = Path(self.tmp_dir.name) / "test_ref_front.png"
        self.tmp_ref_front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

        self.tmp_ref_side = Path(self.tmp_dir.name) / "test_ref_side.png"
        self.tmp_ref_side.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

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
            "objective": "WEIGHTED_IOU",
            "optimization_mode": "BOUNDED_SCALE_TRANSLATE",
            "preserve_topology": True,
            "max_iterations": 2,
            "max_displacement": 0.5,
            "step_size": 0.2,
            "tolerance": 0.001,
            "resolution": 256,
        }

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_schema_registration_and_properties(self):
        """Tool must be properly registered in TOOL_DEFINITIONS and ALL_HANDLERS."""
        self.assertIn(TOOL_FIT_MULTIVIEW_SILHOUETTE, TOOL_DEFINITIONS)
        tool_def = TOOL_DEFINITIONS[TOOL_FIT_MULTIVIEW_SILHOUETTE]
        self.assertEqual(tool_def["name"], "fit_multiview_silhouette")
        self.assertEqual(tool_def["permission_tier"], PERMISSION_SCENE_MUTATION)

        props = tool_def["input_schema"]["properties"]
        self.assertIn("target_object", props)
        self.assertIn("views", props)
        self.assertIn("objective", props)
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
        self.assertIn("views", req)

        self.assertIn("fit_multiview_silhouette", ALL_HANDLERS)
        self.assertIn("fit_multiview_silhouette", _LOCAL_TEST_TOOLS)
        self.assertIn(TOOL_FIT_MULTIVIEW_SILHOUETTE, SUPPORTED_MODELING_TOOLS)

    def test_validate_tool_input_valid(self):
        """Valid inputs must pass validation when trusted_approval is True."""
        sanitized = validate_tool_input(
            TOOL_FIT_MULTIVIEW_SILHOUETTE,
            self.valid_params,
            trusted_approval=True,
        )
        self.assertEqual(sanitized["target_object"], "Suzanne")
        self.assertEqual(len(sanitized["views"]), 2)
        self.assertEqual(sanitized["objective"], "WEIGHTED_IOU")
        self.assertEqual(sanitized["optimization_mode"], "BOUNDED_SCALE_TRANSLATE")
        self.assertEqual(sanitized["max_iterations"], 2)
        self.assertTrue(sanitized["preserve_topology"])

    def test_missing_required_parameters(self):
        """Missing target_object or views must fail validation."""
        p_no_target = dict(self.valid_params)
        p_no_target.pop("target_object")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_no_target, trusted_approval=True)

        p_no_views = dict(self.valid_params)
        p_no_views.pop("views")
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_no_views, trusted_approval=True)

    def test_views_count_bounds(self):
        """Views list must contain between 2 and 3 views."""
        p_one_view = dict(self.valid_params, views=[self.valid_params["views"][0]])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_one_view, trusted_approval=True)

        p_four_views = dict(self.valid_params, views=[
            self.valid_params["views"][0],
            self.valid_params["views"][1],
            {"view": "TOP", "reference_image_path": str(self.tmp_ref_front)},
            {"view": "FRONT", "reference_image_path": str(self.tmp_ref_front)},
        ])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_four_views, trusted_approval=True)

    def test_duplicate_views_rejected(self):
        """Duplicate views in views list must be rejected."""
        p_duplicate = dict(self.valid_params, views=[
            {"view": "FRONT", "reference_image_path": str(self.tmp_ref_front)},
            {"view": "FRONT", "reference_image_path": str(self.tmp_ref_side)},
        ])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_duplicate, trusted_approval=True)

    def test_invalid_view_name_rejected(self):
        """Unsupported view names must be rejected."""
        p_bad_view = dict(self.valid_params, views=[
            {"view": "PERSPECTIVE", "reference_image_path": str(self.tmp_ref_front)},
            {"view": "SIDE", "reference_image_path": str(self.tmp_ref_side)},
        ])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_bad_view, trusted_approval=True)

    def test_invalid_weight_or_tolerance_rejected(self):
        """Non-positive weights or out-of-range regression tolerance must be rejected."""
        p_neg_weight = dict(self.valid_params, views=[
            {"view": "FRONT", "reference_image_path": str(self.tmp_ref_front), "weight": -0.5},
            {"view": "SIDE", "reference_image_path": str(self.tmp_ref_side)},
        ])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_neg_weight, trusted_approval=True)

        p_bad_tol = dict(self.valid_params, views=[
            {"view": "FRONT", "reference_image_path": str(self.tmp_ref_front), "max_regression_tolerance": 1.5},
            {"view": "SIDE", "reference_image_path": str(self.tmp_ref_side)},
        ])
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_bad_tol, trusted_approval=True)

    def test_security_untrusted_approved_rejected_in_schema(self):
        """Model-supplied approved=True without trusted approval must raise PermissionError."""
        p_untrusted = dict(self.valid_params, approved=True)
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_FIT_MULTIVIEW_SILHOUETTE, p_untrusted, trusted_approval=False)
        self.assertIn("untrusted", str(ctx.exception).lower())

    def test_security_untrusted_approved_rejected_in_agent(self):
        """ModelingAgent must reject untrusted approved=True fail-closed."""
        agent = ModelingAgent()
        mock_executor = MagicMock()
        task = AgentTask(
            task_id="test-task-untrusted-mv",
            task_type=TOOL_FIT_MULTIVIEW_SILHOUETTE,
            required_capability=CAPABILITY_MODELING_OBJECT_OPS,
            input_params={"target_object": "Mesh", "views": self.valid_params["views"], "approved": True},
        )
        result = agent.execute_task(task, mock_executor)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertTrue(any("untrusted" in err.lower() for err in result.errors))

    def test_agent_task_input_validation(self):
        """ModelingAgent validate_task_input must check target_object and views."""
        agent = ModelingAgent()
        is_valid, err_code, msg = agent.validate_task_input(
            TOOL_FIT_MULTIVIEW_SILHOUETTE,
            {"views": self.valid_params["views"]},
        )
        self.assertFalse(is_valid)
        self.assertEqual(err_code, "INVALID_PARAMS")
        self.assertIn("target_object", msg)

        is_valid, err_code, msg = agent.validate_task_input(
            TOOL_FIT_MULTIVIEW_SILHOUETTE,
            {"target_object": "Suzanne", "views": [{"view": "FRONT", "reference_image_path": "x.png"}]},
        )
        self.assertFalse(is_valid)
        self.assertEqual(err_code, "INVALID_PARAMS")
        self.assertIn("2 or 3", msg)

    def test_handler_rejects_missing_object(self):
        """Handler must fail if target_object does not exist in scene."""
        mock_bpy = MagicMock()
        mock_bpy.data.objects = {}
        with self.assertRaises(ValueError) as ctx:
            handle_fit_multiview_silhouette(mock_bpy, self.valid_params)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_handler_rejects_non_mesh_object(self):
        """Handler must fail if target_object is not a MESH."""
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = "CAMERA"
        mock_bpy.data.objects = {"Suzanne": mock_obj}
        with self.assertRaises(ValueError) as ctx:
            handle_fit_multiview_silhouette(mock_bpy, self.valid_params)
        self.assertIn("not a mesh", str(ctx.exception).lower())

    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_rollback_on_failed_multiview_optimization(self, mock_comp):
        """When multi-view candidate fails to improve aggregate, initial mesh state is rolled back bit-for-bit."""
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
        worse_front = dict(base_front, iou=0.40)
        worse_side = dict(base_side, iou=0.35)

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

        res = handle_fit_multiview_silhouette(mock_bpy, self.valid_params)

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "NO_IMPROVEMENT")
        self.assertTrue(res["rolled_back"])
        self.assertEqual(res["aggregate_improvement"], 0.0)
        self.assertEqual(list(mock_obj.location), [0.0, 0.0, 0.0])
        self.assertEqual(list(mock_obj.scale), [1.0, 1.0, 1.0])
        self.assertEqual(list(v1.co), [1.0, 0.0, 0.0])

    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_regression_protection_rejects_step_when_one_view_violates_tolerance(self, mock_comp):
        """If aggregate would improve but one protected view regresses beyond tolerance, the candidate step must be rejected."""
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
        # Step where FRONT improves from 0.50 to 0.70 (+0.20), but SIDE drops from 0.50 to 0.40 (-0.10)
        # Aggregate with weights 1:1 goes from 0.50 to 0.55 (+0.05), but SIDE violates tolerance of 0.02!
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

        res = handle_fit_multiview_silhouette(mock_bpy, self.valid_params)

        # Must NOT commit the regressed candidate
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "NO_IMPROVEMENT")
        self.assertTrue(res["rolled_back"])
        self.assertEqual(list(mock_obj.location), [0.0, 0.0, 0.0])

    @patch("blender_addon.universal_mcp.bridge.target_silhouette.evaluate_target_silhouette")
    def test_successful_multiview_optimization_with_topology_preservation(self, mock_comp):
        """When candidate improves aggregate and protects all views, step is accepted and topology is preserved."""
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
        # Candidate improves both FRONT (0.40 -> 0.65) and SIDE (0.42 -> 0.68)
        opt_front = dict(base_front, iou=0.65, dice_coefficient=0.79, divergence_score=0.35, alignment_status="ALIGNED")
        opt_side = dict(base_side, iou=0.68, dice_coefficient=0.81, divergence_score=0.32, alignment_status="ALIGNED")

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

        res = handle_fit_multiview_silhouette(mock_bpy, self.valid_params)

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "OPTIMIZED")
        self.assertFalse(res["rolled_back"])
        self.assertTrue(res["topology_preserved"])
        self.assertAlmostEqual(res["initial_aggregate_score"], 0.41, places=3)
        self.assertAlmostEqual(res["final_aggregate_score"], 0.665, places=3)
        self.assertAlmostEqual(res["aggregate_improvement"], 0.255, places=3)
        self.assertIn("FRONT", res["final_per_view_metrics"])
        self.assertIn("SIDE", res["final_per_view_metrics"])
        self.assertEqual(res["final_per_view_metrics"]["FRONT"]["iou"], 0.65)
        self.assertEqual(res["final_per_view_metrics"]["SIDE"]["iou"], 0.68)

    @patch("blender_addon.universal_mcp.bridge.handlers.handle_fit_multiview_silhouette")
    def test_backward_compatibility_delegation_from_optimize_mesh_silhouette(self, mock_fit_mv):
        """optimize_mesh_silhouette must delegate to fit_multiview_silhouette when views param is present."""
        mock_fit_mv.return_value = {"success": True, "status": "OPTIMIZED"}
        mock_bpy = MagicMock()

        res = handle_optimize_mesh_silhouette(mock_bpy, self.valid_params)

        self.assertTrue(res["success"])
        mock_fit_mv.assert_called_once_with(bpy_module=mock_bpy, params=self.valid_params)


if __name__ == "__main__":
    unittest.main()
