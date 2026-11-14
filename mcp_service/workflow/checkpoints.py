"""
Scene Checkpoint Manager for Universal MCP.
Provides lightweight in-memory snapshot tree tracking of scene state
(objects, transforms, modifiers, materials) prior to stage executions,
supporting transactional rollback without full .blend disk serialization.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set
import time
import uuid
import copy
import logging

logger = logging.getLogger("UniversalMCP_CheckpointManager")


def is_response_success(resp: Any) -> bool:
    """Helper to safely determine success across BridgeResponse, dict, or mock objects."""
    if resp is None:
        return False
    if hasattr(resp, "is_success"):
        return bool(resp.is_success)
    if isinstance(resp, dict):
        return bool(resp.get("success", False))
    val = getattr(resp, "success", None)
    if callable(val):
        return False
    return bool(val)


def get_response_error(resp: Any, default: str = "Unknown error") -> str:
    """Helper to safely extract error message across BridgeResponse, dict, or mock objects."""
    if resp is None:
        return default
    if hasattr(resp, "message") and resp.message:
        return str(resp.message)
    if isinstance(resp, dict):
        return str(resp.get("error") or resp.get("message") or default)
    val = getattr(resp, "error", None)
    if val is not None and not callable(val):
        return str(val)
    msg = getattr(resp, "message", None)
    if msg is not None and not callable(msg):
        return str(msg)
    if hasattr(resp, "result") and isinstance(resp.result, dict):
        err = resp.result.get("error") or resp.result.get("message")
        if err:
            return str(err)
    return default


@dataclass
class SceneCheckpoint:
    """
    Lightweight snapshot of Blender scene state at a specific point in a workflow.
    Records active objects, their transforms, assigned modifiers, and materials.
    """
    checkpoint_id: str = field(default_factory=lambda: f"ckpt_{uuid.uuid4().hex[:12]}")
    stage_id: str = ""
    parent_checkpoint_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    objects: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    materials: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "stage_id": self.stage_id,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "timestamp": self.timestamp,
            "objects": copy.deepcopy(self.objects),
            "materials": list(self.materials),
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneCheckpoint":
        return cls(
            checkpoint_id=data.get("checkpoint_id", f"ckpt_{uuid.uuid4().hex[:12]}"),
            stage_id=data.get("stage_id", ""),
            parent_checkpoint_id=data.get("parent_checkpoint_id"),
            timestamp=data.get("timestamp", time.time()),
            objects=data.get("objects", {}),
            materials=data.get("materials", []),
            metadata=data.get("metadata", {}),
        )


class SceneCheckpointManager:
    """
    Manages the lifecycle and snapshot tree of SceneCheckpoints.
    Enables diffing, hierarchy traversal, and state readback via BlenderExecutor.
    """

    def __init__(self):
        self._checkpoints: Dict[str, SceneCheckpoint] = {}
        self._stage_map: Dict[str, str] = {}  # stage_id -> latest checkpoint_id
        self._children: Dict[str, List[str]] = {}  # checkpoint_id -> list of child checkpoint_ids
        self._root_checkpoint_ids: List[str] = []

    @property
    def total_checkpoints(self) -> int:
        return len(self._checkpoints)

    def capture_checkpoint(
        self,
        stage_id: str,
        executor: Any,
        parent_checkpoint_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SceneCheckpoint:
        """
        Captures live Blender scene state via executor read-only tools and records
        a new SceneCheckpoint node in the snapshot tree.
        """
        t0 = time.time()
        logger.debug("Capturing scene checkpoint for stage '%s'", stage_id)

        # 1. Query live objects
        objects_data: Dict[str, Dict[str, Any]] = {}
        try:
            list_res = executor.execute_tool("list_objects", {})
            raw_objects = []
            if list_res and is_response_success(list_res) and list_res.result:
                raw_objects = list_res.result.get("objects", [])

            for obj_item in raw_objects:
                obj_name = obj_item.get("name") if isinstance(obj_item, dict) else str(obj_item)
                if not obj_name:
                    continue

                # Fetch detailed transforms, modifiers, and materials
                det_res = executor.execute_tool("get_object_details", {"name": obj_name})
                if det_res and is_response_success(det_res) and isinstance(det_res.result, dict):
                    det = det_res.result
                    objects_data[obj_name] = {
                        "name": obj_name,
                        "type": det.get("type", obj_item.get("type", "UNKNOWN") if isinstance(obj_item, dict) else "UNKNOWN"),
                        "location": list(det.get("location", [0.0, 0.0, 0.0])),
                        "rotation": list(det.get("rotation", [0.0, 0.0, 0.0])),
                        "scale": list(det.get("scale", [1.0, 1.0, 1.0])),
                        "dimensions": list(det.get("dimensions", [0.0, 0.0, 0.0])),
                        "materials": list(det.get("materials", [])),
                        "modifiers": copy.deepcopy(det.get("modifiers", [])),
                    }
                else:
                    # Fallback if get_object_details fails on non-standard datablock
                    objects_data[obj_name] = {
                        "name": obj_name,
                        "type": obj_item.get("type", "UNKNOWN") if isinstance(obj_item, dict) else "UNKNOWN",
                        "location": [0.0, 0.0, 0.0],
                        "rotation": [0.0, 0.0, 0.0],
                        "scale": [1.0, 1.0, 1.0],
                        "materials": [],
                        "modifiers": [],
                    }
        except Exception as e:
            logger.warning("Error querying objects during checkpoint capture: %s", e)

        # 2. Query live materials
        materials_list: List[str] = []
        try:
            mat_res = executor.execute_tool("list_materials", {})
            if mat_res and is_response_success(mat_res) and mat_res.result:
                raw_mats = mat_res.result.get("materials", [])
                for m in raw_mats:
                    m_name = m.get("name") if isinstance(m, dict) else str(m)
                    if m_name:
                        materials_list.append(m_name)
        except Exception as e:
            logger.warning("Error querying materials during checkpoint capture: %s", e)

        # 3. Determine parent checkpoint if not specified
        parent_id = parent_checkpoint_id
        if parent_id is None and self._stage_map:
            # Point to latest registered checkpoint
            last_stage_id = list(self._stage_map.keys())[-1]
            parent_id = self._stage_map[last_stage_id]

        # 4. Construct and store checkpoint
        ckpt = SceneCheckpoint(
            stage_id=stage_id,
            parent_checkpoint_id=parent_id,
            timestamp=time.time(),
            objects=objects_data,
            materials=materials_list,
            metadata={
                "capture_duration_ms": round((time.time() - t0) * 1000, 2),
                **(metadata or {}),
            },
        )

        self._checkpoints[ckpt.checkpoint_id] = ckpt
        self._stage_map[stage_id] = ckpt.checkpoint_id

        if parent_id:
            if parent_id not in self._children:
                self._children[parent_id] = []
            self._children[parent_id].append(ckpt.checkpoint_id)
        else:
            self._root_checkpoint_ids.append(ckpt.checkpoint_id)

        logger.info(
            "Captured checkpoint '%s' for stage '%s' (objects=%d, parent=%s)",
            ckpt.checkpoint_id,
            stage_id,
            len(objects_data),
            parent_id,
        )
        return ckpt

    def get_checkpoint(self, checkpoint_id: str) -> Optional[SceneCheckpoint]:
        """Retrieves checkpoint by its unique ID."""
        return self._checkpoints.get(checkpoint_id)

    def get_stage_checkpoint(self, stage_id: str) -> Optional[SceneCheckpoint]:
        """Retrieves the latest checkpoint recorded for a specific stage."""
        ckpt_id = self._stage_map.get(stage_id)
        return self._checkpoints.get(ckpt_id) if ckpt_id else None

    def diff_checkpoints(
        self,
        baseline: SceneCheckpoint,
        target: SceneCheckpoint,
    ) -> Dict[str, Any]:
        """
        Computes differences between two checkpoints:
        - added_objects
        - removed_objects
        - modified_objects (transforms, modifiers, materials)
        - added_materials
        - removed_materials
        """
        base_objs = set(baseline.objects.keys())
        target_objs = set(target.objects.keys())

        added_objs = sorted(list(target_objs - base_objs))
        removed_objs = sorted(list(base_objs - target_objs))
        common_objs = sorted(list(base_objs & target_objs))

        modified_objs: Dict[str, Dict[str, Any]] = {}
        for name in common_objs:
            b_info = baseline.objects[name]
            t_info = target.objects[name]
            diffs = {}

            # Location diff
            b_loc = b_info.get("location", [0, 0, 0])
            t_loc = t_info.get("location", [0, 0, 0])
            if any(abs(b - t) > 0.001 for b, t in zip(b_loc, t_loc)):
                diffs["location"] = {"from": b_loc, "to": t_loc}

            # Rotation diff
            b_rot = b_info.get("rotation", [0, 0, 0])
            t_rot = t_info.get("rotation", [0, 0, 0])
            if any(abs(b - t) > 0.001 for b, t in zip(b_rot, t_rot)):
                diffs["rotation"] = {"from": b_rot, "to": t_rot}

            # Scale diff
            b_scale = b_info.get("scale", [1, 1, 1])
            t_scale = t_info.get("scale", [1, 1, 1])
            if any(abs(b - t) > 0.001 for b, t in zip(b_scale, t_scale)):
                diffs["scale"] = {"from": b_scale, "to": t_scale}

            # Modifiers diff
            b_mods = [m.get("name") for m in b_info.get("modifiers", []) if isinstance(m, dict)]
            t_mods = [m.get("name") for m in t_info.get("modifiers", []) if isinstance(m, dict)]
            if b_mods != t_mods:
                diffs["modifiers"] = {"from": b_mods, "to": t_mods}

            # Materials diff
            b_mats = b_info.get("materials", [])
            t_mats = t_info.get("materials", [])
            if b_mats != t_mats:
                diffs["materials"] = {"from": b_mats, "to": t_mats}

            if diffs:
                modified_objs[name] = diffs

        base_mats = set(baseline.materials)
        target_mats = set(target.materials)

        return {
            "baseline_checkpoint_id": baseline.checkpoint_id,
            "target_checkpoint_id": target.checkpoint_id,
            "added_objects": added_objs,
            "removed_objects": removed_objs,
            "modified_objects": modified_objs,
            "added_materials": sorted(list(target_mats - base_mats)),
            "removed_materials": sorted(list(base_mats - target_mats)),
        }

    def clear(self) -> None:
        """Clears all stored checkpoints."""
        self._checkpoints.clear()
        self._stage_map.clear()
        self._children.clear()
        self._root_checkpoint_ids.clear()

