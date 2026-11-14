"""
Unit and regression tests for TASK-UMCP-0039:
1. Blender Ping operator (UMCP_OT_PingBridge) main-thread deadlock resolution.
2. Immediate bridge_server ping handling without main-thread queue dependency.
3. Approval-setting precedence: Active Scene > Add-on Preferences > In-Memory Registry.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import socket
import threading
import time

from blender_addon.universal_mcp.operators import UMCP_OT_PingBridge
import blender_addon.universal_mcp.operators as operators_module
from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
from blender_addon.universal_mcp.bridge.bridge_client import BridgeClient
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import (
    is_approval_required,
    handle_request_approval,
    handle_get_approval_settings,
    handle_set_approval_settings,
)


class MockScene:
    def __init__(self):
        self.umcp_bridge_port = 9877
        self.umcp_bridge_running = False
        self.umcp_status_message = ""
        self.umcp_require_scene_mutation_approval = True


class MockContext:
    def __init__(self, scene=None, prefs=None):
        self.scene = scene or MockScene()
        self.preferences = prefs


class MockPreferences:
    def __init__(self, require_approval=True):
        self.require_scene_mutation_approval = require_approval


class MockBpyWithPrefs:
    def __init__(self, scene_require=True, pref_require=True):
        self.scene = MockScene()
        self.scene.umcp_require_scene_mutation_approval = scene_require

        self.pref_obj = MockPreferences(require_approval=pref_require)
        self.context = MockContext(scene=self.scene)

        # Mock preferences.addons dictionary
        mock_addon = MagicMock()
        mock_addon.preferences = self.pref_obj
        mock_pref_mgr = MagicMock()
        mock_pref_mgr.addons = {"universal_mcp": mock_addon}
        self.context.preferences = mock_pref_mgr

        self.data = MagicMock()
        self.data.scenes = [self.scene]
        self.app = MagicMock()
        self.app.timers = MagicMock()
        self.ops = MagicMock()
        self.ops.wm = MagicMock()
        self.ops.wm.save_userpref = MagicMock(return_value={'FINISHED'})


class TestPingOperatorDeadlockFix(unittest.TestCase):
    """Tests confirming the Ping operator never deadlocks and reports accurate status."""

    def setUp(self):
        self.orig_server = operators_module._server_instance

    def tearDown(self):
        operators_module._server_instance = self.orig_server

    def test_ping_operator_local_server_fast_path(self):
        """When local server instance is active in this process, ping confirms liveness immediately."""
        mock_server = MagicMock()
        mock_server.running = True
        mock_server.port = 9877
        operators_module._server_instance = mock_server

        op = UMCP_OT_PingBridge()
        ctx = MockContext()
        ctx.scene.umcp_bridge_port = 9877

        reports = []
        op.report = lambda level, msg: reports.append((level, msg))

        res = op.execute(ctx)
        self.assertEqual(res, {'FINISHED'})
        self.assertTrue(ctx.scene.umcp_bridge_running)
        self.assertIn("Pong received from port 9877", ctx.scene.umcp_status_message)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0][0], {'INFO'})

    @patch("blender_addon.universal_mcp.operators.BridgeClient")
    def test_ping_operator_loopback_fallback_success(self, mock_client_cls):
        """When local server instance is not running, loopback probe checks socket with 3.0s timeout."""
        operators_module._server_instance = None
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client_cls.return_value = mock_client

        op = UMCP_OT_PingBridge()
        ctx = MockContext()
        ctx.scene.umcp_bridge_port = 9877

        reports = []
        op.report = lambda level, msg: reports.append((level, msg))

        res = op.execute(ctx)
        self.assertEqual(res, {'FINISHED'})
        mock_client_cls.assert_called_once_with(port=9877, timeout=3.0)
        mock_client.close.assert_called_once()
        self.assertTrue(ctx.scene.umcp_bridge_running)
        self.assertIn("Pong received from port 9877", ctx.scene.umcp_status_message)

    @patch("blender_addon.universal_mcp.operators.BridgeClient")
    def test_ping_operator_loopback_fallback_failure(self, mock_client_cls):
        """When loopback probe fails, operator sets failure status, warning report, and closes client."""
        operators_module._server_instance = None
        mock_client = MagicMock()
        mock_client.ping.return_value = False
        mock_client_cls.return_value = mock_client

        op = UMCP_OT_PingBridge()
        ctx = MockContext()
        ctx.scene.umcp_bridge_port = 9877

        reports = []
        op.report = lambda level, msg: reports.append((level, msg))

        res = op.execute(ctx)
        self.assertEqual(res, {'FINISHED'})
        mock_client_cls.assert_called_once_with(port=9877, timeout=3.0)
        mock_client.close.assert_called_once()
        self.assertIn("No response on port 9877", ctx.scene.umcp_status_message)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0][0], {'WARNING'})

    @patch("blender_addon.universal_mcp.operators.BridgeClient")
    def test_ping_operator_instance_recovery_fast_path(self, mock_client_cls):
        """When _server_instance is None, operator recovers active instance via get_server_instance."""
        operators_module._server_instance = None
        recovered_server = MagicMock()
        recovered_server.running = True
        recovered_server.port = 9877

        with patch("blender_addon.universal_mcp.operators.get_server_instance", return_value=recovered_server) as mock_get:
            op = UMCP_OT_PingBridge()
            ctx = MockContext()
            ctx.scene.umcp_bridge_port = 9877

            reports = []
            op.report = lambda level, msg: reports.append((level, msg))

            res = op.execute(ctx)
            self.assertEqual(res, {'FINISHED'})
            mock_get.assert_called_once_with(9877)
            mock_client_cls.assert_not_called()
            self.assertTrue(ctx.scene.umcp_bridge_running)
            self.assertIn("Pong received from port 9877", ctx.scene.umcp_status_message)
            self.assertEqual(reports[0][0], {'INFO'})

    @patch("blender_addon.universal_mcp.operators.BridgeClient")
    def test_ping_operator_socket_cleanup_on_exception(self, mock_client_cls):
        """When client.ping() raises an exception, client.close() still executes in finally."""
        operators_module._server_instance = None
        mock_client = MagicMock()
        mock_client.ping.side_effect = RuntimeError("Unexpected socket error")
        mock_client_cls.return_value = mock_client

        op = UMCP_OT_PingBridge()
        ctx = MockContext()
        ctx.scene.umcp_bridge_port = 9877

        reports = []
        op.report = lambda level, msg: reports.append((level, msg))

        res = op.execute(ctx)
        self.assertEqual(res, {'FINISHED'})
        mock_client.close.assert_called_once()
        self.assertIn("No response on port 9877", ctx.scene.umcp_status_message)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0][0], {'WARNING'})


class TestBridgeServerPingImmediateResponse(unittest.TestCase):
    """Tests confirming BridgeServer answers ping immediately on socket thread."""

    def test_bridge_server_answers_ping_without_main_thread_queue(self):
        """Ping command returns pong=True even if MainThreadQueue timer is NOT running."""
        # Find an available local port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        test_port = sock.getsockname()[1]
        sock.close()

        server = BridgeServer(port=test_port)
        # Intentionally do NOT start queue timer to simulate blocked main thread
        server.start()

        try:
            client = BridgeClient(port=test_port, timeout=2.0)
            t0 = time.time()
            ping_ok = client.ping()
            duration = time.time() - t0
            self.assertTrue(ping_ok)
            # Must respond in milliseconds, proving no main thread deadlock
            self.assertTrue(duration < 1.0)
            client.close()
        finally:
            server.stop()


class TestApprovalSettingPrecedence(unittest.TestCase):
    """Tests confirming the precedence hierarchy: Active Scene > Add-on Preferences > In-Memory Registry."""

    def test_scene_false_overrides_preferences_true(self):
        """When Active Scene has Require Approval=False and Preferences has True, setting is OFF (auto-approve)."""
        bpy_mock = MockBpyWithPrefs(scene_require=False, pref_require=True)

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            mock_get_reg.return_value = test_reg

            required = is_approval_required(bpy_mock)
            self.assertFalse(required)
            self.assertFalse(test_reg.require_scene_mutation_approval)

    def test_scene_true_overrides_preferences_false(self):
        """When Active Scene has Require Approval=True and Preferences has False, setting is ON (manual approval)."""
        bpy_mock = MockBpyWithPrefs(scene_require=True, pref_require=False)

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            mock_get_reg.return_value = test_reg

            required = is_approval_required(bpy_mock)
            self.assertTrue(required)
            self.assertTrue(test_reg.require_scene_mutation_approval)

    def test_preferences_fallback_when_scene_has_no_property(self):
        """When Scene lacks umcp_require_scene_mutation_approval, Addon Preferences is consulted."""
        bpy_mock = MockBpyWithPrefs(scene_require=True, pref_require=False)
        del bpy_mock.scene.umcp_require_scene_mutation_approval

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            mock_get_reg.return_value = test_reg

            required = is_approval_required(bpy_mock)
            self.assertFalse(required)
            self.assertFalse(test_reg.require_scene_mutation_approval)

    def test_registry_fallback_when_no_scene_and_no_prefs(self):
        """When neither Scene nor Preferences is available, in-memory Registry is consulted."""
        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            test_reg.require_scene_mutation_approval = False
            mock_get_reg.return_value = test_reg

            required = is_approval_required(None)
            self.assertFalse(required)

    def test_handle_request_approval_auto_approves_when_scene_is_false(self):
        """handle_request_approval immediately returns status='approved' when Scene setting is False."""
        bpy_mock = MockBpyWithPrefs(scene_require=False, pref_require=True)

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            mock_get_reg.return_value = test_reg

            resp = handle_request_approval(
                bpy_module=bpy_mock,
                params={
                    "tool_name": "create_primitive",
                    "params": {"primitive_type": "cube", "name": "AutoPrecedenceCube"},
                    "task_id": "task-prec-01",
                }
            )

            self.assertEqual(resp["status"], "approved")
            self.assertIsNotNone(resp.get("approval_token"))
            # Confirm no modal dialog scheduled
            bpy_mock.app.timers.register.assert_not_called()

    def test_handle_request_approval_requires_approval_when_scene_is_true(self):
        """handle_request_approval returns status='pending' and registers dialog when Scene is True."""
        bpy_mock = MockBpyWithPrefs(scene_require=True, pref_require=False)

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            mock_get_reg.return_value = test_reg

            resp = handle_request_approval(
                bpy_module=bpy_mock,
                params={
                    "tool_name": "create_primitive",
                    "params": {"primitive_type": "cube", "name": "ManualPrecedenceCube"},
                    "task_id": "task-prec-02",
                }
            )

            req = test_reg.get_request(resp["request_id"])
            self.assertEqual(req.status, "pending")
            # Confirm modal dialog was scheduled
            bpy_mock.app.timers.register.assert_called_once()

    def test_handle_set_approval_settings_synchronizes_all_tiers(self):
        """handle_set_approval_settings updates registry, active scene, and preferences."""
        bpy_mock = MockBpyWithPrefs(scene_require=True, pref_require=True)

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            mock_get_reg.return_value = test_reg

            res = handle_set_approval_settings(bpy_module=bpy_mock, params={"require_scene_mutation_approval": False})
            self.assertFalse(res["require_scene_mutation_approval"])
            self.assertFalse(test_reg.require_scene_mutation_approval)
            self.assertFalse(bpy_mock.scene.umcp_require_scene_mutation_approval)
            self.assertFalse(bpy_mock.pref_obj.require_scene_mutation_approval)
            bpy_mock.ops.wm.save_userpref.assert_called_once()


if __name__ == "__main__":
    unittest.main()
