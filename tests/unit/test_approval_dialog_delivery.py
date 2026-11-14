import logging
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge import handlers


class ApprovalDialogDeliveryTests(unittest.TestCase):
    def setUp(self):
        handlers._scheduled_approval_dialogs.clear()
        self.registry = ApprovalRegistry()
        self.timer_callback = None
        self.bpy = MagicMock()
        self.bpy.context.scene.umcp_require_scene_mutation_approval = True
        self.bpy.context.preferences = None
        self.bpy.context.window_manager.windows = []
        self.bpy.app.timers.register = self.register_timer
        self.bpy.ops.umcp.approval_dialog.return_value = {'RUNNING_MODAL'}
        self.temp_override_calls = []

        @contextmanager
        def temp_override(**kwargs):
            self.temp_override_calls.append(kwargs)
            yield

        self.bpy.context.temp_override = temp_override

        self.registry_patch = patch.object(handlers, "get_approval_registry", return_value=self.registry)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
        self._add_view3d_window()

    def tearDown(self):
        handlers._scheduled_approval_dialogs.clear()

    def register_timer(self, callback, first_interval):
        self.timer_callback = callback

    def _add_view3d_window(self):
        region = MagicMock(type="WINDOW")
        area = MagicMock(type="VIEW_3D", regions=[region])
        screen = MagicMock(areas=[area])
        self.window = MagicMock(screen=screen)
        self.bpy.context.window_manager.windows = [self.window]

    def _schedule(self, timeout=30.0):
        response = handlers.handle_request_approval(
            bpy_module=self.bpy,
            params={"tool_name": "create_material", "params": {"name": "Test"}, "timeout": timeout},
        )
        self.assertEqual(response["status"], "pending")
        self.assertIsNotNone(self.timer_callback)
        return response["request_id"]

    def test_missing_window_retries_then_invokes_with_valid_override(self):
        self.bpy.context.window_manager.windows = []
        request_id = self._schedule()

        self.assertEqual(self.timer_callback(), handlers._APPROVAL_DIALOG_RETRY_INTERVAL)
        self.bpy.ops.umcp.approval_dialog.assert_not_called()

        self._add_view3d_window()
        self.assertIsNone(self.timer_callback())
        self.bpy.ops.umcp.approval_dialog.assert_called_once_with(
            'INVOKE_DEFAULT', request_id=request_id
        )
        self.assertEqual(self.temp_override_calls[0]["window"], self.window)
        self.assertEqual(self.temp_override_calls[0]["area"].type, "VIEW_3D")

    def test_invalid_ui_context_retries(self):
        self.bpy.context.temp_override = None
        self._schedule()
        self.assertEqual(self.timer_callback(), handlers._APPROVAL_DIALOG_RETRY_INTERVAL)
        self.bpy.ops.umcp.approval_dialog.assert_not_called()

    def test_operator_invocation_failure_is_logged_and_retried(self):
        self.bpy.ops.umcp.approval_dialog.side_effect = RuntimeError("operator poll failed")
        self._schedule()
        with self.assertLogs(handlers._logger, level=logging.ERROR) as logs:
            self.assertEqual(self.timer_callback(), handlers._APPROVAL_DIALOG_RETRY_INTERVAL)
        self.assertIn("operator poll failed", "\n".join(logs.output))

    def test_timer_registration_failure_is_logged(self):
        self.bpy.app.timers.register = MagicMock(side_effect=RuntimeError("timer unavailable"))
        with self.assertLogs(handlers._logger, level=logging.ERROR) as logs:
            response = handlers.handle_request_approval(
                bpy_module=self.bpy,
                params={"tool_name": "create_material", "params": {"name": "Test"}},
            )
        self.assertEqual(response["status"], "pending")
        self.assertIn("timer unavailable", "\n".join(logs.output))
        self.assertNotIn(response["request_id"], handlers._scheduled_approval_dialogs)

    def test_retry_limit_is_bounded_and_logged(self):
        self.bpy.context.window_manager.windows = []
        self._schedule()
        with self.assertLogs(handlers._logger, level=logging.ERROR) as logs:
            for _ in range(handlers._APPROVAL_DIALOG_MAX_ATTEMPTS):
                result = self.timer_callback()
        self.assertIsNone(result)
        self.assertTrue(any("after" in entry and "attempts" in entry for entry in logs.output))

    def test_request_termination_stops_retry(self):
        for decision in ("approved", "denied", "cancelled"):
            with self.subTest(decision=decision):
                handlers._scheduled_approval_dialogs.clear()
                self.bpy.context.window_manager.windows = []
                request_id = self._schedule()
                self.registry.resolve_request(request_id, decision)
                self.assertIsNone(self.timer_callback())
                self.assertNotIn(request_id, handlers._scheduled_approval_dialogs)

        handlers._scheduled_approval_dialogs.clear()
        self.bpy.context.window_manager.windows = []
        expired_id = self._schedule(timeout=0.01)
        self.registry._requests[expired_id].created_at -= 1
        self.assertIsNone(self.timer_callback())
        self.assertEqual(self.registry.get_request(expired_id).status, "expired")

        handlers._scheduled_approval_dialogs.clear()
        self.bpy.context.window_manager.windows = []
        removed_id = self._schedule()
        self.registry._requests.pop(removed_id)
        self.assertIsNone(self.timer_callback())
        self.assertNotIn(removed_id, handlers._scheduled_approval_dialogs)


if __name__ == "__main__":
    unittest.main()
