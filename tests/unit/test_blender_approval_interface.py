"""
Comprehensive test suite for Blender Human Approval Interface.
Tests all requirements for TASK-UMCP-0003:
- Approval flow & token issuance
- Explicit denial fail-closed
- Timeout fail-closed
- Dialog cancellation fail-closed
- Replay attack prevention (single-use token)
- Argument tampering prevention (SHA-256 parameter binding)
- Duplicate decision rejection
- Concurrent request isolation
- Bridge approval provider non-blocking polling
"""

import time
import threading
import unittest
from unittest.mock import MagicMock

from blender_addon.universal_mcp.bridge.approval_registry import (
    ApprovalRegistry,
    ApprovalRequest,
    compute_arg_hash,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_request_approval,
    handle_check_approval_status,
    handle_resolve_approval,
    handle_create_primitive,
)
from mcp_service.security.approval import (
    ApprovalManager,
    ApprovalDecision,
    create_blender_bridge_approval_provider,
)
from mcp_service.execution.blender_executor import BlenderExecutor


class TestBlenderApprovalInterface(unittest.TestCase):
    """Targeted tests for Blender-native human approval lifecycle and security constraints."""

    def setUp(self):
        self.registry = ApprovalRegistry()

    def test_approval_success(self):
        """Human approval issues single-use token and permits scene mutation."""
        params = {
            "primitive_type": "cube",
            "name": "ApprovedBox",
            "location": [1.0, 2.0, 3.0],
            "dimensions": [1.5, 1.5, 1.5],
        }
        req = self.registry.create_request("create_primitive", params, timeout=30.0)
        self.assertEqual(req.status, "pending")
        self.assertFalse(req.executed)

        # User approves via UI operator / registry
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)
        self.assertIsNotNone(token)
        self.assertEqual(req.status, "approved")

        # Consume token with exact matching arguments
        consumed, msg = self.registry.consume_approval(req.request_id, token, "create_primitive", params)
        self.assertTrue(consumed)
        self.assertTrue(req.executed)

    def test_denial_fails_closed(self):
        """User denial transitions request to 'denied' and rejects execution."""
        params = {"primitive_type": "sphere", "name": "DeniedSphere"}
        req = self.registry.create_request("create_primitive", params, timeout=30.0)

        # User clicks Deny
        ok, msg = self.registry.resolve_request(req.request_id, "denied", reason="Rejected by user")
        self.assertTrue(ok)
        self.assertEqual(req.status, "denied")

        # Attempt to consume approval fails closed
        consumed, err = self.registry.consume_approval(req.request_id, "fake_token", "create_primitive", params)
        self.assertFalse(consumed)
        self.assertIn("rejected", err.lower())

    def test_timeout_fails_closed(self):
        """Unanswered approval request expires and fails closed."""
        params = {"primitive_type": "cylinder", "name": "TimedOutCylinder"}
        # Configure very short timeout of 0.05 seconds
        req = self.registry.create_request("create_primitive", params, timeout=0.05)
        time.sleep(0.08)

        self.assertTrue(req.is_expired)
        # Attempt to resolve after timeout is rejected
        ok, msg = self.registry.resolve_request(req.request_id, "approved")
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())

        # Attempt to consume is rejected
        consumed, err = self.registry.consume_approval(req.request_id, req.approval_token, "create_primitive", params)
        self.assertFalse(consumed)

    def test_cancellation_fails_closed(self):
        """User closing or escaping the dialog transitions request to 'cancelled' and fails closed."""
        params = {"primitive_type": "plane", "name": "CancelledPlane"}
        req = self.registry.create_request("create_primitive", params, timeout=30.0)

        # Dialog cancelled
        ok, msg = self.registry.resolve_request(req.request_id, "cancelled", reason="Dialog closed by user")
        self.assertTrue(ok)
        self.assertEqual(req.status, "cancelled")

        consumed, err = self.registry.consume_approval(req.request_id, "dummy_token", "create_primitive", params)
        self.assertFalse(consumed)
        self.assertIn("cancelled", err.lower())

    def test_replay_attack_rejected(self):
        """An approval token can only be consumed once; second attempt is rejected as replay."""
        params = {"primitive_type": "cube", "name": "ReplayBox"}
        req = self.registry.create_request("create_primitive", params, timeout=30.0)
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # First consumption succeeds
        c1, m1 = self.registry.consume_approval(req.request_id, token, "create_primitive", params)
        self.assertTrue(c1)

        # Replay attempt with same token and request ID is rejected
        c2, m2 = self.registry.consume_approval(req.request_id, token, "create_primitive", params)
        self.assertFalse(c2)
        self.assertIn("Replay rejected", m2)

    def test_argument_tampering_rejected(self):
        """
        If parameters are modified after user approved, the SHA-256 hash
        mismatches and execution is blocked.
        """
        approved_params = {
            "primitive_type": "cube",
            "name": "OriginalBox",
            "location": [0.0, 0.0, 0.0],
            "dimensions": [1.0, 1.0, 1.0],
        }
        req = self.registry.create_request("create_primitive", approved_params, timeout=30.0)
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # Attacker modifies dimensions and location
        tampered_params = {
            "primitive_type": "cube",
            "name": "OriginalBox",
            "location": [10.0, 20.0, 30.0],
            "dimensions": [50.0, 50.0, 50.0],
        }

        consumed, err = self.registry.consume_approval(req.request_id, token, "create_primitive", tampered_params)
        self.assertFalse(consumed)
        self.assertIn("Argument tampering detected", err)

    def test_duplicate_decision_rejected(self):
        """Once resolved, subsequent approval or denial decisions on the same request are rejected."""
        params = {"primitive_type": "cube", "name": "Box"}
        req = self.registry.create_request("create_primitive", params, timeout=30.0)

        # First decision: Approved
        ok1, tok1 = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok1)

        # Duplicate decision: Denied attempt on already approved request
        ok2, err2 = self.registry.resolve_request(req.request_id, "denied")
        self.assertFalse(ok2)
        self.assertIn("Duplicate decision rejected", err2)

    def test_concurrent_requests_isolated(self):
        """Concurrent pending requests maintain independent state and isolated token binding."""
        results = {}

        def thread_worker(name, decision):
            p = {"primitive_type": "cube", "name": name}
            req = self.registry.create_request("create_primitive", p, timeout=10.0)
            ok, val = self.registry.resolve_request(req.request_id, decision)
            results[name] = {"req": req, "ok": ok, "val": val, "params": p}

        t1 = threading.Thread(target=thread_worker, args=("BoxA", "approved"))
        t2 = threading.Thread(target=thread_worker, args=("BoxB", "denied"))
        t3 = threading.Thread(target=thread_worker, args=("BoxC", "approved"))

        t1.start()
        t2.start()
        t3.start()
        t1.join()
        t2.join()
        t3.join()

        self.assertEqual(len(results), 3)
        self.assertEqual(results["BoxA"]["req"].status, "approved")
        self.assertEqual(results["BoxB"]["req"].status, "denied")
        self.assertEqual(results["BoxC"]["req"].status, "approved")

        token_a = results["BoxA"]["val"]
        token_c = results["BoxC"]["val"]
        self.assertNotEqual(token_a, token_c)

        # Token A cannot consume Box C
        cross_consume, cross_err = self.registry.consume_approval(
            results["BoxC"]["req"].request_id, token_a, "create_primitive", results["BoxC"]["params"]
        )
        self.assertFalse(cross_consume)

    def test_blender_bridge_approval_provider_flow(self):
        """Tests the asynchronous non-blocking polling provider via mock bridge."""
        mock_bridge = MagicMock()
        mock_bridge.send_command.side_effect = [
            # 1. request_approval response
            {"status": "success", "result": {"request_id": "req_123"}},
            # 2. check_approval_status (pending)
            {"status": "success", "result": {"status": "pending"}},
            # 3. check_approval_status (approved)
            {"status": "success", "result": {"status": "approved", "approval_token": "tok_xyz456"}},
        ]

        provider = create_blender_bridge_approval_provider(mock_bridge, timeout=2.0)
        decision = provider("create_primitive", {"primitive_type": "cube", "name": "AsyncBox"})

        self.assertTrue(decision.approved)
        self.assertEqual(decision.approval_token, "tok_xyz456")
        self.assertEqual(decision.request_id, "req_123")

    def test_executor_with_blender_approval_end_to_end(self):
        """Tests BlenderExecutor executing an approved tool using issued credentials."""
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.send_command.side_effect = [
            # 1. request_approval in Blender
            {"status": "success", "result": {"request_id": "req_abc"}},
            # 2. check_approval_status in Blender
            {"status": "success", "result": {"status": "approved", "approval_token": "token_approved_123"}},
            # 3. create_primitive execution with credentials
            {"status": "success", "result": {"created": True, "name": "LiveBox"}},
        ]

        executor = BlenderExecutor()
        executor.client = mock_bridge
        executor.enable_blender_approval(timeout=5.0)

        resp = executor.execute_tool("create_primitive", {
            "primitive_type": "cube",
            "name": "LiveBox",
            "location": [0.0, 0.0, 0.0],
            "dimensions": [1.0, 1.0, 1.0],
        })

        self.assertEqual(resp.status, "success")
        self.assertTrue(resp.result.get("created"))
        # Verify credentials were passed to Blender execution command
        exec_call = mock_bridge.send_command.call_args_list[-1]
        cmd_name, cmd_params = exec_call[0]
        self.assertEqual(cmd_name, "create_primitive")
        self.assertEqual(cmd_params.get("approval_token"), "token_approved_123")
        self.assertEqual(cmd_params.get("request_id"), "req_abc")

    def test_mcp_entrypoint_initializes_blender_approval(self):
        """TASK-UMCP-0004: MCP entry point initializes Blender approval provider on executor."""
        from mcp_service.configuration.settings import Settings
        from mcp_service.execution.blender_executor import BlenderExecutor
        from mcp_service.server.mcp_server import create_mcp_server

        settings = Settings(bridge_host="127.0.0.1", bridge_port=9877, bridge_timeout=15.0)
        executor = BlenderExecutor(
            host=settings.bridge_host,
            port=settings.bridge_port,
            timeout=settings.bridge_timeout,
        )
        # Verify before initialization
        self.assertFalse(executor.approval_manager.has_provider)

        # Wire approval provider as app.py does
        executor.enable_blender_approval(timeout=settings.bridge_timeout)
        self.assertTrue(executor.approval_manager.has_provider)

        server = create_mcp_server(executor=executor)
        server_executor = getattr(server, "_blender_executor")
        self.assertTrue(server_executor.approval_manager.has_provider)

    def test_schema_defaults_applied_before_hash_calculation(self):
        """TASK-UMCP-0004: Schema defaults are applied before parameter hash calculation preventing false mismatches."""
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True

        captured_requests = []

        def mock_send(cmd, params):
            if cmd == "request_approval":
                captured_requests.append(dict(params))
                # Compute real hash using ApprovalRegistry's compute_arg_hash
                arg_hash = compute_arg_hash(params["tool_name"], params["params"])
                return {
                    "status": "success",
                    "result": {"request_id": "req_defaults", "arg_hash": arg_hash},
                }
            elif cmd == "check_approval_status":
                return {
                    "status": "success",
                    "result": {"status": "approved", "approval_token": "token_defaults_valid"},
                }
            elif cmd == "create_primitive":
                captured_requests.append(dict(params))
                # Verify that params match what was approved
                return {"status": "success", "result": {"created": True, "name": params["name"]}}
            return {"status": "error", "message": f"Unexpected command {cmd}"}

        mock_bridge.send_command.side_effect = mock_send

        executor = BlenderExecutor()
        executor.client = mock_bridge
        executor.enable_blender_approval(timeout=5.0)

        # Call with only required parameters (missing location and dimensions)
        resp = executor.execute_tool("create_primitive", {
            "primitive_type": "cube",
            "name": "DefaultCube",
        })

        self.assertEqual(resp.status, "success")
        self.assertTrue(resp.result.get("created"))

        # 1. Verify request_approval received normalized arguments with schema defaults
        req_approval_call = captured_requests[0]
        req_params = req_approval_call["params"]
        self.assertEqual(req_params["primitive_type"], "cube")
        self.assertEqual(req_params["name"], "DefaultCube")
        self.assertEqual(req_params["location"], [0.0, 0.0, 0.0])
        self.assertEqual(req_params["dimensions"], [1.0, 1.0, 1.0])

        # 2. Verify execution call received exact matching arguments
        exec_call_params = captured_requests[1]
        self.assertEqual(exec_call_params["location"], [0.0, 0.0, 0.0])
        self.assertEqual(exec_call_params["dimensions"], [1.0, 1.0, 1.0])
        self.assertEqual(exec_call_params["approval_token"], "token_defaults_valid")
        self.assertEqual(exec_call_params["request_id"], "req_defaults")

        # 3. Verify hashes computed at request and execution match identically
        h1 = compute_arg_hash("create_primitive", req_params)
        h2 = compute_arg_hash("create_primitive", exec_call_params)
        self.assertEqual(h1, h2, "Hash mismatch: Defaults were not applied consistently!")

    def test_model_supplied_approved_true_cannot_bypass_approval(self):
        """TASK-UMCP-0004: Model-supplied 'approved=True' cannot authorize mutation or bypass approval."""
        mock_bridge = MagicMock()
        mock_bridge.send_command.side_effect = [
            # 1. request_approval in Blender
            {"status": "success", "result": {"request_id": "req_bypass_attempt"}},
            # 2. check_approval_status reports user explicitly denied
            {"status": "success", "result": {"status": "denied", "decision_reason": "User denied in Blender"}},
        ]

        executor = BlenderExecutor()
        executor.client = mock_bridge
        executor.enable_blender_approval(timeout=5.0)

        # Model supplies approved=True attempting to bypass consent
        resp = executor.execute_tool("create_primitive", {
            "primitive_type": "cube",
            "name": "BypassCube",
            "approved": True,
        })

        self.assertEqual(resp.status, "error")
        self.assertIn("Approval denied", resp.message)
        self.assertIn("untrusted", resp.message)
        # Verify create_primitive was NOT dispatched
        for call_item in mock_bridge.send_command.call_args_list:
            self.assertNotEqual(call_item[0][0], "create_primitive")

    def test_end_to_end_tampering_and_replay_protection(self):
        """TASK-UMCP-0004: Validates tamper detection and token replay fail-closed against live ApprovalRegistry."""
        from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry

        live_registry = ApprovalRegistry()

        class RegistryBridgeClient:
            def __init__(self):
                self.tamper_on_create = False
                self.last_req = None

            def send_command(self, cmd, params):
                if cmd == "request_approval":
                    req = live_registry.create_request(params["tool_name"], params["params"], timeout=params["timeout"])
                    self.last_req = req
                    # Simulate human approving in Blender
                    live_registry.resolve_request(req.request_id, "approved")
                    return {"status": "success", "result": {"request_id": req.request_id}}
                elif cmd == "check_approval_status":
                    req = live_registry.get_request(params["request_id"])
                    return {
                        "status": "success",
                        "result": {
                            "status": req.status,
                            "approval_token": req.approval_token,
                        },
                    }
                elif cmd == "create_primitive":
                    p = dict(params)
                    if self.tamper_on_create:
                        p["dimensions"] = [99.0, 99.0, 99.0]
                    consumed, msg = live_registry.consume_approval(
                        p.get("request_id"), p.get("approval_token"), "create_primitive", p
                    )
                    if not consumed:
                        return {"status": "error", "message": f"Scene mutation denied: {msg}"}
                    return {"status": "success", "result": {"created": True, "name": p["name"]}}
                return {"status": "error", "message": f"Unknown {cmd}"}

        bridge_client = RegistryBridgeClient()
        executor = BlenderExecutor()
        executor.client = bridge_client
        executor.enable_blender_approval(timeout=5.0)

        # 1. Normal execution with schema defaults succeeds
        resp1 = executor.execute_tool("create_primitive", {"primitive_type": "cube", "name": "SuccessCube"})
        self.assertEqual(resp1.status, "success")
        self.assertTrue(resp1.result.get("created"))

        # 2. Token replay fails closed
        req_id = bridge_client.last_req.request_id
        tok = bridge_client.last_req.approval_token
        replayed, msg = live_registry.consume_approval(req_id, tok, "create_primitive", {
            "primitive_type": "cube",
            "name": "SuccessCube",
            "location": [0.0, 0.0, 0.0],
            "dimensions": [1.0, 1.0, 1.0],
        })
        self.assertFalse(replayed)
        self.assertIn("Replay rejected", msg)

        # 3. Argument tampering fails closed
        bridge_client.tamper_on_create = True
        resp2 = executor.execute_tool("create_primitive", {"primitive_type": "cube", "name": "TamperedCube"})
        self.assertEqual(resp2.status, "error")
        self.assertIn("Argument tampering detected", resp2.message)


if __name__ == "__main__":
    unittest.main()

