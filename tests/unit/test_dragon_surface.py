"""Organic surface shape, flow, reproducibility and isolation regressions."""
from collections import Counter
import copy
import math
import threading
import unittest
from unittest.mock import patch
from blender_addon.universal_mcp.dragon_body import loft_geometry
from blender_addon.universal_mcp.dragon_armor import HORN,surface_sample
from blender_addon.universal_mcp.dragon_limbs_tail import sweep_geometry
from blender_addon.universal_mcp.dragon_surface import (
    rounded_scale,organic_specs,horn_collar,refine_dragon_surface,SCALE_VERTICES,RIDGE_INDEX,
)


class TestDragonSurface(unittest.TestCase):
    def setUp(self):self.vertices=loft_geometry()['vertices']

    def closed(self,vertices,faces):
        edges=Counter(tuple(sorted((a,b))) for f in faces for a,b in zip(f,f[1:]+f[:1]))
        self.assertTrue(all(n==2 for n in edges.values()))
        self.assertEqual(len(vertices)-len(edges)+len(faces),2)
        origin=vertices[0];volume=0
        for face in faces:
            a=[vertices[face[0]][k]-origin[k] for k in range(3)]
            for j in range(1,len(face)-1):
                b=[vertices[face[j]][k]-origin[k] for k in range(3)];c=[vertices[face[j+1]][k]-origin[k] for k in range(3)]
                cross=(b[1]*c[2]-b[2]*c[1],b[2]*c[0]-b[0]*c[2],b[0]*c[1]-b[1]*c[0])
                volume+=sum(a[k]*cross[k] for k in range(3))/6
        self.assertGreater(volume,0)

    def spec(self,seed=37):return {'t':.45,'u':.13,'dt':.018,'du':.035,'height':.0035,'angle':.12,'seed':seed}

    def test_rounded_leaf_is_closed_outward_and_has_more_than_six_outline_sides(self):
        v,f=rounded_scale(self.vertices,48,self.spec());self.closed(v,f)
        self.assertEqual(len(v),SCALE_VERTICES);self.assertGreater(len(f),24)

    def test_contour_variation_is_deterministic_and_does_not_mutate_source(self):
        before=copy.deepcopy(self.vertices)
        a=rounded_scale(self.vertices,48,self.spec());b=rounded_scale(self.vertices,48,self.spec())
        c=rounded_scale(self.vertices,48,self.spec(81))
        self.assertEqual(a,b);self.assertNotEqual(a[0],c[0]);self.assertEqual(self.vertices,before)

    def test_scale_crown_remains_fitted_at_low_relief(self):
        s=self.spec();v,_=rounded_scale(self.vertices,48,s)
        p,n=surface_sample(self.vertices,48,s['t']-.04*s['dt'],s['u'])
        for k in range(3):self.assertAlmostEqual(v[RIDGE_INDEX][k],p[k]+s['height']*n[k])
        self.assertLess(s['height'],.005)

    def test_adaptive_layout_has_nonuniform_positions_sizes_and_orientation(self):
        a=organic_specs(self.vertices,48,.25,.85,.15,.16,'Torso')
        self.assertEqual(a,organic_specs(self.vertices,48,.25,.85,.15,.16,'Torso'))
        self.assertGreater(len({round(s['dt'],6) for s in a}),20)
        self.assertGreater(len({round(s['u'],6) for s in a}),100)
        self.assertGreater(len({round(s['angle'],4) for s in a}),100)
        self.assertTrue(all(math.sin(2*math.pi*s['u'])>=-.65 for s in a))
        self.assertTrue(all(s['t']-.7*s['dt']>0 and s['t']+.7*s['dt']<1 for s in a))

    def test_horn_root_sleeve_preserves_horn_and_tapers_to_existing_radius(self):
        for side in (1,-1):
            original=sweep_geometry(HORN,steps=12,sides=16,side=side)['vertices'];before=copy.deepcopy(original)
            v,f=horn_collar(original,side=side);self.closed(v,f)
            end=original[7*16:8*16];center=tuple(sum(p[k] for p in end)/16 for k in range(3))
            self.assertLess(math.dist(v[-1],center),math.dist(original[8*16-1],center))
            self.assertEqual(original,before)

    def test_mirrored_scale_winding_stays_positive(self):
        mirrored=[(x,-y,z) for x,y,z in self.vertices]
        v,f=rounded_scale(mirrored,48,self.spec(),side=-1);self.closed(v,f)

    def test_invalid_dimensions_density_and_rotation_rejected(self):
        for patch_values in ({'dt':-.1},{'height':.2},{'angle':1}):
            with self.assertRaises(ValueError):rounded_scale(self.vertices,48,{**self.spec(),**patch_values})
        with self.assertRaises(ValueError):organic_specs(self.vertices,48,.2,.8,.001,.1,'Torso')
        with self.assertRaises(ValueError):horn_collar([])

    def test_production_and_worker_refinement_rejected_before_mutation(self):
        with patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=False):
            with self.assertRaises(PermissionError):refine_dragon_surface(None)
        failures=[]
        def worker():
            try:refine_dragon_surface(None)
            except PermissionError as exc:failures.append(str(exc))
        thread=threading.Thread(target=worker);thread.start();thread.join()
        self.assertEqual(failures,["Surface refinement must run on Blender's main thread"])
