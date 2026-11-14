"""
Unit and Integration Tests for TASK-UMCP-0015 (Phase 2):
Agent Manager Dispatcher and Session Coordination.

Validates:
- Successful deterministic routing and plan creation
- Unknown, unverified, incompatible, and ambiguous capability rejection
- Invalid dependency graphs rejected before dispatch
- Session isolation, tracking, and TTL cleanup
- Duplicate requests and repeated correlation IDs
- Correct task-state transitions and structured failure propagation
- No mutation handler invocation during planning
- Mutation requests blocked without valid existing approval
- Model-supplied approved=True rejection
- Backward compatibility with existing MCP tool discovery and invocation
"""

import unittest
import time
from typing import Dict, Any, Optional

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
)
from mcp_service.agents.registry import AgentRegistry, create_default_registry
from mcp_service.agents.router import CapabilityRouter
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.manager import AgentManager
from mcp_service.agents.session_coordinator import SessionCoordinator, SessionContext
from mcp_service.agents.dispatcher import AgentDispatcher, DispatchResult
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.security.approval import ApprovalManager


class MockDispatcherExecutor(BlenderExecutor):
    """In-memory mock executor tracking execution calls without socket I/O."""

    def __init__(self):
        self.invocations = []
        self.should_fail = False
        self.failure_message = "Simulated Blender execution failure"
        self.approval_manager = ApprovalManager()

    def is_connected(self) -> bool:
        return True

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        trusted_approval: Optional[bool] = None,
    ) -> BridgeResponse:
        self.invocations.append((tool_name, arguments, trusted_approval))

        if self.should_fail:
            return BridgeResponse.error(self.failure_message)

        # Check approval for mutation tools
        if self.approval_manager.requires_approval(tool_name):
            if trusted_approval is False:
                return BridgeResponse.error(f"Approval denied: trusted_approval was False for '{tool_name}'")
            if trusted_approval is not True:
                provider = getattr(self.approval_manager, "_provider", None)
                if not provider:
                    return BridgeResponse.error(
                        f"Approval required: Scene mutation '{tool_name}' requires explicit user approval."
                    )
                decision = provider(tool_name, arguments or {})
                if not decision:
                    return BridgeResponse.error(f"Approval denied: Human operator denied '{tool_name}'.")

        # Mock successful tool responses
        if tool_name == TOOL_GET_SCENE_SUMMARY:
            return BridgeResponse.success({
                "scene_name": "TestScene",
                "total_objects": 2,
                "collections": ["Collection 1"],
            })
        elif tool_name == TOOL_LIST_OBJECTS:
            return BridgeResponse.success({
                "total_matching": 1,
                "objects": [{"name": "Cube", "type": "MESH"}],
            })
        elif tool_name == TOOL_CREATE_PRIMITIVE:
            return BridgeResponse.success({
                "created": True,
                "name": (arguments or {}).get("name", "NewObject"),
                "type": "MESH",
            })
        elif tool_name == TOOL_TRANSFORM_OBJECT:
            return BridgeResponse.success({
                "name": (arguments or {}).get("name", "Cube"),
                "transformed": True,
            })
        return BridgeResponse.success({"status": "mock_success", "tool": tool_name})


class TestAgentDispatcherAndSessionCoordination(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MockDispatcherExecutor()
        self.registry = create_default_registry()
        self.router = CapabilityRouter(self.registry)
        self.planner = TaskPlanner(self.router)
        self.manager = AgentManager(registry=self.registry, router=self.router, planner=self.planner)
        self.coordinator = SessionCoordinator(default_ttl_seconds=3600.0)
        self.dispatcher = AgentDispatcher(
            manager=self.manager,
            coordinator=self.coordinator,
            executor=self.mock_executor,
        )

    # -------------------------------------------------------------------------
    # 1. Routing & Plan Creation Tests
    # -------------------------------------------------------------------------

    def test_dispatch_task_success(self):
        """Validates successful routing, planning, and execution for a read-only query."""
        task = AgentTask(
            task_id="task_summary_01",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            input_params={"include_collections": True},
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_01")
        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.agent_id, "agent.scene_inspector")
        self.assertEqual(res.capability_id, "scene.inspection")
        self.assertIsNotNone(res.result)
        self.assertEqual(res.result.get("scene_name"), "TestScene")
        self.assertEqual(len(self.mock_executor.invocations), 1)

    def test_dispatch_task_auto_resolves_capability(self):
        """Validates that omitting required_capability resolves automatically from task_type."""
        task = AgentTask(
            task_id="task_auto_01",
            required_capability="",  # Omitted
            task_type="list_objects",
            input_params={"object_type": "MESH"},
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_01")
        self.assertTrue(res.success)
        self.assertEqual(res.capability_id, "scene.inspection")
        self.assertEqual(res.agent_id, "agent.scene_inspector")
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)

    # -------------------------------------------------------------------------
    # 2. Unknown, Unverified, Incompatible, & Ambiguous Capability Rejection
    # -------------------------------------------------------------------------

    def test_reject_unknown_capability(self):
        """Unknown capability returns structured NO_MATCH and halts execution."""
        task = AgentTask(
            task_id="task_unknown_cap",
            required_capability="unknown.nonexistent_cap",
            task_type="foo",
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "NO_MATCH")
        self.assertIn("No enabled agent found", res.message)
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_reject_unknown_task_type(self):
        """Unknown task type with no capability returns NO_MATCH without calling executor."""
        task = AgentTask(
            task_id="task_unknown_type",
            required_capability="",
            task_type="non_existent_tool_xyz",
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "NO_MATCH")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_reject_unverified_capability(self):
        """Unverified capability is rejected by default before execution."""
        unverified_agent = AgentManifest(
            agent_id="agent.experimental",
            name="Experimental Agent",
            version="0.1.0",
            capabilities=[
                CapabilityDescriptor(
                    capability_id="experimental.feature",
                    supported_task_types=["test_exp"],
                    read_write="READ_ONLY",
                    verification_status="UNVERIFIED",
                )
            ],
        )
        self.registry.register_agent(unverified_agent)

        task = AgentTask(
            task_id="task_unverified",
            required_capability="experimental.feature",
            task_type="test_exp",
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "UNVERIFIED_CAPABILITY")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_reject_incompatible_task_type(self):
        """Task type incompatible with declared capability is rejected."""
        task = AgentTask(
            task_id="task_incompat",
            required_capability="scene.inspection",
            task_type="unsupported_sub_action",
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "NO_MATCH")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_reject_ambiguous_capability_in_strict_mode(self):
        """Ambiguous match with identical priority and version returns AMBIGUOUS_MATCH in strict mode."""
        base_agent = self.registry.get_agent("agent.scene_inspector")
        competing_agent = AgentManifest(
            agent_id="agent.scene_inspector_clone",
            name="Clone Inspector",
            version=base_agent.version if base_agent else "0.1.11",
            capabilities=[
                CapabilityDescriptor(
                    capability_id="scene.inspection",
                    supported_task_types=["get_scene_summary"],
                    read_write="READ_ONLY",
                    verification_status="VERIFIED",
                )
            ],
            priority=base_agent.priority if base_agent else 10,
        )
        self.registry.register_agent(competing_agent)

        task = AgentTask(
            task_id="task_ambig",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "AMBIGUOUS_MATCH")
        self.assertIn("Ambiguous capability match", res.message)
        self.assertEqual(len(self.mock_executor.invocations), 0)

    # -------------------------------------------------------------------------
    # 3. Invalid Dependency Graphs Rejected Before Dispatch
    # -------------------------------------------------------------------------

    def test_reject_dependency_cycle_before_dispatch(self):
        """Plan with 2-node cycle is rejected prior to dispatch and executes NO tasks."""
        t1 = AgentTask("t1", "scene.inspection", "get_scene_summary", dependencies=["t2"])
        t2 = AgentTask("t2", "scene.inspection", "list_objects", dependencies=["t1"])
        plan = TaskPlan(title="Cycle Plan")
        plan.add_task(t1)
        plan.add_task(t2)

        results = self.dispatcher.dispatch_plan(plan, session_id="sess_cycle")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertFalse(r.success)
            self.assertEqual(r.error_code, "DEPENDENCY_CYCLE")
            self.assertEqual(r.status, TaskStatus.FAILED)
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_reject_missing_dependency_reference(self):
        """Plan with non-existent dependency reference is rejected before dispatch."""
        t1 = AgentTask("t1", "scene.inspection", "get_scene_summary", dependencies=["non_existent_t99"])
        plan = TaskPlan(title="Missing Dep Plan")
        plan.add_task(t1)

        results = self.dispatcher.dispatch_plan(plan)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertEqual(results[0].error_code, "INVALID_PLAN")
        self.assertIn("depends on non-existent task", results[0].message)
        self.assertEqual(len(self.mock_executor.invocations), 0)

    # -------------------------------------------------------------------------
    # 4. Session Scoping, Isolation & Expiration
    # -------------------------------------------------------------------------

    def test_session_isolation(self):
        """Tasks and correlation IDs are strictly isolated per session."""
        task_a = AgentTask("t_a", "scene.inspection", "get_scene_summary")
        self.dispatcher.dispatch_task(task_a, session_id="session_A", correlation_id="corr_001")

        # Session A must find it
        self.assertIsNotNone(self.coordinator.get_task_by_correlation("session_A", "corr_001"))
        self.assertIsNotNone(self.coordinator.get_task("session_A", "t_a"))

        # Session B must NOT find it
        self.assertIsNone(self.coordinator.get_task_by_correlation("session_B", "corr_001"))
        self.assertIsNone(self.coordinator.get_task("session_B", "t_a"))

    def test_session_expiration_and_cleanup(self):
        """Inactive sessions exceeding TTL are evicted; active sessions are preserved."""
        sess_old = self.coordinator.get_or_create_session("sess_old")
        sess_old.last_active_at = time.time() - 4000.0  # 4000s ago

        sess_new = self.coordinator.get_or_create_session("sess_new")
        sess_new.last_active_at = time.time()

        evicted = self.coordinator.cleanup_expired_sessions(max_age_seconds=3600.0)
        self.assertEqual(evicted, 1)
        self.assertFalse(self.coordinator.has_session("sess_old"))
        self.assertTrue(self.coordinator.has_session("sess_new"))

    def test_close_session(self):
        """Explicit session closing removes session state immediately."""
        self.coordinator.get_or_create_session("sess_to_close")
        self.assertTrue(self.coordinator.has_session("sess_to_close"))
        self.assertTrue(self.coordinator.close_session("sess_to_close"))
        self.assertFalse(self.coordinator.has_session("sess_to_close"))

    # -------------------------------------------------------------------------
    # 5. Duplicate Requests & Correlation ID Deduplication
    # -------------------------------------------------------------------------

    def test_duplicate_request_correlation_id_deduplication(self):
        """Repeated correlation ID returns cached result without re-executing."""
        task1 = AgentTask(
            task_id="task_dedup_01",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
        )
        res1 = self.dispatcher.dispatch_task(task1, session_id="sess_dedup", correlation_id="corr_999")
        self.assertTrue(res1.success)
        self.assertFalse(res1.is_duplicate)
        self.assertEqual(len(self.mock_executor.invocations), 1)

        # Dispatch identical correlation ID
        task2 = AgentTask(
            task_id="task_dedup_02",  # Different task_id, same correlation_id
            required_capability="scene.inspection",
            task_type="get_scene_summary",
        )
        res2 = self.dispatcher.dispatch_task(task2, session_id="sess_dedup", correlation_id="corr_999")
        self.assertTrue(res2.success)
        self.assertTrue(res2.is_duplicate)
        self.assertEqual(res2.task_id, "task_dedup_01")
        self.assertEqual(res2.result, res1.result)
        # Executor must NOT have been called a second time
        self.assertEqual(len(self.mock_executor.invocations), 1)

    # -------------------------------------------------------------------------
    # 6. Task State Transitions & Failure Propagation
    # -------------------------------------------------------------------------

    def test_plan_failure_propagates_skips_downstream(self):
        """Failure of upstream task causes downstream dependent tasks to be SKIPPED."""
        t1 = AgentTask("t1", "scene.inspection", "get_scene_summary")
        t2 = AgentTask("t2", "scene.inspection", "list_objects", dependencies=["t1"])
        t3 = AgentTask("t3", "scene.inspection", "list_objects", dependencies=["t2"])

        plan = TaskPlan(title="Cascading Plan")
        plan.add_task(t1)
        plan.add_task(t2)
        plan.add_task(t3)

        # Configure mock executor to fail on t1
        self.mock_executor.should_fail = True
        self.mock_executor.failure_message = "Simulated bridge failure on t1"

        results = self.dispatcher.dispatch_plan(plan, session_id="sess_cascade")
        self.assertEqual(len(results), 3)

        # t1 failed
        self.assertFalse(results[0].success)
        self.assertEqual(results[0].status, TaskStatus.FAILED)
        self.assertEqual(results[0].error_code, "EXECUTION_FAILED")

        # t2 and t3 were skipped due to prerequisite failure
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].status, TaskStatus.SKIPPED)
        self.assertEqual(results[1].error_code, "UPSTREAM_FAILURE")

        self.assertFalse(results[2].success)
        self.assertEqual(results[2].status, TaskStatus.SKIPPED)
        self.assertEqual(results[2].error_code, "UPSTREAM_FAILURE")

        # Only t1 was invoked on the executor
        self.assertEqual(len(self.mock_executor.invocations), 1)

    # -------------------------------------------------------------------------
    # 7. No Mutation Handler Invocation During Planning
    # -------------------------------------------------------------------------

    def test_no_execution_during_planning(self):
        """Constructing, validating, and ordering plans invokes zero executor operations."""
        t1 = AgentTask("m1", "modeling.primitive", "create_primitive", input_params={"name": "Box1", "primitive_type": "cube"})
        t2 = AgentTask("m2", "modeling.transform", "transform_object", dependencies=["m1"], input_params={"name": "Box1", "location": [1, 2, 3]})

        plan = self.manager.create_plan("TwoStepModeling", [t1, t2])
        self.assertEqual(plan.execution_order, ["m1", "m2"])
        # No bridge calls or executor calls occurred
        self.assertEqual(len(self.mock_executor.invocations), 0)

    # -------------------------------------------------------------------------
    # 8. Approval Security Boundary: Mutation Blocked vs Approved
    # -------------------------------------------------------------------------

    def test_mutation_blocked_without_approval_credentials_or_provider(self):
        """Scene mutation with no approval credentials or provider pauses in AWAITING_APPROVAL."""
        task = AgentTask(
            task_id="task_mut_01",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={"name": "Cube_A", "primitive_type": "cube"},
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res.error_code, "APPROVAL_REQUIRED")
        self.assertIn("requires human approval", res.message)
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_mutation_allowed_with_approval_provider(self):
        """Scene mutation with approved provider executes successfully on main thread."""
        self.mock_executor.approval_manager.set_provider(lambda tool, params: True)
        task = AgentTask(
            task_id="task_mut_02",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={"name": "Cube_Approved", "primitive_type": "cube"},
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.result.get("created"), True)
        self.assertEqual(len(self.mock_executor.invocations), 1)

    def test_mutation_explicit_denial_fails_task(self):
        """Scene mutation with denied approval provider transitions to FAILED."""
        self.mock_executor.approval_manager.set_provider(lambda tool, params: False)
        task = AgentTask(
            task_id="task_mut_03",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={"name": "Cube_Denied", "primitive_type": "cube"},
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertIn("denied", res.message.lower())

    def test_model_supplied_approved_flag_rejected(self):
        """Model-supplied 'approved=True' is rejected as untrusted before execution."""
        task = AgentTask(
            task_id="task_bypass_attempt",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={"name": "Cube_Bypass", "primitive_type": "cube", "approved": True},
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertIn("untrusted and cannot authorize", res.message)
        self.assertEqual(len(self.mock_executor.invocations), 0)

    # -------------------------------------------------------------------------
    # 9. MCP Server Integration & Dispatch Tool Call Adapter
    # -------------------------------------------------------------------------

    def test_dispatch_tool_call_read_only(self):
        """dispatch_tool_call converts DispatchResult into standard BridgeResponse."""
        resp = self.dispatcher.dispatch_tool_call(
            tool_name="get_scene_summary",
            arguments={"include_collections": True},
            session_id="sess_adapter",
            correlation_id="corr_adapter_1",
        )
        self.assertTrue(resp.is_success)
        self.assertEqual(resp.result.get("scene_name"), "TestScene")

    def test_dispatch_tool_call_mutation_blocked(self):
        """dispatch_tool_call returns structured error envelope when approval required."""
        resp = self.dispatcher.dispatch_tool_call(
            tool_name="create_primitive",
            arguments={"name": "Box2", "primitive_type": "cube"},
            session_id="sess_adapter",
        )
        self.assertFalse(resp.is_success)
        self.assertIn("Approval required", resp.message)


if __name__ == "__main__":
    unittest.main()
