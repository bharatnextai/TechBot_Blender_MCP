"""
Blender Executor for the external MCP Service.
Bridges external MCP tool calls to Blender over the loopback socket bridge.
"""

from typing import Dict, Any, Optional
import time
import math

from blender_addon.universal_mcp.bridge.bridge_client import BridgeClient, DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT
from shared.schemas.tool_schemas import validate_tool_input, TOOL_DEFINITIONS
from shared.models.protocol_models import BridgeResponse, render_job_failure_snapshot
from ..security.approval import ApprovalManager
from blender_addon.universal_mcp.bridge.mesh_topology import validate_snapshot_id, MAX_PAGE_INDICES

_MODELING_BRIDGE_TOOLS = frozenset({
    "edit_modifier_stack", "inspect_modifier_stack", "configure_curve_geometry", "inspect_curve_geometry",
    "configure_modeling_object", "inspect_modeling_object", "configure_modeling_geometry", "inspect_modeling_geometry",
})

def verify_indexed_topology_response(result, params):
    """Reject older bridges which acknowledge indexed requests with counts only."""
    if not isinstance(result, dict):
        raise ValueError("missing indexed response")
    domain = params["element_domain"]
    source = "EVALUATED_MESH" if params.get("mesh_source") == "evaluated" else "BASE_MESH"
    for key, expected in {"category": "mesh_topology", "target_name": params["target_name"],
            "element_domain": domain, "topology_source": source,
            "coordinate_space": "LOCAL", "mode": "OBJECT", "indices_are_snapshot_local": True,
            "offset": params.get("offset", 0), "limit": params.get("limit", 100)}.items():
        if type(result.get(key)) is not type(expected) or result[key] != expected:
            raise ValueError(f"missing or inconsistent {key}")
    validate_snapshot_id(result.get("snapshot_id"))
    validate_snapshot_id(result.get("state_id"))
    if "expected_snapshot_id" in params and result["snapshot_id"] != params["expected_snapshot_id"]:
        raise ValueError("snapshot binding mismatch")
    for key in ("vertex_count", "edge_count", "polygon_count", "loop_count", "total", "returned", "returned_count"):
        if type(result.get(key)) is not int or result[key] < 0:
            raise ValueError(f"invalid {key}")
    total = result[{"vertices": "vertex_count", "edges": "edge_count", "faces": "polygon_count"}[domain]]
    elements = result.get("elements")
    offset, limit = result["offset"], result["limit"]
    count = min(limit, max(0, total-offset))
    if (not isinstance(elements, list) or result["total"] != total or len(elements) != count
            or result["returned"] != count or result["returned_count"] != count):
        raise ValueError("missing or inconsistent indexed page")
    next_offset = offset+count if offset+count < total else None
    if (type(result.get("has_more")) is not bool or result["has_more"] != (next_offset is not None)
            or "next_offset" not in result or result["next_offset"] != next_offset
            or (next_offset is not None and type(result["next_offset"]) is not int)):
        raise ValueError("inconsistent pagination")
    connectivity = 0
    for index, element in enumerate(elements, start=offset):
        if not isinstance(element, dict) or type(element.get("index")) is not int or element["index"] != index:
            raise ValueError("invalid element index")
        if domain == "vertices":
            coords = element.get("co")
            if not isinstance(coords, list) or len(coords) != 3 or not all(type(v) in (int, float) and math.isfinite(v) for v in coords):
                raise ValueError("invalid vertex coordinates")
        else:
            indices = element.get("vertices")
            if (not isinstance(indices, list) or (len(indices) != 2 if domain == "edges" else len(indices) < 3)
                    or any(type(v) is not int or not 0 <= v < result["vertex_count"] for v in indices)):
                raise ValueError("invalid connectivity")
            connectivity += len(indices)
    if connectivity > MAX_PAGE_INDICES:
        raise ValueError("connectivity budget exceeded")


_verify_indexed_topology = verify_indexed_topology_response


class BlenderExecutor:
    """
    Executes approved tools against Blender via the loopback bridge.
    Handles parameter validation, socket communication, timeouts, and error formatting.
    Enforces trusted human approval for scene mutations.
    """

    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: Optional[int] = None,
        timeout: float = 30.0,
        approval_manager: Optional[ApprovalManager] = None,
    ):
        self.host = host
        self.port = port if port is not None else DEFAULT_BRIDGE_PORT
        self.timeout = timeout
        self.client = BridgeClient(host=self.host, port=self.port, timeout=self.timeout)
        self.approval_manager = approval_manager or ApprovalManager()

    def enable_blender_approval(self, timeout: float = 30.0, pending_ttl: float = 300.0):
        """Connects approval manager to the live Blender-native human approval interface."""
        from ..security.approval import create_blender_bridge_approval_provider
        self.approval_manager.set_provider(
            create_blender_bridge_approval_provider(self.client, timeout=timeout, pending_ttl=pending_ttl)
        )

    def get_blender_approval_status(self, request_id: str) -> Dict[str, Any]:
        """Read the Blender registry status for a specific approval request."""
        response = self.client.send_command("check_approval_status", {"request_id": request_id})
        if response.get("status") != "success":
            raise RuntimeError(response.get("message", "Unable to inspect Blender approval request."))
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Blender returned an invalid approval status response.")
        return result

    def inspect_approval_status(self, request_id: str) -> Dict[str, Any]:
        """Read public registry metadata; never forward a credential-bearing record."""
        response = self.client.send_command("inspect_approval_status", {"request_id": request_id})
        if response.get("status") != "success" or not isinstance(response.get("result"), dict):
            raise RuntimeError("Approval status unavailable.")
        raw = response["result"]
        status = raw.get("status")
        if raw.get("request_id") != request_id or status not in {
            "pending", "approved", "denied", "cancelled", "expired", "not_found", "unknown"
        }:
            raise RuntimeError("Invalid approval status response.")
        public = {"request_id": request_id, "status": status}
        if status == "not_found":
            return public
        for key in ("tool_name", "task_id", "arg_hash", "record_source"):
            value = raw.get(key)
            if value is not None and not isinstance(value, str):
                raise RuntimeError("Invalid approval status metadata.")
            public[key] = value
        for key in ("expires_at", "remaining_seconds"):
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise RuntimeError("Invalid approval status timing.")
            public[key] = value
        if not isinstance(raw.get("token_consumed"), bool):
            raise RuntimeError("Invalid approval consumption metadata.")
        public["token_consumed"] = raw["token_consumed"]
        return public

    def get_approval_status(self, request_id: str, approval_source: Optional[str] = None) -> Dict[str, Any]:
        """Read an approval provider's authoritative status when supported.

        The current bridge contract provides an authoritative status reader for
        Blender requests. Other sources fail explicitly until they expose an
        equivalent status contract.
        """
        if approval_source != "blender":
            raise RuntimeError(f"No authoritative approval status reader for source '{approval_source}'.")
        return self.get_blender_approval_status(request_id)

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        trusted_approval: Optional[bool] = None,
    ) -> BridgeResponse:
        """
        Validates input arguments and executes the tool via Blender bridge.
        Returns a standardized BridgeResponse.
        """
        t0 = time.time()
        arguments = arguments or {}
        decision = None

        # 1. Normalize arguments and validate against tool schema
        try:
            sanitized_params = validate_tool_input(tool_name, arguments, trusted_approval=True)
        except PermissionError as pe:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return BridgeResponse.error(f"Approval denied: {pe}", duration_ms=duration_ms)
        except ValueError as ve:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return BridgeResponse.error(f"Parameter validation failed: {ve}", duration_ms=duration_ms)

        # 2. Trusted Approval Evaluation for mutation/destructive tiers
        if self.approval_manager.requires_approval(tool_name, arguments):
            # If trusted_approval was explicitly passed as False, reject immediately
            if trusted_approval is False:
                duration_ms = round((time.time() - t0) * 1000, 2)
                if arguments.get("approved") is True or sanitized_params.get("approved") is True:
                    return BridgeResponse.error(
                        f"Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize "
                        f"scene mutation '{tool_name}'. Explicit user approval must be granted through a trusted approval mechanism.",
                        duration_ms=duration_ms,
                    )
                return BridgeResponse.error(
                    f"Approval required: Scene mutation '{tool_name}' requires explicit user approval through "
                    "a trusted approval mechanism. The system is running in read-only mode by default.",
                    duration_ms=duration_ms,
                )

            # Build normalized parameter dictionary for the approval provider and parameter digest
            approval_args = dict(sanitized_params)
            approval_args.pop("trusted_approval", None)
            # Retain client-supplied 'approved' flag so verify_approval detects bypass attempts
            if arguments.get("approved") is True:
                approval_args["approved"] = True
            else:
                approval_args["approved"] = False

            if trusted_approval is None or (self.approval_manager.has_provider and not sanitized_params.get('approval_token')):
                decision = self.approval_manager.verify_approval(tool_name, approval_args)
                is_approved, reason = decision[0], decision[1]
                if not is_approved:
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    failure = BridgeResponse.error(reason, duration_ms=duration_ms)
                    # Preserve decision state, never credentials. Specialized agents
                    # need the authoritative pending identity to bind task resumption.
                    state = getattr(decision, "status", None)
                    if state in {"pending", "denied", "cancelled", "expired", "not_found", "unknown"}:
                        expiry = getattr(decision, "expires_at", None)
                        expiry = expiry if type(expiry) in (int, float) and math.isfinite(expiry) else None
                        failure.result = {"approval": {"status": state,
                            "request_id": getattr(decision, "request_id", None), "expires_at": expiry}}
                    return failure
                trusted_approval = is_approved

            # Attach verified approval credentials from decision
            if decision and getattr(decision, "approval_token", None):
                sanitized_params["approval_token"] = decision.approval_token
                sanitized_params["request_id"] = decision.request_id

            # Ensure trusted_approval marker is set on execution payload
            sanitized_params["trusted_approval"] = True
        else:
            # For read-only tools, trusted_approval marker is not needed
            sanitized_params.pop("trusted_approval", None)

        # 2. Bridge Invocation
        try:
            tool_timeout = 1200.0 if tool_name in ("render_scene", "bake_object_texture", "bake_physics_simulation") else self.timeout
            resp = self.client.send_command(tool_name, sanitized_params, timeout=tool_timeout)
            duration_ms = round((time.time() - t0) * 1000, 2)

            if resp.get("status") == "success":
                if tool_name == "inspect_scene_data" and sanitized_params.get("category") == "mesh_topology" and "element_domain" in sanitized_params:
                    try:
                        verify_indexed_topology_response(resp.get("result"), sanitized_params)
                    except (ValueError, TypeError, OverflowError) as exc:
                        return BridgeResponse.error(
                            f"INDEXED_TOPOLOGY_UNAVAILABLE: Blender bridge did not satisfy the indexed topology contract: {exc}. "
                            "Verify the loaded add-on matches this MCP service before retrying; no fallback or scene change was performed.",
                            duration_ms=duration_ms,
                        )
                return BridgeResponse.success(resp.get("result", {}), duration_ms=duration_ms)
            else:
                message = resp.get("message", "Unknown bridge error")
                if tool_name in _MODELING_BRIDGE_TOOLS and isinstance(message, str) and message.startswith(f"Unknown command: '{tool_name}'"):
                    message = (f"BRIDGE_CAPABILITY_UNAVAILABLE: The connected Blender bridge does not implement '{tool_name}'. "
                               "Verify the loaded add-on matches this MCP service; no fallback or retry was performed. " + message)
                failure = BridgeResponse.error(message, duration_ms=duration_ms)
                if tool_name == "render_scene":
                    job = render_job_failure_snapshot(resp.get("error_code"), resp.get("execution_state"))
                    if job is not None:
                        failure.result = {"render_job": job}
                return failure
        except ConnectionError as ce:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return BridgeResponse.error(f"Could not connect to Blender bridge at {self.host}:{self.port}. Ensure Blender is running with Universal MCP enabled.", duration_ms=duration_ms)
        except TimeoutError as te:
            duration_ms = round((time.time() - t0) * 1000, 2)
            failure = BridgeResponse.error(f"Bridge timed out waiting for Blender response: {te}", duration_ms=duration_ms)
            if tool_name == "render_scene":
                failure.result = {"render_job": render_job_failure_snapshot("TRANSPORT_TIMEOUT", "UNKNOWN")}
            return failure
        except Exception as e:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return BridgeResponse.error(f"Execution failed: {str(e)}", duration_ms=duration_ms)
