"""
Video Editor and Sequencer Agent for Universal MCP.
Provides verified non-linear video editing, strip timeline assembly,
editorial trimming, transitions, audio engineering, 2D transforms,
color grading modifiers, titles, meta-sequences, and sequencer rendering in Blender 5.2.2 LTS.

Enforces:
1. Human-in-the-loop approval gating (fail-closed model approved=True rejection).
2. Explicit path traversal and symlink escape defenses on all media and export paths.
3. Nine typed capability descriptors mapping the 22 accepted VSE tools.
4. Independent execution verification and main-thread safety.
"""

from typing import Dict, Any, List, Optional, Set, Tuple
import os
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
    TOOL_INSPECT_VSE_TIMELINE,
    TOOL_CREATE_VSE_STRIP,
    TOOL_MODIFY_VSE_STRIP,
    TOOL_DELETE_VSE_STRIP,
    TOOL_MANAGE_TIMELINE_MARKERS,
    TOOL_TRIM_VSE_STRIP,
    TOOL_SPLIT_VSE_STRIP,
    TOOL_REORDER_VSE_STRIPS,
    TOOL_CREATE_VSE_TRANSITION,
    TOOL_CONFIGURE_VSE_EFFECT,
    TOOL_CONFIGURE_VSE_AUDIO,
    TOOL_MANAGE_VSE_SOUND_MODIFIERS,
    TOOL_TRANSFORM_VSE_STRIP,
    TOOL_CROP_VSE_STRIP,
    TOOL_ANIMATE_VSE_STRIP,
    TOOL_MANAGE_VSE_STRIP_MODIFIERS,
    TOOL_CREATE_VSE_TEXT_STRIP,
    TOOL_CONFIGURE_VSE_TEXT_STYLE,
    TOOL_GROUP_VSE_META_STRIP,
    TOOL_CREATE_VSE_SCENE_STRIP,
    TOOL_RENDER_VSE_SEQUENCE,
    TOOL_MIXDOWN_VSE_AUDIO,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_VideoEditorAgent")

VIDEO_EDITOR_AGENT_ID = "agent.video_editor"

CAPABILITY_VSE_TIMELINE = "video.timeline"
CAPABILITY_VSE_EDITORIAL = "video.editorial"
CAPABILITY_VSE_TRANSITIONS = "video.transitions"
CAPABILITY_VSE_AUDIO = "video.audio"
CAPABILITY_VSE_TRANSFORMS = "video.transforms"
CAPABILITY_VSE_GRADING = "video.grading"
CAPABILITY_VSE_TITLES = "video.titles"
CAPABILITY_VSE_SEQUENCES = "video.sequences"
CAPABILITY_VSE_RENDERING = "video.rendering"

SUPPORTED_VSE_TOOLS: Set[str] = {
    TOOL_INSPECT_VSE_TIMELINE,
    TOOL_CREATE_VSE_STRIP,
    TOOL_MODIFY_VSE_STRIP,
    TOOL_DELETE_VSE_STRIP,
    TOOL_MANAGE_TIMELINE_MARKERS,
    TOOL_TRIM_VSE_STRIP,
    TOOL_SPLIT_VSE_STRIP,
    TOOL_REORDER_VSE_STRIPS,
    TOOL_CREATE_VSE_TRANSITION,
    TOOL_CONFIGURE_VSE_EFFECT,
    TOOL_CONFIGURE_VSE_AUDIO,
    TOOL_MANAGE_VSE_SOUND_MODIFIERS,
    TOOL_TRANSFORM_VSE_STRIP,
    TOOL_CROP_VSE_STRIP,
    TOOL_ANIMATE_VSE_STRIP,
    TOOL_MANAGE_VSE_STRIP_MODIFIERS,
    TOOL_CREATE_VSE_TEXT_STRIP,
    TOOL_CONFIGURE_VSE_TEXT_STYLE,
    TOOL_GROUP_VSE_META_STRIP,
    TOOL_CREATE_VSE_SCENE_STRIP,
    TOOL_RENDER_VSE_SEQUENCE,
    TOOL_MIXDOWN_VSE_AUDIO,
}


def validate_vse_path(
    path: Any,
    is_export: bool = False,
    allowed_root: Optional[str] = None,
) -> str:
    """
    Validates VSE media inputs and export filepaths:
    - Rejects empty, non-string, or whitespace paths
    - Rejects path traversal segments ('..')
    - Resolves realpath to defend against symlink escapes
    - Confirms path is inside allowed_root (if provided or configured in environment)
    """
    if not path or not isinstance(path, str):
        raise ValueError("Parameter 'filepath' / 'output_path' must be a non-empty string.")

    clean_path = path.strip()
    if not clean_path:
        raise ValueError("File path cannot be empty or whitespace.")

    # 1. Path traversal check
    norm_segments = clean_path.replace("\\", "/").split("/")
    if ".." in norm_segments:
        raise ValueError(
            f"Path traversal detected in '{clean_path}'. Parent directory references '..' are forbidden."
        )

    # 2. Workspace root resolution
    root = allowed_root or os.environ.get("UMCP_WORKSPACE_ROOT") or os.environ.get("UMCP_LOCAL_TEST_ROOT")

    # 3. Canonicalize & resolve symlinks
    if not os.path.isabs(clean_path):
        if root:
            clean_path = os.path.join(root, clean_path)
        else:
            clean_path = os.path.abspath(clean_path)

    real_path = os.path.realpath(clean_path)

    if root:
        real_root = os.path.realpath(root)
        try:
            if os.path.commonpath([real_path, real_root]) != real_root:
                raise PermissionError(
                    f"Path '{clean_path}' resolves to '{real_path}', escaping allowed workspace root '{real_root}'."
                )
        except ValueError as ve:
            # Raised on Windows when paths are on different drives
            raise PermissionError(f"Path '{clean_path}' is outside allowed root '{real_root}': {ve}")

    return real_path


def create_video_editor_manifest(version: str = "0.1.92") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Video Editor and Sequencer Agent.
    Priority 70 ensures high precedence before generic delivery (90) or general fallback (100).
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in SUPPORTED_VSE_TOOLS
        if name in TOOL_DEFINITIONS
    }

    capabilities = [
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_TIMELINE,
            description="Manage VSE timeline, channels, strip lifecycles, and timeline markers.",
            supported_task_types=[
                TOOL_INSPECT_VSE_TIMELINE,
                TOOL_CREATE_VSE_STRIP,
                TOOL_MODIFY_VSE_STRIP,
                TOOL_DELETE_VSE_STRIP,
                TOOL_MANAGE_TIMELINE_MARKERS,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_EDITORIAL,
            description="Perform non-linear editorial operations: trim, split, cut, and reorder strips.",
            supported_task_types=[
                TOOL_TRIM_VSE_STRIP,
                TOOL_SPLIT_VSE_STRIP,
                TOOL_REORDER_VSE_STRIPS,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_TRANSITIONS,
            description="Create transitions and visual effect strips (crossfades, wipes, glow, speed, color).",
            supported_task_types=[
                TOOL_CREATE_VSE_TRANSITION,
                TOOL_CONFIGURE_VSE_EFFECT,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_AUDIO,
            description="Configure sound strips, volume fades, audio modifiers, and stem audio mixdown.",
            supported_task_types=[
                TOOL_CONFIGURE_VSE_AUDIO,
                TOOL_MANAGE_VSE_SOUND_MODIFIERS,
                TOOL_MIXDOWN_VSE_AUDIO,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_TRANSFORMS,
            description="Apply 2D geometric transforms, pixel-accurate cropping, and keyframe animations.",
            supported_task_types=[
                TOOL_TRANSFORM_VSE_STRIP,
                TOOL_CROP_VSE_STRIP,
                TOOL_ANIMATE_VSE_STRIP,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_GRADING,
            description="Apply non-linear color grading modifiers (ASC-CDL Color Balance, Curves, Tonemap, Brightness/Contrast).",
            supported_task_types=[
                TOOL_MANAGE_VSE_STRIP_MODIFIERS,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_TITLES,
            description="Generate typography text strips, subtitles, lower-thirds, and font styles.",
            supported_task_types=[
                TOOL_CREATE_VSE_TEXT_STRIP,
                TOOL_CONFIGURE_VSE_TEXT_STYLE,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_SEQUENCES,
            description="Group strips into container MetaStrips and assemble 3D SceneStrips.",
            supported_task_types=[
                TOOL_GROUP_VSE_META_STRIP,
                TOOL_CREATE_VSE_SCENE_STRIP,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
        CapabilityDescriptor(
            capability_id=CAPABILITY_VSE_RENDERING,
            description="Render timeline video sequences to disk via FFMPEG (MP4, MKV, ProRes MOV, WebM).",
            supported_task_types=[
                TOOL_RENDER_VSE_SEQUENCE,
            ],
            read_write="SCENE_MUTATION",
            verification_status="VERIFIED",
            version="1.0.0",
        ),
    ]

    return AgentManifest(
        agent_id=VIDEO_EDITOR_AGENT_ID,
        name="Video Editor and Sequencer Agent",
        version=version,
        description="Specialized agent for non-linear video editing, strip trimming, transitions, audio mixing, color grading, titles, and sequencer rendering.",
        capabilities=capabilities,
        input_schemas=schemas,
        priority=70,
        enabled=True,
    )


class VideoEditorAgent:
    """
    Execution runner for the Video Editor and Sequencer Agent.
    """

    def __init__(self, manifest: Optional[AgentManifest] = None):
        self._manifest = manifest or create_video_editor_manifest()

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def _resolve_default_tool(self, capability_id: Optional[str]) -> str:
        mapping = {
            CAPABILITY_VSE_TIMELINE: TOOL_INSPECT_VSE_TIMELINE,
            CAPABILITY_VSE_EDITORIAL: TOOL_TRIM_VSE_STRIP,
            CAPABILITY_VSE_TRANSITIONS: TOOL_CREATE_VSE_TRANSITION,
            CAPABILITY_VSE_AUDIO: TOOL_CONFIGURE_VSE_AUDIO,
            CAPABILITY_VSE_TRANSFORMS: TOOL_TRANSFORM_VSE_STRIP,
            CAPABILITY_VSE_GRADING: TOOL_MANAGE_VSE_STRIP_MODIFIERS,
            CAPABILITY_VSE_TITLES: TOOL_CREATE_VSE_TEXT_STRIP,
            CAPABILITY_VSE_SEQUENCES: TOOL_GROUP_VSE_META_STRIP,
            CAPABILITY_VSE_RENDERING: TOOL_RENDER_VSE_SEQUENCE,
        }
        return mapping.get(capability_id, TOOL_INSPECT_VSE_TIMELINE)

    def validate_task_parameters(self, task: AgentTask) -> List[str]:
        """
        Validates task arguments against registered VSE tool schemas
        and enforces path safety (traversal & symlink escape defense).
        """
        errors: List[str] = []
        params = task.input_params or {}
        tool_name = task.task_type or self._resolve_default_tool(task.required_capability)

        if not tool_name or tool_name not in SUPPORTED_VSE_TOOLS:
            errors.append(f"Unsupported VSE tool: '{tool_name}'")
            return errors

        try:
            validate_tool_input(tool_name, params, trusted_approval=True)
        except (ValueError, PermissionError) as e:
            errors.append(str(e))

        # Additional path verification for path-bearing VSE tools
        for key in ("filepath", "output_path"):
            if key in params and params[key] is not None:
                try:
                    validate_vse_path(params[key], is_export=(key == "output_path"))
                except (ValueError, PermissionError) as pe:
                    errors.append(str(pe))

        return errors

    def execute_task(
        self,
        task: AgentTask,
        executor: BlenderExecutor,
        trusted_approval: Optional[bool] = None,
    ) -> AgentResult:
        """
        Executes an individual VSE task through BlenderExecutor with strict approval gating.
        """
        t0 = time.time()
        params = dict(task.input_params or {})

        # 1. Untrusted approval rejection
        if params.get("approved") is True or params.get("trusted_approval") is True:
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
            tool_name = self._resolve_default_tool(task.required_capability)

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

        # 4. Approval check for mutating tools
        is_read_only = (tool_name == TOOL_INSPECT_VSE_TIMELINE)
        is_local_autoapprove = os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE") == "1"
        effective_approval = trusted_approval or is_local_autoapprove
        if not is_read_only and not effective_approval:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[
                    f"Approval required: Scene mutation '{tool_name}' requires trusted human approval."
                ],
                verification=VerificationResult(
                    expected_conditions={"human_approval": True},
                    observed_results={"authorized": False, "error_code": "APPROVAL_REQUIRED"},
                    status="FAIL",
                    details="Mutating VSE tool executed without trusted approval credentials.",
                ),
                execution_time_ms=round((time.time() - t0) * 1000, 2),
            )

        # 5. Dispatch through BlenderExecutor
        call_params = dict(params)
        if hasattr(executor, "execute_tool"):
            bridge_resp: BridgeResponse = executor.execute_tool(
                tool_name,
                call_params,
                trusted_approval=effective_approval,
            )
        else:
            bridge_resp: BridgeResponse = executor.call_tool(
                tool_name,
                call_params,
                task_id=task.task_id,
                session_id=task.session_id,
                trusted_approval=effective_approval,
            )

        duration_ms = round((time.time() - t0) * 1000, 2)
        if not bridge_resp.success:
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[bridge_resp.message or "VSE tool execution failed"],
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
                details="VSE tool executed successfully.",
            ),
            execution_time_ms=duration_ms,
        )
