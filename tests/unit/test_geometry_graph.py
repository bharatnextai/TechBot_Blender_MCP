"""Finite graph validation, strict sockets and independent evaluated readback."""
import unittest
from unittest.mock import Mock
from types import SimpleNamespace as NS
from jsonschema import validate as json_validate
from blender_addon.universal_mcp.bridge.geometry_contract import validate,SCHEMA
from blender_addon.universal_mcp.bridge.geometry_tools import _socket,handle_configure_modeling_geometry
from shared.models.agent_contracts import AgentTask,TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.modeling import ModelingAgent

class GeometryGraphTests(unittest.TestCase):
    def setUp(self):
        self.args={'name':'Owned','modifier_name':'Graph','group_name':'OwnedGraph','action':'create','nodes':[{'name':'Move','type':'GeometryNodeTransform','inputs':{'Translation':[1,0,0]}}],'links':[{'from_node':'Input','from_socket':'Geometry','to_node':'Move','to_socket':'Geometry'},{'from_node':'Move','from_socket':'Geometry','to_node':'Output','to_socket':'Geometry'}]}
    def test_typed_graph_and_invalid_nodes_cycles_links(self):
        validate(self.args);json_validate(self.args,SCHEMA)
        for change in ({'nodes':[{'name':'Move','type':'GeometryNodeObjectInfo'}]}, {'nodes':[{'name':'Move','type':'GeometryNodeTransform','inputs':{'code':'x'}}]}, {'nodes':[{'name':'Move','type':'GeometryNodeTransform','inputs':{'Scale':[1,True,1]}}]}, {'links':self.args['links']+[self.args['links'][0]]}, {'links':[{'from_node':'Move','from_socket':'Geometry','to_node':'Move','to_socket':'Geometry'}]}, {'parameters':[{'name':'Geometry','type':'FLOAT','value':1}]}, {'parameters':[{'name':'Value','type':'INT','value':True}]}, {'action':'update'}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate({**self.args,**change})
    def test_socket_identifier_never_falls_back(self):
        socket=NS(name='Mesh',identifier='Geometry',is_unavailable=False,enabled=True)
        node=NS(name='Smooth',bl_idname='GeometryNodeSetShadeSmooth',inputs=[socket])
        self.assertIs(_socket(node,'Geometry'),socket)
        with self.assertRaises(ValueError):_socket(node,'Mesh')
        socket.is_unavailable=True
        with self.assertRaises(ValueError):_socket(node,'Geometry')
    def test_blender52_typed_parameters_capture_and_restore_without_idprops(self):
        from blender_addon.universal_mcp.bridge.geometry_tools import _capture_parameters,_restore_parameters,_parameter_value
        holders={};items=[]
        for identifier,kind,value in [('Vec','NodeSocketVector',[1.,2.,3.]),('Count','NodeSocketInt',3),('Amount','NodeSocketFloat',.5),('Flag','NodeSocketBool',True)]:
            holder=NS(name=identifier,value=value,type='VALUE',attribute_name='')
            holder.bl_rna=NS(properties=[NS(identifier=key,is_readonly=False) for key in ('name','value','type','attribute_name')])
            holders[identifier]=holder;items.append(NS(item_type='SOCKET',in_out='INPUT',socket_type=kind,identifier=identifier))
        holders['Vec'].type='ATTRIBUTE';holders['Vec'].attribute_name='original_attribute'
        mod=NS(properties=NS(inputs=NS(**holders)),node_group=NS(interface=NS(items_tree=items)))
        saved=_capture_parameters(mod)
        holders['Vec'].value=[0.,0.,0.];holders['Vec'].type='VALUE';holders['Vec'].attribute_name=''
        holders['Flag'].value=False
        _restore_parameters(mod,saved)
        self.assertEqual(_parameter_value(mod,'Vec'),[1.,2.,3.])
        self.assertEqual(holders['Vec'].type,'ATTRIBUTE')
        self.assertEqual(holders['Vec'].attribute_name,'original_attribute')
        self.assertIs(_parameter_value(mod,'Flag'),True)

    def test_flags_cannot_authorize(self):
        bpy=NS(context=NS(scene=NS(objects={'Owned':NS(name='Owned',type='MESH')},umcp_require_scene_mutation_approval=True)))
        with self.assertRaises(PermissionError):handle_configure_modeling_geometry(bpy,{**self.args,'approved':True,'trusted_approval':True})
    def test_agent_different_evaluated_output_fails(self):
        task=AgentTask(task_id='graph',required_capability='modeling.geometry_graph',task_type='configure_modeling_geometry',input_params=self.args)
        receipt={'name':'Owned','action':'create','success':True,'verified':True,'snapshot_id':'sha256:'+'b'*64,'evaluated':{'vertex_count':8}}
        executor=NS(execute_tool=Mock(side_effect=[BridgeResponse.success(receipt),BridgeResponse.success({**receipt,'evaluated':{'vertex_count':0}})]))
        self.assertEqual(ModelingAgent().execute_task(task,executor).status,TaskStatus.FAILED)
        self.assertEqual(executor.execute_tool.call_count,2)
