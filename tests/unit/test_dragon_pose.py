"""Silhouette deformation, rigid detail groups and isolation regressions."""
import math
import threading
import unittest
from unittest.mock import patch
from blender_addon.universal_mcp.dragon_pose import (
    HEAD_SHIFT,body_point,head_point,wing_point,group_for,refine_dragon_pose,
)


class TestDragonPose(unittest.TestCase):
    def test_head_region_and_rigid_details_receive_identical_lift(self):
        for point in ((-3.5,.2,2.4),(-2.6,-.4,2.8),(-2.21,0,2.5)):
            self.assertEqual(body_point(point),head_point(point))
        a,b=(-3.2,.1,2.5),(-1.7,.4,3.4)
        self.assertAlmostEqual(math.dist(head_point(a),head_point(b)),math.dist(a,b))
        self.assertEqual(HEAD_SHIFT,(.4,0,1))

    def test_neck_rises_smoothly_and_longitudinal_mapping_never_folds(self):
        values=[body_point((-2.3+i*.005,.5,2.0)) for i in range(301)]
        self.assertTrue(all(a[0]<b[0] for a,b in zip(values,values[1:])))
        self.assertGreater(body_point((-1.9,0,2.3))[2],3)
        for x in (-2.2,-.85):
            h=1e-5;a=body_point((x-h,.5,2));b=body_point((x+h,.5,2))
            self.assertAlmostEqual((b[0]-a[0])/(2*h),1,places=4)
            self.assertAlmostEqual((b[2]-a[2])/(2*h),0,places=4)

    def test_waist_is_narrower_with_fixed_shoulder_and_tail_boundary(self):
        self.assertLess(body_point((.6,.9,2.4))[1],.81)
        self.assertEqual(body_point((0,.9,2.4)),(0,.9,2.4))
        self.assertEqual(body_point((1.7,.4,1.1)),(1.7,.4,1.1))

    def test_each_wing_is_rigid_and_pivots_about_its_fixed_inboard_anchor(self):
        a,b=(-1.2,3.7,3.15),(2.8,4.6,2.0)
        self.assertAlmostEqual(math.dist(wing_point(a,1),wing_point(b,1)),math.dist(a,b))
        ar,br=(a[0],-a[1],a[2]),(b[0],-b[1],b[2])
        self.assertAlmostEqual(math.dist(wing_point(ar,-1),wing_point(br,-1)),math.dist(ar,br))
        for side in (1,-1):self.assertEqual(wing_point((0,.85*side,1.8),side),(0,.85*side,1.8))
        self.assertLess(wing_point(ar,-1)[2],wing_point(a,1)[2])

    def test_leading_wrist_rises_and_trailing_membrane_drops(self):
        wrist=(-1.2,3.7,3.15);trailing=(3.1,2.8,1.5)
        self.assertGreater(wing_point(wrist,1)[2],wrist[2])
        self.assertLess(wing_point(trailing,1)[2],trailing[2])

    def test_classification_moves_all_attached_details_but_keeps_limbs_tail_camera(self):
        for name in ('WingAnatomy_L_RootTendon','Dragon_Wing_Finger_L4','Wing_L_Proxy'):
            self.assertEqual(group_for(name),'wing_L')
        for name in ('Dragon_Horn_Root_L','Dragon_Pupil_R','Dragon_Armor_TemporalHorn_R'):
            self.assertEqual(group_for(name),'head')
        for name in ('Dragon_Armor_Hind_L','Dragon_Tail_Base','Dragon_Leg_Front_R','Camera','Cube'):
            self.assertIsNone(group_for(name))

    def test_invalid_body_point_and_wing_side_rejected(self):
        with self.assertRaises(ValueError):body_point((float('nan'),0,0))
        with self.assertRaises(ValueError):wing_point((1,2,3),0)

    def test_default_and_worker_contexts_fail_before_bpy_mutation(self):
        with patch('blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval',return_value=False):
            with self.assertRaises(PermissionError):refine_dragon_pose(None)
        failures=[]
        def worker():
            try:refine_dragon_pose(None)
            except PermissionError as exc:failures.append(str(exc))
        thread=threading.Thread(target=worker);thread.start();thread.join()
        self.assertEqual(failures,["Pose refinement must run on Blender's main thread"])
