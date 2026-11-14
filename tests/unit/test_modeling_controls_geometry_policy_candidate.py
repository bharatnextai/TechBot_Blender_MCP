"""Detached object-control/Geometry Nodes scope boundaries; no activation."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from tests.policy_candidates.modeling_controls_geometry_policy import authorizes

class ControlsGeometryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.mesh=NS(users=1,vertices=[0]*8,edges=[0]*12,polygons=[0]*6,library=None,animation_data=None,shape_keys=None)
        self.obj=NS(name='Owned',type='MESH',mode='OBJECT',data=self.mesh,library=None,override_library=None,animation_data=None,constraints=[])
        self.bpy=NS(context=NS(mode='OBJECT',scene=NS(objects={'Owned':self.obj}),view_layer=NS(objects={'Owned':self.obj}),selected_objects=[]))
        self.owned={'Owned':(self.obj,self.mesh)};self.groups={}
        self.args=dict(name='Owned',action='transform',space='WORLD',translation=[1,0,0],expected_snapshot_id='sha256:'+'a'*64)
        self.guard=self.enterContext(patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=True))
    def allowed(self,args=None):
        args=self.args if args is None else args
        return authorizes(self.bpy,'configure_modeling_object',args,self.owned,self.groups,args)
    def test_guard_identity_and_exact_plan(self):
        self.assertTrue(self.allowed())
        self.guard.return_value=False;self.assertFalse(self.allowed());self.guard.return_value=True
        self.mesh.users=2;self.assertFalse(self.allowed());self.mesh.users=1
        self.assertFalse(authorizes(self.bpy,'configure_modeling_object',self.args,self.owned,self.groups,{**self.args,'translation':[0,0,0]}))
    def test_flags_bounds_parent_and_selection_scope(self):
        for change in ({'approved':True},{'request_id':'not-proof'},{'translation':[3,0,0]},{'scale':[3,1,1]}):
            with self.subTest(change=change):self.assertFalse(self.allowed({**self.args,**change}))
        args=dict(name='Owned',action='parent',parent_name='Cube',expected_snapshot_id=self.args['expected_snapshot_id'])
        self.assertFalse(self.allowed(args))
        self.bpy.context.selected_objects=[NS(name='Cube')]
        args=dict(name='Owned',action='select',state=True,deselect_all=True,expected_snapshot_id=self.args['expected_snapshot_id'])
        self.assertFalse(self.allowed(args))
