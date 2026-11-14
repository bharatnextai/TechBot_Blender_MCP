"""Finite curve/text contract and fail-closed independent verification."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from jsonschema import validate as json_validate
from blender_addon.universal_mcp.bridge.curve_contract import validate,SCHEMA
from blender_addon.universal_mcp.bridge.curve_tools import handle_configure_curve_geometry
from blender_addon.universal_mcp.bridge import curve_tools, mesh_topology
from shared.schemas.tool_schemas import validate_tool_input
from mcp_service.agents.modeling import ModelingAgent
from shared.models.agent_contracts import AgentTask,TaskStatus
from shared.models.protocol_models import BridgeResponse

class CurveGeometryTests(unittest.TestCase):
    def setUp(self):
        self.args={'name':'OwnedCurve','action':'create','kind':'CURVE','settings':{'dimensions':'3D','extrude':.01},'splines':[{'type':'BEZIER','points':[{'co':[0,0,0]},{'co':[1,0,0]}]}]}
    def test_schema_backend_service_contracts(self):
        json_validate(self.args,SCHEMA);validate(self.args)
        sanitized=validate_tool_input('configure_curve_geometry',self.args,trusted_approval=True)
        self.assertEqual(sanitized['kind'],'CURVE')
        for change in ({'settings':{'extrude':-1}}, {'settings':{'body':'wrong kind'}}, {'splines':[]}, {'splines':[{'type':'NURBS','order':4,'points':[{'co':[0,0,0]},{'co':[1,0,0]}]}]}, {'splines':[{'type':'POLY','points':[{'co':[0,0,0],'handle_left':[0,0,0]},{'co':[1,0,0]}]}]}, {'splines':[{'type':'BEZIER','points':[{'co':[0,0,0],'handle_type_left':'FREE'},{'co':[1,0,0]}]}]}, {'action':'update'}, {'kind':'MESH'}, {'settings':{'bevel_depth':True}}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate({**self.args,**change})
    def test_evaluated_mesh_state_uses_indexed_evaluated_fingerprint_contract(self):
        mesh=NS(vertices=[NS(index=0,co=[1.0,2.0,3.0],select=False)],
            edges=[],polygons=[],loops=[],has_custom_normals=False,is_editmode=False)
        obj=NS(name='Mesh',type='MESH',data=mesh,mode='OBJECT')
        obj.matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
        evaluated=NS(to_mesh=Mock(return_value=mesh),to_mesh_clear=Mock())
        context=NS(mode='OBJECT',scene=NS(objects={'Mesh':obj}),
            view_layer=NS(update=Mock()),evaluated_depsgraph_get=Mock(return_value='graph'))
        obj.evaluated_get=Mock(return_value=evaluated)
        indexed=mesh_topology.inspect_elements(obj,context,{
            'element_domain':'vertices','limit':1,'mesh_source':'evaluated'})
        curve_state=curve_tools.inspect(NS(context=context),'Mesh')
        curve_state=curve_state['evaluated']
        self.assertEqual(curve_state['topology_source'],'EVALUATED_MESH')
        self.assertEqual(curve_state['snapshot_id'],indexed['snapshot_id'])
        self.assertEqual(curve_state['state_id'],indexed['state_id'])
        self.assertEqual(evaluated.to_mesh_clear.call_count,2)
        base_state=curve_tools._mesh_state(mesh,'Mesh')
        self.assertEqual(base_state['topology_source'],'BASE_MESH')
        self.assertNotEqual(base_state['snapshot_id'],curve_state['snapshot_id'])
        self.assertNotEqual(base_state['state_id'],curve_state['state_id'])
    def test_text_and_explicit_converted_copy(self):
        text={'name':'Text','action':'create','kind':'TEXT','settings':{'body':'Test','size':1,'extrude':.02}}
        validate(text);json_validate(text,SCHEMA)
        copy={'name':'Text','action':'copy_to_mesh','output_name':'TextMesh','expected_snapshot_id':'sha256:'+'a'*64}
        validate(copy);json_validate(copy,SCHEMA)
        with self.assertRaises(ValueError):validate({**copy,'settings':{}})
        with self.assertRaises(ValueError):validate({**text,'splines':self.args['splines']})
    def test_post_evaluation_coordinate_and_count_mismatch_is_rejected(self):
        from blender_addon.universal_mcp.bridge.curve_tools import _assert_requested
        observed={'settings':self.args['settings'],'splines':[{'type':'BEZIER','cyclic':False,'points':[{'co':[0,0,0]},{'co':[1,0,0]}]}]}
        requested={**self.args,'splines':[{'type':'BEZIER','points':[{'co':[0,0,.2]},{'co':[1,0,0]}]}]}
        with patch('blender_addon.universal_mcp.bridge.curve_tools._curve_data',return_value=observed):
            with self.assertRaisesRegex(RuntimeError,'point readback mismatch'):_assert_requested(NS(),requested)
        with patch('blender_addon.universal_mcp.bridge.curve_tools._curve_data',return_value={**observed,'splines':[]}):
            with self.assertRaisesRegex(RuntimeError,'Spline count'):_assert_requested(NS(),self.args)

    def test_legacy_circle_mapping_and_strict_transforms(self):
        from blender_addon.universal_mcp.bridge.curve_contract import legacy_request
        circle,kind,transforms=legacy_request({'name':'Circle','curve_type':'CIRCLE'})
        self.assertEqual(kind,'CIRCLE');self.assertEqual(len(circle['splines'][0]['points']),4)
        self.assertTrue(circle['splines'][0]['cyclic'])
        nurbs,kind,_=legacy_request({'name':'NurbsCircle','curve_type':'NURBS_CIRCLE'})
        self.assertEqual(len(nurbs['splines'][0]['points']),8)
        self.assertEqual(nurbs['splines'][0]['order'],3)
        for change in ({'resolution':True},{'scale':[1,0,1]},{'extrude':float('nan')}):
            with self.subTest(change=change),self.assertRaises(ValueError):legacy_request({'name':'Curve',**change})

    def test_flags_do_not_authorize(self):
        bpy=NS(context=NS(mode='OBJECT',scene=NS(umcp_require_scene_mutation_approval=True)))
        with self.assertRaises(PermissionError):handle_configure_curve_geometry(bpy,{**self.args,'approved':True,'trusted_approval':True})
    def test_agent_independent_geometry_mismatch_fails(self):
        task=AgentTask(task_id='curve',required_capability='modeling.curve_geometry',task_type='configure_curve_geometry',input_params=self.args)
        receipt={'name':'OwnedCurve','action':'create','success':True,'verified':True,'snapshot_id':'sha256:'+'a'*64,'evaluated':{'vertex_count':2}}
        executor=NS(execute_tool=Mock(side_effect=[BridgeResponse.success(receipt),BridgeResponse.success({**receipt,'evaluated':{'vertex_count':3}})]))
        self.assertEqual(ModelingAgent().execute_task(task,executor).status,TaskStatus.FAILED)
        self.assertEqual(executor.execute_tool.call_count,2)
