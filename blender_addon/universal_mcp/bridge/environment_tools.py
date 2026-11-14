"""
Environment and Architecture Tools for Universal MCP Blender Plugin.
Provides verified procedural creation and spatial assembly for:
1. Studio Cycloramas (seamless infinite cove backdrops)
2. Object Origin / Pivot Point manipulation
3. Parametric Architectural Room Enclosures
4. Procedural Landscape & Terrain Meshes
5. Surface Asset Scattering & Distribution
6. Ground Snapping & Grid Alignment

Executes strictly on Blender's main event thread with fail-closed validation,
approval verification, and symmetrical error handling.
"""

from typing import Dict, Any, List, Optional, Tuple
import math
import random
from .approval_registry import get_approval_registry


def _is_approval_required(bpy_module=None) -> bool:
    """Helper to check if scene mutation approval is required."""
    registry = get_approval_registry()
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            return True

    scene = getattr(bpy_module.context, "scene", None)
    if scene and hasattr(scene, "umcp_require_scene_mutation_approval"):
        return bool(scene.umcp_require_scene_mutation_approval)

    if registry:
        return registry.is_approval_required()
    return True


def _verify_approval(bpy_module, tool_name: str, params: Dict[str, Any]):
    """Fail-closed human approval verification."""
    if _is_approval_required(bpy_module):
        registry = get_approval_registry()
        req_id = params.get("request_id")
        token = params.get("approval_token")
        if req_id or token:
            ok, reason = registry.consume_approval(req_id, token, tool_name, params)
            if not ok:
                raise PermissionError(f"Scene mutation denied: {reason}")
        else:
            raise PermissionError(
                f"Scene mutation denied for '{tool_name}': Missing trusted human approval credentials. "
                "Both request_id and approval_token from a human approval decision in Blender are required."
            )


# ---------------------------------------------------------------------------
# 1. Studio Cyclorama (Seamless Curved Backdrop)
# ---------------------------------------------------------------------------

def handle_create_cyclorama(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for create_cyclorama.
    Creates a parameterized seamless curved studio sweep backdrop (infinite cove)
    with continuous tangent transitions, consistent upward/inward normals,
    smooth shading, and predictable bounding dimensions.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "create_cyclorama", params)

    name = str(params.get("name", "StudioCyclorama")).strip()
    if not name:
        raise ValueError("Cyclorama name cannot be empty")

    if name in bpy_module.data.objects:
        raise ValueError(f"Collision detected: An object named '{name}' already exists in the scene.")

    width = float(params.get("width", 10.0))
    depth = float(params.get("depth", 10.0))
    wall_height = float(params.get("wall_height", 5.0))
    cove_radius = float(params.get("cove_radius", 1.5))
    cove_segments = int(params.get("cove_segments", 16))

    if width <= 0.0 or depth <= 0.0 or wall_height <= 0.0:
        raise ValueError("Width, depth, and wall_height must all be strictly positive numbers.")
    if cove_radius < 0.0:
        raise ValueError("Cove radius cannot be negative.")
    if cove_radius > min(depth, wall_height):
        raise ValueError(
            f"Cove radius ({cove_radius}m) exceeds maximum allowable radius "
            f"min(depth, wall_height) = {min(depth, wall_height)}m."
        )
    if cove_segments < 1 or cove_segments > 64:
        raise ValueError(f"Cove segments must be between 1 and 64 (got {cove_segments}).")

    loc = params.get("location", [0.0, 0.0, 0.0])
    if not isinstance(loc, (list, tuple)) or len(loc) != 3:
        raise ValueError("Location must be a 3-element list or tuple [x, y, z].")
    location = [float(loc[0]), float(loc[1]), float(loc[2])]

    rot = params.get("rotation_euler", [0.0, 0.0, 0.0])
    if not isinstance(rot, (list, tuple)) or len(rot) != 3:
        raise ValueError("Rotation must be a 3-element list or tuple [rx, ry, rz].")
    rotation = [float(rot[0]), float(rot[1]), float(rot[2])]

    import bmesh
    bm = bmesh.new()

    # Generate 2D profile along Y-Z plane (from front of floor to top of back wall)
    # Floor extends from y = +depth/2 to y = -depth/2 + cove_radius at z = 0.
    # Cove curves from ( -depth/2 + cove_radius, 0 ) to ( -depth/2, cove_radius ).
    # Back wall extends from z = cove_radius to z = wall_height at y = -depth/2.
    half_depth = depth / 2.0
    cove_center_y = -half_depth + cove_radius
    cove_center_z = cove_radius

    profile_pts: List[Tuple[float, float]] = []

    # 1. Front floor edge
    profile_pts.append((half_depth, 0.0))

    # 2. Floor to cove transition point
    if cove_radius > 0.0:
        profile_pts.append((cove_center_y, 0.0))

        # 3. Cove curve points (quarter circle from theta = -pi/2 to 0)
        # Tangent at -pi/2 is horizontal (dz/dy = 0); tangent at 0 is vertical (dy/dz = 0)
        for i in range(1, cove_segments):
            angle = -0.5 * math.pi + (0.5 * math.pi * i / cove_segments)
            py = cove_center_y - cove_radius * math.cos(angle)
            pz = cove_center_z + cove_radius * math.sin(angle)
            profile_pts.append((py, pz))

        # Cove top transition
        profile_pts.append((-half_depth, cove_radius))
    else:
        # Sharp 90-degree corner
        profile_pts.append((-half_depth, 0.0))

    # 4. Top of back wall
    profile_pts.append((-half_depth, wall_height))

    # Deduplicate any coincident points in profile
    clean_profile: List[Tuple[float, float]] = [profile_pts[0]]
    for pt in profile_pts[1:]:
        if abs(pt[0] - clean_profile[-1][0]) > 1e-6 or abs(pt[1] - clean_profile[-1][1]) > 1e-6:
            clean_profile.append(pt)

    # Extrude along X from -width/2 to +width/2
    half_width = width / 2.0
    verts_left = [bm.verts.new((-half_width, py, pz)) for py, pz in clean_profile]
    verts_right = [bm.verts.new((half_width, py, pz)) for py, pz in clean_profile]

    # Create quad faces between profile strips
    # Ensure winding order produces inward/upward normals
    for i in range(len(clean_profile) - 1):
        v0 = verts_left[i]
        v1 = verts_left[i + 1]
        v2 = verts_right[i + 1]
        v3 = verts_right[i]
        bm.faces.new((v0, v1, v2, v3))

    for f in bm.faces:
        f.smooth = True

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_data = bpy_module.data.meshes.new(name)
    bm.to_mesh(mesh_data)
    bm.free()

    obj = bpy_module.data.objects.new(name, mesh_data)
    obj.location = location
    obj.rotation_euler = rotation

    # Link to active collection
    collection = bpy_module.context.collection or bpy_module.context.scene.collection
    collection.objects.link(obj)

    bpy_module.context.view_layer.update()

    # Calculate actual evaluated bounds
    bounds = [[float(c) for c in corner] for corner in obj.bound_box]

    return {
        "status": "SUCCESS",
        "name": obj.name,
        "width": width,
        "depth": depth,
        "wall_height": wall_height,
        "cove_radius": cove_radius,
        "cove_segments": cove_segments,
        "vertex_count": len(mesh_data.vertices),
        "polygon_count": len(mesh_data.polygons),
        "location": list(obj.location),
        "bound_box": bounds,
    }


# ---------------------------------------------------------------------------
# 2. Object Origin / Pivot Point Setting
# ---------------------------------------------------------------------------

def handle_set_object_origin(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for set_object_origin.
    Reposition an object's local origin/pivot point while preserving its
    world-space geometry and vertex coordinates.
    Supports:
      - 'BOTTOM_CENTER': Bounding box center X/Y at Z_min (essential for props/furniture grounding)
      - 'CENTER_OF_MASS' / 'ORIGIN_TO_GEOMETRY': Geometric center of bounding box
      - 'GEOMETRY_TO_ORIGIN': Centers geometry around existing origin
      - 'ORIGIN_TO_CURSOR': Moves origin to current 3D cursor position
      - 'CUSTOM_POINT': World-space coordinates provided in custom_point [x, y, z]
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "set_object_origin", params)

    object_name = str(params.get("object_name", "")).strip()
    if not object_name:
        raise ValueError("object_name must be specified.")

    if object_name not in bpy_module.data.objects:
        raise ValueError(f"Target object '{object_name}' not found in scene.")

    obj = bpy_module.data.objects[object_name]
    if obj.type != "MESH" or obj.data is None:
        raise ValueError(f"Object '{object_name}' is not a mesh object.")

    origin_mode = str(params.get("origin_mode", "BOTTOM_CENTER")).upper().strip()
    valid_modes = {"BOTTOM_CENTER", "CENTER_OF_MASS", "ORIGIN_TO_GEOMETRY", "GEOMETRY_TO_ORIGIN", "ORIGIN_TO_CURSOR", "CUSTOM_POINT"}
    if origin_mode not in valid_modes:
        raise ValueError(f"Invalid origin_mode '{origin_mode}'. Valid modes: {sorted(list(valid_modes))}")

    from mathutils import Vector, Matrix

    bpy_module.context.view_layer.update()
    world_mat = obj.matrix_world.copy()

    # World-space bounding box vertices
    world_corners = [world_mat @ Vector(c) for c in obj.bound_box]
    min_x = min(c.x for c in world_corners)
    max_x = max(c.x for c in world_corners)
    min_y = min(c.y for c in world_corners)
    max_y = max(c.y for c in world_corners)
    min_z = min(c.z for c in world_corners)
    max_z = max(c.z for c in world_corners)

    if origin_mode == "BOTTOM_CENTER":
        target_world_origin = Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, min_z))
    elif origin_mode in ("CENTER_OF_MASS", "ORIGIN_TO_GEOMETRY"):
        target_world_origin = Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5))
    elif origin_mode == "ORIGIN_TO_CURSOR":
        cursor = bpy_module.context.scene.cursor
        target_world_origin = cursor.location.copy()
    elif origin_mode == "CUSTOM_POINT":
        pt = params.get("custom_point")
        if not isinstance(pt, (list, tuple)) or len(pt) != 3:
            raise ValueError("custom_point [x, y, z] is required when origin_mode is 'CUSTOM_POINT'.")
        target_world_origin = Vector((float(pt[0]), float(pt[1]), float(pt[2])))
    elif origin_mode == "GEOMETRY_TO_ORIGIN":
        # Keep origin at current location, center geometry relative to origin
        local_corners = [Vector(c) for c in obj.bound_box]
        local_center = sum(local_corners, Vector()) / 8.0
        mesh = obj.data
        for v in mesh.vertices:
            v.co -= local_center
        mesh.update()
        bpy_module.context.view_layer.update()
        return {
            "status": "SUCCESS",
            "object_name": obj.name,
            "origin_mode": origin_mode,
            "new_origin_world": list(obj.matrix_world.translation),
            "new_location": list(obj.location),
        }

    # Displacement from current world origin to target world origin
    current_world_origin = world_mat.translation.copy()
    delta_world = target_world_origin - current_world_origin

    # Convert delta_world into local coordinates of the mesh
    rot_scale_inv = world_mat.to_3x3().inverted()
    delta_local = rot_scale_inv @ delta_world

    # Offset vertices in local space in opposite direction so world positions are identical
    mesh = obj.data
    for v in mesh.vertices:
        v.co -= delta_local
    mesh.update()

    # Move object origin to target world position
    new_world_mat = world_mat.copy()
    new_world_mat.translation = target_world_origin
    obj.matrix_world = new_world_mat

    bpy_module.context.view_layer.update()

    return {
        "status": "SUCCESS",
        "object_name": obj.name,
        "origin_mode": origin_mode,
        "new_origin_world": [float(target_world_origin.x), float(target_world_origin.y), float(target_world_origin.z)],
        "new_location": [float(obj.location.x), float(obj.location.y), float(obj.location.z)],
    }


# ---------------------------------------------------------------------------
# 3. Parametric Architectural Room Enclosure
# ---------------------------------------------------------------------------

def handle_create_room_enclosure(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for create_room_enclosure.
    Generates a clean manifold architectural room enclosure with parameterized
    interior dimensions, wall thickness, floor slab, optional ceiling slab,
    and structured doorway apertures with accurate lintels.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "create_room_enclosure", params)

    name = str(params.get("name", "InteriorRoom")).strip()
    if not name:
        raise ValueError("Room name cannot be empty")

    if name in bpy_module.data.objects:
        raise ValueError(f"Collision detected: An object named '{name}' already exists in the scene.")

    width = float(params.get("width", 6.0))      # X axis interior
    length = float(params.get("length", 8.0))    # Y axis interior
    height = float(params.get("height", 3.0))    # Z axis interior
    wall_thickness = float(params.get("wall_thickness", 0.2))

    if width <= 0.0 or length <= 0.0 or height <= 0.0:
        raise ValueError("Room width, length, and height must be strictly positive numbers.")
    if wall_thickness <= 0.0:
        raise ValueError("Wall thickness must be strictly positive.")

    include_floor = bool(params.get("include_floor", True))
    include_ceiling = bool(params.get("include_ceiling", False))

    roof_type = params.get("roof_type")
    if roof_type is not None:
        roof_type = str(roof_type).upper().strip()
        if roof_type in ("NONE", ""):
            roof_type = None
        elif roof_type not in ("FLAT", "GABLE", "HIP", "PITCHED", "SHED"):
            raise ValueError(f"Invalid roof_type '{roof_type}'. Must be 'FLAT', 'GABLE', 'HIP', 'PITCHED', 'SHED', or 'NONE'.")

    roof_height = float(params.get("roof_height", 2.0))
    roof_overhang = float(params.get("roof_overhang", 0.3))
    if roof_type and roof_height <= 0.0:
        raise ValueError("roof_height must be strictly positive.")
    if roof_type and roof_overhang < 0.0:
        raise ValueError("roof_overhang cannot be negative.")

    door_wall = params.get("door_wall")
    if door_wall is not None:
        door_wall = str(door_wall).upper().strip()
        if door_wall in ("NONE", ""):
            door_wall = None
        elif door_wall not in ("NORTH", "SOUTH", "EAST", "WEST"):
            raise ValueError(f"Invalid door_wall '{door_wall}'. Must be 'NORTH', 'SOUTH', 'EAST', 'WEST', or 'NONE'.")

    door_width = float(params.get("door_width", 0.9))
    door_height = float(params.get("door_height", 2.1))
    door_offset = float(params.get("door_offset", 0.0))

    if door_wall:
        wall_span = width if door_wall in ("NORTH", "SOUTH") else length
        if door_width <= 0.0 or door_width >= wall_span - 2 * wall_thickness:
            raise ValueError(f"Door width ({door_width}m) must be positive and fit within wall span ({wall_span}m).")
        if door_height <= 0.0 or door_height >= height:
            raise ValueError(f"Door height ({door_height}m) must be positive and less than room height ({height}m).")

    loc = params.get("location", [0.0, 0.0, 0.0])
    location = [float(loc[0]), float(loc[1]), float(loc[2])]

    import bmesh
    bm = bmesh.new()

    hw = width / 2.0
    hl = length / 2.0
    t = wall_thickness

    def add_box(min_x, max_x, min_y, max_y, min_z, max_z):
        """Helper to create a solid manifold box in bmesh."""
        v = [
            bm.verts.new((min_x, min_y, min_z)),
            bm.verts.new((max_x, min_y, min_z)),
            bm.verts.new((max_x, max_y, min_z)),
            bm.verts.new((min_x, max_y, min_z)),
            bm.verts.new((min_x, min_y, max_z)),
            bm.verts.new((max_x, min_y, max_z)),
            bm.verts.new((max_x, max_y, max_z)),
            bm.verts.new((min_x, max_y, max_z)),
        ]
        # Bottom, Top, Front, Back, Left, Right
        bm.faces.new((v[3], v[2], v[1], v[0]))
        bm.faces.new((v[4], v[5], v[6], v[7]))
        bm.faces.new((v[0], v[1], v[5], v[4]))
        bm.faces.new((v[2], v[3], v[7], v[6]))
        bm.faces.new((v[3], v[0], v[4], v[7]))
        bm.faces.new((v[1], v[2], v[6], v[5]))

    # 1. Floor Slab (Z from -t to 0)
    if include_floor:
        add_box(-hw - t, hw + t, -hl - t, hl + t, -t, 0.0)

    # 2. Ceiling Slab (Z from height to height + t)
    if include_ceiling:
        add_box(-hw - t, hw + t, -hl - t, hl + t, height, height + t)

    # 3. Walls (Z from 0 to height)
    # NORTH wall (at +Y): runs from X = -hw - t to hw + t, Y = hl to hl + t
    if door_wall == "NORTH":
        door_center_x = door_offset
        d_min_x = door_center_x - door_width / 2.0
        d_max_x = door_center_x + door_width / 2.0
        add_box(-hw - t, d_min_x, hl, hl + t, 0.0, height)              # Left segment
        add_box(d_max_x, hw + t, hl, hl + t, 0.0, height)               # Right segment
        add_box(d_min_x, d_max_x, hl, hl + t, door_height, height)       # Lintel
    else:
        add_box(-hw - t, hw + t, hl, hl + t, 0.0, height)

    # SOUTH wall (at -Y): runs from X = -hw - t to hw + t, Y = -hl - t to -hl
    if door_wall == "SOUTH":
        door_center_x = door_offset
        d_min_x = door_center_x - door_width / 2.0
        d_max_x = door_center_x + door_width / 2.0
        add_box(-hw - t, d_min_x, -hl - t, -hl, 0.0, height)             # Left segment
        add_box(d_max_x, hw + t, -hl - t, -hl, 0.0, height)              # Right segment
        add_box(d_min_x, d_max_x, -hl - t, -hl, door_height, height)      # Lintel
    else:
        add_box(-hw - t, hw + t, -hl - t, -hl, 0.0, height)

    # EAST wall (at +X): runs from X = hw to hw + t, Y = -hl to hl
    if door_wall == "EAST":
        door_center_y = door_offset
        d_min_y = door_center_y - door_width / 2.0
        d_max_y = door_center_y + door_width / 2.0
        add_box(hw, hw + t, -hl, d_min_y, 0.0, height)                  # Left segment
        add_box(hw, hw + t, d_max_y, hl, 0.0, height)                   # Right segment
        add_box(hw, hw + t, d_min_y, d_max_y, door_height, height)       # Lintel
    else:
        add_box(hw, hw + t, -hl, hl, 0.0, height)

    # WEST wall (at -X): runs from X = -hw - t to -hw, Y = -hl to hl
    if door_wall == "WEST":
        door_center_y = door_offset
        d_min_y = door_center_y - door_width / 2.0
        d_max_y = door_center_y + door_width / 2.0
        add_box(-hw - t, -hw, -hl, d_min_y, 0.0, height)                 # Left segment
        add_box(-hw - t, -hw, d_max_y, hl, 0.0, height)                  # Right segment
        add_box(-hw - t, -hw, d_min_y, d_max_y, door_height, height)      # Lintel
    else:
        add_box(-hw - t, -hw, -hl, hl, 0.0, height)

    # 4. Optional Integrated Roof
    if roof_type:
        _build_roof_mesh(
            bm,
            roof_type=roof_type,
            width=width + 2 * t,
            length=length + 2 * t,
            height=roof_height,
            overhang=roof_overhang,
            base_elevation=height,
        )

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_data = bpy_module.data.meshes.new(name)
    bm.to_mesh(mesh_data)
    is_manifold = all(len(e.link_faces) == 2 for e in bm.edges)
    has_boundary = any(e.is_boundary for e in bm.edges)
    bm.free()

    obj = bpy_module.data.objects.new(name, mesh_data)
    obj.location = location

    collection = bpy_module.context.collection or bpy_module.context.scene.collection
    collection.objects.link(obj)

    bpy_module.context.view_layer.update()
    bounds = [[float(c) for c in corner] for corner in obj.bound_box]

    return {
        "status": "SUCCESS",
        "name": obj.name,
        "interior_dimensions": [width, length, height],
        "wall_thickness": wall_thickness,
        "include_floor": include_floor,
        "include_ceiling": include_ceiling,
        "roof_type": roof_type,
        "roof_height": roof_height if roof_type else None,
        "is_manifold": is_manifold,
        "has_boundary": has_boundary,
        "door_wall": door_wall,
        "vertex_count": len(mesh_data.vertices),
        "polygon_count": len(mesh_data.polygons),
        "location": list(obj.location),
        "bound_box": bounds,
    }


# ---------------------------------------------------------------------------
# 3b. Parametric Roof Structure and Building Envelope Construction
# ---------------------------------------------------------------------------

def _build_roof_mesh(
    bm,
    roof_type: str,
    width: float,
    length: float,
    height: float,
    overhang: float = 0.3,
    base_elevation: float = 0.0,
    thickness: float = 0.2,
):
    """
    Constructs a solid, watertight, manifold roof geometry in bmesh.
    Supports 'GABLE', 'HIP', 'PITCHED'/'SHED', and 'FLAT'.
    """
    roof_type = str(roof_type).upper().strip()
    hw = width / 2.0
    hl = length / 2.0
    xmin = -hw - overhang
    xmax = hw + overhang
    ymin = -hl - overhang
    ymax = hl + overhang
    z0 = float(base_elevation)
    zridge = z0 + float(height)

    if roof_type == "GABLE":
        v0 = bm.verts.new((xmin, ymin, z0))
        v1 = bm.verts.new((xmax, ymin, z0))
        v2 = bm.verts.new((xmax, ymax, z0))
        v3 = bm.verts.new((xmin, ymax, z0))
        v4 = bm.verts.new((0.0, ymin, zridge))
        v5 = bm.verts.new((0.0, ymax, zridge))
        bm.faces.new((v3, v2, v1, v0))       # Bottom ceiling/soffit
        bm.faces.new((v0, v4, v5, v3))       # Left slope
        bm.faces.new((v1, v2, v5, v4))       # Right slope
        bm.faces.new((v0, v1, v4))           # Front gable
        bm.faces.new((v2, v3, v5))           # Back gable

    elif roof_type == "HIP":
        v0 = bm.verts.new((xmin, ymin, z0))
        v1 = bm.verts.new((xmax, ymin, z0))
        v2 = bm.verts.new((xmax, ymax, z0))
        v3 = bm.verts.new((xmin, ymax, z0))

        if length > width:
            yr = (length - width) / 2.0
            v4 = bm.verts.new((0.0, -yr, zridge))
            v5 = bm.verts.new((0.0, yr, zridge))
            bm.faces.new((v3, v2, v1, v0))   # Bottom
            bm.faces.new((v0, v1, v4))       # Front slope
            bm.faces.new((v2, v3, v5))       # Back slope
            bm.faces.new((v0, v4, v5, v3))   # Left slope
            bm.faces.new((v1, v2, v5, v4))   # Right slope
        elif width > length:
            xr = (width - length) / 2.0
            v4 = bm.verts.new((-xr, 0.0, zridge))
            v5 = bm.verts.new((xr, 0.0, zridge))
            bm.faces.new((v3, v2, v1, v0))   # Bottom
            bm.faces.new((v3, v0, v4))       # Left slope
            bm.faces.new((v1, v2, v5))       # Right slope
            bm.faces.new((v0, v1, v5, v4))   # Front slope
            bm.faces.new((v2, v3, v4, v5))   # Back slope
        else:
            # Square pyramid hip
            v4 = bm.verts.new((0.0, 0.0, zridge))
            bm.faces.new((v3, v2, v1, v0))   # Bottom
            bm.faces.new((v0, v1, v4))       # Front
            bm.faces.new((v1, v2, v4))       # Right
            bm.faces.new((v2, v3, v4))       # Back
            bm.faces.new((v3, v0, v4))       # Left

    elif roof_type in ("PITCHED", "SHED"):
        # Monopitch: low at -X, high at +X
        v0 = bm.verts.new((xmin, ymin, z0))
        v1 = bm.verts.new((xmax, ymin, z0))
        v2 = bm.verts.new((xmax, ymax, z0))
        v3 = bm.verts.new((xmin, ymax, z0))
        v4 = bm.verts.new((xmax, ymin, zridge))
        v5 = bm.verts.new((xmax, ymax, zridge))
        bm.faces.new((v3, v2, v1, v0))       # Bottom
        bm.faces.new((v0, v4, v5, v3))       # Pitch slope
        bm.faces.new((v1, v2, v5, v4))       # Back vertical wall
        bm.faces.new((v0, v1, v4))           # Front triangle
        bm.faces.new((v2, v3, v5))           # Back triangle

    elif roof_type == "FLAT":
        t = max(0.1, thickness)
        v = [
            bm.verts.new((xmin, ymin, z0)),
            bm.verts.new((xmax, ymin, z0)),
            bm.verts.new((xmax, ymax, z0)),
            bm.verts.new((xmin, ymax, z0)),
            bm.verts.new((xmin, ymin, z0 + t)),
            bm.verts.new((xmax, ymin, z0 + t)),
            bm.verts.new((xmax, ymax, z0 + t)),
            bm.verts.new((xmin, ymax, z0 + t)),
        ]
        bm.faces.new((v[3], v[2], v[1], v[0]))
        bm.faces.new((v[4], v[5], v[6], v[7]))
        bm.faces.new((v[0], v[1], v[5], v[4]))
        bm.faces.new((v[2], v[3], v[7], v[6]))
        bm.faces.new((v[3], v[0], v[4], v[7]))
        bm.faces.new((v[1], v[2], v[6], v[5]))

    else:
        raise ValueError(f"Unsupported roof_type '{roof_type}'. Must be 'GABLE', 'HIP', 'PITCHED', 'SHED', or 'FLAT'.")


def handle_create_roof_structure(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for create_roof_structure.
    Generates a parametric watertight solid roof geometry (GABLE, HIP, PITCHED, SHED, FLAT)
    with specified dimensions, overhang, elevation, and optional alignment to an existing building.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "create_roof_structure", params)

    name = str(params.get("name", "ArchitecturalRoof")).strip()
    if not name:
        raise ValueError("Roof name cannot be empty")
    if name in bpy_module.data.objects:
        raise ValueError(f"Collision detected: An object named '{name}' already exists in the scene.")

    roof_type = str(params.get("roof_type", "GABLE")).upper().strip()
    valid_types = {"GABLE", "HIP", "PITCHED", "SHED", "FLAT"}
    if roof_type not in valid_types:
        raise ValueError(f"Invalid roof_type '{roof_type}'. Must be one of {sorted(list(valid_types))}.")

    from mathutils import Vector

    target_bldg = params.get("target_building")
    width = float(params.get("width", 8.0))
    length = float(params.get("length", 10.0))
    base_elevation = float(params.get("base_elevation", 0.0))
    loc = params.get("location", [0.0, 0.0, 0.0])
    location = [float(loc[0]), float(loc[1]), float(loc[2])]

    if target_bldg:
        target_name = str(target_bldg).strip()
        if target_name not in bpy_module.data.objects:
            raise ValueError(f"Target building '{target_name}' not found in scene objects.")
        tb = bpy_module.data.objects[target_name]
        corners = [tb.matrix_world @ Vector(c) for c in tb.bound_box]
        min_x = min(c.x for c in corners)
        max_x = max(c.x for c in corners)
        min_y = min(c.y for c in corners)
        max_y = max(c.y for c in corners)
        max_z = max(c.z for c in corners)

        width = max_x - min_x
        length = max_y - min_y
        base_elevation = max_z
        location = [(min_x + max_x) / 2.0, (min_y + max_y) / 2.0, 0.0]

    height = float(params.get("height", 2.5))
    thickness = float(params.get("thickness", 0.2))
    overhang = float(params.get("overhang", 0.3))

    if width <= 0.0 or length <= 0.0 or height <= 0.0:
        raise ValueError("Roof width, length, and height must be strictly positive numbers.")
    if thickness <= 0.0:
        raise ValueError("Roof thickness must be strictly positive.")
    if overhang < 0.0:
        raise ValueError("Roof overhang cannot be negative.")

    import bmesh
    bm = bmesh.new()
    _build_roof_mesh(
        bm,
        roof_type=roof_type,
        width=width,
        length=length,
        height=height,
        overhang=overhang,
        base_elevation=base_elevation,
        thickness=thickness,
    )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_data = bpy_module.data.meshes.new(name)
    bm.to_mesh(mesh_data)
    is_manifold = all(len(e.link_faces) == 2 for e in bm.edges)
    has_boundary = any(e.is_boundary for e in bm.edges)
    bm.free()

    obj = bpy_module.data.objects.new(name, mesh_data)
    obj.location = location

    collection = bpy_module.context.collection or bpy_module.context.scene.collection
    collection.objects.link(obj)
    bpy_module.context.view_layer.update()

    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    b_min = [round(min(c.x for c in corners), 4), round(min(c.y for c in corners), 4), round(min(c.z for c in corners), 4)]
    b_max = [round(max(c.x for c in corners), 4), round(max(c.y for c in corners), 4), round(max(c.z for c in corners), 4)]

    return {
        "status": "SUCCESS",
        "name": obj.name,
        "roof_type": roof_type,
        "dimensions": [round(b_max[0] - b_min[0], 4), round(b_max[1] - b_min[1], 4), round(b_max[2] - b_min[2], 4)],
        "base_elevation": base_elevation,
        "ridge_elevation": base_elevation + height,
        "vertex_count": len(mesh_data.vertices),
        "polygon_count": len(mesh_data.polygons),
        "is_manifold": is_manifold,
        "has_boundary": has_boundary,
        "target_building": target_bldg,
        "location": list(obj.location),
        "bounds_min": b_min,
        "bounds_max": b_max,
    }


def handle_create_building_envelope(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for create_building_envelope.
    Constructs a complete exterior building envelope with structural foundation slab,
    facade walls, multi-story floor slabs, doorway aperture with lintel, and seamlessly integrated roof structure.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "create_building_envelope", params)

    name = str(params.get("name", "BuildingEnvelope")).strip()
    if not name:
        raise ValueError("Building name cannot be empty")
    if name in bpy_module.data.objects:
        raise ValueError(f"Collision detected: An object named '{name}' already exists in the scene.")

    width = float(params.get("width", 10.0))
    length = float(params.get("length", 12.0))
    height = float(params.get("height", 6.0))
    stories = int(params.get("stories", 2))
    foundation_thickness = float(params.get("foundation_thickness", 0.3))
    wall_thickness = float(params.get("wall_thickness", 0.25))

    roof_type = str(params.get("roof_type", "GABLE")).upper().strip()
    valid_roofs = {"GABLE", "HIP", "PITCHED", "FLAT"}
    if roof_type not in valid_roofs:
        raise ValueError(f"Invalid roof_type '{roof_type}'. Must be one of {sorted(list(valid_roofs))}.")
    roof_height = float(params.get("roof_height", 2.5))
    roof_overhang = float(params.get("roof_overhang", 0.4))

    door_wall = params.get("door_wall", "SOUTH")
    if door_wall is not None:
        door_wall = str(door_wall).upper().strip()
        if door_wall in ("NONE", ""):
            door_wall = None
        elif door_wall not in ("NORTH", "SOUTH", "EAST", "WEST"):
            raise ValueError(f"Invalid door_wall '{door_wall}'. Must be 'NORTH', 'SOUTH', 'EAST', 'WEST', or 'NONE'.")

    door_width = float(params.get("door_width", 1.8))
    door_height = float(params.get("door_height", 2.4))

    if width <= 0.0 or length <= 0.0 or height <= 0.0:
        raise ValueError("Building width, length, and height must be strictly positive numbers.")
    if stories < 1 or stories > 10:
        raise ValueError("Stories must be between 1 and 10.")
    if foundation_thickness <= 0.0 or wall_thickness <= 0.0:
        raise ValueError("Foundation and wall thickness must be strictly positive.")
    if roof_height <= 0.0:
        raise ValueError("Roof height must be strictly positive.")

    loc = params.get("location", [0.0, 0.0, 0.0])
    location = [float(loc[0]), float(loc[1]), float(loc[2])]

    import bmesh
    from mathutils import Vector
    bm = bmesh.new()

    hw = width / 2.0
    hl = length / 2.0
    t = wall_thickness

    def add_box(min_x, max_x, min_y, max_y, min_z, max_z):
        v = [
            bm.verts.new((min_x, min_y, min_z)),
            bm.verts.new((max_x, min_y, min_z)),
            bm.verts.new((max_x, max_y, min_z)),
            bm.verts.new((min_x, max_y, min_z)),
            bm.verts.new((min_x, min_y, max_z)),
            bm.verts.new((max_x, min_y, max_z)),
            bm.verts.new((max_x, max_y, max_z)),
            bm.verts.new((min_x, max_y, max_z)),
        ]
        bm.faces.new((v[3], v[2], v[1], v[0]))
        bm.faces.new((v[4], v[5], v[6], v[7]))
        bm.faces.new((v[0], v[1], v[5], v[4]))
        bm.faces.new((v[2], v[3], v[7], v[6]))
        bm.faces.new((v[3], v[0], v[4], v[7]))
        bm.faces.new((v[1], v[2], v[6], v[5]))

    # 1. Foundation Slab (Z = -foundation_thickness to 0.0)
    add_box(-hw - t, hw + t, -hl - t, hl + t, -foundation_thickness, 0.0)

    # 2. Intermediate Floor Slabs
    if stories > 1:
        story_h = height / stories
        for s in range(1, stories):
            zh = s * story_h
            add_box(-hw, hw, -hl, hl, zh - 0.2, zh)

    # 3. Exterior Structural Facade Walls (Z = 0.0 to height)
    # North Wall
    if door_wall == "NORTH":
        d_min_x = -door_width / 2.0
        d_max_x = door_width / 2.0
        add_box(-hw - t, d_min_x, hl, hl + t, 0.0, height)
        add_box(d_max_x, hw + t, hl, hl + t, 0.0, height)
        add_box(d_min_x, d_max_x, hl, hl + t, door_height, height)
    else:
        add_box(-hw - t, hw + t, hl, hl + t, 0.0, height)

    # South Wall
    if door_wall == "SOUTH":
        d_min_x = -door_width / 2.0
        d_max_x = door_width / 2.0
        add_box(-hw - t, d_min_x, -hl - t, -hl, 0.0, height)
        add_box(d_max_x, hw + t, -hl - t, -hl, 0.0, height)
        add_box(d_min_x, d_max_x, -hl - t, -hl, door_height, height)
    else:
        add_box(-hw - t, hw + t, -hl - t, -hl, 0.0, height)

    # East Wall
    if door_wall == "EAST":
        d_min_y = -door_width / 2.0
        d_max_y = door_width / 2.0
        add_box(hw, hw + t, -hl, d_min_y, 0.0, height)
        add_box(hw, hw + t, d_max_y, hl, 0.0, height)
        add_box(hw, hw + t, d_min_y, d_max_y, door_height, height)
    else:
        add_box(hw, hw + t, -hl, hl, 0.0, height)

    # West Wall
    if door_wall == "WEST":
        d_min_y = -door_width / 2.0
        d_max_y = door_width / 2.0
        add_box(-hw - t, -hw, -hl, d_min_y, 0.0, height)
        add_box(-hw - t, -hw, d_max_y, hl, 0.0, height)
        add_box(-hw - t, -hw, d_min_y, d_max_y, door_height, height)
    else:
        add_box(-hw - t, -hw, -hl, hl, 0.0, height)

    # 4. Integrated Roof Structure on Top (Z = height)
    _build_roof_mesh(
        bm,
        roof_type=roof_type,
        width=width + 2 * t,
        length=length + 2 * t,
        height=roof_height,
        overhang=roof_overhang,
        base_elevation=height,
    )

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_data = bpy_module.data.meshes.new(name)
    bm.to_mesh(mesh_data)
    is_manifold = all(len(e.link_faces) == 2 for e in bm.edges)
    has_boundary = any(e.is_boundary for e in bm.edges)
    bm.free()

    obj = bpy_module.data.objects.new(name, mesh_data)
    obj.location = location

    collection = bpy_module.context.collection or bpy_module.context.scene.collection
    collection.objects.link(obj)
    bpy_module.context.view_layer.update()

    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    b_min = [round(min(c.x for c in corners), 4), round(min(c.y for c in corners), 4), round(min(c.z for c in corners), 4)]
    b_max = [round(max(c.x for c in corners), 4), round(max(c.y for c in corners), 4), round(max(c.z for c in corners), 4)]

    return {
        "status": "SUCCESS",
        "name": obj.name,
        "dimensions": [round(b_max[0] - b_min[0], 4), round(b_max[1] - b_min[1], 4), round(b_max[2] - b_min[2], 4)],
        "stories": stories,
        "roof_type": roof_type,
        "roof_height": roof_height,
        "vertex_count": len(mesh_data.vertices),
        "polygon_count": len(mesh_data.polygons),
        "is_manifold": is_manifold,
        "has_boundary": has_boundary,
        "location": list(obj.location),
        "bounds_min": b_min,
        "bounds_max": b_max,
    }


# ---------------------------------------------------------------------------
# 4. Landscapes & Procedural Terrain Creation
# ---------------------------------------------------------------------------

def _pseudo_noise(x: float, y: float, seed: int) -> float:
    """Deterministic 2D smooth value noise generator."""
    def hash2d(ix: int, iy: int) -> float:
        n = (ix * 374761393 + iy * 668265263 + seed * 1013904223) & 0x7FFFFFFF
        n = (n ^ (n >> 13)) * 1274126177 & 0x7FFFFFFF
        return (n / 2147483647.0) * 2.0 - 1.0

    x0 = math.floor(x)
    x1 = x0 + 1
    y0 = math.floor(y)
    y1 = y0 + 1

    fx = x - x0
    fy = y - y0

    # Smoothstep interpolation curve: 3x^2 - 2x^3
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)

    n00 = hash2d(x0, y0)
    n10 = hash2d(x1, y0)
    n01 = hash2d(x0, y1)
    n11 = hash2d(x1, y1)

    ix0 = n00 + sx * (n10 - n00)
    ix1 = n01 + sx * (n11 - n01)
    return ix0 + sy * (ix1 - ix0)


def handle_create_terrain(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for create_terrain.
    Generates a parameterized terrain mesh with multi-octave procedural elevation,
    smooth normal shading, boundary edge falloff damping, and evaluated elevation metrics.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "create_terrain", params)

    name = str(params.get("name", "LandscapeTerrain")).strip()
    if not name:
        raise ValueError("Terrain name cannot be empty")

    if name in bpy_module.data.objects:
        raise ValueError(f"Collision detected: An object named '{name}' already exists in the scene.")

    width = float(params.get("width", 50.0))
    depth = float(params.get("depth", 50.0))
    res_x = int(params.get("resolution_x", 64))
    res_y = int(params.get("resolution_y", 64))
    elevation_scale = float(params.get("elevation_scale", 5.0))
    noise_scale = float(params.get("noise_scale", 0.05))
    noise_octaves = int(params.get("noise_octaves", 4))
    roughness = float(params.get("roughness", 0.5))
    seed = int(params.get("seed", 42))
    boundary_falloff = bool(params.get("boundary_falloff", True))

    if width <= 0.0 or depth <= 0.0:
        raise ValueError("Terrain width and depth must be strictly positive.")
    if res_x < 2 or res_x > 256 or res_y < 2 or res_y > 256:
        raise ValueError(f"Resolution must be between 2 and 256 (got {res_x}x{res_y}).")
    if elevation_scale < 0.0:
        raise ValueError("Elevation scale cannot be negative.")
    if noise_scale <= 0.0:
        raise ValueError("Noise scale must be strictly positive.")
    if noise_octaves < 1 or noise_octaves > 8:
        raise ValueError("Noise octaves must be between 1 and 8.")

    loc = params.get("location", [0.0, 0.0, 0.0])
    location = [float(loc[0]), float(loc[1]), float(loc[2])]

    import bmesh
    bm = bmesh.new()

    dx = width / (res_x - 1)
    dy = depth / (res_y - 1)
    x_start = -width / 2.0
    y_start = -depth / 2.0

    elevations: List[float] = []
    grid_verts = []

    for iy in range(res_y):
        row = []
        py = y_start + iy * dy
        y_norm = iy / (res_y - 1)
        for ix in range(res_x):
            px = x_start + ix * dx
            x_norm = ix / (res_x - 1)

            # Multi-octave fractal noise
            z = 0.0
            amp = 1.0
            freq = noise_scale
            total_amp = 0.0

            for oct_idx in range(noise_octaves):
                z += _pseudo_noise(px * freq, py * freq, seed + oct_idx * 1337) * amp
                total_amp += amp
                amp *= roughness
                freq *= 2.0

            z = (z / total_amp) * elevation_scale

            # Boundary falloff to smoothly meet flat ground at boundaries
            if boundary_falloff:
                falloff = math.sin(math.pi * x_norm) * math.sin(math.pi * y_norm)
                z *= falloff

            v = bm.verts.new((px, py, z))
            row.append(v)
            elevations.append(z)
        grid_verts.append(row)

    # Create quad faces
    for iy in range(res_y - 1):
        for ix in range(res_x - 1):
            v0 = grid_verts[iy][ix]
            v1 = grid_verts[iy][ix + 1]
            v2 = grid_verts[iy + 1][ix + 1]
            v3 = grid_verts[iy + 1][ix]
            bm.faces.new((v0, v1, v2, v3))

    for f in bm.faces:
        f.smooth = True

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_data = bpy_module.data.meshes.new(name)
    bm.to_mesh(mesh_data)
    bm.free()

    obj = bpy_module.data.objects.new(name, mesh_data)
    obj.location = location

    collection = bpy_module.context.collection or bpy_module.context.scene.collection
    collection.objects.link(obj)

    bpy_module.context.view_layer.update()

    min_elev = min(elevations)
    max_elev = max(elevations)
    mean_elev = sum(elevations) / len(elevations)
    variance_elev = sum((e - mean_elev) ** 2 for e in elevations) / len(elevations)

    return {
        "status": "SUCCESS",
        "name": obj.name,
        "width": width,
        "depth": depth,
        "resolution": [res_x, res_y],
        "vertex_count": len(mesh_data.vertices),
        "polygon_count": len(mesh_data.polygons),
        "elevation_min": float(min_elev),
        "elevation_max": float(max_elev),
        "elevation_variance": float(variance_elev),
        "location": list(obj.location),
    }


# ---------------------------------------------------------------------------
# 5. Surface Asset Scattering & Distribution
# ---------------------------------------------------------------------------

def handle_scatter_surface_assets(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for scatter_surface_assets.
    Distributes linked duplicates of source props across a target surface mesh
    with normal alignment, random Z rotation, scale variance, and overlap avoidance.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "scatter_surface_assets", params)

    surface_name = str(params.get("surface_name", "")).strip()
    if not surface_name or surface_name not in bpy_module.data.objects:
        raise ValueError(f"Target surface object '{surface_name}' not found.")

    surface_obj = bpy_module.data.objects[surface_name]
    if surface_obj.type != "MESH" or surface_obj.data is None:
        raise ValueError(f"Surface object '{surface_name}' is not a mesh object.")

    asset_names = params.get("asset_names", [])
    if not isinstance(asset_names, list) or not asset_names:
        raise ValueError("asset_names must be a non-empty list of source object names.")

    for aname in asset_names:
        if aname not in bpy_module.data.objects:
            raise ValueError(f"Source asset object '{aname}' not found in scene.")

    count = int(params.get("count", 30))
    if count < 1 or count > 500:
        raise ValueError(f"Scatter count must be between 1 and 500 (got {count}).")

    seed = int(params.get("seed", 42))
    min_scale = float(params.get("min_scale", 0.8))
    max_scale = float(params.get("max_scale", 1.2))
    if min_scale <= 0.0 or max_scale < min_scale:
        raise ValueError("Invalid scale bounds: min_scale > 0 and max_scale >= min_scale required.")

    random_rot_z = bool(params.get("random_rotation_z", True))
    align_normal = bool(params.get("align_to_normal", True))
    avoid_overlap = bool(params.get("avoid_overlap", True))
    min_dist = float(params.get("min_distance", 1.0))
    name_prefix = str(params.get("name_prefix", "ScatteredAsset")).strip()
    coll_name = str(params.get("collection_name", "ScatteredAssets")).strip()

    from mathutils import Vector, Matrix, Quaternion

    # Find or create target collection
    target_coll = None
    if coll_name in bpy_module.data.collections:
        target_coll = bpy_module.data.collections[coll_name]
    else:
        target_coll = bpy_module.data.collections.new(coll_name)
        bpy_module.context.scene.collection.children.link(target_coll)

    rng = random.Random(seed)
    surface_mesh = surface_obj.data
    surface_mat = surface_obj.matrix_world

    # Sample candidate polygons
    polys = list(surface_mesh.polygons)
    if not polys:
        raise ValueError(f"Surface '{surface_name}' contains zero polygons.")

    scattered_objs: List[str] = []
    placed_points: List[Vector] = []

    attempts = 0
    max_attempts = count * 20

    while len(scattered_objs) < count and attempts < max_attempts:
        attempts += 1
        poly = rng.choice(polys)
        poly_center_local = poly.center
        poly_normal_local = poly.normal

        # Transform to world space
        world_pt = surface_mat @ poly_center_local
        world_norm = (surface_mat.to_3x3() @ poly_normal_local).normalized()

        if avoid_overlap and min_dist > 0.0:
            if any((world_pt - p).length < min_dist for p in placed_points):
                continue

        placed_points.append(world_pt)

        # Select source asset
        src_name = rng.choice(asset_names)
        src_obj = bpy_module.data.objects[src_name]

        # Create linked duplicate sharing mesh datablock (memory efficient)
        inst_name = f"{name_prefix}_{len(scattered_objs) + 1}"
        inst_obj = bpy_module.data.objects.new(inst_name, src_obj.data)
        inst_obj.location = world_pt

        # Scale
        s = rng.uniform(min_scale, max_scale)
        inst_obj.scale = (s, s, s)

        # Rotation
        if align_normal:
            up = Vector((0.0, 0.0, 1.0))
            rot_quat = up.rotation_difference(world_norm)
            if random_rot_z:
                z_twist = Quaternion(Vector((0.0, 0.0, 1.0)), rng.uniform(0.0, 2.0 * math.pi))
                rot_quat = rot_quat @ z_twist
            inst_obj.rotation_euler = rot_quat.to_euler()
        elif random_rot_z:
            inst_obj.rotation_euler = (0.0, 0.0, rng.uniform(0.0, 2.0 * math.pi))

        target_coll.objects.link(inst_obj)
        scattered_objs.append(inst_obj.name)

    bpy_module.context.view_layer.update()

    return {
        "status": "SUCCESS",
        "surface_name": surface_name,
        "requested_count": count,
        "scattered_count": len(scattered_objs),
        "collection_name": target_coll.name,
        "instance_names": scattered_objs,
    }


# ---------------------------------------------------------------------------
# 6. Modular Environment Grid Snapping & Ground Placement
# ---------------------------------------------------------------------------

def handle_snap_to_ground(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for snap_to_ground.
    Aligns the bottom of an object's bounding box (Z_min) precisely to the ground surface
    (Z = 0 or the top of an optional ground object), eliminating floating or floor clipping.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "snap_to_ground", params)

    object_name = str(params.get("object_name", "")).strip()
    if not object_name or object_name not in bpy_module.data.objects:
        raise ValueError(f"Object '{object_name}' not found.")

    obj = bpy_module.data.objects[object_name]
    ground_name = params.get("ground_name")
    offset = float(params.get("offset", 0.0))

    from mathutils import Vector

    bpy_module.context.view_layer.update()
    obj_corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    current_z_min = min(c.z for c in obj_corners)

    ground_z = 0.0
    if ground_name:
        ground_name = str(ground_name).strip()
        if ground_name not in bpy_module.data.objects:
            raise ValueError(f"Ground object '{ground_name}' not found.")
        ground_obj = bpy_module.data.objects[ground_name]
        ground_corners = [ground_obj.matrix_world @ Vector(c) for c in ground_obj.bound_box]
        ground_z = max(c.z for c in ground_corners)

    target_z_min = ground_z + offset
    delta_z = target_z_min - current_z_min

    obj.location.z += delta_z
    bpy_module.context.view_layer.update()

    new_corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    new_z_min = min(c.z for c in new_corners)

    return {
        "status": "SUCCESS",
        "object_name": obj.name,
        "initial_z_min": float(current_z_min),
        "new_z_min": float(new_z_min),
        "ground_z": float(ground_z),
        "displacement_z": float(delta_z),
    }


def handle_align_object_grid(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for align_object_grid.
    Snaps an object's location to the nearest grid increment along specified axes.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "align_object_grid", params)

    object_name = str(params.get("object_name", "")).strip()
    if not object_name or object_name not in bpy_module.data.objects:
        raise ValueError(f"Object '{object_name}' not found.")

    obj = bpy_module.data.objects[object_name]
    grid_size = float(params.get("grid_size", 1.0))
    if grid_size <= 0.0:
        raise ValueError("grid_size must be strictly positive.")

    snap_axes = params.get("snap_axes", ["X", "Y"])
    if not isinstance(snap_axes, list):
        raise ValueError("snap_axes must be a list of axis strings ('X', 'Y', 'Z').")

    axes = {str(a).upper().strip() for a in snap_axes}
    orig_loc = list(obj.location)

    if "X" in axes:
        obj.location.x = round(obj.location.x / grid_size) * grid_size
    if "Y" in axes:
        obj.location.y = round(obj.location.y / grid_size) * grid_size
    if "Z" in axes:
        obj.location.z = round(obj.location.z / grid_size) * grid_size

    bpy_module.context.view_layer.update()

    return {
        "status": "SUCCESS",
        "object_name": obj.name,
        "original_location": [float(c) for c in orig_loc],
        "snapped_location": [float(obj.location.x), float(obj.location.y), float(obj.location.z)],
        "grid_size": grid_size,
        "snap_axes": sorted(list(axes)),
    }


# ---------------------------------------------------------------------------
# 7. Environment Workflow & UniversalMutationJournal Transaction Management
# ---------------------------------------------------------------------------

_ACTIVE_ENVIRONMENT_TRANSACTIONS: Dict[str, Any] = {}


def handle_begin_environment_transaction(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for begin_environment_transaction.
    Initializes a UniversalMutationJournal session tracking pre-mutation scene state.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "begin_environment_transaction", params)

    from .handlers import UniversalMutationJournal
    import time
    import random

    context_name = str(params.get("context_name", "Environment_Workflow")).strip()
    tx_id = f"tx_env_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

    journal = UniversalMutationJournal(bpy_module, context_name=context_name)
    journal.__enter__()
    _ACTIVE_ENVIRONMENT_TRANSACTIONS[tx_id] = journal

    obj_count = len(bpy_module.data.objects) if hasattr(bpy_module.data, "objects") else 0
    mesh_count = len(bpy_module.data.meshes) if hasattr(bpy_module.data, "meshes") else 0
    mat_count = len(bpy_module.data.materials) if hasattr(bpy_module.data, "materials") else 0
    col_count = len(bpy_module.data.collections) if hasattr(bpy_module.data, "collections") else 0

    return {
        "status": "SUCCESS",
        "action": "begin_environment_transaction",
        "transaction_id": tx_id,
        "context_name": context_name,
        "baseline_counts": {
            "objects": obj_count,
            "meshes": mesh_count,
            "materials": mat_count,
            "collections": col_count,
        },
    }


def handle_rollback_environment_transaction(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for rollback_environment_transaction.
    Executes compensating cleanup for items mutated during the active transaction session.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "rollback_environment_transaction", params)

    tx_id = params.get("transaction_id")
    journal = None
    if tx_id and tx_id in _ACTIVE_ENVIRONMENT_TRANSACTIONS:
        journal = _ACTIVE_ENVIRONMENT_TRANSACTIONS.pop(tx_id)
    elif _ACTIVE_ENVIRONMENT_TRANSACTIONS:
        tx_id, journal = _ACTIVE_ENVIRONMENT_TRANSACTIONS.popitem()
    else:
        return {
            "status": "NOOP",
            "message": "No active environment transaction found to roll back.",
        }

    report = journal.rollback_compensation()
    if hasattr(bpy_module, "context") and hasattr(bpy_module.context, "view_layer"):
        bpy_module.context.view_layer.update()

    return {
        "status": "ROLLED_BACK",
        "action": "rollback_environment_transaction",
        "transaction_id": tx_id,
        "compensation_report": report,
    }


def handle_commit_environment_transaction(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for commit_environment_transaction.
    Finalizes active transaction and releases journal tracker.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "commit_environment_transaction", params)

    tx_id = params.get("transaction_id")
    if tx_id and tx_id in _ACTIVE_ENVIRONMENT_TRANSACTIONS:
        _ACTIVE_ENVIRONMENT_TRANSACTIONS.pop(tx_id)
    elif _ACTIVE_ENVIRONMENT_TRANSACTIONS:
        tx_id, _ = _ACTIVE_ENVIRONMENT_TRANSACTIONS.popitem()

    return {
        "status": "COMMITTED",
        "action": "commit_environment_transaction",
        "transaction_id": tx_id,
    }


def handle_execute_environment_workflow(bpy_module=None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handler for execute_environment_workflow.
    Executes a multi-step environment construction workflow atomically.
    If any step fails or encounters an unhandled error, automatically invokes
    UniversalMutationJournal.rollback_compensation() to restore the exact pre-workflow state.
    """
    if bpy_module is None:
        try:
            import bpy
            bpy_module = bpy
        except ImportError:
            raise RuntimeError("bpy is not available in the current environment")

    params = params or {}
    _verify_approval(bpy_module, "execute_environment_workflow", params)

    steps = params.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Parameter 'steps' must be a non-empty list of tool invocation dicts.")

    from .handlers import ALL_HANDLERS, UniversalMutationJournal

    workflow_name = str(params.get("workflow_name", "EnvironmentWorkflow")).strip()
    journal = UniversalMutationJournal(bpy_module, context_name=workflow_name)
    journal.__enter__()

    executed_results = []

    try:
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError(f"Step {idx} must be a dictionary containing 'tool' and 'params'.")
            tool_name = str(step.get("tool", "")).strip()
            tool_params = step.get("params", {})
            if not isinstance(tool_params, dict):
                tool_params = {}

            # Authorize child step under this approved parent workflow transaction
            step_params = dict(tool_params)
            if "request_id" not in step_params or "approval_token" not in step_params:
                registry = get_approval_registry()
                step_req = registry.create_request(tool_name, step_params, timeout=60.0)
                ok, step_token = registry.resolve_request(
                    step_req.request_id,
                    "approved",
                    reason=f"Authorized under approved workflow '{workflow_name}'",
                    approve_task_group=False,
                )
                if ok and step_token:
                    step_params["request_id"] = step_req.request_id
                    step_params["approval_token"] = step_token

            if tool_name not in ALL_HANDLERS:
                raise ValueError(f"Step {idx} tool '{tool_name}' is not registered in ALL_HANDLERS.")

            handler = ALL_HANDLERS[tool_name]
            step_res = handler(bpy_module=bpy_module, params=step_params)

            if isinstance(step_res, dict) and step_res.get("status") in ("error", "ERROR", "FAILED"):
                err_msg = step_res.get("message") or step_res.get("error_message") or f"Tool '{tool_name}' reported failure."
                raise RuntimeError(err_msg)

            executed_results.append({
                "step_index": idx,
                "tool": tool_name,
                "result": step_res,
            })

        if hasattr(bpy_module, "context") and hasattr(bpy_module.context, "view_layer"):
            bpy_module.context.view_layer.update()

        return {
            "status": "SUCCESS",
            "action": "execute_environment_workflow",
            "workflow_name": workflow_name,
            "steps_executed": len(executed_results),
            "step_results": executed_results,
        }
    except Exception as exc:
        rollback_report = journal.rollback_compensation()
        if hasattr(bpy_module, "context") and hasattr(bpy_module.context, "view_layer"):
            bpy_module.context.view_layer.update()

        return {
            "status": "ROLLED_BACK",
            "action": "execute_environment_workflow",
            "workflow_name": workflow_name,
            "failed_step_index": len(executed_results),
            "failed_tool": steps[len(executed_results)].get("tool") if len(executed_results) < len(steps) else "unknown",
            "error_message": str(exc),
            "rollback_report": rollback_report,
            "executed_steps_before_failure": executed_results,
        }
