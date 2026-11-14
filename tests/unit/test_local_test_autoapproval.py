"""Disposable-mode tests; never connect to a live Blender registry."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import threading
from unittest.mock import patch

from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import (
    handle_request_approval, handle_create_material, _local_test_autoapproval,
    handle_uv_smart_project,
)
from tests.unit.test_blender_material_approval_resumption import _FakeBlenderBridge
from mcp_service.agents.dispatcher import AgentDispatcher
from mcp_service.execution.blender_executor import BlenderExecutor
from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue


class TestLocalTestAutoapproval(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="umcp-local-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {"UMCP_LOCAL_TEST_AUTOAPPROVE": "1", "UMCP_LOCAL_TEST_ROOT": str(self.root),
                    "UMCP_BRIDGE_PORT": "19877"}
        for key in ("BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_EXTENSIONS"):
            self.env[key] = str(self.root / key)
            (self.root / key).mkdir()
        self.enterContext(patch.dict(os.environ, self.env))
        self.registry = ApprovalRegistry()
        self.bridge = _FakeBlenderBridge(self.registry)
        self.bpy = self.bridge.bpy
        self.bpy.app = SimpleNamespace(background=True)
        self.bpy.data.filepath = ""
        self.bpy.context = SimpleNamespace(scene=SimpleNamespace(
            umcp_bridge_port=19877, umcp_require_scene_mutation_approval=True))
        self.enterContext(patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=self.registry))

    def request(self, params=None, tool="create_material", timeout=30):
        return handle_request_approval(self.bpy, {"tool_name": tool, "params": params or {"name": "Fixture"}, "timeout": timeout})

    def test_default_remains_pending_even_in_background(self):
        with patch.dict(os.environ, {"UMCP_LOCAL_TEST_AUTOAPPROVE": ""}):
            self.assertEqual(self.request()["status"], "pending")
        self.assertEqual(self.bpy.data.materials.created, [])

    def test_development_issues_and_consumes_bound_single_use_token(self):
        req = self.request()
        self.assertEqual(req["status"], "approved")
        params = {"name": "Fixture", "request_id": req["request_id"], "approval_token": req["approval_token"]}
        handle_create_material(self.bpy, params)
        self.assertTrue(self.registry.inspect_request_status(req["request_id"])["token_consumed"])
        with self.assertRaises(PermissionError):
            handle_create_material(self.bpy, params)
        self.assertEqual(len(self.bpy.data.materials.created), 1)

    def test_tampering_and_expiry_remain_enforced(self):
        req = self.request()
        params = {"name": "Different", "request_id": req["request_id"], "approval_token": req["approval_token"]}
        with self.assertRaises(PermissionError):
            handle_create_material(self.bpy, params)
        record = self.registry.get_request(req["request_id"])
        record.created_at -= 1000
        params["name"] = "Fixture"
        with self.assertRaises(PermissionError):
            handle_create_material(self.bpy, params)
        self.assertEqual(self.bpy.data.materials.created, [])

    def test_flags_never_enable_development_authorization(self):
        for flag in ("approved", "trusted_approval", "_trusted_approval"):
            with self.subTest(flag=flag):
                self.assertEqual(self.request({"name": "Fixture", flag: True})["status"], "pending")
        with self.assertRaises(PermissionError):
            handle_create_material(self.bpy, {"name": "Fixture", "approved": True})

    def test_isolation_guards_fail_closed(self):
        for key, value in (("UMCP_BRIDGE_PORT", "9877"), ("UMCP_BRIDGE_PORT", "bad"),
                           ("UMCP_LOCAL_TEST_ROOT", ""), ("BLENDER_USER_CONFIG", ""),
                           ("BLENDER_USER_SCRIPTS", str(self.root.parent)),
                           ("BLENDER_USER_EXTENSIONS", str(self.root.parent))):
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                self.assertFalse(_local_test_autoapproval(self.bpy, "create_material", {}))
        self.bpy.app.background = False
        self.assertEqual(self.request()["status"], "pending")
        self.bpy.app.background = True
        self.bpy.data.filepath = "user.blend"
        self.assertEqual(self.request()["status"], "pending")

    def test_destructive_and_arbitrary_code_are_not_autoauthorized(self):
        for tool in ("delete_object", "save_blend_file", "open_blend_file", "execute_blender_code", "sculpt_mesh", "unknown"):
            with self.subTest(tool=tool):
                self.assertEqual(self.request(tool=tool)["status"], "pending")

    def test_sculpt_is_not_added_to_existing_background_autoapproval_policy(self):
        params={"object_name":"Fixture","action":"voxel_remesh","expected_snapshot_id":"sha256:"+"a"*64,"voxel_size":0.05}
        self.assertFalse(_local_test_autoapproval(self.bpy,"sculpt_mesh",params))

    def test_render_paths_are_confined_and_never_overwrite(self):
        safe = {"output_path": str(self.root / "render.png"), "output_format": "PNG"}
        self.assertTrue(_local_test_autoapproval(self.bpy, "render_scene", safe))
        for args in ({}, {"output_path": "relative.png"},
                     {"output_path": str(self.root.parent / "outside.png")},
                     {**safe, "render_mode": "animation"}):
            self.assertFalse(_local_test_autoapproval(self.bpy, "render_scene", args))
        (self.root / "render.png").touch()
        self.assertFalse(_local_test_autoapproval(self.bpy, "render_scene", safe))

    def test_dispatcher_validation_and_credentials_are_preserved(self):
        original = self.bridge.send_command
        def send(command, params):
            if command == "request_approval":
                return {"status": "success", "result": handle_request_approval(self.bpy, params)}
            return original(command, params)
        self.bridge.send_command = send
        executor = BlenderExecutor(timeout=0.001)
        executor.client = self.bridge
        executor.enable_blender_approval(timeout=0.001)
        dispatcher = AgentDispatcher(executor=executor)
        invalid = dispatcher.dispatch_tool_call("create_material", {"name": "Invalid", "roughness": 2.0})
        self.assertFalse(invalid.is_success)
        self.assertEqual(len(self.registry._requests), 0)
        result = dispatcher.dispatch_tool_call("create_material", {"name": "Fixture"})
        self.assertTrue(result.is_success, result.message)
        self.assertEqual(len(self.bpy.data.materials.created), 1)
        self.assertTrue(next(iter(self.registry._requests.values())).executed)

    def test_smart_uv_alias_preserves_recorded_operation_binding(self):
        self.bpy.data.objects = {}
        self.bpy.context.scene.objects = {}
        for tool in ("uv_smart_project", "smart_project", "smart_uv_project", "uv_project"):
            with self.subTest(tool=tool):
                req = self.request({"name": "Missing"}, tool=tool)
                # Authorization succeeds; independent target validation still fails.
                with self.assertRaisesRegex(ValueError, "not found"):
                    handle_uv_smart_project(self.bpy, {"name": "Missing", "request_id": req["request_id"], "approval_token": req["approval_token"]})
                self.assertTrue(self.registry.get_request(req["request_id"]).executed)
        wrong = self.request({"name": "Missing"}, tool="create_material")
        with self.assertRaises(PermissionError):
            handle_uv_smart_project(self.bpy, {"name": "Missing", "request_id": wrong["request_id"], "approval_token": wrong["approval_token"]})
        self.assertFalse(self.registry.get_request(wrong["request_id"]).executed)

    def test_queue_guards_legacy_mutations_and_consumes_once(self):
        with patch("blender_addon.universal_mcp.bridge.main_thread_queue.get_approval_registry", return_value=self.registry):
            for tool in ("assign_material", "create_light", "configure_world", "create_camera", "configure_render_settings"):
                queue = MainThreadQueue(self.bpy)
                calls = []
                queue.register_handler(tool, lambda **kw: calls.append(kw) or {})
                def dispatch(params):
                    event, result = threading.Event(), {}
                    queue._queue.put(({"type": tool, "params": params}, event, result))
                    queue.drain_queue()
                    return result["response"]
                with self.subTest(tool=tool):
                    with patch.dict(os.environ, {"UMCP_LOCAL_TEST_AUTOAPPROVE": ""}):
                        self.assertEqual(dispatch({"trusted_approval": True})["status"], "error")
                    self.assertEqual(calls, [])
                    req = self.request(tool=tool)
                    params = {"name": "Fixture", "request_id": req["request_id"], "approval_token": req["approval_token"]}
                    self.assertEqual(dispatch(params)["status"], "success")
                    self.assertEqual(dispatch(params)["status"], "error")
                    self.assertEqual(len(calls), 1)

    def test_sculpt_v1_scope_permits_owned_and_rejects_unowned_or_tampered(self):
        from blender_addon.universal_mcp.bridge.local_test_scope import configure_fixture
        import blender_addon.universal_mcp.bridge.local_test_scope as lts
        mock_mesh = SimpleNamespace(as_pointer=lambda: 12345, shape_keys=None, animation_data=None, library=None)
        mock_obj = SimpleNamespace(name="SculptTarget", type="MESH", as_pointer=lambda: 54321, data=mock_mesh, modifiers=[], library=None)
        self.bpy.data.objects = {"SculptTarget": mock_obj}
        self.bpy.context.scene.objects = {"SculptTarget": mock_obj}
        lts._scope = None
        configure_fixture(self.bpy, self.root, [mock_obj], [])

        valid_params = {
            "object_name": "SculptTarget",
            "action": "voxel_remesh",
            "expected_snapshot_id": "sha256:" + "a" * 64,
            "voxel_size": 0.05,
        }
        with patch.dict(os.environ, {"UMCP_LOCAL_TEST_SCOPE": "sculpt_v1"}):
            self.assertTrue(_local_test_autoapproval(self.bpy, "sculpt_mesh", valid_params))
            self.assertFalse(_local_test_autoapproval(self.bpy, "sculpt_mesh", {**valid_params, "object_name": "Other"}))
            self.assertFalse(_local_test_autoapproval(self.bpy, "sculpt_mesh", {**valid_params, "approved": True}))
            self.assertFalse(_local_test_autoapproval(self.bpy, "sculpt_mesh", {**valid_params, "voxel_size": -1}))
            # Non-background test instance (VIEW_3D requirement)
            self.bpy.app.background = False
            self.assertTrue(_local_test_autoapproval(self.bpy, "sculpt_mesh", valid_params))
            self.assertFalse(_local_test_autoapproval(self.bpy, "create_primitive", {}))
            self.bpy.app.background = True
        self.assertFalse(_local_test_autoapproval(self.bpy, "sculpt_mesh", valid_params))

