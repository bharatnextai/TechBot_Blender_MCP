"""
Simulation & VFX Agent for Universal MCP.
Provides verified rigid body dynamics, collision surfaces, cloth simulation modifiers,
and deterministic point cache baking in Blender 5.2.2 LTS.

Enforces:
1. Human-in-the-loop approval gating (fail-closed model approved=True rejection).
2. Optimistic concurrency snapshot tracking (expected_snapshot_id).
3. Parameter bounds (mass > 0, frame ranges <= 250 frames, timeout guards).
4. Transactional rollback and point cache verification.
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
    TOOL_CONFIGURE_PHYSICS,
    TOOL_SETUP_PHYSICS,
    TOOL_MANAGE_PHYSICS,
    TOOL_INSPECT_PHYSICS,
    TOOL_BAKE_PHYSICS_SIMULATION,
    TOOL_CONFIGURE_FORCE_FIELD,
    TOOL_INSPECT_FORCE_FIELD,
    TOOL_CONFIGURE_PARTICLE_SYSTEM,
    TOOL_INSPECT_PARTICLE_SYSTEM,
    TOOL_CONFIGURE_FLUID_SIMULATION,
    TOOL_INSPECT_FLUID_SIMULATION,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_SimulationVFXAgent")

SIMULATION_VFX_AGENT_ID = "agent.simulation_vfx"

CAPABILITY_PHYSICS_SIMULATION = "physics.simulation"
CAPABILITY_PHYSICS_INSPECT = "physics.inspection"

SUPPORTED_SIMULATION_TOOLS: Set[str] = {
    TOOL_CONFIGURE_PHYSICS,
    TOOL_SETUP_PHYSICS,
    TOOL_MANAGE_PHYSICS,
    TOOL_INSPECT_PHYSICS,
    TOOL_BAKE_PHYSICS_SIMULATION,
    TOOL_CONFIGURE_FORCE_FIELD,
    TOOL_INSPECT_FORCE_FIELD,
    TOOL_CONFIGURE_PARTICLE_SYSTEM,
    TOOL_INSPECT_PARTICLE_SYSTEM,
    TOOL_CONFIGURE_FLUID_SIMULATION,
    TOOL_INSPECT_FLUID_SIMULATION,
}


def create_simulation_vfx_manifest(version: str = "0.1.80") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Simulation & VFX Agent.
    Priority 80 ensures higher precedence than generic fallback modeling agents.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in (
            TOOL_CONFIGURE_PHYSICS,
            TOOL_INSPECT_PHYSICS,
            TOOL_BAKE_PHYSICS_SIMULATION,
            TOOL_CONFIGURE_FORCE_FIELD,
            TOOL_INSPECT_FORCE_FIELD,
            TOOL_CONFIGURE_PARTICLE_SYSTEM,
            TOOL_INSPECT_PARTICLE_SYSTEM,
            TOOL_CONFIGURE_FLUID_SIMULATION,
            TOOL_INSPECT_FLUID_SIMULATION,
        )
        if name in TOOL_DEFINITIONS
    }

    capabilities = [
        CapabilityDescriptor(
            capability_id=CAPABILITY_PHYSICS_SIMULATION,
            description="Configure rigid body dynamics, collision surfaces, cloth simulation, force fields, and bake point caches.",
            supported_task_types=[
                TOOL_CONFIGURE_PHYSICS,
                TOOL_SETUP_PHYSICS,
                TOOL_MANAGE_PHYSICS,
                TOOL_BAKE_PHYSICS_SIMULATION,
                TOOL_CONFIGURE_FORCE_FIELD,
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                TOOL_CONFIGURE_FLUID_SIMULATION,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_PHYSICS_INSPECT,
            description="Inspect active rigid body worlds, physics modifiers, force fields, and simulation point cache states.",
            supported_task_types=[TOOL_INSPECT_PHYSICS, TOOL_INSPECT_FORCE_FIELD, TOOL_INSPECT_PARTICLE_SYSTEM, TOOL_INSPECT_FLUID_SIMULATION],
            read_write="READ_ONLY",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
    ]

    return AgentManifest(
        agent_id=SIMULATION_VFX_AGENT_ID,
        name="Simulation and VFX Agent",
        version=version,
        description="Specialized agent for rigid body dynamics, cloth simulations, collision surfaces, and cache baking.",
        capabilities=capabilities,
        input_schemas=schemas,
        priority=5,  # Precedence over generic modeling agent (100)
        enabled=True,
    )


class SimulationVFXAgent:
    """
    Execution runner for the Simulation and VFX Agent.
    """

    def __init__(self, manifest: Optional[AgentManifest] = None):
        self._manifest = manifest or create_simulation_vfx_manifest()

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def validate_task_parameters(self, task: AgentTask) -> List[str]:
        errors = []
        params = task.input_params or {}
        tool_name = task.task_type
        if tool_name and tool_name in TOOL_DEFINITIONS:
            try:
                validate_tool_input(tool_name, params, trusted_approval=True)
            except ValueError as e:
                errors.append(str(e))
        return errors

    def execute_task(
        self,
        task: AgentTask,
        executor: BlenderExecutor,
        trusted_approval: Optional[bool] = None,
    ) -> AgentResult:
        t0 = time.time()
        params = dict(task.input_params or {})

        # 1. Untrusted approval rejection
        if params.get("approved") is True:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[
                    "Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation."
                ],
                verification=VerificationResult(
                    expected_conditions={"scene_mutation": True, "human_approval": True},
                    observed_results={"success": False, "error_code": "PERMISSION_DENIED"},
                    status="FAIL",
                    details="Model-supplied approval flag rejected.",
                ),
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )

        # 2. Resolve tool name
        tool_name = task.task_type
        if not tool_name:
            if task.required_capability == CAPABILITY_PHYSICS_INSPECT:
                tool_name = TOOL_INSPECT_PHYSICS
            elif "frame_end" in params or "bake" in str(task.task_id).lower():
                tool_name = TOOL_BAKE_PHYSICS_SIMULATION
            else:
                tool_name = TOOL_CONFIGURE_PHYSICS

        # 3. Parameter validation
        val_errors = self.validate_task_parameters(task)
        if val_errors:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=val_errors,
                verification=VerificationResult(status="FAIL", details="; ".join(val_errors)),
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )

        # 4. Dispatch through BlenderExecutor
        call_params = dict(params)
        if hasattr(executor, "execute_tool"):
            bridge_resp: BridgeResponse = executor.execute_tool(
                tool_name,
                call_params,
                trusted_approval=trusted_approval,
            )
        else:
            bridge_resp: BridgeResponse = executor.call_tool(
                tool_name,
                call_params,
                task_id=task.task_id,
                session_id=task.session_id,
                trusted_approval=trusted_approval,
            )

        duration_ms = round((time.time() - t0) * 1000, 2)
        if not bridge_resp.is_success:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[bridge_resp.message or "Physics/Simulation tool execution failed"],
                output=bridge_resp.result,
                verification=VerificationResult(
                    expected_conditions={"execution_success": True},
                    observed_results={"error": bridge_resp.message, "error_code": getattr(bridge_resp, "error_code", None)},
                    status="FAIL",
                    details=bridge_resp.message,
                ),
                execution_time_ms=duration_ms,
            )

        result_data = bridge_resp.result or {}
        return AgentResult(
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            output=result_data,
            evidence_references=[f"tool://{tool_name}?task_id={task.task_id}"],
            verification=VerificationResult(
                expected_conditions={"execution_success": True},
                observed_results={"success": True, "data": result_data},
                status="PASS",
                details="Physics/Simulation tool executed successfully.",
            ),
            execution_time_ms=duration_ms,
        )
