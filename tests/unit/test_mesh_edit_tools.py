"""
Unit tests for Edit-Mode Mesh Extrusion and Inset tools in Universal MCP (v0.1.17).
Covers:
1. Schema declarations and ToolRegistry discovery for extrude_mesh and inset_mesh.
2. Parameter validation in validate_tool_input (empty names, invalid distances, negative thickness, bad directions, invalid faces).
3. Permission tier and human-approval enforcement (untrusted model flags rejected, approval required).
4. Agent manifest and capability routing via CapabilityRouter.
5. ModelingAgent task handling, input validation, and execution verification.
6. Bridge handlers handle_extrude_mesh and handle_inset_mesh with mock execution.
"""

import unittest
from typing import Dict, Any, Optional, List
from unittest.mock import MagicMock, patch

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    TaskStatus,
    AgentResult,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_EXTRUDE_MESH,
    TOOL_INSET_MESH,
    TOOL_EXTRUDE_FACES,
    TOOL_INSET_FACES,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.security.approval import ApprovalManager
from mcp_service.agents.modeling import (
    ModelingAgent,
    create_modeling_manifest,
    MODELING_AGENT_ID,
    CAPABILITY_MODELING_EDIT,
    SUPPORTED_MODELING_TOOLS,
)
from mcp_service.agents.registry import AgentRegistry, create_default_registry
from mcp_service.agents.router import CapabilityRouter
from blender_addon.universal_mcp.bridge.handlers import (
    handle_extrude_mesh,
    handle_inset_mesh,
    handle_execute_blender_code,
    ALL_HANDLERS,
)


class MockBlenderObject:
    def __init__(self, name: str, obj_type: str = "MESH", face_count: int = 6):
        self.name = name
        self.type = obj_type
        self.mode = "OBJECT"
        self.data = MagicMock()
        # Mock polygons/faces
        self.data.polygons = [MagicMock() for _ in range(face_count)]
        self.data.vertices = [MagicMock() for _ in range(face_count * 2)]
        self.data.edges = [MagicMock() for _ in range(face_count * 3)]

    def select_set(self, state: bool):
        pass


class MockBlenderContext:
    def __init__(self, objects: Dict[str, Any]):
        self.scene = MagicMock()
        self.scene.objects = objects
        self.active_object = next(iter(objects.values())) if objects else None
        self.view_layer = MagicMock()
        self.view_layer.objects = MagicMock()
        self.view_layer.objects.active = self.active_object


class MockBpy:
    def __init__(self, objects: Optional[Dict[str, Any]] = None):
        self._objects = objects or {}
        self.data = MagicMock()
        self.data.objects = self._objects
        self.context = MockBlenderContext(self._objects)
        self.ops = MagicMock()
        self.app = MagicMock()
        self.app.timers = MagicMock()


class TestMeshEditSchemasAndValidation(unittest.TestCase):
    """Tests schema declarations and validate_tool_input for extrude_mesh and inset_mesh."""

    def test_tool_definitions_contain_tools(self):
        self.assertIn(TOOL_EXTRUDE_MESH, TOOL_DEFINITIONS)
        self.assertIn(TOOL_INSET_MESH, TOOL_DEFINITIONS)
        self.assertIn(TOOL_EXTRUDE_FACES, TOOL_DEFINITIONS)
        self.assertIn(TOOL_INSET_FACES, TOOL_DEFINITIONS)

        ext_def = TOOL_DEFINITIONS[TOOL_EXTRUDE_MESH]
        self.assertEqual(ext_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertIn("name", ext_def["input_schema"]["properties"])
        self.assertIn("distance", ext_def["input_schema"]["properties"])
        self.assertIn("direction", ext_def["input_schema"]["properties"])
        self.assertIn("faces", ext_def["input_schema"]["properties"])
        self.assertIn("individual", ext_def["input_schema"]["properties"])

        ins_def = TOOL_DEFINITIONS[TOOL_INSET_MESH]
        self.assertEqual(ins_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertIn("name", ins_def["input_schema"]["properties"])
        self.assertIn("thickness", ins_def["input_schema"]["properties"])
        self.assertIn("depth", ins_def["input_schema"]["properties"])
        self.assertIn("faces", ins_def["input_schema"]["properties"])
        self.assertIn("use_individual", ins_def["input_schema"]["properties"])

    def test_tool_registry_discovers_mesh_edit_tools(self):
        registry = ToolRegistry()
        self.assertTrue(registry.has_tool(TOOL_EXTRUDE_MESH))
        self.assertTrue(registry.has_tool(TOOL_INSET_MESH))
        mcp_tools = registry.get_mcp_tools()
        names = [t.name for t in mcp_tools]
        self.assertIn(TOOL_EXTRUDE_MESH, names)
        self.assertIn(TOOL_INSET_MESH, names)

    def test_extrude_validation_valid(self):
        params = {"name": "Cube", "distance": 2.5, "direction": [0.0, 0.0, 1.0], "faces": [0, 1], "individual": True, "expected_snapshot_id": "sha256:"+"a"*64}
        sanitized = validate_tool_input(TOOL_EXTRUDE_MESH, params, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Cube")
        self.assertEqual(sanitized["distance"], 2.5)
        self.assertEqual(sanitized["direction"], [0.0, 0.0, 1.0])
        self.assertEqual(sanitized["faces"], [0, 1])
        self.assertTrue(sanitized["individual"])
        self.assertTrue(sanitized["trusted_approval"])

    def test_extrude_validation_defaults(self):
        sanitized = validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube"}, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Cube")
        self.assertEqual(sanitized["distance"], 1.0)
        self.assertEqual(sanitized["faces"], "selected")
        self.assertFalse(sanitized["individual"])

    def test_extrude_validation_empty_name(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": ""}, trusted_approval=True)

    def test_extrude_validation_invalid_distance(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube", "distance": "far"}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube", "distance": True}, trusted_approval=True)

    def test_extrude_validation_invalid_direction(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube", "direction": [1, 2]}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube", "direction": "up"}, trusted_approval=True)

    def test_extrude_validation_invalid_faces(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube", "faces": "invalid_spec"}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube", "faces": [-1, 2]}, trusted_approval=True)

    def test_inset_validation_valid(self):
        params = {"name": "Cube", "thickness": 0.2, "depth": 0.05, "faces": "all", "use_individual": True}
        sanitized = validate_tool_input(TOOL_INSET_MESH, params, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Cube")
        self.assertEqual(sanitized["thickness"], 0.2)
        self.assertEqual(sanitized["depth"], 0.05)
        self.assertEqual(sanitized["faces"], "all")
        self.assertTrue(sanitized["use_individual"])

    def test_inset_validation_defaults(self):
        sanitized = validate_tool_input(TOOL_INSET_MESH, {"name": "Cube"}, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Cube")
        self.assertEqual(sanitized["thickness"], 0.1)
        self.assertEqual(sanitized["depth"], 0.0)
        self.assertEqual(sanitized["faces"], "selected")
        self.assertFalse(sanitized["use_individual"])

    def test_inset_validation_negative_thickness(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_INSET_MESH, {"name": "Cube", "thickness": -0.5}, trusted_approval=True)

    def test_inset_validation_invalid_depth(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_INSET_MESH, {"name": "Cube", "depth": "deep"}, trusted_approval=True)


class TestMeshEditApprovalEnforcement(unittest.TestCase):
    """Tests approval enforcement for mesh edit tools."""

    def setUp(self):
        self.approval_mgr = ApprovalManager()

    def test_requires_approval(self):
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_EXTRUDE_MESH))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_INSET_MESH))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_EXTRUDE_FACES))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_INSET_FACES))

    def test_untrusted_approved_flag_rejected(self):
        # validate_tool_input must reject approved=True without trusted approval
        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube", "approved": True}, trusted_approval=False)

        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_INSET_MESH, {"name": "Cube", "approved": True}, trusted_approval=False)

        # ApprovalManager must reject model-supplied approved=True
        decision = self.approval_mgr.verify_approval(TOOL_EXTRUDE_MESH, {"name": "Cube", "approved": True})
        self.assertFalse(decision[0])
        self.assertIn("untrusted", decision[1].lower())

    def test_missing_approval_requires_authorization(self):
        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_EXTRUDE_MESH, {"name": "Cube"}, trusted_approval=False)


class TestMeshEditAgentRouting(unittest.TestCase):
    """Tests agent manifest and routing for mesh extrusion and inset."""

    def setUp(self):
        self.registry = create_default_registry()
        self.router = CapabilityRouter(self.registry)
        self.agent_manifest = self.registry.get_agent(MODELING_AGENT_ID)
        self.agent = ModelingAgent()

    def test_modeling_agent_manifest_declares_edit_capability(self):
        manifest = self.agent_manifest
        caps = {c.capability_id: c for c in manifest.capabilities}
        self.assertIn(CAPABILITY_MODELING_EDIT, caps)
        edit_cap = caps[CAPABILITY_MODELING_EDIT]
        self.assertIn(TOOL_EXTRUDE_MESH, edit_cap.supported_task_types)
        self.assertIn(TOOL_INSET_MESH, edit_cap.supported_task_types)
        self.assertIn(TOOL_EXTRUDE_MESH, manifest.input_schemas)
        self.assertIn(TOOL_INSET_MESH, manifest.input_schemas)

    def test_router_routes_by_capability_id(self):
        task = AgentTask(
            task_id="t-extrude-01",
            required_capability=CAPABILITY_MODELING_EDIT,
            task_type=TOOL_EXTRUDE_MESH,
            input_params={"name": "Cube", "distance": 1.0},
        )
        res = self.router.route(task)
        self.assertTrue(res.success)
        self.assertEqual(res.agent.agent_id, MODELING_AGENT_ID)

    def test_router_routes_by_task_type(self):
        task = AgentTask(
            task_id="t-inset-01",
            required_capability="",
            task_type=TOOL_INSET_MESH,
            input_params={"name": "Cube", "thickness": 0.2},
        )
        cap = self.registry.find_capability_by_task_type(TOOL_INSET_MESH)
        self.assertIsNotNone(cap)
        self.assertEqual(cap.capability_id, CAPABILITY_MODELING_EDIT)

    def test_modeling_agent_can_handle(self):
        task1 = AgentTask(task_id="t1", required_capability=CAPABILITY_MODELING_EDIT, task_type=TOOL_EXTRUDE_MESH)
        task2 = AgentTask(task_id="t2", required_capability=CAPABILITY_MODELING_EDIT, task_type=TOOL_INSET_MESH)
        self.assertTrue(self.agent.can_handle(task1))
        self.assertTrue(self.agent.can_handle(task2))


class TestModelingAgentExecution(unittest.TestCase):
    """Tests ModelingAgent task execution and verification for mesh edit operations."""

    def setUp(self):
        self.agent = ModelingAgent(version="0.1.17")
        self.executor = MagicMock()

    def test_untrusted_approved_rejected_in_execute_task(self):
        task = AgentTask(
            task_id="t-ext-deny",
            required_capability=CAPABILITY_MODELING_EDIT,
            task_type=TOOL_EXTRUDE_MESH,
            input_params={"name": "Cube", "approved": True},
        )
        res = self.agent.execute_task(task, self.executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("untrusted", res.errors[0].lower())

    def test_missing_trusted_approval_awaits_approval(self):
        task = AgentTask(
            task_id="t-ext-await",
            required_capability=CAPABILITY_MODELING_EDIT,
            task_type=TOOL_EXTRUDE_MESH,
            input_params={"name": "Cube"},
        )
        self.executor.execute_tool.return_value = BridgeResponse.error(
            "Approval required: Scene mutation 'extrude_mesh' requires explicit user approval through a trusted approval mechanism."
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=None)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)

    def test_approved_extrude_execution(self):
        task = AgentTask(
            task_id="t-ext-exec",
            required_capability=CAPABILITY_MODELING_EDIT,
            task_type=TOOL_EXTRUDE_MESH,
            input_params={"name": "Cube", "distance": 1.5},
        )
        self.executor.execute_tool.return_value = BridgeResponse.success({
            "name": "Cube",
            "operation": "extrude",
            "distance": 1.5,
            "faces_extruded": 1,
            "new_face_count": 11,"new_vertex_count":12,"new_edge_count":20,
            "verified":True,"snapshot_id":"sha256:"+"a"*64,
            "action": "extrude_mesh",
        })
        executed=self.executor.execute_tool.return_value
        self.executor.execute_tool.side_effect=[executed,BridgeResponse.success({"snapshot_id":"sha256:"+"a"*64,
            "vertex_count":12,"edge_count":20,"polygon_count":executed.result["new_face_count"]})]

        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertIn("extruded_mesh:Cube", res.evidence_references)
        self.assertIn("faces_extruded:1", res.evidence_references)
        self.assertIn("new_face_count:11", res.evidence_references)

    def test_approved_inset_execution(self):
        task = AgentTask(
            task_id="t-ins-exec",
            required_capability=CAPABILITY_MODELING_EDIT,
            task_type=TOOL_INSET_MESH,
            input_params={"name": "Cube", "thickness": 0.2},
        )
        self.executor.execute_tool.return_value = BridgeResponse.success({
            "name": "Cube",
            "operation": "inset",
            "thickness": 0.2,
            "faces_inset": 1,
            "new_face_count": 15,"new_vertex_count":12,"new_edge_count":20,
            "verified":True,"snapshot_id":"sha256:"+"a"*64,
            "action": "inset_mesh",
        })
        executed=self.executor.execute_tool.return_value
        self.executor.execute_tool.side_effect=[executed,BridgeResponse.success({"snapshot_id":"sha256:"+"a"*64,
            "vertex_count":12,"edge_count":20,"polygon_count":executed.result["new_face_count"]})]

        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertIn("inset_mesh:Cube", res.evidence_references)
        self.assertIn("faces_inset:1", res.evidence_references)


class TestBridgeHandlersExecution(unittest.TestCase):
    """Tests handle_extrude_mesh and handle_inset_mesh with mock Blender environment."""

    def setUp(self):
        self.cube = MockBlenderObject("Cube", obj_type="MESH", face_count=6)
        self.camera = MockBlenderObject("Camera", obj_type="CAMERA", face_count=0)
        self.bpy = MockBpy({"Cube": self.cube, "Camera": self.camera})

    def approved(self,tool,params):
        from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
        params={k:v for k,v in params.items() if k not in ("trusted_approval","_trusted_test_override")}
        registry=get_approval_registry();req=registry.create_request(tool,params)
        ok,token=registry.resolve_request(req.request_id,"approved");self.assertTrue(ok)
        return {**params,"request_id":req.request_id,"approval_token":token}

    def test_handlers_registered_in_all_handlers(self):
        self.assertIn("extrude_mesh", ALL_HANDLERS)
        self.assertIn("extrude_faces", ALL_HANDLERS)
        self.assertIn("inset_mesh", ALL_HANDLERS)
        self.assertIn("inset_faces", ALL_HANDLERS)

    def test_unauthorized_extrude_denied(self):
        with self.assertRaises(PermissionError):
            handle_extrude_mesh(self.bpy, {"name": "Cube", "distance": 1.0})

    def test_unauthorized_inset_denied(self):
        with self.assertRaises(PermissionError):
            handle_inset_mesh(self.bpy, {"name": "Cube", "thickness": 0.1})

    def test_nonexistent_object_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            handle_extrude_mesh(self.bpy, self.approved("extrude_mesh", {"name": "NonExistentObject"}))
        self.assertIn("not found in scene", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_inset_mesh(self.bpy, self.approved("inset_mesh", {"name": "NonExistentObject"}))
        self.assertIn("not found in scene", str(ctx.exception))

    def test_non_mesh_object_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            handle_extrude_mesh(self.bpy, self.approved("extrude_mesh", {"name": "Camera"}))
        self.assertIn("not of type 'MESH'", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_inset_mesh(self.bpy, self.approved("inset_mesh", {"name": "Camera"}))
        self.assertIn("not of type 'MESH'", str(ctx.exception))

    def test_missing_bmesh_cannot_report_extrude_success(self):
        self.cube.data.shape_keys=None
        params=self.approved("extrude_mesh",{"name":"Cube","distance":1.0,"faces":"all"})
        with patch("blender_addon.universal_mcp.bridge.mesh_edit._snapshot",return_value={"snapshot_id":"sha256:"+"a"*64}), patch.dict("sys.modules",{"bmesh":None}):
            with self.assertRaises(ModuleNotFoundError):handle_extrude_mesh(self.bpy,params)
        self.assertEqual(self.bpy.ops.mock_calls,[])

    def test_missing_bmesh_cannot_report_inset_success(self):
        self.cube.data.shape_keys=None
        params=self.approved("inset_mesh",{"name":"Cube","thickness":.2,"faces":"all"})
        with patch("blender_addon.universal_mcp.bridge.mesh_edit._snapshot",return_value={"snapshot_id":"sha256:"+"a"*64}), patch.dict("sys.modules",{"bmesh":None}):
            with self.assertRaises(ModuleNotFoundError):handle_inset_mesh(self.bpy,params)
        self.assertEqual(self.bpy.ops.mock_calls,[])

    def test_nonatomic_structured_topology_batch_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError,"atomic rollback"):
            handle_execute_blender_code(self.bpy,{"operations":[{"action":"extrude","target":"Cube","params":{"distance":1.2}}]})
        self.assertEqual(self.bpy.ops.mock_calls,[])


if __name__ == "__main__":
    unittest.main()
