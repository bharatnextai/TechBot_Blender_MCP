"""
Central Agent Manager for Universal MCP.
Coordinates capability registration, deterministic routing, and dependency-aware task planning.
Preserves existing execution architecture and security boundaries.
"""

from typing import Dict, Any, List, Optional
from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    TaskPlan,
    TaskStatus,
)
from .registry import AgentRegistry, create_default_registry
from .router import CapabilityRouter, RoutingResult
from .planner import TaskPlanner


class AgentManager:
    """
    Central orchestration facade for the Universal MCP multi-agent architecture.
    Provides deterministic capability matching, plan validation, and topological ordering.
    Does not execute mutations or bypass human approval.
    """

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        router: Optional[CapabilityRouter] = None,
        planner: Optional[TaskPlanner] = None,
    ):
        self.registry = registry or create_default_registry()
        self.router = router or CapabilityRouter(self.registry)
        self.planner = planner or TaskPlanner(self.router)

    def register_agent(self, manifest: AgentManifest, overwrite: bool = False) -> None:
        """Registers a new specialized agent manifest into the registry."""
        self.registry.register_agent(manifest, overwrite=overwrite)

    def get_agent(self, agent_id: str) -> Optional[AgentManifest]:
        """Retrieves an agent manifest by ID."""
        return self.registry.get_agent(agent_id)

    def list_agents(self, enabled_only: bool = True) -> List[AgentManifest]:
        """Lists all registered agent manifests."""
        return self.registry.list_agents(enabled_only=enabled_only)

    def list_verified_capabilities(self) -> List[CapabilityDescriptor]:
        """Lists all capabilities confirmed as VERIFIED by inspected evidence."""
        return self.registry.get_verified_capabilities()

    def route_task(
        self,
        task: AgentTask,
        require_verified: bool = True,
        strict_ambiguity: bool = False,
    ) -> RoutingResult:
        """Deterministically routes an AgentTask to a specialized agent."""
        return self.router.route(task, require_verified=require_verified, strict_ambiguity=strict_ambiguity)

    def create_plan(
        self,
        title: str,
        tasks: List[AgentTask],
        metadata: Optional[Dict[str, Any]] = None,
        require_verified_capabilities: bool = True,
    ) -> TaskPlan:
        """
        Creates, statically validates, and topologically orders a TaskPlan.
        Raises ValueError if plan fails validation or contains cycles.
        """
        plan = TaskPlan(title=title, metadata=metadata or {})
        for task in tasks:
            plan.add_task(task)

        # Validate plan
        errors = self.planner.validate_plan(
            plan,
            require_verified_capabilities=require_verified_capabilities,
        )
        if errors:
            raise ValueError(f"TaskPlan validation failed with {len(errors)} error(s): {'; '.join(errors)}")

        # Establish deterministic execution order
        self.planner.compute_execution_order(plan)
        return plan

    def validate_plan(
        self,
        plan: TaskPlan,
        require_verified_capabilities: bool = True,
    ) -> List[str]:
        """Validates an existing TaskPlan and returns any errors found."""
        return self.planner.validate_plan(
            plan,
            require_verified_capabilities=require_verified_capabilities,
        )
