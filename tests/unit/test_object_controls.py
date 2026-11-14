"""Object controls validation, approval boundary and truthful agent readback."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from jsonschema import validate as json_validate
from blender_addon.universal_mcp.bridge.object_controls import validate,SCHEMA,handle_configure_modeling_object
from shared.schemas.tool_schemas import validate_tool_input
from shared.models.agent_contracts import AgentTask,TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.modeling import ModelingAgent

class ObjectControlTests(unittest.TestCase):
    def setUp(self):
        self.args={'name':'Owned','action':'transform','space':'WORLD','translation':[1,0,0],'pivot':[0,0,0],'expected_snapshot_id':'sha256:'+'a'*64}
    def test_strict_finite_contract_and_canonical_space(self):
        validate(self.args);json_validate(self.args,SCHEMA)
        self.assertEqual(validate_tool_input('configure_modeling_object',self.args,trusted_approval=True)['space'],'WORLD')
        for change in ({'scale':[1,0,1]},{'translation':[True,0,0]},{'rotation':[float('nan'),0,0]},{'action':'parent','parent_name':'Cube'},{'action':'apply'}, {'parent_name':'Cube'}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate({**self.args,**change})
        with self.assertRaises(ValueError):validate({'name':'Owned','action':'select','expected_snapshot_id':self.args['expected_snapshot_id']})
    def test_selection_clamp_rolls_back_other_selection_and_active(self):
        from blender_addon.universal_mcp.bridge.object_controls import select_after_approval
        class Block:
            def __init__(self,name,selected,locked=False):self.name=name;self.selected=selected;self.locked=locked
            def select_get(self):return self.selected
            def select_set(self,value):
                if not self.locked:self.selected=value
        class Collection(list):
            def __contains__(self,value):return any(o.name==value if isinstance(value,str) else o==value for o in self)
        target=Block('Target',False,True);other=Block('Other',True)
        objects=Collection([target,other]);objects.active=other
        bpy=NS(context=NS(mode='OBJECT',scene=NS(objects={'Target':target,'Other':other}),view_layer=NS(objects=objects)))
        with self.assertRaisesRegex(RuntimeError,'ROLLED_BACK_VERIFIED'):
            select_after_approval(bpy,{'name':'Target','state':True,'deselect_all':True,'make_active':True})
        self.assertFalse(target.select_get());self.assertTrue(other.select_get());self.assertIs(objects.active,other)
        with self.assertRaises(ValueError):select_after_approval(bpy,{'name':'Target','state':'yes'})

    def test_public_flags_never_authorize(self):
        obj=NS(type='MESH',mode='OBJECT')
        bpy=NS(context=NS(mode='OBJECT',scene=NS(objects={'Owned':obj},umcp_require_scene_mutation_approval=True),view_layer=NS(objects={'Owned':obj})))
        with self.assertRaises(PermissionError):handle_configure_modeling_object(bpy,{**self.args,'approved':True,'trusted_approval':True})
    def test_agent_mismatched_actual_transform_fails_without_retry(self):
        task=AgentTask(task_id='control',required_capability='modeling.object_controls',task_type='configure_modeling_object',input_params=self.args)
        receipt={'name':'Owned','action':'transform','success':True,'verified':True,'snapshot_id':'sha256:'+'b'*64,'matrix_world':[[1]]}
        executor=NS(execute_tool=Mock(side_effect=[BridgeResponse.success(receipt),BridgeResponse.success({**receipt,'matrix_world':[[2]]})]))
        self.assertEqual(ModelingAgent().execute_task(task,executor).status,TaskStatus.FAILED)
        self.assertEqual(executor.execute_tool.call_count,2)
