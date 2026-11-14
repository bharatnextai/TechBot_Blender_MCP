from tests.unit.modeling_approval_fixture import approved
"""
Unit tests for UV Mapping and Unwrap tools in Universal MCP (v0.1.18).
Validates:
1. Schema declarations and ToolRegistry discovery for uv_unwrap and uv_smart_project (and aliases).
2. Parameter validation, type bounds, and default sanitization in validate_tool_input.
3. Security gating: rejection of untrusted approved=True and enforcement of trusted approval.
4. Agent routing, manifest declarations, and capability handling in ModelingAgent.
5. Task execution evidence references generation.
6. Bridge handlers handle_uv_unwrap and handle_uv_smart_project with mock execution.
7. Structured modeling action execution via execute_blender_code.
"""

import unittest
from unittest.mock import MagicMock
import math

from shared.schemas.tool_schemas import (
    TOOL_UV_UNWRAP,
    TOOL_UV_SMART_PROJECT,
    TOOL_UNWRAP_MESH,
    TOOL_SMART_PROJECT,
    TOOL_SMART_UV_PROJECT,
    TOOL_UV_PROJECT,
    TOOL_DEFINITIONS,
    TOOL_EXECUTE_BLENDER_CODE,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.security.approval import ApprovalManager
from mcp_service.agents.modeling import (
    ModelingAgent,
    create_modeling_manifest,
    CAPABILITY_MODELING_UV,
    SUPPORTED_MODELING_TOOLS,
)
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.execution.blender_executor import BlenderExecutor
from blender_addon.universal_mcp.bridge.handlers import (
    ALL_HANDLERS,
    handle_uv_unwrap,
    handle_uv_smart_project,
    handle_execute_blender_code,
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
        self.data.uv_layers = MagicMock()
        self.material_slots = []

    def select_set(self, state: bool):
        pass


class MockBlenderContext:
    def __init__(self, objects: dict):
        self.scene = MagicMock()
        self.scene.objects = objects
        self.active_object = next(iter(objects.values())) if objects else None
        self.view_layer = MagicMock()
        self.view_layer.objects = MagicMock()
        self.view_layer.objects.active = self.active_object


class MockBpy:
    def __init__(self, objects: dict = None):
        self._objects = objects or {}
        self.data = MagicMock()
        self.data.objects = self._objects
        self.data.materials = {}
        self.context = MockBlenderContext(self._objects)
        self.ops = MagicMock()
        self.app = MagicMock()
        self.app.timers = MagicMock()


class TestUVMappingSchemasAndValidation(unittest.TestCase):
    """Tests schema declarations and validate_tool_input for uv_unwrap and uv_smart_project."""

    def test_schema_registration(self):
        self.assertIn(TOOL_UV_UNWRAP, TOOL_DEFINITIONS)
        self.assertIn(TOOL_UV_SMART_PROJECT, TOOL_DEFINITIONS)
        self.assertIn(TOOL_UNWRAP_MESH, TOOL_DEFINITIONS)
        self.assertIn(TOOL_SMART_PROJECT, TOOL_DEFINITIONS)
        self.assertIn(TOOL_SMART_UV_PROJECT, TOOL_DEFINITIONS)
        self.assertIn(TOOL_UV_PROJECT, TOOL_DEFINITIONS)

        unwrap_def = TOOL_DEFINITIONS[TOOL_UV_UNWRAP]
        self.assertEqual(unwrap_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertIn("method", unwrap_def["input_schema"]["properties"])
        self.assertIn("margin", unwrap_def["input_schema"]["properties"])
        self.assertIn("fill_holes", unwrap_def["input_schema"]["properties"])
        self.assertIn("correct_aspect", unwrap_def["input_schema"]["properties"])
        self.assertIn("uv_layer", unwrap_def["input_schema"]["properties"])
        self.assertIn("faces", unwrap_def["input_schema"]["properties"])

        smart_def = TOOL_DEFINITIONS[TOOL_UV_SMART_PROJECT]
        self.assertEqual(smart_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertIn("angle_limit", smart_def["input_schema"]["properties"])
        self.assertIn("island_margin", smart_def["input_schema"]["properties"])
        self.assertIn("area_weight", smart_def["input_schema"]["properties"])
        self.assertIn("scale_to_bounds", smart_def["input_schema"]["properties"])
        self.assertIn("correct_aspect", smart_def["input_schema"]["properties"])
        self.assertIn("uv_layer", smart_def["input_schema"]["properties"])
        self.assertIn("faces", smart_def["input_schema"]["properties"])

    def test_tool_registry_discovery(self):
        registry = ToolRegistry()
        self.assertTrue(registry.has_tool(TOOL_UV_UNWRAP))
        self.assertTrue(registry.has_tool(TOOL_UV_SMART_PROJECT))
        self.assertTrue(registry.has_tool(TOOL_UNWRAP_MESH))
        self.assertTrue(registry.has_tool(TOOL_SMART_PROJECT))

        names = [t.name for t in registry.get_mcp_tools()]
        self.assertIn(TOOL_UV_UNWRAP, names)
        self.assertIn(TOOL_UV_SMART_PROJECT, names)

    def test_unwrap_validation_valid(self):
        params = {
            "name": "Cube",
            "method": "CONFORMAL",
            "margin": 0.05,
            "fill_holes": False,
            "correct_aspect": False,
            "uv_layer": "LightmapUV",
            "faces": [0, 1, 2],
        }
        sanitized = validate_tool_input(TOOL_UV_UNWRAP, params, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Cube")
        self.assertEqual(sanitized["method"], "CONFORMAL")
        self.assertEqual(sanitized["margin"], 0.05)
        self.assertFalse(sanitized["fill_holes"])
        self.assertFalse(sanitized["correct_aspect"])
        self.assertEqual(sanitized["uv_layer"], "LightmapUV")
        self.assertEqual(sanitized["faces"], [0, 1, 2])

    def test_unwrap_validation_defaults(self):
        sanitized = validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube"}, trusted_approval=True)
        self.assertEqual(sanitized["method"], "ANGLE_BASED")
        self.assertEqual(sanitized["margin"], 0.001)
        self.assertTrue(sanitized["fill_holes"])
        self.assertTrue(sanitized["correct_aspect"])
        self.assertEqual(sanitized["uv_layer"], "UVMap")
        self.assertEqual(sanitized["faces"], "all")

    def test_unwrap_validation_empty_name(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": ""}, trusted_approval=True)

    def test_unwrap_validation_invalid_method(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "method": "SPHERICAL"}, trusted_approval=True)

    def test_unwrap_validation_invalid_margin(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "margin": -0.1}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "margin": 1.5}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "margin": "wide"}, trusted_approval=True)

    def test_unwrap_validation_invalid_faces(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "faces": "top"}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "faces": [-1, 0]}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "faces": ["zero"]}, trusted_approval=True)

    def test_smart_project_validation_valid(self):
        params = {
            "name": "Cylinder",
            "angle_limit": 45.0,
            "island_margin": 0.02,
            "area_weight": 0.5,
            "correct_aspect": True,
            "scale_to_bounds": True,
            "uv_layer": "UVMap",
            "faces": "selected",
        }
        sanitized = validate_tool_input(TOOL_UV_SMART_PROJECT, params, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Cylinder")
        self.assertEqual(sanitized["angle_limit"], 45.0)
        self.assertEqual(sanitized["island_margin"], 0.02)
        self.assertEqual(sanitized["area_weight"], 0.5)
        self.assertTrue(sanitized["scale_to_bounds"])
        self.assertEqual(sanitized["faces"], "selected")

    def test_smart_project_validation_defaults(self):
        sanitized = validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube"}, trusted_approval=True)
        self.assertEqual(sanitized["angle_limit"], 66.0)
        self.assertEqual(sanitized["island_margin"], 0.0)
        self.assertEqual(sanitized["area_weight"], 0.0)
        self.assertTrue(sanitized["correct_aspect"])
        self.assertFalse(sanitized["scale_to_bounds"])
        self.assertEqual(sanitized["uv_layer"], "UVMap")
        self.assertEqual(sanitized["faces"], "all")

    def test_smart_project_validation_invalid_angles(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "angle_limit": 0.5}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "angle_limit": 90.0}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "angle_limit": "steep"}, trusted_approval=True)

    def test_smart_project_validation_invalid_margins_and_weights(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "island_margin": -0.01}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "island_margin": 1.2}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "area_weight": -0.5}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "area_weight": 2.0}, trusted_approval=True)


class TestUVMappingSecurityAndApproval(unittest.TestCase):
    """Tests human approval requirements and model-supplied approval flag rejection."""

    def setUp(self):
        self.approval_mgr = ApprovalManager()

    def test_approval_manager_requires_approval(self):
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_UV_UNWRAP))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_UV_SMART_PROJECT))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_UNWRAP_MESH))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_SMART_PROJECT))

    def test_rejection_of_model_supplied_approved_flag(self):
        # Untrusted approved=True in arguments must be rejected
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube", "approved": True}, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube", "approved": True}, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize", str(ctx.exception))

    def test_rejection_of_unauthorized_call(self):
        # Missing trusted approval must raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_UV_UNWRAP, {"name": "Cube"}, trusted_approval=False)
        self.assertIn("requires explicit user approval", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_UV_SMART_PROJECT, {"name": "Cube"}, trusted_approval=False)
        self.assertIn("requires explicit user approval", str(ctx.exception))


class MockExecutor(BlenderExecutor):
    def __init__(self):
        self.invocations = []
        self.should_fail = False
        self.mock_response_data = {}

    def is_connected(self) -> bool:
        return True

    def execute_tool(self, tool_name: str, arguments: dict = None, trusted_approval: bool = None) -> BridgeResponse:
        self.invocations.append((tool_name, arguments, trusted_approval))
        if self.should_fail:
            return BridgeResponse.error("Simulated UV execution failure")
        return BridgeResponse.success(self.mock_response_data or {"action": tool_name, "success": True})


class TestModelingAgentUVRoutingAndExecution(unittest.TestCase):
    """Tests ModelingAgent integration for UV unwrap and projection."""

    def setUp(self):
        self.agent = ModelingAgent(version="0.1.18")
        self.executor = MockExecutor()

    def test_manifest_capabilities(self):
        manifest = self.agent.manifest
        caps = {c.capability_id: c for c in manifest.capabilities}
        self.assertIn(CAPABILITY_MODELING_UV, caps)
        uv_cap = caps[CAPABILITY_MODELING_UV]
        self.assertIn(TOOL_UV_UNWRAP, uv_cap.supported_task_types)
        self.assertIn(TOOL_UV_SMART_PROJECT, uv_cap.supported_task_types)
        self.assertIn(TOOL_UNWRAP_MESH, uv_cap.supported_task_types)
        self.assertIn(TOOL_SMART_PROJECT, uv_cap.supported_task_types)
        self.assertIn(TOOL_UV_UNWRAP, manifest.input_schemas)
        self.assertIn(TOOL_UV_SMART_PROJECT, manifest.input_schemas)

    def test_can_handle(self):
        task1 = AgentTask(task_id="t1", required_capability=CAPABILITY_MODELING_UV, task_type=TOOL_UV_UNWRAP)
        task2 = AgentTask(task_id="t2", required_capability=CAPABILITY_MODELING_UV, task_type=TOOL_UV_SMART_PROJECT)
        task3 = AgentTask(task_id="t3", required_capability=CAPABILITY_MODELING_UV, task_type="invalid_tool")
        self.assertTrue(self.agent.can_handle(task1))
        self.assertTrue(self.agent.can_handle(task2))
        self.assertFalse(self.agent.can_handle(task3))

    def test_rejection_of_untrusted_approved_in_agent(self):
        task = AgentTask(
            task_id="t-agent-untrust",
            required_capability=CAPABILITY_MODELING_UV,
            task_type=TOOL_UV_UNWRAP,
            input_params={"name": "Cube", "approved": True},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=False)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.verification.observed_results["error_code"], "PERMISSION_DENIED")
        self.assertIn("untrusted and cannot authorize", res.errors[0])

    def test_approved_unwrap_execution(self):
        self.executor.mock_response_data = {
            "name": "Cube",
            "operation": "uv_unwrap",
            "uv_layer": "UVMap",
            "faces_unwrapped": 6,
            "uv_bounds": [0.0, 0.0, 1.0, 1.0],
            "action": "uv_unwrap",
        }
        task = AgentTask(
            task_id="t-uv-unw",
            required_capability=CAPABILITY_MODELING_UV,
            task_type=TOOL_UV_UNWRAP,
            input_params={"name": "Cube", "margin": 0.005},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertIn("unwrapped_mesh:Cube", res.evidence_references)
        self.assertIn("faces_unwrapped:6", res.evidence_references)
        self.assertIn("uv_layer:UVMap", res.evidence_references)

    def test_approved_smart_project_execution(self):
        self.executor.mock_response_data = {
            "name": "Cube",
            "operation": "uv_smart_project",
            "uv_layer": "UVMap",
            "faces_projected": 6,
            "uv_bounds": [0.001, 0.001, 0.999, 0.999],
            "angle_limit": 66.0,
            "action": "uv_smart_project",
        }
        task = AgentTask(
            task_id="t-uv-smart",
            required_capability=CAPABILITY_MODELING_UV,
            task_type=TOOL_UV_SMART_PROJECT,
            input_params={"name": "Cube", "angle_limit": 66.0},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertIn("projected_mesh:Cube", res.evidence_references)
        self.assertIn("faces_projected:6", res.evidence_references)
        self.assertIn("uv_layer:UVMap", res.evidence_references)


class TestBridgeHandlersExecution(unittest.TestCase):
    """Tests handle_uv_unwrap and handle_uv_smart_project with mock Blender environment."""

    def setUp(self):
        self.cube = MockBlenderObject("Cube", obj_type="MESH", face_count=6)
        self.camera = MockBlenderObject("Camera", obj_type="CAMERA", face_count=0)
        self.empty_mesh = MockBlenderObject("EmptyMesh", obj_type="MESH", face_count=0)
        self.bpy = MockBpy({"Cube": self.cube, "Camera": self.camera, "EmptyMesh": self.empty_mesh})

    def test_handlers_registered_in_all_handlers(self):
        self.assertIn("uv_unwrap", ALL_HANDLERS)
        self.assertIn("unwrap_mesh", ALL_HANDLERS)
        self.assertIn("uv_smart_project", ALL_HANDLERS)
        self.assertIn("smart_project", ALL_HANDLERS)
        self.assertIn("smart_uv_project", ALL_HANDLERS)
        self.assertIn("uv_project", ALL_HANDLERS)

    def test_unauthorized_unwrap_denied(self):
        with self.assertRaises(PermissionError):
            handle_uv_unwrap(self.bpy, {"name": "Cube"})

    def test_unauthorized_smart_project_denied(self):
        with self.assertRaises(PermissionError):
            handle_uv_smart_project(self.bpy, {"name": "Cube"})

    def test_nonexistent_object_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            handle_uv_unwrap(self.bpy, {"name": "NonExistentObject", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("not found in scene", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_uv_smart_project(self.bpy, {"name": "NonExistentObject", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("not found in scene", str(ctx.exception))

    def test_non_mesh_object_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            handle_uv_unwrap(self.bpy, {"name": "Camera", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("not of type 'MESH'", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_uv_smart_project(self.bpy, {"name": "Camera", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("not of type 'MESH'", str(ctx.exception))

    def test_empty_mesh_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            handle_uv_unwrap(self.bpy, {"name": "EmptyMesh", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("0 faces", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_uv_smart_project(self.bpy, {"name": "EmptyMesh", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("0 faces", str(ctx.exception))

    def test_empty_face_selection_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            handle_uv_unwrap(self.bpy, {"name": "Cube", "faces": [], "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("No faces specified", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_uv_smart_project(self.bpy, {"name": "Cube", "faces": [], "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("No faces specified", str(ctx.exception))

    def test_mock_uv_unwrap_success(self):
        params = {
            "name": "Cube",
            "method": "ANGLE_BASED",
            "margin": 0.002,
            "faces": "all",
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_uv_unwrap(self.bpy, params)
        self.assertEqual(res["name"], "Cube")
        self.assertEqual(res["operation"], "uv_unwrap")
        self.assertEqual(res["method"], "ANGLE_BASED")
        self.assertEqual(res["margin"], 0.002)
        self.assertEqual(res["faces_unwrapped"], 6)
        self.assertEqual(res["action"], "uv_unwrap")

    def test_mock_uv_smart_project_success(self):
        params = {
            "name": "Cube",
            "angle_limit": 60.0,
            "island_margin": 0.01,
            "area_weight": 0.0,
            "faces": [0, 1],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_uv_smart_project(self.bpy, params)
        self.assertEqual(res["name"], "Cube")
        self.assertEqual(res["operation"], "uv_smart_project")
        self.assertEqual(res["angle_limit"], 60.0)
        self.assertEqual(res["faces_projected"], 2)
        self.assertEqual(res["action"], "uv_smart_project")

    def test_structured_modeling_uv_operations(self):
        params = {
            "operations": [
                {"action": "uv_smart_project", "target": "Cube", "params": {"angle_limit": 66.0}},
                {"action": "uv_unwrap", "target": "Cube", "params": {"method": "CONFORMAL", "margin": 0.01}},
            ],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_execute_blender_code(self.bpy, approved('execute_blender_code',params))
        self.assertTrue(res.get("executed", False))
        ops = res.get("operations", [])
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]["action"], "uv_smart_project")
        self.assertEqual(ops[0]["target"], "Cube")
        self.assertEqual(ops[1]["action"], "uv_unwrap")
        self.assertEqual(ops[1]["target"], "Cube")


if __name__ == "__main__":
    unittest.main()
