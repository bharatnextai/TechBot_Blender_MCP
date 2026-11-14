"""
Unit and Integration Tests for TASK-UMCP-0017 (Phase 4):
Modeling & Geometry Agent with Verified Recovery.

Validates:
- Manifest structure and verified capability registration for modeling.primitive,
  modeling.transform, and modeling.execution.
- Routing through Agent Manager, AgentRegistry, and CapabilityRouter.
- Pre-execution validation of task inputs and constraints (names, types, bounds).
- Rejection of unsupported primitive types (torus, cone, suzanne) and unsupported
  mesh operations (extrude, inset, bevel, boolean, geometry_nodes).
- Static AST security validation of modeling scripts (blocking eval, exec, import, file access).
- Human approval gating: rejection of model-supplied approved=True, parameter hash binding,
  and single-use token lifecycle.
- Transaction boundaries: distinguishing undo markers, committed mutations, detected failures,
  and verified rollback recovery.
- Dispatcher integration and session tracking.
"""

import unittest
from typing import Dict, Any, Optional, List

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
    VerificationResult,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_EXECUTE_BLENDER_CODE,
    TOOL_DEFINITIONS,
    ALLOWED_MODELING_ACTIONS,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    create_modeling_manifest,
    MODELING_AGENT_ID,
    CAPABILITY_MODELING_PRIMITIVE,
    CAPABILITY_MODELING_TRANSFORM,
    CAPABILITY_MODELING_EXECUTION,
    CAPABILITY_MODELING_EDIT,
    CAPABILITY_MODELING_UV,
    CAPABILITY_MODELING_KEYFRAME,
    CAPABILITY_MODELING_GEONODES,
    CAPABILITY_MODELING_ASSET_IO,
    CAPABILITY_MODELING_OBJECT_OPS,
    SUPPORTED_MODELING_TOOLS,
    ALLOWED_PRIMITIVES,
)
from mcp_service.agents.registry import AgentRegistry, create_default_registry
from mcp_service.agents.manager import AgentManager
from mcp_service.agents.session_coordinator import SessionCoordinator
from mcp_service.agents.dispatcher import AgentDispatcher, DispatchResult
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.security.approval import ApprovalManager


class MockModelingExecutor(BlenderExecutor):
    """
    Mock BlenderExecutor simulating Blender main-thread execution with
    approval checks and transactional undo rollback tracking.
    """

    def __init__(self):
        self.invocations: List[tuple] = []
        self.scene_objects = {"Cube": {"type": "MESH", "location": [0.0, 0.0, 0.0]}}
        self.approval_manager = ApprovalManager()
        self.undo_stack: List[str] = []
        self.should_fail = False
        self.failure_message = "Simulated Blender execution failure"
        self.rollback_executed = False

    def is_connected(self) -> bool:
        return True

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        trusted_approval: Optional[bool] = None,
    ) -> BridgeResponse:
        self.invocations.append((tool_name, arguments, trusted_approval))
        args = dict(arguments or {})

        # 1. Approval Verification
        if self.approval_manager.requires_approval(tool_name):
            if trusted_approval is False or args.get("approved") is True:
                return BridgeResponse.error(
                    f"Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation '{tool_name}'."
                )
            if trusted_approval is not True:
                has_creds = bool(args.get("request_id") and args.get("approval_token"))
                provider = getattr(self.approval_manager, "_provider", None)
                if not has_creds and not provider:
                    return BridgeResponse.error(
                        f"Approval required: Scene mutation '{tool_name}' requires human approval in Blender."
                    )
                if provider:
                    decision = provider(tool_name, args)
                    if not decision:
                        return BridgeResponse.error(f"Approval denied: Human operator denied '{tool_name}'.")

        # 2. Simulated Failure with Undo Rollback
        if self.should_fail:
            self.undo_stack.append("undo_push")
            # Trigger failure and perform simulated rollback
            self.undo_stack.append("undo")
            self.rollback_executed = True
            return BridgeResponse.error(
                f"Modeling execution failed and scene changes were rolled back: {self.failure_message}"
            )

        # 3. Simulate Successful Operations
        if tool_name == TOOL_CREATE_PRIMITIVE:
            name = args.get("name", "NewObject")
            prim_type = args.get("primitive_type", "cube")
            loc = args.get("location", [0.0, 0.0, 0.0])
            self.scene_objects[name] = {"type": "MESH", "primitive_type": prim_type, "location": loc}
            return BridgeResponse.success({
                "created": True,
                "name": name,
                "type": "MESH",
                "primitive_type": prim_type,
                "location": loc,
            })

        elif tool_name == TOOL_TRANSFORM_OBJECT:
            name = args.get("name")
            if name not in self.scene_objects:
                return BridgeResponse.error(f"Object '{name}' not found in active scene.")
            loc = args.get("location", self.scene_objects[name]["location"])
            self.scene_objects[name]["location"] = loc
            return BridgeResponse.success({
                "transformed": True,
                "name": name,
                "location": loc,
                "relative": args.get("relative", False),
            })

        elif tool_name == TOOL_EXECUTE_BLENDER_CODE:
            ops = args.get("operations", [])
            self.undo_stack.append("undo_push")
            return BridgeResponse.success({
                "executed": True,
                "transactional": True,
                "operations_count": len(ops),
                "operations": ops,
            })

        return BridgeResponse.error(f"Unknown mock tool: {tool_name}")


class TestModelingManifestAndRegistry(unittest.TestCase):
    """Validates ModelingAgent manifest, declared capabilities, and registry discovery."""

    def test_manifest_structure(self):
        manifest = create_modeling_manifest(version="0.1.10")
        manifest.validate()
        self.assertEqual(manifest.agent_id, MODELING_AGENT_ID)
        self.assertEqual(manifest.version, "0.1.10")
        self.assertGreaterEqual(len(manifest.capabilities), 30)

        caps = {c.capability_id: c for c in manifest.capabilities}
        self.assertIn(CAPABILITY_MODELING_PRIMITIVE, caps)
        self.assertIn(CAPABILITY_MODELING_TRANSFORM, caps)
        self.assertIn(CAPABILITY_MODELING_EXECUTION, caps)
        self.assertIn(CAPABILITY_MODELING_EDIT, caps)
        self.assertIn(CAPABILITY_MODELING_UV, caps)
        self.assertIn(CAPABILITY_MODELING_KEYFRAME, caps)
        self.assertIn(CAPABILITY_MODELING_GEONODES, caps)
        self.assertIn(CAPABILITY_MODELING_ASSET_IO, caps)
        self.assertIn(CAPABILITY_MODELING_OBJECT_OPS, caps)
        self.assertIn("modeling.modifiers", caps)
        self.assertIn("modeling.modifier_inspection", caps)
        self.assertIn("modeling.sculpting", caps)
        self.assertIn("modeling.sculpt_inspection", caps)
        self.assertIn("modeling.landmarks", caps)
        self.assertIn("modeling.landmarks_inspection", caps)
        self.assertIn("modeling.surface_detail", caps)
        self.assertIn("modeling.surface_detail_inspect", caps)
        self.assertIn("modeling.anatomical_mask", caps)
        self.assertIn("modeling.anatomical_mask_inspect", caps)
        self.assertIn("modeling.symmetrize", caps)

        for cap in manifest.capabilities:
            self.assertEqual(cap.read_write, "READ_ONLY" if cap.capability_id in ("modeling.modifier_inspection", "modeling.modifier_stack_inspection", "modeling.curve_geometry_inspection", "modeling.object_control_inspection", "modeling.geometry_graph_inspection", "modeling.sculpt_inspection", "modeling.landmarks_inspection", "modeling.surface_detail_inspect", "modeling.anatomical_mask_inspect", "modeling.rigging_inspection", "modeling.physics_inspection") else "SCENE_MUTATION")
            self.assertEqual(cap.verification_status, "VERIFIED")

        # Input schemas must be defined for all 3 mutation tools
        self.assertIn(TOOL_CREATE_PRIMITIVE, manifest.input_schemas)
        self.assertIn(TOOL_TRANSFORM_OBJECT, manifest.input_schemas)
        self.assertIn(TOOL_EXECUTE_BLENDER_CODE, manifest.input_schemas)

    def test_registry_discovery(self):
        registry = create_default_registry()
        agent = registry.get_agent(MODELING_AGENT_ID)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.version, "0.1.13")

        # Discover by capability IDs
        for cap_id in (CAPABILITY_MODELING_PRIMITIVE, CAPABILITY_MODELING_TRANSFORM, CAPABILITY_MODELING_EXECUTION):
            matches = registry.find_agents_by_capability(cap_id)
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].agent_id, MODELING_AGENT_ID)

        # Discover by task types
        for tool in SUPPORTED_MODELING_TOOLS:
            cap = registry.find_capability_by_task_type(tool)
            self.assertIsNotNone(cap)
            self.assertEqual(cap.read_write, "READ_ONLY" if tool in ("inspect_modifiers", "inspect_modifier_stack", "inspect_curve_geometry", "inspect_modeling_object", "inspect_modeling_geometry", "inspect_sculpt_state", "inspect_semantic_landmarks", "inspect_surface_detail", "inspect_anatomical_mask", "inspect_armature", "inspect_physics") else "SCENE_MUTATION")

    def test_routing_via_agent_manager(self):
        manager = AgentManager()
        for tool, cap_id in [
            (TOOL_CREATE_PRIMITIVE, CAPABILITY_MODELING_PRIMITIVE),
            (TOOL_TRANSFORM_OBJECT, CAPABILITY_MODELING_TRANSFORM),
            (TOOL_EXECUTE_BLENDER_CODE, CAPABILITY_MODELING_EXECUTION),
        ]:
            task = AgentTask(
                task_id=f"route-{tool}",
                required_capability=cap_id,
                task_type=tool,
            )
            res = manager.route_task(task, require_verified=True)
            self.assertTrue(res.success)
            self.assertEqual(res.agent.agent_id, MODELING_AGENT_ID)
            self.assertEqual(res.capability.read_write, "SCENE_MUTATION")


class TestModelingAgentValidation(unittest.TestCase):
    """Validates pre-execution input constraints and unsupported operation rejection."""

    def setUp(self):
        self.agent = ModelingAgent(version="0.1.10")
        self.executor = MockModelingExecutor()

    def test_create_primitive_validation(self):
        # Missing name
        task1 = AgentTask(
            task_id="t-val-1",
            required_capability=CAPABILITY_MODELING_PRIMITIVE,
            task_type=TOOL_CREATE_PRIMITIVE,
            input_params={"primitive_type": "cube", "name": ""},
        )
        res1 = self.agent.execute_task(task1, self.executor)
        self.assertEqual(res1.status, TaskStatus.FAILED)
        self.assertIn("name", res1.errors[0].lower())
        self.assertEqual(res1.verification.observed_results["error_code"], "INVALID_PARAMS")

        # Missing primitive_type
        task2 = AgentTask(
            task_id="t-val-2",
            required_capability=CAPABILITY_MODELING_PRIMITIVE,
            task_type=TOOL_CREATE_PRIMITIVE,
            input_params={"name": "MyCube"},
        )
        res2 = self.agent.execute_task(task2, self.executor)
        self.assertEqual(res2.status, TaskStatus.FAILED)
        self.assertEqual(res2.verification.observed_results["error_code"], "INVALID_PARAMS")

    def test_unsupported_primitive_types_rejected(self):
        unsupported_types = ["suzanne", "curve_circle", "metaball", "text", "empty"]
        for pt in unsupported_types:
            task = AgentTask(
                task_id=f"t-unsupp-{pt}",
                required_capability=CAPABILITY_MODELING_PRIMITIVE,
                task_type=TOOL_CREATE_PRIMITIVE,
                input_params={"name": f"Obj_{pt}", "primitive_type": pt},
            )
            res = self.agent.execute_task(task, self.executor)
            self.assertEqual(res.status, TaskStatus.FAILED)
            self.assertEqual(res.verification.observed_results["error_code"], "UNSUPPORTED_REQUEST")
            self.assertIn("unsupported primitive type", res.errors[0].lower())

    def test_transform_object_validation(self):
        # Missing target name
        task1 = AgentTask(
            task_id="t-tf-1",
            required_capability=CAPABILITY_MODELING_TRANSFORM,
            task_type=TOOL_TRANSFORM_OBJECT,
            input_params={"name": "", "location": [1, 2, 3]},
        )
        res1 = self.agent.execute_task(task1, self.executor)
        self.assertEqual(res1.status, TaskStatus.FAILED)
        self.assertEqual(res1.verification.observed_results["error_code"], "INVALID_PARAMS")

        # Missing transform attributes (no location, rotation, or scale)
        task2 = AgentTask(
            task_id="t-tf-2",
            required_capability=CAPABILITY_MODELING_TRANSFORM,
            task_type=TOOL_TRANSFORM_OBJECT,
            input_params={"name": "Cube"},
        )
        res2 = self.agent.execute_task(task2, self.executor)
        self.assertEqual(res2.status, TaskStatus.FAILED)
        self.assertEqual(res2.verification.observed_results["error_code"], "INVALID_PARAMS")
        self.assertIn("at least one transform attribute", res2.errors[0].lower())

    def test_unsupported_modeling_operations_rejected(self):
        """Operations not yet verified in Blender 5.2 (extrude, inset, bevel, boolean) must be rejected."""
        unsupported_actions = [
            "bevel",
            "bevel_edges",
            "boolean",
            "boolean_difference",
            "geometry_nodes",
            "loop_cut",
            "knife",
            "spin",
            "screw",
        ]
        for act in unsupported_actions:
            task = AgentTask(
                task_id=f"t-unsupp-op-{act}",
                required_capability=CAPABILITY_MODELING_EXECUTION,
                task_type=TOOL_EXECUTE_BLENDER_CODE,
                input_params={"operations": [{"action": act, "target": "Cube"}]},
            )
            res = self.agent.execute_task(task, self.executor)
            self.assertEqual(res.status, TaskStatus.FAILED)
            self.assertEqual(res.verification.observed_results["error_code"], "UNSUPPORTED_REQUEST")
            self.assertIn("unsupported modeling operation", res.errors[0].lower())

    def test_ast_security_violations_rejected(self):
        """Disallowed Python code (imports, os.system, eval, exec) must be rejected before execution."""
        unsafe_snippets = [
            "import os\nos.system('dir')",
            "from subprocess import Popen",
            "eval('1 + 1')",
            "exec('x = 1')",
            "open('test.txt', 'w')",
        ]
        for code in unsafe_snippets:
            task = AgentTask(
                task_id="t-ast-unsafe",
                required_capability=CAPABILITY_MODELING_EXECUTION,
                task_type=TOOL_EXECUTE_BLENDER_CODE,
                input_params={"code": code},
            )
            res = self.agent.execute_task(task, self.executor)
            self.assertEqual(res.status, TaskStatus.FAILED)
            self.assertEqual(res.verification.observed_results["error_code"], "SECURITY_VIOLATION")


class TestModelingAgentExecutionAndRecovery(unittest.TestCase):
    """Validates successful mutations, approval enforcement, transaction boundaries, and rollback."""

    def setUp(self):
        self.agent = ModelingAgent(version="0.1.10")
        self.executor = MockModelingExecutor()

    def test_untrusted_approved_true_rejected(self):
        task = AgentTask(
            task_id="t-untrusted-app",
            required_capability=CAPABILITY_MODELING_PRIMITIVE,
            task_type=TOOL_CREATE_PRIMITIVE,
            input_params={"name": "Sphere01", "primitive_type": "sphere", "approved": True},
        )
        res = self.agent.execute_task(task, self.executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])
        self.assertEqual(res.verification.observed_results["error_code"], "PERMISSION_DENIED")
        self.assertEqual(res.verification.observed_results["transaction_status"], "NOT_APPLICABLE")

    def test_successful_primitive_creation(self):
        task = AgentTask(
            task_id="t-create-cube",
            required_capability=CAPABILITY_MODELING_PRIMITIVE,
            task_type=TOOL_CREATE_PRIMITIVE,
            input_params={"name": "NewCube", "primitive_type": "cube", "location": [0.0, 1.0, 2.0]},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.output["name"], "NewCube")
        self.assertIn("created_object:NewCube", res.evidence_references)
        self.assertIn("primitive_type:cube", res.evidence_references)
        self.assertEqual(res.verification.status, "PASS")
        self.assertEqual(res.verification.observed_results["transaction_status"], "COMMITTED")

    def test_successful_object_transform(self):
        task = AgentTask(
            task_id="t-tf-cube",
            required_capability=CAPABILITY_MODELING_TRANSFORM,
            task_type=TOOL_TRANSFORM_OBJECT,
            input_params={"name": "Cube", "location": [10.0, 0.0, 0.0], "relative": True},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.output["name"], "Cube")
        self.assertIn("transformed_object:Cube", res.evidence_references)
        self.assertIn("relative:True", res.evidence_references)
        self.assertEqual(res.verification.status, "PASS")
        self.assertEqual(res.verification.observed_results["transaction_status"], "COMMITTED")

    def test_successful_structured_modeling_execution(self):
        task = AgentTask(
            task_id="t-exec-subsurf",
            required_capability=CAPABILITY_MODELING_EXECUTION,
            task_type=TOOL_EXECUTE_BLENDER_CODE,
            input_params={
                "operations": [
                    {"action": "add_modifier", "target": "Cube", "params": {"modifier_type": "SUBSURF", "name": "Subsurf"}},
                    {"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}},
                ]
            },
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.output["operations_count"], 2)
        self.assertIn("operations_executed:2", res.evidence_references)
        self.assertEqual(res.verification.status, "PASS")
        self.assertEqual(res.verification.observed_results["transaction_status"], "COMMITTED")

    def test_transactional_failure_does_not_prove_rollback_from_message(self):
        """A generic executor rollback phrase is not independent restoration evidence."""
        self.executor.should_fail = True
        self.executor.failure_message = "Simulated crash during modifier application"

        task = AgentTask(
            task_id="t-fail-rollback",
            required_capability=CAPABILITY_MODELING_EXECUTION,
            task_type=TOOL_EXECUTE_BLENDER_CODE,
            input_params={"operations": [{"action": "add_modifier", "target": "Cube", "params": {"modifier_type": "SUBSURF"}}]},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("rolled back", res.errors[0].lower())
        self.assertEqual(res.verification.status, "FAIL")
        self.assertEqual(res.verification.observed_results["transaction_status"], "ROLLBACK_UNVERIFIED")
        self.assertFalse(res.verification.observed_results["rollback_verified"])
        self.assertTrue(self.executor.rollback_executed)


class TestModelingDispatcherIntegration(unittest.TestCase):
    """Validates dispatching modeling operations through AgentDispatcher."""

    def setUp(self):
        self.executor = MockModelingExecutor()
        self.coordinator = SessionCoordinator()
        self.manager = AgentManager()
        self.dispatcher = AgentDispatcher(
            manager=self.manager,
            coordinator=self.coordinator,
            executor=self.executor,
        )

    def test_unapproved_mutation_pauses_in_awaiting_approval(self):
        """Mutations dispatched without human approval pause in AWAITING_APPROVAL."""
        task = AgentTask(
            task_id="disp-mutation-unapproved",
            required_capability=CAPABILITY_MODELING_PRIMITIVE,
            task_type=TOOL_CREATE_PRIMITIVE,
            input_params={"name": "NewSphere", "primitive_type": "sphere"},
        )
        res: DispatchResult = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res.error_code, "APPROVAL_REQUIRED")
        self.assertEqual(res.agent_id, MODELING_AGENT_ID)
        self.assertFalse(self.executor.invocations)

    def test_approved_mutation_dispatches_successfully(self):
        """Mutations dispatched with trusted_approval=True execute and succeed."""
        task = AgentTask(
            task_id="disp-mutation-approved",
            required_capability=CAPABILITY_MODELING_PRIMITIVE,
            task_type=TOOL_CREATE_PRIMITIVE,
            input_params={"name": "ApprovedCube", "primitive_type": "cube"},
        )
        res: DispatchResult = self.dispatcher.dispatch_task(task, trusted_approval=True)
        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.agent_id, MODELING_AGENT_ID)
        self.assertEqual(res.result["name"], "ApprovedCube")
        self.assertEqual(res.verification.status, "PASS")
        self.assertEqual(res.verification.observed_results["transaction_status"], "COMMITTED")

    def test_unsupported_operation_dispatched_returns_structured_error(self):
        """Unsupported operation (e.g. bevel) dispatched returns UNSUPPORTED_REQUEST."""
        task = AgentTask(
            task_id="disp-unsupp-bevel",
            required_capability=CAPABILITY_MODELING_EXECUTION,
            task_type=TOOL_EXECUTE_BLENDER_CODE,
            input_params={"operations": [{"action": "bevel", "target": "Cube"}]},
        )
        res: DispatchResult = self.dispatcher.dispatch_task(task, trusted_approval=True)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "UNSUPPORTED_REQUEST")
        self.assertIn("Unsupported modeling operation", res.message)

    def test_all_four_primitive_types_supported(self):
        """Verifies Cube, Sphere, Cylinder, and Plane are all successfully created."""
        primitives = [
            ("cube", {"name": "TestCube", "primitive_type": "cube", "location": [0, 0, 0]}),
            ("sphere", {"name": "TestSphere", "primitive_type": "sphere", "radius": 1.5, "segments": 32}),
            ("cylinder", {"name": "TestCylinder", "primitive_type": "cylinder", "radius": 0.8, "depth": 2.5}),
            ("plane", {"name": "TestPlane", "primitive_type": "plane", "size": 4.0}),
        ]
        for p_type, params in primitives:
            task = AgentTask(
                task_id=f"disp-prim-{p_type}",
                required_capability=CAPABILITY_MODELING_PRIMITIVE,
                task_type=TOOL_CREATE_PRIMITIVE,
                input_params=params,
            )
            res = self.dispatcher.dispatch_task(task, trusted_approval=True)
            self.assertTrue(res.success, f"Primitive '{p_type}' failed: {res.message}")
            self.assertEqual(res.status, TaskStatus.SUCCEEDED)
            self.assertEqual(res.result["primitive_type"], p_type)

    def test_token_replay_rejected_via_approval_registry(self):
        """Approval token cannot be reused for a second mutation."""
        from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
        reg = ApprovalRegistry()
        params = {"name": "ReplayCube", "primitive_type": "cube"}
        req = reg.create_request(TOOL_CREATE_PRIMITIVE, params)
        ok, token = reg.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # First consumption
        ok1, reason1 = reg.consume_approval(req.request_id, token, TOOL_CREATE_PRIMITIVE, params)
        self.assertTrue(ok1)

        # Replay attempt
        ok2, reason2 = reg.consume_approval(req.request_id, token, TOOL_CREATE_PRIMITIVE, params)
        self.assertFalse(ok2)
        self.assertIn("already been consumed", reason2)

    def test_structured_modeling_all_actions(self):
        """Verifies supported modeling actions (modifiers, shade mode, material, parenting, joining)."""
        actions = [
            {"action": "add_modifier", "target": "Cube", "params": {"modifier_type": "SUBSURF", "name": "Subsurf"}},
            {"action": "modify_modifier", "target": "Cube", "params": {"modifier_name": "Subsurf", "properties": {"levels": 2}}},
            {"action": "remove_modifier", "target": "Cube", "params": {"modifier_name": "Subsurf"}},
            {"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}},
            {"action": "subdivide_mesh", "target": "Cube", "params": {"cuts": 2}},
            {"action": "create_material", "params": {"material_name": "Mat_Gold"}},
            {"action": "assign_material", "target": "Cube", "params": {"material_name": "Mat_Gold"}},
            {"action": "parent_object", "target": "Cube", "params": {"parent_name": "Camera"}},
            {"action": "join_objects", "target": "Cube", "params": {"objects_to_join": ["Coffer_Asset"]}},
        ]
        task = AgentTask(
            task_id="disp-all-actions",
            required_capability=CAPABILITY_MODELING_EXECUTION,
            task_type=TOOL_EXECUTE_BLENDER_CODE,
            input_params={"operations": actions},
        )
        res = self.dispatcher.dispatch_task(task, trusted_approval=True)
        self.assertTrue(res.success, f"All actions execution failed: {res.message}")
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.result["operations_count"], len(actions))


if __name__ == "__main__":
    unittest.main()
