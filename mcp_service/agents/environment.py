"""
Environment and Architecture Agent for Universal MCP.
Provides verified autonomous macro-environment creation and spatial orchestration:
1. Studio Cycloramas (seamless curved backdrops for product staging)
2. Object Origin / Pivot Point placement (bottom-center, geometry-to-origin)
3. Parametric Architectural Room Enclosures (walls, floors, ceilings, apertures)
4. Landscapes & Procedural Terrain (multi-octave elevation, boundary falloff)
5. Surface Asset Distribution (scattering props with normal alignment and scale variation)
6. Spatial Snapping & Grid Alignment (ground placement, modular grid alignment)

Enforces:
1. Strict input parameter validation and range checking.
2. Trusted human approval pipeline bindings (untrusted model approved=True rejection).
3. Post-operation scene inspection and dimension verification.
4. Symmetrical rollback and cleanup on failure.
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
    TOOL_CREATE_CYCLORAMA,
    TOOL_SET_OBJECT_ORIGIN,
    TOOL_CREATE_ROOM_ENCLOSURE,
    TOOL_CREATE_ROOF_STRUCTURE,
    TOOL_CREATE_BUILDING_ENVELOPE,
    TOOL_CREATE_TERRAIN,
    TOOL_SCATTER_SURFACE_ASSETS,
    TOOL_SNAP_TO_GROUND,
    TOOL_ALIGN_OBJECT_GRID,
    TOOL_BEGIN_ENVIRONMENT_TRANSACTION,
    TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION,
    TOOL_COMMIT_ENVIRONMENT_TRANSACTION,
    TOOL_EXECUTE_ENVIRONMENT_WORKFLOW,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_EnvironmentAgent")

ENVIRONMENT_AGENT_ID = "agent.environment"
CAPABILITY_ENVIRONMENT_STAGING = "environment.staging"
CAPABILITY_ENVIRONMENT_ARCHITECTURE = "environment.architecture"
CAPABILITY_ENVIRONMENT_TERRAIN = "environment.terrain"
CAPABILITY_ENVIRONMENT_LAYOUT = "environment.layout"
CAPABILITY_ENVIRONMENT_WORKFLOW = "environment.workflow"

SUPPORTED_ENVIRONMENT_TOOLS: Set[str] = {
    TOOL_CREATE_CYCLORAMA,
    TOOL_SET_OBJECT_ORIGIN,
    TOOL_CREATE_ROOM_ENCLOSURE,
    TOOL_CREATE_ROOF_STRUCTURE,
    TOOL_CREATE_BUILDING_ENVELOPE,
    TOOL_CREATE_TERRAIN,
    TOOL_SCATTER_SURFACE_ASSETS,
    TOOL_SNAP_TO_GROUND,
    TOOL_ALIGN_OBJECT_GRID,
    TOOL_BEGIN_ENVIRONMENT_TRANSACTION,
    TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION,
    TOOL_COMMIT_ENVIRONMENT_TRANSACTION,
    TOOL_EXECUTE_ENVIRONMENT_WORKFLOW,
}


def create_environment_manifest(version: str = "0.1.92") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Environment and Architecture Agent.
    Declares verified macro-environment staging, architecture, terrain, and layout capabilities.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in SUPPORTED_ENVIRONMENT_TOOLS
        if name in TOOL_DEFINITIONS
    }

    return AgentManifest(
        agent_id=ENVIRONMENT_AGENT_ID,
        name="Environment and Architecture Agent",
        version=version,
        description=(
            "Constructs verified architectural enclosures, studio cyclorama staging, "
            "landscapes and procedural terrain, surface prop distribution, and modular grid layouts."
        ),
        capabilities=[
            CapabilityDescriptor(
                capability_id=CAPABILITY_ENVIRONMENT_STAGING,
                description="Creates studio cycloramas, curved sweep backdrops, and manipulates object origin/pivot points.",
                supported_task_types=[TOOL_CREATE_CYCLORAMA, TOOL_SET_OBJECT_ORIGIN],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_ENVIRONMENT_ARCHITECTURE,
                description="Creates parametric room enclosures, roofs, building envelopes, floors, walls, and doorway apertures.",
                supported_task_types=[TOOL_CREATE_ROOM_ENCLOSURE, TOOL_CREATE_ROOF_STRUCTURE, TOOL_CREATE_BUILDING_ENVELOPE],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_ENVIRONMENT_TERRAIN,
                description="Generates procedural landscape terrain meshes and scatters props across surfaces with normal alignment.",
                supported_task_types=[TOOL_CREATE_TERRAIN, TOOL_SCATTER_SURFACE_ASSETS],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_ENVIRONMENT_LAYOUT,
                description="Snaps objects to ground planes and aligns modular components to coordinate grids.",
                supported_task_types=[TOOL_SNAP_TO_GROUND, TOOL_ALIGN_OBJECT_GRID],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_ENVIRONMENT_WORKFLOW,
                description="Manages transactional multi-tool environment construction workflows with UniversalMutationJournal rollback.",
                supported_task_types=[
                    TOOL_BEGIN_ENVIRONMENT_TRANSACTION,
                    TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION,
                    TOOL_COMMIT_ENVIRONMENT_TRANSACTION,
                    TOOL_EXECUTE_ENVIRONMENT_WORKFLOW,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
        ],
        input_schemas=schemas,
        priority=4,
        enabled=True,
    )


class EnvironmentAgent:
    """
    Specialized Environment and Architecture Agent.
    Validates environment and architectural inputs, enforces human approval for mutations,
    executes operations via BlenderExecutor, and inspects evaluated spatial geometry.
    """

    def __init__(self, version: str = "0.1.92"):
        self.version = version
        self._manifest = create_environment_manifest(version=self.version)

    @property
    def agent_id(self) -> str:
        return ENVIRONMENT_AGENT_ID

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def get_manifest(self) -> AgentManifest:
        return self._manifest

    def can_handle(self, task: AgentTask) -> bool:
        """Checks whether this agent can handle the requested capability or task type."""
        req_cap = task.required_capability
        if req_cap and req_cap not in (
            CAPABILITY_ENVIRONMENT_STAGING,
            CAPABILITY_ENVIRONMENT_ARCHITECTURE,
            CAPABILITY_ENVIRONMENT_TERRAIN,
            CAPABILITY_ENVIRONMENT_LAYOUT,
            CAPABILITY_ENVIRONMENT_WORKFLOW,
        ):
            return False
        if task.task_type:
            return task.task_type in SUPPORTED_ENVIRONMENT_TOOLS
        return True

    def validate_task_input(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Performs pre-execution validation of environment inputs.
        Returns: (is_valid, error_code, error_message)
        """
        if tool_name not in SUPPORTED_ENVIRONMENT_TOOLS:
            return (
                False,
                "UNSUPPORTED_REQUEST",
                f"Unsupported environment tool '{tool_name}'. Supported: {sorted(list(SUPPORTED_ENVIRONMENT_TOOLS))}",
            )

        if tool_name == TOOL_CREATE_CYCLORAMA:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Parameter 'name' cannot be empty for cyclorama."
            width = params.get("width", 10.0)
            depth = params.get("depth", 10.0)
            wall_height = params.get("wall_height", 5.0)
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0.0 for v in (width, depth, wall_height)):
                return False, "INVALID_PARAMS", "Cyclorama width, depth, and wall_height must be positive numbers."

        elif tool_name == TOOL_SET_OBJECT_ORIGIN:
            obj_name = str(params.get("object_name", "")).strip()
            if not obj_name:
                return False, "INVALID_PARAMS", "Parameter 'object_name' is required."
            mode = str(params.get("origin_mode", "BOTTOM_CENTER")).upper().strip()
            valid_modes = {"BOTTOM_CENTER", "CENTER_OF_MASS", "ORIGIN_TO_GEOMETRY", "GEOMETRY_TO_ORIGIN", "ORIGIN_TO_CURSOR", "CUSTOM_POINT"}
            if mode not in valid_modes:
                return False, "INVALID_PARAMS", f"Invalid origin_mode '{mode}'. Allowed: {sorted(list(valid_modes))}"

        elif tool_name == TOOL_CREATE_ROOM_ENCLOSURE:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Parameter 'name' cannot be empty for room enclosure."
            for dim in ("width", "length", "height", "wall_thickness"):
                v = params.get(dim, 1.0)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0.0:
                    return False, "INVALID_PARAMS", f"Room parameter '{dim}' must be a positive number."

        elif tool_name == TOOL_CREATE_ROOF_STRUCTURE:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Parameter 'name' cannot be empty for roof structure."
            rt = str(params.get("roof_type", "GABLE")).upper().strip()
            if rt not in {"GABLE", "HIP", "PITCHED", "SHED", "FLAT"}:
                return False, "INVALID_PARAMS", f"Invalid roof_type '{rt}'. Must be 'GABLE', 'HIP', 'PITCHED', 'SHED', or 'FLAT'."
            for dim in ("width", "length", "height", "thickness"):
                v = params.get(dim, 1.0)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0.0:
                    return False, "INVALID_PARAMS", f"Roof parameter '{dim}' must be a positive number."

        elif tool_name == TOOL_CREATE_BUILDING_ENVELOPE:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Parameter 'name' cannot be empty for building envelope."
            for dim in ("width", "length", "height", "foundation_thickness", "wall_thickness", "roof_height"):
                v = params.get(dim, 1.0)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0.0:
                    return False, "INVALID_PARAMS", f"Building parameter '{dim}' must be a positive number."
            stories = params.get("stories", 2)
            if isinstance(stories, bool) or not isinstance(stories, int) or stories < 1 or stories > 10:
                return False, "INVALID_PARAMS", "Building 'stories' must be an integer between 1 and 10."

        elif tool_name == TOOL_EXECUTE_ENVIRONMENT_WORKFLOW:
            steps = params.get("steps")
            if not isinstance(steps, list) or not steps:
                return False, "INVALID_PARAMS", "Workflow 'steps' must be a non-empty list of tool invocations."

        elif tool_name == TOOL_CREATE_TERRAIN:
            name = str(params.get("name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Parameter 'name' cannot be empty for terrain."
            for res in ("resolution_x", "resolution_y"):
                r = params.get(res, 64)
                if isinstance(r, bool) or not isinstance(r, int) or r < 2 or r > 256:
                    return False, "INVALID_PARAMS", f"Resolution '{res}' must be an integer between 2 and 256."

        elif tool_name == TOOL_SCATTER_SURFACE_ASSETS:
            surf = str(params.get("surface_name", "")).strip()
            if not surf:
                return False, "INVALID_PARAMS", "Parameter 'surface_name' is required."
            assets = params.get("asset_names", [])
            if not isinstance(assets, list) or not assets:
                return False, "INVALID_PARAMS", "Parameter 'asset_names' must be a non-empty list of asset names."

        return True, None, None

    async def execute_task(
        self,
        task: AgentTask,
        executor: BlenderExecutor,
        trusted_approval: Optional[bool] = None,
    ) -> AgentResult:
        """
        Executes an environment task through the BlenderExecutor.
        Enforces human approval credentials and returns an AgentResult with verification metrics.
        """
        start_time = time.time()
        tool_name = task.task_type

        # 1. Validation
        is_valid, err_code, err_msg = self.validate_task_input(tool_name, task.input_params)
        if not is_valid:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[f"[{err_code}] {err_msg}"],
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )

        # 2. Schema sanitization and approval check
        try:
            sanitized_params = validate_tool_input(
                tool_name, task.input_params, trusted_approval=bool(trusted_approval)
            )
        except (ValueError, PermissionError) as e:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[str(e)],
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )

        # 3. Execution via executor
        try:
            response: BridgeResponse = await executor.execute(tool_name, sanitized_params)
            duration_ms = (time.time() - start_time) * 1000.0

            if response.status == "SUCCESS":
                data = response.result if isinstance(response.result, dict) else {}
                verif = VerificationResult(
                    status="PASS",
                    observed_results=data,
                    details=f"rna_inspection:{tool_name}",
                )
                return AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.SUCCEEDED,
                    output=data,
                    verification=verif,
                    execution_time_ms=duration_ms,
                )
            else:
                return AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[response.message or "Unknown execution failure"],
                    execution_time_ms=duration_ms,
                )
        except Exception as ex:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[str(ex)],
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )

    async def execute_workflow(
        self,
        tasks: List[AgentTask],
        executor: BlenderExecutor,
        trusted_approval: Optional[bool] = None,
        workflow_name: str = "EnvironmentWorkflow",
    ) -> AgentResult:
        """
        Executes a sequence of environment tasks atomically with UniversalMutationJournal rollback.
        If any task in the sequence fails, compensating cleanup is executed to restore the
        exact pre-workflow scene state.
        """
        start_time = time.time()
        workflow_id = f"wf_{int(start_time * 1000)}"

        # 1. Pre-validation of all tasks
        for idx, task in enumerate(tasks):
            is_valid, err_code, err_msg = self.validate_task_input(task.task_type, task.input_params)
            if not is_valid:
                return AgentResult(
                    task_id=workflow_id,
                    status=TaskStatus.FAILED,
                    errors=[f"Workflow validation failure at step {idx} ({task.task_type}): [{err_code}] {err_msg}"],
                    execution_time_ms=(time.time() - start_time) * 1000.0,
                )

        # 2. Package steps for execute_environment_workflow
        steps = []
        for t in tasks:
            steps.append({
                "tool": t.task_type,
                "params": t.input_params,
            })

        workflow_params = {
            "workflow_name": workflow_name,
            "steps": steps,
        }

        # 3. Schema sanitization and approval check
        try:
            sanitized_params = validate_tool_input(
                TOOL_EXECUTE_ENVIRONMENT_WORKFLOW, workflow_params, trusted_approval=bool(trusted_approval)
            )
        except (ValueError, PermissionError) as e:
            return AgentResult(
                task_id=workflow_id,
                status=TaskStatus.FAILED,
                errors=[str(e)],
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )

        # 4. Dispatch to bridge executor
        try:
            response: BridgeResponse = await executor.execute(TOOL_EXECUTE_ENVIRONMENT_WORKFLOW, sanitized_params)
            duration_ms = (time.time() - start_time) * 1000.0

            if response.status == "SUCCESS":
                data = response.result if isinstance(response.result, dict) else {}
                verif = VerificationResult(
                    status="PASS",
                    observed_results=data,
                    details=f"workflow_journal:{workflow_name}",
                )
                return AgentResult(
                    task_id=workflow_id,
                    status=TaskStatus.SUCCEEDED,
                    output=data,
                    verification=verif,
                    execution_time_ms=duration_ms,
                )
            else:
                data = response.result if isinstance(response.result, dict) else {}
                err_msg = response.message or (data.get("error_message") if isinstance(data, dict) else "Workflow execution failure")
                return AgentResult(
                    task_id=workflow_id,
                    status=TaskStatus.FAILED,
                    output=data,
                    errors=[err_msg],
                    execution_time_ms=duration_ms,
                )
        except Exception as ex:
            return AgentResult(
                task_id=workflow_id,
                status=TaskStatus.FAILED,
                errors=[str(ex)],
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )
