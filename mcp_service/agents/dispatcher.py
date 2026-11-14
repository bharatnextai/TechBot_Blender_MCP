"""
Agent Dispatcher for Universal MCP.
Connects the Agent Manager (Registry, Router, Planner) and Session Coordinator
to existing MCP and loopback bridge interfaces without bypassing approval, validation,
or the main-thread execution boundary.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set
import copy
import time
import uuid
import inspect
import logging
import os
import secrets

from shared.models.agent_contracts import (
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
    VerificationResult,
    TaskOutputRef,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import TOOL_CHECK_APPROVAL_STATUS, TOOL_GET_TASK_STATUS, TOOL_RESOLVE_PENDING_APPROVAL, validate_tool_input
from .manager import AgentManager
from .session_coordinator import SessionCoordinator, SessionContext
from .scene_inspector import SceneInspectorAgent, SCENE_INSPECTOR_AGENT_ID
from .modeling import ModelingAgent, MODELING_AGENT_ID
from .materials import MaterialsAgent, MATERIALS_AGENT_ID
from .render_lighting import RenderLightingAgent, RENDER_LIGHTING_AGENT_ID
from .rigging_animation import RiggingAnimationAgent, RIGGING_ANIMATION_AGENT_ID
from .simulation_vfx import SimulationVFXAgent, SIMULATION_VFX_AGENT_ID
from .interchange_delivery import InterchangeDeliveryAgent, INTERCHANGE_DELIVERY_AGENT_ID
from .compositor import CompositorAgent, COMPOSITOR_AGENT_ID
from .director import DirectorAgent, DIRECTOR_AGENT_ID
from .video_editor import VideoEditorAgent, VIDEO_EDITOR_AGENT_ID
from ..execution.blender_executor import BlenderExecutor
from ..security.approval import compute_param_hash, ApprovalDecision

logger = logging.getLogger("UniversalMCP_Dispatcher")


def _approval_kwargs(call, value):
    """Inspect compatibility before a call; never retry an executed TypeError."""
    try:
        parameters = inspect.signature(call).parameters
        accepts = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()) or (
            "trusted_approval" in parameters and parameters["trusted_approval"].kind in
            (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY))
    except (TypeError, ValueError):
        accepts = True
    return {"trusted_approval": value} if accepts else {}


class BindingResolutionError(Exception):
    """
    Raised when runtime reference resolution fails closed.
    Encapsulates specific error code, diagnostic message, and partial audit traces.
    """
    def __init__(self, code: str, message: str, partial_traces: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.code = code
        self.error_code = code
        self.message = message
        self.partial_traces = partial_traces or []


SENSITIVE_PARAM_KEYWORDS: Set[str] = {
    "token", "password", "secret", "auth", "credential", "key", "cert", "private"
}


def is_sensitive_key(key_or_path: str) -> bool:
    """Returns True if the parameter key or path contains sensitive credential keywords."""
    norm = str(key_or_path).lower()
    return any(kw in norm for kw in SENSITIVE_PARAM_KEYWORDS)


def redact_sensitive_values(val: Any) -> Any:
    """Recursively redacts values for any keys matching sensitive keywords in dictionaries or lists."""
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            if is_sensitive_key(k):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = redact_sensitive_values(v)
        return sanitized
    elif isinstance(val, (list, tuple)):
        sanitized_list = [redact_sensitive_values(item) for item in val]
        return tuple(sanitized_list) if isinstance(val, tuple) else sanitized_list
    return copy.deepcopy(val)


def contains_untrusted_approval_flag(node: Any) -> bool:
    """Recursively checks whether an untrusted approval flag ('approved' or 'trusted_approval') is True."""
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in ("approved", "trusted_approval") and v is True:
                return True
            if contains_untrusted_approval_flag(v):
                return True
    elif isinstance(node, (list, tuple)):
        for item in node:
            if contains_untrusted_approval_flag(item):
                return True
    return False


def resolve_path_in_output(output: Any, path: str, param_path: str, task_id: str, partial_traces: List[Dict[str, Any]]) -> Any:
    """
    Traverses dictionary keys and list indices along a dot-separated path in an output object.
    Fails closed on null traversal, missing fields, invalid indices, or out-of-bounds indices.
    """
    segments = path.split(".")
    curr = output
    for seg in segments:
        if curr is None:
            raise BindingResolutionError(
                "NULL_TRAVERSAL",
                f"Null traversal encountered at segment '{seg}' along path '{path}' for parameter '{param_path}' (source task '{task_id}').",
                partial_traces=partial_traces,
            )
        if isinstance(curr, dict):
            if seg not in curr:
                raise BindingResolutionError(
                    "FIELD_NOT_FOUND",
                    f"Field '{seg}' not found in output of task '{task_id}' along path '{path}' for parameter '{param_path}'.",
                    partial_traces=partial_traces,
                )
            curr = curr[seg]
        elif isinstance(curr, (list, tuple)):
            if not seg.isdigit():
                raise BindingResolutionError(
                    "INVALID_INDEX",
                    f"List traversal requires integer index, got '{seg}' along path '{path}' for parameter '{param_path}' (source task '{task_id}').",
                    partial_traces=partial_traces,
                )
            idx = int(seg)
            if idx < 0 or idx >= len(curr):
                raise BindingResolutionError(
                    "INDEX_OUT_OF_BOUNDS",
                    f"Index {idx} out of bounds for list of length {len(curr)} along path '{path}' for parameter '{param_path}' (source task '{task_id}').",
                    partial_traces=partial_traces,
                )
            curr = curr[idx]
        else:
            raise BindingResolutionError(
                "INVALID_TRAVERSAL",
                f"Cannot traverse segment '{seg}' on non-container type '{type(curr).__name__}' along path '{path}' for parameter '{param_path}' (source task '{task_id}').",
                partial_traces=partial_traces,
            )
    return curr


def check_expected_type(val: Any, expected_type: str, param_path: str, task_id: str, path: str, partial_traces: List[Dict[str, Any]]) -> None:
    """
    Strictly verifies that the resolved value matches the expected type contract.
    Guarantees bool is not treated as int/number.
    """
    expected_norm = str(expected_type).strip().lower()
    type_ok = False
    if expected_norm in ("string", "str"):
        type_ok = isinstance(val, str)
    elif expected_norm in ("integer", "int"):
        type_ok = isinstance(val, int) and not isinstance(val, bool)
    elif expected_norm in ("number", "float"):
        type_ok = isinstance(val, (int, float)) and not isinstance(val, bool)
    elif expected_norm in ("boolean", "bool"):
        type_ok = isinstance(val, bool)
    elif expected_norm in ("array", "list"):
        type_ok = isinstance(val, (list, tuple))
    elif expected_norm in ("object", "dict"):
        type_ok = isinstance(val, dict)
    else:
        type_ok = True

    if not type_ok:
        raise BindingResolutionError(
            "TYPE_MISMATCH",
            f"Type mismatch for parameter '{param_path}' referencing '{task_id}.{path}': "
            f"expected '{expected_type}', resolved type is '{type(val).__name__}'.",
            partial_traces=partial_traces,
        )


def resolve_task_references(
    task: AgentTask,
    plan: Optional[TaskPlan] = None,
    session_results: Optional[Dict[str, AgentResult]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Deterministically resolves canonical structured task output references in task.input_params
    against recorded upstream task execution results in session_results.

    Rules:
    1. Returns a newly resolved parameter dictionary. Never mutates task.input_params.
    2. Enforces that references target direct declared dependencies of the task.
    3. Requires the referenced task's latest status to be SUCCEEDED with non-null output.
    4. Evaluates dot-separated path traversal for dicts and list indices.
    5. Validates expected types against resolved runtime values.
    6. Produces sanitized binding trace entries auditing resolution outcomes while redacting secrets.
    7. Fails closed with BindingResolutionError if any reference cannot be resolved safely.
    """
    if not task.input_params or not isinstance(task.input_params, dict):
        return ({}, [])

    results_map = session_results or {}
    declared_deps = set(task.dependencies) if task.dependencies else set()
    traces: List[Dict[str, Any]] = []

    def _resolve_single_ref(ref: TaskOutputRef, breadcrumb: str) -> Any:
        try:
            ref.validate()
        except ValueError as ve:
            raise BindingResolutionError(
                "MALFORMED_REFERENCE",
                f"Malformed reference at '{breadcrumb}': {ve}",
                partial_traces=traces,
            )

        # 1. Dependency check
        if ref.task_id not in declared_deps:
            raise BindingResolutionError(
                "UNDECLARED_DEPENDENCY",
                f"Undeclared dependency: Task '{task.task_id}' parameter '{breadcrumb}' references "
                f"task '{ref.task_id}', which is not in declared dependencies: {sorted(declared_deps)}.",
                partial_traces=traces,
            )

        # 2. Status & Output check in session results
        if ref.task_id not in results_map:
            raise BindingResolutionError(
                "PREREQUISITE_NOT_SUCCEEDED",
                f"Prerequisite task '{ref.task_id}' referenced by '{breadcrumb}' has no recorded result in session.",
                partial_traces=traces,
            )

        source_res = results_map[ref.task_id]
        if source_res.status != TaskStatus.SUCCEEDED:
            st_str = source_res.status.value if isinstance(source_res.status, TaskStatus) else str(source_res.status)
            raise BindingResolutionError(
                "PREREQUISITE_NOT_SUCCEEDED",
                f"Prerequisite task '{ref.task_id}' referenced by '{breadcrumb}' did not succeed (status='{st_str}').",
                partial_traces=traces,
            )

        if source_res.output is None:
            raise BindingResolutionError(
                "DATA_UNAVAILABLE",
                f"Prerequisite task '{ref.task_id}' referenced by '{breadcrumb}' produced null output.",
                partial_traces=traces,
            )

        # 3. Path Traversal
        resolved_val = resolve_path_in_output(
            source_res.output,
            ref.path,
            param_path=breadcrumb,
            task_id=ref.task_id,
            partial_traces=traces,
        )

        # 4. Expected Type Check
        if ref.expected_type is not None:
            check_expected_type(
                resolved_val,
                ref.expected_type,
                param_path=breadcrumb,
                task_id=ref.task_id,
                path=ref.path,
                partial_traces=traces,
            )

        # 5. Redaction and audit trace recording
        is_redacted = is_sensitive_key(breadcrumb) or is_sensitive_key(ref.path)
        if is_redacted:
            trace_val = "[REDACTED]"
        else:
            trace_val = redact_sensitive_values(resolved_val)
            if trace_val != resolved_val:
                is_redacted = True

        traces.append({
            "param_path": breadcrumb,
            "source_task_id": ref.task_id,
            "source_path": ref.path,
            "expected_type": ref.expected_type,
            "resolved_type": type(resolved_val).__name__,
            "resolved_value": trace_val,
            "is_redacted": is_redacted,
            "status": "RESOLVED",
        })

        return copy.deepcopy(resolved_val)

    def _traverse_and_resolve(node: Any, breadcrumb: str) -> Any:
        if isinstance(node, TaskOutputRef):
            return _resolve_single_ref(node, breadcrumb)

        if isinstance(node, dict):
            if "$ref" in node:
                try:
                    ref = TaskOutputRef.from_dict(node)
                except ValueError as ve:
                    raise BindingResolutionError(
                        "MALFORMED_REFERENCE",
                        f"Malformed reference at '{breadcrumb}': {ve}",
                        partial_traces=traces,
                    )
                return _resolve_single_ref(ref, breadcrumb)

            # Regular dictionary
            resolved_dict = {}
            for k, v in node.items():
                child_path = f"{breadcrumb}.{k}" if breadcrumb else str(k)
                resolved_dict[k] = _traverse_and_resolve(v, child_path)
            return resolved_dict

        if isinstance(node, list):
            resolved_list = []
            for idx, item in enumerate(node):
                child_path = f"{breadcrumb}[{idx}]"
                resolved_list.append(_traverse_and_resolve(item, child_path))
            return resolved_list

        if isinstance(node, tuple):
            resolved_list = []
            for idx, item in enumerate(node):
                child_path = f"{breadcrumb}[{idx}]"
                resolved_list.append(_traverse_and_resolve(item, child_path))
            return tuple(resolved_list)

        if isinstance(node, str) and node.startswith("$ref:"):
            raise BindingResolutionError(
                "UNSUPPORTED_SYNTAX",
                f"Shorthand '$ref:' syntax is not supported at '{breadcrumb}': '{node}'. "
                f"Use canonical structured format: {{'$ref': {{'task_id': ..., 'path': ...}}}}",
                partial_traces=traces,
            )

        return copy.deepcopy(node)

    resolved_params = _traverse_and_resolve(task.input_params, "")
    return (resolved_params, traces)


@dataclass
class DispatchResult:
    """
    Structured outcome of task or plan dispatch.
    Traceable across session, correlation ID, task ID, and plan ID.
    """
    success: bool
    task_id: str
    plan_id: Optional[str] = None
    session_id: str = "default"
    correlation_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    agent_id: Optional[str] = None
    capability_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    message: str = ""
    execution_time_ms: float = 0.0
    is_duplicate: bool = False
    verification: Optional[VerificationResult] = None
    resolved_input_params: Optional[Dict[str, Any]] = None
    binding_traces: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes result into standardized dictionary."""
        return {
            "success": self.success,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "agent_id": self.agent_id,
            "capability_id": self.capability_id,
            "result": self.result,
            "error_code": self.error_code,
            "message": self.message,
            "execution_time_ms": self.execution_time_ms,
            "is_duplicate": self.is_duplicate,
            "verification": self.verification.to_dict() if self.verification else None,
            "resolved_input_params": self.resolved_input_params,
            "binding_traces": self.binding_traces,
        }

    def to_bridge_response(self) -> BridgeResponse:
        """Converts result into a standard BridgeResponse envelope."""
        if self.success:
            return BridgeResponse.success(
                result=self.result or {},
                command_id=self.task_id,
                duration_ms=self.execution_time_ms,
            )
        else:
            msg = self.message or f"Dispatch error: {self.error_code or 'UNKNOWN_ERROR'}"
            resp = BridgeResponse.error(
                message=msg,
                command_id=self.task_id,
                duration_ms=self.execution_time_ms,
            )
            if self.result is not None:
                resp.result = self.result
            return resp


class AgentDispatcher:
    """
    Central request dispatcher coordinating:
    1. Correlation and session scoping (deduplication, isolation).
    2. Deterministic capability routing (no arbitrary fallback).
    3. Dependency-aware task planning and static graph validation (cycle detection).
    4. Strict authorization and approval gates (model approved=True rejection).
    5. Controlled execution through BlenderExecutor onto Blender main thread.
    6. Structured verification and result tracking.
    """

    def __init__(
        self,
        manager: Optional[AgentManager] = None,
        coordinator: Optional[SessionCoordinator] = None,
        executor: Optional[BlenderExecutor] = None,
        agent_runners: Optional[Dict[str, Any]] = None,
    ):
        self.manager = manager or AgentManager()
        self.coordinator = coordinator or SessionCoordinator()
        self.executor = executor or BlenderExecutor()
        self._agent_runners = dict(agent_runners) if agent_runners is not None else {
            DIRECTOR_AGENT_ID: DirectorAgent(),
            SCENE_INSPECTOR_AGENT_ID: SceneInspectorAgent(),
            MODELING_AGENT_ID: ModelingAgent(),
            MATERIALS_AGENT_ID: MaterialsAgent(),
            RENDER_LIGHTING_AGENT_ID: RenderLightingAgent(),
            RIGGING_ANIMATION_AGENT_ID: RiggingAnimationAgent(),
            SIMULATION_VFX_AGENT_ID: SimulationVFXAgent(),
            INTERCHANGE_DELIVERY_AGENT_ID: InterchangeDeliveryAgent(),
            COMPOSITOR_AGENT_ID: CompositorAgent(),
            VIDEO_EDITOR_AGENT_ID: VideoEditorAgent(),
        }

    def register_agent_runner(self, agent_id: str, runner: Any) -> None:
        """Registers or replaces an agent runner implementation."""
        self._agent_runners[agent_id] = runner

    def get_agent_runner(self, agent_id: str) -> Optional[Any]:
        """Retrieves registered agent runner for the given agent_id."""
        return self._agent_runners.get(agent_id)

    @property
    def registry(self):
        return self.manager.registry

    @property
    def router(self):
        return self.manager.router

    @property
    def planner(self):
        return self.manager.planner

    def dispatch_task(
        self,
        task: AgentTask,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        trusted_approval: Optional[bool] = None,
        plan: Optional[TaskPlan] = None,
        approval_token: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> DispatchResult:
        """
        Dispatches an individual AgentTask through the controlled pipeline:
        Deduplication -> Reference Resolution -> Security Gate -> Routing -> Planning -> Authorization -> Execution -> Tracking.
        """
        t0 = time.time()
        sid = session_id or task.session_id or "default"
        cid = correlation_id or task.correlation_id

        # 1. Session Scoping & Existing / Duplicate Check
        session = self.coordinator.get_or_create_session(sid)
        task.session_id = session.session_id

        existing = session.tasks.get(task.task_id)
        if not existing and cid:
            existing = self.coordinator.get_task_by_correlation(session.session_id, cid)

        if existing:
            if existing.is_terminal:
                output = existing.result.output if existing.result else None
                err_code = None if existing.status == TaskStatus.SUCCEEDED else (
                    existing.result.errors[0] if existing.result and existing.result.errors else "PREVIOUS_FAILURE"
                )
                msg = (
                    "Duplicate request: returning cached result for correlation ID."
                    if cid
                    else "Duplicate request: returning cached result for task ID."
                )
                return DispatchResult(
                    success=(existing.status == TaskStatus.SUCCEEDED),
                    task_id=existing.task_id,
                    plan_id=plan.plan_id if plan else None,
                    session_id=session.session_id,
                    correlation_id=cid or existing.correlation_id,
                    status=existing.status,
                    agent_id=existing.target_agent_id,
                    capability_id=existing.required_capability,
                    result=output,
                    error_code=err_code if existing.status != TaskStatus.SUCCEEDED else None,
                    message=msg,
                    execution_time_ms=existing.result.execution_time_ms if existing.result else 0.0,
                    is_duplicate=True,
                    resolved_input_params=existing.resolved_input_params,
                    binding_traces=existing.binding_traces,
                )

            if existing.status == TaskStatus.AWAITING_APPROVAL:
                # 1. Untrusted approval flag check
                if contains_untrusted_approval_flag(task.input_params):
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    try:
                        existing.transition_to(TaskStatus.FAILED)
                    except ValueError:
                        pass
                    agent_result = AgentResult(
                        task_id=existing.task_id,
                        status=TaskStatus.FAILED,
                        errors=["Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation."],
                        execution_time_ms=duration_ms,
                    )
                    self.coordinator.record_result(session.session_id, existing.task_id, agent_result)
                    self.coordinator.clear_pending_approval(session.session_id, existing.task_id)
                    existing.result = agent_result
                    return DispatchResult(
                        success=False,
                        task_id=existing.task_id,
                        plan_id=plan.plan_id if plan else None,
                        session_id=session.session_id,
                        correlation_id=cid or existing.correlation_id,
                        status=TaskStatus.FAILED,
                        agent_id=existing.target_agent_id,
                        capability_id=existing.required_capability,
                        error_code="PERMISSION_DENIED",
                        message=(
                            "Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation. "
                            "Explicit user approval must be granted through a trusted approval mechanism."
                        ),
                        execution_time_ms=duration_ms,
                        resolved_input_params=task.input_params,
                    )

                # 2. Check parameter tampering against pending binding
                binding = self.coordinator.get_pending_approval(session.session_id, existing.task_id) or existing.approval_binding
                tool_name = (binding.get("tool_name") if binding else None) or existing.task_type or existing.required_capability
                expected_hash = binding.get("param_hash") if binding else None
                cur_hash = compute_param_hash(tool_name, task.input_params)

                if expected_hash and cur_hash != expected_hash:
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    return DispatchResult(
                        success=False,
                        task_id=existing.task_id,
                        plan_id=plan.plan_id if plan else None,
                        session_id=session.session_id,
                        correlation_id=cid or existing.correlation_id,
                        status=TaskStatus.AWAITING_APPROVAL,
                        agent_id=existing.target_agent_id,
                        capability_id=existing.required_capability,
                        error_code="PARAMETER_TAMPERING",
                        message=(
                            f"Parameter tampering detected: Parameters for task '{existing.task_id}' do not match "
                            f"the pending approval request. Fresh approval is required."
                        ),
                        execution_time_ms=duration_ms,
                        resolved_input_params=task.input_params,
                    )

                # 3. Check for trusted approval
                token_to_use = approval_token or task.input_params.get("approval_token")
                req_id_to_use = request_id or task.input_params.get("request_id")
                has_creds = bool(token_to_use and req_id_to_use)

                if trusted_approval is True or has_creds:
                    return self.resume_task(
                        task_id=existing.task_id,
                        session_id=session.session_id,
                        trusted_approval=trusted_approval,
                        approval_token=token_to_use,
                        request_id=req_id_to_use,
                        execution_params=binding.get("raw_params") if binding else existing.resolved_input_params,
                    )
                elif trusted_approval is False:
                    return self.resume_task(
                        task_id=existing.task_id,
                        session_id=session.session_id,
                        trusted_approval=False,
                    )
                else:
                    # Reconcile cached task state against the approval source
                    # before claiming that its request is still pending.
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    nonce = binding.get("nonce", "") if binding else ""
                    expires_at = binding.get("expires_at", 0.0) if binding else 0.0
                    p_hash = binding.get("param_hash", "") if binding else ""
                    approval_request_id = binding.get("blender_request_id") if binding else None
                    approval_source = binding.get("approval_source") if binding else None
                    approval_status = "unknown"
                    approval_error_code = "APPROVAL_STATUS_UNAVAILABLE"
                    approval_message = (
                        "The approval source's current status is unavailable. The task remains fail-closed; "
                        "do not treat stored resolver credentials as approval."
                    )

                    status_reader = getattr(self.executor, "get_approval_status", None)
                    if approval_source == "blender" and approval_request_id and callable(status_reader):
                        try:
                            status_result = status_reader(approval_request_id, approval_source)
                            if isinstance(status_result, dict):
                                reported_status = str(status_result.get("status", "unknown")).strip().lower()
                                if reported_status in {"pending", "approved", "denied", "cancelled", "expired", "not_found"}:
                                    approval_status = reported_status
                        except Exception as exc:
                            approval_message = (
                                f"Could not verify Blender approval request '{approval_request_id}': {exc}. "
                                "The task remains fail-closed."
                            )

                    if approval_status == "pending":
                        approval_error_code = "APPROVAL_REQUIRED"
                        approval_message = (
                            f"Blender confirms approval request '{approval_request_id}' is still pending. "
                            "Approve or deny it in Blender before resolving the paused task."
                        )
                    elif approval_status == "approved":
                        approval_error_code = "APPROVAL_RECORDED"
                        approval_message = (
                            f"Blender records human approval for request '{approval_request_id}'. "
                            "Invoke resolve_pending_approval to validate its single-use token and resume the task."
                        )
                    elif approval_status in {"denied", "cancelled"}:
                        approval_error_code = "PERMISSION_DENIED"
                        approval_message = f"Blender records the approval request as {approval_status}; the task cannot resume."
                    elif approval_status == "expired":
                        approval_error_code = "APPROVAL_EXPIRED"
                        approval_message = (
                            f"Blender approval request '{approval_request_id}' expired. "
                            "Start a fresh task to obtain a new approval request."
                        )
                    elif approval_status == "not_found":
                        approval_error_code = "APPROVAL_REQUEST_NOT_FOUND"
                        approval_message = (
                            f"Blender no longer has approval request '{approval_request_id}' (it may have expired, "
                            "been purged, or the registry may have been reloaded). Start a fresh task to obtain "
                            "a new approval request."
                        )

                    app_payload = {
                        "task_id": existing.task_id,
                        "session_id": session.session_id,
                        "tool_name": tool_name,
                        "param_hash": p_hash,
                        "nonce": nonce,
                        "expires_at": expires_at,
                        "resolution_tool": "resolve_pending_approval",
                        "approval_status": approval_status,
                    }
                    if approval_request_id:
                        app_payload["approval_request_id"] = approval_request_id
                    return DispatchResult(
                        success=False,
                        task_id=existing.task_id,
                        plan_id=plan.plan_id if plan else None,
                        session_id=session.session_id,
                        correlation_id=cid or existing.correlation_id,
                        status=TaskStatus.AWAITING_APPROVAL,
                        agent_id=existing.target_agent_id,
                        capability_id=existing.required_capability,
                        error_code=approval_error_code,
                        message=(
                            f"Task '{existing.task_id}' remains paused in AWAITING_APPROVAL. {approval_message} "
                            f"Resolver correlation fields are task_id='{existing.task_id}', "
                            f"session_id='{session.session_id}', nonce='{nonce}', param_hash='{p_hash}'. "
                            "These fields do not themselves authorize the mutation."
                        ),
                        result={"pending_approval": app_payload},
                        execution_time_ms=duration_ms,
                        resolved_input_params=binding.get("raw_params") if binding else existing.resolved_input_params,
                        binding_traces=existing.binding_traces,
                    )

        if cid:
            task.correlation_id = cid

        # 1.5 Runtime Result Binding Resolution
        try:
            resolved_params, binding_traces = resolve_task_references(
                task=task,
                plan=plan,
                session_results=session.task_results,
            )
            task.resolved_input_params = resolved_params
            task.binding_traces = binding_traces
        except BindingResolutionError as bre:
            duration_ms = round((time.time() - t0) * 1000, 2)
            try:
                task.transition_to(TaskStatus.FAILED)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[bre.message],
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(session.session_id, task.task_id, agent_result)
            task.result = agent_result
            task.binding_traces = bre.partial_traces
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                plan_id=plan.plan_id if plan else None,
                session_id=session.session_id,
                correlation_id=cid,
                status=TaskStatus.FAILED,
                error_code=bre.error_code,
                message=bre.message,
                execution_time_ms=duration_ms,
                resolved_input_params=None,
                binding_traces=bre.partial_traces,
            )

        # 2. Security Check: Model-supplied 'approved=True' or 'trusted_approval=True' is untrusted
        if contains_untrusted_approval_flag(resolved_params) or contains_untrusted_approval_flag(task.input_params):
            duration_ms = round((time.time() - t0) * 1000, 2)
            try:
                task.transition_to(TaskStatus.FAILED)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=["Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation."],
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(session.session_id, task.task_id, agent_result)
            task.result = agent_result
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                plan_id=plan.plan_id if plan else None,
                session_id=session.session_id,
                correlation_id=cid,
                status=TaskStatus.FAILED,
                error_code="PERMISSION_DENIED",
                message=(
                    "Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation. "
                    "Explicit user approval must be granted through a trusted approval mechanism."
                ),
                execution_time_ms=duration_ms,
                resolved_input_params=resolved_params,
                binding_traces=binding_traces,
            )

        # 3. Deterministic Capability Routing
        if not task.required_capability:
            if task.task_type:
                cap_desc = self.registry.find_capability_by_task_type(task.task_type)
                if cap_desc:
                    task.required_capability = cap_desc.capability_id
                else:
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    try:
                        task.transition_to(TaskStatus.FAILED)
                    except ValueError:
                        pass
                    agent_result = AgentResult(
                        task_id=task.task_id,
                        status=TaskStatus.FAILED,
                        errors=[f"No registered capability found for task type '{task.task_type}'."],
                        execution_time_ms=duration_ms,
                    )
                    self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                    task.result = agent_result
                    return DispatchResult(
                        success=False,
                        task_id=task.task_id,
                        session_id=session.session_id,
                        correlation_id=cid,
                        status=TaskStatus.FAILED,
                        error_code="NO_MATCH",
                        message=f"No registered capability found for task type '{task.task_type}'.",
                        execution_time_ms=duration_ms,
                        resolved_input_params=resolved_params,
                        binding_traces=binding_traces,
                    )
            else:
                duration_ms = round((time.time() - t0) * 1000, 2)
                try:
                    task.transition_to(TaskStatus.FAILED)
                except ValueError:
                    pass
                agent_result = AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=["Task must specify 'required_capability' or 'task_type'."],
                    execution_time_ms=duration_ms,
                )
                self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                task.result = agent_result
                return DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    session_id=session.session_id,
                    correlation_id=cid,
                    status=TaskStatus.FAILED,
                    error_code="NO_MATCH",
                    message="Task must specify 'required_capability' or 'task_type'.",
                    execution_time_ms=duration_ms,
                    resolved_input_params=resolved_params,
                    binding_traces=binding_traces,
                )

        routing_res = self.manager.route_task(task, require_verified=True, strict_ambiguity=True)
        if not routing_res.success:
            duration_ms = round((time.time() - t0) * 1000, 2)
            try:
                task.transition_to(TaskStatus.FAILED)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[routing_res.message],
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(session.session_id, task.task_id, agent_result)
            task.result = agent_result
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                session_id=session.session_id,
                correlation_id=cid,
                status=TaskStatus.FAILED,
                error_code=routing_res.error_code or "NO_MATCH",
                message=routing_res.message,
                execution_time_ms=duration_ms,
                resolved_input_params=resolved_params,
                binding_traces=binding_traces,
            )

        task.target_agent_id = routing_res.agent.agent_id
        cap = routing_res.capability

        # 4. Planning & Graph Validation (Standalone single-task plan if needed)
        task_plan = plan
        if task_plan is None:
            task_plan = TaskPlan(title=f"Plan for task {task.task_id}")
            to_collect = list(task.dependencies)
            visited_deps = set()
            while to_collect:
                dep_id = to_collect.pop(0)
                if dep_id in visited_deps:
                    continue
                visited_deps.add(dep_id)
                if dep_id in session.tasks and dep_id not in task_plan.tasks:
                    dep_task = session.tasks[dep_id]
                    task_plan.add_task(dep_task)
                    to_collect.extend(dep_task.dependencies)
            task_plan.add_task(task)
            plan_errors = self.manager.validate_plan(task_plan, require_verified_capabilities=True)
            if plan_errors:
                duration_ms = round((time.time() - t0) * 1000, 2)
                try:
                    task.transition_to(TaskStatus.FAILED)
                except ValueError:
                    pass
                agent_result = AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=plan_errors,
                    execution_time_ms=duration_ms,
                )
                self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                task.result = agent_result
                return DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    plan_id=task_plan.plan_id,
                    session_id=session.session_id,
                    correlation_id=cid,
                    status=TaskStatus.FAILED,
                    error_code="INVALID_PLAN",
                    message=f"TaskPlan validation failed: {'; '.join(plan_errors)}",
                    execution_time_ms=duration_ms,
                    resolved_input_params=resolved_params,
                    binding_traces=binding_traces,
                )

        # Transition task to READY upon successful plan validation
        if task.status == TaskStatus.PENDING:
            task.transition_to(TaskStatus.READY)

        # Track task in session
        self.coordinator.track_task(session.session_id, task, correlation_id=cid)
        if plan is None:
            self.coordinator.track_plan(session.session_id, task_plan)

        # 5. Authorization Stage
        is_mutation = cap and cap.read_write in ("SCENE_MUTATION", "DESTRUCTIVE")
        if is_mutation:
            if trusted_approval is False:
                duration_ms = round((time.time() - t0) * 1000, 2)
                try:
                    task.transition_to(TaskStatus.FAILED)
                except ValueError:
                    pass
                agent_result = AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=["Scene mutation denied: trusted_approval was explicitly False."],
                    execution_time_ms=duration_ms,
                )
                self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                task.result = agent_result
                return DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    plan_id=task_plan.plan_id,
                    session_id=session.session_id,
                    correlation_id=cid,
                    status=TaskStatus.FAILED,
                    agent_id=task.target_agent_id,
                    capability_id=task.required_capability,
                    error_code="PERMISSION_DENIED",
                    message="Scene mutation denied: trusted_approval was explicitly False.",
                    execution_time_ms=duration_ms,
                    resolved_input_params=resolved_params,
                    binding_traces=binding_traces,
                )

            # Check if approval credentials exist or if approval provider is present
            has_credentials = bool(resolved_params.get("request_id") and resolved_params.get("approval_token"))
            app_mgr = getattr(self.executor, "approval_manager", None)
            has_provider = bool(getattr(app_mgr, "_provider", None)) if app_mgr else False

            if trusted_approval is not True and not has_credentials and not has_provider:
                # Block mutation: transition to AWAITING_APPROVAL and return structured response
                duration_ms = round((time.time() - t0) * 1000, 2)
                try:
                    task.transition_to(TaskStatus.AWAITING_APPROVAL)
                except ValueError:
                    pass

                tool_name = task.task_type or task.required_capability
                clean_params = {
                    k: v for k, v in resolved_params.items()
                    if k not in ("session_id", "correlation_id")
                }
                param_hash = compute_param_hash(tool_name, clean_params)
                nonce = secrets.token_hex(16)
                created_now = time.time()
                expires_at = created_now + 300.0  # 5 minute TTL

                binding = {
                    "task_id": task.task_id,
                    "session_id": session.session_id,
                    "correlation_id": cid,
                    "tool_name": tool_name,
                    "raw_params": copy.deepcopy(clean_params),
                    "param_hash": param_hash,
                    "nonce": nonce,
                    "expires_at": expires_at,
                    "consumed": False,
                    "target_agent_id": task.target_agent_id,
                    "required_capability": task.required_capability,
                    "created_at": created_now,
                    "status": "awaiting_approval",
                }
                task.approval_binding = binding
                self.coordinator.record_pending_approval(session.session_id, task.task_id, binding)

                approval_payload = {
                    "task_id": task.task_id,
                    "session_id": session.session_id,
                    "tool_name": tool_name,
                    "param_hash": param_hash,
                    "nonce": nonce,
                    "expires_at": expires_at,
                    "resolution_tool": "resolve_pending_approval",
                }

                return DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    plan_id=task_plan.plan_id,
                    session_id=session.session_id,
                    correlation_id=cid,
                    status=TaskStatus.AWAITING_APPROVAL,
                    agent_id=task.target_agent_id,
                    capability_id=task.required_capability,
                    error_code="APPROVAL_REQUIRED",
                    message=(
                        f"Approval required: Scene mutation '{task.task_type}' requires human approval in Blender. "
                        f"The task is paused in AWAITING_APPROVAL state. "
                        f"To deny or resume after a separate Blender UI approval, invoke 'resolve_pending_approval' "
                        f"with task_id='{task.task_id}', session_id='{session.session_id}', "
                        f"decision='approved'|'denied', nonce='{nonce}', param_hash='{param_hash}'. "
                        "These resolver credentials do not themselves authorize the mutation."
                    ),
                    result={"pending_approval": approval_payload},
                    execution_time_ms=duration_ms,
                    resolved_input_params=resolved_params,
                    binding_traces=binding_traces,
                )

        # 6. Controlled Execution Stage
        try:
            task.transition_to(TaskStatus.RUNNING)
        except ValueError:
            pass

        # Sanitize parameters (exclude internal metadata keys from executor arguments)
        clean_params = {
            k: v for k, v in resolved_params.items()
            if k not in ("session_id", "correlation_id")
        }

        # Delegate to specialized agent runner if registered for target agent
        agent_runner = self._agent_runners.get(task.target_agent_id) if self._agent_runners else None
        if agent_runner and hasattr(agent_runner, "execute_task"):
            runner_task = AgentTask(
                task_id=task.task_id,
                required_capability=task.required_capability,
                task_type=task.task_type,
                input_params=clean_params,
                session_id=session.session_id,
                correlation_id=cid,
                target_agent_id=task.target_agent_id,
                resolved_input_params=resolved_params,
                binding_traces=binding_traces,
            )
            try:
                agent_result: AgentResult = agent_runner.execute_task(
                    runner_task, self.executor, **_approval_kwargs(agent_runner.execute_task, trusted_approval)
                )
            except Exception as exc:
                logger.exception("Agent runner failed after a single invocation")
                agent_result = AgentResult(task_id=task.task_id, status=TaskStatus.FAILED,
                                           errors=[f"Agent execution error: {exc}"])
            duration_ms = agent_result.execution_time_ms or round((time.time() - t0) * 1000, 2)

            if agent_result.status == TaskStatus.SUCCEEDED:
                try:
                    task.transition_to(TaskStatus.SUCCEEDED)
                except ValueError:
                    pass
                self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                task.result = agent_result
                return DispatchResult(
                    success=True,
                    task_id=task.task_id,
                    plan_id=task_plan.plan_id,
                    session_id=session.session_id,
                    correlation_id=cid,
                    status=TaskStatus.SUCCEEDED,
                    agent_id=task.target_agent_id,
                    capability_id=task.required_capability,
                    result=agent_result.output,
                    execution_time_ms=duration_ms,
                    verification=agent_result.verification,
                    resolved_input_params=resolved_params,
                    binding_traces=binding_traces,
                )
            else:
                err_msg = "; ".join(agent_result.errors) if agent_result.errors else "Agent execution failed"
                err_msg_lower = err_msg.lower()
                obs = agent_result.verification.observed_results if agent_result.verification else {}
                err_code = obs.get("error_code")
                if not err_code:
                    if "approval required" in err_msg_lower:
                        err_code = "APPROVAL_REQUIRED"
                    elif "permission denied" in err_msg_lower or "read-only" in err_msg_lower or "approval denied" in err_msg_lower:
                        err_code = "PERMISSION_DENIED"
                    elif "unsupported" in err_msg_lower:
                        err_code = "UNSUPPORTED_REQUEST"
                    elif "security" in err_msg_lower or "ast" in err_msg_lower:
                        err_code = "SECURITY_VIOLATION"
                    elif "invalid" in err_msg_lower or "required" in err_msg_lower:
                        err_code = "INVALID_PARAMS"
                    elif "not found" in err_msg_lower or "does not exist" in err_msg_lower or "missing target" in err_msg_lower:
                        err_code = "DATA_UNAVAILABLE"
                    elif "collision" in err_msg_lower or "already exists" in err_msg_lower:
                        err_code = "NAME_COLLISION"
                    else:
                        err_code = "EXECUTION_FAILED"

                task_status = TaskStatus.AWAITING_APPROVAL if err_code == "APPROVAL_REQUIRED" else TaskStatus.FAILED
                pending_approval = None
                blender_request_id = obs.get("approval_request_id")
                if task_status == TaskStatus.AWAITING_APPROVAL and obs.get("approval_pending") and blender_request_id:
                    created_at = time.time()
                    expires_at = float(obs.get("approval_expires_at") or (created_at + 300.0))
                    param_hash = compute_param_hash(task.task_type or task.required_capability, clean_params)
                    nonce = secrets.token_hex(16)
                    binding = {
                        "task_id": task.task_id,
                        "session_id": session.session_id,
                        "correlation_id": cid,
                        "tool_name": task.task_type or task.required_capability,
                        "raw_params": copy.deepcopy(clean_params),
                        "param_hash": param_hash,
                        "nonce": nonce,
                        "expires_at": expires_at,
                        "consumed": False,
                        "target_agent_id": task.target_agent_id,
                        "required_capability": task.required_capability,
                        "created_at": created_at,
                        "status": "awaiting_approval",
                        "approval_source": "blender",
                        "blender_request_id": blender_request_id,
                    }
                    task.approval_binding = binding
                    self.coordinator.record_pending_approval(session.session_id, task.task_id, binding)
                    pending_approval = {
                        "task_id": task.task_id,
                        "session_id": session.session_id,
                        "tool_name": binding["tool_name"],
                        "param_hash": param_hash,
                        "nonce": nonce,
                        "expires_at": expires_at,
                        "approval_request_id": blender_request_id,
                        "approval_status": "pending",
                        "resolution_tool": "resolve_pending_approval",
                    }
                try:
                    task.transition_to(task_status)
                except ValueError:
                    pass
                self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                task.result = agent_result
                return DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    plan_id=task_plan.plan_id,
                    session_id=session.session_id,
                    correlation_id=cid,
                    status=task_status,
                    agent_id=task.target_agent_id,
                    capability_id=task.required_capability,
                    error_code=err_code,
                    message=(
                        f"{err_msg} Blender approval request '{blender_request_id}' remains pending; "
                        f"use the Blender approval UI, then resolve the original task with the returned task_id, "
                        "session_id, nonce, and param_hash."
                        if pending_approval else err_msg
                    ),
                    result={"pending_approval": pending_approval} if pending_approval else None,
                    execution_time_ms=duration_ms,
                    verification=agent_result.verification,
                    resolved_input_params=resolved_params,
                    binding_traces=binding_traces,
                )

        tool_name = task.task_type or task.required_capability
        try:
            kwargs = _approval_kwargs(self.executor.execute_tool, trusted_approval) if trusted_approval is not None else {}
            resp = self.executor.execute_tool(tool_name, clean_params, **kwargs)
        except Exception as exc:
            logger.exception(f"Unexpected executor exception during dispatch of '{tool_name}': {exc}")
            resp = BridgeResponse.error(f"Internal dispatcher error: {exc}")

        duration_ms = round((time.time() - t0) * 1000, 2)

        if resp.is_success:
            self.coordinator.clear_pending_approval(session.session_id, task.task_id)
            task.approval_binding = None
            try:
                task.transition_to(TaskStatus.SUCCEEDED)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=TaskStatus.SUCCEEDED,
                output=resp.result,
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(session.session_id, task.task_id, agent_result)
            task.result = agent_result
            return DispatchResult(
                success=True,
                task_id=task.task_id,
                plan_id=task_plan.plan_id,
                session_id=session.session_id,
                correlation_id=cid,
                status=TaskStatus.SUCCEEDED,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                result=resp.result,
                execution_time_ms=duration_ms,
                resolved_input_params=resolved_params,
                binding_traces=binding_traces,
            )
        else:
            msg_lower = (resp.message or "").lower()
            if "approval required" in msg_lower:
                status = TaskStatus.AWAITING_APPROVAL
                err_code = "APPROVAL_REQUIRED"
                param_hash = compute_param_hash(tool_name, clean_params)
                binding = {
                    "task_id": task.task_id,
                    "session_id": session.session_id,
                    "correlation_id": cid,
                    "tool_name": tool_name,
                    "raw_params": copy.deepcopy(clean_params),
                    "param_hash": param_hash,
                    "target_agent_id": task.target_agent_id,
                    "required_capability": task.required_capability,
                    "created_at": time.time(),
                    "status": "awaiting_approval",
                }
                task.approval_binding = binding
                self.coordinator.record_pending_approval(session.session_id, task.task_id, binding)
            elif "approval denied" in msg_lower or "permission" in msg_lower:
                status = TaskStatus.FAILED
                err_code = "PERMISSION_DENIED"
                self.coordinator.clear_pending_approval(session.session_id, task.task_id)
            else:
                status = TaskStatus.FAILED
                err_code = "EXECUTION_FAILED"
                self.coordinator.clear_pending_approval(session.session_id, task.task_id)

            try:
                task.transition_to(status)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=status,
                errors=[resp.message or "Execution failed"],
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(session.session_id, task.task_id, agent_result)
            task.result = agent_result
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                plan_id=task_plan.plan_id,
                session_id=session.session_id,
                correlation_id=cid,
                status=status,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                error_code=err_code,
                message=resp.message or "Execution failed",
                execution_time_ms=duration_ms,
                resolved_input_params=resolved_params,
                binding_traces=binding_traces,
            )

    def dispatch_plan(
        self,
        plan: TaskPlan,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        trusted_approval: Optional[bool] = None,
    ) -> List[DispatchResult]:
        """
        Dispatches a multi-task TaskPlan through topological execution.
        Performs full static validation before executing any task.
        If any upstream task fails, downstream dependent tasks are automatically SKIPPED.
        """
        sid = session_id or "default"
        session = self.coordinator.get_or_create_session(sid)

        # 1. Full Static Validation of Entire Plan
        errors = self.manager.validate_plan(plan, require_verified_capabilities=True)
        if errors:
            try:
                plan.transition_to(TaskStatus.FAILED)
            except ValueError:
                pass
            for t in plan.tasks.values():
                try:
                    t.transition_to(TaskStatus.FAILED)
                except ValueError:
                    pass

            is_cycle = any("cycle" in e.lower() for e in errors)
            err_code = "DEPENDENCY_CYCLE" if is_cycle else "INVALID_PLAN"
            err_msg = f"TaskPlan validation failed with {len(errors)} error(s): {'; '.join(errors)}"

            return [
                DispatchResult(
                    success=False,
                    task_id=t.task_id,
                    plan_id=plan.plan_id,
                    session_id=session.session_id,
                    status=TaskStatus.FAILED,
                    error_code=err_code,
                    message=err_msg,
                )
                for t in plan.tasks.values()
            ]

        # 2. Compute topological execution order
        self.manager.planner.compute_execution_order(plan)
        if plan.status == TaskStatus.PENDING:
            plan.transition_to(TaskStatus.READY)
        if plan.status == TaskStatus.READY:
            plan.transition_to(TaskStatus.RUNNING)
        self.coordinator.track_plan(session.session_id, plan)

        results: List[DispatchResult] = []

        # 3. Execute in deterministic topological order
        for tid in plan.execution_order:
            task = plan.tasks[tid]
            self.manager.planner.advance_plan_state(plan)

            # If task was skipped due to upstream failure, record and advance
            if task.status == TaskStatus.SKIPPED:
                res = DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    plan_id=plan.plan_id,
                    session_id=session.session_id,
                    status=TaskStatus.SKIPPED,
                    error_code="UPSTREAM_FAILURE",
                    message=f"Task '{task.task_id}' was skipped due to failure of a prerequisite task.",
                )
                results.append(res)
                continue

            # Dispatch task
            res = self.dispatch_task(
                task,
                session_id=session.session_id,
                trusted_approval=trusted_approval,
                plan=plan,
            )
            results.append(res)

            # Advance plan state to propagate failures to downstream tasks
            self.manager.planner.advance_plan_state(plan)

        return results

    def resume_task(
        self,
        task_id: str,
        session_id: Optional[str] = None,
        trusted_approval: Optional[bool] = None,
        approval_token: Optional[str] = None,
        request_id: Optional[str] = None,
        execution_params: Optional[Dict[str, Any]] = None,
    ) -> DispatchResult:
        """
        Resumes an operation currently paused in AWAITING_APPROVAL after trusted approval verification.
        Validates session, task state, parameter integrity, replay prevention, and expiration.
        """
        t0 = time.time()
        sid = session_id or "default"
        session = self.coordinator.get_session(sid)
        if not session:
            return DispatchResult(
                success=False,
                task_id=task_id,
                session_id=sid,
                status=TaskStatus.FAILED,
                error_code="SESSION_NOT_FOUND",
                message=f"Session '{sid}' not found.",
                execution_time_ms=0.0,
            )

        task = session.tasks.get(task_id)
        if not task:
            return DispatchResult(
                success=False,
                task_id=task_id,
                session_id=sid,
                status=TaskStatus.FAILED,
                error_code="TASK_NOT_FOUND",
                message=f"Task '{task_id}' not found in session '{sid}'.",
                execution_time_ms=0.0,
            )

        # 1. Idempotence & Terminal State Check (Duplicate Execution prevention)
        if task.is_terminal:
            output = task.result.output if task.result else None
            err_code = None if task.status == TaskStatus.SUCCEEDED else (
                task.result.errors[0] if task.result and task.result.errors else "PREVIOUS_FAILURE"
            )
            return DispatchResult(
                success=(task.status == TaskStatus.SUCCEEDED),
                task_id=task.task_id,
                session_id=sid,
                correlation_id=task.correlation_id,
                status=task.status,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                result=output,
                error_code=err_code if task.status != TaskStatus.SUCCEEDED else None,
                message="Duplicate execution: returning cached result for already-completed task.",
                execution_time_ms=task.result.execution_time_ms if task.result else 0.0,
                is_duplicate=True,
                resolved_input_params=task.resolved_input_params,
                binding_traces=task.binding_traces,
            )

        if task.status != TaskStatus.AWAITING_APPROVAL:
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                session_id=sid,
                correlation_id=task.correlation_id,
                status=task.status,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                error_code="INVALID_STATE",
                message=f"Task '{task_id}' cannot be resumed from state '{task.status.value}'. Expected AWAITING_APPROVAL.",
                execution_time_ms=0.0,
                resolved_input_params=task.resolved_input_params,
                binding_traces=task.binding_traces,
            )

        # 2. Retrieve Pending Approval Binding
        binding = self.coordinator.get_pending_approval(sid, task_id) or task.approval_binding
        tool_name = (binding.get("tool_name") if binding else None) or task.task_type or task.required_capability
        expected_hash = binding.get("param_hash") if binding else None
        bound_params = (binding.get("raw_params") if binding else None) or task.resolved_input_params or task.input_params

        exec_params = execution_params if execution_params is not None else bound_params
        exec_params = dict(exec_params or {})

        # 3. Parameter Tampering Check
        current_hash = compute_param_hash(tool_name, exec_params)
        if expected_hash and current_hash != expected_hash:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                session_id=sid,
                correlation_id=task.correlation_id,
                status=TaskStatus.AWAITING_APPROVAL,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                error_code="PARAMETER_TAMPERING",
                message=(
                    f"Parameter tampering detected: Parameters for task '{task_id}' do not match "
                    f"the pending approval request. Fresh approval is required."
                ),
                execution_time_ms=duration_ms,
                resolved_input_params=exec_params,
                binding_traces=task.binding_traces,
            )

        # 4. Security Check: Reject untrusted approval flags in parameters
        if contains_untrusted_approval_flag(exec_params):
            duration_ms = round((time.time() - t0) * 1000, 2)
            try:
                task.transition_to(TaskStatus.FAILED)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=["Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation."],
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(sid, task.task_id, agent_result)
            self.coordinator.clear_pending_approval(sid, task.task_id)
            task.result = agent_result
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                session_id=sid,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILED,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                error_code="PERMISSION_DENIED",
                message=(
                    "Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation. "
                    "Explicit user approval must be granted through a trusted approval mechanism."
                ),
                execution_time_ms=duration_ms,
                resolved_input_params=exec_params,
                binding_traces=task.binding_traces,
            )

        # 5. Trusted Approval Verification
        if trusted_approval is False:
            duration_ms = round((time.time() - t0) * 1000, 2)
            try:
                task.transition_to(TaskStatus.FAILED)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=["Scene mutation denied: trusted_approval was explicitly False."],
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(sid, task.task_id, agent_result)
            self.coordinator.clear_pending_approval(sid, task.task_id)
            task.result = agent_result
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                session_id=sid,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILED,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                error_code="PERMISSION_DENIED",
                message="Scene mutation denied: trusted_approval was explicitly False.",
                execution_time_ms=duration_ms,
                resolved_input_params=exec_params,
                binding_traces=task.binding_traces,
            )

        token_to_use = approval_token or exec_params.get("approval_token")
        req_id_to_use = request_id or exec_params.get("request_id")
        has_credentials = bool(token_to_use and req_id_to_use)
        app_mgr = getattr(self.executor, "approval_manager", None)

        if trusted_approval is not True and not has_credentials:
            if app_mgr and app_mgr.has_provider:
                decision = app_mgr.verify_approval(tool_name, exec_params)
                if decision.approved:
                    trusted_approval = True
                    token_to_use = decision.approval_token
                    req_id_to_use = decision.request_id
                else:
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    reason_lower = (decision.reason or "").lower()
                    if "expired" in reason_lower or "timed out" in reason_lower:
                        err_code = "APPROVAL_EXPIRED"
                        term_status = TaskStatus.FAILED
                    elif "denied" in reason_lower or "cancelled" in reason_lower:
                        err_code = "PERMISSION_DENIED"
                        term_status = TaskStatus.FAILED
                    else:
                        err_code = "APPROVAL_REQUIRED"
                        term_status = TaskStatus.AWAITING_APPROVAL

                    if term_status == TaskStatus.FAILED:
                        try:
                            task.transition_to(TaskStatus.FAILED)
                        except ValueError:
                            pass
                        agent_result = AgentResult(
                            task_id=task.task_id,
                            status=TaskStatus.FAILED,
                            errors=[decision.reason or "Approval denied"],
                            execution_time_ms=duration_ms,
                        )
                        self.coordinator.record_result(sid, task.task_id, agent_result)
                        self.coordinator.clear_pending_approval(sid, task.task_id)
                        task.result = agent_result

                    return DispatchResult(
                        success=False,
                        task_id=task.task_id,
                        session_id=sid,
                        correlation_id=task.correlation_id,
                        status=term_status,
                        agent_id=task.target_agent_id,
                        capability_id=task.required_capability,
                        error_code=err_code,
                        message=decision.reason or "Approval verification failed.",
                        execution_time_ms=duration_ms,
                        resolved_input_params=exec_params,
                        binding_traces=task.binding_traces,
                    )
            else:
                # No trusted approval and no provider
                return DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    session_id=sid,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.AWAITING_APPROVAL,
                    agent_id=task.target_agent_id,
                    capability_id=task.required_capability,
                    error_code="APPROVAL_REQUIRED",
                    message=(
                        f"Approval required: Scene mutation '{tool_name}' requires explicit user approval through "
                        f"a trusted approval mechanism. Task '{task_id}' remains in AWAITING_APPROVAL state."
                    ),
                    execution_time_ms=0.0,
                    resolved_input_params=exec_params,
                    binding_traces=task.binding_traces,
                )

        # 6. Execute Resumed Task
        try:
            task.transition_to(TaskStatus.RUNNING)
        except ValueError:
            pass

        clean_params = {
            k: v for k, v in exec_params.items()
            if k not in ("session_id", "correlation_id")
        }
        if token_to_use:
            clean_params["approval_token"] = token_to_use
        if req_id_to_use:
            clean_params["request_id"] = req_id_to_use

        # Delegate to specialized agent runner if registered
        agent_runner = self._agent_runners.get(task.target_agent_id) if self._agent_runners else None
        if agent_runner and hasattr(agent_runner, "execute_task"):
            runner_task = AgentTask(
                task_id=task.task_id,
                required_capability=task.required_capability,
                task_type=task.task_type,
                input_params=clean_params,
                session_id=session.session_id,
                correlation_id=task.correlation_id,
                dependencies=task.dependencies,
                preconditions=task.preconditions,
                acceptance_criteria=task.acceptance_criteria,
                target_agent_id=task.target_agent_id,
                resolved_input_params=clean_params,
            )
            runner_task.status = TaskStatus.RUNNING
            try:
                agent_result = agent_runner.execute_task(
                    runner_task, executor=self.executor,
                    **_approval_kwargs(agent_runner.execute_task, True),
                )
            except Exception as exc:
                logger.exception(f"Unexpected agent runner exception during resume of '{tool_name}': {exc}")
                agent_result = AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[f"Agent execution error: {exc}"],
                )

            duration_ms = round((time.time() - t0) * 1000, 2)
            agent_result.execution_time_ms = duration_ms

            if agent_result.is_success:
                try:
                    task.transition_to(TaskStatus.SUCCEEDED)
                except ValueError:
                    pass
                self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                self.coordinator.clear_pending_approval(session.session_id, task.task_id)
                task.result = agent_result
                # Advance plan state if task belongs to any tracked plan
                for p in session.plans.values():
                    if task.task_id in p.tasks:
                        self.manager.planner.advance_plan_state(p)
                return DispatchResult(
                    success=True,
                    task_id=task.task_id,
                    session_id=session.session_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.SUCCEEDED,
                    agent_id=task.target_agent_id,
                    capability_id=task.required_capability,
                    result=agent_result.output,
                    execution_time_ms=duration_ms,
                    verification=agent_result.verification,
                    resolved_input_params=exec_params,
                    binding_traces=task.binding_traces,
                )
            else:
                err_msg = agent_result.errors[0] if agent_result.errors else "Execution failed"
                msg_lower = err_msg.lower()
                if "approval required" in msg_lower:
                    task_status = TaskStatus.AWAITING_APPROVAL
                    err_code = "APPROVAL_REQUIRED"
                elif "expired" in msg_lower or "timed out" in msg_lower:
                    task_status = TaskStatus.FAILED
                    err_code = "APPROVAL_EXPIRED"
                elif "tamper" in msg_lower:
                    task_status = TaskStatus.AWAITING_APPROVAL
                    err_code = "PARAMETER_TAMPERING"
                elif "replay" in msg_lower or "already been consumed" in msg_lower:
                    task_status = TaskStatus.FAILED
                    err_code = "DUPLICATE_EXECUTION"
                elif "denied" in msg_lower or "permission" in msg_lower:
                    task_status = TaskStatus.FAILED
                    err_code = "PERMISSION_DENIED"
                else:
                    task_status = TaskStatus.FAILED
                    err_code = "EXECUTION_FAILED"

                try:
                    task.transition_to(task_status)
                except ValueError:
                    pass
                self.coordinator.record_result(session.session_id, task.task_id, agent_result)
                if task_status == TaskStatus.FAILED:
                    self.coordinator.clear_pending_approval(session.session_id, task.task_id)
                task.result = agent_result
                return DispatchResult(
                    success=False,
                    task_id=task.task_id,
                    session_id=session.session_id,
                    correlation_id=task.correlation_id,
                    status=task_status,
                    agent_id=task.target_agent_id,
                    capability_id=task.required_capability,
                    error_code=err_code,
                    message=err_msg,
                    execution_time_ms=duration_ms,
                    verification=agent_result.verification,
                    resolved_input_params=exec_params,
                    binding_traces=task.binding_traces,
                )

        # Standard tool execution path
        try:
            resp = self.executor.execute_tool(
                tool_name,
                clean_params,
                trusted_approval=True,
            )
        except Exception as exc:
            logger.exception(f"Unexpected executor exception during resume of '{tool_name}': {exc}")
            resp = BridgeResponse.error(f"Internal dispatcher error: {exc}")

        duration_ms = round((time.time() - t0) * 1000, 2)
        if resp.is_success:
            try:
                task.transition_to(TaskStatus.SUCCEEDED)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=TaskStatus.SUCCEEDED,
                output=resp.result,
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(session.session_id, task.task_id, agent_result)
            self.coordinator.clear_pending_approval(session.session_id, task.task_id)
            task.result = agent_result
            # Advance plan state if task belongs to any tracked plan
            for p in session.plans.values():
                if task.task_id in p.tasks:
                    self.manager.planner.advance_plan_state(p)
            return DispatchResult(
                success=True,
                task_id=task.task_id,
                session_id=session.session_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.SUCCEEDED,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                result=resp.result,
                execution_time_ms=duration_ms,
                resolved_input_params=exec_params,
                binding_traces=task.binding_traces,
            )
        else:
            msg_lower = (resp.message or "").lower()
            if "expired" in msg_lower or "timed out" in msg_lower:
                status = TaskStatus.FAILED
                err_code = "APPROVAL_EXPIRED"
            elif "tamper" in msg_lower:
                status = TaskStatus.AWAITING_APPROVAL
                err_code = "PARAMETER_TAMPERING"
            elif "replay" in msg_lower or "already been consumed" in msg_lower:
                status = TaskStatus.FAILED
                err_code = "DUPLICATE_EXECUTION"
            elif "denied" in msg_lower or "permission" in msg_lower:
                status = TaskStatus.FAILED
                err_code = "PERMISSION_DENIED"
            elif "approval required" in msg_lower:
                status = TaskStatus.AWAITING_APPROVAL
                err_code = "APPROVAL_REQUIRED"
            else:
                status = TaskStatus.FAILED
                err_code = "EXECUTION_FAILED"

            try:
                task.transition_to(status)
            except ValueError:
                pass
            agent_result = AgentResult(
                task_id=task.task_id,
                status=status,
                errors=[resp.message or "Execution failed"],
                execution_time_ms=duration_ms,
            )
            self.coordinator.record_result(session.session_id, task.task_id, agent_result)
            if status == TaskStatus.FAILED:
                self.coordinator.clear_pending_approval(session.session_id, task.task_id)
            task.result = agent_result
            return DispatchResult(
                success=False,
                task_id=task.task_id,
                session_id=session.session_id,
                correlation_id=task.correlation_id,
                status=status,
                agent_id=task.target_agent_id,
                capability_id=task.required_capability,
                error_code=err_code,
                message=resp.message or "Execution failed",
                execution_time_ms=duration_ms,
                resolved_input_params=exec_params,
                binding_traces=task.binding_traces,
            )

    def resolve_pending_approval(
        self,
        task_id: str,
        session_id: str = "default",
        decision: str = "approved",
        nonce: str = "",
        param_hash: str = "",
        auth_token: Optional[str] = None,
    ) -> DispatchResult:
        """
        Resolves a pending operation paused in AWAITING_APPROVAL state with cryptographic nonce,
        canonical parameter hash, session scoping, and optional server authentication token.
        Resumes the original pending task exactly once upon approval.
        """
        t0 = time.time()
        sid = session_id or "default"

        # 1. Server authentication check if configured
        expected_server_token = os.environ.get("UMCP_AUTH_TOKEN")
        if expected_server_token:
            if not auth_token or not secrets.compare_digest(str(auth_token), str(expected_server_token)):
                return DispatchResult(
                    success=False,
                    task_id=task_id,
                    session_id=sid,
                    status=TaskStatus.FAILED,
                    error_code="AUTHENTICATION_FAILED",
                    message="Approval resolution failed: Invalid or missing server auth_token.",
                    execution_time_ms=0.0,
                )

        # Only a Blender registry token issued after a human UI decision may authorize a mutation.
        # MCP task credentials bind the pending task but are not approval evidence.
        correlation_valid, _, validated_binding, _ = self.coordinator.validate_pending_approval(
            session_id=sid,
            task_id=task_id,
            decision=decision,
            nonce=nonce,
            param_hash=param_hash,
        )
        pending_binding = validated_binding if correlation_valid else self.coordinator.get_pending_approval(sid, task_id)
        approval_token = None
        approval_request_id = None
        if decision.lower() == "approved" and correlation_valid:
            if not pending_binding or pending_binding.get("approval_source") != "blender":
                return DispatchResult(
                    success=False,
                    task_id=task_id,
                    session_id=sid,
                    status=TaskStatus.AWAITING_APPROVAL,
                    error_code="TRUSTED_APPROVAL_REQUIRED",
                    message=(
                        "Resolver credentials do not prove human approval. This task can resume only after "
                        "the Blender approval registry records an explicit approval."
                    ),
                    execution_time_ms=round((time.time() - t0) * 1000, 2),
                )
            approval_request_id = pending_binding.get("blender_request_id")
            status_reader = getattr(self.executor, "get_blender_approval_status", None)
            if not approval_request_id or not callable(status_reader):
                return DispatchResult(
                    success=False,
                    task_id=task_id,
                    session_id=sid,
                    status=TaskStatus.AWAITING_APPROVAL,
                    error_code="APPROVAL_STATUS_UNAVAILABLE",
                    message="Cannot verify the Blender approval request; the task remains pending.",
                    execution_time_ms=round((time.time() - t0) * 1000, 2),
                )
            try:
                blender_status = status_reader(approval_request_id)
            except Exception as exc:
                return DispatchResult(
                    success=False,
                    task_id=task_id,
                    session_id=sid,
                    status=TaskStatus.AWAITING_APPROVAL,
                    error_code="APPROVAL_STATUS_UNAVAILABLE",
                    message=f"Cannot verify Blender approval request: {exc}",
                    execution_time_ms=round((time.time() - t0) * 1000, 2),
                )
            blender_decision = str(blender_status.get("status", "")).lower()
            if blender_decision == "pending":
                approval_payload = {
                    "task_id": task_id,
                    "session_id": sid,
                    "tool_name": pending_binding.get("tool_name"),
                    "param_hash": pending_binding.get("param_hash"),
                    "nonce": pending_binding.get("nonce"),
                    "expires_at": pending_binding.get("expires_at"),
                    "approval_request_id": approval_request_id,
                    "approval_status": "pending",
                    "resolution_tool": "resolve_pending_approval",
                }
                return DispatchResult(
                    success=False,
                    task_id=task_id,
                    session_id=sid,
                    correlation_id=pending_binding.get("correlation_id"),
                    status=TaskStatus.AWAITING_APPROVAL,
                    error_code="APPROVAL_REQUIRED",
                    message="Blender has not recorded a human approval yet; the task remains pending.",
                    result={"pending_approval": approval_payload},
                    execution_time_ms=round((time.time() - t0) * 1000, 2),
                )
            if blender_decision == "approved":
                approval_token = blender_status.get("approval_token")
                if not isinstance(approval_token, str) or not approval_token:
                    return DispatchResult(
                        success=False,
                        task_id=task_id,
                        session_id=sid,
                        status=TaskStatus.AWAITING_APPROVAL,
                        error_code="APPROVAL_TOKEN_UNAVAILABLE",
                        message="Blender reports approval but did not provide a valid single-use token.",
                        execution_time_ms=round((time.time() - t0) * 1000, 2),
                    )
            elif blender_decision in ("denied", "cancelled"):
                decision = "denied"
            elif blender_decision == "expired":
                self.coordinator.resolve_pending_approval(
                    session_id=sid,
                    task_id=task_id,
                    decision="approved",
                    nonce=nonce,
                    param_hash=param_hash,
                )
                return DispatchResult(
                    success=False,
                    task_id=task_id,
                    session_id=sid,
                    status=TaskStatus.FAILED,
                    error_code="APPROVAL_EXPIRED",
                    message="Blender approval request expired before human approval.",
                    execution_time_ms=round((time.time() - t0) * 1000, 2),
                )
            else:
                return DispatchResult(
                    success=False,
                    task_id=task_id,
                    session_id=sid,
                    status=TaskStatus.AWAITING_APPROVAL,
                    error_code="APPROVAL_REQUEST_NOT_FOUND",
                    message="The Blender approval request is unavailable; the task remains fail-closed.",
                    execution_time_ms=round((time.time() - t0) * 1000, 2),
                )

        # Coordinator-level validation & resolution (thread-safe, single-use, expiration, nonce/hash check)
        success, code, binding, task = self.coordinator.resolve_pending_approval(
            session_id=sid,
            task_id=task_id,
            decision=decision,
            nonce=nonce,
            param_hash=param_hash,
        )

        duration_ms = round((time.time() - t0) * 1000, 2)

        if not success:
            err_msg_map = {
                "SESSION_NOT_FOUND": f"Session '{sid}' not found.",
                "TASK_NOT_FOUND": f"Task '{task_id}' not found in session '{sid}'.",
                "DUPLICATE_EXECUTION": "Duplicate execution: Task has already completed.",
                "INVALID_TASK_STATE": f"Task '{task_id}' is not in AWAITING_APPROVAL state.",
                "NO_PENDING_APPROVAL": f"No pending approval record found for task '{task_id}'.",
                "REPLAY_ATTACK_DETECTED": f"Replay rejected: Pending approval for task '{task_id}' has already been consumed.",
                "APPROVAL_EXPIRED": f"Approval expired: Pending approval for task '{task_id}' exceeded its time-to-live.",
                "INVALID_NONCE": f"Authorization rejected: Invalid or mismatched nonce for task '{task_id}'.",
                "PARAM_HASH_MISMATCH": f"Authorization rejected: Parameter hash mismatch for task '{task_id}'.",
                "INVALID_DECISION": f"Invalid decision '{decision}'. Expected 'approved' or 'denied'.",
            }
            err_status = TaskStatus.FAILED if code in ("DUPLICATE_EXECUTION", "REPLAY_ATTACK_DETECTED", "APPROVAL_EXPIRED") else (
                task.status if task else TaskStatus.FAILED
            )
            return DispatchResult(
                success=False,
                task_id=task_id,
                session_id=sid,
                correlation_id=task.correlation_id if task else None,
                status=err_status,
                agent_id=task.target_agent_id if task else None,
                capability_id=task.required_capability if task else None,
                error_code=code,
                message=err_msg_map.get(code, f"Approval resolution failed: {code}"),
                execution_time_ms=duration_ms,
                resolved_input_params=task.resolved_input_params if task else None,
                binding_traces=task.binding_traces if task else [],
            )

        # 3. Explicit Denial
        if decision.lower() == "denied":
            return DispatchResult(
                success=False,
                task_id=task_id,
                session_id=sid,
                correlation_id=task.correlation_id if task else None,
                status=TaskStatus.FAILED,
                agent_id=task.target_agent_id if task else None,
                capability_id=task.required_capability if task else None,
                error_code="PERMISSION_DENIED",
                message=f"Scene mutation for task '{task_id}' was explicitly denied by user.",
                execution_time_ms=duration_ms,
                resolved_input_params=task.resolved_input_params if task else None,
                binding_traces=task.binding_traces if task else [],
            )

        # 4. Explicit Approval: Resume the ORIGINAL task exactly once
        return self.resume_task(
            task_id=task_id,
            session_id=sid,
            trusted_approval=True,
            approval_token=approval_token,
            request_id=approval_request_id,
            execution_params=binding.get("raw_params") if binding else task.resolved_input_params,
        )

    def dispatch_tool_call(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> BridgeResponse:
        """
        Adapter method connecting MCP Server call_tool directly to the dispatcher pipeline.
        Converts the resulting DispatchResult into a standard BridgeResponse.
        Correlates matching pending tasks in AWAITING_APPROVAL to prevent duplicate task proliferation.
        Directly routes resolve_pending_approval to secure resolution pipeline.
        """
        arguments = dict(arguments or {})
        sid = session_id or arguments.get("session_id") or "default"
        cid = correlation_id or arguments.get("correlation_id")

        if tool_name == TOOL_CHECK_APPROVAL_STATUS:
            try:
                params = validate_tool_input(TOOL_CHECK_APPROVAL_STATUS, arguments)
            except ValueError as exc:
                return BridgeResponse.error(f"Invalid parameters for {TOOL_CHECK_APPROVAL_STATUS}: {exc}")
            try:
                return BridgeResponse.success(self.executor.inspect_approval_status(params["request_id"]))
            except Exception:
                # Transport/bridge errors may contain private response data.
                return BridgeResponse.error("Approval status unavailable: could not read the authoritative Blender registry.")

        if tool_name == TOOL_GET_TASK_STATUS:
            try:
                validated_args = validate_tool_input(TOOL_GET_TASK_STATUS, arguments)
            except Exception as ve:
                return BridgeResponse.error(f"Invalid parameters for {TOOL_GET_TASK_STATUS}: {ve}")
            status_session = str(validated_args.get("session_id") or sid)
            task_id = str(validated_args.get("task_id", "")).strip()
            if not task_id:
                return BridgeResponse.error(f"Invalid parameters for {TOOL_GET_TASK_STATUS}: task_id is required.")
            return BridgeResponse.success(
                self.coordinator.get_task_status_snapshot(status_session, task_id)
            )

        if tool_name == TOOL_RESOLVE_PENDING_APPROVAL:
            try:
                validated_args = validate_tool_input(TOOL_RESOLVE_PENDING_APPROVAL, arguments)
            except Exception as ve:
                return BridgeResponse.error(f"Invalid parameters for {TOOL_RESOLVE_PENDING_APPROVAL}: {ve}")

            task_id = validated_args.get("task_id", "")
            decision = validated_args.get("decision", "").lower()
            nonce = validated_args.get("nonce", "")
            param_hash = validated_args.get("param_hash", "")
            auth_token = validated_args.get("auth_token")

            dispatch_res = self.resolve_pending_approval(
                task_id=task_id,
                session_id=sid,
                decision=decision,
                nonce=nonce,
                param_hash=param_hash,
                auth_token=auth_token,
            )
            return dispatch_res.to_bridge_response()

        p_hash = compute_param_hash(tool_name, arguments)
        pending_task = self.coordinator.get_pending_task_by_hash(sid, tool_name, p_hash)

        if pending_task:
            task = pending_task
            task.input_params = arguments
        else:
            task_id = str(uuid.uuid4())
            cap_desc = self.registry.find_capability_by_task_type(tool_name)
            cap_id = cap_desc.capability_id if cap_desc else ""

            task = AgentTask(
                task_id=task_id,
                required_capability=cap_id,
                task_type=tool_name,
                input_params=arguments,
                session_id=sid,
                correlation_id=cid,
            )

        dispatch_res = self.dispatch_task(task, session_id=sid, correlation_id=cid)
        return dispatch_res.to_bridge_response()
