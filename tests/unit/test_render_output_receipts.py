"""Fresh render completion and receipt-based, read-only artifact verification."""
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from tests.unit.test_render_scene import MockBpy, MockCameraObject, render_png
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import handle_render_scene


class RenderCompletionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="umcp-render-completion-")
        self.addCleanup(directory.cleanup); self.root = Path(directory.name)
        self.bpy = MockBpy(str(self.root), write_files=False)
        self.bpy.scene.camera = MockCameraObject("Camera")
        self.registry = ApprovalRegistry()
        self.enterContext(patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=self.registry))
        Path(self.bpy.scene.render.filepath).write_bytes(b"PREEXISTING_OUTPUT")

    def execute(self):
        args = {"render_mode": "still"}
        request = self.registry.create_request("render_scene", args)
        ok, token = self.registry.resolve_request(request.request_id, "approved"); self.assertTrue(ok)
        return handle_render_scene(self.bpy, {**args, "request_id": request.request_id, "approval_token": token})

    def test_cancelled_operator_cannot_accept_preexisting_file(self):
        self.bpy.ops.render.render = lambda **kwargs: {"CANCELLED"}
        with self.assertRaisesRegex(RuntimeError, "did not finish"):
            self.execute()

    def test_missing_operator_cannot_accept_preexisting_file(self):
        self.bpy.ops.render = NS()
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.execute()

    def test_finished_operator_without_new_output_is_not_success(self):
        self.bpy.ops.render.render = lambda **kwargs: {"FINISHED"}
        with self.assertRaisesRegex(RuntimeError, "fresh"):
            self.execute()


class RenderReceiptTests(unittest.TestCase):
    def setUp(self):
        from blender_addon.universal_mcp.bridge import render_outputs as receipts
        self.api = receipts
        receipts._receipts.clear()
        self.addCleanup(receipts._receipts.clear)
        directory = tempfile.TemporaryDirectory(prefix="umcp-receipt-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "output.png"
        self.path.write_bytes(render_png(8, 4))

    def register(self):
        return self.api.record_render_output(str(self.path), 8, 4, "PNG", 1, "Camera")

    def inspect(self, identifier):
        return self.api.handle_inspect_render_output(params={"render_id": identifier})

    def test_repeated_inspection_verifies_without_writes(self):
        identifier = self.register(); before = self.api.file_signature(self.path)
        first = self.inspect(identifier)
        self.assertEqual(first, self.inspect(identifier))
        self.assertTrue(first["verified"])
        self.assertTrue(first["artifact"]["png_structure_verified"])
        self.assertEqual(first["artifact"]["width"], 8)
        self.assertEqual(self.api.file_signature(self.path), before)

    def test_changed_deleted_or_corrupted_output_is_not_verified(self):
        for mode in ("replace", "delete", "corrupt"):
            with self.subTest(mode=mode):
                self.path.write_bytes(render_png(8, 4)); identifier = self.register()
                if mode == "delete": self.path.unlink()
                elif mode == "replace": self.path.write_bytes(render_png(4, 8))
                else: self.path.write_bytes(b"not a PNG")
                with self.assertRaises((ValueError, FileNotFoundError)):
                    self.inspect(identifier)

    def test_unknown_expired_and_evicted_receipts_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.inspect("a"*32)
        identifier = self.register()
        created, entry = self.api._receipts[identifier]
        with patch.object(self.api.time, "monotonic", return_value=created+self.api.RECEIPT_TTL):
            with self.assertRaisesRegex(ValueError, "expired"): self.inspect(identifier)
        first = self.register()
        with patch.object(self.api, "RECEIPT_LIMIT", 1): self.register()
        with self.assertRaisesRegex(ValueError, "not found"): self.inspect(first)
        latest = self.register(); self.api._receipts.clear()
        with self.assertRaisesRegex(ValueError, "reloaded"): self.inspect(latest)

    def test_schema_rejects_paths_credentials_and_malformed_ids(self):
        from shared.schemas.tool_schemas import validate_tool_input
        for params in ({"render_id": "A"*32}, {"render_id": "a"*31}, {"render_id": "a"*32, "path": str(self.path)},
                       {"render_id": "a"*32, "approved": True}, {"render_id": "a"*32, "approval_token": "secret"}):
            with self.subTest(params=params):
                with self.assertRaises(ValueError): validate_tool_input("inspect_render_output", params)

    def test_invalid_png_and_wrong_dimensions_cannot_be_registered(self):
        with self.assertRaisesRegex(ValueError, "dimensions"):
            self.api.record_render_output(str(self.path), 4, 8, "PNG", 1, "Camera")
        good = self.path.read_bytes()
        for content in (good[:-6], b"bad", good[:-1]+bytes([good[-1]^1])):
            self.path.write_bytes(content)
            with self.assertRaises(ValueError): self.register()

    def test_file_and_decoded_budgets_fail_closed(self):
        with patch.object(self.api, "MAX_FILE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "budget"): self.register()
        with patch.object(self.api, "MAX_DECODED_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "budget"): self.register()


class RenderAgentFailureTests(unittest.TestCase):
    def test_missing_unverified_mismatched_or_unavailable_receipt_fails_task(self):
        from mcp_service.agents.render_lighting import RenderLightingAgent
        from shared.models.agent_contracts import AgentTask, TaskStatus
        from shared.models.protocol_models import BridgeResponse
        for mode in ("missing", "unverified", "mismatch", "unavailable"):
            with self.subTest(mode=mode):
                calls = []
                class Executor:
                    def execute_tool(self, tool_name, params, **kwargs):
                        calls.append(tool_name)
                        if tool_name == "inspect_render_output":
                            if mode == "unavailable": raise RuntimeError("Bridge reloaded")
                            return BridgeResponse.success({"success": True, "verified": mode != "unverified",
                                "render_id": "b"*32 if mode == "mismatch" else "a"*32,
                                "width": 64, "height": 64, "frame": 1, "camera": "Camera", "file_format": "PNG",
                                "artifact": {"path": "output.png", "width": 64, "height": 64,
                                    "sha256": "b"*64, "size_bytes": 100, "png_structure_verified": True}})
                        result = {"rendered": True, "operator_completed": True, "output_file": "output.png",
                            "width": 64, "height": 64, "frame": 1, "camera": "Camera"}
                        if mode != "missing": result["render_id"] = "a"*32
                        return BridgeResponse.success(result)
                task = AgentTask(task_id="receipt-test", required_capability="world.manage", task_type="render_scene", input_params={"render_mode": "still"})
                result = RenderLightingAgent().execute_task(task, executor=Executor(), trusted_approval=True)
                self.assertEqual(result.status, TaskStatus.FAILED)
                self.assertEqual(result.verification.status, "FAIL")
                self.assertEqual(calls.count("render_scene"), 1)
                self.assertIn("receipt", result.errors[0])

