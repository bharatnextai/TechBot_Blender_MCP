"""Typed component batch contract, security, routing, and truthful readback."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from jsonschema import validate as json_validate,ValidationError
from blender_addon.universal_mcp.bridge.component_edit import validate,SCHEMA,ACTION_FIELDS,handle_edit_mesh
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from shared.schemas.tool_schemas import validate_tool_input,TOOL_DEFINITIONS
from shared.models.agent_contracts import AgentTask,TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.modeling import ModelingAgent

class ComponentContractTests(unittest.TestCase):
    def setUp(self):
        self.params={"name":"Owned","expected_snapshot_id":"sha256:"+"a"*64,"operations":[{"action":"move_vertices","vertices":[0],"delta":[0,0,1]}]}

    def test_strict_schema_and_backend_agree(self):
        json_validate(self.params,SCHEMA)
        self.assertEqual(validate_tool_input("edit_mesh",self.params,trusted_approval=True)["operations"],self.params["operations"])
        for change in ({"code":"unsafe"},{"expected_snapshot_id":"bad"},{"operations":[]},
            {"operations":[{"action":"move_vertices","vertices":[True],"delta":[0,0,1]}]},
            {"operations":[{"action":"move_vertices","vertices":[0,0],"delta":[0,0,1]}]},
            {"operations":[{"action":"move_vertices","vertices":[0],"delta":[0,0,1],"width":1}]},
            {"operations":[{"action":"unknown"}]},{"operations":[{"action":"bevel","edges":[0],"width":1,"segments":0}]},
            {"operations":[{"action":"create","points":[[0,0]]}]}):
            params={**self.params,**change}
            with self.subTest(change=change):
                with self.assertRaises(ValueError):validate(params)
                with self.assertRaises(ValidationError):json_validate(params,SCHEMA)
        with self.assertRaises(ValueError):validate({**self.params,"operations":[{"action":"move_vertices","vertices":[0],"delta":[float("nan"),0,0]}]})

    def test_declared_actions_have_exact_fields(self):
        for action,(props,required) in ACTION_FIELDS.items():
            self.assertIn(action,SCHEMA["properties"]["operations"]["items"]["properties"]["action"]["enum"])
            self.assertNotIn("code",props)
        self.assertEqual(TOOL_DEFINITIONS["edit_mesh"]["permission_tier"],"SCENE_MUTATION")
        agent=ModelingAgent()
        self.assertTrue(agent.can_handle(AgentTask(task_id="x",required_capability="modeling.mesh_edit",task_type="edit_mesh")))
        self.assertTrue(any("edit_mesh" in cap.supported_task_types for cap in agent.manifest.capabilities))

    def test_tokens_flags_tamper_and_replay(self):
        registry=ApprovalRegistry();bpy=NS(context=NS(scene=NS(umcp_require_scene_mutation_approval=True,objects={"Owned":NS(type="MESH",data=object())})))
        with patch("blender_addon.universal_mcp.bridge.component_edit.get_approval_registry",return_value=registry),patch("blender_addon.universal_mcp.bridge.component_edit.run",return_value={"verified":True}) as execute:
            for flags in ({"approved":True},{"trusted_approval":True}):
                with self.assertRaises(PermissionError):handle_edit_mesh(bpy,{**self.params,**flags})
            req=registry.create_request("edit_mesh",self.params);ok,token=registry.resolve_request(req.request_id,"approved");self.assertTrue(ok)
            args={**self.params,"request_id":req.request_id,"approval_token":token}
            with self.assertRaises(PermissionError):handle_edit_mesh(bpy,{**args,"expected_snapshot_id":"sha256:"+"b"*64})
            self.assertEqual(execute.call_count,0)
            handle_edit_mesh(bpy,args);self.assertEqual(execute.call_count,1)
            with self.assertRaises(PermissionError):handle_edit_mesh(bpy,args)
            self.assertEqual(execute.call_count,1)

    def test_agent_requires_separate_geometry_and_state_match(self):
        task=AgentTask(task_id="mesh",required_capability="modeling.mesh_edit",task_type="edit_mesh",input_params=self.params)
        result={"success":True,"verified":True,"snapshot_id":"sha256:"+"b"*64,"state_id":"sha256:"+"c"*64,
            "new_vertex_count":4,"new_edge_count":4,"new_face_count":1}
        actual={"snapshot_id":result["snapshot_id"],"state_id":result["state_id"],"vertex_count":4,"edge_count":4,"polygon_count":1}
        good=NS(execute_tool=Mock(side_effect=[BridgeResponse.success(result),BridgeResponse.success(actual)]))
        self.assertEqual(ModelingAgent().execute_task(task,good,trusted_approval=True).status,TaskStatus.SUCCEEDED)
        for observed in ({**actual,"state_id":"wrong"},{**actual,"polygon_count":2},{}):
            executor=NS(execute_tool=Mock(side_effect=[BridgeResponse.success(result),BridgeResponse.success(observed)]))
            self.assertEqual(ModelingAgent().execute_task(task,executor,trusted_approval=True).status,TaskStatus.FAILED)
            self.assertEqual(executor.execute_tool.call_count,2)
