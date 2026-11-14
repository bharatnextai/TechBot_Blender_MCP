"""
Spatial Relationship Engine for Universal MCP Scene Intelligence (Phase 3.4).

Provides deterministic, tolerance-aware spatial relationship detection between SceneNodes:
- ON_TOP_OF(A, B) / UNDER(A, B)
- INSIDE(A, B) / CONTAINS(A, B)
- FACING(A, B)
- LEFT_OF(A, B) / RIGHT_OF(A, B)
- IN_FRONT_OF(A, B) / BEHIND(A, B)
- NEAR(A, B)

Reuses verified AABB, OBB, and SceneGraph representations from Phase 3.3.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union, Set
import math
import logging

from .scenegraph import (
    AABB,
    OBB,
    SceneNode,
    Vec3,
    _vec_add,
    _vec_sub,
    _vec_scale,
    _vec_dot,
    _vec_cross,
    _vec_length,
    _vec_normalize,
    _mat_vec_mul,
    _euler_to_rotation_matrix,
)

logger = logging.getLogger("UniversalMCP_SpatialRelations")


class SpatialRelationType(str, Enum):
    """Enumeration of supported spatial relationship predicates."""
    ON_TOP_OF = "ON_TOP_OF"
    UNDER = "UNDER"
    INSIDE = "INSIDE"
    CONTAINS = "CONTAINS"
    FACING = "FACING"
    LEFT_OF = "LEFT_OF"
    RIGHT_OF = "RIGHT_OF"
    IN_FRONT_OF = "IN_FRONT_OF"
    BEHIND = "BEHIND"
    NEAR = "NEAR"


@dataclass
class SpatialRelationResult:
    """
    Structured outcome of a spatial relationship evaluation between two scene entities.
    """
    relation: SpatialRelationType
    source: str
    target: str
    holds: bool
    confidence: float = 1.0
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relation": self.relation.value,
            "source": self.source,
            "target": self.target,
            "holds": self.holds,
            "confidence": round(self.confidence, 4),
            "metrics": {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in self.metrics.items()
            },
        }


def _aabb_surface_distance(a: AABB, b: AABB) -> float:
    """
    Calculates exact Euclidean surface-to-surface distance between two AABBs.
    Returns 0.0 if the boxes intersect or touch.
    """
    d0 = max(0.0, max(a.min_point[0], b.min_point[0]) - min(a.max_point[0], b.max_point[0]))
    d1 = max(0.0, max(a.min_point[1], b.min_point[1]) - min(a.max_point[1], b.max_point[1]))
    d2 = max(0.0, max(a.min_point[2], b.min_point[2]) - min(a.max_point[2], b.max_point[2]))
    return math.sqrt(d0 * d0 + d1 * d1 + d2 * d2)


def _xy_footprint_overlap(a: AABB, b: AABB) -> Tuple[float, float, float]:
    """
    Computes horizontal (XY plane) bounding box overlap area and coverage ratios.
    Returns (overlap_area, ratio_a, ratio_b) where ratio is overlap / footprint_area.
    """
    ox = max(0.0, min(a.max_point[0], b.max_point[0]) - max(a.min_point[0], b.min_point[0]))
    oy = max(0.0, min(a.max_point[1], b.max_point[1]) - max(a.min_point[1], b.min_point[1]))
    overlap_area = ox * oy

    w_a = max(1e-6, a.max_point[0] - a.min_point[0])
    h_a = max(1e-6, a.max_point[1] - a.min_point[1])
    area_a = w_a * h_a

    w_b = max(1e-6, b.max_point[0] - b.min_point[0])
    h_b = max(1e-6, b.max_point[1] - b.min_point[1])
    area_b = w_b * h_b

    ratio_a = overlap_area / area_a
    ratio_b = overlap_area / area_b
    return overlap_area, ratio_a, ratio_b


class SpatialRelationshipEngine:
    """
    Deterministic, tolerance-aware spatial relationship solver.
    Evaluates topological, directional, containment, and proximity predicates
    between SceneNodes in world space.
    """

    def eval_on_top_of(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        vertical_tolerance: float = 0.20,
        contact_tolerance: float = 0.10,
        min_xy_overlap: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is on top of node_b.
        Requires:
        1. Vertical contact: node_a bottom is near node_b top:
           -contact_tolerance <= (node_a.z_min - node_b.z_max) <= vertical_tolerance
        2. Horizontal footprint overlap in XY plane: overlap_ratio >= min_xy_overlap.
        """
        if node_a.aabb is None or node_b.aabb is None:
            return SpatialRelationResult(
                relation=SpatialRelationType.ON_TOP_OF,
                source=node_a.name,
                target=node_b.name,
                holds=False,
                confidence=0.0,
                metrics={"error": "Missing AABB bounds"},
            )

        z_a_bottom = node_a.aabb.min_point[2]
        z_b_top = node_b.aabb.max_point[2]
        delta_z = z_a_bottom - z_b_top

        vertical_holds = (-contact_tolerance <= delta_z <= vertical_tolerance)
        overlap_area, ratio_a, ratio_b = _xy_footprint_overlap(node_a.aabb, node_b.aabb)
        xy_holds = (ratio_a >= min_xy_overlap or ratio_b >= min_xy_overlap)

        holds = bool(vertical_holds and xy_holds)

        # Confidence based on vertical closeness and footprint coverage
        if holds:
            v_penalty = abs(delta_z) / max(vertical_tolerance, 1e-4) * 0.4
            xy_bonus = min(1.0, ratio_a) * 0.6
            confidence = max(0.1, min(1.0, 1.0 - v_penalty + (xy_bonus - 0.3)))
        else:
            confidence = 0.0

        return SpatialRelationResult(
            relation=SpatialRelationType.ON_TOP_OF,
            source=node_a.name,
            target=node_b.name,
            holds=holds,
            confidence=confidence,
            metrics={
                "vertical_gap": delta_z,
                "vertical_holds": vertical_holds,
                "overlap_area": overlap_area,
                "overlap_ratio_source": ratio_a,
                "overlap_ratio_target": ratio_b,
                "xy_holds": xy_holds,
            },
        )

    def eval_under(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        vertical_tolerance: float = 0.20,
        contact_tolerance: float = 0.10,
        min_xy_overlap: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is under node_b (reciprocal of node_b on top of node_a).
        """
        if node_a.aabb is None or node_b.aabb is None:
            return SpatialRelationResult(
                relation=SpatialRelationType.UNDER,
                source=node_a.name,
                target=node_b.name,
                holds=False,
                confidence=0.0,
                metrics={"error": "Missing AABB bounds"},
            )

        z_a_top = node_a.aabb.max_point[2]
        z_b_bottom = node_b.aabb.min_point[2]
        delta_z = z_b_bottom - z_a_top

        vertical_holds = (-contact_tolerance <= delta_z <= vertical_tolerance)
        overlap_area, ratio_a, ratio_b = _xy_footprint_overlap(node_a.aabb, node_b.aabb)
        xy_holds = (ratio_a >= min_xy_overlap or ratio_b >= min_xy_overlap)

        holds = bool(vertical_holds and xy_holds)

        confidence = 0.0
        if holds:
            v_penalty = abs(delta_z) / max(vertical_tolerance, 1e-4) * 0.4
            confidence = max(0.1, min(1.0, 1.0 - v_penalty))

        return SpatialRelationResult(
            relation=SpatialRelationType.UNDER,
            source=node_a.name,
            target=node_b.name,
            holds=holds,
            confidence=confidence,
            metrics={
                "vertical_gap": delta_z,
                "vertical_holds": vertical_holds,
                "overlap_area": overlap_area,
                "overlap_ratio_source": ratio_a,
                "overlap_ratio_target": ratio_b,
                "xy_holds": xy_holds,
            },
        )

    def eval_inside(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        tolerance: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is geometrically inside node_b.
        Evaluates world-space corner containment against node_b's OBB slabs (or AABB).
        """
        if node_a.aabb is None or node_b.aabb is None:
            return SpatialRelationResult(
                relation=SpatialRelationType.INSIDE,
                source=node_a.name,
                target=node_b.name,
                holds=False,
                confidence=0.0,
                metrics={"error": "Missing bounding volumes"},
            )

        # 1. AABB quick containment check
        a_min, a_max = node_a.aabb.min_point, node_a.aabb.max_point
        b_min, b_max = node_b.aabb.min_point, node_b.aabb.max_point

        aabb_inside = (
            a_min[0] >= b_min[0] - tolerance and a_max[0] <= b_max[0] + tolerance and
            a_min[1] >= b_min[1] - tolerance and a_max[1] <= b_max[1] + tolerance and
            a_min[2] >= b_min[2] - tolerance and a_max[2] <= b_max[2] + tolerance
        )

        # 2. Detailed OBB corner check if OBB available on container
        corners_inside = 0
        total_corners = len(node_a.world_corners) if node_a.world_corners else 8
        tested_corners = node_a.world_corners if node_a.world_corners else node_a.aabb.corners

        if node_b.obb and tested_corners:
            c = node_b.obb.center
            axes = node_b.obb.axes
            extents = node_b.obb.extents
            for pt in tested_corners:
                v = _vec_sub(pt, c)
                in_slabs = True
                for i in range(3):
                    proj = abs(_vec_dot(v, axes[i]))
                    if proj > extents[i] + tolerance:
                        in_slabs = False
                        break
                if in_slabs:
                    corners_inside += 1
        elif aabb_inside:
            corners_inside = total_corners

        containment_ratio = corners_inside / float(max(total_corners, 1))
        holds = (corners_inside == total_corners) or aabb_inside

        return SpatialRelationResult(
            relation=SpatialRelationType.INSIDE,
            source=node_a.name,
            target=node_b.name,
            holds=bool(holds),
            confidence=containment_ratio if holds else 0.0,
            metrics={
                "corners_inside": corners_inside,
                "total_corners": total_corners,
                "containment_ratio": containment_ratio,
                "aabb_inside": aabb_inside,
            },
        )

    def eval_contains(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        tolerance: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a contains node_b (reciprocal of node_b inside node_a).
        """
        res = self.eval_inside(node_b, node_a, tolerance=tolerance)
        return SpatialRelationResult(
            relation=SpatialRelationType.CONTAINS,
            source=node_a.name,
            target=node_b.name,
            holds=res.holds,
            confidence=res.confidence,
            metrics=res.metrics,
        )

    def eval_facing(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        forward_axis: Vec3 = (0.0, 1.0, 0.0),
        angle_tolerance_deg: float = 45.0,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is oriented towards node_b.
        Computes the angle between node_a's world-space forward vector and the displacement vector to node_b.
        """
        pos_a = node_a.obb.center if node_a.obb else node_a.location
        pos_b = node_b.obb.center if node_b.obb else node_b.location

        displacement = _vec_sub(pos_b, pos_a)
        distance = _vec_length(displacement)

        if distance < 1e-5:
            return SpatialRelationResult(
                relation=SpatialRelationType.FACING,
                source=node_a.name,
                target=node_b.name,
                holds=False,
                confidence=0.0,
                metrics={"distance": 0.0, "reason": "Coincident centers"},
            )

        dir_to_target = _vec_normalize(displacement)

        # Compute world-space forward vector for node_a
        if node_a.obb and len(node_a.obb.axes) == 3:
            u0, u1, u2 = node_a.obb.axes
            f_world = (
                forward_axis[0] * u0[0] + forward_axis[1] * u1[0] + forward_axis[2] * u2[0],
                forward_axis[0] * u0[1] + forward_axis[1] * u1[1] + forward_axis[2] * u2[1],
                forward_axis[0] * u0[2] + forward_axis[1] * u1[2] + forward_axis[2] * u2[2],
            )
        else:
            rot_mat = _euler_to_rotation_matrix(node_a.rotation_euler)
            f_world = _mat_vec_mul(rot_mat, forward_axis)

        f_world = _vec_normalize(f_world)
        cos_theta = _vec_dot(f_world, dir_to_target)
        cos_clamped = max(-1.0, min(1.0, cos_theta))
        angle_rad = math.acos(cos_clamped)
        angle_deg = math.degrees(angle_rad)

        holds = (angle_deg <= angle_tolerance_deg)

        # Confidence drops smoothly from 1.0 (exact collinear 0 deg) to 0.0 at threshold
        if holds:
            confidence = max(0.0, min(1.0, (angle_tolerance_deg - angle_deg) / max(angle_tolerance_deg, 1e-4)))
        else:
            confidence = 0.0

        return SpatialRelationResult(
            relation=SpatialRelationType.FACING,
            source=node_a.name,
            target=node_b.name,
            holds=bool(holds),
            confidence=confidence,
            metrics={
                "angle_deg": angle_deg,
                "angle_tolerance_deg": angle_tolerance_deg,
                "cos_theta": cos_clamped,
                "distance": distance,
                "forward_vector_world": f_world,
                "direction_to_target": dir_to_target,
            },
        )

    def eval_left_of(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        reference_frame: str = "local",
        tolerance: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is to the left of node_b.
        - "local": Evaluates along node_b's local Right vector (OBB axis 0).
                   node_a is LEFT of node_b if dot(pos_a - pos_b, right_b) < -tolerance.
        - "world": Evaluates along global X axis (pos_a.x - pos_b.x < -tolerance).
        """
        pos_a = node_a.obb.center if node_a.obb else node_a.location
        pos_b = node_b.obb.center if node_b.obb else node_b.location
        disp = _vec_sub(pos_a, pos_b)

        if reference_frame == "local" and node_b.obb:
            right_axis = node_b.obb.axes[0]
            lateral_offset = _vec_dot(disp, right_axis)
        else:
            lateral_offset = disp[0]

        holds = (lateral_offset < -tolerance)

        return SpatialRelationResult(
            relation=SpatialRelationType.LEFT_OF,
            source=node_a.name,
            target=node_b.name,
            holds=bool(holds),
            confidence=1.0 if holds else 0.0,
            metrics={
                "lateral_offset": lateral_offset,
                "tolerance": tolerance,
                "reference_frame": reference_frame,
            },
        )

    def eval_right_of(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        reference_frame: str = "local",
        tolerance: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is to the right of node_b.
        - "local": Evaluates along node_b's local Right vector (OBB axis 0).
                   node_a is RIGHT of node_b if dot(pos_a - pos_b, right_b) > tolerance.
        - "world": Evaluates along global X axis (pos_a.x - pos_b.x > tolerance).
        """
        pos_a = node_a.obb.center if node_a.obb else node_a.location
        pos_b = node_b.obb.center if node_b.obb else node_b.location
        disp = _vec_sub(pos_a, pos_b)

        if reference_frame == "local" and node_b.obb:
            right_axis = node_b.obb.axes[0]
            lateral_offset = _vec_dot(disp, right_axis)
        else:
            lateral_offset = disp[0]

        holds = (lateral_offset > tolerance)

        return SpatialRelationResult(
            relation=SpatialRelationType.RIGHT_OF,
            source=node_a.name,
            target=node_b.name,
            holds=bool(holds),
            confidence=1.0 if holds else 0.0,
            metrics={
                "lateral_offset": lateral_offset,
                "tolerance": tolerance,
                "reference_frame": reference_frame,
            },
        )

    def eval_in_front_of(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        reference_frame: str = "local",
        forward_axis: Vec3 = (0.0, 1.0, 0.0),
        tolerance: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is in front of node_b.
        - "local": Evaluates along node_b's local Forward vector (OBB axis 1).
                   node_a is IN_FRONT_OF node_b if dot(pos_a - pos_b, fwd_b) > tolerance.
        - "world": Evaluates along global Y axis (pos_a.y - pos_b.y > tolerance).
        """
        pos_a = node_a.obb.center if node_a.obb else node_a.location
        pos_b = node_b.obb.center if node_b.obb else node_b.location
        disp = _vec_sub(pos_a, pos_b)

        if reference_frame == "local" and node_b.obb:
            u0, u1, u2 = node_b.obb.axes
            f_world = (
                forward_axis[0] * u0[0] + forward_axis[1] * u1[0] + forward_axis[2] * u2[0],
                forward_axis[0] * u0[1] + forward_axis[1] * u1[1] + forward_axis[2] * u2[1],
                forward_axis[0] * u0[2] + forward_axis[1] * u1[2] + forward_axis[2] * u2[2],
            )
            longitudinal_offset = _vec_dot(disp, _vec_normalize(f_world))
        else:
            longitudinal_offset = disp[1]

        holds = (longitudinal_offset > tolerance)

        return SpatialRelationResult(
            relation=SpatialRelationType.IN_FRONT_OF,
            source=node_a.name,
            target=node_b.name,
            holds=bool(holds),
            confidence=1.0 if holds else 0.0,
            metrics={
                "longitudinal_offset": longitudinal_offset,
                "tolerance": tolerance,
                "reference_frame": reference_frame,
            },
        )

    def eval_behind(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        reference_frame: str = "local",
        forward_axis: Vec3 = (0.0, 1.0, 0.0),
        tolerance: float = 0.05,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is behind node_b.
        - "local": Evaluates along node_b's local Forward vector (OBB axis 1).
                   node_a is BEHIND node_b if dot(pos_a - pos_b, fwd_b) < -tolerance.
        - "world": Evaluates along global Y axis (pos_a.y - pos_b.y < -tolerance).
        """
        pos_a = node_a.obb.center if node_a.obb else node_a.location
        pos_b = node_b.obb.center if node_b.obb else node_b.location
        disp = _vec_sub(pos_a, pos_b)

        if reference_frame == "local" and node_b.obb:
            u0, u1, u2 = node_b.obb.axes
            f_world = (
                forward_axis[0] * u0[0] + forward_axis[1] * u1[0] + forward_axis[2] * u2[0],
                forward_axis[0] * u0[1] + forward_axis[1] * u1[1] + forward_axis[2] * u2[1],
                forward_axis[0] * u0[2] + forward_axis[1] * u1[2] + forward_axis[2] * u2[2],
            )
            longitudinal_offset = _vec_dot(disp, _vec_normalize(f_world))
        else:
            longitudinal_offset = disp[1]

        holds = (longitudinal_offset < -tolerance)

        return SpatialRelationResult(
            relation=SpatialRelationType.BEHIND,
            source=node_a.name,
            target=node_b.name,
            holds=bool(holds),
            confidence=1.0 if holds else 0.0,
            metrics={
                "longitudinal_offset": longitudinal_offset,
                "tolerance": tolerance,
                "reference_frame": reference_frame,
            },
        )

    def eval_near(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        max_distance: float = 1.5,
        use_surface_distance: bool = True,
    ) -> SpatialRelationResult:
        """
        Determines whether node_a is near node_b within max_distance.
        Uses exact AABB surface-to-surface distance if available and requested;
        otherwise evaluates Euclidean distance between centroids.
        """
        if use_surface_distance and node_a.aabb and node_b.aabb:
            distance = _aabb_surface_distance(node_a.aabb, node_b.aabb)
        else:
            pos_a = node_a.obb.center if node_a.obb else node_a.location
            pos_b = node_b.obb.center if node_b.obb else node_b.location
            distance = _vec_length(_vec_sub(pos_a, pos_b))

        holds = (distance <= max_distance)

        confidence = max(0.0, min(1.0, 1.0 - (distance / max(max_distance, 1e-4)))) if holds else 0.0

        return SpatialRelationResult(
            relation=SpatialRelationType.NEAR,
            source=node_a.name,
            target=node_b.name,
            holds=bool(holds),
            confidence=confidence,
            metrics={
                "distance": distance,
                "max_distance": max_distance,
                "use_surface_distance": use_surface_distance,
            },
        )

    def check_relation(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        relation: Union[str, SpatialRelationType],
        **kwargs,
    ) -> SpatialRelationResult:
        """
        Dispatches and evaluates a single specified relation between node_a and node_b.
        """
        if isinstance(relation, str):
            rel_type = SpatialRelationType(relation.upper())
        else:
            rel_type = relation

        dispatch = {
            SpatialRelationType.ON_TOP_OF: self.eval_on_top_of,
            SpatialRelationType.UNDER: self.eval_under,
            SpatialRelationType.INSIDE: self.eval_inside,
            SpatialRelationType.CONTAINS: self.eval_contains,
            SpatialRelationType.FACING: self.eval_facing,
            SpatialRelationType.LEFT_OF: self.eval_left_of,
            SpatialRelationType.RIGHT_OF: self.eval_right_of,
            SpatialRelationType.IN_FRONT_OF: self.eval_in_front_of,
            SpatialRelationType.BEHIND: self.eval_behind,
            SpatialRelationType.NEAR: self.eval_near,
        }

        func = dispatch.get(rel_type)
        if not func:
            raise ValueError(f"Unsupported spatial relation: {relation}")

        return func(node_a, node_b, **kwargs)

    def find_all_relations(
        self,
        node_a: SceneNode,
        node_b: SceneNode,
        only_holding: bool = True,
        **kwargs,
    ) -> List[SpatialRelationResult]:
        """
        Evaluates all supported spatial relationships from node_a to node_b.
        """
        results: List[SpatialRelationResult] = []
        for rel_type in SpatialRelationType:
            try:
                res = self.check_relation(node_a, node_b, rel_type, **kwargs)
                if not only_holding or res.holds:
                    results.append(res)
            except Exception as e:
                logger.debug(f"Failed evaluating {rel_type} between {node_a.name} and {node_b.name}: {e}")
        return results

