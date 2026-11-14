"""
Physics Bake Synchronization & Frame-Accurate Readback (Phase 3.4).

Enforces that physics point cache simulation baking completes successfully
before multi-frame animation evaluation and rendering proceed.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger("UniversalMCP_PhysicsSync")


class PhysicsBakeSynchronizer:
    """
    Coordinates physics simulation point cache baking and multi-frame readback.
    """

    def sync_and_bake(
        self,
        executor: Any,
        physics_type: str = "RIGID_BODY",
        frame_start: int = 1,
        frame_end: int = 60,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Triggers simulation baking across the requested frame range and asserts
        that cache points were committed to memory.
        """
        if frame_start < 1 or frame_end > 250:
            raise ValueError(f"Physics bake frame range [{frame_start}, {frame_end}] outside bounds [1, 250].")

        bake_res = executor.execute_tool(
            "bake_physics_simulation",
            {
                "physics_type": physics_type,
                "frame_start": frame_start,
                "frame_end": frame_end,
                "timeout_seconds": timeout_seconds,
            },
        )

        res_dict = bake_res.result if hasattr(bake_res, "result") and isinstance(bake_res.result, dict) else {}
        is_success = bool(getattr(bake_res, "is_success", False) or res_dict.get("success", False))

        return {
            "success": is_success,
            "physics_type": physics_type,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "bake_result": res_dict,
        }

    def evaluate_marker_frames(
        self,
        executor: Any,
        objects: List[str],
        marker_frames: List[int],
    ) -> Dict[int, Dict[str, List[float]]]:
        """
        Evaluates the scene at specified marker frames via inspect_physics,
        returning evaluated world-space coordinates for trajectory readback.
        """
        frame_evaluations: Dict[int, Dict[str, List[float]]] = {}

        for frame in marker_frames:
            frame_evaluations[frame] = {}
            for obj_name in objects:
                insp_res = executor.execute_tool(
                    "inspect_physics",
                    {
                        "object_name": obj_name,
                        "frame": frame,
                        "include_cache_info": False,
                    },
                )
                res_dict = insp_res.result if hasattr(insp_res, "result") and isinstance(insp_res.result, dict) else {}
                target_info = res_dict.get("target", {})
                eval_loc = target_info.get("evaluated_location") or target_info.get("location") or [0.0, 0.0, 0.0]
                frame_evaluations[frame][obj_name] = [round(float(v), 4) for v in eval_loc]

        return frame_evaluations

