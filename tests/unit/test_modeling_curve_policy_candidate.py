"""Detached curve/text scope boundaries; no activation or registry decisions."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from tests.policy_candidates.modeling_curve_policy import authorizes

class CurvePolicyTests(unittest.TestCase):
    def setUp(self):
        self.bpy=NS(context=NS(mode='OBJECT',scene=NS(objects={})),data=NS(objects={},curves={}))
        self.owned={'Owned':(None,None),'Mesh':(None,None)}
        self.args=dict(name='Owned',action='create',kind='TEXT',settings={'body':'Fixture','size':1})
        self.guard=self.enterContext(patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=True))
    def allowed(self,args=None):
        args=self.args if args is None else args
        return authorizes(self.bpy,'configure_curve_geometry',args,self.owned,args)
    def test_guards_names_and_fixed_plan(self):
        self.assertTrue(self.allowed())
        self.guard.return_value=False;self.assertFalse(self.allowed());self.guard.return_value=True
        self.assertFalse(authorizes(self.bpy,'configure_curve_geometry',self.args,self.owned,{**self.args,'name':'Other'}))
        self.bpy.data.objects['Owned']=NS();self.assertFalse(self.allowed())
    def test_bounds_flags_and_unowned_targets(self):
        for change in ({'approved':True},{'request_id':'not-proof'},{'name':'Cube'},{'settings':{'body':'x'*33}},{'settings':{'body':'Fixture','extrude':.2}},{'settings':{'body':'Fixture','resolution_u':13}}):
            with self.subTest(change=change):self.assertFalse(self.allowed({**self.args,**change}))
