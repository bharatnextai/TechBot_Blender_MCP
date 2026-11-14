"""
Protocol data models for the Universal MCP Blender bridge and service.
Defines standard request/response envelopes and serializable data structures.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import uuid
import time


@dataclass
class BridgeCommand:
    """Standard command message sent across the bridge."""
    command: str
    params: Dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.command,
            "params": self.params,
            "command_id": self.command_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeCommand":
        cmd_type = data.get("type") or data.get("command") or ""
        params = data.get("params") or {}
        cmd_id = data.get("command_id") or str(uuid.uuid4())
        ts = data.get("timestamp") or time.time()
        return cls(command=cmd_type, params=params, command_id=cmd_id, timestamp=ts)


@dataclass
class BridgeResponse:
    """Standard response envelope returned across the bridge."""
    status: str  # "success" or "error"
    result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    command_id: Optional[str] = None
    execution_time_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
        }
        if self.result is not None:
            out["result"] = self.result
        if self.message is not None:
            out["message"] = self.message
        if self.command_id is not None:
            out["command_id"] = self.command_id
        return out

    @classmethod
    def success(cls, result: Dict[str, Any], command_id: Optional[str] = None, duration_ms: float = 0.0) -> "BridgeResponse":
        return cls(status="success", result=result, command_id=command_id, execution_time_ms=duration_ms)

    @classmethod
    def error(cls, message: str, command_id: Optional[str] = None, duration_ms: float = 0.0) -> "BridgeResponse":
        return cls(status="error", message=message, command_id=command_id, execution_time_ms=duration_ms)


@dataclass
class SceneSummaryData:
    """Structured data payload for get_scene_summary."""
    scene_name: str
    frame_current: int
    frame_start: int
    frame_end: int
    fps: int
    unit_system: str
    total_objects: int
    object_counts_by_type: Dict[str, int]
    active_camera: Optional[str] = None
    active_object: Optional[str] = None
    collection_count: int = 0
    collections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ObjectItemData:
    """Summary representation of a single scene object."""
    name: str
    type: str
    collections: List[str] = field(default_factory=list)
    visible: bool = True
    parent: Optional[str] = None
    children_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ObjectDetailsData:
    """Comprehensive transform and structural detail for an object."""
    name: str
    type: str
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation_euler: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    dimensions: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    bound_box: List[List[float]] = field(default_factory=list)
    parent: Optional[str] = None
    collections: List[str] = field(default_factory=list)
    visible: bool = True
    mesh_stats: Optional[Dict[str, int]] = None
    materials: List[str] = field(default_factory=list)
    modifiers: List[Dict[str, Any]] = field(default_factory=list)
    custom_properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MaterialItemData:
    """Summary of a Blender material."""
    name: str
    use_nodes: bool
    users: int
    diffuse_color: List[float] = field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    metallic: float = 0.0
    roughness: float = 0.5
    texture_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def render_job_failure_snapshot(error_code: Any, execution_state: Any) -> Optional[Dict[str, Any]]:
    """Sanitized historical evidence, never a live Blender job-status assertion."""
    states = {
        "IN_FLIGHT_TIMEOUT": "ACTIVE_IN_FLIGHT",
        "QUEUE_TIMEOUT_CANCELLED": "DISCARDED_FROM_QUEUE",
        "BLIND_RETRY_BLOCKED": "REQUIRES_RECONCILIATION",
        "TRANSPORT_TIMEOUT": "UNKNOWN",
    }
    if not isinstance(error_code, str) or error_code not in states:
        return None
    state = execution_state if execution_state == states[error_code] else "UNKNOWN"
    not_started = state in {"DISCARDED_FROM_QUEUE", "REQUIRES_RECONCILIATION"}
    return {
        "error_code": error_code,
        "execution_state_at_response": state,
        "outcome": "not_started" if not_started else "unknown",
        "completion_verified": False,
        "requires_reconciliation": state != "DISCARDED_FROM_QUEUE",
        "automatic_retry_allowed": False,
    }
