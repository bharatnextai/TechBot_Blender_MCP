"""
Unit Tests for TASK-UMCP-0034: Trusted Approval Resume Integration.

Validates:
1. Material assignment pausing in AWAITING_APPROVAL with exact approval binding preserved.
2. Repeated requests without trusted approval preserving pending task and binding.
3. Untrusted chat/model 'approved=True' and 'trusted_approval=True' rejection (PERMISSION_DENIED).
4. Successful resumption after trusted approval verification to SUCCEEDED.
5. Resumption with valid approval credentials (request_id and approval_token).
6. Parameter tampering detection and rejection (PARAMETER_TAMPERING) requiring fresh approval.
7. Expired approval rejection (APPROVAL_EXPIRED).
8. Provider denial handling (PERMISSION_DENIED).
9. Duplicate execution prevention returning cached result with is_duplicate=True.
10. dispatch_tool_call pending task correlation by parameter hash.
"""

import copy
import unittest
from typing import Dict, Any, Optional

from shared.models.agent_contracts import (
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
)
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.registry import create_default_registry
from mcp_service.agents.router import CapabilityRouter
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.manager import AgentManager
from mcp_service.agents.session_coordinator import SessionCoordinator
from mcp_service.agents.dispatcher import AgentDispatcher, DispatchResult
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.security.approval import (
    ApprovalManager,
    ApprovalDecision,
    compute_param_hash,
)


class MockApprovalExecutor(BlenderExecutor):
    """In-memory mock executor tracking invocations for approval resumption tests."""

    def __init__(self):
        self.invocations = []
        self.approval_manager = ApprovalManager()

    def is_connected(self) -> bool:
        return True

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        trusted_approval: Optional[bool] = None,
    ) -> BridgeResponse:
        params = dict(arguments or {})
        self.invocations.append((tool_name, params, trusted_approval))

        # Check approval requirements
        if self.approval_manager.requires_approval(tool_name):
            if trusted_approval is False:
                return BridgeResponse.error(f"Approval denied: trusted_approval was False for '{tool_name}'")
            if trusted_approval is not True and not (params.get("request_id") and params.get("approval_token")):
                return BridgeResponse.error(f"Approval required: Scene mutation '{tool_name}' requires approval.")

        if tool_name == "assign_material":
            target = params.get("target_name") or params.get("target", "Cube")
            material = params.get("material_name") or params.get("name", "DragonScale")
            return BridgeResponse.success({
                "target": target,
                "material_name": material,
                "slot_index": 0,
                "action": "assign_material",
            })
        elif tool_name == "create_material":
            name = params.get("name", "NewMaterial")
            return BridgeResponse.success({
                "name": name,
                "diffuse_color": [0.8, 0.2, 0.2, 1.0],
                "created": True,
            })
        elif tool_name == "create_primitive":
            return BridgeResponse.success({
                "name": params.get("name", "Cube"),
                "created": True,
            })
        elif tool_name == "inspect_scene_data":
            target = params.get("target_name") or params.get("target", "Cube")
            return BridgeResponse.success({
                "target_name": target,
                "category": "object_materials",
                "materials": [
                    {"slot_index": 0, "material_name": "DragonScale", "assigned": True}
                ],
            })
        return BridgeResponse.success({"status": "ok", "tool": tool_name})


class TestApprovalResumption(unittest.TestCase):
    """Test suite for trusted approval resumption and pending operation tracking."""

    def setUp(self):
        self.registry = create_default_registry()
        self.router = CapabilityRouter(self.registry)
        self.planner = TaskPlanner(self.router)
        self.manager = AgentManager(
            registry=self.registry,
            router=self.router,
            planner=self.planner,
        )
        self.coordinator = SessionCoordinator()
        self.executor = MockApprovalExecutor()
        self.dispatcher = AgentDispatcher(
            manager=self.manager,
            coordinator=self.coordinator,
            executor=self.executor,
        )

    def test_material_assignment_pauses_and_preserves_binding(self):
        """Mutation task pauses in AWAITING_APPROVAL and preserves exact approval binding."""
        task = AgentTask(
            task_id="task_dragon_001",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_01",
            correlation_id="corr_dragon_01",
        )

        res = self.dispatcher.dispatch_task(task, session_id="session_test_01")

        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res.error_code, "APPROVAL_REQUIRED")
        self.assertIn("Approval required", res.message)

        # Verify task state in coordinator
        session = self.coordinator.get_session("session_test_01")
        self.assertIsNotNone(session)
        stored_task = session.tasks.get("task_dragon_001")
        self.assertIsNotNone(stored_task)
        self.assertEqual(stored_task.status, TaskStatus.AWAITING_APPROVAL)

        # Verify approval binding
        binding = self.coordinator.get_pending_approval("session_test_01", "task_dragon_001")
        self.assertIsNotNone(binding)
        self.assertEqual(binding["task_id"], "task_dragon_001")
        self.assertEqual(binding["tool_name"], "assign_material")
        self.assertEqual(binding["raw_params"]["target_name"], "Cube")
        self.assertEqual(binding["raw_params"]["material_name"], "DragonScale")

        # Verify parameter hash matches compute_param_hash
        expected_hash = compute_param_hash("assign_material", {"target_name": "Cube", "material_name": "DragonScale"})
        self.assertEqual(binding["param_hash"], expected_hash)
        self.assertEqual(stored_task.approval_binding["param_hash"], expected_hash)

        # Verify executor was NOT invoked for mutation
        self.assertEqual(len(self.executor.invocations), 0)

    def test_repeated_requests_without_status_source_report_unknown(self):
        """A cached local binding without a status reader is not reported as live pending."""
        task = AgentTask(
            task_id="task_dragon_002",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_02",
        )

        # Initial dispatch
        res1 = self.dispatcher.dispatch_task(task, session_id="session_test_02")
        self.assertEqual(res1.status, TaskStatus.AWAITING_APPROVAL)

        # Second dispatch (e.g. user replies "approved" in chat and model re-dispatches)
        repeat_task = AgentTask(
            task_id="task_dragon_002",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_02",
        )
        res2 = self.dispatcher.dispatch_task(repeat_task, session_id="session_test_02")

        self.assertFalse(res2.success)
        self.assertEqual(res2.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res2.error_code, "APPROVAL_STATUS_UNAVAILABLE")
        self.assertEqual(res2.result["pending_approval"]["approval_status"], "unknown")
        self.assertIn("status is unavailable", res2.message)
        self.assertEqual(res2.task_id, "task_dragon_002")

        # Task and binding are preserved intact
        session = self.coordinator.get_session("session_test_02")
        self.assertEqual(len(session.tasks), 1)
        stored = session.tasks["task_dragon_002"]
        self.assertEqual(stored.status, TaskStatus.AWAITING_APPROVAL)
        self.assertIsNotNone(stored.approval_binding)

        # Zero mutation execution
        self.assertEqual(len(self.executor.invocations), 0)

    def test_untrusted_chat_and_model_flags_rejected(self):
        """Model or caller passing approved=True is strictly rejected with PERMISSION_DENIED."""
        task = AgentTask(
            task_id="task_dragon_003",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_03",
        )
        self.dispatcher.dispatch_task(task, session_id="session_test_03")

        # Now caller attempts to re-dispatch with approved=True
        bypass_task = AgentTask(
            task_id="task_dragon_003",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={
                "target_name": "Cube",
                "material_name": "DragonScale",
                "approved": True,
            },
            session_id="session_test_03",
        )
        res = self.dispatcher.dispatch_task(bypass_task, session_id="session_test_03")

        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertIn("untrusted", res.message)

        # Pending approval cleared on failure
        self.assertIsNone(self.coordinator.get_pending_approval("session_test_03", "task_dragon_003"))
        self.assertEqual(len(self.executor.invocations), 0)

    def test_successful_trusted_approval_resumption(self):
        """Resumption with trusted_approval=True transitions task to SUCCEEDED and executes."""
        task = AgentTask(
            task_id="task_dragon_004",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_04",
        )
        res_init = self.dispatcher.dispatch_task(task, session_id="session_test_04")
        self.assertEqual(res_init.status, TaskStatus.AWAITING_APPROVAL)

        # Resume with trusted approval
        res_resume = self.dispatcher.resume_task(
            task_id="task_dragon_004",
            session_id="session_test_04",
            trusted_approval=True,
        )

        self.assertTrue(res_resume.success)
        self.assertEqual(res_resume.status, TaskStatus.SUCCEEDED)
        self.assertIsNotNone(res_resume.result)
        self.assertEqual(res_resume.result.get("material_name"), "DragonScale")

        # Task in session is SUCCEEDED and pending approval is cleared
        session = self.coordinator.get_session("session_test_04")
        self.assertEqual(session.tasks["task_dragon_004"].status, TaskStatus.SUCCEEDED)
        self.assertIsNone(self.coordinator.get_pending_approval("session_test_04", "task_dragon_004"))

        # Executor was invoked with trusted_approval=True
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 1)
        tool, args, trusted = mutation_invs[0]
        self.assertEqual(tool, "assign_material")
        self.assertEqual(args["material_name"], "DragonScale")
        self.assertTrue(trusted)

    def test_resumption_via_dispatch_task_with_trusted_approval(self):
        """dispatch_task called with trusted_approval=True on pending task resumes successfully."""
        task = AgentTask(
            task_id="task_dragon_005",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_05",
        )
        self.dispatcher.dispatch_task(task, session_id="session_test_05")

        # Re-dispatch with trusted_approval=True
        resume_task = AgentTask(
            task_id="task_dragon_005",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_05",
        )
        res = self.dispatcher.dispatch_task(resume_task, session_id="session_test_05", trusted_approval=True)

        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 1)

    def test_resumption_with_credentials(self):
        """Resumption with request_id and approval_token resumes successfully."""
        task = AgentTask(
            task_id="task_dragon_006",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_06",
        )
        self.dispatcher.dispatch_task(task, session_id="session_test_06")

        res = self.dispatcher.resume_task(
            task_id="task_dragon_006",
            session_id="session_test_06",
            request_id="req_token_123",
            approval_token="secret_token_abc",
        )

        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 1)
        tool, args, trusted = mutation_invs[0]
        self.assertEqual(args.get("request_id"), "req_token_123")
        self.assertEqual(args.get("approval_token"), "secret_token_abc")

    def test_parameter_tampering_detected_and_rejected(self):
        """Altering parameters for pending task is rejected with PARAMETER_TAMPERING."""
        task = AgentTask(
            task_id="task_dragon_007",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_07",
        )
        self.dispatcher.dispatch_task(task, session_id="session_test_07")

        # Attempt to resume with modified parameters (e.g. material changed to Gold)
        tampered_params = {"target_name": "Cube", "material_name": "Gold"}
        res = self.dispatcher.resume_task(
            task_id="task_dragon_007",
            session_id="session_test_07",
            trusted_approval=True,
            execution_params=tampered_params,
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res.error_code, "PARAMETER_TAMPERING")
        self.assertIn("Parameter tampering detected", res.message)

        # Also test tampering via dispatch_task re-entry
        tampered_task = AgentTask(
            task_id="task_dragon_007",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params=tampered_params,
            session_id="session_test_07",
        )
        res2 = self.dispatcher.dispatch_task(tampered_task, session_id="session_test_07", trusted_approval=True)
        self.assertFalse(res2.success)
        self.assertEqual(res2.error_code, "PARAMETER_TAMPERING")

        # Zero executions performed under tampered parameters
        self.assertEqual(len(self.executor.invocations), 0)

    def test_expired_approval_rejected(self):
        """Resumption with expired approval provider decision fails with APPROVAL_EXPIRED."""
        task = AgentTask(
            task_id="task_dragon_008",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_08",
        )
        self.dispatcher.dispatch_task(task, session_id="session_test_08")

        # Configure approval provider that returns expired decision
        def expired_provider(tool, args):
            return ApprovalDecision(False, "Approval timed out after 30.0s", request_id="req_exp")

        self.executor.approval_manager.set_provider(expired_provider)

        res = self.dispatcher.resume_task(
            task_id="task_dragon_008",
            session_id="session_test_08",
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "APPROVAL_EXPIRED")
        self.assertIn("timed out", res.message)

        self.assertEqual(len(self.executor.invocations), 0)

    def test_denied_approval_fails_task(self):
        """Explicit denial by user or provider fails resumption with PERMISSION_DENIED."""
        task = AgentTask(
            task_id="task_dragon_009",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_09",
        )
        self.dispatcher.dispatch_task(task, session_id="session_test_09")

        # Explicit deny via trusted_approval=False
        res = self.dispatcher.resume_task(
            task_id="task_dragon_009",
            session_id="session_test_09",
            trusted_approval=False,
        )

        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertIn("denied", res.message)

        self.assertEqual(len(self.executor.invocations), 0)

    def test_duplicate_execution_returns_cached_result(self):
        """Resuming an already SUCCEEDED task returns cached result with is_duplicate=True."""
        task = AgentTask(
            task_id="task_dragon_010",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_10",
            correlation_id="corr_dragon_10",
        )
        self.dispatcher.dispatch_task(task, session_id="session_test_10")

        # Resume once -> SUCCEEDED
        res1 = self.dispatcher.resume_task(
            task_id="task_dragon_010",
            session_id="session_test_10",
            trusted_approval=True,
        )
        self.assertTrue(res1.success)
        self.assertFalse(res1.is_duplicate)
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 1)

        # Resume second time -> duplicate cached result
        res2 = self.dispatcher.resume_task(
            task_id="task_dragon_010",
            session_id="session_test_10",
            trusted_approval=True,
        )
        self.assertTrue(res2.success)
        self.assertTrue(res2.is_duplicate)
        self.assertIn("Duplicate execution", res2.message)
        # Executor was NOT invoked a second time for mutation
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 1)

        # Dispatch second time with correlation ID -> duplicate cached result
        dup_task = AgentTask(
            task_id="task_dragon_new",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_test_10",
            correlation_id="corr_dragon_10",
        )
        res3 = self.dispatcher.dispatch_task(dup_task, session_id="session_test_10")
        self.assertTrue(res3.success)
        self.assertTrue(res3.is_duplicate)
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 1)

    def test_dispatch_tool_call_correlates_pending_approval(self):
        """dispatch_tool_call reuses existing pending task in AWAITING_APPROVAL."""
        params = {"target_name": "Cube", "material_name": "DragonScale", "correlation_id": "tool_corr_01"}

        # 1. First tool call pauses in AWAITING_APPROVAL
        resp1 = self.dispatcher.dispatch_tool_call("assign_material", params, session_id="session_tool_01")
        self.assertFalse(resp1.is_success)
        self.assertIn("Approval required", resp1.message)

        # Check pending task created
        session = self.coordinator.get_session("session_tool_01")
        self.assertEqual(len(session.tasks), 1)
        first_task_id = list(session.tasks.keys())[0]

        # 2. Second tool call with same arguments reuses the same pending task
        resp2 = self.dispatcher.dispatch_tool_call("assign_material", params, session_id="session_tool_01")
        self.assertFalse(resp2.is_success)
        self.assertIn("status is unavailable", resp2.message)

        # No duplicate task created!
        self.assertEqual(len(session.tasks), 1)
        self.assertIn(first_task_id, session.tasks)

        # 3. Resume the pending task with trusted approval
        resume_res = self.dispatcher.resume_task(first_task_id, session_id="session_tool_01", trusted_approval=True)
        self.assertTrue(resume_res.success)
        self.assertEqual(session.tasks[first_task_id].status, TaskStatus.SUCCEEDED)

        # 4. Third tool call returns cached duplicate result
        resp3 = self.dispatcher.dispatch_tool_call(
            "assign_material",
            params,
            session_id="session_tool_01",
        )
        self.assertTrue(resp3.is_success)
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 1)


if __name__ == "__main__":
    unittest.main()
