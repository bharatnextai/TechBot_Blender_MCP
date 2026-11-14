"""Unit tests for bounded organic sculpting and anatomy refinement (TASK v0.1.56)."""
import math
import unittest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_SCULPT_ORGANIC_ANATOMY,
    TOOL_SCULPT_MESH,
    TOOL_OPTIMIZE_MESH_SILHOUETTE,
    validate_tool_input,
    PERMISSION_SCENE_MUTATION,
)
from blender_addon.universal_mcp.bridge.handlers import (
    _LOCAL_TEST_TOOLS,
    ALL_HANDLERS,
    handle_sculpt_organic_anatomy,
)
from blender_addon.universal_mcp.bridge.sculpt_contract import validate as validate_sculpt_contract
from mcp_service.agents.modeling import (
    ModelingAgent,
    SUPPORTED_MODELING_TOOLS,
    MODELING_AGENT_ID,
    CAPABILITY_MODELING_SCULPT,
    CAPABILITY_MODELING_OBJECT_OPS,
)
from shared.models.agent_contracts import AgentTask
from mcp_service.agents.registry import AgentRegistry
from mcp_service.agents.router import CapabilityRouter


class TestOrganicSculptingContract(unittest.TestCase):
    def valid_params(self, **kwargs):
        base = {
            "target_object": "DisposableMesh",
            "brush_type": "INFLATE",
            "radius": 0.5,
            "strength": 0.5,
            "max_displacement": 0.2,
            "iterations": 1,
            "preserve_topology": True,
            "dynamic_topology": False,
        }
        base.update(kwargs)
        return base

    def test_tool_registration_and_permission_tier(self):
        """Tool must be registered as SCENE_MUTATION and present in all handlers and test scopes."""
        self.assertIn(TOOL_SCULPT_ORGANIC_ANATOMY, TOOL_DEFINITIONS)
        tool_def = TOOL_DEFINITIONS[TOOL_SCULPT_ORGANIC_ANATOMY]
        self.assertEqual(tool_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(tool_def["name"], "sculpt_organic_anatomy")
        self.assertIn("target_object", tool_def["input_schema"]["required"])
        self.assertIn(TOOL_SCULPT_ORGANIC_ANATOMY, SUPPORTED_MODELING_TOOLS)
        self.assertIn("sculpt_organic_anatomy", _LOCAL_TEST_TOOLS)
        self.assertIn("sculpt_organic_anatomy", ALL_HANDLERS)

    def test_brush_type_validation(self):
        """Supported brush types (GRAB, INFLATE, SMOOTH, CLAY, DRAW) accepted; invalid rejected."""
        for b_type in ("GRAB", "INFLATE", "SMOOTH", "CLAY", "DRAW", "grab", "inflate", "smooth", "clay", "draw"):
            res = validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(brush_type=b_type), trusted_approval=True)
            self.assertEqual(res["brush_type"], b_type.upper())

        for invalid_b in ("PINCH", "SNAKE_HOOK", "LAYER", "FLATTEN", "", 123):
            with self.assertRaises((ValueError, TypeError)):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(brush_type=invalid_b), trusted_approval=True)

    def test_bounded_radius_and_strength_validation(self):
        """Radius in [0.001, 10.0] and strength in [0.0, 1.0] strictly enforced."""
        valid = validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(radius=0.001, strength=0.0), trusted_approval=True)
        self.assertEqual(valid["radius"], 0.001)
        self.assertEqual(valid["strength"], 0.0)

        valid_max = validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(radius=10.0, strength=1.0), trusted_approval=True)
        self.assertEqual(valid_max["radius"], 10.0)
        self.assertEqual(valid_max["strength"], 1.0)

        for bad_r in (0.0, -1.0, 10.1, float("nan"), float("inf"), "big"):
            with self.assertRaises((ValueError, TypeError)):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(radius=bad_r), trusted_approval=True)

        for bad_s in (-0.1, 1.1, float("nan"), float("inf"), "strong"):
            with self.assertRaises((ValueError, TypeError)):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(strength=bad_s), trusted_approval=True)

    def test_max_displacement_and_iterations_limits(self):
        """Displacement in [0.001, 2.0] and iterations in [1, 10] strictly enforced."""
        valid = validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(max_displacement=2.0, iterations=10), trusted_approval=True)
        self.assertEqual(valid["max_displacement"], 2.0)
        self.assertEqual(valid["iterations"], 10)

        for bad_d in (0.0, -0.5, 2.1, float("nan")):
            with self.assertRaises((ValueError, TypeError)):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(max_displacement=bad_d), trusted_approval=True)

        for bad_it in (0, -1, 11, "five"):
            with self.assertRaises((ValueError, TypeError)):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(iterations=bad_it), trusted_approval=True)

    def test_resource_limits_vertex_and_face_counts(self):
        """max_vertex_count and max_face_count in [100, 100000] strictly enforced."""
        valid = validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(max_vertex_count=100, max_face_count=100000), trusted_approval=True)
        self.assertEqual(valid["max_vertex_count"], 100)
        self.assertEqual(valid["max_face_count"], 100000)

        for bad_v in (99, 100001, -10):
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(max_vertex_count=bad_v), trusted_approval=True)

        for bad_f in (99, 100001, -5):
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(max_face_count=bad_f), trusted_approval=True)

    def test_topology_preservation_conflict_check(self):
        """Conflicting parameters preserve_topology=True and dynamic_topology=True must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(
                TOOL_SCULPT_ORGANIC_ANATOMY,
                self.valid_params(preserve_topology=True, dynamic_topology=True),
                trusted_approval=True,
            )
        self.assertIn("Conflicting parameters", str(ctx.exception))

        # Explicit dynamic topology requires preserve_topology=False
        valid = validate_tool_input(
            TOOL_SCULPT_ORGANIC_ANATOMY,
            self.valid_params(preserve_topology=False, dynamic_topology=True),
            trusted_approval=True,
        )
        self.assertFalse(valid["preserve_topology"])
        self.assertTrue(valid["dynamic_topology"])

    def test_stroke_points_and_direction_validation(self):
        """stroke_points coordinates and stroke_direction vector strictly validated."""
        # 3D points
        valid_3d = validate_tool_input(
            TOOL_SCULPT_ORGANIC_ANATOMY,
            self.valid_params(stroke_points=[[0.0, 1.0, 2.0], [0.5, 0.5, 0.5]], stroke_direction=[0.0, 1.0, 0.0]),
            trusted_approval=True,
        )
        self.assertEqual(len(valid_3d["stroke_points"]), 2)
        self.assertEqual(valid_3d["stroke_direction"], [0.0, 1.0, 0.0])

        # Dict points
        valid_dict = validate_tool_input(
            TOOL_SCULPT_ORGANIC_ANATOMY,
            self.valid_params(stroke_points=[{"x": 1.0, "y": 2.0, "z": 3.0}]),
            trusted_approval=True,
        )
        self.assertEqual(valid_dict["stroke_points"], [[1.0, 2.0, 3.0]])

        # Invalid points
        for bad_pts in ([], [[]], [[float("nan"), 0.0, 0.0]], [[0, 0, 0, 0]], "points"):
            with self.assertRaises((ValueError, TypeError)):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(stroke_points=bad_pts), trusted_approval=True)

        # Invalid direction
        for bad_dir in ([0.0, 1.0], [0, 0, 0, 0], [float("nan"), 0.0, 0.0]):
            with self.assertRaises((ValueError, TypeError)):
                validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(stroke_direction=bad_dir), trusted_approval=True)

    def test_views_and_objective_validation(self):
        """Multi-view configuration and objective validation."""
        views_cfg = [
            {"view": "FRONT", "reference_image_path": "C:/fake/front.png", "weight": 1.0, "max_regression_tolerance": 0.01},
            {"view": "SIDE", "reference_image_path": "C:/fake/side.png", "weight": 1.5, "max_regression_tolerance": 0.02},
        ]
        valid = validate_tool_input(
            TOOL_SCULPT_ORGANIC_ANATOMY,
            self.valid_params(views=views_cfg, objective="MIN_IOU"),
            trusted_approval=True,
        )
        self.assertEqual(len(valid["views"]), 2)
        self.assertEqual(valid["objective"], "MIN_IOU")

        # Duplicate views rejected
        dup_views = [
            {"view": "FRONT", "reference_image_path": "C:/fake/front1.png"},
            {"view": "FRONT", "reference_image_path": "C:/fake/front2.png"},
        ]
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(views=dup_views), trusted_approval=True)

        # Invalid objective rejected
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(objective="MAX_IOU"), trusted_approval=True)

    def test_untrusted_approval_flag_defense(self):
        """Untrusted approved=True in arguments must be rejected fail-closed with PermissionError."""
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(approved=True), trusted_approval=False)
        self.assertIn("untrusted", str(ctx.exception).lower())

        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(), trusted_approval=False)
        self.assertIn("approval required", str(ctx.exception).lower())

    def test_target_object_and_alias_resolution(self):
        """target_object and object_name are accepted interchangeably."""
        valid_tgt = validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, {"target_object": "MeshA", "brush_type": "CLAY"}, trusted_approval=True)
        self.assertEqual(valid_tgt["target_object"], "MeshA")

        valid_obj = validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, {"object_name": "MeshB", "brush_type": "DRAW"}, trusted_approval=True)
        self.assertEqual(valid_obj["target_object"], "MeshB")

        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SCULPT_ORGANIC_ANATOMY, {"brush_type": "CLAY"}, trusted_approval=True)

    def test_modeling_agent_routing_and_validation(self):
        """ModelingAgent routes TOOL_SCULPT_ORGANIC_ANATOMY and validates task input."""
        agent = ModelingAgent()
        manifest = agent.manifest
        cap = manifest.get_capability(CAPABILITY_MODELING_SCULPT)
        self.assertIsNotNone(cap)
        self.assertIn(TOOL_SCULPT_ORGANIC_ANATOMY, cap.supported_task_types)

        registry = AgentRegistry()
        registry.register_agent(manifest)
        router = CapabilityRouter(registry=registry)
        task = AgentTask(task_id="t_sculpt", required_capability=CAPABILITY_MODELING_SCULPT, task_type=TOOL_SCULPT_ORGANIC_ANATOMY)
        res = router.route(task, require_verified=True)
        self.assertTrue(res.success)
        self.assertEqual(res.agent.agent_id, MODELING_AGENT_ID)

        # Agent validate_task_input
        self.assertTrue(agent.validate_task_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params())[0])
        self.assertFalse(agent.validate_task_input(TOOL_SCULPT_ORGANIC_ANATOMY, {})[0])
        self.assertFalse(agent.validate_task_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(brush_type="UNKNOWN"))[0])
        self.assertFalse(agent.validate_task_input(TOOL_SCULPT_ORGANIC_ANATOMY, self.valid_params(preserve_topology=True, dynamic_topology=True))[0])

    def test_backward_compatible_delegation_from_sculpt_mesh_contract(self):
        """sculpt_mesh contract accepts action='sculpt_organic_anatomy' and 'organic_anatomy'."""
        snapshot = "sha256:" + "b" * 64
        valid_action1 = validate_sculpt_contract({
            "object_name": "DragonMesh",
            "expected_snapshot_id": snapshot,
            "action": "sculpt_organic_anatomy",
            "brush_type": "GRAB",
            "radius": 1.0,
        })
        self.assertEqual(valid_action1["action"], "sculpt_organic_anatomy")

        valid_action2 = validate_sculpt_contract({
            "object_name": "DragonMesh",
            "expected_snapshot_id": snapshot,
            "action": "organic_anatomy",
            "brush_type": "SMOOTH",
            "radius": 0.5,
        })
        self.assertEqual(valid_action2["action"], "organic_anatomy")

    def test_affected_region_parameter_validation(self):
        """affected_region bounds and center parameters validated."""
        valid = validate_tool_input(
            TOOL_SCULPT_ORGANIC_ANATOMY,
            self.valid_params(affected_region={"center": [0.0, 1.0, 2.0], "max_radius": 5.0}),
            trusted_approval=True,
        )
        self.assertEqual(valid["affected_region"]["center"], [0.0, 1.0, 2.0])
        self.assertEqual(valid["affected_region"]["max_radius"], 5.0)

    def test_brush_falloff_calculation(self):
        """Cubic smooth falloff (1 - (d/R)^2)^3 behaves smoothly from 1.0 at center to 0.0 at radius."""
        radius = 1.0
        # at d = 0, falloff = 1.0
        w0 = ((1.0 - (0.0 / radius) ** 2) ** 3.0)
        self.assertAlmostEqual(w0, 1.0)

        # at d = 0.5, falloff = (1 - 0.25)^3 = 0.75^3 = 0.421875
        w_half = ((1.0 - (0.5 / radius) ** 2) ** 3.0)
        self.assertAlmostEqual(w_half, 0.421875)

        # at d = 1.0, falloff = 0.0
        w1 = ((1.0 - (1.0 / radius) ** 2) ** 3.0)
        self.assertAlmostEqual(w1, 0.0)

    def test_backward_compatible_delegation_from_optimize_mesh_silhouette(self):
        """optimize_mesh_silhouette accepts brush_type for organic sculpting delegation."""
        valid_opt = validate_tool_input(
            TOOL_OPTIMIZE_MESH_SILHOUETTE,
            {
                "target_object": "DragonMesh",
                "reference_image_path": "C:/fake/dragon.png",
                "brush_type": "INFLATE",
                "radius": 0.8,
            },
            trusted_approval=True,
        )
        self.assertEqual(valid_opt["brush_type"], "INFLATE")
        self.assertEqual(valid_opt["radius"], 0.8)

    def test_all_five_brushes_execute_on_mock_mesh(self):
        """All 5 brushes (GRAB, INFLATE, SMOOTH, CLAY, DRAW) successfully mutate mock mesh geometry."""
        from types import SimpleNamespace

        for b_name in ("GRAB", "INFLATE", "SMOOTH", "CLAY", "DRAW"):
            # Construct a minimal mock Blender object
            verts = [
                SimpleNamespace(co=[-0.5, -0.5, 0.0], normal=[0.0, 0.0, 1.0]),
                SimpleNamespace(co=[0.5, -0.5, 0.0], normal=[0.0, 0.0, 1.0]),
                SimpleNamespace(co=[0.5, 0.5, 0.0], normal=[0.0, 0.0, 1.0]),
                SimpleNamespace(co=[-0.5, 0.5, 0.0], normal=[0.0, 0.0, 1.0]),
            ]
            edges = [
                SimpleNamespace(vertices=[0, 1]),
                SimpleNamespace(vertices=[1, 2]),
                SimpleNamespace(vertices=[2, 3]),
                SimpleNamespace(vertices=[3, 0]),
            ]
            polys = [SimpleNamespace(vertices=[0, 1, 2, 3])]
            mock_mesh = SimpleNamespace(
                vertices=verts,
                edges=edges,
                polygons=polys,
                update=lambda: None,
            )
            mock_obj = SimpleNamespace(
                name="MockDragon",
                type="MESH",
                data=mock_mesh,
                location=[0.0, 0.0, 0.0],
                rotation_euler=[0.0, 0.0, 0.0],
                scale=[1.0, 1.0, 1.0],
                dimensions=[1.0, 1.0, 0.01],
                library=None,
            )
            mock_bpy = SimpleNamespace(
                data=SimpleNamespace(objects={"MockDragon": mock_obj}, meshes=SimpleNamespace(remove=lambda m: None)),
                context=SimpleNamespace(
                    scene=SimpleNamespace(umcp_require_scene_mutation_approval=False),
                    view_layer=SimpleNamespace(update=lambda: None),
                ),
            )

            res = handle_sculpt_organic_anatomy(
                bpy_module=mock_bpy,
                params={
                    "target_object": "MockDragon",
                    "brush_type": b_name,
                    "radius": 2.0,
                    "strength": 0.5,
                    "max_displacement": 0.2,
                    "stroke_direction": [0.0, 0.0, 1.0],
                    "preserve_topology": True,
                },
            )
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["sculpt_status"], "SCULPTED")
            self.assertEqual(res["brush_type"], b_name)
            self.assertTrue(res["topology_preserved"])
            self.assertGreater(res["max_vertex_displacement"], 0.0)
            self.assertLessEqual(res["max_vertex_displacement"], 0.200001)


if __name__ == "__main__":
    unittest.main()
