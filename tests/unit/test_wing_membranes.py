"""Topology and shape checks for the isolated wing generator."""
from collections import Counter, defaultdict
import math
import threading
import unittest
from unittest.mock import patch

from blender_addon.universal_mcp.wing_membranes import membrane_geometry, replace_wing_membranes, _tube_mesh


class TestWingMembranes(unittest.TestCase):
    def test_connected_manifold_disk_and_quad_layout(self):
        data = membrane_geometry()
        edges, adjacent = Counter(), defaultdict(set)
        for face in data["faces"]:
            self.assertEqual(len(face), len(set(face)))
            for a, b in zip(face, face[1:]+face[:1]):
                edges[tuple(sorted((a, b)))] += 1
                adjacent[a].add(b)
                adjacent[b].add(a)
        self.assertTrue(all(n in (1, 2) for n in edges.values()))
        seen, pending = set(), [0]
        while pending:
            v = pending.pop()
            if v not in seen:
                seen.add(v)
                pending.extend(adjacent[v]-seen)
        self.assertEqual(len(seen), len(data["vertices"]))
        self.assertEqual(len(data["vertices"])-len(edges)+len(data["faces"]), 1)
        boundary_degree = Counter(v for edge, n in edges.items() if n == 1 for v in edge)
        self.assertTrue(all(n == 2 for n in boundary_degree.values()))
        self.assertGreater(sum(len(f)==4 for f in data["faces"])/len(data["faces"]), 0.9)

    def test_finite_uv_nonzero_projected_faces(self):
        data = membrane_geometry()
        self.assertEqual(len(data["uv"]), len(data["vertices"]))
        self.assertTrue(all(math.isfinite(v) for p in data["vertices"] for v in p))
        self.assertTrue(all(0 <= v <= 1 for p in data["uv"] for v in p))
        for face in data["faces"]:
            points = [data["vertices"][i] for i in face]
            signed_area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))/2
            self.assertGreater(signed_area, 1e-8)

    def test_exact_mirror_with_consistent_dorsal_normals(self):
        left = membrane_geometry(1, (0,1.35,1.8))
        right = membrane_geometry(-1, (0,-1.35,1.8))
        self.assertEqual(right["vertices"], [(x,-y,z) for x,y,z in left["vertices"]])
        self.assertEqual(right["faces"], [tuple(reversed(f)) for f in left["faces"]])

    def test_scalloped_outer_edges_and_connected_finger_seams(self):
        plain = membrane_geometry(scallop=0)
        shaped = membrane_geometry(scallop=0.22)
        for index in (2,3,4,5):
            midpoint = index*14+7
            self.assertNotEqual(plain["boundary"][midpoint],shaped["boundary"][midpoint])
            self.assertEqual(plain["boundary"][index*14],shaped["boundary"][index*14])
        self.assertEqual(len(shaped["ribs"]),5)
        self.assertGreater(len(shaped["boundary"]),4)

    def test_inboard_attachment_reaches_body_instead_of_floating(self):
        left = membrane_geometry()
        right = membrane_geometry(-1, (0, -1.35, 1.8))
        self.assertAlmostEqual(left["ribs"][0][0][1], 0.85)
        self.assertAlmostEqual(right["ribs"][0][0][1], -0.85)

    def test_membrane_spokes_follow_structural_finger_centers(self):
        data = membrane_geometry()
        width = len(data["boundary"])
        wrist = data["vertices"][0]
        for rib, anchor in zip(data["ribs"][1:], (5, 4, 3, 2)):
            for ring in range(1, 19):
                point = data["vertices"][1+(ring-1)*width+anchor*14]
                expected = [(1-ring/18)*wrist[k]+(ring/18)*rib[-1][k] for k in range(3)]
                for actual, target in zip(point, expected):
                    self.assertAlmostEqual(actual, target, places=12)

    def test_capped_ribs_have_two_faces_per_edge(self):
        v,f=_tube_mesh([(0,0,0),(1,2,1),(2,3,2)])
        edges=Counter(tuple(sorted((a,b))) for face in f for a,b in zip(face,face[1:]+face[:1]))
        self.assertTrue(all(n==2 for n in edges.values()))
        self.assertEqual(len(v)-len(edges)+len(f),2)

    def test_invalid_inputs_are_bounded(self):
        for kwargs in ({"side":0},{"side":True},{"radial":1},{"spans":65},{"scallop":0.5},{"root":(0,float('nan'),1)}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                membrane_geometry(**kwargs)

    def test_production_profile_cannot_run_builder(self):
        with patch("blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval",return_value=False):
            with self.assertRaises(PermissionError):
                replace_wing_membranes(None,None,None)

    def test_worker_thread_rejected_before_any_blender_access(self):
        errors=[]
        def worker():
            try:
                replace_wing_membranes(None,None,None)
            except PermissionError as exc:
                errors.append(str(exc))
        thread=threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(errors,["Wing generation must run on Blender's main thread"])
