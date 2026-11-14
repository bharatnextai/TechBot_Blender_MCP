"""
Interchange & Delivery Agent for Universal MCP.
Provides verified 3D asset export and import (glTF/GLB, USD/USDC/USDA, FBX, OBJ, STL, PLY, ABC),
cryptographic SHA-256 sidecar generation, and project management in Blender 5.2.2 LTS.

Enforces:
1. Human-in-the-loop approval gating (fail-closed model approved=True rejection).
2. Path traversal security checks (forbidden '..' segments).
3. Overwrite protection policies.
4. Transactional failure cleanup and independent round-trip readback.
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
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_EXPORT_SCENE,
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_IMPORT_SCENE,
    TOOL_OPEN_BLEND_FILE,
    TOOL_OPEN_PROJECT,
    TOOL_LOAD_BLEND_FILE,
    TOOL_SAVE_BLEND_FILE,
    TOOL_PURGE_ORPHANED_DATABLOCKS,
    TOOL_PURGE_ORPHANS,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_InterchangeDeliveryAgent")

INTERCHANGE_DELIVERY_AGENT_ID = "agent.interchange_delivery"

CAPABILITY_INTERCHANGE_ASSET_IO = "interchange.asset_io"
CAPABILITY_INTERCHANGE_PROJECT = "interchange.project"

SUPPORTED_INTERCHANGE_TOOLS: Set[str] = {
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_EXPORT_SCENE,
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_IMPORT_SCENE,
    TOOL_OPEN_BLEND_FILE,
    TOOL_OPEN_PROJECT,
    TOOL_LOAD_BLEND_FILE,
    TOOL_SAVE_BLEND_FILE,
    TOOL_PURGE_ORPHANED_DATABLOCKS,
    TOOL_PURGE_ORPHANS,
}


def create_interchange_delivery_manifest(version: str = "0.1.80") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Interchange & Delivery Agent.
    Priority 80 ensures higher precedence than generic fallback modeling agents.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in (
            TOOL_EXPORT_SCENE_ASSET,
            TOOL_IMPORT_SCENE_ASSET,
            TOOL_OPEN_BLEND_FILE,
            TOOL_SAVE_BLEND_FILE,
            TOOL_PURGE_ORPHANED_DATABLOCKS,
        )
        if name in TOOL_DEFINITIONS
    }

    capabilities = [
        CapabilityDescriptor(
            capability_id=CAPABILITY_INTERCHANGE_ASSET_IO,
            description="Export and import industry-standard 3D formats (glTF/GLB, USD/USDC, FBX, OBJ, STL, PLY, ABC) with checksums.",
            supported_task_types=[
                TOOL_EXPORT_SCENE_ASSET,
                TOOL_EXPORT_SCENE,
                TOOL_IMPORT_SCENE_ASSET,
                TOOL_IMPORT_SCENE,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_INTERCHANGE_PROJECT,
            description="Project level file operations (open, save blend files, purge unlinked datablocks).",
            supported_task_types=[
                TOOL_OPEN_BLEND_FILE,
                TOOL_OPEN_PROJECT,
                TOOL_LOAD_BLEND_FILE,
                TOOL_SAVE_BLEND_FILE,
                TOOL_PURGE_ORPHANED_DATABLOCKS,
                TOOL_PURGE_ORPHANS,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
    ]

    return AgentManifest(
        agent_id=INTERCHANGE_DELIVERY_AGENT_ID,
        name="Interchange and Delivery Agent",
        version=version,
        description="Specialized agent for 3D asset interchange, glTF/USD serialization, and release delivery.",
        capabilities=capabilities,
        input_schemas=schemas,
        priority=5,  # Precedence over generic modeling agent (100)
        enabled=True,
    )


class InterchangeDeliveryAgent:
    """
    Execution runner for the Interchange and Delivery Agent.
    """

    def __init__(self, manifest: Optional[AgentManifest] = None):
        self._manifest = manifest or create_interchange_delivery_manifest()

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
            if task.required_capability == CAPABILITY_INTERCHANGE_PROJECT:
                if "filepath" in params and "save" in str(task.task_id).lower():
                    tool_name = TOOL_SAVE_BLEND_FILE
                elif "confirm_discard_unsaved" in params or "open" in str(task.task_id).lower():
                    tool_name = TOOL_OPEN_BLEND_FILE
                else:
                    tool_name = TOOL_PURGE_ORPHANED_DATABLOCKS
            elif "import" in str(task.task_id).lower():
                tool_name = TOOL_IMPORT_SCENE_ASSET
            else:
                tool_name = TOOL_EXPORT_SCENE_ASSET

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
        is_success = (
            bridge_resp.is_success
            if isinstance(bridge_resp, BridgeResponse)
            else (bridge_resp.get("success", True) if isinstance(bridge_resp, dict) else bool(bridge_resp))
        )
        if not is_success:
            err_msg = (
                bridge_resp.message
                if isinstance(bridge_resp, BridgeResponse)
                else (bridge_resp.get("message") if isinstance(bridge_resp, dict) else str(bridge_resp))
            ) or "Interchange/Delivery tool execution failed"
            err_code = getattr(bridge_resp, "error_code", None) or (
                bridge_resp.get("error_code") if isinstance(bridge_resp, dict) else None
            )
            out_res = (
                bridge_resp.result
                if isinstance(bridge_resp, BridgeResponse)
                else (bridge_resp if isinstance(bridge_resp, dict) else {})
            )
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[err_msg],
                output=out_res,
                verification=VerificationResult(
                    expected_conditions={"execution_success": True},
                    observed_results={"error": err_msg, "error_code": err_code},
                    status="FAIL",
                    details=err_msg,
                ),
                execution_time_ms=duration_ms,
            )

        result_data = (
            bridge_resp.result
            if isinstance(bridge_resp, BridgeResponse)
            else (bridge_resp if isinstance(bridge_resp, dict) else {})
        ) or {}
        return AgentResult(
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            output=result_data,
            evidence_references=[f"tool://{tool_name}?task_id={task.task_id}"],
            verification=VerificationResult(
                expected_conditions={"execution_success": True},
                observed_results={"success": True, "data": result_data},
                status="PASS",
                details="Interchange/Delivery tool executed successfully.",
            ),
            execution_time_ms=duration_ms,
        )
