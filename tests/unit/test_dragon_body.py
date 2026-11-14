"""Isolated head/body geometry and production-boundary regression checks."""
from collections import Counter
import math
import threading
import unittest
from unittest.mock import patch

from blender_addon.universal_mcp.dragon_body import (
    CORE_PROFILE, JAW_PROFILE, loft_geometry, spike_geometry, model_head_body,
)


class TestDragonBody(unittest.TestCase):
    def assert_closed(self, vertices, faces):
        edges = Counter(tuple(sorted((a, b))) for f in faces for a, b in zip(f, f[1:]+f[:1]))
        self.assertTrue(all(n == 2 for n in edges.values()))
        self.assertEqual(len(vertices)-len(edges)+len(faces), 2)
        neighbours = {i: set() for i in range(len(vertices))}
        for a, b in edges:
            neighbours[a].add(b); neighbours[b].add(a)
        seen = {0}; stack = [0]
        while stack:
            for i in neighbours[stack.pop()] - seen:
                seen.add(i); stack.append(i)
        self.assertEqual(len(seen), len(vertices))
        self.assertTrue(all(math.isfinite(x) for v in vertices for x in v))

    def test_core_and_jaw_are_individually_connected_closed_surfaces(self):
        for profile in (CORE_PROFILE, JAW_PROFILE):
            data = loft_geometry(profile)
            self.assert_closed(data['vertices'], data['faces'])
            xs = [data['vertices'][i*data['sides']][0] for i in range(data['rings'])]
            self.assertTrue(all(a < b for a,b in zip(xs,xs[1:])))

    def test_anatomical_relief_is_bilateral_and_changes_lateral_contours(self):
        sculpted = loft_geometry(); plain = loft_geometry(anatomical=False)
        self.assertGreater(max(math.dist(a,b) for a,b in zip(sculpted['vertices'],plain['vertices'])), .04)
        sides = sculpted['sides']
        for ring in range(sculpted['rings']):
            for j in range(sides):
                a = sculpted['vertices'][ring*sides+j]
                b = sculpted['vertices'][ring*sides+(sides//2-j)%sides]
                self.assertAlmostEqual(a[0],b[0]); self.assertAlmostEqual(a[1],-b[1]); self.assertAlmostEqual(a[2],b[2])

    def test_nose_neck_and_chest_share_one_mesh_and_mouth_is_open(self):
        core=loft_geometry(); jaw=loft_geometry(JAW_PROFILE,anatomical=False)
        front=[v for v in core['vertices'] if -3.5<v[0]<-3.2]
        lower=[v for v in jaw['vertices'] if -3.5<v[0]<-3.2]
        self.assertGreater(min(v[2] for v in front)-max(v[2] for v in lower), .05)
        self.assertLess(min(v[0] for v in core['vertices']),-3.6)
        self.assertGreater(max(v[0] for v in core['vertices']),2)
        self.assertTrue(any(core['belly']))

    def test_teeth_have_closed_nondegenerate_tips(self):
        vertices,faces=spike_geometry((0,0,0),(0,0,.1))
        self.assert_closed(vertices,faces)
        self.assertEqual(len(set(vertices)),len(vertices))

    def test_invalid_profiles_and_density_rejected(self):
        for kwargs in ({'steps':2},{'sides':100},{'profile':CORE_PROFILE[::-1]},
                       {'profile':((0,0,1,1),(1,0,-1,1),(2,0,1,1))}):
            with self.assertRaises(ValueError):loft_geometry(**kwargs)
        with self.assertRaises(ValueError):spike_geometry((0,0,0),(0,0,0))

    def test_production_context_and_worker_rejected_before_mutation(self):
        with patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=False):
            with self.assertRaises(PermissionError):model_head_body(None,None,None,None,None)
        failures=[]
        def worker():
            try:model_head_body(None,None,None,None,None)
            except PermissionError as exc:failures.append(str(exc))
        thread=threading.Thread(target=worker);thread.start();thread.join()
        self.assertEqual(failures,["Body modeling must run on Blender's main thread"])
