"""
Agent Registry for Universal MCP.
Stores, validates, and discovers specialized agent manifests and declared capabilities.
"""

from typing import Dict, Any, List, Optional
from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
)


def create_default_registry() -> "AgentRegistry":
    """
    Factory creating an AgentRegistry populated with the verified baseline agents
    confirmed by the functional coverage roadmap and test evidence.
    """
    registry = AgentRegistry()

    from .scene_inspector import create_scene_inspector_manifest
    from .modeling import create_modeling_manifest
    from .materials import create_materials_manifest
    from .render_lighting import create_render_lighting_manifest
    from .rigging_animation import create_rigging_animation_manifest
    from .simulation_vfx import create_simulation_vfx_manifest
    from .interchange_delivery import create_interchange_delivery_manifest
    from .compositor import create_compositor_manifest
    from .director import create_director_manifest
    from .environment import create_environment_manifest
    from .video_editor import create_video_editor_manifest

    # 1. Director Agent (Top-level supervisor and brief orchestrator)
    director_agent = create_director_manifest(version="0.1.80")
    registry.register_agent(director_agent)

    # 2. Scene Inspector Agent (Verified read-only scene inspection & visual capture)
    scene_inspector = create_scene_inspector_manifest(version="0.1.13")
    registry.register_agent(scene_inspector)

    # 3. Modeling & Geometry Agent (Verified mesh primitives, transforms, and structured modeling)
    modeling_agent = create_modeling_manifest(version="0.1.13")
    registry.register_agent(modeling_agent)

    # 4. Materials Agent (Verified Principled BSDF creation and slot assignment)
    materials_agent = create_materials_manifest(version="0.1.13")
    registry.register_agent(materials_agent)

    # 5. Render & Lighting Agent (Verified light sources and world background settings)
    render_lighting_agent = create_render_lighting_manifest(version="0.1.13")
    registry.register_agent(render_lighting_agent)

    # 6. Rigging & Animation Agent (Verified skeletal armatures, skinning, IK, and keyframes)
    rigging_animation_agent = create_rigging_animation_manifest(version="0.1.80")
    registry.register_agent(rigging_animation_agent)

    # 7. Simulation & VFX Agent (Verified rigid bodies, cloth, collision, and point caches)
    simulation_vfx_agent = create_simulation_vfx_manifest(version="0.1.80")
    registry.register_agent(simulation_vfx_agent)

    # 8. Interchange & Delivery Agent (Verified glTF/USD serialization and packaging)
    interchange_delivery_agent = create_interchange_delivery_manifest(version="0.1.80")
    registry.register_agent(interchange_delivery_agent)

    # 9. Compositor Agent (Verified compositing node trees and render pass routing)
    compositor_agent = create_compositor_manifest(version="0.1.80")
    registry.register_agent(compositor_agent)

    # 10. Environment & Architecture Agent (Verified macro-environment staging, architecture, terrain, and layout)
    environment_agent = create_environment_manifest(version="0.1.92")
    registry.register_agent(environment_agent)

    # 11. Video Editor and Sequencer Agent (Verified non-linear video editing, strips, transitions, titles, and rendering)
    video_editor_agent = create_video_editor_manifest(version="0.1.92")
    registry.register_agent(video_editor_agent)

    return registry


class AgentRegistry:
    """
    In-memory registry of specialized agents and their capability manifests.
    Thread-safe reads; provides deterministic lookup by agent ID or capability.
    """

    def __init__(self):
        self._agents: Dict[str, AgentManifest] = {}

    def register_agent(self, manifest: AgentManifest, overwrite: bool = False) -> None:
        """
        Validates and registers an agent manifest.
        Raises ValueError if manifest is invalid or agent_id already exists without overwrite.
        """
        manifest.validate()
        if manifest.agent_id in self._agents and not overwrite:
            raise ValueError(
                f"Agent with ID '{manifest.agent_id}' is already registered. Set overwrite=True to replace."
            )
        self._agents[manifest.agent_id] = manifest

    def unregister_agent(self, agent_id: str) -> bool:
        """Removes an agent from the registry. Returns True if removed, False if not found."""
        return self._agents.pop(agent_id, None) is not None

    def get_agent(self, agent_id: str) -> Optional[AgentManifest]:
        """Retrieves an agent manifest by ID."""
        return self._agents.get(agent_id)

    def list_agents(self, enabled_only: bool = True) -> List[AgentManifest]:
        """Returns list of registered agent manifests."""
        if enabled_only:
            return [a for a in self._agents.values() if a.enabled]
        return list(self._agents.values())

    def get_verified_capabilities(self) -> List[CapabilityDescriptor]:
        """Returns list of all capabilities declared with verification_status='VERIFIED'."""
        verified = []
        for agent in self._agents.values():
            if not agent.enabled:
                continue
            for cap in agent.capabilities:
                if cap.verification_status == "VERIFIED":
                    verified.append(cap)
        return verified

    def find_agents_by_capability(
        self,
        capability_id: str,
        task_type: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[AgentManifest]:
        """Finds all agents declaring a specified capability ID and optional task type."""
        matches = []
        for agent in self._agents.values():
            if enabled_only and not agent.enabled:
                continue
            if agent.has_capability(capability_id, task_type=task_type):
                matches.append(agent)
        return matches

    def find_capability_by_task_type(
        self,
        task_type: str,
        enabled_only: bool = True,
    ) -> Optional[CapabilityDescriptor]:
        """Finds the first capability descriptor that declares support for the given task_type."""
        for agent in self._agents.values():
            if enabled_only and not agent.enabled:
                continue
            for cap in agent.capabilities:
                if task_type in cap.supported_task_types:
                    return cap
        return None
