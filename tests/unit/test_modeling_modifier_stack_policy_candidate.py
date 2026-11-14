"""Detached extended modifier scope boundaries; no live activation."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from tests.policy_candidates.modeling_modifier_stack_policy import authorizes

class Stack(list):
    def get(self,name):return next((m for m in self if m.name==name),None)

class ModifierPolicyTests(unittest.TestCase):
    def setUp(self):
        self.mesh=NS(users=1,vertices=[0]*4,edges=[0]*4,polygons=[0],shape_keys=None,library=None,animation_data=None)
        self.obj=NS(type='MESH',mode='OBJECT',data=self.mesh,modifiers=Stack(),library=None,override_library=None,animation_data=None)
        self.bpy=NS(context=NS(mode='OBJECT',scene=NS(objects={'Owned':self.obj})))
        self.owned={'Owned':(self.obj,self.mesh,{})}
        self.args=dict(name='Owned',modifier_name='Mirror',modifier_type='MIRROR',action='add',properties={'use_axis':[True,False,False]},expected_snapshot_id='sha256:'+'a'*64)
        self.guard=self.enterContext(patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=True))
    def allowed(self,args=None):
        args=self.args if args is None else args
        return authorizes(self.bpy,'edit_modifier_stack',args,self.owned,args)
    def test_guards_identity_and_exact_fixed_plan(self):
        self.assertTrue(self.allowed())
        self.assertFalse(authorizes(self.bpy,'edit_modifier_stack',self.args,self.owned,{**self.args,'modifier_name':'Different'}))
        self.mesh.users=2;self.assertFalse(self.allowed());self.mesh.users=1
        self.guard.return_value=False;self.assertFalse(self.allowed());self.guard.return_value=True
        self.obj.modifiers.append(NS(name='Unrecorded'))
        self.assertFalse(self.allowed())
    def test_scope_bounds_flags_missing_modifiers_and_operands(self):
        for change in ({'approved':True},{'request_id':'proof'}, {'modifier_type':'ARRAY','properties':{'count':3}}, {'modifier_type':'BEVEL','properties':{'width':.2}}, {'modifier_type':'BOOLEAN','properties':{'operand_name':'Cube'}}, {'action':'remove','properties':{}}):
            with self.subTest(change=change):self.assertFalse(self.allowed({**self.args,**change}))
