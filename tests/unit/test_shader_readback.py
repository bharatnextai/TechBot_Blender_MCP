"""Regression coverage for shader no-ops and material task verification."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from blender_addon.universal_mcp.bridge.handlers import handle_manage_shader_nodes
from mcp_service.agents.materials import MaterialsAgent
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse


class ShaderReadbackTests(unittest.TestCase):
    def setUp(self):
        self.roughness=NS(name='Roughness',identifier='Roughness',default_value=.5)
        self.output=NS(name='BSDF',identifier='BSDF')
        self.node=NS(inputs=[self.roughness],outputs=[self.output],label='')
        self.links=[]
        self.tree=NS(nodes={'Principled BSDF':self.node},links=NS(new=Mock()))
        self.bpy=NS(data=NS(materials={'Mat':NS(use_nodes=True,node_tree=self.tree)}))
        self.guard=patch('blender_addon.universal_mcp.bridge.handlers.get_approval_registry',return_value=None)
        self.guard.start();self.addCleanup(self.guard.stop)

    def call(self,**params):
        return handle_manage_shader_nodes(self.bpy,{'target_name':'Mat','node_name':'Principled BSDF',**params})

    def test_invalid_property_rejected_without_assignment(self):
        with self.assertRaisesRegex(ValueError,'not found'):self.call(action='set_property',property_name='NotAProperty',property_value=.68)
        self.assertEqual(self.roughness.default_value,.5)

    def test_roughness_has_verified_float_readback(self):
        r=self.call(action='set_property',property_name='Roughness',property_value=.68)
        self.assertTrue(r['verified']);self.assertAlmostEqual(r['property_value'],.68)

    def test_existing_node_attribute_readback(self):
        self.assertEqual(self.call(action='set_property',property_name='label',property_value='Skin')['property_value'],'Skin')

    def test_clamped_assignment_fails_and_restores(self):
        class Clamped:
            name=identifier='Roughness'
            def __init__(self):self.value=.5
            @property
            def default_value(self):return self.value
            @default_value.setter
            def default_value(self,value):self.value=min(1,value)
        self.node.inputs=[Clamped()]
        with self.assertRaisesRegex(RuntimeError,'readback mismatch'):self.call(action='set_property',property_name='Roughness',property_value=2)
        self.assertEqual(self.node.inputs[0].default_value,.5)

    def test_missing_requested_output_or_input_does_not_link(self):
        for output,input_name in (('Wrong','Roughness'),('BSDF','Wrong'),('','Roughness')):
            with self.subTest(output=output,input=input_name):
                with self.assertRaisesRegex(ValueError,'socket'):self.call(action='connect',from_node='Principled BSDF',to_node='Principled BSDF',from_socket=output,to_socket=input_name)
        self.tree.links.new.assert_not_called()

    def run_agent(self,response,**params):
        executor=NS(execute_tool=Mock(return_value=response))
        task=AgentTask(task_id='shader-test',required_capability='materials.manage',task_type='manage_shader_nodes',input_params={'target_name':'Mat','node_name':'Principled BSDF','action':'set_property','property_name':'Roughness','property_value':.68,**params})
        # Internal dispatcher-approved fixture, not an MCP-supplied approval flag.
        return MaterialsAgent().execute_task(task,executor,trusted_approval=True)

    def test_bridge_failure_propagates_to_task_fail(self):
        r=self.run_agent(BridgeResponse.error('Unknown shader property'))
        self.assertEqual(r.status,TaskStatus.FAILED);self.assertEqual(r.verification.status,'FAIL')
        self.assertEqual(r.verification.observed_results['transaction_status'],'ROLLBACK_UNVERIFIED')

    def test_unverified_or_mismatching_success_never_passes(self):
        base={'success':True,'verified':True,'property_set':True,'node_name':'Principled BSDF','property_name':'Roughness','property_value':.68}
        for change in ({'verified':False},{'property_value':.1},{'property_set':False},{'node_name':'Other'}):
            r=self.run_agent(BridgeResponse.success({**base,**change}))
            self.assertEqual(r.status,TaskStatus.FAILED);self.assertEqual(r.verification.status,'FAIL')

    def test_verified_matching_result_passes(self):
        r=self.run_agent(BridgeResponse.success({'success':True,'verified':True,'property_set':True,'node_name':'Principled BSDF','property_name':'Roughness','property_value':.680000007}))
        self.assertEqual(r.status,TaskStatus.SUCCEEDED);self.assertEqual(r.verification.status,'PASS')

    def test_wrong_socket_success_cannot_pass_agent(self):
        r=self.run_agent(BridgeResponse.success({'success':True,'verified':True,'connected':True,'from_node':'A','to_node':'B','from_socket':'Other','to_socket':'Surface'}),action='connect',from_node='A',to_node='B',from_socket='BSDF',to_socket='Surface')
        self.assertEqual(r.status,TaskStatus.FAILED)

    def test_inner_shader_failure_cannot_pass_agent(self):
        r=self.run_agent(BridgeResponse.success({'success':False}),action='create_node')
        self.assertEqual(r.status,TaskStatus.FAILED);self.assertEqual(r.verification.status,'FAIL')

    def test_case_normalized_action_cannot_skip_readback_verification(self):
        r=self.run_agent(BridgeResponse.success({}),action='SET_PROPERTY')
        self.assertEqual(r.status,TaskStatus.FAILED);self.assertEqual(r.verification.status,'FAIL')

    def test_connection_is_verified_from_actual_link_collection(self):
        owner=self
        class Links(list):
            def new(self,output,input_socket):
                self.append(NS(from_socket=output,to_socket=input_socket))
        self.tree.links=Links()
        result=self.call(action='connect',from_node='Principled BSDF',to_node='Principled BSDF',from_socket='BSDF',to_socket='Roughness')
        self.assertTrue(result['verified']);self.assertEqual(len(owner.tree.links),1)
