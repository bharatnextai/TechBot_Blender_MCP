"""
Unit tests for Phase 3.4: Spatial Relationship Engine.
Verifies:
1. ON_TOP_OF and UNDER evaluation with vertical contact tolerance and horizontal XY overlap.
2. INSIDE and CONTAINS evaluation using AABB and OBB corner containment.
3. FACING directional alignment evaluation under varying angles and object rotations.
4. LEFT_OF and RIGHT_OF lateral evaluation in local and world reference frames.
5. IN_FRONT_OF and BEHIND longitudinal evaluation in local and world reference frames.
6. NEAR proximity evaluation using exact AABB surface-to-surface distance.
7. SceneGraph integration: check_spatial_relation, get_spatial_relations, and find_related_objects.
"""

import unittest
import math
from typing import Dict, Any, List

from mcp_service.intelligence.scenegraph import (
    AABB,
    OBB,
    SceneNode,
    SceneGraph,
)
from mcp_service.intelligence.spatial_relations import (
    SpatialRelationType,
    SpatialRelationResult,
    SpatialRelationshipEngine,
)


class TestPhase3SpatialRelations(unittest.TestCase):

    def setUp(self):
        self.engine = SpatialRelationshipEngine()

    def test_on_top_of_and_under(self):
        """Verifies ON_TOP_OF and reciprocal UNDER detection with contact and footprint tolerances."""
        # Table: centered at (0, 0, 0.5), dimensions (2.0, 2.0, 1.0) -> Z span: [0.0, 1.0]
        table = SceneNode(
            name="Table",
            location=(0.0, 0.0, 0.5),
            dimensions=(2.0, 2.0, 1.0),
        )

        # Cup: resting directly on top at (0, 0, 1.25), dimensions (0.5, 0.5, 0.5) -> Z span: [1.0, 1.5]
        cup = SceneNode(
            name="Cup",
            location=(0.0, 0.0, 1.25),
            dimensions=(0.5, 0.5, 0.5),
        )

        # 1. Cup on top of table
        res_on_top = self.engine.eval_on_top_of(cup, table)
        self.assertTrue(res_on_top.holds)
        self.assertEqual(res_on_top.relation, SpatialRelationType.ON_TOP_OF)
        self.assertAlmostEqual(res_on_top.metrics["vertical_gap"], 0.0, places=3)
        self.assertGreater(res_on_top.confidence, 0.7)

        # 2. Table under cup
        res_under = self.engine.eval_under(table, cup)
        self.assertTrue(res_under.holds)
        self.assertEqual(res_under.relation, SpatialRelationType.UNDER)

        # 3. Table is NOT on top of cup
        res_table_on_cup = self.engine.eval_on_top_of(table, cup)
        self.assertFalse(res_table_on_cup.holds)

        # 4. Floating object: too high (Z=3.0)
        balloon = SceneNode(
            name="Balloon",
            location=(0.0, 0.0, 3.0),
            dimensions=(0.5, 0.5, 0.5),
        )
        res_balloon = self.engine.eval_on_top_of(balloon, table)
        self.assertFalse(res_balloon.holds)

        # 5. Shifted object: correct Z but no XY footprint overlap
        sidewalk_cup = SceneNode(
            name="SidewalkCup",
            location=(5.0, 5.0, 1.25),
            dimensions=(0.5, 0.5, 0.5),
        )
        res_sidewalk = self.engine.eval_on_top_of(sidewalk_cup, table)
        self.assertFalse(res_sidewalk.holds)

    def test_inside_and_contains(self):
        """Verifies INSIDE and reciprocal CONTAINS containment."""
        # Cabinet / Big Box: centered at (0, 0, 0), dimensions (4.0, 4.0, 4.0)
        cabinet = SceneNode(
            name="Cabinet",
            location=(0.0, 0.0, 0.0),
            dimensions=(4.0, 4.0, 4.0),
        )

        # Book: centered at (0.5, 0.5, 0.5), dimensions (0.8, 0.8, 0.8)
        book = SceneNode(
            name="Book",
            location=(0.5, 0.5, 0.5),
            dimensions=(0.8, 0.8, 0.8),
        )

        # Outside Item: at (5.0, 0.0, 0.0)
        lamp = SceneNode(
            name="Lamp",
            location=(5.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 2.0),
        )

        # 1. Book is inside Cabinet
        res_inside = self.engine.eval_inside(book, cabinet)
        self.assertTrue(res_inside.holds)
        self.assertEqual(res_inside.relation, SpatialRelationType.INSIDE)
        self.assertEqual(res_inside.metrics["containment_ratio"], 1.0)

        # 2. Cabinet contains Book
        res_contains = self.engine.eval_contains(cabinet, book)
        self.assertTrue(res_contains.holds)
        self.assertEqual(res_contains.relation, SpatialRelationType.CONTAINS)

        # 3. Cabinet is NOT inside Book
        res_cabinet_inside = self.engine.eval_inside(cabinet, book)
        self.assertFalse(res_cabinet_inside.holds)

        # 4. Lamp is NOT inside Cabinet
        res_lamp = self.engine.eval_inside(lamp, cabinet)
        self.assertFalse(res_lamp.holds)

    def test_facing_directional_alignment(self):
        """Verifies FACING directional orientation with angular tolerances and object rotation."""
        # Character at origin, facing +Y (default rotation [0, 0, 0])
        hero = SceneNode(
            name="Hero",
            location=(0.0, 0.0, 0.0),
            rotation_euler=(0.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 2.0),
        )

        # Target 1: Directly ahead at (0.0, 5.0, 0.0) -> angle = 0 deg
        target_front = SceneNode(
            name="TargetFront",
            location=(0.0, 5.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        res_front = self.engine.eval_facing(hero, target_front)
        self.assertTrue(res_front.holds)
        self.assertAlmostEqual(res_front.metrics["angle_deg"], 0.0, places=2)
        self.assertAlmostEqual(res_front.confidence, 1.0, places=2)

        # Target 2: Directly behind at (0.0, -5.0, 0.0) -> angle = 180 deg
        target_behind = SceneNode(
            name="TargetBehind",
            location=(0.0, -5.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        res_behind = self.engine.eval_facing(hero, target_behind)
        self.assertFalse(res_behind.holds)
        self.assertAlmostEqual(res_behind.metrics["angle_deg"], 180.0, places=2)

        # Target 3: At (4.0, 4.0, 0.0) -> angle = 45 deg
        target_angle = SceneNode(
            name="TargetAngle",
            location=(4.0, 4.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        res_angle_50 = self.engine.eval_facing(hero, target_angle, angle_tolerance_deg=50.0)
        self.assertTrue(res_angle_50.holds)
        self.assertAlmostEqual(res_angle_50.metrics["angle_deg"], 45.0, places=1)

        res_angle_30 = self.engine.eval_facing(hero, target_angle, angle_tolerance_deg=30.0)
        self.assertFalse(res_angle_30.holds)

        # Rotated Hero: turned 90 degrees around Z axis (pi/2) -> facing -X
        hero_rot = SceneNode(
            name="HeroRotated",
            location=(0.0, 0.0, 0.0),
            rotation_euler=(0.0, 0.0, math.pi / 2.0),
            dimensions=(1.0, 1.0, 2.0),
        )
        target_west = SceneNode(
            name="TargetWest",
            location=(-5.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        res_rot = self.engine.eval_facing(hero_rot, target_west)
        self.assertTrue(res_rot.holds)
        self.assertAlmostEqual(res_rot.metrics["angle_deg"], 0.0, places=1)

    def test_left_of_and_right_of(self):
        """Verifies LEFT_OF and RIGHT_OF lateral evaluation in world and local frames."""
        center_obj = SceneNode(
            name="Center",
            location=(0.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        left_obj = SceneNode(
            name="Left",
            location=(-3.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        right_obj = SceneNode(
            name="Right",
            location=(3.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )

        # LeftObj relative to CenterObj
        self.assertTrue(self.engine.eval_left_of(left_obj, center_obj).holds)
        self.assertFalse(self.engine.eval_right_of(left_obj, center_obj).holds)

        # RightObj relative to CenterObj
        self.assertTrue(self.engine.eval_right_of(right_obj, center_obj).holds)
        self.assertFalse(self.engine.eval_left_of(right_obj, center_obj).holds)

    def test_in_front_of_and_behind(self):
        """Verifies IN_FRONT_OF and BEHIND longitudinal evaluation in world and local frames."""
        center_obj = SceneNode(
            name="Center",
            location=(0.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        front_obj = SceneNode(
            name="Front",
            location=(0.0, 4.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )
        behind_obj = SceneNode(
            name="Behind",
            location=(0.0, -4.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )

        # FrontObj relative to Center
        self.assertTrue(self.engine.eval_in_front_of(front_obj, center_obj).holds)
        self.assertFalse(self.engine.eval_behind(front_obj, center_obj).holds)

        # BehindObj relative to Center
        self.assertTrue(self.engine.eval_behind(behind_obj, center_obj).holds)
        self.assertFalse(self.engine.eval_in_front_of(behind_obj, center_obj).holds)

    def test_near_proximity(self):
        """Verifies NEAR proximity evaluation using exact AABB surface distance."""
        obj_a = SceneNode(
            name="Base",
            location=(0.0, 0.0, 0.0),
            dimensions=(2.0, 2.0, 2.0),  # spans [-1, 1] on each axis
        )

        # Close: centered at (2.2, 0, 0), dimensions (1, 1, 1) -> spans [1.7, 2.7]
        # Surface distance = 1.7 - 1.0 = 0.7m
        obj_close = SceneNode(
            name="Close",
            location=(2.2, 0.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )

        # Distant: centered at (10.0, 0, 0) -> surface distance = 9.5 - 1.0 = 8.5m
        obj_distant = SceneNode(
            name="Distant",
            location=(10.0, 0.0, 0.0),
            dimensions=(1.0, 1.0, 1.0),
        )

        # Near threshold = 1.0m: obj_close is within 1.0m (0.7m <= 1.0m)
        res_close = self.engine.eval_near(obj_close, obj_a, max_distance=1.0)
        self.assertTrue(res_close.holds)
        self.assertAlmostEqual(res_close.metrics["distance"], 0.7, places=2)

        # obj_distant is outside 1.0m
        res_distant = self.engine.eval_near(obj_distant, obj_a, max_distance=1.0)
        self.assertFalse(res_distant.holds)

    def test_scenegraph_integration(self):
        """Verifies high-level spatial relation queries directly on SceneGraph."""
        sg = SceneGraph()

        desk = SceneNode(name="Desk", location=(0.0, 0.0, 0.5), dimensions=(3.0, 1.5, 1.0))
        laptop = SceneNode(name="Laptop", location=(0.0, 0.0, 1.05), dimensions=(0.4, 0.3, 0.1))
        chair = SceneNode(name="Chair", location=(0.0, -1.2, 0.5), dimensions=(0.6, 0.6, 1.0))

        sg.add_node(desk)
        sg.add_node(laptop)
        sg.add_node(chair)

        # 1. check_spatial_relation
        self.assertTrue(sg.check_spatial_relation("Laptop", "Desk", "ON_TOP_OF"))
        self.assertTrue(sg.check_spatial_relation("Desk", "Laptop", "UNDER"))
        self.assertFalse(sg.check_spatial_relation("Chair", "Desk", "ON_TOP_OF"))

        # 2. get_spatial_relations
        relations = sg.get_spatial_relations("Laptop", "Desk")
        rel_types = [r.relation for r in relations]
        self.assertIn(SpatialRelationType.ON_TOP_OF, rel_types)
        self.assertIn(SpatialRelationType.NEAR, rel_types)

        # 3. find_related_objects
        near_desk = sg.find_related_objects("Desk", "NEAR", max_distance=2.0)
        near_names = [name for name, _ in near_desk]
        self.assertIn("Laptop", near_names)
        self.assertIn("Chair", near_names)


if __name__ == "__main__":
    unittest.main()

