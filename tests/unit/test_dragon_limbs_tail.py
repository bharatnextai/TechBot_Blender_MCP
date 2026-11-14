"""Limb/tail geometry, silhouette proportions and isolation regressions."""
from collections import Counter
import math
import threading
import unittest
from unittest.mock import patch

from blender_addon.universal_mcp.dragon_limbs_tail import (
    FRONT,HIND,TAIL,foot_specs,sweep_geometry,model_limbs_tail,
)


class TestDragonLimbsTail(unittest.TestCase):
    def closed(self,data):
        vertices,faces=data['vertices'],data['faces']
        edges=Counter(tuple(sorted((a,b))) for f in faces for a,b in zip(f,f[1:]+f[:1]))
        self.assertTrue(all(n==2 for n in edges.values()))
        self.assertEqual(len(vertices)-len(edges)+len(faces),2)
        adjacency={i:set() for i in range(len(vertices))}
        for a,b in edges:adjacency[a].add(b);adjacency[b].add(a)
        visited={0};stack=[0]
        while stack:
            for i in adjacency[stack.pop()]-visited:visited.add(i);stack.append(i)
        self.assertEqual(len(visited),len(vertices))
        volume=0
        for face in faces:
            a=vertices[face[0]]
            for j in range(1,len(face)-1):
                b,c=vertices[face[j]],vertices[face[j+1]]
                cross=(b[1]*c[2]-b[2]*c[1],b[2]*c[0]-b[0]*c[2],b[0]*c[1]-b[1]*c[0])
                volume+=sum(a[k]*cross[k] for k in range(3))/6
        self.assertGreater(volume,0)
        self.assertTrue(all(math.isfinite(x) for v in vertices for x in v))

    def test_limbs_and_tail_are_closed_connected_and_outward(self):
        for profile in (FRONT,HIND,TAIL):
            for side in (1,-1):self.closed(sweep_geometry(profile,side=side))

    def test_mirrored_limbs_match_exactly_with_reversed_winding(self):
        a=sweep_geometry(HIND);b=sweep_geometry(HIND,side=-1)
        self.assertEqual([(x,-y,z) for x,y,z in a['vertices']],b['vertices'])
        self.assertEqual([tuple(reversed(f)) for f in a['faces']],b['faces'])

    def test_tail_tapers_continuously_curves_and_has_raised_tip(self):
        data=sweep_geometry(TAIL,steps=16,sides=48)
        radii=[p[3] for p in data['centers']]
        self.assertTrue(all(a>=b for a,b in zip(radii,radii[1:])))
        self.assertGreater(TAIL[-1][0]-TAIL[0][0],3.8)
        self.assertGreater(TAIL[-1][2]-min(p[2] for p in TAIL),.8)
        self.assertGreater(TAIL[-1][1],.7)
        self.assertLess(radii[-1],radii[0]/50)

    def test_ring_frames_do_not_flip_at_joint_bends(self):
        for profile in (FRONT,HIND,TAIL):
            frames=sweep_geometry(profile)['frames']
            self.assertTrue(all(sum(a[0][k]*b[0][k] for k in range(3))>.8 for a,b in zip(frames,frames[1:])))

    def test_four_distinct_digits_and_tapered_curved_claws_per_foot(self):
        for end in ('Front','Hind'):
            digits=foot_specs(end)['digits'];self.assertEqual(len(digits),4)
            self.assertEqual(len({tuple(t[-1][:3]) for _,t,_ in digits}),4)
            for _,toe,claw in digits:
                self.closed(sweep_geometry(toe,sides=20))
                self.closed(sweep_geometry(claw,sides=20))
                self.assertLess(claw[-1][2],claw[0][2])
                self.assertLess(claw[-1][3],claw[0][3]/10)

    def test_density_invalid_controls_and_degenerate_paths_rejected(self):
        for kwargs in ({'steps':2},{'sides':80},{'side':0},{'profile':((0,0,0,1,1),)*3},
                       {'profile':((0,0,0,1,1),(1,0,0,-1,1),(2,0,0,1,1))}):
            with self.assertRaises(ValueError):sweep_geometry(**{'profile':TAIL,**kwargs})

    def test_production_and_worker_contexts_cannot_mutate(self):
        with patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=False):
            with self.assertRaises(PermissionError):model_limbs_tail(None,None,None,None)
        failures=[]
        def worker():
            try:model_limbs_tail(None,None,None,None)
            except PermissionError as exc:failures.append(str(exc))
        thread=threading.Thread(target=worker);thread.start();thread.join()
        self.assertEqual(failures,["Limb/tail modeling must run on Blender's main thread"])
