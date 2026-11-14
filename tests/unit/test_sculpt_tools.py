import unittest

from blender_addon.universal_mcp.bridge.sculpt_contract import validate
from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS, TOOL_SCULPT_MESH, TOOL_INSPECT_SCULPT_STATE,
    validate_tool_input,
)
from mcp_service.agents.modeling import ModelingAgent, SUPPORTED_MODELING_TOOLS, MODELING_AGENT_ID

SNAPSHOT="sha256:"+"a"*64

class SculptContractTests(unittest.TestCase):
    def valid(self, action, **kwargs):
        return {"object_name":"DisposableMesh","expected_snapshot_id":SNAPSHOT,"action":action,**kwargs}

    def test_registered_typed_tools_and_mutation_tier(self):
        self.assertIn(TOOL_SCULPT_MESH, TOOL_DEFINITIONS)
        self.assertIn(TOOL_INSPECT_SCULPT_STATE, TOOL_DEFINITIONS)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_SCULPT_MESH]["permission_tier"],"SCENE_MUTATION")
        self.assertEqual(TOOL_DEFINITIONS[TOOL_INSPECT_SCULPT_STATE]["permission_tier"],"READ_ONLY")
        self.assertTrue({TOOL_SCULPT_MESH,TOOL_INSPECT_SCULPT_STATE}<=SUPPORTED_MODELING_TOOLS)
        self.assertTrue(ModelingAgent().can_handle(type("T",(),{"required_capability":"modeling.sculpting","task_type":TOOL_SCULPT_MESH})()))

    def test_mode_lifecycle_contract(self):
        for action in ("enter_sculpt","exit_sculpt"):
            self.assertEqual(validate(self.valid(action))["action"],action)

    def test_brush_selection_and_settings_bounds(self):
        self.assertEqual(validate(self.valid("set_brush",brush_name="Draw"))["brush_name"],"Draw")
        self.assertEqual(validate(self.valid("set_brush_settings",settings={"size":40,"strength":0.5,"use_frontface":True}))["settings"]["size"],40)
        for settings in ({"size":0},{"strength":1.1},{"unrelated":True},{"size":True},{"size":1.5}):
            with self.assertRaises(ValueError):validate(self.valid("set_brush_settings",settings=settings))

    def test_bounded_stroke_and_finite_coordinates(self):
        points=[{"x":.1,"y":.2,"pressure":.5},{"x":.9,"y":.8}]
        self.assertEqual(len(validate(self.valid("stroke",points=points))["points"]),2)
        for bad in ([{"x":.1,"y":.2}], [{"x":0,"y":0},{"x":1.1,"y":0}], [{"x":0,"y":0},{"x":1,"y":1,"pressure":float("nan")}], [{"x":0,"y":0,"button":"left"},{"x":1,"y":1}]):
            with self.assertRaises(ValueError):validate(self.valid("stroke",points=bad))

    def test_remesh_dyntopo_and_stale_snapshot_validation(self):
        self.assertEqual(validate(self.valid("voxel_remesh",voxel_size=.05))["voxel_size"],.05)
        self.assertTrue(validate(self.valid("set_dyntopo",enabled=True,detail_mode="CONSTANT",detail_size=2))["enabled"])
        for params in (self.valid("voxel_remesh",voxel_size=0),self.valid("set_dyntopo",enabled=1),
                       {**self.valid("exit_sculpt"),"expected_snapshot_id":"old"},
                       {**self.valid("enter_sculpt"),"approved":True}):
            with self.assertRaises(ValueError):validate(params)

    def test_service_schema_validation_and_modeling_rejection(self):
        valid=validate_tool_input(TOOL_SCULPT_MESH,self.valid("stroke",points=[{"x":0,"y":0},{"x":1,"y":1}]),trusted_approval=True)
        self.assertEqual(valid["action"],"stroke")
        self.assertTrue(validate_tool_input(TOOL_INSPECT_SCULPT_STATE,{"object_name":"DisposableMesh"}))
        agent=ModelingAgent()
        self.assertTrue(agent.validate_task_input(TOOL_SCULPT_MESH,self.valid("enter_sculpt"))[0])
        self.assertFalse(agent.validate_task_input(TOOL_SCULPT_MESH,{**self.valid("stroke"),"points":[]})[0])
        with self.assertRaises(ValueError):validate_tool_input(TOOL_SCULPT_MESH,{**self.valid("enter_sculpt"),"approved":True})

    def test_sculpt_capability_verified_and_routeable(self):
        agent = ModelingAgent()
        manifest = agent.manifest
        cap = manifest.get_capability("modeling.sculpting")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.verification_status, "VERIFIED")
        from shared.models.agent_contracts import AgentTask
        from mcp_service.agents.registry import AgentRegistry
        from mcp_service.agents.router import CapabilityRouter
        registry = AgentRegistry()
        registry.register_agent(manifest)
        router = CapabilityRouter(registry=registry)
        task = AgentTask(task_id="t1", required_capability="modeling.sculpting", task_type=TOOL_SCULPT_MESH)
        res = router.route(task, require_verified=True)
        self.assertTrue(res.success)
        self.assertEqual(res.agent.agent_id, MODELING_AGENT_ID)

    def test_activate_brush_helper(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from blender_addon.universal_mcp.bridge.sculpt_tools import _activate_brush

        fake_sculpt = SimpleNamespace(brush=None)
        mock_bpy = MagicMock()

        # Target matches existing brush
        existing_brush = SimpleNamespace(name="Clay")
        fake_sculpt.brush = existing_brush
        self.assertTrue(_activate_brush(mock_bpy, fake_sculpt, "Clay"))

        # Empty target returns False
        self.assertFalse(_activate_brush(mock_bpy, fake_sculpt, ""))

        # Essentials asset activation
        fake_sculpt.brush = None
        def activate_essentials(asset_library_type=None, relative_asset_identifier=None):
            fake_sculpt.brush = SimpleNamespace(name="Draw")
            return {"FINISHED"}
        mock_bpy.ops.brush.asset_activate = activate_essentials
        self.assertTrue(_activate_brush(mock_bpy, fake_sculpt, "Draw"))

if __name__=="__main__":unittest.main()

