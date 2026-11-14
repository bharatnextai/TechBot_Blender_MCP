"""
Agent Manager package for Universal MCP.
Exposes AgentRegistry, CapabilityRouter, TaskPlanner, and AgentManager.
"""

from .registry import AgentRegistry, create_default_registry
from .router import CapabilityRouter, RoutingResult
from .planner import TaskPlanner
from .manager import AgentManager
from .session_coordinator import SessionCoordinator, SessionContext
from .dispatcher import AgentDispatcher, DispatchResult
from .scene_inspector import (
    SceneInspectorAgent,
    create_scene_inspector_manifest,
    SCENE_INSPECTOR_AGENT_ID,
    SCENE_INSPECTION_CAPABILITY_ID,
)
from .modeling import (
    ModelingAgent,
    create_modeling_manifest,
    MODELING_AGENT_ID,
    CAPABILITY_MODELING_PRIMITIVE,
    CAPABILITY_MODELING_TRANSFORM,
    CAPABILITY_MODELING_EXECUTION,
)
from .materials import (
    MaterialsAgent,
    create_materials_manifest,
    MATERIALS_AGENT_ID,
    CAPABILITY_MATERIALS_MANAGE,
    CAPABILITY_MATERIALS_INSPECT,
)
from .rigging_animation import (
    RiggingAnimationAgent,
    create_rigging_animation_manifest,
    RIGGING_ANIMATION_AGENT_ID,
)
from .simulation_vfx import (
    SimulationVFXAgent,
    create_simulation_vfx_manifest,
    SIMULATION_VFX_AGENT_ID,
)
from .interchange_delivery import (
    InterchangeDeliveryAgent,
    create_interchange_delivery_manifest,
    INTERCHANGE_DELIVERY_AGENT_ID,
)
from .compositor import (
    CompositorAgent,
    create_compositor_manifest,
    COMPOSITOR_AGENT_ID,
)
from .director import (
    DirectorAgent,
    create_director_manifest,
    DIRECTOR_AGENT_ID,
)
from .video_editor import (
    VideoEditorAgent,
    create_video_editor_manifest,
    VIDEO_EDITOR_AGENT_ID,
)
from .render_lighting import (
    RenderLightingAgent,
    create_render_lighting_manifest,
    RENDER_LIGHTING_AGENT_ID,
    CAPABILITY_LIGHTING_MANAGE,
    CAPABILITY_WORLD_MANAGE,
    CAPABILITY_LIGHTING_INSPECT,
)

__all__ = [
    "AgentRegistry",
    "create_default_registry",
    "CapabilityRouter",
    "RoutingResult",
    "TaskPlanner",
    "AgentManager",
    "SessionCoordinator",
    "SessionContext",
    "AgentDispatcher",
    "DispatchResult",
    "SceneInspectorAgent",
    "create_scene_inspector_manifest",
    "SCENE_INSPECTOR_AGENT_ID",
    "SCENE_INSPECTION_CAPABILITY_ID",
    "ModelingAgent",
    "create_modeling_manifest",
    "MODELING_AGENT_ID",
    "CAPABILITY_MODELING_PRIMITIVE",
    "CAPABILITY_MODELING_TRANSFORM",
    "CAPABILITY_MODELING_EXECUTION",
    "MaterialsAgent",
    "create_materials_manifest",
    "MATERIALS_AGENT_ID",
    "CAPABILITY_MATERIALS_MANAGE",
    "CAPABILITY_MATERIALS_INSPECT",
    "RenderLightingAgent",
    "create_render_lighting_manifest",
    "RENDER_LIGHTING_AGENT_ID",
    "CAPABILITY_LIGHTING_MANAGE",
    "CAPABILITY_WORLD_MANAGE",
    "CAPABILITY_LIGHTING_INSPECT",
    "RiggingAnimationAgent",
    "create_rigging_animation_manifest",
    "RIGGING_ANIMATION_AGENT_ID",
    "SimulationVFXAgent",
    "create_simulation_vfx_manifest",
    "SIMULATION_VFX_AGENT_ID",
    "InterchangeDeliveryAgent",
    "create_interchange_delivery_manifest",
    "INTERCHANGE_DELIVERY_AGENT_ID",
    "CompositorAgent",
    "create_compositor_manifest",
    "COMPOSITOR_AGENT_ID",
    "DirectorAgent",
    "create_director_manifest",
    "DIRECTOR_AGENT_ID",
    "VideoEditorAgent",
    "create_video_editor_manifest",
    "VIDEO_EDITOR_AGENT_ID",
]