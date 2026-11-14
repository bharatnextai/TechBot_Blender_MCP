"""
Director Agent for Universal MCP.
Provides high-level studio production brief analysis, departmental task delegation,
and human-gated plan orchestration across specialized domain agents.

Enforces:
1. Typed DelegationContract data structures.
2. Complete mutation plan approval gating before delegated execution.
3. Strict fail-closed rejection of untrusted client approvals.
4. Topologically ordered execution across specialized domain agents.
"""

from typing import Dict, Any, List, Optional, Set, Tuple, Callable
import time
import logging
import uuid
import os
import re

from blender_addon.universal_mcp.bridge.asset_interchange import (
    detect_format_from_path,
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_IMPORT_FORMATS,
)

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    AgentResult,
    VerificationResult,
    TaskStatus,
    TaskPlan,
    DelegationContract,
    TaskOutputRef,
)
from shared.models.protocol_models import BridgeResponse
from .scene_inspector import SCENE_INSPECTOR_AGENT_ID
from .modeling import MODELING_AGENT_ID
from .materials import MATERIALS_AGENT_ID
from .render_lighting import RENDER_LIGHTING_AGENT_ID
from .rigging_animation import RIGGING_ANIMATION_AGENT_ID
from .simulation_vfx import SIMULATION_VFX_AGENT_ID
from .interchange_delivery import INTERCHANGE_DELIVERY_AGENT_ID
from .compositor import COMPOSITOR_AGENT_ID
from .environment import ENVIRONMENT_AGENT_ID
from .video_editor import VIDEO_EDITOR_AGENT_ID

logger = logging.getLogger("UniversalMCP_DirectorAgent")

DIRECTOR_AGENT_ID = "agent.director"
CAPABILITY_DIRECTOR_ORCHESTRATION = "director.orchestration"


def create_director_manifest(version: str = "0.1.80") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Director Agent.
    Priority 10 gives it top precedence for high-level brief orchestration.
    """
    capabilities = [
        CapabilityDescriptor(
            capability_id=CAPABILITY_DIRECTOR_ORCHESTRATION,
            description="Decomposes natural language production briefs into typed delegation contracts across specialized agents.",
            supported_task_types=["orchestrate_production_brief", "compile_delegation_contract"],
            read_write="READ_ONLY",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
    ]

    return AgentManifest(
        agent_id=DIRECTOR_AGENT_ID,
        name="Director and Production Supervisor Agent",
        version=version,
        description="Top-level supervisor agent orchestrating multi-domain production pipelines via DelegationContracts.",
        capabilities=capabilities,
        priority=1,  # Top priority for orchestration
        enabled=True,
    )


def _extract_interchange_intents(brief: str) -> Dict[str, Any]:
    norm = str(brief).lower()
    ext_re = r"glb|gltf|fbx|usd|usdc|usda|obj|stl|ply|abc"

    quoted_assets = re.findall(rf"['\"]([^'\"\r\n]+\.(?:{ext_re}))['\"]", brief, re.IGNORECASE)
    cleaned = re.sub(r"['\"][^'\"\r\n]+['\"]", " ", brief)
    unquoted_assets = re.findall(rf"\b([a-zA-Z0-9_\-\./\\:]+\.(?:{ext_re}))\b", cleaned, re.IGNORECASE)
    assets: List[str] = quoted_assets + [p for p in unquoted_assets if p not in quoted_assets]

    quoted_blends = re.findall(r"['\"]([^'\"\r\n]+\.blend)['\"]", brief, re.IGNORECASE)
    unquoted_blends = re.findall(r"\b([a-zA-Z0-9_\-\./\\:]+\.blend)\b", cleaned, re.IGNORECASE)
    blends: List[str] = quoted_blends + [p for p in unquoted_blends if p not in quoted_blends]

    import_path = None
    import_format = None
    has_import = any(
        kw in norm
        for kw in ("import", "bring in", "load asset", "load model", "import asset", "import mesh", "import scene", "convert")
    ) and not any(kw in norm for kw in ("import rendered plate", "import plate"))

    if has_import:
        # Check for explicit unsupported import extension first
        m_unsupp = re.search(
            r"(?:import(?:ing)?|load\s+asset|load\s+model|bring\s+in|convert)\s+(?:scene\s+asset\s+|asset\s+|model\s+)?(?:['\"]([^'\"\r\n]+\.([a-zA-Z0-9_]+))['\"]|([a-zA-Z0-9_\-\./\\:]+\.([a-zA-Z0-9_]+)))",
            brief,
            re.IGNORECASE,
        )
        if m_unsupp:
            unsupp_ext = (m_unsupp.group(2) or m_unsupp.group(4)).lower()
            if unsupp_ext not in ext_re.split("|") and unsupp_ext != "blend":
                raise ValueError(
                    f"Unsupported import format '{unsupp_ext.upper()}'. Supported formats: {', '.join(SUPPORTED_IMPORT_FORMATS)}"
                )

        m_imp = re.search(
            rf"(?:import(?:ing)?|load\s+asset|load\s+model|bring\s+in|convert)\s+(?:scene\s+asset\s+|asset\s+|model\s+)?(?:['\"]([^'\"\r\n]+\.(?:{ext_re}))['\"]|([a-zA-Z0-9_\-\./\\:]+\.(?:{ext_re})))",
            brief,
            re.IGNORECASE,
        )
        if m_imp:
            import_path = (m_imp.group(1) or m_imp.group(2)).strip()
        elif assets:
            import_path = assets[0].strip()

        if import_path:
            if ".." in import_path.replace("\\", "/").split("/"):
                raise ValueError(
                    f"Path traversal detected in import path: '{import_path}'. Parent references '..' are forbidden."
                )
            import_format = detect_format_from_path(import_path)
            if not import_format:
                ext = os.path.splitext(import_path)[1].lower().lstrip(".")
                import_format = ext.upper()
        else:
            for fmt_kw, fmt_name in [
                ("obj", "OBJ"),
                ("stl", "STL"),
                ("ply", "PLY"),
                ("alembic", "ABC"),
                ("abc", "ABC"),
                ("gltf", "GLTF"),
                ("glb", "GLB"),
                ("usdc", "USDC"),
                ("usda", "USDA"),
                ("usd", "USD"),
                ("fbx", "FBX"),
            ]:
                if re.search(rf"\b{fmt_kw}\b", norm):
                    import_format = fmt_name
                    import_path = f"imported_asset.{fmt_kw}" if fmt_kw != "alembic" else "imported_asset.abc"
                    break

        if import_format and import_format not in SUPPORTED_IMPORT_FORMATS:
            raise ValueError(
                f"Unsupported import format '{import_format}'. Supported formats: {', '.join(SUPPORTED_IMPORT_FORMATS)}"
            )

    export_path = None
    export_format = None
    has_export = any(
        kw in norm
        for kw in (
            "export",
            "deliver",
            "package",
            "save as asset",
            "output asset",
            "save asset",
            "convert",
            "to glb",
            "to obj",
            "to stl",
            "to ply",
            "to abc",
            "as obj",
            "as stl",
            "as ply",
            "as abc",
        )
    )
    is_pure_video_export = (
        ("render" in norm or "encode" in norm)
        and any(v_ext in norm for v_ext in ("mp4", "mov", "mkv"))
        and not any(a_ext in norm for a_ext in ext_re.split("|"))
        and not any(a_kw in norm for a_kw in ("3d", "asset", "mesh", "model", "geometry", "scene asset"))
    )

    if has_export and not is_pure_video_export:
        # Check for explicit unsupported export keyword or extension
        m_unsupp_exp = re.search(
            r"(?:export(?:ing)?|deliver|output|save\s+as\s+asset|save\s+asset|to|as)\s+(?:scene\s+to\s+|asset\s+to\s+|as\s+|to\s+)?(?:['\"]([^'\"\r\n]+\.([a-zA-Z0-9_]+))['\"]|([a-zA-Z0-9_\-\./\\:]+\.([a-zA-Z0-9_]+)))",
            brief,
            re.IGNORECASE,
        )
        if m_unsupp_exp:
            unsupp_ext = (m_unsupp_exp.group(2) or m_unsupp_exp.group(4)).lower()
            if unsupp_ext not in ext_re.split("|") and unsupp_ext not in ("mp4", "mov", "mkv", "blend"):
                raise ValueError(
                    f"Unsupported export format '{unsupp_ext.upper()}'. Supported formats: {', '.join(SUPPORTED_EXPORT_FORMATS)}"
                )

        m_fmt_unsupp = re.search(r"\b(?:export|to|as)\s+(3ds|dae|dxf|c4d|max|ma|mb)\b", norm)
        if m_fmt_unsupp:
            raise ValueError(
                f"Unsupported export format '{m_fmt_unsupp.group(1).upper()}'. Supported formats: {', '.join(SUPPORTED_EXPORT_FORMATS)}"
            )

        m_exp = re.search(
            rf"(?:export(?:ing)?|deliver|output|save\s+as\s+asset|save\s+asset|to|as)\s+(?:scene\s+to\s+|asset\s+to\s+|as\s+|to\s+)?(?:['\"]([^'\"\r\n]+\.(?:{ext_re}))['\"]|([a-zA-Z0-9_\-\./\\:]+\.(?:{ext_re})))",
            brief,
            re.IGNORECASE,
        )
        found_exp = (m_exp.group(1) or m_exp.group(2)).strip() if m_exp else None
        if found_exp and found_exp != import_path:
            export_path = found_exp
        else:
            remaining = [p.strip() for p in assets if p.strip() != import_path]
            if remaining:
                export_path = remaining[-1]

        if export_path:
            if ".." in export_path.replace("\\", "/").split("/"):
                raise ValueError(
                    f"Path traversal detected in export path: '{export_path}'. Parent references '..' are forbidden."
                )
            export_format = detect_format_from_path(export_path)
            if not export_format:
                ext = os.path.splitext(export_path)[1].lower().lstrip(".")
                export_format = ext.upper()
        else:
            for fmt_kw, fmt_name, def_ext in [
                ("obj", "OBJ", ".obj"),
                ("stl", "STL", ".stl"),
                ("ply", "PLY", ".ply"),
                ("alembic", "ABC", ".abc"),
                ("abc", "ABC", ".abc"),
                ("gltf", "GLTF", ".gltf"),
                ("usdc", "USDC", ".usdc"),
                ("usda", "USDA", ".usda"),
                ("usd", "USD", ".usd"),
                ("fbx", "FBX", ".fbx"),
                ("glb", "GLB", ".glb"),
            ]:
                if re.search(rf"\b{fmt_kw}\b", norm):
                    export_format = fmt_name
                    export_path = f"hero_delivery{def_ext}"
                    break

            if not export_format and has_export:
                export_format = "GLB"
                export_path = "hero_delivery.glb"

        if export_format and export_format not in SUPPORTED_EXPORT_FORMATS:
            raise ValueError(
                f"Unsupported export format '{export_format}'. Supported formats: {', '.join(SUPPORTED_EXPORT_FORMATS)}"
            )

    save_path = None
    has_save_project = (
        any(
            kw in norm
            for kw in (
                "save project",
                "save blend",
                "save scene",
                "save the project",
                "save as project",
                "save file",
            )
        )
        or bool(blends)
    )
    if has_save_project:
        if blends:
            save_path = blends[-1].strip()
        else:
            save_path = "project.blend"
        if ".." in save_path.replace("\\", "/").split("/"):
            raise ValueError(
                f"Path traversal detected in save project path: '{save_path}'. Parent references '..' are forbidden."
            )

    return {
        "has_import": bool(has_import and import_path),
        "import_path": import_path,
        "import_format": import_format,
        "has_export": bool(has_export and export_path),
        "export_path": export_path,
        "export_format": export_format,
        "has_save_project": bool(has_save_project and save_path),
        "save_path": save_path,
    }


class DirectorAgent:
    """
    Executive director that translates production briefs into structured DelegationContracts
    and coordinates their execution across specialized domain agents.
    """

    def __init__(self, manifest: Optional[AgentManifest] = None):
        self._manifest = manifest or create_director_manifest()

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def decompose_brief(
        self,
        brief: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DelegationContract:
        """
        Decomposes a production brief into domain-specific tasks wrapped in a DelegationContract.
        Analyzes keywords and structural requirements to map tasks to appropriate domain agents.
        """
        if not brief or not str(brief).strip():
            raise ValueError("Production brief cannot be empty.")

        norm = str(brief).lower()
        io_intents = _extract_interchange_intents(brief)
        has_import = io_intents["has_import"]

        # Strip filepaths from action text to prevent filename tokens (e.g. 'cube', 'gold')
        # from triggering unintended domain stages in asset conversion pipelines
        norm_actions = norm
        for p in (io_intents["import_path"], io_intents["export_path"], io_intents["save_path"]):
            if p:
                norm_actions = norm_actions.replace(str(p).lower(), " ")

        contract_title = title or f"Production Plan: {brief[:50]}..."
        contract = DelegationContract(
            title=contract_title,
            brief=brief,
            director_agent_id=DIRECTOR_AGENT_ID,
            metadata=dict(metadata or {}),
        )

        domain_tasks: Dict[str, List[AgentTask]] = {}
        dependencies: Dict[str, List[str]] = {}

        # 0. Asset Import stage (if requested)
        import_tasks = []
        if has_import:
            t_import = AgentTask(
                task_id="stage_0_import",
                required_capability="interchange.asset_io",
                task_type="import_scene_asset",
                input_params={
                    "filepath": io_intents["import_path"],
                    "format": io_intents["import_format"],
                    "verify_checksum": bool("verify" in norm or "checksum" in norm),
                },
                dependencies=[],
            )
            import_tasks.append(t_import)

        # 1. Inspection stage (if requested or as initial scene check)
        if any(kw in norm for kw in ("inspect", "check", "audit", "summary", "read")):
            insp_deps = [import_tasks[-1].task_id] if import_tasks else []
            t_inspect = AgentTask(
                task_id="stage_0_inspect",
                required_capability="scene.inspection",
                task_type="get_scene_summary",
                input_params={},
                dependencies=insp_deps,
            )
            domain_tasks[SCENE_INSPECTOR_AGENT_ID] = [t_inspect]
            if insp_deps:
                dependencies[t_inspect.task_id] = insp_deps

        # 2. Environment & Architecture stage
        env_tasks = []
        env_deps = [import_tasks[-1].task_id] if import_tasks else []
        if any(kw in norm for kw in ("cyclorama", "studio", "backdrop", "cove")):
            t_cyc = AgentTask(
                task_id="stage_env_cyclorama",
                required_capability="environment.staging",
                task_type="create_cyclorama",
                input_params={"name": "StudioCyclorama", "width": 12.0, "depth": 12.0, "wall_height": 6.0},
                dependencies=env_deps,
            )
            env_tasks.append(t_cyc)
            if env_deps:
                dependencies[t_cyc.task_id] = env_deps
        elif any(kw in norm for kw in ("room", "interior", "enclosure", "architecture")):
            t_room = AgentTask(
                task_id="stage_env_room",
                required_capability="environment.architecture",
                task_type="create_room_enclosure",
                input_params={"name": "InteriorRoom", "width": 6.0, "length": 8.0, "height": 3.0, "wall_thickness": 0.2},
                dependencies=env_deps,
            )
            env_tasks.append(t_room)
            if env_deps:
                dependencies[t_room.task_id] = env_deps
        elif any(kw in norm for kw in ("terrain", "landscape", "elevation", "heightfield")):
            t_terrain = AgentTask(
                task_id="stage_env_terrain",
                required_capability="environment.terrain",
                task_type="create_terrain",
                input_params={"name": "LandscapeTerrain", "width": 50.0, "depth": 50.0, "elevation_scale": 5.0},
                dependencies=env_deps,
            )
            env_tasks.append(t_terrain)
            if env_deps:
                dependencies[t_terrain.task_id] = env_deps

        if env_tasks:
            domain_tasks[ENVIRONMENT_AGENT_ID] = env_tasks

        # 2. Modeling / Geometry stage
        modeling_tasks = []
        if has_import:
            has_explicit_primitive = any(
                kw in norm_actions
                for kw in (
                    "create primitive", "add primitive", "create cube", "add cube",
                    "create sphere", "add sphere", "create cylinder", "add cylinder",
                    "create plane", "add plane", "make a cube", "make a sphere"
                )
            )
        else:
            has_explicit_primitive = any(
                kw in norm_actions for kw in ("cube", "sphere", "cylinder", "plane", "primitive", "create primitive", "add primitive")
            ) or any(kw in norm_actions for kw in ("model", "create", "mesh"))
        if has_explicit_primitive:
            prim_type = "CUBE"
            if "sphere" in norm_actions:
                prim_type = "UVSPHERE"
            elif "cylinder" in norm_actions:
                prim_type = "CYLINDER"
            elif "plane" in norm_actions:
                prim_type = "PLANE"

            prim_params = {"primitive_type": prim_type, "name": "HeroAsset"}
            if prim_type == "CYLINDER":
                prim_params["radius"] = 1.0
                prim_params["depth"] = 2.0
            elif prim_type == "UVSPHERE":
                prim_params["radius"] = 1.0
            else:
                prim_params["size"] = 2.0

            prim_deps = [import_tasks[-1].task_id] if import_tasks else []
            t_model = AgentTask(
                task_id="stage_1_modeling",
                required_capability="modeling.primitive",
                task_type="create_primitive",
                input_params=prim_params,
                dependencies=prim_deps,
            )
            modeling_tasks.append(t_model)
            if prim_deps:
                dependencies[t_model.task_id] = prim_deps

        if modeling_tasks:
            domain_tasks[MODELING_AGENT_ID] = modeling_tasks

        # 3. Materials & Shaders stage
        mat_tasks = []
        has_mat_intent = any(kw in norm for kw in ("material", "shader", "roughness", "metallic", "texture", "pbr", "gold", "glossy")) or (
            "color" in norm and not any(kw in norm for kw in ("color strip", "color balance", "color grade", "color grading"))
        )
        if has_mat_intent:
            mat_deps = [modeling_tasks[-1].task_id] if modeling_tasks else ([import_tasks[-1].task_id] if import_tasks else [])
            t_mat = AgentTask(
                task_id="stage_2_materials",
                required_capability="materials.manage",
                task_type="create_material",
                input_params={"name": "HeroPBRMaterial", "roughness": 0.3, "metallic": 0.8},
                dependencies=mat_deps,
            )
            mat_tasks.append(t_mat)
            if mat_deps:
                dependencies[t_mat.task_id] = mat_deps

        if mat_tasks:
            domain_tasks[MATERIALS_AGENT_ID] = mat_tasks

        # 4. Rigging & Animation stage
        rig_tasks = []
        if any(kw in norm for kw in ("rig", "armature", "bone", "skin", "ik", "animate", "keyframe")):
            rig_deps = [modeling_tasks[-1].task_id] if modeling_tasks else ([import_tasks[-1].task_id] if import_tasks else [])
            t_rig = AgentTask(
                task_id="stage_3_rigging",
                required_capability="rigging.armatures",
                task_type="create_armature",
                input_params={"name": "HeroArmature", "location": [0.0, 0.0, 0.0]},
                dependencies=rig_deps,
            )
            rig_tasks.append(t_rig)
            if rig_deps:
                dependencies[t_rig.task_id] = rig_deps

        if rig_tasks:
            domain_tasks[RIGGING_ANIMATION_AGENT_ID] = rig_tasks

        # 5. Simulation & VFX stage
        sim_tasks = []
        if any(kw in norm for kw in ("physics", "rigid", "collision", "cloth", "gravity", "drop", "simulat")):
            sim_deps = [modeling_tasks[-1].task_id] if modeling_tasks else ([import_tasks[-1].task_id] if import_tasks else [])
            t_sim = AgentTask(
                task_id="stage_4_simulation",
                required_capability="physics.simulation",
                task_type="configure_physics",
                input_params={"object_name": "HeroAsset", "physics_type": "RIGID_BODY", "rigid_body_type": "ACTIVE", "mass": 2.5},
                dependencies=sim_deps,
            )
            sim_tasks.append(t_sim)
            if sim_deps:
                dependencies[t_sim.task_id] = sim_deps

        if sim_tasks:
            domain_tasks[SIMULATION_VFX_AGENT_ID] = sim_tasks

        # 6. Lighting & Cameras stage
        render_tasks = []
        has_vse_render = any(kw in norm for kw in ("render video", "render sequence", "vse render", "editorial render")) or (
            any(kw in norm for kw in ("mp4", "mov", "mkv")) and any(kw in norm for kw in ("video", "sequence", "timeline", "vse"))
        )
        has_scene_render = any(kw in norm for kw in (
            "render scene", "render the scene", "scene render",
            "render 3d", "3d render", "render plate", "render shot",
            "render frame", "render still", "rendered plate"
        )) or (
            "render" in norm and any(kw in norm for kw in ("scene", "3d", "plate", "shot", "camera", "turntable", "model", "geometry")) and not has_vse_render
        ) or (
            "render" in norm and any(kw in norm for kw in ("scene", "3d", "plate")) and has_vse_render
        )

        has_lighting_intent = any(kw in norm for kw in ("light", "sun", "camera", "turntable", "shot", "frame")) or (
            "render" in norm and not has_vse_render and not has_scene_render
        )
        if has_lighting_intent:
            light_deps = [modeling_tasks[-1].task_id] if modeling_tasks else ([import_tasks[-1].task_id] if import_tasks else [])
            t_light = AgentTask(
                task_id="stage_5_lighting",
                required_capability="lighting.manage",
                task_type="create_light",
                input_params={"name": "StudioSun", "light_type": "SUN", "energy": 4.0},
                dependencies=light_deps,
            )
            render_tasks.append(t_light)
            if light_deps:
                dependencies[t_light.task_id] = light_deps

        # 7. Compositor stage
        comp_tasks = []
        if any(kw in norm for kw in ("composite", "compositor", "denoise", "glare", "post-process")):
            prev_deps = [t.task_id for t in render_tasks] if render_tasks else ([modeling_tasks[-1].task_id] if modeling_tasks else [])
            t_comp = AgentTask(
                task_id="stage_6_compositor",
                required_capability="compositor.pipeline",
                task_type="manage_compositor_nodes",
                input_params={"action": "enable"},
                dependencies=prev_deps,
            )
            comp_tasks.append(t_comp)
            if prev_deps:
                dependencies[t_comp.task_id] = prev_deps

        if comp_tasks:
            domain_tasks[COMPOSITOR_AGENT_ID] = comp_tasks

        # Scene Render task (if requested, runs after lighting & compositor)
        t_scene_render = None
        if has_scene_render:
            render_deps = [comp_tasks[-1].task_id] if comp_tasks else ([render_tasks[-1].task_id] if render_tasks else ([modeling_tasks[-1].task_id] if modeling_tasks else ([import_tasks[-1].task_id] if import_tasks else [])))
            t_scene_render = AgentTask(
                task_id="stage_scene_render",
                required_capability="world.manage",
                task_type="render_scene",
                input_params={"render_mode": "still"},
                dependencies=list(render_deps),
            )
            render_tasks.append(t_scene_render)
            if render_deps:
                dependencies[t_scene_render.task_id] = list(render_deps)

        if render_tasks:
            domain_tasks[RENDER_LIGHTING_AGENT_ID] = render_tasks

        # 8. Video Editing & Sequencer stage
        editorial_tasks = []
        is_video_context = any(
            kw in norm
            for kw in (
                "video", "sequence", "timeline", "vse", "strip",
                "edit", "trim", "transition", "audio track",
                "soundtrack", "subtitle", "title card", "lower third",
                "lower-third", "pip", "picture-in-picture", "picture in picture",
                "overlay", "inset", "color grade", "color grading", "color balance",
                "transform", "crop"
            )
        ) or (has_scene_render and any(kw in norm for kw in ("timeline", "assemble", "edit", "strip", "sequence", "plate", "handoff", "import")))
        if is_video_context:
            current_deps = [t_scene_render.task_id] if t_scene_render else [t.task_id for t in (comp_tasks or render_tasks)]
            planned_video_strips = []
            planned_audio_strips = []

            has_overlay_intent = any(
                kw in norm
                for kw in (
                    "pip", "picture-in-picture", "picture in picture",
                    "overlay", "inset"
                )
            )
            has_transform_intent = any(
                kw in norm
                for kw in ("transform", "reposition", "scale", "corner", "offset")
            ) or has_overlay_intent
            has_crop_intent = any(
                kw in norm
                for kw in ("crop", "cropping", "crop border", "crop margin", "crop edge", "crop framing")
            )
            has_grade_intent = any(
                kw in norm
                for kw in (
                    "color grade", "color grading", "color balance",
                    "bright/contrast", "brightness/contrast", "contrast",
                    "strip modifier", "warm grade", "cool grade",
                    "lift gamma gain", "asc-cdl"
                )
            )
            has_title_intent = any(
                kw in norm
                for kw in ("title", "subtitle", "lower-third", "lower third", "caption", "text strip", "title card")
            )
            has_style_intent = any(
                kw in norm
                for kw in (
                    "lower-third", "lower third", "styled title", "title box",
                    "caption box", "subtitle box", "box background", "style title",
                    "typography", "shadow"
                )
            )

            # 8a. Timeline assembly / base strips (Channel 1)
            if has_scene_render:
                plate_name = "RenderPlate"
                t_timeline = AgentTask(
                    task_id="stage_vse_timeline",
                    required_capability="video.timeline",
                    task_type="create_vse_strip",
                    input_params={
                        "strip_type": "IMAGE",
                        "name": plate_name,
                        "channel": 1,
                        "frame_start": 1,
                        "duration": 50,
                        "filepath": TaskOutputRef(
                            task_id=t_scene_render.task_id,
                            path="output_file",
                            expected_type="string",
                        ).to_dict(),
                    },
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_timeline)
                planned_video_strips.append(plate_name)
                if current_deps:
                    dependencies[t_timeline.task_id] = list(current_deps)
                current_deps = [t_timeline.task_id]
            elif any(kw in norm for kw in ("timeline", "assemble", "assembly", "color strip", "create strip", "add strip", "new strip", "background")) or has_overlay_intent:
                strip_name = "ColorStrip"
                t_timeline = AgentTask(
                    task_id="stage_vse_timeline",
                    required_capability="video.timeline",
                    task_type="create_vse_strip",
                    input_params={
                        "strip_type": "COLOR",
                        "name": strip_name,
                        "channel": 1,
                        "frame_start": 1,
                        "duration": 50,
                        "color": [0.1, 0.1, 0.1],
                    },
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_timeline)
                planned_video_strips.append(strip_name)
                if current_deps:
                    dependencies[t_timeline.task_id] = list(current_deps)
                current_deps = [t_timeline.task_id]

            # 8b. Multi-track overlay / Inset strip (Channel 2)
            overlay_name = None
            if has_overlay_intent:
                overlay_name = "OverlayStrip"
                t_overlay = AgentTask(
                    task_id="stage_vse_overlay",
                    required_capability="video.timeline",
                    task_type="create_vse_strip",
                    input_params={
                        "strip_type": "COLOR",
                        "name": overlay_name,
                        "channel": 2,
                        "frame_start": 1,
                        "duration": 50,
                        "color": [0.2, 0.4, 0.8],
                    },
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_overlay)
                planned_video_strips.append(overlay_name)
                if current_deps:
                    dependencies[t_overlay.task_id] = list(current_deps)
                current_deps = [t_overlay.task_id]

            # 8c. 2D Transforms & Cropping (Spatial composition)
            if has_transform_intent:
                target_transform = overlay_name if overlay_name else (planned_video_strips[-1] if planned_video_strips else "ColorStrip")
                t_transform = AgentTask(
                    task_id="stage_vse_transform",
                    required_capability="video.transforms",
                    task_type="transform_vse_strip",
                    input_params={
                        "name": target_transform,
                        "scale_x": 0.35,
                        "scale_y": 0.35,
                        "offset_x": 220.0,
                        "offset_y": 140.0,
                        "action": "UPDATE",
                    },
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_transform)
                if current_deps:
                    dependencies[t_transform.task_id] = list(current_deps)
                current_deps = [t_transform.task_id]

            if has_crop_intent:
                target_crop = overlay_name if overlay_name else (planned_video_strips[-1] if planned_video_strips else "ColorStrip")
                t_crop = AgentTask(
                    task_id="stage_vse_crop",
                    required_capability="video.transforms",
                    task_type="crop_vse_strip",
                    input_params={
                        "name": target_crop,
                        "min_x": 10,
                        "max_x": 10,
                        "min_y": 10,
                        "max_y": 10,
                        "action": "UPDATE",
                    },
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_crop)
                if current_deps:
                    dependencies[t_crop.task_id] = list(current_deps)
                current_deps = [t_crop.task_id]

            # 8d. Strip-level color grading modifiers
            if has_grade_intent:
                target_grade = planned_video_strips[0] if planned_video_strips else ("RenderPlate" if has_scene_render else "ColorStrip")
                if any(kw in norm for kw in ("contrast", "bright", "bright_contrast", "brightness")):
                    grade_params = {
                        "action": "ADD",
                        "name": target_grade,
                        "modifier_type": "BRIGHT_CONTRAST",
                        "bright": 0.1,
                        "contrast": 1.2,
                    }
                else:
                    grade_params = {
                        "action": "ADD",
                        "name": target_grade,
                        "modifier_type": "COLOR_BALANCE",
                        "correction_method": "LIFT_GAMMA_GAIN",
                        "lift": [0.0, 0.0, 0.05],
                        "gamma": [1.0, 1.0, 1.0],
                        "gain": [1.1, 1.05, 0.95],
                        "color_multiply": 1.1,
                    }

                t_grade = AgentTask(
                    task_id="stage_vse_grade",
                    required_capability="video.grading",
                    task_type="manage_vse_strip_modifiers",
                    input_params=grade_params,
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_grade)
                if current_deps:
                    dependencies[t_grade.task_id] = list(current_deps)
                current_deps = [t_grade.task_id]

            # 8e. Editorial cuts & trims
            if any(kw in norm for kw in ("trim", "cut", "split")):
                target_strip = planned_video_strips[0] if planned_video_strips else "ColorStrip"
                if "trim" in norm:
                    t_edit = AgentTask(
                        task_id="stage_vse_trim",
                        required_capability="video.editorial",
                        task_type="trim_vse_strip",
                        input_params={"name": target_strip, "left_handle": 10, "right_handle": 50},
                        dependencies=list(current_deps),
                    )
                else:
                    t_edit = AgentTask(
                        task_id="stage_vse_split",
                        required_capability="video.editorial",
                        task_type="split_vse_strip",
                        input_params={"name": target_strip, "split_frame": 25},
                        dependencies=list(current_deps),
                    )
                    split_second_strip = f"{target_strip}_split"
                    if target_strip not in planned_video_strips:
                        planned_video_strips.append(target_strip)
                    planned_video_strips.append(split_second_strip)

                editorial_tasks.append(t_edit)
                if current_deps:
                    dependencies[t_edit.task_id] = list(current_deps)
                current_deps = [t_edit.task_id]

            # 8f. Transitions
            if any(kw in norm for kw in ("transition", "crossfade", "fade", "wipe", "dissolve")):
                if len(planned_video_strips) >= 2:
                    input1 = planned_video_strips[0]
                    input2 = planned_video_strips[1]
                elif planned_video_strips:
                    second_strip_name = f"{planned_video_strips[0]}_B"
                    input1 = planned_video_strips[0]
                    input2 = second_strip_name
                else:
                    input1 = "StripA"
                    input2 = "StripB"

                t_trans = AgentTask(
                    task_id="stage_vse_transition",
                    required_capability="video.transitions",
                    task_type="create_vse_transition",
                    input_params={"transition_type": "CROSS", "input1": input1, "input2": input2},
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_trans)
                if current_deps:
                    dependencies[t_trans.task_id] = list(current_deps)
                current_deps = [t_trans.task_id]

            # 8g. Titles & typography
            if has_title_intent:
                title_channel = 3 if has_overlay_intent else 2
                is_lower_third = any(kw in norm for kw in ("lower-third", "lower third"))
                text_content = "Lower Third" if is_lower_third else "Title Card"
                text_name = "LowerThird" if is_lower_third else "TitleCard"

                title_params = {
                    "text": text_content,
                    "channel": title_channel,
                    "frame_start": 1,
                    "duration": 60,
                }
                if has_style_intent or is_lower_third:
                    title_params["name"] = text_name

                t_title = AgentTask(
                    task_id="stage_vse_title",
                    required_capability="video.titles",
                    task_type="create_vse_text_strip",
                    input_params=title_params,
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_title)
                if current_deps:
                    dependencies[t_title.task_id] = list(current_deps)
                current_deps = [t_title.task_id]

                if has_style_intent:
                    t_title_style = AgentTask(
                        task_id="stage_vse_title_style",
                        required_capability="video.titles",
                        task_type="configure_vse_text_style",
                        input_params={
                            "name": text_name,
                            "action": "UPDATE",
                            "font_size": 42.0,
                            "location": [0.1, 0.15],
                            "alignment_x": "LEFT",
                            "use_box": True,
                            "box_color": [0.0, 0.0, 0.0, 0.7],
                            "box_margin": 0.1,
                            "use_shadow": True,
                        },
                        dependencies=list(current_deps),
                    )
                    editorial_tasks.append(t_title_style)
                    if current_deps:
                        dependencies[t_title_style.task_id] = list(current_deps)
                    current_deps = [t_title_style.task_id]

            # 8h. Audio engineering
            has_audio_intent = any(kw in norm for kw in ("audio", "sound", "music", "soundtrack", "mixdown", "volume"))
            has_audio_track_creation = any(
                kw in norm
                for kw in ("add audio", "create audio", "add sound", "audio track", "sound strip", "audio strip", "soundtrack track")
            ) or any(ext in norm for ext in (".wav", ".mp3", ".ogg", ".flac", ".aac"))

            if has_audio_intent:
                audio_strip_name = "AudioTrack"
                audio_channel = 4 if has_overlay_intent else 3
                if has_audio_track_creation:
                    import re
                    match = re.search(r'[\w\-/\\]+\.(?:wav|mp3|ogg|flac|aac)', norm)
                    sound_path = match.group(0) if match else "soundtrack.wav"
                    t_audio_strip = AgentTask(
                        task_id="stage_vse_audio_strip",
                        required_capability="video.timeline",
                        task_type="create_vse_strip",
                        input_params={
                            "strip_type": "SOUND",
                            "name": audio_strip_name,
                            "filepath": sound_path,
                            "channel": audio_channel,
                            "frame_start": 1,
                        },
                        dependencies=list(current_deps),
                    )
                    editorial_tasks.append(t_audio_strip)
                    planned_audio_strips.append(audio_strip_name)
                    if current_deps:
                        dependencies[t_audio_strip.task_id] = list(current_deps)
                    current_deps = [t_audio_strip.task_id]

                target_audio_name = planned_audio_strips[-1] if planned_audio_strips else "AudioTrack"
                t_audio = AgentTask(
                    task_id="stage_vse_audio",
                    required_capability="video.audio",
                    task_type="configure_vse_audio",
                    input_params={"name": target_audio_name, "volume": 1.0},
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_audio)
                if current_deps:
                    dependencies[t_audio.task_id] = list(current_deps)
                current_deps = [t_audio.task_id]

            # 8i. Sequencer rendering
            if any(kw in norm for kw in ("render video", "render sequence", "vse render", "editorial render")) or (
                has_vse_render and any(kw in norm for kw in ("render", "export", "mp4", "mov", "mkv", "encode"))
            ) or (
                not has_scene_render and any(kw in norm for kw in ("render", "export", "mp4", "mov", "mkv", "encode"))
            ):
                t_render = AgentTask(
                    task_id="stage_vse_render",
                    required_capability="video.rendering",
                    task_type="render_vse_sequence",
                    input_params={"output_path": "editorial_render.mp4", "format": "MPEG4"},
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_render)
                if current_deps:
                    dependencies[t_render.task_id] = list(current_deps)
                current_deps = [t_render.task_id]

            # Fallback for general video request with no sub-intent matched
            if not editorial_tasks:
                t_vse = AgentTask(
                    task_id="stage_vse_timeline",
                    required_capability="video.timeline",
                    task_type="create_vse_strip",
                    input_params={
                        "strip_type": "COLOR",
                        "name": "ColorStrip",
                        "channel": 1,
                        "frame_start": 1,
                        "duration": 50,
                        "color": [0.1, 0.1, 0.1],
                    },
                    dependencies=list(current_deps),
                )
                editorial_tasks.append(t_vse)
                if current_deps:
                    dependencies[t_vse.task_id] = list(current_deps)

        if editorial_tasks:
            domain_tasks[VIDEO_EDITOR_AGENT_ID] = editorial_tasks

        # 9. Interchange & Delivery stage (Import, Export, and Save Project)
        interchange_tasks = []
        if import_tasks:
            interchange_tasks.extend(import_tasks)

        delivery_tasks = []
        if io_intents["has_export"]:
            all_processing = (
                import_tasks + env_tasks + modeling_tasks + mat_tasks +
                rig_tasks + sim_tasks + render_tasks + comp_tasks + editorial_tasks
            )
            all_prev = [t.task_id for t in all_processing]
            t_export = AgentTask(
                task_id="stage_7_delivery",
                required_capability="interchange.asset_io",
                task_type="export_scene_asset",
                input_params={
                    "filepath": io_intents["export_path"],
                    "format": io_intents["export_format"],
                    "selected_only": bool("selected" in norm),
                    "overwrite": bool("overwrite" in norm),
                },
                dependencies=all_prev,
            )
            delivery_tasks.append(t_export)
            if all_prev:
                dependencies[t_export.task_id] = all_prev

        if delivery_tasks:
            interchange_tasks.extend(delivery_tasks)

        project_tasks = []
        if io_intents["has_save_project"]:
            all_prior = (
                import_tasks + env_tasks + modeling_tasks + mat_tasks +
                rig_tasks + sim_tasks + render_tasks + comp_tasks + editorial_tasks + delivery_tasks
            )
            save_deps = [delivery_tasks[-1].task_id] if delivery_tasks else ([all_prior[-1].task_id] if all_prior else [])
            t_save = AgentTask(
                task_id="stage_save_project",
                required_capability="interchange.project",
                task_type="save_blend_file",
                input_params={
                    "filepath": io_intents["save_path"],
                    "overwrite": bool("overwrite" in norm),
                },
                dependencies=save_deps,
            )
            project_tasks.append(t_save)
            if save_deps:
                dependencies[t_save.task_id] = save_deps

        if project_tasks:
            interchange_tasks.extend(project_tasks)

        if interchange_tasks:
            domain_tasks[INTERCHANGE_DELIVERY_AGENT_ID] = interchange_tasks

        contract.domain_tasks = domain_tasks
        contract.dependencies = dependencies
        return contract

    def submit_contract(
        self,
        contract: DelegationContract,
        dispatcher: Any,
        session_id: str = "default",
        trusted_approval: Optional[bool] = None,
    ) -> Tuple[TaskPlan, List[Any]]:
        """
        Submits a DelegationContract for execution through the dispatcher.
        Enforces human approval gating across all mutation tasks before execution.
        """
        # 1. Check for untrusted model approvals in any task parameters
        for aid, tasks in contract.domain_tasks.items():
            for t in tasks:
                if t.input_params and t.input_params.get("approved") is True:
                    raise PermissionError(
                        f"Untrusted approved=True flag detected in task '{t.task_id}' assigned to '{aid}'. "
                        "Model-supplied approvals are strictly prohibited."
                    )

        # 2. Compile DelegationContract to TaskPlan
        plan = contract.compile_plan(session_id=session_id)

        # 3. Check if human approval is required
        has_mutations = any(
            t.required_capability not in ("scene.inspection", "visual.capture", "director.orchestration", "rigging.inspection", "physics.inspection", "compositor.inspection")
            and not (t.required_capability == "video.timeline" and t.task_type == "inspect_vse_timeline")
            for t in plan.tasks.values()
        )

        # Check local test auto-approval environment variable
        is_local_autoapprove = os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE") == "1"
        if trusted_approval is not None:
            effective_approval = bool(trusted_approval)
        else:
            effective_approval = is_local_autoapprove

        if has_mutations and not effective_approval:
            # Plan cannot proceed without human authorization
            if plan.status == TaskStatus.PENDING:
                plan.transition_to(TaskStatus.READY)
            plan.transition_to(TaskStatus.AWAITING_APPROVAL)
            for t in plan.tasks.values():
                if t.status == TaskStatus.PENDING:
                    t.transition_to(TaskStatus.READY)
                if t.status == TaskStatus.READY:
                    t.transition_to(TaskStatus.AWAITING_APPROVAL)
            
            from shared.models.agent_contracts import AgentResult
            from ..agents.dispatcher import DispatchResult
            results = [
                DispatchResult(
                    success=False,
                    task_id=t.task_id,
                    plan_id=plan.plan_id,
                    session_id=session_id,
                    status=TaskStatus.AWAITING_APPROVAL,
                    error_code="APPROVAL_REQUIRED",
                    message="Scene mutation plan requires human approval before delegated execution.",
                )
                for t in plan.tasks.values()
            ]
            return plan, results

        # 4. If approved or read-only, dispatch through dispatcher
        results = dispatcher.dispatch_plan(
            plan,
            session_id=session_id,
            trusted_approval=effective_approval,
        )
        return plan, results

    def compile_workflow(
        self,
        contract: DelegationContract,
        orchestrator: Optional[Any] = None,
        gates: Optional[Dict[str, Any]] = None,
    ):
        """
        Compiles a DelegationContract into a WorkflowDAG for WorkflowOrchestrator.
        """
        from ..workflow.orchestrator import WorkflowOrchestrator
        orch = orchestrator or WorkflowOrchestrator()
        return orch.compile_contract(contract, gates=gates)

    def submit_workflow(
        self,
        contract: DelegationContract,
        orchestrator: Any,
        session_id: str = "default",
        trusted_approval: Optional[bool] = None,
        gates: Optional[Dict[str, List[Any]]] = None,
        adaptive_replan_fn: Optional[Callable[[Any, str], Optional[AgentTask]]] = None,
    ):
        """
        Submits a DelegationContract for execution through WorkflowOrchestrator.
        Enforces human approval gating, in-memory checkpointing, verification gates,
        and transactional rollback recovery.
        """
        # 1. Reject untrusted model approvals in any task parameters
        for aid, tasks in contract.domain_tasks.items():
            for t in tasks:
                if t.input_params and t.input_params.get("approved") is True:
                    raise PermissionError(
                        f"Untrusted approved=True flag detected in task '{t.task_id}' assigned to '{aid}'. "
                        "Model-supplied approvals are strictly prohibited."
                    )

        # 2. Compile contract into WorkflowDAG via orchestrator
        dag = orchestrator.compile_contract(contract, gates=gates)

        # 3. Check if human approval is required
        has_mutations = any(
            stage.task.required_capability not in ("scene.inspection", "visual.capture", "director.orchestration", "rigging.inspection", "physics.inspection", "compositor.inspection")
            and not (stage.task.required_capability == "video.timeline" and stage.task.task_type == "inspect_vse_timeline")
            for stage in dag.stages.values()
        )

        is_local_autoapprove = os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE") == "1"
        if trusted_approval is not None:
            effective_approval = bool(trusted_approval)
        else:
            effective_approval = is_local_autoapprove

        # 4. Execute workflow via orchestrator
        return orchestrator.execute_workflow(
            dag=dag,
            session_id=session_id,
            requires_human_approval=has_mutations,
            approval_status="APPROVED" if effective_approval else "PENDING",
            trusted_approval=effective_approval,
            adaptive_replan_fn=adaptive_replan_fn,
        )

    def batch_convert(
        self,
        input_paths: List[str],
        output_dir: str,
        target_format: str = "GLB",
        orchestrator: Optional[Any] = None,
        executor: Optional[Any] = None,
        trusted_approval: bool = True,
        overwrite: bool = True,
        session_id: str = "batch_session",
        gates: Optional[Dict[str, List[Any]]] = None,
    ):
        """
        Executes a batch multi-asset conversion across input files into target format
        using BatchAssetProcessor and WorkflowOrchestrator.
        """
        from ..workflow.batch import BatchAssetProcessor
        processor = BatchAssetProcessor(
            orchestrator=orchestrator,
            executor=executor,
            director=self,
        )
        return processor.process_batch(
            input_paths=input_paths,
            output_dir=output_dir,
            target_format=target_format,
            trusted_approval=trusted_approval,
            overwrite=overwrite,
            session_id=session_id,
            gates=gates,
        )

