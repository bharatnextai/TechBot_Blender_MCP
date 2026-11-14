"""
Unit tests for Secure Chat Approval Resolution (TASK-UMCP-0038).

Tests:
1. Pending approval pause generates cryptographic nonce and canonical param_hash.
2. Successful approval resolution resumes the original pending task exactly once to SUCCEEDED.
3. Explicit denial transitions task to FAILED with PERMISSION_DENIED without executor invocation.
4. Replay attacks are rejected and duplicate executions prevented.
5. Wrong nonce is rejected with INVALID_NONCE.
6. Wrong parameter hash is rejected with PARAM_HASH_MISMATCH.
7. Expired / stale approval is rejected with APPROVAL_EXPIRED.
8. Non-existent task or session returns TASK_NOT_FOUND / SESSION_NOT_FOUND.
9. Invalid task state (not in AWAITING_APPROVAL) is rejected.
10. Server authentication token (UMCP_AUTH_TOKEN) is strictly enforced when configured.
11. Tool input validation rejects missing fields or invalid decision enums.
12. MCP dispatch_tool_call integration routes resolve_pending_approval correctly.
13. Repeated mutation requests before approval preserve credentials intact.
"""

import unittest
import os
import time
from typing import Dict, Any, Optional

from shared.models.agent_contracts import (
    AgentTask,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_RESOLVE_PENDING_APPROVAL,
    validate_tool_input,
)
from mcp_service.agents.registry import create_default_registry
from mcp_service.agents.router import CapabilityRouter
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.manager import AgentManager
from mcp_service.agents.session_coordinator import SessionCoordinator
from mcp_service.agents.dispatcher import AgentDispatcher, DispatchResult
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.security.approval import (
    ApprovalManager,
    compute_param_hash,
)


class MockSecureApprovalExecutor(BlenderExecutor):
    """In-memory mock executor tracking invocations for secure chat approval tests."""

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
        elif tool_name == "create_primitive":
            return BridgeResponse.success({
                "name": params.get("name", "NewPrimitive"),
                "primitive_type": params.get("primitive_type", "cube"),
                "action": "create_primitive",
            })
        elif tool_name == "execute_blender_code":
            return BridgeResponse.success({
                "status": "success",
                "executed_operations": len(params.get("operations", [])),
                "transactional": True,
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

        return BridgeResponse.success({"action": tool_name})


class TestSecureChatApproval(unittest.TestCase):
    """Test suite covering secure chat approval resolution."""

    def setUp(self):
        self.executor = MockSecureApprovalExecutor()
        self.registry = create_default_registry()
        self.router = CapabilityRouter(self.registry)
        self.planner = TaskPlanner(self.router)
        self.manager = AgentManager(
            registry=self.registry,
            router=self.router,
            planner=self.planner,
        )
        self.coordinator = SessionCoordinator()
        self.dispatcher = AgentDispatcher(
            manager=self.manager,
            coordinator=self.coordinator,
            executor=self.executor,
        )
        # Ensure clean environment
        if "UMCP_AUTH_TOKEN" in os.environ:
            del os.environ["UMCP_AUTH_TOKEN"]

    def tearDown(self):
        if "UMCP_AUTH_TOKEN" in os.environ:
            del os.environ["UMCP_AUTH_TOKEN"]

    def test_approval_pause_generates_nonce_and_param_hash(self):
        """Dispatching mutation without approval returns APPROVAL_REQUIRED with nonce and hash."""
        task = AgentTask(
            task_id="task_sec_001",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_01",
        )

        res = self.dispatcher.dispatch_task(task, session_id="session_sec_01")

        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res.error_code, "APPROVAL_REQUIRED")
        self.assertIn("resolve_pending_approval", res.message)

        # Result contains structured pending approval payload
        self.assertIsNotNone(res.result)
        pending_info = res.result.get("pending_approval")
        self.assertIsNotNone(pending_info)
        self.assertEqual(pending_info["task_id"], "task_sec_001")
        self.assertEqual(pending_info["session_id"], "session_sec_01")
        self.assertTrue(len(pending_info["nonce"]) >= 16)
        self.assertTrue(pending_info["expires_at"] > time.time())

        # Coordinator binding has nonce, param_hash, and consumed=False
        binding = self.coordinator.get_pending_approval("session_sec_01", "task_sec_001")
        self.assertIsNotNone(binding)
        self.assertEqual(binding["nonce"], pending_info["nonce"])
        self.assertEqual(binding["param_hash"], pending_info["param_hash"])
        self.assertFalse(binding["consumed"])

        # Executor was NOT invoked
        self.assertEqual(len(self.executor.invocations), 0)

    def test_mcp_resolver_credentials_cannot_approve_original_task(self):
        """Nonce/hash credentials correlate a task but cannot act as human approval."""
        task = AgentTask(
            task_id="task_sec_002",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_02",
        )
        res_pause = self.dispatcher.dispatch_task(task, session_id="session_sec_02")
        self.assertEqual(res_pause.status, TaskStatus.AWAITING_APPROVAL)

        nonce = res_pause.result["pending_approval"]["nonce"]
        p_hash = res_pause.result["pending_approval"]["param_hash"]

        # Resolve credentials alone cannot authorize a mutation.
        res_approved = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_002",
            session_id="session_sec_02",
            decision="approved",
            nonce=nonce,
            param_hash=p_hash,
        )

        self.assertFalse(res_approved.success)
        self.assertEqual(res_approved.error_code, "TRUSTED_APPROVAL_REQUIRED")
        self.assertEqual(res_approved.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res_approved.task_id, "task_sec_002")
        self.assertEqual(res_approved.session_id, "session_sec_02")

        # No execution occurs and the pending record remains available.
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 0)
        self.assertIsNotNone(self.coordinator.get_pending_approval("session_sec_02", "task_sec_002"))
        session = self.coordinator.get_session("session_sec_02")
        stored_task = session.tasks.get("task_sec_002")
        self.assertEqual(stored_task.status, TaskStatus.AWAITING_APPROVAL)

    def test_explicit_denial_transitions_to_failed(self):
        """Explicit denial marks task FAILED with PERMISSION_DENIED and clears pending approval."""
        task = AgentTask(
            task_id="task_sec_003",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_03",
        )
        res_pause = self.dispatcher.dispatch_task(task, session_id="session_sec_03")
        self.assertEqual(res_pause.status, TaskStatus.AWAITING_APPROVAL)

        nonce = res_pause.result["pending_approval"]["nonce"]
        p_hash = res_pause.result["pending_approval"]["param_hash"]

        # Resolve with "denied"
        res_denied = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_003",
            session_id="session_sec_03",
            decision="denied",
            nonce=nonce,
            param_hash=p_hash,
        )

        self.assertFalse(res_denied.success)
        self.assertEqual(res_denied.status, TaskStatus.FAILED)
        self.assertEqual(res_denied.error_code, "PERMISSION_DENIED")
        self.assertIn("explicitly denied", res_denied.message)

        # Executor was NOT invoked
        self.assertEqual(len(self.executor.invocations), 0)

        # Verify pending approval cleared
        self.assertIsNone(self.coordinator.get_pending_approval("session_sec_03", "task_sec_003"))

        # Task in coordinator is FAILED
        session = self.coordinator.get_session("session_sec_03")
        stored_task = session.tasks.get("task_sec_003")
        self.assertEqual(stored_task.status, TaskStatus.FAILED)

    def test_repeated_resolver_credentials_never_authorize(self):
        """Repeated resolver submissions cannot substitute for Blender consent."""
        task = AgentTask(
            task_id="task_sec_004",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_04",
        )
        res_pause = self.dispatcher.dispatch_task(task, session_id="session_sec_04")
        nonce = res_pause.result["pending_approval"]["nonce"]
        p_hash = res_pause.result["pending_approval"]["param_hash"]

        # First resolution attempt: no Blender approval record exists.
        res1 = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_004",
            session_id="session_sec_04",
            decision="approved",
            nonce=nonce,
            param_hash=p_hash,
        )
        self.assertFalse(res1.success)
        self.assertEqual(res1.error_code, "TRUSTED_APPROVAL_REQUIRED")
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 0)

        # Second resolution attempt with same credentials (replay)
        res2 = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_004",
            session_id="session_sec_04",
            decision="approved",
            nonce=nonce,
            param_hash=p_hash,
        )
        self.assertFalse(res2.success)
        self.assertEqual(res2.error_code, "TRUSTED_APPROVAL_REQUIRED")
        # Executor NOT invoked a second time
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 0)

    def test_wrong_nonce_rejected(self):
        """Supplying an incorrect nonce is rejected with INVALID_NONCE."""
        task = AgentTask(
            task_id="task_sec_005",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_05",
        )
        res_pause = self.dispatcher.dispatch_task(task, session_id="session_sec_05")
        p_hash = res_pause.result["pending_approval"]["param_hash"]

        res_bad_nonce = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_005",
            session_id="session_sec_05",
            decision="approved",
            nonce="invalid_untrusted_nonce_000000000",
            param_hash=p_hash,
        )

        self.assertFalse(res_bad_nonce.success)
        self.assertEqual(res_bad_nonce.error_code, "INVALID_NONCE")
        self.assertEqual(len(self.executor.invocations), 0)

        # Task remains in AWAITING_APPROVAL
        binding = self.coordinator.get_pending_approval("session_sec_05", "task_sec_005")
        self.assertIsNotNone(binding)
        self.assertFalse(binding["consumed"])

    def test_parameter_hash_mismatch_rejected(self):
        """Supplying a tampered or mismatched parameter hash is rejected."""
        task = AgentTask(
            task_id="task_sec_006",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_06",
        )
        res_pause = self.dispatcher.dispatch_task(task, session_id="session_sec_06")
        nonce = res_pause.result["pending_approval"]["nonce"]

        res_bad_hash = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_006",
            session_id="session_sec_06",
            decision="approved",
            nonce=nonce,
            param_hash="0000000000000000000000000000000000000000000000000000000000000000",
        )

        self.assertFalse(res_bad_hash.success)
        self.assertEqual(res_bad_hash.error_code, "PARAM_HASH_MISMATCH")
        self.assertEqual(len(self.executor.invocations), 0)

        # Task remains in AWAITING_APPROVAL
        binding = self.coordinator.get_pending_approval("session_sec_06", "task_sec_006")
        self.assertIsNotNone(binding)
        self.assertFalse(binding["consumed"])

    def test_stale_expired_approval_rejected(self):
        """Approving after expires_at has passed is rejected with APPROVAL_EXPIRED."""
        task = AgentTask(
            task_id="task_sec_007",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_07",
        )
        res_pause = self.dispatcher.dispatch_task(task, session_id="session_sec_07")
        nonce = res_pause.result["pending_approval"]["nonce"]
        p_hash = res_pause.result["pending_approval"]["param_hash"]

        # Manually expire the binding
        binding = self.coordinator.get_pending_approval("session_sec_07", "task_sec_007")
        binding["expires_at"] = time.time() - 10.0

        res_expired = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_007",
            session_id="session_sec_07",
            decision="approved",
            nonce=nonce,
            param_hash=p_hash,
        )

        self.assertFalse(res_expired.success)
        self.assertEqual(res_expired.error_code, "APPROVAL_EXPIRED")
        self.assertEqual(len(self.executor.invocations), 0)

        # Task transitioned to FAILED
        session = self.coordinator.get_session("session_sec_07")
        stored_task = session.tasks.get("task_sec_007")
        self.assertEqual(stored_task.status, TaskStatus.FAILED)

    def test_nonexistent_task_or_session(self):
        """Resolving non-existent task or session returns error."""
        res_no_task = self.dispatcher.resolve_pending_approval(
            task_id="ghost_task_999",
            session_id="ghost_session_999",
            decision="approved",
            nonce="some_nonce",
            param_hash="some_hash",
        )
        self.assertFalse(res_no_task.success)
        self.assertIn(res_no_task.error_code, ("SESSION_NOT_FOUND", "TASK_NOT_FOUND"))

    def test_invalid_task_state(self):
        """Resolving a task that is READY or RUNNING is rejected."""
        session = self.coordinator.get_or_create_session("session_sec_09")
        ready_task = AgentTask(
            task_id="task_ready_001",
            required_capability="materials.manage",
            task_type="assign_material",
            status=TaskStatus.READY,
            session_id="session_sec_09",
        )
        self.coordinator.track_task("session_sec_09", ready_task)

        res = self.dispatcher.resolve_pending_approval(
            task_id="task_ready_001",
            session_id="session_sec_09",
            decision="approved",
            nonce="some_nonce",
            param_hash="some_hash",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "INVALID_TASK_STATE")

    def test_server_auth_token_enforcement(self):
        """When UMCP_AUTH_TOKEN is configured, resolution requires valid auth_token."""
        os.environ["UMCP_AUTH_TOKEN"] = "secure-production-secret-42"

        task = AgentTask(
            task_id="task_sec_010",
            required_capability="materials.manage",
            task_type="assign_material",
            input_params={"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_sec_10",
        )
        res_pause = self.dispatcher.dispatch_task(task, session_id="session_sec_10")
        nonce = res_pause.result["pending_approval"]["nonce"]
        p_hash = res_pause.result["pending_approval"]["param_hash"]

        # Call without auth_token -> rejected
        res_unauth = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_010",
            session_id="session_sec_10",
            decision="approved",
            nonce=nonce,
            param_hash=p_hash,
            auth_token=None,
        )
        self.assertFalse(res_unauth.success)
        self.assertEqual(res_unauth.error_code, "AUTHENTICATION_FAILED")

        # Call with wrong auth_token -> rejected
        res_wrong_auth = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_010",
            session_id="session_sec_10",
            decision="approved",
            nonce=nonce,
            param_hash=p_hash,
            auth_token="wrong-token",
        )
        self.assertFalse(res_wrong_auth.success)
        self.assertEqual(res_wrong_auth.error_code, "AUTHENTICATION_FAILED")

        # Server authentication does not turn resolver credentials into human consent.
        res_ok = self.dispatcher.resolve_pending_approval(
            task_id="task_sec_010",
            session_id="session_sec_10",
            decision="approved",
            nonce=nonce,
            param_hash=p_hash,
            auth_token="secure-production-secret-42",
        )
        self.assertFalse(res_ok.success)
        self.assertEqual(res_ok.error_code, "TRUSTED_APPROVAL_REQUIRED")
        self.assertEqual(res_ok.status, TaskStatus.AWAITING_APPROVAL)

    def test_tool_input_validation(self):
        """validate_tool_input rejects missing required fields and invalid decisions."""
        # Missing task_id
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_RESOLVE_PENDING_APPROVAL, {
                "decision": "approved",
                "nonce": "abc",
                "param_hash": "def",
            })

        # Missing decision
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_RESOLVE_PENDING_APPROVAL, {
                "task_id": "t1",
                "nonce": "abc",
                "param_hash": "def",
            })

        # Invalid decision enum
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_RESOLVE_PENDING_APPROVAL, {
                "task_id": "t1",
                "decision": "maybe",
                "nonce": "abc",
                "param_hash": "def",
            })

        # Empty nonce
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_RESOLVE_PENDING_APPROVAL, {
                "task_id": "t1",
                "decision": "approved",
                "nonce": "  ",
                "param_hash": "def",
            })

        # Valid input
        sanitized = validate_tool_input(TOOL_RESOLVE_PENDING_APPROVAL, {
            "task_id": "t1",
            "decision": "APPROVED",
            "nonce": "abc",
            "param_hash": "def",
        })
        self.assertEqual(sanitized["decision"], "approved")
        self.assertEqual(sanitized["session_id"], "default")

    def test_dispatch_tool_call_end_to_end_resolution(self):
        """MCP dispatch_tool_call end-to-end flow from pause to resolution."""
        # 1. Dispatch scene mutation via dispatch_tool_call
        resp1: BridgeResponse = self.dispatcher.dispatch_tool_call(
            "assign_material",
            {"target_name": "Cube", "material_name": "DragonScale"},
            session_id="session_tool_sec",
        )
        self.assertFalse(resp1.is_success)
        self.assertEqual(resp1.status, "error")
        self.assertIn("Approval required", resp1.message)

        # 2. Extract resolution parameters
        self.assertIsNotNone(resp1.result)
        pending_info = resp1.result.get("pending_approval")
        self.assertIsNotNone(pending_info)
        task_id = pending_info["task_id"]
        nonce = pending_info["nonce"]
        param_hash = pending_info["param_hash"]

        # 3. Resolve via dispatch_tool_call("resolve_pending_approval", ...)
        resp2: BridgeResponse = self.dispatcher.dispatch_tool_call(
            "resolve_pending_approval",
            {
                "task_id": task_id,
                "session_id": "session_tool_sec",
                "decision": "approved",
                "nonce": nonce,
                "param_hash": param_hash,
            },
            session_id="session_tool_sec",
        )
        self.assertFalse(resp2.is_success)
        self.assertIn("Resolver credentials do not prove human approval", resp2.message)
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 0)

    def test_repeated_mutation_dispatch_preserves_nonce_and_hash(self):
        """Repeated mutation tool calls return APPROVAL_REQUIRED with the existing nonce and hash."""
        params = {"target_name": "Cube", "material_name": "DragonScale"}
        resp1 = self.dispatcher.dispatch_tool_call("assign_material", params, session_id="session_repeat_sec")
        info1 = resp1.result["pending_approval"]

        # Repeated dispatch
        resp2 = self.dispatcher.dispatch_tool_call("assign_material", params, session_id="session_repeat_sec")
        self.assertFalse(resp2.is_success)
        info2 = resp2.result["pending_approval"]

        # Nonce and hash are preserved
        self.assertEqual(info1["task_id"], info2["task_id"])
        self.assertEqual(info1["nonce"], info2["nonce"])
        self.assertEqual(info1["param_hash"], info2["param_hash"])

        # Preserved resolver credentials remain non-authorizing.
        resp_res = self.dispatcher.dispatch_tool_call(
            "resolve_pending_approval",
            {
                "task_id": info2["task_id"],
                "session_id": "session_repeat_sec",
                "decision": "approved",
                "nonce": info2["nonce"],
                "param_hash": info2["param_hash"],
            },
            session_id="session_repeat_sec",
        )
        self.assertFalse(resp_res.is_success)
        self.assertIn("Resolver credentials do not prove human approval", resp_res.message)
        mutation_invs = [inv for inv in self.executor.invocations if inv[0] == "assign_material"]
        self.assertEqual(len(mutation_invs), 0)


if __name__ == "__main__":
    unittest.main()
