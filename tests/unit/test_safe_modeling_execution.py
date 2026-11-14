"""
Unit Tests for Safe Modeling Execution Foundation (TASK-UMCP-0012).
Tests AST security validation, structured operations validation, trusted approval binding,
tampering rejection, replay rejection, execution, and transactional rollback.
"""

import unittest
from shared.schemas.tool_schemas import (
    validate_tool_input,
    validate_restricted_code_ast,
    TOOL_EXECUTE_BLENDER_CODE,
    PERMISSION_SCENE_MUTATION,
    TOOL_DEFINITIONS,
)
from blender_addon.universal_mcp.bridge.approval_registry import (
    ApprovalRegistry,
    compute_arg_hash,
)
from blender_addon.universal_mcp.bridge.handlers import handle_execute_blender_code


class TestASTSecurityValidation(unittest.TestCase):
    def test_import_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast("import os\nos.system('calc')")
        self.assertIn("Import", str(ctx.exception))

    def test_import_from_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast("from subprocess import Popen")
        self.assertIn("ImportFrom", str(ctx.exception))

    def test_class_definition_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast("class Exploit: pass")
        self.assertIn("ClassDef", str(ctx.exception))

    def test_try_except_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast("try:\n    pass\nexcept:\n    pass")
        self.assertIn("Try", str(ctx.exception))

    def test_global_and_delete_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast("global x\nx = 1")
        self.assertIn("Global", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast("del x")
        self.assertIn("Delete", str(ctx.exception))

    def test_banned_identifiers_rejected(self):
        banned_snippets = [
            "__import__('os')",
            "eval('1 + 1')",
            "exec('x = 1')",
            "open('secret.txt')",
            "compile('pass', '', 'exec')",
            "getattr(bpy, 'ops')",
            "setattr(bpy, 'foo', 1)",
            "os.system('calc')",
            "sys.exit(0)",
            "subprocess.run(['dir'])",
        ]
        for snippet in banned_snippets:
            with self.assertRaises(ValueError, msg=f"Should reject: {snippet}"):
                validate_restricted_code_ast(snippet)

    def test_private_and_dunder_attribute_rejected(self):
        snippets = [
            "x = obj.__class__",
            "x = obj.__subclasses__()",
            "x = obj._hidden_attr",
            "obj._secret = 123",
        ]
        for snippet in snippets:
            with self.assertRaises(ValueError, msg=f"Should reject private attr: {snippet}"):
                validate_restricted_code_ast(snippet)

    def test_disallowed_operator_rejected(self):
        disallowed = [
            "bpy.ops.wm.quit_blender()",
            "bpy.ops.wm.open_mainfile(filepath='hack.blend')",
            "bpy.ops.wm.save_as_mainfile(filepath='hack.blend')",
            "bpy.ops.wm.read_factory_settings()",
            "bpy.ops.script.python_file_run(filepath='exploit.py')",
        ]
        for op in disallowed:
            with self.assertRaises(ValueError, msg=f"Should reject operator: {op}") as ctx:
                validate_restricted_code_ast(op)
            self.assertIn("Disallowed operator call", str(ctx.exception))

    def test_allowlisted_operators_pass(self):
        valid_code = (
            "bpy.ops.object.shade_smooth()\n"
            "bpy.ops.object.modifier_add(type='SUBSURF')\n"
            "bpy.ops.mesh.subdivide(number_cuts=2)\n"
            "for i in range(5):\n"
            "    print(i)\n"
        )
        # Should not raise
        validate_restricted_code_ast(valid_code)

    def test_oversized_code_rejected(self):
        oversized = "x = 1\n" * 5000  # > 16384 characters
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast(oversized)
        self.assertIn("exceeds maximum allowed limit", str(ctx.exception))


class TestStructuredModelingSchemaValidation(unittest.TestCase):
    def test_permission_tier(self):
        tool_def = TOOL_DEFINITIONS[TOOL_EXECUTE_BLENDER_CODE]
        self.assertEqual(tool_def["permission_tier"], PERMISSION_SCENE_MUTATION)

    def test_missing_operations_and_code_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, {})
        self.assertIn("Either 'operations' (structured plan) or 'code' (restricted script)", str(ctx.exception))

    def test_non_transactional_rejected(self):
        payload = {
            "operations": [{"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}}],
            "transactional": False,
        }
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload)
        self.assertIn("Non-transactional execution is rejected", str(ctx.exception))

    def test_invalid_action_rejected(self):
        payload = {
            "operations": [{"action": "delete_all_files", "target": "Cube"}],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload)
        self.assertIn("is invalid. Allowed actions:", str(ctx.exception))

    def test_missing_target_rejected(self):
        payload = {
            "operations": [{"action": "add_modifier", "params": {"modifier_type": "SUBSURF"}}],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload)
        self.assertIn("requires a non-empty 'target'", str(ctx.exception))

    def test_invalid_modifier_type_rejected(self):
        payload = {
            "operations": [{"action": "add_modifier", "target": "Cube", "params": {"modifier_type": "INVALID_MOD"}}],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload)
        self.assertIn("requires a valid modifier type", str(ctx.exception))

    def test_subdivide_mesh_cuts_range(self):
        # cuts must be between 1 and 10
        payload_low = {
            "operations": [{"action": "subdivide_mesh", "target": "Cube", "params": {"cuts": 0}}],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload_low)
        self.assertIn("cuts' must be an integer between 1 and 10", str(ctx.exception))

        payload_high = {
            "operations": [{"action": "subdivide_mesh", "target": "Cube", "params": {"cuts": 20}}],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload_high)
        self.assertIn("cuts' must be an integer between 1 and 10", str(ctx.exception))


class MockModifier:
    def __init__(self, name: str, mod_type: str):
        self.name = name
        self.type = mod_type
        self.show_viewport = True
        self.show_render = True


class MockModifierStack(dict):
    def new(self, name: str, type: str = ""):
        mod = MockModifier(name, type)
        self[name] = mod
        return mod

    def remove(self, mod):
        if hasattr(mod, "name") and mod.name in self:
            del self[mod.name]

    def get(self, name):
        return super().get(name)


class MockObject:
    def __init__(self, name, obj_type="MESH"):
        self.name = name
        self.type = obj_type
        self.modifiers = MockModifierStack()
        self.material_slots = []
        self.data = type("MeshData", (), {"materials": []})() if obj_type == "MESH" else None
        self.parent = None
        self.selected = False

    def select_set(self, val):
        self.selected = val


class MockBpy:
    def __init__(self):
        self.undo_steps = []
        self._undo_stack = []

        def _undo_push(*args, **kwargs):
            self.undo_steps.append("push")
            snap = {}
            for k, obj in self.data.objects.items():
                if hasattr(obj, "modifiers"):
                    snap[k] = list(obj.modifiers.keys())
            self._undo_stack.append(snap)

        def _undo(*args, **kwargs):
            self.undo_steps.append("undo")
            if self._undo_stack:
                snap = self._undo_stack.pop()
                for k, mod_names in snap.items():
                    if k in self.data.objects and hasattr(self.data.objects[k], "modifiers"):
                        obj = self.data.objects[k]
                        for m in list(obj.modifiers.keys()):
                            if m not in mod_names:
                                del obj.modifiers[m]
            return {'FINISHED'}

        self.data = type("Data", (), {
            "objects": {},
            "materials": type("Materials", (), {
                "_mats": {},
                "new": lambda *args, **kwargs: type("Mat", (), {"name": kwargs.get("name", ""), "use_nodes": False, "node_tree": None})(),
                "get": lambda *args, **kwargs: None,
            })(),
        })()
        self.context = type("Context", (), {
            "view_layer": type("ViewLayer", (), {
                "objects": type("ActiveObjHolder", (), {"active": None})(),
                "update": lambda *args, **kwargs: None,
            })(),
        })()
        self.ops = type("Ops", (), {
            "ed": type("EdOps", (), {
                "undo_push": _undo_push,
                "undo": _undo,
            })(),
            "object": type("ObjectOps", (), {
                "select_all": lambda *args, **kwargs: None,
                "shade_smooth": lambda *args, **kwargs: None,
                "shade_flat": lambda *args, **kwargs: None,
                "mode_set": lambda *args, **kwargs: None,
                "join": lambda *args, **kwargs: None,
            })(),
            "mesh": type("MeshOps", (), {
                "select_all": lambda *args, **kwargs: None,
                "subdivide": lambda *args, **kwargs: None,
            })(),
        })()


class TestModelingExecutionAndSecurityBoundary(unittest.TestCase):
    def setUp(self):
        from blender_addon.universal_mcp.bridge import approval_registry
        self.registry = ApprovalRegistry()
        approval_registry._global_registry = self.registry
        self.bpy = MockBpy()
        self.cube = MockObject("Cube", "MESH")
        self.bpy.data.objects["Cube"] = self.cube

    def tearDown(self):
        from blender_addon.universal_mcp.bridge import approval_registry
        approval_registry._global_registry = None

    def test_untrusted_approved_flag_rejected(self):
        payload = {
            "operations": [{"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}}],
            "approved": True,
        }
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize scene mutation", str(ctx.exception))

    def test_missing_credentials_rejected_by_handler(self):
        params = {
            "operations": [{"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}}],
        }
        with self.assertRaises(PermissionError) as ctx:
            handle_execute_blender_code(bpy_module=self.bpy, params=params)
        self.assertIn("Missing trusted human approval credentials", str(ctx.exception))

    def test_successful_approval_and_execution(self):
        from blender_addon.universal_mcp.bridge import handlers
        handlers._approval_registry = self.registry

        params = {
            "operations": [
                {"action": "add_modifier", "target": "Cube", "params": {"modifier_type": "SUBSURF", "name": "SubsurfMod"}},
                {"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}},
            ],
            "transactional": True,
        }
        req = self.registry.create_request(TOOL_EXECUTE_BLENDER_CODE, params)
        req_id = req.request_id
        ok, res = self.registry.resolve_request(req_id, "approved")
        self.assertTrue(ok)
        token = res

        exec_params = dict(params)
        exec_params["request_id"] = req_id
        exec_params["approval_token"] = token

        result = handle_execute_blender_code(bpy_module=self.bpy, params=exec_params)
        self.assertTrue(result["executed"])
        self.assertEqual(result["operations_count"], 2)
        self.assertIn("SubsurfMod", self.cube.modifiers)
        self.assertIn("push", self.bpy.undo_steps)

    def test_tampered_parameters_rejected(self):
        from blender_addon.universal_mcp.bridge import handlers
        handlers._approval_registry = self.registry

        original_params = {
            "operations": [{"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}}],
        }
        req = self.registry.create_request(TOOL_EXECUTE_BLENDER_CODE, original_params)
        req_id = req.request_id
        ok, token = self.registry.resolve_request(req_id, "approved")
        self.assertTrue(ok)

        # Tamper with the parameters (change shade mode to FLAT)
        tampered_params = {
            "operations": [{"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "FLAT"}}],
            "request_id": req_id,
            "approval_token": token,
        }
        with self.assertRaises(PermissionError) as ctx:
            handle_execute_blender_code(bpy_module=self.bpy, params=tampered_params)
        self.assertIn("tampering detected", str(ctx.exception).lower())

    def test_single_use_token_replay_rejected(self):
        from blender_addon.universal_mcp.bridge import handlers
        handlers._approval_registry = self.registry

        params = {
            "operations": [{"action": "set_shade_mode", "target": "Cube", "params": {"shade_mode": "SMOOTH"}}],
        }
        req = self.registry.create_request(TOOL_EXECUTE_BLENDER_CODE, params)
        req_id = req.request_id
        ok, token = self.registry.resolve_request(req_id, "approved")
        self.assertTrue(ok)

        exec_params = dict(params)
        exec_params["request_id"] = req_id
        exec_params["approval_token"] = token

        # First consumption succeeds
        res1 = handle_execute_blender_code(bpy_module=self.bpy, params=exec_params)
        self.assertTrue(res1["executed"])

        # Second attempt (replay) must be rejected
        with self.assertRaises(PermissionError) as ctx:
            handle_execute_blender_code(bpy_module=self.bpy, params=exec_params)
        self.assertIn("already been consumed", str(ctx.exception))

    def test_transactional_rollback_on_failure(self):
        from blender_addon.universal_mcp.bridge import handlers
        handlers._approval_registry = self.registry

        params = {
            "operations": [
                {"action": "add_modifier", "target": "Cube", "params": {"modifier_type": "SUBSURF", "name": "SubsurfMod"}},
                # Target NonExistent object to trigger error
                {"action": "set_shade_mode", "target": "NonExistentObject", "params": {"shade_mode": "SMOOTH"}},
            ],
            "transactional": True,
        }
        req = self.registry.create_request(TOOL_EXECUTE_BLENDER_CODE, params)
        req_id = req.request_id
        ok, token = self.registry.resolve_request(req_id, "approved")
        self.assertTrue(ok)

        exec_params = dict(params)
        exec_params["request_id"] = req_id
        exec_params["approval_token"] = token

        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.bpy, params=exec_params)
        self.assertIn("Modeling execution failed and scene changes were rolled back", str(ctx.exception))
        self.assertIn("undo", self.bpy.undo_steps)

    def test_compensating_journal_cleans_up_created_objects_on_failure(self):
        """Verifies that UniversalMutationJournal removes objects created during a partially-failed script."""
        from blender_addon.universal_mcp.bridge import handlers
        handlers._approval_registry = self.registry

        # Pre-existing object Cube
        self.assertIn("Cube", self.bpy.data.objects)

        # Code that creates a new object in bpy.data.objects and then fails
        failing_code = (
            "bpy.data.objects['Temp_Leaked_Obj'] = 'leaked_data'\n"
            "assert False, 'Mid-script failure after object creation'\n"
        )
        params = {
            "code": failing_code,
            "transactional": True,
        }
        req = self.registry.create_request(TOOL_EXECUTE_BLENDER_CODE, params)
        req_id = req.request_id
        ok, token = self.registry.resolve_request(req_id, "approved")
        self.assertTrue(ok)

        exec_params = dict(params)
        exec_params["request_id"] = req_id
        exec_params["approval_token"] = token

        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.bpy, params=exec_params)

        self.assertIn("Mid-script failure after object creation", str(ctx.exception))
        # Created object must be cleaned up
        self.assertNotIn("Temp_Leaked_Obj", self.bpy.data.objects)
        # Pre-existing Cube must remain
        self.assertIn("Cube", self.bpy.data.objects)

    def test_undo_success_with_dirty_scene_reports_dirty_not_rollback(self):
        """
        Regression Test for TASK-UMCP-0054 (Requirement A.2):
        When Blender undo reports success ({'FINISHED'}), but journal verification detects
        that pre-existing data-blocks remain dirty (e.g. un-undone modifier or coordinate change),
        handle_execute_blender_code must report DIRTY state and NEVER claim successful rollback.
        """
        from blender_addon.universal_mcp.bridge import handlers
        handlers._approval_registry = self.registry

        # Setup mock undo that reports {'FINISHED'} but intentionally does NOT revert scene
        self.bpy.ops.ed.undo = lambda *args, **kwargs: {'FINISHED'}

        params = {
            "operations": [
                {"action": "add_modifier", "target": "Cube", "params": {"modifier_type": "SUBSURF", "name": "UnrestoredMod"}},
                # Target NonExistent object to trigger error
                {"action": "set_shade_mode", "target": "NonExistentObject", "params": {"shade_mode": "SMOOTH"}},
            ],
            "transactional": True,
        }
        req = self.registry.create_request(TOOL_EXECUTE_BLENDER_CODE, params)
        req_id = req.request_id
        ok, token = self.registry.resolve_request(req_id, "approved")
        self.assertTrue(ok)

        exec_params = dict(params)
        exec_params["request_id"] = req_id
        exec_params["approval_token"] = token

        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.bpy, params=exec_params)

        err_msg = str(ctx.exception)
        # Must report DIRTY state
        self.assertIn("DIRTY state", err_msg)
        self.assertIn("could not be fully rolled back", err_msg)
        # Must NEVER falsely claim that scene changes were rolled back
        self.assertNotIn("and scene changes were rolled back", err_msg)

    def test_undo_push_failure_prevents_calling_undo(self):
        """
        TASK-UMCP-0056 (Requirement 1):
        When bpy.ops.ed.undo_push() fails or raises an exception during setup,
        handle_execute_blender_code must NOT invoke bpy.ops.ed.undo() on failure,
        preventing accidental reversion of unrelated prior user actions.
        """
        from blender_addon.universal_mcp.bridge import handlers
        handlers._approval_registry = self.registry

        # Setup undo_push to fail
        def failing_push(*args, **kwargs):
            raise RuntimeError("Context incorrect for undo_push")

        undo_called = []
        def track_undo(*args, **kwargs):
            undo_called.append(True)
            return {'FINISHED'}

        self.bpy.ops.ed.undo_push = failing_push
        self.bpy.ops.ed.undo = track_undo

        params = {
            "operations": [
                {"action": "set_shade_mode", "target": "NonExistentObject", "params": {"shade_mode": "SMOOTH"}},
            ],
            "transactional": True,
        }
        req = self.registry.create_request(TOOL_EXECUTE_BLENDER_CODE, params)
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        exec_params = dict(params)
        exec_params["request_id"] = req.request_id
        exec_params["approval_token"] = token

        with self.assertRaises(RuntimeError):
            handle_execute_blender_code(bpy_module=self.bpy, params=exec_params)

        # undo() must NEVER be called because undo_push failed!
        self.assertEqual(len(undo_called), 0, "undo() was called even though undo_push failed!")


if __name__ == "__main__":
    unittest.main()
