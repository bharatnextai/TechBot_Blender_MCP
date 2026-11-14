"""Additive wing details: bounded sampling, closed topology and preservation."""
from collections import Counter
import copy
import math
import threading
import unittest
from unittest.mock import patch

from blender_addon.universal_mcp.wing_membranes import membrane_geometry
from blender_addon.universal_mcp.wing_anatomy import (
    _point,surface_sample,vein_network,tendon_fairing,joint_geometry,refine_wing_anatomy,
)


class TestWingAnatomy(unittest.TestCase):
    def setUp(self):
        self.surface=membrane_geometry()["vertices"]

    def assert_closed(self,vertices,faces):
        edges=Counter(tuple(sorted((a,b))) for face in faces for a,b in zip(face,face[1:]+face[:1]))
        self.assertTrue(all(count==2 for count in edges.values()))
        self.assertEqual(len(vertices)-len(edges)+len(faces),2)
        self.assertTrue(all(math.isfinite(x) for v in vertices for x in v))

    def test_sampling_existing_grid_without_modifying_it(self):
        before=copy.deepcopy(self.surface)
        for ring,column in ((3,12),(12,35),(18,70)):
            point=_point(self.surface,ring/18,column/84)
            expected=self.surface[1+(ring-1)*85+column]
            for a,b in zip(point,expected):self.assertAlmostEqual(a,b)
        p,n=surface_sample(self.surface,0.5,0.6)
        self.assertAlmostEqual(sum(x*x for x in n),1.0)
        self.assertGreater(n[2],0)
        self.assertEqual(self.surface,before)

    def test_vein_branches_attach_exactly_and_remain_in_panel(self):
        for panel in (2,3,4,5):
            paths=vein_network(panel)
            self.assertEqual(len(paths),4)
            for branch in paths[1:]:
                self.assertEqual(branch["uv"][0],paths[0]["uv"][branch["parent_index"]])
                self.assertLess(branch["radius"],paths[0]["radius"])
            for vein in paths:
                for t,u in vein["uv"]:
                    self.assertTrue(0<t<1)
                    self.assertTrue(panel/6<u<(panel+1)/6)

    def test_fairings_are_closed_and_uv_matched(self):
        original=copy.deepcopy(self.surface)
        for side in (1,-1):
            vertices=membrane_geometry(side,(0,1.35*side,1.8))["vertices"]
            for seam in (2,3,4,5):
                v,f,uv=tendon_fairing(vertices,seam,side)
                self.assert_closed(v,f)
                self.assertEqual(len(uv),len(v))
                for p,(t,u) in zip(v,uv):
                    surface,n=surface_sample(vertices,t,u)
                    distance=sum((p[k]-surface[k])*n[k] for k in range(3))
                    self.assertGreaterEqual(distance,0.00799)
                    self.assertLess(distance,0.05)
        self.assertEqual(self.surface,original)

    def test_rounded_joints_have_closed_topology(self):
        v,f=joint_geometry((0,1,2),(0.2,0.3,0.1))
        self.assert_closed(v,f)
        self.assertGreater(len(v),100)

    def test_flattened_joint_rotates_along_limb(self):
        v,f=joint_geometry((0,0,0),(0.24,0.105,0.055),math.pi/2)
        self.assert_closed(v,f)
        self.assertAlmostEqual(max(abs(p[0]) for p in v),0.105)
        self.assertAlmostEqual(max(abs(p[1]) for p in v),0.24)
        self.assertAlmostEqual(max(abs(p[2]) for p in v),0.055)

    def test_invalid_grid_parameters_and_panels_rejected(self):
        for params in (([],0.5,0.5),(self.surface,-0.1,0.5),(self.surface,0.5,2)):
            with self.assertRaises(ValueError):_point(*params)
        with self.assertRaises(ValueError):vein_network(0)

    def test_default_and_worker_context_cannot_mutate(self):
        with patch("blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval",return_value=False):
            with self.assertRaises(PermissionError):refine_wing_anatomy(None,None,None)
        failures=[]
        def worker():
            try:refine_wing_anatomy(None,None,None)
            except PermissionError as exc:failures.append(str(exc))
        thread=threading.Thread(target=worker);thread.start();thread.join()
        self.assertEqual(failures,["Wing refinement must run on Blender's main thread"])
