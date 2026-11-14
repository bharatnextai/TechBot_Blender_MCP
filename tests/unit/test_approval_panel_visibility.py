import importlib.util
import pathlib
import sys
import time
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import handle_check_approval_status


class _Layout:
    def __init__(self, events):
        self.events = events

    def box(self):
        return self

    def row(self, **kwargs):
        return self

    def column(self, **kwargs):
        return self

    def separator(self):
        self.events.append(("separator",))

    def label(self, **kwargs):
        self.events.append(("label", kwargs.get("text", "")))

    def prop(self, *args, **kwargs):
        self.events.append(("prop", kwargs.get("text", "")))

    def operator(self, bl_idname, **kwargs):
        self.events.append(("operator", bl_idname, kwargs.get("text", "")))
        return SimpleNamespace()


class ApprovalPanelVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bpy_module = types.ModuleType("bpy")
        bpy_types = types.ModuleType("bpy.types")
        bpy_types.Panel = type("Panel", (), {})
        bpy_module.types = bpy_types
        module_name = "blender_addon.universal_mcp.ui._approval_panel_visibility_test"
        panel_path = pathlib.Path(__file__).parents[2] / "blender_addon" / "universal_mcp" / "ui" / "panels.py"
        spec = importlib.util.spec_from_file_location(module_name, panel_path)
        cls.panel_module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"bpy": bpy_module, "bpy.types": bpy_types}):
            spec.loader.exec_module(cls.panel_module)

    def _draw(self, registry):
        events = []
        panel = self.panel_module.UMCP_PT_MainPanel()
        panel.layout = _Layout(events)
        scene = SimpleNamespace(
            umcp_bridge_running=True,
            umcp_status_message="",
            umcp_bridge_port=9877,
            umcp_require_scene_mutation_approval=True,
        )
        context = SimpleNamespace(scene=scene)
        with patch(
            "blender_addon.universal_mcp.bridge.approval_registry.get_approval_registry",
            return_value=registry,
        ):
            panel.draw(context)
        return events

    def test_expired_request_remains_visible_without_resolution_actions(self):
        registry = ApprovalRegistry()
        req = registry.create_request("create_material", {"name": "ExpiredMat"}, timeout=300.0)
        req.created_at = time.time() - 301.0

        self.assertEqual(registry.get_pending_requests(), [])
        events = self._draw(registry)
        labels = [event[1] for event in events if event[0] == "label"]
        operators = [event[1] for event in events if event[0] == "operator"]

        self.assertIn("Recent Approval Requests:", labels)
        self.assertIn(f"Request ID: {req.request_id}", labels)
        self.assertIn("Status: expired", labels)
        self.assertIn("Reason: Timeout expired", labels)
        self.assertNotIn("umcp.resolve_approval", operators)
        self.assertNotIn("umcp.approval_dialog", operators)

    def test_active_pending_request_keeps_approve_and_deny_actions(self):
        registry = ApprovalRegistry()
        registry.create_request("create_material", {"name": "PendingMat"})

        events = self._draw(registry)
        operators = [event[1:] for event in events if event[0] == "operator"]

        self.assertIn(("umcp.resolve_approval", "Approve"), operators)
        self.assertIn(("umcp.resolve_approval", "Deny"), operators)
        self.assertIn(("umcp.approval_dialog", "Open Dialog"), operators)

    def test_old_expired_request_is_archived_and_visible_with_status(self):
        registry = ApprovalRegistry()
        req = registry.create_request("create_material", {"name": "ArchivedMat"}, timeout=300.0)
        req.created_at = time.time() - 601.0

        events = self._draw(registry)
        labels = [event[1] for event in events if event[0] == "label"]
        operators = [event[1] for event in events if event[0] == "operator"]
        self.assertIsNone(registry.get_request(req.request_id))
        self.assertIn(f"Request ID: {req.request_id}", labels)
        self.assertIn("Status: expired", labels)
        self.assertNotIn("umcp.resolve_approval", operators)
        self.assertNotIn("umcp.approval_dialog", operators)

        with patch(
            "blender_addon.universal_mcp.bridge.handlers.get_approval_registry",
            return_value=registry,
        ):
            status = handle_check_approval_status(params={"request_id": req.request_id})
        self.assertEqual(status["status"], "expired")
        self.assertIsNone(status["approval_token"])

        resolved, reason = registry.resolve_request(req.request_id, "approved")
        self.assertFalse(resolved)
        self.assertIn("not found", reason)

    def test_old_but_unexpired_pending_request_is_not_evicted(self):
        registry = ApprovalRegistry()
        req = registry.create_request("create_material", {"name": "LongPending"}, timeout=3600.0)
        req.created_at = time.time() - 601.0

        recent = registry.get_recent_requests()
        self.assertEqual(recent[0].request_id, req.request_id)
        self.assertEqual(recent[0].status, "pending")
        self.assertIs(registry.get_request(req.request_id), req)

        events = self._draw(registry)
        operators = [event[1] for event in events if event[0] == "operator"]
        self.assertIn("umcp.resolve_approval", operators)

    def test_archived_approved_request_does_not_retain_token(self):
        registry = ApprovalRegistry()
        req = registry.create_request("create_material", {"name": "ApprovedMat"}, timeout=300.0)
        approved, token = registry.resolve_request(req.request_id, "approved")
        self.assertTrue(approved)
        req.created_at = time.time() - 601.0
        recent = registry.get_recent_requests()
        self.assertEqual(recent[0].status, "approved")
        self.assertIsNone(recent[0].approval_token)

        with patch(
            "blender_addon.universal_mcp.bridge.handlers.get_approval_registry",
            return_value=registry,
        ):
            status = handle_check_approval_status(params={"request_id": req.request_id})
        self.assertEqual(status["status"], "approved")
        self.assertIsNone(status["approval_token"])

        consumed, reason = registry.consume_approval(
            req.request_id, token, "create_material", {"name": "ApprovedMat"}
        )
        self.assertFalse(consumed)
        self.assertIn("not found", reason)

    def test_empty_registry_has_visible_diagnostic(self):
        events = self._draw(ApprovalRegistry())
        labels = [event[1] for event in events if event[0] == "label"]
        self.assertIn("No recent approval requests in this Blender registry.", labels)


if __name__ == "__main__":
    unittest.main()
