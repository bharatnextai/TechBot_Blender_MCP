"""Typed shader authorization, graph preservation and false-success checks."""
import os
import unittest
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from jsonschema import validate, ValidationError
from blender_addon.universal_mcp.bridge.material_shader_contract import validate_material_shader, verify_material_shader
from blender_addon.universal_mcp.bridge.material_shader_tools import handle_configure_material_shader, handle_inspect_material_shader
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from shared.schemas.tool_schemas import TOOL_DEFINITIONS
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.materials import MaterialsAgent
import tests.unit.test_scoped_test_policy as isolation


class Nodes(list):
    def __init__(self, links):
        super().__init__(); self.links = links
    def get(self, name):
        return next((node for node in self if node.name == name), None)
    def new(self, kind):
        values = {"Scale": 5., "Detail": 2., "Roughness": .5, "Distortion": 0.}
        node = NS(name="Noise Texture", bl_idname=kind, inputs=[], outputs=[])
        node.inputs = [NS(identifier=key, default_value=value, is_linked=False, node=node) for key, value in values.items()]
        node.outputs = [NS(identifier="Color", is_linked=False, node=node), NS(identifier="Fac", is_linked=False, node=node)]
        self.append(node); return node
    def remove(self, node):
        for link in list(self.links):
            if link.from_node == node or link.to_node == node:
                self.links.remove(link)
        super().remove(node)


class Links(list):
    def new(self, output, input_socket):
        output.is_linked = input_socket.is_linked = True
        self.append(NS(from_node=output.node, to_node=input_socket.node, from_socket=output, to_socket=input_socket))
    def remove(self, link):
        super().remove(link)
        link.from_socket.is_linked = any(other.from_socket == link.from_socket for other in self)
        link.to_socket.is_linked = any(other.to_socket == link.to_socket for other in self)


class TypedMaterialShaderTests(unittest.TestCase):
    def setUp(self):
        self.links = Links(); self.nodes = Nodes(self.links)
        self.bsdf = NS(name="Principled BSDF", bl_idname="ShaderNodeBsdfPrincipled", inputs=[])
        self.bsdf.inputs = [NS(identifier=key, default_value=value, is_linked=False, node=self.bsdf) for key, value in {
            "Base Color": [.8, .8, .8, 1.], "Metallic": 0., "Roughness": .5, "IOR": 1.45}.items()]
        self.bsdf.outputs = [NS(identifier="BSDF", is_linked=False, node=self.bsdf)]
        output = NS(name="Material Output", bl_idname="ShaderNodeOutputMaterial", is_active_output=True)
        output.inputs = [NS(identifier="Surface", is_linked=False, node=output)]
        self.nodes.append(self.bsdf)
        self.nodes.append(output)
        self.links.new(self.bsdf.outputs[0], output.inputs[0])
        self.material = NS(name="Mat", use_nodes=True, node_tree=NS(nodes=self.nodes, links=self.links))
        self.bpy = NS(data=NS(materials={"Mat": self.material}), context=NS(scene=NS(umcp_require_scene_mutation_approval=True)))
        self.registry = ApprovalRegistry()
        self.enterContext(patch("blender_addon.universal_mcp.bridge.material_shader_tools.get_approval_registry", return_value=self.registry))
        self.args = dict(target_name="Mat", bsdf_node_name="Principled BSDF", action="set_principled", inputs={"roughness": .68})

    def inspect(self):
        return handle_inspect_material_shader(self.bpy, {"target_name": "Mat"})

    def execute(self, args):
        request = self.registry.create_request("configure_material_shader", args)
        ok, token = self.registry.resolve_request(request.request_id, "approved"); self.assertTrue(ok)
        credentials = {**args, "request_id": request.request_id, "approval_token": token}
        return handle_configure_material_shader(self.bpy, credentials), credentials

    def noise(self, action, values=None):
        args = dict(target_name="Mat", bsdf_node_name="Principled BSDF", noise_node_name="TypedNoise", action=action)
        if values is not None:
            args["noise_inputs"] = values
        return args

    def test_conditional_schemas_and_finite_validation(self):
        schema = TOOL_DEFINITIONS["configure_material_shader"]["input_schema"]
        validate(self.args, schema)
        validate(self.noise("add_noise", {"scale": 2}), schema)
        for args in ({**self.args, "inputs": {}}, {**self.args, "inputs": {"unknown": 1}},
                     {**self.args, "inputs": {"roughness": True}}, {**self.args, "inputs": {"base_color": [1, 0, 0]}},
                     self.noise("remove_noise", {"scale": 1}), {**self.args, "noise_node_name": "Invalid"}):
            with self.subTest(args=args), self.assertRaises((ValidationError, ValueError)):
                validate(args, schema); validate_material_shader(args)
        for value in (float("nan"), float("inf"), -1, 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_material_shader({**self.args, "inputs": {"roughness": value}})

    def test_read_only_inspection_never_enables_nodes(self):
        self.material.use_nodes = False
        result = self.inspect()
        self.assertTrue(result["verified"]); self.assertEqual(result["nodes"], [])
        self.assertFalse(self.material.use_nodes)

    def test_principled_write_and_single_use(self):
        result, credentials = self.execute(self.args)
        self.assertTrue(verify_material_shader(self.args, result, self.inspect()))
        with self.assertRaises(PermissionError):
            handle_configure_material_shader(self.bpy, credentials)

    def test_flags_and_cross_tool_tokens_are_not_authorization(self):
        with self.assertRaises(PermissionError):
            handle_configure_material_shader(self.bpy, {**self.args, "approved": True, "trusted_approval": True})
        request = self.registry.create_request("manage_shader_nodes", self.args)
        _, token = self.registry.resolve_request(request.request_id, "approved")
        with self.assertRaises(PermissionError):
            handle_configure_material_shader(self.bpy, {**self.args, "request_id": request.request_id, "approval_token": token})

    def test_parameter_tampering_and_expiry_fail_without_writes(self):
        for expired in (False, True):
            request = self.registry.create_request("configure_material_shader", self.args)
            _, token = self.registry.resolve_request(request.request_id, "approved")
            if expired:
                request.created_at -= 1000
            args = {**self.args, "request_id": request.request_id, "approval_token": token}
            if not expired:
                args["inputs"] = {"roughness": .69}
            with self.subTest(expired=expired), self.assertRaises(PermissionError):
                handle_configure_material_shader(self.bpy, args)
            self.assertEqual(self.bsdf.inputs[2].default_value, .5)

    def test_clamped_input_fails_and_restores(self):
        class Clamped:
            identifier = "Roughness"; is_linked = False
            value = .5
            @property
            def default_value(self):
                return self.value
            @default_value.setter
            def default_value(self, value):
                self.value = min(.5, value)
        self.bsdf.inputs[2] = Clamped()
        with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
            self.execute(self.args)
        self.assertEqual(self.bsdf.inputs[2].default_value, .5)

    def test_thread_guard_runs_before_blender_access(self):
        class Sentinel:
            def __getattribute__(self, key):
                raise AssertionError("Blender accessed off main thread")
        errors = []
        def worker():
            try:
                handle_inspect_material_shader(Sentinel(), {"target_name": "Mat"})
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=worker); thread.start(); thread.join()
        self.assertEqual(len(errors), 1); self.assertIsInstance(errors[0], RuntimeError)

    def test_noise_add_update_remove_restores_graph(self):
        before = self.inspect()
        for action, values in (("add_noise", {"scale": 2, "detail": 2}), ("update_noise", {"scale": 8, "roughness": .7}), ("remove_noise", None)):
            args = self.noise(action, values)
            result, _ = self.execute(args)
            self.assertTrue(verify_material_shader(args, result, self.inspect()))
        self.assertEqual(before, self.inspect())

    def test_missing_socket_does_not_fall_back_or_create_node(self):
        self.bsdf.inputs = [socket for socket in self.bsdf.inputs if socket.identifier != "Base Color"]
        with self.assertRaisesRegex(ValueError, "socket"):
            self.execute(self.noise("add_noise", {"scale": 2}))
        self.assertEqual(len(self.nodes), 2)

    def test_orphan_principled_is_not_reported_as_effective_surface_change(self):
        self.links.remove(self.links[0])
        with self.assertRaisesRegex(ValueError, "directly feed"):
            self.execute(self.args)
        self.assertEqual(self.bsdf.inputs[2].default_value, .5)

    def test_link_conflicts_preserve_unrelated_graph(self):
        noise = self.nodes.new("ShaderNodeTexNoise"); noise.name = "Existing"
        self.links.new(noise.outputs[0], self.bsdf.inputs[0])
        before = self.inspect()
        with self.assertRaisesRegex(ValueError, "already linked"):
            self.execute(self.noise("add_noise", {"scale": 2}))
        self.assertEqual(before, self.inspect())

    def test_noise_update_or_remove_rejects_additional_connections(self):
        self.execute(self.noise("add_noise", {"scale": 2}))
        noise = self.nodes.get("TypedNoise")
        self.links.new(noise.outputs[1], self.bsdf.inputs[2])
        before = self.inspect()
        for args in (self.noise("update_noise", {"scale": 8}), self.noise("remove_noise")):
            with self.subTest(action=args["action"]), self.assertRaisesRegex(ValueError, "conflicting"):
                self.execute(args)
            self.assertEqual(before, self.inspect())
        with self.assertRaisesRegex(ValueError, "linked shader input"):
            self.execute({**self.args, "inputs": {"base_color": [.4, .1, .1, 1]}})
        self.assertEqual(before, self.inspect())

    def test_agent_requires_separate_matching_readback(self):
        result, _ = self.execute(self.args)
        task = AgentTask(task_id="typed-shader", task_type="configure_material_shader", required_capability="materials.typed_shader", input_params=self.args)
        executor = NS(execute_tool=Mock(side_effect=[BridgeResponse.success(result), BridgeResponse.success(self.inspect())]))
        self.assertEqual(MaterialsAgent().execute_task(task, executor, trusted_approval=True).status, TaskStatus.SUCCEEDED)
        executor = NS(execute_tool=Mock(side_effect=[BridgeResponse.success(result), BridgeResponse.error("unavailable")]))
        outcome = MaterialsAgent().execute_task(task, executor, trusted_approval=True)
        self.assertEqual(outcome.status, TaskStatus.FAILED); self.assertEqual(outcome.verification.status, "FAIL")

    def test_agent_nested_failure_is_not_pass_or_claimed_rollback(self):
        task = AgentTask(task_id="typed-shader", task_type="configure_material_shader", required_capability="materials.typed_shader", input_params=self.args)
        executor = NS(execute_tool=Mock(return_value=BridgeResponse.success({"success": False})))
        outcome = MaterialsAgent().execute_task(task, executor, trusted_approval=True)
        self.assertEqual(outcome.status, TaskStatus.FAILED)
        self.assertEqual(outcome.verification.observed_results["transaction_status"], "ROLLBACK_UNVERIFIED")


class TypedShaderIsolationTests(unittest.TestCase):
    def test_existing_shader_policy_guards_and_no_extra_powers(self):
        fixture = isolation.TestFixtureLedger(); self.addCleanup(fixture.doCleanups); fixture.setUp()
        args = dict(target_name="FixtureMat", bsdf_node_name="Principled BSDF", action="set_principled", inputs={"roughness": .68}, approved=False)
        self.assertTrue(fixture.allowed("configure_material_shader", args))
        for override in ({"approved": True}, {"trusted_approval": True}, {"request_id": "not-proof"}, {"code": "anything"}):
            self.assertFalse(fixture.allowed("configure_material_shader", {**args, **override}))
        with patch.dict(os.environ, {"UMCP_LOCAL_TEST_AUTOAPPROVE": ""}):
            self.assertFalse(fixture.allowed("configure_material_shader", args))
        fixture.bpy.data.filepath = "user.blend"
        self.assertFalse(fixture.allowed("configure_material_shader", args))
