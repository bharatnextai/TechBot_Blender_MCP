"""
Trusted Approval Manager for Universal MCP.
Enforces the boundary between untrusted model arguments and trusted human consent.
Connects external MCP requests to the Blender-native approval interface over the loopback bridge.
"""

from typing import Dict, Any, Optional, Callable, Tuple, Union
import hashlib
import json
import logging
import os
import time

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    PERMISSION_READ_ONLY,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_DESTRUCTIVE,
)

logger = logging.getLogger("UniversalMCP.Approval")


def compute_param_hash(tool_name: str, params: Dict[str, Any]) -> str:
    """
    Computes a deterministic SHA-256 hash of tool name and parameters.
    Excludes untrusted flags and metadata to ensure exact parameter binding.
    Matches the canonical hash computation of the Blender ApprovalRegistry.
    """
    clean_params = {
        k: v for k, v in params.items()
        if k not in (
            "approved", "trusted_approval", "_trusted_approval",
            "approval_token", "request_id", "task_id", "session_id", "correlation_id"
        )
    }
    payload_str = f"{tool_name}:{json.dumps(clean_params, sort_keys=True)}"
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


class ApprovalDecision(tuple):
    """
    Subclasses tuple so that (approved, reason) unpacking works identically for backward compatibility:
        is_approved, reason = verify_approval(...)
    while also exposing credentials:
        decision.request_id, decision.approval_token
    """
    def __new__(
        cls,
        approved: bool,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
        approval_token: Optional[str] = None,
        status: Optional[str] = None,
        expires_at: Optional[float] = None,
    ):
        return super().__new__(cls, (approved, reason))

    def __init__(
        self,
        approved: bool,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
        approval_token: Optional[str] = None,
        status: Optional[str] = None,
        expires_at: Optional[float] = None,
    ):
        self.approved: bool = approved
        self.reason: Optional[str] = reason
        self.request_id: Optional[str] = request_id
        self.approval_token: Optional[str] = approval_token
        self.status: Optional[str] = status
        self.expires_at: Optional[float] = expires_at

    def __bool__(self) -> bool:
        return self.approved


ApprovalCallback = Callable[[str, Dict[str, Any]], Union[bool, Tuple[bool, Optional[str]], ApprovalDecision]]


class ApprovalManager:
    """
    Manages trusted user approval for scene mutations.

    Trust Boundary:
    - Model arguments (including any 'approved' flag passed in JSON-RPC) are UNTRUSTED.
    - Approval must come from a trusted approval provider (e.g. Blender human-in-the-loop dialog,
      registered user-prompt callback, or secure pre-authorization ticket).
    - If no trusted approval mechanism exists, all mutations are rejected by default.
    """

    def __init__(self, provider: Optional[ApprovalCallback] = None):
        self._provider: Optional[ApprovalCallback] = provider

    @property
    def has_provider(self) -> bool:
        """Returns True if a trusted approval provider is registered."""
        return self._provider is not None

    def set_provider(self, provider: Optional[ApprovalCallback]) -> None:
        """Sets or unregisters the trusted approval provider callback."""
        self._provider = provider

    def requires_approval(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """Checks if a tool belongs to a mutation or destructive permission tier."""
        if arguments and arguments.get("action") in ("list_nodes", "inspect", "inspect_nodes"):
            return False
        tool_def = TOOL_DEFINITIONS.get(tool_name, {})
        tier = tool_def.get("permission_tier", PERMISSION_READ_ONLY)
        return tier in (PERMISSION_SCENE_MUTATION, PERMISSION_DESTRUCTIVE)

    def verify_approval(
        self,
        tool_name: str,
        untrusted_arguments: Dict[str, Any],
    ) -> ApprovalDecision:
        """
        Verifies whether the tool execution has trusted human approval.

        Returns:
            ApprovalDecision (unpacks as (is_approved: bool, error_message: Optional[str]))
        """
        # Read-only tools and read-only actions within mutation-tier tools never require mutation approval
        if not self.requires_approval(tool_name, untrusted_arguments):
            return ApprovalDecision(True, None)

        # Check for untrusted model bypass attempt
        model_attempted_bypass = (
            untrusted_arguments.get("approved") is True or
            untrusted_arguments.get("trusted_approval") is True
        )

        # Check if a trusted approval mechanism exists
        if self._provider is None:
            if model_attempted_bypass:
                msg = (
                    f"Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize "
                    f"scene mutation '{tool_name}'. Explicit user approval must be granted through "
                    f"a trusted approval mechanism. No trusted approval mechanism is currently configured."
                )
            else:
                msg = (
                    f"Approval required: Scene mutation '{tool_name}' requires explicit user approval "
                    f"through a trusted approval mechanism. No trusted approval mechanism is currently configured. "
                    f"The system operates in read-only mode by default."
                )
            return ApprovalDecision(False, msg)

        # Invoke trusted approval provider
        try:
            raw_result = self._provider(tool_name, untrusted_arguments)
        except Exception as e:
            logger.exception(f"Error in trusted approval provider for '{tool_name}': {e}")
            return ApprovalDecision(False, f"Approval error: Trusted approval provider raised an exception: {e}")

        # Normalize provider result to ApprovalDecision
        if isinstance(raw_result, ApprovalDecision):
            decision = raw_result
        elif isinstance(raw_result, tuple):
            decision = ApprovalDecision(bool(raw_result[0]), raw_result[1] if len(raw_result) > 1 else None)
        elif isinstance(raw_result, bool):
            decision = ApprovalDecision(
                raw_result,
                "Explicitly approved by user" if raw_result else f"Approval denied: User or trusted approval provider denied scene mutation '{tool_name}'."
            )
        else:
            decision = ApprovalDecision(False, f"Invalid approval provider response type: {type(raw_result).__name__}")

        if decision.approved:
            return decision
        else:
            if model_attempted_bypass:
                reason = (
                    f"Approval denied: User or trusted approval provider denied scene mutation '{tool_name}'. "
                    f"Model-supplied argument 'approved=True' was rejected as untrusted."
                )
                return ApprovalDecision(False, reason, request_id=decision.request_id)
            return decision


def create_blender_bridge_approval_provider(
    bridge_client,
    timeout: float = 30.0,
    pending_ttl: float = 300.0,
) -> ApprovalCallback:
    """
    Creates an approval provider that connects to the Blender-native approval interface
    over the loopback TCP bridge.
    Executes an asynchronous pending-request workflow via check_approval_status polling
    so Blender's main event thread and UI remain 100% responsive.
    """
    def provider(tool_name: str, arguments: Dict[str, Any]) -> ApprovalDecision:
        try:
            # 1. Request approval in Blender
            task_id = arguments.get("task_id") or arguments.get("session_id")
            env_ttl = os.environ.get("UMCP_APPROVAL_PENDING_TTL")
            effective_pending_ttl = float(env_ttl) if env_ttl else float(pending_ttl)
            request_timeout = effective_pending_ttl if env_ttl else max(float(timeout), effective_pending_ttl)
            req_payload = {
                "tool_name": tool_name,
                "params": arguments,
                "timeout": request_timeout,
            }
            if task_id:
                req_payload["task_id"] = task_id

            resp = bridge_client.send_command("request_approval", req_payload)
            if resp.get("status") != "success":
                err_msg = resp.get("message", "Failed to initiate approval request in Blender.")
                return ApprovalDecision(False, f"Approval error: {err_msg}")

            result_data = resp.get("result", {})
            req_id = result_data.get("request_id")
            if not req_id:
                return ApprovalDecision(False, "Approval error: Blender did not return a valid request_id.")

            # Immediate auto-approval check (when Require Scene Mutation Approval is OFF)
            if result_data.get("status") == "approved" and result_data.get("approval_token"):
                return ApprovalDecision(
                    True,
                    "Automatically approved (Require Scene Mutation Approval is disabled)",
                    request_id=req_id,
                    approval_token=result_data.get("approval_token"),
                    status="approved",
                    expires_at=result_data.get("expires_at"),
                )

            # 2. Asynchronously poll check_approval_status without blocking Blender
            t_start = time.time()
            poll_interval = 0.1
            while (time.time() - t_start) < (timeout + 2.0):
                status_resp = bridge_client.send_command("check_approval_status", {"request_id": req_id})
                if status_resp.get("status") == "success":
                    s_data = status_resp.get("result", {})
                    st = s_data.get("status")
                    if st == "approved":
                        token = s_data.get("approval_token")
                        return ApprovalDecision(
                            True,
                            "Approved by user in Blender",
                            request_id=req_id,
                            approval_token=token,
                            status="approved",
                            expires_at=s_data.get("expires_at"),
                        )
                    elif st == "denied":
                        reason = s_data.get("decision_reason") or "User explicitly clicked Deny in Blender"
                        return ApprovalDecision(False, f"Approval denied: {reason}", request_id=req_id, status="denied")
                    elif st == "cancelled":
                        reason = s_data.get("decision_reason") or "User cancelled or closed the approval dialog"
                        return ApprovalDecision(False, f"Approval cancelled: {reason}", request_id=req_id, status="cancelled")
                    elif st == "expired":
                        return ApprovalDecision(False, f"Approval timed out after {request_timeout}s", request_id=req_id, status="expired")
                time.sleep(poll_interval)

            return ApprovalDecision(
                False,
                f"Approval is still pending in Blender after waiting {timeout}s.",
                request_id=req_id,
                status="pending",
                expires_at=result_data.get("expires_at"),
            )
        except Exception as e:
            return ApprovalDecision(False, f"Error communicating with Blender approval interface: {e}")

    return provider
