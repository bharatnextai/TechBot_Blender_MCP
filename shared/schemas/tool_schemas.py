"""
Tool schemas and definitions for the Universal MCP Blender Plugin.
Defines JSON schemas, tool descriptors, and parameter validation.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
from blender_addon.universal_mcp.bridge.mesh_topology import validate_topology_options

# Permission Tiers
PERMISSION_READ_ONLY = "READ_ONLY"
PERMISSION_SCENE_MUTATION = "SCENE_MUTATION"
PERMISSION_DESTRUCTIVE = "DESTRUCTIVE"

# Tool Identifiers
TOOL_GET_SCENE_SUMMARY = "get_scene_summary"
TOOL_LIST_OBJECTS = "list_objects"
TOOL_GET_OBJECT_DETAILS = "get_object_details"
TOOL_LIST_MATERIALS = "list_materials"
TOOL_CREATE_PRIMITIVE = "create_primitive"
TOOL_EDIT_MESH = "edit_mesh"
TOOL_TRANSFORM_OBJECT = "transform_object"
TOOL_INSPECT_SCENE_DATA = "inspect_scene_data"
TOOL_EXECUTE_BLENDER_CODE = "execute_blender_code"
TOOL_CONFIGURE_MODELING_GEOMETRY = "configure_modeling_geometry"
TOOL_INSPECT_MODELING_GEOMETRY = "inspect_modeling_geometry"
TOOL_CONFIGURE_MODELING_OBJECT = "configure_modeling_object"
TOOL_INSPECT_MODELING_OBJECT = "inspect_modeling_object"
TOOL_CONFIGURE_CURVE_GEOMETRY = "configure_curve_geometry"
TOOL_INSPECT_CURVE_GEOMETRY = "inspect_curve_geometry"
TOOL_EDIT_MODIFIER_STACK = "edit_modifier_stack"
TOOL_INSPECT_MODIFIER_STACK = "inspect_modifier_stack"
TOOL_CONFIGURE_MODIFIER = "configure_modifier"
TOOL_INSPECT_MODIFIERS = "inspect_modifiers"
TOOL_APPLY_MODIFIER = "apply_modifier"
TOOL_CONFIGURE_MATERIAL_SHADER = "configure_material_shader"
TOOL_INSPECT_MATERIAL_SHADER = "inspect_material_shader"
TOOL_INSPECT_RENDER_OUTPUT = "inspect_render_output"
TOOL_CREATE_MATERIAL = "create_material"
TOOL_ASSIGN_MATERIAL = "assign_material"
TOOL_CREATE_LIGHT = "create_light"
TOOL_CONFIGURE_LIGHT = "configure_light"
TOOL_CONFIGURE_WORLD = "configure_world"
TOOL_CAPTURE_VIEWPORT = "capture_viewport"
TOOL_RESOLVE_PENDING_APPROVAL = "resolve_pending_approval"
TOOL_GET_TASK_STATUS = "get_task_status"
TOOL_CHECK_APPROVAL_STATUS = "check_approval_status"
TOOL_CREATE_CAMERA = "create_camera"
TOOL_CONFIGURE_CAMERA = "configure_camera"
TOOL_EDIT_CAMERA = "edit_camera"
TOOL_SWITCH_CAMERA = "switch_camera"
TOOL_CONFIGURE_RENDER_SETTINGS = "configure_render_settings"
TOOL_DELETE_OBJECT = "delete_object"
TOOL_SAVE_BLEND_FILE = "save_blend_file"
TOOL_RENDER_SCENE = "render_scene"
TOOL_EXTRUDE_MESH = "extrude_mesh"
TOOL_INSET_MESH = "inset_mesh"
TOOL_EXTRUDE_FACES = "extrude_faces"
TOOL_INSET_FACES = "inset_faces"
TOOL_UV_UNWRAP = "uv_unwrap"
TOOL_UV_SMART_PROJECT = "uv_smart_project"
TOOL_UNWRAP_MESH = "unwrap_mesh"
TOOL_SMART_PROJECT = "smart_project"
TOOL_SMART_UV_PROJECT = "smart_uv_project"
TOOL_UV_PROJECT = "uv_project"
TOOL_MANAGE_UV_SEAMS = "manage_uv_seams"
TOOL_PACK_UV_ISLANDS = "pack_uv_islands"
TOOL_MANAGE_UV_LAYERS = "manage_uv_layers"
TOOL_INSPECT_UV_MESH = "inspect_uv_mesh"
TOOL_MANAGE_KEYFRAME = "manage_keyframe"
TOOL_INSERT_KEYFRAME = "insert_keyframe"
TOOL_DELETE_KEYFRAME = "delete_keyframe"
TOOL_CONFIGURE_GEOMETRY_NODES = "configure_geometry_nodes"
TOOL_INSPECT_GEOMETRY_NODES = "inspect_geometry_nodes"
TOOL_EXPORT_SCENE_ASSET = "export_scene_asset"
TOOL_IMPORT_SCENE_ASSET = "import_scene_asset"
TOOL_EXPORT_SCENE = "export_scene"
TOOL_IMPORT_SCENE = "import_scene"
TOOL_DUPLICATE_OBJECT = "duplicate_object"
TOOL_RENAME_OBJECT = "rename_object"
TOOL_DUPLICATE = "duplicate"
TOOL_RENAME = "rename"
TOOL_SELECT_OBJECT = "select_object"
TOOL_SELECT = "select"
TOOL_PURGE_ORPHANED_DATABLOCKS = "purge_orphaned_datablocks"
TOOL_PURGE_ORPHANS = "purge_orphans"
TOOL_CREATE_CURVE_OR_TEXT = "create_curve_or_text"
TOOL_CREATE_CURVE = "create_curve"
TOOL_CREATE_TEXT = "create_text"
TOOL_MANAGE_SHADER_NODES = "manage_shader_nodes"
TOOL_CONNECT_SHADER_NODES = "connect_shader_nodes"
TOOL_MANAGE_NODES = "manage_nodes"
TOOL_BAKE_OBJECT_TEXTURE = "bake_object_texture"
TOOL_BAKE_TEXTURE = "bake_texture"
TOOL_BAKE_MATERIALS = "bake_materials"
TOOL_MANAGE_COMPOSITOR_NODES = "manage_compositor_nodes"
TOOL_CONFIGURE_COMPOSITOR = "configure_compositor"
TOOL_MANAGE_COMPOSITOR = "manage_compositor"
TOOL_INSPECT_COMPOSITOR_PIPELINE = "inspect_compositor_pipeline"
TOOL_CONFIGURE_ANIMATION_CURVE = "configure_animation_curve"
TOOL_MANAGE_FCURVE = "manage_fcurve"
TOOL_SET_KEYFRAME_INTERPOLATION = "set_keyframe_interpolation"
TOOL_MANAGE_ACTION_SLOTS = "manage_action_slots"
TOOL_CONFIGURE_PHYSICS = "configure_physics"
TOOL_SETUP_PHYSICS = "setup_physics"
TOOL_MANAGE_PHYSICS = "manage_physics"
TOOL_INSPECT_PHYSICS = "inspect_physics"
TOOL_BAKE_PHYSICS_SIMULATION = "bake_physics_simulation"
TOOL_CONFIGURE_FORCE_FIELD = "configure_force_field"
TOOL_INSPECT_FORCE_FIELD = "inspect_force_field"
TOOL_CONFIGURE_PARTICLE_SYSTEM = "configure_particle_system"
TOOL_INSPECT_PARTICLE_SYSTEM = "inspect_particle_system"
TOOL_CONFIGURE_FLUID_SIMULATION = "configure_fluid_simulation"
TOOL_INSPECT_FLUID_SIMULATION = "inspect_fluid_simulation"
TOOL_OPEN_BLEND_FILE = "open_blend_file"
TOOL_OPEN_PROJECT = "open_project"
TOOL_LOAD_BLEND_FILE = "load_blend_file"
TOOL_CREATE_ARMATURE = "create_armature"
TOOL_EDIT_ARMATURE_BONES = "edit_armature_bones"
TOOL_INSPECT_ARMATURE = "inspect_armature"
TOOL_BIND_ARMATURE_MESH = "bind_armature_mesh"
TOOL_CONFIGURE_BONE_CONSTRAINT = "configure_bone_constraint"
TOOL_SCULPT_MESH = "sculpt_mesh"
TOOL_INSPECT_SCULPT_STATE = "inspect_sculpt_state"
TOOL_LOAD_REFERENCE_IMAGE = "load_reference_image"
TOOL_CROP_REFERENCE_IMAGE = "crop_reference_image"
TOOL_COMPARE_SILHOUETTE_ALIGNMENT = "compare_silhouette_alignment"
TOOL_CALIBRATE_REFERENCE_VIEWS = "calibrate_reference_views"
TOOL_OPTIMIZE_MESH_SILHOUETTE = "optimize_mesh_silhouette"
TOOL_FIT_MULTIVIEW_SILHOUETTE = "fit_multiview_silhouette"
TOOL_REFINE_MESH_MULTIRESOLUTION = "refine_mesh_multiresolution"
TOOL_SCULPT_ORGANIC_ANATOMY = "sculpt_organic_anatomy"
TOOL_CONFIGURE_SEMANTIC_LANDMARKS = "configure_semantic_landmarks"
TOOL_INSPECT_SEMANTIC_LANDMARKS = "inspect_semantic_landmarks"
TOOL_GUIDE_MESH_LANDMARKS = "guide_mesh_landmarks"
TOOL_DETAIL_SURFACE_FEATURES = "detail_surface_features"
TOOL_INSPECT_SURFACE_DETAIL = "inspect_surface_detail"
TOOL_CONFIGURE_ANATOMICAL_MASK = "configure_anatomical_mask"
TOOL_INSPECT_ANATOMICAL_MASK = "inspect_anatomical_mask"
TOOL_SYMMETRIZE_MESH_GEOMETRY = "symmetrize_mesh_geometry"
TOOL_DETECT_SEMANTIC_LANDMARKS = "detect_semantic_landmarks"
TOOL_BAKE_MESH_SURFACE_MAP = "bake_mesh_surface_map"
TOOL_BEVEL_MESH = "bevel_mesh"
TOOL_BEVEL_EDGES = "bevel_edges"
TOOL_SPLIT_MESH = "split_mesh"
TOOL_KNIFE_MESH = "knife_mesh"
TOOL_BISECT_MESH = "bisect_mesh"
TOOL_DISSOLVE_MESH = "dissolve_mesh"
TOOL_MERGE_MESH = "merge_mesh"
TOOL_RECALCULATE_NORMALS = "recalculate_normals"
TOOL_ALIGN_NORMALS = "align_normals"

# VSE Tool Identifiers
TOOL_INSPECT_VSE_TIMELINE = "inspect_vse_timeline"
TOOL_CREATE_VSE_STRIP = "create_vse_strip"
TOOL_MODIFY_VSE_STRIP = "modify_vse_strip"
TOOL_DELETE_VSE_STRIP = "delete_vse_strip"
TOOL_MANAGE_TIMELINE_MARKERS = "manage_timeline_markers"
TOOL_TRIM_VSE_STRIP = "trim_vse_strip"
TOOL_SPLIT_VSE_STRIP = "split_vse_strip"
TOOL_REORDER_VSE_STRIPS = "reorder_vse_strips"
TOOL_CREATE_VSE_TRANSITION = "create_vse_transition"
TOOL_CONFIGURE_VSE_EFFECT = "configure_vse_effect"
TOOL_CONFIGURE_VSE_AUDIO = "configure_vse_audio"
TOOL_MANAGE_VSE_SOUND_MODIFIERS = "manage_vse_sound_modifiers"
TOOL_TRANSFORM_VSE_STRIP = "transform_vse_strip"
TOOL_CROP_VSE_STRIP = "crop_vse_strip"
TOOL_ANIMATE_VSE_STRIP = "animate_vse_strip"
TOOL_MANAGE_VSE_STRIP_MODIFIERS = "manage_vse_strip_modifiers"
TOOL_CREATE_VSE_TEXT_STRIP = "create_vse_text_strip"
TOOL_CONFIGURE_VSE_TEXT_STYLE = "configure_vse_text_style"
TOOL_GROUP_VSE_META_STRIP = "group_vse_meta_strip"
TOOL_CREATE_VSE_SCENE_STRIP = "create_vse_scene_strip"
TOOL_RENDER_VSE_SEQUENCE = "render_vse_sequence"
TOOL_MIXDOWN_VSE_AUDIO = "mixdown_vse_audio"

# Capability 8 Environment and Architecture Tool Identifiers
TOOL_CREATE_CYCLORAMA = "create_cyclorama"
TOOL_SET_OBJECT_ORIGIN = "set_object_origin"
TOOL_CREATE_ROOM_ENCLOSURE = "create_room_enclosure"
TOOL_CREATE_ROOF_STRUCTURE = "create_roof_structure"
TOOL_CREATE_BUILDING_ENVELOPE = "create_building_envelope"
TOOL_CREATE_TERRAIN = "create_terrain"
TOOL_SCATTER_SURFACE_ASSETS = "scatter_surface_assets"
TOOL_SNAP_TO_GROUND = "snap_to_ground"
TOOL_ALIGN_OBJECT_GRID = "align_object_grid"
TOOL_BEGIN_ENVIRONMENT_TRANSACTION = "begin_environment_transaction"
TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION = "rollback_environment_transaction"
TOOL_COMMIT_ENVIRONMENT_TRANSACTION = "commit_environment_transaction"
TOOL_EXECUTE_ENVIRONMENT_WORKFLOW = "execute_environment_workflow"




# -------------------------------------------------------------------------
# Tool Definitions & Schemas conforming to MCP Tool Specification
# -------------------------------------------------------------------------

TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    TOOL_GET_SCENE_SUMMARY: {
        "name": TOOL_GET_SCENE_SUMMARY,
        "description": (
            "Retrieve high-level summary metadata about the active Blender scene: "
            "scene name, current frame, frame range, FPS, unit system, total object count, "
            "breakdown of objects by type (mesh, camera, light, armature, etc.), active camera, "
            "and active object."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "include_collections": {
                    "type": "boolean",
                    "description": "Whether to include a list of top-level collection names.",
                    "default": True,
                }
            },
            "additionalProperties": False,
        },
    },
    TOOL_LIST_OBJECTS: {
        "name": TOOL_LIST_OBJECTS,
        "description": (
            "List objects in the active scene with filtering, pagination, and structural hierarchy. "
            "Returns object names, types, associated collections, visibility, parent, and child count."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "description": "Optional object type filter (e.g. 'MESH', 'CAMERA', 'LIGHT', 'ARMATURE', 'EMPTY', 'CURVE').",
                },
                "collection_name": {
                    "type": "string",
                    "description": "Optional collection name filter. Only objects linked to this collection are returned.",
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Whether to include hidden or disabled objects.",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of objects to return (1 to 1000).",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of objects to skip for pagination.",
                    "default": 0,
                    "minimum": 0,
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_GET_OBJECT_DETAILS: {
        "name": TOOL_GET_OBJECT_DETAILS,
        "description": (
            "Retrieve detailed transform, geometric, and modifier data for a specific object by name: "
            "location, rotation (Euler), scale, bounding box, dimensions, parent, assigned collections, "
            "mesh vertex/polygon statistics (if mesh), assigned material names, and modifier stack."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact name of the object to inspect.",
                },
                "include_mesh_stats": {
                    "type": "boolean",
                    "description": "Whether to calculate vertex, edge, and polygon counts for mesh objects.",
                    "default": True,
                },
                "include_materials": {
                    "type": "boolean",
                    "description": "Whether to return names of materials linked to slots.",
                    "default": True,
                },
                "include_modifiers": {
                    "type": "boolean",
                    "description": "Whether to return the modifier stack summary.",
                    "default": True,
                },
                "include_custom_properties": {
                    "type": "boolean",
                    "description": "Whether to inspect custom properties stored on the object.",
                    "default": False,
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_LIST_MATERIALS: {
        "name": TOOL_LIST_MATERIALS,
        "description": (
            "List materials defined in the Blender file, including node usage, user counts, "
            "base diffuse color, metallic/roughness values, and linked image texture file names."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "filter_name": {
                    "type": "string",
                    "description": "Optional substring filter to match material names.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of materials to return.",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 500,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset.",
                    "default": 0,
                    "minimum": 0,
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CREATE_PRIMITIVE: {
        "name": TOOL_CREATE_PRIMITIVE,
        "description": (
            "Create a validated basic 3D primitive (cube, sphere, cylinder, plane) in the active Blender scene. "
            "Requires explicit user approval through a trusted approval mechanism to authorize scene modification. "
            "Client- or model-supplied approval flags in tool arguments are untrusted and cannot authorize mutations. "
            "Validates input geometry, prevents name collisions, and preserves existing scene objects."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "primitive_type": {
                    "type": "string",
                    "description": "Type of 3D primitive to create. Supported: 'cube', 'sphere', 'cylinder', 'plane', 'cone', 'torus', 'monkey', 'grid'.",
                    "enum": ["cube", "sphere", "cylinder", "plane", "cone", "torus", "monkey", "grid"],
                },
                "name": {
                    "type": "string",
                    "description": "Unique name for the new object. Must not collide with any existing object.",
                },
                "location": {
                    "type": "array",
                    "description": "3D world coordinates [x, y, z] for object placement.",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "default": [0.0, 0.0, 0.0],
                },
                "dimensions": {
                    "type": "array",
                    "description": "Size dimensions [x, y, z] in Blender units. Must be non-negative numbers. Optional; defaults to match primitive geometry.",
                    "items": {"type": "number", "minimum": 0.0},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "radius": {
                    "type": "number",
                    "description": "Radius in Blender units for sphere or cylinder primitive. Must be positive (0.0001 to 10000.0). Applies to 'sphere' (default 0.5) and 'cylinder' (default 0.5).",
                    "minimum": 0.0001,
                    "maximum": 10000.0,
                },
                "depth": {
                    "type": "number",
                    "description": "Height/depth in Blender units for cylinder primitive. Must be positive (0.0001 to 10000.0). Applies only to 'cylinder' (default 1.0).",
                    "minimum": 0.0001,
                    "maximum": 10000.0,
                },
                "size": {
                    "type": "number",
                    "description": "Edge length in Blender units for plane primitive. Must be positive (0.0001 to 10000.0). Applies only to 'plane' (default 1.0).",
                    "minimum": 0.0001,
                    "maximum": 10000.0,
                },
                "segments": {
                    "type": "integer",
                    "description": "Number of vertical segments for UV sphere. Range: 3 to 500. Applies only to 'sphere' (default 32).",
                    "minimum": 3,
                    "maximum": 500,
                },
                "ring_count": {
                    "type": "integer",
                    "description": "Number of horizontal rings for UV sphere. Range: 3 to 500. Applies only to 'sphere' (default 16).",
                    "minimum": 3,
                    "maximum": 500,
                },
                "vertices": {
                    "type": "integer",
                    "description": "Number of circular vertices for cylinder cross-section. Range: 3 to 500. Applies only to 'cylinder' (default 32).",
                    "minimum": 3,
                    "maximum": 500,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "required": ["primitive_type", "name"],
            "additionalProperties": False,
        },
    },
    TOOL_TRANSFORM_OBJECT: {
        "name": TOOL_TRANSFORM_OBJECT,
        "description": (
            "Transform an existing object in the active Blender scene by setting or offsetting "
            "its location, rotation (Euler in radians), and/or scale. "
            "Requires explicit user approval through a trusted approval mechanism to authorize scene modification. "
            "Client- or model-supplied approval flags in tool arguments are untrusted and cannot authorize mutations. "
            "Supports absolute transform assignment (default) or relative offset accumulation ('relative': True)."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact name of the existing object in the scene to transform.",
                },
                "bone_name": {
                    "type": "string",
                    "description": "Optional pose bone name if transforming an armature bone in pose mode.",
                },
                "location": {
                    "type": "array",
                    "description": "3D coordinates [x, y, z] in Blender units. When relative=False, sets absolute location; when relative=True, adds translation delta.",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "rotation_euler": {
                    "type": "array",
                    "description": "3D Euler rotation angles [rx, ry, rz] in radians. When relative=False, sets absolute rotation; when relative=True, adds angular delta.",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "scale": {
                    "type": "array",
                    "description": "3D scale factors [sx, sy, sz]. Must be positive numbers (>= 0.0001). When relative=False, sets absolute scale; when relative=True, multiplies current scale.",
                    "items": {"type": "number", "minimum": 0.0001},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "relative": {
                    "type": "boolean",
                    "description": "If True, transforms are applied relative to current object state (location += loc, rotation += rot, scale *= scale). Defaults to False (absolute assignment).",
                    "default": False,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_SCENE_DATA: {
        "name": TOOL_INSPECT_SCENE_DATA,
        "description": (
            "Inspect structured Blender scene data with an explicit, safe read-only allowlist. "
            "Supported categories: 'scene_summary', 'object_modifiers', 'object_materials', "
            "'mesh_topology', 'scene_hierarchy', 'world_settings', 'collection_tree', "
            "'render_settings', 'blender_info', 'uv_layers', 'render_result', 'cameras', 'camera_settings'. "
            "Arbitrary code execution and unapproved data access are strictly rejected."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category of scene data to inspect.",
                    "enum": [
                        "scene_summary",
                        "object_modifiers",
                        "object_materials",
                        "mesh_topology",
                        "scene_hierarchy",
                        "world_settings",
                        "collection_tree",
                        "render_settings",
                        "blender_info",
                        "uv_layers",
                        "render_result",
                        "compositor_pipeline",
                        "compositor_settings",
                        "cameras",
                        "camera_settings",
                    ],
                },
                "target_name": {
                    "type": "string",
                    "description": "Target object name in the active scene. Required for object-specific categories ('object_modifiers', 'object_materials', 'mesh_topology', 'uv_layers').",
                },
                "mesh_source": {
                    "type": "string", "enum": ["base", "evaluated"],
                    "description": "Indexed topology only. Base is editable source; evaluated is a temporary modifier result, freed after readback. Object Mode only; evaluated indices cannot authorize base-mesh edits.",
                },
                "expected_snapshot_id": {
                    "type": "string", "pattern": "^sha256:[0-9a-f]{64}$",
                    "description": "Indexed topology only: reject the page if geometry/source changed since this fingerprint."
                },
                "element_domain": {
                    "type": "string", "enum": ["vertices", "edges", "faces"],
                    "description": "Optional indexed base-mesh domain for mesh_topology only. Object Mode, active-scene mesh only. Omitting preserves count-only response. Local coordinates; indices are snapshot-local. Paginated with limit/offset; oversized snapshots/pages fail explicitly.",
                },
                "include_parameters": {
                    "type": "boolean",
                    "description": "Whether to include detailed property values for modifiers/materials.",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum items for collection/hierarchy or indexed mesh queries.",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 100,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset for collection/hierarchy or indexed mesh queries.",
                    "minimum": 0,
                    "default": 0,
                },
            },
            "required": ["category"],
            "additionalProperties": False,
        },
    },
    TOOL_EXECUTE_BLENDER_CODE: {
        "name": TOOL_EXECUTE_BLENDER_CODE,
        "description": (
            "Safely execute structured modeling operations or restricted AST-validated Blender Python code. "
            "All mutations require explicit trusted human approval in Blender and execute transactionally "
            "with automatic undo rollback on failure. Unrestricted eval/exec is prohibited. "
            "Supports operations: 'add_modifier', 'modify_modifier', 'remove_modifier', 'set_shade_mode', "
            "'subdivide_mesh', 'create_material', 'assign_material', 'parent_object', 'join_objects'."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "description": "List of structured modeling operations to execute sequentially within a single transaction.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "The modeling operation to perform.",
                                "enum": [
                                    "add_modifier",
                                    "modify_modifier",
                                    "remove_modifier",
                                    "set_shade_mode",
                                    "subdivide_mesh",
                                    "create_material",
                                    "assign_material",
                                    "parent_object",
                                    "join_objects",
                                ],
                            },
                            "target": {
                                "type": "string",
                                "description": "Target object name in the active scene.",
                            },
                            "params": {
                                "type": "object",
                                "description": "Action-specific parameters dictionary.",
                            },
                        },
                        "required": ["action"],
                    },
                },
                "code": {
                    "type": "string",
                    "description": "Optional Python modeling script strictly restricted to allowlisted bpy operations. Must pass static AST security validation.",
                },
                "transactional": {
                    "type": "boolean",
                    "description": "Whether to wrap execution in a Blender undo transaction to roll back on any error. Defaults to True.",
                    "default": True,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CREATE_MATERIAL: {
        "name": TOOL_CREATE_MATERIAL,
        "description": (
            "Create a verified Principled BSDF material in the active Blender session with configurable "
            "PBR properties (base color, roughness, metallic, ior, alpha, specular)."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the new material.",
                },
                "base_color": {
                    "type": "array",
                    "description": "Base color RGBA or RGB list [r, g, b, (a)] with values between 0.0 and 1.0.",
                    "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "minItems": 3,
                    "maxItems": 4,
                    "default": [0.8, 0.8, 0.8, 1.0],
                },
                "roughness": {
                    "type": "number",
                    "description": "Surface roughness (0.0 = mirror smooth, 1.0 = completely diffuse).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.5,
                },
                "metallic": {
                    "type": "number",
                    "description": "Metallic reflectivity (0.0 = dielectric, 1.0 = full metallic).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                },
                "ior": {
                    "type": "number",
                    "description": "Index of Refraction for dielectric transmission/Fresnel (default 1.45).",
                    "minimum": 0.0,
                    "maximum": 5.0,
                    "default": 1.45,
                },
                "alpha": {
                    "type": "number",
                    "description": "Transparency/alpha value (0.0 = invisible, 1.0 = opaque).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 1.0,
                },
                "specular": {
                    "type": "number",
                    "description": "Specular reflectance level (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.5,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_ASSIGN_MATERIAL: {
        "name": TOOL_ASSIGN_MATERIAL,
        "description": (
            "Assign an existing material to an object in the active scene, optionally targeting a specific material slot index."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "Target object name to assign the material to.",
                },
                "material_name": {
                    "type": "string",
                    "description": "Name of the existing material in the scene.",
                },
                "slot_index": {
                    "type": "integer",
                    "description": "Optional material slot index to assign into. If omitted or beyond existing slots, a new slot is appended.",
                    "minimum": 0,
                },
                "face_indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "description": "Optional list of polygon/face indices to assign to this material slot.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "required": ["target_name", "material_name"],
            "additionalProperties": False,
        },
    },
    TOOL_CREATE_LIGHT: {
        "name": TOOL_CREATE_LIGHT,
        "description": (
            "Create and position a light source in the active scene (Point, Sun, Spot, Area) "
            "with configurable energy, color, and transform."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the light object.",
                },
                "light_type": {
                    "type": "string",
                    "description": "Type of light source: POINT, SUN, SPOT, or AREA.",
                    "enum": ["POINT", "SUN", "SPOT", "AREA"],
                    "default": "POINT",
                },
                "energy": {
                    "type": "number",
                    "description": "Light power/energy in Watts (for Sun, typical values are 1-10).",
                    "minimum": 0.0,
                    "default": 1000.0,
                },
                "color": {
                    "type": "array",
                    "description": "RGB light color components [r, g, b] normalized to 0.0-1.0.",
                    "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "minItems": 3,
                    "maxItems": 3,
                    "default": [1.0, 1.0, 1.0],
                },
                "location": {
                    "type": "array",
                    "description": "3D world location coordinates [x, y, z].",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "default": [0.0, 0.0, 5.0],
                },
                "rotation_euler": {
                    "type": "array",
                    "description": "Euler rotation angles in radians [rx, ry, rz].",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "default": [0.0, 0.0, 0.0],
                },
                "spot_size": {
                    "type": "number",
                    "description": "Cone angle in radians for SPOT lights (0.0 to 3.1416).",
                    "minimum": 0.0,
                    "maximum": 3.1416,
                },
                "size": {
                    "type": "number",
                    "description": "Size or radius for AREA and POINT lights in meters.",
                    "minimum": 0.0,
                },
                "shape": {
                    "type": "string",
                    "description": "Shape for AREA lights: 'SQUARE', 'RECTANGLE', 'DISK', or 'ELLIPSE'.",
                    "enum": ["SQUARE", "RECTANGLE", "DISK", "ELLIPSE"],
                    "default": "SQUARE",
                },
                "size_y": {
                    "type": "number",
                    "description": "Secondary Y dimension in meters for RECTANGLE and ELLIPSE AREA lights (>= 0.0).",
                    "minimum": 0.0,
                },
                "diffuse_factor": {
                    "type": "number",
                    "description": "Diffuse reflection contribution factor multiplier (>= 0.0).",
                    "minimum": 0.0,
                    "default": 1.0,
                },
                "specular_factor": {
                    "type": "number",
                    "description": "Specular reflection contribution factor multiplier (>= 0.0).",
                    "minimum": 0.0,
                    "default": 1.0,
                },
                "volume_factor": {
                    "type": "number",
                    "description": "Volume scattering contribution factor multiplier (>= 0.0).",
                    "minimum": 0.0,
                    "default": 1.0,
                },
                "use_shadow": {
                    "type": "boolean",
                    "description": "Whether this light casts shadows in render calculations.",
                    "default": True,
                },
                "shadow_soft_size": {
                    "type": "number",
                    "description": "Light size for shadow softness radius in meters (>= 0.0).",
                    "minimum": 0.0,
                },
                "shadow_buffer_clip_start": {
                    "type": "number",
                    "description": "Near clipping distance for shadow buffer evaluation in meters (>= 0.0001).",
                    "minimum": 0.0001,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_LIGHT: {
        "name": TOOL_CONFIGURE_LIGHT,
        "description": (
            "Configure properties and transform of an existing light source in the active scene "
            "(Point, Sun, Spot, Area). Updates energy, color, location, rotation, spot size/blend, and area size."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name of the existing light object.",
                },
                "light_type": {
                    "type": "string",
                    "description": "Type of light source: POINT, SUN, SPOT, or AREA.",
                    "enum": ["POINT", "SUN", "SPOT", "AREA"],
                },
                "energy": {
                    "type": "number",
                    "description": "Light power/energy in Watts (for Sun, typical values are 1-10). Must be non-negative.",
                    "minimum": 0.0,
                },
                "color": {
                    "type": "array",
                    "description": "RGB light color components [r, g, b] normalized to 0.0-1.0.",
                    "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "location": {
                    "type": "array",
                    "description": "3D world location coordinates [x, y, z].",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "rotation_euler": {
                    "type": "array",
                    "description": "Euler rotation angles in radians [rx, ry, rz].",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "spot_size": {
                    "type": "number",
                    "description": "Cone angle in radians for SPOT lights (0.0 to 3.1416).",
                    "minimum": 0.0,
                    "maximum": 3.1416,
                },
                "spot_blend": {
                    "type": "number",
                    "description": "Soft edge blend factor for SPOT lights (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "size": {
                    "type": "number",
                    "description": "Size or radius for AREA and POINT lights in meters.",
                    "minimum": 0.0,
                },
                "shape": {
                    "type": "string",
                    "description": "Shape for AREA lights: 'SQUARE', 'RECTANGLE', 'DISK', or 'ELLIPSE'.",
                    "enum": ["SQUARE", "RECTANGLE", "DISK", "ELLIPSE"],
                    "default": "SQUARE",
                },
                "size_y": {
                    "type": "number",
                    "description": "Secondary Y dimension in meters for RECTANGLE and ELLIPSE AREA lights (>= 0.0).",
                    "minimum": 0.0,
                },
                "diffuse_factor": {
                    "type": "number",
                    "description": "Diffuse reflection contribution factor multiplier (>= 0.0).",
                    "minimum": 0.0,
                    "default": 1.0,
                },
                "specular_factor": {
                    "type": "number",
                    "description": "Specular reflection contribution factor multiplier (>= 0.0).",
                    "minimum": 0.0,
                    "default": 1.0,
                },
                "volume_factor": {
                    "type": "number",
                    "description": "Volume scattering contribution factor multiplier (>= 0.0).",
                    "minimum": 0.0,
                    "default": 1.0,
                },
                "use_shadow": {
                    "type": "boolean",
                    "description": "Whether this light casts shadows in render calculations.",
                    "default": True,
                },
                "shadow_soft_size": {
                    "type": "number",
                    "description": "Light size for shadow softness radius in meters (>= 0.0).",
                    "minimum": 0.0,
                },
                "shadow_buffer_clip_start": {
                    "type": "number",
                    "description": "Near clipping distance for shadow buffer evaluation in meters (>= 0.0001).",
                    "minimum": 0.0001,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_WORLD: {
        "name": TOOL_CONFIGURE_WORLD,
        "description": (
            "Configure the active world background settings (color, strength, and node-tree activation)."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "color": {
                    "type": "array",
                    "description": "RGB background color components [r, g, b] normalized to 0.0-1.0.",
                    "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "minItems": 3,
                    "maxItems": 3,
                    "default": [0.05, 0.05, 0.05],
                },
                "strength": {
                    "type": "number",
                    "description": "Background emission strength multiplier (>= 0.0).",
                    "minimum": 0.0,
                    "default": 1.0,
                },
                "use_nodes": {
                    "type": "boolean",
                    "description": "Whether the world shader uses an active node tree.",
                    "default": True,
                },
                "environment_image": {
                    "type": "string",
                    "description": "Optional image datablock name or absolute filepath to bind to an environment texture background node.",
                },
                "sky_type": {
                    "type": "string",
                    "description": "Optional physical sky model type: 'MULTIPLE_SCATTERING' (Nishita Multiple Scattering), 'SINGLE_SCATTERING', 'PREETHAM', 'HOSEK_WILKIE', or 'NISHITA' (alias for MULTIPLE_SCATTERING).",
                    "enum": ["MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "PREETHAM", "HOSEK_WILKIE", "NISHITA"],
                },
                "sun_disc": {
                    "type": "boolean",
                    "description": "Whether to render the visible sun disc in the physical sky (Nishita).",
                    "default": True,
                },
                "sun_size": {
                    "type": "number",
                    "description": "Angular diameter of the sun disc in radians [0.0 to 1.5708] (Nishita). Default ~0.009512 rad (0.545 deg).",
                    "minimum": 0.0,
                    "maximum": 1.570796,
                },
                "sun_intensity": {
                    "type": "number",
                    "description": "Multiplier for the sun disc brightness (>= 0.0, default 1.0) (Nishita).",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                },
                "sun_elevation": {
                    "type": "number",
                    "description": "Solar elevation angle above the horizon in radians [-1.5708 to 1.5708] (Nishita). Default ~0.2618 rad (15 deg).",
                    "minimum": -1.570796,
                    "maximum": 1.570796,
                },
                "sun_rotation": {
                    "type": "number",
                    "description": "Solar azimuth rotation angle in radians [-6.2832 to 6.2832] (Nishita). Default 0.0.",
                    "minimum": -6.283185,
                    "maximum": 6.283185,
                },
                "altitude": {
                    "type": "number",
                    "description": "Observer altitude above sea level in meters [0.0 to 100000.0] (Nishita). Default 100.0.",
                    "minimum": 0.0,
                    "maximum": 100000.0,
                },
                "air_density": {
                    "type": "number",
                    "description": "Air molecule density multiplier (Rayleigh scattering) [0.0 to 1000.0] (Nishita). Default 1.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                },
                "aerosol_density": {
                    "type": "number",
                    "description": "Aerosol / haze / dust particle density multiplier (Mie scattering) [0.0 to 1000.0] (Nishita). Default 1.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                },
                "ozone_density": {
                    "type": "number",
                    "description": "Ozone layer density multiplier (Ozone absorption) [0.0 to 1000.0] (Nishita). Default 1.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                },
                "turbidity": {
                    "type": "number",
                    "description": "Atmospheric turbidity [1.0 to 10.0] for Preetham/Hosek-Wilkie models. Default 2.2.",
                    "minimum": 1.0,
                    "maximum": 10.0,
                },
                "ground_albedo": {
                    "type": "number",
                    "description": "Ground albedo reflection factor [0.0 to 1.0] for Preetham/Hosek-Wilkie models. Default 0.3.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "environment_rotation": {
                    "description": "Rotation for the environment texture (HDRI) or background mapping. Either a single float (rotation angle around Z-axis in radians) or a 3-element list [rx, ry, rz] in radians.",
                    "oneOf": [
                        {"type": "number"},
                        {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
                    ],
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CAPTURE_VIEWPORT: {
        "name": TOOL_CAPTURE_VIEWPORT,
        "description": (
            "Capture a bounded visual snapshot of the 3D viewport or active camera without mutating "
            "scene state or persistent render settings. Returns base64 PNG data."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "width": {
                    "type": "integer",
                    "description": "Image resolution width in pixels (bounded 64 to 2048).",
                    "minimum": 64,
                    "maximum": 2048,
                    "default": 512,
                },
                "height": {
                    "type": "integer",
                    "description": "Image resolution height in pixels (bounded 64 to 2048).",
                    "minimum": 64,
                    "maximum": 2048,
                    "default": 512,
                },
                "mode": {
                    "type": "string",
                    "description": "Capture viewpoint: active interactive 3D viewport ('VIEWPORT') or scene active camera ('CAMERA').",
                    "enum": ["VIEWPORT", "CAMERA"],
                    "default": "VIEWPORT",
                },
                "format": {
                    "type": "string",
                    "description": "Output image format (PNG only).",
                    "enum": ["PNG"],
                    "default": "PNG",
                },
                "view": {
                    "type": "string",
                    "description": "Viewpoint projection or angle: 'CURRENT' (default), 'FRONT', 'SIDE', 'TOP', or 'PERSPECTIVE'. Supported in interactive 3D Viewport or via directional camera capture.",
                    "enum": ["CURRENT", "FRONT", "SIDE", "TOP", "PERSPECTIVE"],
                    "default": "CURRENT",
                },
                "samples": {
                    "type": "integer",
                    "description": "Render sample count for capture (bounded 1 to 64).",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 1,
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CHECK_APPROVAL_STATUS: {
        "name": TOOL_CHECK_APPROVAL_STATUS,
        "description": (
            "Read authoritative Blender approval-request metadata without approving, resuming, or "
            "consuming authorization. Returns token-free request state and token_consumed; "
            "approval or token consumption does not prove successful task execution."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "minLength": 1, "description": "Exact Blender approval request ID."},
            },
            "required": ["request_id"],
            "additionalProperties": False,
        },
    },
    TOOL_GET_TASK_STATUS: {
        "name": TOOL_GET_TASK_STATUS,
        "description": (
            "Read the stored status and sanitized outcome of an Agent Manager task in a session. "
            "For tasks awaiting approval, reports the local approval binding as unverified (or expired "
            "from its recorded deadline); it does not claim Blender still has a pending request."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Unique Agent Manager task identifier.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session that owns the task.",
                    "default": "default",
                },
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    TOOL_RESOLVE_PENDING_APPROVAL: {
        "name": TOOL_RESOLVE_PENDING_APPROVAL,
        "description": (
            "Resume or deny a pending scene mutation task. An approval decision only resumes the task if "
            "Blender's approval registry has already recorded an explicit human approval and issued its token; "
            "resolver credentials alone never authorize a mutation. "
            "Requires the exact task_id, session_id, cryptographic single-use nonce, canonical param_hash, "
            "and decision ('approved' or 'denied'). Resumes the original pending task exactly once upon approval."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Unique identifier of the pending AgentTask paused in AWAITING_APPROVAL.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID scoping the pending task.",
                    "default": "default",
                },
                "decision": {
                    "type": "string",
                    "description": "Resolution request: 'approved' resumes only after Blender UI approval; 'denied' cancels the task.",
                    "enum": ["approved", "denied"],
                },
                "nonce": {
                    "type": "string",
                    "description": "Single-use cryptographic nonce issued when the task was paused.",
                },
                "param_hash": {
                    "type": "string",
                    "description": "Canonical SHA-256 hash of the pending tool parameters.",
                },
                "auth_token": {
                    "type": "string",
                    "description": "Optional authentication token if UMCP_AUTH_TOKEN is configured.",
                },
            },
            "required": ["task_id", "decision", "nonce", "param_hash"],
            "additionalProperties": False,
        },
    },
    TOOL_CREATE_CAMERA: {
        "name": TOOL_CREATE_CAMERA,
        "description": (
            "Create a new camera in the active Blender scene with configurable focal length (lens), "
            "clipping planes, sensor width, and world transform. Can automatically set the new camera as active."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the new camera object.",
                },
                "location": {
                    "type": "array",
                    "description": "3D world coordinates [x, y, z] for camera placement.",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "default": [0.0, -5.0, 2.0],
                },
                "rotation_euler": {
                    "type": "array",
                    "description": "Euler rotation angles in radians [rx, ry, rz].",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "default": [1.1, 0.0, 0.0],
                },
                "lens": {
                    "type": "number",
                    "description": "Focal length in millimeters (1.0 to 5000.0).",
                    "minimum": 1.0,
                    "maximum": 5000.0,
                    "default": 50.0,
                },
                "clip_start": {
                    "type": "number",
                    "description": "Near clipping distance in Blender units (> 0.0001).",
                    "minimum": 0.0001,
                    "default": 0.1,
                },
                "clip_end": {
                    "type": "number",
                    "description": "Far clipping distance in Blender units.",
                    "minimum": 0.01,
                    "default": 1000.0,
                },
                "sensor_width": {
                    "type": "number",
                    "description": "Camera sensor width in millimeters (1.0 to 200.0).",
                    "minimum": 1.0,
                    "maximum": 200.0,
                    "default": 36.0,
                },
                "set_active": {
                    "type": "boolean",
                    "description": "Whether to assign this camera as the active scene camera.",
                    "default": True,
                },
                "camera_type": {
                    "type": "string",
                    "description": "Camera projection type: 'PERSP' (Perspective), 'ORTHO' (Orthographic), or 'PANO' (Panoramic).",
                    "enum": ["PERSP", "ORTHO", "PANO"],
                    "default": "PERSP",
                },
                "type": {
                    "type": "string",
                    "description": "Alias for camera projection type: 'PERSP', 'ORTHO', or 'PANO'.",
                    "enum": ["PERSP", "ORTHO", "PANO"],
                },
                "focal_length": {
                    "type": "number",
                    "description": "Focal length in millimeters (alias for lens).",
                    "minimum": 1.0,
                    "maximum": 5000.0,
                    "default": 50.0,
                },
                "ortho_scale": {
                    "type": "number",
                    "description": "Orthographic scale factor for ORTHO cameras (> 0.001 to 10000.0).",
                    "minimum": 0.001,
                    "maximum": 10000.0,
                    "default": 6.0,
                },
                "sensor_height": {
                    "type": "number",
                    "description": "Camera sensor height in millimeters (1.0 to 200.0).",
                    "minimum": 1.0,
                    "maximum": 200.0,
                    "default": 24.0,
                },
                "sensor_fit": {
                    "type": "string",
                    "description": "Sensor fit mode: 'AUTO', 'HORIZONTAL', or 'VERTICAL'.",
                    "enum": ["AUTO", "HORIZONTAL", "VERTICAL"],
                    "default": "AUTO",
                },
                "shift_x": {
                    "type": "number",
                    "description": "Horizontal camera shift (-10.0 to 10.0).",
                    "minimum": -10.0,
                    "maximum": 10.0,
                    "default": 0.0,
                },
                "shift_y": {
                    "type": "number",
                    "description": "Vertical camera shift (-10.0 to 10.0).",
                    "minimum": -10.0,
                    "maximum": 10.0,
                    "default": 0.0,
                },
                "dof": {
                    "type": "object",
                    "description": "Depth of field settings.",
                    "properties": {
                        "use_dof": {"type": "boolean", "description": "Enable depth of field."},
                        "focus_distance": {"type": "number", "minimum": 0.001, "description": "Focus distance in meters."},
                        "aperture_fstop": {"type": "number", "minimum": 0.1, "maximum": 128.0, "description": "Aperture f-stop number."},
                        "focus_object": {"type": ["string", "null"], "description": "Target object name for dynamic depth of field focus point."},
                    },
                },
                "use_dof": {
                    "type": "boolean",
                    "description": "Enable depth of field.",
                    "default": False,
                },
                "focus_distance": {
                    "type": "number",
                    "description": "Focus distance in meters.",
                    "minimum": 0.001,
                    "default": 10.0,
                },
                "aperture_fstop": {
                    "type": "number",
                    "description": "Aperture f-stop number.",
                    "minimum": 0.1,
                    "maximum": 128.0,
                    "default": 2.8,
                },
                "track_to_object": {
                    "type": ["string", "null"],
                    "description": "Target object name for camera to track using a TRACK_TO constraint. Pass null or empty string to disable tracking.",
                },
                "focus_object": {
                    "type": ["string", "null"],
                    "description": "Target object name for dynamic depth-of-field focus point. Pass null or empty string to disable focus target.",
                },
                "show_composition_thirds": {
                    "type": "boolean",
                    "description": "Display rule-of-thirds composition guide grid in the camera viewport.",
                    "default": False,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_CAMERA: {
        "name": TOOL_CONFIGURE_CAMERA,
        "description": (
            "Configure properties and transform of an existing camera in the active Blender scene. "
            "Updates focal length (lens), projection type (PERSP, ORTHO, PANO), orthographic scale, "
            "clipping planes (clip_start, clip_end), sensor dimensions (sensor_width, sensor_height, sensor_fit), "
            "shift (shift_x, shift_y), depth of field (use_dof, focus_distance, aperture_fstop), "
            "3D transform (location, rotation), and active camera assignment."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the existing camera object to configure.",
                },
                "target_name": {
                    "type": "string",
                    "description": "Alias for name of the camera object.",
                },
                "camera_name": {
                    "type": "string",
                    "description": "Alias for name of the camera object.",
                },
                "camera_type": {
                    "type": "string",
                    "description": "Camera projection type: 'PERSP' (Perspective), 'ORTHO' (Orthographic), or 'PANO' (Panoramic).",
                    "enum": ["PERSP", "ORTHO", "PANO"],
                },
                "type": {
                    "type": "string",
                    "description": "Alias for camera projection type: 'PERSP', 'ORTHO', or 'PANO'.",
                    "enum": ["PERSP", "ORTHO", "PANO"],
                },
                "lens": {
                    "type": "number",
                    "description": "Focal length in millimeters (1.0 to 5000.0).",
                    "minimum": 1.0,
                    "maximum": 5000.0,
                },
                "focal_length": {
                    "type": "number",
                    "description": "Focal length in millimeters (alias for lens).",
                    "minimum": 1.0,
                    "maximum": 5000.0,
                },
                "ortho_scale": {
                    "type": "number",
                    "description": "Orthographic scale factor for ORTHO cameras (> 0.001 to 10000.0).",
                    "minimum": 0.001,
                    "maximum": 10000.0,
                },
                "clip_start": {
                    "type": "number",
                    "description": "Near clipping distance in Blender units (> 0.0001).",
                    "minimum": 0.0001,
                },
                "clip_end": {
                    "type": "number",
                    "description": "Far clipping distance in Blender units (> clip_start).",
                    "minimum": 0.001,
                },
                "sensor_width": {
                    "type": "number",
                    "description": "Camera sensor width in millimeters (1.0 to 200.0).",
                    "minimum": 1.0,
                    "maximum": 200.0,
                },
                "sensor_height": {
                    "type": "number",
                    "description": "Camera sensor height in millimeters (1.0 to 200.0).",
                    "minimum": 1.0,
                    "maximum": 200.0,
                },
                "sensor_fit": {
                    "type": "string",
                    "description": "Sensor fit mode: 'AUTO', 'HORIZONTAL', or 'VERTICAL'.",
                    "enum": ["AUTO", "HORIZONTAL", "VERTICAL"],
                },
                "shift_x": {
                    "type": "number",
                    "description": "Horizontal camera shift (-10.0 to 10.0).",
                    "minimum": -10.0,
                    "maximum": 10.0,
                },
                "shift_y": {
                    "type": "number",
                    "description": "Vertical camera shift (-10.0 to 10.0).",
                    "minimum": -10.0,
                    "maximum": 10.0,
                },
                "dof": {
                    "type": "object",
                    "description": "Depth of field settings.",
                    "properties": {
                        "use_dof": {"type": "boolean", "description": "Enable depth of field."},
                        "focus_distance": {"type": "number", "minimum": 0.001, "description": "Focus distance in meters."},
                        "aperture_fstop": {"type": "number", "minimum": 0.1, "maximum": 128.0, "description": "Aperture f-stop number."},
                        "focus_object": {"type": ["string", "null"], "description": "Target object name for dynamic depth of field focus point."},
                    },
                },
                "use_dof": {
                    "type": "boolean",
                    "description": "Enable depth of field.",
                },
                "focus_distance": {
                    "type": "number",
                    "description": "Focus distance in meters.",
                    "minimum": 0.001,
                },
                "aperture_fstop": {
                    "type": "number",
                    "description": "Aperture f-stop number.",
                    "minimum": 0.1,
                    "maximum": 128.0,
                },
                "track_to_object": {
                    "type": ["string", "null"],
                    "description": "Target object name for camera to track using a TRACK_TO constraint. Pass null or empty string to remove tracking constraint.",
                },
                "focus_object": {
                    "type": ["string", "null"],
                    "description": "Target object name for dynamic depth-of-field focus point. Pass null or empty string to clear focus object.",
                },
                "show_composition_thirds": {
                    "type": "boolean",
                    "description": "Display rule-of-thirds composition guide grid in the camera viewport.",
                },
                "location": {
                    "type": "array",
                    "description": "3D world location coordinates [x, y, z].",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "rotation_euler": {
                    "type": "array",
                    "description": "Euler rotation angles in radians [rx, ry, rz].",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "set_active": {
                    "type": "boolean",
                    "description": "Whether to set this camera as the active scene camera.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_SWITCH_CAMERA: {
        "name": TOOL_SWITCH_CAMERA,
        "description": (
            "Switch the active scene camera in the active Blender scene. "
            "Designates the specified camera object as scene.camera. "
            "Validates that the target object exists and is of type CAMERA."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "camera_name": {
                    "type": "string",
                    "description": "Name of the existing camera object to designate as the active scene camera.",
                },
                "name": {
                    "type": "string",
                    "description": "Alias for camera_name.",
                },
                "target_name": {
                    "type": "string",
                    "description": "Alias for camera_name.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent. Mutations must be approved through a trusted approval mechanism.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier for grouping related scene mutation operations.",
                },
            },
            "anyOf": [
                {"required": ["camera_name"]},
                {"required": ["name"]},
                {"required": ["target_name"]},
            ],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_RENDER_SETTINGS: {
        "name": TOOL_CONFIGURE_RENDER_SETTINGS,
        "description": (
            "Configure active render settings: render engine ('BLENDER_EEVEE_NEXT', 'CYCLES', 'BLENDER_WORKBENCH'), "
            "resolution dimensions, percentage, frame range, FPS, output image format, output path, and active camera."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "engine": {
                    "type": "string",
                    "description": "Render engine: 'BLENDER_EEVEE_NEXT', 'CYCLES', or 'BLENDER_WORKBENCH'.",
                    "enum": ["BLENDER_EEVEE_NEXT", "CYCLES", "BLENDER_WORKBENCH"],
                },
                "resolution_x": {
                    "type": "integer",
                    "description": "Render resolution width in pixels (1 to 65536).",
                    "minimum": 1,
                    "maximum": 65536,
                },
                "resolution_y": {
                    "type": "integer",
                    "description": "Render resolution height in pixels (1 to 65536).",
                    "minimum": 1,
                    "maximum": 65536,
                },
                "resolution_percentage": {
                    "type": "integer",
                    "description": "Render resolution scaling percentage (1 to 1000).",
                    "minimum": 1,
                    "maximum": 1000,
                },
                "frame_start": {
                    "type": "integer",
                    "description": "Animation timeline start frame.",
                },
                "frame_end": {
                    "type": "integer",
                    "description": "Animation timeline end frame.",
                },
                "frame_current": {
                    "type": "integer",
                    "description": "Animation timeline current frame or playhead position to evaluate.",
                },
                "fps": {
                    "type": "integer",
                    "description": "Frames per second (1 to 240).",
                    "minimum": 1,
                    "maximum": 240,
                },
                "fps_base": {
                    "type": "number",
                    "description": "Framerate base divisor (e.g., 1.001 for 23.976 fps).",
                    "minimum": 0.001,
                },
                "output_format": {
                    "type": "string",
                    "description": "Output image file format ('PNG', 'JPEG', 'OPEN_EXR', 'TARGA', 'TIFF').",
                    "enum": ["PNG", "JPEG", "OPEN_EXR", "TARGA", "TIFF"],
                },
                "output_path": {
                    "type": "string",
                    "description": "Configured render output filepath or directory (e.g. '//render/' or absolute path).",
                },
                "color_mode": {
                    "type": "string",
                    "description": "Image color mode ('BW', 'RGB', 'RGBA'). Compatibility depends on output_format.",
                    "enum": ["BW", "RGB", "RGBA"],
                },
                "color_depth": {
                    "type": "string",
                    "description": "Bit depth per channel ('8', '16', '32'). Supported depths depend on output_format.",
                    "enum": ["8", "16", "32"],
                },
                "compression": {
                    "type": "integer",
                    "description": "Image compression level percentage (0 to 100) for formats like PNG and OPEN_EXR.",
                    "minimum": 0,
                    "maximum": 100,
                },
                "quality": {
                    "type": "integer",
                    "description": "Image quality percentage (1 to 100) for lossy formats like JPEG and WEBP.",
                    "minimum": 1,
                    "maximum": 100,
                },
                "active_camera": {
                    "type": "string",
                    "description": "Name of camera object in scene to designate as active camera.",
                },
                "cycles_samples": {
                    "type": "integer",
                    "description": "Render sample count for Cycles engine.",
                    "minimum": 1,
                    "maximum": 65536,
                },
                "cycles_device": {
                    "type": "string",
                    "description": "Device type for Cycles rendering ('CPU' or 'GPU').",
                    "enum": ["CPU", "GPU"],
                },
                "film_transparent": {
                    "type": "boolean",
                    "description": "Whether to render background transparent with alpha channel.",
                },
                "view_transform": {
                    "type": "string",
                    "description": "Color management view transform preset.",
                    "enum": ["Standard", "ACES 1.3", "ACES 2.0", "Khronos PBR Neutral", "AgX", "Filmic", "Filmic Log", "False Color", "Raw"],
                },
                "look": {
                    "type": "string",
                    "description": "Color management look contrast preset.",
                    "enum": [
                        "None", "Very Low Contrast", "Low Contrast", "Medium Low Contrast", "Medium Contrast", "Medium High Contrast", "High Contrast", "Very High Contrast",
                        "AgX - Very Low Contrast", "AgX - Low Contrast", "AgX - Medium Low Contrast", "AgX - Base Contrast", "AgX - Medium High Contrast", "AgX - High Contrast", "AgX - Very High Contrast", "AgX - Punchy", "AgX - Greyscale", "Punchy"
                    ],
                },
                "exposure": {
                    "type": "number",
                    "description": "Color management exposure adjustment in EV (-32.0 to 32.0).",
                    "minimum": -32.0,
                    "maximum": 32.0,
                },
                "gamma": {
                    "type": "number",
                    "description": "Color management display gamma adjustment (-32.0 to 32.0, default 1.0).",
                    "minimum": -32.0,
                    "maximum": 32.0,
                },
                "color_management": {
                    "type": "object",
                    "description": "Color management settings bundle.",
                    "properties": {
                        "view_transform": {
                            "type": "string",
                            "enum": ["Standard", "ACES 1.3", "ACES 2.0", "Khronos PBR Neutral", "AgX", "Filmic", "Filmic Log", "False Color", "Raw"],
                        },
                        "look": {
                            "type": "string",
                            "enum": [
                                "None", "Very Low Contrast", "Low Contrast", "Medium Low Contrast", "Medium Contrast", "Medium High Contrast", "High Contrast", "Very High Contrast",
                                "AgX - Very Low Contrast", "AgX - Low Contrast", "AgX - Medium Low Contrast", "AgX - Base Contrast", "AgX - Medium High Contrast", "AgX - High Contrast", "AgX - Very High Contrast", "AgX - Punchy", "AgX - Greyscale", "Punchy"
                            ],
                        },
                        "exposure": {
                            "type": "number",
                            "minimum": -32.0,
                            "maximum": 32.0,
                        },
                        "gamma": {
                            "type": "number",
                            "minimum": -32.0,
                            "maximum": 32.0,
                        },
                    },
                },
                "use_denoising": {
                    "type": "boolean",
                    "description": "Enable denoising for Cycles render engine.",
                },
                "denoiser": {
                    "type": "string",
                    "description": "Denoising algorithm for Cycles ('OPENIMAGEDENOISE' or 'OPTIX').",
                    "enum": ["OPENIMAGEDENOISE", "OPTIX"],
                },
                "max_bounces": {
                    "type": "integer",
                    "description": "Total maximum light bounces for Cycles render (0 to 1024).",
                    "minimum": 0,
                    "maximum": 1024,
                },
                "diffuse_bounces": {
                    "type": "integer",
                    "description": "Maximum diffuse light bounces for Cycles render (0 to 1024).",
                    "minimum": 0,
                    "maximum": 1024,
                },
                "glossy_bounces": {
                    "type": "integer",
                    "description": "Maximum glossy/specular light bounces for Cycles render (0 to 1024).",
                    "minimum": 0,
                    "maximum": 1024,
                },
                "transmission_bounces": {
                    "type": "integer",
                    "description": "Maximum transmission light bounces for Cycles render (0 to 1024).",
                    "minimum": 0,
                    "maximum": 1024,
                },
                "volume_bounces": {
                    "type": "integer",
                    "description": "Maximum volume light bounces for Cycles render (0 to 1024).",
                    "minimum": 0,
                    "maximum": 1024,
                },
                "transparent_max_bounces": {
                    "type": "integer",
                    "description": "Maximum transparent light bounces for Cycles render (0 to 1024).",
                    "minimum": 0,
                    "maximum": 1024,
                },
                "time_limit": {
                    "type": "number",
                    "description": "Render time limit in seconds for Cycles engine (0.0 = unlimited).",
                    "minimum": 0.0,
                },
                "use_adaptive_sampling": {
                    "type": "boolean",
                    "description": "Enable adaptive sampling for Cycles render engine.",
                },
                "adaptive_threshold": {
                    "type": "number",
                    "description": "Noise threshold for Cycles adaptive sampling (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "adaptive_min_samples": {
                    "type": "integer",
                    "description": "Minimum samples before adaptive sampling begins for Cycles (0 to 65536).",
                    "minimum": 0,
                    "maximum": 65536,
                },
                "cycles": {
                    "type": "object",
                    "description": "Cycles engine configuration bundle.",
                    "properties": {
                        "use_denoising": {"type": "boolean"},
                        "denoiser": {"type": "string", "enum": ["OPENIMAGEDENOISE", "OPTIX"]},
                        "samples": {"type": "integer", "minimum": 1, "maximum": 65536},
                        "device": {"type": "string", "enum": ["CPU", "GPU"]},
                        "max_bounces": {"type": "integer", "minimum": 0, "maximum": 1024},
                        "diffuse_bounces": {"type": "integer", "minimum": 0, "maximum": 1024},
                        "glossy_bounces": {"type": "integer", "minimum": 0, "maximum": 1024},
                        "transmission_bounces": {"type": "integer", "minimum": 0, "maximum": 1024},
                        "volume_bounces": {"type": "integer", "minimum": 0, "maximum": 1024},
                        "transparent_max_bounces": {"type": "integer", "minimum": 0, "maximum": 1024},
                        "time_limit": {"type": "number", "minimum": 0.0},
                        "use_adaptive_sampling": {"type": "boolean"},
                        "adaptive_threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "adaptive_min_samples": {"type": "integer", "minimum": 0, "maximum": 65536},
                    },
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_DELETE_OBJECT: {
        "name": TOOL_DELETE_OBJECT,
        "description": (
            "Safely delete an object from the active scene, optionally unlinking its underlying datablock "
            "if no other objects reference it. Destructive operation requiring approval."
        ),
        "permission_tier": PERMISSION_DESTRUCTIVE,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact name of the object to delete.",
                },
                "unlink_data": {
                    "type": "boolean",
                    "description": "Whether to remove the underlying mesh/curve/camera/light data if unreferenced (default True).",
                    "default": True,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_SAVE_BLEND_FILE: {
        "name": TOOL_SAVE_BLEND_FILE,
        "description": (
            "Save the active Blender file to disk. If filepath is omitted, saves to the current file path. "
            "Protects against accidental overwriting unless overwrite=True."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Destination .blend file path. If omitted, saves over the currently opened .blend file.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether to overwrite an existing file if destination path already exists on disk (default False).",
                    "default": False,
                },
                "compress": {
                    "type": "boolean",
                    "description": "Whether to compress the saved .blend file (default True).",
                    "default": True,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_RENDER_SCENE: {
        "name": TOOL_RENDER_SCENE,
        "description": (
            "Render the active Blender scene to disk as a still image or animation sequence/video. "
            "Supports configurable render mode ('still' or 'animation'), target frame or frame range, "
            "custom output path, image format, and optional camera selection. "
            "Requires user approval and strictly verifies generated output files on disk."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "render_mode": {
                    "type": "string",
                    "description": "Render mode: 'still' for single frame or 'animation' for frame range sequence/video.",
                    "enum": ["still", "animation"],
                    "default": "still",
                },
                "frame": {
                    "type": "integer",
                    "description": "Target frame number for still render. Defaults to current scene frame if omitted.",
                },
                "frame_start": {
                    "type": "integer",
                    "description": "Starting frame for animation render. Defaults to scene start frame if omitted.",
                },
                "frame_end": {
                    "type": "integer",
                    "description": "Ending frame for animation render. Defaults to scene end frame if omitted.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Custom output file path or directory. If omitted, uses the scene's configured render filepath.",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output image format ('PNG', 'JPEG', 'OPEN_EXR', 'TARGA', 'TIFF'). If omitted, uses scene's configured format.",
                    "enum": ["PNG", "JPEG", "OPEN_EXR", "TARGA", "TIFF"],
                },
                "camera": {
                    "type": "string",
                    "description": "Optional name of the camera object to render from. If omitted, uses the active scene camera.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_EXTRUDE_MESH: {
        "name": TOOL_EXTRUDE_MESH,
        "description": (
            "Extrude mesh faces in Blender Edit Mode with explicit distance, direction, and selection controls. "
            "Supports region extrusion and individual face extrusion. Enforces active mesh verification, "
            "Edit Mode transition, and topology updates."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the target mesh object in the active scene.",
                },
                "distance": {
                    "type": "number",
                    "description": "Extrusion distance (positive or negative float). Defaults to 1.0.",
                    "default": 1.0,
                },
                "direction": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "3D direction vector [x, y, z] for extrusion. If omitted, extrudes along face normal(s).",
                },
                "faces": {
                    "description": "Faces to extrude: 'selected' (currently selected faces in edit mode), 'all' (all faces), or a list of integer face indices [0, 1, 2]. Defaults to 'selected'.",
                    "default": "selected",
                },
                "individual": {
                    "type": "boolean",
                    "description": "Whether to extrude faces individually (discrete) or as a connected region. Defaults to False.",
                    "default": False,
                },
                "dissolve_orthogonal_edges": {
                    "type": "boolean",
                    "description": "Whether to dissolve orthogonal edges during extrusion. Defaults to False.",
                    "default": False,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_INSET_MESH: {
        "name": TOOL_INSET_MESH,
        "description": (
            "Inset mesh faces in Blender Edit Mode with configurable thickness, depth, and selection controls. "
            "Supports region inset and individual face inset. Enforces active mesh verification, "
            "Edit Mode transition, and topology updates."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the target mesh object in the active scene.",
                },
                "thickness": {
                    "type": "number",
                    "description": "Inset thickness (offset distance inward). Must be non-negative. Defaults to 0.1.",
                    "default": 0.1,
                },
                "depth": {
                    "type": "number",
                    "description": "Inset depth displacement (positive extends outward, negative indents inward). Defaults to 0.0.",
                    "default": 0.0,
                },
                "faces": {
                    "description": "Faces to inset: 'selected' (currently selected in edit mode), 'all' (all faces), or a list of integer face indices [0, 1, 2]. Defaults to 'selected'.",
                    "default": "selected",
                },
                "use_individual": {
                    "type": "boolean",
                    "description": "Whether to inset each face individually rather than as an entire region. Defaults to False.",
                    "default": False,
                },
                "use_outset": {
                    "type": "boolean",
                    "description": "Outset rather than inset. Defaults to False.",
                    "default": False,
                },
                "use_boundary": {
                    "type": "boolean",
                    "description": "Whether to inset open mesh boundary edges. Defaults to True.",
                    "default": True,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_UV_UNWRAP: {
        "name": TOOL_UV_UNWRAP,
        "description": (
            "Unwraps selected or all faces of a mesh object into UV coordinates using Blender's Edit Mode unwrap engine. "
            "Supports angle-based (ABF) and conformal (LSCM) methods, seam packing margin, aspect correction, and hole filling."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target mesh object name.",
                },
                "method": {
                    "type": "string",
                    "description": "Unwrap method: 'ANGLE_BASED' (conformal / ABF, standard) or 'CONFORMAL' (LSCM). Defaults to 'ANGLE_BASED'.",
                    "enum": ["ANGLE_BASED", "CONFORMAL"],
                    "default": "ANGLE_BASED",
                },
                "margin": {
                    "type": "number",
                    "description": "Space between UV islands (0.0 to 1.0). Defaults to 0.001.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.001,
                },
                "fill_holes": {
                    "type": "boolean",
                    "description": "Virtually fill holes in mesh before unwrapping to avoid overlapping. Defaults to True.",
                    "default": True,
                },
                "correct_aspect": {
                    "type": "boolean",
                    "description": "Map UV coordinates taking image or object aspect ratio into account. Defaults to True.",
                    "default": True,
                },
                "uv_layer": {
                    "type": "string",
                    "description": "Target UV map layer name. Defaults to 'UVMap'.",
                    "default": "UVMap",
                },
                "faces": {
                    "description": "Faces to unwrap: 'all' (all faces), 'selected' (currently selected faces in edit mode), or a list of integer face indices [0, 1, 2]. Defaults to 'all'.",
                    "default": "all",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optional SHA-256 snapshot id for optimistic concurrency control.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_UV_SMART_PROJECT: {
        "name": TOOL_UV_SMART_PROJECT,
        "description": (
            "Projects UV coordinates onto a mesh object using Blender's Smart UV Project algorithm. "
            "Projects faces based on angle limits and island margins, ideal for hard-surface or non-organic meshes."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target mesh object name.",
                },
                "angle_limit": {
                    "type": "number",
                    "description": "Lower angles yield more UV islands with less distortion; higher angles yield fewer islands with more distortion (1.0 to 89.0 degrees). Defaults to 66.0.",
                    "minimum": 1.0,
                    "maximum": 89.0,
                    "default": 66.0,
                },
                "island_margin": {
                    "type": "number",
                    "description": "Margin between UV islands (0.0 to 1.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                },
                "area_weight": {
                    "type": "number",
                    "description": "Weight projection area by face area (0.0 to 1.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                },
                "correct_aspect": {
                    "type": "boolean",
                    "description": "Map UVs taking image or object aspect ratio into account. Defaults to True.",
                    "default": True,
                },
                "scale_to_bounds": {
                    "type": "boolean",
                    "description": "Scale UV coordinates to fit the 0.0-1.0 UV bounds. Defaults to False.",
                    "default": False,
                },
                "uv_layer": {
                    "type": "string",
                    "description": "Target UV map layer name. Defaults to 'UVMap'.",
                    "default": "UVMap",
                },
                "faces": {
                    "description": "Faces to project: 'all' (all faces), 'selected' (currently selected faces in edit mode), or a list of integer face indices [0, 1, 2]. Defaults to 'all'.",
                    "default": "all",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optional SHA-256 snapshot id for optimistic concurrency control.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_MANAGE_UV_SEAMS: {
        "name": TOOL_MANAGE_UV_SEAMS,
        "description": (
            "Marks, clears, or resets UV seams on mesh edges with transactional rollback and optimistic concurrency checks."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target mesh object name.",
                },
                "action": {
                    "type": "string",
                    "description": "Operation: 'mark' (mark specified edges as seams), 'clear' (clear seams from specified edges), or 'clear_all' (remove all seams from mesh). Defaults to 'mark'.",
                    "enum": ["mark", "clear", "clear_all"],
                    "default": "mark",
                },
                "edges": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of non-negative integer edge indices to mark or clear. Required for 'mark' and 'clear'.",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optional SHA-256 snapshot id for optimistic concurrency control.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_PACK_UV_ISLANDS: {
        "name": TOOL_PACK_UV_ISLANDS,
        "description": (
            "Packs UV islands within the unit square with margin and optional rotation using Blender's island packing engine."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target mesh object name.",
                },
                "uv_layer": {
                    "type": "string",
                    "description": "Target UV map layer name. Defaults to active UV layer.",
                },
                "margin": {
                    "type": "number",
                    "description": "Margin spacing between packed UV islands (0.0 to 1.0). Defaults to 0.01.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.01,
                },
                "rotate": {
                    "type": "boolean",
                    "description": "Allow rotation of islands to achieve tighter packing. Defaults to True.",
                    "default": True,
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optional SHA-256 snapshot id for optimistic concurrency control.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_MANAGE_UV_LAYERS: {
        "name": TOOL_MANAGE_UV_LAYERS,
        "description": (
            "Creates, activates, renames, or deletes UV map layers on a mesh object with rollback and concurrency safety."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target mesh object name.",
                },
                "action": {
                    "type": "string",
                    "description": "Operation: 'create' (add new UV layer), 'set_active' (activate layer for editing/rendering), 'rename' (rename existing layer), or 'remove' (delete UV layer). Defaults to 'create'.",
                    "enum": ["create", "set_active", "rename", "remove"],
                    "default": "create",
                },
                "layer_name": {
                    "type": "string",
                    "description": "Name of the target UV layer.",
                },
                "new_name": {
                    "type": "string",
                    "description": "New layer name when action is 'rename'.",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optional SHA-256 snapshot id for optimistic concurrency control.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name", "layer_name"],
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_UV_MESH: {
        "name": TOOL_INSPECT_UV_MESH,
        "description": (
            "Inspects UV layers, seams, coordinates bounds, island count estimates, and topology on a mesh object. Read-only."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target mesh object name.",
                },
                "uv_layer": {
                    "type": "string",
                    "description": "Optional target UV map layer name. Defaults to active UV layer.",
                },
                "detail_level": {
                    "type": "string",
                    "description": "Detail level: 'summary' (bounds, island estimate, seam count) or 'detailed' (includes sample per-face UV coordinates). Defaults to 'summary'.",
                    "enum": ["summary", "detailed"],
                    "default": "summary",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_MANAGE_KEYFRAME: {
        "name": TOOL_MANAGE_KEYFRAME,
        "description": (
            "Inserts, updates, or deletes animation keyframes for supported object properties "
            "(location, rotation_euler, scale) at specified frames with verified channel bounds."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target object name.",
                },
                "bone_name": {
                    "type": "string",
                    "description": "Optional pose bone name if keyframing an armature bone in pose mode.",
                },
                "property_path": {
                    "type": "string",
                    "description": "Property to keyframe: 'location', 'rotation_euler', or 'scale'.",
                    "enum": ["location", "rotation_euler", "scale"],
                },
                "frame": {
                    "type": "number",
                    "description": "Frame number for keyframe insertion/deletion.",
                },
                "action": {
                    "type": "string",
                    "description": "Operation to perform: 'insert' (default) or 'delete'.",
                    "enum": ["insert", "delete"],
                    "default": "insert",
                },
                "value": {
                    "description": "Optional numeric value or 3-element array to set prior to inserting the keyframe.",
                },
                "index": {
                    "type": "integer",
                    "description": "Array index for multi-axis properties: -1 for all axes, or 0 (X), 1 (Y), 2 (Z). Defaults to -1.",
                    "minimum": -1,
                    "maximum": 2,
                    "default": -1,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name", "property_path", "frame"],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_GEOMETRY_NODES: {
        "name": TOOL_CONFIGURE_GEOMETRY_NODES,
        "description": (
            "Inspects, configures, or evaluates Geometry Nodes modifier stacks, node trees, links, and interface sockets on a scene mesh object."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Target object name.",
                },
                "target_object": {
                    "type": "string",
                    "description": "Alias for name.",
                },
                "object_name": {
                    "type": "string",
                    "description": "Alias for name.",
                },
                "action": {
                    "type": "string",
                    "description": "Action: 'inspect', 'create', 'assign_group', 'add_node', 'remove_node', 'add_link', 'remove_link', 'set_node_input', 'add_socket', 'set_socket_default', 'configure_graph', 'update_graph', 'evaluate', or 'apply'. Defaults to 'inspect'.",
                    "enum": [
                        "inspect", "create", "assign_group", "add_node", "remove_node",
                        "add_link", "remove_link", "set_node_input", "add_socket",
                        "set_socket_default", "configure_graph", "update_graph", "evaluate", "apply"
                    ],
                    "default": "inspect",
                },
                "modifier_name": {
                    "type": "string",
                    "description": "Name of the Geometry Nodes modifier. Defaults to 'GeometryNodes'.",
                    "default": "GeometryNodes",
                },
                "node_group_name": {
                    "type": "string",
                    "description": "Name of the GeometryNodeTree node group to assign or create.",
                },
                "node_type": {
                    "type": "string",
                    "description": "Type of node to add for add_node (e.g. 'GeometryNodeTransform', 'GeometryNodeSubdivisionSurface', 'GeometryNodeMeshCube', etc.).",
                },
                "node_name": {
                    "type": "string",
                    "description": "Name of node for add_node, remove_node, or set_node_input.",
                },
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Optional [x, y] coordinates for add_node.",
                },
                "inputs": {
                    "type": "object",
                    "description": "Optional dictionary of initial input socket default values for add_node.",
                },
                "from_node": {
                    "type": "string",
                    "description": "Source node name for add_link or remove_link (e.g. 'Input', 'Group Input', or node name).",
                },
                "from_socket": {
                    "type": "string",
                    "description": "Source socket name for add_link or remove_link (e.g. 'Geometry', 'Mesh').",
                },
                "to_node": {
                    "type": "string",
                    "description": "Target node name for add_link or remove_link (e.g. 'Output', 'Group Output', or node name).",
                },
                "to_socket": {
                    "type": "string",
                    "description": "Target socket name for add_link or remove_link (e.g. 'Geometry', 'Mesh').",
                },
                "value": {
                    "description": "Value to set for set_node_input.",
                },
                "socket_name": {
                    "type": "string",
                    "description": "Interface socket name to add or configure.",
                },
                "socket_type": {
                    "type": "string",
                    "description": "Socket type: 'NodeSocketFloat', 'NodeSocketInt', 'NodeSocketVector', 'NodeSocketColor', 'NodeSocketBool', 'NodeSocketString', 'NodeSocketGeometry'.",
                    "enum": ["NodeSocketFloat", "NodeSocketInt", "NodeSocketVector", "NodeSocketColor", "NodeSocketBool", "NodeSocketString", "NodeSocketGeometry"],
                    "default": "NodeSocketFloat",
                },
                "in_out": {
                    "type": "string",
                    "enum": ["INPUT", "OUTPUT", "input", "output"],
                    "description": "Interface socket direction for add_socket. Defaults to 'INPUT'.",
                },
                "default_value": {
                    "description": "Default value for the interface socket.",
                },
                "min_value": {
                    "type": "number",
                    "description": "Optional minimum value limit for numeric sockets.",
                },
                "max_value": {
                    "type": "number",
                    "description": "Optional maximum value limit for numeric sockets.",
                },
                "nodes": {
                    "type": "array",
                    "description": "List of node specifications for configure_graph/update_graph.",
                },
                "links": {
                    "type": "array",
                    "description": "List of link specifications for configure_graph/update_graph.",
                },
                "parameters": {
                    "type": "array",
                    "description": "List of interface parameter specifications for configure_graph/update_graph.",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "pattern": "^sha256:[0-9a-f]{64}$",
                    "description": "Optimistic concurrency state fingerprint from previous inspect call.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_EXPORT_SCENE_ASSET: {
        "name": TOOL_EXPORT_SCENE_ASSET,
        "description": (
            "Exports scene objects to an industry-standard 3D file format (glTF/GLB, FBX, USD/USDC/USDA, OBJ, STL, PLY, ABC) "
            "with overwrite protection and post-export file verification."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Absolute output destination filepath on disk.",
                },
                "format": {
                    "type": "string",
                    "description": "Export format: 'GLTF', 'GLB', 'FBX', 'USD', 'USDC', 'USDA', 'OBJ', 'STL', 'PLY', 'ABC'. Auto-detected from file extension if omitted.",
                    "enum": ["GLTF", "GLB", "FBX", "USD", "USDC", "USDA", "OBJ", "STL", "PLY", "ABC"],
                },
                "selected_only": {
                    "type": "boolean",
                    "description": "Whether to export only currently selected objects. Defaults to False (entire scene).",
                    "default": False,
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether to allow overwriting an existing destination file. Defaults to False.",
                    "default": False,
                },
                "generate_sidecar": {
                    "type": "boolean",
                    "description": "Whether to generate a SHA-256 sidecar file (.sha256). Defaults to True.",
                    "default": True,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["filepath"],
            "additionalProperties": False,
        },
    },
    TOOL_IMPORT_SCENE_ASSET: {
        "name": TOOL_IMPORT_SCENE_ASSET,
        "description": (
            "Imports a 3D asset file (glTF/GLB, FBX, USD/USDC/USDA, OBJ, STL, PLY, ABC) into the active Blender scene."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Absolute path to existing 3D asset file on disk.",
                },
                "format": {
                    "type": "string",
                    "description": "File format: 'GLTF', 'GLB', 'FBX', 'USD', 'USDC', 'USDA', 'OBJ', 'STL', 'PLY', 'ABC'. Auto-detected from file extension if omitted.",
                    "enum": ["GLTF", "GLB", "FBX", "USD", "USDC", "USDA", "OBJ", "STL", "PLY", "ABC"],
                },
                "verify_checksum": {
                    "type": "boolean",
                    "description": "Whether to verify asset integrity against a SHA-256 sidecar file if present. Defaults to False.",
                    "default": False,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["filepath"],
            "additionalProperties": False,
        },
    },
    TOOL_DUPLICATE_OBJECT: {
        "name": TOOL_DUPLICATE_OBJECT,
        "description": (
            "Duplicates an existing object in the scene with independent data blocks (deep copy) or linked data. "
            "Supports optional location, rotation_euler, and scale transforms for direct placement."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the existing object to duplicate.",
                },
                "new_name": {
                    "type": "string",
                    "description": "Optional name for the newly created duplicate.",
                },
                "linked": {
                    "type": "boolean",
                    "description": "Whether to share the underlying datablock (linked copy) or create an independent deep copy. Defaults to False (independent).",
                    "default": False,
                },
                "location": {
                    "type": "array",
                    "description": "Optional 3D world coordinates [x, y, z] to position the duplicate object.",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "rotation_euler": {
                    "type": "array",
                    "description": "Optional Euler rotation angles in radians [rx, ry, rz] for the duplicate object.",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "scale": {
                    "type": "array",
                    "description": "Optional size scale factors [sx, sy, sz] for the duplicate object.",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_RENAME_OBJECT: {
        "name": TOOL_RENAME_OBJECT,
        "description": (
            "Renames an existing object in the active scene with targeted verification."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Current object name.",
                },
                "new_name": {
                    "type": "string",
                    "description": "New name for the object.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name", "new_name"],
            "additionalProperties": False,
        },
    },
    TOOL_SELECT_OBJECT: {
        "name": TOOL_SELECT_OBJECT,
        "description": (
            "Selects or deselects an object in the active scene and optionally makes it the active object. "
            "Supports clearing existing selections with deselect_all."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact target object name.",
                },
                "state": {
                    "type": "boolean",
                    "description": "Whether to select (True) or deselect (False) the target object. Defaults to True.",
                    "default": True,
                },
                "deselect_all": {
                    "type": "boolean",
                    "description": "Optionally deselect all other objects before applying selection. Defaults to False.",
                    "default": False,
                },
                "make_active": {
                    "type": "boolean",
                    "description": "Optionally make the target the active object when selecting. Defaults to True.",
                    "default": True,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_PURGE_ORPHANED_DATABLOCKS: {
        "name": TOOL_PURGE_ORPHANED_DATABLOCKS,
        "description": (
            "Safely purges unused (orphaned, zero-user) Blender datablocks from memory using bpy.data.orphans_purge. "
            "WARNING: Potentially irreversible operation that removes unlinked meshes, materials, textures, curves, and actions."
        ),
        "permission_tier": PERMISSION_DESTRUCTIVE,
        "input_schema": {
            "type": "object",
            "properties": {
                "do_recursive": {
                    "type": "boolean",
                    "description": "Whether to recursively purge datablocks that become orphaned during the purge pass. Defaults to True.",
                    "default": True,
                },
                "do_local_ids": {
                    "type": "boolean",
                    "description": "Whether to purge local datablocks. Defaults to True.",
                    "default": True,
                },
                "do_linked_ids": {
                    "type": "boolean",
                    "description": "Whether to purge linked datablocks from external libraries. Defaults to True.",
                    "default": True,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CREATE_CURVE_OR_TEXT: {
        "name": TOOL_CREATE_CURVE_OR_TEXT,
        "description": (
            "Create 2D or 3D Bezier/NURBS curves, circle paths, or text objects in the active scene. "
            "Supports configurable dimensions, geometry extrude depth, bevel depth, curve resolution, "
            "and text body contents."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the created curve or text object.",
                },
                "curve_type": {
                    "type": "string",
                    "enum": ["BEZIER", "CIRCLE", "PATH", "NURBS_CURVE", "NURBS_CIRCLE", "TEXT"],
                    "description": "Type of curve or text geometry to create.",
                    "default": "BEZIER",
                },
                "body": {
                    "type": "string",
                    "description": "Text body content when curve_type is TEXT.",
                    "default": "Text",
                },
                "dimensions": {
                    "type": "string",
                    "enum": ["2D", "3D"],
                    "description": "Curve dimensions (2D or 3D). Defaults to 3D.",
                    "default": "3D",
                },
                "extrude": {
                    "type": "number",
                    "description": "Geometric extrusion depth along curve normal in meters.",
                    "minimum": 0.0,
                    "default": 0.0,
                },
                "bevel_depth": {
                    "type": "number",
                    "description": "Bevel depth applied to the curve in meters.",
                    "minimum": 0.0,
                    "default": 0.0,
                },
                "resolution": {
                    "type": "integer",
                    "description": "Surface resolution (U) for curve evaluation.",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 12,
                },
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Target [x, y, z] location coordinates in meters.",
                    "default": [0.0, 0.0, 0.0],
                },
                "rotation": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Target [x, y, z] Euler rotation in radians.",
                    "default": [0.0, 0.0, 0.0],
                },
                "scale": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Target [x, y, z] scale factors.",
                    "default": [1.0, 1.0, 1.0],
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    TOOL_MANAGE_SHADER_NODES: {
        "name": TOOL_MANAGE_SHADER_NODES,
        "description": (
            "Manipulate shader node graphs for materials or world environments. "
            "Supports creating nodes, removing nodes, connecting sockets, disconnecting sockets, "
            "setting socket/node properties, and listing existing node networks."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "Name of the target Material or World datablock.",
                },
                "target_type": {
                    "type": "string",
                    "enum": ["MATERIAL", "WORLD"],
                    "description": "Target datablock type (MATERIAL or WORLD). Defaults to MATERIAL.",
                    "default": "MATERIAL",
                },
                "action": {
                    "type": "string",
                    "enum": ["create_node", "remove_node", "connect", "disconnect", "set_property", "list_nodes"],
                    "description": "Node graph action to perform.",
                    "default": "create_node",
                },
                "node_type": {
                    "type": "string",
                    "description": "Blender shader node RNA type (e.g., ShaderNodeTexImage, ShaderNodeMapping, ShaderNodeTexCoord, ShaderNodeMath).",
                },
                "node_name": {
                    "type": "string",
                    "description": "Name or identifier of the node for creation, removal, or property updates.",
                },
                "from_node": {
                    "type": "string",
                    "description": "Source node name for connection/disconnection.",
                },
                "from_socket": {
                    "type": "string",
                    "description": "Source output socket name or index.",
                },
                "to_node": {
                    "type": "string",
                    "description": "Destination node name for connection/disconnection.",
                },
                "to_socket": {
                    "type": "string",
                    "description": "Destination input socket name or index.",
                },
                "property_name": {
                    "type": "string",
                    "description": "Property or input socket name when action is set_property.",
                },
                "property_value": {
                    "description": "Value to assign when action is set_property (scalar, string, or array).",
                },
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Optional [x, y] coordinates in the Node Editor canvas.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["target_name"],
            "additionalProperties": False,
        },
    },
    TOOL_BAKE_OBJECT_TEXTURE: {
        "name": TOOL_BAKE_OBJECT_TEXTURE,
        "description": (
            "Bake materials, lighting, normals, roughness, or ambient occlusion into an image texture "
            "for a target mesh object using Cycles rendering engine. Supports saving to disk."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name of the target mesh object with valid UV coordinates.",
                },
                "bake_type": {
                    "type": "string",
                    "enum": ["COMBINED", "DIFFUSE", "ROUGHNESS", "NORMAL", "AO", "EMIT", "SHADOW"],
                    "description": "Type of bake pass to perform.",
                    "default": "COMBINED",
                },
                "image_name": {
                    "type": "string",
                    "description": "Target image datablock name. Created if not already existing.",
                },
                "width": {
                    "type": "integer",
                    "description": "Bake image width in pixels (64 to 8192).",
                    "minimum": 64,
                    "maximum": 8192,
                    "default": 1024,
                },
                "height": {
                    "type": "integer",
                    "description": "Bake image height in pixels (64 to 8192).",
                    "minimum": 64,
                    "maximum": 8192,
                    "default": 1024,
                },
                "margin": {
                    "type": "integer",
                    "description": "Pixel margin around baked UV islands (0 to 64).",
                    "minimum": 0,
                    "maximum": 64,
                    "default": 16,
                },
                "save_filepath": {
                    "type": "string",
                    "description": "Optional file path to write the baked PNG image to disk.",
                },
                "use_selected_to_active": {
                    "type": "boolean",
                    "description": "Whether to bake from selected objects to the active object.",
                    "default": False,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["object_name"],
            "additionalProperties": False,
        },
    },
    TOOL_MANAGE_COMPOSITOR_NODES: {
        "name": TOOL_MANAGE_COMPOSITOR_NODES,
        "description": (
            "Manipulate Blender's compositing node tree for post-processing effects, bloom/glare, "
            "denoising, color grading, render passes, and composite outputs in Blender 5.2.2 LTS."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "scene_name": {
                    "type": "string",
                    "description": "Optional scene name (defaults to active scene).",
                },
                "action": {
                    "type": "string",
                    "enum": ["enable", "inspect", "create_node", "remove_node", "connect", "disconnect", "set_property", "configure_render_passes", "list_nodes"],
                    "description": "Compositing action to perform.",
                    "default": "inspect",
                },
                "node_type": {
                    "type": "string",
                    "description": "Compositor node type (e.g. CompositorNodeGlare, CompositorNodeDenoise, CompositorNodeBlur, CompositorNodeColorBalance, CompositorNodeCryptomatteV2).",
                },
                "node_name": {
                    "type": "string",
                    "description": "Name or identifier of the node for creation, removal, or property updates.",
                },
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Optional [x, y] node placement coordinates.",
                },
                "inputs": {
                    "type": "object",
                    "description": "Optional initial socket values for node creation.",
                },
                "from_node": {
                    "type": "string",
                    "description": "Source node name for connection/disconnection.",
                },
                "from_socket": {
                    "type": "string",
                    "description": "Source output socket name or index.",
                },
                "to_node": {
                    "type": "string",
                    "description": "Destination node name for connection/disconnection.",
                },
                "to_socket": {
                    "type": "string",
                    "description": "Destination input socket name or index.",
                },
                "property_name": {
                    "type": "string",
                    "description": "Property name when action is set_property.",
                },
                "property_value": {
                    "description": "Value to assign when action is set_property.",
                },
                "passes": {
                    "type": "object",
                    "description": "Dictionary of pass names to booleans for configure_render_passes (e.g. {'z': true, 'normal': true, 'diffuse': true, 'glossy': true, 'ao': true, 'shadow': true, 'emission': true, 'environment': true, 'mist': true}).",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optional snapshot identifier for optimistic concurrency control (stale-state protection).",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_COMPOSITOR_PIPELINE: {
        "name": TOOL_INSPECT_COMPOSITOR_PIPELINE,
        "description": "Inspect the active Blender 5.2.2 LTS compositor pipeline, nodes, links, and enabled render passes.",
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "scene_name": {
                    "type": "string",
                    "description": "Optional scene name (defaults to active scene).",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CREATE_ARMATURE: {
        "name": TOOL_CREATE_ARMATURE,
        "description": "Creates a new Armature object and underlying datablock in the scene with position, rotation, and scale transforms.",
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the new armature (defaults to 'Armature').",
                    "default": "Armature",
                },
                "location": {
                    "type": "array",
                    "description": "Armature 3D location [x, y, z].",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                },
                "rotation": {
                    "type": "array",
                    "description": "Armature Euler rotation [x, y, z] in radians.",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                },
                "scale": {
                    "type": "array",
                    "description": "Armature scale [x, y, z].",
                    "items": {"type": "number"},
                    "default": [1.0, 1.0, 1.0],
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_EDIT_ARMATURE_BONES: {
        "name": TOOL_EDIT_ARMATURE_BONES,
        "description": "Edits armature bones in Edit Mode with rollback protection: add_bone, edit_bone, remove_bone, hierarchy parenting, connect flags.",
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "armature_name": {
                    "type": "string",
                    "description": "Target armature object name.",
                },
                "operations": {
                    "type": "array",
                    "description": "List of bone operations to apply atomically.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["add_bone", "edit_bone", "remove_bone", "add", "edit", "remove"]},
                            "name": {"type": "string"},
                            "head": {"type": "array", "items": {"type": "number"}},
                            "tail": {"type": "array", "items": {"type": "number"}},
                            "roll": {"type": "number"},
                            "parent": {"type": ["string", "null"]},
                            "use_connect": {"type": "boolean"},
                            "use_deform": {"type": "boolean"},
                        },
                        "required": ["name"],
                    },
                },
                "action": {
                    "type": "string",
                    "description": "Single operation action shortcut if 'operations' array is omitted.",
                    "enum": ["add_bone", "edit_bone", "remove_bone"],
                },
                "name": {
                    "type": "string",
                    "description": "Single bone name shortcut if 'operations' array is omitted.",
                },
                "head": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Head [x, y, z] shortcut for single operation.",
                },
                "tail": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Tail [x, y, z] shortcut for single operation.",
                },
                "parent": {
                    "type": ["string", "null"],
                    "description": "Parent bone name shortcut for single operation.",
                },
                "use_connect": {
                    "type": "boolean",
                    "description": "Connect head to parent tail flag for single operation.",
                },
                "use_deform": {
                    "type": "boolean",
                    "description": "Deform flag for single operation.",
                },
                "roll": {
                    "type": "number",
                    "description": "Bone roll in radians shortcut for single operation.",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optimistic concurrency state hash. Mutation is rejected if state changed.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["armature_name"],
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_ARMATURE: {
        "name": TOOL_INSPECT_ARMATURE,
        "description": "Inspects armature rest bones, bone hierarchy, roll angles, pose transforms, pose constraints, and snapshot ID.",
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "armature_name": {
                    "type": "string",
                    "description": "Name of the armature to inspect.",
                },
                "include_pose": {
                    "type": "boolean",
                    "description": "Whether to include pose transforms and bone constraints (defaults to True).",
                    "default": True,
                },
                "frame": {
                    "type": "integer",
                    "description": "Optional scene timeline frame to evaluate pose transforms at.",
                },
            },
            "required": ["armature_name"],
            "additionalProperties": False,
        },
    },
    TOOL_BIND_ARMATURE_MESH: {
        "name": TOOL_BIND_ARMATURE_MESH,
        "description": "Binds a target mesh to an armature via ARMATURE modifier and vertex groups (AUTOMATIC, ENVELOPE, NAME_ONLY, MANUAL).",
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "mesh_object_name": {
                    "type": "string",
                    "description": "Name of the target mesh object to skin.",
                },
                "armature_name": {
                    "type": "string",
                    "description": "Name of the source armature object.",
                },
                "bind_mode": {
                    "type": "string",
                    "enum": ["AUTOMATIC", "ENVELOPE", "NAME_ONLY", "MANUAL"],
                    "description": "Binding method: AUTOMATIC (heat weighting), ENVELOPE, NAME_ONLY (vertex groups only), MANUAL (explicit weights).",
                    "default": "AUTOMATIC",
                },
                "vertex_weights": {
                    "type": "object",
                    "description": "Optional dictionary of bone vertex weights: {bone_name: {vertex_index: weight}}.",
                },
                "use_deform_only": {
                    "type": "boolean",
                    "description": "Whether to create vertex groups only for bones with use_deform=True (defaults to True).",
                    "default": True,
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optimistic concurrency state hash of the armature.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["mesh_object_name", "armature_name"],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_BONE_CONSTRAINT: {
        "name": TOOL_CONFIGURE_BONE_CONSTRAINT,
        "description": "Configures Pose Mode constraints on armature bones: Inverse Kinematics (IK), Limit Rotation, Copy Transforms.",
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "armature_name": {
                    "type": "string",
                    "description": "Name of the armature containing the target bone.",
                },
                "bone_name": {
                    "type": "string",
                    "description": "Name of the pose bone to constrain.",
                },
                "constraint_type": {
                    "type": "string",
                    "enum": ["IK", "LIMIT_ROTATION", "COPY_TRANSFORMS"],
                    "description": "Type of bone constraint to configure.",
                    "default": "IK",
                },
                "action": {
                    "type": "string",
                    "enum": ["ADD", "REMOVE", "UPDATE"],
                    "description": "Action: ADD new constraint, REMOVE existing, or UPDATE properties (defaults to ADD).",
                    "default": "ADD",
                },
                "constraint_name": {
                    "type": "string",
                    "description": "Optional explicit constraint name.",
                },
                "target_object": {
                    "type": "string",
                    "description": "Target object name for constraints that track objects.",
                },
                "target_bone": {
                    "type": "string",
                    "description": "Target subtarget bone name on target armature.",
                },
                "chain_count": {
                    "type": "integer",
                    "description": "IK chain length (number of bones up the hierarchy; 0 solves all ancestor bones).",
                    "default": 0,
                },
                "pole_target": {
                    "type": "string",
                    "description": "Optional pole target object for IK constraints.",
                },
                "pole_subtarget": {
                    "type": "string",
                    "description": "Optional pole target bone name for IK constraints.",
                },
                "pole_angle": {
                    "type": "number",
                    "description": "Pole angle in radians for IK constraints.",
                },
                "influence": {
                    "type": "number",
                    "description": "Constraint influence factor between 0.0 and 1.0.",
                    "default": 1.0,
                },
                "limit_rotation_settings": {
                    "type": "object",
                    "description": "Settings for LIMIT_ROTATION: use_limit_x/y/z (bool), min_x/y/z (float), max_x/y/z (float).",
                },
                "owner_space": {
                    "type": "string",
                    "enum": ["WORLD", "CUSTOM", "POSE", "LOCAL"],
                    "description": "Coordinate space of the owner bone.",
                },
                "target_space": {
                    "type": "string",
                    "enum": ["WORLD", "CUSTOM", "POSE", "LOCAL"],
                    "description": "Coordinate space of the target object/bone.",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Optimistic concurrency state hash of the armature.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["armature_name", "bone_name"],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_ANIMATION_CURVE: {
        "name": TOOL_CONFIGURE_ANIMATION_CURVE,
        "description": (
            "Configure animation F-Curves, keyframe interpolation modes (CONSTANT, LINEAR, BEZIER), "
            "curve modifiers (CYCLES, NOISE, LIMITS), and Blender 5.2 Action Slots on an animated object."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name of the target animated object.",
                },
                "data_path": {
                    "type": "string",
                    "description": "Animation property path (e.g. 'location', 'rotation_euler', 'scale').",
                },
                "array_index": {
                    "type": "integer",
                    "description": "Channel array index (0 for X, 1 for Y, 2 for Z, or -1 for all channels).",
                    "default": -1,
                },
                "action": {
                    "type": "string",
                    "enum": ["set_interpolation", "add_modifier", "remove_modifier", "manage_slot", "list_fcurves"],
                    "description": "Animation curve action to perform.",
                    "default": "set_interpolation",
                },
                "interpolation": {
                    "type": "string",
                    "enum": ["CONSTANT", "LINEAR", "BEZIER"],
                    "description": "Keyframe interpolation mode.",
                    "default": "BEZIER",
                },
                "easing": {
                    "type": "string",
                    "enum": ["AUTO", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"],
                    "description": "Keyframe easing mode.",
                    "default": "AUTO",
                },
                "modifier_type": {
                    "type": "string",
                    "description": "F-Curve modifier type (e.g. CYCLES, NOISE, GENERATOR, LIMITS).",
                },
                "slot_name": {
                    "type": "string",
                    "description": "Slot name for Blender 5.2 Action Slots.",
                },
                "slot_id_type": {
                    "type": "string",
                    "description": "Target ID type for ActionSlot creation (defaults to 'OBJECT').",
                    "default": "OBJECT",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["object_name"],
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_PHYSICS: {
        "name": TOOL_CONFIGURE_PHYSICS,
        "description": (
            "Configure physics simulations on a scene object: Rigid Body dynamics (Active/Passive, "
            "mass, friction, restitution, collision shape), Cloth simulation modifier (presets: SILK, COTTON, LEATHER, "
            "pinning vertex group, quality), or Collision body (damping, cloth friction, thickness)."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name of the target object to attach or configure physics on.",
                },
                "physics_type": {
                    "type": "string",
                    "enum": ["RIGID_BODY", "CLOTH", "COLLISION", "RIGID_BODY_CONSTRAINT"],
                    "description": "Physics system type.",
                    "default": "RIGID_BODY",
                },
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "configure"],
                    "description": "Action to perform (add, remove, configure).",
                    "default": "add",
                },
                "rigid_body_type": {
                    "type": "string",
                    "enum": ["ACTIVE", "PASSIVE"],
                    "description": "Rigid body simulation type (ACTIVE or PASSIVE).",
                    "default": "ACTIVE",
                },
                "mass": {
                    "type": "number",
                    "description": "Rigid body or cloth mass in kilograms (0.01 to 10000.0).",
                    "minimum": 0.01,
                    "maximum": 10000.0,
                    "default": 1.0,
                },
                "friction": {
                    "type": "number",
                    "description": "Surface friction coefficient (0.0 to 1.0 for rigid bodies; 0.0 to 80.0 for cloth collision).",
                    "minimum": 0.0,
                    "maximum": 80.0,
                    "default": 0.5,
                },
                "restitution": {
                    "type": "number",
                    "description": "Bounciness / restitution coefficient (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                },
                "collision_shape": {
                    "type": "string",
                    "enum": ["BOX", "SPHERE", "CAPSULE", "CYLINDER", "CONE", "CONVEX_HULL", "MESH"],
                    "description": "Rigid body collision boundary shape.",
                    "default": "CONVEX_HULL",
                },
                "kinematic": {
                    "type": "boolean",
                    "description": "Whether the rigid body is animated / kinematic (driven by animation/script rather than physics forces).",
                    "default": False,
                },
                "linear_damping": {
                    "type": "number",
                    "description": "Amount of linear velocity lost over time for rigid body (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.04,
                },
                "angular_damping": {
                    "type": "number",
                    "description": "Amount of angular velocity lost over time for rigid body (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.10,
                },
                "cloth_preset": {
                    "type": "string",
                    "enum": ["SILK", "COTTON", "LEATHER"],
                    "description": "Optional physical cloth preset setting stiffness, shear, and density parameters.",
                },
                "pin_vertex_group": {
                    "type": "string",
                    "description": "Optional vertex group name used for mass pinning in cloth simulation.",
                },
                "quality": {
                    "type": "integer",
                    "description": "Cloth simulation quality steps per frame (1 to 20).",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
                "use_self_collision": {
                    "type": "boolean",
                    "description": "Enable or disable cloth self-collision.",
                    "default": False,
                },
                "self_distance_min": {
                    "type": "number",
                    "description": "Minimum distance between colliding cloth faces/vertices in meters (0.0005 to 0.1).",
                    "minimum": 0.0005,
                    "maximum": 0.1,
                    "default": 0.015,
                },
                "self_friction": {
                    "type": "number",
                    "description": "Friction coefficient for cloth self-collision (0.0 to 80.0).",
                    "minimum": 0.0,
                    "maximum": 80.0,
                    "default": 5.0,
                },
                "use_collision": {
                    "type": "boolean",
                    "description": "Enable or disable cloth object collision with other collision objects.",
                    "default": True,
                },
                "distance_min": {
                    "type": "number",
                    "description": "Minimum distance between cloth and external collision objects in meters (0.001 to 1.0).",
                    "minimum": 0.001,
                    "maximum": 1.0,
                    "default": 0.015,
                },
                "collision_quality": {
                    "type": "integer",
                    "description": "Collision quality steps for cloth collision solver (1 to 20).",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 2,
                },
                "use_internal_springs": {
                    "type": "boolean",
                    "description": "Enable or disable cloth internal spring generation across 3D mesh volume.",
                    "default": False,
                },
                "internal_spring_max_length": {
                    "type": "number",
                    "description": "Maximum length of internal springs in meters (0.0 means unconstrained / no limit; 0.0 to 1000.0).",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                    "default": 0.0,
                },
                "internal_tension_stiffness": {
                    "type": "number",
                    "description": "Tension stiffness of internal springs (0.0 to 10000.0).",
                    "minimum": 0.0,
                    "maximum": 10000.0,
                    "default": 15.0,
                },
                "internal_compression_stiffness": {
                    "type": "number",
                    "description": "Compression stiffness of internal springs (0.0 to 10000.0).",
                    "minimum": 0.0,
                    "maximum": 10000.0,
                    "default": 15.0,
                },
                "internal_spring_normal_check": {
                    "type": "boolean",
                    "description": "Check that internal springs align with face normals to avoid inverted springs.",
                    "default": True,
                },
                "use_pressure": {
                    "type": "boolean",
                    "description": "Enable or disable uniform cloth internal gas pressure simulation.",
                    "default": False,
                },
                "uniform_pressure_force": {
                    "type": "number",
                    "description": "Uniform pressure force applied outwards in Pascals (-10000.0 to 10000.0; positive inflates, negative deflates).",
                    "minimum": -10000.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "use_pressure_volume": {
                    "type": "boolean",
                    "description": "Auto-adjust pressure to preserve or target a specific volume.",
                    "default": False,
                },
                "target_volume": {
                    "type": "number",
                    "description": "Target volume factor when use_pressure_volume is enabled (0.0 to 10000.0).",
                    "minimum": 0.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "pressure_factor": {
                    "type": "number",
                    "description": "Pressure scaling factor (0.0 to 10000.0).",
                    "minimum": 0.0,
                    "maximum": 10000.0,
                    "default": 1.0,
                },
                "damping": {
                    "type": "number",
                    "description": "Collision damping factor (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.1,
                },
                "cloth_friction": {
                    "type": "number",
                    "description": "Collision surface friction against cloth (0.0 to 80.0).",
                    "minimum": 0.0,
                    "maximum": 80.0,
                    "default": 5.0,
                },
                "thickness_outer": {
                    "type": "number",
                    "description": "Outer collision distance around mesh surface (0.001 to 1.0).",
                    "minimum": 0.001,
                    "maximum": 1.0,
                    "default": 0.02,
                },
                "constraint_type": {
                    "type": "string",
                    "enum": ["FIXED", "POINT", "HINGE", "SLIDER", "GENERIC"],
                    "description": "Rigid body constraint type (FIXED, POINT, HINGE, SLIDER, GENERIC).",
                    "default": "FIXED",
                },
                "target_object_1": {
                    "type": "string",
                    "description": "First object connected by the rigid body constraint (defaults to object_name if omitted).",
                },
                "target_object_2": {
                    "type": "string",
                    "description": "Second object connected by the rigid body constraint (optional; connects to world if omitted).",
                },
                "disable_collisions": {
                    "type": "boolean",
                    "description": "Disable collisions between the two constrained objects.",
                    "default": True,
                },
                "use_breaking": {
                    "type": "boolean",
                    "description": "Allow the constraint to break when impulse exceeds breaking_threshold.",
                    "default": False,
                },
                "breaking_threshold": {
                    "type": "number",
                    "description": "Threshold of linear/angular impulse required to break the constraint (0.0 to 100000.0).",
                    "minimum": 0.0,
                    "maximum": 100000.0,
                    "default": 10.0,
                },
                "use_limit_lin_x": {
                    "type": "boolean",
                    "description": "Enable linear translation limit along the X axis.",
                    "default": False,
                },
                "limit_lin_x_lower": {
                    "type": "number",
                    "description": "Lower linear translation limit along the X axis in meters (-10000.0 to 10000.0).",
                    "minimum": -10000.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "limit_lin_x_upper": {
                    "type": "number",
                    "description": "Upper linear translation limit along the X axis in meters (-10000.0 to 10000.0).",
                    "minimum": -10000.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "use_limit_lin_y": {
                    "type": "boolean",
                    "description": "Enable linear translation limit along the Y axis.",
                    "default": False,
                },
                "limit_lin_y_lower": {
                    "type": "number",
                    "description": "Lower linear translation limit along the Y axis in meters (-10000.0 to 10000.0).",
                    "minimum": -10000.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "limit_lin_y_upper": {
                    "type": "number",
                    "description": "Upper linear translation limit along the Y axis in meters (-10000.0 to 10000.0).",
                    "minimum": -10000.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "use_limit_lin_z": {
                    "type": "boolean",
                    "description": "Enable linear translation limit along the Z axis.",
                    "default": False,
                },
                "limit_lin_z_lower": {
                    "type": "number",
                    "description": "Lower linear translation limit along the Z axis in meters (-10000.0 to 10000.0).",
                    "minimum": -10000.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "limit_lin_z_upper": {
                    "type": "number",
                    "description": "Upper linear translation limit along the Z axis in meters (-10000.0 to 10000.0).",
                    "minimum": -10000.0,
                    "maximum": 10000.0,
                    "default": 0.0,
                },
                "use_limit_ang_x": {
                    "type": "boolean",
                    "description": "Enable angular rotation limit around the X axis.",
                    "default": False,
                },
                "limit_ang_x_lower": {
                    "type": "number",
                    "description": "Lower angular rotation limit around the X axis in radians (-100.0 to 100.0).",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": -0.785398,
                },
                "limit_ang_x_upper": {
                    "type": "number",
                    "description": "Upper angular rotation limit around the X axis in radians (-100.0 to 100.0).",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": 0.785398,
                },
                "use_limit_ang_y": {
                    "type": "boolean",
                    "description": "Enable angular rotation limit around the Y axis.",
                    "default": False,
                },
                "limit_ang_y_lower": {
                    "type": "number",
                    "description": "Lower angular rotation limit around the Y axis in radians (-100.0 to 100.0).",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": -0.785398,
                },
                "limit_ang_y_upper": {
                    "type": "number",
                    "description": "Upper angular rotation limit around the Y axis in radians (-100.0 to 100.0).",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": 0.785398,
                },
                "use_limit_ang_z": {
                    "type": "boolean",
                    "description": "Enable angular rotation limit around the Z axis.",
                    "default": False,
                },
                "limit_ang_z_lower": {
                    "type": "number",
                    "description": "Lower angular rotation limit around the Z axis in radians (-100.0 to 100.0).",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": -0.785398,
                },
                "limit_ang_z_upper": {
                    "type": "number",
                    "description": "Upper angular rotation limit around the Z axis in radians (-100.0 to 100.0).",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": 0.785398,
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Expected state snapshot ID for optimistic concurrency control.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["object_name"],
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_PHYSICS: {
        "name": TOOL_INSPECT_PHYSICS,
        "description": (
            "Inspect active physics configuration in the scene or on a specific object: "
            "rigid body world settings, solver substeps, point cache baking status, and cloth/collision settings."
        ),
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Optional name of target object to inspect. If omitted, all physics objects in scene are reported.",
                },
                "include_cache_info": {
                    "type": "boolean",
                    "description": "Whether to query point cache baking status and frame ranges.",
                    "default": True,
                },
                "frame": {
                    "type": "integer",
                    "description": "Optional scene timeline frame to evaluate physics transformations at.",
                    "minimum": 1,
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_BAKE_PHYSICS_SIMULATION: {
        "name": TOOL_BAKE_PHYSICS_SIMULATION,
        "description": (
            "Bake physics simulation caches (Rigid Body, Cloth, or All) across a bounded frame range "
            "(maximum 250 frames) with deterministic point cache verification."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "physics_type": {
                    "type": "string",
                    "enum": ["RIGID_BODY", "CLOTH", "ALL"],
                    "description": "Simulation domain to bake.",
                    "default": "RIGID_BODY",
                },
                "object_name": {
                    "type": "string",
                    "description": "Target object name for cloth baking. Optional if physics_type is RIGID_BODY or ALL.",
                },
                "frame_start": {
                    "type": "integer",
                    "description": "Starting frame of simulation cache (>= 1).",
                    "minimum": 1,
                    "default": 1,
                },
                "frame_end": {
                    "type": "integer",
                    "description": "Ending frame of simulation cache (<= frame_start + 250).",
                    "minimum": 1,
                    "default": 50,
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Maximum execution duration before timeout guard trips (1.0 to 300.0).",
                    "minimum": 1.0,
                    "maximum": 300.0,
                    "default": 30.0,
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Expected state snapshot ID for optimistic concurrency control.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_FORCE_FIELD: {
        "name": TOOL_CONFIGURE_FORCE_FIELD,
        "description": (
            "Create, configure, inspect, or remove physics force fields (WIND, TURBULENCE, VORTEX) "
            "with full parameter controls (strength, flow, wind_factor, size, inflow, noise, seed, falloff, limits) "
            "and transactional rollback."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the force field object to create, configure, inspect, or remove (alias: object_name).",
                },
                "object_name": {
                    "type": "string",
                    "description": "Alias for name.",
                },
                "action": {
                    "type": "string",
                    "enum": ["create", "add", "configure", "inspect", "remove", "delete"],
                    "description": "Action to perform: 'create'/'add', 'configure', 'inspect', or 'remove'/'delete'. Defaults to 'create'.",
                    "default": "create",
                },
                "field_type": {
                    "type": "string",
                    "enum": ["WIND", "TURBULENCE", "VORTEX"],
                    "description": "Force field type: WIND (directional air velocity), TURBULENCE (pseudorandom turbulent disturbance), or VORTEX (spiral vortex flow).",
                    "default": "WIND",
                },
                "strength": {
                    "type": "number",
                    "description": "Strength of the force field (-100000.0 to 100000.0). Defaults to 1.0.",
                    "minimum": -100000.0,
                    "maximum": 100000.0,
                    "default": 1.0,
                },
                "flow": {
                    "type": "number",
                    "description": "Air flow velocity conversion factor (0.0 to 1000.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                    "default": 0.0,
                },
                "shape": {
                    "type": "string",
                    "enum": ["POINT", "LINE", "PLANE", "SURFACE", "POINTS"],
                    "description": "Directional effector shape calculation. Defaults to POINT.",
                    "default": "POINT",
                },
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "World coordinate location [x, y, z] for new or transformed force field.",
                },
                "rotation": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Euler rotation [rx, ry, rz] in radians (defines orientation for directional fields like WIND).",
                },
                "wind_factor": {
                    "type": "number",
                    "description": "How much the force is reduced when acting parallel to a surface (0.0 to 1.0, e.g. cloth). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 1.0,
                },
                "size": {
                    "type": "number",
                    "description": "Size scale of the turbulence perturbation (0.0 to 1000.0, for TURBULENCE). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                    "default": 1.0,
                },
                "use_global_coords": {
                    "type": "boolean",
                    "description": "Use effector global coordinates for turbulence noise evaluation (for TURBULENCE). Defaults to False.",
                    "default": False,
                },
                "inflow": {
                    "type": "number",
                    "description": "Inwards radial suction component of vortex force (-1000.0 to 1000.0, for VORTEX). Defaults to 0.0.",
                    "minimum": -1000.0,
                    "maximum": 1000.0,
                },
                "noise": {
                    "type": "number",
                    "description": "Amount of noise perturbation added to force strength (0.0 to 10.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 0.0,
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for force field noise evaluation (1 to 128). Defaults to 1.",
                    "minimum": 1,
                    "maximum": 128,
                    "default": 1,
                },
                "falloff_power": {
                    "type": "number",
                    "description": "Power of distance falloff curve (0.0 to 10.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 0.0,
                },
                "use_min_distance": {
                    "type": "boolean",
                    "description": "Whether to enforce a minimum distance for force falloff. Defaults to False.",
                    "default": False,
                },
                "distance_min": {
                    "type": "number",
                    "description": "Minimum distance for field falloff (0.0 to 1000.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                    "default": 0.0,
                },
                "use_max_distance": {
                    "type": "boolean",
                    "description": "Whether to enforce a maximum distance for force influence. Defaults to False.",
                    "default": False,
                },
                "distance_max": {
                    "type": "number",
                    "description": "Maximum distance for field influence (0.0 to 100000.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 100000.0,
                    "default": 0.0,
                },
                "use_2d_force": {
                    "type": "boolean",
                    "description": "Apply force only in the 2D plane perpendicular to local Z. Defaults to False.",
                    "default": False,
                },
                "z_direction": {
                    "type": "string",
                    "enum": ["POSITIVE", "NEGATIVE", "BOTH"],
                    "description": "Effect in full, positive, or negative Z direction. Defaults to BOTH.",
                    "default": "BOTH",
                },
                "falloff_type": {
                    "type": "string",
                    "enum": ["CONE", "SPHERE", "TUBE"],
                    "description": "Falloff geometry shape. Defaults to SPHERE.",
                    "default": "SPHERE",
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Expected state snapshot ID for optimistic concurrency control.",
                },
                "snapshot_id": {
                    "type": "string",
                    "description": "Alias for expected_snapshot_id.",
                },
                "delete_object": {
                    "type": "boolean",
                    "description": "For remove action: whether to delete the empty object itself (True) or only reset field type to NONE (False). Defaults to False.",
                    "default": False,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_FORCE_FIELD: {
        "name": TOOL_INSPECT_FORCE_FIELD,
        "description": "Inspect active physics force fields in the scene or on a specific object.",
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Optional name of the force field object to inspect. If omitted, all force fields in the scene are reported.",
                },
                "object_name": {
                    "type": "string",
                    "description": "Alias for name.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_PARTICLE_SYSTEM: {
        "name": TOOL_CONFIGURE_PARTICLE_SYSTEM,
        "description": (
            "Create, configure, inspect, or remove emitter or hair particle systems on mesh objects "
            "with full parameter controls (count, lifetime, initial velocity, hair dynamics cloth solver, "
            "object/collection instancing) and transactional rollback."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name of the target mesh object (alias: name).",
                },
                "name": {
                    "type": "string",
                    "description": "Alias for object_name.",
                },
                "system_name": {
                    "type": "string",
                    "description": "Name of the particle system (default: 'ParticleSystem').",
                    "default": "ParticleSystem",
                },
                "action": {
                    "type": "string",
                    "enum": ["create", "add", "configure", "inspect", "remove", "delete"],
                    "description": "Action to perform: 'create'/'add', 'configure', 'inspect', or 'remove'/'delete'. Defaults to 'create'.",
                    "default": "create",
                },
                "system_type": {
                    "type": "string",
                    "enum": ["EMITTER", "HAIR"],
                    "description": "Particle system type ('EMITTER' or 'HAIR'). Defaults to 'EMITTER'.",
                    "default": "EMITTER",
                },
                "hair_length": {
                    "type": "number",
                    "description": "Length of hair strands in meters (0.0001 to 10000.0). Used when system_type is HAIR. Defaults to 4.0.",
                    "minimum": 0.0001,
                    "maximum": 10000.0,
                    "default": 4.0,
                },
                "hair_step": {
                    "type": "integer",
                    "description": "Number of hair segments/keys per strand (1 to 7). Used when system_type is HAIR. Defaults to 5.",
                    "minimum": 1,
                    "maximum": 7,
                    "default": 5,
                },
                "use_hair_dynamics": {
                    "type": "boolean",
                    "description": "Whether physics dynamics (cloth solver) is enabled for hair strands. Defaults to False.",
                    "default": False,
                },
                "hair_dynamics_quality": {
                    "type": "integer",
                    "description": "Hair dynamics simulation solver quality steps (1 to 80). Defaults to 5.",
                    "minimum": 1,
                    "maximum": 80,
                    "default": 5,
                },
                "hair_dynamics_mass": {
                    "type": "number",
                    "description": "Hair dynamics mass per strand in kg (0.0001 to 10000.0). Defaults to 1.0.",
                    "minimum": 0.0001,
                    "maximum": 10000.0,
                    "default": 1.0,
                },
                "hair_dynamics_bending_stiffness": {
                    "type": "number",
                    "description": "Hair dynamics bending stiffness (0.0 to 10000.0). Defaults to 0.5.",
                    "minimum": 0.0,
                    "maximum": 10000.0,
                    "default": 0.5,
                },
                "hair_dynamics_air_damping": {
                    "type": "number",
                    "description": "Hair dynamics air damping (0.0 to 10.0). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "hair_dynamics_pin_stiffness": {
                    "type": "number",
                    "description": "Hair dynamics pin stiffness at the root (0.0 to 10000.0). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 10000.0,
                    "default": 1.0,
                },
                "count": {
                    "type": "integer",
                    "description": "Total number of emitted particles (1 to 1000000). Defaults to 1000.",
                    "minimum": 1,
                    "maximum": 1000000,
                    "default": 1000,
                },
                "frame_start": {
                    "type": "number",
                    "description": "Starting frame for particle emission. Defaults to 1.0.",
                    "minimum": -100000.0,
                    "maximum": 100000.0,
                    "default": 1.0,
                },
                "frame_end": {
                    "type": "number",
                    "description": "Ending frame for particle emission. Defaults to 200.0.",
                    "minimum": -100000.0,
                    "maximum": 100000.0,
                    "default": 200.0,
                },
                "lifetime": {
                    "type": "number",
                    "description": "Lifetime of particles in frames (0.1 to 100000.0). Defaults to 50.0.",
                    "minimum": 0.1,
                    "maximum": 100000.0,
                    "default": 50.0,
                },
                "lifetime_random": {
                    "type": "number",
                    "description": "Random variation factor for particle lifetime (0.0 to 1.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                },
                "normal_factor": {
                    "type": "number",
                    "description": "Initial velocity along surface normal (-1000.0 to 1000.0). Defaults to 1.0.",
                    "minimum": -1000.0,
                    "maximum": 1000.0,
                    "default": 1.0,
                },
                "tangent_factor": {
                    "type": "number",
                    "description": "Initial velocity along surface tangent (-1000.0 to 1000.0). Defaults to 0.0.",
                    "minimum": -1000.0,
                    "maximum": 1000.0,
                    "default": 0.0,
                },
                "object_factor": {
                    "type": "number",
                    "description": "Emitter object movement velocity factor (0.0 to 1000.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                    "default": 0.0,
                },
                "factor_random": {
                    "type": "number",
                    "description": "Random velocity perturbation factor (0.0 to 1000.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1000.0,
                    "default": 0.0,
                },
                "object_align_factor": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Initial velocity aligned with object axes [x, y, z].",
                },
                "physics_type": {
                    "type": "string",
                    "enum": ["NEWTON", "NO", "KEYED", "BOIDS", "FLUID"],
                    "description": "Particle physics solver type. Defaults to NEWTON.",
                    "default": "NEWTON",
                },
                "mass": {
                    "type": "number",
                    "description": "Mass of individual particles in kg (0.00001 to 10000.0). Defaults to 1.0.",
                    "minimum": 0.00001,
                    "maximum": 10000.0,
                    "default": 1.0,
                },
                "particle_size": {
                    "type": "number",
                    "description": "Display/instance size of particles in meters (0.0001 to 1000.0). Defaults to 0.05.",
                    "minimum": 0.0001,
                    "maximum": 1000.0,
                    "default": 0.05,
                },
                "size_random": {
                    "type": "number",
                    "description": "Random size variation factor (0.0 to 1.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                },
                "render_type": {
                    "type": "string",
                    "enum": ["NONE", "HALO", "LINE", "PATH", "OBJECT", "COLLECTION"],
                    "description": "Particle visualization/instancing render type. Defaults to HALO.",
                    "default": "HALO",
                },
                "instance_object": {
                    "type": "string",
                    "description": "Name of object to instance for each particle (used when render_type is OBJECT).",
                },
                "instance_collection": {
                    "type": "string",
                    "description": "Name of collection to instance for particles (used when render_type is COLLECTION).",
                },
                "use_scale_instance": {
                    "type": "boolean",
                    "description": "Whether instanced object/collection scales with particle size. Defaults to True.",
                    "default": True,
                },
                "use_global_instance": {
                    "type": "boolean",
                    "description": "Whether to use global coordinates for instanced object. Defaults to False.",
                    "default": False,
                },
                "delete_settings": {
                    "type": "boolean",
                    "description": "On removal: whether to delete unlinked ParticleSettings datablock from blender data. Defaults to True.",
                    "default": True,
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Expected state snapshot ID for optimistic concurrency control.",
                },
                "snapshot_id": {
                    "type": "string",
                    "description": "Alias for expected_snapshot_id.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_PARTICLE_SYSTEM: {
        "name": TOOL_INSPECT_PARTICLE_SYSTEM,
        "description": "Inspect active emitter particle systems and evaluated particle states on objects.",
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Optional name of the object whose particle systems to inspect. If omitted, all particle systems across the scene are reported.",
                },
                "name": {
                    "type": "string",
                    "description": "Alias for object_name.",
                },
                "system_name": {
                    "type": "string",
                    "description": "Optional specific particle system name to inspect.",
                },
                "frame": {
                    "type": "integer",
                    "description": "Optional frame number to evaluate simulated particles at.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_CONFIGURE_FLUID_SIMULATION: {
        "name": TOOL_CONFIGURE_FLUID_SIMULATION,
        "description": (
            "Create, configure, inspect, or remove Mantaflow fluid simulations (Domain, Flow, Effector) "
            "for gas/smoke volumetrics and liquid simulations with parameter validation, safe interactive limits, "
            "optimistic concurrency, and transactional rollback."
        ),
        "permission_tier": PERMISSION_SCENE_MUTATION,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name of the target mesh object (alias: name).",
                },
                "name": {
                    "type": "string",
                    "description": "Alias for object_name.",
                },
                "action": {
                    "type": "string",
                    "enum": ["create", "add", "configure", "inspect", "remove", "delete"],
                    "description": "Action to perform: 'create'/'add', 'configure', 'inspect', or 'remove'/'delete'. Defaults to 'create'.",
                    "default": "create",
                },
                "fluid_type": {
                    "type": "string",
                    "enum": ["DOMAIN", "FLOW", "EFFECTOR"],
                    "description": "Fluid role on object: 'DOMAIN' (gas/liquid boundary), 'FLOW' (emitter/inflow/outflow), or 'EFFECTOR' (collision/guide). Defaults to 'DOMAIN'.",
                    "default": "DOMAIN",
                },
                "domain_type": {
                    "type": "string",
                    "enum": ["GAS", "LIQUID"],
                    "description": "Domain simulation type: 'GAS' (smoke/fire volumetrics) or 'LIQUID' (water/fluid surface). Defaults to 'GAS'.",
                    "default": "GAS",
                },
                "resolution_max": {
                    "type": "integer",
                    "description": "Max resolution divisions for fluid domain grid (16 to 256). Defaults to 32.",
                    "minimum": 16,
                    "maximum": 256,
                    "default": 32,
                },
                "time_scale": {
                    "type": "number",
                    "description": "Simulation time playback scale (0.0001 to 10.0). Defaults to 1.0.",
                    "minimum": 0.0001,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "cfl_condition": {
                    "type": "number",
                    "description": "CFL condition threshold (0.0 to 10.0). Defaults to 2.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 2.0,
                },
                "use_adaptive_timesteps": {
                    "type": "boolean",
                    "description": "Whether to use adaptive timestepping based on CFL condition. Defaults to True.",
                    "default": True,
                },
                "timesteps_min": {
                    "type": "integer",
                    "description": "Minimum simulation timesteps per frame (1 to 100). Defaults to 1.",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 1,
                },
                "timesteps_max": {
                    "type": "integer",
                    "description": "Maximum simulation timesteps per frame (1 to 100). Defaults to 4.",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 4,
                },
                "alpha": {
                    "type": "number",
                    "description": "Gas buoyancy density factor (-5.0 to 5.0). Defaults to 1.0.",
                    "minimum": -5.0,
                    "maximum": 5.0,
                    "default": 1.0,
                },
                "beta": {
                    "type": "number",
                    "description": "Gas buoyancy heat factor (-5.0 to 5.0). Defaults to 1.0.",
                    "minimum": -5.0,
                    "maximum": 5.0,
                    "default": 1.0,
                },
                "vorticity": {
                    "type": "number",
                    "description": "Gas turbulence vorticity / swirl factor (0.0 to 4.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 4.0,
                    "default": 0.0,
                },
                "use_dissolve_smoke": {
                    "type": "boolean",
                    "description": "Whether smoke dissolves over time. Defaults to False.",
                    "default": False,
                },
                "dissolve_speed": {
                    "type": "integer",
                    "description": "Number of frames for smoke to dissolve (1 to 10000). Defaults to 5.",
                    "minimum": 1,
                    "maximum": 10000,
                    "default": 5,
                },
                "burning_rate": {
                    "type": "number",
                    "description": "Fire burning speed rate (0.01 to 4.0). Defaults to 0.75.",
                    "minimum": 0.01,
                    "maximum": 4.0,
                    "default": 0.75,
                },
                "flame_smoke": {
                    "type": "number",
                    "description": "Amount of smoke generated by fire (0.0 to 8.0). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 8.0,
                    "default": 1.0,
                },
                "flame_vorticity": {
                    "type": "number",
                    "description": "Additional vorticity created by flames (0.0 to 2.0). Defaults to 0.5.",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "default": 0.5,
                },
                "simulation_method": {
                    "type": "string",
                    "enum": ["FLIP", "APIC"],
                    "description": "Liquid simulation method ('FLIP' or 'APIC'). Defaults to 'FLIP'.",
                    "default": "FLIP",
                },
                "flip_ratio": {
                    "type": "number",
                    "description": "Ratio of FLIP to PIC velocity update (0.0 to 1.0). Defaults to 0.97.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.97,
                },
                "particle_radius": {
                    "type": "number",
                    "description": "Particle radius factor relative to cell size (0.0 to 10.0). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "use_mesh": {
                    "type": "boolean",
                    "description": "Whether surface mesh generation is enabled for liquid domain. Defaults to True.",
                    "default": True,
                },
                "mesh_scale": {
                    "type": "integer",
                    "description": "Resolution scale factor for generated liquid mesh (1 to 100). Defaults to 2.",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 2,
                },
                "use_diffusion": {
                    "type": "boolean",
                    "description": "Whether liquid viscosity diffusion is enabled. Defaults to False.",
                    "default": False,
                },
                "viscosity_base": {
                    "type": "number",
                    "description": "Viscosity base factor for liquid (0.0 to 10.0). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "viscosity_exponent": {
                    "type": "integer",
                    "description": "Viscosity exponent value (10^-n) (0 to 10). Defaults to 6.",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 6,
                },
                "surface_tension": {
                    "type": "number",
                    "description": "Surface tension of liquid (0.0 to 100.0). Defaults to 0.0.",
                    "minimum": 0.0,
                    "maximum": 100.0,
                    "default": 0.0,
                },
                "cache_type": {
                    "type": "string",
                    "enum": ["REPLAY", "MODULAR", "ALL"],
                    "description": "Cache type for domain ('REPLAY', 'MODULAR', 'ALL'). Defaults to 'REPLAY'.",
                    "default": "REPLAY",
                },
                "cache_frame_start": {
                    "type": "integer",
                    "description": "Start frame of simulation cache (1 to 100000). Defaults to 1.",
                    "minimum": 1,
                    "maximum": 100000,
                    "default": 1,
                },
                "cache_frame_end": {
                    "type": "integer",
                    "description": "End frame of simulation cache (1 to 100000, max span <= 250). Defaults to 50.",
                    "minimum": 1,
                    "maximum": 100000,
                    "default": 50,
                },
                "flow_type": {
                    "type": "string",
                    "enum": ["SMOKE", "BOTH", "FIRE", "LIQUID"],
                    "description": "Flow emission type: 'SMOKE', 'BOTH' (fire+smoke), 'FIRE', or 'LIQUID'. Defaults to 'SMOKE'.",
                    "default": "SMOKE",
                },
                "flow_behavior": {
                    "type": "string",
                    "enum": ["INFLOW", "OUTFLOW", "GEOMETRY"],
                    "description": "Flow behavior: 'INFLOW' (continuous stream), 'OUTFLOW' (drain/sink), or 'GEOMETRY' (one-time volume). Defaults to 'GEOMETRY'.",
                    "default": "GEOMETRY",
                },
                "density": {
                    "type": "number",
                    "description": "Flow emission density (0.0 to 10.0). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "fuel_amount": {
                    "type": "number",
                    "description": "Flow emission fuel amount for fire (0.0 to 10.0). Defaults to 1.0.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "temperature": {
                    "type": "number",
                    "description": "Flow emission temperature difference (-10.0 to 10.0). Defaults to 1.0.",
                    "minimum": -10.0,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "use_inflow": {
                    "type": "boolean",
                    "description": "Whether inflow is actively emitting. Defaults to True.",
                    "default": True,
                },
                "surface_distance": {
                    "type": "number",
                    "description": "Distance from mesh surface for flow/effector emission (0.0 to 10.0). Defaults to 1.0 for flow, 0.0 for effector.",
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "default": 1.0,
                },
                "subframes": {
                    "type": "integer",
                    "description": "Emission subframes for fast-moving flow/effector objects (0 to 200). Defaults to 0.",
                    "minimum": 0,
                    "maximum": 200,
                    "default": 0,
                },
                "use_initial_velocity": {
                    "type": "boolean",
                    "description": "Whether to impart initial velocity to emitted fluid. Defaults to False.",
                    "default": False,
                },
                "velocity_factor": {
                    "type": "number",
                    "description": "Velocity multiplier (-100.0 to 100.0). Defaults to 1.0.",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": 1.0,
                },
                "velocity_normal": {
                    "type": "number",
                    "description": "Normal velocity component (-100.0 to 100.0). Defaults to 0.0.",
                    "minimum": -100.0,
                    "maximum": 100.0,
                    "default": 0.0,
                },
                "velocity_coord": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Cartesian initial velocity vector [X, Y, Z]. Defaults to [0.0, 0.0, 0.0].",
                    "default": [0.0, 0.0, 0.0],
                },
                "effector_type": {
                    "type": "string",
                    "enum": ["COLLISION", "GUIDE"],
                    "description": "Effector role: 'COLLISION' (solid obstacle/deflector) or 'GUIDE' (flow director). Defaults to 'COLLISION'.",
                    "default": "COLLISION",
                },
                "use_effector": {
                    "type": "boolean",
                    "description": "Whether effector influence is enabled. Defaults to True.",
                    "default": True,
                },
                "use_plane_init": {
                    "type": "boolean",
                    "description": "Treat effector as planar surface rather than closed volume. Defaults to False.",
                    "default": False,
                },
                "expected_snapshot_id": {
                    "type": "string",
                    "description": "Expected state snapshot ID for optimistic concurrency control.",
                },
                "snapshot_id": {
                    "type": "string",
                    "description": "Alias for expected_snapshot_id.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task identifier.",
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_INSPECT_FLUID_SIMULATION: {
        "name": TOOL_INSPECT_FLUID_SIMULATION,
        "description": "Inspect active Mantaflow fluid simulations (Domain, Flow, Effector) and cache state.",
        "permission_tier": PERMISSION_READ_ONLY,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Optional name of the object with fluid modifier to inspect. If omitted, all fluid objects in the scene are reported.",
                },
                "name": {
                    "type": "string",
                    "description": "Alias for object_name.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED.",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
    },
    TOOL_OPEN_BLEND_FILE: {
        "name": TOOL_OPEN_BLEND_FILE,
        "description": (
            "Safely load and open an existing Blender (.blend) project file from disk. "
            "WARNING: Unloads current scene and datablocks. Requires confirm_discard_unsaved=True "
            "if current scene has unsaved modifications. Disables untrusted embedded scripts by default."
        ),
        "permission_tier": PERMISSION_DESTRUCTIVE,
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Absolute filesystem path to the target .blend file to open.",
                },
                "confirm_discard_unsaved": {
                    "type": "boolean",
                    "description": "Explicit confirmation to discard any unsaved modifications in the active project.",
                    "default": False,
                },
                "use_scripts": {
                    "type": "boolean",
                    "description": "Whether to allow embedded Python scripts in the opened file (defaults to False for security).",
                    "default": False,
                },
                "approved": {
                    "type": "boolean",
                    "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                    "default": False,
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task or workflow identifier.",
                },
            },
            "required": ["filepath"],
            "additionalProperties": False,
        },
    },
}

TOOL_DEFINITIONS[TOOL_INSPECT_SCENE_DATA]["input_schema"]["allOf"] = [{
    "if": {"anyOf": [{"required": [key]} for key in ("element_domain", "mesh_source", "expected_snapshot_id")]},
    "then": {"properties": {"category": {"const": "mesh_topology"}}, "required": ["target_name", "element_domain"]},
}, {"if": {"required": ["element_domain", "offset"], "properties": {"offset": {"minimum": 1}}},
    "then": {"required": ["expected_snapshot_id"]}}]

from blender_addon.universal_mcp.bridge.component_edit import SCHEMA as COMPONENT_SCHEMA, validate as validate_component_edit
TOOL_DEFINITIONS[TOOL_EDIT_MESH] = {
    "name":TOOL_EDIT_MESH,"permission_tier":PERMISSION_SCENE_MUTATION,
    "description":"Atomic typed base-mesh batch on an active-scene Object Mode mesh. Requires a base fingerprint. Component indices reference the initial snapshot, not reindexed intermediate data; deleted references fail. Stages privately, verifies geometry/state and rolls back before commit on error. Supports finite create/delete/extrude/inset/bevel/subdivide/quad-loop-cut/bridge/merge/dissolve/fill/normals/shading/vertex-control actions.",
    "input_schema":{**COMPONENT_SCHEMA,"properties":{**COMPONENT_SCHEMA["properties"],"approved":{"type":"boolean","default":False,"description":"Untrusted; never authorization."}}},
}

from blender_addon.universal_mcp.bridge.modifier_contract import PROPERTY_SPECS, validate_modifier_params
from blender_addon.universal_mcp.bridge.render_outputs import validate_render_id

TOOL_DEFINITIONS[TOOL_INSPECT_RENDER_OUTPUT] = {
    "name": TOOL_INSPECT_RENDER_OUTPUT, "permission_tier": PERMISSION_READ_ONLY,
    "description": "Verify a registered still-render receipt against the current output file. Checks identity, SHA-256 and PNG CRC/dimensions/decoded scanlines. No caller file paths; unknown, expired, changed or missing artifacts fail explicitly.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["render_id"],
        "properties": {"render_id": {"type": "string", "pattern": "^[0-9a-f]{32}$", "minLength": 32, "maxLength": 32}}},
}
from blender_addon.universal_mcp.bridge.material_shader_contract import PRINCIPLED, NOISE, validate_material_shader

def _shader_input_schema(specs):
    return {"type": "object", "minProperties": 1, "additionalProperties": False, "properties": {
        key: ({"type": "array", "minItems": 4, "maxItems": 4,
               "items": {"type": "number", "minimum": low, "maximum": high}} if key == "base_color" else
              {"type": "number", "minimum": low, "maximum": high}) for key, (_, low, high) in specs.items()}}

TOOL_DEFINITIONS[TOOL_CONFIGURE_MATERIAL_SHADER] = {
    "name": TOOL_CONFIGURE_MATERIAL_SHADER, "permission_tier": PERMISSION_SCENE_MUTATION,
    "description": "Typed Principled Base Color/Metallic/Roughness/IOR writes and add/update/remove of one Noise.Color to Base Color graph. Exact sockets only; conflicting links rejected. Requires trusted approval and separate readback.",
    "input_schema": {"type": "object", "additionalProperties": False,
        "required": ["target_name", "bsdf_node_name", "action"], "properties": {
            "target_name": {"type": "string", "minLength": 1, "maxLength": 63},
            "bsdf_node_name": {"type": "string", "minLength": 1, "maxLength": 63},
            "noise_node_name": {"type": "string", "minLength": 1, "maxLength": 63},
            "action": {"type": "string", "enum": ["set_principled", "add_noise", "update_noise", "remove_noise"]},
            "inputs": _shader_input_schema(PRINCIPLED), "noise_inputs": _shader_input_schema(NOISE),
            "approved": {"type": "boolean", "default": False, "description": "Untrusted flag, never approval proof."},
            "task_id": {"type": "string"},
        }, "allOf": [
            {"if": {"properties": {"action": {"const": "set_principled"}}},
             "then": {"required": ["inputs"], "not": {"anyOf": [{"required": ["noise_inputs"]}, {"required": ["noise_node_name"]}]}},
             "else": {"required": ["noise_node_name"], "not": {"required": ["inputs"]}}},
            {"if": {"properties": {"action": {"enum": ["add_noise", "update_noise"]}}}, "then": {"required": ["noise_inputs"]}},
            {"if": {"properties": {"action": {"const": "remove_noise"}}}, "then": {"not": {"required": ["noise_inputs"]}}},
        ]},
}
TOOL_DEFINITIONS[TOOL_INSPECT_MATERIAL_SHADER] = {
    "name": TOOL_INSPECT_MATERIAL_SHADER, "permission_tier": PERMISSION_READ_ONLY,
    "description": "Read-only material graph snapshot: exact node types, supported input values and socket-identifier links. Never enables nodes or changes materials.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["target_name"],
                     "properties": {"target_name": {"type": "string", "minLength": 1, "maxLength": 63}}},
}

from blender_addon.universal_mcp.bridge.geometry_contract import SCHEMA as MODELING_GEOMETRY_SCHEMA, INSPECTION as MODELING_GEOMETRY_INSPECTION, validate as validate_modeling_geometry
TOOL_DEFINITIONS[TOOL_CONFIGURE_MODELING_GEOMETRY]={"name":TOOL_CONFIGURE_MODELING_GEOMETRY,"permission_tier":PERMISSION_SCENE_MUTATION,"description":"Finite transactional full Geometry Nodes specification: typed nodes/parameters/links, exact socket identifiers (root semantic names), evaluated mesh readback. No arbitrary nodes or external references. Finite contract verified in disposable Blender 5.2.2; broader domain remains partial.","input_schema":MODELING_GEOMETRY_SCHEMA}
TOOL_DEFINITIONS[TOOL_INSPECT_MODELING_GEOMETRY]={"name":TOOL_INSPECT_MODELING_GEOMETRY,"permission_tier":PERMISSION_READ_ONLY,"description":"Read finite Geometry Nodes graph/interface/instance parameters and base/evaluated geometry fingerprints. Missing modifier is reported honestly.","input_schema":MODELING_GEOMETRY_INSPECTION}

from blender_addon.universal_mcp.bridge.object_controls import SCHEMA as OBJECT_CONTROL_SCHEMA, INSPECTION as OBJECT_CONTROL_INSPECTION, validate as validate_object_control
TOOL_DEFINITIONS[TOOL_CONFIGURE_MODELING_OBJECT]={"name":TOOL_CONFIGURE_MODELING_OBJECT,"permission_tier":PERMISSION_SCENE_MUTATION,"description":"Snapshot-bound finite local/world delta transform with explicit pivot, world-preserving parent/clear_parent, selection. Rejects shear, singular scales, animated/constrained/linked targets and cycles. Finite contract verified in disposable Blender 5.2.2; broader domain remains partial.","input_schema":OBJECT_CONTROL_SCHEMA}
TOOL_DEFINITIONS[TOOL_INSPECT_MODELING_OBJECT]={"name":TOOL_INSPECT_MODELING_OBJECT,"permission_tier":PERMISSION_READ_ONLY,"description":"Read modeling-object world/basis/parent-inverse matrices, parent and selection/active context snapshot. Object Mode only.","input_schema":OBJECT_CONTROL_INSPECTION}

from blender_addon.universal_mcp.bridge.curve_contract import SCHEMA as CURVE_GEOMETRY_SCHEMA, INSPECTION as CURVE_GEOMETRY_INSPECTION, validate as validate_curve_geometry
TOOL_DEFINITIONS[TOOL_CONFIGURE_CURVE_GEOMETRY] = {
    "name":TOOL_CONFIGURE_CURVE_GEOMETRY,"permission_tier":PERMISSION_SCENE_MUTATION,
    "description":"Finite atomic curve/text create/update or evaluated copy_to_mesh. Explicit Bezier/poly/NURBS splines/control points, text body/settings, bevel/extrusion. Update requires current snapshot; converted copy preserves source. Finite contract verified in disposable Blender 5.2.2; not arbitrary curve conversion support.",
    "input_schema":CURVE_GEOMETRY_SCHEMA}
TOOL_DEFINITIONS[TOOL_INSPECT_CURVE_GEOMETRY] = {
    "name":TOOL_INSPECT_CURVE_GEOMETRY,"permission_tier":PERMISSION_READ_ONLY,
    "description":"Read actual finite curve/text spline/control-point/settings and independently evaluated mesh fingerprint/counts; also inspects converted mesh copies. Object Mode only.",
    "input_schema":CURVE_GEOMETRY_INSPECTION}

from blender_addon.universal_mcp.bridge.advanced_modifier_contract import SCHEMA as MODIFIER_STACK_SCHEMA, INSPECTION as MODIFIER_STACK_INSPECTION, validate as validate_modifier_stack
TOOL_DEFINITIONS[TOOL_EDIT_MODIFIER_STACK] = {
    "name": TOOL_EDIT_MODIFIER_STACK, "permission_tier": PERMISSION_SCENE_MUTATION,
    "description": "Finite modifier stack transaction: add/update/remove/reorder/visibility/apply for SUBSURF, BEVEL, SOLIDIFY, BOOLEAN, MIRROR and ARRAY. Requires current inspector snapshot and trusted approval. Apply only the first viewport-enabled modifier; rejects animated, linked and shape-key targets. Finite contract verified in disposable Blender 5.2.2; not universal modifier support.",
    "input_schema": MODIFIER_STACK_SCHEMA,
}
TOOL_DEFINITIONS[TOOL_INSPECT_MODIFIER_STACK] = {
    "name": TOOL_INSPECT_MODIFIER_STACK, "permission_tier": PERMISSION_READ_ONLY,
    "description": "Read ordered finite modifier properties and visibility, base and evaluated topology fingerprints/counts, plus an optimistic concurrency snapshot. Object mode only.",
    "input_schema": MODIFIER_STACK_INSPECTION,
}

TOOL_DEFINITIONS[TOOL_APPLY_MODIFIER] = {
    "name": TOOL_APPLY_MODIFIER,
    "description": (
        "Apply the first, viewport-enabled modifier in the stack to the target mesh object. "
        "Converts evaluated modifier geometry into permanent base mesh geometry with independent readback and transactional rollback."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target mesh object in the active scene.",
            },
            "target_object": {
                "type": "string",
                "description": "Alias for name.",
            },
            "object_name": {
                "type": "string",
                "description": "Alias for name.",
            },
            "modifier_name": {
                "type": "string",
                "description": "Name of the modifier to apply (must be the first viewport-enabled modifier in stack).",
            },
            "modifier_type": {
                "type": "string",
                "enum": ["SUBSURF", "BEVEL", "SOLIDIFY", "BOOLEAN", "MIRROR", "ARRAY"],
                "description": "Type of modifier to apply. Inferred from object modifier stack if omitted.",
            },
            "expected_snapshot_id": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "Modifier stack snapshot fingerprint from inspect_modifier_stack.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
        "required": ["name", "modifier_name", "expected_snapshot_id"],
        "additionalProperties": False,
    },
}

from blender_addon.universal_mcp.bridge.sculpt_contract import validate as validate_sculpt
TOOL_DEFINITIONS[TOOL_SCULPT_MESH] = {
    "name": TOOL_SCULPT_MESH, "permission_tier": PERMISSION_SCENE_MUTATION,
    "description": "Finite snapshot-bound sculpt controls: mode lifecycle, existing sculpt brush/settings, normalized View3D brush stroke, voxel remesh and dynamic topology. Main-thread only; mutations require normal human approval and independent mesh readback.",
    "input_schema": {"type":"object","additionalProperties":False,"required":["object_name","action","expected_snapshot_id"],"properties":{
        "object_name":{"type":"string","minLength":1,"maxLength":63},
        "action":{"type":"string","enum":["enter_sculpt","exit_sculpt","set_brush","set_brush_settings","stroke","voxel_remesh","set_dyntopo","sculpt_organic_anatomy","organic_anatomy"]},
        "expected_snapshot_id":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},
        "brush_name":{"type":"string","minLength":1,"maxLength":63},
        "settings":{"type":"object","minProperties":1,"additionalProperties":False,"properties":{
            "size":{"type":"integer","minimum":1,"maximum":500},"strength":{"type":"number","minimum":0,"maximum":1},
            "use_frontface":{"type":"boolean"},"use_accumulate":{"type":"boolean"},"use_pressure_size":{"type":"boolean"},"use_pressure_strength":{"type":"boolean"}}},
        "points":{"type":"array","minItems":2,"maxItems":256,"items":{"type":"object","additionalProperties":False,"required":["x","y"],"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"pressure":{"type":"number","minimum":0,"maximum":1}}}},
        "voxel_size":{"type":"number","minimum":0.001,"maximum":1},"enabled":{"type":"boolean"},
        "detail_mode":{"type":"string","enum":["RELATIVE","CONSTANT"]},"detail_size":{"type":"number","minimum":0.001,"maximum":100},
        "brush_type":{"type":"string","enum":["GRAB","INFLATE","SMOOTH","CLAY","DRAW"]},
        "radius":{"type":"number","minimum":0.001,"maximum":10.0},
        "strength":{"type":"number","minimum":0.0,"maximum":1.0},
        "max_displacement":{"type":"number","minimum":0.001,"maximum":2.0},
        "iterations":{"type":"integer","minimum":1,"maximum":10},
        "preserve_topology":{"type":"boolean"},
        "dynamic_topology":{"type":"boolean"},
        "request_id":{"type":"string"},"approval_token":{"type":"string"},"task_id":{"type":"string"}}}
}
TOOL_DEFINITIONS[TOOL_LOAD_REFERENCE_IMAGE] = {
    "name": TOOL_LOAD_REFERENCE_IMAGE,
    "description": (
        "Load a reference image into the Blender scene as a native Image Empty object or "
        "calibrated textured mesh plane for visual alignment and reference-driven 3D modeling. "
        "Supports front, side, and top orthographic alignment."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["image_path"],
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Filesystem path to the reference image (.png, .jpg, .jpeg, .webp, .tga, .bmp, .tif, .tiff, .exr).",
            },
            "name": {
                "type": "string",
                "description": "Name for the created Blender object.",
                "default": "Reference_Image",
            },
            "display_mode": {
                "type": "string",
                "description": "Display representation: 'EMPTY' (Blender Image Empty) or 'PLANE' (calibrated textured mesh plane).",
                "enum": ["EMPTY", "PLANE"],
                "default": "EMPTY",
            },
            "view_axis": {
                "type": "string",
                "description": "Orthographic view alignment: 'FRONT' (facing -Y), 'SIDE' (facing +X), 'TOP' (facing +Z), or 'USER' (custom rotation).",
                "enum": ["FRONT", "SIDE", "TOP", "USER"],
                "default": "FRONT",
            },
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "3D spatial position [x, y, z] in Blender units (meters).",
                "default": [0.0, 0.0, 0.0],
            },
            "rotation_euler": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Explicit Euler rotation [rx, ry, rz] in radians. Overrides view_axis default when provided.",
            },
            "scale": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Scale factors [sx, sy, sz].",
                "default": [1.0, 1.0, 1.0],
            },
            "size": {
                "type": "number",
                "description": "Primary dimension (meters) of the empty display size or plane dimension.",
                "minimum": 0.01,
                "maximum": 10000.0,
                "default": 5.0,
            },
            "opacity": {
                "type": "number",
                "description": "Display transparency/alpha (0.0 = transparent, 1.0 = opaque).",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.8,
            },
            "depth": {
                "type": "string",
                "description": "Display depth relative to geometry: 'DEFAULT', 'FRONT', or 'BACK'.",
                "enum": ["DEFAULT", "FRONT", "BACK"],
                "default": "DEFAULT",
            },
            "crop_box": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional normalized crop bounds [u_min, v_min, u_max, v_max] in [0.0, 1.0].",
            },
            "coordinate_system": {
                "type": "string",
                "enum": ["UV", "IMAGE_SPACE"],
                "default": "UV",
                "description": "Coordinate convention: 'UV' (default, [0,0] bottom-left) or 'IMAGE_SPACE' ([0,0] top-left).",
            },
            "output_path": {
                "type": "string",
                "description": "Destination file path for cropped image when crop_box is provided. Must not overwrite source image.",
            },
        },
    },
}
TOOL_DEFINITIONS[TOOL_CROP_REFERENCE_IMAGE] = {
    "name": TOOL_CROP_REFERENCE_IMAGE,
    "description": (
        "Crop a rectangular region from a reference sheet image using normalized [u_min, v_min, u_max, v_max] "
        "coordinates, save the cropped image, and optionally load it as a calibrated Blender reference object "
        "(Image Empty or Plane) with orthographic view alignment (FRONT, SIDE, TOP, USER)."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["image_path", "crop_box"],
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Filesystem path to the source reference image (.png, .jpg, .jpeg, .webp, .tga, .bmp, .tif, .tiff, .exr).",
            },
            "crop_box": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 4,
                "maxItems": 4,
                "description": "Normalized bounding box [u_min, v_min, u_max, v_max] in [0.0, 1.0] range, where u_min < u_max and v_min < v_max.",
            },
            "coordinate_system": {
                "type": "string",
                "enum": ["UV", "IMAGE_SPACE"],
                "default": "UV",
                "description": "Coordinate convention: 'UV' (default, [0,0] bottom-left to [1,1] top-right) or 'IMAGE_SPACE' ([0,0] top-left to [1,1] bottom-right).",
            },
            "output_path": {
                "type": "string",
                "description": "Destination file path for the cropped image. Must not overwrite source image.",
            },
            "load_as_reference": {
                "type": "boolean",
                "default": True,
                "description": "If true, load the cropped image into Blender as a reference object.",
            },
            "name": {
                "type": "string",
                "description": "Name for the created Blender reference object.",
                "default": "Reference_Crop",
            },
            "display_mode": {
                "type": "string",
                "enum": ["EMPTY", "PLANE"],
                "default": "EMPTY",
                "description": "Display representation: 'EMPTY' (Blender Image Empty) or 'PLANE' (calibrated textured mesh plane).",
            },
            "view_axis": {
                "type": "string",
                "enum": ["FRONT", "SIDE", "TOP", "USER"],
                "default": "FRONT",
                "description": "Orthographic view alignment: 'FRONT' (facing -Y), 'SIDE' (facing +X), 'TOP' (facing +Z), or 'USER' (custom rotation).",
            },
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "3D spatial position [x, y, z] in Blender units (meters).",
                "default": [0.0, 0.0, 0.0],
            },
            "rotation_euler": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Explicit Euler rotation [rx, ry, rz] in radians. Overrides view_axis default when provided.",
            },
            "scale": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Scale factors [sx, sy, sz].",
                "default": [1.0, 1.0, 1.0],
            },
            "size": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 10000.0,
                "default": 5.0,
                "description": "Primary dimension (meters) of the empty display size or plane dimension.",
            },
            "opacity": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.8,
                "description": "Display transparency/alpha (0.0 = transparent, 1.0 = opaque).",
            },
            "depth": {
                "type": "string",
                "enum": ["DEFAULT", "FRONT", "BACK"],
                "default": "DEFAULT",
                "description": "Display depth relative to geometry: 'DEFAULT', 'FRONT', or 'BACK'.",
            },
        },
    },
}
TOOL_DEFINITIONS[TOOL_COMPARE_SILHOUETTE_ALIGNMENT] = {
    "name": TOOL_COMPARE_SILHOUETTE_ALIGNMENT,
    "description": (
        "Compare a rendered 3D model silhouette against a reference image (or cropped reference-sheet region) "
        "from a specified orthographic or camera view (FRONT, SIDE, TOP, PERSPECTIVE). "
        "Produces measurable pixel-level alignment evidence: dimensions, foreground masks, intersection, union, "
        "IoU (Intersection-over-Union), Sørensen-Dice coefficient, and divergence score."
    ),
    "permission_tier": PERMISSION_READ_ONLY,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["reference_image_path"],
        "properties": {
            "reference_image_path": {
                "type": "string",
                "description": "Filesystem path to the reference image file.",
            },
            "crop_box": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional normalized crop bounds [u_min, v_min, u_max, v_max] in [0.0, 1.0] for reference sheet regions.",
            },
            "coordinate_system": {
                "type": "string",
                "enum": ["UV", "IMAGE_SPACE"],
                "default": "UV",
                "description": "Coordinate convention for crop_box: 'UV' (default, [0,0] bottom-left) or 'IMAGE_SPACE' ([0,0] top-left).",
            },
            "view": {
                "type": "string",
                "enum": ["CURRENT", "FRONT", "SIDE", "TOP", "PERSPECTIVE"],
                "default": "FRONT",
                "description": "Camera/orthographic viewpoint to capture and evaluate.",
            },
            "mode": {
                "type": "string",
                "enum": ["CAMERA", "VIEWPORT"],
                "default": "CAMERA",
                "description": "Capture pipeline: 'CAMERA' (default, rendered frames) or 'VIEWPORT' (interactive window). Headless requires CAMERA.",
            },
            "camera_name": {
                "type": "string",
                "description": "Optional name of scene camera to use. If not specified, uses active scene camera.",
            },
            "rendered_image_path": {
                "type": "string",
                "description": "Optional filesystem path to a pre-rendered model image. When provided, skips in-engine render capture.",
            },
            "width": {
                "type": "integer",
                "minimum": 64,
                "maximum": 2048,
                "default": 512,
                "description": "Evaluation image width in pixels.",
            },
            "height": {
                "type": "integer",
                "minimum": 64,
                "maximum": 2048,
                "default": 512,
                "description": "Evaluation image height in pixels.",
            },
            "mask_threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.05,
                "description": "Sensitivity threshold for foreground silhouette detection (0.0 to 1.0).",
            },
            "reference_background_color": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 255.0},
                "minItems": 3,
                "maxItems": 4,
                "description": "Optional background color [R, G, B, (A)] of the reference image. If omitted, sampled from image corner.",
            },
            "diff_output_path": {
                "type": "string",
                "description": "Optional file path to save a color-coded visual difference mask (green=overlap, red=excess, blue=missed).",
            },
        },
    },
}

TOOL_DEFINITIONS[TOOL_CALIBRATE_REFERENCE_VIEWS] = {
    "name": TOOL_CALIBRATE_REFERENCE_VIEWS,
    "description": (
        "Align, scale, and position multi-view reference planes (FRONT, SIDE, TOP) in 3D space "
        "around a shared origin or target bounding box. Ensures consistent scale, ground alignment, "
        "and orthogonal placement for reference-driven modeling."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["views"],
        "properties": {
            "views": {
                "type": "array",
                "minItems": 1,
                "description": "List of reference views to calibrate.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "view_axis"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the reference object in Blender scene.",
                        },
                        "view_axis": {
                            "type": "string",
                            "enum": ["FRONT", "SIDE", "TOP"],
                            "description": "View alignment axis ('FRONT', 'SIDE', or 'TOP').",
                        },
                        "offset_distance": {
                            "type": "number",
                            "default": 5.0,
                            "description": "Offset distance (meters) along normal axis from origin.",
                        },
                        "flip_normal": {
                            "type": "boolean",
                            "default": False,
                            "description": "Whether to position on opposite side of normal axis.",
                        },
                        "scale": {
                            "type": "number",
                            "minimum": 0.001,
                            "default": 1.0,
                            "description": "Uniform scale factor applied to the reference object.",
                        },
                    },
                },
            },
            "origin": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "default": [0.0, 0.0, 0.0],
                "description": "3D spatial origin [x, y, z] in Blender units (meters) around which views are centered.",
            },
            "target_bounding_box": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": "Target model world-space bounding box [min_x, min_y, min_z, max_x, max_y, max_z] in meters. Must be non-degenerate.",
            },
            "align_ground": {
                "type": "boolean",
                "default": True,
                "description": "If true, aligns bottom of Front and Side reference planes to ground level (Z = origin_z or min_z).",
            },
            "reorient_rotations": {
                "type": "boolean",
                "default": True,
                "description": "If true, enforces canonical orthographic Euler rotations for each view axis.",
            },
        },
    },
}

VIEW_FIT_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["view", "reference_image_path"],
    "additionalProperties": False,
    "properties": {
        "view": {
            "type": "string",
            "enum": ["FRONT", "SIDE", "TOP"],
            "description": "Orthographic camera view: 'FRONT', 'SIDE', or 'TOP'.",
        },
        "reference_image_path": {
            "type": "string",
            "minLength": 1,
            "description": "Filesystem path to reference image or reference sheet file.",
        },
        "crop_box": {
            "type": "array",
            "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "minItems": 4,
            "maxItems": 4,
            "description": "Optional normalized crop bounds [u_min, v_min, u_max, v_max] in [0.0, 1.0].",
        },
        "coordinate_system": {
            "type": "string",
            "enum": ["UV", "IMAGE_SPACE"],
            "default": "UV",
            "description": "Coordinate system convention: 'UV' (bottom-left) or 'IMAGE_SPACE' (top-left).",
        },
        "weight": {
            "type": "number",
            "minimum": 0.01,
            "maximum": 10.0,
            "default": 1.0,
            "description": "Relative weight of this view in the aggregate objective score.",
        },
        "max_regression_tolerance": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 0.5,
            "default": 0.01,
            "description": "Maximum allowed decrease in IoU for this protected view per iteration or overall.",
        },
        "camera_name": {
            "type": "string",
            "description": "Optional scene camera name to use for this view.",
        },
    },
}

TOOL_DEFINITIONS[TOOL_OPTIMIZE_MESH_SILHOUETTE] = {
    "name": TOOL_OPTIMIZE_MESH_SILHOUETTE,
    "description": (
        "Iteratively deform and optimize an explicitly designated target mesh against a reference image "
        "or cropped reference-sheet view (FRONT, SIDE, TOP) using measured silhouette comparison. "
        "Enforces bounded transformation/displacement steps, monotonic IoU improvement, "
        "topology preservation, and automatic transactional rollback on failure or non-improvement."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object", "reference_image_path"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene to optimize.",
            },
            "reference_image_path": {
                "type": "string",
                "minLength": 1,
                "description": "Filesystem path to the reference image or reference sheet file.",
            },
            "view": {
                "type": "string",
                "enum": ["FRONT", "SIDE", "TOP"],
                "default": "FRONT",
                "description": "Orthographic camera viewpoint to optimize against: 'FRONT', 'SIDE', or 'TOP'.",
            },
            "crop_box": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional normalized crop bounds [u_min, v_min, u_max, v_max] in [0.0, 1.0] for reference sheet regions.",
            },
            "coordinate_system": {
                "type": "string",
                "enum": ["UV", "IMAGE_SPACE"],
                "default": "UV",
                "description": "Coordinate system convention for crop_box: 'UV' ([0,0] bottom-left) or 'IMAGE_SPACE' ([0,0] top-left).",
            },
            "optimization_mode": {
                "type": "string",
                "enum": ["BOUNDED_SCALE_TRANSLATE", "VERTEX_DISPLACEMENT", "HYBRID"],
                "default": "BOUNDED_SCALE_TRANSLATE",
                "description": "Deformation mode: 'BOUNDED_SCALE_TRANSLATE' (centroid & bounding extents), 'VERTEX_DISPLACEMENT' (contour vertex deformation), or 'HYBRID' (both).",
            },
            "preserve_topology": {
                "type": "boolean",
                "default": True,
                "description": "Strictly preserve mesh topology (vertex, edge, and face counts remain invariant).",
            },
            "max_iterations": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 5,
                "description": "Maximum number of optimization iterations to run (clamped between 1 and 20).",
            },
            "max_displacement": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 5.0,
                "default": 0.5,
                "description": "Maximum allowed displacement cap in Blender units (meters) per iteration.",
            },
            "step_size": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 2.0,
                "default": 0.2,
                "description": "Optimization step rate factor between 0.01 and 2.0.",
            },
            "tolerance": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.001,
                "description": "Minimum IoU improvement required to accept an iteration step.",
            },
            "resolution": {
                "type": "integer",
                "minimum": 64,
                "maximum": 1024,
                "default": 256,
                "description": "Evaluation image render width and height in pixels.",
            },
            "mask_threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.05,
                "description": "Sensitivity threshold for foreground silhouette detection (0.0 to 1.0).",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, automatically rollback mesh state if objective does not strictly improve or on error.",
            },
            "camera_name": {
                "type": "string",
                "description": "Optional scene camera name to use for projection.",
            },
            "views": {
                "type": "array",
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "minItems": 2,
                "maxItems": 3,
                "description": "Optional list of 2 or 3 view configurations for simultaneous multi-view fitting.",
            },
            "subdivision_levels": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4,
                "description": "Optional Catmull-Clark subdivision level for multiresolution refinement delegation (1 to 4).",
            },
            "subdivision_type": {
                "type": "string",
                "enum": ["CATMULL_CLARK", "SIMPLE"],
                "default": "CATMULL_CLARK",
                "description": "Subdivision algorithm to use when refining mesh.",
            },
            "refinement_mode": {
                "type": "string",
                "enum": ["MULTIRESOLUTION", "STANDARD", "SCULPT_ANATOMY", "LANDMARK_GUIDED", "SURFACE_DETAIL"],
                "default": "STANDARD",
                "description": "Optional refinement mode flag.",
            },
            "feature_type": {
                "type": "string",
                "enum": ["SCALES", "RIDGES", "FACETS", "VEINS"],
                "description": "Optional anatomical surface detail feature type for SURFACE_DETAIL mode.",
            },
            "depth": {
                "type": "number",
                "minimum": -1.0,
                "maximum": 1.0,
                "default": 0.05,
                "description": "Optional signed surface relief depth in meters for SURFACE_DETAIL mode.",
            },
            "feature_scale": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 5.0,
                "default": 0.2,
                "description": "Optional feature scale in meters for SURFACE_DETAIL mode.",
            },
            "preserve_landmarks": {
                "type": "boolean",
                "default": True,
                "description": "Optional flag to preserve semantic landmarks during refinement or detailing.",
            },
            "mask_vertex_group": {
                "type": "string",
                "maxLength": 63,
                "description": "Optional name of a vertex group on the mesh to restrict optimization.",
            },
            "use_symmetry": {
                "type": "boolean",
                "default": False,
                "description": "Whether to enforce bilateral symmetry across symmetry_axis during optimization.",
            },
            "symmetry_axis": {
                "type": "string",
                "enum": ["X", "Y", "Z", "NONE"],
                "default": "X",
                "description": "Reflection plane axis for bilateral symmetry.",
            },
            "landmarks": {
                "type": "array",
                "description": "Optional list of semantic landmark definitions for landmark-guided optimization.",
            },
            "max_vertex_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 20000,
                "description": "Upper vertex cap limit before rejecting refinement.",
            },
            "max_face_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 20000,
                "description": "Upper face/polygon cap limit before rejecting refinement.",
            },
            "brush_type": {
                "type": "string",
                "enum": ["GRAB", "INFLATE", "SMOOTH", "CLAY", "DRAW"],
                "description": "Optional brush operation for sculpt anatomy refinement delegation.",
            },
            "radius": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 10.0,
                "description": "Brush radius in meters for sculpt anatomy delegation.",
            },
            "strength": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Brush strength factor for sculpt anatomy delegation.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_FIT_MULTIVIEW_SILHOUETTE] = {
    "name": TOOL_FIT_MULTIVIEW_SILHOUETTE,
    "description": (
        "Simultaneously optimize a designated target mesh against multiple calibrated reference views "
        "(FRONT, SIDE, TOP) using measured silhouette comparison. Jointly optimizes aggregate IoU/Dice "
        "while enforcing per-view regression protections, avoiding directional oscillation, and "
        "providing automatic transactional rollback if objectives or regression thresholds are not met."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object", "views"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene to optimize.",
            },
            "views": {
                "type": "array",
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "minItems": 2,
                "maxItems": 3,
                "description": "List of 2 to 3 distinct orthographic reference view configurations (e.g. FRONT, SIDE, TOP).",
            },
            "objective": {
                "type": "string",
                "enum": ["WEIGHTED_IOU", "MIN_IOU", "WEIGHTED_DICE"],
                "default": "WEIGHTED_IOU",
                "description": "Multi-view aggregate objective function to maximize.",
            },
            "optimization_mode": {
                "type": "string",
                "enum": ["BOUNDED_SCALE_TRANSLATE", "VERTEX_DISPLACEMENT", "HYBRID"],
                "default": "BOUNDED_SCALE_TRANSLATE",
                "description": "Deformation mode across all views.",
            },
            "preserve_topology": {
                "type": "boolean",
                "default": True,
                "description": "Strictly preserve mesh topology (vertex, edge, and polygon counts remain invariant).",
            },
            "max_iterations": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 5,
                "description": "Maximum number of joint optimization iterations.",
            },
            "max_displacement": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 5.0,
                "default": 0.5,
                "description": "Maximum allowed displacement cap in Blender units (meters) per iteration.",
            },
            "step_size": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 2.0,
                "default": 0.2,
                "description": "Optimization step rate factor between 0.01 and 2.0.",
            },
            "tolerance": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.001,
                "description": "Minimum aggregate objective improvement required to accept an iteration step.",
            },
            "resolution": {
                "type": "integer",
                "minimum": 64,
                "maximum": 1024,
                "default": 256,
                "description": "Evaluation image render width and height in pixels.",
            },
            "mask_threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.05,
                "description": "Sensitivity threshold for foreground silhouette detection.",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, automatically rollback mesh state if aggregate objective does not strictly improve or regression tolerance is violated.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_REFINE_MESH_MULTIRESOLUTION] = {
    "name": TOOL_REFINE_MESH_MULTIRESOLUTION,
    "description": (
        "Perform bounded multiresolution surface refinement and contour alignment on an explicitly designated "
        "target mesh against one or more calibrated reference views (FRONT, SIDE, TOP). Applies controlled "
        "subdivision with strict vertex, face, displacement, and iteration bounds, evaluates multi-view "
        "silhouette alignment with regression protection, and enforces transactional rollback if objective "
        "fails to improve or limits are violated."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene to refine.",
            },
            "views": {
                "type": "array",
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "minItems": 1,
                "maxItems": 3,
                "description": "List of 1 to 3 distinct orthographic reference view configurations (FRONT, SIDE, TOP).",
            },
            "reference_image_path": {
                "type": "string",
                "minLength": 1,
                "description": "Optional single reference image path if 'views' is omitted.",
            },
            "view": {
                "type": "string",
                "enum": ["FRONT", "SIDE", "TOP"],
                "default": "FRONT",
                "description": "Orthographic view if single reference image is specified: 'FRONT', 'SIDE', or 'TOP'.",
            },
            "crop_box": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional normalized crop bounds [u_min, v_min, u_max, v_max] in [0.0, 1.0].",
            },
            "coordinate_system": {
                "type": "string",
                "enum": ["UV", "IMAGE_SPACE"],
                "default": "UV",
                "description": "Coordinate system convention: 'UV' or 'IMAGE_SPACE'.",
            },
            "subdivision_type": {
                "type": "string",
                "enum": ["CATMULL_CLARK", "SIMPLE"],
                "default": "CATMULL_CLARK",
                "description": "Subdivision algorithm: 'CATMULL_CLARK' (smooth surface) or 'SIMPLE' (linear subdivision).",
            },
            "subdivision_levels": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4,
                "default": 1,
                "description": "Number of subdivision levels to apply (clamped between 1 and 4).",
            },
            "max_vertex_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 20000,
                "description": "Maximum allowed vertex count limit; pre-modification check rejects if exceeded.",
            },
            "max_face_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 20000,
                "description": "Maximum allowed face/polygon count limit; pre-modification check rejects if exceeded.",
            },
            "max_displacement": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 2.0,
                "default": 0.2,
                "description": "Maximum allowed displacement cap in Blender units (meters) per iteration.",
            },
            "max_iterations": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 3,
                "description": "Maximum number of surface refinement iterations.",
            },
            "step_size": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 1.0,
                "default": 0.15,
                "description": "Refinement step rate factor between 0.01 and 1.0.",
            },
            "tolerance": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.001,
                "description": "Minimum aggregate objective improvement required to accept an iteration step.",
            },
            "resolution": {
                "type": "integer",
                "minimum": 64,
                "maximum": 1024,
                "default": 256,
                "description": "Evaluation image render width and height in pixels.",
            },
            "mask_threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.05,
                "description": "Sensitivity threshold for foreground silhouette detection.",
            },
            "objective": {
                "type": "string",
                "enum": ["WEIGHTED_IOU", "MIN_IOU", "WEIGHTED_DICE"],
                "default": "WEIGHTED_IOU",
                "description": "Multi-view aggregate objective function to maximize.",
            },
            "mask_vertex_group": {
                "type": "string",
                "maxLength": 63,
                "description": "Optional name of a vertex group on the mesh to restrict and modulate sculpt stroke displacement weights [0.0..1.0].",
            },
            "use_symmetry": {
                "type": "boolean",
                "default": False,
                "description": "Whether to enforce bilateral symmetry across symmetry_axis during sculpting.",
            },
            "symmetry_axis": {
                "type": "string",
                "enum": ["X", "Y", "Z", "NONE"],
                "default": "X",
                "description": "Reflection plane axis for bilateral symmetry (default 'X' for sagittal symmetry).",
            },
            "seam_threshold": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.005,
                "description": "Midline distance threshold in meters. Midline vertices within this distance to symmetry plane are clamped to zero displacement along the symmetry axis.",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, automatically rollback mesh state if objective does not strictly improve or regression tolerance is violated.",
            },
            "camera_name": {
                "type": "string",
                "description": "Optional scene camera name to use for evaluation.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_SCULPT_ORGANIC_ANATOMY] = {
    "name": TOOL_SCULPT_ORGANIC_ANATOMY,
    "description": (
        "Bounded organic sculpting and coarse anatomy refinement on an explicitly named mesh. "
        "Supports a verified initial brush set ('GRAB', 'INFLATE', 'SMOOTH', 'CLAY', 'DRAW') with "
        "bounded radius, strength, stroke coordinates, max displacement, and iteration limits. "
        "Preserves topology by default; requires explicit parameter configuration and limits for dynamic topology. "
        "Evaluates candidate deformation against calibrated FRONT, SIDE, and TOP silhouette objectives when provided, "
        "and enforces transactional rollback if constraints or regression tolerances are violated."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene to sculpt.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "brush_type": {
                "type": "string",
                "enum": ["GRAB", "INFLATE", "SMOOTH", "CLAY", "DRAW"],
                "default": "INFLATE",
                "description": "Sculpt brush operation: 'GRAB' (translation along stroke vector), 'INFLATE' (normal displacement), 'SMOOTH' (Laplacian relaxation), 'CLAY' (surface build-up along average normal), or 'DRAW' (surface displacement).",
            },
            "radius": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 10.0,
                "default": 0.5,
                "description": "Brush influence radius in Blender units (meters).",
            },
            "strength": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "description": "Sculpt brush strength factor in [0.0, 1.0].",
            },
            "stroke_points": {
                "type": "array",
                "description": "Array of 3D spatial points [x, y, z] or 2D screen coordinates representing brush contact path.",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 3,
                },
            },
            "stroke_direction": {
                "type": "array",
                "description": "Explicit 3D direction vector [dx, dy, dz] for directional brushes like GRAB.",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
            },
            "max_displacement": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 2.0,
                "default": 0.5,
                "description": "Maximum allowed spatial displacement per vertex in Blender units (meters).",
            },
            "iterations": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 1,
                "description": "Number of bounded sculpting passes/iterations to execute.",
            },
            "preserve_topology": {
                "type": "boolean",
                "default": True,
                "description": "Strictly preserve mesh topology (vertex, edge, face count). Defaults to true.",
            },
            "dynamic_topology": {
                "type": "boolean",
                "default": False,
                "description": "Explicitly enable dynamic topology mode (requires preserve_topology=false).",
            },
            "dynamic_topology_detail": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 10.0,
                "default": 0.2,
                "description": "Detail size for dynamic topology remeshing in meters.",
            },
            "max_vertex_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper bound limit on allowed vertex count for resource protection.",
            },
            "max_face_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper bound limit on allowed polygon face count for resource protection.",
            },
            "views": {
                "type": "array",
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "minItems": 1,
                "maxItems": 3,
                "description": "Optional calibrated multi-view reference configurations (FRONT, SIDE, TOP) for reference-guided acceptance evaluation.",
            },
            "reference_image_path": {
                "type": "string",
                "minLength": 1,
                "description": "Optional single reference image path if 'views' is omitted.",
            },
            "view": {
                "type": "string",
                "enum": ["FRONT", "SIDE", "TOP"],
                "default": "FRONT",
                "description": "Orthographic view if single reference image is specified: 'FRONT', 'SIDE', or 'TOP'.",
            },
            "crop_box": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional normalized crop bounds [u_min, v_min, u_max, v_max] in [0.0, 1.0].",
            },
            "coordinate_system": {
                "type": "string",
                "enum": ["UV", "IMAGE_SPACE"],
                "default": "UV",
                "description": "Coordinate system convention: 'UV' or 'IMAGE_SPACE'.",
            },
            "objective": {
                "type": "string",
                "enum": ["WEIGHTED_IOU", "MIN_IOU", "WEIGHTED_DICE"],
                "default": "WEIGHTED_IOU",
                "description": "Multi-view silhouette objective function: 'WEIGHTED_IOU', 'MIN_IOU', or 'WEIGHTED_DICE'.",
            },
            "min_aggregate_improvement": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 0.5,
                "default": 0.0001,
                "description": "Minimum required aggregate objective improvement to accept deformation when views are configured.",
            },
            "affected_region": {
                "type": "object",
                "description": "Optional bounding limits for the affected region (center [x, y, z] and max_radius).",
                "properties": {
                    "center": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                    "max_radius": {
                        "type": "number",
                        "minimum": 0.001,
                        "maximum": 20.0,
                    },
                },
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, automatically rollback mesh state if objective does not strictly improve or regression tolerance is violated.",
            },
            "camera_name": {
                "type": "string",
                "description": "Optional scene camera name to use for evaluation.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


LANDMARK_DEFINITION_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "additionalProperties": False,
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 63,
            "description": "Identifier for the semantic landmark, e.g. 'snout_tip', 'horn_tip_left', 'horn_tip_right', 'wing_apex_left', 'wing_apex_right', 'tail_tip', 'limb_joint_front_left', 'claw_tip_front_left'.",
        },
        "vertex_index": {
            "type": "integer",
            "minimum": 0,
            "description": "Optional index of the mesh vertex corresponding to this landmark.",
        },
        "position_3d": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 3,
            "maxItems": 3,
            "description": "Optional 3D world/local coordinate [x, y, z] for this landmark.",
        },
        "reference_views": {
            "type": "object",
            "description": "Mapping from view name ('FRONT', 'SIDE', 'TOP') to normalized 2D reference coordinates [u, v] in [0, 1].",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "weight": {
            "type": "number",
            "minimum": 0.01,
            "maximum": 10.0,
            "default": 1.0,
            "description": "Importance weight of this landmark relative to others.",
        },
        "tolerance": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "default": 0.05,
            "description": "Maximum acceptable 2D reprojection error in normalized coordinates.",
        },
    },
}

TOOL_DEFINITIONS[TOOL_CONFIGURE_SEMANTIC_LANDMARKS] = {
    "name": TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
    "description": (
        "Configure, update, or clear named 3D semantic landmarks and their corresponding 2D reference-image "
        "coordinates (FRONT, SIDE, TOP) on a designated mesh. Supports explicit landmarks such as snout_tip, horn_tips, "
        "wing_apexes, tail_tip, limb_joints, and claw_tips."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "action": {
                "type": "string",
                "enum": ["SET", "UPDATE", "REMOVE", "CLEAR"],
                "default": "SET",
                "description": "Landmark operation: 'SET' (replace/set landmarks), 'UPDATE' (merge/update landmarks), 'REMOVE' (delete specified landmarks), or 'CLEAR' (remove all landmarks).",
            },
            "landmarks": {
                "type": "array",
                "items": LANDMARK_DEFINITION_SCHEMA,
                "description": "Array of semantic landmark definitions.",
            },
            "calibrated_cameras": {
                "type": "object",
                "description": "Optional mapping of view names ('FRONT', 'SIDE', 'TOP') to Blender camera names.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_INSPECT_SEMANTIC_LANDMARKS] = {
    "name": TOOL_INSPECT_SEMANTIC_LANDMARKS,
    "description": (
        "Inspect configured semantic landmarks on a mesh object. Computes current 3D positions, "
        "reprojects them onto calibrated 2D reference views (FRONT, SIDE, TOP), and measures "
        "per-view and aggregate reprojection error (RMSE and mean error)."
    ),
    "permission_tier": PERMISSION_READ_ONLY,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene to inspect.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "views": {
                "type": "array",
                "items": {"type": "string", "enum": ["FRONT", "SIDE", "TOP"]},
                "description": "Optional list of views to evaluate reprojection error for. Defaults to all configured views.",
            },
            "include_projection_details": {
                "type": "boolean",
                "default": True,
                "description": "Whether to return detailed per-landmark per-view reprojection coordinates.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_GUIDE_MESH_LANDMARKS] = {
    "name": TOOL_GUIDE_MESH_LANDMARKS,
    "description": (
        "Deform a designated mesh toward calibrated 2D/3D semantic landmarks using bounded multi-view back-projection "
        "with smooth radial influence and Laplacian regularization. Requires measurable landmark error reduction "
        "while enforcing silhouette regression tolerances across protected views. Preserves topology by default."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "landmarks": {
                "type": "array",
                "items": LANDMARK_DEFINITION_SCHEMA,
                "description": "Optional list of landmarks to configure or override for this guidance run.",
            },
            "views": {
                "type": "array",
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "description": "Optional list of 1 to 3 calibrated reference view configurations for silhouette regression monitoring.",
            },
            "max_iterations": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
                "description": "Maximum number of guidance iterations.",
            },
            "step_size": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 1.0,
                "default": 0.2,
                "description": "Guidance step size / learning rate factor in [0.01, 1.0].",
            },
            "max_displacement": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 2.0,
                "default": 0.5,
                "description": "Maximum allowed displacement cap in meters per vertex.",
            },
            "influence_radius": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 10.0,
                "default": 0.8,
                "description": "Radius of influence around landmark vertices in meters.",
            },
            "falloff_type": {
                "type": "string",
                "enum": ["SMOOTH", "LINEAR", "SHARP", "CONSTANT"],
                "default": "SMOOTH",
                "description": "Spatial falloff function for landmark influence.",
            },
            "min_error_reduction": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.001,
                "description": "Minimum required landmark RMSE reduction to accept deformation.",
            },
            "objective": {
                "type": "string",
                "enum": ["WEIGHTED_LANDMARK_RMSE", "MEAN_LANDMARK_ERROR"],
                "default": "WEIGHTED_LANDMARK_RMSE",
                "description": "Landmark optimization objective metric.",
            },
            "preserve_topology": {
                "type": "boolean",
                "default": True,
                "description": "Strictly preserve mesh topology (vertex, edge, face count).",
            },
            "max_vertex_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper vertex cap limit before rejecting guidance.",
            },
            "max_face_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper face cap limit before rejecting guidance.",
            },
            "laplacian_smoothing": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.05,
                "description": "Laplacian surface smoothing factor to maintain mesh fairness.",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, transactionally roll back mesh if objective does not improve or tolerances are violated.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_DETAIL_SURFACE_FEATURES] = {
    "name": TOOL_DETAIL_SURFACE_FEATURES,
    "description": (
        "Applies controlled, bounded fine-scale anatomical surface detailing (SCALES, RIDGES, FACETS, VEINS) "
        "on an explicitly designated target mesh. Preserves existing semantic landmarks, prevents multi-view "
        "silhouette regression beyond configured tolerances, and maintains strict topology invariants by default "
        "with transactional rollback upon failure."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object", "feature_type"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "feature_type": {
                "type": "string",
                "enum": ["SCALES", "RIDGES", "FACETS", "VEINS"],
                "description": "Type of anatomical surface detail feature to apply.",
            },
            "feature_scale": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 5.0,
                "default": 0.2,
                "description": "Scale, wavelength, or cellular spacing of the feature pattern in meters.",
            },
            "spacing": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 5.0,
                "description": "Alias for feature_scale.",
            },
            "depth": {
                "type": "number",
                "minimum": -1.0,
                "maximum": 1.0,
                "default": 0.05,
                "description": "Signed surface relief depth in meters (positive = outward relief, negative = creased indent).",
            },
            "strength": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "description": "Strength modulation factor in [0.0, 1.0].",
            },
            "max_displacement": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.08,
                "description": "Strict maximum displacement cap in meters per vertex.",
            },
            "orientation": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "3D directional vector [x, y, z] for directional features (RIDGES, VEINS).",
            },
            "region_center": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Optional center coordinate [x, y, z] of the influence region.",
            },
            "region_radius": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 50.0,
                "default": 0.0,
                "description": "Radius of influence sphere in meters. 0.0 applies to the entire mesh.",
            },
            "region_bounds": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": "Optional bounding box [xmin, ymin, zmin, xmax, ymax, zmax] to restrict deformation.",
            },
            "mask_vertex_group": {
                "type": "string",
                "maxLength": 63,
                "description": "Optional name of a vertex group on the mesh to restrict and modulate surface detailing weights [0.0..1.0].",
            },
            "use_symmetry": {
                "type": "boolean",
                "default": False,
                "description": "Whether to enforce bilateral symmetry across symmetry_axis during detailing.",
            },
            "symmetry_axis": {
                "type": "string",
                "enum": ["X", "Y", "Z", "NONE"],
                "default": "X",
                "description": "Reflection plane axis for bilateral symmetry (default 'X' for sagittal symmetry).",
            },
            "seam_threshold": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.005,
                "description": "Midline distance threshold in meters. Midline vertices within this distance to symmetry plane are clamped to zero displacement along the symmetry axis.",
            },
            "falloff_type": {
                "type": "string",
                "enum": ["SMOOTH", "LINEAR", "SHARP", "CONSTANT"],
                "default": "SMOOTH",
                "description": "Spatial boundary falloff function for regional influence.",
            },
            "iterations": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 1,
                "description": "Number of surface detailing passes.",
            },
            "preserve_landmarks": {
                "type": "boolean",
                "default": True,
                "description": "If true, damps displacement near existing semantic landmarks to prevent landmark drift.",
            },
            "landmark_protection_radius": {
                "type": "number",
                "minimum": 0.01,
                "maximum": 2.0,
                "default": 0.25,
                "description": "Radius in meters around landmarks within which displacement is damped.",
            },
            "max_landmark_regression": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 0.5,
                "default": 0.01,
                "description": "Maximum allowed increase in landmark RMSE before triggering rejection and rollback.",
            },
            "preserve_topology": {
                "type": "boolean",
                "default": True,
                "description": "Strictly preserve mesh topology (vertex, edge, face count invariant).",
            },
            "subdivide_before_detail": {
                "type": "boolean",
                "default": False,
                "description": "Optional pre-detail Catmull-Clark subdivision pass for coarse blockout geometry.",
            },
            "subdivision_level": {
                "type": "integer",
                "minimum": 0,
                "maximum": 2,
                "default": 0,
                "description": "Subdivision level if subdivide_before_detail is true.",
            },
            "max_vertex_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper vertex cap limit before rejecting detailing.",
            },
            "max_face_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper face cap limit before rejecting detailing.",
            },
            "views": {
                "type": "array",
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "description": "Optional calibrated reference views for silhouette regression monitoring.",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, roll back mesh state bit-for-bit if limits are exceeded or regression occurs.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_INSPECT_SURFACE_DETAIL] = {
    "name": TOOL_INSPECT_SURFACE_DETAIL,
    "description": (
        "Inspect surface geometric detail metrics of a designated mesh object, including surface roughness, "
        "Laplacian curvature variation, bounding dimensions, topology statistics, and landmark stability."
    ),
    "permission_tier": PERMISSION_READ_ONLY,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "include_roughness": {
                "type": "boolean",
                "default": True,
                "description": "Whether to calculate local surface roughness / Laplacian curvature metric.",
            },
            "include_landmarks": {
                "type": "boolean",
                "default": True,
                "description": "Whether to report stability metrics for stored semantic landmarks.",
            },
            "region_center": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Optional center coordinate [x, y, z] to restrict inspection to a localized region.",
            },
            "region_radius": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 50.0,
                "default": 0.0,
                "description": "Radius of region around region_center in meters (0.0 evaluates whole mesh).",
            },
        },
    },
}

TOOL_DEFINITIONS[TOOL_CONFIGURE_ANATOMICAL_MASK] = {
    "name": TOOL_CONFIGURE_ANATOMICAL_MASK,
    "description": (
        "Configure an anatomical region mask / vertex group on a designated mesh object (e.g. Horns, Wings, Scales) "
        "with smooth spatial weight falloff and optional bilateral symmetry."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object", "mask_name"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "mask_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the anatomical vertex group / mask (e.g. 'Horns', 'Wings', 'Body_Scales', 'Spine_Ridges').",
            },
            "action": {
                "type": "string",
                "enum": ["SET", "ADD", "SUBTRACT", "CLEAR"],
                "default": "SET",
                "description": "Action to perform: 'SET' assigns weights, 'ADD' sums with existing, 'SUBTRACT' subtracts, 'CLEAR' zeroes group.",
            },
            "region_type": {
                "type": "string",
                "enum": ["SPHERE", "BOUNDING_BOX", "CYLINDER", "NORMAL_FACING", "ALL"],
                "default": "SPHERE",
                "description": "Spatial or geometric region formula used to evaluate vertex membership weights.",
            },
            "center": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Center coordinate [x, y, z] for spherical, cylindrical, or bounding regions.",
            },
            "radius": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 50.0,
                "default": 1.0,
                "description": "Radius in meters for SPHERE or CYLINDER region types.",
            },
            "radii": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Optional [rx, ry, rz] radii for ellipsoidal region bounds.",
            },
            "region_bounds": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": "Optional bounding box [xmin, ymin, zmin, xmax, ymax, zmax] for BOUNDING_BOX region type.",
            },
            "falloff": {
                "type": "string",
                "enum": ["SMOOTH", "LINEAR", "CONSTANT", "SHARP"],
                "default": "SMOOTH",
                "description": "Weight falloff curve from region center to outer boundary.",
            },
            "min_weight": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.0,
                "description": "Minimum weight outside or at region perimeter.",
            },
            "max_weight": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 1.0,
                "description": "Maximum peak weight at region center.",
            },
            "normal_vector": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Direction vector [x, y, z] for NORMAL_FACING region type (e.g. [0, 0, 1] for dorsal).",
            },
            "normal_tolerance": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "description": "Alignment tolerance for NORMAL_FACING (dot product threshold = 1.0 - normal_tolerance).",
            },
            "symmetry_axis": {
                "type": "string",
                "enum": ["X", "Y", "Z", "NONE"],
                "default": "NONE",
                "description": "If specified (e.g. 'X'), evaluates and mirrors mask weights symmetrically across the plane.",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, rolls back vertex group modifications on error.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}


TOOL_DEFINITIONS[TOOL_INSPECT_ANATOMICAL_MASK] = {
    "name": TOOL_INSPECT_ANATOMICAL_MASK,
    "description": (
        "Inspect anatomical mask / vertex group distributions and evaluate bilateral mesh symmetry "
        "(asymmetry RMSE, midline seam vertices, symmetry pairing)."
    ),
    "permission_tier": PERMISSION_READ_ONLY,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "mask_name": {
                "type": "string",
                "maxLength": 63,
                "description": "Optional name of specific mask / vertex group to inspect (if omitted, lists all groups).",
            },
            "symmetry_axis": {
                "type": "string",
                "enum": ["X", "Y", "Z", "NONE"],
                "default": "X",
                "description": "Axis to evaluate bilateral symmetry across (default 'X' for sagittal symmetry).",
            },
            "seam_threshold": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.005,
                "description": "Midline distance threshold in meters for classifying sagittal seam vertices.",
            },
            "evaluate_symmetry": {
                "type": "boolean",
                "default": True,
                "description": "Whether to calculate bilateral pairing and asymmetry RMSE.",
            },
        },
    },
}

TOOL_DEFINITIONS[TOOL_SYMMETRIZE_MESH_GEOMETRY] = {
    "name": TOOL_SYMMETRIZE_MESH_GEOMETRY,
    "description": (
        "Enforce bilateral symmetry on a designated mesh object across a specified reflection plane (default X), "
        "locking sagittal midline vertices to prevent seam separation."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "symmetry_axis": {
                "type": "string",
                "enum": ["X", "Y", "Z"],
                "default": "X",
                "description": "Reflection plane normal axis (default 'X' for sagittal symmetry).",
            },
            "source_direction": {
                "type": "string",
                "enum": ["+TO_-", "-TO_+", "AVERAGE"],
                "default": "+TO_-",
                "description": "Direction of symmetry transfer: '+TO_-' mirrors positive coordinates to negative, '-TO_+' reverses, 'AVERAGE' blends both.",
            },
            "seam_threshold": {
                "type": "number",
                "minimum": 0.0001,
                "maximum": 0.5,
                "default": 0.005,
                "description": "Midline distance threshold in meters. Midline vertices within this distance are locked strictly to 0 on symmetry axis.",
            },
            "lock_midline": {
                "type": "boolean",
                "default": True,
                "description": "Whether to snap and lock midline vertices to exactly 0.0 along the symmetry axis.",
            },
            "preserve_topology": {
                "type": "boolean",
                "default": True,
                "description": "Ensure vertex, edge, and face counts remain invariant.",
            },
            "max_vertex_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper vertex cap limit before rejecting symmetrization.",
            },
            "max_face_count": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "default": 50000,
                "description": "Upper face cap limit before rejecting symmetrization.",
            },
            "views": {
                "type": "array",
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "description": "Optional calibrated reference views for silhouette regression monitoring.",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "If true, rollback mesh state bit-for-bit if limits are exceeded or regression occurs.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}

TOOL_DEFINITIONS[TOOL_DETECT_SEMANTIC_LANDMARKS] = {
    "name": TOOL_DETECT_SEMANTIC_LANDMARKS,
    "description": (
        "Automatically detect semantic anatomical landmarks (snout, horn apices, wing apices, tail tip) "
        "from calibrated reference silhouettes or mesh boundary curvature, project to closest surface vertices, "
        "and optionally persist them into the target mesh datablock."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target mesh object in the Blender scene.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "views": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": VIEW_FIT_CONFIG_SCHEMA,
                "description": "Optional list of calibrated reference views for 2D silhouette contour extrema detection.",
            },
            "landmark_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "snout_tip",
                        "horn_apex_left",
                        "horn_apex_right",
                        "wing_apex_left",
                        "wing_apex_right",
                        "tail_tip",
                        "claw_apex_front_left",
                        "claw_apex_front_right",
                    ],
                },
                "description": "List of anatomical landmark types to detect. Defaults to standard dragon features.",
            },
            "detection_method": {
                "type": "string",
                "enum": ["CONTOUR_EXTREMA", "BOUNDING_PROJECTION", "CURVATURE_PEAKS"],
                "default": "CONTOUR_EXTREMA",
                "description": "Algorithm for feature detection: 'CONTOUR_EXTREMA' from silhouette, 'BOUNDING_PROJECTION' from view-aligned bounds, or 'CURVATURE_PEAKS' from mesh geometry.",
            },
            "store_on_mesh": {
                "type": "boolean",
                "default": True,
                "description": "Whether to store the detected landmarks in target object's custom properties (_umcp_semantic_landmarks).",
            },
            "confidence_threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "description": "Minimum confidence threshold to include a detected landmark.",
            },
            "max_vertex_distance": {
                "type": "number",
                "minimum": 0.001,
                "maximum": 10.0,
                "default": 2.0,
                "description": "Maximum 3D distance allowed when projecting landmark rays onto target mesh vertices.",
            },
            "enforce_symmetry": {
                "type": "boolean",
                "default": True,
                "description": "Enforce bilateral symmetry across sagittal X axis for paired landmarks (horn, wing, claws).",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}

TOOL_DEFINITIONS[TOOL_BAKE_MESH_SURFACE_MAP] = {
    "name": TOOL_BAKE_MESH_SURFACE_MAP,
    "description": (
        "Bake high-resolution mesh surface detail (tangent normal maps, displacement heightmaps, roughness, AO) "
        "from a detailed source mesh to a low-poly target retopology mesh, or self-bake detail onto the target mesh. "
        "Handles Cycles bake setup, UV verification/auto-unwrapping, non-color space, ray distance/cage extrusion, and image export."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_object"],
        "properties": {
            "target_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the target low-poly (retopology) mesh object to receive the bake.",
            },
            "object_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Alias for target_object.",
            },
            "source_object": {
                "type": "string",
                "minLength": 1,
                "maxLength": 63,
                "description": "Name of the high-poly source mesh object containing detailed sculpting/features. If omitted or equal to target_object, performs self-bake.",
            },
            "map_type": {
                "type": "string",
                "enum": ["NORMAL", "DISPLACEMENT", "ROUGHNESS", "AO"],
                "default": "NORMAL",
                "description": "Surface map type to bake.",
            },
            "width": {
                "type": "integer",
                "minimum": 64,
                "maximum": 4096,
                "default": 512,
                "description": "Baked image texture width in pixels.",
            },
            "height": {
                "type": "integer",
                "minimum": 64,
                "maximum": 4096,
                "default": 512,
                "description": "Baked image texture height in pixels.",
            },
            "margin": {
                "type": "integer",
                "minimum": 0,
                "maximum": 64,
                "default": 16,
                "description": "Margin in pixels around UV islands during baking.",
            },
            "save_filepath": {
                "type": "string",
                "description": "Optional absolute file path on disk to save the baked image (PNG).",
            },
            "cage_extrusion": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 2.0,
                "default": 0.05,
                "description": "Ray casting cage extrusion distance in meters for selected-to-active bake.",
            },
            "max_ray_distance": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 10.0,
                "default": 0.0,
                "description": "Maximum ray casting distance in meters (0.0 = unlimited/auto).",
            },
            "use_selected_to_active": {
                "type": "boolean",
                "default": True,
                "description": "Whether to bake detail from source_object to target_object. Automatically False if source_object is omitted or identical to target_object.",
            },
            "auto_unwrap_if_needed": {
                "type": "boolean",
                "default": True,
                "description": "If target mesh has no UV layer, automatically unwrap with Smart UV Project before baking.",
            },
            "color_space": {
                "type": "string",
                "enum": ["Non-Color", "sRGB"],
                "default": "Non-Color",
                "description": "Color space setting for the baked image datablock (default 'Non-Color' for normal/displacement/roughness).",
            },
            "rollback_on_failure": {
                "type": "boolean",
                "default": True,
                "description": "Restore scene render engine, material, and object selection state if baking fails.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
    },
}

TOOL_DEFINITIONS[TOOL_INSPECT_SCULPT_STATE] = {
    "name": TOOL_INSPECT_SCULPT_STATE,
    "permission_tier": PERMISSION_READ_ONLY,
    "description": "Read sculpt mode, active brush settings, dynamic-topology flag, voxel size and stable base mesh snapshot.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["object_name"], "properties": {"object_name": {"type": "string", "minLength": 1, "maxLength": 63}}},
}

TOOL_DEFINITIONS[TOOL_CONFIGURE_MODIFIER] = {
    "name": TOOL_CONFIGURE_MODIFIER,
    "description": "Typed add/update/remove for SUBSURF, BEVEL and SOLIDIFY modifiers. Requires trusted approval; verifies properties and stack. No apply/reorder or arbitrary RNA properties.",
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "modifier_name", "modifier_type", "action"],
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 63},
            "modifier_name": {"type": "string", "minLength": 1, "maxLength": 63},
            "modifier_type": {"type": "string", "enum": list(PROPERTY_SPECS)},
            "action": {"type": "string", "enum": ["add", "update", "remove"]},
            "properties": {"type": "object", "additionalProperties": False, "properties": {
                key: {"type": "integer" if spec[0] is int else "number", "minimum": spec[1], "maximum": spec[2]}
                for specs in PROPERTY_SPECS.values() for key, spec in specs.items()}},
            "approved": {"type": "boolean", "default": False, "description": "Untrusted caller flag; never proof of approval."},
            "task_id": {"type": "string"},
        },
    },
}
TOOL_DEFINITIONS[TOOL_INSPECT_MODIFIERS] = {
    "name": TOOL_INSPECT_MODIFIERS,
    "description": "Read-only ordered modifier stack with exact typed property readback for SUBSURF, BEVEL and SOLIDIFY; other types are identified as unsupported by the typed writer.",
    "permission_tier": PERMISSION_READ_ONLY,
    "input_schema": {"type": "object", "additionalProperties": False,
        "required": ["name"], "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 63}}},
}
TOOL_DEFINITIONS[TOOL_CONFIGURE_MODIFIER]["input_schema"]["allOf"] = [
    {"if": {"properties": {"modifier_type": {"const": kind}}},
     "then": {"properties": {"properties": {"type": "object", "additionalProperties": False,
         "properties": {key: {"type": "integer" if spec[0] is int else "number", "minimum": spec[1], "maximum": spec[2]}
                        for key, spec in specs.items()}}}}}
    for kind, specs in PROPERTY_SPECS.items()
] + [{"if": {"properties": {"action": {"const": "remove"}}},
      "then": {"properties": {"properties": {"maxProperties": 0}}},
      "else": {"required": ["properties"], "properties": {"properties": {"minProperties": 1}}}}]

for _face_tool in (TOOL_EXTRUDE_MESH, TOOL_INSET_MESH):
    TOOL_DEFINITIONS[_face_tool]["input_schema"]["properties"]["expected_snapshot_id"] = {
        "type": "string", "pattern": "^sha256:[0-9a-f]{64}$",
        "description": "Base-mesh fingerprint. Required when faces is an explicit index list; mismatches fail before editing."
    }

TOOL_DEFINITIONS[TOOL_BEVEL_MESH] = {
    "name": TOOL_BEVEL_MESH,
    "description": (
        "Bevel mesh edges or vertices in Blender with explicit offset, segments, profile, and element selection. "
        "Transactional mutation with manifold verification and bit-for-bit rollback."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target mesh object in the active scene.",
            },
            "target_object": {
                "type": "string",
                "description": "Alias for name.",
            },
            "object_name": {
                "type": "string",
                "description": "Alias for name.",
            },
            "offset": {
                "type": "number",
                "minimum": 0.0,
                "default": 0.1,
                "description": "Bevel amount/offset distance.",
            },
            "offset_type": {
                "type": "string",
                "enum": ["OFFSET", "WIDTH", "DEPTH", "PERCENT", "ABSOLUTE"],
                "default": "OFFSET",
                "description": "Method of measuring the bevel amount.",
            },
            "segments": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "default": 1,
                "description": "Number of segments in the bevel curve.",
            },
            "profile": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.5,
                "description": "Profile shape (0.5 is round, < 0.5 concave, > 0.5 convex).",
            },
            "affect": {
                "type": "string",
                "enum": ["EDGES", "VERTICES"],
                "default": "EDGES",
                "description": "Whether to bevel edges or only vertices.",
            },
            "clamp_overlap": {
                "type": "boolean",
                "default": False,
                "description": "Clamp the bevel amount to prevent overlapping geometry.",
            },
            "edges": {
                "description": "Edges to bevel: 'selected', 'all', or a list of integer edge indices. Defaults to 'all'.",
                "default": "all",
            },
            "vertices": {
                "description": "Vertices to bevel when affect is 'VERTICES': 'selected', 'all', or a list of integer vertex indices.",
            },
            "expected_snapshot_id": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "Base-mesh snapshot fingerprint. Required when edges or vertices is an explicit index list.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_SPLIT_MESH] = {
    "name": TOOL_SPLIT_MESH,
    "description": (
        "Split mesh geometry via bisect plane cutting, edge subdivision, or edge splitting with explicit bounds, "
        "plane coordinates, and transactional verification."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target mesh object in the active scene.",
            },
            "target_object": {
                "type": "string",
                "description": "Alias for name.",
            },
            "object_name": {
                "type": "string",
                "description": "Alias for name.",
            },
            "method": {
                "type": "string",
                "enum": ["BISECT", "SUBDIVIDE", "SPLIT_EDGES"],
                "default": "BISECT",
                "description": "Split method: BISECT (plane cut), SUBDIVIDE (edge subdivide), or SPLIT_EDGES (disconnect edges).",
            },
            "plane_co": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Point on plane for bisect [x, y, z]. Defaults to [0.0, 0.0, 0.0].",
            },
            "plane_no": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Plane normal vector for bisect [x, y, z]. Defaults to [0.0, 0.0, 1.0].",
            },
            "clear_inner": {
                "type": "boolean",
                "default": False,
                "description": "For BISECT: remove geometry behind the plane.",
            },
            "clear_outer": {
                "type": "boolean",
                "default": False,
                "description": "For BISECT: remove geometry in front of the plane.",
            },
            "threshold": {
                "type": "number",
                "minimum": 0.0,
                "default": 0.0001,
                "description": "Distance threshold for bisect cutting plane.",
            },
            "cuts": {
                "type": "integer",
                "minimum": 1,
                "maximum": 16,
                "default": 1,
                "description": "Number of cuts for SUBDIVIDE method.",
            },
            "edges": {
                "description": "Edges to subdivide or split: 'selected', 'all', or a list of integer edge indices.",
            },
            "expected_snapshot_id": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "Base-mesh snapshot fingerprint. Required when edges is an explicit index list.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_DISSOLVE_MESH] = {
    "name": TOOL_DISSOLVE_MESH,
    "description": (
        "Dissolve vertices, edges, or faces from a mesh object with transactional manifold verification and boundary preservation."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target mesh object in the active scene.",
            },
            "target_object": {
                "type": "string",
                "description": "Alias for name.",
            },
            "object_name": {
                "type": "string",
                "description": "Alias for name.",
            },
            "dissolve_type": {
                "type": "string",
                "enum": ["VERTICES", "EDGES", "FACES"],
                "default": "EDGES",
                "description": "Element domain to dissolve: VERTICES, EDGES, or FACES.",
            },
            "indices": {
                "description": "Indices to dissolve: 'selected' or an explicit list of non-negative integer indices.",
                "default": "selected",
            },
            "use_verts": {
                "type": "boolean",
                "default": True,
                "description": "Dissolve vertices attached to dissolved edges or faces when they become isolated.",
            },
            "use_face_split": {
                "type": "boolean",
                "default": False,
                "description": "Split off surrounding faces when dissolving edges or vertices.",
            },
            "expected_snapshot_id": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "Base-mesh snapshot fingerprint. Required when indices is an explicit list.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_MERGE_MESH] = {
    "name": TOOL_MERGE_MESH,
    "description": (
        "Merge vertices at center, collapsed edges, target 3D cursor position, or by distance threshold with topological manifold verification."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target mesh object in the active scene.",
            },
            "target_object": {
                "type": "string",
                "description": "Alias for name.",
            },
            "object_name": {
                "type": "string",
                "description": "Alias for name.",
            },
            "mode": {
                "type": "string",
                "enum": ["CENTER", "COLLAPSE", "CURSOR", "DISTANCE"],
                "default": "CENTER",
                "description": "Merge mode: CENTER, COLLAPSE, CURSOR, DISTANCE.",
            },
            "vertices": {
                "description": "Vertices to merge: 'selected', 'all', or an explicit list of non-negative integer indices.",
                "default": "selected",
            },
            "target_location": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Target 3D position [x, y, z] when mode is 'CURSOR'.",
            },
            "distance_threshold": {
                "type": "number",
                "minimum": 0.0,
                "default": 0.001,
                "description": "Distance threshold when mode is 'DISTANCE'.",
            },
            "expected_snapshot_id": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "Base-mesh snapshot fingerprint. Required when vertices is an explicit index list.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_RECALCULATE_NORMALS] = {
    "name": TOOL_RECALCULATE_NORMALS,
    "description": (
        "Recalculate or flip mesh face normals (outside, inside, or flip) with winding consistency and topology verification."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target mesh object in the active scene.",
            },
            "target_object": {
                "type": "string",
                "description": "Alias for name.",
            },
            "object_name": {
                "type": "string",
                "description": "Alias for name.",
            },
            "action": {
                "type": "string",
                "enum": ["RECALCULATE_OUTSIDE", "RECALCULATE_INSIDE", "FLIP"],
                "default": "RECALCULATE_OUTSIDE",
                "description": "Normal operation: RECALCULATE_OUTSIDE, RECALCULATE_INSIDE, or FLIP.",
            },
            "faces": {
                "description": "Faces to operate on: 'all', 'selected', or an explicit list of non-negative integer face indices.",
                "default": "all",
            },
            "expected_snapshot_id": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "Base-mesh snapshot fingerprint. Required when faces is an explicit index list.",
            },
            "approved": {
                "type": "boolean",
                "default": False,
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task or workflow identifier.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

# Register aliases for mesh modeling operations
TOOL_DEFINITIONS[TOOL_BEVEL_EDGES] = dict(TOOL_DEFINITIONS[TOOL_BEVEL_MESH])
TOOL_DEFINITIONS[TOOL_BEVEL_EDGES]["name"] = TOOL_BEVEL_EDGES
TOOL_DEFINITIONS[TOOL_KNIFE_MESH] = dict(TOOL_DEFINITIONS[TOOL_SPLIT_MESH])
TOOL_DEFINITIONS[TOOL_KNIFE_MESH]["name"] = TOOL_KNIFE_MESH
TOOL_DEFINITIONS[TOOL_BISECT_MESH] = dict(TOOL_DEFINITIONS[TOOL_SPLIT_MESH])
TOOL_DEFINITIONS[TOOL_BISECT_MESH]["name"] = TOOL_BISECT_MESH
TOOL_DEFINITIONS[TOOL_ALIGN_NORMALS] = dict(TOOL_DEFINITIONS[TOOL_RECALCULATE_NORMALS])
TOOL_DEFINITIONS[TOOL_ALIGN_NORMALS]["name"] = TOOL_ALIGN_NORMALS

# Register aliases for face operations
TOOL_DEFINITIONS[TOOL_EXTRUDE_FACES] = dict(TOOL_DEFINITIONS[TOOL_EXTRUDE_MESH])
TOOL_DEFINITIONS[TOOL_EXTRUDE_FACES]["name"] = TOOL_EXTRUDE_FACES
TOOL_DEFINITIONS[TOOL_INSET_FACES] = dict(TOOL_DEFINITIONS[TOOL_INSET_MESH])
TOOL_DEFINITIONS[TOOL_INSET_FACES]["name"] = TOOL_INSET_FACES

# Register aliases for UV operations
TOOL_DEFINITIONS[TOOL_UNWRAP_MESH] = dict(TOOL_DEFINITIONS[TOOL_UV_UNWRAP])
TOOL_DEFINITIONS[TOOL_UNWRAP_MESH]["name"] = TOOL_UNWRAP_MESH
TOOL_DEFINITIONS[TOOL_SMART_PROJECT] = dict(TOOL_DEFINITIONS[TOOL_UV_SMART_PROJECT])
TOOL_DEFINITIONS[TOOL_SMART_PROJECT]["name"] = TOOL_SMART_PROJECT
TOOL_DEFINITIONS[TOOL_SMART_UV_PROJECT] = dict(TOOL_DEFINITIONS[TOOL_UV_SMART_PROJECT])
TOOL_DEFINITIONS[TOOL_SMART_UV_PROJECT]["name"] = TOOL_SMART_UV_PROJECT
TOOL_DEFINITIONS[TOOL_UV_PROJECT] = dict(TOOL_DEFINITIONS[TOOL_UV_SMART_PROJECT])
TOOL_DEFINITIONS[TOOL_UV_PROJECT]["name"] = TOOL_UV_PROJECT

# Register aliases for animation, geometry nodes, asset IO, and object ops
TOOL_DEFINITIONS[TOOL_INSERT_KEYFRAME] = dict(TOOL_DEFINITIONS[TOOL_MANAGE_KEYFRAME])
TOOL_DEFINITIONS[TOOL_INSERT_KEYFRAME]["name"] = TOOL_INSERT_KEYFRAME
TOOL_DEFINITIONS[TOOL_DELETE_KEYFRAME] = dict(TOOL_DEFINITIONS[TOOL_MANAGE_KEYFRAME])
TOOL_DEFINITIONS[TOOL_DELETE_KEYFRAME]["name"] = TOOL_DELETE_KEYFRAME

TOOL_DEFINITIONS[TOOL_INSPECT_GEOMETRY_NODES] = dict(TOOL_DEFINITIONS[TOOL_CONFIGURE_GEOMETRY_NODES])
TOOL_DEFINITIONS[TOOL_INSPECT_GEOMETRY_NODES]["name"] = TOOL_INSPECT_GEOMETRY_NODES
TOOL_DEFINITIONS[TOOL_INSPECT_GEOMETRY_NODES]["permission_tier"] = PERMISSION_READ_ONLY

TOOL_DEFINITIONS[TOOL_EXPORT_SCENE] = dict(TOOL_DEFINITIONS[TOOL_EXPORT_SCENE_ASSET])
TOOL_DEFINITIONS[TOOL_EXPORT_SCENE]["name"] = TOOL_EXPORT_SCENE
TOOL_DEFINITIONS[TOOL_IMPORT_SCENE] = dict(TOOL_DEFINITIONS[TOOL_IMPORT_SCENE_ASSET])
TOOL_DEFINITIONS[TOOL_IMPORT_SCENE]["name"] = TOOL_IMPORT_SCENE

TOOL_DEFINITIONS[TOOL_DUPLICATE] = dict(TOOL_DEFINITIONS[TOOL_DUPLICATE_OBJECT])
TOOL_DEFINITIONS[TOOL_DUPLICATE]["name"] = TOOL_DUPLICATE
TOOL_DEFINITIONS[TOOL_RENAME] = dict(TOOL_DEFINITIONS[TOOL_RENAME_OBJECT])
TOOL_DEFINITIONS[TOOL_RENAME]["name"] = TOOL_RENAME

TOOL_DEFINITIONS[TOOL_SELECT] = dict(TOOL_DEFINITIONS[TOOL_SELECT_OBJECT])
TOOL_DEFINITIONS[TOOL_SELECT]["name"] = TOOL_SELECT
TOOL_DEFINITIONS[TOOL_PURGE_ORPHANS] = dict(TOOL_DEFINITIONS[TOOL_PURGE_ORPHANED_DATABLOCKS])
TOOL_DEFINITIONS[TOOL_PURGE_ORPHANS]["name"] = TOOL_PURGE_ORPHANS

TOOL_DEFINITIONS[TOOL_EDIT_CAMERA] = dict(TOOL_DEFINITIONS[TOOL_CONFIGURE_CAMERA])
TOOL_DEFINITIONS[TOOL_EDIT_CAMERA]["name"] = TOOL_EDIT_CAMERA

TOOL_DEFINITIONS[TOOL_CREATE_CURVE] = dict(TOOL_DEFINITIONS[TOOL_CREATE_CURVE_OR_TEXT])
TOOL_DEFINITIONS[TOOL_CREATE_CURVE]["name"] = TOOL_CREATE_CURVE
TOOL_DEFINITIONS[TOOL_CREATE_TEXT] = dict(TOOL_DEFINITIONS[TOOL_CREATE_CURVE_OR_TEXT])
TOOL_DEFINITIONS[TOOL_CREATE_TEXT]["name"] = TOOL_CREATE_TEXT

TOOL_DEFINITIONS[TOOL_CONNECT_SHADER_NODES] = dict(TOOL_DEFINITIONS[TOOL_MANAGE_SHADER_NODES])
TOOL_DEFINITIONS[TOOL_CONNECT_SHADER_NODES]["name"] = TOOL_CONNECT_SHADER_NODES
TOOL_DEFINITIONS[TOOL_MANAGE_NODES] = dict(TOOL_DEFINITIONS[TOOL_MANAGE_SHADER_NODES])
TOOL_DEFINITIONS[TOOL_MANAGE_NODES]["name"] = TOOL_MANAGE_NODES

TOOL_DEFINITIONS[TOOL_BAKE_TEXTURE] = dict(TOOL_DEFINITIONS[TOOL_BAKE_OBJECT_TEXTURE])
TOOL_DEFINITIONS[TOOL_BAKE_TEXTURE]["name"] = TOOL_BAKE_TEXTURE
TOOL_DEFINITIONS[TOOL_BAKE_MATERIALS] = dict(TOOL_DEFINITIONS[TOOL_BAKE_OBJECT_TEXTURE])
TOOL_DEFINITIONS[TOOL_BAKE_MATERIALS]["name"] = TOOL_BAKE_MATERIALS

TOOL_DEFINITIONS[TOOL_CONFIGURE_COMPOSITOR] = dict(TOOL_DEFINITIONS[TOOL_MANAGE_COMPOSITOR_NODES])
TOOL_DEFINITIONS[TOOL_CONFIGURE_COMPOSITOR]["name"] = TOOL_CONFIGURE_COMPOSITOR
TOOL_DEFINITIONS[TOOL_MANAGE_COMPOSITOR] = dict(TOOL_DEFINITIONS[TOOL_MANAGE_COMPOSITOR_NODES])
TOOL_DEFINITIONS[TOOL_MANAGE_COMPOSITOR]["name"] = TOOL_MANAGE_COMPOSITOR

TOOL_DEFINITIONS[TOOL_MANAGE_FCURVE] = dict(TOOL_DEFINITIONS[TOOL_CONFIGURE_ANIMATION_CURVE])
TOOL_DEFINITIONS[TOOL_MANAGE_FCURVE]["name"] = TOOL_MANAGE_FCURVE
TOOL_DEFINITIONS[TOOL_SET_KEYFRAME_INTERPOLATION] = dict(TOOL_DEFINITIONS[TOOL_CONFIGURE_ANIMATION_CURVE])
TOOL_DEFINITIONS[TOOL_SET_KEYFRAME_INTERPOLATION]["name"] = TOOL_SET_KEYFRAME_INTERPOLATION
TOOL_DEFINITIONS[TOOL_MANAGE_ACTION_SLOTS] = dict(TOOL_DEFINITIONS[TOOL_CONFIGURE_ANIMATION_CURVE])
TOOL_DEFINITIONS[TOOL_MANAGE_ACTION_SLOTS]["name"] = TOOL_MANAGE_ACTION_SLOTS

TOOL_DEFINITIONS[TOOL_SETUP_PHYSICS] = dict(TOOL_DEFINITIONS[TOOL_CONFIGURE_PHYSICS])
TOOL_DEFINITIONS[TOOL_SETUP_PHYSICS]["name"] = TOOL_SETUP_PHYSICS
TOOL_DEFINITIONS[TOOL_MANAGE_PHYSICS] = dict(TOOL_DEFINITIONS[TOOL_CONFIGURE_PHYSICS])
TOOL_DEFINITIONS[TOOL_MANAGE_PHYSICS]["name"] = TOOL_MANAGE_PHYSICS

TOOL_DEFINITIONS[TOOL_OPEN_PROJECT] = dict(TOOL_DEFINITIONS[TOOL_OPEN_BLEND_FILE])
TOOL_DEFINITIONS[TOOL_OPEN_PROJECT]["name"] = TOOL_OPEN_PROJECT
TOOL_DEFINITIONS[TOOL_LOAD_BLEND_FILE] = dict(TOOL_DEFINITIONS[TOOL_OPEN_BLEND_FILE])
TOOL_DEFINITIONS[TOOL_LOAD_BLEND_FILE]["name"] = TOOL_LOAD_BLEND_FILE

# VSE Capability 1: Timeline & Strip Lifecycle Tool Definitions
TOOL_DEFINITIONS[TOOL_INSPECT_VSE_TIMELINE] = {
    "name": TOOL_INSPECT_VSE_TIMELINE,
    "description": (
        "Inspect the Video Sequence Editor (VSE) timeline: frame range, FPS, occupied channels, "
        "summary descriptors of all strips, and timeline markers."
    ),
    "permission_tier": PERMISSION_READ_ONLY,
    "input_schema": {
        "type": "object",
        "properties": {
            "include_strips": {
                "type": "boolean",
                "description": "Whether to include detailed strip descriptors (default True).",
                "default": True,
            },
            "include_markers": {
                "type": "boolean",
                "description": "Whether to include timeline markers (default True).",
                "default": True,
            },
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CREATE_VSE_STRIP] = {
    "name": TOOL_CREATE_VSE_STRIP,
    "description": (
        "Create a new strip in the Blender Video Sequence Editor (VSE). "
        "Supports COLOR, TEXT, IMAGE, SOUND, and MOVIE strips on specified channels and frame ranges."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["strip_type", "channel", "frame_start"],
        "properties": {
            "strip_type": {
                "type": "string",
                "enum": ["COLOR", "TEXT", "IMAGE", "SOUND", "MOVIE"],
                "description": "Type of strip to create in the sequence editor.",
            },
            "name": {
                "type": "string",
                "description": "Unique name for the strip. Auto-generated if omitted.",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "Sequencer channel (track) index (1 to 128).",
            },
            "frame_start": {
                "type": "integer",
                "description": "Timeline start frame position.",
            },
            "duration": {
                "type": "integer",
                "minimum": 1,
                "default": 50,
                "description": "Duration in frames (used for COLOR, TEXT, and IMAGE strips).",
            },
            "color": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 3,
                "maxItems": 4,
                "description": "RGB or RGBA color float tuple (0.0 to 1.0) for COLOR strips.",
            },
            "text": {
                "type": "string",
                "description": "Text string content for TEXT strips.",
            },
            "filepath": {
                "type": "string",
                "description": "Absolute or sandbox-relative file path for IMAGE, SOUND, or MOVIE strips.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_MODIFY_VSE_STRIP] = {
    "name": TOOL_MODIFY_VSE_STRIP,
    "description": (
        "Modify an existing strip in the Blender Video Sequence Editor (VSE). "
        "Allows updating channel, start frame, duration, mute, lock, blend mode, and color."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the strip to modify.",
            },
            "new_name": {
                "type": "string",
                "description": "Optional new name for the strip.",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "New sequencer channel index (1 to 128).",
            },
            "frame_start": {
                "type": "integer",
                "description": "New timeline start frame position.",
            },
            "duration": {
                "type": "integer",
                "minimum": 1,
                "description": "New duration in frames.",
            },
            "mute": {
                "type": "boolean",
                "description": "Mute (hide/disable) state.",
            },
            "lock": {
                "type": "boolean",
                "description": "Lock state against accidental editing.",
            },
            "blend_type": {
                "type": "string",
                "description": "Blend mode (e.g., REPLACE, CROSS, ALPHA_OVER).",
            },
            "blend_alpha": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Blend opacity (0.0 to 1.0).",
            },
            "color": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "minItems": 3,
                "maxItems": 4,
                "description": "RGB color float tuple (0.0 to 1.0) for COLOR strips.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_DELETE_VSE_STRIP] = {
    "name": TOOL_DELETE_VSE_STRIP,
    "description": (
        "Remove and unlink a strip from the Blender Video Sequence Editor (VSE) by name."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the strip to delete.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_MANAGE_TIMELINE_MARKERS] = {
    "name": TOOL_MANAGE_TIMELINE_MARKERS,
    "description": (
        "Manage timeline markers in the active scene: add, remove, or list markers."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["action"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "list"],
                "description": "Marker operation to perform.",
            },
            "name": {
                "type": "string",
                "description": "Marker name (required for 'add' and 'remove').",
            },
            "frame": {
                "type": "integer",
                "description": "Timeline frame index for the marker (required for 'add').",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


# VSE Capability 2: Editorial & Trimming Tool Definitions
TOOL_DEFINITIONS[TOOL_TRIM_VSE_STRIP] = {
    "name": TOOL_TRIM_VSE_STRIP,
    "description": (
        "Trim head (in-point) and/or tail (out-point) handles of a strip in the Video Sequence Editor (VSE), "
        "with optional ripple editing to shift subsequent strips on the same channel."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the strip to trim.",
            },
            "trim_mode": {
                "type": "string",
                "enum": ["ABSOLUTE", "RELATIVE"],
                "default": "ABSOLUTE",
                "description": "Trim mode: ABSOLUTE frame position or RELATIVE frame delta.",
            },
            "left_handle": {
                "type": "integer",
                "description": "New left handle (in-point) frame or relative delta.",
            },
            "right_handle": {
                "type": "integer",
                "description": "New right handle (out-point) frame or relative delta.",
            },
            "ripple": {
                "type": "boolean",
                "default": False,
                "description": "Whether to ripple shift subsequent strips on the same channel by the duration delta.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_SPLIT_VSE_STRIP] = {
    "name": TOOL_SPLIT_VSE_STRIP,
    "description": (
        "Split a strip at a designated cut frame into two contiguous strips on the same channel, "
        "preserving properties across the cut."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name", "split_frame"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the strip to split.",
            },
            "split_frame": {
                "type": "integer",
                "description": "Timeline frame index where the split cut occurs (must be strictly between in-point and out-point).",
            },
            "right_strip_name": {
                "type": "string",
                "description": "Optional name for the new second (right) strip.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_REORDER_VSE_STRIPS] = {
    "name": TOOL_REORDER_VSE_STRIPS,
    "description": (
        "Perform editorial reorganization on VSE strips: MOVE channel/position, SWAP channels between strips, "
        "CLOSE_GAPS between sequential strips on a channel, or SNAP to adjacent strip boundaries."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["action"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["MOVE", "SWAP", "CLOSE_GAPS", "SNAP"],
                "description": "Editorial action to perform.",
            },
            "name": {
                "type": "string",
                "description": "Target strip name for MOVE or SNAP.",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "Target channel for MOVE, or channel index for CLOSE_GAPS.",
            },
            "target_frame": {
                "type": "integer",
                "description": "Target timeline start frame for MOVE, or snap frame target for SNAP with snap_to='FRAME'.",
            },
            "strip_a": {
                "type": "string",
                "description": "First strip name for SWAP.",
            },
            "strip_b": {
                "type": "string",
                "description": "Second strip name for SWAP.",
            },
            "snap_to": {
                "type": "string",
                "enum": ["PREVIOUS_STRIP", "NEXT_STRIP", "FRAME"],
                "default": "PREVIOUS_STRIP",
                "description": "Snap alignment target.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


# VSE Capability 3: Transitions & Visual Effects Tool Definitions
TOOL_DEFINITIONS[TOOL_CREATE_VSE_TRANSITION] = {
    "name": TOOL_CREATE_VSE_TRANSITION,
    "description": (
        "Create a transition effect (CROSS, GAMMA_CROSS, WIPE, ALPHA_OVER, ALPHA_UNDER, COLORMIX) "
        "between two overlapping or adjacent strips in the Video Sequence Editor (VSE)."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["transition_type", "input1", "input2"],
        "properties": {
            "transition_type": {
                "type": "string",
                "enum": ["CROSS", "GAMMA_CROSS", "WIPE", "ALPHA_OVER", "ALPHA_UNDER", "COLORMIX"],
                "description": "Type of transition to create.",
            },
            "input1": {
                "type": "string",
                "description": "Name of the first (outgoing / lower) input strip.",
            },
            "input2": {
                "type": "string",
                "description": "Name of the second (incoming / upper) input strip.",
            },
            "name": {
                "type": "string",
                "description": "Optional name for the transition strip. Auto-generated if omitted.",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "Channel index for the transition strip.",
            },
            "frame_start": {
                "type": "integer",
                "description": "Timeline start frame (defaults to overlap start).",
            },
            "duration": {
                "type": "integer",
                "minimum": 1,
                "description": "Transition duration in frames (defaults to overlap length).",
            },
            "wipe_type": {
                "type": "string",
                "enum": ["SINGLE", "DOUBLE", "IRIS", "CLOCK"],
                "default": "SINGLE",
                "description": "Wipe transition pattern type for WIPE transitions.",
            },
            "direction": {
                "type": "string",
                "enum": ["IN", "OUT"],
                "default": "OUT",
                "description": "Wipe direction (IN or OUT).",
            },
            "blur_width": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.0,
                "description": "Wipe edge blur factor (0.0 to 1.0).",
            },
            "angle": {
                "type": "number",
                "description": "Wipe angle in radians.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CONFIGURE_VSE_EFFECT] = {
    "name": TOOL_CONFIGURE_VSE_EFFECT,
    "description": (
        "Create, update, or inspect visual effect strips (GAUSSIAN_BLUR, GLOW, SPEED, ADJUSTMENT, COLORMIX) "
        "in the Video Sequence Editor (VSE)."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["action"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["CREATE", "UPDATE", "INSPECT"],
                "description": "Effect action: CREATE new effect strip, UPDATE existing effect properties, or INSPECT effect settings.",
            },
            "name": {
                "type": "string",
                "description": "Name of the effect strip (required for UPDATE and INSPECT, optional for CREATE).",
            },
            "effect_type": {
                "type": "string",
                "enum": ["GAUSSIAN_BLUR", "GLOW", "SPEED", "ADJUSTMENT", "COLORMIX"],
                "description": "Type of visual effect strip (required for CREATE).",
            },
            "input_strip": {
                "type": "string",
                "description": "Source strip name to apply effect to (required for GAUSSIAN_BLUR, GLOW, SPEED).",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "Channel index for the effect strip.",
            },
            "frame_start": {
                "type": "integer",
                "description": "Timeline start frame (defaults to input_strip.left_handle if provided).",
            },
            "duration": {
                "type": "integer",
                "minimum": 1,
                "description": "Duration in frames (defaults to input_strip.duration if provided).",
            },
            "size_x": {
                "type": "number",
                "minimum": 0.0,
                "description": "Horizontal blur size for GAUSSIAN_BLUR.",
            },
            "size_y": {
                "type": "number",
                "minimum": 0.0,
                "description": "Vertical blur size for GAUSSIAN_BLUR.",
            },
            "threshold": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Luminance threshold for GLOW.",
            },
            "clamp": {
                "type": "number",
                "minimum": 0.0,
                "description": "Maximum luminance clamp for GLOW.",
            },
            "boost_factor": {
                "type": "number",
                "minimum": 0.0,
                "description": "Glow brightness multiplier.",
            },
            "blur_radius": {
                "type": "number",
                "minimum": 0.0,
                "description": "Glow blur radius.",
            },
            "quality": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Glow calculation quality (1 to 5).",
            },
            "speed_factor": {
                "type": "number",
                "minimum": 0.01,
                "description": "Playback speed multiplier for SPEED effect.",
            },
            "speed_control": {
                "type": "string",
                "enum": ["MULTIPLY", "LENGTH", "FRAME"],
                "default": "MULTIPLY",
                "description": "Speed control method.",
            },
            "mute": {
                "type": "boolean",
                "description": "Mute state of the effect strip.",
            },
            "blend_alpha": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Effect blend opacity (0.0 to 1.0).",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


# VSE Capability 4: Audio Engineering Tool Definitions
TOOL_DEFINITIONS[TOOL_CONFIGURE_VSE_AUDIO] = {
    "name": TOOL_CONFIGURE_VSE_AUDIO,
    "description": (
        "Configure audio properties (volume, pan, pitch correction, waveform display, mute, fade-in/fade-out) "
        "on a SoundStrip in the Video Sequence Editor (VSE)."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target audio/sound strip.",
            },
            "action": {
                "type": "string",
                "enum": ["UPDATE", "INSPECT"],
                "default": "UPDATE",
                "description": "Action: UPDATE audio settings or INSPECT current configuration.",
            },
            "volume": {
                "type": "number",
                "minimum": 0.0,
                "description": "Playback volume multiplier (1.0 = 100%, 0.0 = silent).",
            },
            "pan": {
                "type": "number",
                "minimum": -1.0,
                "maximum": 1.0,
                "description": "Stereo panning (-1.0 = full left, 0.0 = center, 1.0 = full right).",
            },
            "pitch_correction": {
                "type": "boolean",
                "description": "Maintain audio pitch when strip playback speed is retimed.",
            },
            "show_waveform": {
                "type": "boolean",
                "description": "Draw audio waveform inside the timeline strip.",
            },
            "mute": {
                "type": "boolean",
                "description": "Mute audio playback for this strip.",
            },
            "fade_in_duration": {
                "type": "integer",
                "minimum": 1,
                "description": "Duration in frames for linear volume fade-in from strip start.",
            },
            "fade_out_duration": {
                "type": "integer",
                "minimum": 1,
                "description": "Duration in frames for linear volume fade-out to strip end.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_MANAGE_VSE_SOUND_MODIFIERS] = {
    "name": TOOL_MANAGE_VSE_SOUND_MODIFIERS,
    "description": (
        "Add, remove, update, or list audio modifiers (SOUND_EQUALIZER, PITCH, ECHO) "
        "on sequencer strips (MetaStrips, MovieStrips, or Adjustment strips) in the VSE."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["action", "name"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ADD", "REMOVE", "UPDATE", "LIST"],
                "description": "Action to perform on strip sound modifiers.",
            },
            "name": {
                "type": "string",
                "description": "Target strip name.",
            },
            "modifier_name": {
                "type": "string",
                "description": "Name of modifier (optional for ADD/LIST, required for REMOVE/UPDATE).",
            },
            "modifier_type": {
                "type": "string",
                "enum": ["SOUND_EQUALIZER", "PITCH", "ECHO"],
                "description": "Modifier type (required for ADD).",
            },
            "mute": {
                "type": "boolean",
                "description": "Mute modifier effect.",
            },
            "enable": {
                "type": "boolean",
                "description": "Enable or disable modifier in viewport/rendering.",
            },
            "pitch_mode": {
                "type": "string",
                "enum": ["SEMITONES", "CENTS", "RATIO"],
                "description": "Pitch adjustment method for PITCH modifier.",
            },
            "semitones": {
                "type": "number",
                "description": "Semitone shift for PITCH modifier (-36 to +36).",
            },
            "cents": {
                "type": "number",
                "description": "Fine cents shift for PITCH modifier (-100 to +100).",
            },
            "ratio": {
                "type": "number",
                "minimum": 0.01,
                "description": "Frequency ratio multiplier for PITCH modifier.",
            },
            "preserve_formant": {
                "type": "boolean",
                "description": "Preserve vocal formants when shifting pitch.",
            },
            "quality": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Pitch algorithm quality (1 to 5).",
            },
            "delay": {
                "type": "number",
                "minimum": 0.0,
                "description": "Echo delay in seconds for ECHO modifier.",
            },
            "feedback": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Echo feedback repetition amount (0.0 to 1.0).",
            },
            "mix": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Echo dry/wet mix factor (0.0 to 1.0).",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}
import ast
import math

ALLOWED_INSPECT_CATEGORIES = (
    "scene_summary",
    "object_modifiers",
    "object_materials",
    "mesh_topology",
    "scene_hierarchy",
    "world_settings",
    "collection_tree",
    "render_settings",
    "blender_info",
    "uv_layers",
    "render_result",
    "compositor_pipeline",
    "compositor_settings",
    "cameras",
    "camera_settings",
)
OBJECT_SPECIFIC_INSPECT_CATEGORIES = {
    "object_modifiers",
    "object_materials",
    "mesh_topology",
    "uv_layers",
}


# VSE Capability 5: Transforms & Keyframing Tool Definitions
TOOL_DEFINITIONS[TOOL_TRANSFORM_VSE_STRIP] = {
    "name": TOOL_TRANSFORM_VSE_STRIP,
    "description": (
        "Configure 2D transform attributes (offset_x, offset_y, scale_x, scale_y, rotation, origin, filter) "
        "on a strip in the Video Sequence Editor (VSE)."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target strip in the sequence editor.",
            },
            "action": {
                "type": "string",
                "enum": ["UPDATE", "INSPECT"],
                "default": "UPDATE",
                "description": "Action: UPDATE transform properties or INSPECT current transform.",
            },
            "offset_x": {
                "type": "number",
                "description": "Horizontal translation offset in pixels.",
            },
            "offset_y": {
                "type": "number",
                "description": "Vertical translation offset in pixels.",
            },
            "scale_x": {
                "type": "number",
                "description": "Horizontal scale factor (1.0 = 100%).",
            },
            "scale_y": {
                "type": "number",
                "description": "Vertical scale factor (1.0 = 100%).",
            },
            "rotation": {
                "type": "number",
                "description": "Rotation angle in radians.",
            },
            "origin": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Origin pivot point [x, y] in normalized coordinates (0.0 to 1.0).",
            },
            "filter": {
                "type": "string",
                "enum": ["AUTO", "NEAREST", "BILINEAR"],
                "description": "Interpolation filter method.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CROP_VSE_STRIP] = {
    "name": TOOL_CROP_VSE_STRIP,
    "description": (
        "Configure pixel cropping boundaries (min_x, max_x, min_y, max_y) on a strip in the VSE."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target strip in the sequence editor.",
            },
            "action": {
                "type": "string",
                "enum": ["UPDATE", "INSPECT"],
                "default": "UPDATE",
                "description": "Action: UPDATE crop properties or INSPECT current crop boundaries.",
            },
            "min_x": {
                "type": "integer",
                "minimum": 0,
                "description": "Left crop margin in pixels.",
            },
            "max_x": {
                "type": "integer",
                "minimum": 0,
                "description": "Right crop margin in pixels.",
            },
            "min_y": {
                "type": "integer",
                "minimum": 0,
                "description": "Bottom crop margin in pixels.",
            },
            "max_y": {
                "type": "integer",
                "minimum": 0,
                "description": "Top crop margin in pixels.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_ANIMATE_VSE_STRIP] = {
    "name": TOOL_ANIMATE_VSE_STRIP,
    "description": (
        "Insert or delete keyframes on strip transform, crop, opacity, or audio properties in the VSE."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name", "action", "property", "frame"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target strip in the sequence editor.",
            },
            "action": {
                "type": "string",
                "enum": ["INSERT_KEYFRAME", "DELETE_KEYFRAME"],
                "description": "Animation action: INSERT_KEYFRAME or DELETE_KEYFRAME.",
            },
            "property": {
                "type": "string",
                "enum": [
                    "OFFSET_X", "OFFSET_Y", "SCALE_X", "SCALE_Y", "ROTATION",
                    "BLEND_ALPHA", "VOLUME", "PAN",
                    "CROP_LEFT", "CROP_RIGHT", "CROP_BOTTOM", "CROP_TOP"
                ],
                "description": "Property identifier to keyframe.",
            },
            "frame": {
                "type": "integer",
                "description": "Timeline frame index for the keyframe.",
            },
            "value": {
                "type": "number",
                "description": "Optional value to apply to the property before keyframing (for INSERT_KEYFRAME).",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

# VSE Capability 6: Color Grading & Strip Modifiers Tool Definitions
TOOL_DEFINITIONS[TOOL_MANAGE_VSE_STRIP_MODIFIERS] = {
    "name": TOOL_MANAGE_VSE_STRIP_MODIFIERS,
    "description": (
        "Add, remove, update, or list visual color grading and strip modifiers "
        "(COLOR_BALANCE, BRIGHT_CONTRAST, WHITE_BALANCE, TONEMAP, CURVES, HUE_CORRECT, MASK) "
        "on strips in the Video Sequence Editor (VSE)."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["action", "name"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ADD", "REMOVE", "UPDATE", "LIST"],
                "description": "Action to perform on strip modifiers.",
            },
            "name": {
                "type": "string",
                "description": "Name of the target strip in the sequence editor.",
            },
            "modifier_name": {
                "type": "string",
                "description": "Name of modifier (optional for ADD/LIST, required for REMOVE/UPDATE).",
            },
            "modifier_type": {
                "type": "string",
                "enum": ["COLOR_BALANCE", "BRIGHT_CONTRAST", "WHITE_BALANCE", "TONEMAP", "CURVES", "HUE_CORRECT", "MASK"],
                "description": "Modifier type (required for ADD).",
            },
            "mute": {
                "type": "boolean",
                "description": "Mute modifier effect.",
            },
            "enable": {
                "type": "boolean",
                "description": "Enable or disable modifier in viewport/rendering.",
            },
            "input_mask_type": {
                "type": "string",
                "enum": ["STRIP", "ID"],
                "description": "Masking input type.",
            },
            "input_mask_strip": {
                "type": "string",
                "description": "Name of strip to use as a mask.",
            },
            "mask_time": {
                "type": "string",
                "enum": ["RELATIVE", "ABSOLUTE"],
                "description": "Time mapping method for the mask.",
            },
            "correction_method": {
                "type": "string",
                "enum": ["LIFT_GAMMA_GAIN", "OFFSET_POWER_SLOPE"],
                "description": "Color correction formula for COLOR_BALANCE modifier.",
            },
            "lift": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Shadows lift RGB [r, g, b] for COLOR_BALANCE.",
            },
            "gamma": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Midtones gamma RGB [r, g, b] for COLOR_BALANCE.",
            },
            "gain": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Highlights gain RGB [r, g, b] for COLOR_BALANCE.",
            },
            "slope": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "ASC-CDL slope RGB [r, g, b] for COLOR_BALANCE.",
            },
            "offset": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "ASC-CDL offset RGB [r, g, b] for COLOR_BALANCE.",
            },
            "power": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "ASC-CDL power RGB [r, g, b] for COLOR_BALANCE.",
            },
            "color_multiply": {
                "type": "number",
                "minimum": 0.0,
                "description": "Overall color balance multiplier.",
            },
            "bright": {
                "type": "number",
                "description": "Brightness adjustment for BRIGHT_CONTRAST.",
            },
            "contrast": {
                "type": "number",
                "description": "Contrast adjustment for BRIGHT_CONTRAST.",
            },
            "white_value": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "White point balance RGB [r, g, b] for WHITE_BALANCE.",
            },
            "tonemap_type": {
                "type": "string",
                "enum": ["RD_PHOTORECEPTOR", "RH_SIMPLE"],
                "description": "Tonemapping algorithm for TONEMAP.",
            },
            "tonemap_key": {
                "type": "number",
                "description": "Key value for TONEMAP.",
            },
            "tonemap_intensity": {
                "type": "number",
                "description": "Intensity for TONEMAP.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}
# VSE Capability 7: Titles & Subtitles Tool Definitions
TOOL_DEFINITIONS[TOOL_CREATE_VSE_TEXT_STRIP] = {
    "name": TOOL_CREATE_VSE_TEXT_STRIP,
    "description": (
        "Create a dedicated text or subtitle strip in the Video Sequence Editor (VSE) "
        "with typography, placement, alignment, shadow, outline, and background box styling."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["text", "channel", "frame_start", "duration"],
        "properties": {
            "text": {
                "type": "string",
                "description": "Text content to display.",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "Timeline channel index (1 to 128).",
            },
            "frame_start": {
                "type": "integer",
                "description": "Timeline start frame.",
            },
            "duration": {
                "type": "integer",
                "minimum": 1,
                "description": "Duration in frames.",
            },
            "name": {
                "type": "string",
                "description": "Optional unique name for the text strip.",
            },
            "font_size": {
                "type": "number",
                "minimum": 1.0,
                "description": "Font size in points.",
            },
            "color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Text color as RGBA [r, g, b, a].",
            },
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Normalized screen coordinates [x, y] (0.0 to 1.0).",
            },
            "alignment_x": {
                "type": "string",
                "enum": ["LEFT", "CENTER", "RIGHT"],
                "description": "Horizontal text alignment.",
            },
            "anchor_x": {
                "type": "string",
                "enum": ["LEFT", "CENTER", "RIGHT"],
                "description": "Horizontal anchor alignment.",
            },
            "anchor_y": {
                "type": "string",
                "enum": ["TOP", "CENTER", "BOTTOM"],
                "description": "Vertical anchor alignment.",
            },
            "wrap_width": {
                "type": "number",
                "minimum": 0.0,
                "description": "Word wrap width (0.0 = no wrap).",
            },
            "use_bold": {
                "type": "boolean",
                "description": "Render text in bold weight.",
            },
            "use_italic": {
                "type": "boolean",
                "description": "Render text in italic slant.",
            },
            "use_shadow": {
                "type": "boolean",
                "description": "Enable drop shadow behind text.",
            },
            "shadow_color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Shadow RGBA color [r, g, b, a].",
            },
            "shadow_blur": {
                "type": "number",
                "minimum": 0.0,
                "description": "Shadow edge blur radius.",
            },
            "use_outline": {
                "type": "boolean",
                "description": "Enable text outline stroke.",
            },
            "outline_color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Outline stroke RGBA color [r, g, b, a].",
            },
            "outline_width": {
                "type": "number",
                "minimum": 0.0,
                "description": "Outline stroke width.",
            },
            "use_box": {
                "type": "boolean",
                "description": "Enable background box behind text.",
            },
            "box_color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Background box RGBA color [r, g, b, a].",
            },
            "box_margin": {
                "type": "number",
                "minimum": 0.0,
                "description": "Background box padding margin.",
            },
            "box_roundness": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Background box corner roundness (0.0 to 1.0).",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CONFIGURE_VSE_TEXT_STYLE] = {
    "name": TOOL_CONFIGURE_VSE_TEXT_STYLE,
    "description": (
        "Configure or inspect typography, layout, shadow, outline, or box styling "
        "on an existing text or subtitle strip in the VSE."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the target text strip.",
            },
            "action": {
                "type": "string",
                "enum": ["UPDATE", "INSPECT"],
                "default": "UPDATE",
                "description": "Action: UPDATE styling properties or INSPECT current configuration.",
            },
            "text": {
                "type": "string",
                "description": "New text content to display.",
            },
            "font_size": {
                "type": "number",
                "minimum": 1.0,
                "description": "Font size in points.",
            },
            "color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Text color as RGBA [r, g, b, a].",
            },
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Normalized screen coordinates [x, y] (0.0 to 1.0).",
            },
            "alignment_x": {
                "type": "string",
                "enum": ["LEFT", "CENTER", "RIGHT"],
                "description": "Horizontal text alignment.",
            },
            "anchor_x": {
                "type": "string",
                "enum": ["LEFT", "CENTER", "RIGHT"],
                "description": "Horizontal anchor alignment.",
            },
            "anchor_y": {
                "type": "string",
                "enum": ["TOP", "CENTER", "BOTTOM"],
                "description": "Vertical anchor alignment.",
            },
            "wrap_width": {
                "type": "number",
                "minimum": 0.0,
                "description": "Word wrap width (0.0 = no wrap).",
            },
            "use_bold": {
                "type": "boolean",
                "description": "Render text in bold weight.",
            },
            "use_italic": {
                "type": "boolean",
                "description": "Render text in italic slant.",
            },
            "use_shadow": {
                "type": "boolean",
                "description": "Enable drop shadow behind text.",
            },
            "shadow_color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Shadow RGBA color [r, g, b, a].",
            },
            "shadow_blur": {
                "type": "number",
                "minimum": 0.0,
                "description": "Shadow edge blur radius.",
            },
            "use_outline": {
                "type": "boolean",
                "description": "Enable text outline stroke.",
            },
            "outline_color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Outline stroke RGBA color [r, g, b, a].",
            },
            "outline_width": {
                "type": "number",
                "minimum": 0.0,
                "description": "Outline stroke width.",
            },
            "use_box": {
                "type": "boolean",
                "description": "Enable background box behind text.",
            },
            "box_color": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Background box RGBA color [r, g, b, a].",
            },
            "box_margin": {
                "type": "number",
                "minimum": 0.0,
                "description": "Background box padding margin.",
            },
            "box_roundness": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Background box corner roundness (0.0 to 1.0).",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

# VSE Capability 8: Nested Sequences Tool Definitions
TOOL_DEFINITIONS[TOOL_GROUP_VSE_META_STRIP] = {
    "name": TOOL_GROUP_VSE_META_STRIP,
    "description": (
        "Group multiple strips into a nested MetaStrip container, ungroup an existing "
        "MetaStrip back into individual strips, or inspect internal nested strips in the VSE."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["action"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["CREATE", "UNGROUP", "INSPECT"],
                "description": "Action to perform: 'CREATE' (group strips into meta), 'UNGROUP' (separate meta strip), 'INSPECT' (query child strips).",
            },
            "name": {
                "type": "string",
                "description": "Name of the meta strip (required for UNGROUP and INSPECT; optional for CREATE).",
            },
            "strip_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of strip names to group into the meta strip (required when action='CREATE').",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "Timeline channel index for the meta strip container (1 to 128).",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CREATE_VSE_SCENE_STRIP] = {
    "name": TOOL_CREATE_VSE_SCENE_STRIP,
    "description": (
        "Create a nested SceneStrip referencing another Blender scene's 3D camera view "
        "or sequencer timeline inside the active VSE."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["scene_name", "channel", "frame_start"],
        "properties": {
            "scene_name": {
                "type": "string",
                "description": "Name of the referenced Blender scene (must exist in bpy.data.scenes).",
            },
            "channel": {
                "type": "integer",
                "minimum": 1,
                "maximum": 128,
                "description": "Timeline channel index (1 to 128).",
            },
            "frame_start": {
                "type": "integer",
                "description": "Starting frame on the timeline.",
            },
            "name": {
                "type": "string",
                "description": "Optional custom name for the scene strip.",
            },
            "duration": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional strip duration in frames (defaults to scene frame range length).",
            },
            "scene_input": {
                "type": "string",
                "enum": ["CAMERA", "SEQUENCER"],
                "description": "Input source from referenced scene: 'CAMERA' (render 3D camera) or 'SEQUENCER' (nested sequencer timeline).",
                "default": "CAMERA",
            },
            "scene_camera": {
                "type": "string",
                "description": "Optional camera object name to use from the referenced scene.",
            },
            "view_layer": {
                "type": "string",
                "description": "Optional view layer name in the referenced scene.",
            },
            "blend_type": {
                "type": "string",
                "enum": ["REPLACE", "CROSS", "ALPHA_OVER", "ALPHA_UNDER", "MULTIPLY", "ADD", "SUBTRACT"],
                "description": "Blend mode for compositing the scene strip.",
            },
            "blend_alpha": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Opacity factor (0.0 to 1.0).",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

# VSE Capability 9: Sequencer Rendering & Audio Mixdown Tool Definitions
TOOL_DEFINITIONS[TOOL_RENDER_VSE_SEQUENCE] = {
    "name": TOOL_RENDER_VSE_SEQUENCE,
    "description": (
        "Render a video or image sequence from the active Video Sequence Editor (VSE) "
        "timeline to an output file on disk using FFMPEG or image formats."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["output_path"],
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Destination file path for the rendered video or image sequence (path traversal forbidden).",
            },
            "frame_start": {
                "type": "integer",
                "description": "Optional starting frame (defaults to scene frame_start).",
            },
            "frame_end": {
                "type": "integer",
                "description": "Optional ending frame (defaults to scene frame_end).",
            },
            "format": {
                "type": "string",
                "enum": ["MPEG4", "MKV", "QUICKTIME", "WEBM", "AVI", "PNG", "JPEG"],
                "description": "Container format (defaults to MPEG4).",
                "default": "MPEG4",
            },
            "video_codec": {
                "type": "string",
                "enum": ["H264", "H265", "PRORES", "DNXHD", "PNG", "NONE"],
                "description": "Video encoding codec (defaults to H264 for MPEG4/MKV, PRORES for QUICKTIME).",
            },
            "audio_codec": {
                "type": "string",
                "enum": ["AAC", "AC3", "FLAC", "MP3", "PCM", "OPUS", "NONE"],
                "description": "Audio encoding codec (defaults to AAC).",
            },
            "resolution_x": {
                "type": "integer",
                "minimum": 16,
                "maximum": 8192,
                "description": "Horizontal render resolution in pixels.",
            },
            "resolution_y": {
                "type": "integer",
                "minimum": 16,
                "maximum": 8192,
                "description": "Vertical render resolution in pixels.",
            },
            "resolution_percentage": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Render resolution scaling percentage (1 to 100).",
            },
            "fps": {
                "type": "number",
                "minimum": 1.0,
                "maximum": 240.0,
                "description": "Timeline framerate for rendering.",
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_MIXDOWN_VSE_AUDIO] = {
    "name": TOOL_MIXDOWN_VSE_AUDIO,
    "description": (
        "Mix down and export all active audio strips from the Video Sequence Editor timeline "
        "to a dedicated audio sound file (WAV, FLAC, MP3, OGG, AAC)."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "required": ["output_path"],
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Destination file path for the mixed audio file (path traversal forbidden).",
            },
            "container": {
                "type": "string",
                "enum": ["WAV", "FLAC", "MP3", "OGG", "AAC"],
                "description": "Audio container format (inferred from output_path extension if omitted).",
            },
            "codec": {
                "type": "string",
                "enum": ["PCM", "FLAC", "MP3", "VORBIS", "AAC"],
                "description": "Audio codec (inferred from container if omitted).",
            },
            "format": {
                "type": "string",
                "enum": ["U8", "S16", "S24", "S32", "FLOAT", "DOUBLE"],
                "description": "Audio bit depth / sample format (default: S16).",
                "default": "S16",
            },
            "channels": {
                "type": "string",
                "enum": ["MONO", "STEREO", "SURROUND_51", "SURROUND_71"],
                "description": "Channel layout (default: STEREO).",
                "default": "STEREO",
            },
            "sample_rate": {
                "type": "integer",
                "minimum": 8000,
                "maximum": 192000,
                "description": "Audio sample rate in Hz (default: 48000).",
                "default": 48000,
            },
            "bitrate": {
                "type": "integer",
                "minimum": 32,
                "maximum": 512,
                "description": "Audio bitrate in kbps for compressed formats (default: 192).",
                "default": 192,
            },
            "approved": {
                "type": "boolean",
                "description": "DEPRECATED / UNTRUSTED: Client-supplied approval flags in tool arguments are not trusted as proof of human consent.",
                "default": False,
            },
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CREATE_CYCLORAMA] = {
    "name": TOOL_CREATE_CYCLORAMA,
    "description": (
        "Creates a parameterized seamless curved studio sweep backdrop (infinite cove) "
        "with smooth shading, tangent continuity, and predictable bounding dimensions "
        "for product staging and visualization."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the cyclorama object to create.", "default": "StudioCyclorama"},
            "width": {"type": "number", "minimum": 0.1, "description": "Width along X axis in meters.", "default": 10.0},
            "depth": {"type": "number", "minimum": 0.1, "description": "Floor depth along Y axis in meters.", "default": 10.0},
            "wall_height": {"type": "number", "minimum": 0.1, "description": "Height of the back wall along Z axis in meters.", "default": 5.0},
            "cove_radius": {"type": "number", "minimum": 0.0, "description": "Fillet radius of the curved transition cove.", "default": 1.5},
            "cove_segments": {"type": "integer", "minimum": 1, "maximum": 64, "description": "Subdivision segments along the cove curve.", "default": 16},
            "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "default": [0.0, 0.0, 0.0]},
            "rotation_euler": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "default": [0.0, 0.0, 0.0]},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_SET_OBJECT_ORIGIN] = {
    "name": TOOL_SET_OBJECT_ORIGIN,
    "description": (
        "Reposition an object's local origin/pivot point while preserving world-space "
        "vertex coordinates. Supports 'BOTTOM_CENTER', 'CENTER_OF_MASS', 'ORIGIN_TO_GEOMETRY', "
        "'GEOMETRY_TO_ORIGIN', 'ORIGIN_TO_CURSOR', 'CUSTOM_POINT'."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "object_name": {"type": "string", "description": "Name of the target mesh object."},
            "origin_mode": {
                "type": "string",
                "enum": ["BOTTOM_CENTER", "CENTER_OF_MASS", "ORIGIN_TO_GEOMETRY", "GEOMETRY_TO_ORIGIN", "ORIGIN_TO_CURSOR", "CUSTOM_POINT"],
                "description": "Target origin placement mode.",
                "default": "BOTTOM_CENTER",
            },
            "custom_point": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": "World [x, y, z] point when origin_mode is 'CUSTOM_POINT'."},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["object_name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CREATE_ROOM_ENCLOSURE] = {
    "name": TOOL_CREATE_ROOM_ENCLOSURE,
    "description": (
        "Creates a solid manifold architectural room enclosure with parameterized width, "
        "length, wall height, wall thickness, floor slab, optional ceiling slab, and structured doorway apertures."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the room enclosure object.", "default": "InteriorRoom"},
            "width": {"type": "number", "minimum": 0.5, "description": "Interior room width along X axis in meters.", "default": 6.0},
            "length": {"type": "number", "minimum": 0.5, "description": "Interior room length along Y axis in meters.", "default": 8.0},
            "height": {"type": "number", "minimum": 0.5, "description": "Interior room height along Z axis in meters.", "default": 3.0},
            "wall_thickness": {"type": "number", "minimum": 0.01, "description": "Wall thickness in meters.", "default": 0.2},
            "include_floor": {"type": "boolean", "description": "Whether to generate floor slab.", "default": True},
            "include_ceiling": {"type": "boolean", "description": "Whether to generate ceiling slab.", "default": False},
            "door_wall": {
                "type": "string",
                "enum": ["NORTH", "SOUTH", "EAST", "WEST", "NONE"],
                "description": "Wall containing doorway cutout (or 'NONE').",
                "default": "NONE",
            },
            "door_width": {"type": "number", "minimum": 0.1, "description": "Doorway aperture width in meters.", "default": 0.9},
            "door_height": {"type": "number", "minimum": 0.1, "description": "Doorway aperture height in meters.", "default": 2.1},
            "door_offset": {"type": "number", "description": "Offset from wall center along wall axis in meters.", "default": 0.0},
            "roof_type": {
                "type": "string",
                "enum": ["NONE", "FLAT", "GABLE", "HIP", "PITCHED"],
                "description": "Optional integrated roof structure type atop the room walls.",
                "default": "NONE",
            },
            "roof_height": {"type": "number", "minimum": 0.1, "description": "Rise of the integrated roof in meters.", "default": 2.0},
            "roof_overhang": {"type": "number", "minimum": 0.0, "description": "Overhang of the integrated roof beyond walls.", "default": 0.3},
            "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "default": [0.0, 0.0, 0.0]},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CREATE_ROOF_STRUCTURE] = {
    "name": TOOL_CREATE_ROOF_STRUCTURE,
    "description": (
        "Generates a parametric watertight solid roof structure ('GABLE', 'HIP', 'PITCHED', 'SHED', 'FLAT') "
        "with specified span, rise height, rafter/slab thickness, eaves overhang, and optional snapping to existing building objects."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the roof object to create.", "default": "ArchitecturalRoof"},
            "roof_type": {
                "type": "string",
                "enum": ["GABLE", "HIP", "PITCHED", "SHED", "FLAT"],
                "description": "Roof architecture geometry type.",
                "default": "GABLE",
            },
            "width": {"type": "number", "minimum": 0.5, "description": "Base roof span along X axis in meters.", "default": 8.0},
            "length": {"type": "number", "minimum": 0.5, "description": "Base roof length along Y axis in meters.", "default": 10.0},
            "height": {"type": "number", "minimum": 0.1, "description": "Ridge rise height above base elevation in meters.", "default": 2.5},
            "thickness": {"type": "number", "minimum": 0.01, "description": "Roof slab or rafter thickness in meters.", "default": 0.2},
            "overhang": {"type": "number", "minimum": 0.0, "description": "Eaves overhang beyond footprint in meters.", "default": 0.3},
            "base_elevation": {"type": "number", "description": "Base elevation Z coordinate where the roof rests.", "default": 0.0},
            "target_building": {"type": "string", "description": "Optional name of building/enclosure object to automatically snap and match dimensions to."},
            "solid": {"type": "boolean", "description": "Whether to generate closed watertight manifold solid geometry.", "default": True},
            "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "default": [0.0, 0.0, 0.0]},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CREATE_BUILDING_ENVELOPE] = {
    "name": TOOL_CREATE_BUILDING_ENVELOPE,
    "description": (
        "Constructs a complete exterior building envelope with structural foundation slab, "
        "exterior facade walls, multi-story floor slabs, structured doorway apertures, and seamlessly integrated roof structure."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the building envelope object.", "default": "BuildingEnvelope"},
            "width": {"type": "number", "minimum": 1.0, "description": "Building envelope width along X axis in meters.", "default": 10.0},
            "length": {"type": "number", "minimum": 1.0, "description": "Building envelope length along Y axis in meters.", "default": 12.0},
            "height": {"type": "number", "minimum": 1.0, "description": "Total wall/facade height in meters.", "default": 6.0},
            "stories": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Number of stories/floors in building.", "default": 2},
            "foundation_thickness": {"type": "number", "minimum": 0.05, "description": "Foundation slab thickness in meters.", "default": 0.3},
            "wall_thickness": {"type": "number", "minimum": 0.05, "description": "Exterior facade wall thickness in meters.", "default": 0.25},
            "roof_type": {
                "type": "string",
                "enum": ["GABLE", "HIP", "PITCHED", "FLAT"],
                "description": "Integrated roof geometry type.",
                "default": "GABLE",
            },
            "roof_height": {"type": "number", "minimum": 0.1, "description": "Rise of integrated roof in meters.", "default": 2.5},
            "roof_overhang": {"type": "number", "minimum": 0.0, "description": "Eaves overhang beyond exterior walls in meters.", "default": 0.4},
            "door_wall": {
                "type": "string",
                "enum": ["NORTH", "SOUTH", "EAST", "WEST", "NONE"],
                "description": "Wall containing primary entrance aperture.",
                "default": "SOUTH",
            },
            "door_width": {"type": "number", "minimum": 0.5, "description": "Entrance doorway width in meters.", "default": 1.8},
            "door_height": {"type": "number", "minimum": 1.0, "description": "Entrance doorway height in meters.", "default": 2.4},
            "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "default": [0.0, 0.0, 0.0]},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_CREATE_TERRAIN] = {
    "name": TOOL_CREATE_TERRAIN,
    "description": (
        "Generates a parameterized landscape terrain mesh with multi-octave procedural elevation, "
        "smooth shading, boundary falloff damping, and evaluated elevation metrics."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the terrain object.", "default": "LandscapeTerrain"},
            "width": {"type": "number", "minimum": 1.0, "description": "Terrain width along X axis in meters.", "default": 50.0},
            "depth": {"type": "number", "minimum": 1.0, "description": "Terrain depth along Y axis in meters.", "default": 50.0},
            "resolution_x": {"type": "integer", "minimum": 2, "maximum": 256, "description": "Vertex resolution along X axis.", "default": 64},
            "resolution_y": {"type": "integer", "minimum": 2, "maximum": 256, "description": "Vertex resolution along Y axis.", "default": 64},
            "elevation_scale": {"type": "number", "minimum": 0.0, "description": "Maximum elevation displacement height in meters.", "default": 5.0},
            "noise_scale": {"type": "number", "minimum": 0.001, "description": "Base frequency of procedural noise.", "default": 0.05},
            "noise_octaves": {"type": "integer", "minimum": 1, "maximum": 8, "description": "Number of fractal noise octaves.", "default": 4},
            "roughness": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Fractal roughness multiplier per octave.", "default": 0.5},
            "seed": {"type": "integer", "description": "Deterministic random seed for procedural noise.", "default": 42},
            "boundary_falloff": {"type": "boolean", "description": "Smoothly dampen elevation to zero at boundaries.", "default": True},
            "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "default": [0.0, 0.0, 0.0]},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_SCATTER_SURFACE_ASSETS] = {
    "name": TOOL_SCATTER_SURFACE_ASSETS,
    "description": (
        "Distributes linked duplicates of source props across a target surface mesh "
        "with surface normal alignment, random Z rotation, scale variation, and overlap avoidance."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "surface_name": {"type": "string", "description": "Target terrain/surface object name to scatter onto."},
            "asset_names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "List of source asset object names to distribute."},
            "count": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Number of asset instances to scatter.", "default": 30},
            "seed": {"type": "integer", "description": "Random seed for distribution.", "default": 42},
            "min_scale": {"type": "number", "minimum": 0.01, "description": "Minimum instance scale multiplier.", "default": 0.8},
            "max_scale": {"type": "number", "minimum": 0.01, "description": "Maximum instance scale multiplier.", "default": 1.2},
            "random_rotation_z": {"type": "boolean", "description": "Apply random rotation around surface normal / Z axis.", "default": True},
            "align_to_normal": {"type": "boolean", "description": "Align instance Up vector to surface normal.", "default": True},
            "collection_name": {"type": "string", "description": "Target collection for scattered instances.", "default": "ScatteredAssets"},
            "name_prefix": {"type": "string", "description": "Naming prefix for created instances.", "default": "ScatteredAsset"},
            "min_distance": {"type": "number", "minimum": 0.0, "description": "Minimum distance between scattered instances to prevent overlap.", "default": 1.0},
            "avoid_overlap": {"type": "boolean", "description": "Enforce minimum distance checking.", "default": True},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["surface_name", "asset_names"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_SNAP_TO_GROUND] = {
    "name": TOOL_SNAP_TO_GROUND,
    "description": (
        "Aligns an object's bounding box bottom (Z_min) precisely to the ground surface "
        "(Z = 0 or the top of a specified ground object) with optional offset."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "object_name": {"type": "string", "description": "Name of the target object to align."},
            "ground_name": {"type": "string", "description": "Optional ground object name. If omitted, snaps to world Z = 0."},
            "offset": {"type": "number", "description": "Vertical offset added above ground surface in meters.", "default": 0.0},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["object_name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_ALIGN_OBJECT_GRID] = {
    "name": TOOL_ALIGN_OBJECT_GRID,
    "description": (
        "Snaps an object's world location to the nearest grid increment along specified axes."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "object_name": {"type": "string", "description": "Name of the target object to snap."},
            "grid_size": {"type": "number", "minimum": 0.001, "description": "Grid step size in meters.", "default": 1.0},
            "snap_axes": {
                "type": "array",
                "items": {"type": "string", "enum": ["X", "Y", "Z"]},
                "description": "Axes along which to apply grid snapping.",
                "default": ["X", "Y"],
            },
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["object_name"],
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_BEGIN_ENVIRONMENT_TRANSACTION] = {
    "name": TOOL_BEGIN_ENVIRONMENT_TRANSACTION,
    "description": (
        "Begins a transactional environment mutation session backed by UniversalMutationJournal. "
        "Captures pre-mutation scene state (objects, meshes, materials, collections, transforms) for atomic rollback."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "context_name": {"type": "string", "description": "Diagnostic name for the transaction.", "default": "Environment_Workflow"},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION] = {
    "name": TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION,
    "description": (
        "Executes compensating rollback for an active environment transaction via UniversalMutationJournal. "
        "Restores objects, collections, meshes, materials, transforms, and parents to the pre-transaction baseline."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "string", "description": "Identifier of transaction to roll back (or latest if omitted)."},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_COMMIT_ENVIRONMENT_TRANSACTION] = {
    "name": TOOL_COMMIT_ENVIRONMENT_TRANSACTION,
    "description": (
        "Finalizes and commits an active environment transaction, releasing journal tracking resources."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "string", "description": "Identifier of transaction to commit (or latest if omitted)."},
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOL_DEFINITIONS[TOOL_EXECUTE_ENVIRONMENT_WORKFLOW] = {
    "name": TOOL_EXECUTE_ENVIRONMENT_WORKFLOW,
    "description": (
        "Executes a multi-step environment construction workflow atomically with automatic UniversalMutationJournal "
        "rollback if any step fails or encounters an error, restoring the exact pre-workflow scene state."
    ),
    "permission_tier": PERMISSION_SCENE_MUTATION,
    "input_schema": {
        "type": "object",
        "properties": {
            "workflow_name": {"type": "string", "description": "Descriptive name of the multi-tool workflow.", "default": "EnvironmentWorkflow"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "description": "Name of the environment tool to execute."},
                        "params": {"type": "object", "description": "Input parameters for the tool."},
                    },
                    "required": ["tool"],
                },
                "minItems": 1,
                "description": "Sequential tool invocation steps.",
            },
            "approved": {"type": "boolean", "default": False},
            "request_id": {"type": "string"},
            "approval_token": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["steps"],
        "additionalProperties": False,
    },
}

ALLOWED_MODELING_ACTIONS = (
    "add_modifier",
    "modify_modifier",
    "remove_modifier",
    "set_shade_mode",
    "subdivide_mesh",
    "create_material",
    "assign_material",
    "parent_object",
    "join_objects",
    "extrude",
    "extrude_faces",
    "extrude_mesh",
    "inset",
    "inset_faces",
    "inset_mesh",
    "uv_unwrap",
    "unwrap",
    "unwrap_mesh",
    "uv_smart_project",
    "smart_project",
    "smart_uv_project",
    "uv_project",
    "manage_uv_seams",
    "pack_uv_islands",
    "manage_uv_layers",
    "inspect_uv_mesh",
    "manage_keyframe",
    "insert_keyframe",
    "delete_keyframe",
    "configure_geometry_nodes",
    "inspect_geometry_nodes",
    "export_scene_asset",
    "export_scene",
    "import_scene_asset",
    "import_scene",
    "duplicate_object",
    "duplicate",
    "rename_object",
    "rename",
    "select_object",
    "select",
    "purge_orphaned_datablocks",
    "purge_orphans",
    "create_curve_or_text",
    "create_curve",
    "create_text",
    "manage_shader_nodes",
    "connect_shader_nodes",
    "manage_nodes",
    "bake_object_texture",
    "bake_texture",
    "bake_materials",
    "manage_compositor_nodes",
    "configure_compositor",
    "manage_compositor",
    "configure_animation_curve",
    "manage_fcurve",
    "set_keyframe_interpolation",
    "manage_action_slots",
    "configure_physics",
    "setup_physics",
    "manage_physics",
    "inspect_physics",
    "bake_physics_simulation",
    "open_blend_file",
    "open_project",
    "load_blend_file",
)

ALLOWED_MODIFIER_TYPES = {
    "SUBSURF",
    "BEVEL",
    "SOLIDIFY",
    "MIRROR",
    "BOOLEAN",
    "DECIMATE",
    "ARRAY",
    "SMOOTH",
    "WEIGHTED_NORMAL",
    "EDGE_SPLIT",
    "REMESH",
    "SIMPLE_DEFORM",
    "WELD",
    "TRIANGULATE",
    "WIREFRAME",
}
from blender_addon.universal_mcp.bridge.ast_validator import (
    DISALLOWED_AST_NODES,
    BANNED_NAMES,
    ALLOWED_OPERATOR_PREFIXES,
    SAFE_BUILTIN_CALLS,
    _get_call_chain,
    validate_restricted_code_ast,
)


PRIMITIVE_SPECIFIC_PARAMS: Dict[str, set] = {
    "cube": set(),
    "sphere": {"radius", "segments", "ring_count"},
    "cylinder": {"radius", "depth", "vertices"},
    "plane": {"size"},
    "cone": {"radius", "depth", "vertices"},
    "torus": {"radius", "segments", "ring_count"},
    "monkey": {"size"},
    "grid": {"size", "segments", "ring_count"},
}
ALL_PRIMITIVE_SPECIFIC_PARAMS: set = {"radius", "depth", "size", "segments", "ring_count", "vertices"}


def _validate_and_sanitize_landmarks(landmarks_raw: Any, action: str) -> List[Dict[str, Any]]:
    sanitized_lms: List[Dict[str, Any]] = []
    for idx, lm in enumerate(landmarks_raw):
        if action == "REMOVE" and isinstance(lm, str):
            clean_name = lm.strip()
            if not clean_name:
                raise ValueError(f"Landmark at index {idx} to remove must be a non-empty string.")
            sanitized_lms.append({"name": clean_name})
            continue
        if not isinstance(lm, dict):
            raise ValueError(f"Landmark at index {idx} must be a dictionary.")
        name = str(lm.get("name", "")).strip()
        if not name:
            raise ValueError(f"Landmark at index {idx} must have a non-empty 'name'.")
        if action == "REMOVE":
            sanitized_lms.append({"name": name})
            continue

        san_lm: Dict[str, Any] = {"name": name}
        has_pos = False
        if "vertex_index" in lm and lm["vertex_index"] is not None:
            v_idx = lm["vertex_index"]
            if not isinstance(v_idx, int) or isinstance(v_idx, bool) or v_idx < 0:
                raise ValueError(f"Landmark '{name}' vertex_index must be an integer >= 0.")
            san_lm["vertex_index"] = v_idx
            has_pos = True
        if "position_3d" in lm and lm["position_3d"] is not None:
            p3d = lm["position_3d"]
            if not isinstance(p3d, (list, tuple)) or len(p3d) != 3 or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in p3d):
                raise ValueError(f"Landmark '{name}' position_3d must be a 3-element finite numeric array [x, y, z].")
            san_lm["position_3d"] = [float(c) for c in p3d]
            has_pos = True
        if "reference_views" in lm and lm["reference_views"] is not None:
            ref_views = lm["reference_views"]
            san_rv: Dict[str, List[float]] = {}
            if isinstance(ref_views, dict):
                for v_name, coords in ref_views.items():
                    v_clean = str(v_name).strip().upper()
                    if v_clean not in ("FRONT", "SIDE", "TOP"):
                        raise ValueError(f"Landmark '{name}' has invalid view '{v_clean}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                    if not isinstance(coords, (list, tuple)) or len(coords) != 2 or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in coords):
                        raise ValueError(f"Landmark '{name}' view '{v_clean}' coordinates must be a 2-element numeric array [u, v].")
                    u, v = float(coords[0]), float(coords[1])
                    if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
                        raise ValueError(f"Landmark '{name}' view '{v_clean}' [u, v] coordinates must be normalized between 0.0 and 1.0.")
                    san_rv[v_clean] = [u, v]
            elif isinstance(ref_views, (list, tuple)):
                for r_item in ref_views:
                    if not isinstance(r_item, dict):
                        raise ValueError(f"Landmark '{name}' reference view entry must be a dict.")
                    v_clean = str(r_item.get("view", "")).strip().upper()
                    if v_clean not in ("FRONT", "SIDE", "TOP"):
                        raise ValueError(f"Landmark '{name}' has invalid view '{v_clean}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                    coords = r_item.get("uv") or r_item.get("coordinates")
                    if not isinstance(coords, (list, tuple)) or len(coords) != 2 or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in coords):
                        raise ValueError(f"Landmark '{name}' view '{v_clean}' uv must be a 2-element numeric array [u, v].")
                    u, v = float(coords[0]), float(coords[1])
                    if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
                        raise ValueError(f"Landmark '{name}' view '{v_clean}' [u, v] coordinates must be normalized between 0.0 and 1.0.")
                    san_rv[v_clean] = [u, v]
            else:
                raise ValueError(f"Landmark '{name}' reference_views must be a dict or list.")
            san_lm["reference_views"] = san_rv
            has_pos = True

        has_prop = has_pos or ("weight" in lm) or ("tolerance" in lm)
        if not has_prop:
            raise ValueError(f"Landmark '{name}' must provide at least one of 'vertex_index', 'position_3d', 'reference_views', 'weight', or 'tolerance'.")
        if action != "UPDATE" and not has_pos:
            raise ValueError(f"Landmark '{name}' must provide at least one of 'vertex_index', 'position_3d', or 'reference_views'.")

        weight = float(lm.get("weight", 1.0))
        if not math.isfinite(weight) or weight <= 0.0 or weight > 10.0:
            raise ValueError(f"Landmark '{name}' weight must be a positive float <= 10.0.")
        san_lm["weight"] = weight

        tol = float(lm.get("tolerance", 0.05))
        if not math.isfinite(tol) or tol < 0.0 or tol > 1.0:
            raise ValueError(f"Landmark '{name}' tolerance must be a float between 0.0 and 1.0.")
        san_lm["tolerance"] = tol

        sanitized_lms.append(san_lm)
    return sanitized_lms


def validate_tool_input(tool_name: str, params: Dict[str, Any], trusted_approval: bool = False) -> Dict[str, Any]:
    """
    Validates input parameters against the tool schema.
    Returns sanitized parameters with defaults applied, or raises ValueError on validation failure.
    Enforces trusted user approval for scene mutation tools. Model-supplied approval flags are untrusted.
    """
    if tool_name == TOOL_INSPECT_RENDER_OUTPUT:
        validate_render_id(params)
    tool_def = TOOL_DEFINITIONS.get(tool_name)
    if not tool_def:
        raise ValueError(f"Unknown tool: '{tool_name}'. Available: {list(TOOL_DEFINITIONS.keys())}")

    if tool_name == TOOL_CHECK_APPROVAL_STATUS:
        # This control query accepts no generic credential/metadata passthrough.
        if set(params) - {"request_id"}:
            raise ValueError("Approval status queries accept only request_id.")
        request_id = params.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("Approval status request_id must be a non-empty string.")
        return {"request_id": request_id.strip()}

    schema = tool_def["input_schema"]
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    sanitized = {}

    if tool_name in (
        TOOL_EXTRUDE_MESH, TOOL_EXTRUDE_FACES,
        TOOL_INSET_MESH, TOOL_INSET_FACES,
        TOOL_BEVEL_MESH, TOOL_BEVEL_EDGES,
        TOOL_SPLIT_MESH, TOOL_KNIFE_MESH, TOOL_BISECT_MESH,
        TOOL_DISSOLVE_MESH, TOOL_MERGE_MESH,
        TOOL_RECALCULATE_NORMALS, TOOL_ALIGN_NORMALS,
        TOOL_EDIT_MODIFIER_STACK, TOOL_INSPECT_MODIFIER_STACK,
        TOOL_CONFIGURE_MODIFIER, TOOL_INSPECT_MODIFIERS,
        TOOL_APPLY_MODIFIER,
        TOOL_CONFIGURE_GEOMETRY_NODES, TOOL_INSPECT_GEOMETRY_NODES,
    ):
        if 'target_object' in params or 'object_name' in params:
            params = dict(params)
            if 'name' not in params:
                params['name'] = params.pop('target_object', None) or params.pop('object_name', None)
            else:
                params.pop('target_object', None)
                params.pop('object_name', None)

    if tool_name in (TOOL_CREATE_CAMERA, TOOL_CONFIGURE_CAMERA, TOOL_EDIT_CAMERA):
        for unsupp in ("stereoscopy", "stereo", "multi_view", "velocity", "fisheye_polynomial", "motion_blur"):
            if unsupp in params:
                raise ValueError(f"Unsupported camera property '{unsupp}'.")
        if 'target_name' in params or 'camera_name' in params or 'target_object' in params or 'object_name' in params:
            params = dict(params)
            if 'name' not in params:
                params['name'] = (
                    params.pop('target_name', None)
                    or params.pop('camera_name', None)
                    or params.pop('target_object', None)
                    or params.pop('object_name', None)
                )
            else:
                params.pop('target_name', None)
                params.pop('camera_name', None)
                params.pop('target_object', None)
                params.pop('object_name', None)

    if tool_name == TOOL_SWITCH_CAMERA:
        if 'name' in params or 'target_name' in params:
            params = dict(params)
            if 'camera_name' not in params:
                params['camera_name'] = params.pop('name', None) or params.pop('target_name', None)
            else:
                params.pop('name', None)
                params.pop('target_name', None)

    if tool_name in (TOOL_SCULPT_ORGANIC_ANATOMY, TOOL_CONFIGURE_SEMANTIC_LANDMARKS, TOOL_INSPECT_SEMANTIC_LANDMARKS, TOOL_GUIDE_MESH_LANDMARKS, TOOL_DETAIL_SURFACE_FEATURES, TOOL_INSPECT_SURFACE_DETAIL, TOOL_CONFIGURE_ANATOMICAL_MASK, TOOL_INSPECT_ANATOMICAL_MASK, TOOL_SYMMETRIZE_MESH_GEOMETRY, TOOL_DETECT_SEMANTIC_LANDMARKS, TOOL_BAKE_MESH_SURFACE_MAP):
        if 'target_object' not in params and 'object_name' in params:
            params = dict(params)
            params['target_object'] = params['object_name']


    if tool_name == TOOL_EDIT_MESH:
        validate_component_edit(params)
    if tool_name in (TOOL_CONFIGURE_MODELING_GEOMETRY, TOOL_INSPECT_MODELING_GEOMETRY):
        validate_modeling_geometry(params, inspection=tool_name == TOOL_INSPECT_MODELING_GEOMETRY)

    if tool_name in (TOOL_CONFIGURE_MODELING_OBJECT, TOOL_INSPECT_MODELING_OBJECT):
        validate_object_control(params, inspection=tool_name == TOOL_INSPECT_MODELING_OBJECT)

    if tool_name in (TOOL_CONFIGURE_CURVE_GEOMETRY, TOOL_INSPECT_CURVE_GEOMETRY):
        validate_curve_geometry(params, inspection=tool_name == TOOL_INSPECT_CURVE_GEOMETRY)

    if tool_name in (TOOL_EDIT_MODIFIER_STACK, TOOL_INSPECT_MODIFIER_STACK):
        validate_modifier_stack(params, inspection=tool_name == TOOL_INSPECT_MODIFIER_STACK)

    if tool_name in (TOOL_CONFIGURE_MODIFIER, TOOL_INSPECT_MODIFIERS):
        validate_modifier_params(params, inspection=tool_name == TOOL_INSPECT_MODIFIERS)
    if tool_name in (TOOL_CONFIGURE_MATERIAL_SHADER, TOOL_INSPECT_MATERIAL_SHADER):
        validate_material_shader(params, inspection=tool_name == TOOL_INSPECT_MATERIAL_SHADER)
    if tool_name in (TOOL_SCULPT_MESH, TOOL_INSPECT_SCULPT_STATE):
        validate_sculpt(params, inspection=tool_name == TOOL_INSPECT_SCULPT_STATE)

    if tool_name in (TOOL_SCULPT_ORGANIC_ANATOMY, TOOL_OPTIMIZE_MESH_SILHOUETTE, TOOL_SCULPT_MESH):
        if "brush_type" in sanitized:
            sanitized["brush_type"] = str(sanitized["brush_type"]).strip().upper()


    # Check required fields
    for req_field in required:
        if req_field not in params:
            raise ValueError(f"Missing required parameter '{req_field}' for tool '{tool_name}'")

    # Validate each property
    for key, val in params.items():
        if key in ("approval_token", "request_id", "session_id", "correlation_id"):
            sanitized[key] = val
            continue

        if key not in properties:
            raise ValueError(f"Unknown parameter '{key}' for tool '{tool_name}'. Allowed: {list(properties.keys())}")

        prop_spec = properties[key]
        prop_type = prop_spec.get("type")

        # Type checks
        if prop_type == "boolean":
            if not isinstance(val, bool):
                raise ValueError(f"Parameter '{key}' must be a boolean, got {type(val).__name__}")
        elif prop_type == "number":
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"Parameter '{key}' must be a number, got {type(val).__name__}")
            if not math.isfinite(val):
                raise ValueError(f"Parameter '{key}' must be a finite number, got {val}")
            min_val = prop_spec.get("minimum")
            max_val = prop_spec.get("maximum")
            if min_val is not None and val < min_val:
                raise ValueError(f"Parameter '{key}' must be >= {min_val}, got {val}")
            if max_val is not None and val > max_val:
                raise ValueError(f"Parameter '{key}' must be <= {max_val}, got {val}")
        elif prop_type == "integer":
            if not isinstance(val, int) or isinstance(val, bool):
                raise ValueError(f"Parameter '{key}' must be an integer, got {type(val).__name__}")
            min_val = prop_spec.get("minimum")
            max_val = prop_spec.get("maximum")
            if min_val is not None and val < min_val:
                raise ValueError(f"Parameter '{key}' must be >= {min_val}, got {val}")
            if max_val is not None and val > max_val:
                raise ValueError(f"Parameter '{key}' must be <= {max_val}, got {val}")
        elif prop_type == "string":
            if not isinstance(val, str):
                raise ValueError(f"Parameter '{key}' must be a string, got {type(val).__name__}")
            if key in ("name", "target_name") and not val.strip():
                raise ValueError(f"Parameter '{key}' cannot be empty")
            pattern = prop_spec.get("pattern")
            if pattern:
                import re
                if not re.match(pattern, val):
                    raise ValueError(f"Parameter '{key}' does not match required pattern '{pattern}': {val}")
            enum_vals = prop_spec.get("enum")
            if enum_vals and val.lower() not in [e.lower() for e in enum_vals]:
                raise ValueError(f"Invalid value for '{key}': '{val}'. Allowed: {enum_vals}")
            if enum_vals:
                matched_enum = next((e for e in enum_vals if str(e).lower() == val.lower()), None)
                val = matched_enum if matched_enum is not None else val
        elif prop_type == "object":
            if not isinstance(val, dict):
                raise ValueError(f"Parameter '{key}' must be an object (dictionary), got {type(val).__name__}")
        elif prop_type == "array":
            if not isinstance(val, (list, tuple)):
                raise ValueError(f"Parameter '{key}' must be a list, got {type(val).__name__}")
            min_items = prop_spec.get("minItems")
            max_items = prop_spec.get("maxItems")
            if min_items is not None and len(val) < min_items:
                raise ValueError(f"Parameter '{key}' must contain at least {min_items} items, got {len(val)}")
            if max_items is not None and len(val) > max_items:
                raise ValueError(f"Parameter '{key}' must contain at most {max_items} items, got {len(val)}")
            item_spec = prop_spec.get("items", {})
            item_type = item_spec.get("type")
            item_min = item_spec.get("minimum")
            item_max = item_spec.get("maximum")
            for idx, item in enumerate(val):
                if item_type == "number":
                    if not isinstance(item, (int, float)) or isinstance(item, bool):
                        raise ValueError(f"Item {idx} in '{key}' must be a number, got {type(item).__name__}")
                    if not math.isfinite(item):
                        raise ValueError(f"Item {idx} in '{key}' must be a finite number, got {item}")
                    if item_min is not None and item < item_min:
                        raise ValueError(f"Item {idx} in '{key}' must be >= {item_min}, got {item}")
                    if item_max is not None and item > item_max:
                        raise ValueError(f"Item {idx} in '{key}' must be <= {item_max}, got {item}")
                elif item_type == "object":
                    if not isinstance(item, dict):
                        raise ValueError(f"Item {idx} in '{key}' must be an object (dictionary), got {type(item).__name__}")

        sanitized[key] = val

    if tool_name in (TOOL_CONFIGURE_MODIFIER, TOOL_EDIT_MODIFIER_STACK, TOOL_APPLY_MODIFIER) and "modifier_type" in sanitized:
        sanitized["modifier_type"] = sanitized["modifier_type"].upper()

    if tool_name == TOOL_CONFIGURE_MODELING_OBJECT and "space" in sanitized:
        sanitized["space"] = sanitized["space"].upper()

    if tool_name == TOOL_CONFIGURE_CURVE_GEOMETRY and "kind" in sanitized:
        sanitized["kind"] = sanitized["kind"].upper()

    # Primitive-specific parameter applicability check for create_primitive
    if tool_name == TOOL_CREATE_PRIMITIVE:
        prim_type = sanitized.get("primitive_type", "").lower()
        allowed_specific = PRIMITIVE_SPECIFIC_PARAMS.get(prim_type, set())
        for k in params.keys():
            if k in ALL_PRIMITIVE_SPECIFIC_PARAMS and k not in allowed_specific:
                raise ValueError(
                    f"Parameter '{k}' is not applicable for primitive type '{prim_type}'. "
                    f"Allowed primitive-specific parameters for '{prim_type}': "
                    f"{sorted(allowed_specific) if allowed_specific else 'None'}"
                )

    # Tool-specific validation for transform_object
    if tool_name == TOOL_TRANSFORM_OBJECT:
        if not any(k in params for k in ("location", "rotation_euler", "scale")):
            raise ValueError(
                f"At least one transform property ('location', 'rotation_euler', 'scale') "
                f"must be provided for tool '{tool_name}'"
            )

    # Tool-specific validation for inspect_scene_data
    if tool_name == TOOL_INSPECT_SCENE_DATA:
        cat = sanitized.get("category", "").lower()
        validate_topology_options(sanitized, cat)
        if cat in OBJECT_SPECIFIC_INSPECT_CATEGORIES:
            target = sanitized.get("target_name")
            if not target or not str(target).strip():
                raise ValueError(f"Category '{cat}' requires a non-empty 'target_name' parameter.")

    # Tool-specific validation for execute_blender_code
    if tool_name == TOOL_EXECUTE_BLENDER_CODE:
        has_ops = "operations" in sanitized and sanitized["operations"]
        has_code = "code" in sanitized and sanitized["code"]
        if not has_ops and not has_code:
            raise ValueError("Either 'operations' (structured plan) or 'code' (restricted script) must be provided for 'execute_blender_code'.")

        # Rollback guarantee requirement: transactional must be True
        if sanitized.get("transactional") is False:
            raise ValueError(
                "Non-transactional execution is rejected. All modeling operations must guarantee safe rollback via 'transactional': True."
            )

        if has_ops:
            ops = sanitized["operations"]
            if not isinstance(ops, list) or len(ops) == 0:
                raise ValueError("Parameter 'operations' must be a non-empty list of operation specifications.")
            for idx, op in enumerate(ops):
                if not isinstance(op, dict):
                    raise ValueError(f"Operation {idx} in 'operations' must be an object (dictionary).")
                action = str(op.get("action", "")).strip().lower()
                if not action or action not in ALLOWED_MODELING_ACTIONS:
                    raise ValueError(
                        f"Operation {idx} action '{action}' is invalid. Allowed actions: {list(ALLOWED_MODELING_ACTIONS)}"
                    )
                op_target = op.get("target")
                op_params = op.get("params", {})
                if not isinstance(op_params, dict):
                    raise ValueError(f"Operation {idx} 'params' must be a dictionary.")

                # Action-specific target/param validation
                if action in (
                    "add_modifier", "modify_modifier", "remove_modifier", "set_shade_mode",
                    "subdivide_mesh", "assign_material", "parent_object", "join_objects",
                    "manage_keyframe", "insert_keyframe", "delete_keyframe",
                    "configure_geometry_nodes", "inspect_geometry_nodes",
                    "duplicate_object", "duplicate", "rename_object", "rename",
                ):
                    if not op_target or not str(op_target).strip():
                        raise ValueError(f"Operation {idx} '{action}' requires a non-empty 'target' object name.")

                if action == "add_modifier":
                    m_type = str(op_params.get("modifier_type") or op_params.get("type", "")).upper()
                    if not m_type or m_type not in ALLOWED_MODIFIER_TYPES:
                        raise ValueError(
                            f"Operation {idx} 'add_modifier' requires a valid modifier type. Allowed: {sorted(ALLOWED_MODIFIER_TYPES)}"
                        )
                elif action == "modify_modifier":
                    m_name = op_params.get("modifier_name") or op_params.get("name")
                    if not m_name or not str(m_name).strip():
                        raise ValueError(f"Operation {idx} 'modify_modifier' requires 'modifier_name'.")
                    if "properties" not in op_params or not isinstance(op_params["properties"], dict):
                        raise ValueError(f"Operation {idx} 'modify_modifier' requires a 'properties' dictionary.")
                elif action == "remove_modifier":
                    m_name = op_params.get("modifier_name") or op_params.get("name")
                    if not m_name or not str(m_name).strip():
                        raise ValueError(f"Operation {idx} 'remove_modifier' requires 'modifier_name'.")
                elif action == "set_shade_mode":
                    mode = str(op_params.get("shade_mode", "")).upper()
                    if mode not in ("SMOOTH", "FLAT"):
                        raise ValueError(f"Operation {idx} 'set_shade_mode' requires 'shade_mode' to be 'SMOOTH' or 'FLAT'.")
                elif action == "subdivide_mesh":
                    cuts = op_params.get("cuts", 1)
                    if not isinstance(cuts, int) or cuts < 1 or cuts > 10:
                        raise ValueError(f"Operation {idx} 'subdivide_mesh' parameter 'cuts' must be an integer between 1 and 10.")
                elif action == "create_material":
                    mat_name = op_params.get("material_name") or op_params.get("name")
                    if not mat_name or not str(mat_name).strip():
                        raise ValueError(f"Operation {idx} 'create_material' requires a non-empty 'material_name'.")
                elif action == "assign_material":
                    mat_name = op_params.get("material_name") or op_params.get("name")
                    if not mat_name or not str(mat_name).strip():
                        raise ValueError(f"Operation {idx} 'assign_material' requires a non-empty 'material_name'.")
                elif action == "parent_object":
                    p_name = op_params.get("parent_name") or op_params.get("parent")
                    if not p_name or not str(p_name).strip():
                        raise ValueError(f"Operation {idx} 'parent_object' requires 'parent_name'.")
                elif action == "join_objects":
                    objs_to_join = op_params.get("objects_to_join")
                    if not isinstance(objs_to_join, (list, tuple)) or not objs_to_join:
                        raise ValueError(f"Operation {idx} 'join_objects' requires a non-empty list 'objects_to_join'.")

        if has_code:
            code_str = sanitized["code"]
            validate_restricted_code_ast(code_str)

    # Tool-specific validation for create_material
    if tool_name == TOOL_CREATE_MATERIAL:
        m_name = str(sanitized.get("name", "")).strip()
        if not m_name:
            raise ValueError("Parameter 'name' cannot be empty for create_material.")

    # Tool-specific validation for assign_material
    if tool_name == TOOL_ASSIGN_MATERIAL:
        t_name = str(sanitized.get("target_name", "")).strip()
        if not t_name:
            raise ValueError("Parameter 'target_name' cannot be empty for assign_material.")
        mat_name = str(sanitized.get("material_name", "")).strip()
        if not mat_name:
            raise ValueError("Parameter 'material_name' cannot be empty for assign_material.")

    # Tool-specific validation for create_light and configure_light
    if tool_name in (TOOL_CREATE_LIGHT, TOOL_CONFIGURE_LIGHT):
        l_name = str(sanitized.get("name", "")).strip()
        if not l_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        for unsupp in ("render_engine", "engine", "cycles", "eevee", "compositing", "compositor", "light_linking", "light_groups", "shadow_baking"):
            if unsupp in sanitized:
                raise ValueError(f"Unsupported lighting property '{unsupp}'.")
        if "light_type" in sanitized:
            l_type = str(sanitized.get("light_type", "POINT")).strip().upper()
            if l_type not in ("POINT", "SUN", "SPOT", "AREA"):
                raise ValueError(f"Invalid light_type '{l_type}'. Allowed types: ['POINT', 'SUN', 'SPOT', 'AREA'].")
            sanitized["light_type"] = l_type
        if "energy" in sanitized:
            e = sanitized["energy"]
            if not isinstance(e, (int, float)) or isinstance(e, bool) or float(e) < 0.0:
                raise ValueError(f"Parameter 'energy' must be a non-negative number, got {e}.")
        if "color" in sanitized:
            c = sanitized["color"]
            if not isinstance(c, (list, tuple)) or len(c) != 3 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0.0 or v > 1.0 for v in c):
                raise ValueError(f"Parameter 'color' must be a 3-element list [r, g, b] with values in [0.0, 1.0].")
        if "spot_size" in sanitized:
            ss = sanitized["spot_size"]
            if not isinstance(ss, (int, float)) or isinstance(ss, bool) or float(ss) < 0.0 or float(ss) > 3.1416:
                raise ValueError(f"Parameter 'spot_size' must be between 0.0 and 3.1416, got {ss}.")
        if "spot_blend" in sanitized:
            sb = sanitized["spot_blend"]
            if not isinstance(sb, (int, float)) or isinstance(sb, bool) or float(sb) < 0.0 or float(sb) > 1.0:
                raise ValueError(f"Parameter 'spot_blend' must be between 0.0 and 1.0, got {sb}.")
        if "size" in sanitized:
            sz = sanitized["size"]
            if not isinstance(sz, (int, float)) or isinstance(sz, bool) or float(sz) < 0.0:
                raise ValueError(f"Parameter 'size' must be a non-negative number, got {sz}.")
        if "shape" in sanitized:
            shp = str(sanitized["shape"]).strip().upper()
            if shp not in ("SQUARE", "RECTANGLE", "DISK", "ELLIPSE"):
                raise ValueError(f"Invalid shape '{shp}'. Allowed AREA light shapes: ['SQUARE', 'RECTANGLE', 'DISK', 'ELLIPSE'].")
            sanitized["shape"] = shp
        if "size_y" in sanitized:
            sy = sanitized["size_y"]
            if not isinstance(sy, (int, float)) or isinstance(sy, bool) or float(sy) < 0.0:
                raise ValueError(f"Parameter 'size_y' must be a non-negative number, got {sy}.")
        if "diffuse_factor" in sanitized:
            df = sanitized["diffuse_factor"]
            if not isinstance(df, (int, float)) or isinstance(df, bool) or float(df) < 0.0:
                raise ValueError(f"Parameter 'diffuse_factor' must be a non-negative number, got {df}.")
        if "specular_factor" in sanitized:
            sf = sanitized["specular_factor"]
            if not isinstance(sf, (int, float)) or isinstance(sf, bool) or float(sf) < 0.0:
                raise ValueError(f"Parameter 'specular_factor' must be a non-negative number, got {sf}.")
        if "volume_factor" in sanitized:
            vf = sanitized["volume_factor"]
            if not isinstance(vf, (int, float)) or isinstance(vf, bool) or float(vf) < 0.0:
                raise ValueError(f"Parameter 'volume_factor' must be a non-negative number, got {vf}.")
        if "use_shadow" in sanitized:
            ush = sanitized["use_shadow"]
            if not isinstance(ush, bool):
                raise ValueError(f"Parameter 'use_shadow' must be a boolean, got {ush}.")
        if "shadow_soft_size" in sanitized:
            sss = sanitized["shadow_soft_size"]
            if not isinstance(sss, (int, float)) or isinstance(sss, bool) or float(sss) < 0.0:
                raise ValueError(f"Parameter 'shadow_soft_size' must be a non-negative number, got {sss}.")
        if "shadow_buffer_clip_start" in sanitized:
            sbcs = sanitized["shadow_buffer_clip_start"]
            if not isinstance(sbcs, (int, float)) or isinstance(sbcs, bool) or float(sbcs) < 0.0001:
                raise ValueError(f"Parameter 'shadow_buffer_clip_start' must be a positive number (>= 0.0001), got {sbcs}.")

    if tool_name == TOOL_CONFIGURE_WORLD:
        for unsupp in ("render_engine", "engine", "cycles", "eevee", "compositing", "compositor", "light_linking"):
            if unsupp in sanitized:
                raise ValueError(f"Unsupported world property '{unsupp}'.")
        if "color" in sanitized:
            c = sanitized["color"]
            if not isinstance(c, (list, tuple)) or len(c) != 3 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0.0 or v > 1.0 for v in c):
                raise ValueError(f"Parameter 'color' must be a 3-element list [r, g, b] with values in [0.0, 1.0].")
        if "strength" in sanitized:
            s = sanitized["strength"]
            if not isinstance(s, (int, float)) or isinstance(s, bool) or float(s) < 0.0:
                raise ValueError(f"Parameter 'strength' must be a non-negative number, got {s}.")
        if "environment_image" in sanitized and "sky_type" in sanitized:
            raise ValueError("Cannot specify both 'environment_image' and 'sky_type' simultaneously.")
        if "sky_type" in sanitized:
            st = str(sanitized["sky_type"]).strip().upper()
            allowed_sky_types = {"MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "PREETHAM", "HOSEK_WILKIE", "NISHITA"}
            if st not in allowed_sky_types:
                raise ValueError(f"Invalid sky_type '{st}'. Allowed values: {sorted(list(allowed_sky_types))}.")
            sanitized["sky_type"] = "MULTIPLE_SCATTERING" if st == "NISHITA" else st
        if "sun_disc" in sanitized:
            sd = sanitized["sun_disc"]
            if not isinstance(sd, bool):
                raise ValueError(f"Parameter 'sun_disc' must be a boolean, got {sd}.")
        if "sun_size" in sanitized:
            ss = sanitized["sun_size"]
            if not isinstance(ss, (int, float)) or isinstance(ss, bool) or float(ss) < 0.0 or float(ss) > 1.5707964:
                raise ValueError(f"Parameter 'sun_size' must be between 0.0 and 1.5708 radians, got {ss}.")
        if "sun_intensity" in sanitized:
            si = sanitized["sun_intensity"]
            if not isinstance(si, (int, float)) or isinstance(si, bool) or float(si) < 0.0:
                raise ValueError(f"Parameter 'sun_intensity' must be non-negative, got {si}.")
        if "sun_elevation" in sanitized:
            se = sanitized["sun_elevation"]
            if not isinstance(se, (int, float)) or isinstance(se, bool) or float(se) < -1.5707964 or float(se) > 1.5707964:
                raise ValueError(f"Parameter 'sun_elevation' must be between -1.5708 and 1.5708 radians, got {se}.")
        if "sun_rotation" in sanitized:
            sr = sanitized["sun_rotation"]
            if not isinstance(sr, (int, float)) or isinstance(sr, bool) or float(sr) < -6.2831854 or float(sr) > 6.2831854:
                raise ValueError(f"Parameter 'sun_rotation' must be between -6.2832 and 6.2832 radians, got {sr}.")
        if "altitude" in sanitized:
            alt = sanitized["altitude"]
            if not isinstance(alt, (int, float)) or isinstance(alt, bool) or float(alt) < 0.0 or float(alt) > 100000.0:
                raise ValueError(f"Parameter 'altitude' must be between 0.0 and 100000.0 meters, got {alt}.")
        for d_prop in ("air_density", "aerosol_density", "ozone_density"):
            if d_prop in sanitized:
                dv = sanitized[d_prop]
                if not isinstance(dv, (int, float)) or isinstance(dv, bool) or float(dv) < 0.0 or float(dv) > 1000.0:
                    raise ValueError(f"Parameter '{d_prop}' must be between 0.0 and 1000.0, got {dv}.")
        if "turbidity" in sanitized:
            tb = sanitized["turbidity"]
            if not isinstance(tb, (int, float)) or isinstance(tb, bool) or float(tb) < 1.0 or float(tb) > 10.0:
                raise ValueError(f"Parameter 'turbidity' must be between 1.0 and 10.0, got {tb}.")
        if "ground_albedo" in sanitized:
            ga = sanitized["ground_albedo"]
            if not isinstance(ga, (int, float)) or isinstance(ga, bool) or float(ga) < 0.0 or float(ga) > 1.0:
                raise ValueError(f"Parameter 'ground_albedo' must be between 0.0 and 1.0, got {ga}.")
        if "environment_rotation" in sanitized:
            er = sanitized["environment_rotation"]
            if isinstance(er, (int, float)) and not isinstance(er, bool):
                pass
            elif isinstance(er, (list, tuple)) and len(er) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in er):
                pass
            else:
                raise ValueError("Parameter 'environment_rotation' must be a number (Z-axis radians) or a 3-element list [rx, ry, rz] in radians.")

    # Tool-specific validation for capture_viewport
    if tool_name == TOOL_CAPTURE_VIEWPORT:
        mode = str(sanitized.get("mode", "VIEWPORT")).strip().upper()
        if mode not in ("VIEWPORT", "CAMERA"):
            raise ValueError(f"Invalid capture mode '{mode}'. Allowed modes: ['VIEWPORT', 'CAMERA'].")
        sanitized["mode"] = mode
        view = str(sanitized.get("view", "CURRENT")).strip().upper()
        if view not in ("CURRENT", "FRONT", "SIDE", "TOP", "PERSPECTIVE"):
            raise ValueError(f"Invalid view '{view}'. Allowed views: ['CURRENT', 'FRONT', 'SIDE', 'TOP', 'PERSPECTIVE'].")
        sanitized["view"] = view

    # Tool-specific validation for resolve_pending_approval
    if tool_name == TOOL_RESOLVE_PENDING_APPROVAL:
        for field_name in ("task_id", "nonce", "param_hash"):
            val_str = str(sanitized.get(field_name, "")).strip()
            if not val_str:
                raise ValueError(f"Parameter '{field_name}' cannot be empty for resolve_pending_approval.")
    # Tool-specific validation for create_camera, configure_camera, edit_camera
    if tool_name in (TOOL_CREATE_CAMERA, TOOL_CONFIGURE_CAMERA, TOOL_EDIT_CAMERA):
        c_name = str(sanitized.get("name", "")).strip()
        if not c_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        for unsupp in ("stereoscopy", "stereo", "multi_view", "velocity", "fisheye_polynomial", "motion_blur"):
            if unsupp in sanitized:
                raise ValueError(f"Unsupported camera property '{unsupp}'.")
        c_type = sanitized.get("camera_type", sanitized.get("type"))
        if c_type is not None:
            c_type_str = str(c_type).strip().upper()
            if c_type_str not in ("PERSP", "ORTHO", "PANO"):
                raise ValueError(f"Invalid camera type '{c_type}'. Allowed types: ['PERSP', 'ORTHO', 'PANO'].")
            sanitized["camera_type"] = c_type_str
            sanitized["type"] = c_type_str
        focal = sanitized.get("lens", sanitized.get("focal_length"))
        if focal is not None:
            if not isinstance(focal, (int, float)) or isinstance(focal, bool) or float(focal) <= 0.0 or float(focal) > 5000.0:
                raise ValueError(f"Parameter 'focal_length' must be a positive number in [1.0, 5000.0], got {focal}.")
        ortho_scale = sanitized.get("ortho_scale")
        if ortho_scale is not None:
            if not isinstance(ortho_scale, (int, float)) or isinstance(ortho_scale, bool) or float(ortho_scale) <= 0.0:
                raise ValueError(f"Parameter 'ortho_scale' must be a positive number, got {ortho_scale}.")
        clip_start = sanitized.get("clip_start")
        clip_end = sanitized.get("clip_end")
        if clip_start is not None:
            if not isinstance(clip_start, (int, float)) or isinstance(clip_start, bool) or float(clip_start) <= 0.0:
                raise ValueError(f"Parameter 'clip_start' must be positive, got {clip_start}.")
        if clip_end is not None:
            if not isinstance(clip_end, (int, float)) or isinstance(clip_end, bool) or float(clip_end) <= 0.0:
                raise ValueError(f"Parameter 'clip_end' must be positive, got {clip_end}.")
        if clip_start is not None and clip_end is not None and float(clip_start) >= float(clip_end):
            raise ValueError(f"Parameter 'clip_start' ({clip_start}) must be strictly less than 'clip_end' ({clip_end}).")
        sensor_fit = sanitized.get("sensor_fit")
        if sensor_fit is not None:
            s_fit = str(sensor_fit).strip().upper()
            if s_fit not in ("AUTO", "HORIZONTAL", "VERTICAL"):
                raise ValueError(f"Invalid sensor_fit '{sensor_fit}'. Allowed: ['AUTO', 'HORIZONTAL', 'VERTICAL'].")
            sanitized["sensor_fit"] = s_fit
        dof = sanitized.get("dof")
        if dof is not None:
            if not isinstance(dof, dict):
                raise ValueError("Parameter 'dof' must be an object/dict.")
            if "aperture_fstop" in dof:
                fstop = dof["aperture_fstop"]
                if not isinstance(fstop, (int, float)) or isinstance(fstop, bool) or float(fstop) <= 0.0:
                    raise ValueError(f"DOF aperture_fstop must be positive, got {fstop}.")
            if "focus_distance" in dof:
                fdist = dof["focus_distance"]
                if not isinstance(fdist, (int, float)) or isinstance(fdist, bool) or float(fdist) <= 0.0:
                    raise ValueError(f"DOF focus_distance must be positive, got {fdist}.")
            if "focus_object" in dof:
                fobj = dof["focus_object"]
                if fobj is not None:
                    if not isinstance(fobj, str):
                        raise ValueError(f"DOF 'focus_object' must be a string or null, got {type(fobj).__name__}.")
                    if fobj.strip() and fobj.strip() == c_name:
                        raise ValueError("Camera cannot focus on itself.")
        fstop = sanitized.get("aperture_fstop")
        if fstop is not None:
            if not isinstance(fstop, (int, float)) or isinstance(fstop, bool) or float(fstop) <= 0.0:
                raise ValueError(f"Parameter 'aperture_fstop' must be positive, got {fstop}.")
        fdist = sanitized.get("focus_distance")
        if fdist is not None:
            if not isinstance(fdist, (int, float)) or isinstance(fdist, bool) or float(fdist) <= 0.0:
                raise ValueError(f"Parameter 'focus_distance' must be positive, got {fdist}.")
        focus_object = sanitized.get("focus_object")
        if focus_object is not None:
            if not isinstance(focus_object, str):
                raise ValueError(f"Parameter 'focus_object' must be a string or null, got {type(focus_object).__name__}.")
            if focus_object.strip() and focus_object.strip() == c_name:
                raise ValueError("Camera cannot focus on itself.")
        track_to_object = sanitized.get("track_to_object")
        if track_to_object is not None:
            if not isinstance(track_to_object, str):
                raise ValueError(f"Parameter 'track_to_object' must be a string or null, got {type(track_to_object).__name__}.")
            if track_to_object.strip() and track_to_object.strip() == c_name:
                raise ValueError("Camera cannot track itself.")
        show_composition_thirds = sanitized.get("show_composition_thirds")
        if show_composition_thirds is not None:
            if not isinstance(show_composition_thirds, bool):
                raise ValueError(f"Parameter 'show_composition_thirds' must be a boolean, got {type(show_composition_thirds).__name__}.")

    # Tool-specific validation for switch_camera
    if tool_name == TOOL_SWITCH_CAMERA:
        c_name = str(sanitized.get("camera_name", sanitized.get("name", ""))).strip()
        if not c_name:
            raise ValueError(f"Parameter 'camera_name' cannot be empty for {tool_name}.")
        sanitized["camera_name"] = c_name

    # Tool-specific validation for configure_render_settings
    if tool_name == TOOL_CONFIGURE_RENDER_SETTINGS:
        ft = sanitized.get("film_transparent")
        if ft is not None and not isinstance(ft, bool):
            raise ValueError(f"Parameter 'film_transparent' must be a boolean, got {type(ft).__name__}.")

        cm = sanitized.get("color_management")
        if cm is not None and not isinstance(cm, dict):
            raise ValueError("Parameter 'color_management' must be a dict/object.")

        vt = sanitized.get("view_transform")
        if vt is None and isinstance(cm, dict):
            vt = cm.get("view_transform")
        if vt is not None:
            if not isinstance(vt, str):
                raise ValueError("Parameter 'view_transform' must be a string.")
            allowed_vt = ("Standard", "ACES 1.3", "ACES 2.0", "Khronos PBR Neutral", "AgX", "Filmic", "Filmic Log", "False Color", "Raw")
            vt_map = {item.lower(): item for item in allowed_vt}
            if vt.lower() not in vt_map:
                raise ValueError(f"Invalid view_transform '{vt}'. Allowed: {list(allowed_vt)}.")
            canonical_vt = vt_map[vt.lower()]
            sanitized["view_transform"] = canonical_vt
            if isinstance(cm, dict) and "view_transform" in cm:
                cm["view_transform"] = canonical_vt

        look = sanitized.get("look")
        if look is None and isinstance(cm, dict):
            look = cm.get("look")
        if look is not None:
            if not isinstance(look, str):
                raise ValueError("Parameter 'look' must be a string.")
            allowed_look = (
                "None", "Very Low Contrast", "Low Contrast", "Medium Low Contrast", "Medium Contrast", "Medium High Contrast", "High Contrast", "Very High Contrast",
                "AgX - Very Low Contrast", "AgX - Low Contrast", "AgX - Medium Low Contrast", "AgX - Base Contrast", "AgX - Medium High Contrast", "AgX - High Contrast", "AgX - Very High Contrast", "AgX - Punchy", "AgX - Greyscale", "Punchy"
            )
            look_map = {item.lower(): item for item in allowed_look}
            if look.lower() not in look_map:
                raise ValueError(f"Invalid look '{look}'. Allowed: {list(allowed_look)}.")
            canonical_look = look_map[look.lower()]
            sanitized["look"] = canonical_look
            if isinstance(cm, dict) and "look" in cm:
                cm["look"] = canonical_look

        exp = sanitized.get("exposure")
        if exp is None and isinstance(cm, dict):
            exp = cm.get("exposure")
        if exp is not None:
            if not isinstance(exp, (int, float)) or isinstance(exp, bool) or not math.isfinite(exp) or exp < -32.0 or exp > 32.0:
                raise ValueError(f"Parameter 'exposure' must be a finite number in [-32.0, 32.0], got {exp}.")

        gamma = sanitized.get("gamma")
        if gamma is None and isinstance(cm, dict):
            gamma = cm.get("gamma")
        if gamma is not None:
            if not isinstance(gamma, (int, float)) or isinstance(gamma, bool) or not math.isfinite(gamma) or gamma < -32.0 or gamma > 32.0:
                raise ValueError(f"Parameter 'gamma' must be a finite number in [-32.0, 32.0], got {gamma}.")
            sanitized["gamma"] = float(gamma)
            if isinstance(cm, dict):
                cm["gamma"] = float(gamma)

        # Output format image settings
        c_mode = sanitized.get("color_mode")
        if c_mode is not None:
            if not isinstance(c_mode, str):
                raise ValueError("Parameter 'color_mode' must be a string.")
            allowed_c_mode = ("BW", "RGB", "RGBA")
            cm_map = {item.lower(): item for item in allowed_c_mode}
            if c_mode.lower() not in cm_map:
                raise ValueError(f"Invalid color_mode '{c_mode}'. Allowed: {list(allowed_c_mode)}.")
            sanitized["color_mode"] = cm_map[c_mode.lower()]

        c_depth = sanitized.get("color_depth")
        if c_depth is not None:
            c_depth_str = str(c_depth).strip()
            allowed_c_depth = ("8", "16", "32")
            if c_depth_str not in allowed_c_depth:
                raise ValueError(f"Invalid color_depth '{c_depth}'. Allowed: {list(allowed_c_depth)}.")
            sanitized["color_depth"] = c_depth_str

        comp = sanitized.get("compression")
        if comp is not None:
            if not isinstance(comp, int) or isinstance(comp, bool) or comp < 0 or comp > 100:
                raise ValueError(f"Parameter 'compression' must be an integer between 0 and 100, got {comp}.")

        qual = sanitized.get("quality")
        if qual is not None:
            if not isinstance(qual, int) or isinstance(qual, bool) or qual < 1 or qual > 100:
                raise ValueError(f"Parameter 'quality' must be an integer between 1 and 100, got {qual}.")

        cyc = sanitized.get("cycles")
        if cyc is not None and not isinstance(cyc, dict):
            raise ValueError("Parameter 'cycles' must be a dict/object.")

        ud = sanitized.get("use_denoising")
        if ud is None and isinstance(cyc, dict):
            ud = cyc.get("use_denoising")
        if ud is not None and not isinstance(ud, bool):
            raise ValueError(f"Parameter 'use_denoising' must be a boolean, got {type(ud).__name__}.")

        dn = sanitized.get("denoiser")
        if dn is None and isinstance(cyc, dict):
            dn = cyc.get("denoiser")
        if dn is not None:
            if not isinstance(dn, str):
                raise ValueError("Parameter 'denoiser' must be a string.")
            allowed_dn = ("OPENIMAGEDENOISE", "OPTIX")
            dn_map = {item.lower(): item for item in allowed_dn}
            if dn.lower() not in dn_map:
                raise ValueError(f"Invalid denoiser '{dn}'. Allowed: ['OPENIMAGEDENOISE', 'OPTIX'].")
            canonical_dn = dn_map[dn.lower()]
            sanitized["denoiser"] = canonical_dn
            if isinstance(cyc, dict) and "denoiser" in cyc:
                cyc["denoiser"] = canonical_dn

        for b_name in ("max_bounces", "diffuse_bounces", "glossy_bounces", "transmission_bounces", "volume_bounces", "transparent_max_bounces"):
            b_val = sanitized.get(b_name)
            if b_val is None and isinstance(cyc, dict):
                b_val = cyc.get(b_name)
            if b_val is not None:
                if not isinstance(b_val, int) or isinstance(b_val, bool) or b_val < 0 or b_val > 1024:
                    raise ValueError(f"Parameter '{b_name}' must be an integer between 0 and 1024, got {b_val}.")

        t_limit = sanitized.get("time_limit")
        if t_limit is None and isinstance(cyc, dict):
            t_limit = cyc.get("time_limit")
        if t_limit is not None:
            if not isinstance(t_limit, (int, float)) or isinstance(t_limit, bool) or not math.isfinite(t_limit) or t_limit < 0.0:
                raise ValueError(f"Parameter 'time_limit' must be a non-negative finite number, got {t_limit}.")
            sanitized["time_limit"] = float(t_limit)
            if isinstance(cyc, dict):
                cyc["time_limit"] = float(t_limit)

        uas = sanitized.get("use_adaptive_sampling")
        if uas is None and isinstance(cyc, dict):
            uas = cyc.get("use_adaptive_sampling")
        if uas is not None:
            if not isinstance(uas, bool):
                raise ValueError(f"Parameter 'use_adaptive_sampling' must be a boolean, got {type(uas).__name__}.")
            sanitized["use_adaptive_sampling"] = uas
            if isinstance(cyc, dict):
                cyc["use_adaptive_sampling"] = uas

        athresh = sanitized.get("adaptive_threshold")
        if athresh is None and isinstance(cyc, dict):
            athresh = cyc.get("adaptive_threshold")
        if athresh is not None:
            if not isinstance(athresh, (int, float)) or isinstance(athresh, bool) or not math.isfinite(athresh) or athresh < 0.0 or athresh > 1.0:
                raise ValueError(f"Parameter 'adaptive_threshold' must be a finite number between 0.0 and 1.0, got {athresh}.")
            sanitized["adaptive_threshold"] = float(athresh)
            if isinstance(cyc, dict):
                cyc["adaptive_threshold"] = float(athresh)

        amin = sanitized.get("adaptive_min_samples")
        if amin is None and isinstance(cyc, dict):
            amin = cyc.get("adaptive_min_samples")
        if amin is not None:
            if not isinstance(amin, int) or isinstance(amin, bool) or amin < 0 or amin > 65536:
                raise ValueError(f"Parameter 'adaptive_min_samples' must be an integer between 0 and 65536, got {amin}.")
            sanitized["adaptive_min_samples"] = amin
            if isinstance(cyc, dict):
                cyc["adaptive_min_samples"] = amin

    # Tool-specific validation for delete_object
    if tool_name == TOOL_DELETE_OBJECT:
        o_name = str(sanitized.get("name", "")).strip()
        if not o_name:
            raise ValueError("Parameter 'name' cannot be empty for delete_object.")

    # Tool-specific validation for render_scene
    if tool_name == TOOL_RENDER_SCENE:
        r_mode = sanitized.get("render_mode", "still")
        if r_mode not in ("still", "animation"):
            raise ValueError(f"Parameter 'render_mode' must be 'still' or 'animation', got '{r_mode}'.")
        if r_mode == "animation":
            f_start = sanitized.get("frame_start")
            f_end = sanitized.get("frame_end")
            if f_start is not None and f_end is not None:
                if int(f_start) > int(f_end):
                    raise ValueError(f"frame_start ({f_start}) cannot exceed frame_end ({f_end}) for animation render.")

    # Tool-specific validation for extrude_mesh / extrude_faces
    if tool_name in (TOOL_EXTRUDE_MESH, TOOL_EXTRUDE_FACES):
        e_name = str(sanitized.get("name", "")).strip()
        if not e_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        dist = sanitized.get("distance", 1.0)
        if not isinstance(dist, (int, float)) or isinstance(dist, bool) or not math.isfinite(dist):
            raise ValueError(f"Parameter 'distance' must be a finite number, got {dist}.")
        direction = sanitized.get("direction")
        if direction is not None:
            if not isinstance(direction, (list, tuple)) or len(direction) != 3 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in direction
            ):
                raise ValueError(f"Parameter 'direction' must be a 3-element finite numeric list [x, y, z], got {direction}.")
        faces = sanitized.get("faces")
        if faces is not None:
            if isinstance(faces, str):
                if faces.lower() not in ("selected", "all"):
                    raise ValueError(f"Parameter 'faces' string must be 'selected' or 'all', got '{faces}'.")
            elif isinstance(faces, (list, tuple)):
                if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in faces):
                    raise ValueError("Parameter 'faces' list must contain non-negative integers.")
            else:
                raise ValueError(f"Parameter 'faces' must be 'selected', 'all', or a list of face indices, got {type(faces).__name__}.")

    # Tool-specific validation for inset_mesh / inset_faces
    if tool_name in (TOOL_INSET_MESH, TOOL_INSET_FACES):
        i_name = str(sanitized.get("name", "")).strip()
        if not i_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        thickness = sanitized.get("thickness", 0.1)
        if not isinstance(thickness, (int, float)) or isinstance(thickness, bool) or not math.isfinite(thickness) or thickness < 0:
            raise ValueError(f"Parameter 'thickness' must be a non-negative finite number, got {thickness}.")
        depth = sanitized.get("depth", 0.0)
        if not isinstance(depth, (int, float)) or isinstance(depth, bool) or not math.isfinite(depth):
            raise ValueError(f"Parameter 'depth' must be a finite number, got {depth}.")
        faces = sanitized.get("faces")
        if faces is not None:
            if isinstance(faces, str):
                if faces.lower() not in ("selected", "all"):
                    raise ValueError(f"Parameter 'faces' string must be 'selected' or 'all', got '{faces}'.")
            elif isinstance(faces, (list, tuple)):
                if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in faces):
                    raise ValueError("Parameter 'faces' list must contain non-negative integers.")
            else:
                raise ValueError(f"Parameter 'faces' must be 'selected', 'all', or a list of face indices, got {type(faces).__name__}.")

    if tool_name in (TOOL_EXTRUDE_MESH, TOOL_EXTRUDE_FACES, TOOL_INSET_MESH, TOOL_INSET_FACES):
        from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
        if isinstance(sanitized.get("faces"), (list, tuple)) and "expected_snapshot_id" not in sanitized:
            raise ValueError("Explicit face indices require expected_snapshot_id")
        if "expected_snapshot_id" in sanitized:
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for bevel_mesh / bevel_edges
    if tool_name in (TOOL_BEVEL_MESH, TOOL_BEVEL_EDGES):
        b_name = str(sanitized.get("name", "")).strip()
        if not b_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        offset = sanitized.get("offset", 0.1)
        if not isinstance(offset, (int, float)) or isinstance(offset, bool) or not math.isfinite(offset) or offset < 0:
            raise ValueError(f"Parameter 'offset' must be a non-negative finite number, got {offset}.")
        segments = sanitized.get("segments", 1)
        if not isinstance(segments, int) or isinstance(segments, bool) or segments < 1 or segments > 64:
            raise ValueError(f"Parameter 'segments' must be an integer between 1 and 64, got {segments}.")
        profile = sanitized.get("profile", 0.5)
        if not isinstance(profile, (int, float)) or isinstance(profile, bool) or not math.isfinite(profile) or not (0.0 <= profile <= 1.0):
            raise ValueError(f"Parameter 'profile' must be a finite number between 0.0 and 1.0, got {profile}.")
        affect = str(sanitized.get("affect", "EDGES")).upper()
        if affect not in ("EDGES", "VERTICES"):
            raise ValueError(f"Parameter 'affect' must be 'EDGES' or 'VERTICES', got '{affect}'.")
        sanitized["affect"] = affect
        from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
        for elem_key in ("edges", "vertices"):
            if isinstance(sanitized.get(elem_key), (list, tuple)):
                if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in sanitized[elem_key]):
                    raise ValueError(f"Parameter '{elem_key}' list must contain non-negative integers.")
                if "expected_snapshot_id" not in sanitized:
                    raise ValueError(f"Explicit {elem_key} indices require expected_snapshot_id")
        if "expected_snapshot_id" in sanitized:
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for split_mesh / knife_mesh / bisect_mesh
    if tool_name in (TOOL_SPLIT_MESH, TOOL_KNIFE_MESH, TOOL_BISECT_MESH):
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        method = str(sanitized.get("method", "BISECT")).upper()
        if method not in ("BISECT", "SUBDIVIDE", "SPLIT_EDGES"):
            raise ValueError(f"Parameter 'method' must be 'BISECT', 'SUBDIVIDE', or 'SPLIT_EDGES', got '{method}'.")
        sanitized["method"] = method
        if method == "BISECT":
            for vec_key, default_vec in (("plane_co", [0.0, 0.0, 0.0]), ("plane_no", [0.0, 0.0, 1.0])):
                v = sanitized.get(vec_key, default_vec)
                if not isinstance(v, (list, tuple)) or len(v) != 3 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v):
                    raise ValueError(f"Parameter '{vec_key}' must be a 3-element finite numeric list [x, y, z], got {v}.")
                if vec_key == "plane_no" and sum(x*x for x in v) <= 1e-12:
                    raise ValueError("Parameter 'plane_no' cannot be a zero vector.")
        elif method == "SUBDIVIDE":
            cuts = sanitized.get("cuts", 1)
            if not isinstance(cuts, int) or isinstance(cuts, bool) or cuts < 1 or cuts > 16:
                raise ValueError(f"Parameter 'cuts' must be an integer between 1 and 16, got {cuts}.")
        from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
        if isinstance(sanitized.get("edges"), (list, tuple)):
            if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in sanitized["edges"]):
                raise ValueError("Parameter 'edges' list must contain non-negative integers.")
            if "expected_snapshot_id" not in sanitized:
                raise ValueError("Explicit edge indices require expected_snapshot_id")
        if "expected_snapshot_id" in sanitized:
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for dissolve_mesh
    if tool_name == TOOL_DISSOLVE_MESH:
        d_name = str(sanitized.get("name", "")).strip()
        if not d_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        dtype = str(sanitized.get("dissolve_type", "EDGES")).upper()
        if dtype not in ("VERTICES", "EDGES", "FACES"):
            raise ValueError(f"Parameter 'dissolve_type' must be 'VERTICES', 'EDGES', or 'FACES', got '{dtype}'.")
        sanitized["dissolve_type"] = dtype
        from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
        if isinstance(sanitized.get("indices"), (list, tuple)):
            if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in sanitized["indices"]):
                raise ValueError("Parameter 'indices' list must contain non-negative integers.")
            if "expected_snapshot_id" not in sanitized:
                raise ValueError("Explicit indices require expected_snapshot_id")
        if "expected_snapshot_id" in sanitized:
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for merge_mesh
    if tool_name == TOOL_MERGE_MESH:
        m_name = str(sanitized.get("name", "")).strip()
        if not m_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        mode = str(sanitized.get("mode", "CENTER")).upper()
        if mode not in ("CENTER", "COLLAPSE", "CURSOR", "DISTANCE"):
            raise ValueError(f"Parameter 'mode' must be 'CENTER', 'COLLAPSE', 'CURSOR', or 'DISTANCE', got '{mode}'.")
        sanitized["mode"] = mode
        if mode == "CURSOR":
            t_loc = sanitized.get("target_location")
            if not isinstance(t_loc, (list, tuple)) or len(t_loc) != 3 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in t_loc):
                raise ValueError(f"Parameter 'target_location' [x, y, z] is required for mode 'CURSOR', got {t_loc}.")
        if mode == "DISTANCE":
            dist = sanitized.get("distance_threshold", 0.001)
            if not isinstance(dist, (int, float)) or isinstance(dist, bool) or not math.isfinite(dist) or dist < 0:
                raise ValueError(f"Parameter 'distance_threshold' must be a non-negative finite number, got {dist}.")
        from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
        if isinstance(sanitized.get("vertices"), (list, tuple)):
            if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in sanitized["vertices"]):
                raise ValueError("Parameter 'vertices' list must contain non-negative integers.")
            if "expected_snapshot_id" not in sanitized:
                raise ValueError("Explicit vertex indices require expected_snapshot_id")
        if "expected_snapshot_id" in sanitized:
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for recalculate_normals / align_normals
    if tool_name == TOOL_APPLY_MODIFIER:
        from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
        if "expected_snapshot_id" in sanitized:
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    if tool_name in (TOOL_RECALCULATE_NORMALS, TOOL_ALIGN_NORMALS):
        rn_name = str(sanitized.get("name", "")).strip()
        if not rn_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        action = str(sanitized.get("action", "RECALCULATE_OUTSIDE")).upper()
        if action not in ("RECALCULATE_OUTSIDE", "RECALCULATE_INSIDE", "FLIP"):
            raise ValueError(f"Parameter 'action' must be 'RECALCULATE_OUTSIDE', 'RECALCULATE_INSIDE', or 'FLIP', got '{action}'.")
        sanitized["action"] = action
        from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
        if isinstance(sanitized.get("faces"), (list, tuple)):
            if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in sanitized["faces"]):
                raise ValueError("Parameter 'faces' list must contain non-negative integers.")
            if "expected_snapshot_id" not in sanitized:
                raise ValueError("Explicit face indices require expected_snapshot_id")
        if "expected_snapshot_id" in sanitized:
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for uv_unwrap / unwrap_mesh
    if tool_name in (TOOL_UV_UNWRAP, TOOL_UNWRAP_MESH):
        if "expected_snapshot_id" in sanitized:
            from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
            validate_snapshot_id(sanitized["expected_snapshot_id"])
        u_name = str(sanitized.get("name", "")).strip()
        if not u_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        method = sanitized.get("method")
        if method is not None:
            if not isinstance(method, str) or method.upper() not in ("ANGLE_BASED", "CONFORMAL"):
                raise ValueError(f"Parameter 'method' must be 'ANGLE_BASED' or 'CONFORMAL', got {method}.")
            sanitized["method"] = method.upper()
        margin = sanitized.get("margin")
        if margin is not None:
            if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not math.isfinite(margin) or not (0.0 <= margin <= 1.0):
                raise ValueError(f"Parameter 'margin' must be a finite number between 0.0 and 1.0, got {margin}.")
        fill_holes = sanitized.get("fill_holes")
        if fill_holes is not None and not isinstance(fill_holes, bool):
            raise ValueError(f"Parameter 'fill_holes' must be a boolean, got {fill_holes}.")
        correct_aspect = sanitized.get("correct_aspect")
        if correct_aspect is not None and not isinstance(correct_aspect, bool):
            raise ValueError(f"Parameter 'correct_aspect' must be a boolean, got {correct_aspect}.")
        faces = sanitized.get("faces")
        if faces is not None:
            if isinstance(faces, str):
                if faces.lower() not in ("selected", "all"):
                    raise ValueError(f"Parameter 'faces' string must be 'selected' or 'all', got '{faces}'.")
            elif isinstance(faces, (list, tuple)):
                if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in faces):
                    raise ValueError("Parameter 'faces' list must contain non-negative integers.")
            else:
                raise ValueError(f"Parameter 'faces' must be 'selected', 'all', or a list of face indices, got {type(faces).__name__}.")

    # Tool-specific validation for uv_smart_project and aliases
    if tool_name in (TOOL_UV_SMART_PROJECT, TOOL_SMART_PROJECT, TOOL_SMART_UV_PROJECT, TOOL_UV_PROJECT):
        if "expected_snapshot_id" in sanitized:
            from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
            validate_snapshot_id(sanitized["expected_snapshot_id"])
        p_name = str(sanitized.get("name", "")).strip()
        if not p_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        angle_limit = sanitized.get("angle_limit")
        if angle_limit is not None:
            if not isinstance(angle_limit, (int, float)) or isinstance(angle_limit, bool) or not math.isfinite(angle_limit) or not (1.0 <= angle_limit <= 89.0):
                raise ValueError(f"Parameter 'angle_limit' must be a finite number between 1.0 and 89.0 degrees, got {angle_limit}.")
        island_margin = sanitized.get("island_margin")
        if island_margin is not None:
            if not isinstance(island_margin, (int, float)) or isinstance(island_margin, bool) or not math.isfinite(island_margin) or not (0.0 <= island_margin <= 1.0):
                raise ValueError(f"Parameter 'island_margin' must be a finite number between 0.0 and 1.0, got {island_margin}.")
        area_weight = sanitized.get("area_weight")
        if area_weight is not None:
            if not isinstance(area_weight, (int, float)) or isinstance(area_weight, bool) or not math.isfinite(area_weight) or not (0.0 <= area_weight <= 1.0):
                raise ValueError(f"Parameter 'area_weight' must be a finite number between 0.0 and 1.0, got {area_weight}.")
        correct_aspect = sanitized.get("correct_aspect")
        if correct_aspect is not None and not isinstance(correct_aspect, bool):
            raise ValueError(f"Parameter 'correct_aspect' must be a boolean, got {correct_aspect}.")
        scale_to_bounds = sanitized.get("scale_to_bounds")
        if scale_to_bounds is not None and not isinstance(scale_to_bounds, bool):
            raise ValueError(f"Parameter 'scale_to_bounds' must be a boolean, got {scale_to_bounds}.")
        faces = sanitized.get("faces")
        if faces is not None:
            if isinstance(faces, str):
                if faces.lower() not in ("selected", "all"):
                    raise ValueError(f"Parameter 'faces' string must be 'selected' or 'all', got '{faces}'.")
            elif isinstance(faces, (list, tuple)):
                if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in faces):
                    raise ValueError("Parameter 'faces' list must contain non-negative integers.")
            else:
                raise ValueError(f"Parameter 'faces' must be 'selected', 'all', or a list of face indices, got {type(faces).__name__}.")

    # Tool-specific validation for manage_uv_seams
    if tool_name == TOOL_MANAGE_UV_SEAMS:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for manage_uv_seams.")
        action = str(sanitized.get("action", "mark")).strip().lower()
        if action not in ("mark", "clear", "clear_all"):
            raise ValueError(f"Parameter 'action' must be 'mark', 'clear', or 'clear_all', got '{sanitized.get('action')}'.")
        sanitized["action"] = action
        if action in ("mark", "clear"):
            edges = sanitized.get("edges")
            if edges is None:
                raise ValueError(f"Parameter 'edges' is required for action '{action}'.")
            if not isinstance(edges, (list, tuple)):
                raise ValueError(f"Parameter 'edges' must be a list of integers, got {type(edges).__name__}.")
            if len(edges) == 0:
                raise ValueError("Parameter 'edges' list cannot be empty.")
            if not all(isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in edges):
                raise ValueError("Parameter 'edges' must contain non-negative integers.")
        if "expected_snapshot_id" in sanitized:
            from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for pack_uv_islands
    if tool_name == TOOL_PACK_UV_ISLANDS:
        p_name = str(sanitized.get("name", "")).strip()
        if not p_name:
            raise ValueError("Parameter 'name' cannot be empty for pack_uv_islands.")
        margin = sanitized.get("margin")
        if margin is not None:
            if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not math.isfinite(margin) or not (0.0 <= margin <= 1.0):
                raise ValueError(f"Parameter 'margin' must be a finite number between 0.0 and 1.0, got {margin}.")
        rotate = sanitized.get("rotate")
        if rotate is not None and not isinstance(rotate, bool):
            raise ValueError(f"Parameter 'rotate' must be a boolean, got {rotate}.")
        if "expected_snapshot_id" in sanitized:
            from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for manage_uv_layers
    if tool_name == TOOL_MANAGE_UV_LAYERS:
        l_name = str(sanitized.get("name", "")).strip()
        if not l_name:
            raise ValueError("Parameter 'name' cannot be empty for manage_uv_layers.")
        action = str(sanitized.get("action", "create")).strip().lower()
        if action not in ("create", "set_active", "rename", "remove"):
            raise ValueError(f"Parameter 'action' must be 'create', 'set_active', 'rename', or 'remove', got '{sanitized.get('action')}'.")
        sanitized["action"] = action
        layer_name = str(sanitized.get("layer_name", "")).strip()
        if not layer_name:
            raise ValueError("Parameter 'layer_name' cannot be empty for manage_uv_layers.")
        sanitized["layer_name"] = layer_name
        if action == "rename":
            new_name = str(sanitized.get("new_name", "")).strip()
            if not new_name:
                raise ValueError("Parameter 'new_name' is required when action is 'rename'.")
            sanitized["new_name"] = new_name
        if "expected_snapshot_id" in sanitized:
            from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for inspect_uv_mesh
    if tool_name == TOOL_INSPECT_UV_MESH:
        i_name = str(sanitized.get("name", "")).strip()
        if not i_name:
            raise ValueError("Parameter 'name' cannot be empty for inspect_uv_mesh.")
        detail_level = str(sanitized.get("detail_level", "summary")).strip().lower()
        if detail_level not in ("summary", "detailed"):
            raise ValueError(f"Parameter 'detail_level' must be 'summary' or 'detailed', got '{sanitized.get('detail_level')}'.")
        sanitized["detail_level"] = detail_level

    # Tool-specific validation for manage_keyframe and aliases
    if tool_name in (TOOL_MANAGE_KEYFRAME, TOOL_INSERT_KEYFRAME, TOOL_DELETE_KEYFRAME):
        k_name = str(sanitized.get("name", "")).strip()
        if not k_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        prop_path = str(sanitized.get("property_path", "")).strip().lower()
        if prop_path not in ("location", "rotation_euler", "scale"):
            raise ValueError(f"Parameter 'property_path' must be 'location', 'rotation_euler', or 'scale', got '{sanitized.get('property_path')}'.")
        sanitized["property_path"] = prop_path
        frame_val = sanitized.get("frame")
        if not isinstance(frame_val, (int, float)) or isinstance(frame_val, bool) or not math.isfinite(frame_val):
            raise ValueError(f"Parameter 'frame' must be a finite number, got {frame_val}.")
        act = str(sanitized.get("action", "insert")).strip().lower()
        if act not in ("insert", "delete"):
            raise ValueError(f"Parameter 'action' must be 'insert' or 'delete', got '{sanitized.get('action')}'.")
        sanitized["action"] = act
        idx_val = sanitized.get("index", -1)
        if not isinstance(idx_val, int) or isinstance(idx_val, bool) or idx_val < -1 or idx_val > 2:
            raise ValueError(f"Parameter 'index' must be an integer between -1 and 2, got {idx_val}.")

    # Tool-specific validation for configure_geometry_nodes and aliases
    if tool_name in (TOOL_CONFIGURE_GEOMETRY_NODES, TOOL_INSPECT_GEOMETRY_NODES):
        g_name = str(sanitized.get("name", "")).strip()
        if not g_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        act = str(sanitized.get("action", "inspect" if tool_name == TOOL_INSPECT_GEOMETRY_NODES else "inspect")).strip().lower()
        allowed_actions = (
            "inspect", "create", "assign_group", "add_node", "remove_node",
            "add_link", "remove_link", "set_node_input", "add_socket",
            "set_socket_default", "configure_graph", "update_graph", "evaluate", "apply"
        )
        if act not in allowed_actions:
            raise ValueError(f"Parameter 'action' must be one of {allowed_actions}, got '{sanitized.get('action')}'.")
        sanitized["action"] = act
        stype = sanitized.get("socket_type")
        if stype is not None:
            if stype not in ("NodeSocketFloat", "NodeSocketInt", "NodeSocketVector", "NodeSocketColor", "NodeSocketBool", "NodeSocketString", "NodeSocketGeometry"):
                raise ValueError(f"Invalid socket_type '{stype}'.")
        if "expected_snapshot_id" in sanitized:
            from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id
            validate_snapshot_id(sanitized["expected_snapshot_id"])

    # Tool-specific validation for export_scene_asset and aliases
    if tool_name in (TOOL_EXPORT_SCENE_ASSET, TOOL_EXPORT_SCENE):
        exp_path = str(sanitized.get("filepath", "")).strip()
        if not exp_path:
            raise ValueError(f"Parameter 'filepath' cannot be empty for {tool_name}.")
        fmt = sanitized.get("format")
        if fmt is not None:
            fmt_upper = str(fmt).strip().upper()
            if fmt_upper not in ("GLTF", "GLB", "FBX", "USD", "USDC", "USDA", "OBJ", "STL", "PLY", "ABC"):
                raise ValueError(f"Unsupported export format '{fmt}'. Allowed: GLTF, GLB, FBX, USD, USDC, USDA, OBJ, STL, PLY, ABC.")
            sanitized["format"] = fmt_upper

    # Tool-specific validation for import_scene_asset and aliases
    if tool_name in (TOOL_IMPORT_SCENE_ASSET, TOOL_IMPORT_SCENE):
        imp_path = str(sanitized.get("filepath", "")).strip()
        if not imp_path:
            raise ValueError(f"Parameter 'filepath' cannot be empty for {tool_name}.")
        fmt = sanitized.get("format")
        if fmt is not None:
            fmt_upper = str(fmt).strip().upper()
            if fmt_upper not in ("GLTF", "GLB", "FBX", "USD", "USDC", "USDA", "OBJ", "STL", "PLY", "ABC"):
                raise ValueError(f"Unsupported import format '{fmt}'. Allowed: GLTF, GLB, FBX, USD, USDC, USDA, OBJ, STL, PLY, ABC.")
            sanitized["format"] = fmt_upper

    # Tool-specific validation for duplicate_object and aliases
    if tool_name in (TOOL_DUPLICATE_OBJECT, TOOL_DUPLICATE):
        d_name = str(sanitized.get("name", "")).strip()
        if not d_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        for attr in ("location", "rotation_euler", "scale"):
            val = sanitized.get(attr)
            if val is not None:
                if not isinstance(val, (list, tuple)) or len(val) != 3 or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in val
                ):
                    raise ValueError(f"Parameter '{attr}' must be a 3-element finite numeric list for {tool_name}.")

    # Tool-specific validation for create_armature
    if tool_name == TOOL_CREATE_ARMATURE:
        for attr in ("location", "rotation", "scale"):
            val = sanitized.get(attr)
            if val is not None:
                if not isinstance(val, (list, tuple)) or len(val) != 3 or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in val
                ):
                    raise ValueError(f"Parameter '{attr}' must be a 3-element finite numeric list for {tool_name}.")

    # Tool-specific validation for edit_armature_bones
    if tool_name == TOOL_EDIT_ARMATURE_BONES:
        arm_name = str(sanitized.get("armature_name", "")).strip()
        if not arm_name:
            raise ValueError(f"Parameter 'armature_name' cannot be empty for {tool_name}.")

    # Tool-specific validation for inspect_armature
    if tool_name == TOOL_INSPECT_ARMATURE:
        arm_name = str(sanitized.get("armature_name", "")).strip()
        if not arm_name:
            raise ValueError(f"Parameter 'armature_name' cannot be empty for {tool_name}.")

    # Tool-specific validation for bind_armature_mesh
    if tool_name == TOOL_BIND_ARMATURE_MESH:
        mesh_name = str(sanitized.get("mesh_object_name", "")).strip()
        arm_name = str(sanitized.get("armature_name", "")).strip()
        if not mesh_name:
            raise ValueError(f"Parameter 'mesh_object_name' cannot be empty for {tool_name}.")
        if not arm_name:
            raise ValueError(f"Parameter 'armature_name' cannot be empty for {tool_name}.")
        bm = str(sanitized.get("bind_mode", "AUTOMATIC")).strip().upper()
        if bm not in ("AUTOMATIC", "ENVELOPE", "NAME_ONLY", "MANUAL"):
            raise ValueError(f"Unsupported bind_mode '{bm}'. Allowed: AUTOMATIC, ENVELOPE, NAME_ONLY, MANUAL.")
        sanitized["bind_mode"] = bm

    # Tool-specific validation for configure_bone_constraint
    if tool_name == TOOL_CONFIGURE_BONE_CONSTRAINT:
        arm_name = str(sanitized.get("armature_name", "")).strip()
        bone_name = str(sanitized.get("bone_name", "")).strip()
        if not arm_name:
            raise ValueError(f"Parameter 'armature_name' cannot be empty for {tool_name}.")
        if not bone_name:
            raise ValueError(f"Parameter 'bone_name' cannot be empty for {tool_name}.")
        ctype = str(sanitized.get("constraint_type", "IK")).strip().upper()
        if ctype not in ("IK", "LIMIT_ROTATION", "COPY_TRANSFORMS"):
            raise ValueError(f"Unsupported constraint_type '{ctype}'. Allowed: IK, LIMIT_ROTATION, COPY_TRANSFORMS.")
        sanitized["constraint_type"] = ctype
        act = str(sanitized.get("action", "ADD")).strip().upper()
        if act not in ("ADD", "REMOVE", "UPDATE"):
            raise ValueError(f"Unsupported action '{act}'. Allowed: ADD, REMOVE, UPDATE.")
        sanitized["action"] = act

    # Tool-specific validation for compare_silhouette_alignment
    if tool_name == TOOL_COMPARE_SILHOUETTE_ALIGNMENT:
        ref_path = str(sanitized.get("reference_image_path", "")).strip()
        if not ref_path:
            raise ValueError("Parameter 'reference_image_path' cannot be empty for compare_silhouette_alignment.")
        sanitized["reference_image_path"] = ref_path

        if "crop_box" in sanitized:
            cb = sanitized["crop_box"]
            if not isinstance(cb, (list, tuple)) or len(cb) != 4:
                raise ValueError("Parameter 'crop_box' must be a list/tuple of 4 numbers [u_min, v_min, u_max, v_max].")
            for c in cb:
                if not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) or not (0.0 <= c <= 1.0):
                    raise ValueError(f"Crop box coordinate {c} must be a finite number within [0.0, 1.0].")
            if cb[0] >= cb[2] or cb[1] >= cb[3]:
                raise ValueError(f"Invalid crop_box: u_min must be < u_max and v_min < v_max, got {cb}.")
            sanitized["crop_box"] = [float(x) for x in cb]

        coord_sys = str(sanitized.get("coordinate_system", "UV")).strip().upper()
        if coord_sys not in ("UV", "IMAGE_SPACE"):
            raise ValueError(f"Invalid coordinate_system '{coord_sys}'. Allowed: ['UV', 'IMAGE_SPACE'].")
        sanitized["coordinate_system"] = coord_sys

        view_val = str(sanitized.get("view", "FRONT")).strip().upper()
        if view_val not in ("CURRENT", "FRONT", "SIDE", "TOP", "PERSPECTIVE"):
            raise ValueError(f"Invalid view '{view_val}'. Allowed: ['CURRENT', 'FRONT', 'SIDE', 'TOP', 'PERSPECTIVE'].")
        sanitized["view"] = view_val

        mode_val = str(sanitized.get("mode", "CAMERA")).strip().upper()
        if mode_val not in ("CAMERA", "VIEWPORT"):
            raise ValueError(f"Invalid mode '{mode_val}'. Allowed: ['CAMERA', 'VIEWPORT'].")
        sanitized["mode"] = mode_val

        for dim_prop in ("width", "height"):
            if dim_prop in sanitized:
                dim_v = sanitized[dim_prop]
                if not isinstance(dim_v, int) or isinstance(dim_v, bool) or dim_v < 64 or dim_v > 2048:
                    raise ValueError(f"Parameter '{dim_prop}' must be an integer between 64 and 2048.")

        if "mask_threshold" in sanitized:
            mt = sanitized["mask_threshold"]
            if not isinstance(mt, (int, float)) or isinstance(mt, bool) or not math.isfinite(mt) or not (0.0 <= mt <= 1.0):
                raise ValueError(f"Parameter 'mask_threshold' must be a finite number between 0.0 and 1.0, got {mt}.")

        if "diff_output_path" in sanitized:
            d_path = str(sanitized["diff_output_path"]).strip()
            if not d_path:
                raise ValueError("Parameter 'diff_output_path' cannot be empty.")
            sanitized["diff_output_path"] = d_path

    # Tool-specific validation for calibrate_reference_views
    if tool_name == TOOL_CALIBRATE_REFERENCE_VIEWS:
        views_list = sanitized.get("views")
        if not isinstance(views_list, (list, tuple)) or len(views_list) == 0:
            raise ValueError("Parameter 'views' must be a non-empty list of view alignment configurations.")
        sanitized_views = []
        for i, v in enumerate(views_list):
            if not isinstance(v, dict):
                raise ValueError(f"View configuration at index {i} must be an object (dictionary).")
            v_name = str(v.get("name", "")).strip()
            if not v_name:
                raise ValueError(f"View at index {i} requires a non-empty 'name' property.")
            v_axis = str(v.get("view_axis", "")).strip().upper()
            if v_axis not in ("FRONT", "SIDE", "TOP"):
                raise ValueError(f"View at index {i} has invalid view_axis '{v_axis}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
            offset_dist = float(v.get("offset_distance", 5.0))
            if not math.isfinite(offset_dist):
                raise ValueError(f"View at index {i} 'offset_distance' must be a finite number.")
            scale_v = float(v.get("scale", 1.0))
            if not math.isfinite(scale_v) or scale_v <= 0.0:
                raise ValueError(f"View at index {i} 'scale' must be a positive finite number > 0.0.")
            flip_norm = bool(v.get("flip_normal", False))
            sanitized_views.append({
                "name": v_name,
                "view_axis": v_axis,
                "offset_distance": offset_dist,
                "flip_normal": flip_norm,
                "scale": scale_v,
            })
        sanitized["views"] = sanitized_views

        if "origin" in sanitized:
            orig = sanitized["origin"]
            if not isinstance(orig, (list, tuple)) or len(orig) != 3 or not all(
                isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in orig
            ):
                raise ValueError("Parameter 'origin' must be a 3-element finite numeric list [x, y, z].")
            sanitized["origin"] = [float(c) for c in orig]

        if "target_bounding_box" in sanitized:
            bbox = sanitized["target_bounding_box"]
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 6 or not all(
                isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in bbox
            ):
                raise ValueError("Parameter 'target_bounding_box' must be a 6-element finite numeric list [min_x, min_y, min_z, max_x, max_y, max_z].")
            min_x, min_y, min_z, max_x, max_y, max_z = [float(c) for c in bbox]
            if min_x >= max_x:
                raise ValueError(f"Invalid target_bounding_box: min_x ({min_x}) must be strictly less than max_x ({max_x}).")
            if min_y >= max_y:
                raise ValueError(f"Invalid target_bounding_box: min_y ({min_y}) must be strictly less than max_y ({max_y}).")
            if min_z >= max_z:
                raise ValueError(f"Invalid target_bounding_box: min_z ({min_z}) must be strictly less than max_z ({max_z}).")
            if (max_x - min_x) <= 0.0001 or (max_y - min_y) <= 0.0001 or (max_z - min_z) <= 0.0001:
                raise ValueError("Invalid target_bounding_box: extents along all three axes must be > 0.0001 meters.")
            sanitized["target_bounding_box"] = [min_x, min_y, min_z, max_x, max_y, max_z]

    # Tool-specific validation for crop_reference_image and load_reference_image
    if tool_name in (TOOL_LOAD_REFERENCE_IMAGE, TOOL_CROP_REFERENCE_IMAGE):
        img_path = str(sanitized.get("image_path", "")).strip()
        if not img_path:
            raise ValueError(f"Parameter 'image_path' cannot be empty for {tool_name}.")
        
        # Validate crop_box if provided (required for crop_reference_image)
        if tool_name == TOOL_CROP_REFERENCE_IMAGE or "crop_box" in sanitized:
            if "crop_box" not in sanitized:
                raise ValueError("Parameter 'crop_box' is required for crop_reference_image.")
            crop_box = sanitized["crop_box"]
            if not isinstance(crop_box, (list, tuple)) or len(crop_box) != 4:
                raise ValueError(f"Parameter 'crop_box' must be a list/tuple of 4 numbers [u_min, v_min, u_max, v_max], got {type(crop_box).__name__}.")
            for c in crop_box:
                if not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c):
                    raise ValueError(f"All crop_box elements must be finite numbers, got {c}.")
                if c < 0.0 or c > 1.0:
                    raise ValueError(f"Crop box coordinate {c} must be within normalized range [0.0, 1.0].")
            u_min, v_min, u_max, v_max = float(crop_box[0]), float(crop_box[1]), float(crop_box[2]), float(crop_box[3])
            if u_min >= u_max:
                raise ValueError(f"Invalid crop_box: u_min ({u_min}) must be strictly less than u_max ({u_max}).")
            if v_min >= v_max:
                raise ValueError(f"Invalid crop_box: v_min ({v_min}) must be strictly less than v_max ({v_max}).")
            sanitized["crop_box"] = [u_min, v_min, u_max, v_max]

            coord_sys = str(sanitized.get("coordinate_system", "UV")).strip().upper()
            if coord_sys not in ("UV", "IMAGE_SPACE"):
                raise ValueError(f"Invalid coordinate_system '{coord_sys}'. Allowed: ['UV', 'IMAGE_SPACE'].")
            sanitized["coordinate_system"] = coord_sys

            if "output_path" in sanitized:
                out_p = str(sanitized["output_path"]).strip()
                if not out_p:
                    raise ValueError(f"Parameter 'output_path' cannot be empty string for {tool_name}.")
                if out_p.lower() == img_path.lower():
                    raise ValueError("Parameter 'output_path' cannot overwrite source 'image_path'.")
                sanitized["output_path"] = out_p

        load_ref = sanitized.get("load_as_reference", True)
        if tool_name == TOOL_CROP_REFERENCE_IMAGE and not isinstance(load_ref, bool):
            raise ValueError("Parameter 'load_as_reference' must be a boolean.")

        if tool_name == TOOL_LOAD_REFERENCE_IMAGE or load_ref:
            display_mode = str(sanitized.get("display_mode", "EMPTY")).strip().upper()
            if display_mode not in ("EMPTY", "PLANE"):
                raise ValueError(f"Invalid display_mode '{display_mode}'. Allowed: ['EMPTY', 'PLANE'].")
            sanitized["display_mode"] = display_mode
            view_axis = str(sanitized.get("view_axis", "FRONT")).strip().upper()
            if view_axis not in ("FRONT", "SIDE", "TOP", "USER"):
                raise ValueError(f"Invalid view_axis '{view_axis}'. Allowed: ['FRONT', 'SIDE', 'TOP', 'USER'].")
            sanitized["view_axis"] = view_axis
            for attr in ("location", "rotation_euler", "scale"):
                val = sanitized.get(attr)
                if val is not None:
                    if not isinstance(val, (list, tuple)) or len(val) != 3 or not all(
                        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                        for v in val
                    ):
                        raise ValueError(f"Parameter '{attr}' must be a 3-element finite numeric list for {tool_name}.")
            if "size" in sanitized:
                size_val = float(sanitized["size"])
                if not math.isfinite(size_val) or size_val <= 0:
                    raise ValueError(f"Parameter 'size' must be a positive finite number for {tool_name}.")
            if "opacity" in sanitized:
                op_val = float(sanitized["opacity"])
                if not math.isfinite(op_val) or not 0.0 <= op_val <= 1.0:
                    raise ValueError(f"Parameter 'opacity' must be between 0.0 and 1.0 for {tool_name}.")
            depth_val = str(sanitized.get("depth", "DEFAULT")).strip().upper()
            if depth_val not in ("DEFAULT", "FRONT", "BACK"):
                raise ValueError(f"Invalid depth '{depth_val}'. Allowed: ['DEFAULT', 'FRONT', 'BACK'].")
            sanitized["depth"] = depth_val


    # Tool-specific validation for rename_object and aliases
    if tool_name in (TOOL_RENAME_OBJECT, TOOL_RENAME):
        r_name = str(sanitized.get("name", "")).strip()
        if not r_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        new_name = str(sanitized.get("new_name", "")).strip()
        if not new_name:
            raise ValueError(f"Parameter 'new_name' cannot be empty for {tool_name}.")
        sanitized["new_name"] = new_name

    # Tool-specific validation for select_object and aliases
    if tool_name in (TOOL_SELECT_OBJECT, TOOL_SELECT):
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        if "state" in sanitized and not isinstance(sanitized["state"], bool):
            raise ValueError(f"Parameter 'state' must be a boolean for {tool_name}.")
        if "deselect_all" in sanitized and not isinstance(sanitized["deselect_all"], bool):
            raise ValueError(f"Parameter 'deselect_all' must be a boolean for {tool_name}.")
        if "make_active" in sanitized and not isinstance(sanitized["make_active"], bool):
            raise ValueError(f"Parameter 'make_active' must be a boolean for {tool_name}.")

    # Tool-specific validation for purge_orphaned_datablocks and aliases
    if tool_name in (TOOL_PURGE_ORPHANED_DATABLOCKS, TOOL_PURGE_ORPHANS):
        if "do_recursive" in sanitized and not isinstance(sanitized["do_recursive"], bool):
            raise ValueError(f"Parameter 'do_recursive' must be a boolean for {tool_name}.")
        if "do_local_ids" in sanitized and not isinstance(sanitized["do_local_ids"], bool):
            raise ValueError(f"Parameter 'do_local_ids' must be a boolean for {tool_name}.")
        if "do_linked_ids" in sanitized and not isinstance(sanitized["do_linked_ids"], bool):
            raise ValueError(f"Parameter 'do_linked_ids' must be a boolean for {tool_name}.")

    # Tool-specific validation for create_curve_or_text and aliases
    if tool_name in (TOOL_CREATE_CURVE_OR_TEXT, TOOL_CREATE_CURVE, TOOL_CREATE_TEXT):
        c_name = str(sanitized.get("name", "")).strip()
        if not c_name:
            raise ValueError(f"Parameter 'name' cannot be empty for {tool_name}.")
        c_type = str(sanitized.get("curve_type", "BEZIER")).strip().upper()
        if c_type not in ("BEZIER", "CIRCLE", "PATH", "NURBS_CURVE", "NURBS_CIRCLE", "TEXT"):
            raise ValueError(f"Unsupported curve_type '{c_type}'. Allowed: BEZIER, CIRCLE, PATH, NURBS_CURVE, NURBS_CIRCLE, TEXT.")
        sanitized["curve_type"] = c_type
        dim = str(sanitized.get("dimensions", "3D")).strip().upper()
        if dim not in ("2D", "3D"):
            raise ValueError(f"Parameter 'dimensions' must be '2D' or '3D', got '{dim}'.")
        sanitized["dimensions"] = dim

    # Tool-specific validation for manage_shader_nodes and aliases
    if tool_name in (TOOL_MANAGE_SHADER_NODES, TOOL_CONNECT_SHADER_NODES, TOOL_MANAGE_NODES):
        t_name = str(sanitized.get("target_name", "")).strip()
        if not t_name:
            raise ValueError(f"Parameter 'target_name' cannot be empty for {tool_name}.")
        t_type = str(sanitized.get("target_type", "MATERIAL")).strip().upper()
        if t_type not in ("MATERIAL", "WORLD"):
            raise ValueError(f"Parameter 'target_type' must be 'MATERIAL' or 'WORLD', got '{t_type}'.")
        sanitized["target_type"] = t_type
        sn_act = str(sanitized.get("action", "create_node")).strip().lower()
        if sn_act not in ("create_node", "remove_node", "connect", "disconnect", "set_property", "list_nodes"):
            raise ValueError(f"Unsupported action '{sn_act}' for {tool_name}.")
        sanitized["action"] = sn_act

    # Tool-specific validation for bake_object_texture and aliases
    if tool_name in (TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS):
        b_name = str(sanitized.get("object_name", "")).strip()
        if not b_name:
            raise ValueError(f"Parameter 'object_name' cannot be empty for {tool_name}.")
        b_type = str(sanitized.get("bake_type", "COMBINED")).strip().upper()
        if b_type not in ("COMBINED", "DIFFUSE", "ROUGHNESS", "NORMAL", "AO", "EMIT", "SHADOW"):
            raise ValueError(f"Unsupported bake_type '{b_type}'. Allowed: COMBINED, DIFFUSE, ROUGHNESS, NORMAL, AO, EMIT, SHADOW.")
        sanitized["bake_type"] = b_type

    # Tool-specific validation for manage_compositor_nodes and aliases
    if tool_name in (TOOL_MANAGE_COMPOSITOR_NODES, TOOL_CONFIGURE_COMPOSITOR, TOOL_MANAGE_COMPOSITOR):
        cn_act = str(sanitized.get("action", "inspect")).strip().lower()
        if cn_act not in ("enable", "inspect", "create_node", "remove_node", "connect", "disconnect", "set_property", "configure_render_passes", "list_nodes"):
            raise ValueError(f"Unsupported action '{cn_act}' for {tool_name}.")
        sanitized["action"] = cn_act
        if cn_act == "configure_render_passes":
            passes = sanitized.get("passes")
            if not isinstance(passes, dict) or not passes:
                raise ValueError(f"Parameter 'passes' (dict) is required for {tool_name} with action 'configure_render_passes'.")

    # Tool-specific validation for configure_animation_curve and aliases
    if tool_name in (TOOL_CONFIGURE_ANIMATION_CURVE, TOOL_MANAGE_FCURVE, TOOL_SET_KEYFRAME_INTERPOLATION, TOOL_MANAGE_ACTION_SLOTS):
        ac_name = str(sanitized.get("object_name", "")).strip()
        if not ac_name:
            raise ValueError(f"Parameter 'object_name' cannot be empty for {tool_name}.")
        ac_act = str(sanitized.get("action", "set_interpolation")).strip().lower()
        if ac_act not in ("set_interpolation", "add_modifier", "remove_modifier", "manage_slot", "list_fcurves"):
            raise ValueError(f"Unsupported action '{ac_act}' for {tool_name}.")
        sanitized["action"] = ac_act
        interp = sanitized.get("interpolation")
        if interp is not None:
            interp_upper = str(interp).strip().upper()
            if interp_upper not in ("CONSTANT", "LINEAR", "BEZIER"):
                raise ValueError(f"Unsupported interpolation '{interp}'. Allowed: CONSTANT, LINEAR, BEZIER.")
            sanitized["interpolation"] = interp_upper

    # Tool-specific validation for configure_physics and aliases
    if tool_name in (TOOL_CONFIGURE_PHYSICS, TOOL_SETUP_PHYSICS, TOOL_MANAGE_PHYSICS):
        p_name = str(sanitized.get("object_name", "")).strip()
        if not p_name:
            raise ValueError(f"Parameter 'object_name' cannot be empty for {tool_name}.")
        p_type = str(sanitized.get("physics_type", "RIGID_BODY")).strip().upper()
        if p_type not in ("RIGID_BODY", "CLOTH", "COLLISION", "RIGID_BODY_CONSTRAINT"):
            raise ValueError(f"Unsupported physics_type '{p_type}'. Allowed: RIGID_BODY, CLOTH, COLLISION, RIGID_BODY_CONSTRAINT.")
        sanitized["physics_type"] = p_type
        p_act = str(sanitized.get("action", "add")).strip().lower()
        if p_act not in ("add", "remove", "configure"):
            raise ValueError(f"Unsupported action '{p_act}'. Allowed: add, remove, configure.")
        sanitized["action"] = p_act

        if "mass" in sanitized:
            m_val = float(sanitized["mass"])
            if m_val < 0.01 or m_val > 10000.0:
                raise ValueError(f"Parameter 'mass' must be between 0.01 and 10000.0 kg, got {m_val}.")
        if "friction" in sanitized:
            f_val = float(sanitized["friction"])
            max_f = 80.0 if p_type == "CLOTH" else 1.0
            if f_val < 0.0 or f_val > max_f:
                raise ValueError(f"Parameter 'friction' must be between 0.0 and {max_f}, got {f_val}.")
        if "restitution" in sanitized:
            r_val = float(sanitized["restitution"])
            if r_val < 0.0 or r_val > 1.0:
                raise ValueError(f"Parameter 'restitution' must be between 0.0 and 1.0, got {r_val}.")
        if "collision_shape" in sanitized:
            cs_val = str(sanitized["collision_shape"]).strip().upper()
            if cs_val not in ("BOX", "SPHERE", "CAPSULE", "CYLINDER", "CONE", "CONVEX_HULL", "MESH"):
                raise ValueError(f"Unsupported collision_shape '{cs_val}'. Allowed: BOX, SPHERE, CAPSULE, CYLINDER, CONE, CONVEX_HULL, MESH.")
            sanitized["collision_shape"] = cs_val
        if "cloth_preset" in sanitized and sanitized["cloth_preset"] is not None:
            cp_val = str(sanitized["cloth_preset"]).strip().upper()
            if cp_val not in ("SILK", "COTTON", "LEATHER"):
                raise ValueError(f"Unsupported cloth_preset '{cp_val}'. Allowed: SILK, COTTON, LEATHER.")
            sanitized["cloth_preset"] = cp_val
        if "quality" in sanitized:
            q_val = int(sanitized["quality"])
            if q_val < 1 or q_val > 20:
                raise ValueError(f"Parameter 'quality' must be between 1 and 20, got {q_val}.")
        if "damping" in sanitized:
            d_val = float(sanitized["damping"])
            if d_val < 0.0 or d_val > 1.0:
                raise ValueError(f"Parameter 'damping' must be between 0.0 and 1.0, got {d_val}.")
        if "cloth_friction" in sanitized:
            cf_val = float(sanitized["cloth_friction"])
            if cf_val < 0.0 or cf_val > 80.0:
                raise ValueError(f"Parameter 'cloth_friction' must be between 0.0 and 80.0, got {cf_val}.")
        if "thickness_outer" in sanitized:
            to_val = float(sanitized["thickness_outer"])
            if to_val < 0.001 or to_val > 1.0:
                raise ValueError(f"Parameter 'thickness_outer' must be between 0.001 and 1.0, got {to_val}.")
        if "use_self_collision" in sanitized and sanitized["use_self_collision"] is not None:
            sanitized["use_self_collision"] = bool(sanitized["use_self_collision"])
        if "self_distance_min" in sanitized and sanitized["self_distance_min"] is not None:
            sd_val = float(sanitized["self_distance_min"])
            if sd_val < 0.0005 or sd_val > 0.1:
                raise ValueError(f"Parameter 'self_distance_min' must be between 0.0005 and 0.1, got {sd_val}.")
            sanitized["self_distance_min"] = sd_val
        if "self_friction" in sanitized and sanitized["self_friction"] is not None:
            sf_val = float(sanitized["self_friction"])
            if sf_val < 0.0 or sf_val > 80.0:
                raise ValueError(f"Parameter 'self_friction' must be between 0.0 and 80.0, got {sf_val}.")
            sanitized["self_friction"] = sf_val
        if "use_collision" in sanitized and sanitized["use_collision"] is not None:
            sanitized["use_collision"] = bool(sanitized["use_collision"])
        if "distance_min" in sanitized and sanitized["distance_min"] is not None:
            dm_val = float(sanitized["distance_min"])
            if dm_val < 0.001 or dm_val > 1.0:
                raise ValueError(f"Parameter 'distance_min' must be between 0.001 and 1.0, got {dm_val}.")
            sanitized["distance_min"] = dm_val
        if "collision_quality" in sanitized and sanitized["collision_quality"] is not None:
            cq_val = int(sanitized["collision_quality"])
            if cq_val < 1 or cq_val > 20:
                raise ValueError(f"Parameter 'collision_quality' must be between 1 and 20, got {cq_val}.")
            sanitized["collision_quality"] = cq_val
        if "use_internal_springs" in sanitized and sanitized["use_internal_springs"] is not None:
            sanitized["use_internal_springs"] = bool(sanitized["use_internal_springs"])
        if "internal_spring_max_length" in sanitized and sanitized["internal_spring_max_length"] is not None:
            ism_val = float(sanitized["internal_spring_max_length"])
            if ism_val < 0.0 or ism_val > 1000.0:
                raise ValueError(f"Parameter 'internal_spring_max_length' must be between 0.0 and 1000.0, got {ism_val}.")
            sanitized["internal_spring_max_length"] = ism_val
        if "internal_tension_stiffness" in sanitized and sanitized["internal_tension_stiffness"] is not None:
            its_val = float(sanitized["internal_tension_stiffness"])
            if its_val < 0.0 or its_val > 10000.0:
                raise ValueError(f"Parameter 'internal_tension_stiffness' must be between 0.0 and 10000.0, got {its_val}.")
            sanitized["internal_tension_stiffness"] = its_val
        if "internal_compression_stiffness" in sanitized and sanitized["internal_compression_stiffness"] is not None:
            ics_val = float(sanitized["internal_compression_stiffness"])
            if ics_val < 0.0 or ics_val > 10000.0:
                raise ValueError(f"Parameter 'internal_compression_stiffness' must be between 0.0 and 10000.0, got {ics_val}.")
            sanitized["internal_compression_stiffness"] = ics_val
        if "internal_spring_normal_check" in sanitized and sanitized["internal_spring_normal_check"] is not None:
            sanitized["internal_spring_normal_check"] = bool(sanitized["internal_spring_normal_check"])
        if "use_pressure" in sanitized and sanitized["use_pressure"] is not None:
            sanitized["use_pressure"] = bool(sanitized["use_pressure"])
        if "uniform_pressure_force" in sanitized and sanitized["uniform_pressure_force"] is not None:
            upf_val = float(sanitized["uniform_pressure_force"])
            if upf_val < -10000.0 or upf_val > 10000.0:
                raise ValueError(f"Parameter 'uniform_pressure_force' must be between -10000.0 and 10000.0, got {upf_val}.")
            sanitized["uniform_pressure_force"] = upf_val
        if "use_pressure_volume" in sanitized and sanitized["use_pressure_volume"] is not None:
            sanitized["use_pressure_volume"] = bool(sanitized["use_pressure_volume"])
        if "target_volume" in sanitized and sanitized["target_volume"] is not None:
            tv_val = float(sanitized["target_volume"])
            if tv_val < 0.0 or tv_val > 10000.0:
                raise ValueError(f"Parameter 'target_volume' must be between 0.0 and 10000.0, got {tv_val}.")
            sanitized["target_volume"] = tv_val
        if "pressure_factor" in sanitized and sanitized["pressure_factor"] is not None:
            pf_val = float(sanitized["pressure_factor"])
            if pf_val < 0.0 or pf_val > 10000.0:
                raise ValueError(f"Parameter 'pressure_factor' must be between 0.0 and 10000.0, got {pf_val}.")
            sanitized["pressure_factor"] = pf_val
        if "kinematic" in sanitized and sanitized["kinematic"] is not None:
            sanitized["kinematic"] = bool(sanitized["kinematic"])
        if "linear_damping" in sanitized and sanitized["linear_damping"] is not None:
            ld_val = float(sanitized["linear_damping"])
            if ld_val < 0.0 or ld_val > 1.0:
                raise ValueError(f"Parameter 'linear_damping' must be between 0.0 and 1.0, got {ld_val}.")
            sanitized["linear_damping"] = ld_val
        if "angular_damping" in sanitized and sanitized["angular_damping"] is not None:
            ad_val = float(sanitized["angular_damping"])
            if ad_val < 0.0 or ad_val > 1.0:
                raise ValueError(f"Parameter 'angular_damping' must be between 0.0 and 1.0, got {ad_val}.")
            sanitized["angular_damping"] = ad_val

        # Rigid body constraint validations
        if "constraint_type" in sanitized and sanitized["constraint_type"] is not None:
            ct_val = str(sanitized["constraint_type"]).strip().upper()
            if ct_val not in ("FIXED", "POINT", "HINGE", "SLIDER", "GENERIC"):
                raise ValueError(f"Unsupported constraint_type '{ct_val}'. Allowed: FIXED, POINT, HINGE, SLIDER, GENERIC.")
            sanitized["constraint_type"] = ct_val
        elif p_type == "RIGID_BODY_CONSTRAINT" and sanitized.get("action") == "add":
            sanitized["constraint_type"] = "FIXED"

        if "target_object_1" in sanitized and sanitized["target_object_1"] is not None:
            t1_val = str(sanitized["target_object_1"]).strip()
            sanitized["target_object_1"] = t1_val if t1_val else None

        if "target_object_2" in sanitized and sanitized["target_object_2"] is not None:
            t2_val = str(sanitized["target_object_2"]).strip()
            sanitized["target_object_2"] = t2_val if t2_val else None

        if sanitized.get("target_object_1") and sanitized.get("target_object_2"):
            if sanitized["target_object_1"] == sanitized["target_object_2"]:
                raise ValueError("Rigid body constraint cannot connect an object to itself.")

        if "disable_collisions" in sanitized and sanitized["disable_collisions"] is not None:
            sanitized["disable_collisions"] = bool(sanitized["disable_collisions"])
        if "use_breaking" in sanitized and sanitized["use_breaking"] is not None:
            sanitized["use_breaking"] = bool(sanitized["use_breaking"])
        if "breaking_threshold" in sanitized and sanitized["breaking_threshold"] is not None:
            bt_val = float(sanitized["breaking_threshold"])
            if bt_val < 0.0 or bt_val > 100000.0:
                raise ValueError(f"Parameter 'breaking_threshold' must be between 0.0 and 100000.0, got {bt_val}.")
            sanitized["breaking_threshold"] = bt_val

        for axis in ("x", "y", "z"):
            u_lin = f"use_limit_lin_{axis}"
            if u_lin in sanitized and sanitized[u_lin] is not None:
                sanitized[u_lin] = bool(sanitized[u_lin])
            l_lin = f"limit_lin_{axis}_lower"
            if l_lin in sanitized and sanitized[l_lin] is not None:
                sanitized[l_lin] = float(sanitized[l_lin])
                if sanitized[l_lin] < -10000.0 or sanitized[l_lin] > 10000.0:
                    raise ValueError(f"Parameter '{l_lin}' must be between -10000.0 and 10000.0, got {sanitized[l_lin]}.")
            u_lin_val = f"limit_lin_{axis}_upper"
            if u_lin_val in sanitized and sanitized[u_lin_val] is not None:
                sanitized[u_lin_val] = float(sanitized[u_lin_val])
                if sanitized[u_lin_val] < -10000.0 or sanitized[u_lin_val] > 10000.0:
                    raise ValueError(f"Parameter '{u_lin_val}' must be between -10000.0 and 10000.0, got {sanitized[u_lin_val]}.")
            if l_lin in sanitized and u_lin_val in sanitized and sanitized[l_lin] is not None and sanitized[u_lin_val] is not None:
                if sanitized[l_lin] > sanitized[u_lin_val]:
                    raise ValueError(f"Parameter '{l_lin}' ({sanitized[l_lin]}) cannot be greater than '{u_lin_val}' ({sanitized[u_lin_val]}).")
            act = "remove"
        if act not in ("create", "configure", "inspect", "remove"):
            raise ValueError(f"Unsupported action '{act}' for {tool_name}. Allowed: create, configure, inspect, remove.")
        sanitized["action"] = act

        if tool_name == TOOL_CONFIGURE_FORCE_FIELD and act in ("create", "configure"):
            f_type = str(sanitized.get("field_type", "WIND")).strip().upper()
            if f_type not in ("WIND", "TURBULENCE", "VORTEX"):
                raise ValueError(f"Unsupported field_type '{f_type}'. Allowed: WIND, TURBULENCE, VORTEX.")
            sanitized["field_type"] = f_type

            if "strength" in sanitized and sanitized["strength"] is not None:
                s_val = float(sanitized["strength"])
                if s_val < -100000.0 or s_val > 100000.0:
                    raise ValueError(f"Parameter 'strength' must be between -100000.0 and 100000.0, got {s_val}.")

            if "flow" in sanitized and sanitized["flow"] is not None:
                fl_val = float(sanitized["flow"])
                if fl_val < 0.0 or fl_val > 1000.0:
                    raise ValueError(f"Parameter 'flow' must be between 0.0 and 1000.0, got {fl_val}.")

            if "wind_factor" in sanitized and sanitized["wind_factor"] is not None:
                wf_val = float(sanitized["wind_factor"])
                if wf_val < 0.0 or wf_val > 1.0:
                    raise ValueError(f"Parameter 'wind_factor' must be between 0.0 and 1.0, got {wf_val}.")

            if "size" in sanitized and sanitized["size"] is not None:
                sz_val = float(sanitized["size"])
                if sz_val < 0.0 or sz_val > 1000.0:
                    raise ValueError(f"Parameter 'size' must be between 0.0 and 1000.0, got {sz_val}.")

            if "inflow" in sanitized and sanitized["inflow"] is not None:
                inf_val = float(sanitized["inflow"])
                if inf_val < -1000.0 or inf_val > 1000.0:
                    raise ValueError(f"Parameter 'inflow' must be between -1000.0 and 1000.0, got {inf_val}.")

            if "noise" in sanitized and sanitized["noise"] is not None:
                n_val = float(sanitized["noise"])
                if n_val < 0.0 or n_val > 10.0:
                    raise ValueError(f"Parameter 'noise' must be between 0.0 and 10.0, got {n_val}.")

            if "seed" in sanitized and sanitized["seed"] is not None:
                sd_val = int(sanitized["seed"])
                if sd_val < 1 or sd_val > 128:
                    raise ValueError(f"Parameter 'seed' must be between 1 and 128, got {sd_val}.")

            if "falloff_power" in sanitized and sanitized["falloff_power"] is not None:
                fp_val = float(sanitized["falloff_power"])
                if fp_val < 0.0 or fp_val > 10.0:
                    raise ValueError(f"Parameter 'falloff_power' must be between 0.0 and 10.0, got {fp_val}.")

            d_min = sanitized.get("distance_min")
            d_max = sanitized.get("distance_max")
            if d_min is not None and d_max is not None:
                if float(d_min) > float(d_max):
                    raise ValueError(f"Parameter 'distance_min' ({d_min}) cannot be greater than 'distance_max' ({d_max}).")

    # Tool-specific validation for configure_particle_system and inspect_particle_system
    if tool_name in (TOOL_CONFIGURE_PARTICLE_SYSTEM, TOOL_INSPECT_PARTICLE_SYSTEM):
        name_val = sanitized.get("object_name") or sanitized.get("name")
        if name_val is not None:
            sanitized["object_name"] = str(name_val).strip()
            sanitized["name"] = sanitized["object_name"]

        act = str(sanitized.get("action", "create")).strip().lower()
        if act in ("add", "new"):
            act = "create"
        elif act in ("delete",):
            act = "remove"
        if act not in ("create", "configure", "inspect", "remove"):
            raise ValueError(f"Unsupported action '{act}' for {tool_name}. Allowed: create, configure, inspect, remove.")
        sanitized["action"] = act

        if tool_name == TOOL_CONFIGURE_PARTICLE_SYSTEM and act in ("create", "configure"):
            s_type = None
            if "system_type" in sanitized and sanitized["system_type"] is not None:
                s_type = str(sanitized.get("system_type")).strip().upper()
                if s_type not in ("EMITTER", "HAIR"):
                    raise ValueError(f"Unsupported system_type '{s_type}'. Allowed: EMITTER, HAIR.")
                sanitized["system_type"] = s_type
            elif act == "create":
                s_type = "EMITTER"
                sanitized["system_type"] = s_type

            if "hair_length" in sanitized and sanitized["hair_length"] is not None:
                hl_val = float(sanitized["hair_length"])
                if hl_val < 0.0001 or hl_val > 10000.0:
                    raise ValueError(f"Parameter 'hair_length' must be between 0.0001 and 10000.0, got {hl_val}.")

            if "hair_step" in sanitized and sanitized["hair_step"] is not None:
                hs_val = int(sanitized["hair_step"])
                if hs_val < 1 or hs_val > 7:
                    raise ValueError(f"Parameter 'hair_step' must be between 1 and 7, got {hs_val}.")

            if "hair_dynamics_quality" in sanitized and sanitized["hair_dynamics_quality"] is not None:
                hdq_val = int(sanitized["hair_dynamics_quality"])
                if hdq_val < 1 or hdq_val > 80:
                    raise ValueError(f"Parameter 'hair_dynamics_quality' must be between 1 and 80, got {hdq_val}.")

            if "hair_dynamics_mass" in sanitized and sanitized["hair_dynamics_mass"] is not None:
                hdm_val = float(sanitized["hair_dynamics_mass"])
                if hdm_val < 0.0001 or hdm_val > 10000.0:
                    raise ValueError(f"Parameter 'hair_dynamics_mass' must be between 0.0001 and 10000.0, got {hdm_val}.")

            if "hair_dynamics_bending_stiffness" in sanitized and sanitized["hair_dynamics_bending_stiffness"] is not None:
                hdb_val = float(sanitized["hair_dynamics_bending_stiffness"])
                if hdb_val < 0.0 or hdb_val > 10000.0:
                    raise ValueError(f"Parameter 'hair_dynamics_bending_stiffness' must be between 0.0 and 10000.0, got {hdb_val}.")

            if "hair_dynamics_air_damping" in sanitized and sanitized["hair_dynamics_air_damping"] is not None:
                hda_val = float(sanitized["hair_dynamics_air_damping"])
                if hda_val < 0.0 or hda_val > 10.0:
                    raise ValueError(f"Parameter 'hair_dynamics_air_damping' must be between 0.0 and 10.0, got {hda_val}.")

            if "hair_dynamics_pin_stiffness" in sanitized and sanitized["hair_dynamics_pin_stiffness"] is not None:
                hdp_val = float(sanitized["hair_dynamics_pin_stiffness"])
                if hdp_val < 0.0 or hdp_val > 10000.0:
                    raise ValueError(f"Parameter 'hair_dynamics_pin_stiffness' must be between 0.0 and 10000.0, got {hdp_val}.")

            if "count" in sanitized and sanitized["count"] is not None:
                c_val = int(sanitized["count"])
                if c_val < 1 or c_val > 1000000:
                    raise ValueError(f"Parameter 'count' must be between 1 and 1000000, got {c_val}.")

            if "lifetime" in sanitized and sanitized["lifetime"] is not None:
                lt_val = float(sanitized["lifetime"])
                if lt_val < 0.1 or lt_val > 100000.0:
                    raise ValueError(f"Parameter 'lifetime' must be between 0.1 and 100000.0, got {lt_val}.")

            if "lifetime_random" in sanitized and sanitized["lifetime_random"] is not None:
                ltr_val = float(sanitized["lifetime_random"])
                if ltr_val < 0.0 or ltr_val > 1.0:
                    raise ValueError(f"Parameter 'lifetime_random' must be between 0.0 and 1.0, got {ltr_val}.")

            f_start = sanitized.get("frame_start")
            f_end = sanitized.get("frame_end")
            if f_start is not None and f_end is not None:
                if float(f_end) < float(f_start):
                    raise ValueError(f"Parameter 'frame_end' ({f_end}) must be >= 'frame_start' ({f_start}).")

            if "normal_factor" in sanitized and sanitized["normal_factor"] is not None:
                nf_val = float(sanitized["normal_factor"])
                if nf_val < -1000.0 or nf_val > 1000.0:
                    raise ValueError(f"Parameter 'normal_factor' must be between -1000.0 and 1000.0, got {nf_val}.")

            if "tangent_factor" in sanitized and sanitized["tangent_factor"] is not None:
                tf_val = float(sanitized["tangent_factor"])
                if tf_val < -1000.0 or tf_val > 1000.0:
                    raise ValueError(f"Parameter 'tangent_factor' must be between -1000.0 and 1000.0, got {tf_val}.")

            if "object_factor" in sanitized and sanitized["object_factor"] is not None:
                of_val = float(sanitized["object_factor"])
                if of_val < 0.0 or of_val > 1000.0:
                    raise ValueError(f"Parameter 'object_factor' must be between 0.0 and 1000.0, got {of_val}.")

            if "factor_random" in sanitized and sanitized["factor_random"] is not None:
                fr_val = float(sanitized["factor_random"])
                if fr_val < 0.0 or fr_val > 1000.0:
                    raise ValueError(f"Parameter 'factor_random' must be between 0.0 and 1000.0, got {fr_val}.")

            if "particle_size" in sanitized and sanitized["particle_size"] is not None:
                ps_val = float(sanitized["particle_size"])
                if ps_val < 0.0001 or ps_val > 1000.0:
                    raise ValueError(f"Parameter 'particle_size' must be between 0.0001 and 1000.0, got {ps_val}.")

            if "size_random" in sanitized and sanitized["size_random"] is not None:
                sr_val = float(sanitized["size_random"])
                if sr_val < 0.0 or sr_val > 1.0:
                    raise ValueError(f"Parameter 'size_random' must be between 0.0 and 1.0, got {sr_val}.")

            if "render_type" in sanitized and sanitized["render_type"] is not None:
                rt_val = str(sanitized["render_type"]).strip().upper()
                if rt_val not in ("NONE", "HALO", "LINE", "PATH", "OBJECT", "COLLECTION"):
                    raise ValueError(f"Unsupported render_type '{rt_val}'. Allowed: NONE, HALO, LINE, PATH, OBJECT, COLLECTION.")
                if s_type == "HAIR" and rt_val in ("HALO", "LINE"):
                    raise ValueError(f"Unsupported render_type '{rt_val}' for HAIR system. Allowed: NONE, PATH, OBJECT, COLLECTION.")
                sanitized["render_type"] = rt_val

            if "physics_type" in sanitized and sanitized["physics_type"] is not None:
                pt_val = str(sanitized["physics_type"]).strip().upper()
                if pt_val not in ("NEWTON", "NO", "KEYED", "BOIDS", "FLUID"):
                    raise ValueError(f"Unsupported physics_type '{pt_val}' for particle system. Allowed: NEWTON, NO, KEYED, BOIDS, FLUID.")
                sanitized["physics_type"] = pt_val

    # Tool-specific validation for configure_fluid_simulation and inspect_fluid_simulation
    if tool_name in (TOOL_CONFIGURE_FLUID_SIMULATION, TOOL_INSPECT_FLUID_SIMULATION):
        name_val = sanitized.get("object_name") or sanitized.get("name")
        if name_val is not None:
            sanitized["object_name"] = str(name_val).strip()
            sanitized["name"] = sanitized["object_name"]

        act = str(sanitized.get("action", "create")).strip().lower()
        if act in ("add", "new"):
            act = "create"
        elif act in ("delete",):
            act = "remove"
        if act not in ("create", "configure", "inspect", "remove"):
            raise ValueError(f"Unsupported action '{act}' for {tool_name}. Allowed: create, configure, inspect, remove.")
        sanitized["action"] = act

        if tool_name == TOOL_CONFIGURE_FLUID_SIMULATION and act in ("create", "configure"):
            ft = None
            if "fluid_type" in sanitized and sanitized["fluid_type"] is not None:
                ft = str(sanitized["fluid_type"]).strip().upper()
                if ft not in ("DOMAIN", "FLOW", "EFFECTOR"):
                    raise ValueError(f"Unsupported fluid_type '{ft}'. Allowed: DOMAIN, FLOW, EFFECTOR.")
                sanitized["fluid_type"] = ft
            elif act == "create":
                ft = "DOMAIN"
                sanitized["fluid_type"] = ft

            dt = None
            if "domain_type" in sanitized and sanitized["domain_type"] is not None:
                dt = str(sanitized["domain_type"]).strip().upper()
                if dt not in ("GAS", "LIQUID"):
                    raise ValueError(f"Unsupported domain_type '{dt}'. Allowed: GAS, LIQUID.")
                sanitized["domain_type"] = dt

            flt = None
            if "flow_type" in sanitized and sanitized["flow_type"] is not None:
                flt = str(sanitized["flow_type"]).strip().upper()
                if flt not in ("SMOKE", "BOTH", "FIRE", "LIQUID"):
                    raise ValueError(f"Unsupported flow_type '{flt}'. Allowed: SMOKE, BOTH, FIRE, LIQUID.")
                sanitized["flow_type"] = flt

            if "flow_behavior" in sanitized and sanitized["flow_behavior"] is not None:
                fb = str(sanitized["flow_behavior"]).strip().upper()
                if fb not in ("INFLOW", "OUTFLOW", "GEOMETRY"):
                    raise ValueError(f"Unsupported flow_behavior '{fb}'. Allowed: INFLOW, OUTFLOW, GEOMETRY.")
                sanitized["flow_behavior"] = fb

            if "effector_type" in sanitized and sanitized["effector_type"] is not None:
                et = str(sanitized["effector_type"]).strip().upper()
                if et not in ("COLLISION", "GUIDE"):
                    raise ValueError(f"Unsupported effector_type '{et}'. Allowed: COLLISION, GUIDE.")
                sanitized["effector_type"] = et

            if "simulation_method" in sanitized and sanitized["simulation_method"] is not None:
                sm = str(sanitized["simulation_method"]).strip().upper()
                if sm not in ("FLIP", "APIC"):
                    raise ValueError(f"Unsupported simulation_method '{sm}'. Allowed: FLIP, APIC.")
                sanitized["simulation_method"] = sm

            if "cache_type" in sanitized and sanitized["cache_type"] is not None:
                ct = str(sanitized["cache_type"]).strip().upper()
                if ct not in ("REPLAY", "MODULAR", "ALL"):
                    raise ValueError(f"Unsupported cache_type '{ct}'. Allowed: REPLAY, MODULAR, ALL.")
                sanitized["cache_type"] = ct

            if "resolution_max" in sanitized and sanitized["resolution_max"] is not None:
                res_val = int(sanitized["resolution_max"])
                if res_val < 16 or res_val > 256:
                    raise ValueError(f"Parameter 'resolution_max' must be between 16 and 256, got {res_val}.")

            c_start = sanitized.get("cache_frame_start")
            c_end = sanitized.get("cache_frame_end")
            if c_start is not None and c_end is not None:
                if int(c_end) < int(c_start):
                    raise ValueError(f"Parameter 'cache_frame_end' ({c_end}) must be >= cache_frame_start ({c_start}).")
                span = int(c_end) - int(c_start)
                if span > 250:
                    raise ValueError(f"Cache frame span ({span}) exceeds maximum allowed safe limit of 250 frames.")

            ts_min = sanitized.get("timesteps_min")
            ts_max = sanitized.get("timesteps_max")
            if ts_min is not None and ts_max is not None:
                if int(ts_max) < int(ts_min):
                    raise ValueError(f"Parameter 'timesteps_max' ({ts_max}) must be >= timesteps_min ({ts_min}).")

            if dt and flt:
                if dt == "GAS" and flt == "LIQUID":
                    raise ValueError("Incompatible fluid configuration: flow_type 'LIQUID' cannot be used with domain_type 'GAS'.")
                if dt == "LIQUID" and flt in ("SMOKE", "FIRE", "BOTH"):
                    raise ValueError(f"Incompatible fluid configuration: flow_type '{flt}' cannot be used with domain_type 'LIQUID'.")

    # Tool-specific validation for open_blend_file and aliases
    if tool_name in (TOOL_OPEN_BLEND_FILE, TOOL_OPEN_PROJECT, TOOL_LOAD_BLEND_FILE):
        o_path = str(sanitized.get("filepath", "")).strip()
        if not o_path:
            raise ValueError(f"Parameter 'filepath' cannot be empty for {tool_name}.")
        if "confirm_discard_unsaved" in sanitized and not isinstance(sanitized["confirm_discard_unsaved"], bool):
            raise ValueError(f"Parameter 'confirm_discard_unsaved' must be a boolean for {tool_name}.")
        if "use_scripts" in sanitized and not isinstance(sanitized["use_scripts"], bool):
            raise ValueError(f"Parameter 'use_scripts' must be a boolean for {tool_name}.")

    # Apply defaults for missing optional properties

    for key, prop_spec in properties.items():
        if key not in sanitized and "default" in prop_spec:
            if tool_name in (TOOL_CONFIGURE_PHYSICS, TOOL_SETUP_PHYSICS, TOOL_MANAGE_PHYSICS, TOOL_CONFIGURE_FORCE_FIELD, TOOL_CONFIGURE_PARTICLE_SYSTEM, TOOL_CONFIGURE_FLUID_SIMULATION) and sanitized.get("action") == "configure":
                if tool_name == TOOL_CONFIGURE_PARTICLE_SYSTEM:
                    if key not in ("action", "approved", "name", "object_name", "system_name"):
                        continue
                elif tool_name == TOOL_CONFIGURE_FLUID_SIMULATION:
                    if key not in ("action", "approved", "name", "object_name"):
                        continue
                else:
                    if key not in ("physics_type", "action", "approved", "field_type", "name", "object_name", "system_name"):
                        continue
            if tool_name == TOOL_CONFIGURE_PARTICLE_SYSTEM and sanitized.get("system_type", "EMITTER") != "HAIR":
                if key in ("hair_length", "hair_step", "use_hair_dynamics", "hair_dynamics_quality", "hair_dynamics_mass", "hair_dynamics_bending_stiffness", "hair_dynamics_air_damping", "hair_dynamics_pin_stiffness"):
                    continue
            if tool_name == TOOL_CONFIGURE_PARTICLE_SYSTEM and sanitized.get("system_type") == "HAIR" and key == "render_type":
                sanitized[key] = "PATH"
                continue
            if tool_name == TOOL_CONFIGURE_FORCE_FIELD and key == "inflow" and "flow" in sanitized:
                continue
            if tool_name == TOOL_CONFIGURE_FORCE_FIELD and key == "flow" and "inflow" in sanitized:
                continue
            sanitized[key] = prop_spec["default"]

    # Primitive-specific default assignment and dimension resolution for create_primitive
    if tool_name == TOOL_CREATE_PRIMITIVE:
        prim_type = sanitized.get("primitive_type", "").lower()
        if prim_type == "sphere":
            if "radius" not in sanitized:
                sanitized["radius"] = 0.5
            if "segments" not in sanitized:
                sanitized["segments"] = 32
            if "ring_count" not in sanitized:
                sanitized["ring_count"] = 16
            if "dimensions" not in params:
                r = float(sanitized["radius"])
                sanitized["dimensions"] = [round(r * 2.0, 4), round(r * 2.0, 4), round(r * 2.0, 4)]
        elif prim_type == "cylinder":
            if "radius" not in sanitized:
                sanitized["radius"] = 0.5
            if "depth" not in sanitized:
                sanitized["depth"] = 1.0
            if "vertices" not in sanitized:
                sanitized["vertices"] = 32
            if "dimensions" not in params:
                r = float(sanitized["radius"])
                d = float(sanitized["depth"])
                sanitized["dimensions"] = [round(r * 2.0, 4), round(r * 2.0, 4), round(d, 4)]
        elif prim_type == "plane":
            if "size" not in sanitized:
                sanitized["size"] = 1.0
            if "dimensions" not in params:
                s = float(sanitized["size"])
                sanitized["dimensions"] = [round(s, 4), round(s, 4), 0.0001]
        elif prim_type == "cone":
            if "radius" not in sanitized:
                sanitized["radius"] = 1.0
            if "depth" not in sanitized:
                sanitized["depth"] = 2.0
            if "vertices" not in sanitized:
                sanitized["vertices"] = 32
            if "dimensions" not in params:
                r = float(sanitized["radius"])
                d = float(sanitized["depth"])
                sanitized["dimensions"] = [round(r * 2.0, 4), round(r * 2.0, 4), round(d, 4)]
        elif prim_type == "torus":
            if "radius" not in sanitized:
                sanitized["radius"] = 1.0
            if "segments" not in sanitized:
                sanitized["segments"] = 48
            if "ring_count" not in sanitized:
                sanitized["ring_count"] = 12
            if "dimensions" not in params:
                r = float(sanitized["radius"])
                sanitized["dimensions"] = [round(r * 2.0, 4), round(r * 2.0, 4), round(r * 0.5, 4)]
        elif prim_type in ("monkey", "grid"):
            if "size" not in sanitized:
                sanitized["size"] = 2.0
            if prim_type == "grid":
                if "segments" not in sanitized:
                    sanitized["segments"] = 10
                if "ring_count" not in sanitized:
                    sanitized["ring_count"] = 10
            if "dimensions" not in params:
                s = float(sanitized["size"])
                sanitized["dimensions"] = [round(s, 4), round(s, 4), 0.0001 if prim_type == "grid" else round(s, 4)]
        elif prim_type == "cube":
            if "dimensions" not in params:
                sanitized["dimensions"] = [1.0, 1.0, 1.0]


    # Tool-specific validation for optimize_mesh_silhouette
    if tool_name == TOOL_OPTIMIZE_MESH_SILHOUETTE:
        tgt = str(sanitized.get("target_object", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for optimize_mesh_silhouette.")
        sanitized["target_object"] = tgt

        views_list = sanitized.get("views")
        if views_list is not None:
            if not isinstance(views_list, (list, tuple)) or len(views_list) < 2 or len(views_list) > 3:
                raise ValueError("Parameter 'views' must be a list containing 2 or 3 view configurations.")
            seen_views = set()
            sanitized_views = []
            for idx, vc in enumerate(views_list):
                if not isinstance(vc, dict):
                    raise ValueError(f"View configuration at index {idx} must be a dictionary.")
                v_name = str(vc.get("view", "")).strip().upper()
                if v_name not in ("FRONT", "SIDE", "TOP"):
                    raise ValueError(f"View at index {idx} has invalid 'view' '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                if v_name in seen_views:
                    raise ValueError(f"Duplicate view '{v_name}' found in views list at index {idx}. Each view must be distinct.")
                seen_views.add(v_name)
                v_ref = str(vc.get("reference_image_path", "")).strip()
                if not v_ref:
                    raise ValueError(f"View '{v_name}' requires non-empty 'reference_image_path'.")
                weight = float(vc.get("weight", 1.0))
                regr_tol = float(vc.get("max_regression_tolerance", 0.01))
                csys = str(vc.get("coordinate_system", "UV")).strip().upper()
                cbox = vc.get("crop_box")
                sanitized_views.append({
                    "view": v_name,
                    "reference_image_path": v_ref,
                    "weight": weight,
                    "max_regression_tolerance": regr_tol,
                    "coordinate_system": csys,
                    "crop_box": cbox,
                })
            sanitized["views"] = sanitized_views

        r_path = str(sanitized.get("reference_image_path", "")).strip()
        if not r_path and sanitized.get("views"):
            r_path = sanitized["views"][0]["reference_image_path"]
        if not r_path:
            raise ValueError("Parameter 'reference_image_path' is required for optimize_mesh_silhouette.")
        sanitized["reference_image_path"] = r_path

        view = str(sanitized.get("view", "FRONT")).strip().upper()
        if view not in ("FRONT", "SIDE", "TOP"):
            raise ValueError(f"Invalid view '{view}'. Allowed views: ['FRONT', 'SIDE', 'TOP'].")
        sanitized["view"] = view

        mode = str(sanitized.get("optimization_mode", "BOUNDED_SCALE_TRANSLATE")).strip().upper()
        if mode not in ("BOUNDED_SCALE_TRANSLATE", "VERTEX_DISPLACEMENT", "HYBRID"):
            raise ValueError(f"Invalid optimization_mode '{mode}'. Allowed: ['BOUNDED_SCALE_TRANSLATE', 'VERTEX_DISPLACEMENT', 'HYBRID'].")
        sanitized["optimization_mode"] = mode

        if "crop_box" in sanitized and sanitized["crop_box"] is not None:
            cbox = sanitized["crop_box"]
            if not isinstance(cbox, (list, tuple)) or len(cbox) != 4 or not all(
                isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in cbox
            ):
                raise ValueError("Parameter 'crop_box' must be a 4-element numeric array [u_min, v_min, u_max, v_max].")
            u_min, v_min, u_max, v_max = [float(c) for c in cbox]
            if not (0.0 <= u_min <= 1.0 and 0.0 <= v_min <= 1.0 and 0.0 <= u_max <= 1.0 and 0.0 <= v_max <= 1.0):
                raise ValueError("All crop_box values must be normalized floats between 0.0 and 1.0.")
            if u_min >= u_max:
                raise ValueError(f"Invalid crop_box: u_min ({u_min}) must be strictly less than u_max ({u_max}).")
            if v_min >= v_max:
                raise ValueError(f"Invalid crop_box: v_min ({v_min}) must be strictly less than v_max ({v_max}).")
            sanitized["crop_box"] = [u_min, v_min, u_max, v_max]

        csys = str(sanitized.get("coordinate_system", "UV")).strip().upper()
        if csys not in ("UV", "IMAGE_SPACE"):
            raise ValueError(f"Invalid coordinate_system '{csys}'. Allowed: ['UV', 'IMAGE_SPACE'].")
        sanitized["coordinate_system"] = csys

        if "max_iterations" in sanitized:
            max_iter = int(sanitized["max_iterations"])
            if max_iter < 1 or max_iter > 20:
                raise ValueError("Parameter 'max_iterations' must be an integer between 1 and 20.")
            sanitized["max_iterations"] = max_iter

        if "max_displacement" in sanitized:
            max_disp = float(sanitized["max_displacement"])
            if not math.isfinite(max_disp) or max_disp <= 0.0 or max_disp > 10.0:
                raise ValueError("Parameter 'max_displacement' must be a positive float <= 10.0.")
            sanitized["max_displacement"] = max_disp

        if "step_size" in sanitized:
            step_s = float(sanitized["step_size"])
            if not math.isfinite(step_s) or step_s <= 0.0 or step_s > 5.0:
                raise ValueError("Parameter 'step_size' must be a positive float <= 5.0.")
            sanitized["step_size"] = step_s

        if "tolerance" in sanitized:
            tol = float(sanitized["tolerance"])
            if not math.isfinite(tol) or tol < 0.0 or tol > 1.0:
                raise ValueError("Parameter 'tolerance' must be a float between 0.0 and 1.0.")
            sanitized["tolerance"] = tol

        if "resolution" in sanitized:
            res = int(sanitized["resolution"])
            if res < 64 or res > 2048:
                raise ValueError("Parameter 'resolution' must be an integer between 64 and 2048.")
            sanitized["resolution"] = res

        if "mask_threshold" in sanitized:
            m_thresh = float(sanitized["mask_threshold"])
            if not math.isfinite(m_thresh) or m_thresh < 0.0 or m_thresh > 1.0:
                raise ValueError("Parameter 'mask_threshold' must be a float between 0.0 and 1.0.")
            sanitized["mask_threshold"] = m_thresh

        if "subdivision_levels" in sanitized:
            s_lvl = int(sanitized["subdivision_levels"])
            if s_lvl < 1 or s_lvl > 4:
                raise ValueError("Parameter 'subdivision_levels' must be an integer between 1 and 4.")
            sanitized["subdivision_levels"] = s_lvl

        if "subdivision_type" in sanitized:
            s_type = str(sanitized["subdivision_type"]).strip().upper()
            if s_type not in ("CATMULL_CLARK", "SIMPLE"):
                raise ValueError(f"Invalid subdivision_type '{s_type}'. Allowed: ['CATMULL_CLARK', 'SIMPLE'].")
            sanitized["subdivision_type"] = s_type

        if "refinement_mode" in sanitized:
            sanitized["refinement_mode"] = str(sanitized["refinement_mode"]).strip().upper()
        if "brush_type" in sanitized:
            b_type = str(sanitized["brush_type"]).strip().upper()
            if b_type not in ("GRAB", "INFLATE", "SMOOTH", "CLAY", "DRAW"):
                raise ValueError(f"Invalid brush_type '{b_type}'. Allowed: ['GRAB', 'INFLATE', 'SMOOTH', 'CLAY', 'DRAW'].")
            sanitized["brush_type"] = b_type


    # Tool-specific validation for fit_multiview_silhouette
    if tool_name == TOOL_FIT_MULTIVIEW_SILHOUETTE:
        tgt = str(sanitized.get("target_object", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for fit_multiview_silhouette.")
        sanitized["target_object"] = tgt

        views_list = sanitized.get("views")
        if not isinstance(views_list, (list, tuple)) or len(views_list) < 2 or len(views_list) > 3:
            raise ValueError("Parameter 'views' must be a list containing 2 or 3 view configurations.")

        seen_views = set()
        sanitized_views = []
        for idx, vc in enumerate(views_list):
            if not isinstance(vc, dict):
                raise ValueError(f"View configuration at index {idx} must be a dictionary.")
            v_name = str(vc.get("view", "")).strip().upper()
            if v_name not in ("FRONT", "SIDE", "TOP"):
                raise ValueError(f"View at index {idx} has invalid 'view' '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
            if v_name in seen_views:
                raise ValueError(f"Duplicate view '{v_name}' found in views list at index {idx}. Each view must be distinct.")
            seen_views.add(v_name)

            r_path = str(vc.get("reference_image_path", "")).strip()
            if not r_path:
                raise ValueError(f"View '{v_name}' requires non-empty 'reference_image_path'.")

            weight = float(vc.get("weight", 1.0))
            if not math.isfinite(weight) or weight <= 0.0 or weight > 10.0:
                raise ValueError(f"View '{v_name}' weight must be a positive float <= 10.0.")

            regr_tol = float(vc.get("max_regression_tolerance", 0.01))
            if not math.isfinite(regr_tol) or regr_tol < 0.0 or regr_tol > 0.5:
                raise ValueError(f"View '{v_name}' max_regression_tolerance must be a float between 0.0 and 0.5.")

            csys = str(vc.get("coordinate_system", "UV")).strip().upper()
            if csys not in ("UV", "IMAGE_SPACE"):
                raise ValueError(f"View '{v_name}' has invalid coordinate_system '{csys}'.")

            cbox = vc.get("crop_box")
            if cbox is not None:
                if not isinstance(cbox, (list, tuple)) or len(cbox) != 4 or not all(
                    isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in cbox
                ):
                    raise ValueError(f"View '{v_name}' crop_box must be a 4-element numeric array.")
                u_min, v_min, u_max, v_max = [float(c) for c in cbox]
                if not (0.0 <= u_min <= 1.0 and 0.0 <= v_min <= 1.0 and 0.0 <= u_max <= 1.0 and 0.0 <= v_max <= 1.0):
                    raise ValueError(f"View '{v_name}' crop_box values must be normalized between 0.0 and 1.0.")
                if u_min >= u_max or v_min >= v_max:
                    raise ValueError(f"View '{v_name}' has invalid crop_box bounds (u_min >= u_max or v_min >= v_max).")
                cbox = [u_min, v_min, u_max, v_max]

            san_vc = {
                "view": v_name,
                "reference_image_path": r_path,
                "weight": weight,
                "max_regression_tolerance": regr_tol,
                "coordinate_system": csys,
                "crop_box": cbox,
            }
            if "camera_name" in vc:
                san_vc["camera_name"] = str(vc["camera_name"]).strip()
            sanitized_views.append(san_vc)

        sanitized["views"] = sanitized_views

        obj_func = str(sanitized.get("objective", "WEIGHTED_IOU")).strip().upper()
        if obj_func not in ("WEIGHTED_IOU", "MIN_IOU", "WEIGHTED_DICE"):
            raise ValueError(f"Invalid objective '{obj_func}'. Allowed: ['WEIGHTED_IOU', 'MIN_IOU', 'WEIGHTED_DICE'].")
        sanitized["objective"] = obj_func



        mode = str(sanitized.get("optimization_mode", "BOUNDED_SCALE_TRANSLATE")).strip().upper()
        if mode not in ("BOUNDED_SCALE_TRANSLATE", "VERTEX_DISPLACEMENT", "HYBRID"):
            raise ValueError(f"Invalid optimization_mode '{mode}'. Allowed: ['BOUNDED_SCALE_TRANSLATE', 'VERTEX_DISPLACEMENT', 'HYBRID'].")
        sanitized["optimization_mode"] = mode

        if "max_iterations" in sanitized:
            max_iter = int(sanitized["max_iterations"])
            if max_iter < 1 or max_iter > 20:
                raise ValueError("Parameter 'max_iterations' must be an integer between 1 and 20.")
            sanitized["max_iterations"] = max_iter

        if "max_displacement" in sanitized:
            max_disp = float(sanitized["max_displacement"])
            if not math.isfinite(max_disp) or max_disp <= 0.0 or max_disp > 10.0:
                raise ValueError("Parameter 'max_displacement' must be a positive float <= 10.0.")
            sanitized["max_displacement"] = max_disp

        if "step_size" in sanitized:
            step_s = float(sanitized["step_size"])
            if not math.isfinite(step_s) or step_s <= 0.0 or step_s > 5.0:
                raise ValueError("Parameter 'step_size' must be a positive float <= 5.0.")
            sanitized["step_size"] = step_s

        if "tolerance" in sanitized:
            tol = float(sanitized["tolerance"])
            if not math.isfinite(tol) or tol < 0.0 or tol > 1.0:
                raise ValueError("Parameter 'tolerance' must be a float between 0.0 and 1.0.")
            sanitized["tolerance"] = tol

        if "resolution" in sanitized:
            res = int(sanitized["resolution"])
            if res < 64 or res > 2048:
                raise ValueError("Parameter 'resolution' must be an integer between 64 and 2048.")
            sanitized["resolution"] = res

        if "mask_threshold" in sanitized:
            m_thresh = float(sanitized["mask_threshold"])
            if not math.isfinite(m_thresh) or m_thresh < 0.0 or m_thresh > 1.0:
                raise ValueError("Parameter 'mask_threshold' must be a float between 0.0 and 1.0.")
            sanitized["mask_threshold"] = m_thresh

    if tool_name == TOOL_REFINE_MESH_MULTIRESOLUTION:
        tgt = str(sanitized.get("target_object", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for refine_mesh_multiresolution.")
        sanitized["target_object"] = tgt

        views_list = sanitized.get("views")
        if views_list is not None:
            if not isinstance(views_list, (list, tuple)) or len(views_list) < 1 or len(views_list) > 3:
                raise ValueError("Parameter 'views' must be a list containing 1 to 3 view configurations.")
            seen_views = set()
            sanitized_views = []
            for idx, vc in enumerate(views_list):
                if not isinstance(vc, dict):
                    raise ValueError(f"View configuration at index {idx} must be a dictionary.")
                v_name = str(vc.get("view", "")).strip().upper()
                if v_name not in ("FRONT", "SIDE", "TOP"):
                    raise ValueError(f"View at index {idx} has invalid 'view' '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                if v_name in seen_views:
                    raise ValueError(f"Duplicate view '{v_name}' found in views list at index {idx}. Each view must be distinct.")
                seen_views.add(v_name)

                r_path = str(vc.get("reference_image_path", "")).strip()
                if not r_path:
                    raise ValueError(f"View '{v_name}' requires non-empty 'reference_image_path'.")

                weight = float(vc.get("weight", 1.0))
                if not math.isfinite(weight) or weight <= 0.0 or weight > 10.0:
                    raise ValueError(f"View '{v_name}' weight must be a positive float <= 10.0.")

                regr_tol = float(vc.get("max_regression_tolerance", 0.01))
                if not math.isfinite(regr_tol) or regr_tol < 0.0 or regr_tol > 0.5:
                    raise ValueError(f"View '{v_name}' max_regression_tolerance must be a float between 0.0 and 0.5.")

                csys = str(vc.get("coordinate_system", "UV")).strip().upper()
                if csys not in ("UV", "IMAGE_SPACE"):
                    raise ValueError(f"View '{v_name}' has invalid coordinate_system '{csys}'.")

                cbox = vc.get("crop_box")
                if cbox is not None:
                    if not isinstance(cbox, (list, tuple)) or len(cbox) != 4 or not all(
                        isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in cbox
                    ):
                        raise ValueError(f"View '{v_name}' crop_box must be a 4-element numeric array.")
                    u_min, v_min, u_max, v_max = [float(c) for c in cbox]
                    if not (0.0 <= u_min <= 1.0 and 0.0 <= v_min <= 1.0 and 0.0 <= u_max <= 1.0 and 0.0 <= v_max <= 1.0):
                        raise ValueError(f"View '{v_name}' crop_box values must be normalized between 0.0 and 1.0.")
                    if u_min >= u_max or v_min >= v_max:
                        raise ValueError(f"View '{v_name}' has invalid crop_box bounds (u_min >= u_max or v_min >= v_max).")
                    cbox = [u_min, v_min, u_max, v_max]

                san_vc = {
                    "view": v_name,
                    "reference_image_path": r_path,
                    "weight": weight,
                    "max_regression_tolerance": regr_tol,
                    "coordinate_system": csys,
                    "crop_box": cbox,
                }
                if "camera_name" in vc:
                    san_vc["camera_name"] = str(vc["camera_name"]).strip()
                sanitized_views.append(san_vc)
            sanitized["views"] = sanitized_views
        else:
            r_path = str(sanitized.get("reference_image_path", "")).strip()
            if not r_path:
                raise ValueError("Either 'views' or 'reference_image_path' is required for refine_mesh_multiresolution.")
            v_name = str(sanitized.get("view", "FRONT")).strip().upper()
            if v_name not in ("FRONT", "SIDE", "TOP"):
                raise ValueError(f"Invalid view '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
            sanitized["views"] = [{
                "view": v_name,
                "reference_image_path": r_path,
                "weight": 1.0,
                "max_regression_tolerance": float(sanitized.get("max_regression_tolerance", 0.01)),
                "coordinate_system": str(sanitized.get("coordinate_system", "UV")).strip().upper(),
                "crop_box": sanitized.get("crop_box"),
                "camera_name": sanitized.get("camera_name"),
            }]

        sub_type = str(sanitized.get("subdivision_type", "CATMULL_CLARK")).strip().upper()
        if sub_type not in ("CATMULL_CLARK", "SIMPLE"):
            raise ValueError(f"Invalid subdivision_type '{sub_type}'. Allowed: ['CATMULL_CLARK', 'SIMPLE'].")
        sanitized["subdivision_type"] = sub_type

        sub_levels = int(sanitized.get("subdivision_levels", 1))
        if sub_levels < 1 or sub_levels > 4:
            raise ValueError("Parameter 'subdivision_levels' must be an integer between 1 and 4.")
        sanitized["subdivision_levels"] = sub_levels

        max_v = int(sanitized.get("max_vertex_count", 20000))
        if max_v < 100 or max_v > 100000:
            raise ValueError("Parameter 'max_vertex_count' must be an integer between 100 and 100,000.")
        sanitized["max_vertex_count"] = max_v

        max_f = int(sanitized.get("max_face_count", 20000))
        if max_f < 100 or max_f > 100000:
            raise ValueError("Parameter 'max_face_count' must be an integer between 100 and 100,000.")
        sanitized["max_face_count"] = max_f

        if "max_displacement" in sanitized:
            max_disp = float(sanitized["max_displacement"])
            if not math.isfinite(max_disp) or max_disp <= 0.0 or max_disp > 2.0:
                raise ValueError("Parameter 'max_displacement' must be a positive float <= 2.0.")
            sanitized["max_displacement"] = max_disp

        if "max_iterations" in sanitized:
            max_iter = int(sanitized["max_iterations"])
            if max_iter < 1 or max_iter > 10:
                raise ValueError("Parameter 'max_iterations' must be an integer between 1 and 10.")
            sanitized["max_iterations"] = max_iter

        if "step_size" in sanitized:
            step_s = float(sanitized["step_size"])
            if not math.isfinite(step_s) or step_s <= 0.0 or step_s > 1.0:
                raise ValueError("Parameter 'step_size' must be a positive float <= 1.0.")
            sanitized["step_size"] = step_s

        if "tolerance" in sanitized:
            tol = float(sanitized["tolerance"])
            if not math.isfinite(tol) or tol < 0.0 or tol > 0.5:
                raise ValueError("Parameter 'tolerance' must be a float between 0.0 and 0.5.")
            sanitized["tolerance"] = tol

        if "resolution" in sanitized:
            res = int(sanitized["resolution"])
            if res < 64 or res > 1024:
                raise ValueError("Parameter 'resolution' must be an integer between 64 and 1024.")
            sanitized["resolution"] = res

        obj_func = str(sanitized.get("objective", "WEIGHTED_IOU")).strip().upper()
        if obj_func not in ("WEIGHTED_IOU", "MIN_IOU", "WEIGHTED_DICE"):
            raise ValueError(f"Invalid objective '{obj_func}'. Allowed: ['WEIGHTED_IOU', 'MIN_IOU', 'WEIGHTED_DICE'].")
        sanitized["objective"] = obj_func




    if tool_name == TOOL_SCULPT_ORGANIC_ANATOMY:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for sculpt_organic_anatomy.")
        sanitized["target_object"] = tgt

        b_type = str(sanitized.get("brush_type", "INFLATE")).strip().upper()
        if b_type not in ("GRAB", "INFLATE", "SMOOTH", "CLAY", "DRAW"):
            raise ValueError(f"Invalid brush_type '{b_type}'. Allowed: ['GRAB', 'INFLATE', 'SMOOTH', 'CLAY', 'DRAW'].")
        sanitized["brush_type"] = b_type

        rad = float(sanitized.get("radius", 0.5))
        if not math.isfinite(rad) or rad < 0.001 or rad > 10.0:
            raise ValueError("Parameter 'radius' must be a float between 0.001 and 10.0.")
        sanitized["radius"] = rad

        stren = float(sanitized.get("strength", 0.5))
        if not math.isfinite(stren) or stren < 0.0 or stren > 1.0:
            raise ValueError("Parameter 'strength' must be a float between 0.0 and 1.0.")
        sanitized["strength"] = stren

        max_disp = float(sanitized.get("max_displacement", 0.5))
        if not math.isfinite(max_disp) or max_disp < 0.001 or max_disp > 2.0:
            raise ValueError("Parameter 'max_displacement' must be a float between 0.001 and 2.0.")
        sanitized["max_displacement"] = max_disp

        iters = int(sanitized.get("iterations", 1))
        if iters < 1 or iters > 10:
            raise ValueError("Parameter 'iterations' must be an integer between 1 and 10.")
        sanitized["iterations"] = iters

        pres_topo = bool(sanitized.get("preserve_topology", True))
        dyn_topo = bool(sanitized.get("dynamic_topology", False))
        if pres_topo and dyn_topo:
            raise ValueError("Conflicting parameters: preserve_topology=True but dynamic_topology=True. Dynamic topology alters mesh topology and requires preserve_topology=False.")
        sanitized["preserve_topology"] = pres_topo
        sanitized["dynamic_topology"] = dyn_topo

        max_v = int(sanitized.get("max_vertex_count", 50000))
        if max_v < 100 or max_v > 100000:
            raise ValueError("Parameter 'max_vertex_count' must be an integer between 100 and 100,000.")
        sanitized["max_vertex_count"] = max_v

        max_f = int(sanitized.get("max_face_count", 50000))
        if max_f < 100 or max_f > 100000:
            raise ValueError("Parameter 'max_face_count' must be an integer between 100 and 100,000.")
        sanitized["max_face_count"] = max_f

        sp = sanitized.get("stroke_points")
        if sp is not None:
            if not isinstance(sp, (list, tuple)) or len(sp) < 1 or len(sp) > 64:
                raise ValueError("Parameter 'stroke_points' must be a list containing 1 to 64 coordinates.")
            sanitized_points = []
            for p_idx, pt in enumerate(sp):
                if isinstance(pt, (list, tuple)):
                    if len(pt) not in (2, 3) or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in pt):
                        raise ValueError(f"stroke_point at index {p_idx} must be a 2 or 3-element finite numeric array.")
                    sanitized_points.append([float(c) for c in pt])
                elif isinstance(pt, dict):
                    coords = [pt.get("x"), pt.get("y"), pt.get("z", 0.0)]
                    if any(c is None or isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) for c in coords):
                        raise ValueError(f"stroke_point at index {p_idx} must contain finite numeric 'x', 'y' (and optional 'z').")
                    sanitized_points.append([float(coords[0]), float(coords[1]), float(coords[2])])
                else:
                    raise ValueError(f"stroke_point at index {p_idx} must be an array or dict.")
            sanitized["stroke_points"] = sanitized_points

        sdir = sanitized.get("stroke_direction")
        if sdir is not None:
            if not isinstance(sdir, (list, tuple)) or len(sdir) != 3 or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in sdir):
                raise ValueError("Parameter 'stroke_direction' must be a 3-element finite numeric array.")
            sanitized["stroke_direction"] = [float(c) for c in sdir]

        views_list = sanitized.get("views")
        if views_list is not None:
            if not isinstance(views_list, (list, tuple)) or len(views_list) < 1 or len(views_list) > 3:
                raise ValueError("Parameter 'views' must be a list containing 1 to 3 view configurations.")
            seen_views = set()
            sanitized_views = []
            for idx, vc in enumerate(views_list):
                if not isinstance(vc, dict):
                    raise ValueError(f"View configuration at index {idx} must be a dictionary.")
                v_name = str(vc.get("view", "")).strip().upper()
                if v_name not in ("FRONT", "SIDE", "TOP"):
                    raise ValueError(f"View at index {idx} has invalid 'view' '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                if v_name in seen_views:
                    raise ValueError(f"Duplicate view '{v_name}' found in views list at index {idx}. Each view must be distinct.")
                seen_views.add(v_name)

                r_path = str(vc.get("reference_image_path", "")).strip()
                if not r_path:
                    raise ValueError(f"View '{v_name}' requires non-empty 'reference_image_path'.")

                weight = float(vc.get("weight", 1.0))
                if not math.isfinite(weight) or weight <= 0.0 or weight > 10.0:
                    raise ValueError(f"View '{v_name}' weight must be a positive float <= 10.0.")

                regr_tol = float(vc.get("max_regression_tolerance", 0.01))
                if not math.isfinite(regr_tol) or regr_tol < 0.0 or regr_tol > 0.5:
                    raise ValueError(f"View '{v_name}' max_regression_tolerance must be a float between 0.0 and 0.5.")

                csys = str(vc.get("coordinate_system", "UV")).strip().upper()
                if csys not in ("UV", "IMAGE_SPACE"):
                    raise ValueError(f"View '{v_name}' has invalid coordinate_system '{csys}'.")

                cbox = vc.get("crop_box")
                if cbox is not None:
                    if not isinstance(cbox, (list, tuple)) or len(cbox) != 4 or not all(
                        isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in cbox
                    ):
                        raise ValueError(f"View '{v_name}' crop_box must be a 4-element numeric array.")
                    u_min, v_min, u_max, v_max = [float(c) for c in cbox]
                    if not (0.0 <= u_min <= 1.0 and 0.0 <= v_min <= 1.0 and 0.0 <= u_max <= 1.0 and 0.0 <= v_max <= 1.0):
                        raise ValueError(f"View '{v_name}' crop_box values must be normalized between 0.0 and 1.0.")
                    if u_min >= u_max or v_min >= v_max:
                        raise ValueError(f"View '{v_name}' has invalid crop_box bounds (u_min >= u_max or v_min >= v_max).")
                    cbox = [u_min, v_min, u_max, v_max]

                san_vc = {
                    "view": v_name,
                    "reference_image_path": r_path,
                    "weight": weight,
                    "max_regression_tolerance": regr_tol,
                    "coordinate_system": csys,
                    "crop_box": cbox,
                }
                if "camera_name" in vc:
                    san_vc["camera_name"] = str(vc["camera_name"]).strip()
                sanitized_views.append(san_vc)
            sanitized["views"] = sanitized_views

        obj_func = str(sanitized.get("objective", "WEIGHTED_IOU")).strip().upper()
        if obj_func not in ("WEIGHTED_IOU", "MIN_IOU", "WEIGHTED_DICE"):
            raise ValueError(f"Invalid objective '{obj_func}'. Allowed: ['WEIGHTED_IOU', 'MIN_IOU', 'WEIGHTED_DICE'].")
        sanitized["objective"] = obj_func


    if tool_name == TOOL_CONFIGURE_SEMANTIC_LANDMARKS:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for configure_semantic_landmarks.")
        sanitized["target_object"] = tgt

        action = str(sanitized.get("action", "SET")).strip().upper()
        if action not in ("SET", "UPDATE", "REMOVE", "CLEAR"):
            raise ValueError(f"Invalid action '{action}'. Allowed: ['SET', 'UPDATE', 'REMOVE', 'CLEAR'].")
        sanitized["action"] = action

        if action in ("SET", "UPDATE"):
            lms = sanitized.get("landmarks")
            if not isinstance(lms, (list, tuple)) or len(lms) < 1 or len(lms) > 100:
                raise ValueError(f"Parameter 'landmarks' must be a non-empty list of 1 to 100 landmark definitions for action '{action}'.")
            sanitized["landmarks"] = _validate_and_sanitize_landmarks(lms, action)
        elif action == "REMOVE":
            lms = sanitized.get("landmarks")
            if not isinstance(lms, (list, tuple)) or len(lms) < 1:
                raise ValueError("Parameter 'landmarks' must be a non-empty list of landmark names or objects to remove.")
            sanitized["landmarks"] = _validate_and_sanitize_landmarks(lms, action)
        else:
            sanitized["landmarks"] = []

        if "calibrated_cameras" in sanitized and sanitized["calibrated_cameras"] is not None:
            if not isinstance(sanitized["calibrated_cameras"], dict):
                raise ValueError("Parameter 'calibrated_cameras' must be a dictionary mapping view names to camera names.")

    if tool_name == TOOL_INSPECT_SEMANTIC_LANDMARKS:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for inspect_semantic_landmarks.")
        sanitized["target_object"] = tgt

        if "views" in sanitized and sanitized["views"] is not None:
            v_list = sanitized["views"]
            if not isinstance(v_list, (list, tuple)):
                raise ValueError("Parameter 'views' must be a list of view names.")
            san_views = []
            for v in v_list:
                v_up = str(v).strip().upper()
                if v_up not in ("FRONT", "SIDE", "TOP"):
                    raise ValueError(f"Invalid view '{v_up}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                if v_up not in san_views:
                    san_views.append(v_up)
            sanitized["views"] = san_views
        else:
            sanitized["views"] = ["FRONT", "SIDE", "TOP"]
        sanitized["include_projection_details"] = bool(sanitized.get("include_projection_details", True))

    if tool_name == TOOL_GUIDE_MESH_LANDMARKS:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for guide_mesh_landmarks.")
        sanitized["target_object"] = tgt

        if "landmarks" in sanitized and sanitized["landmarks"] is not None:
            lms = sanitized["landmarks"]
            if not isinstance(lms, (list, tuple)):
                raise ValueError("Parameter 'landmarks' must be a list of landmark definitions.")
            sanitized["landmarks"] = _validate_and_sanitize_landmarks(lms, "SET")

        max_it = int(sanitized.get("max_iterations", 10))
        if max_it < 1 or max_it > 50:
            raise ValueError("Parameter 'max_iterations' must be an integer between 1 and 50.")
        sanitized["max_iterations"] = max_it

        s_size = float(sanitized.get("step_size", 0.2))
        if not math.isfinite(s_size) or s_size < 0.01 or s_size > 1.0:
            raise ValueError("Parameter 'step_size' must be a float between 0.01 and 1.0.")
        sanitized["step_size"] = s_size

        m_disp = float(sanitized.get("max_displacement", 0.5))
        if not math.isfinite(m_disp) or m_disp < 0.001 or m_disp > 2.0:
            raise ValueError("Parameter 'max_displacement' must be a float between 0.001 and 2.0.")
        sanitized["max_displacement"] = m_disp

        inf_r = float(sanitized.get("influence_radius", 0.8))
        if not math.isfinite(inf_r) or inf_r < 0.01 or inf_r > 10.0:
            raise ValueError("Parameter 'influence_radius' must be a float between 0.01 and 10.0.")
        sanitized["influence_radius"] = inf_r

        f_type = str(sanitized.get("falloff_type", "SMOOTH")).strip().upper()
        if f_type not in ("SMOOTH", "LINEAR", "SHARP", "CONSTANT"):
            raise ValueError(f"Invalid falloff_type '{f_type}'. Allowed: ['SMOOTH', 'LINEAR', 'SHARP', 'CONSTANT'].")
        sanitized["falloff_type"] = f_type

        min_red = float(sanitized.get("min_error_reduction", 0.001))
        if not math.isfinite(min_red) or min_red < 0.0 or min_red > 1.0:
            raise ValueError("Parameter 'min_error_reduction' must be a float between 0.0 and 1.0.")
        sanitized["min_error_reduction"] = min_red

        obj_type = str(sanitized.get("objective", "WEIGHTED_LANDMARK_RMSE")).strip().upper()
        if obj_type not in ("WEIGHTED_LANDMARK_RMSE", "MEAN_LANDMARK_ERROR"):
            raise ValueError(f"Invalid objective '{obj_type}'. Allowed: ['WEIGHTED_LANDMARK_RMSE', 'MEAN_LANDMARK_ERROR'].")
        sanitized["objective"] = obj_type

        pres_topo = bool(sanitized.get("preserve_topology", True))
        sanitized["preserve_topology"] = pres_topo

        max_v = int(sanitized.get("max_vertex_count", 50000))
        if max_v < 100 or max_v > 100000:
            raise ValueError("Parameter 'max_vertex_count' must be an integer between 100 and 100,000.")
        sanitized["max_vertex_count"] = max_v

        max_f = int(sanitized.get("max_face_count", 50000))
        if max_f < 100 or max_f > 100000:
            raise ValueError("Parameter 'max_face_count' must be an integer between 100 and 100,000.")
        sanitized["max_face_count"] = max_f

        smooth = float(sanitized.get("laplacian_smoothing", 0.05))
        if not math.isfinite(smooth) or smooth < 0.0 or smooth > 1.0:
            raise ValueError("Parameter 'laplacian_smoothing' must be a float between 0.0 and 1.0.")
        sanitized["laplacian_smoothing"] = smooth

        sanitized["rollback_on_failure"] = bool(sanitized.get("rollback_on_failure", True))
    # Tool-specific validation for VSE tools
    if tool_name == TOOL_INSPECT_VSE_TIMELINE:
        if "include_strips" in sanitized and not isinstance(sanitized["include_strips"], bool):
            raise ValueError("Parameter 'include_strips' must be a boolean.")
        if "include_markers" in sanitized and not isinstance(sanitized["include_markers"], bool):
            raise ValueError("Parameter 'include_markers' must be a boolean.")

    if tool_name == TOOL_CREATE_VSE_STRIP:
        stype = str(sanitized.get("strip_type", "")).strip().upper()
        if stype not in ("COLOR", "TEXT", "IMAGE", "SOUND", "MOVIE"):
            raise ValueError(f"Invalid strip_type '{stype}'. Allowed: ['COLOR', 'TEXT', 'IMAGE', 'SOUND', 'MOVIE'].")
        sanitized["strip_type"] = stype

        chan = sanitized.get("channel")
        if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
            raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")

        f_start = sanitized.get("frame_start")
        if not isinstance(f_start, int) or isinstance(f_start, bool):
            raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")

        if stype in ("IMAGE", "SOUND", "MOVIE"):
            fp = str(sanitized.get("filepath", "")).strip()
            if not fp:
                raise ValueError(f"Parameter 'filepath' cannot be empty for strip_type '{stype}'.")
            if ".." in fp.replace("\\", "/").split("/"):
                raise ValueError("Path traversal sequences ('..') are strictly forbidden in 'filepath'.")
            valid_exts = {
                "IMAGE": (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".tga", ".bmp"),
                "SOUND": (".wav", ".mp3", ".ogg", ".flac", ".aac"),
                "MOVIE": (".mp4", ".mov", ".mkv", ".avi", ".webm"),
            }
            if not fp.lower().endswith(valid_exts[stype]):
                raise ValueError(f"File extension for {stype} strip must be one of {sorted(valid_exts[stype])}, got '{fp}'.")

        if stype == "COLOR" and "color" in sanitized:
            col = sanitized["color"]
            if not isinstance(col, (list, tuple)) or len(col) not in (3, 4):
                raise ValueError("Parameter 'color' must be a list of 3 or 4 floats (RGB or RGBA).")
            for c_val in col:
                if not isinstance(c_val, (int, float)) or isinstance(c_val, bool) or not (0.0 <= c_val <= 1.0):
                    raise ValueError(f"Color components must be floats between 0.0 and 1.0, got {c_val}.")

    if tool_name == TOOL_MODIFY_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for modify_vse_strip.")
        if "channel" in sanitized:
            chan = sanitized["channel"]
            if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
                raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")
        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")
        if "frame_start" in sanitized:
            f_start = sanitized["frame_start"]
            if not isinstance(f_start, int) or isinstance(f_start, bool):
                raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

    if tool_name == TOOL_DELETE_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for delete_vse_strip.")

    if tool_name == TOOL_MANAGE_TIMELINE_MARKERS:
        act = str(sanitized.get("action", "")).strip().lower()
        if act not in ("add", "remove", "list"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['add', 'remove', 'list'].")
        sanitized["action"] = act
        if act in ("add", "remove"):
            m_name = str(sanitized.get("name", "")).strip()
            if not m_name:
                raise ValueError(f"Parameter 'name' cannot be empty for marker action '{act}'.")
        if act == "add":
            if "frame" not in sanitized or not isinstance(sanitized["frame"], int) or isinstance(sanitized["frame"], bool):
                raise ValueError("Parameter 'frame' must be an integer frame number for marker action 'add'.")

    if tool_name == TOOL_TRIM_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for trim_vse_strip.")
        t_mode = str(sanitized.get("trim_mode", "ABSOLUTE")).strip().upper()
        if t_mode not in ("ABSOLUTE", "RELATIVE"):
            raise ValueError(f"Invalid trim_mode '{t_mode}'. Allowed: ['ABSOLUTE', 'RELATIVE'].")
        sanitized["trim_mode"] = t_mode
        if "left_handle" not in sanitized and "right_handle" not in sanitized:
            raise ValueError("At least one of 'left_handle' or 'right_handle' must be specified for trim_vse_strip.")
        if "left_handle" in sanitized and (not isinstance(sanitized["left_handle"], int) or isinstance(sanitized["left_handle"], bool)):
            raise ValueError("Parameter 'left_handle' must be an integer frame value.")
        if "right_handle" in sanitized and (not isinstance(sanitized["right_handle"], int) or isinstance(sanitized["right_handle"], bool)):
            raise ValueError("Parameter 'right_handle' must be an integer frame value.")

    if tool_name == TOOL_SPLIT_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for split_vse_strip.")
        if "split_frame" not in sanitized or not isinstance(sanitized["split_frame"], int) or isinstance(sanitized["split_frame"], bool):
            raise ValueError("Parameter 'split_frame' must be an integer frame number for split_vse_strip.")

    if tool_name == TOOL_REORDER_VSE_STRIPS:
        act = str(sanitized.get("action", "")).strip().upper()
        if act not in ("MOVE", "SWAP", "CLOSE_GAPS", "SNAP"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['MOVE', 'SWAP', 'CLOSE_GAPS', 'SNAP'].")
        sanitized["action"] = act
        if act == "MOVE":
            if not str(sanitized.get("name", "")).strip():
                raise ValueError("Action 'MOVE' requires a non-empty 'name'.")
            if "channel" not in sanitized and "target_frame" not in sanitized:
                raise ValueError("Action 'MOVE' requires at least one of 'channel' or 'target_frame'.")
        elif act == "SWAP":
            s_a = str(sanitized.get("strip_a", "")).strip()
            s_b = str(sanitized.get("strip_b", "")).strip()
            if not s_a or not s_b:
                raise ValueError("Action 'SWAP' requires both 'strip_a' and 'strip_b'.")
            if s_a == s_b:
                raise ValueError("Action 'SWAP' requires distinct strip names.")
        elif act == "CLOSE_GAPS":
            if "channel" not in sanitized or not isinstance(sanitized["channel"], int) or isinstance(sanitized["channel"], bool):
                raise ValueError("Action 'CLOSE_GAPS' requires an integer 'channel' parameter.")
        elif act == "SNAP":
            if not str(sanitized.get("name", "")).strip():
                raise ValueError("Action 'SNAP' requires a non-empty 'name'.")
            snap_to = str(sanitized.get("snap_to", "PREVIOUS_STRIP")).strip().upper()
            if snap_to not in ("PREVIOUS_STRIP", "NEXT_STRIP", "FRAME"):
                raise ValueError(f"Invalid snap_to '{snap_to}'. Allowed: ['PREVIOUS_STRIP', 'NEXT_STRIP', 'FRAME'].")
            sanitized["snap_to"] = snap_to
            if snap_to == "FRAME" and ("target_frame" not in sanitized or not isinstance(sanitized["target_frame"], int) or isinstance(sanitized["target_frame"], bool)):
                raise ValueError("Action 'SNAP' with snap_to='FRAME' requires an integer 'target_frame'.")

    if tool_name == TOOL_CREATE_VSE_TRANSITION:
        t_type = str(sanitized.get("transition_type", "")).strip().upper()
        if t_type not in ("CROSS", "GAMMA_CROSS", "WIPE", "ALPHA_OVER", "ALPHA_UNDER", "COLORMIX"):
            raise ValueError(f"Invalid transition_type '{t_type}'. Allowed: ['CROSS', 'GAMMA_CROSS', 'WIPE', 'ALPHA_OVER', 'ALPHA_UNDER', 'COLORMIX'].")
        sanitized["transition_type"] = t_type
        i1 = str(sanitized.get("input1", "")).strip()
        i2 = str(sanitized.get("input2", "")).strip()
        if not i1 or not i2:
            raise ValueError("Parameters 'input1' and 'input2' cannot be empty for create_vse_transition.")
        if i1 == i2:
            raise ValueError("Transition requires distinct 'input1' and 'input2' strips.")
        if "channel" in sanitized:
            ch = sanitized["channel"]
            if not isinstance(ch, int) or isinstance(ch, bool) or ch < 1 or ch > 128:
                raise ValueError("Parameter 'channel' must be an integer between 1 and 128.")
        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError("Parameter 'duration' must be a positive integer.")
        if t_type == "WIPE":
            if "wipe_type" in sanitized:
                w_type = str(sanitized["wipe_type"]).strip().upper()
                if w_type not in ("SINGLE", "DOUBLE", "IRIS", "CLOCK"):
                    raise ValueError(f"Invalid wipe_type '{w_type}'.")
                sanitized["wipe_type"] = w_type
            if "direction" in sanitized:
                w_dir = str(sanitized["direction"]).strip().upper()
                if w_dir not in ("IN", "OUT"):
                    raise ValueError(f"Invalid direction '{w_dir}'.")
                sanitized["direction"] = w_dir

    if tool_name == TOOL_CONFIGURE_VSE_EFFECT:
        act = str(sanitized.get("action", "")).strip().upper()
        if act not in ("CREATE", "UPDATE", "INSPECT"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['CREATE', 'UPDATE', 'INSPECT'].")
        sanitized["action"] = act
        if act == "CREATE":
            e_type = str(sanitized.get("effect_type", "")).strip().upper()
            if e_type not in ("GAUSSIAN_BLUR", "GLOW", "SPEED", "ADJUSTMENT", "COLORMIX"):
                raise ValueError(f"Invalid effect_type '{e_type}'. Allowed: ['GAUSSIAN_BLUR', 'GLOW', 'SPEED', 'ADJUSTMENT', 'COLORMIX'].")
            sanitized["effect_type"] = e_type
            if e_type in ("GAUSSIAN_BLUR", "GLOW", "SPEED") and not str(sanitized.get("input_strip", "")).strip():
                raise ValueError(f"Effect type '{e_type}' requires 'input_strip'.")
        elif act in ("UPDATE", "INSPECT"):
            if not str(sanitized.get("name", "")).strip():
                raise ValueError(f"Action '{act}' requires a non-empty 'name'.")

    if tool_name == TOOL_CONFIGURE_VSE_AUDIO:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Tool 'configure_vse_audio' requires a non-empty 'name'.")
        act = str(sanitized.get("action", "UPDATE")).strip().upper()
        if act not in ("UPDATE", "INSPECT"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['UPDATE', 'INSPECT'].")
        sanitized["action"] = act
        if "volume" in sanitized:
            vol = sanitized["volume"]
            if not isinstance(vol, (int, float)) or isinstance(vol, bool) or vol < 0.0:
                raise ValueError("Parameter 'volume' must be a non-negative number.")
        if "pan" in sanitized:
            pan = sanitized["pan"]
            if not isinstance(pan, (int, float)) or isinstance(pan, bool) or pan < -1.0 or pan > 1.0:
                raise ValueError("Parameter 'pan' must be a number between -1.0 and 1.0.")

    if tool_name == TOOL_MANAGE_VSE_SOUND_MODIFIERS:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Tool 'manage_vse_sound_modifiers' requires a non-empty 'name'.")
        act = str(sanitized.get("action", "")).strip().upper()
        if act not in ("ADD", "REMOVE", "UPDATE", "LIST"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['ADD', 'REMOVE', 'UPDATE', 'LIST'].")
        sanitized["action"] = act
        if act == "ADD":
            m_type = str(sanitized.get("modifier_type", "")).strip().upper()
            if m_type not in ("SOUND_EQUALIZER", "PITCH", "ECHO"):
                raise ValueError(f"Invalid modifier_type '{m_type}'. Allowed: ['SOUND_EQUALIZER', 'PITCH', 'ECHO'].")
            sanitized["modifier_type"] = m_type
        elif act in ("REMOVE", "UPDATE"):
            if not str(sanitized.get("modifier_name", "")).strip():
                raise ValueError(f"Action '{act}' requires a non-empty 'modifier_name'.")

    if tool_name == TOOL_CREATE_VSE_TEXT_STRIP:
        t_text = str(sanitized.get("text", "")).strip()
        if not t_text:
            raise ValueError("Parameter 'text' cannot be empty for create_vse_text_strip.")
        ch = sanitized.get("channel")
        if not isinstance(ch, int) or isinstance(ch, bool) or ch < 1 or ch > 128:
            raise ValueError("Parameter 'channel' must be an integer between 1 and 128.")
        dur = sanitized.get("duration")
        if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
            raise ValueError("Parameter 'duration' must be a positive integer.")

    if tool_name == TOOL_CONFIGURE_VSE_TEXT_STYLE:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Tool 'configure_vse_text_style' requires a non-empty 'name'.")
        act = str(sanitized.get("action", "UPDATE")).strip().upper()
        if act not in ("UPDATE", "INSPECT"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['UPDATE', 'INSPECT'].")
        sanitized["action"] = act

    if tool_name == TOOL_GROUP_VSE_META_STRIP:
        act = str(sanitized.get("action", "")).strip().upper()
        if act not in ("CREATE", "UNGROUP", "INSPECT"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['CREATE', 'UNGROUP', 'INSPECT'].")
        sanitized["action"] = act
        if act == "CREATE":
            sn = sanitized.get("strip_names")
            if not isinstance(sn, (list, tuple)) or len(sn) == 0:
                raise ValueError("Action 'CREATE' requires a non-empty list of 'strip_names'.")
            sanitized["strip_names"] = [str(s).strip() for s in sn if str(s).strip()]
            if not sanitized["strip_names"]:
                raise ValueError("Action 'CREATE' requires at least one non-empty strip name.")
            if "channel" in sanitized and sanitized["channel"] is not None:
                ch = sanitized["channel"]
                if not isinstance(ch, int) or isinstance(ch, bool) or ch < 1 or ch > 128:
                    raise ValueError("Parameter 'channel' must be an integer between 1 and 128.")
        else:
            s_name = str(sanitized.get("name", "")).strip()
            if not s_name:
                raise ValueError(f"Action '{act}' requires a non-empty 'name'.")
            sanitized["name"] = s_name

    if tool_name == TOOL_CREATE_VSE_SCENE_STRIP:
        sc_name = str(sanitized.get("scene_name", "")).strip()
        if not sc_name:
            raise ValueError("Parameter 'scene_name' cannot be empty for create_vse_scene_strip.")
        ch = sanitized.get("channel")
        if not isinstance(ch, int) or isinstance(ch, bool) or ch < 1 or ch > 128:
            raise ValueError("Parameter 'channel' must be an integer between 1 and 128.")
        if "frame_start" not in sanitized or not isinstance(sanitized["frame_start"], int) or isinstance(sanitized["frame_start"], bool):
            raise ValueError("Parameter 'frame_start' must be an integer.")
        if "duration" in sanitized and sanitized["duration"] is not None:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError("Parameter 'duration' must be a positive integer.")
        if "scene_input" in sanitized and sanitized["scene_input"] is not None:
            si = str(sanitized["scene_input"]).strip().upper()
            if si not in ("CAMERA", "SEQUENCER"):
                raise ValueError(f"Invalid scene_input '{si}'. Allowed: ['CAMERA', 'SEQUENCER'].")
            sanitized["scene_input"] = si

    if tool_name == TOOL_RENDER_VSE_SEQUENCE:
        out_p = str(sanitized.get("output_path", "")).strip()
        if not out_p:
            raise ValueError("Parameter 'output_path' cannot be empty for render_vse_sequence.")
        if ".." in out_p:
            raise ValueError("Directory traversal ('..') is forbidden in 'output_path'.")
        ext = Path(out_p).suffix.lower()
        allowed_video_exts = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".png", ".jpg", ".jpeg")
        if ext not in allowed_video_exts:
            raise ValueError(f"Invalid file extension '{ext}' for render_vse_sequence. Allowed: {list(allowed_video_exts)}.")
        if "frame_start" in sanitized and "frame_end" in sanitized:
            f_s = sanitized["frame_start"]
            f_e = sanitized["frame_end"]
            if isinstance(f_s, int) and isinstance(f_e, int) and f_s > f_e:
                raise ValueError(f"frame_start ({f_s}) must be <= frame_end ({f_e}).")
        if "format" in sanitized and sanitized["format"] is not None:
            fmt = str(sanitized["format"]).strip().upper()
            allowed_fmts = ("MPEG4", "MKV", "QUICKTIME", "WEBM", "AVI", "PNG", "JPEG")
            if fmt not in allowed_fmts:
                raise ValueError(f"Invalid format '{fmt}'. Allowed: {list(allowed_fmts)}.")
            sanitized["format"] = fmt
        if "video_codec" in sanitized and sanitized["video_codec"] is not None:
            vc = str(sanitized["video_codec"]).strip().upper()
            allowed_vcs = ("H264", "H265", "PRORES", "DNXHD", "PNG", "NONE")
            if vc not in allowed_vcs:
                raise ValueError(f"Invalid video_codec '{vc}'. Allowed: {list(allowed_vcs)}.")
            sanitized["video_codec"] = vc
        if "audio_codec" in sanitized and sanitized["audio_codec"] is not None:
            ac = str(sanitized["audio_codec"]).strip().upper()
            allowed_acs = ("AAC", "AC3", "FLAC", "MP3", "PCM", "OPUS", "NONE")
            if ac not in allowed_acs:
                raise ValueError(f"Invalid audio_codec '{ac}'. Allowed: {list(allowed_acs)}.")
            sanitized["audio_codec"] = ac

    if tool_name == TOOL_MIXDOWN_VSE_AUDIO:
        out_p = str(sanitized.get("output_path", "")).strip()
        if not out_p:
            raise ValueError("Parameter 'output_path' cannot be empty for mixdown_vse_audio.")
        if ".." in out_p:
            raise ValueError("Directory traversal ('..') is forbidden in 'output_path'.")
        ext = Path(out_p).suffix.lower()
        allowed_audio_exts = (".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac")
        if ext not in allowed_audio_exts:
            raise ValueError(f"Invalid file extension '{ext}' for mixdown_vse_audio. Allowed: {list(allowed_audio_exts)}.")
        if "container" in sanitized and sanitized["container"] is not None:
            c = str(sanitized["container"]).strip().upper()
            allowed_cs = ("WAV", "FLAC", "MP3", "OGG", "AAC")
            if c not in allowed_cs:
                raise ValueError(f"Invalid container '{c}'. Allowed: {list(allowed_cs)}.")
            sanitized["container"] = c
        if "codec" in sanitized and sanitized["codec"] is not None:
            cd = str(sanitized["codec"]).strip().upper()
            allowed_cds = ("PCM", "FLAC", "MP3", "VORBIS", "AAC")
            if cd not in allowed_cds:
                raise ValueError(f"Invalid codec '{cd}'. Allowed: {list(allowed_cds)}.")
            sanitized["codec"] = cd
        if "format" in sanitized and sanitized["format"] is not None:
            f = str(sanitized["format"]).strip().upper()
            allowed_fs = ("U8", "S16", "S24", "S32", "FLOAT", "DOUBLE")
            if f not in allowed_fs:
                raise ValueError(f"Invalid format '{f}'. Allowed: {list(allowed_fs)}.")
            sanitized["format"] = f
        if "channels" in sanitized and sanitized["channels"] is not None:
            chans = str(sanitized["channels"]).strip().upper()
            allowed_chans = ("MONO", "STEREO", "SURROUND_51", "SURROUND_71")
            if chans not in allowed_chans:
                raise ValueError(f"Invalid channels '{chans}'. Allowed: {list(allowed_chans)}.")
            sanitized["channels"] = chans

    if tool_name == TOOL_TRANSFORM_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Tool 'transform_vse_strip' requires a non-empty 'name'.")
        act = str(sanitized.get("action", "UPDATE")).strip().upper()
        if act not in ("UPDATE", "INSPECT"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['UPDATE', 'INSPECT'].")
        sanitized["action"] = act
        if "filter" in sanitized:
            f = str(sanitized["filter"]).strip().upper()
            if f not in ("AUTO", "NEAREST", "BILINEAR"):
                raise ValueError(f"Invalid filter '{f}'.")
            sanitized["filter"] = f

    if tool_name == TOOL_CROP_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Tool 'crop_vse_strip' requires a non-empty 'name'.")
        act = str(sanitized.get("action", "UPDATE")).strip().upper()
        if act not in ("UPDATE", "INSPECT"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['UPDATE', 'INSPECT'].")
        sanitized["action"] = act

    if tool_name == TOOL_ANIMATE_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Tool 'animate_vse_strip' requires a non-empty 'name'.")
        act = str(sanitized.get("action", "")).strip().upper()
        if act not in ("INSERT_KEYFRAME", "DELETE_KEYFRAME"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['INSERT_KEYFRAME', 'DELETE_KEYFRAME'].")
        sanitized["action"] = act
        prop = str(sanitized.get("property", "")).strip().upper()
        valid_props = (
            "OFFSET_X", "OFFSET_Y", "SCALE_X", "SCALE_Y", "ROTATION",
            "BLEND_ALPHA", "VOLUME", "PAN",
            "CROP_LEFT", "CROP_RIGHT", "CROP_BOTTOM", "CROP_TOP"
        )
        if prop not in valid_props:
            raise ValueError(f"Invalid property '{prop}'. Allowed: {list(valid_props)}.")
        sanitized["property"] = prop
        if "frame" not in sanitized or not isinstance(sanitized["frame"], int) or isinstance(sanitized["frame"], bool):
            raise ValueError("Tool 'animate_vse_strip' requires an integer 'frame'.")

    if tool_name == TOOL_MANAGE_VSE_STRIP_MODIFIERS:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Tool 'manage_vse_strip_modifiers' requires a non-empty 'name'.")
        act = str(sanitized.get("action", "")).strip().upper()
        if act not in ("ADD", "REMOVE", "UPDATE", "LIST"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['ADD', 'REMOVE', 'UPDATE', 'LIST'].")
        sanitized["action"] = act
        if act == "ADD":
            m_type = str(sanitized.get("modifier_type", "")).strip().upper()
            valid_types = ("COLOR_BALANCE", "BRIGHT_CONTRAST", "WHITE_BALANCE", "TONEMAP", "CURVES", "HUE_CORRECT", "MASK")
            if m_type not in valid_types:
                raise ValueError(f"Invalid modifier_type '{m_type}'. Allowed: {list(valid_types)}.")
            sanitized["modifier_type"] = m_type
        elif act in ("REMOVE", "UPDATE"):
            if not str(sanitized.get("modifier_name", "")).strip():
                raise ValueError(f"Action '{act}' requires a non-empty 'modifier_name'.")
    # Tool-specific validation for VSE tools
    if tool_name == TOOL_INSPECT_VSE_TIMELINE:
        if "include_strips" in sanitized and not isinstance(sanitized["include_strips"], bool):
            raise ValueError("Parameter 'include_strips' must be a boolean.")
        if "include_markers" in sanitized and not isinstance(sanitized["include_markers"], bool):
            raise ValueError("Parameter 'include_markers' must be a boolean.")

    if tool_name == TOOL_CREATE_VSE_STRIP:
        stype = str(sanitized.get("strip_type", "")).strip().upper()
        if stype not in ("COLOR", "TEXT", "IMAGE", "SOUND", "MOVIE"):
            raise ValueError(f"Invalid strip_type '{stype}'. Allowed: ['COLOR', 'TEXT', 'IMAGE', 'SOUND', 'MOVIE'].")
        sanitized["strip_type"] = stype

        chan = sanitized.get("channel")
        if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
            raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")

        f_start = sanitized.get("frame_start")
        if not isinstance(f_start, int) or isinstance(f_start, bool):
            raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")

        if stype in ("IMAGE", "SOUND", "MOVIE"):
            fp = str(sanitized.get("filepath", "")).strip()
            if not fp:
                raise ValueError(f"Parameter 'filepath' cannot be empty for strip_type '{stype}'.")
            if ".." in fp.replace("\\", "/").split("/"):
                raise ValueError("Path traversal sequences ('..') are strictly forbidden in 'filepath'.")
            valid_exts = {
                "IMAGE": (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".tga", ".bmp"),
                "SOUND": (".wav", ".mp3", ".ogg", ".flac", ".aac"),
                "MOVIE": (".mp4", ".mov", ".mkv", ".avi", ".webm"),
            }
            if not fp.lower().endswith(valid_exts[stype]):
                raise ValueError(f"File extension for {stype} strip must be one of {sorted(valid_exts[stype])}, got '{fp}'.")

        if stype == "COLOR" and "color" in sanitized:
            col = sanitized["color"]
            if not isinstance(col, (list, tuple)) or len(col) not in (3, 4):
                raise ValueError("Parameter 'color' must be a list of 3 or 4 floats (RGB or RGBA).")
            for c_val in col:
                if not isinstance(c_val, (int, float)) or isinstance(c_val, bool) or not (0.0 <= c_val <= 1.0):
                    raise ValueError(f"Color components must be floats between 0.0 and 1.0, got {c_val}.")

    if tool_name == TOOL_MODIFY_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for modify_vse_strip.")
        if "channel" in sanitized:
            chan = sanitized["channel"]
            if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
                raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")
        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")
        if "frame_start" in sanitized:
            f_start = sanitized["frame_start"]
            if not isinstance(f_start, int) or isinstance(f_start, bool):
                raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

    if tool_name == TOOL_DELETE_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for delete_vse_strip.")

    if tool_name == TOOL_MANAGE_TIMELINE_MARKERS:
        act = str(sanitized.get("action", "")).strip().lower()
        if act not in ("add", "remove", "list"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['add', 'remove', 'list'].")
        sanitized["action"] = act
        if act in ("add", "remove"):
            m_name = str(sanitized.get("name", "")).strip()
            if not m_name:
                raise ValueError(f"Parameter 'name' cannot be empty for marker action '{act}'.")
        if act == "add":
            if "frame" not in sanitized or not isinstance(sanitized["frame"], int) or isinstance(sanitized["frame"], bool):
                raise ValueError("Parameter 'frame' must be an integer frame number for marker action 'add'.")

        views_list = sanitized.get("views")
        if views_list is not None:
            if not isinstance(views_list, (list, tuple)) or len(views_list) < 1 or len(views_list) > 3:
                raise ValueError("Parameter 'views' must be a list containing 1 to 3 view configurations.")
            seen_views = set()
            sanitized_views = []
            for idx, vc in enumerate(views_list):
                if not isinstance(vc, dict):
                    raise ValueError(f"View configuration at index {idx} must be a dictionary.")
                v_name = str(vc.get("view", "")).strip().upper()
                if v_name not in ("FRONT", "SIDE", "TOP"):
                    raise ValueError(f"View at index {idx} has invalid 'view' '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                if v_name in seen_views:
                    raise ValueError(f"Duplicate view '{v_name}' found in views list at index {idx}. Each view must be distinct.")
                seen_views.add(v_name)

                r_path = str(vc.get("reference_image_path", "")).strip()
                if not r_path:
                    raise ValueError(f"View '{v_name}' requires non-empty 'reference_image_path'.")

                weight = float(vc.get("weight", 1.0))
                if not math.isfinite(weight) or weight <= 0.0 or weight > 10.0:
                    raise ValueError(f"View '{v_name}' weight must be a positive float <= 10.0.")

                regr_tol = float(vc.get("max_regression_tolerance", 0.02))
                if not math.isfinite(regr_tol) or regr_tol < 0.0 or regr_tol > 0.5:
                    raise ValueError(f"View '{v_name}' max_regression_tolerance must be a float between 0.0 and 0.5.")

                csys = str(vc.get("coordinate_system", "UV")).strip().upper()
                if csys not in ("UV", "IMAGE_SPACE"):
                    raise ValueError(f"View '{v_name}' has invalid coordinate_system '{csys}'.")

                cbox = vc.get("crop_box")
                if cbox is not None:
                    if not isinstance(cbox, (list, tuple)) or len(cbox) != 4 or not all(
                        isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in cbox
                    ):
                        raise ValueError(f"View '{v_name}' crop_box must be a 4-element numeric array.")
                    u_min, v_min, u_max, v_max = [float(c) for c in cbox]
                    if not (0.0 <= u_min <= 1.0 and 0.0 <= v_min <= 1.0 and 0.0 <= u_max <= 1.0 and 0.0 <= v_max <= 1.0):
                        raise ValueError(f"View '{v_name}' crop_box values must be normalized between 0.0 and 1.0.")
                    if u_min >= u_max or v_min >= v_max:
                        raise ValueError(f"View '{v_name}' has invalid crop_box bounds (u_min >= u_max or v_min >= v_max).")
                    cbox = [u_min, v_min, u_max, v_max]

                san_vc = {
                    "view": v_name,
                    "reference_image_path": r_path,
                    "weight": weight,
                    "max_regression_tolerance": regr_tol,
                    "coordinate_system": csys,
                    "crop_box": cbox,
                }
                if "camera_name" in vc:
                    san_vc["camera_name"] = str(vc["camera_name"]).strip()
                sanitized_views.append(san_vc)
            sanitized["views"] = sanitized_views

    if tool_name == TOOL_INSPECT_SURFACE_DETAIL:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for inspect_surface_detail.")
        sanitized["target_object"] = tgt
        sanitized["include_roughness"] = bool(sanitized.get("include_roughness", True))
        sanitized["include_landmarks"] = bool(sanitized.get("include_landmarks", True))
        rc = sanitized.get("region_center")
        if rc is not None:
            if not isinstance(rc, (list, tuple)) or len(rc) != 3 or not all(
                isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in rc
            ):
                raise ValueError("Parameter 'region_center' must be a 3-element numeric array [x, y, z].")
            sanitized["region_center"] = [float(c) for c in rc]
        rr = float(sanitized.get("region_radius", 0.0))
        if not math.isfinite(rr) or rr < 0.0 or rr > 50.0:
            raise ValueError("Parameter 'region_radius' must be a float between 0.0 and 50.0.")
        sanitized["region_radius"] = rr


    if tool_name == TOOL_CONFIGURE_ANATOMICAL_MASK:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for configure_anatomical_mask.")
        sanitized["target_object"] = tgt

        mname = str(sanitized.get("mask_name", "")).strip()
        if not mname:
            raise ValueError("Parameter 'mask_name' must be a non-empty string.")
        if len(mname) > 63:
            raise ValueError("Parameter 'mask_name' must not exceed 63 characters.")
        sanitized["mask_name"] = mname

        act = str(sanitized.get("action", "SET")).strip().upper()
        if act not in ("SET", "ADD", "SUBTRACT", "CLEAR"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['SET', 'ADD', 'SUBTRACT', 'CLEAR'].")
        sanitized["action"] = act

        rtype = str(sanitized.get("region_type", "SPHERE")).strip().upper()
        if rtype not in ("SPHERE", "BOUNDING_BOX", "CYLINDER", "NORMAL_FACING", "ALL"):
            raise ValueError(f"Invalid region_type '{rtype}'. Allowed: ['SPHERE', 'BOUNDING_BOX', 'CYLINDER', 'NORMAL_FACING', 'ALL'].")
        sanitized["region_type"] = rtype

        c = sanitized.get("center")
        if c is not None:
            if not isinstance(c, (list, tuple)) or len(c) != 3 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in c
            ):
                raise ValueError("Parameter 'center' must be a 3-element numeric array [x, y, z].")
            sanitized["center"] = [float(v) for v in c]
        else:
            sanitized["center"] = [0.0, 0.0, 0.0]

        rad = float(sanitized.get("radius", 1.0))
        if not math.isfinite(rad) or rad < 0.0 or rad > 50.0:
            raise ValueError("Parameter 'radius' must be a float between 0.0 and 50.0.")
        sanitized["radius"] = rad

        radii = sanitized.get("radii")
        if radii is not None:
            if not isinstance(radii, (list, tuple)) or len(radii) != 3 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0.0 for v in radii
            ):
                raise ValueError("Parameter 'radii' must be a 3-element non-negative numeric array [rx, ry, rz].")
            sanitized["radii"] = [float(v) for v in radii]

        rb = sanitized.get("region_bounds")
        if rb is not None:
            if not isinstance(rb, (list, tuple)) or len(rb) != 6 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in rb
            ):
                raise ValueError("Parameter 'region_bounds' must be a 6-element numeric array [xmin, ymin, zmin, xmax, ymax, zmax].")
            if rb[0] >= rb[3] or rb[1] >= rb[4] or rb[2] >= rb[5]:
                raise ValueError("Parameter 'region_bounds' minimums must be strictly less than maximums.")
            sanitized["region_bounds"] = [float(v) for v in rb]

        fo = str(sanitized.get("falloff", "SMOOTH")).strip().upper()
        if fo not in ("SMOOTH", "LINEAR", "CONSTANT", "SHARP"):
            raise ValueError(f"Invalid falloff '{fo}'. Allowed: ['SMOOTH', 'LINEAR', 'CONSTANT', 'SHARP'].")
        sanitized["falloff"] = fo

        min_w = float(sanitized.get("min_weight", 0.0))
        if not math.isfinite(min_w) or min_w < 0.0 or min_w > 1.0:
            raise ValueError("Parameter 'min_weight' must be a float between 0.0 and 1.0.")
        sanitized["min_weight"] = min_w

        max_w = float(sanitized.get("max_weight", 1.0))
        if not math.isfinite(max_w) or max_w < 0.0 or max_w > 1.0:
            raise ValueError("Parameter 'max_weight' must be a float between 0.0 and 1.0.")
        sanitized["max_weight"] = max_w

        nv = sanitized.get("normal_vector")
        if nv is not None:
            if not isinstance(nv, (list, tuple)) or len(nv) != 3 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in nv
            ):
                raise ValueError("Parameter 'normal_vector' must be a 3-element numeric array [x, y, z].")
            if all(abs(v) < 1e-6 for v in nv):
                raise ValueError("Parameter 'normal_vector' must not be a zero vector.")
            sanitized["normal_vector"] = [float(v) for v in nv]

        ntol = float(sanitized.get("normal_tolerance", 0.5))
        if not math.isfinite(ntol) or ntol < 0.0 or ntol > 1.0:
            raise ValueError("Parameter 'normal_tolerance' must be a float between 0.0 and 1.0.")
        sanitized["normal_tolerance"] = ntol

        saxis = str(sanitized.get("symmetry_axis", "NONE")).strip().upper()
        if saxis not in ("X", "Y", "Z", "NONE"):
            raise ValueError(f"Invalid symmetry_axis '{saxis}'. Allowed: ['X', 'Y', 'Z', 'NONE'].")
        sanitized["symmetry_axis"] = saxis
        sanitized["rollback_on_failure"] = bool(sanitized.get("rollback_on_failure", True))
    # Tool-specific validation for VSE tools
    if tool_name == TOOL_INSPECT_VSE_TIMELINE:
        if "include_strips" in sanitized and not isinstance(sanitized["include_strips"], bool):
            raise ValueError("Parameter 'include_strips' must be a boolean.")
        if "include_markers" in sanitized and not isinstance(sanitized["include_markers"], bool):
            raise ValueError("Parameter 'include_markers' must be a boolean.")

    if tool_name == TOOL_CREATE_VSE_STRIP:
        stype = str(sanitized.get("strip_type", "")).strip().upper()
        if stype not in ("COLOR", "TEXT", "IMAGE", "SOUND", "MOVIE"):
            raise ValueError(f"Invalid strip_type '{stype}'. Allowed: ['COLOR', 'TEXT', 'IMAGE', 'SOUND', 'MOVIE'].")
        sanitized["strip_type"] = stype

        chan = sanitized.get("channel")
        if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
            raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")

        f_start = sanitized.get("frame_start")
        if not isinstance(f_start, int) or isinstance(f_start, bool):
            raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")

        if stype in ("IMAGE", "SOUND", "MOVIE"):
            fp = str(sanitized.get("filepath", "")).strip()
            if not fp:
                raise ValueError(f"Parameter 'filepath' cannot be empty for strip_type '{stype}'.")
            if ".." in fp.replace("\\", "/").split("/"):
                raise ValueError("Path traversal sequences ('..') are strictly forbidden in 'filepath'.")
            valid_exts = {
                "IMAGE": (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".tga", ".bmp"),
                "SOUND": (".wav", ".mp3", ".ogg", ".flac", ".aac"),
                "MOVIE": (".mp4", ".mov", ".mkv", ".avi", ".webm"),
            }
            if not fp.lower().endswith(valid_exts[stype]):
                raise ValueError(f"File extension for {stype} strip must be one of {sorted(valid_exts[stype])}, got '{fp}'.")

        if stype == "COLOR" and "color" in sanitized:
            col = sanitized["color"]
            if not isinstance(col, (list, tuple)) or len(col) not in (3, 4):
                raise ValueError("Parameter 'color' must be a list of 3 or 4 floats (RGB or RGBA).")
            for c_val in col:
                if not isinstance(c_val, (int, float)) or isinstance(c_val, bool) or not (0.0 <= c_val <= 1.0):
                    raise ValueError(f"Color components must be floats between 0.0 and 1.0, got {c_val}.")

    if tool_name == TOOL_MODIFY_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for modify_vse_strip.")
        if "channel" in sanitized:
            chan = sanitized["channel"]
            if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
                raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")
        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")
        if "frame_start" in sanitized:
            f_start = sanitized["frame_start"]
            if not isinstance(f_start, int) or isinstance(f_start, bool):
                raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

    if tool_name == TOOL_DELETE_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for delete_vse_strip.")

    if tool_name == TOOL_MANAGE_TIMELINE_MARKERS:
        act = str(sanitized.get("action", "")).strip().lower()
        if act not in ("add", "remove", "list"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['add', 'remove', 'list'].")
        sanitized["action"] = act
        if act in ("add", "remove"):
            m_name = str(sanitized.get("name", "")).strip()
            if not m_name:
                raise ValueError(f"Parameter 'name' cannot be empty for marker action '{act}'.")
        if act == "add":
            if "frame" not in sanitized or not isinstance(sanitized["frame"], int) or isinstance(sanitized["frame"], bool):
                raise ValueError("Parameter 'frame' must be an integer frame number for marker action 'add'.")

    if tool_name == TOOL_INSPECT_ANATOMICAL_MASK:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for inspect_anatomical_mask.")
        sanitized["target_object"] = tgt

        mname = sanitized.get("mask_name")
        if mname is not None:
            sanitized["mask_name"] = str(mname).strip()

        saxis = str(sanitized.get("symmetry_axis", "X")).strip().upper()
        if saxis not in ("X", "Y", "Z", "NONE"):
            raise ValueError(f"Invalid symmetry_axis '{saxis}'. Allowed: ['X', 'Y', 'Z', 'NONE'].")
        sanitized["symmetry_axis"] = saxis

        sthr = float(sanitized.get("seam_threshold", 0.005))
        if not math.isfinite(sthr) or sthr < 0.0001 or sthr > 0.5:
            raise ValueError("Parameter 'seam_threshold' must be a float between 0.0001 and 0.5.")
        sanitized["seam_threshold"] = sthr
        sanitized["evaluate_symmetry"] = bool(sanitized.get("evaluate_symmetry", True))

    if tool_name == TOOL_SYMMETRIZE_MESH_GEOMETRY:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for symmetrize_mesh_geometry.")
        sanitized["target_object"] = tgt

        saxis = str(sanitized.get("symmetry_axis", "X")).strip().upper()
        if saxis not in ("X", "Y", "Z"):
            raise ValueError(f"Invalid symmetry_axis '{saxis}'. Allowed: ['X', 'Y', 'Z'].")
        sanitized["symmetry_axis"] = saxis

        sdir = str(sanitized.get("source_direction", "+TO_-")).strip().upper()
        if sdir not in ("+TO_-", "-TO_+", "AVERAGE"):
            raise ValueError(f"Invalid source_direction '{sdir}'. Allowed: ['+TO_-', '-TO_+', 'AVERAGE'].")
        sanitized["source_direction"] = sdir

        sthr = float(sanitized.get("seam_threshold", 0.005))
        if not math.isfinite(sthr) or sthr < 0.0001 or sthr > 0.5:
            raise ValueError("Parameter 'seam_threshold' must be a float between 0.0001 and 0.5.")
        sanitized["seam_threshold"] = sthr

        sanitized["lock_midline"] = bool(sanitized.get("lock_midline", True))
        sanitized["preserve_topology"] = bool(sanitized.get("preserve_topology", True))

        max_v = int(sanitized.get("max_vertex_count", 50000))
        if max_v < 100 or max_v > 100000:
            raise ValueError("Parameter 'max_vertex_count' must be an integer between 100 and 100,000.")
        sanitized["max_vertex_count"] = max_v

        max_f = int(sanitized.get("max_face_count", 50000))
        if max_f < 100 or max_f > 100000:
            raise ValueError("Parameter 'max_face_count' must be an integer between 100 and 100,000.")
        sanitized["max_face_count"] = max_f

        sanitized["rollback_on_failure"] = bool(sanitized.get("rollback_on_failure", True))
    # Tool-specific validation for VSE tools
    if tool_name == TOOL_INSPECT_VSE_TIMELINE:
        if "include_strips" in sanitized and not isinstance(sanitized["include_strips"], bool):
            raise ValueError("Parameter 'include_strips' must be a boolean.")
        if "include_markers" in sanitized and not isinstance(sanitized["include_markers"], bool):
            raise ValueError("Parameter 'include_markers' must be a boolean.")

    if tool_name == TOOL_CREATE_VSE_STRIP:
        stype = str(sanitized.get("strip_type", "")).strip().upper()
        if stype not in ("COLOR", "TEXT", "IMAGE", "SOUND", "MOVIE"):
            raise ValueError(f"Invalid strip_type '{stype}'. Allowed: ['COLOR', 'TEXT', 'IMAGE', 'SOUND', 'MOVIE'].")
        sanitized["strip_type"] = stype

        chan = sanitized.get("channel")
        if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
            raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")

        f_start = sanitized.get("frame_start")
        if not isinstance(f_start, int) or isinstance(f_start, bool):
            raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")

        if stype in ("IMAGE", "SOUND", "MOVIE"):
            fp = str(sanitized.get("filepath", "")).strip()
            if not fp:
                raise ValueError(f"Parameter 'filepath' cannot be empty for strip_type '{stype}'.")
            if ".." in fp.replace("\\", "/").split("/"):
                raise ValueError("Path traversal sequences ('..') are strictly forbidden in 'filepath'.")
            valid_exts = {
                "IMAGE": (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".tga", ".bmp"),
                "SOUND": (".wav", ".mp3", ".ogg", ".flac", ".aac"),
                "MOVIE": (".mp4", ".mov", ".mkv", ".avi", ".webm"),
            }
            if not fp.lower().endswith(valid_exts[stype]):
                raise ValueError(f"File extension for {stype} strip must be one of {sorted(valid_exts[stype])}, got '{fp}'.")

        if stype == "COLOR" and "color" in sanitized:
            col = sanitized["color"]
            if not isinstance(col, (list, tuple)) or len(col) not in (3, 4):
                raise ValueError("Parameter 'color' must be a list of 3 or 4 floats (RGB or RGBA).")
            for c_val in col:
                if not isinstance(c_val, (int, float)) or isinstance(c_val, bool) or not (0.0 <= c_val <= 1.0):
                    raise ValueError(f"Color components must be floats between 0.0 and 1.0, got {c_val}.")

    if tool_name == TOOL_MODIFY_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for modify_vse_strip.")
        if "channel" in sanitized:
            chan = sanitized["channel"]
            if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
                raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")
        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")
        if "frame_start" in sanitized:
            f_start = sanitized["frame_start"]
            if not isinstance(f_start, int) or isinstance(f_start, bool):
                raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

    if tool_name == TOOL_DELETE_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for delete_vse_strip.")

    if tool_name == TOOL_MANAGE_TIMELINE_MARKERS:
        act = str(sanitized.get("action", "")).strip().lower()
        if act not in ("add", "remove", "list"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['add', 'remove', 'list'].")
        sanitized["action"] = act
        if act in ("add", "remove"):
            m_name = str(sanitized.get("name", "")).strip()
            if not m_name:
                raise ValueError(f"Parameter 'name' cannot be empty for marker action '{act}'.")
        if act == "add":
            if "frame" not in sanitized or not isinstance(sanitized["frame"], int) or isinstance(sanitized["frame"], bool):
                raise ValueError("Parameter 'frame' must be an integer frame number for marker action 'add'.")

        views_list = sanitized.get("views")
        if views_list is not None:
            if not isinstance(views_list, (list, tuple)) or len(views_list) < 1 or len(views_list) > 3:
                raise ValueError("Parameter 'views' must be a list containing 1 to 3 view configurations.")
            seen_views = set()
            sanitized_views = []
            for idx, vc in enumerate(views_list):
                if not isinstance(vc, dict):
                    raise ValueError(f"View configuration at index {idx} must be a dictionary.")
                v_name = str(vc.get("view", "")).strip().upper()
                if v_name not in ("FRONT", "SIDE", "TOP"):
                    raise ValueError(f"View at index {idx} has invalid 'view' '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                if v_name in seen_views:
                    raise ValueError(f"Duplicate view '{v_name}' found in views list at index {idx}. Each view must be distinct.")
                seen_views.add(v_name)
                r_path = str(vc.get("reference_image_path", "")).strip()
                if not r_path:
                    raise ValueError(f"View '{v_name}' requires non-empty 'reference_image_path'.")
                weight = float(vc.get("weight", 1.0))
                if not math.isfinite(weight) or weight <= 0.0 or weight > 10.0:
                    raise ValueError(f"View '{v_name}' weight must be a positive float <= 10.0.")
                regr_tol = float(vc.get("max_regression_tolerance", 0.02))
                if not math.isfinite(regr_tol) or regr_tol < 0.0 or regr_tol > 0.5:
                    raise ValueError(f"View '{v_name}' max_regression_tolerance must be a float between 0.0 and 0.5.")
                csys = str(vc.get("coordinate_system", "UV")).strip().upper()
                if csys not in ("UV", "IMAGE_SPACE"):
                    raise ValueError(f"View '{v_name}' has invalid coordinate_system '{csys}'.")
                cbox = vc.get("crop_box")
                if cbox is not None:
                    if not isinstance(cbox, (list, tuple)) or len(cbox) != 4 or not all(
                        isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in cbox
                    ):
                        raise ValueError(f"View '{v_name}' crop_box must be a 4-element numeric array.")
                    u_min, v_min, u_max, v_max = [float(c) for c in cbox]
                    if not (0.0 <= u_min <= 1.0 and 0.0 <= v_min <= 1.0 and 0.0 <= u_max <= 1.0 and 0.0 <= v_max <= 1.0):
                        raise ValueError(f"View '{v_name}' crop_box values must be normalized between 0.0 and 1.0.")
                    if u_min >= u_max or v_min >= v_max:
                        raise ValueError(f"View '{v_name}' has invalid crop_box bounds (u_min >= u_max or v_min >= v_max).")
                    cbox = [u_min, v_min, u_max, v_max]
                san_vc = {
                    "view": v_name,
                    "reference_image_path": r_path,
                    "weight": weight,
                    "max_regression_tolerance": regr_tol,
                    "coordinate_system": csys,
                    "crop_box": cbox,
                }
                if "camera_name" in vc:
                    san_vc["camera_name"] = str(vc["camera_name"]).strip()
                sanitized_views.append(san_vc)
            sanitized["views"] = sanitized_views

    # Also handle symmetry and mask parameters in detail_surface_features and sculpt_organic_anatomy
    if tool_name in (TOOL_DETAIL_SURFACE_FEATURES, TOOL_SCULPT_ORGANIC_ANATOMY):
        if "mask_vertex_group" in sanitized and sanitized["mask_vertex_group"] is not None:
            sanitized["mask_vertex_group"] = str(sanitized["mask_vertex_group"]).strip()
        sanitized["use_symmetry"] = bool(sanitized.get("use_symmetry", False))
        saxis = str(sanitized.get("symmetry_axis", "X")).strip().upper()
        if saxis not in ("X", "Y", "Z", "NONE"):
            raise ValueError(f"Invalid symmetry_axis '{saxis}'. Allowed: ['X', 'Y', 'Z', 'NONE'].")
        sanitized["symmetry_axis"] = saxis
        sthr = float(sanitized.get("seam_threshold", 0.005))
        if not math.isfinite(sthr) or sthr < 0.0001 or sthr > 0.5:
            raise ValueError("Parameter 'seam_threshold' must be a float between 0.0001 and 0.5.")
        sanitized["seam_threshold"] = sthr

    if tool_name == TOOL_DETECT_SEMANTIC_LANDMARKS:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for detect_semantic_landmarks.")
        sanitized["target_object"] = tgt

        dmethod = str(sanitized.get("detection_method", "CONTOUR_EXTREMA")).strip().upper()
        if dmethod not in ("CONTOUR_EXTREMA", "BOUNDING_PROJECTION", "CURVATURE_PEAKS"):
            raise ValueError(f"Invalid detection_method '{dmethod}'. Allowed: ['CONTOUR_EXTREMA', 'BOUNDING_PROJECTION', 'CURVATURE_PEAKS'].")
        sanitized["detection_method"] = dmethod

        sanitized["store_on_mesh"] = bool(sanitized.get("store_on_mesh", True))
        sanitized["enforce_symmetry"] = bool(sanitized.get("enforce_symmetry", True))

        cthr = float(sanitized.get("confidence_threshold", 0.5))
        if not math.isfinite(cthr) or cthr < 0.0 or cthr > 1.0:
            raise ValueError("Parameter 'confidence_threshold' must be a float between 0.0 and 1.0.")
        sanitized["confidence_threshold"] = cthr

        max_vd = float(sanitized.get("max_vertex_distance", 2.0))
        if not math.isfinite(max_vd) or max_vd < 0.001 or max_vd > 10.0:
            raise ValueError("Parameter 'max_vertex_distance' must be a float between 0.001 and 10.0.")
        sanitized["max_vertex_distance"] = max_vd

        lm_types = sanitized.get("landmark_types")
        if lm_types is not None:
            if not isinstance(lm_types, (list, tuple)) or len(lm_types) == 0:
                raise ValueError("Parameter 'landmark_types' must be a non-empty list of string landmark names.")
            allowed_lms = {
                "snout_tip", "horn_apex_left", "horn_apex_right", "wing_apex_left",
                "wing_apex_right", "tail_tip", "claw_apex_front_left", "claw_apex_front_right"
            }
            clean_types = []
            for lm in lm_types:
                s_lm = str(lm).strip().lower()
                if s_lm not in allowed_lms:
                    raise ValueError(f"Invalid landmark type '{lm}'. Allowed: {sorted(list(allowed_lms))}.")
                if s_lm not in clean_types:
                    clean_types.append(s_lm)
            sanitized["landmark_types"] = clean_types
        else:
            sanitized["landmark_types"] = [
                "snout_tip", "horn_apex_left", "horn_apex_right", "wing_apex_left", "wing_apex_right", "tail_tip"
            ]

        views_list = sanitized.get("views")
        if views_list is not None:
            if not isinstance(views_list, (list, tuple)) or len(views_list) < 1 or len(views_list) > 3:
                raise ValueError("Parameter 'views' must be a list containing 1 to 3 view configurations.")
            seen_views = set()
            sanitized_views = []
            for idx, vc in enumerate(views_list):
                if not isinstance(vc, dict):
                    raise ValueError(f"View configuration at index {idx} must be a dictionary.")
                v_name = str(vc.get("view", "")).strip().upper()
                if v_name not in ("FRONT", "SIDE", "TOP"):
                    raise ValueError(f"View at index {idx} has invalid 'view' '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP'].")
                if v_name in seen_views:
                    raise ValueError(f"Duplicate view '{v_name}' found in views list at index {idx}.")
                seen_views.add(v_name)
                r_path = str(vc.get("reference_image_path", "")).strip()
                if not r_path:
                    raise ValueError(f"View '{v_name}' requires non-empty 'reference_image_path'.")
                cbox = vc.get("crop_box")
                if cbox is not None:
                    if not isinstance(cbox, (list, tuple)) or len(cbox) != 4 or not all(
                        isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in cbox
                    ):
                        raise ValueError(f"View '{v_name}' crop_box must be a 4-element numeric array.")
                    u_min, v_min, u_max, v_max = [float(c) for c in cbox]
                    if not (0.0 <= u_min <= 1.0 and 0.0 <= v_min <= 1.0 and 0.0 <= u_max <= 1.0 and 0.0 <= v_max <= 1.0):
                        raise ValueError(f"View '{v_name}' crop_box values must be normalized between 0.0 and 1.0.")
                    if u_min >= u_max or v_min >= v_max:
                        raise ValueError(f"View '{v_name}' has invalid crop_box bounds (u_min >= u_max or v_min >= v_max).")
                    cbox = [u_min, v_min, u_max, v_max]
                san_vc = {
                    "view": v_name,
                    "reference_image_path": r_path,
                    "crop_box": cbox,
                }
                if "camera_name" in vc:
                    san_vc["camera_name"] = str(vc["camera_name"]).strip()
                sanitized_views.append(san_vc)
            sanitized["views"] = sanitized_views

    if tool_name == TOOL_BAKE_MESH_SURFACE_MAP:
        tgt = str(sanitized.get("target_object") or sanitized.get("object_name", "")).strip()
        if not tgt:
            raise ValueError("Parameter 'target_object' is required for bake_mesh_surface_map.")
        sanitized["target_object"] = tgt

        src = sanitized.get("source_object")
        if src is not None:
            src = str(src).strip()
            sanitized["source_object"] = src if src else None
        else:
            sanitized["source_object"] = None

        mtype = str(sanitized.get("map_type", "NORMAL")).strip().upper()
        if mtype not in ("NORMAL", "DISPLACEMENT", "ROUGHNESS", "AO"):
            raise ValueError(f"Invalid map_type '{mtype}'. Allowed: ['NORMAL', 'DISPLACEMENT', 'ROUGHNESS', 'AO'].")
        sanitized["map_type"] = mtype

        w = int(sanitized.get("width", 512))
        if w < 64 or w > 4096:
            raise ValueError("Parameter 'width' must be an integer between 64 and 4096.")
        sanitized["width"] = w

        h = int(sanitized.get("height", 512))
        if h < 64 or h > 4096:
            raise ValueError("Parameter 'height' must be an integer between 64 and 4096.")
        sanitized["height"] = h

        mgn = int(sanitized.get("margin", 16))
        if mgn < 0 or mgn > 64:
            raise ValueError("Parameter 'margin' must be an integer between 0 and 64.")
        sanitized["margin"] = mgn

        sfp = sanitized.get("save_filepath")
        if sfp is not None:
            sfp = str(sfp).strip()
            if sfp:
                import os
                if not os.path.isabs(sfp):
                    raise ValueError(f"Parameter 'save_filepath' must be an absolute path: '{sfp}'.")
                sanitized["save_filepath"] = sfp
            else:
                sanitized["save_filepath"] = None
        else:
            sanitized["save_filepath"] = None

        cage_ext = float(sanitized.get("cage_extrusion", 0.05))
        if not math.isfinite(cage_ext) or cage_ext < 0.0 or cage_ext > 2.0:
            raise ValueError("Parameter 'cage_extrusion' must be a float between 0.0 and 2.0.")
        sanitized["cage_extrusion"] = cage_ext

        max_ray = float(sanitized.get("max_ray_distance", 0.0))
        if not math.isfinite(max_ray) or max_ray < 0.0 or max_ray > 10.0:
            raise ValueError("Parameter 'max_ray_distance' must be a float between 0.0 and 10.0.")
        sanitized["max_ray_distance"] = max_ray

        sanitized["use_selected_to_active"] = bool(sanitized.get("use_selected_to_active", True))
        sanitized["auto_unwrap_if_needed"] = bool(sanitized.get("auto_unwrap_if_needed", True))

        cspace = str(sanitized.get("color_space", "Non-Color")).strip()
        if cspace.lower() == "non-color":
            cspace = "Non-Color"
        elif cspace.lower() == "srgb":
            cspace = "sRGB"
        else:
            raise ValueError(f"Invalid color_space '{cspace}'. Allowed: ['Non-Color', 'sRGB'].")
        sanitized["color_space"] = cspace

        sanitized["rollback_on_failure"] = bool(sanitized.get("rollback_on_failure", True))

    # Tool-specific validation for VSE tools
    if tool_name == TOOL_INSPECT_VSE_TIMELINE:
        if "include_strips" in sanitized and not isinstance(sanitized["include_strips"], bool):
            raise ValueError("Parameter 'include_strips' must be a boolean.")
        if "include_markers" in sanitized and not isinstance(sanitized["include_markers"], bool):
            raise ValueError("Parameter 'include_markers' must be a boolean.")

    if tool_name == TOOL_CREATE_VSE_STRIP:
        stype = str(sanitized.get("strip_type", "")).strip().upper()
        if stype not in ("COLOR", "TEXT", "IMAGE", "SOUND", "MOVIE"):
            raise ValueError(f"Invalid strip_type '{stype}'. Allowed: ['COLOR', 'TEXT', 'IMAGE', 'SOUND', 'MOVIE'].")
        sanitized["strip_type"] = stype

        chan = sanitized.get("channel")
        if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
            raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")

        f_start = sanitized.get("frame_start")
        if not isinstance(f_start, int) or isinstance(f_start, bool):
            raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")

        if stype in ("IMAGE", "SOUND", "MOVIE"):
            fp = str(sanitized.get("filepath", "")).strip()
            if not fp:
                raise ValueError(f"Parameter 'filepath' cannot be empty for strip_type '{stype}'.")
            if ".." in fp.replace("\\", "/").split("/"):
                raise ValueError("Path traversal sequences ('..') are strictly forbidden in 'filepath'.")
            valid_exts = {
                "IMAGE": (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".tga", ".bmp"),
                "SOUND": (".wav", ".mp3", ".ogg", ".flac", ".aac"),
                "MOVIE": (".mp4", ".mov", ".mkv", ".avi", ".webm"),
            }
            if not fp.lower().endswith(valid_exts[stype]):
                raise ValueError(f"File extension for {stype} strip must be one of {sorted(valid_exts[stype])}, got '{fp}'.")

        if stype == "COLOR" and "color" in sanitized:
            col = sanitized["color"]
            if not isinstance(col, (list, tuple)) or len(col) not in (3, 4):
                raise ValueError("Parameter 'color' must be a list of 3 or 4 floats (RGB or RGBA).")
            for c_val in col:
                if not isinstance(c_val, (int, float)) or isinstance(c_val, bool) or not (0.0 <= c_val <= 1.0):
                    raise ValueError(f"Color components must be floats between 0.0 and 1.0, got {c_val}.")

    if tool_name == TOOL_MODIFY_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for modify_vse_strip.")
        if "channel" in sanitized:
            chan = sanitized["channel"]
            if not isinstance(chan, int) or isinstance(chan, bool) or chan < 1 or chan > 128:
                raise ValueError(f"Parameter 'channel' must be an integer between 1 and 128, got {chan}.")
        if "duration" in sanitized:
            dur = sanitized["duration"]
            if not isinstance(dur, int) or isinstance(dur, bool) or dur < 1:
                raise ValueError(f"Parameter 'duration' must be a positive integer, got {dur}.")
        if "frame_start" in sanitized:
            f_start = sanitized["frame_start"]
            if not isinstance(f_start, int) or isinstance(f_start, bool):
                raise ValueError(f"Parameter 'frame_start' must be an integer frame number, got {f_start}.")

    if tool_name == TOOL_DELETE_VSE_STRIP:
        s_name = str(sanitized.get("name", "")).strip()
        if not s_name:
            raise ValueError("Parameter 'name' cannot be empty for delete_vse_strip.")

    if tool_name == TOOL_MANAGE_TIMELINE_MARKERS:
        act = str(sanitized.get("action", "")).strip().lower()
        if act not in ("add", "remove", "list"):
            raise ValueError(f"Invalid action '{act}'. Allowed: ['add', 'remove', 'list'].")
        sanitized["action"] = act
        if act in ("add", "remove"):
            m_name = str(sanitized.get("name", "")).strip()
            if not m_name:
                raise ValueError(f"Parameter 'name' cannot be empty for marker action '{act}'.")
        if act == "add":
            if "frame" not in sanitized or not isinstance(sanitized["frame"], int) or isinstance(sanitized["frame"], bool):
                raise ValueError("Parameter 'frame' must be an integer frame number for marker action 'add'.")

    # Explicit user approval enforcement for scene-changing tools (default to read-only mode)
    if tool_def.get("permission_tier") in (PERMISSION_SCENE_MUTATION, PERMISSION_DESTRUCTIVE):
        if not trusted_approval:
            if params.get("approved") is True or sanitized.get("approved") is True:
                raise PermissionError(
                    f"Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize "
                    f"scene mutation '{tool_name}'. Explicit user approval must be granted through a trusted approval mechanism."
                )
            raise PermissionError(
                f"Approval required: Scene mutation '{tool_name}' requires explicit user approval through "
                "a trusted approval mechanism. The system is running in read-only mode by default."
            )
        # When trusted approval is verified, mark it explicitly in sanitized payload
        sanitized["trusted_approval"] = True

    return sanitized


def get_all_tool_definitions() -> List[Dict[str, Any]]:
    """Returns list of all registered tool definitions for MCP discovery."""
    return list(TOOL_DEFINITIONS.values())