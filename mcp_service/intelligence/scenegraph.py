"""
SceneGraph Spatial Hierarchy & Bounding Volume Engine for Universal MCP.
Provides:
1. Axis-Aligned Bounding Box (AABB) model with min/max, center, size, volume, and intersection tests.
2. Oriented Bounding Box (OBB) model with full 15-axis Separating Axis Theorem (SAT) collision detection.
3. SceneNode hierarchical representation tracking parenting, transforms, materials, and bounding volumes.
4. SceneGraph spatial query engine supporting deterministic intersection tests, radius queries, raycasts,
   and Blender live readback integration.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple, Set, Union
import math
import copy
import logging

logger = logging.getLogger("UniversalMCP_SceneGraph")

Vec3 = Tuple[float, float, float]


def _vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vec_scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)


def _vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vec_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vec_length(v: Vec3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _vec_normalize(v: Vec3) -> Vec3:
    l = _vec_length(v)
    if l < 1e-9:
        return (0.0, 0.0, 0.0)
    return (v[0] / l, v[1] / l, v[2] / l)


def _euler_to_rotation_matrix(rot_euler: Vec3) -> Tuple[Vec3, Vec3, Vec3]:
    """
    Computes 3x3 rotation matrix for standard Blender Euler 'XYZ' intrinsic rotation.
    R = Rz * Ry * Rx
    """
    rx, ry, rz = rot_euler
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    # Row vectors or column vectors: here we define standard matrix acting on column vectors
    # [ R00 R01 R02 ]
    # [ R10 R11 R12 ]
    # [ R20 R21 R22 ]
    r00 = cy * cz
    r01 = sx * sy * cz - cx * sz
    r02 = cx * sy * cz + sx * sz

    r10 = cy * sz
    r11 = sx * sy * sz + cx * cz
    r12 = cx * sy * sz - sx * cz

    r20 = -sy
    r21 = sx * cy
    r22 = cx * cy

    return (
        (r00, r01, r02),
        (r10, r11, r12),
        (r20, r21, r22),
    )


def _mat_vec_mul(mat: Tuple[Vec3, Vec3, Vec3], v: Vec3) -> Vec3:
    return (
        mat[0][0] * v[0] + mat[0][1] * v[1] + mat[0][2] * v[2],
        mat[1][0] * v[0] + mat[1][1] * v[1] + mat[1][2] * v[2],
        mat[2][0] * v[0] + mat[2][1] * v[1] + mat[2][2] * v[2],
    )


@dataclass
class AABB:
    """
    Axis-Aligned Bounding Box defined by minimum and maximum extents in world space.
    """
    min_point: Vec3 = (0.0, 0.0, 0.0)
    max_point: Vec3 = (0.0, 0.0, 0.0)

    @property
    def center(self) -> Vec3:
        return (
            (self.min_point[0] + self.max_point[0]) * 0.5,
            (self.min_point[1] + self.max_point[1]) * 0.5,
            (self.min_point[2] + self.max_point[2]) * 0.5,
        )

    @property
    def size(self) -> Vec3:
        return (
            max(0.0, self.max_point[0] - self.min_point[0]),
            max(0.0, self.max_point[1] - self.min_point[1]),
            max(0.0, self.max_point[2] - self.min_point[2]),
        )

    @property
    def extents(self) -> Vec3:
        """Half-lengths along each axis."""
        s = self.size
        return (s[0] * 0.5, s[1] * 0.5, s[2] * 0.5)

    @property
    def volume(self) -> float:
        s = self.size
        return s[0] * s[1] * s[2]

    def contains_point(self, point: Vec3, tolerance: float = 1e-4) -> bool:
        return all(
            (self.min_point[i] - tolerance) <= point[i] <= (self.max_point[i] + tolerance)
            for i in range(3)
        )

    def intersects(self, other: "AABB", tolerance: float = 1e-4) -> bool:
        """
        Determines whether this AABB intersects or overlaps with another AABB.
        """
        for i in range(3):
            if (self.min_point[i] - tolerance) > other.max_point[i]:
                return False
            if (self.max_point[i] + tolerance) < other.min_point[i]:
                return False
        return True

    def union(self, other: "AABB") -> "AABB":
        """Returns minimal enclosing AABB covering both this and other."""
        return AABB(
            min_point=(
                min(self.min_point[0], other.min_point[0]),
                min(self.min_point[1], other.min_point[1]),
                min(self.min_point[2], other.min_point[2]),
            ),
            max_point=(
                max(self.max_point[0], other.max_point[0]),
                max(self.max_point[1], other.max_point[1]),
                max(self.max_point[2], other.max_point[2]),
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_point": [round(x, 4) for x in self.min_point],
            "max_point": [round(x, 4) for x in self.max_point],
            "center": [round(x, 4) for x in self.center],
            "size": [round(x, 4) for x in self.size],
            "volume": round(self.volume, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AABB":
        return cls(
            min_point=tuple(data.get("min_point", [0, 0, 0])),
            max_point=tuple(data.get("max_point", [0, 0, 0])),
        )

    @classmethod
    def from_points(cls, points: List[Vec3]) -> "AABB":
        if not points:
            return cls((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        return cls(
            min_point=(min(xs), min(ys), min(zs)),
            max_point=(max(xs), max(ys), max(zs)),
        )


@dataclass
class OBB:
    """
    Oriented Bounding Box defined by center, 3 orthonormal orientation axes, and half-extents.
    Supports deterministic 15-axis Separating Axis Theorem (SAT) collision detection.
    """
    center: Vec3 = (0.0, 0.0, 0.0)
    axes: Tuple[Vec3, Vec3, Vec3] = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    extents: Vec3 = (0.5, 0.5, 0.5)
    corners: List[Vec3] = field(default_factory=list)

    def __post_init__(self):
        if not self.corners:
            self.corners = self._compute_corners()

    def _compute_corners(self) -> List[Vec3]:
        """Generates 8 world-space corners from center, axes, and extents."""
        c = self.center
        u0, u1, u2 = self.axes
        e0, e1, e2 = self.extents
        corners = []
        for s0 in (-1.0, 1.0):
            for s1 in (-1.0, 1.0):
                for s2 in (-1.0, 1.0):
                    p = (
                        c[0] + s0 * e0 * u0[0] + s1 * e1 * u1[0] + s2 * e2 * u2[0],
                        c[1] + s0 * e0 * u0[1] + s1 * e1 * u1[1] + s2 * e2 * u2[1],
                        c[2] + s0 * e0 * u0[2] + s1 * e1 * u1[2] + s2 * e2 * u2[2],
                    )
                    corners.append(p)
        return corners

    @property
    def volume(self) -> float:
        return 8.0 * self.extents[0] * self.extents[1] * self.extents[2]

    def to_aabb(self) -> AABB:
        """Computes minimal enclosing AABB for this OBB."""
        return AABB.from_points(self.corners)

    def intersects(self, other: "OBB", tolerance: float = 1e-4) -> bool:
        """
        Exact deterministic 3D collision check using the 15-axis Separating Axis Theorem (SAT).
        Tests:
        - 3 face normal axes of box A (self.axes)
        - 3 face normal axes of box B (other.axes)
        - 9 cross products of axes (self.axes[i] x other.axes[j])
        Returns True if the OBBs overlap on all 15 axes; False if any separating axis exists.
        """
        # Vector between centers in world space
        t_world = _vec_sub(other.center, self.center)

        # Express t in self's coordinate frame
        t = (
            _vec_dot(t_world, self.axes[0]),
            _vec_dot(t_world, self.axes[1]),
            _vec_dot(t_world, self.axes[2]),
        )

        # Rotation matrix R[i][j] = dot(A_i, B_j)
        r = [
            [_vec_dot(self.axes[i], other.axes[j]) for j in range(3)]
            for i in range(3)
        ]

        # Absolute rotation matrix with small epsilon to handle parallel/degenerate axes
        q = [[abs(r[i][j]) + 1e-7 for j in range(3)] for i in range(3)]

        a = self.extents
        b = other.extents

        # 1. Test Box A's 3 basis axes: A_0, A_1, A_2
        for i in range(3):
            ra = a[i]
            rb = b[0] * q[i][0] + b[1] * q[i][1] + b[2] * q[i][2]
            if abs(t[i]) > (ra + rb + tolerance):
                return False

        # 2. Test Box B's 3 basis axes: B_0, B_1, B_2
        for j in range(3):
            ra = a[0] * q[0][j] + a[1] * q[1][j] + a[2] * q[2][j]
            rb = b[j]
            t_proj = abs(t[0] * r[0][j] + t[1] * r[1][j] + t[2] * r[2][j])
            if t_proj > (ra + rb + tolerance):
                return False

        # 3. Test 9 cross-product axes: A_i x B_j
        # Axis A_0 x B_0
        ra = a[1] * q[2][0] + a[2] * q[1][0]
        rb = b[1] * q[0][2] + b[2] * q[0][1]
        if abs(t[2] * r[1][0] - t[1] * r[2][0]) > (ra + rb + tolerance):
            return False

        # Axis A_0 x B_1
        ra = a[1] * q[2][1] + a[2] * q[1][1]
        rb = b[0] * q[0][2] + b[2] * q[0][0]
        if abs(t[2] * r[1][1] - t[1] * r[2][1]) > (ra + rb + tolerance):
            return False

        # Axis A_0 x B_2
        ra = a[1] * q[2][2] + a[2] * q[1][2]
        rb = b[0] * q[0][1] + b[1] * q[0][0]
        if abs(t[2] * r[1][2] - t[1] * r[2][2]) > (ra + rb + tolerance):
            return False

        # Axis A_1 x B_0
        ra = a[0] * q[2][0] + a[2] * q[0][0]
        rb = b[1] * q[1][2] + b[2] * q[1][1]
        if abs(t[0] * r[2][0] - t[2] * r[0][0]) > (ra + rb + tolerance):
            return False

        # Axis A_1 x B_1
        ra = a[0] * q[2][1] + a[2] * q[0][1]
        rb = b[0] * q[1][2] + b[2] * q[1][0]
        if abs(t[0] * r[2][1] - t[2] * r[0][1]) > (ra + rb + tolerance):
            return False

        # Axis A_1 x B_2
        ra = a[0] * q[2][2] + a[2] * q[0][2]
        rb = b[0] * q[1][1] + b[1] * q[1][0]
        if abs(t[0] * r[2][2] - t[2] * r[0][2]) > (ra + rb + tolerance):
            return False

        # Axis A_2 x B_0
        ra = a[0] * q[1][0] + a[1] * q[0][0]
        rb = b[1] * q[2][2] + b[2] * q[2][1]
        if abs(t[1] * r[0][0] - t[0] * r[1][0]) > (ra + rb + tolerance):
            return False

        # Axis A_2 x B_1
        ra = a[0] * q[1][1] + a[1] * q[0][1]
        rb = b[0] * q[2][2] + b[2] * q[2][0]
        if abs(t[1] * r[0][1] - t[0] * r[1][1]) > (ra + rb + tolerance):
            return False

        # Axis A_2 x B_2
        ra = a[0] * q[1][2] + a[1] * q[0][2]
        rb = b[0] * q[2][1] + b[1] * q[2][0]
        if abs(t[1] * r[0][2] - t[0] * r[1][2]) > (ra + rb + tolerance):
            return False

        # No separating axis found; boxes intersect
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center": [round(x, 4) for x in self.center],
            "axes": [[round(v, 4) for v in ax] for ax in self.axes],
            "extents": [round(x, 4) for x in self.extents],
            "corners": [[round(x, 4) for x in pt] for pt in self.corners],
            "volume": round(self.volume, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OBB":
        return cls(
            center=tuple(data.get("center", [0, 0, 0])),
            axes=tuple(tuple(ax) for ax in data.get("axes", [[1, 0, 0], [0, 1, 0], [0, 0, 1]])),
            extents=tuple(data.get("extents", [0.5, 0.5, 0.5])),
            corners=[tuple(c) for c in data.get("corners", [])],
        )


@dataclass
class SceneNode:
    """
    Spatial hierarchy node representing an individual Blender scene entity.
    """
    name: str
    type: str = "MESH"
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    location: Vec3 = (0.0, 0.0, 0.0)
    rotation_euler: Vec3 = (0.0, 0.0, 0.0)
    scale: Vec3 = (1.0, 1.0, 1.0)
    dimensions: Vec3 = (1.0, 1.0, 1.0)
    local_bound_box: List[Vec3] = field(default_factory=list)
    world_corners: List[Vec3] = field(default_factory=list)
    aabb: Optional[AABB] = None
    obb: Optional[OBB] = None
    mesh_stats: Optional[Dict[str, Any]] = None
    materials: List[str] = field(default_factory=list)
    modifiers: List[Dict[str, Any]] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)
    visible: bool = True

    def __post_init__(self):
        if not self.world_corners or self.aabb is None or self.obb is None:
            self._compute_world_bounds()

    def _compute_world_bounds(self) -> None:
        """
        Transforms local bound_box coordinates into world-space corners,
        constructing exact AABB and OBB models.
        """
        rot_mat = _euler_to_rotation_matrix(self.rotation_euler)

        # Orthonormal orientation axes
        u0 = _mat_vec_mul(rot_mat, (1.0, 0.0, 0.0))
        u1 = _mat_vec_mul(rot_mat, (0.0, 1.0, 0.0))
        u2 = _mat_vec_mul(rot_mat, (0.0, 0.0, 1.0))
        axes = (u0, u1, u2)

        # Local corner template if none provided
        if not self.local_bound_box:
            # Derive unscaled local points from dimensions / scale
            sx = self.scale[0] if abs(self.scale[0]) > 1e-6 else 1.0
            sy = self.scale[1] if abs(self.scale[1]) > 1e-6 else 1.0
            sz = self.scale[2] if abs(self.scale[2]) > 1e-6 else 1.0
            hx = (self.dimensions[0] / sx) * 0.5
            hy = (self.dimensions[1] / sy) * 0.5
            hz = (self.dimensions[2] / sz) * 0.5
            local_pts = []
            for sx_sign in (-1.0, 1.0):
                for sy_sign in (-1.0, 1.0):
                    for sz_sign in (-1.0, 1.0):
                        local_pts.append((sx_sign * hx, sy_sign * hy, sz_sign * hz))
        else:
            local_pts = self.local_bound_box

        # Transform local points to world coordinates: P_world = R * (P_local * scale) + location
        world_pts: List[Vec3] = []
        for lp in local_pts:
            scaled = (lp[0] * self.scale[0], lp[1] * self.scale[1], lp[2] * self.scale[2])
            rotated = _mat_vec_mul(rot_mat, scaled)
            world_pt = _vec_add(rotated, self.location)
            world_pts.append(world_pt)

        self.world_corners = world_pts

        # AABB from world corners
        self.aabb = AABB.from_points(world_pts)

        # OBB from center, axes, and extents
        center = self.location
        if world_pts:
            # True centroid of corners
            cx = sum(p[0] for p in world_pts) / len(world_pts)
            cy = sum(p[1] for p in world_pts) / len(world_pts)
            cz = sum(p[2] for p in world_pts) / len(world_pts)
            center = (cx, cy, cz)

        # Extents along local axes computed directly from projected world corners
        if world_pts:
            e0 = max(abs(_vec_dot(_vec_sub(p, center), u0)) for p in world_pts)
            e1 = max(abs(_vec_dot(_vec_sub(p, center), u1)) for p in world_pts)
            e2 = max(abs(_vec_dot(_vec_sub(p, center), u2)) for p in world_pts)
            extents = (max(e0, 1e-4), max(e1, 1e-4), max(e2, 1e-4))
        else:
            dx = self.dimensions[0] * 0.5 if self.dimensions[0] > 0 else 0.5
            dy = self.dimensions[1] * 0.5 if self.dimensions[1] > 0 else 0.5
            dz = self.dimensions[2] * 0.5 if self.dimensions[2] > 0 else 0.5
            extents = (dx, dy, dz)

        self.obb = OBB(
            center=center,
            axes=axes,
            extents=extents,
            corners=world_pts,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "parent": self.parent,
            "children": list(self.children),
            "location": [round(x, 4) for x in self.location],
            "rotation_euler": [round(x, 4) for x in self.rotation_euler],
            "scale": [round(x, 4) for x in self.scale],
            "dimensions": [round(x, 4) for x in self.dimensions],
            "local_bound_box": [[round(x, 4) for x in pt] for pt in self.local_bound_box],
            "world_corners": [[round(x, 4) for x in pt] for pt in self.world_corners],
            "aabb": self.aabb.to_dict() if self.aabb else None,
            "obb": self.obb.to_dict() if self.obb else None,
            "mesh_stats": copy.deepcopy(self.mesh_stats),
            "materials": list(self.materials),
            "modifiers": copy.deepcopy(self.modifiers),
            "collections": list(self.collections),
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneNode":
        aabb = AABB.from_dict(data["aabb"]) if data.get("aabb") else None
        obb = OBB.from_dict(data["obb"]) if data.get("obb") else None
        local_bound_box = [tuple(c) for c in data.get("local_bound_box", [])]
        world_corners = [tuple(c) for c in data.get("world_corners", [])]
        return cls(
            name=data["name"],
            type=data.get("type", "MESH"),
            parent=data.get("parent"),
            children=data.get("children", []),
            location=tuple(data.get("location", [0, 0, 0])),
            rotation_euler=tuple(data.get("rotation_euler", [0, 0, 0])),
            scale=tuple(data.get("scale", [1, 1, 1])),
            dimensions=tuple(data.get("dimensions", [1, 1, 1])),
            local_bound_box=local_bound_box,
            world_corners=world_corners,
            aabb=aabb,
            obb=obb,
            mesh_stats=data.get("mesh_stats"),
            materials=data.get("materials", []),
            modifiers=data.get("modifiers", []),
            collections=data.get("collections", []),
            visible=data.get("visible", True),
        )


class SceneGraph:
    """
    Spatial hierarchy and geometric query engine for Blender scenes.
    Tracks parent-child object relations and performs deterministic AABB/OBB intersection tests.
    """

    def __init__(self):
        self.nodes: Dict[str, SceneNode] = {}
        self.root_nodes: List[str] = []

    def add_node(self, node: SceneNode) -> None:
        self.nodes[node.name] = node
        self._rebuild_hierarchy()

    def get_node(self, name: str) -> Optional[SceneNode]:
        return self.nodes.get(name)

    def _rebuild_hierarchy(self) -> None:
        """Reconstructs children lists and root_nodes list from parent references."""
        for n in self.nodes.values():
            n.children = []
        roots = []
        for name, node in self.nodes.items():
            if node.parent and node.parent in self.nodes:
                self.nodes[node.parent].children.append(name)
            else:
                roots.append(name)
        self.root_nodes = sorted(roots)

    def get_children(self, name: str) -> List[SceneNode]:
        node = self.nodes.get(name)
        if not node:
            return []
        return [self.nodes[child] for child in node.children if child in self.nodes]

    def get_parent(self, name: str) -> Optional[SceneNode]:
        node = self.nodes.get(name)
        if not node or not node.parent:
            return None
        return self.nodes.get(node.parent)

    def get_ancestors(self, name: str) -> List[SceneNode]:
        ancestors = []
        curr = self.get_parent(name)
        visited = set()
        while curr and curr.name not in visited:
            visited.add(curr.name)
            ancestors.append(curr)
            curr = self.get_parent(curr.name)
        return ancestors

    def get_descendants(self, name: str) -> List[SceneNode]:
        descendants = []
        queue = [c for c in self.get_children(name)]
        visited = set()
        while queue:
            child = queue.pop(0)
            if child.name not in visited:
                visited.add(child.name)
                descendants.append(child)
                queue.extend(self.get_children(child.name))
        return descendants

    def get_aabb(self, name: str) -> Optional[AABB]:
        node = self.nodes.get(name)
        return node.aabb if node else None

    def get_obb(self, name: str) -> Optional[OBB]:
        node = self.nodes.get(name)
        return node.obb if node else None

    def get_scene_bounds(self) -> AABB:
        """Computes the overall AABB covering all nodes in the scene."""
        if not self.nodes:
            return AABB((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        pts = []
        for node in self.nodes.values():
            if node.world_corners:
                pts.extend(node.world_corners)
            elif node.aabb:
                pts.append(node.aabb.min_point)
                pts.append(node.aabb.max_point)
        return AABB.from_points(pts)

    def check_intersection(
        self,
        name_a: str,
        name_b: str,
        method: str = "OBB",
        tolerance: float = 1e-4,
    ) -> bool:
        """
        Tests whether two objects intersect.
        Method: 'OBB' (15-axis SAT, exact) or 'AABB' (axis-aligned, conservative).
        """
        node_a = self.nodes.get(name_a)
        node_b = self.nodes.get(name_b)
        if not node_a or not node_b:
            return False

        # Quick AABB rejection test
        if node_a.aabb and node_b.aabb:
            if not node_a.aabb.intersects(node_b.aabb, tolerance=tolerance):
                return False

        if method.upper() == "AABB":
            return True

        # Exact OBB SAT test
        if node_a.obb and node_b.obb:
            return node_a.obb.intersects(node_b.obb, tolerance=tolerance)

        return True

    def find_intersections(
        self,
        name: str,
        method: str = "OBB",
        include_descendants: bool = False,
    ) -> List[str]:
        """
        Finds all other scene objects intersecting with the specified object.
        """
        if name not in self.nodes:
            return []

        descendants = {d.name for d in self.get_descendants(name)} if not include_descendants else set()
        intersections = []

        for other_name in sorted(list(self.nodes.keys())):
            if other_name == name:
                continue
            if not include_descendants and (other_name in descendants or self.nodes[name].parent == other_name):
                continue
            if self.check_intersection(name, other_name, method=method):
                intersections.append(other_name)

        return intersections

    def find_all_intersections(self, method: str = "OBB") -> List[Tuple[str, str]]:
        """
        Finds all intersecting object pairs in the scene.
        """
        names = sorted(list(self.nodes.keys()))
        pairs = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                if self.check_intersection(a, b, method=method):
                    pairs.append((a, b))
        return pairs

    def query_radius(self, center: Vec3, radius: float) -> List[str]:
        """
        Finds all objects whose bounding volumes intersect a sphere of given radius.
        """
        results = []
        r2 = radius * radius
        for name, node in sorted(self.nodes.items()):
            if not node.aabb:
                continue
            # Distance from point to AABB
            d2 = 0.0
            for i in range(3):
                if center[i] < node.aabb.min_point[i]:
                    diff = node.aabb.min_point[i] - center[i]
                    d2 += diff * diff
                elif center[i] > node.aabb.max_point[i]:
                    diff = center[i] - node.aabb.max_point[i]
                    d2 += diff * diff
            if d2 <= r2:
                results.append(name)
        return results

    def raycast(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float = 1000.0,
    ) -> List[Tuple[str, float]]:
        """
        Performs ray-AABB intersection queries against all nodes.
        Returns list of (object_name, hit_distance) sorted in order of proximity along the ray.
        """
        dir_norm = _vec_normalize(direction)
        if _vec_length(dir_norm) < 1e-9:
            return []

        hits: List[Tuple[str, float]] = []

        for name, node in self.nodes.items():
            if not node.aabb:
                continue
            box = node.aabb
            tmin = 0.0
            tmax = max_distance
            hit = True

            for i in range(3):
                inv_d = 1.0 / dir_norm[i] if abs(dir_norm[i]) > 1e-9 else float("inf")
                t0 = (box.min_point[i] - origin[i]) * inv_d
                t1 = (box.max_point[i] - origin[i]) * inv_d
                if inv_d < 0.0:
                    t0, t1 = t1, t0
                tmin = max(tmin, t0)
                tmax = min(tmax, t1)
                if tmax < tmin:
                    hit = False
                    break

            if hit and tmin <= max_distance:
                hits.append((name, round(tmin, 4)))

        hits.sort(key=lambda x: x[1])
        return hits

    def check_spatial_relation(
        self,
        node_a: Union[str, "SceneNode"],
        node_b: Union[str, "SceneNode"],
        relation: Union[str, Any],
        **kwargs,
    ) -> bool:
        """
        Evaluates whether a named spatial relationship (e.g. 'ON_TOP_OF', 'FACING') holds
        between node_a and node_b.
        """
        from .spatial_relations import SpatialRelationshipEngine
        na = self.get_node(node_a) if isinstance(node_a, str) else node_a
        nb = self.get_node(node_b) if isinstance(node_b, str) else node_b
        if not na or not nb:
            return False
        engine = SpatialRelationshipEngine()
        res = engine.check_relation(na, nb, relation, **kwargs)
        return bool(res.holds)

    def get_spatial_relations(
        self,
        node_a: Union[str, "SceneNode"],
        node_b: Union[str, "SceneNode"],
        only_holding: bool = True,
        **kwargs,
    ) -> List[Any]:
        """
        Evaluates all spatial relationships from node_a to node_b.
        """
        from .spatial_relations import SpatialRelationshipEngine
        na = self.get_node(node_a) if isinstance(node_a, str) else node_a
        nb = self.get_node(node_b) if isinstance(node_b, str) else node_b
        if not na or not nb:
            return []
        engine = SpatialRelationshipEngine()
        return engine.find_all_relations(na, nb, only_holding=only_holding, **kwargs)

    def find_related_objects(
        self,
        source: Union[str, "SceneNode"],
        relation: Union[str, Any],
        **kwargs,
    ) -> List[Tuple[str, Any]]:
        """
        Finds all objects in the scene graph that satisfy the specified spatial relation
        with respect to the source object.
        Returns list of (target_name, SpatialRelationResult).
        """
        from .spatial_relations import SpatialRelationshipEngine
        src_node = self.get_node(source) if isinstance(source, str) else source
        if not src_node:
            return []
        engine = SpatialRelationshipEngine()
        results: List[Tuple[str, Any]] = []
        for name, target_node in self.nodes.items():
            if name == src_node.name:
                continue
            res = engine.check_relation(src_node, target_node, relation, **kwargs)
            if res.holds:
                results.append((name, res))
        return results

    @classmethod
    def from_blender(
        cls,
        executor: Any,
        include_mesh_stats: bool = True,
    ) -> "SceneGraph":
        """
        Builds a complete SceneGraph by querying live Blender scene state
        using standard read-only MCP inspection contracts ('list_objects' and 'get_object_details').
        """
        sg = cls()

        def _check_success(res):
            if not res:
                return False
            if hasattr(res, "is_success"):
                return bool(res.is_success)
            if hasattr(res, "status"):
                return res.status == "success"
            return bool(getattr(res, "success", False))

        list_res = executor.execute_tool("list_objects", {})
        if not _check_success(list_res):
            logger.warning("SceneGraph: Failed to list scene objects.")
            return sg

        raw_objects = list_res.result.get("objects", []) if list_res.result else []

        for obj_item in raw_objects:
            obj_name = obj_item.get("name") if isinstance(obj_item, dict) else str(obj_item)
            if not obj_name:
                continue

            det_res = executor.execute_tool(
                "get_object_details",
                {"name": obj_name, "include_mesh_stats": include_mesh_stats},
            )
            if not _check_success(det_res) or not isinstance(det_res.result, dict):
                continue

            det = det_res.result
            raw_bound_box = det.get("bound_box", [])
            local_pts = [tuple(pt) for pt in raw_bound_box] if raw_bound_box else []

            node = SceneNode(
                name=obj_name,
                type=det.get("type", "UNKNOWN"),
                parent=det.get("parent"),
                location=tuple(det.get("location", [0.0, 0.0, 0.0])),
                rotation_euler=tuple(det.get("rotation_euler", [0.0, 0.0, 0.0])),
                scale=tuple(det.get("scale", [1.0, 1.0, 1.0])),
                dimensions=tuple(det.get("dimensions", [1.0, 1.0, 1.0])),
                local_bound_box=local_pts,
                mesh_stats=det.get("mesh_stats"),
                materials=list(det.get("materials", [])),
                modifiers=list(det.get("modifiers", [])),
                collections=list(det.get("collections", [])),
                visible=det.get("visible", True),
            )
            sg.add_node(node)

        return sg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_nodes": list(self.root_nodes),
            "nodes": {name: n.to_dict() for name, n in self.nodes.items()},
            "scene_bounds": self.get_scene_bounds().to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneGraph":
        sg = cls()
        nodes_data = data.get("nodes", {})
        for name, ndata in nodes_data.items():
            node = SceneNode.from_dict(ndata)
            sg.nodes[name] = node
        sg._rebuild_hierarchy()
        return sg
