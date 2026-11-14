"""Render timeout evidence must survive executor, agent and task-status query."""
import json
import unittest
from unittest.mock import Mock
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.agents.dispatcher import AgentDispatcher
from shared.models.agent_contracts import AgentTask, TaskStatus


class RenderJobStatusTests(unittest.TestCase):
    def run_failure(self, response=None, exception=None):
        executor = BlenderExecutor()
        executor.client = Mock()
        if exception: executor.client.send_command.side_effect = exception
        else: executor.client.send_command.return_value = response
        dispatcher = AgentDispatcher(executor=executor)
        task = AgentTask(task_id="render-job", session_id="render-test", required_capability="world.manage",
            task_type="render_scene", input_params={"render_mode": "still"})
        result = dispatcher.dispatch_task(task, session_id="render-test", trusted_approval=True)
        self.assertEqual(result.status, TaskStatus.FAILED)
        query = {"task_id": task.task_id, "session_id": "render-test"}
        status = dispatcher.dispatch_tool_call("get_task_status", query).result
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status, dispatcher.dispatch_tool_call("get_task_status", query).result)
        self.assertEqual(executor.client.send_command.call_count, 1)
        return status

    def test_active_timeout_is_unknown_outcome_not_confirmed_render_failure(self):
        status = self.run_failure({"status": "error", "error_code": "IN_FLIGHT_TIMEOUT",
            "execution_state": "ACTIVE_IN_FLIGHT", "requires_reconciliation": True, "message": "Render still running",
            "approval_token": "PRIVATE", "unreconciled_task": {"params": {"secret": "PRIVATE"}}})
        job = status["result"]["verification"]["render_job"]
        self.assertEqual(job["outcome"], "unknown")
        self.assertEqual(job["execution_state_at_response"], "ACTIVE_IN_FLIGHT")
        self.assertFalse(job["completion_verified"])
        self.assertTrue(job["requires_reconciliation"])
        self.assertFalse(job["automatic_retry_allowed"])
        self.assertNotIn("PRIVATE", json.dumps(status))

    def test_queue_timeout_reports_not_started(self):
        status = self.run_failure({"status": "error", "error_code": "QUEUE_TIMEOUT_CANCELLED",
            "execution_state": "DISCARDED_FROM_QUEUE", "message": "Cancelled before starting"})
        job = status["result"]["verification"]["render_job"]
        self.assertEqual(job["outcome"], "not_started")
        self.assertFalse(job["requires_reconciliation"])

    def test_transport_timeout_does_not_claim_cancellation(self):
        status = self.run_failure(exception=TimeoutError("Socket timed out"))
        job = status["result"]["verification"]["render_job"]
        self.assertEqual(job["outcome"], "unknown")
        self.assertEqual(job["execution_state_at_response"], "UNKNOWN")
        self.assertEqual(job["error_code"], "TRANSPORT_TIMEOUT")

    def test_blocked_retry_is_not_started_but_prior_job_requires_reconciliation(self):
        status = self.run_failure({"status": "error", "error_code": "BLIND_RETRY_BLOCKED",
            "execution_state": "REQUIRES_RECONCILIATION", "message": "Previous execution unknown"})
        job = status["result"]["verification"]["render_job"]
        self.assertEqual(job["outcome"], "not_started")
        self.assertTrue(job["requires_reconciliation"])

    def test_mismatched_queue_evidence_cannot_claim_not_started(self):
        status = self.run_failure({"status": "error", "error_code": "QUEUE_TIMEOUT_CANCELLED",
            "execution_state": "ACTIVE_IN_FLIGHT", "message": "Inconsistent evidence"})
        job = status["result"]["verification"]["render_job"]
        self.assertEqual(job["outcome"], "unknown")
        self.assertEqual(job["execution_state_at_response"], "UNKNOWN")

    def test_ordinary_error_keeps_existing_status_contract(self):
        status = self.run_failure({"status": "error", "message": "Camera not found"})
        self.assertNotIn("render_job", status["result"]["verification"])
        self.assertEqual(status["result"]["verification"]["error_code"], "DATA_UNAVAILABLE")

    def test_timeout_metadata_is_render_specific_and_does_not_authorize(self):
        executor = BlenderExecutor(); executor.client = Mock()
        executor.client.send_command.return_value = {"status": "error", "error_code": "IN_FLIGHT_TIMEOUT",
            "execution_state": "ACTIVE_IN_FLIGHT", "message": "Timed out"}
        denied = executor.execute_tool("render_scene", {"render_mode": "still", "approved": True}, trusted_approval=False)
        self.assertFalse(denied.is_success)
        executor.client.send_command.assert_not_called()
        ordinary = executor.execute_tool("get_scene_summary", {})
        self.assertIsNone(ordinary.result)
