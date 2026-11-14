import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry, get_approval_registry


class TestApprovalTokenLoggingRedaction(unittest.TestCase):
    """
    Focused regression test proving that UMCP_OT_ResolveApproval never emits
    the raw approval token in log messages, reports, or status strings.
    """

    @classmethod
    def setUpClass(cls):
        # Create minimal mock bpy module to import operators in standard Python
        bpy_module = types.ModuleType("bpy")
        bpy_types = types.ModuleType("bpy.types")
        bpy_props = types.ModuleType("bpy.props")

        class MockOperator:
            def report(self, level, msg):
                pass

        bpy_types.Operator = MockOperator
        bpy_props.StringProperty = lambda **kw: ""
        bpy_props.EnumProperty = lambda **kw: ""

        bpy_module.types = bpy_types
        bpy_module.props = bpy_props

        module_name = "blender_addon.universal_mcp.operators_token_redaction_test"
        op_path = pathlib.Path(__file__).parents[2] / "blender_addon" / "universal_mcp" / "operators.py"
        spec = importlib.util.spec_from_file_location(module_name, op_path)
        cls.op_module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"bpy": bpy_module, "bpy.types": bpy_types, "bpy.props": bpy_props}):
            spec.loader.exec_module(cls.op_module)

    def setUp(self):
        self.registry = get_approval_registry()
        # Clean registry before each test
        with self.registry._lock:
            self.registry._requests.clear()
            self.registry._recent_requests.clear()
            self.registry._tokens.clear()

    def test_approval_token_is_redacted_from_reports_and_status(self):
        """
        When a request is approved via UMCP_OT_ResolveApproval, the approval token
        is generated in the registry but NEVER emitted in self.report or umcp_status_message.
        """
        req = self.registry.create_request("edit_mesh", {"name": "TestCube"}, timeout=60.0)
        req_id = req.request_id

        reports = []

        op = self.op_module.UMCP_OT_ResolveApproval()
        op.request_id = req_id
        op.action = "approve"
        op.report = lambda level_set, msg: reports.append((level_set, msg))

        scene = SimpleNamespace(umcp_status_message="")
        context = SimpleNamespace(scene=scene)

        res = op.execute(context)
        self.assertEqual(res, {'FINISHED'})

        # Confirm request was actually approved in the registry and has a token
        req_in_reg = self.registry.get_request_for_status(req_id)
        self.assertEqual(req_in_reg.status, "approved")
        token = getattr(req_in_reg, "approval_token", None)
        self.assertTrue(token, "Approval token should have been generated")
        self.assertEqual(len(token), 32, "Hex token should be 32 chars")

        # Crucial check: Token must NOT be in reports or scene status message
        self.assertNotIn(token, scene.umcp_status_message)
        for _, msg in reports:
            self.assertNotIn(token, msg, f"Token {token} leaked in operator report: {msg}")

        # Diagnostics check: Message should still contain request ID and approval info
        self.assertIn(req_id, scene.umcp_status_message)
        self.assertIn("Approved", scene.umcp_status_message)
        self.assertTrue(any(req_id in msg and "approved" in msg.lower() and "redacted" in msg.lower() for _, msg in reports))

    def test_denial_does_not_leak_or_generate_tokens(self):
        """
        When a request is denied via UMCP_OT_ResolveApproval, status is 'denied',
        no approval token is generated, and reports reflect denial diagnostics.
        """
        req = self.registry.create_request("edit_mesh", {"name": "TestCube"}, timeout=60.0)
        req_id = req.request_id

        reports = []

        op = self.op_module.UMCP_OT_ResolveApproval()
        op.request_id = req_id
        op.action = "deny"
        op.report = lambda level_set, msg: reports.append((level_set, msg))

        scene = SimpleNamespace(umcp_status_message="")
        context = SimpleNamespace(scene=scene)

        res = op.execute(context)
        self.assertEqual(res, {'FINISHED'})

        req_in_reg = self.registry.get_request_for_status(req_id)
        self.assertEqual(req_in_reg.status, "denied")
        self.assertIsNone(getattr(req_in_reg, "approval_token", None))

        self.assertIn(req_id, scene.umcp_status_message)
        self.assertIn("Denied", scene.umcp_status_message)
        self.assertTrue(any(req_id in msg and "denied" in msg.lower() for _, msg in reports))


if __name__ == "__main__":
    unittest.main()
