"""Unit tests for semantic anatomical landmark guidance (TASK v0.1.57)."""
import json
import math
import unittest
from types import SimpleNamespace

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
    TOOL_INSPECT_SEMANTIC_LANDMARKS,
    TOOL_GUIDE_MESH_LANDMARKS,
    TOOL_OPTIMIZE_MESH_SILHOUETTE,
    validate_tool_input,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
)
from blender_addon.universal_mcp.bridge.handlers import (
    _LOCAL_TEST_TOOLS,
    ALL_HANDLERS,
    READ_ONLY_HANDLERS,
    _project_point_to_view,
    handle_configure_semantic_landmarks,
    handle_inspect_semantic_landmarks,
    handle_guide_mesh_landmarks,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    SUPPORTED_MODELING_TOOLS,
    MODELING_AGENT_ID,
    CAPABILITY_MODELING_LANDMARKS,
    CAPABILITY_MODELING_LANDMARKS_INSPECT,
    CAPABILITY_MODELING_OBJECT_OPS,
)
from shared.models.agent_contracts import AgentTask, AgentResult, TaskStatus


class TestSemanticLandmarksContract(unittest.TestCase):
    def valid_landmarks(self):
        return [
            {
                "name": "snout_tip",
                "vertex_index": 0,
                "position_3d": [0.0, -1.5, 0.5],
                "reference_views": {
                    "FRONT": [0.5, 0.375],
                    "SIDE": [0.3125, 0.375],
                    "TOP": [0.5, 0.3125],
                },
                "weight": 2.0,
                "tolerance": 0.03,
            },
            {
                "name": "horn_tip_left",
                "vertex_index": 1,
                "position_3d": [-0.6, -0.8, 1.8],
                "reference_views": {
                    "FRONT": [0.425, 0.5375],
                    "SIDE": [0.4, 0.5375],
                    "TOP": [0.425, 0.4],
                },
                "weight": 1.5,
                "tolerance": 0.04,
            },
            {
                "name": "horn_tip_right",
                "vertex_index": 2,
                "position_3d": [0.6, -0.8, 1.8],
                "reference_views": {
                    "FRONT": [0.575, 0.5375],
                    "SIDE": [0.4, 0.5375],
                    "TOP": [0.575, 0.4],
                },
                "weight": 1.5,
                "tolerance": 0.04,
            },
            {
                "name": "wing_apex_left",
                "vertex_index": 3,
                "position_3d": [-2.5, 0.5, 2.2],
                "reference_views": {
                    "FRONT": [0.1875, 0.5875],
                    "SIDE": [0.5625, 0.5875],
                    "TOP": [0.1875, 0.5625],
                },
                "weight": 1.8,
                "tolerance": 0.05,
            },
            {
                "name": "wing_apex_right",
                "vertex_index": 4,
                "position_3d": [2.5, 0.5, 2.2],
                "reference_views": {
                    "FRONT": [0.8125, 0.5875],
                    "SIDE": [0.5625, 0.5875],
                    "TOP": [0.8125, 0.5625],
                },
                "weight": 1.8,
                "tolerance": 0.05,
            },
            {
                "name": "tail_tip",
                "vertex_index": 5,
                "position_3d": [0.0, 3.0, 0.8],
                "reference_views": {
                    "FRONT": [0.5, 0.4125],
                    "SIDE": [0.875, 0.4125],
                    "TOP": [0.5, 0.875],
                },
                "weight": 1.2,
                "tolerance": 0.05,
            },
        ]

    def test_tool_registration_and_permission_tiers(self):
        """All three tools must be correctly registered with appropriate permission tiers."""
        self.assertIn(TOOL_CONFIGURE_SEMANTIC_LANDMARKS, TOOL_DEFINITIONS)
        self.assertIn(TOOL_INSPECT_SEMANTIC_LANDMARKS, TOOL_DEFINITIONS)
        self.assertIn(TOOL_GUIDE_MESH_LANDMARKS, TOOL_DEFINITIONS)

        conf_def = TOOL_DEFINITIONS[TOOL_CONFIGURE_SEMANTIC_LANDMARKS]
        self.assertEqual(conf_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertIn("target_object", conf_def["input_schema"]["required"])

        insp_def = TOOL_DEFINITIONS[TOOL_INSPECT_SEMANTIC_LANDMARKS]
        self.assertEqual(insp_def["permission_tier"], PERMISSION_READ_ONLY)
        self.assertIn("target_object", insp_def["input_schema"]["required"])

        guide_def = TOOL_DEFINITIONS[TOOL_GUIDE_MESH_LANDMARKS]
        self.assertEqual(guide_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertIn("target_object", guide_def["input_schema"]["required"])

        self.assertIn(TOOL_CONFIGURE_SEMANTIC_LANDMARKS, SUPPORTED_MODELING_TOOLS)
        self.assertIn(TOOL_INSPECT_SEMANTIC_LANDMARKS, SUPPORTED_MODELING_TOOLS)
        self.assertIn(TOOL_GUIDE_MESH_LANDMARKS, SUPPORTED_MODELING_TOOLS)

        self.assertIn("configure_semantic_landmarks", _LOCAL_TEST_TOOLS)
        self.assertIn("guide_mesh_landmarks", _LOCAL_TEST_TOOLS)

        self.assertIn("configure_semantic_landmarks", ALL_HANDLERS)
        self.assertIn("inspect_semantic_landmarks", ALL_HANDLERS)
        self.assertIn("guide_mesh_landmarks", ALL_HANDLERS)
        self.assertIn("inspect_semantic_landmarks", READ_ONLY_HANDLERS)

    def test_configure_landmarks_validation(self):
        """Valid actions, landmarks, and aliasing succeed; invalid inputs fail."""
        # SET with valid landmarks
        res = validate_tool_input(
            TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
            {"target_object": "Dragon", "action": "SET", "landmarks": self.valid_landmarks()},
            trusted_approval=True,
        )
        self.assertEqual(res["target_object"], "Dragon")
        self.assertEqual(res["action"], "SET")
        self.assertEqual(len(res["landmarks"]), 6)

        # Aliasing: object_name -> target_object
        res_alias = validate_tool_input(
            TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
            {"object_name": "Dragon_Mesh", "action": "CLEAR"},
            trusted_approval=True,
        )
        self.assertEqual(res_alias["target_object"], "Dragon_Mesh")
        self.assertEqual(res_alias["action"], "CLEAR")

        # Invalid action rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
                {"target_object": "Dragon", "action": "DESTROY"},
                trusted_approval=True,
            )

        # Missing target_object rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
                {"action": "CLEAR"},
                trusted_approval=True,
            )

        # Empty landmarks for SET rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
                {"target_object": "Dragon", "action": "SET", "landmarks": []},
                trusted_approval=True,
            )

        # Malformed landmark (missing name) rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
                {"target_object": "Dragon", "action": "SET", "landmarks": [{"vertex_index": 0}]},
                trusted_approval=True,
            )

        # Malformed landmark coordinates rejected (out of [0, 1] range)
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
                {
                    "target_object": "Dragon",
                    "action": "SET",
                    "landmarks": [{"name": "bad", "reference_views": {"FRONT": [1.5, 0.5]}}],
                },
                trusted_approval=True,
            )

    def test_inspect_landmarks_validation(self):
        """inspect_semantic_landmarks validates target_object and defaults views."""
        res = validate_tool_input(
            TOOL_INSPECT_SEMANTIC_LANDMARKS,
            {"target_object": "Dragon"},
            trusted_approval=False,
        )
        self.assertEqual(res["target_object"], "Dragon")
        self.assertEqual(res["views"], ["FRONT", "SIDE", "TOP"])
        self.assertTrue(res["include_projection_details"])

        # Filtered views
        res_filtered = validate_tool_input(
            TOOL_INSPECT_SEMANTIC_LANDMARKS,
            {"target_object": "Dragon", "views": ["FRONT", "SIDE"]},
            trusted_approval=False,
        )
        self.assertEqual(res_filtered["views"], ["FRONT", "SIDE"])

        # Invalid view rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_INSPECT_SEMANTIC_LANDMARKS,
                {"target_object": "Dragon", "views": ["ISOMETRIC"]},
                trusted_approval=False,
            )

    def test_guide_landmarks_validation(self):
        """guide_mesh_landmarks validates bounded parameters and limits."""
        res = validate_tool_input(
            TOOL_GUIDE_MESH_LANDMARKS,
            {
                "target_object": "Dragon",
                "max_iterations": 15,
                "step_size": 0.3,
                "max_displacement": 0.4,
                "influence_radius": 1.2,
                "falloff_type": "SMOOTH",
                "min_error_reduction": 0.002,
                "laplacian_smoothing": 0.1,
                "preserve_topology": True,
            },
            trusted_approval=True,
        )
        self.assertEqual(res["max_iterations"], 15)
        self.assertEqual(res["step_size"], 0.3)
        self.assertEqual(res["falloff_type"], "SMOOTH")

        # Invalid falloff rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_GUIDE_MESH_LANDMARKS,
                {"target_object": "Dragon", "falloff_type": "EXPONENTIAL"},
                trusted_approval=True,
            )

        # Out-of-bounds iterations rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_GUIDE_MESH_LANDMARKS,
                {"target_object": "Dragon", "max_iterations": 100},
                trusted_approval=True,
            )

    def test_untrusted_approval_defense(self):
        """Tool argument 'approved=True' is rejected fail-closed on both mutation tools."""
        for tool_name in (TOOL_CONFIGURE_SEMANTIC_LANDMARKS, TOOL_GUIDE_MESH_LANDMARKS):
            params = {"target_object": "Dragon", "approved": True}
            if tool_name == TOOL_CONFIGURE_SEMANTIC_LANDMARKS:
                params["action"] = "CLEAR"
            with self.assertRaises(PermissionError) as ctx:
                validate_tool_input(tool_name, params, trusted_approval=False)
            self.assertIn("untrusted", str(ctx.exception).lower())

    def test_analytical_projection_math(self):
        """_project_point_to_view accurately projects 3D coordinates onto normalized 2D frames."""
        # Origin (0, 0, 1.5) with ortho_scale=8.0
        # FRONT: u = 0.5 + 0/8 = 0.5, v = 0.5 + (1.5 - 1.5)/8 = 0.5
        uv_front = _project_point_to_view([0.0, 0.0, 1.5], "FRONT", ortho_scale=8.0)
        self.assertEqual(uv_front, [0.5, 0.5])

        # Point at x=4, z=1.5 -> right border in FRONT
        uv_right = _project_point_to_view([4.0, 0.0, 1.5], "FRONT", ortho_scale=8.0)
        self.assertEqual(uv_right, [1.0, 0.5])

        # Point at y=4, z=1.5 -> right border in SIDE
        uv_side = _project_point_to_view([0.0, 4.0, 1.5], "SIDE", ortho_scale=8.0)
        self.assertEqual(uv_side, [1.0, 0.5])

        # Point at x=0, y=0 in TOP -> center (0.5, 0.5)
        uv_top = _project_point_to_view([0.0, 0.0, 5.0], "TOP", ortho_scale=8.0)
        self.assertEqual(uv_top, [0.5, 0.5])

    def test_mock_mesh_lifecycle_and_guidance(self):
        """Lifecycle on mock mesh: SET, INSPECT, UPDATE, GUIDE, REMOVE, CLEAR."""
        class MockMatrix:
            def __matmul__(self, other):
                return list(other)
            def inverted(self):
                return self
            def to_3x3(self):
                return self

        verts = [
            SimpleNamespace(co=[-0.5, -0.5, 0.0]),
            SimpleNamespace(co=[0.5, -0.5, 0.0]),
            SimpleNamespace(co=[0.5, 0.5, 0.0]),
            SimpleNamespace(co=[-0.5, 0.5, 0.0]),
            SimpleNamespace(co=[0.0, 0.0, 1.0]),
        ]
        edges = [
            SimpleNamespace(vertices=[0, 1]),
            SimpleNamespace(vertices=[1, 2]),
            SimpleNamespace(vertices=[2, 3]),
            SimpleNamespace(vertices=[3, 0]),
            SimpleNamespace(vertices=[0, 4]),
            SimpleNamespace(vertices=[1, 4]),
            SimpleNamespace(vertices=[2, 4]),
            SimpleNamespace(vertices=[3, 4]),
        ]
        polys = [
            SimpleNamespace(vertices=[0, 1, 2, 3]),
            SimpleNamespace(vertices=[0, 1, 4]),
            SimpleNamespace(vertices=[1, 2, 4]),
            SimpleNamespace(vertices=[2, 3, 4]),
            SimpleNamespace(vertices=[3, 0, 4]),
        ]
        mock_mesh = SimpleNamespace(
            vertices=verts,
            edges=edges,
            polygons=polys,
            update=lambda: None,
        )
        class MockMeshObject:
            def __init__(self, name, data, matrix_world):
                self.name = name
                self.type = "MESH"
                self.data = data
                self.location = [0.0, 0.0, 0.0]
                self.rotation_euler = [0.0, 0.0, 0.0]
                self.scale = [1.0, 1.0, 1.0]
                self.matrix_world = matrix_world
                self.library = None
                self._props = {}
            def __getitem__(self, k):
                return self._props[k]
            def __setitem__(self, k, v):
                self._props[k] = v
            def get(self, k, default=None):
                return self._props.get(k, default)

        mock_obj = MockMeshObject("MockDragon", mock_mesh, MockMatrix())
        custom_props = mock_obj._props
        mock_bpy = SimpleNamespace(
            data=SimpleNamespace(objects={"MockDragon": mock_obj}),
            context=SimpleNamespace(scene=SimpleNamespace(camera=None, umcp_require_scene_mutation_approval=False)),
        )

        # 1. SET landmarks
        conf_res = handle_configure_semantic_landmarks(
            mock_bpy,
            {
                "target_object": "MockDragon",
                "action": "SET",
                "landmarks": [
                    {
                        "name": "snout_tip",
                        "vertex_index": 0,
                        "reference_views": {"FRONT": [0.45, 0.3]},
                        "weight": 2.0,
                    },
                    {
                        "name": "horn_apex",
                        "vertex_index": 4,
                        "reference_views": {"FRONT": [0.5, 0.65]},
                        "weight": 1.5,
                    },
                ],
            },
        )
        self.assertEqual(conf_res["status"], "SUCCESS")
        self.assertEqual(conf_res["landmarks_count"], 2)
        self.assertIn("umcp_landmarks", custom_props)

        # 2. INSPECT landmarks
        insp_res = handle_inspect_semantic_landmarks(
            mock_bpy,
            {"target_object": "MockDragon"},
        )
        self.assertEqual(insp_res["status"], "SUCCESS")
        self.assertEqual(insp_res["landmarks_count"], 2)
        self.assertGreater(insp_res["aggregate_rmse"], 0.0)

        # 3. GUIDE mesh landmarks
        guide_res = handle_guide_mesh_landmarks(
            mock_bpy,
            {
                "target_object": "MockDragon",
                "max_iterations": 5,
                "step_size": 0.2,
                "max_displacement": 0.3,
                "influence_radius": 1.0,
                "min_error_reduction": 0.0001,
            },
        )
        self.assertEqual(guide_res["status"], "SUCCESS")
        self.assertEqual(guide_res["guidance_status"], "ACCEPTED")
        self.assertTrue(guide_res["topology_preserved"])
        self.assertGreater(guide_res["landmark_error_reduction"], 0.0)
        self.assertLess(guide_res["final_landmark_rmse"], guide_res["initial_landmark_rmse"])

        # 4. UPDATE landmark
        upd_res = handle_configure_semantic_landmarks(
            mock_bpy,
            {
                "target_object": "MockDragon",
                "action": "UPDATE",
                "landmarks": [{"name": "snout_tip", "weight": 3.0}],
            },
        )
        self.assertEqual(upd_res["status"], "SUCCESS")
        saved_lms = json.loads(custom_props["umcp_landmarks"])
        snout = next(l for l in saved_lms if l["name"] == "snout_tip")
        self.assertEqual(snout["weight"], 3.0)

        # 5. REMOVE landmark
        rem_res = handle_configure_semantic_landmarks(
            mock_bpy,
            {
                "target_object": "MockDragon",
                "action": "REMOVE",
                "landmarks": [{"name": "horn_apex"}],
            },
        )
        self.assertEqual(rem_res["landmarks_count"], 1)

        # 6. CLEAR landmarks
        clr_res = handle_configure_semantic_landmarks(
            mock_bpy,
            {"target_object": "MockDragon", "action": "CLEAR"},
        )
        self.assertEqual(clr_res["landmarks_count"], 0)

    def test_precondition_resource_limits_rejection(self):
        """Precondition vertex count exceeding limit is rejected before modification."""
        verts = [SimpleNamespace(co=[0.0, 0.0, 0.0]) for _ in range(500)]
        polys = [SimpleNamespace(vertices=[0, 1, 2]) for _ in range(300)]
        mock_mesh = SimpleNamespace(vertices=verts, polygons=polys)
        mock_obj = SimpleNamespace(name="DenseDragon", type="MESH", data=mock_mesh, library=None)
        mock_bpy = SimpleNamespace(
            data=SimpleNamespace(objects={"DenseDragon": mock_obj}),
            context=SimpleNamespace(scene=SimpleNamespace(umcp_require_scene_mutation_approval=False)),
        )

        with self.assertRaises(ValueError) as ctx:
            handle_guide_mesh_landmarks(
                mock_bpy,
                {"target_object": "DenseDragon", "max_vertex_count": 200},
            )
        self.assertIn("Precondition limit exceeded", str(ctx.exception))

    def test_non_mesh_and_missing_target_rejection(self):
        """Non-mesh target or non-existent target objects are rejected fail-closed."""
        mock_camera = SimpleNamespace(name="CameraObj", type="CAMERA", library=None)
        mock_bpy = SimpleNamespace(
            data=SimpleNamespace(objects={"CameraObj": mock_camera}),
            context=SimpleNamespace(scene=SimpleNamespace(umcp_require_scene_mutation_approval=False)),
        )

        with self.assertRaises(ValueError) as ctx1:
            handle_configure_semantic_landmarks(mock_bpy, {"target_object": "CameraObj", "action": "CLEAR"})
        self.assertIn("not a MESH", str(ctx1.exception))

        with self.assertRaises(ValueError) as ctx2:
            handle_configure_semantic_landmarks(mock_bpy, {"target_object": "GhostObj", "action": "CLEAR"})
        self.assertIn("not found in Blender scene", str(ctx2.exception))

    def test_backward_compatible_delegation_from_optimize_mesh_silhouette(self):
        """optimize_mesh_silhouette accepts refinement_mode='LANDMARK_GUIDED' and 'landmarks'."""
        valid_opt = validate_tool_input(
            TOOL_OPTIMIZE_MESH_SILHOUETTE,
            {
                "target_object": "DragonMesh",
                "reference_image_path": "C:/fake/dragon.png",
                "refinement_mode": "LANDMARK_GUIDED",
                "landmarks": [{"name": "snout_tip", "vertex_index": 0}],
            },
            trusted_approval=True,
        )
        self.assertEqual(valid_opt["refinement_mode"], "LANDMARK_GUIDED")
        self.assertIn("landmarks", valid_opt)

    def test_modeling_agent_routing_and_evidence(self):
        """ModelingAgent routes landmark tools and captures structured evidence."""
        agent = ModelingAgent()
        manifest = agent.get_manifest()
        caps = {c.capability_id: c for c in manifest.capabilities}

        self.assertIn(CAPABILITY_MODELING_LANDMARKS, caps)
        self.assertIn(CAPABILITY_MODELING_LANDMARKS_INSPECT, caps)
        self.assertIn(TOOL_CONFIGURE_SEMANTIC_LANDMARKS, caps[CAPABILITY_MODELING_LANDMARKS].supported_task_types)
        self.assertIn(TOOL_GUIDE_MESH_LANDMARKS, caps[CAPABILITY_MODELING_LANDMARKS].supported_task_types)
        self.assertIn(TOOL_INSPECT_SEMANTIC_LANDMARKS, caps[CAPABILITY_MODELING_LANDMARKS_INSPECT].supported_task_types)

        # Validate task input
        self.assertTrue(agent.validate_task_input(TOOL_CONFIGURE_SEMANTIC_LANDMARKS, {"target_object": "Dragon", "action": "SET"})[0])
        self.assertTrue(agent.validate_task_input(TOOL_INSPECT_SEMANTIC_LANDMARKS, {"target_object": "Dragon"})[0])
        self.assertTrue(agent.validate_task_input(TOOL_GUIDE_MESH_LANDMARKS, {"target_object": "Dragon"})[0])
        self.assertFalse(agent.validate_task_input(TOOL_GUIDE_MESH_LANDMARKS, {})[0])

        # Evidence capture via execute_task
        from mcp_service.execution.blender_executor import BridgeResponse
        class MockExecutor:
            def is_connected(self):
                return True
            def execute_tool(self, tool_name, arguments=None, trusted_approval=None):
                return BridgeResponse.success({
                    "status": "SUCCESS",
                    "guidance_status": "ACCEPTED",
                    "initial_landmark_rmse": 0.082,
                    "final_landmark_rmse": 0.041,
                    "landmark_error_reduction": 0.041,
                    "landmarks_count": 6,
                    "max_vertex_displacement": 0.185,
                })

        agent = ModelingAgent()
        task = AgentTask(
            task_id="t_guide",
            required_capability=CAPABILITY_MODELING_LANDMARKS,
            task_type=TOOL_GUIDE_MESH_LANDMARKS,
            input_params={"target_object": "Dragon"},
        )
        agent_res = agent.execute_task(task, MockExecutor(), trusted_approval=True)
        self.assertEqual(agent_res.status, TaskStatus.SUCCEEDED)
        self.assertIn("guidance_status:ACCEPTED", agent_res.evidence_references)
        self.assertIn("landmark_error_reduction:0.041", agent_res.evidence_references)
        self.assertIn("landmarks_count:6", agent_res.evidence_references)


if __name__ == "__main__":
    unittest.main()
