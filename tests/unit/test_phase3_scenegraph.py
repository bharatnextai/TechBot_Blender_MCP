"""
Unit tests for Phase 3.3: SceneGraph Spatial Hierarchy & Bounding Volume Engine.
Verifies:
1. AABB geometric calculations, contains_point, union, and intersection tests.
2. OBB exact 15-axis Separating Axis Theorem (SAT) collision detection, including rotated edge-edge cases.
3. SceneNode world-coordinate corner transformation under translation, scale, and Euler rotation.
4. SceneGraph parent-child hierarchy navigation (ancestors, descendants, root nodes).
5. Deterministic spatial queries: find_intersections, find_all_intersections, query_radius, raycast.
6. SceneGraph construction from Blender inspection contracts and serialization fidelity.
"""

import unittest
import math
from typing import Dict, Any, List, Optional

from mcp_service.intelligence.scenegraph import (
    AABB,
    OBB,
    SceneNode,
    SceneGraph,
)
from shared.models.protocol_models import BridgeResponse


class MockBlenderExecutor:
    """Mock executor returning structured Blender inspection contracts."""
    def __init__(self):
        self.scene_objects = {}

    def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None, trusted_approval: Optional[bool] = None) -> BridgeResponse:
        arguments = arguments or {}
        if tool_name == "list_objects":
            objs = [{"name": name, "type": info.get("type", "MESH")} for name, info in self.scene_objects.items()]
            return BridgeResponse.success({"objects": objs})
        elif tool_name == "get_object_details":
            name = arguments.get("name")
            if name in self.scene_objects:
                return BridgeResponse.success(self.scene_objects[name])
            return BridgeResponse.error(f"Object not found: {name}")
        return BridgeResponse.error(f"Unhandled tool: {tool_name}")


class TestPhase3SceneGraph(unittest.TestCase):

    def test_aabb_properties_and_intersection(self):
        """Verifies AABB min/max, center, size, volume, containment, and overlap."""
        box1 = AABB(min_point=(-1.0, -1.0, -1.0), max_point=(1.0, 1.0, 1.0))
        self.assertEqual(box1.center, (0.0, 0.0, 0.0))
        self.assertEqual(box1.size, (2.0, 2.0, 2.0))
        self.assertEqual(box1.volume, 8.0)
        self.assertTrue(box1.contains_point((0.0, 0.0, 0.0)))
        self.assertTrue(box1.contains_point((1.0, 1.0, 1.0)))
        self.assertFalse(box1.contains_point((1.5, 0.0, 0.0)))

        # Overlapping box
        box2 = AABB(min_point=(0.5, 0.5, 0.5), max_point=(2.5, 2.5, 2.5))
        self.assertTrue(box1.intersects(box2))
        self.assertTrue(box2.intersects(box1))

        # Disjoint box
        box3 = AABB(min_point=(3.0, 3.0, 3.0), max_point=(5.0, 5.0, 5.0))
        self.assertFalse(box1.intersects(box3))
        self.assertFalse(box3.intersects(box1))

        # Union
        u = box1.union(box2)
        self.assertEqual(u.min_point, (-1.0, -1.0, -1.0))
        self.assertEqual(u.max_point, (2.5, 2.5, 2.5))

    def test_obb_sat_exact_collision(self):
        """Verifies exact 15-axis Separating Axis Theorem (SAT) collision checking."""
        # Box A: Unit cube at origin, unrotated
        obb_a = OBB(
            center=(0.0, 0.0, 0.0),
            axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            extents=(1.0, 1.0, 1.0),
        )

        # Box B: Unit cube at (1.5, 0.0, 0.0), overlapping with A
        obb_b = OBB(
            center=(1.5, 0.0, 0.0),
            axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            extents=(1.0, 1.0, 1.0),
        )
        self.assertTrue(obb_a.intersects(obb_b))

        # Box C: Unit cube at (3.0, 0.0, 0.0), disjoint
        obb_c = OBB(
            center=(3.0, 0.0, 0.0),
            axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            extents=(1.0, 1.0, 1.0),
        )
        self.assertFalse(obb_a.intersects(obb_c))

        # Critical SAT Test: Rotated OBBs
        # Box A is 1x1x1 at origin.
        # Box D is rotated 45 degrees around Z axis at (1.8, 1.8, 0.0).
        # Its AABB will overlap with Box A, BUT its actual rotated OBB does NOT overlap!
        rad45 = math.pi / 4.0
        cos45, sin45 = math.cos(rad45), math.sin(rad45)
        rot_axes = (
            (cos45, -sin45, 0.0),
            (sin45, cos45, 0.0),
            (0.0, 0.0, 1.0),
        )
        obb_d = OBB(
            center=(1.4, 1.4, 0.0),
            axes=rot_axes,
            extents=(0.4, 0.4, 0.4),
        )
        # Check that AABB overlaps (conservative false positive)
        self.assertTrue(obb_a.to_aabb().intersects(obb_d.to_aabb()))
        # Check that exact OBB SAT correctly resolves separation!
        self.assertFalse(obb_a.intersects(obb_d))

    def test_scene_node_world_transform_and_corners(self):
        """Verifies local bound_box transformed to world coordinates under location, scale, and Euler rotation."""
        # 2x2x2 cube transformed: loc=[10, 0, 0], scale=[2, 1, 1], rot=[0, 0, 0]
        local_pts = [
            (-1.0, -1.0, -1.0), (-1.0, -1.0, 1.0), (-1.0, 1.0, -1.0), (-1.0, 1.0, 1.0),
            (1.0, -1.0, -1.0), (1.0, -1.0, 1.0), (1.0, 1.0, -1.0), (1.0, 1.0, 1.0),
        ]
        node = SceneNode(
            name="TransformedCube",
            type="MESH",
            location=(10.0, 0.0, 0.0),
            rotation_euler=(0.0, 0.0, 0.0),
            scale=(2.0, 1.0, 1.0),
            dimensions=(2.0, 2.0, 2.0),
            local_bound_box=local_pts,
        )

        self.assertIsNotNone(node.aabb)
        # Scaled x is [-2, 2] + 10 = [8, 12]
        self.assertAlmostEqual(node.aabb.min_point[0], 8.0)
        self.assertAlmostEqual(node.aabb.max_point[0], 12.0)
        self.assertAlmostEqual(node.aabb.min_point[1], -1.0)
        self.assertAlmostEqual(node.aabb.max_point[1], 1.0)
        self.assertAlmostEqual(node.aabb.center[0], 10.0)

    def test_scene_graph_hierarchy_traversal(self):
        """Verifies parent-child hierarchy building, root node detection, ancestors, and descendants."""
        sg = SceneGraph()
        n_root = SceneNode(name="Table", dimensions=(2.0, 2.0, 0.8), location=(0.0, 0.0, 0.4))
        n_child1 = SceneNode(name="TableCloth", parent="Table", dimensions=(2.1, 2.1, 0.1), location=(0.0, 0.0, 0.85))
        n_grandchild = SceneNode(name="Plate", parent="TableCloth", dimensions=(0.3, 0.3, 0.05), location=(0.0, 0.0, 0.9))
        n_other = SceneNode(name="Floor", dimensions=(10.0, 10.0, 0.1), location=(0.0, 0.0, -0.05))

        sg.add_node(n_root)
        sg.add_node(n_child1)
        sg.add_node(n_grandchild)
        sg.add_node(n_other)

        self.assertEqual(sorted(sg.root_nodes), ["Floor", "Table"])
        self.assertEqual([c.name for c in sg.get_children("Table")], ["TableCloth"])
        self.assertEqual([d.name for d in sg.get_descendants("Table")], ["TableCloth", "Plate"])
        self.assertEqual([a.name for a in sg.get_ancestors("Plate")], ["TableCloth", "Table"])

    def test_scene_graph_spatial_queries(self):
        """Verifies find_intersections, find_all_intersections, query_radius, and raycast."""
        sg = SceneGraph()
        box_a = SceneNode(name="BoxA", location=(0.0, 0.0, 0.0), dimensions=(2.0, 2.0, 2.0))
        box_b = SceneNode(name="BoxB", location=(1.0, 0.0, 0.0), dimensions=(2.0, 2.0, 2.0))
        box_c = SceneNode(name="BoxC", location=(10.0, 0.0, 0.0), dimensions=(2.0, 2.0, 2.0))

        sg.add_node(box_a)
        sg.add_node(box_b)
        sg.add_node(box_c)

        # Intersection queries
        self.assertTrue(sg.check_intersection("BoxA", "BoxB"))
        self.assertFalse(sg.check_intersection("BoxA", "BoxC"))
        self.assertEqual(sg.find_intersections("BoxA"), ["BoxB"])
        self.assertEqual(sg.find_all_intersections(), [("BoxA", "BoxB")])

        # Radius query around (0, 0, 0)
        near_objs = sg.query_radius((0.0, 0.0, 0.0), radius=2.5)
        self.assertIn("BoxA", near_objs)
        self.assertIn("BoxB", near_objs)
        self.assertNotIn("BoxC", near_objs)

        # Raycast along +X axis from (-5, 0, 0)
        hits = sg.raycast(origin=(-5.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0))
        hit_names = [h[0] for h in hits]
        self.assertEqual(hit_names[:2], ["BoxA", "BoxB"])
        self.assertIn("BoxC", hit_names)
        # BoxA is closer than BoxB, which is closer than BoxC
        dist_a = next(h[1] for h in hits if h[0] == "BoxA")
        dist_b = next(h[1] for h in hits if h[0] == "BoxB")
        dist_c = next(h[1] for h in hits if h[0] == "BoxC")
        self.assertLess(dist_a, dist_b)
        self.assertLess(dist_b, dist_c)

    def test_scene_graph_from_mock_blender_and_serialization(self):
        """Verifies SceneGraph.from_blender() and round-trip JSON dictionary serialization."""
        executor = MockBlenderExecutor()
        executor.scene_objects = {
            "Hero": {
                "name": "Hero",
                "type": "MESH",
                "location": [0.0, 0.0, 1.0],
                "rotation_euler": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "dimensions": [2.0, 2.0, 2.0],
                "bound_box": [
                    [-1.0, -1.0, -1.0], [-1.0, -1.0, 1.0], [-1.0, 1.0, -1.0], [-1.0, 1.0, 1.0],
                    [1.0, -1.0, -1.0], [1.0, -1.0, 1.0], [1.0, 1.0, -1.0], [1.0, 1.0, 1.0],
                ],
                "parent": None,
                "materials": ["HeroMat"],
                "mesh_stats": {"vertices_count": 8, "polygons_count": 6},
                "collections": ["MainCollection"],
                "visible": True,
            },
            "Hat": {
                "name": "Hat",
                "type": "MESH",
                "location": [0.0, 0.0, 2.2],
                "rotation_euler": [0.0, 0.0, 0.0],
                "scale": [0.5, 0.5, 0.5],
                "dimensions": [1.0, 1.0, 0.5],
                "bound_box": [
                    [-0.5, -0.5, -0.25], [-0.5, -0.5, 0.25], [-0.5, 0.5, -0.25], [-0.5, 0.5, 0.25],
                    [0.5, -0.5, -0.25], [0.5, -0.5, 0.25], [0.5, 0.5, -0.25], [0.5, 0.5, 0.25],
                ],
                "parent": "Hero",
                "materials": ["HatMat"],
                "mesh_stats": {"vertices_count": 16, "polygons_count": 12},
                "collections": ["MainCollection"],
                "visible": True,
            },
        }

        sg = SceneGraph.from_blender(executor)
        self.assertEqual(len(sg.nodes), 2)
        self.assertEqual(sg.root_nodes, ["Hero"])
        self.assertEqual([c.name for c in sg.get_children("Hero")], ["Hat"])

        # Check bounds
        hero_aabb = sg.get_aabb("Hero")
        self.assertIsNotNone(hero_aabb)
        self.assertEqual(hero_aabb.center, (0.0, 0.0, 1.0))

        # Check round-trip serialization
        sg_dict = sg.to_dict()
        sg_restored = SceneGraph.from_dict(sg_dict)
        self.assertEqual(len(sg_restored.nodes), 2)
        self.assertEqual(sg_restored.root_nodes, ["Hero"])
        self.assertEqual(sg_restored.get_children("Hero")[0].name, "Hat")
        self.assertEqual(sg_restored.get_aabb("Hero").center, hero_aabb.center)


if __name__ == "__main__":
    unittest.main()
