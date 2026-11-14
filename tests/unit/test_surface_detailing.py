"""Unit tests for fine-scale anatomical surface detailing (TASK v0.1.58)."""
import math
import unittest
from types import SimpleNamespace
from typing import Dict, Any

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_DETAIL_SURFACE_FEATURES,
    TOOL_INSPECT_SURFACE_DETAIL,
    TOOL_OPTIMIZE_MESH_SILHOUETTE,
    validate_tool_input,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
)
from blender_addon.universal_mcp.bridge.handlers import (
    _LOCAL_TEST_TOOLS,
    ALL_HANDLERS,
    READ_ONLY_HANDLERS,
    handle_inspect_surface_detail,
    handle_detail_surface_features,
    handle_optimize_mesh_silhouette,
    handle_configure_semantic_landmarks,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    SUPPORTED_MODELING_TOOLS,
    MODELING_AGENT_ID,
    CAPABILITY_MODELING_SURFACE_DETAIL,
    CAPABILITY_MODELING_SURFACE_DETAIL_INSPECT,
    CAPABILITY_MODELING_OBJECT_OPS,
)
from shared.models.agent_contracts import AgentTask, AgentResult, TaskStatus
from shared.models.protocol_models import BridgeResponse


class MockMatrix:
    def __init__(self):
        self.rows = [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    def __getitem__(self, idx):
        return self.rows[idx]
    def __matmul__(self, other):
        return list(other)
    def inverted(self):
        return self
    def to_3x3(self):
        return self


class MockMeshObject:
    def __init__(self, name, data, matrix_world=None):
        self.name = name
        self.type = "MESH"
        self.data = data
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.matrix_world = matrix_world or MockMatrix()
        self.library = None
        self._props = {}
    def __getitem__(self, k):
        return self._props[k]
    def __setitem__(self, k, v):
        self._props[k] = v
    def get(self, k, default=None):
        return self._props.get(k, default)


def create_mock_sphere_mesh():
    # 3x3 grid / dome mesh for deterministic testing
    coords = [
        [-1.0, -1.0, 0.0], [0.0, -1.0, 0.2], [1.0, -1.0, 0.0],
        [-1.0,  0.0, 0.2], [0.0,  0.0, 0.5], [1.0,  0.0, 0.2],
        [-1.0,  1.0, 0.0], [0.0,  1.0, 0.2], [1.0,  1.0, 0.0],
    ]
    verts = [
        SimpleNamespace(co=list(c), normal=[0.0, 0.0, 1.0])
        for c in coords
    ]
    edges = [
        SimpleNamespace(vertices=[0, 1]), SimpleNamespace(vertices=[1, 2]),
        SimpleNamespace(vertices=[3, 4]), SimpleNamespace(vertices=[4, 5]),
        SimpleNamespace(vertices=[6, 7]), SimpleNamespace(vertices=[7, 8]),
        SimpleNamespace(vertices=[0, 3]), SimpleNamespace(vertices=[3, 6]),
        SimpleNamespace(vertices=[1, 4]), SimpleNamespace(vertices=[4, 7]),
        SimpleNamespace(vertices=[2, 5]), SimpleNamespace(vertices=[5, 8]),
    ]
    polys = [
        SimpleNamespace(vertices=[0, 1, 4, 3]),
        SimpleNamespace(vertices=[1, 2, 5, 4]),
        SimpleNamespace(vertices=[3, 4, 7, 6]),
        SimpleNamespace(vertices=[4, 5, 8, 7]),
    ]
    return SimpleNamespace(
        vertices=verts,
        edges=edges,
        polygons=polys,
        shape_keys=None,
        animation_data=None,
        update=lambda: None,
    )


class TestSurfaceDetailingContract(unittest.TestCase):
    """Tests schema definitions, permissions, and parameter sanitization."""

    def test_schema_registration_and_permissions(self):
        self.assertIn(TOOL_DETAIL_SURFACE_FEATURES, TOOL_DEFINITIONS)
        self.assertIn(TOOL_INSPECT_SURFACE_DETAIL, TOOL_DEFINITIONS)

        def_detail = TOOL_DEFINITIONS[TOOL_DETAIL_SURFACE_FEATURES]
        def_inspect = TOOL_DEFINITIONS[TOOL_INSPECT_SURFACE_DETAIL]

        self.assertEqual(def_detail["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(def_inspect["permission_tier"], PERMISSION_READ_ONLY)
        self.assertIn("detail_surface_features", _LOCAL_TEST_TOOLS)
        self.assertIn(TOOL_DETAIL_SURFACE_FEATURES, ALL_HANDLERS)
        self.assertIn(TOOL_INSPECT_SURFACE_DETAIL, ALL_HANDLERS)
        self.assertIn(TOOL_INSPECT_SURFACE_DETAIL, READ_ONLY_HANDLERS)

    def test_detail_validation_success(self):
        params = {
            "target_object": "DragonBlockout",
            "feature_type": "SCALES",
            "feature_scale": 0.15,
            "depth": 0.04,
            "strength": 0.8,
            "max_displacement": 0.05,
            "orientation": [0.0, 1.0, 0.0],
            "region_center": [0.0, 0.0, 0.5],
            "region_radius": 1.5,
            "falloff_type": "SMOOTH",
            "iterations": 2,
            "preserve_landmarks": True,
            "landmark_protection_radius": 0.3,
            "max_landmark_regression": 0.015,
            "max_vertex_count": 20000,
            "max_face_count": 20000,
        }
        res = validate_tool_input(TOOL_DETAIL_SURFACE_FEATURES, params, trusted_approval=True)
        self.assertEqual(res["target_object"], "DragonBlockout")
        self.assertEqual(res["feature_type"], "SCALES")
        self.assertAlmostEqual(res["feature_scale"], 0.15)
        self.assertAlmostEqual(res["depth"], 0.04)
        self.assertAlmostEqual(res["strength"], 0.8)
        self.assertEqual(res["orientation"], [0.0, 1.0, 0.0])
        self.assertEqual(res["iterations"], 2)
        self.assertTrue(res["preserve_landmarks"])

    def test_detail_validation_rejections(self):
        # Missing target_object
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_DETAIL_SURFACE_FEATURES, {"feature_type": "SCALES"}, trusted_approval=True)

        # Invalid feature type
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_DETAIL_SURFACE_FEATURES,
                {"target_object": "Dragon", "feature_type": "SPIKES"},
                trusted_approval=True,
            )

        # Invalid scale
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_DETAIL_SURFACE_FEATURES,
                {"target_object": "Dragon", "feature_type": "RIDGES", "feature_scale": 10.0},
                trusted_approval=True,
            )

        # Invalid depth
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_DETAIL_SURFACE_FEATURES,
                {"target_object": "Dragon", "feature_type": "RIDGES", "depth": 2.5},
                trusted_approval=True,
            )

        # Zero length orientation
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_DETAIL_SURFACE_FEATURES,
                {"target_object": "Dragon", "feature_type": "RIDGES", "orientation": [0.0, 0.0, 0.0]},
                trusted_approval=True,
            )

        # Out-of-bounds iterations
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_DETAIL_SURFACE_FEATURES,
                {"target_object": "Dragon", "feature_type": "FACETS", "iterations": 20},
                trusted_approval=True,
            )

    def test_untrusted_approval_defense(self):
        # approved=True from untrusted client must raise PermissionError fail-closed
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(
                TOOL_DETAIL_SURFACE_FEATURES,
                {"target_object": "Dragon", "feature_type": "SCALES", "approved": True},
                trusted_approval=False,
            )
        self.assertIn("Tool argument 'approved=True' is untrusted", str(ctx.exception))

    def test_inspect_surface_detail_validation(self):
        res = validate_tool_input(
            TOOL_INSPECT_SURFACE_DETAIL,
            {"target_object": "Dragon"},
            trusted_approval=False,
        )
        self.assertEqual(res["target_object"], "Dragon")
        self.assertTrue(res["include_roughness"])
        self.assertTrue(res["include_landmarks"])


class TestSurfaceDetailingHandlers(unittest.TestCase):
    """Tests execution of handlers on mock Blender meshes."""

    def setUp(self):
        self.mock_mesh = create_mock_sphere_mesh()
        self.mock_obj = MockMeshObject("TestMesh", self.mock_mesh)
        self.mock_bpy = SimpleNamespace(
            data=SimpleNamespace(objects={"TestMesh": self.mock_obj}),
            context=SimpleNamespace(scene=SimpleNamespace(camera=None, umcp_require_scene_mutation_approval=False)),
        )

    def test_inspect_surface_detail(self):
        res = handle_inspect_surface_detail(self.mock_bpy, {"target_object": "TestMesh"})
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["vertex_count"], 9)
        self.assertEqual(res["edge_count"], 12)
        self.assertEqual(res["face_count"], 4)
        self.assertEqual(res["roughness_metric"], "MEAN_LAPLACIAN_DEVIATION")
        self.assertGreater(res["surface_roughness"], 0.0)
        self.assertGreater(res["mean_edge_length"], 0.0)

    def test_detail_scales_application(self):
        init_rough = handle_inspect_surface_detail(self.mock_bpy, {"target_object": "TestMesh"})["surface_roughness"]

        res = handle_detail_surface_features(self.mock_bpy, {
            "target_object": "TestMesh",
            "feature_type": "SCALES",
            "feature_scale": 0.5,
            "depth": 0.08,
            "strength": 0.7,
            "max_displacement": 0.05,
            "iterations": 1,
            "preserve_landmarks": False,
        })
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["detailing_status"], "ACCEPTED")
        self.assertEqual(res["feature_type"], "SCALES")
        self.assertGreater(res["affected_vertices_count"], 0)
        self.assertGreater(res["max_vertex_displacement"], 0.0)
        self.assertLessEqual(res["max_vertex_displacement"], 0.05001)
        self.assertTrue(res["topology_preserved"])

        post_rough = res["final_surface_roughness"]
        self.assertNotEqual(init_rough, post_rough)

    def test_detail_feature_types(self):
        for ftype in ("RIDGES", "FACETS", "VEINS"):
            mesh = create_mock_sphere_mesh()
            obj = MockMeshObject("Mesh_" + ftype, mesh)
            bpy_mod = SimpleNamespace(
                data=SimpleNamespace(objects={"Mesh_" + ftype: obj}),
                context=SimpleNamespace(scene=SimpleNamespace(camera=None, umcp_require_scene_mutation_approval=False)),
            )
            res = handle_detail_surface_features(bpy_mod, {
                "target_object": "Mesh_" + ftype,
                "feature_type": ftype,
                "feature_scale": 0.3,
                "depth": 0.06,
                "orientation": [0.0, 1.0, 0.0],
                "iterations": 1,
                "preserve_landmarks": False,
            })
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["detailing_status"], "ACCEPTED")
            self.assertEqual(res["feature_type"], ftype)
            self.assertGreater(res["affected_vertices_count"], 0)

    def test_landmark_protection_damping(self):
        # Configure a landmark at vertex index 4 (center vertex [0, 0, 0.5])
        handle_configure_semantic_landmarks(self.mock_bpy, {
            "target_object": "TestMesh",
            "action": "SET",
            "landmarks": [{
                "name": "snout_tip",
                "vertex_index": 4,
                "position_3d": [0.0, 0.0, 0.5],
                "weight": 2.0,
            }],
        })

        initial_co_v4 = list(self.mock_mesh.vertices[4].co)

        # Apply detailing with landmark preservation enabled
        res = handle_detail_surface_features(self.mock_bpy, {
            "target_object": "TestMesh",
            "feature_type": "SCALES",
            "feature_scale": 0.4,
            "depth": 0.08,
            "preserve_landmarks": True,
            "landmark_protection_radius": 0.5,
        })
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["landmarks_preserved"])

        # Center vertex (landmark) must have exact zero displacement due to quadratic damping
        final_co_v4 = list(self.mock_mesh.vertices[4].co)
        disp_v4 = math.sqrt(sum((final_co_v4[k] - initial_co_v4[k])**2 for k in range(3)))
        self.assertAlmostEqual(disp_v4, 0.0, places=5)

    def test_precondition_limit_rejection(self):
        # Create a mesh with 120 vertices to trigger max_vertex_count=100 limit
        large_verts = [SimpleNamespace(co=[float(i), 0.0, 0.0], normal=[0.0, 0.0, 1.0]) for i in range(120)]
        large_mesh = SimpleNamespace(
            vertices=large_verts,
            edges=[SimpleNamespace(vertices=[i, i+1]) for i in range(119)],
            polygons=[SimpleNamespace(vertices=[0, 1, 2])],
            shape_keys=None,
            animation_data=None,
            update=lambda: None,
        )
        large_obj = MockMeshObject("LargeMesh", large_mesh)
        bpy_mod = SimpleNamespace(
            data=SimpleNamespace(objects={"LargeMesh": large_obj}),
            context=SimpleNamespace(scene=SimpleNamespace(camera=None, umcp_require_scene_mutation_approval=False)),
        )

        with self.assertRaises(ValueError) as ctx:
            handle_detail_surface_features(bpy_mod, {
                "target_object": "LargeMesh",
                "feature_type": "SCALES",
                "max_vertex_count": 100,  # target has 120 vertices
            })
        self.assertIn("Precondition limit exceeded", str(ctx.exception))

    def test_backward_compatible_delegation(self):
        # Delegation from optimize_mesh_silhouette via refinement_mode="SURFACE_DETAIL"
        res = handle_optimize_mesh_silhouette(self.mock_bpy, {
            "target_object": "TestMesh",
            "refinement_mode": "SURFACE_DETAIL",
            "feature_type": "RIDGES",
            "depth": 0.05,
            "preserve_landmarks": False,
        })
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["detailing_status"], "ACCEPTED")
        self.assertEqual(res["feature_type"], "RIDGES")


class TestSurfaceDetailingAgent(unittest.TestCase):
    """Tests ModelingAgent integration, task routing, and structured evidence."""

    def setUp(self):
        self.agent = ModelingAgent(version="0.1.58")

    def test_manifest_and_capabilities(self):
        manifest = self.agent.manifest
        self.assertGreaterEqual(len(manifest.capabilities), 30)
        cap_ids = [c.capability_id for c in manifest.capabilities]
        self.assertIn(CAPABILITY_MODELING_SURFACE_DETAIL, cap_ids)
        self.assertIn(CAPABILITY_MODELING_SURFACE_DETAIL_INSPECT, cap_ids)

    def test_can_handle_task(self):
        task_detail = AgentTask(
            task_id="task_detail_01",
            required_capability=CAPABILITY_MODELING_SURFACE_DETAIL,
            input_params={"target_object": "Dragon", "feature_type": "SCALES"},
        )
        self.assertTrue(self.agent.can_handle(task_detail))

        task_inspect = AgentTask(
            task_id="task_insp_01",
            required_capability=CAPABILITY_MODELING_SURFACE_DETAIL_INSPECT,
            input_params={"target_object": "Dragon"},
        )
        self.assertTrue(self.agent.can_handle(task_inspect))

    def test_execute_task_evidence_collection(self):
        class MockExecutor:
            def execute_tool(self, tool_name, params, **kwargs):
                if tool_name == TOOL_DETAIL_SURFACE_FEATURES:
                    return BridgeResponse.success({
                        "status": "SUCCESS",
                        "detailing_status": "ACCEPTED",
                        "target_object": params.get("target_object", "Dragon"),
                        "feature_type": "SCALES",
                        "surface_roughness_delta": 0.0125,
                        "max_vertex_displacement": 0.035,
                        "affected_vertices_count": 142,
                        "landmarks_preserved": True,
                    })
                elif tool_name == TOOL_INSPECT_SURFACE_DETAIL:
                    return BridgeResponse.success({
                        "status": "SUCCESS",
                        "target_object": params.get("target_object", "Dragon"),
                        "surface_roughness": 0.045,
                        "vertex_count": 482,
                        "face_count": 960,
                    })
                return BridgeResponse.error(f"Unknown tool: {tool_name}")

        executor = MockExecutor()

        # Execute detail task
        task = AgentTask(
            task_id="detail_dragon",
            required_capability=CAPABILITY_MODELING_SURFACE_DETAIL,
            input_params={"target_object": "Dragon", "feature_type": "SCALES"},
        )
        result: AgentResult = self.agent.execute_task(task, executor, trusted_approval=True)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        ev_refs = result.evidence_references
        self.assertIn("detailing_status:ACCEPTED", ev_refs)
        self.assertIn("feature_type:SCALES", ev_refs)
        self.assertIn("surface_roughness_delta:0.0125", ev_refs)
        self.assertIn("max_displacement:0.035", ev_refs)
        self.assertIn("affected_vertices_count:142", ev_refs)
        self.assertIn("landmarks_preserved:True", ev_refs)


if __name__ == "__main__":
    unittest.main()
