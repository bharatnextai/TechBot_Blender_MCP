"""Typed modifier contract, authorization and truthful outcome checks."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from blender_addon.universal_mcp.bridge.modifier_contract import validate_modifier_params, structured_policy_params, verify_modifier_readback
from blender_addon.universal_mcp.bridge.modifier_tools import handle_configure_modifier, handle_inspect_modifiers
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from shared.schemas.tool_schemas import validate_tool_input, TOOL_DEFINITIONS
from shared.models.protocol_models import BridgeResponse
from shared.models.agent_contracts import AgentTask, TaskStatus
from mcp_service.agents.modeling import ModelingAgent
import tests.unit.test_scoped_test_policy as ledger_tests
from blender_addon.universal_mcp.bridge import local_test_scope


class Stack(list):
    active = None
    def move(self, old, new):
        self.insert(new, self.pop(old))
    def get(self, name):
        return next((mod for mod in self if mod.name == name), None)
    def new(self, name, type):
        mod = NS(name=name, type=type, levels=0, render_levels=0, width=.01, segments=1, thickness=.01)
        mod.profile_type = "SUPERELLIPSE"
        point = lambda x, y: NS(location=[x,y], bl_rna=NS(properties=[NS(identifier="location", type="FLOAT", is_readonly=False)]))
        mod.custom_profile = NS(points=[point(1,0),point(0,1)], bl_rna=NS(properties=[]), update=lambda: None)
        mod.bl_rna = NS(properties=[NS(identifier=key, type="STRING" if isinstance(value,str) else "FLOAT", is_readonly=False)
                                   for key,value in vars(mod).items() if key not in ("custom_profile", "bl_rna")])
        mod.keys = lambda: []
        self.append(mod)
        return mod


class TypedModifierTests(unittest.TestCase):
    def setUp(self):
        self.stack = Stack()
        self.obj = NS(name="Owned", type="MESH", modifiers=self.stack)
        self.bpy = NS(context=NS(mode="OBJECT", scene=NS(objects={"Owned": self.obj}, umcp_require_scene_mutation_approval=True)))
        self.registry = ApprovalRegistry()
        self.enterContext(patch("blender_addon.universal_mcp.bridge.modifier_tools.get_approval_registry", return_value=self.registry))
        self.params = dict(name="Owned", modifier_name="Bevel", modifier_type="BEVEL", action="add", properties={"width": .02, "segments": 2})

    def execute(self, params):
        req = self.registry.create_request("configure_modifier", params)
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)
        args = {**params, "request_id": req.request_id, "approval_token": token}
        return handle_configure_modifier(self.bpy, args), args

    def test_typed_schema_discovery_and_canonical_type(self):
        schema = TOOL_DEFINITIONS["configure_modifier"]["input_schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["properties"]["additionalProperties"])
        self.assertEqual(validate_tool_input("configure_modifier", self.params, trusted_approval=True)["modifier_type"], "BEVEL")
        self.assertEqual(TOOL_DEFINITIONS["inspect_modifiers"]["permission_tier"], "READ_ONLY")

    def test_invalid_contracts_fail_before_any_mutation(self):
        for args in ({**self.params, "code": "anything"}, {**self.params, "properties": {}},
                     {**self.params, "properties": {"levels": 1}}, {**self.params, "properties": {"width": float("nan")}},
                     {**self.params, "properties": {"segments": True}}, {**self.params, "properties": {"segments": 65}},
                     {**self.params, "properties": {"no_such_property": 1}}, {**self.params, "action": "apply"},
                     {**self.params, "modifier_type": "BOOLEAN"}, {**self.params, "modifier_name": " Bad "}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_modifier_params(args)
        self.assertEqual(len(self.stack), 0)

    def test_flags_are_not_credentials(self):
        with self.assertRaises(PermissionError):
            handle_configure_modifier(self.bpy, {**self.params, "approved": True, "trusted_approval": True})
        self.assertEqual(len(self.stack), 0)

    def test_sdk_schema_rejects_wrong_type_and_action_properties(self):
        from jsonschema import validate, ValidationError
        schema = TOOL_DEFINITIONS["configure_modifier"]["input_schema"]
        validate(self.params, schema)
        validate({**self.params, "action": "remove", "properties": {}}, schema)
        for args in ({**self.params, "properties": {"levels": 1}}, {**self.params, "properties": {}},
                     {**self.params, "action": "remove"}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                validate(args, schema)

    def test_token_tampering_expiry_and_cross_tool_replay_are_rejected(self):
        for expired, tool in ((False, "configure_modifier"), (True, "configure_modifier"), (False, "execute_blender_code")):
            registry = ApprovalRegistry()
            req = registry.create_request(tool, self.params)
            ok, token = registry.resolve_request(req.request_id, "approved")
            self.assertTrue(ok)
            if expired:
                req.created_at -= 1000
            args = {**self.params, "request_id": req.request_id, "approval_token": token}
            if not expired and tool == "configure_modifier":
                args["properties"] = {"width": .03}
            with self.subTest(expired=expired, tool=tool), patch("blender_addon.universal_mcp.bridge.modifier_tools.get_approval_registry", return_value=registry):
                with self.assertRaises(PermissionError):
                    handle_configure_modifier(self.bpy, args)
            self.assertEqual(len(self.stack), 0)

    def test_add_update_remove_and_read_only_postconditions(self):
        result, credentials = self.execute(self.params)
        inspection = handle_inspect_modifiers(self.bpy, {"name": "Owned"})
        self.assertTrue(verify_modifier_readback(self.params, result, inspection))
        with self.assertRaises(PermissionError):
            handle_configure_modifier(self.bpy, credentials)
        update = {**self.params, "action": "update", "properties": {"width": .04}}
        result, _ = self.execute(update)
        self.assertTrue(verify_modifier_readback(update, result, handle_inspect_modifiers(self.bpy, {"name": "Owned"})))
        remove = {key: value for key, value in {**self.params, "action": "remove"}.items() if key != "properties"}
        result, _ = self.execute(remove)
        self.assertTrue(verify_modifier_readback(remove, result, handle_inspect_modifiers(self.bpy, {"name": "Owned"})))
        self.assertEqual(len(self.stack), 0)

    def test_remove_postcondition_failure_restores_properties_order_and_active(self):
        self.execute(self.params)
        self.stack.new("Later", "SOLIDIFY")
        self.stack.active = self.stack[0]
        self.stack[0].segments = 7
        with patch("blender_addon.universal_mcp.bridge.modifier_tools._verify_stack", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.execute({**self.params, "action": "remove", "properties": {}})
        self.assertEqual([m.name for m in self.stack], ["Bevel", "Later"])
        self.assertEqual(self.stack[0].segments, 7)
        self.assertIs(self.stack.active, self.stack[0])

    def test_checkpoint_preserves_enum_flag_sets(self):
        from blender_addon.universal_mcp.bridge import modifier_checkpoint
        self.execute(self.params)
        mod=self.stack[0]
        mod.debug_options={'B','A'}
        mod.bl_rna.properties.append(NS(identifier='debug_options',type='ENUM',is_readonly=False,is_enum_flag=True))
        checkpoint=modifier_checkpoint.capture(self.obj,mod)
        mod.debug_options=set()
        modifier_checkpoint.restore(self.obj,checkpoint)
        self.assertEqual(mod.debug_options,{'A','B'})
        self.assertIsInstance(mod.debug_options,set)

    def test_unsafe_removal_checkpoint_rejected_without_changes(self):
        self.execute(self.params)
        self.stack[0].profile_type = "CUSTOM"
        with self.assertRaisesRegex(ValueError, "Custom bevel"):
            self.execute({**self.params, "action": "remove", "properties": {}})
        self.assertEqual(len(self.stack), 1)
        self.stack[0].profile_type = "SUPERELLIPSE"
        self.obj.animation_data = NS()
        with self.assertRaisesRegex(ValueError, "animated"):
            self.execute({**self.params, "action": "remove", "properties": {}})
        self.assertEqual(len(self.stack), 1)

    def test_collision_type_mismatch_and_edit_mode_are_errors(self):
        self.execute(self.params)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.execute(self.params)
        with self.assertRaisesRegex(ValueError, "requested type"):
            self.execute({**self.params, "modifier_type": "SOLIDIFY", "action": "remove", "properties": {}})
        self.bpy.context.mode = "EDIT_MESH"
        with self.assertRaisesRegex(ValueError, "Object mode"):
            self.execute({**self.params, "action": "update"})
        self.assertEqual(self.bpy.context.mode, "EDIT_MESH")

    def test_clamped_write_fails_and_removes_created_modifier(self):
        class Clamped:
            name = "Bevel"; type = "BEVEL"; segments = 1
            @property
            def width(self):
                return 0
            @width.setter
            def width(self, value):
                pass
        def create(**kwargs):
            value = Clamped(); self.stack.append(value); return value
        self.stack.new = create
        with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
            self.execute(self.params)
        self.assertEqual(len(self.stack), 0)

    def test_agent_rejects_success_when_independent_state_disagrees(self):
        result, _ = self.execute(self.params)
        inspection = handle_inspect_modifiers(self.bpy, {"name": "Owned"})
        task = AgentTask(task_id="typed-modifier", required_capability="modeling.modifiers", task_type="configure_modifier", input_params=self.params)
        valid = NS(execute_tool=Mock(side_effect=[BridgeResponse.success(result), BridgeResponse.success(inspection)]))
        self.assertEqual(ModelingAgent().execute_task(task, valid).status, TaskStatus.SUCCEEDED)
        invalid = NS(execute_tool=Mock(side_effect=[BridgeResponse.success(result), BridgeResponse.success({**inspection, "modifiers": []})]))
        outcome = ModelingAgent().execute_task(task, invalid)
        self.assertEqual(outcome.status, TaskStatus.FAILED)
        self.assertEqual(outcome.verification.status, "FAIL")

    def test_agent_nested_failure_or_unavailable_inspection_never_passes(self):
        task = AgentTask(task_id="typed-modifier", required_capability="modeling.modifiers", task_type="configure_modifier", input_params=self.params)
        for receipt in ({"success": False}, {}, {"success": True, "verified": True}):
            with self.subTest(receipt=receipt):
                executor = NS(execute_tool=Mock(side_effect=[BridgeResponse.success(receipt), BridgeResponse.error("unavailable")]))
                self.assertEqual(ModelingAgent().execute_task(task, executor).status, TaskStatus.FAILED)

    def test_policy_mapping_has_no_code_or_extra_operations(self):
        mapped = structured_policy_params(self.params)
        self.assertEqual(set(mapped), {"operations"})
        self.assertEqual(mapped["operations"][0]["action"], "add_modifier")
        self.assertEqual(mapped["operations"][0]["params"]["properties"], self.params["properties"])


class TypedModifierPolicyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ledger_tests.TestFixtureLedger()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp(); self.fixture.register()
        self.args = dict(name="OwnedMesh", modifier_name="OwnedSubsurf", modifier_type="SUBSURF", action="update", properties={"levels": 1}, approved=False)

    def allowed(self, args):
        return self.fixture.allowed("configure_modifier", args)

    def test_same_bounds_and_identity_as_existing_policy(self):
        self.assertTrue(self.allowed(self.args))
        for args in ({**self.args, "properties": {"levels": 3}}, {**self.args, "name": "Cube"},
                     {**self.args, "approved": True}, {**self.args, "request_id": "not-proof"},
                     {**self.args, "trusted_approval": True}, {**self.args, "task_id": "not-enrollment"},
                     {**self.args, "modifier_type": "BEVEL", "action": "remove", "properties": {}}):
            with self.subTest(args=args):
                self.assertFalse(self.allowed(args))

    def test_host_can_enroll_only_actual_planned_modifier_on_owned_object(self):
        modifier = ledger_tests.Block(name="FreshBevel", type="BEVEL")
        self.fixture.obj.modifiers[modifier.name] = modifier
        args = {**self.args, "modifier_name": modifier.name, "modifier_type": "BEVEL", "properties": {"width": .02}}
        self.assertFalse(self.allowed(args))
        local_test_scope.record_fixture_modifier(self.fixture.bpy, self.fixture.obj, modifier)
        self.assertTrue(self.allowed(args))
        stranger = ledger_tests.Block(name="Unowned", type="MESH", data=self.fixture.obj.data, modifiers=self.fixture.obj.modifiers)
        with self.assertRaises(ValueError):
            local_test_scope.record_fixture_modifier(self.fixture.bpy, stranger, modifier)
