"""Fitted scale topology, regional layout and isolated execution regressions."""
from collections import Counter
import copy
import math
import threading
import unittest
from unittest.mock import patch

from blender_addon.universal_mcp.dragon_body import loft_geometry
from blender_addon.universal_mcp.dragon_limbs_tail import sweep_geometry
from blender_addon.universal_mcp.dragon_armor import (
    HORN,surface_sample,x_parameter,plate_geometry,field_specs,detail_dragon_armor,
)


class TestDragonArmor(unittest.TestCase):
    def setUp(self):self.vertices=loft_geometry()['vertices']

    def test_plate_is_closed_outward_shell_on_actual_curved_surface(self):
        for t,u in ((.2,.25),(.5,.03),(.8,.7)):
            vertices,faces=plate_geometry(self.vertices,48,t,u,.02,.035,.015)
            edges=Counter(tuple(sorted((a,b))) for f in faces for a,b in zip(f,f[1:]+f[:1]))
            self.assertTrue(all(n==2 for n in edges.values()))
            self.assertEqual(len(vertices)-len(edges)+len(faces),2)
            volume=0
            for f in faces:
                a=vertices[f[0]]
                for j in range(1,len(f)-1):
                    b,c=vertices[f[j]],vertices[f[j+1]]
                    cross=(b[1]*c[2]-b[2]*c[1],b[2]*c[0]-b[0]*c[2],b[0]*c[1]-b[1]*c[0])
                    volume+=sum(a[k]*cross[k] for k in range(3))/6
            self.assertGreater(volume,0)

    def test_surface_sampler_wraps_and_preserves_input(self):
        before=copy.deepcopy(self.vertices)
        a=surface_sample(self.vertices,48,.4,.01)
        b=surface_sample(self.vertices,48,.4,1.01)
        for p,q in zip(a,b):
            for x,y in zip(p,q):self.assertAlmostEqual(x,y)
        self.assertAlmostEqual(sum(x*x for x in a[1]),1)
        self.assertEqual(self.vertices,before)

    def test_plate_ridge_is_attached_at_declared_surface_offset(self):
        t,u,dt,du,h=.4,.21,.02,.035,.018
        vertices,_=plate_geometry(self.vertices,48,t,u,dt,du,h)
        p,n=surface_sample(self.vertices,48,t-.08*dt,u)
        for k in range(3):self.assertAlmostEqual(vertices[12][k],p[k]+h*1.18*n[k])

    def test_regional_layout_is_staggered_varied_and_anatomically_distinct(self):
        a=field_specs(.2,.8,12,22,'Neck');b=field_specs(.2,.8,12,3,'Ventral')
        self.assertTrue(all(math.sin(2*math.pi*s['u'])>=-.65 for s in a))
        self.assertTrue(all(.65<s['u']<.85 for s in b))
        self.assertGreater(len({round(s['dt'],5) for s in a}),10)
        self.assertGreater(max(s['du'] for s in b),max(s['du'] for s in a))
        # Curved rows vary longitudinal placement around the circumference.
        self.assertGreater(len({round(s['t'],6) for s in a}),12)
        self.assertTrue(any(s['u']==0 for s in a))
        self.assertTrue(any(abs(s['u']-1/44)<1e-8 for s in a))
        tail=field_specs(.025,.94,34,14,'Tail')
        self.assertGreater(tail[0]['height'],tail[-1]['height']*2)

    def test_swept_horns_are_bilateral_tapered_and_point_backwards(self):
        left=sweep_geometry(HORN,sides=16);right=sweep_geometry(HORN,sides=16,side=-1)
        self.assertEqual([(x,-y,z) for x,y,z in left['vertices']],right['vertices'])
        self.assertGreater(HORN[-1][0]-HORN[0][0],.8)
        self.assertLess(HORN[-1][3],HORN[0][3]/40)

    def test_x_mapping_samples_preserved_core_instead_of_rebuilding_it(self):
        t=x_parameter(self.vertices,48,-1.8)
        p,_=surface_sample(self.vertices,48,t,.2)
        self.assertAlmostEqual(p[0],-1.8)

    def test_invalid_surface_and_plate_domains_rejected(self):
        for args in (([],48,.5,.2),(self.vertices,48,1,.2),(self.vertices,48,.4,float('nan'))):
            with self.assertRaises(ValueError):surface_sample(*args)
        with self.assertRaises(ValueError):plate_geometry(self.vertices,48,.5,.2,-.1,.1,.01)
        with self.assertRaises(ValueError):field_specs(.1,.9,4,4,'Uniform')

    def test_production_and_worker_calls_fail_before_mutation(self):
        with patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=False):
            with self.assertRaises(PermissionError):detail_dragon_armor(None)
        failures=[]
        def worker():
            try:detail_dragon_armor(None)
            except PermissionError as exc:failures.append(str(exc))
        thread=threading.Thread(target=worker);thread.start();thread.join()
        self.assertEqual(failures,["Armor modeling must run on Blender's main thread"])
