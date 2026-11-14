"""
Deterministic Capability Router for Universal MCP Agent Manager.
Matches incoming task requirements against registered agent capabilities,
filtering unverified capabilities and resolving matches deterministically.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
)
from .registry import AgentRegistry


def _parse_version(v_str: str) -> Tuple[int, ...]:
    """Helper to parse a semantic version string into a comparable integer tuple."""
    parts = []
    for chunk in str(v_str).split("."):
        clean = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(clean) if clean else 0)
    return tuple(parts) if parts else (0,)


@dataclass
class RoutingResult:
    """
    Structured outcome of capability routing.
    """
    success: bool
    agent: Optional[AgentManifest] = None
    capability: Optional[CapabilityDescriptor] = None
    error_code: Optional[str] = None  # None, "NO_MATCH", "UNVERIFIED_CAPABILITY", "AMBIGUOUS_MATCH"
    message: str = ""
    candidates: List[Tuple[AgentManifest, CapabilityDescriptor]] = field(default_factory=list)


class CapabilityRouter:
    """
    Deterministic router selecting specialized agents by declared capabilities.
    Enforces verification status filtering and deterministic tie-breaking.
    """

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or AgentRegistry()

    def route(
        self,
        task: AgentTask,
        require_verified: bool = True,
        strict_ambiguity: bool = False,
    ) -> RoutingResult:
        """
        Routes an AgentTask to the appropriate registered agent:
        1. Identifies agents declaring task.required_capability and task.task_type.
        2. Filters out disabled agents.
        3. If require_verified=True, rejects unverified capabilities.
        4. Applies deterministic tie-breaking if multiple agents qualify.
        """
        req_cap = task.required_capability
        task_type = task.task_type or None

        candidates: List[Tuple[AgentManifest, CapabilityDescriptor]] = []
        unverified_found: List[Tuple[AgentManifest, CapabilityDescriptor]] = []

        all_agents = self.registry.list_agents(enabled_only=True)

        for agent in all_agents:
            cap = agent.get_capability(req_cap)
            if not cap:
                continue
            # Check task_type compatibility if specified
            if task_type and cap.supported_task_types and task_type not in cap.supported_task_types:
                continue

            if cap.verification_status != "VERIFIED":
                unverified_found.append((agent, cap))
                if require_verified:
                    continue

            candidates.append((agent, cap))

        # 1. No matches found
        if not candidates:
            if unverified_found:
                agent_ids = [a.agent_id for a, _ in unverified_found]
                return RoutingResult(
                    success=False,
                    error_code="UNVERIFIED_CAPABILITY",
                    message=(
                        f"Capability '{req_cap}' is declared by agent(s) {agent_ids} "
                        f"but has verification_status='{unverified_found[0][1].verification_status}' "
                        f"and cannot be routed for execution."
                    ),
                    candidates=unverified_found,
                )
            return RoutingResult(
                success=False,
                error_code="NO_MATCH",
                message=f"No enabled agent found declaring capability '{req_cap}' (task_type='{task_type}').",
            )

        # 2. Exactly one match
        if len(candidates) == 1:
            return RoutingResult(
                success=True,
                agent=candidates[0][0],
                capability=candidates[0][1],
                message="Single matching agent resolved.",
                candidates=candidates,
            )

        # 3. Multiple candidates: Deterministic Selection or Ambiguity Error
        # Sort key:
        # a. Priority ascending (lower priority number = higher precedence, e.g. 10 before 100)
        # b. Version descending (higher version preferred)
        # c. Agent ID ascending (alphabetical tie-breaker for strict reproducibility)
        sorted_candidates = sorted(
            candidates,
            key=lambda pair: (
                pair[0].priority,
                tuple(-x for x in _parse_version(pair[0].version)),
                pair[0].agent_id,
            ),
        )

        # If strict ambiguity check is enabled, check if top two candidates have identical precedence
        if strict_ambiguity and len(sorted_candidates) > 1:
            first, second = sorted_candidates[0][0], sorted_candidates[1][0]
            if (first.priority, _parse_version(first.version)) == (second.priority, _parse_version(second.version)):
                return RoutingResult(
                    success=False,
                    error_code="AMBIGUOUS_MATCH",
                    message=(
                        f"Ambiguous capability match: multiple agents { [c[0].agent_id for c in candidates] } "
                        f"match capability '{req_cap}' with identical precedence."
                    ),
                    candidates=candidates,
                )

        selected = sorted_candidates[0]
        return RoutingResult(
            success=True,
            agent=selected[0],
            capability=selected[1],
            message=f"Deterministically selected '{selected[0].agent_id}' from {len(candidates)} candidates.",
            candidates=candidates,
        )
