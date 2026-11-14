"""Failure-oriented checks for modifier and bake outcomes; no live connection."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from blender_addon.universal_mcp.bridge.handlers import handle_bake_object_texture, handle_execute_blender_code
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from mcp_service.agents.materials import MaterialsAgent
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from tests.unit.test_safe_modeling_execution import MockBpy, MockObject


class ModifierFailureTests(unittest.TestCase):
    def test_whole_capability_evidence_is_not_routing_eligibility(self):
        from mcp_service.agents.modeling import ModelingAgent
        from mcp_service.agents.render_lighting import RenderLightingAgent
        for agent in (ModelingAgent(), MaterialsAgent(), RenderLightingAgent()):
            with self.subTest(agent=agent.agent_id):
                audit = agent.manifest.constraints["e2e_audit"]
                self.assertEqual(audit["verification_status"], "NOT VERIFIED")
                self.assertEqual(audit["implementation_status"], "PARTIALLY IMPLEMENTED")

    def test_clamped_modifier_assignment_is_failure(self):
        class Clamped:
            name = "Existing"
            type = "SUBSURF"
            @property
            def levels(self):
                return 2
            @levels.setter
            def levels(self, value):
                pass
        bpy = MockBpy(); obj = MockObject("Cube"); bpy.data.objects["Cube"] = obj
        obj.modifiers["Existing"] = Clamped()
        params = {"operations": [{"action": "modify_modifier", "target": "Cube", "params": {
            "modifier_name": "Existing", "properties": {"levels": 3}}}]}
        registry = ApprovalRegistry(); req = registry.create_request("execute_blender_code", params)
        ok, token = registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)
        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry):
            with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
                handle_execute_blender_code(bpy, {**params, "request_id": req.request_id, "approval_token": token})

    def test_unknown_property_is_not_silently_skipped(self):
        bpy = MockBpy(); obj = MockObject("Cube"); bpy.data.objects["Cube"] = obj
        obj.modifiers.new("Existing", "BEVEL")
        params = {"operations": [{"action": "modify_modifier", "target": "Cube", "params": {
            "modifier_name": "Existing", "properties": {"not_a_property": 1}}}]}
        registry = ApprovalRegistry(); req = registry.create_request("execute_blender_code", params)
        ok, token = registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)
        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry):
            with self.assertRaisesRegex(RuntimeError, "Unknown modifier property"):
                handle_execute_blender_code(bpy, {**params, "request_id": req.request_id, "approval_token": token})


class BakeReadbackTests(unittest.TestCase):
    def setUp(self):
        self.node = NS(select=False)
        class Nodes(list):
            pass
        self.nodes = Nodes([self.node])
        self.nodes.active = self.node
        self.nodes.new = Mock(return_value=NS(select=False))
        self.nodes.remove = Mock()
        self.mat = NS(node_tree=NS(nodes=self.nodes))
        self.obj = NS(type="MESH", name="Owned", data=NS(uv_layers=[1], materials=[self.mat]), select_set=Mock())
        self.image = NS(size=[64, 64], has_data=True, pixels=[.68, .68, .68, 1], name="Bake", colorspace_settings=NS(name="sRGB"))
        self.operator = Mock(return_value={"FINISHED"})
        self.bpy = NS(data=NS(objects={"Owned": self.obj}, images=NS(get=lambda name: self.image)),
                      ops=NS(object=NS(bake=self.operator)), context=NS(scene=NS(render=NS(engine="BLENDER_EEVEE")),
                      selected_objects=[self.obj], view_layer=NS(objects=NS(active=self.obj))))
        self.enterContext(patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=None))

    def call(self):
        return handle_bake_object_texture(self.bpy, dict(object_name="Owned", image_name="Bake", bake_type="ROUGHNESS", width=64, height=64))

    def test_cancelled_operator_is_failure_and_restores_engine_and_node(self):
        self.operator.return_value = {"CANCELLED"}
        with self.assertRaisesRegex(RuntimeError, "did not finish"):
            self.call()
        self.assertEqual(self.bpy.context.scene.render.engine, "BLENDER_EEVEE")
        self.assertIs(self.nodes.active, self.node)
        self.nodes.remove.assert_called_once()

    def test_bad_image_readback_is_failure(self):
        self.image.has_data = False
        with self.assertRaisesRegex(RuntimeError, "readback failed"):
            self.call()

    def test_setup_exception_restores_engine(self):
        self.nodes.new.side_effect = RuntimeError("setup failed")
        with self.assertRaisesRegex(RuntimeError, "setup failed"):
            self.call()
        self.assertEqual(self.bpy.context.scene.render.engine, "BLENDER_EEVEE")

    def test_roughness_is_data_and_success_requires_readback(self):
        result = self.call()
        self.assertTrue(result["verified"])
        self.assertEqual(self.image.colorspace_settings.name, "Non-Color")

    def test_material_agent_rejects_unverified_bake_success(self):
        task = AgentTask(task_id="bake-test", required_capability="materials.manage", task_type="bake_object_texture",
                         input_params=dict(object_name="Owned", bake_type="ROUGHNESS", width=64, height=64))
        for result in ({}, {"success": False}, {"success": True, "baked": True}):
            with self.subTest(result=result):
                executor = NS(execute_tool=Mock(return_value=BridgeResponse.success(result)))
                outcome = MaterialsAgent().execute_task(task, executor, trusted_approval=True)
                self.assertEqual(outcome.status, TaskStatus.FAILED)
                self.assertEqual(outcome.verification.status, "FAIL")
