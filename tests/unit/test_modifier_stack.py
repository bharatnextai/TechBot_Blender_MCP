"""Finite extended modifier schemas, fail-closed dispatch and agent readback."""
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace as NS
from jsonschema import validate as json_validate,ValidationError
from blender_addon.universal_mcp.bridge.advanced_modifier_contract import validate,SCHEMA
from blender_addon.universal_mcp.bridge import modifier_stack
from shared.schemas.tool_schemas import TOOL_DEFINITIONS,validate_tool_input
from shared.models.agent_contracts import AgentTask,TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.modeling import ModelingAgent


class ModifierStackTests(unittest.TestCase):
    def setUp(self):
        self.args=dict(name='Owned',modifier_name='Mirror',modifier_type='MIRROR',action='add',properties={'use_axis':[True,False,False]},expected_snapshot_id='sha256:'+'a'*64)

    def test_finite_schema_and_service_validation_agree(self):
        json_validate(self.args,SCHEMA);validate(self.args);validate_tool_input('edit_modifier_stack',self.args,trusted_approval=True)
        for change in ({'properties':{'use_axis':[1,0,0]}},{'properties':{'width':.1}}, {'action':'apply','index':0}, {'modifier_type':'NODES'}, {'properties':{'merge_threshold':float('nan')}}, {'properties':{}}, {'expected_snapshot_id':'old'}, {'modifier_name':' Bad '}):
            args={**self.args,**change}
            with self.subTest(change=change), self.assertRaises(ValueError):validate(args)
        for kind,properties in [('BOOLEAN',{'operand_name':'Cutter','operation':'DIFFERENCE','solver':'EXACT'}),('ARRAY',{'count':2,'relative_offset_displace':[1,0,0]}),('SUBSURF',{'levels':1}),('BEVEL',{'width':.02}),('SOLIDIFY',{'thickness':.02})]:
            args={**self.args,'modifier_type':kind,'properties':properties}
            json_validate(args,SCHEMA);validate(args)

    def test_discovery_classification_and_production_policy_unchanged(self):
        from blender_addon.universal_mcp.bridge.handlers import ALL_HANDLERS,READ_ONLY_HANDLERS
        self.assertIn('edit_modifier_stack',ALL_HANDLERS)
        self.assertNotIn('edit_modifier_stack',READ_ONLY_HANDLERS)
        self.assertIn('inspect_modifier_stack',READ_ONLY_HANDLERS)
        self.assertEqual(TOOL_DEFINITIONS['edit_modifier_stack']['permission_tier'],'SCENE_MUTATION')
        from mcp_service.agents.modeling import create_modeling_manifest
        cap=next(c for c in create_modeling_manifest().capabilities if 'edit_modifier_stack' in c.supported_task_types)
        self.assertEqual(cap.verification_status,'VERIFIED')
        self.assertEqual(cap.constraints['whole_domain_status'],'PARTIALLY IMPLEMENTED')

    def test_flags_never_authorize(self):
        bpy=NS(context=NS(scene=NS(objects={'Owned':NS(name='Owned',type='MESH')},umcp_require_scene_mutation_approval=True)))
        with self.assertRaises(PermissionError):modifier_stack.handle_edit_modifier_stack(bpy,{**self.args,'approved':True,'trusted_approval':True})

    def test_agent_separate_state_mismatch_fails_without_retry(self):
        task=AgentTask(task_id='modstack',required_capability='modeling.modifier_stack',task_type='edit_modifier_stack',input_params=self.args)
        receipt={'success':True,'verified':True,'name':'Owned','snapshot_id':'sha256:'+'b'*64,'modifiers':[],'base':{},'evaluated':{},'matrix_world':[]}
        for readback in ({**receipt,'snapshot_id':'sha256:'+'c'*64},{**receipt,'evaluated':{'vertex_count':999}},{**receipt,'success':False}):
            executor=NS(execute_tool=Mock(side_effect=[BridgeResponse.success(receipt),BridgeResponse.success(readback)]))
            with self.subTest(readback=readback):
                self.assertEqual(ModelingAgent().execute_task(task,executor).status,TaskStatus.FAILED)
                self.assertEqual(executor.execute_tool.call_count,2)
