"""
Modeling and Geometry Agent for Universal MCP.
Provides verified scene mutation capabilities:
1. Primitive creation (Cube, UV Sphere, Cylinder, Plane).
2. Object transforms (Location, Rotation Euler, Scale in absolute and relative modes).
3. Restricted structured modeling operations and AST-validated Python code.

Enforces human-approval bindings, input parameter validation, operation boundary checks,
transaction boundaries, and verified undo rollback recovery.
"""

from typing import Dict, Any, List, Optional, Set, Tuple
import time
import logging

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    AgentResult,
    VerificationResult,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_CONFIGURE_MODIFIER,
    TOOL_EDIT_MODIFIER_STACK,
    TOOL_APPLY_MODIFIER,
    TOOL_CONFIGURE_CURVE_GEOMETRY,
    TOOL_CONFIGURE_MODELING_OBJECT,
    TOOL_CONFIGURE_MODELING_GEOMETRY,
    TOOL_INSPECT_MODELING_GEOMETRY,    TOOL_INSPECT_MODELING_OBJECT,    TOOL_INSPECT_CURVE_GEOMETRY,    TOOL_INSPECT_MODIFIER_STACK,
    TOOL_EDIT_MESH,
    TOOL_SCULPT_MESH,
    TOOL_INSPECT_SCULPT_STATE,
    TOOL_INSPECT_MODIFIERS,
    TOOL_LOAD_REFERENCE_IMAGE,
    TOOL_CROP_REFERENCE_IMAGE,
    TOOL_COMPARE_SILHOUETTE_ALIGNMENT,
    TOOL_CALIBRATE_REFERENCE_VIEWS,
    TOOL_OPTIMIZE_MESH_SILHOUETTE,
    TOOL_FIT_MULTIVIEW_SILHOUETTE,
    TOOL_REFINE_MESH_MULTIRESOLUTION,
    TOOL_SCULPT_ORGANIC_ANATOMY,
    TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
    TOOL_INSPECT_SEMANTIC_LANDMARKS,
    TOOL_GUIDE_MESH_LANDMARKS,
    TOOL_DETAIL_SURFACE_FEATURES,
    TOOL_INSPECT_SURFACE_DETAIL,
    TOOL_CONFIGURE_ANATOMICAL_MASK,
    TOOL_INSPECT_ANATOMICAL_MASK,
    TOOL_SYMMETRIZE_MESH_GEOMETRY,
    TOOL_DETECT_SEMANTIC_LANDMARKS,
    TOOL_BAKE_MESH_SURFACE_MAP,
    TOOL_DETECT_SEMANTIC_LANDMARKS,
    TOOL_BAKE_MESH_SURFACE_MAP,
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_EXECUTE_BLENDER_CODE,
    TOOL_DELETE_OBJECT,
    TOOL_SAVE_BLEND_FILE,
    TOOL_EXTRUDE_MESH,
    TOOL_INSET_MESH,
    TOOL_EXTRUDE_FACES,
    TOOL_INSET_FACES,

    TOOL_BEVEL_MESH,
    TOOL_BEVEL_EDGES,
    TOOL_SPLIT_MESH,
    TOOL_KNIFE_MESH,
    TOOL_BISECT_MESH,
    TOOL_DISSOLVE_MESH,
    TOOL_MERGE_MESH,
    TOOL_RECALCULATE_NORMALS,
    TOOL_ALIGN_NORMALS,
    TOOL_UV_UNWRAP,
    TOOL_UV_SMART_PROJECT,
    TOOL_UNWRAP_MESH,
    TOOL_SMART_PROJECT,
    TOOL_SMART_UV_PROJECT,
    TOOL_UV_PROJECT,
    TOOL_MANAGE_UV_SEAMS,
    TOOL_PACK_UV_ISLANDS,
    TOOL_MANAGE_UV_LAYERS,
    TOOL_INSPECT_UV_MESH,
    TOOL_MANAGE_KEYFRAME,
    TOOL_INSERT_KEYFRAME,
    TOOL_DELETE_KEYFRAME,
    TOOL_CONFIGURE_GEOMETRY_NODES,
    TOOL_INSPECT_GEOMETRY_NODES,
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_EXPORT_SCENE,
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_IMPORT_SCENE,
    TOOL_DUPLICATE_OBJECT,
    TOOL_DUPLICATE,
    TOOL_RENAME_OBJECT,
    TOOL_RENAME,
    TOOL_SELECT_OBJECT,
    TOOL_SELECT,
    TOOL_PURGE_ORPHANED_DATABLOCKS,
    TOOL_PURGE_ORPHANS,
    TOOL_CREATE_CURVE_OR_TEXT,
    TOOL_CREATE_CURVE,
    TOOL_CREATE_TEXT,
    TOOL_CONFIGURE_PHYSICS,
    TOOL_SETUP_PHYSICS,
    TOOL_MANAGE_PHYSICS,
    TOOL_INSPECT_PHYSICS,
    TOOL_BAKE_PHYSICS_SIMULATION,
    TOOL_CONFIGURE_ANIMATION_CURVE,
    TOOL_MANAGE_FCURVE,
    TOOL_SET_KEYFRAME_INTERPOLATION,
    TOOL_MANAGE_ACTION_SLOTS,
    TOOL_OPEN_BLEND_FILE,
    TOOL_OPEN_PROJECT,
    TOOL_LOAD_BLEND_FILE,
    TOOL_CREATE_ARMATURE,
    TOOL_EDIT_ARMATURE_BONES,
    TOOL_INSPECT_ARMATURE,
    TOOL_BIND_ARMATURE_MESH,
    TOOL_CONFIGURE_BONE_CONSTRAINT,
    ALLOWED_MODELING_ACTIONS,
    TOOL_DEFINITIONS,
    validate_restricted_code_ast,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_ModelingAgent")

ALLOWED_PRIMITIVES: Set[str] = {"cube", "sphere", "cylinder", "plane", "cone", "torus", "monkey", "grid"}

MODELING_AGENT_ID = "agent.modeling"
CAPABILITY_MODELING_PRIMITIVE = "modeling.primitive"
CAPABILITY_MODELING_TRANSFORM = "modeling.transform"
CAPABILITY_MODELING_EXECUTION = "modeling.execution"
CAPABILITY_MODELING_EDIT = "modeling.mesh_edit"
CAPABILITY_MODELING_UV = "modeling.uv"
CAPABILITY_MODELING_KEYFRAME = "modeling.animation_keyframe"
CAPABILITY_MODELING_GEONODES = "modeling.geometry_nodes"
CAPABILITY_MODELING_ASSET_IO = "modeling.asset_io"
CAPABILITY_MODELING_OBJECT_OPS = "modeling.object_operations"
CAPABILITY_MODELING_MODIFIERS = "modeling.modifiers"
CAPABILITY_MODELING_MODIFIER_INSPECT = "modeling.modifier_inspection"
CAPABILITY_MODELING_SCULPT = "modeling.sculpting"
CAPABILITY_MODELING_SCULPT_INSPECT = "modeling.sculpt_inspection"
CAPABILITY_MODELING_LANDMARKS = "modeling.landmarks"
CAPABILITY_MODELING_LANDMARKS_INSPECT = "modeling.landmarks_inspection"
CAPABILITY_MODELING_SURFACE_DETAIL = "modeling.surface_detail"
CAPABILITY_MODELING_SURFACE_DETAIL_INSPECT = "modeling.surface_detail_inspect"
CAPABILITY_MODELING_ANATOMICAL_MASK = "modeling.anatomical_mask"
CAPABILITY_MODELING_ANATOMICAL_MASK_INSPECT = "modeling.anatomical_mask_inspect"
CAPABILITY_MODELING_SYMMETRIZE = "modeling.symmetrize"
CAPABILITY_MODELING_LANDMARK_DETECTION = "modeling.landmark_detection"
CAPABILITY_MODELING_SURFACE_BAKE = "modeling.surface_bake"
CAPABILITY_MODELING_RIGGING = "modeling.rigging"
CAPABILITY_MODELING_RIGGING_INSPECT = "modeling.rigging_inspection"
CAPABILITY_MODELING_PHYSICS = "modeling.physics"
CAPABILITY_MODELING_PHYSICS_INSPECT = "modeling.physics_inspection"

SUPPORTED_MODELING_TOOLS: Set[str] = {
    TOOL_LOAD_REFERENCE_IMAGE,
    TOOL_CROP_REFERENCE_IMAGE,
    TOOL_COMPARE_SILHOUETTE_ALIGNMENT,
    TOOL_CALIBRATE_REFERENCE_VIEWS,
    TOOL_OPTIMIZE_MESH_SILHOUETTE,
    TOOL_FIT_MULTIVIEW_SILHOUETTE,
    TOOL_REFINE_MESH_MULTIRESOLUTION,
    TOOL_SCULPT_ORGANIC_ANATOMY,
    TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
    TOOL_INSPECT_SEMANTIC_LANDMARKS,
    TOOL_GUIDE_MESH_LANDMARKS,
    TOOL_DETAIL_SURFACE_FEATURES,
    TOOL_INSPECT_SURFACE_DETAIL,
    TOOL_CONFIGURE_ANATOMICAL_MASK,
    TOOL_INSPECT_ANATOMICAL_MASK,
    TOOL_SYMMETRIZE_MESH_GEOMETRY,
    TOOL_DETECT_SEMANTIC_LANDMARKS,
    TOOL_BAKE_MESH_SURFACE_MAP,
    TOOL_DETECT_SEMANTIC_LANDMARKS,
    TOOL_BAKE_MESH_SURFACE_MAP,
    TOOL_CONFIGURE_MODIFIER,
    TOOL_EDIT_MODIFIER_STACK,
    TOOL_APPLY_MODIFIER,
    TOOL_CONFIGURE_CURVE_GEOMETRY,
    TOOL_CONFIGURE_MODELING_OBJECT,
    TOOL_CONFIGURE_MODELING_GEOMETRY,
    TOOL_INSPECT_MODELING_GEOMETRY,    TOOL_INSPECT_MODELING_OBJECT,    TOOL_INSPECT_CURVE_GEOMETRY,    TOOL_INSPECT_MODIFIER_STACK,
    TOOL_EDIT_MESH,
    TOOL_SCULPT_MESH,
    TOOL_INSPECT_SCULPT_STATE,
    TOOL_INSPECT_MODIFIERS,
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_EXECUTE_BLENDER_CODE,
    TOOL_DELETE_OBJECT,
    TOOL_SAVE_BLEND_FILE,
    TOOL_EXTRUDE_MESH,
    TOOL_INSET_MESH,
    TOOL_EXTRUDE_FACES,
    TOOL_INSET_FACES,
    TOOL_BEVEL_MESH,
    TOOL_BEVEL_EDGES,
    TOOL_SPLIT_MESH,
    TOOL_KNIFE_MESH,
    TOOL_BISECT_MESH,
    TOOL_DISSOLVE_MESH,
    TOOL_MERGE_MESH,
    TOOL_RECALCULATE_NORMALS,
    TOOL_ALIGN_NORMALS,
    TOOL_UV_UNWRAP,
    TOOL_UV_SMART_PROJECT,
    TOOL_UNWRAP_MESH,
    TOOL_SMART_PROJECT,
    TOOL_SMART_UV_PROJECT,
    TOOL_UV_PROJECT,
    TOOL_MANAGE_UV_SEAMS,
    TOOL_PACK_UV_ISLANDS,
    TOOL_MANAGE_UV_LAYERS,
    TOOL_INSPECT_UV_MESH,
    TOOL_MANAGE_KEYFRAME,
    TOOL_INSERT_KEYFRAME,
    TOOL_DELETE_KEYFRAME,
    TOOL_CONFIGURE_GEOMETRY_NODES,
    TOOL_INSPECT_GEOMETRY_NODES,
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_EXPORT_SCENE,
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_IMPORT_SCENE,
    TOOL_DUPLICATE_OBJECT,
    TOOL_DUPLICATE,
    TOOL_RENAME_OBJECT,
    TOOL_RENAME,
    TOOL_SELECT_OBJECT,
    TOOL_SELECT,
    TOOL_PURGE_ORPHANED_DATABLOCKS,
    TOOL_PURGE_ORPHANS,
    TOOL_CREATE_CURVE_OR_TEXT,
    TOOL_CREATE_CURVE,
    TOOL_CREATE_TEXT,
    TOOL_CONFIGURE_PHYSICS,
    TOOL_SETUP_PHYSICS,
    TOOL_MANAGE_PHYSICS,
    TOOL_INSPECT_PHYSICS,
    TOOL_BAKE_PHYSICS_SIMULATION,
    TOOL_CONFIGURE_ANIMATION_CURVE,
    TOOL_MANAGE_FCURVE,
    TOOL_SET_KEYFRAME_INTERPOLATION,
    TOOL_MANAGE_ACTION_SLOTS,
    TOOL_OPEN_BLEND_FILE,
    TOOL_OPEN_PROJECT,
    TOOL_LOAD_BLEND_FILE,
    TOOL_CREATE_ARMATURE,
    TOOL_EDIT_ARMATURE_BONES,
    TOOL_INSPECT_ARMATURE,
    TOOL_BIND_ARMATURE_MESH,
    TOOL_CONFIGURE_BONE_CONSTRAINT,
}

UNSUPPORTED_OPERATIONS: Set[str] = {
    "bevel",
    "bevel_edges",
    "boolean",
    "boolean_difference",
    "boolean_union",
    "loop_cut",
    "knife",
    "spin",
    "screw",
}


def create_modeling_manifest(version: str = "0.1.13") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Modeling & Geometry Agent.
    Declares only verified scene-mutation capabilities with human approval requirements.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in (
            TOOL_CONFIGURE_MODIFIER,
    TOOL_EDIT_MODIFIER_STACK,
    TOOL_CONFIGURE_CURVE_GEOMETRY,
    TOOL_CONFIGURE_MODELING_OBJECT,
    TOOL_CONFIGURE_MODELING_GEOMETRY,
    TOOL_INSPECT_MODELING_GEOMETRY,    TOOL_INSPECT_MODELING_OBJECT,    TOOL_INSPECT_CURVE_GEOMETRY,    TOOL_INSPECT_MODIFIER_STACK,
    TOOL_EDIT_MESH,
            TOOL_SCULPT_MESH,
            TOOL_INSPECT_SCULPT_STATE,
            TOOL_INSPECT_MODIFIERS,
            TOOL_LOAD_REFERENCE_IMAGE,
            TOOL_CROP_REFERENCE_IMAGE,
            TOOL_COMPARE_SILHOUETTE_ALIGNMENT,
            TOOL_CALIBRATE_REFERENCE_VIEWS,
            TOOL_OPTIMIZE_MESH_SILHOUETTE,
            TOOL_FIT_MULTIVIEW_SILHOUETTE,
            TOOL_REFINE_MESH_MULTIRESOLUTION,
            TOOL_SCULPT_ORGANIC_ANATOMY,
    TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
    TOOL_INSPECT_SEMANTIC_LANDMARKS,
    TOOL_GUIDE_MESH_LANDMARKS,
            TOOL_CREATE_PRIMITIVE,
            TOOL_TRANSFORM_OBJECT,
            TOOL_EXECUTE_BLENDER_CODE,
            TOOL_DELETE_OBJECT,
            TOOL_SAVE_BLEND_FILE,
            TOOL_EXTRUDE_MESH,
            TOOL_INSET_MESH,
            TOOL_EXTRUDE_FACES,
            TOOL_INSET_FACES,
            TOOL_UV_UNWRAP,
            TOOL_UV_SMART_PROJECT,
            TOOL_UNWRAP_MESH,
            TOOL_SMART_PROJECT,
            TOOL_SMART_UV_PROJECT,
            TOOL_UV_PROJECT,
            TOOL_MANAGE_KEYFRAME,
            TOOL_INSERT_KEYFRAME,
            TOOL_DELETE_KEYFRAME,
            TOOL_CONFIGURE_GEOMETRY_NODES,
            TOOL_INSPECT_GEOMETRY_NODES,
            TOOL_EXPORT_SCENE_ASSET,
            TOOL_EXPORT_SCENE,
            TOOL_IMPORT_SCENE_ASSET,
            TOOL_IMPORT_SCENE,
            TOOL_DUPLICATE_OBJECT,
            TOOL_DUPLICATE,
            TOOL_RENAME_OBJECT,
            TOOL_RENAME,
            TOOL_SELECT_OBJECT,
            TOOL_SELECT,
            TOOL_PURGE_ORPHANED_DATABLOCKS,
            TOOL_PURGE_ORPHANS,
            TOOL_CREATE_ARMATURE,
            TOOL_EDIT_ARMATURE_BONES,
            TOOL_INSPECT_ARMATURE,
            TOOL_BIND_ARMATURE_MESH,
            TOOL_CONFIGURE_BONE_CONSTRAINT,
            TOOL_INSPECT_PHYSICS,
            TOOL_BAKE_PHYSICS_SIMULATION,
        )
        if name in TOOL_DEFINITIONS
    }
    return AgentManifest(
        agent_id=MODELING_AGENT_ID,
        name="Modeling and Geometry Agent",
        version=version,
        description=(
            "Creates mesh primitives, modifies transforms, and executes structured modeling operations "
            "with human approval gating, transaction boundaries, and verified rollback recovery."
        ),
        capabilities=[
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_SCULPT,description="Typed sculpt mode, brush, stroke, voxel remesh, dynamic topology, and bounded organic anatomy sculpting verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_SCULPT_MESH, TOOL_SCULPT_ORGANIC_ANATOMY],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"approval":"normal human approval required","whole_domain_status":"PARTIALLY IMPLEMENTED","dispatch":"verified through isolated real-Blender mutation E2E"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_SCULPT_INSPECT,description="Read-only sculpt mode/brush/topology inspection; verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_INSPECT_SCULPT_STATE],read_write="READ_ONLY",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_LANDMARKS,description="Semantic anatomical landmark guidance with dual-condition acceptance and silhouette regression protection verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_CONFIGURE_SEMANTIC_LANDMARKS, TOOL_GUIDE_MESH_LANDMARKS],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"approval":"normal human approval required","whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/LANDMARK_GUIDANCE_V0157.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_LANDMARKS_INSPECT,description="Read-only semantic landmark reprojection error evaluation across FRONT, SIDE, TOP views verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_INSPECT_SEMANTIC_LANDMARKS],read_write="READ_ONLY",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/LANDMARK_GUIDANCE_V0157.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_SURFACE_DETAIL,description="Fine-scale anatomical surface detailing (SCALES, RIDGES, FACETS, VEINS) with landmark preservation and silhouette regression protection verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_DETAIL_SURFACE_FEATURES],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"approval":"normal human approval required","whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/SURFACE_DETAILING_V0158.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_SURFACE_DETAIL_INSPECT,description="Read-only surface geometric detail inspection, Laplacian roughness, and topology readback verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_INSPECT_SURFACE_DETAIL],read_write="READ_ONLY",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/SURFACE_DETAILING_V0158.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_ANATOMICAL_MASK,description="Vertex-group-based anatomical region masking with spatial falloff and bilateral symmetry mirroring verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_CONFIGURE_ANATOMICAL_MASK],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"approval":"normal human approval required","whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/ANATOMICAL_MASKING_V0159.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_ANATOMICAL_MASK_INSPECT,description="Read-only anatomical mask inspection with bilateral symmetry RMSE evaluation verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_INSPECT_ANATOMICAL_MASK],read_write="READ_ONLY",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/ANATOMICAL_MASKING_V0159.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_SYMMETRIZE,description="Bilateral X/Y/Z mesh symmetrization with midline locking and silhouette regression protection verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_SYMMETRIZE_MESH_GEOMETRY],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"approval":"normal human approval required","whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/ANATOMICAL_MASKING_V0159.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_LANDMARK_DETECTION,description="Automated semantic anatomical landmark detection from reference silhouettes or mesh boundary geometry with bilateral symmetry enforcement verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_DETECT_SEMANTIC_LANDMARKS],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"approval":"normal human approval required","whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_GAPS_CLOSURE_V0160.md"}),
            CapabilityDescriptor(capability_id=CAPABILITY_MODELING_SURFACE_BAKE,description="High-resolution surface detail baking (tangent normal maps, displacement, roughness, AO) from detailed source meshes to low-poly retopology meshes or self-baking with Cycles CPU and non-color textures verified through isolated MCP to Blender 5.2.2.",supported_task_types=[TOOL_BAKE_MESH_SURFACE_MAP],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"approval":"normal human approval required","whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_GAPS_CLOSURE_V0160.md"}),
            CapabilityDescriptor(capability_id="modeling.geometry_graph",description="Finite Geometry Nodes graph transactions; real MCP/native evaluated output and rollback verified.",supported_task_types=[TOOL_CONFIGURE_MODELING_GEOMETRY],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_CONTROLS_GEOMETRY_PROGRESS.md"}),
            CapabilityDescriptor(capability_id="modeling.geometry_graph_inspection",description="Finite graph/evaluated output readback; real MCP/native verified.",supported_task_types=[TOOL_INSPECT_MODELING_GEOMETRY],read_write="READ_ONLY",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_CONTROLS_GEOMETRY_PROGRESS.md"}),
            CapabilityDescriptor(capability_id="modeling.object_controls",description="Finite object controls; real MCP/native matrices, selection, parenting and rollback verified.",supported_task_types=[TOOL_CONFIGURE_MODELING_OBJECT],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_CONTROLS_GEOMETRY_PROGRESS.md"}),
            CapabilityDescriptor(capability_id="modeling.object_control_inspection",description="Finite object/context readback; real MCP/native verified.",supported_task_types=[TOOL_INSPECT_MODELING_OBJECT],read_write="READ_ONLY",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_CONTROLS_GEOMETRY_PROGRESS.md"}),
            CapabilityDescriptor(capability_id="modeling.curve_geometry",description="Finite curve/text transactions; real MCP/native readback and rollback verified.",supported_task_types=[TOOL_CONFIGURE_CURVE_GEOMETRY],read_write="SCENE_MUTATION",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_CURVE_PROGRESS.md"}),
            CapabilityDescriptor(capability_id="modeling.curve_geometry_inspection",description="Finite curve/text/evaluated geometry inspection; real MCP/native verified.",supported_task_types=[TOOL_INSPECT_CURVE_GEOMETRY],read_write="READ_ONLY",verification_status="VERIFIED",constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_CURVE_PROGRESS.md"}),
            CapabilityDescriptor(capability_id="modeling.modifier_stack", description="Finite six-type modifier stack transactions; real MCP/Blender readback and fault rollback verified.",
                supported_task_types=[TOOL_EDIT_MODIFIER_STACK, TOOL_APPLY_MODIFIER], read_write="SCENE_MUTATION", verification_status="VERIFIED", constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_COMPONENT_MODIFIER_PROGRESS.md"}),
            CapabilityDescriptor(capability_id="modeling.modifier_stack_inspection", description="Base/evaluated mesh and finite six-type stack readback; real MCP/Blender verified.",
                supported_task_types=[TOOL_INSPECT_MODIFIER_STACK], read_write="READ_ONLY", verification_status="VERIFIED", constraints={"whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_COMPONENT_MODIFIER_PROGRESS.md"}),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_MODIFIERS,
                description="Typed add/update/remove for SUBSURF, BEVEL, SOLIDIFY; verified numeric readback. Other types, apply and reorder are excluded.",
                supported_task_types=[TOOL_CONFIGURE_MODIFIER], read_write="SCENE_MUTATION",
                verification_status="VERIFIED", constraints={"supported_types": ["SUBSURF", "BEVEL", "SOLIDIFY"],
                    "actions": ["add", "update", "remove"], "typed_contract_status": "FULLY IMPLEMENTED",
                    "typed_contract_verification": "VERIFIED", "whole_domain_status": "PARTIALLY IMPLEMENTED",
                    "evidence": "docs/verification/TYPED_MODIFIERS_V0141.md"}),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_MODIFIER_INSPECT,
                description="Read-only ordered modifier stack and typed property values.",
                supported_task_types=[TOOL_INSPECT_MODIFIERS], read_write="READ_ONLY", verification_status="VERIFIED"),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_PRIMITIVE,
                description="Creates parameterized 3D mesh primitives (Cube, UV Sphere, Cylinder, Plane, Cone, Torus, Monkey, Grid).",
                supported_task_types=[TOOL_CREATE_PRIMITIVE],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_TRANSFORM,
                description="Modifies location, Euler rotation, and scale for scene objects.",
                supported_task_types=[TOOL_TRANSFORM_OBJECT],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_EXECUTION,
                description="Executes structured modeling operations, object deletions, datablock purges, and project file saving.",
                supported_task_types=[
                    TOOL_EXECUTE_BLENDER_CODE,
                    TOOL_DELETE_OBJECT,
                    TOOL_SAVE_BLEND_FILE,
                    TOOL_PURGE_ORPHANED_DATABLOCKS,
                    TOOL_PURGE_ORPHANS,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_EDIT,
                description="Object-mode staged finite component edits and legacy face extrusion/inset, with snapshot binding and actual-state readback.",
                constraints={"mode":"OBJECT","indices":"initial_snapshot","whole_domain_status":"PARTIALLY IMPLEMENTED","evidence":"docs/verification/MODELING_REMEDIATION_V0146.md"},
                supported_task_types=[
                    TOOL_EDIT_MESH, TOOL_EXTRUDE_MESH, TOOL_INSET_MESH, TOOL_EXTRUDE_FACES, TOOL_INSET_FACES,
                    TOOL_BEVEL_MESH, TOOL_BEVEL_EDGES, TOOL_SPLIT_MESH, TOOL_KNIFE_MESH, TOOL_BISECT_MESH,
                    TOOL_DISSOLVE_MESH, TOOL_MERGE_MESH, TOOL_RECALCULATE_NORMALS, TOOL_ALIGN_NORMALS
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_UV,
                description="Executes safe UV unwrapping and projection operations (uv_unwrap, uv_smart_project) on scene mesh geometry.",
                supported_task_types=[
                    TOOL_UV_UNWRAP,
                    TOOL_UV_SMART_PROJECT,
                    TOOL_UNWRAP_MESH,
                    TOOL_SMART_PROJECT,
                    TOOL_SMART_UV_PROJECT,
                    TOOL_UV_PROJECT,
                    TOOL_MANAGE_UV_SEAMS,
                    TOOL_PACK_UV_ISLANDS,
                    TOOL_MANAGE_UV_LAYERS,
                    TOOL_INSPECT_UV_MESH,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_KEYFRAME,
                description="Inserts, updates, or deletes animation keyframes and configures F-Curves and Action Slots on supported object properties.",
                supported_task_types=[
                    TOOL_MANAGE_KEYFRAME,
                    TOOL_INSERT_KEYFRAME,
                    TOOL_DELETE_KEYFRAME,
                    TOOL_CONFIGURE_ANIMATION_CURVE,
                    TOOL_MANAGE_FCURVE,
                    TOOL_SET_KEYFRAME_INTERPOLATION,
                    TOOL_MANAGE_ACTION_SLOTS,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_GEONODES,
                description="Inspects or configures Geometry Nodes modifiers, node groups, and interface sockets.",
                supported_task_types=[TOOL_CONFIGURE_GEOMETRY_NODES, TOOL_INSPECT_GEOMETRY_NODES],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_ASSET_IO,
                description="Exports or imports 3D scene assets in glTF/GLB, FBX, and USD formats, and loads .blend projects.",
                supported_task_types=[
                    TOOL_EXPORT_SCENE_ASSET,
                    TOOL_EXPORT_SCENE,
                    TOOL_IMPORT_SCENE_ASSET,
                    TOOL_IMPORT_SCENE,
                    TOOL_OPEN_BLEND_FILE,
                    TOOL_OPEN_PROJECT,
                    TOOL_LOAD_BLEND_FILE,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_RIGGING,
                description="Creates armatures, edits bones, binds meshes with vertex groups, and configures IK constraints.",
                supported_task_types=[
                    TOOL_CREATE_ARMATURE,
                    TOOL_EDIT_ARMATURE_BONES,
                    TOOL_BIND_ARMATURE_MESH,
                    TOOL_CONFIGURE_BONE_CONSTRAINT,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_RIGGING_INSPECT,
                description="Inspects armature bone hierarchy, rest geometry, pose transforms, and constraints.",
                supported_task_types=[
                    TOOL_INSPECT_ARMATURE,
                ],
                read_write="READ_ONLY",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_PHYSICS,
                description="Configures rigid bodies, cloth simulation presets, collision bodies, and bakes point caches.",
                supported_task_types=[
                    TOOL_CONFIGURE_PHYSICS,
                    TOOL_SETUP_PHYSICS,
                    TOOL_MANAGE_PHYSICS,
                    TOOL_BAKE_PHYSICS_SIMULATION,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_PHYSICS_INSPECT,
                description="Inspects rigid body world settings, simulation point caches, and object physics states.",
                supported_task_types=[
                    TOOL_INSPECT_PHYSICS,
                ],
                read_write="READ_ONLY",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MODELING_OBJECT_OPS,
                description="Selects, duplicates, renames, creates curves/text, and configures physics on scene objects.",
                supported_task_types=[
                    TOOL_SELECT_OBJECT,
                    TOOL_SELECT,
                    TOOL_DUPLICATE_OBJECT,
                    TOOL_DUPLICATE,
                    TOOL_RENAME_OBJECT,
                    TOOL_RENAME,
                    TOOL_CREATE_CURVE_OR_TEXT,
                    TOOL_CREATE_CURVE,
                    TOOL_CREATE_TEXT,
                    TOOL_CONFIGURE_PHYSICS,
                    TOOL_SETUP_PHYSICS,
                    TOOL_MANAGE_PHYSICS,
                    TOOL_LOAD_REFERENCE_IMAGE,
                    TOOL_CROP_REFERENCE_IMAGE,
                    TOOL_COMPARE_SILHOUETTE_ALIGNMENT,
                    TOOL_CALIBRATE_REFERENCE_VIEWS,
                    TOOL_OPTIMIZE_MESH_SILHOUETTE,
                    TOOL_FIT_MULTIVIEW_SILHOUETTE,
                    TOOL_REFINE_MESH_MULTIRESOLUTION,
                    TOOL_SCULPT_ORGANIC_ANATOMY,
    TOOL_CONFIGURE_SEMANTIC_LANDMARKS,
    TOOL_INSPECT_SEMANTIC_LANDMARKS,
    TOOL_GUIDE_MESH_LANDMARKS,
    TOOL_DETAIL_SURFACE_FEATURES,
    TOOL_INSPECT_SURFACE_DETAIL,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
        ],
        input_schemas=schemas,
        constraints={"e2e_audit": {
            "scope": ["object_operations", "mesh_modeling", "modifiers", "geometry_nodes", "uvs"],
            "implementation_status": "PARTIALLY IMPLEMENTED",
            "verification_status": "NOT VERIFIED",
            "evidence": "docs/verification/TEN_CAPABILITY_EVIDENCE.json",
        }},
        priority=20,
        enabled=True,
    )


class ModelingAgent:
    """
    Specialized Modeling & Geometry Agent.
    Receives validated modeling tasks, verifies operation compatibility and input constraints,
    enforces human approval bindings, and executes via BlenderExecutor with transaction rollback tracking.
    """

    def __init__(self, version: str = "0.1.13"):
        self.version = version
        self._manifest = create_modeling_manifest(version=self.version)

    @property
    def agent_id(self) -> str:
        return MODELING_AGENT_ID

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def get_manifest(self) -> AgentManifest:
        return self._manifest

    def can_handle(self, task: AgentTask) -> bool:
        """Checks whether this agent can handle the requested capability and task type."""
        req_cap = task.required_capability
        if req_cap and req_cap not in (
            CAPABILITY_MODELING_PRIMITIVE,
            CAPABILITY_MODELING_TRANSFORM,
            CAPABILITY_MODELING_EXECUTION,
            CAPABILITY_MODELING_EDIT,
            CAPABILITY_MODELING_UV,
            CAPABILITY_MODELING_KEYFRAME,
            CAPABILITY_MODELING_GEONODES,
            CAPABILITY_MODELING_ASSET_IO,
            CAPABILITY_MODELING_OBJECT_OPS,
            CAPABILITY_MODELING_MODIFIERS,
            CAPABILITY_MODELING_MODIFIER_INSPECT,
            "modeling.modifier_stack",
            "modeling.modifier_stack_inspection",
            CAPABILITY_MODELING_SCULPT,
            CAPABILITY_MODELING_SCULPT_INSPECT,
            CAPABILITY_MODELING_LANDMARKS,
            CAPABILITY_MODELING_LANDMARKS_INSPECT,
            CAPABILITY_MODELING_SURFACE_DETAIL,
            CAPABILITY_MODELING_SURFACE_DETAIL_INSPECT,
            CAPABILITY_MODELING_ANATOMICAL_MASK,
            CAPABILITY_MODELING_ANATOMICAL_MASK_INSPECT,
            CAPABILITY_MODELING_SYMMETRIZE,
            CAPABILITY_MODELING_LANDMARK_DETECTION,
            CAPABILITY_MODELING_SURFACE_BAKE,
            CAPABILITY_MODELING_RIGGING,
            CAPABILITY_MODELING_RIGGING_INSPECT,
        ):
            return False
        if task.task_type:
            return task.task_type in SUPPORTED_MODELING_TOOLS
        return True

    def validate_task_input(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Performs strict pre-execution validation of task inputs, parameters, and operation constraints.
        Returns: (is_valid, error_code, error_message)
        """
        if tool_name not in SUPPORTED_MODELING_TOOLS:
            return (
                False,
                "UNSUPPORTED_REQUEST",
                f"Unsupported modeling tool '{tool_name}'. Supported tools: {sorted(list(SUPPORTED_MODELING_TOOLS))}",
            )

        if tool_name == TOOL_EDIT_MESH:
            from blender_addon.universal_mcp.bridge.component_edit import validate
            try:validate(params)
            except ValueError as error:return False,"INVALID_PARAMS",str(error)

        if tool_name in (TOOL_SCULPT_MESH, TOOL_INSPECT_SCULPT_STATE):
            from blender_addon.universal_mcp.bridge.sculpt_contract import validate
            try:validate(params, inspection=tool_name == TOOL_INSPECT_SCULPT_STATE)
            except ValueError as error:return False,"INVALID_PARAMS",str(error)

        if tool_name in (TOOL_CONFIGURE_MODELING_GEOMETRY, TOOL_INSPECT_MODELING_GEOMETRY):
            from blender_addon.universal_mcp.bridge.geometry_contract import validate
            try:validate(params, inspection=tool_name == TOOL_INSPECT_MODELING_GEOMETRY)
            except ValueError as error:return False,"INVALID_PARAMS",str(error)

        if tool_name in (TOOL_CONFIGURE_MODELING_OBJECT, TOOL_INSPECT_MODELING_OBJECT):
            from blender_addon.universal_mcp.bridge.object_controls import validate
            try:validate(params, inspection=tool_name == TOOL_INSPECT_MODELING_OBJECT)
            except ValueError as error:return False,"INVALID_PARAMS",str(error)

        if tool_name in (TOOL_CONFIGURE_CURVE_GEOMETRY, TOOL_INSPECT_CURVE_GEOMETRY):
            from blender_addon.universal_mcp.bridge.curve_contract import validate
            try:validate(params, inspection=tool_name == TOOL_INSPECT_CURVE_GEOMETRY)
            except ValueError as error:return False,"INVALID_PARAMS",str(error)

        if tool_name in (TOOL_EDIT_MODIFIER_STACK, TOOL_INSPECT_MODIFIER_STACK, TOOL_APPLY_MODIFIER):
            try:
                if tool_name == TOOL_APPLY_MODIFIER:
                    # Its public contract permits omission; the main-thread handler
                    # infers the type from the named modifier before stack validation.
                    from shared.schemas.tool_schemas import validate_tool_input
                    validate_tool_input(tool_name, params, trusted_approval=True)
                else:
                    from blender_addon.universal_mcp.bridge.advanced_modifier_contract import validate
                    validate(params, inspection=tool_name == TOOL_INSPECT_MODIFIER_STACK)
            except ValueError as error:return False,"INVALID_PARAMS",str(error)

        if tool_name in (TOOL_CONFIGURE_MODIFIER, TOOL_INSPECT_MODIFIERS):
            from blender_addon.universal_mcp.bridge.modifier_contract import validate_modifier_params
            try:
                validate_modifier_params(params, inspection=tool_name == TOOL_INSPECT_MODIFIERS)
            except ValueError as error:
                return False, "INVALID_PARAMS", str(error)

        # 0. Validation for reference image tools
        if tool_name in (TOOL_LOAD_REFERENCE_IMAGE, TOOL_CROP_REFERENCE_IMAGE):
            if not params.get("image_path"):
                return False, "INVALID_PARAMS", f"Parameter 'image_path' is required for {tool_name}."
            if tool_name == TOOL_CROP_REFERENCE_IMAGE:
                if not params.get("crop_box"):
                    return False, "INVALID_PARAMS", "Parameter 'crop_box' is required for crop_reference_image."

        if tool_name == TOOL_COMPARE_SILHOUETTE_ALIGNMENT:
            if not params.get("reference_image_path"):
                return False, "INVALID_PARAMS", "Parameter 'reference_image_path' is required for compare_silhouette_alignment."

        if tool_name == TOOL_CALIBRATE_REFERENCE_VIEWS:
            if not params.get("views") or not isinstance(params.get("views"), (list, tuple)):
                return False, "INVALID_PARAMS", "Parameter 'views' must be a non-empty list for calibrate_reference_views."

        if tool_name == TOOL_OPTIMIZE_MESH_SILHOUETTE:
            if not params.get("target_object"):
                return False, "INVALID_PARAMS", "Parameter 'target_object' is required for optimize_mesh_silhouette."
            if not params.get("reference_image_path"):
                return False, "INVALID_PARAMS", "Parameter 'reference_image_path' is required for optimize_mesh_silhouette."

        if tool_name == TOOL_FIT_MULTIVIEW_SILHOUETTE:
            if not params.get("target_object"):
                return False, "INVALID_PARAMS", "Parameter 'target_object' is required for fit_multiview_silhouette."
            views = params.get("views")
            if not isinstance(views, (list, tuple)) or len(views) < 2 or len(views) > 3:
                return False, "INVALID_PARAMS", "Parameter 'views' must be a list containing 2 or 3 view configurations."
            seen = set()
            for v_cfg in views:
                if not isinstance(v_cfg, dict):
                    return False, "INVALID_PARAMS", "Each view configuration must be a dictionary."
                v_name = str(v_cfg.get("view", "")).strip().upper()
                if v_name not in ("FRONT", "SIDE", "TOP"):
                    return False, "INVALID_PARAMS", f"Invalid view '{v_name}'. Allowed: ['FRONT', 'SIDE', 'TOP']."
                if v_name in seen:
                    return False, "INVALID_PARAMS", f"Duplicate view '{v_name}' in views list."
                seen.add(v_name)
                if not v_cfg.get("reference_image_path"):
                    return False, "INVALID_PARAMS", f"View '{v_name}' requires 'reference_image_path'."

        if tool_name == TOOL_REFINE_MESH_MULTIRESOLUTION:
            if not params.get("target_object"):
                return False, "INVALID_PARAMS", "Parameter 'target_object' is required for refine_mesh_multiresolution."
            if not params.get("views") and not params.get("reference_image_path"):
                return False, "INVALID_PARAMS", "Either 'views' or 'reference_image_path' is required for refine_mesh_multiresolution."
            if params.get("subdivision_levels") is not None:
                try:
                    lvl = int(params["subdivision_levels"])
                    if lvl < 1 or lvl > 4:
                        return False, "INVALID_PARAMS", "Parameter 'subdivision_levels' must be between 1 and 4."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'subdivision_levels' must be an integer."
            if params.get("max_vertex_count") is not None:
                try:
                    mv = int(params["max_vertex_count"])
                    if mv < 100 or mv > 100000:
                        return False, "INVALID_PARAMS", "Parameter 'max_vertex_count' must be between 100 and 100,000."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'max_vertex_count' must be an integer."
            if params.get("max_face_count") is not None:
                try:
                    mf = int(params["max_face_count"])
                    if mf < 100 or mf > 100000:
                        return False, "INVALID_PARAMS", "Parameter 'max_face_count' must be between 100 and 100,000."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'max_face_count' must be an integer."

        if tool_name == TOOL_SCULPT_ORGANIC_ANATOMY:
            target_obj = params.get("target_object") or params.get("object_name")
            if not target_obj:
                return False, "INVALID_PARAMS", "Parameter 'target_object' is required for sculpt_organic_anatomy."
            b_type = str(params.get("brush_type", "INFLATE")).strip().upper()
            if b_type not in ("GRAB", "INFLATE", "SMOOTH", "CLAY", "DRAW"):
                return False, "INVALID_PARAMS", f"Invalid brush_type '{b_type}'. Allowed: ['GRAB', 'INFLATE', 'SMOOTH', 'CLAY', 'DRAW']."
            pres_topo = bool(params.get("preserve_topology", True))
            dyn_topo = bool(params.get("dynamic_topology", False))
            if pres_topo and dyn_topo:
                return False, "INVALID_PARAMS", "Conflicting parameters: preserve_topology=True but dynamic_topology=True."
            if params.get("radius") is not None:
                try:
                    r = float(params["radius"])
                    if r < 0.001 or r > 10.0:
                        return False, "INVALID_PARAMS", "Parameter 'radius' must be between 0.001 and 10.0."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'radius' must be a float."
            if params.get("strength") is not None:
                try:
                    s = float(params["strength"])
                    if s < 0.0 or s > 1.0:
                        return False, "INVALID_PARAMS", "Parameter 'strength' must be between 0.0 and 1.0."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'strength' must be a float."
            if params.get("max_displacement") is not None:
                try:
                    md = float(params["max_displacement"])
                    if md < 0.001 or md > 2.0:
                        return False, "INVALID_PARAMS", "Parameter 'max_displacement' must be between 0.001 and 2.0."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'max_displacement' must be a float."
            if params.get("iterations") is not None:
                try:
                    it = int(params["iterations"])
                    if it < 1 or it > 10:
                        return False, "INVALID_PARAMS", "Parameter 'iterations' must be between 1 and 10."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'iterations' must be an integer."
            if params.get("max_vertex_count") is not None:
                try:
                    mv = int(params["max_vertex_count"])
                    if mv < 100 or mv > 100000:
                        return False, "INVALID_PARAMS", "Parameter 'max_vertex_count' must be between 100 and 100,000."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'max_vertex_count' must be an integer."
            if params.get("max_face_count") is not None:
                try:
                    mf = int(params["max_face_count"])
                    if mf < 100 or mf > 100000:
                        return False, "INVALID_PARAMS", "Parameter 'max_face_count' must be between 100 and 100,000."
                except (ValueError, TypeError):
                    return False, "INVALID_PARAMS", "Parameter 'max_face_count' must be an integer."

        if tool_name in (TOOL_CONFIGURE_SEMANTIC_LANDMARKS, TOOL_INSPECT_SEMANTIC_LANDMARKS, TOOL_GUIDE_MESH_LANDMARKS):
            target_obj = params.get("target_object") or params.get("object_name")
            if not target_obj:
                return False, "INVALID_PARAMS", f"Parameter 'target_object' is required for {tool_name}."
            if tool_name == TOOL_CONFIGURE_SEMANTIC_LANDMARKS:
                act = str(params.get("action", "SET")).strip().upper()
                if act not in ("SET", "UPDATE", "REMOVE", "CLEAR"):
                    return False, "INVALID_PARAMS", f"Invalid action '{act}'. Allowed: ['SET', 'UPDATE', 'REMOVE', 'CLEAR']."
            if tool_name == TOOL_GUIDE_MESH_LANDMARKS:
                if params.get("max_iterations") is not None:
                    try:
                        it = int(params["max_iterations"])
                        if it < 1 or it > 50:
                            return False, "INVALID_PARAMS", "Parameter 'max_iterations' must be between 1 and 50."
                    except (ValueError, TypeError):
                        return False, "INVALID_PARAMS", "Parameter 'max_iterations' must be an integer."
                if params.get("max_vertex_count") is not None:
                    try:
                        mv = int(params["max_vertex_count"])
                        if mv < 100 or mv > 100000:
                            return False, "INVALID_PARAMS", "Parameter 'max_vertex_count' must be between 100 and 100,000."
                    except (ValueError, TypeError):
                        return False, "INVALID_PARAMS", "Parameter 'max_vertex_count' must be an integer."

        # 1. Validation for create_primitive
        if tool_name == TOOL_CREATE_PRIMITIVE:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required and cannot be empty."

            prim_type = str(params.get("primitive_type", "")).strip().lower()
            if not prim_type:
                return False, "INVALID_PARAMS", "'primitive_type' is required for create_primitive."

            if prim_type not in ALLOWED_PRIMITIVES:
                return (
                    False,
                    "UNSUPPORTED_REQUEST",
                    f"Unsupported primitive type '{prim_type}'. Supported types: {sorted(list(ALLOWED_PRIMITIVES))}. "
                    "Torus, Cone, Suzanne, curves, and metaballs are not supported in this phase.",
                )

            location = params.get("location")
            if location is not None:
                if not isinstance(location, (list, tuple)) or len(location) != 3:
                    return False, "INVALID_PARAMS", "Location must be a 3-element list [x, y, z]."

            dimensions = params.get("dimensions")
            if dimensions is not None:
                if not isinstance(dimensions, (list, tuple)) or len(dimensions) != 3:
                    return False, "INVALID_PARAMS", "Dimensions must be a 3-element list [dx, dy, dz]."

        # 2. Validation for transform_object
        elif tool_name == TOOL_TRANSFORM_OBJECT:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required and cannot be empty."

            has_loc = "location" in params
            has_rot = "rotation_euler" in params
            has_scale = "scale" in params
            if not (has_loc or has_rot or has_scale):
                return (
                    False,
                    "INVALID_PARAMS",
                    "At least one transform attribute ('location', 'rotation_euler', 'scale') must be provided.",
                )

            for key in ("location", "rotation_euler", "scale"):
                val = params.get(key)
                if val is not None:
                    if not isinstance(val, (list, tuple)) or len(val) != 3:
                        return False, "INVALID_PARAMS", f"Transform attribute '{key}' must be a 3-element list."

        # 3. Validation for execute_blender_code
        elif tool_name == TOOL_EXECUTE_BLENDER_CODE:
            operations = params.get("operations")
            code = params.get("code")

            if not operations and not code:
                return (
                    False,
                    "INVALID_PARAMS",
                    "execute_blender_code requires either an 'operations' list or a validated 'code' string.",
                )

            if operations is not None:
                if not isinstance(operations, list):
                    return False, "INVALID_PARAMS", "'operations' must be a list of operation dictionaries."
                for idx, op in enumerate(operations):
                    if not isinstance(op, dict):
                        return False, "INVALID_PARAMS", f"Operation at index {idx} must be a dictionary."
                    action = str(op.get("action", "")).strip().lower()
                    if not action:
                        return False, "INVALID_PARAMS", f"Operation at index {idx} is missing required 'action'."

                    if action in UNSUPPORTED_OPERATIONS or action not in ALLOWED_MODELING_ACTIONS:
                        return (
                            False,
                            "UNSUPPORTED_REQUEST",
                            f"Unsupported modeling operation '{action}'. Supported actions: {sorted(list(ALLOWED_MODELING_ACTIONS))}. "
                            "Use the typed edit_mesh, edit_modifier_stack or configure_modeling_geometry contract for advanced modeling; this legacy structured action is unsupported.",
                        )

            if code is not None and isinstance(code, str) and code.strip():
                try:
                    validate_restricted_code_ast(code)
                except ValueError as ve:
                    return False, "SECURITY_VIOLATION", f"AST security violation in modeling code: {str(ve)}"

        # 4. Validation for delete_object
        elif tool_name == TOOL_DELETE_OBJECT:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for delete_object."

        # 5. Validation for save_blend_file
        elif tool_name == TOOL_SAVE_BLEND_FILE:
            filepath = params.get("filepath")
            if filepath is not None and (not isinstance(filepath, str) or not filepath.strip()):
                return False, "INVALID_PARAMS", "Parameter 'filepath' must be a non-empty string when provided."

        # 6. Validation for extrude_mesh / extrude_faces
        elif tool_name in (TOOL_EXTRUDE_MESH, TOOL_EXTRUDE_FACES):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for mesh extrusion."
            dist = params.get("distance", 1.0)
            if not isinstance(dist, (int, float)) or isinstance(dist, bool):
                return False, "INVALID_PARAMS", "Parameter 'distance' must be a numeric value."
            direction = params.get("direction")
            if direction is not None:
                if not isinstance(direction, (list, tuple)) or len(direction) != 3:
                    return False, "INVALID_PARAMS", "Parameter 'direction' must be a 3-element list [x, y, z]."

        # 7. Validation for inset_mesh / inset_faces
        elif tool_name in (TOOL_INSET_MESH, TOOL_INSET_FACES):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for mesh inset."
            thickness = params.get("thickness", 0.1)
            if not isinstance(thickness, (int, float)) or isinstance(thickness, bool) or thickness < 0:
                return False, "INVALID_PARAMS", "Parameter 'thickness' must be a non-negative number."
            depth = params.get("depth", 0.0)
            if not isinstance(depth, (int, float)) or isinstance(depth, bool):
                return False, "INVALID_PARAMS", "Parameter 'depth' must be a numeric value."

        # 8. Validation for uv_unwrap / unwrap_mesh
        elif tool_name in (TOOL_UV_UNWRAP, TOOL_UNWRAP_MESH):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for mesh UV unwrap."
            method = params.get("method")
            if method is not None:
                if not isinstance(method, str) or method.upper() not in ("ANGLE_BASED", "CONFORMAL"):
                    return False, "INVALID_PARAMS", "Parameter 'method' must be 'ANGLE_BASED' or 'CONFORMAL'."
            margin = params.get("margin")
            if margin is not None:
                if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not (0.0 <= margin <= 1.0):
                    return False, "INVALID_PARAMS", "Parameter 'margin' must be a numeric value between 0.0 and 1.0."

        # 9. Validation for uv_smart_project and aliases
        elif tool_name in (TOOL_UV_SMART_PROJECT, TOOL_SMART_PROJECT, TOOL_SMART_UV_PROJECT, TOOL_UV_PROJECT):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for mesh UV smart projection."
            angle_limit = params.get("angle_limit")
            if angle_limit is not None:
                if not isinstance(angle_limit, (int, float)) or isinstance(angle_limit, bool) or not (1.0 <= angle_limit <= 89.0):
                    return False, "INVALID_PARAMS", "Parameter 'angle_limit' must be a number between 1.0 and 89.0 degrees."
            island_margin = params.get("island_margin")
            if island_margin is not None:
                if not isinstance(island_margin, (int, float)) or isinstance(island_margin, bool) or not (0.0 <= island_margin <= 1.0):
                    return False, "INVALID_PARAMS", "Parameter 'island_margin' must be a number between 0.0 and 1.0."

        # UV seam management
        elif tool_name == TOOL_MANAGE_UV_SEAMS:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for UV seam management."
            action = str(params.get("action", "mark")).strip().lower()
            if action not in ("mark", "clear", "clear_all"):
                return False, "INVALID_PARAMS", f"Parameter 'action' must be 'mark', 'clear', or 'clear_all', got '{action}'."
            if action in ("mark", "clear"):
                edges = params.get("edges")
                if edges is None or not isinstance(edges, (list, tuple)) or len(edges) == 0:
                    return False, "INVALID_PARAMS", f"Parameter 'edges' must be a non-empty list of integers for action '{action}'."

        # UV island packing
        elif tool_name == TOOL_PACK_UV_ISLANDS:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for UV island packing."
            margin = params.get("margin")
            if margin is not None:
                if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not (0.0 <= margin <= 1.0):
                    return False, "INVALID_PARAMS", "Parameter 'margin' must be a numeric value between 0.0 and 1.0."

        # UV layer management
        elif tool_name == TOOL_MANAGE_UV_LAYERS:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for UV layer management."
            layer_name = str(params.get("layer_name", "")).strip()
            if not layer_name:
                return False, "INVALID_PARAMS", "Parameter 'layer_name' is required for UV layer management."
            action = str(params.get("action", "create")).strip().lower()
            if action not in ("create", "set_active", "rename", "remove"):
                return False, "INVALID_PARAMS", f"Parameter 'action' must be 'create', 'set_active', 'rename', or 'remove'."
            if action == "rename" and not str(params.get("new_name", "")).strip():
                return False, "INVALID_PARAMS", "Parameter 'new_name' is required when action is 'rename'."

        # UV mesh inspection
        elif tool_name == TOOL_INSPECT_UV_MESH:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for UV inspection."

        # 10. Validation for manage_keyframe and aliases
        elif tool_name in (TOOL_MANAGE_KEYFRAME, TOOL_INSERT_KEYFRAME, TOOL_DELETE_KEYFRAME):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for keyframe management."
            prop_path = str(params.get("property_path", "")).strip().lower()
            if not prop_path or prop_path not in ("location", "rotation_euler", "scale"):
                return False, "INVALID_PARAMS", "Parameter 'property_path' must be 'location', 'rotation_euler', or 'scale'."
            frame = params.get("frame")
            if frame is None or not isinstance(frame, (int, float)) or isinstance(frame, bool):
                return False, "INVALID_PARAMS", "Parameter 'frame' must be a numeric value."

        # 11. Validation for configure_geometry_nodes and aliases
        elif tool_name in (TOOL_CONFIGURE_GEOMETRY_NODES, TOOL_INSPECT_GEOMETRY_NODES):
            name = str(params.get("name") or params.get("target_object") or params.get("object_name") or "").strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for Geometry Nodes."
            action = str(params.get("action", "inspect" if tool_name == TOOL_INSPECT_GEOMETRY_NODES else "inspect")).strip().lower()
            allowed = (
                "inspect", "create", "assign_group", "add_node", "remove_node",
                "add_link", "remove_link", "set_node_input", "add_socket",
                "set_socket_default", "configure_graph", "update_graph", "evaluate", "apply"
            )
            if action not in allowed:
                return False, "INVALID_PARAMS", f"Invalid action '{action}' for Geometry Nodes."

        # Rigging Validation
        elif tool_name == TOOL_CREATE_ARMATURE:
            for attr in ("location", "rotation", "scale"):
                val = params.get(attr)
                if val is not None and (not isinstance(val, (list, tuple)) or len(val) != 3):
                    return False, "INVALID_PARAMS", f"Transform attribute '{attr}' must be a 3-element list."

        elif tool_name == TOOL_EDIT_ARMATURE_BONES:
            if not str(params.get("armature_name", "")).strip():
                return False, "INVALID_PARAMS", "Parameter 'armature_name' is required."

        elif tool_name == TOOL_INSPECT_ARMATURE:
            if not str(params.get("armature_name", "")).strip():
                return False, "INVALID_PARAMS", "Parameter 'armature_name' is required."

        elif tool_name == TOOL_BIND_ARMATURE_MESH:
            if not str(params.get("mesh_object_name", "")).strip():
                return False, "INVALID_PARAMS", "Parameter 'mesh_object_name' is required."
            if not str(params.get("armature_name", "")).strip():
                return False, "INVALID_PARAMS", "Parameter 'armature_name' is required."

        elif tool_name == TOOL_CONFIGURE_BONE_CONSTRAINT:
            if not str(params.get("armature_name", "")).strip():
                return False, "INVALID_PARAMS", "Parameter 'armature_name' is required."
            if not str(params.get("bone_name", "")).strip():
                return False, "INVALID_PARAMS", "Parameter 'bone_name' is required."

        # 12. Validation for export_scene_asset and aliases
        elif tool_name in (TOOL_EXPORT_SCENE_ASSET, TOOL_EXPORT_SCENE):
            filepath = str(params.get("filepath", "")).strip()
            if not filepath:
                return False, "INVALID_PARAMS", "Parameter 'filepath' is required for asset export."

        # 13. Validation for import_scene_asset and aliases
        elif tool_name in (TOOL_IMPORT_SCENE_ASSET, TOOL_IMPORT_SCENE):
            filepath = str(params.get("filepath", "")).strip()
            if not filepath:
                return False, "INVALID_PARAMS", "Parameter 'filepath' is required for asset import."

        # 14. Validation for duplicate_object and aliases
        elif tool_name in (TOOL_DUPLICATE_OBJECT, TOOL_DUPLICATE):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for duplication."
            for attr in ("location", "rotation_euler", "scale"):
                val = params.get(attr)
                if val is not None:
                    if not isinstance(val, (list, tuple)) or len(val) != 3:
                        return False, "INVALID_PARAMS", f"Transform attribute '{attr}' must be a 3-element list."

        # 15. Validation for rename_object and aliases
        elif tool_name in (TOOL_RENAME_OBJECT, TOOL_RENAME):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for renaming."
            new_name = str(params.get("new_name", "")).strip()
            if not new_name:
                return False, "INVALID_PARAMS", "Parameter 'new_name' is required for renaming."

        # 16. Validation for select_object and aliases
        elif tool_name in (TOOL_SELECT_OBJECT, TOOL_SELECT):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for selection."
            for k in ("state", "deselect_all", "make_active"):
                if k in params and not isinstance(params[k], bool):
                    return False, "INVALID_PARAMS", f"Parameter '{k}' must be a boolean."

        # 17. Validation for purge_orphaned_datablocks and aliases
        elif tool_name in (TOOL_PURGE_ORPHANED_DATABLOCKS, TOOL_PURGE_ORPHANS):
            for k in ("do_recursive", "do_local_ids", "do_linked_ids"):
                if k in params and not isinstance(params[k], bool):
                    return False, "INVALID_PARAMS", f"Parameter '{k}' must be a boolean."

        # 18. Validation for create_curve_or_text and aliases
        elif tool_name in (TOOL_CREATE_CURVE_OR_TEXT, TOOL_CREATE_CURVE, TOOL_CREATE_TEXT):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Object 'name' is required for curve or text creation."

        # 19. Validation for configure_physics and aliases
        elif tool_name in (TOOL_CONFIGURE_PHYSICS, TOOL_SETUP_PHYSICS, TOOL_MANAGE_PHYSICS):
            name = str(params.get("object_name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Parameter 'object_name' is required for physics configuration."

        elif tool_name == TOOL_BAKE_PHYSICS_SIMULATION:
            f_start = int(params.get("frame_start", 1))
            f_end = int(params.get("frame_end", 50))
            if f_start < 1 or f_end < f_start or (f_end - f_start) > 250:
                return False, "INVALID_PARAMS", "Invalid frame range: must be >= 1, end >= start, and span <= 250 frames."

        # 20. Validation for configure_animation_curve and aliases
        elif tool_name in (TOOL_CONFIGURE_ANIMATION_CURVE, TOOL_MANAGE_FCURVE, TOOL_SET_KEYFRAME_INTERPOLATION, TOOL_MANAGE_ACTION_SLOTS):
            name = str(params.get("object_name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Parameter 'object_name' is required for animation curve configuration."

        # 21. Validation for open_blend_file and aliases
        elif tool_name in (TOOL_OPEN_BLEND_FILE, TOOL_OPEN_PROJECT, TOOL_LOAD_BLEND_FILE):
            filepath = str(params.get("filepath", "")).strip()
            if not filepath:
                return False, "INVALID_PARAMS", "Parameter 'filepath' is required for opening a blend file."

        return True, None, None

    def execute_task(
        self,
        task: AgentTask,
        executor: BlenderExecutor,
        trusted_approval: Optional[bool] = None,
    ) -> AgentResult:
        """
        Executes a validated scene mutation task via BlenderExecutor.
        Enforces human approval requirements, input parameter constraints,
        and transactional boundary tracking with rollback verification.
        """
        t0 = time.time()
        params = dict(task.input_params or {})

        # 1. Reject untrusted model-supplied 'approved=True'
        if params.get("approved") is True:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[
                    "Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation. "
                    "Explicit user approval must be granted through a trusted approval mechanism."
                ],
                verification=VerificationResult(
                    expected_conditions={"scene_mutation": True, "human_approval": True},
                    observed_results={
                        "success": False,
                        "transaction_status": "NOT_APPLICABLE",
                        "error_code": "PERMISSION_DENIED",
                    },
                    status="FAIL",
                    details="Model-supplied approval flag rejected.",
                ),
                execution_time_ms=duration_ms,
            )

        # 2. Resolve target tool name
        tool_name = task.task_type
        if not tool_name:
            if task.required_capability == CAPABILITY_MODELING_PRIMITIVE:
                tool_name = TOOL_CREATE_PRIMITIVE
            elif task.required_capability == CAPABILITY_MODELING_TRANSFORM:
                tool_name = TOOL_TRANSFORM_OBJECT
            elif task.required_capability == CAPABILITY_MODELING_EXECUTION:
                if "do_recursive" in params or "purge" in str(task.task_id).lower():
                    tool_name = TOOL_PURGE_ORPHANED_DATABLOCKS
                elif "operations" in params or "code" in params:
                    tool_name = TOOL_EXECUTE_BLENDER_CODE
                elif "filepath" in params:
                    tool_name = TOOL_SAVE_BLEND_FILE
                else:
                    tool_name = TOOL_EXECUTE_BLENDER_CODE
            elif task.required_capability == CAPABILITY_MODELING_EDIT:
                if task.task_type in (
                    TOOL_BEVEL_MESH, TOOL_BEVEL_EDGES,
                    TOOL_SPLIT_MESH, TOOL_KNIFE_MESH, TOOL_BISECT_MESH,
                    TOOL_DISSOLVE_MESH, TOOL_MERGE_MESH,
                    TOOL_RECALCULATE_NORMALS, TOOL_ALIGN_NORMALS,
                    TOOL_EDIT_MESH, TOOL_EXTRUDE_MESH, TOOL_INSET_MESH,
                    TOOL_EXTRUDE_FACES, TOOL_INSET_FACES,
                ):
                    tool_name = task.task_type
                elif "offset" in params or "segments" in params or "affect" in params:
                    tool_name = TOOL_BEVEL_MESH
                elif "plane_co" in params or "plane_no" in params or "method" in params:
                    tool_name = TOOL_SPLIT_MESH
                elif "dissolve_type" in params:
                    tool_name = TOOL_DISSOLVE_MESH
                elif "mode" in params and params.get("mode") in ("CENTER", "COLLAPSE", "CURSOR", "DISTANCE"):
                    tool_name = TOOL_MERGE_MESH
                elif "action" in params and params.get("action") in ("RECALCULATE_OUTSIDE", "RECALCULATE_INSIDE", "FLIP"):
                    tool_name = TOOL_RECALCULATE_NORMALS
                elif "thickness" in params or "depth" in params:
                    tool_name = TOOL_INSET_MESH
                else:
                    tool_name = TOOL_EXTRUDE_MESH
            elif task.required_capability == CAPABILITY_MODELING_UV:
                if "angle_limit" in params or "island_margin" in params or "area_weight" in params:
                    tool_name = TOOL_UV_SMART_PROJECT
                else:
                    tool_name = TOOL_UV_UNWRAP
            elif task.required_capability == CAPABILITY_MODELING_KEYFRAME:
                if "interpolation" in params or "modifier_type" in params or "slot_name" in params or params.get("action") in ("set_interpolation", "add_modifier", "remove_modifier", "manage_slot", "list_fcurves"):
                    tool_name = TOOL_CONFIGURE_ANIMATION_CURVE
                else:
                    tool_name = TOOL_MANAGE_KEYFRAME
            elif task.required_capability == CAPABILITY_MODELING_SURFACE_DETAIL:
                tool_name = TOOL_DETAIL_SURFACE_FEATURES
            elif task.required_capability == CAPABILITY_MODELING_SURFACE_DETAIL_INSPECT:
                tool_name = TOOL_INSPECT_SURFACE_DETAIL
            elif task.required_capability == CAPABILITY_MODELING_ANATOMICAL_MASK:
                tool_name = TOOL_CONFIGURE_ANATOMICAL_MASK
            elif task.required_capability == CAPABILITY_MODELING_ANATOMICAL_MASK_INSPECT:
                tool_name = TOOL_INSPECT_ANATOMICAL_MASK
            elif task.required_capability == CAPABILITY_MODELING_SYMMETRIZE:
                tool_name = TOOL_SYMMETRIZE_MESH_GEOMETRY
            elif task.required_capability == CAPABILITY_MODELING_LANDMARK_DETECTION:
                tool_name = TOOL_DETECT_SEMANTIC_LANDMARKS
            elif task.required_capability == CAPABILITY_MODELING_SURFACE_BAKE:
                tool_name = TOOL_BAKE_MESH_SURFACE_MAP
            elif task.required_capability in (CAPABILITY_MODELING_MODIFIERS, "modeling.modifier_stack"):
                if task.task_type == TOOL_APPLY_MODIFIER or "apply" in str(task.task_id).lower() or params.get("action") == "apply":
                    tool_name = TOOL_APPLY_MODIFIER
                elif "action" in params:
                    tool_name = TOOL_EDIT_MODIFIER_STACK
                else:
                    tool_name = TOOL_EDIT_MODIFIER_STACK
            elif task.required_capability in (CAPABILITY_MODELING_MODIFIER_INSPECT, "modeling.modifier_stack_inspection"):
                tool_name = TOOL_INSPECT_MODIFIER_STACK
            elif task.required_capability == CAPABILITY_MODELING_GEONODES:
                tool_name = TOOL_CONFIGURE_GEOMETRY_NODES
            elif task.required_capability == CAPABILITY_MODELING_ASSET_IO:
                if "confirm_discard_unsaved" in params or "open" in str(task.task_id).lower() or params.get("action") == "open":
                    tool_name = TOOL_OPEN_BLEND_FILE
                elif "import" in str(task.task_id).lower() or params.get("action") == "import":
                    tool_name = TOOL_IMPORT_SCENE_ASSET
                else:
                    tool_name = TOOL_EXPORT_SCENE_ASSET
            elif task.required_capability == CAPABILITY_MODELING_OBJECT_OPS:
                if "curve_type" in params or "body" in params or "curve" in str(task.task_id).lower() or "text" in str(task.task_id).lower():
                    tool_name = TOOL_CREATE_CURVE_OR_TEXT
                elif "physics_type" in params or "rigid_body_type" in params or "physics" in str(task.task_id).lower():
                    tool_name = TOOL_CONFIGURE_PHYSICS
                elif "state" in params or "deselect_all" in params or "make_active" in params or "select" in str(task.task_id).lower():
                    tool_name = TOOL_SELECT_OBJECT
                elif "new_name" in params and "duplicate" not in str(task.task_id).lower():
                    tool_name = TOOL_RENAME_OBJECT
                else:
                    tool_name = TOOL_DUPLICATE_OBJECT
            elif "primitive_type" in params:
                tool_name = TOOL_CREATE_PRIMITIVE
            elif "operations" in params or "code" in params:
                tool_name = TOOL_EXECUTE_BLENDER_CODE
            elif "filepath" in params and ("format" in params or any(params["filepath"].endswith(f".{e}") for e in ("gltf", "glb", "fbx", "usd", "usdc", "usda"))):
                tool_name = TOOL_EXPORT_SCENE_ASSET
            elif "filepath" in params:
                tool_name = TOOL_SAVE_BLEND_FILE
            else:
                tool_name = TOOL_TRANSFORM_OBJECT

        # 3. Pre-execution Parameter & Constraint Validation
        is_valid, err_code, err_msg = self.validate_task_input(tool_name, params)
        if not is_valid:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[err_msg or "Validation error"],
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name, "scene_mutation": True},
                    observed_results={
                        "success": False,
                        "transaction_status": "NOT_APPLICABLE",
                        "error_code": err_code,
                        "error": err_msg,
                    },
                    status="FAIL",
                    details=f"Pre-execution validation failed: {err_msg}",
                ),
                execution_time_ms=duration_ms,
            )

        read_only = TOOL_DEFINITIONS.get(tool_name, {}).get("permission_tier") == "READ_ONLY"
        # Choose a compatible call signature before execution, never by retrying a
        # TypeError that may have occurred after Blender already performed work.
        try:
            kwargs = {}
            if trusted_approval is not None:
                import inspect
                try:
                    signature = inspect.signature(executor.execute_tool)
                    accepts_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()) or (
                        "trusted_approval" in signature.parameters and signature.parameters["trusted_approval"].kind in
                        (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY))
                except (TypeError, ValueError):
                    accepts_keyword = True  # Fail once if an opaque callable rejects the keyword.
                if accepts_keyword:
                    kwargs["trusted_approval"] = trusted_approval
            resp: BridgeResponse = executor.execute_tool(tool_name, params, **kwargs)
        except Exception as exc:
            logger.exception(f"ModelingAgent unexpected executor error for '{tool_name}': {exc}")
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[f"Execution exception: {str(exc)}"],
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name, "scene_mutation": not read_only},
                    observed_results={
                        "success": False,
                        "transaction_status": "ROLLBACK_UNVERIFIED",
                        "error_code": "EXECUTION_FAILED",
                    },
                    status="FAIL",
                    details=f"Unexpected executor exception: {exc}",
                ),
                execution_time_ms=duration_ms,
            )

        duration_ms = round((time.time() - t0) * 1000, 2)

        if resp.is_success and isinstance(resp.result, dict) and (resp.result.get("success") is False or
                tool_name == TOOL_GUIDE_MESH_LANDMARKS and resp.result.get("status") == "ERROR"):
            reason = resp.result.get("reason") or resp.result.get("error_reason") or "Modeling operation explicitly reported failure"
            resp = BridgeResponse.error(f"Modeling operation explicitly reported failure: {reason}")
        if tool_name in (TOOL_EDIT_MESH, TOOL_EXTRUDE_MESH, TOOL_EXTRUDE_FACES, TOOL_INSET_MESH, TOOL_INSET_FACES) and resp.is_success:
            try:
                observed = executor.execute_tool("inspect_scene_data", {"category":"mesh_topology", "target_name":params["name"], "element_domain":"vertices", "limit":1})
                actual = observed.result or {}
                reported = resp.result or {}
                matches = (observed.is_success and reported.get("verified") is True
                    and isinstance(reported.get("snapshot_id"), str) and reported["snapshot_id"] == actual.get("snapshot_id")
                    and (tool_name != TOOL_EDIT_MESH or reported.get("state_id") == actual.get("state_id") and bool(reported.get("state_id")))
                    and all(reported.get(key)==actual.get(field) for key,field in
                        (("new_vertex_count","vertex_count"),("new_edge_count","edge_count"),("new_face_count","polygon_count"))))
            except Exception:
                matches = False
            if not matches:
                resp = BridgeResponse.error("Mesh independent geometry readback failed; reconcile actual state; no retry or rollback claimed")
        elif tool_name == TOOL_CONFIGURE_MODELING_GEOMETRY and resp.is_success:
            try:
                readback=executor.execute_tool(TOOL_INSPECT_MODELING_GEOMETRY,{"name":params["name"],"modifier_name":params["modifier_name"]})
                receipt=resp.result or {};actual=readback.result or {}
                matches=readback.is_success and receipt.get("name")==params["name"] and receipt.get("action")==params["action"]
                matches=matches and all(value.get("success") is True and value.get("verified") is True for value in (receipt,actual))
                matches=matches and receipt.get("snapshot_id")==actual.get("snapshot_id") and all(receipt.get(key)==actual.get(key) for key in ("modifier_name","group_name","stack","nodes","links","parameters","base","evaluated"))
            except Exception:matches=False
            if not matches:resp=BridgeResponse.error("Geometry graph independent readback failed; reconcile actual state")
        elif tool_name == TOOL_INSPECT_MODELING_GEOMETRY and resp.is_success:
            observed=resp.result or {}
            if observed.get("success") is not True or observed.get("verified") is not True or observed.get("name")!=params["name"] or observed.get("modifier_name")!=params["modifier_name"] or not observed.get("snapshot_id"):
                resp=BridgeResponse.error("Geometry graph inspector did not return verified actual state")
        elif tool_name == TOOL_CONFIGURE_MODELING_OBJECT and resp.is_success:
            try:
                readback=executor.execute_tool(TOOL_INSPECT_MODELING_OBJECT,{"name":params["name"]})
                receipt=resp.result or {};actual=readback.result or {}
                matches=readback.is_success and receipt.get("name")==params["name"] and receipt.get("action")==params["action"]
                matches=matches and all(value.get("success") is True and value.get("verified") is True for value in (receipt,actual))
                matches=matches and receipt.get("snapshot_id")==actual.get("snapshot_id") and all(receipt.get(key)==actual.get(key) for key in ("matrix_world","matrix_basis","matrix_parent_inverse","parent","parent_type","selected","selected_objects","active_object"))
            except Exception:matches=False
            if not matches:resp=BridgeResponse.error("Object controls independent readback failed; reconcile actual state")
        elif tool_name == TOOL_SCULPT_MESH and resp.is_success and params.get("action") not in ("sculpt_organic_anatomy", "organic_anatomy"):
            try:
                receipt=resp.result or {}
                actual_resp=executor.execute_tool(TOOL_INSPECT_SCULPT_STATE,{"object_name":params["object_name"]})
                actual=actual_resp.result or {}
                matches=actual_resp.is_success and receipt.get("success") is True and receipt.get("verified") is True
                matches=matches and receipt.get("object_name")==params["object_name"] and receipt.get("snapshot_id")==actual.get("snapshot_id") and receipt.get("state_id")==actual.get("state_id")
                matches=matches and receipt.get("mode")==actual.get("mode") and receipt.get("topology_source")==actual.get("topology_source")
                matches=matches and all(receipt.get(k)==actual.get(v) for k,v in (("vertex_count","vertex_count"),("edge_count","edge_count"),("face_count","face_count")))
            except Exception:matches=False
            if not matches:resp=BridgeResponse.error("Sculpt independent mesh/state readback failed; reconcile actual Blender state")
        elif tool_name == TOOL_INSPECT_SCULPT_STATE and resp.is_success:
            actual=resp.result or {}
            if actual.get("success") is not True or actual.get("verified") is not True or actual.get("object_name")!=params["object_name"] or not actual.get("snapshot_id") or not actual.get("state_id"):
                resp=BridgeResponse.error("Sculpt inspector did not return verified actual state")
        elif tool_name == TOOL_INSPECT_MODELING_OBJECT and resp.is_success:
            observed=resp.result or {}
            if observed.get("success") is not True or observed.get("verified") is not True or observed.get("name")!=params["name"] or not observed.get("snapshot_id"):
                resp=BridgeResponse.error("Object inspector did not return verified actual state")
        elif tool_name == TOOL_CONFIGURE_CURVE_GEOMETRY and resp.is_success:
            try:
                target=params.get("output_name",params["name"])
                readback=executor.execute_tool(TOOL_INSPECT_CURVE_GEOMETRY,{"name":target})
                receipt=resp.result or {};actual=readback.result or {}
                matches=readback.is_success and receipt.get("name")==target and receipt.get("action")==params["action"]
                matches=matches and all(value.get("success") is True and value.get("verified") is True for value in (receipt,actual))
                matches=matches and receipt.get("snapshot_id")==actual.get("snapshot_id") and all(receipt.get(key)==actual.get(key) for key in ("type","settings","splines","geometry","evaluated","matrix_world"))
            except Exception:matches=False
            if not matches:resp=BridgeResponse.error("Curve/text independent readback failed; reconcile actual state")
        elif tool_name == TOOL_INSPECT_CURVE_GEOMETRY and resp.is_success:
            observed=resp.result or {}
            if observed.get("success") is not True or observed.get("verified") is not True or observed.get("name")!=params["name"] or not observed.get("snapshot_id"):
                resp=BridgeResponse.error("Curve/text inspector did not return verified actual state")
        elif tool_name in (TOOL_EDIT_MODIFIER_STACK, TOOL_APPLY_MODIFIER) and resp.is_success:
            try:
                readback=executor.execute_tool(TOOL_INSPECT_MODIFIER_STACK,{"name":params["name"]})
                receipt=resp.result or {}; actual=readback.result or {}
                matches=readback.is_success and all(value.get("success") is True and value.get("verified") is True for value in (receipt,actual))
                matches=matches and receipt.get("name")==params["name"] and receipt.get("snapshot_id")==actual.get("snapshot_id")
                matches=matches and all(receipt.get(key)==actual.get(key) for key in ("modifiers","base","evaluated","matrix_world"))
            except Exception:matches=False
            if not matches:resp=BridgeResponse.error("Modifier stack independent readback failed; reconcile actual state")
        elif tool_name == TOOL_INSPECT_MODIFIER_STACK and resp.is_success:
            observed=resp.result or {}
            if observed.get("success") is not True or observed.get("verified") is not True or observed.get("name")!=params["name"] or not observed.get("snapshot_id"):
                resp=BridgeResponse.error("Modifier stack inspector did not return verified actual state")
        elif tool_name == TOOL_CONFIGURE_MODIFIER and resp.is_success:
            from blender_addon.universal_mcp.bridge.modifier_contract import verify_modifier_readback
            try:
                inspected = executor.execute_tool(TOOL_INSPECT_MODIFIERS, {"name": params["name"]})
                matches = inspected.is_success and verify_modifier_readback(params, resp.result, inspected.result)
            except Exception:
                matches = False
            if not matches:
                resp = BridgeResponse.error("Modifier independent readback failed; execution/rollback must be reconciled")
        elif tool_name == TOOL_INSPECT_MODIFIERS and resp.is_success:
            observed = resp.result or {}
            if observed.get("success") is not True or observed.get("verified") is not True or observed.get("name") != params["name"] or not isinstance(observed.get("modifiers"), list):
                resp = BridgeResponse.error("Modifier inspection did not return verified actual state")

        # 5. Handle Execution Outcome & Transaction Verification
        if resp.is_success:
            raw_result = dict(resp.result or {})
            evidence_refs: List[str] = []

            if tool_name in (TOOL_LOAD_REFERENCE_IMAGE, TOOL_CROP_REFERENCE_IMAGE):
                obj_name = raw_result.get("name", params.get("name"))
                if obj_name:
                    evidence_refs.append(f"reference_object:{obj_name}")
                if "display_mode" in raw_result:
                    evidence_refs.append(f"display_mode:{raw_result.get('display_mode')}")
                if "image_name" in raw_result:
                    evidence_refs.append(f"image_name:{raw_result.get('image_name')}")
                if "crop_box" in raw_result:
                    evidence_refs.append(f"crop_box:{raw_result['crop_box']}")
                if "crop_dimensions" in raw_result:
                    evidence_refs.append(f"crop_dimensions:{raw_result['crop_dimensions']}")
                if "dimensions" in raw_result:
                    evidence_refs.append(f"dimensions:{raw_result['dimensions']}")
                if "aspect_ratio" in raw_result:
                    evidence_refs.append(f"aspect_ratio:{raw_result['aspect_ratio']}")
                if "crop_aspect_ratio" in raw_result:
                    evidence_refs.append(f"crop_aspect_ratio:{raw_result['crop_aspect_ratio']}")
                if "output_image_path" in raw_result:
                    evidence_refs.append(f"output_path:{raw_result['output_image_path']}")
            elif tool_name == TOOL_COMPARE_SILHOUETTE_ALIGNMENT:
                if "alignment_status" in raw_result:
                    evidence_refs.append(f"alignment_status:{raw_result['alignment_status']}")
                if "iou" in raw_result:
                    evidence_refs.append(f"iou:{raw_result['iou']}")
                if "dice_coefficient" in raw_result:
                    evidence_refs.append(f"dice:{raw_result['dice_coefficient']}")
                if "divergence_score" in raw_result:
                    evidence_refs.append(f"divergence:{raw_result['divergence_score']}")
            elif tool_name == TOOL_CALIBRATE_REFERENCE_VIEWS:
                if "status" in raw_result:
                    evidence_refs.append(f"calibration_status:{raw_result['status']}")
                if "calibrated_objects" in raw_result:
                    evidence_refs.append(f"calibrated_count:{len(raw_result['calibrated_objects'])}")
            elif tool_name == TOOL_OPTIMIZE_MESH_SILHOUETTE:
                if "status" in raw_result:
                    evidence_refs.append(f"optimization_status:{raw_result['status']}")
                if "iou_improvement" in raw_result:
                    evidence_refs.append(f"iou_improvement:{raw_result['iou_improvement']}")
                if "divergence_reduction" in raw_result:
                    evidence_refs.append(f"divergence_reduction:{raw_result['divergence_reduction']}")
                if "topology_preserved" in raw_result:
                    evidence_refs.append(f"topology_preserved:{raw_result['topology_preserved']}")
            elif tool_name == TOOL_FIT_MULTIVIEW_SILHOUETTE:
                if "status" in raw_result:
                    evidence_refs.append(f"multiview_status:{raw_result['status']}")
                if "aggregate_improvement" in raw_result:
                    evidence_refs.append(f"aggregate_improvement:{raw_result['aggregate_improvement']}")
                if "topology_preserved" in raw_result:
                    evidence_refs.append(f"topology_preserved:{raw_result['topology_preserved']}")
                if "final_aggregate_score" in raw_result:
                    evidence_refs.append(f"final_aggregate_score:{raw_result['final_aggregate_score']}")
            elif tool_name == TOOL_REFINE_MESH_MULTIRESOLUTION:
                if "status" in raw_result:
                    evidence_refs.append(f"refinement_status:{raw_result['status']}")
                if "final_vertex_count" in raw_result:
                    evidence_refs.append(f"final_vertex_count:{raw_result['final_vertex_count']}")
                if "final_face_count" in raw_result:
                    evidence_refs.append(f"final_face_count:{raw_result['final_face_count']}")
                if "aggregate_improvement" in raw_result:
                    evidence_refs.append(f"aggregate_improvement:{raw_result['aggregate_improvement']}")
            elif tool_name == TOOL_SCULPT_ORGANIC_ANATOMY:
                if "sculpt_status" in raw_result:
                    evidence_refs.append(f"sculpt_status:{raw_result['sculpt_status']}")
                if "brush_type" in raw_result:
                    evidence_refs.append(f"brush_type:{raw_result['brush_type']}")
                if "final_vertex_count" in raw_result:
                    evidence_refs.append(f"final_vertex_count:{raw_result['final_vertex_count']}")
                if "final_face_count" in raw_result:
                    evidence_refs.append(f"final_face_count:{raw_result['final_face_count']}")
                if "max_vertex_displacement" in raw_result:
                    evidence_refs.append(f"max_displacement:{raw_result['max_vertex_displacement']}")
                if "aggregate_improvement" in raw_result and raw_result["aggregate_improvement"] is not None:
                    evidence_refs.append(f"aggregate_improvement:{raw_result['aggregate_improvement']}")
            elif tool_name == TOOL_CONFIGURE_SEMANTIC_LANDMARKS:
                if "landmarks_count" in raw_result:
                    evidence_refs.append(f"landmarks_count:{raw_result['landmarks_count']}")
                if "action" in raw_result:
                    evidence_refs.append(f"action:{raw_result['action']}")
                if "target_object" in raw_result:
                    evidence_refs.append(f"target_object:{raw_result['target_object']}")
            elif tool_name == TOOL_INSPECT_SEMANTIC_LANDMARKS:
                if "landmarks_count" in raw_result:
                    evidence_refs.append(f"landmarks_count:{raw_result['landmarks_count']}")
                if "aggregate_rmse" in raw_result:
                    evidence_refs.append(f"aggregate_rmse:{raw_result['aggregate_rmse']}")
                if "mean_landmark_error" in raw_result:
                    evidence_refs.append(f"mean_landmark_error:{raw_result['mean_landmark_error']}")
            elif tool_name == TOOL_GUIDE_MESH_LANDMARKS:
                if "guidance_status" in raw_result:
                    evidence_refs.append(f"guidance_status:{raw_result['guidance_status']}")
                if "initial_landmark_rmse" in raw_result:
                    evidence_refs.append(f"initial_landmark_rmse:{raw_result['initial_landmark_rmse']}")
                if "final_landmark_rmse" in raw_result:
                    evidence_refs.append(f"final_landmark_rmse:{raw_result['final_landmark_rmse']}")
                if "landmark_error_reduction" in raw_result:
                    evidence_refs.append(f"landmark_error_reduction:{raw_result['landmark_error_reduction']}")
                if "landmarks_count" in raw_result:
                    evidence_refs.append(f"landmarks_count:{raw_result['landmarks_count']}")
                if "max_vertex_displacement" in raw_result:
                    evidence_refs.append(f"max_displacement:{raw_result['max_vertex_displacement']}")
            elif tool_name == TOOL_DETAIL_SURFACE_FEATURES:
                if "detailing_status" in raw_result:
                    evidence_refs.append(f"detailing_status:{raw_result['detailing_status']}")
                if "feature_type" in raw_result:
                    evidence_refs.append(f"feature_type:{raw_result['feature_type']}")
                if "surface_roughness_delta" in raw_result:
                    evidence_refs.append(f"surface_roughness_delta:{raw_result['surface_roughness_delta']}")
                if "max_vertex_displacement" in raw_result:
                    evidence_refs.append(f"max_displacement:{raw_result['max_vertex_displacement']}")
                if "affected_vertices_count" in raw_result:
                    evidence_refs.append(f"affected_vertices_count:{raw_result['affected_vertices_count']}")
                if "landmarks_preserved" in raw_result:
                    evidence_refs.append(f"landmarks_preserved:{raw_result['landmarks_preserved']}")
            elif tool_name == TOOL_INSPECT_SURFACE_DETAIL:
                if "surface_roughness" in raw_result:
                    evidence_refs.append(f"surface_roughness:{raw_result['surface_roughness']}")
                if "vertex_count" in raw_result:
                    evidence_refs.append(f"vertex_count:{raw_result['vertex_count']}")
                if "face_count" in raw_result:
                    evidence_refs.append(f"face_count:{raw_result['face_count']}")
            elif tool_name == TOOL_CREATE_PRIMITIVE:
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"created_object:{obj_name}")
                evidence_refs.append(f"primitive_type:{raw_result.get('primitive_type')}")
                if "location" in raw_result:
                    evidence_refs.append(f"location:{raw_result['location']}")

            elif tool_name == TOOL_TRANSFORM_OBJECT:
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"transformed_object:{obj_name}")
                if "location" in raw_result:
                    evidence_refs.append(f"location:{raw_result['location']}")
                if "relative" in raw_result:
                    evidence_refs.append(f"relative:{raw_result['relative']}")

            elif tool_name == TOOL_EXECUTE_BLENDER_CODE:
                count = raw_result.get("operations_count", 0)
                evidence_refs.append(f"operations_executed:{count}")
                evidence_refs.append(f"transactional:{raw_result.get('transactional', True)}")
                for op in raw_result.get("operations", [])[:5]:
                    evidence_refs.append(f"action:{op.get('action')}:{op.get('target')}")

            elif tool_name == TOOL_DELETE_OBJECT:
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"deleted_object:{obj_name}")
                evidence_refs.append(f"deleted:{raw_result.get('deleted', True)}")

            elif tool_name == TOOL_SAVE_BLEND_FILE:
                evidence_refs.append(f"saved_filepath:{raw_result.get('filepath')}")
                evidence_refs.append(f"saved:{raw_result.get('saved', True)}")

            elif tool_name in (TOOL_EXTRUDE_MESH, TOOL_EXTRUDE_FACES):
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"extruded_mesh:{obj_name}")
                evidence_refs.append(f"faces_extruded:{raw_result.get('faces_extruded', 0)}")
                evidence_refs.append(f"new_face_count:{raw_result.get('new_face_count', 0)}")

            elif tool_name in (TOOL_INSET_MESH, TOOL_INSET_FACES):
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"inset_mesh:{obj_name}")
                evidence_refs.append(f"faces_inset:{raw_result.get('faces_inset', 0)}")
                evidence_refs.append(f"new_face_count:{raw_result.get('new_face_count', 0)}")

            elif tool_name in (TOOL_UV_UNWRAP, TOOL_UNWRAP_MESH):
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"unwrapped_mesh:{obj_name}")
                evidence_refs.append(f"uv_layer:{raw_result.get('uv_layer', 'UVMap')}")
                evidence_refs.append(f"faces_unwrapped:{raw_result.get('faces_unwrapped', 0)}")

            elif tool_name in (TOOL_UV_SMART_PROJECT, TOOL_SMART_PROJECT, TOOL_SMART_UV_PROJECT, TOOL_UV_PROJECT):
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"projected_mesh:{obj_name}")
                evidence_refs.append(f"uv_layer:{raw_result.get('uv_layer', 'UVMap')}")
                evidence_refs.append(f"faces_projected:{raw_result.get('faces_projected', 0)}")

            elif tool_name == TOOL_MANAGE_UV_SEAMS:
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"uv_seams:{obj_name}")
                evidence_refs.append(f"action:{raw_result.get('action')}")
                evidence_refs.append(f"seams_count:{raw_result.get('total_seam_count', 0)}")

            elif tool_name == TOOL_PACK_UV_ISLANDS:
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"packed_uv:{obj_name}")
                evidence_refs.append(f"uv_layer:{raw_result.get('uv_layer')}")
                evidence_refs.append(f"margin:{raw_result.get('margin')}")

            elif tool_name == TOOL_MANAGE_UV_LAYERS:
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"uv_layers:{obj_name}")
                evidence_refs.append(f"action:{raw_result.get('action')}")
                evidence_refs.append(f"active_layer:{raw_result.get('active_uv_layer')}")

            elif tool_name == TOOL_INSPECT_UV_MESH:
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"inspected_uv:{obj_name}")
                evidence_refs.append(f"uv_layer_count:{raw_result.get('uv_layer_count', 0)}")
                evidence_refs.append(f"seam_count:{raw_result.get('seam_count', 0)}")

            elif tool_name in (TOOL_MANAGE_KEYFRAME, TOOL_INSERT_KEYFRAME, TOOL_DELETE_KEYFRAME):
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"keyframe:{obj_name}")
                evidence_refs.append(f"property:{raw_result.get('property_path')}")
                evidence_refs.append(f"frame:{raw_result.get('frame')}")

            elif tool_name in (TOOL_CONFIGURE_GEOMETRY_NODES, TOOL_INSPECT_GEOMETRY_NODES):
                obj_name = raw_result.get("name", params.get("name"))
                evidence_refs.append(f"geometry_nodes:{obj_name}")
                evidence_refs.append(f"modifier:{raw_result.get('modifier_name')}")
                evidence_refs.append(f"action:{raw_result.get('action')}")

            elif tool_name == TOOL_CREATE_ARMATURE:
                evidence_refs.append(f"armature:{raw_result.get('armature_name')}")
                evidence_refs.append(f"snapshot_id:{raw_result.get('snapshot_id')}")

            elif tool_name == TOOL_EDIT_ARMATURE_BONES:
                evidence_refs.append(f"armature:{raw_result.get('armature_name')}")
                evidence_refs.append(f"bones_count:{raw_result.get('bones_count', 0)}")
                evidence_refs.append(f"snapshot_id:{raw_result.get('snapshot_id')}")

            elif tool_name == TOOL_INSPECT_ARMATURE:
                evidence_refs.append(f"armature:{raw_result.get('armature_name')}")
                evidence_refs.append(f"bones_count:{raw_result.get('bones_count', 0)}")

            elif tool_name == TOOL_BIND_ARMATURE_MESH:
                evidence_refs.append(f"mesh:{raw_result.get('mesh_object_name')}")
                evidence_refs.append(f"armature:{raw_result.get('armature_name')}")
                evidence_refs.append(f"modifier:{raw_result.get('modifier_name')}")

            elif tool_name == TOOL_CONFIGURE_BONE_CONSTRAINT:
                evidence_refs.append(f"bone:{raw_result.get('bone_name')}")
                evidence_refs.append(f"constraint:{raw_result.get('constraint_name')}")
                evidence_refs.append(f"type:{raw_result.get('constraint_type')}")

            elif tool_name in (TOOL_EXPORT_SCENE_ASSET, TOOL_EXPORT_SCENE):
                evidence_refs.append(f"exported_asset:{raw_result.get('filepath')}")
                evidence_refs.append(f"format:{raw_result.get('format')}")
                evidence_refs.append(f"file_size:{raw_result.get('file_size_bytes', 0)}")
                if raw_result.get("sha256"):
                    evidence_refs.append(f"sha256:{raw_result.get('sha256')}")
                if raw_result.get("sidecar_path"):
                    evidence_refs.append(f"sidecar:{raw_result.get('sidecar_path')}")

            elif tool_name in (TOOL_IMPORT_SCENE_ASSET, TOOL_IMPORT_SCENE):
                evidence_refs.append(f"imported_asset:{raw_result.get('filepath')}")
                evidence_refs.append(f"format:{raw_result.get('format')}")
                evidence_refs.append(f"imported_count:{raw_result.get('imported_count', 0)}")
                if "checksum_verified" in raw_result:
                    evidence_refs.append(f"checksum_verified:{raw_result.get('checksum_verified')}")

            elif tool_name in (TOOL_DUPLICATE_OBJECT, TOOL_DUPLICATE):
                evidence_refs.append(f"original_object:{raw_result.get('name')}")
                evidence_refs.append(f"duplicated_object:{raw_result.get('duplicate_name')}")
                evidence_refs.append(f"data_independent:{raw_result.get('data_independent', True)}")

            elif tool_name in (TOOL_RENAME_OBJECT, TOOL_RENAME):
                evidence_refs.append(f"old_name:{raw_result.get('old_name')}")
                evidence_refs.append(f"renamed_object:{raw_result.get('new_name')}")

            elif tool_name in (TOOL_SELECT_OBJECT, TOOL_SELECT):
                evidence_refs.append(f"selected_target:{raw_result.get('name')}")
                evidence_refs.append(f"state:{raw_result.get('state')}")
                evidence_refs.append(f"is_selected:{raw_result.get('is_selected')}")
                evidence_refs.append(f"active_object:{raw_result.get('active_object')}")

            elif tool_name in (TOOL_PURGE_ORPHANED_DATABLOCKS, TOOL_PURGE_ORPHANS):
                evidence_refs.append(f"purged_count:{raw_result.get('purged_count', 0)}")
                evidence_refs.append(f"do_recursive:{raw_result.get('do_recursive', True)}")

            elif tool_name in (TOOL_CREATE_CURVE_OR_TEXT, TOOL_CREATE_CURVE, TOOL_CREATE_TEXT):
                evidence_refs.append(f"curve_object:{raw_result.get('name')}")
                evidence_refs.append(f"curve_type:{raw_result.get('curve_type')}")
                evidence_refs.append(f"created:{raw_result.get('created', True)}")

            elif tool_name in (TOOL_CONFIGURE_PHYSICS, TOOL_SETUP_PHYSICS, TOOL_MANAGE_PHYSICS):
                evidence_refs.append(f"physics_object:{raw_result.get('object_name')}")
                evidence_refs.append(f"physics_type:{raw_result.get('physics_type')}")
                evidence_refs.append(f"action:{raw_result.get('action')}")
                if "snapshot_id" in raw_result:
                    evidence_refs.append(f"snapshot_id:{raw_result.get('snapshot_id')}")

            elif tool_name == TOOL_INSPECT_PHYSICS:
                if "snapshot_id" in raw_result:
                    evidence_refs.append(f"snapshot_id:{raw_result.get('snapshot_id')}")
                if "target" in raw_result and raw_result["target"]:
                    evidence_refs.append(f"target:{raw_result['target'].get('object_name')}")

            elif tool_name == TOOL_BAKE_PHYSICS_SIMULATION:
                evidence_refs.append(f"physics_type:{raw_result.get('physics_type')}")
                evidence_refs.append(f"frame_count:{raw_result.get('frame_count')}")
                if "snapshot_id" in raw_result:
                    evidence_refs.append(f"snapshot_id:{raw_result.get('snapshot_id')}")

            elif tool_name in (TOOL_CONFIGURE_ANIMATION_CURVE, TOOL_MANAGE_FCURVE, TOOL_SET_KEYFRAME_INTERPOLATION, TOOL_MANAGE_ACTION_SLOTS):
                evidence_refs.append(f"anim_object:{raw_result.get('object_name')}")
                evidence_refs.append(f"action:{raw_result.get('action')}")
                if "interpolation" in raw_result:
                    evidence_refs.append(f"interpolation:{raw_result.get('interpolation')}")

            elif tool_name in (TOOL_OPEN_BLEND_FILE, TOOL_OPEN_PROJECT, TOOL_LOAD_BLEND_FILE):
                evidence_refs.append(f"opened_project:{raw_result.get('filepath')}")
                evidence_refs.append(f"object_count:{raw_result.get('object_count', 0)}")

            verification = VerificationResult(
                expected_conditions={"tool": tool_name, "scene_mutation": not read_only},
                observed_results={
                    "success": True,
                    "transaction_status": "NOT_APPLICABLE" if read_only else raw_result.get("transaction_status", "COMMITTED"),
                    "evidence_count": len(evidence_refs),
                },
                status="PASS",
                details=(f"Read-only {tool_name} independently observed." if read_only else f"{tool_name} completed with verified unchanged state." if raw_result.get("transaction_status")=="NO_CHANGE_VERIFIED" else f"Scene mutation '{tool_name}' successfully executed and committed."),
            )

            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.SUCCEEDED,
                output=raw_result,
                evidence_references=evidence_refs,
                verification=verification,
                execution_time_ms=duration_ms,
            )

        else:
            err_msg = resp.message or "Execution failed"
            err_lower = err_msg.lower()
            approval = (resp.result or {}).get("approval", {}) if isinstance(resp.result, dict) else {}
            approval = approval if isinstance(approval, dict) else {}
            approval_state = approval.get("status")
            approval_pending = approval_state == "pending" and bool(approval.get("request_id"))

            # Distinguish transaction rollback status
            verified_tools = {TOOL_EDIT_MESH, TOOL_EDIT_MODIFIER_STACK, TOOL_CONFIGURE_CURVE_GEOMETRY,
                              TOOL_CONFIGURE_MODELING_OBJECT, TOOL_CONFIGURE_MODELING_GEOMETRY,
                              TOOL_EXTRUDE_MESH, TOOL_INSET_MESH, TOOL_EXTRUDE_FACES, TOOL_INSET_FACES,
                              TOOL_CREATE_CURVE_OR_TEXT, TOOL_SELECT_OBJECT, TOOL_SELECT}
            # Only these kernels emit the marker after actual state restoration.
            # An arbitrary undo/rolled-back phrase, or a marker embedded in user
            # text, is not evidence that Blender restored anything.
            if not read_only and tool_name in verified_tools and err_msg.startswith("ROLLED_BACK_VERIFIED:"):
                tx_status = "ROLLED_BACK"
                rollback_verified = True
            elif read_only or approval_state in {"pending", "denied", "cancelled", "expired", "not_found", "unknown"} or any(t in err_lower for t in ("denied", "permission", "approval required", "untrusted")):
                tx_status = "NOT_APPLICABLE"
                rollback_verified = False
            else:
                tx_status = "ROLLBACK_UNVERIFIED"
                rollback_verified = False

            # Categorize error code
            if approval_pending:
                err_code = "APPROVAL_REQUIRED"
            elif approval_state == "expired":
                err_code = "APPROVAL_EXPIRED"
            elif approval_state in {"denied", "cancelled"}:
                err_code = "PERMISSION_DENIED"
            elif "approval required" in err_lower:
                err_code = "APPROVAL_REQUIRED"
            elif "permission" in err_lower or "denied" in err_lower:
                err_code = "PERMISSION_DENIED"
            elif "unsupported" in err_lower:
                err_code = "UNSUPPORTED_REQUEST"
            elif "security" in err_lower or "ast" in err_lower:
                err_code = "SECURITY_VIOLATION"
            elif "not found" in err_lower or "does not exist" in err_lower:
                err_code = "DATA_UNAVAILABLE"
            elif "collision" in err_lower or "already exists" in err_lower:
                err_code = "NAME_COLLISION"
            else:
                err_code = "EXECUTION_FAILED"

            verification = VerificationResult(
                expected_conditions={"tool": tool_name, "scene_mutation": not read_only},
                observed_results={
                    "success": False,
                    "transaction_status": tx_status,
                    "rollback_verified": rollback_verified,
                    "error_code": err_code,
                    "error": err_msg,
                    **({"approval_pending": True, "approval_request_id": approval["request_id"],
                        "approval_expires_at": approval.get("expires_at")} if approval_pending else {}),
                },
                status="FAIL",
                details=(
                    f"Mutation '{tool_name}' failed with status '{tx_status}'. "
                    f"Rollback verified: {rollback_verified}."
                ),
            )

            agent_status = TaskStatus.AWAITING_APPROVAL if err_code == "APPROVAL_REQUIRED" else TaskStatus.FAILED

            return AgentResult(
                task_id=task.task_id,
                status=agent_status,
                errors=[err_msg],
                verification=verification,
                execution_time_ms=duration_ms,
            )
