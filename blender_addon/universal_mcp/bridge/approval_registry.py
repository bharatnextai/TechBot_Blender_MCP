"""
Approval Registry and Pending Request Store for Universal MCP in Blender.
Manages the lifecycle of human approval requests for scene mutations.
Pure Python standard library only (zero external pip dependencies).
"""

import hashlib
import json
import secrets
import threading
import time
from typing import Dict, Any, Optional, Tuple, List


RECENT_REQUEST_RETENTION_SECONDS = 3600.0
RECENT_REQUEST_HISTORY_LIMIT = 100


def compute_arg_hash(tool_name: str, params: Dict[str, Any]) -> str:
    """
    Computes a deterministic SHA-256 hash of tool name and parameters.
    Excludes untrusted flags and metadata to ensure exact parameter binding.
    """
    clean_params = {
        k: v for k, v in params.items()
        if k not in (
            "approved", "trusted_approval", "_trusted_approval",
            "approval_token", "request_id", "task_id", "session_id"
        )
    }
    payload_str = f"{tool_name}:{json.dumps(clean_params, sort_keys=True)}"
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


class ApprovalRequest:
    """Represents a single pending human approval request."""

    def __init__(
        self,
        request_id: str,
        tool_name: str,
        params: Dict[str, Any],
        timeout_seconds: float = 30.0,
        task_id: Optional[str] = None,
    ):
        self.request_id: str = request_id
        self.tool_name: str = tool_name
        self.params: Dict[str, Any] = dict(params)
        self.task_id: Optional[str] = (
            task_id or
            params.get("task_id") or
            params.get("session_id")
        )
        self.arg_hash: str = compute_arg_hash(tool_name, params)
        self.created_at: float = time.time()
        self.timeout_seconds: float = max(0.01, float(timeout_seconds))
        self.status: str = "pending"  # pending, approved, denied, cancelled, expired
        self.decision_reason: Optional[str] = None
        self.approval_token: Optional[str] = None
        self.event: threading.Event = threading.Event()
        self.executed: bool = False

    @property
    def is_expired(self) -> bool:
        """Checks if request has exceeded its configured timeout."""
        return (time.time() - self.created_at) > self.timeout_seconds

    @property
    def remaining_seconds(self) -> float:
        """Returns remaining seconds before timeout."""
        return max(0.0, self.timeout_seconds - (time.time() - self.created_at))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes request metadata for UI and protocol reporting."""
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "task_id": self.task_id,
            "params": self.params,
            "arg_hash": self.arg_hash,
            "created_at": self.created_at,
            "timeout_seconds": self.timeout_seconds,
            "remaining_seconds": round(self.remaining_seconds, 1),
            "status": self.status,
            "decision_reason": self.decision_reason,
            "executed": self.executed,
        }


class ApprovalRequestSnapshot:
    """Token-free terminal request metadata retained briefly for UI diagnostics."""

    def __init__(self, request: ApprovalRequest):
        self.request_id = request.request_id
        self.tool_name = request.tool_name
        self.params = dict(request.params)
        self.task_id = request.task_id
        self.arg_hash = request.arg_hash
        self.created_at = request.created_at
        self.timeout_seconds = request.timeout_seconds
        self.status = request.status
        self.decision_reason = request.decision_reason
        self.approval_token = None
        self.executed = request.executed

    @property
    def is_expired(self) -> bool:
        return self.status == "expired" or (time.time() - self.created_at) > self.timeout_seconds

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.timeout_seconds - (time.time() - self.created_at))


class ApprovalRegistry:
    """
    Thread-safe registry managing pending mutation approval requests.
    Enforces replay rejection, tampering checks, and fail-closed timeout logic.
    Supports task-level grouping and optional auto-approval setting.
    """

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}
        self._recent_requests: Dict[str, ApprovalRequestSnapshot] = {}
        self._tokens: Dict[str, str] = {}  # token -> request_id
        self._lock: threading.Lock = threading.Lock()
        self.require_scene_mutation_approval: bool = True

    def create_request(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: float = 30.0,
        request_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> ApprovalRequest:
        """Creates and stores a new pending approval request."""
        with self._lock:
            # Clean up old expired requests
            self._cleanup_expired_locked()

            req_id = request_id or secrets.token_hex(8)
            t_id = task_id or params.get("task_id") or params.get("session_id")
            req = ApprovalRequest(
                request_id=req_id,
                tool_name=tool_name,
                params=params,
                timeout_seconds=timeout,
                task_id=t_id,
            )
            self._requests[req_id] = req
            return req

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Retrieves an approval request by ID."""
        with self._lock:
            req = self._requests.get(request_id)
            if req and req.status == "pending" and req.is_expired:
                req.status = "expired"
                req.decision_reason = f"Request timed out after {req.timeout_seconds}s"
                req.event.set()
            return req

    def get_request_for_status(self, request_id: str):
        """Return live or retained terminal state without exposing archived tokens."""
        with self._lock:
            req = self._requests.get(request_id)
            if req and req.status == "pending" and req.is_expired:
                req.status = "expired"
                req.decision_reason = f"Request timed out after {req.timeout_seconds}s"
                req.event.set()
            if req is not None:
                return req
            snapshot = self._recent_requests.get(request_id)
            if snapshot and (time.time() - snapshot.created_at) <= RECENT_REQUEST_RETENTION_SECONDS:
                return snapshot
            return None

    def inspect_request_status(self, request_id: str) -> Dict[str, Any]:
        """Return a token-free projection without expiry transitions or cleanup."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("Approval status request_id must be a non-empty string.")
        request_id = request_id.strip()
        with self._lock:
            now = time.time()
            req = self._requests.get(request_id)
            source = "live"
            if req is None:
                req = self._recent_requests.get(request_id)
                source = "archive"
                if req is not None and now - req.created_at > RECENT_REQUEST_RETENTION_SECONDS:
                    req = None
            if req is None:
                return {"request_id": request_id, "status": "not_found"}
            expires_at = req.created_at + req.timeout_seconds
            status = req.status
            if status == "pending" and now > expires_at:
                status = "expired"
            if status not in {"pending", "approved", "denied", "cancelled", "expired"}:
                status = "unknown"
            return {
                "request_id": req.request_id,
                "status": status,
                "tool_name": req.tool_name,
                "task_id": req.task_id,
                "arg_hash": req.arg_hash,
                "expires_at": expires_at,
                "remaining_seconds": round(max(0.0, expires_at - now), 1),
                "token_consumed": bool(req.executed),
                "record_source": source,
            }

    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Returns list of currently active pending requests."""
        with self._lock:
            self._cleanup_expired_locked()
            return [req for req in self._requests.values() if req.status == "pending" and not req.is_expired]

    def get_recent_requests(self, limit: int = 20) -> List[ApprovalRequest]:
        """Returns recent requests, including terminal states retained for diagnostics."""
        with self._lock:
            self._cleanup_expired_locked()
            recent = sorted(
                [*self._requests.values(), *self._recent_requests.values()],
                key=lambda req: req.created_at,
                reverse=True,
            )
            return recent[:max(0, int(limit))]

    def get_pending_requests_for_task(self, task_id: str) -> List[ApprovalRequest]:
        """Returns list of active pending requests matching a specific task_id."""
        with self._lock:
            self._cleanup_expired_locked()
            return [
                req for req in self._requests.values()
                if req.status == "pending" and not req.is_expired and req.task_id == task_id
            ]

    def resolve_request(
        self,
        request_id: str,
        decision: str,  # 'approved', 'denied', 'cancelled'
        reason: Optional[str] = None,
        approve_task_group: bool = True,
    ) -> Tuple[bool, str]:
        """
        Resolves a pending request with a human decision.
        Fails closed on expired or already resolved requests.
        When decision is 'approved' and approve_task_group is True:
        Approves all eligible pending requests belonging to the same active task group.
        Does not approve unrelated tasks, expired requests, or already-resolved requests.
        Deny behavior remains unchanged (affects only the target request).
        """
        with self._lock:
            req = self._requests.get(request_id)
            if not req:
                return False, f"Request '{request_id}' not found."

            if req.status != "pending":
                return False, f"Duplicate decision rejected: Request '{request_id}' is already resolved as '{req.status}'."

            if req.is_expired:
                req.status = "expired"
                req.decision_reason = f"Request timed out after {req.timeout_seconds}s"
                req.event.set()
                return False, "Approval expired: Decision made after timeout window."

            decision = decision.lower().strip()
            if decision == "approved":
                token = secrets.token_hex(16)
                req.status = "approved"
                req.approval_token = token
                req.decision_reason = reason or "Explicitly approved by user"
                self._tokens[token] = request_id
                req.event.set()

                # Approve all eligible pending requests in the same active task group
                if approve_task_group and req.task_id:
                    for other_id, other_req in list(self._requests.items()):
                        if other_id == request_id:
                            continue
                        # Match exact non-empty task_id
                        if other_req.task_id == req.task_id:
                            if other_req.status == "pending":
                                if other_req.is_expired:
                                    other_req.status = "expired"
                                    other_req.decision_reason = f"Request timed out after {other_req.timeout_seconds}s"
                                    other_req.event.set()
                                else:
                                    other_token = secrets.token_hex(16)
                                    other_req.status = "approved"
                                    other_req.approval_token = other_token
                                    other_req.decision_reason = (
                                        reason or f"Approved as part of active task group '{req.task_id}'"
                                    )
                                    self._tokens[other_token] = other_id
                                    other_req.event.set()

                return True, token
            elif decision in ("denied", "cancelled"):
                req.status = decision
                req.decision_reason = reason or f"Explicitly {decision} by user"
                req.event.set()
                return True, f"Request {decision}"
            else:
                return False, f"Invalid decision '{decision}'. Must be 'approved', 'denied', or 'cancelled'."


    def consume_approval(
        self,
        request_id: Optional[str],
        token: Optional[str],
        tool_name: str,
        execution_params: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Validates and consumes an approval token for scene mutation.
        Enforces:
        - Valid token and request ID binding
        - Single-use consumption (rejects replay attacks)
        - Argument tampering checks (SHA-256 hash match)
        - Expiration window
        """
        if not request_id or not token:
            return False, "Missing approval credentials: Both request_id and approval_token are required."

        with self._lock:
            req = self._requests.get(request_id)
            if not req:
                return False, f"Invalid approval: Request ID '{request_id}' not found."

            if req.status != "approved":
                return False, f"Approval rejected: Request status is '{req.status}', expected 'approved'."

            if req.approval_token != token:
                return False, "Invalid approval: Token does not match requested approval record."

            # Replay protection: Token can only be consumed once
            if req.executed:
                return False, f"Replay rejected: Approval token for request '{request_id}' has already been consumed."

            # Expiration window check (approval valid for execution up to 60s past creation)
            max_validity = req.timeout_seconds + 60.0
            if (time.time() - req.created_at) > max_validity:
                return False, f"Approval expired: Approval token exceeded maximum validity of {max_validity}s."

            # Argument tampering check: Verify exact parameters match what user approved
            current_hash = compute_arg_hash(tool_name, execution_params)
            if current_hash != req.arg_hash:
                return False, (
                    f"Argument tampering detected: Execution parameters do not match approved parameters. "
                    f"Expected hash {req.arg_hash[:12]}..., got {current_hash[:12]}..."
                )

            # Task correlation check: If request has task_id and execution parameters specify task_id, they must match
            exec_task_id = execution_params.get("task_id") or execution_params.get("session_id")
            if req.task_id and exec_task_id and req.task_id != exec_task_id:
                return False, (
                    f"Task correlation mismatch: Approval token belongs to task '{req.task_id}', "
                    f"but execution requested task '{exec_task_id}'."
                )

            # Mark as consumed
            req.executed = True
            return True, "Approval verified and consumed successfully."

    def cancel_all(self, reason: str = "System shutdown / unregister"):
        """Fails closed all pending requests during shutdown."""
        with self._lock:
            for req in self._requests.values():
                if req.status == "pending":
                    req.status = "cancelled"
                    req.decision_reason = reason
                    req.event.set()

    def _cleanup_expired_locked(self):
        """Internal helper to mark expired requests and purge stale items (> 10 mins old)."""
        now = time.time()
        stale_ids = []
        for req_id, req in self._requests.items():
            if req.status == "pending" and req.is_expired:
                req.status = "expired"
                req.decision_reason = "Timeout expired"
                req.event.set()
            # Never evict a request that is still actively pending. Its
            # configured timeout may legitimately exceed the diagnostic
            # history window.
            if (now - req.created_at) > 600.0 and req.status != "pending":
                stale_ids.append(req_id)

        for sid in stale_ids:
            req = self._requests.pop(sid, None)
            if req:
                # Keep terminal metadata for UI/status diagnostics, but never
                # retain an archived authorization token.
                if req.status != "pending":
                    self._recent_requests[sid] = ApprovalRequestSnapshot(req)
                if req.approval_token:
                    self._tokens.pop(req.approval_token, None)

        cutoff = now - RECENT_REQUEST_RETENTION_SECONDS
        for req_id, snapshot in list(self._recent_requests.items()):
            if snapshot.created_at < cutoff:
                self._recent_requests.pop(req_id, None)
        if len(self._recent_requests) > RECENT_REQUEST_HISTORY_LIMIT:
            oldest = sorted(
                self._recent_requests.values(), key=lambda item: item.created_at
            )[:len(self._recent_requests) - RECENT_REQUEST_HISTORY_LIMIT]
            for snapshot in oldest:
                self._recent_requests.pop(snapshot.request_id, None)


# Global singleton instance for the add-on
_global_registry: Optional[ApprovalRegistry] = None


def get_approval_registry() -> ApprovalRegistry:
    """Returns the process-wide ApprovalRegistry singleton."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ApprovalRegistry()
    return _global_registry
