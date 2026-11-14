"""Public approval-status contract tests; all registry/bridge objects are isolated fixtures."""
import asyncio
import copy
import json
import time
import unittest
from unittest.mock import Mock, patch

import mcp.types as types

from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry, ApprovalRequestSnapshot
from blender_addon.universal_mcp.bridge.handlers import (
    ALL_HANDLERS, READ_ONLY_HANDLERS, handle_inspect_approval_status,
)
from mcp_service.agents.dispatcher import AgentDispatcher
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.server.mcp_server import create_mcp_server
from shared.schemas.tool_schemas import TOOL_CHECK_APPROVAL_STATUS, validate_tool_input


class TestPublicApprovalStatus(unittest.TestCase):
    def setUp(self):
        self.registry = ApprovalRegistry()
        self.req = self.registry.create_request(
            "create_material", {"name": "OfflineFixture", "private_parameter": "not-public"},
            request_id="offline-request", timeout=30.0,
        )
        self.executor = BlenderExecutor()
        self.client = Mock()
        self.executor.client = self.client
        self.dispatcher = AgentDispatcher(executor=self.executor)

        def send(command, params):
            self.assertEqual(command, "inspect_approval_status")
            with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=self.registry):
                return {"status": "success", "result": handle_inspect_approval_status(params=params)}
        self.client.send_command.side_effect = send

    def query(self):
        return self.dispatcher.dispatch_tool_call(TOOL_CHECK_APPROVAL_STATUS, {"request_id": self.req.request_id})

    def registry_state(self):
        return (
            self.req.status, self.req.approval_token, self.req.executed, self.req.event.is_set(),
            dict(self.registry._tokens), tuple(self.registry._requests), tuple(self.registry._recent_requests),
        )

    def test_discovery_and_mcp_invocation(self):
        tool = ToolRegistry().get_tool_definition(TOOL_CHECK_APPROVAL_STATUS)
        self.assertEqual(tool["permission_tier"], "READ_ONLY")
        self.assertEqual(tool["input_schema"]["required"], ["request_id"])
        self.assertFalse(tool["input_schema"]["additionalProperties"])
        server = create_mcp_server(executor=self.executor, dispatcher=self.dispatcher)
        catalog = asyncio.run(server.request_handlers[types.ListToolsRequest](types.ListToolsRequest()))
        self.assertIn(TOOL_CHECK_APPROVAL_STATUS, {t.name for t in catalog.root.tools})
        request = types.CallToolRequest(params=types.CallToolRequestParams(
            name=TOOL_CHECK_APPROVAL_STATUS, arguments={"request_id": self.req.request_id}
        ))
        response = asyncio.run(server.request_handlers[types.CallToolRequest](request))
        self.assertEqual(json.loads(response.root.content[0].text)["result"]["status"], "pending")

    def test_bridge_registration_is_read_only(self):
        self.assertIs(ALL_HANDLERS["inspect_approval_status"], handle_inspect_approval_status)
        self.assertIs(READ_ONLY_HANDLERS["inspect_approval_status"], handle_inspect_approval_status)

    def test_query_states_are_token_free_and_do_not_resume_or_consume(self):
        for status in ("pending", "approved", "denied", "cancelled", "expired"):
            with self.subTest(status=status):
                # Fixture state, not an approval operation against a Blender session.
                self.req.status = status
                self.req.approval_token = "offline-private-credential"
                before = self.registry_state()
                result = self.query()
                self.assertTrue(result.is_success)
                self.assertEqual(result.result["status"], status)
                self.assertFalse(result.result["token_consumed"])
                self.assertNotIn("offline-private-credential", json.dumps(result.result))
                self.assertFalse({"approval_token", "params", "nonce", "decision_reason", "executed"} & set(result.result))
                self.assertEqual(self.registry_state(), before)
                self.assertEqual(self.dispatcher.coordinator.active_session_count, 0)

    def test_expired_pending_is_effective_state_without_registry_transition(self):
        self.req.created_at = time.time() - 100.0
        before = self.registry_state()
        for _ in range(2):
            result = self.query()
            self.assertEqual(result.result["status"], "expired")
            self.assertEqual(result.result["remaining_seconds"], 0.0)
        self.assertEqual(self.registry_state(), before)
        self.assertEqual(self.req.status, "pending")
        self.assertFalse(self.req.event.is_set())

    def test_consumption_is_not_claimed_as_successful_execution(self):
        self.req.status = "approved"
        self.req.executed = True
        result = self.query().result
        self.assertTrue(result["token_consumed"])
        self.assertEqual(result["status"], "approved")
        self.assertNotIn("success", result)
        self.assertNotIn("execution_succeeded", result)

    def test_approved_state_is_not_changed_at_pending_deadline(self):
        self.req.status = "approved"
        self.req.created_at = time.time() - self.req.timeout_seconds - 1
        self.assertEqual(self.query().result["status"], "approved")
        self.assertFalse(self.req.executed)

    def test_terminal_archive_is_visible_without_restoring_authority(self):
        self.req.status = "denied"
        self.req.created_at = time.time() - 700.0
        self.registry._recent_requests[self.req.request_id] = ApprovalRequestSnapshot(self.req)
        self.registry._requests.clear()
        before = self.registry_state()
        result = self.query().result
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["record_source"], "archive")
        self.assertEqual(self.registry_state(), before)

    def test_archive_expiry_does_not_purge(self):
        self.req.status = "expired"
        self.req.created_at = time.time() - 4000.0
        self.registry._recent_requests[self.req.request_id] = ApprovalRequestSnapshot(self.req)
        self.registry._requests.clear()
        before = self.registry_state()
        self.assertEqual(self.query().result["status"], "not_found")
        self.assertEqual(self.registry_state(), before)

    def test_registry_purge_or_reload_is_not_reported_as_pending(self):
        for registry in (self.registry, ApprovalRegistry()):
            registry._requests.clear()
            with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry):
                result = handle_inspect_approval_status(params={"request_id": self.req.request_id})
            self.assertEqual(result, {"request_id": self.req.request_id, "status": "not_found"})

    def test_unknown_record_state_is_explicit(self):
        self.req.status = "unexpected-fixture-state"
        self.assertEqual(self.query().result["status"], "unknown")

    def test_validation_rejects_credentials_flags_and_non_string_ids(self):
        for value in (None, "", " ", 12, [], True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_tool_input(TOOL_CHECK_APPROVAL_STATUS, {"request_id": value})
        for key in ("approved", "trusted_approval", "approval_token", "nonce", "include_token", "session_id"):
            with self.subTest(key=key):
                args = {"request_id": "offline-request", key: True}
                with self.assertRaises(ValueError):
                    validate_tool_input(TOOL_CHECK_APPROVAL_STATUS, args)
                with self.assertRaises(ValueError):
                    handle_inspect_approval_status(params=args)
        self.assertEqual(validate_tool_input(TOOL_CHECK_APPROVAL_STATUS, {"request_id": " id "}), {"request_id": "id"})

    def test_public_projection_discards_unexpected_private_fields(self):
        raw = self.registry.inspect_request_status(self.req.request_id)
        raw.update({"approval_token": "private", "params": {"credential": "private"}, "nonce": "private"})
        self.client.send_command.side_effect = None
        self.client.send_command.return_value = {"status": "success", "result": raw}
        result = self.query()
        self.assertTrue(result.is_success)
        self.assertNotIn("private", json.dumps(result.result))

    def test_unavailable_or_malformed_source_never_claims_pending_or_leaks_errors(self):
        responses = (
            {"status": "error", "message": "sensitive transport diagnostic"},
            {"status": "success", "result": None},
            {"status": "success", "result": {"status": "pending", "request_id": "wrong-request"}},
        )
        self.client.send_command.side_effect = None
        for response in responses:
            self.client.send_command.return_value = response
            result = self.query()
            self.assertFalse(result.is_success)
            self.assertIn("unavailable", result.message)
            self.assertNotIn("sensitive", result.message)
            self.assertIsNone(result.result)
        self.client.send_command.side_effect = RuntimeError("sensitive transport diagnostic")
        self.assertNotIn("sensitive", self.query().message)

    def test_nested_malformed_metadata_is_rejected(self):
        raw = self.registry.inspect_request_status(self.req.request_id)
        raw["task_id"] = {"approval_token": "private"}
        self.client.send_command.side_effect = None
        self.client.send_command.return_value = {"status": "success", "result": raw}
        self.assertFalse(self.query().is_success)
