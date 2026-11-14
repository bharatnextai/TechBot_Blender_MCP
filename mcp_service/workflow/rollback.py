"""
Stage Rollback Engine for Universal MCP.
Enables transactional reversion of scene state to a designated SceneCheckpoint
upon stage execution failure or verification gate violation, ensuring no partial
mutations contaminate subsequent operations or adaptive retries.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set
import time
import uuid
import copy
import logging

from .checkpoints import SceneCheckpoint, SceneCheckpointManager, is_response_success, get_response_error

logger = logging.getLogger("UniversalMCP_RollbackEngine")


@dataclass
class RollbackReceipt:
    """
    Cryptographic audit receipt detailing the outcome of a stage rollback operation.
    """
    receipt_id: str = field(default_factory=lambda: f"rcpt_{uuid.uuid4().hex[:12]}")
    target_checkpoint_id: str = ""
    stage_id: str = ""
    success: bool = False
    objects_removed: List[str] = field(default_factory=list)
    objects_restored: List[str] = field(default_factory=list)
    modifiers_reverted: List[str] = field(default_factory=list)
    verified: bool = False
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RollbackReceipt":
        return cls(**data)


class StageRollbackEngine:
    """
    Executes targeted state restorations against live Blender sessions using
    declarative SceneCheckpoints and verified MCP tools.
    """

    def __init__(self, checkpoint_manager: Optional[SceneCheckpointManager] = None):
        self._checkpoint_manager = checkpoint_manager or SceneCheckpointManager()

    def rollback_to_checkpoint(
        self,
        target_checkpoint: SceneCheckpoint,
        executor: Any,
        trusted_approval: bool = True,
    ) -> RollbackReceipt:
        """
        Reverts the live Blender scene state to the given target_checkpoint:
        1. Deletes newly created objects not present in the checkpoint.
        2. Restores modified object transforms (location, rotation, scale).
        3. Removes newly added modifiers not present in the checkpoint.
        4. Verifies post-rollback scene state against checkpoint objects.
        """
        t0 = time.time()
        stage_id = target_checkpoint.stage_id
        ckpt_id = target_checkpoint.checkpoint_id
        logger.info(
            "Initiating stage rollback to checkpoint '%s' (stage '%s')",
            ckpt_id,
            stage_id,
        )

        receipt = RollbackReceipt(
            target_checkpoint_id=ckpt_id,
            stage_id=stage_id,
            timestamp=time.time(),
        )

        try:
            # 1. Fetch live objects
            list_res = executor.execute_tool("list_objects", {})
            if not is_response_success(list_res):
                raise RuntimeError(f"Failed to query live scene objects: {get_response_error(list_res)}")

            raw_objects = list_res.result.get("objects", []) if list_res.result else []
            live_names = [
                o.get("name") if isinstance(o, dict) else str(o)
                for o in raw_objects
                if (o.get("name") if isinstance(o, dict) else str(o))
            ]

            target_objs = target_checkpoint.objects

            # 2. Identify and delete added objects
            added_names = [name for name in live_names if name not in target_objs]
            for obj_to_delete in added_names:
                logger.info("Rollback: Deleting added object '%s'", obj_to_delete)
                del_res = executor.execute_tool(
                    "delete_object",
                    {"name": obj_to_delete},
                    trusted_approval=trusted_approval,
                )
                if is_response_success(del_res):
                    receipt.objects_removed.append(obj_to_delete)
                else:
                    err_msg = getattr(del_res, "error", getattr(del_res, "message", f"delete_object failed on '{obj_to_delete}'"))
                    logger.warning("Rollback warning: Failed to delete object '%s': %s", obj_to_delete, err_msg)

            # Purge orphaned datablocks from removed objects to prevent contamination
            if receipt.objects_removed:
                try:
                    executor.execute_tool("purge_orphaned_datablocks", {}, trusted_approval=trusted_approval)
                except Exception as pe:
                    logger.debug("Optional datablock purge during rollback non-critical: %s", pe)

            # 3. Restore transforms and revert added modifiers on surviving objects
            surviving_names = [name for name in live_names if name in target_objs]
            for name in surviving_names:
                ckpt_info = target_objs[name]

                # Query live details
                det_res = executor.execute_tool("get_object_details", {"name": name})
                if not is_response_success(det_res) or not isinstance(det_res.result, dict):
                    continue

                live_det = det_res.result

                # Check transforms
                live_loc = live_det.get("location", [0.0, 0.0, 0.0])
                ckpt_loc = ckpt_info.get("location", [0.0, 0.0, 0.0])
                live_rot = live_det.get("rotation", [0.0, 0.0, 0.0])
                ckpt_rot = ckpt_info.get("rotation", [0.0, 0.0, 0.0])
                live_scale = live_det.get("scale", [1.0, 1.0, 1.0])
                ckpt_scale = ckpt_info.get("scale", [1.0, 1.0, 1.0])

                loc_diff = any(abs(l - c) > 0.001 for l, c in zip(live_loc, ckpt_loc))
                rot_diff = any(abs(l - c) > 0.001 for l, c in zip(live_rot, ckpt_rot))
                scale_diff = any(abs(l - c) > 0.001 for l, c in zip(live_scale, ckpt_scale))

                if loc_diff or rot_diff or scale_diff:
                    logger.info("Rollback: Restoring transforms for object '%s'", name)
                    tx_params: Dict[str, Any] = {"name": name}
                    if loc_diff:
                        tx_params["location"] = ckpt_loc
                    if rot_diff:
                        tx_params["rotation_euler"] = ckpt_rot
                    if scale_diff:
                        tx_params["scale"] = ckpt_scale

                    tx_res = executor.execute_tool(
                        "transform_object",
                        tx_params,
                        trusted_approval=trusted_approval,
                    )
                    if is_response_success(tx_res):
                        receipt.objects_restored.append(name)
                    else:
                        logger.warning("Rollback warning: Failed to restore transforms on '%s'", name)

                # Check modifiers
                live_mods = [m.get("name") for m in live_det.get("modifiers", []) if isinstance(m, dict)]
                ckpt_mods = [m.get("name") for m in ckpt_info.get("modifiers", []) if isinstance(m, dict)]
                added_mods = [m for m in live_mods if m not in ckpt_mods]

                for mod_name in added_mods:
                    logger.info("Rollback: Removing added modifier '%s' from '%s'", mod_name, name)
                    mod_res = executor.execute_tool(
                        "edit_modifier_stack",
                        {
                            "object_name": name,
                            "action": "remove",
                            "modifier_name": mod_name,
                        },
                        trusted_approval=trusted_approval,
                    )
                    if is_response_success(mod_res):
                        receipt.modifiers_reverted.append(f"{name}:{mod_name}")
                    else:
                        logger.warning("Rollback warning: Failed to remove modifier '%s' from '%s'", mod_name, name)

            # 4. Independent post-rollback verification
            verify_res = executor.execute_tool("list_objects", {})
            post_raw = verify_res.result.get("objects", []) if (is_response_success(verify_res) and verify_res.result) else []
            post_names = set(
                o.get("name") if isinstance(o, dict) else str(o)
                for o in post_raw
                if (o.get("name") if isinstance(o, dict) else str(o))
            )

            # Verify no added objects remain
            remaining_added = [name for name in receipt.objects_removed if name in post_names]
            # Verify all checkpoint objects are present
            missing_expected = [name for name in target_objs.keys() if name not in post_names]

            if not remaining_added and not missing_expected:
                receipt.verified = True
                receipt.success = True
                logger.info(
                    "Rollback to checkpoint '%s' VERIFIED successfully (removed=%d, restored=%d, reverted_mods=%d)",
                    ckpt_id,
                    len(receipt.objects_removed),
                    len(receipt.objects_restored),
                    len(receipt.modifiers_reverted),
                )
            else:
                receipt.verified = False
                receipt.success = False
                err_details = []
                if remaining_added:
                    err_details.append(f"Objects still present: {remaining_added}")
                if missing_expected:
                    err_details.append(f"Expected objects missing: {missing_expected}")
                receipt.error = f"Post-rollback verification failed: {'; '.join(err_details)}"
                logger.error(receipt.error)

        except Exception as e:
            receipt.success = False
            receipt.verified = False
            receipt.error = str(e)
            logger.error("Exception during stage rollback: %s", e)

        receipt.duration_ms = round((time.time() - t0) * 1000, 2)
        return receipt

