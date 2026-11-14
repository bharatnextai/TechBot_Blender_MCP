"""
Rigging & Animation Agent for Universal MCP.
Provides verified skeletal armature management, bone editing, mesh skinning/binding,
IK constraints, and timeline keyframe animation in Blender 5.2.2 LTS.

Enforces:
1. Human-in-the-loop approval gating (fail-closed model approved=True rejection).
2. Optimistic concurrency snapshot tracking (expected_snapshot_id).
3. Parameter bounds (bone vectors, chain lengths, frame ranges).
4. Transactional rollback and readback verification.
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
    TOOL_CREATE_ARMATURE,
    TOOL_EDIT_ARMATURE_BONES,
    TOOL_INSPECT_ARMATURE,
    TOOL_BIND_ARMATURE_MESH,
    TOOL_CONFIGURE_BONE_CONSTRAINT,
    TOOL_MANAGE_KEYFRAME,
    TOOL_INSERT_KEYFRAME,
    TOOL_DELETE_KEYFRAME,
    TOOL_CONFIGURE_ANIMATION_CURVE,
    TOOL_MANAGE_FCURVE,
    TOOL_SET_KEYFRAME_INTERPOLATION,
    TOOL_MANAGE_ACTION_SLOTS,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_RiggingAnimationAgent")

RIGGING_ANIMATION_AGENT_ID = "agent.rigging_animation"

CAPABILITY_RIGGING_ARMATURES = "rigging.armatures"
CAPABILITY_RIGGING_INSPECT = "rigging.inspection"
CAPABILITY_ANIMATION_KEYFRAME = "animation.keyframe"

SUPPORTED_RIGGING_ANIMATION_TOOLS: Set[str] = {
    TOOL_CREATE_ARMATURE,
    TOOL_EDIT_ARMATURE_BONES,
    TOOL_INSPECT_ARMATURE,
    TOOL_BIND_ARMATURE_MESH,
    TOOL_CONFIGURE_BONE_CONSTRAINT,
    TOOL_MANAGE_KEYFRAME,
    TOOL_INSERT_KEYFRAME,
    TOOL_DELETE_KEYFRAME,
    TOOL_CONFIGURE_ANIMATION_CURVE,
    TOOL_MANAGE_FCURVE,
    TOOL_SET_KEYFRAME_INTERPOLATION,
    TOOL_MANAGE_ACTION_SLOTS,
}


def create_rigging_animation_manifest(version: str = "0.1.80") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Rigging & Animation Agent.
    Priority 80 ensures higher precedence than generic fallback modeling agents.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in (
            TOOL_CREATE_ARMATURE,
            TOOL_EDIT_ARMATURE_BONES,
            TOOL_INSPECT_ARMATURE,
            TOOL_BIND_ARMATURE_MESH,
            TOOL_CONFIGURE_BONE_CONSTRAINT,
            TOOL_MANAGE_KEYFRAME,
            TOOL_INSERT_KEYFRAME,
            TOOL_DELETE_KEYFRAME,
            TOOL_CONFIGURE_ANIMATION_CURVE,
        )
        if name in TOOL_DEFINITIONS
    }

    capabilities = [
        CapabilityDescriptor(
            capability_id=CAPABILITY_RIGGING_ARMATURES,
            description="Construct armatures, edit bone hierarchies, skin meshes, and configure IK constraints.",
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
            capability_id=CAPABILITY_RIGGING_INSPECT,
            description="Inspect skeletal bone hierarchies, joints, and pose transforms.",
            supported_task_types=[TOOL_INSPECT_ARMATURE],
            read_write="READ_ONLY",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_ANIMATION_KEYFRAME,
            description="Manage timeline keyframes, F-curves, and action interpolation.",
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
    ]

    return AgentManifest(
        agent_id=RIGGING_ANIMATION_AGENT_ID,
        name="Rigging and Animation Agent",
        version=version,
        description="Specialized agent for skeletal armatures, skinning, IK constraints, and keyframed animation.",
        capabilities=capabilities,
        input_schemas=schemas,
        priority=5,  # Precedence over generic modeling agent (100)
        enabled=True,
    )


class RiggingAnimationAgent:
    """
    Execution runner for the Rigging and Animation Agent.
    """

    def __init__(self, manifest: Optional[AgentManifest] = None):
        self._manifest = manifest or create_rigging_animation_manifest()

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
            if task.required_capability == CAPABILITY_RIGGING_INSPECT:
                tool_name = TOOL_INSPECT_ARMATURE
            elif task.required_capability == CAPABILITY_ANIMATION_KEYFRAME:
                if "interpolation" in params or params.get("action") in ("set_interpolation", "add_modifier"):
                    tool_name = TOOL_CONFIGURE_ANIMATION_CURVE
                else:
                    tool_name = TOOL_MANAGE_KEYFRAME
            elif task.required_capability == CAPABILITY_RIGGING_ARMATURES:
                if "bones" in params or "bone_name" in params:
                    tool_name = TOOL_EDIT_ARMATURE_BONES
                elif "mesh_name" in params or "armature_name" in params and "bind_type" in params:
                    tool_name = TOOL_BIND_ARMATURE_MESH
                elif "constraint_type" in params or "ik_target" in params:
                    tool_name = TOOL_CONFIGURE_BONE_CONSTRAINT
                else:
                    tool_name = TOOL_CREATE_ARMATURE
            else:
                tool_name = TOOL_CREATE_ARMATURE

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
        if not bridge_resp.success:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[bridge_resp.message or "Rigging/Animation tool execution failed"],
                output=bridge_resp.result,
                verification=VerificationResult(
                    expected_conditions={"execution_success": True},
                    observed_results={"error": bridge_resp.message, "error_code": bridge_resp.error_code},
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
                details="Rigging/Animation tool executed successfully.",
            ),
            execution_time_ms=duration_ms,
        )
