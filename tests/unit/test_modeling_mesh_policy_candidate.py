"""Detached mesh-test scope boundaries; no activation or registry decisions."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from tests.policy_candidates.modeling_mesh_policy import authorizes

class TestCandidate(unittest.TestCase):
    def setUp(self):
        self.mesh=NS(users=1,vertices=[0]*4,edges=[0]*4,polygons=[0],shape_keys=None,library=None)
        self.obj=NS(type="MESH",data=self.mesh,modifiers=[],library=None)
        self.bpy=NS(context=NS(mode="OBJECT",scene=NS(objects={"Owned":self.obj})))
        self.owned={"Owned":(self.obj,self.mesh)}
        self.args={"name":"Owned","expected_snapshot_id":"sha256:"+"a"*64,"operations":[{"action":"move_vertices","vertices":[0],"delta":[0,0,1]}]}
        self.guard=self.enterContext(patch("blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval",return_value=True))
    def test_identity_guards_and_policy_exclusion(self):
        self.assertTrue(authorizes(self.bpy,"edit_mesh",self.args,self.owned))
        self.assertFalse(authorizes(self.bpy,"edit_mesh",self.args,{}))
        self.mesh.users=2;self.assertFalse(authorizes(self.bpy,"edit_mesh",self.args,self.owned));self.mesh.users=1
        self.guard.return_value=False;self.assertFalse(authorizes(self.bpy,"edit_mesh",self.args,self.owned))
    def test_bounds_flags_and_other_tools(self):
        for extra in ({"trusted_approval":True},{"approved":True},{"request_id":"not-proof"},
            {"operations":[{"action":"move_vertices","vertices":[0],"delta":[0,0,3]}]},
            {"operations":[{"action":"bevel","edges":[0],"width":.2}]},
            {"operations":[{"action":"subdivide","edges":[0],"cuts":3}]}):
            with self.subTest(extra=extra):self.assertFalse(authorizes(self.bpy,"edit_mesh",{**self.args,**extra},self.owned))
        self.assertFalse(authorizes(self.bpy,"execute_blender_code",self.args,self.owned))
