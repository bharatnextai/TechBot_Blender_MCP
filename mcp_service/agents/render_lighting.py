"""
Render and Lighting Agent for Universal MCP.
Provides verified scene lighting creation, configuration, and world background settings
in Blender 5.2.2 LTS.

Enforces:
1. Strict parameter validation (light types POINT, SUN, SPOT, AREA, energy, colors [0.0, 1.0]).
2. Rejection of unsupported render/compositing/light-linking features with structured errors.
3. Trusted human approval pipeline bindings (model approved=True rejection).
4. Post-operation read-only inspection verification (list_objects, inspect_scene_data).
"""

from typing import Dict, Any, List, Optional, Set, Tuple
import time
import logging
import math

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    AgentResult,
    VerificationResult,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse, render_job_failure_snapshot
from shared.schemas.tool_schemas import (
    TOOL_INSPECT_RENDER_OUTPUT,
    validate_tool_input,
    TOOL_CREATE_LIGHT,
    TOOL_CONFIGURE_LIGHT,
    TOOL_CONFIGURE_WORLD,
    TOOL_CREATE_CAMERA,
    TOOL_CONFIGURE_CAMERA,
    TOOL_EDIT_CAMERA,
    TOOL_SWITCH_CAMERA,
    TOOL_CONFIGURE_RENDER_SETTINGS,
    TOOL_RENDER_SCENE,
    TOOL_LIST_OBJECTS,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_MANAGE_COMPOSITOR_NODES,
    TOOL_CONFIGURE_COMPOSITOR,
    TOOL_MANAGE_COMPOSITOR,
    TOOL_INSPECT_COMPOSITOR_PIPELINE,
    TOOL_DEFINITIONS,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_RenderLightingAgent")

RENDER_LIGHTING_AGENT_ID = "agent.render_lighting"
CAPABILITY_LIGHTING_MANAGE = "lighting.manage"
CAPABILITY_WORLD_MANAGE = "world.manage"
CAPABILITY_LIGHTING_INSPECT = "lighting.inspect"

SUPPORTED_LIGHTING_TOOLS: Set[str] = {
    TOOL_INSPECT_RENDER_OUTPUT,
    TOOL_CREATE_LIGHT,
    TOOL_CONFIGURE_LIGHT,
    TOOL_CONFIGURE_WORLD,
    TOOL_CREATE_CAMERA,
    TOOL_CONFIGURE_CAMERA,
    TOOL_EDIT_CAMERA,
    TOOL_SWITCH_CAMERA,
    TOOL_CONFIGURE_RENDER_SETTINGS,
    TOOL_RENDER_SCENE,
    TOOL_LIST_OBJECTS,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_MANAGE_COMPOSITOR_NODES,
    TOOL_CONFIGURE_COMPOSITOR,
    TOOL_MANAGE_COMPOSITOR,
    TOOL_INSPECT_COMPOSITOR_PIPELINE,
}

ALLOWED_LIGHT_TYPES: Set[str] = {
    "POINT",
    "SUN",
    "SPOT",
    "AREA",
}

UNSUPPORTED_LIGHTING_FEATURES: Set[str] = {
    "render_engine",
    "engine",
    "cycles",
    "luxcore",
    "eevee_next",
    "octane",
    "compositing",
    "compositor",
    "composite_nodes",
    "light_linking",
    "light_groups",
    "shadow_baking",
    "bake",
    "radiosity",
    "global_illumination_baking",
}


def create_render_lighting_manifest(version: str = "0.1.13") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Render & Lighting Agent.
    Declares only verified scene lighting, camera, render, and world background operations.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in (
            TOOL_INSPECT_RENDER_OUTPUT,
            TOOL_CREATE_LIGHT,
            TOOL_CONFIGURE_LIGHT,
            TOOL_CONFIGURE_WORLD,
            TOOL_CREATE_CAMERA,
            TOOL_CONFIGURE_CAMERA,
            TOOL_EDIT_CAMERA,
            TOOL_SWITCH_CAMERA,
            TOOL_CONFIGURE_RENDER_SETTINGS,
            TOOL_RENDER_SCENE,
            TOOL_LIST_OBJECTS,
            TOOL_INSPECT_SCENE_DATA,
            TOOL_GET_OBJECT_DETAILS,
        )
        if name in TOOL_DEFINITIONS
    }
    return AgentManifest(
        agent_id=RENDER_LIGHTING_AGENT_ID,
        name="Render and Lighting Agent",
        version=version,
        description=(
            "Creates and positions scene lights and cameras, configures render settings and world background, "
            "and inspects illumination data with human approval gating and post-operation verification."
        ),
        capabilities=[
            CapabilityDescriptor(
                capability_id=CAPABILITY_LIGHTING_MANAGE,
                description="Creates and configures scene lights and cameras with transform and optical parameters.",
                supported_task_types=[TOOL_CREATE_LIGHT, TOOL_CONFIGURE_LIGHT, TOOL_CREATE_CAMERA, TOOL_CONFIGURE_CAMERA, TOOL_EDIT_CAMERA, TOOL_SWITCH_CAMERA],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_WORLD_MANAGE,
                description="Configures scene world background color, strength, render output settings, and compositor nodes.",
                supported_task_types=[
                    TOOL_CONFIGURE_WORLD,
                    TOOL_CONFIGURE_RENDER_SETTINGS,
                    TOOL_RENDER_SCENE,
                    TOOL_MANAGE_COMPOSITOR_NODES,
                    TOOL_CONFIGURE_COMPOSITOR,
                    TOOL_MANAGE_COMPOSITOR,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_LIGHTING_INSPECT,
                description="Inspects active scene lights, object hierarchies, world settings, and compositor pipelines.",
                supported_task_types=[TOOL_LIST_OBJECTS, TOOL_INSPECT_SCENE_DATA, TOOL_GET_OBJECT_DETAILS, TOOL_INSPECT_RENDER_OUTPUT, TOOL_INSPECT_COMPOSITOR_PIPELINE],
                read_write="READ_ONLY",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
        ],
        input_schemas=schemas,
        constraints={"still_render_output_receipts": {
            "status": "VERIFIED",
            "scope": "Fresh FINISHED still render and separate registered-output readback; PNG CRC/deflate/dimensions, bounded in-memory receipts; not whole rendering",
            "evidence": "docs/verification/STILL_RENDER_OUTPUT_V0144.md",
        }, "camera_render_approval_handoff": {
            "status": "VERIFIED",
            "scope": "Public camera and still-render provider handoff, pending task resume and replay rejection under isolated test policy; not human UI proof",
            "evidence": "docs/verification/CAMERA_RENDER_HANDOFF_V0143.md",
        }, "e2e_audit": {
            "scope": ["lighting_world", "cameras", "rendering"],
            "implementation_status": "PARTIALLY IMPLEMENTED",
            "verification_status": "NOT VERIFIED",
            "evidence": "docs/verification/TEN_CAPABILITY_EVIDENCE.json",
        }},
        priority=10,
        enabled=True,
    )


class RenderLightingAgent:
    """
    Specialized Render & Lighting Agent.
    Validates light and world configuration inputs, enforces human approval for mutations,
    executes via BlenderExecutor, and performs post-operation read-only inspection.
    """

    def __init__(self, version: str = "0.1.13"):
        self.version = version
        self._manifest = create_render_lighting_manifest(version=self.version)

    @property
    def agent_id(self) -> str:
        return RENDER_LIGHTING_AGENT_ID

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def get_manifest(self) -> AgentManifest:
        return self._manifest

    def can_handle(self, task: AgentTask) -> bool:
        """Checks whether this agent can handle the requested capability or task type."""
        req_cap = task.required_capability
        if req_cap and req_cap not in (
            CAPABILITY_LIGHTING_MANAGE,
            CAPABILITY_WORLD_MANAGE,
            CAPABILITY_LIGHTING_INSPECT,
        ):
            return False
        if task.task_type:
            return task.task_type in SUPPORTED_LIGHTING_TOOLS
        return True

    def validate_task_input(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Performs strict pre-execution validation of lighting and world inputs.
        Returns: (is_valid, error_code, error_message)
        """
        if tool_name not in SUPPORTED_LIGHTING_TOOLS:
            return (
                False,
                "UNSUPPORTED_REQUEST",
                f"Unsupported lighting tool '{tool_name}'. Supported tools: {sorted(list(SUPPORTED_LIGHTING_TOOLS))}",
            )

        # Check for unsupported render/compositing/linking features passed in params
        if tool_name not in (TOOL_CONFIGURE_RENDER_SETTINGS, TOOL_RENDER_SCENE, TOOL_MANAGE_COMPOSITOR_NODES, TOOL_CONFIGURE_COMPOSITOR, TOOL_MANAGE_COMPOSITOR, TOOL_INSPECT_COMPOSITOR_PIPELINE):
            for key, val in params.items():
                k_lower = key.lower()
                val_lower = str(val).lower() if isinstance(val, (str, bool)) else ""
                if k_lower in UNSUPPORTED_LIGHTING_FEATURES or val_lower in UNSUPPORTED_LIGHTING_FEATURES:
                    return (
                        False,
                        "UNSUPPORTED_REQUEST",
                        f"Unsupported render/lighting feature '{key}={val}'. Render engines, compositing, "
                        "light linking, and baking are not supported in this phase.",
                    )

        # 1. Validation for create_light and configure_light
        if tool_name in (TOOL_CREATE_LIGHT, TOOL_CONFIGURE_LIGHT):
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Light 'name' is required and cannot be empty."

            light_type = str(params.get("light_type", "POINT")).strip().upper()
            if light_type not in ALLOWED_LIGHT_TYPES:
                return (
                    False,
                    "UNSUPPORTED_REQUEST",
                    f"Unsupported light type '{light_type}'. Allowed light types: {sorted(list(ALLOWED_LIGHT_TYPES))}.",
                )

            energy = params.get("energy")
            if energy is not None:
                if not isinstance(energy, (int, float)) or isinstance(energy, bool):
                    return False, "INVALID_PARAMS", "Parameter 'energy' must be a number."
                if float(energy) < 0.0:
                    return False, "INVALID_PARAMS", f"Parameter 'energy' must be non-negative, got {energy}."

            color = params.get("color")
            if color is not None:
                if not isinstance(color, (list, tuple)) or len(color) != 3:
                    return False, "INVALID_PARAMS", "Parameter 'color' must be a 3-element list [r, g, b]."
                for idx, c in enumerate(color):
                    if not isinstance(c, (int, float)) or isinstance(c, bool):
                        return False, "INVALID_PARAMS", f"Color component {idx} must be a number."
                    if c < 0.0 or c > 1.0:
                        return False, "INVALID_PARAMS", f"Color component {idx} must be between 0.0 and 1.0, got {c}."

            location = params.get("location")
            if location is not None:
                if not isinstance(location, (list, tuple)) or len(location) != 3:
                    return False, "INVALID_PARAMS", "Parameter 'location' must be a 3-element list [x, y, z]."

            rotation = params.get("rotation_euler")
            if rotation is not None:
                if not isinstance(rotation, (list, tuple)) or len(rotation) != 3:
                    return False, "INVALID_PARAMS", "Parameter 'rotation_euler' must be a 3-element list [rx, ry, rz]."

            spot_size = params.get("spot_size")
            if spot_size is not None:
                if not isinstance(spot_size, (int, float)) or isinstance(spot_size, bool):
                    return False, "INVALID_PARAMS", "Parameter 'spot_size' must be a number."
                if spot_size < 0.0 or spot_size > 3.1416:
                    return False, "INVALID_PARAMS", f"Parameter 'spot_size' must be between 0.0 and 3.1416, got {spot_size}."

            spot_blend = params.get("spot_blend")
            if spot_blend is not None:
                if not isinstance(spot_blend, (int, float)) or isinstance(spot_blend, bool):
                    return False, "INVALID_PARAMS", "Parameter 'spot_blend' must be a number."
                if spot_blend < 0.0 or spot_blend > 1.0:
                    return False, "INVALID_PARAMS", f"Parameter 'spot_blend' must be between 0.0 and 1.0, got {spot_blend}."

            size = params.get("size")
            if size is not None:
                if not isinstance(size, (int, float)) or isinstance(size, bool):
                    return False, "INVALID_PARAMS", "Parameter 'size' must be a number."
                if float(size) < 0.0:
                    return False, "INVALID_PARAMS", f"Parameter 'size' must be non-negative, got {size}."

            shape = params.get("shape")
            if shape is not None:
                shp = str(shape).strip().upper()
                if shp not in ("SQUARE", "RECTANGLE", "DISK", "ELLIPSE"):
                    return False, "INVALID_PARAMS", f"Invalid shape '{shape}'. Allowed AREA light shapes: ['SQUARE', 'RECTANGLE', 'DISK', 'ELLIPSE']."

            size_y = params.get("size_y")
            if size_y is not None:
                if not isinstance(size_y, (int, float)) or isinstance(size_y, bool):
                    return False, "INVALID_PARAMS", "Parameter 'size_y' must be a number."
                if float(size_y) < 0.0:
                    return False, "INVALID_PARAMS", f"Parameter 'size_y' must be non-negative, got {size_y}."

            for factor_name in ("diffuse_factor", "specular_factor", "volume_factor"):
                factor_val = params.get(factor_name)
                if factor_val is not None:
                    if not isinstance(factor_val, (int, float)) or isinstance(factor_val, bool):
                        return False, "INVALID_PARAMS", f"Parameter '{factor_name}' must be a number."
                    if float(factor_val) < 0.0:
                        return False, "INVALID_PARAMS", f"Parameter '{factor_name}' must be non-negative, got {factor_val}."

            use_shadow = params.get("use_shadow")
            if use_shadow is not None and not isinstance(use_shadow, bool):
                return False, "INVALID_PARAMS", f"Parameter 'use_shadow' must be a boolean, got {use_shadow}."

            shadow_soft_size = params.get("shadow_soft_size")
            if shadow_soft_size is not None:
                if not isinstance(shadow_soft_size, (int, float)) or isinstance(shadow_soft_size, bool):
                    return False, "INVALID_PARAMS", "Parameter 'shadow_soft_size' must be a number."
                if float(shadow_soft_size) < 0.0:
                    return False, "INVALID_PARAMS", f"Parameter 'shadow_soft_size' must be non-negative, got {shadow_soft_size}."

            shadow_buffer_clip_start = params.get("shadow_buffer_clip_start")
            if shadow_buffer_clip_start is not None:
                if not isinstance(shadow_buffer_clip_start, (int, float)) or isinstance(shadow_buffer_clip_start, bool):
                    return False, "INVALID_PARAMS", "Parameter 'shadow_buffer_clip_start' must be a number."
                if float(shadow_buffer_clip_start) < 0.0001:
                    return False, "INVALID_PARAMS", f"Parameter 'shadow_buffer_clip_start' must be positive (>= 0.0001), got {shadow_buffer_clip_start}."

        # 2. Validation for configure_world
        elif tool_name == TOOL_CONFIGURE_WORLD:
            color = params.get("color")
            if color is not None:
                if not isinstance(color, (list, tuple)) or len(color) != 3:
                    return False, "INVALID_PARAMS", "Parameter 'color' must be a 3-element list [r, g, b]."
                for idx, c in enumerate(color):
                    if not isinstance(c, (int, float)) or isinstance(c, bool):
                        return False, "INVALID_PARAMS", f"World color component {idx} must be a number."
                    if c < 0.0 or c > 1.0:
                        return False, "INVALID_PARAMS", f"World color component {idx} must be between 0.0 and 1.0, got {c}."

            strength = params.get("strength")
            if strength is not None:
                if not isinstance(strength, (int, float)) or isinstance(strength, bool):
                    return False, "INVALID_PARAMS", "Parameter 'strength' must be a number."
                if float(strength) < 0.0:
                    return False, "INVALID_PARAMS", f"Parameter 'strength' must be non-negative, got {strength}."

            env_img = params.get("environment_image")
            if env_img is not None:
                if not isinstance(env_img, str) or not env_img.strip():
                    return False, "INVALID_PARAMS", "Parameter 'environment_image' must be a non-empty string."

            sky_type = params.get("sky_type")
            if env_img is not None and sky_type is not None:
                return False, "INVALID_PARAMS", "Cannot specify both 'environment_image' and 'sky_type' simultaneously."

            if sky_type is not None:
                st = str(sky_type).strip().upper()
                if st not in {"MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "PREETHAM", "HOSEK_WILKIE", "NISHITA"}:
                    return False, "INVALID_PARAMS", f"Invalid sky_type '{st}'. Allowed values: ['MULTIPLE_SCATTERING', 'SINGLE_SCATTERING', 'PREETHAM', 'HOSEK_WILKIE', 'NISHITA']."

            sun_disc = params.get("sun_disc")
            if sun_disc is not None and not isinstance(sun_disc, bool):
                return False, "INVALID_PARAMS", f"Parameter 'sun_disc' must be a boolean, got {sun_disc}."

            sun_size = params.get("sun_size")
            if sun_size is not None:
                if not isinstance(sun_size, (int, float)) or isinstance(sun_size, bool) or float(sun_size) < 0.0 or float(sun_size) > 1.5707964:
                    return False, "INVALID_PARAMS", f"Parameter 'sun_size' must be between 0.0 and 1.5708 radians, got {sun_size}."

            sun_intensity = params.get("sun_intensity")
            if sun_intensity is not None:
                if not isinstance(sun_intensity, (int, float)) or isinstance(sun_intensity, bool) or float(sun_intensity) < 0.0:
                    return False, "INVALID_PARAMS", f"Parameter 'sun_intensity' must be non-negative, got {sun_intensity}."

            sun_elevation = params.get("sun_elevation")
            if sun_elevation is not None:
                if not isinstance(sun_elevation, (int, float)) or isinstance(sun_elevation, bool) or float(sun_elevation) < -1.5707964 or float(sun_elevation) > 1.5707964:
                    return False, "INVALID_PARAMS", f"Parameter 'sun_elevation' must be between -1.5708 and 1.5708 radians, got {sun_elevation}."

            sun_rotation = params.get("sun_rotation")
            if sun_rotation is not None:
                if not isinstance(sun_rotation, (int, float)) or isinstance(sun_rotation, bool) or float(sun_rotation) < -6.2831854 or float(sun_rotation) > 6.2831854:
                    return False, "INVALID_PARAMS", f"Parameter 'sun_rotation' must be between -6.2832 and 6.2832 radians, got {sun_rotation}."

            altitude = params.get("altitude")
            if altitude is not None:
                if not isinstance(altitude, (int, float)) or isinstance(altitude, bool) or float(altitude) < 0.0 or float(altitude) > 100000.0:
                    return False, "INVALID_PARAMS", f"Parameter 'altitude' must be between 0.0 and 100000.0 meters, got {altitude}."

            for d_prop in ("air_density", "aerosol_density", "ozone_density"):
                dv = params.get(d_prop)
                if dv is not None:
                    if not isinstance(dv, (int, float)) or isinstance(dv, bool) or float(dv) < 0.0 or float(dv) > 1000.0:
                        return False, "INVALID_PARAMS", f"Parameter '{d_prop}' must be between 0.0 and 1000.0, got {dv}."

            turbidity = params.get("turbidity")
            if turbidity is not None:
                if not isinstance(turbidity, (int, float)) or isinstance(turbidity, bool) or float(turbidity) < 1.0 or float(turbidity) > 10.0:
                    return False, "INVALID_PARAMS", f"Parameter 'turbidity' must be between 1.0 and 10.0, got {turbidity}."

            ground_albedo = params.get("ground_albedo")
            if ground_albedo is not None:
                if not isinstance(ground_albedo, (int, float)) or isinstance(ground_albedo, bool) or float(ground_albedo) < 0.0 or float(ground_albedo) > 1.0:
                    return False, "INVALID_PARAMS", f"Parameter 'ground_albedo' must be between 0.0 and 1.0, got {ground_albedo}."

            env_rot = params.get("environment_rotation")
            if env_rot is not None:
                if isinstance(env_rot, (int, float)) and not isinstance(env_rot, bool):
                    pass
                elif isinstance(env_rot, (list, tuple)) and len(env_rot) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in env_rot):
                    pass
                else:
                    return False, "INVALID_PARAMS", "Parameter 'environment_rotation' must be a number (Z-axis radians) or a 3-element list [rx, ry, rz] in radians."

        # 3. Validation for create_camera, configure_camera, edit_camera
        elif tool_name in (TOOL_CREATE_CAMERA, TOOL_CONFIGURE_CAMERA, TOOL_EDIT_CAMERA):
            name = str(params.get("name") or params.get("target_name") or params.get("camera_name") or "").strip()
            if not name:
                return False, "INVALID_PARAMS", f"Camera 'name' is required and cannot be empty for {tool_name}."

            focal_length = params.get("focal_length")
            if focal_length is not None:
                if not isinstance(focal_length, (int, float)) or isinstance(focal_length, bool) or focal_length <= 0:
                    return False, "INVALID_PARAMS", "Parameter 'focal_length' must be a positive number."

            clip_start = params.get("clip_start")
            if clip_start is not None:
                if not isinstance(clip_start, (int, float)) or isinstance(clip_start, bool) or clip_start <= 0:
                    return False, "INVALID_PARAMS", "Parameter 'clip_start' must be a positive number."

            clip_end = params.get("clip_end")
            if clip_end is not None:
                if not isinstance(clip_end, (int, float)) or isinstance(clip_end, bool) or clip_end <= 0:
                    return False, "INVALID_PARAMS", "Parameter 'clip_end' must be a positive number."

            if clip_start is not None and clip_end is not None and clip_start >= clip_end:
                return False, "INVALID_PARAMS", "Parameter 'clip_start' must be strictly less than 'clip_end'."

            for tf in ("location", "rotation_euler"):
                val = params.get(tf)
                if val is not None:
                    if not isinstance(val, (list, tuple)) or len(val) != 3:
                        return False, "INVALID_PARAMS", f"Parameter '{tf}' must be a 3-element list [x, y, z]."

            track_to = params.get("track_to_object")
            if track_to is not None:
                if not isinstance(track_to, str):
                    return False, "INVALID_PARAMS", "Parameter 'track_to_object' must be a string."
                if track_to.strip() and track_to.strip() == name:
                    return False, "INVALID_PARAMS", "Camera cannot track itself."

            focus_obj = params.get("focus_object")
            if focus_obj is not None:
                if not isinstance(focus_obj, str):
                    return False, "INVALID_PARAMS", "Parameter 'focus_object' must be a string."
                if focus_obj.strip() and focus_obj.strip() == name:
                    return False, "INVALID_PARAMS", "Camera cannot focus on itself."

            dof = params.get("dof")
            if isinstance(dof, dict):
                dof_fobj = dof.get("focus_object")
                if dof_fobj is not None:
                    if not isinstance(dof_fobj, str):
                        return False, "INVALID_PARAMS", "DOF parameter 'focus_object' must be a string."
                    if dof_fobj.strip() and dof_fobj.strip() == name:
                        return False, "INVALID_PARAMS", "Camera cannot focus on itself."

            thirds = params.get("show_composition_thirds")
            if thirds is not None and not isinstance(thirds, bool):
                return False, "INVALID_PARAMS", "Parameter 'show_composition_thirds' must be a boolean."

        # 4. Validation for configure_render_settings
        elif tool_name == TOOL_CONFIGURE_RENDER_SETTINGS:
            engine = params.get("engine")
            if engine is not None and not isinstance(engine, str):
                return False, "INVALID_PARAMS", "Parameter 'engine' must be a string."

            for dim in ("resolution_x", "resolution_y"):
                val = params.get(dim)
                if val is not None:
                    if not isinstance(val, int) or isinstance(val, bool) or val < 1:
                        return False, "INVALID_PARAMS", f"Parameter '{dim}' must be a positive integer."

            pct = params.get("resolution_percentage")
            if pct is not None:
                if not isinstance(pct, int) or isinstance(pct, bool) or pct < 1 or pct > 1000:
                    return False, "INVALID_PARAMS", "Parameter 'resolution_percentage' must be between 1 and 1000."

            fps = params.get("fps")
            if fps is not None:
                if not isinstance(fps, int) or isinstance(fps, bool) or fps < 1:
                    return False, "INVALID_PARAMS", "Parameter 'fps' must be a positive integer."

            ft = params.get("film_transparent")
            if ft is not None and not isinstance(ft, bool):
                return False, "INVALID_PARAMS", "Parameter 'film_transparent' must be a boolean."

            cm = params.get("color_management")
            if cm is not None and not isinstance(cm, dict):
                return False, "INVALID_PARAMS", "Parameter 'color_management' must be a dict/object."

            vt = params.get("view_transform") or (cm.get("view_transform") if isinstance(cm, dict) else None)
            if vt is not None:
                if not isinstance(vt, str):
                    return False, "INVALID_PARAMS", "Parameter 'view_transform' must be a string."
                allowed_vt = ("Standard", "ACES 1.3", "ACES 2.0", "Khronos PBR Neutral", "AgX", "Filmic", "Filmic Log", "False Color", "Raw")
                vt_map = {item.lower(): item for item in allowed_vt}
                if vt.lower() not in vt_map:
                    return False, "INVALID_PARAMS", f"Invalid view_transform '{vt}'. Allowed: {list(allowed_vt)}."

            look = params.get("look") or (cm.get("look") if isinstance(cm, dict) else None)
            if look is not None:
                if not isinstance(look, str):
                    return False, "INVALID_PARAMS", "Parameter 'look' must be a string."
                allowed_look = (
                    "None", "Very Low Contrast", "Low Contrast", "Medium Low Contrast", "Medium Contrast", "Medium High Contrast", "High Contrast", "Very High Contrast",
                    "AgX - Very Low Contrast", "AgX - Low Contrast", "AgX - Medium Low Contrast", "AgX - Base Contrast", "AgX - Medium High Contrast", "AgX - High Contrast", "AgX - Very High Contrast", "AgX - Punchy", "AgX - Greyscale", "Punchy"
                )
                look_map = {item.lower(): item for item in allowed_look}
                if look.lower() not in look_map:
                    return False, "INVALID_PARAMS", f"Invalid look '{look}'. Allowed: {list(allowed_look)}."

            exp = params.get("exposure") if "exposure" in params else (cm.get("exposure") if isinstance(cm, dict) else None)
            if exp is not None:
                if not isinstance(exp, (int, float)) or isinstance(exp, bool) or not math.isfinite(exp) or exp < -32.0 or exp > 32.0:
                    return False, "INVALID_PARAMS", f"Parameter 'exposure' must be a finite number in [-32.0, 32.0], got {exp}."

            cyc = params.get("cycles")
            if cyc is not None and not isinstance(cyc, dict):
                return False, "INVALID_PARAMS", "Parameter 'cycles' must be a dict/object."

            ud = params.get("use_denoising") if "use_denoising" in params else (cyc.get("use_denoising") if isinstance(cyc, dict) else None)
            if ud is not None and not isinstance(ud, bool):
                return False, "INVALID_PARAMS", "Parameter 'use_denoising' must be a boolean."

            dn = params.get("denoiser") or (cyc.get("denoiser") if isinstance(cyc, dict) else None)
            if dn is not None:
                if not isinstance(dn, str):
                    return False, "INVALID_PARAMS", "Parameter 'denoiser' must be a string."
                allowed_dn = ("OPENIMAGEDENOISE", "OPTIX")
                dn_map = {item.lower(): item for item in allowed_dn}
                if dn.lower() not in dn_map:
                    return False, "INVALID_PARAMS", f"Invalid denoiser '{dn}'. Allowed: ['OPENIMAGEDENOISE', 'OPTIX']."

            for b_name in ("max_bounces", "diffuse_bounces", "glossy_bounces", "transmission_bounces", "volume_bounces", "transparent_max_bounces"):
                b_val = params.get(b_name) if b_name in params else (cyc.get(b_name) if isinstance(cyc, dict) else None)
                if b_val is not None:
                    if not isinstance(b_val, int) or isinstance(b_val, bool) or b_val < 0 or b_val > 1024:
                        return False, "INVALID_PARAMS", f"Parameter '{b_name}' must be an integer between 0 and 1024, got {b_val}."

        # 5. Validation for render_scene
        elif tool_name == TOOL_RENDER_SCENE:
            render_mode = params.get("render_mode", "still")
            if render_mode not in ("still", "animation"):
                return False, "INVALID_PARAMS", f"Parameter 'render_mode' must be 'still' or 'animation', got '{render_mode}'."

            if render_mode == "animation":
                f_start = params.get("frame_start")
                f_end = params.get("frame_end")
                if f_start is not None:
                    if not isinstance(f_start, int) or isinstance(f_start, bool):
                        return False, "INVALID_PARAMS", "Parameter 'frame_start' must be an integer."
                if f_end is not None:
                    if not isinstance(f_end, int) or isinstance(f_end, bool):
                        return False, "INVALID_PARAMS", "Parameter 'frame_end' must be an integer."
                if f_start is not None and f_end is not None and f_start > f_end:
                    return False, "INVALID_PARAMS", f"frame_start ({f_start}) cannot exceed frame_end ({f_end}) for animation render."

            frame = params.get("frame")
            if frame is not None:
                if not isinstance(frame, int) or isinstance(frame, bool):
                    return False, "INVALID_PARAMS", "Parameter 'frame' must be an integer."

        # 6. Validation for manage_compositor_nodes and aliases
        elif tool_name in (TOOL_MANAGE_COMPOSITOR_NODES, TOOL_CONFIGURE_COMPOSITOR, TOOL_MANAGE_COMPOSITOR):
            act = str(params.get("action", "inspect")).strip().lower()
            if act not in ("enable", "inspect", "create_node", "remove_node", "connect", "disconnect", "set_property", "configure_render_passes", "list_nodes"):
                return False, "INVALID_PARAMS", f"Unsupported action '{act}' for compositor node management."

        return True, None, None

    def execute_task(
        self,
        task: AgentTask,
        executor: BlenderExecutor,
        trusted_approval: Optional[bool] = None,
    ) -> AgentResult:
        """
        Executes a validated lighting or world task via BlenderExecutor with approval enforcement
        and read-only post-operation verification.
        """
        t0 = time.time()
        tool_name = task.task_type or task.required_capability or TOOL_CREATE_LIGHT
        raw_params = dict(task.input_params)

        # 1. Pre-execution input validation
        is_valid, err_code, err_msg = self.validate_task_input(tool_name, raw_params)
        if not is_valid:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[err_msg or "Validation error"],
                execution_time_ms=duration_ms,
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name},
                    observed_results={"error_code": err_code, "error": err_msg, "transaction_status": "NOT_APPLICABLE"},
                    status="FAIL",
                    details=err_msg or "Validation error",
                ),
            )

        # 2. Strict Human Approval Enforcement for mutations
        is_mutation = tool_name in (
            TOOL_CREATE_LIGHT,
            TOOL_CONFIGURE_LIGHT,
            TOOL_CONFIGURE_WORLD,
            TOOL_CREATE_CAMERA,
            TOOL_CONFIGURE_CAMERA,
            TOOL_EDIT_CAMERA,
            TOOL_SWITCH_CAMERA,
            TOOL_CONFIGURE_RENDER_SETTINGS,
            TOOL_RENDER_SCENE,
            TOOL_MANAGE_COMPOSITOR_NODES,
            TOOL_CONFIGURE_COMPOSITOR,
            TOOL_MANAGE_COMPOSITOR,
        ) and raw_params.get("action") not in ("inspect", "list_nodes")
        approval_decision = None
        if is_mutation:
            # Model-supplied approved=True is strictly rejected as untrusted
            if raw_params.get("approved") is True:
                duration_ms = round((time.time() - t0) * 1000, 2)
                return AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[
                        f"Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize "
                        f"mutation '{tool_name}'. Explicit user approval must be granted through a trusted approval mechanism."
                    ],
                    execution_time_ms=duration_ms,
                    verification=VerificationResult(
                        expected_conditions={"tool": tool_name},
                        observed_results={"error_code": "PERMISSION_DENIED", "transaction_status": "NOT_APPLICABLE"},
                        status="FAIL",
                        details="Untrusted model approved=True rejected",
                    ),
                )

            # Use the configured Blender approval provider for the human decision.
            # Resumed tasks bypass this prompt only after the dispatcher reads the
            # approved single-use token from Blender's registry; the bridge validates it again.
            if trusted_approval is not True:
                approval_manager = getattr(executor, "approval_manager", None) if trusted_approval is None else None
                if approval_manager and approval_manager.has_provider:
                    # Bind the Blender request to the same normalized parameters that
                    # BlenderExecutor will later send to the bridge (including schema defaults).
                    approval_params = validate_tool_input(tool_name, raw_params, trusted_approval=True)
                    approval_params.pop("trusted_approval", None)
                    approval_params.pop("approved", None)
                    approval_decision = approval_manager.verify_approval(tool_name, approval_params)
                    if not approval_decision.approved:
                        duration_ms = round((time.time() - t0) * 1000, 2)
                        reason = approval_decision.reason or "Approval was not granted."
                        pending = approval_decision.status == "pending" and bool(approval_decision.request_id)
                        expired = approval_decision.status == "expired" or (
                            approval_decision.status is None and "expired" in reason.lower()
                        )
                        denied = approval_decision.status in ("denied", "cancelled") or (
                            approval_decision.status is None and any(
                                word in reason.lower() for word in ("denied", "cancelled", "expired", "timed out")
                            )
                        )
                        observed = {
                            "error_code": "APPROVAL_REQUIRED" if pending else (
                                "APPROVAL_EXPIRED" if expired else "PERMISSION_DENIED" if denied else "APPROVAL_REQUIRED"
                            ),
                            "transaction_status": "NOT_APPLICABLE",
                        }
                        if pending:
                            observed.update({
                                "approval_pending": True,
                                "approval_request_id": approval_decision.request_id,
                                "approval_expires_at": approval_decision.expires_at,
                            })
                        return AgentResult(
                            task_id=task.task_id,
                            status=TaskStatus.AWAITING_APPROVAL if pending or not (denied or expired) else TaskStatus.FAILED,
                            errors=[reason],
                            execution_time_ms=duration_ms,
                            verification=VerificationResult(
                                expected_conditions={"tool": tool_name},
                                observed_results=observed,
                                status="FAIL",
                                details=reason,
                            ),
                        )
                    if not approval_decision.request_id or not approval_decision.approval_token:
                        return AgentResult(
                            task_id=task.task_id, status=TaskStatus.FAILED,
                            errors=["Approval provider returned no bound Blender credentials"],
                            verification=VerificationResult(expected_conditions={"tool": tool_name},
                                observed_results={"error_code": "APPROVAL_CREDENTIALS_MISSING", "transaction_status": "NOT_APPLICABLE"},
                                status="FAIL", details="No executable approval token was provided"),
                        )
                    trusted_approval = True
                else:
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    return AgentResult(
                        task_id=task.task_id,
                        status=TaskStatus.AWAITING_APPROVAL,
                        errors=[
                            f"Approval required: Mutation '{tool_name}' requires explicit user approval through "
                            "a trusted approval mechanism."
                        ],
                        execution_time_ms=duration_ms,
                        verification=VerificationResult(
                            expected_conditions={"tool": tool_name},
                            observed_results={"error_code": "APPROVAL_REQUIRED", "transaction_status": "NOT_APPLICABLE"},
                            status="FAIL",
                            details="Explicit user approval required for scene mutation",
                        ),
                    )

        # 3. Execution via BlenderExecutor
        clean_params = dict(raw_params)
        clean_params.pop("approved", None)
        if approval_decision:
            if approval_decision.request_id:
                clean_params["request_id"] = approval_decision.request_id
            if approval_decision.approval_token:
                clean_params["approval_token"] = approval_decision.approval_token

        try:
            if is_mutation and trusted_approval is True:
                try:
                    resp = executor.execute_tool(tool_name, clean_params, trusted_approval=True)
                except TypeError:
                    resp = executor.execute_tool(tool_name, clean_params)
            else:
                resp = executor.execute_tool(tool_name, clean_params)
        except Exception as exc:
            logger.exception(f"Unexpected executor exception during lighting execution of '{tool_name}': {exc}")
            resp = BridgeResponse.error(f"Executor exception: {exc}")

        exec_duration_ms = round((time.time() - t0) * 1000, 2)

        # 4. Handle Execution Failure
        if not resp.is_success or (isinstance(resp.result, dict) and resp.result.get("success") is False):
            err_msg = resp.message or "Execution failed"
            err_code = "EXECUTION_FAILED"
            err_msg_lower = err_msg.lower()
            if "not found" in err_msg_lower:
                err_code = "DATA_UNAVAILABLE"
            elif "exists" in err_msg_lower:
                err_code = "NAME_COLLISION"
            elif "unsupported" in err_msg_lower:
                err_code = "UNSUPPORTED_REQUEST"

            observed = {"error_code": err_code, "error": err_msg, "transaction_status": "ROLLBACK_UNVERIFIED"}
            if tool_name == TOOL_RENDER_SCENE and isinstance(resp.result, dict):
                raw_job = resp.result.get("render_job")
                if isinstance(raw_job, dict):
                    job = render_job_failure_snapshot(raw_job.get("error_code"), raw_job.get("execution_state_at_response"))
                    if job is not None:
                        observed.update(error_code=job["error_code"], render_job=job)

            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[err_msg],
                execution_time_ms=exec_duration_ms,
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name},
                    observed_results=observed,
                    status="FAIL",
                    details=err_msg,
                ),
            )

        # 5. Post-Operation Read-Only Inspection Verification
        v_start = time.time()
        verification_passed = True
        verification_details: Dict[str, Any] = {}

        if tool_name == TOOL_CONFIGURE_LIGHT:
            light_name = str(raw_params.get("name", "")).strip()
            try:
                insp_resp = executor.execute_tool(TOOL_GET_OBJECT_DETAILS, {"name": light_name})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    verification_details["verified_light"] = insp_resp.result
                    verification_details["light_configured"] = True
                else:
                    verification_passed = False
                    verification_details["error"] = f"Configured light '{light_name}' could not be inspected."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"


        elif tool_name == TOOL_CREATE_LIGHT:
            light_name = str(raw_params.get("name", "")).strip()
            try:
                insp_resp = executor.execute_tool(TOOL_LIST_OBJECTS, {"object_type": "LIGHT"})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    found_objs = insp_resp.result.get("objects", [])
                    matched = [o for o in found_objs if o.get("name") == light_name]
                    if matched:
                        verification_details["verified_light"] = matched[0]
                        verification_details["light_exists"] = True
                    else:
                        verification_passed = False
                        verification_details["error"] = f"Created light '{light_name}' not found in active scene."
                else:
                    verification_passed = False
                    verification_details["error"] = "Verification inspection failed to retrieve scene lights."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"


        elif tool_name == TOOL_CREATE_CAMERA:
            cam_name = str(raw_params.get("name", "")).strip()
            try:
                insp_resp = executor.execute_tool(TOOL_LIST_OBJECTS, {"object_type": "CAMERA"})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    found_objs = insp_resp.result.get("objects", [])
                    matched = [o for o in found_objs if o.get("name") == cam_name]
                    if matched:
                        verification_details["verified_camera"] = matched[0]
                        verification_details["camera_exists"] = True
                    else:
                        verification_passed = False
                        verification_details["error"] = f"Created camera '{cam_name}' not found in active scene."
                else:
                    verification_passed = False
                    verification_details["error"] = "Verification inspection failed to retrieve scene cameras."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"


        elif tool_name in (TOOL_CONFIGURE_CAMERA, TOOL_EDIT_CAMERA):
            cam_name = str(raw_params.get("name") or raw_params.get("target_name") or raw_params.get("camera_name") or "").strip()
            try:
                insp_resp = executor.execute_tool(TOOL_GET_OBJECT_DETAILS, {"name": cam_name, "include_mesh_stats": False})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    cam_details = insp_resp.result.get("camera_details")
                    if cam_details and cam_details.get("name") == cam_name:
                        verification_details["verified_camera"] = cam_details
                        verification_details["camera_configured"] = True
                    else:
                        verification_passed = False
                        verification_details["error"] = f"Camera details verification failed for '{cam_name}'."
                else:
                    verification_passed = False
                    verification_details["error"] = f"Failed to inspect configured camera '{cam_name}'."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"

        elif tool_name == TOOL_SWITCH_CAMERA:
            cam_name = str(raw_params.get("camera_name") or raw_params.get("name") or raw_params.get("target_name") or "").strip()
            try:
                insp_resp = executor.execute_tool(TOOL_INSPECT_SCENE_DATA, {"category": "cameras"})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    act_cam = insp_resp.result.get("active_camera")
                    if act_cam == cam_name:
                        verification_details["verified_active_camera"] = act_cam
                        verification_details["camera_switched"] = True
                    else:
                        verification_passed = False
                        verification_details["error"] = f"Active camera mismatch: expected '{cam_name}', got '{act_cam}'."
                else:
                    verification_passed = False
                    verification_details["error"] = f"Failed to inspect camera state after switching to '{cam_name}'."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"

        elif tool_name == TOOL_CONFIGURE_WORLD:
            try:
                insp_resp = executor.execute_tool(TOOL_INSPECT_SCENE_DATA, {"category": "world_settings"})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    verification_details["verified_world"] = insp_resp.result
                    verification_details["world_configured"] = True
                else:
                    verification_passed = False
                    verification_details["error"] = "Failed to inspect world settings after configuration."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"


        elif tool_name == TOOL_CONFIGURE_RENDER_SETTINGS:
            try:
                insp_resp = executor.execute_tool(TOOL_INSPECT_SCENE_DATA, {"category": "render_settings"})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    verification_details["verified_render_settings"] = insp_resp.result
                    verification_details["render_configured"] = True
                else:
                    verification_passed = False
                    verification_details["error"] = "Failed to inspect render settings after configuration."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"


        elif tool_name == TOOL_RENDER_SCENE:
            if isinstance(resp.result, dict) and resp.result.get("rendered") is True:
                verification_details["verified_render"] = resp.result
                verification_details["render_verified"] = True
                if raw_params.get("render_mode", "still") == "still":
                    try:
                        receipt_id = resp.result.get("render_id")
                        validate_tool_input(TOOL_INSPECT_RENDER_OUTPUT, {"render_id": receipt_id})
                        inspected = executor.execute_tool(TOOL_INSPECT_RENDER_OUTPUT, {"render_id": receipt_id})
                        actual = inspected.result or {}
                        verification_passed = (resp.result.get("operator_completed") is True and inspected.is_success
                            and actual.get("success") is True and actual.get("verified") is True
                            and actual.get("render_id") == receipt_id and actual.get("artifact", {}).get("path") == resp.result.get("output_file")
                            and actual.get("width") == resp.result.get("width") and actual.get("height") == resp.result.get("height")
                            and actual.get("frame") == resp.result.get("frame") and actual.get("camera") == resp.result.get("camera"))
                        artifact = actual.get("artifact", {})
                        verification_passed = (verification_passed and type(actual.get("width")) is int and actual["width"] > 0
                            and type(actual.get("height")) is int and actual["height"] > 0
                            and type(actual.get("frame")) is int and isinstance(actual.get("camera"), str) and bool(actual["camera"])
                            and isinstance(artifact.get("sha256"), str) and len(artifact["sha256"]) == 64
                            and isinstance(artifact.get("size_bytes"), int) and artifact["size_bytes"] > 0)
                        if actual.get("file_format") == "PNG":
                            verification_passed = (verification_passed and artifact.get("png_structure_verified") is True
                                and artifact.get("width") == actual.get("width") and artifact.get("height") == actual.get("height"))
                        verification_details["render_receipt"] = actual
                    except Exception:
                        verification_passed = False
                    verification_details["render_verified"] = verification_passed
                    if not verification_passed:
                        verification_details["error"] = "Still render lacks a matching verified fresh output receipt"
                elif raw_params.get("render_mode", "still") == "animation":
                    try:
                        expected_count = resp.result.get("total_frames")
                        f_start = resp.result.get("frame_start")
                        f_end = resp.result.get("frame_end")
                        expected_range_count = (f_end - f_start + 1) if (f_start is not None and f_end is not None) else expected_count
                        frame_receipts = resp.result.get("frame_receipts", [])
                        render_ids = resp.result.get("render_ids", [])
                        output_paths = resp.result.get("output_paths", [])
                        verification_passed = (
                            resp.result.get("operator_completed") is True
                            and bool(expected_count and expected_count > 0)
                            and expected_count == expected_range_count
                            and len(output_paths) == expected_count
                            and len(frame_receipts) == expected_count
                            and len(render_ids) == expected_count
                        )
                        if verification_passed and render_ids:
                            sample_receipt_id = render_ids[-1]
                            validate_tool_input(TOOL_INSPECT_RENDER_OUTPUT, {"render_id": sample_receipt_id})
                            inspected = executor.execute_tool(TOOL_INSPECT_RENDER_OUTPUT, {"render_id": sample_receipt_id})
                            actual = inspected.result or {}
                            verification_passed = (
                                inspected.is_success
                                and actual.get("success") is True
                                and actual.get("verified") is True
                                and actual.get("render_id") == sample_receipt_id
                                and actual.get("artifact", {}).get("path") in output_paths
                            )
                            artifact = actual.get("artifact", {})
                            verification_passed = (
                                verification_passed
                                and isinstance(artifact.get("sha256"), str)
                                and len(artifact["sha256"]) == 64
                                and isinstance(artifact.get("size_bytes"), int)
                                and artifact["size_bytes"] > 0
                            )
                            if actual.get("file_format") == "PNG":
                                verification_passed = (
                                    verification_passed
                                    and artifact.get("png_structure_verified") is True
                                )
                            verification_details["sample_receipt"] = actual
                    except Exception:
                        verification_passed = False
                    verification_details["render_verified"] = verification_passed
                    if not verification_passed:
                        verification_details["error"] = "Animation render lacks matching verified fresh output receipts"
            else:
                verification_passed = False
                verification_details["error"] = "Render scene operation did not report verified completion."

        elif tool_name == TOOL_INSPECT_RENDER_OUTPUT:
            verification_passed = isinstance(resp.result, dict) and resp.result.get("verified") is True and resp.result.get("render_id") == raw_params.get("render_id")
            if not verification_passed:
                verification_details["error"] = "Render receipt did not verify actual output state"
        elif tool_name in (TOOL_LIST_OBJECTS, TOOL_INSPECT_SCENE_DATA, TOOL_GET_OBJECT_DETAILS):
            verification_details["read_only_output"] = True

        v_duration_ms = round((time.time() - v_start) * 1000, 2)
        total_duration_ms = round((time.time() - t0) * 1000, 2)

        if not verification_passed:
            verification_details["transaction_status"] = "ROLLBACK_UNVERIFIED"
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                output=resp.result,
                errors=[verification_details.get("error", "Post-operation lighting verification failed")],
                execution_time_ms=total_duration_ms,
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name},
                    observed_results=verification_details,
                    status="FAIL",
                    details=verification_details.get("error", "Post-operation lighting verification failed"),
                ),
            )

        verification_details["transaction_status"] = "COMMITTED" if is_mutation else "NOT_APPLICABLE"
        return AgentResult(
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            output=resp.result,
            execution_time_ms=total_duration_ms,
            verification=VerificationResult(
                expected_conditions={"tool": tool_name},
                observed_results=verification_details,
                status="PASS",
                details=f"Lighting operation '{tool_name}' verified successfully.",
            ),
        )
