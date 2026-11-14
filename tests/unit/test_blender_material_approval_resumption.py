"""Regression tests for Blender-registry-backed create_material approval resumption."""

import time
import unittest
from unittest.mock import patch

from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import handle_create_material
from mcp_service.agents.dispatcher import AgentDispatcher
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.security.approval import compute_param_hash
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.schemas.tool_schemas import TOOL_CREATE_MATERIAL


class _FakeMaterial:
    def __init__(self, name):
        self.name = name
        self.use_nodes = False
        self.node_tree = None


class _FakeMaterials:
    def __init__(self):
        self.created = []
        self.fail_with = None

    def new(self, name):
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        material = _FakeMaterial(name)
        self.created.append(material)
        return material


class _FakeBpy:
    def __init__(self):
        self.data = type("Data", (), {"materials": _FakeMaterials()})()


class _FakeBlenderBridge:
    def __init__(self, registry):
        self.registry = registry
        self.bpy = _FakeBpy()
        self.created_results = []
        self.invalid_status_token = None
        self.status_calls = []
        self.status_error = None
        self.status_override = None
        self.status_sequence = []

    def send_command(self, command, params):
        if command == "request_approval":
            req = self.registry.create_request(
                params["tool_name"],
                params.get("params", {}),
                timeout=params.get("timeout", 30.0),
                task_id=params.get("task_id"),
            )
            return {
                "status": "success",
                "result": {
                    "request_id": req.request_id,
                    "tool_name": req.tool_name,
                    "status": req.status,
                    "expires_at": req.created_at + req.timeout_seconds,
                },
            }
        if command == "check_approval_status":
            self.status_calls.append(params["request_id"])
            if self.status_error:
                raise self.status_error
            if self.status_sequence:
                return {"status": "success", "result": {"status": self.status_sequence.pop(0)}}
            if self.status_override:
                return {"status": "success", "result": {"status": self.status_override}}
            req = self.registry.get_request(params["request_id"])
            if not req:
                return {"status": "success", "result": {"status": "not_found"}}
            return {
                "status": "success",
                "result": {
                    "request_id": req.request_id,
                    "status": req.status,
                    "approval_token": self.invalid_status_token or req.approval_token,
                    "expires_at": req.created_at + req.timeout_seconds,
                },
            }
        if command == TOOL_CREATE_MATERIAL:
            try:
                with patch(
                    "blender_addon.universal_mcp.bridge.handlers.get_approval_registry",
                    return_value=self.registry,
                ):
                    result = handle_create_material(self.bpy, params)
                self.created_results.append(result)
                return {"status": "success", "result": result}
            except Exception as exc:
                return {"status": "error", "message": str(exc)}
        if command == "list_materials":
            return {
                "status": "success",
                "result": {
                    "materials": [
                        {"name": material.name}
                        for material in self.bpy.data.materials.created
                        if not params.get("filter_name") or material.name == params["filter_name"]
                    ]
                },
            }
        return {"status": "error", "message": f"Unexpected bridge command: {command}"}


class TestBlenderMaterialApprovalResumption(unittest.TestCase):
    def setUp(self):
        self.registry = ApprovalRegistry()
        self.bridge = _FakeBlenderBridge(self.registry)
        self.executor = BlenderExecutor(timeout=0.001)
        self.executor.client = self.bridge
        self.executor.enable_blender_approval(timeout=0.001, pending_ttl=30.0)
        self.dispatcher = AgentDispatcher(executor=self.executor)
        self.session_id = "session-blender-material-approval"

    def _start_pending_material(self, task_id="task-blender-material-approval", name="ApprovalTestMaterial"):
        task = AgentTask(
            task_id=task_id,
            required_capability="materials.manage",
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": name},
            session_id=self.session_id,
        )
        result = self.dispatcher.dispatch_task(task, session_id=self.session_id)
        self.assertEqual(result.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(result.error_code, "APPROVAL_REQUIRED")
        pending = result.result["pending_approval"]
        self.assertTrue(pending["approval_request_id"])
        self.assertTrue(pending["nonce"])
        self.assertTrue(pending["param_hash"])
        self.assertEqual(pending["approval_status"], "pending")
        self.assertEqual(len(self.bridge.created_results), 0)
        return pending

    def _resolve(self, pending, decision="approved"):
        return self.dispatcher.resolve_pending_approval(
            task_id=pending["task_id"],
            session_id=pending["session_id"],
            decision=decision,
            nonce=pending["nonce"],
            param_hash=pending["param_hash"],
        )

    def _repeat_task(self, pending):
        task = AgentTask(
            task_id=pending["task_id"],
            required_capability="materials.manage",
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "ApprovalTestMaterial"},
            session_id=self.session_id,
        )
        return self.dispatcher.dispatch_task(task, session_id=self.session_id)

    def test_blender_provider_timeout_preserves_inspectable_pending_binding(self):
        pending = self._start_pending_material()
        binding = self.dispatcher.coordinator.get_pending_approval(self.session_id, pending["task_id"])
        self.assertEqual(binding["approval_source"], "blender")
        self.assertEqual(binding["blender_request_id"], pending["approval_request_id"])
        self.assertEqual(binding["param_hash"], compute_param_hash(TOOL_CREATE_MATERIAL, {"name": "ApprovalTestMaterial"}))

        # Resolver credentials alone cannot authorize while Blender still reports pending.
        unresolved = self._resolve(pending)
        self.assertEqual(unresolved.error_code, "APPROVAL_REQUIRED")
        self.assertEqual(unresolved.status, TaskStatus.AWAITING_APPROVAL)
        self.assertIsNotNone(self.dispatcher.coordinator.get_pending_approval(self.session_id, pending["task_id"]))
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_explicit_blender_human_approval_resumes_with_registry_token(self):
        pending = self._start_pending_material()
        ok, _token = self.registry.resolve_request(pending["approval_request_id"], "approved")
        self.assertTrue(ok)

        result = self._resolve(pending)

        self.assertTrue(result.success)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(len(self.bridge.created_results), 1)
        self.assertEqual(self.bridge.created_results[0]["name"], "ApprovalTestMaterial")
        self.assertEqual(self.bridge.bpy.data.materials.created[0].name, "ApprovalTestMaterial")
        self.assertIsNone(self.dispatcher.coordinator.get_pending_approval(self.session_id, pending["task_id"]))

    def test_task_status_query_reports_approval_then_resumes_exactly_once(self):
        pending = self._start_pending_material(task_id="task-status-approved-once")
        session = self.dispatcher.coordinator.get_session(self.session_id)
        last_active_at = session.last_active_at
        before = self.dispatcher.dispatch_tool_call(
            "get_task_status",
            {"task_id": pending["task_id"], "session_id": self.session_id},
        )
        self.assertTrue(before.is_success)
        self.assertEqual(before.result["status"], TaskStatus.AWAITING_APPROVAL.value)
        self.assertEqual(before.result["approval"]["state"], "unverified")
        self.assertEqual(session.last_active_at, last_active_at)
        self.assertEqual(len(self.bridge.created_results), 0)

        ok, _token = self.registry.resolve_request(pending["approval_request_id"], "approved")
        self.assertTrue(ok)
        # The task-status query reports stored task state; it neither resumes nor
        # claims that the Blender request remains pending.
        after_human_click = self.dispatcher.dispatch_tool_call(
            "get_task_status",
            {"task_id": pending["task_id"], "session_id": self.session_id},
        )
        self.assertEqual(after_human_click.result["status"], TaskStatus.AWAITING_APPROVAL.value)
        self.assertEqual(after_human_click.result["approval"]["state"], "unverified")
        self.assertEqual(len(self.bridge.created_results), 0)

        resumed = self._resolve(pending)
        self.assertTrue(resumed.success)
        self.assertEqual(len(self.bridge.created_results), 1)
        replay = self._resolve(pending)
        self.assertFalse(replay.success)
        self.assertEqual(len(self.bridge.created_results), 1)

        final = self.dispatcher.dispatch_tool_call(
            "get_task_status",
            {"task_id": pending["task_id"], "session_id": self.session_id},
        )
        self.assertTrue(final.is_success)
        self.assertEqual(final.result["status"], TaskStatus.SUCCEEDED.value)
        self.assertEqual(final.result["result"]["output_summary"]["name"], "ApprovalTestMaterial")

    def test_task_status_query_reports_execution_failure_details(self):
        pending = self._start_pending_material(task_id="task-status-execution-failure")
        self.registry.resolve_request(pending["approval_request_id"], "approved")
        self.bridge.bpy.data.materials.fail_with = "simulated material creation failure"

        resumed = self._resolve(pending)
        self.assertFalse(resumed.success)
        self.assertEqual(resumed.error_code, "EXECUTION_FAILED")

        status = self.dispatcher.dispatch_tool_call(
            "get_task_status",
            {"task_id": pending["task_id"], "session_id": self.session_id},
        )
        self.assertTrue(status.is_success)
        self.assertEqual(status.result["status"], TaskStatus.FAILED.value)
        self.assertIn(
            "simulated material creation failure",
            status.result["result"]["errors"][0],
        )

    def test_task_status_query_does_not_claim_stale_approval_is_pending(self):
        pending = self._start_pending_material(task_id="task-status-stale-approval")
        binding = self.dispatcher.coordinator.get_pending_approval(self.session_id, pending["task_id"])
        binding["expires_at"] = time.time() - 1.0
        self.bridge.status_calls.clear()

        status = self.dispatcher.dispatch_tool_call(
            "get_task_status",
            {"task_id": pending["task_id"], "session_id": self.session_id},
        )

        self.assertTrue(status.is_success)
        self.assertEqual(status.result["status"], TaskStatus.AWAITING_APPROVAL.value)
        self.assertEqual(status.result["approval"]["state"], "expired")
        self.assertNotEqual(status.result["approval"]["state"], "pending")
        self.assertEqual(self.bridge.status_calls, [])
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_task_status_query_missing_task_is_explicit_and_read_only(self):
        before = self.dispatcher.coordinator.active_session_count
        status = self.dispatcher.dispatch_tool_call(
            "get_task_status",
            {"task_id": "missing-task", "session_id": "missing-session"},
        )
        self.assertTrue(status.is_success)
        self.assertEqual(status.result["status"], "session_not_found")
        self.assertFalse(status.result["found"])
        self.assertEqual(self.dispatcher.coordinator.active_session_count, before)

    def test_task_status_is_discoverable_as_read_only_mcp_tool(self):
        tool = ToolRegistry().get_tool_definition("get_task_status")
        self.assertIsNotNone(tool)
        self.assertEqual(tool["permission_tier"], "READ_ONLY")

    def test_blender_denial_fails_task_without_material_creation(self):
        pending = self._start_pending_material()
        ok, _ = self.registry.resolve_request(pending["approval_request_id"], "denied")
        self.assertTrue(ok)

        result = self._resolve(pending)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "PERMISSION_DENIED")
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_expired_blender_request_fails_closed(self):
        pending = self._start_pending_material(task_id="task-expired-blender-request")
        req = self.registry.get_request(pending["approval_request_id"])
        req.created_at = time.time() - req.timeout_seconds - 1.0

        result = self._resolve(pending)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "APPROVAL_EXPIRED")
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_invalid_registry_token_is_rejected_by_blender_handler(self):
        pending = self._start_pending_material(task_id="task-invalid-blender-token")
        ok, _token = self.registry.resolve_request(pending["approval_request_id"], "approved")
        self.assertTrue(ok)
        self.bridge.invalid_status_token = "forged-token"

        result = self._resolve(pending)

        self.assertFalse(result.success)
        self.assertIn(result.error_code, ("PERMISSION_DENIED", "EXECUTION_FAILED"))
        self.assertEqual(len(self.bridge.created_results), 0)
        self.assertEqual(len(self.bridge.bpy.data.materials.created), 0)

    def test_mcp_resolver_credentials_without_blender_request_cannot_approve(self):
        task = AgentTask(
            task_id="task-mcp-only-approval",
            required_capability="materials.manage",
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "MustRemainBlocked"},
            session_id=self.session_id,
        )
        self.executor.approval_manager.set_provider(None)
        paused = self.dispatcher.dispatch_task(task, session_id=self.session_id)
        pending = paused.result["pending_approval"]

        result = self._resolve(pending)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "TRUSTED_APPROVAL_REQUIRED")
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_repeated_task_reports_authoritative_pending_status(self):
        pending = self._start_pending_material()
        self.bridge.status_calls.clear()

        result = self._repeat_task(pending)

        self.assertEqual(result.error_code, "APPROVAL_REQUIRED")
        self.assertEqual(result.result["pending_approval"]["approval_status"], "pending")
        self.assertEqual(result.result["pending_approval"]["approval_request_id"], pending["approval_request_id"])
        self.assertEqual(self.bridge.status_calls, [pending["approval_request_id"]])

    def test_repeated_task_does_not_resume_from_status_alone(self):
        pending = self._start_pending_material(task_id="task-repeat-approved-status")
        self.registry.resolve_request(pending["approval_request_id"], "approved")

        result = self._repeat_task(pending)

        self.assertEqual(result.error_code, "APPROVAL_RECORDED")
        self.assertEqual(result.result["pending_approval"]["approval_status"], "approved")
        self.assertEqual(len(self.bridge.created_results), 0)
        self.assertEqual(len(self.bridge.bpy.data.materials.created), 0)

    def test_repeated_task_reports_expired_registry_request(self):
        pending = self._start_pending_material(task_id="task-repeat-expired")
        req = self.registry.get_request(pending["approval_request_id"])
        req.created_at = time.time() - req.timeout_seconds - 1.0

        result = self._repeat_task(pending)

        self.assertEqual(result.error_code, "APPROVAL_EXPIRED")
        self.assertEqual(result.result["pending_approval"]["approval_status"], "expired")
        self.assertIn("fresh task", result.message)
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_repeated_task_reports_purged_registry_request(self):
        pending = self._start_pending_material(task_id="task-repeat-purged")
        req = self.registry.get_request(pending["approval_request_id"])
        req.created_at = time.time() - 601.0
        self.assertEqual(self.registry.get_pending_requests(), [])
        self.assertIsNone(self.registry.get_request(pending["approval_request_id"]))

        result = self._repeat_task(pending)

        self.assertEqual(result.error_code, "APPROVAL_REQUEST_NOT_FOUND")
        self.assertEqual(result.result["pending_approval"]["approval_status"], "not_found")
        self.assertIn("fresh task", result.message)
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_repeated_task_reports_registry_reload_and_bridge_unavailable(self):
        pending = self._start_pending_material(task_id="task-repeat-reloaded")
        # A Blender add-on reload recreates the in-memory registry; the old
        # request ID is then authoritatively absent from the new registry.
        self.bridge.registry = ApprovalRegistry()
        reloaded = self._repeat_task(pending)
        self.assertEqual(reloaded.error_code, "APPROVAL_REQUEST_NOT_FOUND")
        self.assertEqual(reloaded.result["pending_approval"]["approval_status"], "not_found")

        pending_unavailable = self._start_pending_material(task_id="task-repeat-unavailable")
        self.bridge.status_error = ConnectionError("bridge unavailable during Blender reload")
        unavailable = self._repeat_task(pending_unavailable)
        self.assertEqual(unavailable.error_code, "APPROVAL_STATUS_UNAVAILABLE")
        self.assertEqual(unavailable.result["pending_approval"]["approval_status"], "unknown")
        self.assertIn("bridge unavailable", unavailable.message)
        self.assertEqual(len(self.bridge.created_results), 0)

    def test_repeated_status_queries_do_not_reuse_cached_pending_state(self):
        pending = self._start_pending_material(task_id="task-repeat-changing-status")
        self.bridge.status_calls.clear()
        self.bridge.status_sequence = ["pending", "not_found"]

        first = self._repeat_task(pending)
        second = self._repeat_task(pending)

        self.assertEqual(first.result["pending_approval"]["approval_status"], "pending")
        self.assertEqual(second.result["pending_approval"]["approval_status"], "not_found")
        self.assertEqual(second.error_code, "APPROVAL_REQUEST_NOT_FOUND")
        self.assertEqual(
            self.bridge.status_calls,
            [pending["approval_request_id"], pending["approval_request_id"]],
        )


if __name__ == "__main__":
    unittest.main()
