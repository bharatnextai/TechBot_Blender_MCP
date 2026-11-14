"""Scoped policy: production predicate, actual registry tokens, fake ownership."""
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import tests.policy_review.test_candidate as review
from blender_addon.universal_mcp.bridge import local_test_scope as scope
from blender_addon.universal_mcp.bridge.handlers import _local_test_autoapproval, handle_request_approval
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue


class TestIntegratedPredicate(review.TestScopedCandidate):
    def allowed(self, tool, params):
        return scope.permits(tool, params, **self.host)


class Items(dict):
    def __iter__(self):
        return iter(self.values())


class Block(NS):
    def as_pointer(self):
        return id(self)


class TestFixtureLedger(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="umcp-scope-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = {"UMCP_LOCAL_TEST_AUTOAPPROVE": "1", "UMCP_LOCAL_TEST_SCOPE": "modifier_bake_v1",
                    "UMCP_LOCAL_TEST_ROOT": str(self.root), "UMCP_BRIDGE_PORT": "19877"}
        for key in ("BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_EXTENSIONS"):
            directory = self.root / key; directory.mkdir(); self.env[key] = str(directory)
        self.enterContext(patch.dict(os.environ, self.env))
        self.enterContext(patch.object(scope, "_scope", None))
        self.material = Block(use_nodes=True)
        self.modifier = Block(name="OwnedSubsurf", type="SUBSURF")
        self.obj = Block(name="OwnedMesh", type="MESH", data=Block(uv_layers=[1], materials=[self.material]),
                         modifiers=Items(OwnedSubsurf=self.modifier))
        self.bpy = NS(app=NS(background=True), data=NS(filepath="", objects=Items(OwnedMesh=self.obj), images={}),
                      context=NS(mode="OBJECT", selected_objects=[self.obj], view_layer=NS(objects=NS(active=self.obj)),
                      scene=NS(umcp_bridge_port=19877, umcp_require_scene_mutation_approval=True)))
        self.params = {"operations": [{"action": "modify_modifier", "target": "OwnedMesh", "params": {
            "modifier_name": "OwnedSubsurf", "properties": {"levels": 1}}}], "transactional": True, "approved": False}

    def register(self):
        scope.configure_fixture(self.bpy, self.root, [self.obj], [self.material])

    def allowed(self, tool="execute_blender_code", params=None):
        return _local_test_autoapproval(self.bpy, tool, self.params if params is None else params)

    def test_no_ledger_no_flag_default_and_original_guards(self):
        self.assertFalse(self.allowed())
        self.register(); self.assertTrue(self.allowed())
        for key, value in (("UMCP_LOCAL_TEST_SCOPE", ""), ("UMCP_LOCAL_TEST_AUTOAPPROVE", ""),
                           ("UMCP_BRIDGE_PORT", "9877"), ("BLENDER_USER_CONFIG", "")):
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                self.assertFalse(self.allowed())
        self.bpy.app.background = False
        self.assertFalse(self.allowed())

    def test_object_mesh_modifier_identity_and_root(self):
        self.register()
        self.bpy.data.objects["OwnedMesh"] = Block(**vars(self.obj))
        self.assertFalse(self.allowed())
        self.bpy.data.objects["OwnedMesh"] = self.obj
        original = self.obj.data
        self.obj.data = Block(**vars(original)); self.assertFalse(self.allowed()); self.obj.data = original
        self.obj.modifiers["OwnedSubsurf"] = Block(name="OwnedSubsurf", type="SUBSURF")
        self.assertFalse(self.allowed())
        self.assertFalse(scope.permits_owned(self.bpy, "execute_blender_code", self.params, self.root.parent))

    def test_bake_preconditions(self):
        self.register()
        args = dict(object_name="OwnedMesh", image_name="FreshImage", bake_type="ROUGHNESS", width=64,
                    height=64, margin=2, save_filepath=str(self.root / "bake.png"), use_selected_to_active=False, approved=False)
        self.assertTrue(self.allowed("bake_object_texture", args))
        self.bpy.context.selected_objects = []
        self.assertFalse(self.allowed("bake_object_texture", args))
        self.bpy.context.selected_objects = [self.obj]
        self.obj.data.materials = [Block(use_nodes=True)]
        self.assertFalse(self.allowed("bake_object_texture", args))
        self.obj.data.materials = [self.material]
        self.bpy.data.images["FreshImage"] = object()
        self.assertFalse(self.allowed("bake_object_texture", args))

    def test_registry_hash_expiry_and_single_use(self):
        self.register()
        registry = ApprovalRegistry()
        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry):
            req = handle_request_approval(self.bpy, {"tool_name": "execute_blender_code", "params": self.params})
        self.assertEqual(req["status"], "approved")
        args = {**self.params, "request_id": req["request_id"], "approval_token": req["approval_token"]}
        self.assertFalse(registry.consume_approval(req["request_id"], req["approval_token"], "execute_blender_code", {**args, "code": "pass"})[0])
        self.assertTrue(registry.consume_approval(req["request_id"], req["approval_token"], "execute_blender_code", args)[0])
        self.assertFalse(registry.consume_approval(req["request_id"], req["approval_token"], "execute_blender_code", args)[0])
        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry):
            expired = handle_request_approval(self.bpy, {"tool_name": "execute_blender_code", "params": self.params})
        registry.get_request(expired["request_id"]).created_at -= 1000
        self.assertFalse(registry.consume_approval(expired["request_id"], expired["approval_token"], "execute_blender_code", self.params)[0])

    def test_queue_rechecks_ownership_before_execution(self):
        self.register()
        registry = ApprovalRegistry()
        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry), patch("blender_addon.universal_mcp.bridge.main_thread_queue.get_approval_registry", return_value=registry):
            req = handle_request_approval(self.bpy, {"tool_name": "execute_blender_code", "params": self.params})
            self.bpy.data.objects["OwnedMesh"] = Block(**vars(self.obj))
            queue = MainThreadQueue(self.bpy); calls = []
            queue.register_handler("execute_blender_code", lambda **kwargs: calls.append(kwargs))
            event = threading.Event(); result = {}
            queue._queue.put(({"type": "execute_blender_code", "params": {**self.params,
                "request_id": req["request_id"], "approval_token": req["approval_token"]}}, event, result))
            queue.drain_queue()
            self.assertEqual(result["response"]["status"], "error")
            self.assertEqual(calls, [])
            self.assertFalse(registry.get_request(req["request_id"]).executed)

    def test_flags_cannot_authorize_or_replace_ledger(self):
        self.register()
        for flag in ("approved", "trusted_approval", "_trusted_approval", "_trusted_test_override"):
            self.assertFalse(self.allowed(params={**self.params, flag: True}))
        with self.assertRaises(RuntimeError):
            self.register()
