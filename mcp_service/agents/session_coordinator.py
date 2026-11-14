"""
Session-Scoped Coordinator for Universal MCP Agent Manager.
Tracks task and plan lifecycles within isolated sessions, handles request deduplication
via correlation IDs, and manages thread-safe lifecycle transitions and TTL cleanup.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import threading
import time
import uuid
import secrets

from shared.models.protocol_models import render_job_failure_snapshot

from shared.models.agent_contracts import (
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
)


@dataclass
class SessionContext:
    """
    Isolated session state holding task graphs, task statuses, correlation mappings,
    and structured execution results.
    """
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    tasks: Dict[str, AgentTask] = field(default_factory=dict)
    plans: Dict[str, TaskPlan] = field(default_factory=dict)
    correlation_to_task: Dict[str, str] = field(default_factory=dict)
    task_results: Dict[str, AgentResult] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    pending_approvals: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def touch(self) -> None:
        """Updates last_active_at timestamp."""
        self.last_active_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes session summary metadata."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "task_count": len(self.tasks),
            "plan_count": len(self.plans),
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "plans": {pid: p.to_dict() for pid, p in self.plans.items()},
            "metadata": self.metadata,
        }


class SessionCoordinator:
    """
    Thread-safe session coordinator managing isolated session contexts.
    Guarantees cross-session isolation, deterministic correlation deduplication,
    and automatic or manual session expiration.
    """

    def __init__(self, default_ttl_seconds: float = 3600.0):
        self.default_ttl_seconds: float = max(1.0, float(default_ttl_seconds))
        self._sessions: Dict[str, SessionContext] = {}
        self._lock: threading.RLock = threading.RLock()

    def get_or_create_session(self, session_id: Optional[str] = None) -> SessionContext:
        """
        Retrieves an existing session or creates a new one.
        Thread-safe; updates last_active_at on access.
        """
        sid = (str(session_id).strip() if session_id else "") or str(uuid.uuid4())
        with self._lock:
            if sid not in self._sessions:
                self._sessions[sid] = SessionContext(session_id=sid)
            else:
                self._sessions[sid].touch()
            return self._sessions[sid]

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Retrieves a session context by ID without creating one."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.touch()
            return session

    def has_session(self, session_id: str) -> bool:
        """Checks if a session is currently registered."""
        with self._lock:
            return session_id in self._sessions

    def close_session(self, session_id: str) -> bool:
        """Explicitly closes and removes a session."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def cleanup_expired_sessions(self, max_age_seconds: Optional[float] = None) -> int:
        """
        Evicts sessions that have been inactive longer than max_age_seconds (or default_ttl_seconds).
        Returns the number of evicted sessions.
        """
        ttl = self.default_ttl_seconds if max_age_seconds is None else max(0.01, float(max_age_seconds))
        now = time.time()
        evicted = 0
        with self._lock:
            to_remove = [
                sid for sid, s in self._sessions.items()
                if (now - s.last_active_at) > ttl
            ]
            for sid in to_remove:
                del self._sessions[sid]
                evicted += 1
        return evicted

    def track_task(
        self,
        session_id: str,
        task: AgentTask,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Registers an AgentTask in the specified session and maps optional correlation ID.
        """
        with self._lock:
            session = self.get_or_create_session(session_id)
            task.session_id = session.session_id
            if correlation_id:
                task.correlation_id = correlation_id
                session.correlation_to_task[correlation_id] = task.task_id
            session.tasks[task.task_id] = task
            session.touch()

    def get_task(self, session_id: str, task_id: str) -> Optional[AgentTask]:
        """Retrieves a task by task_id within the given session context."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            return session.tasks.get(task_id)

    def get_task_status_snapshot(self, session_id: str, task_id: str) -> Dict[str, Any]:
        """Returns a sanitized task-status snapshot without touching session state."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {"found": False, "task_id": task_id, "session_id": session_id, "status": "session_not_found"}

            task = session.tasks.get(task_id)
            if task is None:
                return {"found": False, "task_id": task_id, "session_id": session_id, "status": "task_not_found"}

            task_status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status)
            snapshot: Dict[str, Any] = {
                "found": True,
                "task_id": task.task_id,
                "session_id": session.session_id,
                "task_type": task.task_type,
                "status": task_status,
                "is_terminal": task.is_terminal,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }

            binding = session.pending_approvals.get(task_id) or task.approval_binding
            if task_status == TaskStatus.AWAITING_APPROVAL.value:
                approval_state = "unverified"
                expires_at = None
                request_id = None
                if binding:
                    expires_at = binding.get("expires_at")
                    request_id = binding.get("blender_request_id")
                    if expires_at and time.time() >= float(expires_at):
                        approval_state = "expired"
                snapshot["approval"] = {
                    "state": approval_state,
                    "request_id": request_id,
                    "expires_at": expires_at,
                }
                snapshot["next_action"] = (
                    "After approving in Blender, call resolve_pending_approval with the resolver fields "
                    "from the original pending response. This query does not resume the task."
                )

            result = task.result
            if result is not None:
                result_status = result.status.value if isinstance(result.status, TaskStatus) else str(result.status)
                result_snapshot: Dict[str, Any] = {
                    "status": result_status,
                    "execution_time_ms": result.execution_time_ms,
                }
                # Errors from a paused run describe the state at pause time and
                # can become stale after the human approves in Blender.
                if task.is_terminal:
                    result_snapshot["errors"] = list(result.errors)
                if result.verification is not None:
                    observed = result.verification.observed_results or {}
                    result_snapshot["verification"] = {
                        "status": result.verification.status,
                        "details": result.verification.details,
                        "error_code": observed.get("error_code"),
                    }
                    if task.task_type == "render_scene" and task_status == TaskStatus.FAILED.value:
                        raw_job = observed.get("render_job")
                        if isinstance(raw_job, dict):
                            job = render_job_failure_snapshot(raw_job.get("error_code"), raw_job.get("execution_state_at_response"))
                            if job is not None:
                                result_snapshot["verification"]["render_job"] = job
                                snapshot["next_action"] = (
                                    "This is evidence at the failed response, not current Blender execution status. "
                                    "If reconciliation is required, inspect actual scene/output after Blender finishes. "
                                    "This query does not poll Blender, cancel execution or retry rendering."
                                )
                output = result.output
                if isinstance(output, dict):
                    safe_keys = ("name", "material_name", "action", "created", "target", "target_name", "slot_index")
                    output_summary = {key: output[key] for key in safe_keys if key in output}
                    if output_summary:
                        result_snapshot["output_summary"] = output_summary
                snapshot["result"] = result_snapshot

            return snapshot

    def get_task_by_correlation(
        self,
        session_id: str,
        correlation_id: str,
    ) -> Optional[AgentTask]:
        """
        Retrieves a task previously registered with the given correlation_id in this session.
        Prevents cross-session task leakage by strictly scoping lookup to session_id.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            task_id = session.correlation_to_task.get(correlation_id)
            if not task_id:
                return None
            return session.tasks.get(task_id)

    def record_result(
        self,
        session_id: str,
        task_id: str,
        result: AgentResult,
    ) -> None:
        """
        Stores structured AgentResult for a task and updates the task instance.
        """
        with self._lock:
            session = self.get_or_create_session(session_id)
            session.task_results[task_id] = result
            task = session.tasks.get(task_id)
            if task:
                task.result = result
                if result.status and task.status != result.status:
                    try:
                        task.transition_to(result.status)
                    except ValueError:
                        pass
            session.touch()

    def track_plan(self, session_id: str, plan: TaskPlan) -> None:
        """Registers a TaskPlan in the specified session context."""
        with self._lock:
            session = self.get_or_create_session(session_id)
            session.plans[plan.plan_id] = plan
            for tid, t in plan.tasks.items():
                session.tasks[tid] = t
            session.touch()

    def get_plan(self, session_id: str, plan_id: str) -> Optional[TaskPlan]:
        """Retrieves a TaskPlan by plan_id within the given session context."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            return session.plans.get(plan_id)

    def list_active_sessions(self) -> List[str]:
        """Returns list of all active session IDs."""
        with self._lock:
            return list(self._sessions.keys())

    @property
    def active_session_count(self) -> int:
        """Returns count of active sessions."""
        with self._lock:
            return len(self._sessions)

    def record_pending_approval(
        self,
        session_id: str,
        task_id: str,
        binding: Dict[str, Any],
    ) -> None:
        """Stores a pending approval binding record for a task."""
        with self._lock:
            session = self.get_or_create_session(session_id)
            session.pending_approvals[task_id] = dict(binding)
            task = session.tasks.get(task_id)
            if task:
                task.approval_binding = dict(binding)
            session.touch()

    def get_pending_approval(
        self,
        session_id: str,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the pending approval binding for a task in the session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            return session.pending_approvals.get(task_id)

    def clear_pending_approval(
        self,
        session_id: str,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Removes and returns the pending approval record once resolved or terminal."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            binding = session.pending_approvals.pop(task_id, None)
            task = session.tasks.get(task_id)
            if task and task.approval_binding:
                task.approval_binding = None
            session.touch()
            return binding

    def get_pending_task_by_hash(
        self,
        session_id: str,
        tool_name: str,
        param_hash: str,
    ) -> Optional[AgentTask]:
        """
        Finds an active pending task in AWAITING_APPROVAL state with matching tool_name and parameter hash.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            for tid, binding in session.pending_approvals.items():
                if binding.get("tool_name") == tool_name and binding.get("param_hash") == param_hash:
                    task = session.tasks.get(tid)
                    if task and task.status == TaskStatus.AWAITING_APPROVAL:
                        return task
            return None

    def resolve_pending_approval(
        self,
        session_id: str,
        task_id: str,
        decision: str,
        nonce: str,
        param_hash: str,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[AgentTask]]:
        """
        Thread-safely validates and resolves a pending approval.
        Verifies task existence, AWAITING_APPROVAL status, single-use nonce,
        canonical param_hash, and expiration.
        Returns (success: bool, status_code: str, binding: Optional[dict], task: Optional[AgentTask]).
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False, "SESSION_NOT_FOUND", None, None

            task = session.tasks.get(task_id)
            if not task:
                return False, "TASK_NOT_FOUND", None, None

            if task.is_terminal:
                return False, "DUPLICATE_EXECUTION", None, task

            if task.status != TaskStatus.AWAITING_APPROVAL:
                return False, "INVALID_TASK_STATE", None, task

            binding = session.pending_approvals.get(task_id) or task.approval_binding
            if not binding:
                return False, "NO_PENDING_APPROVAL", None, task

            # Replay check: has nonce already been consumed?
            if binding.get("consumed", False):
                return False, "REPLAY_ATTACK_DETECTED", binding, task

            # Expiration check (TTL)
            expires_at = binding.get("expires_at", 0.0)
            if expires_at and time.time() > expires_at:
                binding["consumed"] = True
                try:
                    task.transition_to(TaskStatus.FAILED)
                except ValueError:
                    pass
                return False, "APPROVAL_EXPIRED", binding, task

            # Constant-time nonce check
            expected_nonce = str(binding.get("nonce", "")).strip()
            if not expected_nonce or not secrets.compare_digest(str(nonce).strip(), expected_nonce):
                return False, "INVALID_NONCE", binding, task

            # Constant-time param_hash check
            expected_hash = str(binding.get("param_hash", "")).strip()
            if not expected_hash or not secrets.compare_digest(str(param_hash).strip(), expected_hash):
                return False, "PARAM_HASH_MISMATCH", binding, task

            # Decision handling
            norm_decision = str(decision).strip().lower()
            if norm_decision == "denied":
                binding["consumed"] = True
                try:
                    task.transition_to(TaskStatus.FAILED)
                except ValueError:
                    pass
                session.pending_approvals.pop(task_id, None)
                if task.approval_binding:
                    task.approval_binding["consumed"] = True
                session.touch()
                return True, "DENIED", binding, task
            elif norm_decision == "approved":
                binding["consumed"] = True
                if task.approval_binding:
                    task.approval_binding["consumed"] = True
                session.touch()
                return True, "APPROVED", binding, task
            else:
                return False, "INVALID_DECISION", binding, task

    def validate_pending_approval(
        self,
        session_id: str,
        task_id: str,
        decision: str,
        nonce: str,
        param_hash: str,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[AgentTask]]:
        """Validate approval correlation fields without consuming a pending binding."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False, "SESSION_NOT_FOUND", None, None
            task = session.tasks.get(task_id)
            if not task:
                return False, "TASK_NOT_FOUND", None, None
            if task.is_terminal:
                return False, "DUPLICATE_EXECUTION", None, task
            if task.status != TaskStatus.AWAITING_APPROVAL:
                return False, "INVALID_TASK_STATE", None, task
            binding = session.pending_approvals.get(task_id) or task.approval_binding
            if not binding:
                return False, "NO_PENDING_APPROVAL", None, task
            if binding.get("consumed", False):
                return False, "REPLAY_ATTACK_DETECTED", binding, task
            expires_at = binding.get("expires_at", 0.0)
            if expires_at and time.time() > expires_at:
                return False, "APPROVAL_EXPIRED", binding, task
            expected_nonce = str(binding.get("nonce", "")).strip()
            if not expected_nonce or not secrets.compare_digest(str(nonce).strip(), expected_nonce):
                return False, "INVALID_NONCE", binding, task
            expected_hash = str(binding.get("param_hash", "")).strip()
            if not expected_hash or not secrets.compare_digest(str(param_hash).strip(), expected_hash):
                return False, "PARAM_HASH_MISMATCH", binding, task
            if str(decision).strip().lower() not in ("approved", "denied"):
                return False, "INVALID_DECISION", binding, task
            return True, "VALID", binding, task
