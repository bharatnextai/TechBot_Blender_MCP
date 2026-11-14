"""
Multi-Track Shot Staging & Timeline Orchestration (Phase 3.4).

Coordinates simultaneous keyframing of character armatures, cameras, and lighting
properties across defined timeline spans (bounded to frames 1..250).
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
import logging

logger = logging.getLogger("UniversalMCP_ShotStaging")


@dataclass
class TimelineKeyframe:
    """Individual keyframe payload."""
    frame: int
    value: Union[float, List[float], Tuple[float, ...]]
    property_path: str = "location"
    index: int = -1  # -1 for all channels, 0 for X, 1 for Y, 2 for Z


@dataclass
class TimelineTrack:
    """Track of keyframes bound to an individual object property."""
    object_name: str
    property_path: str = "location"
    keyframes: List[TimelineKeyframe] = field(default_factory=list)

    def add_keyframe(self, frame: int, value: Union[float, List[float], Tuple[float, ...]], index: int = -1) -> None:
        self.keyframes.append(TimelineKeyframe(frame=frame, value=value, property_path=self.property_path, index=index))


@dataclass
class ShotTimelinePlan:
    """
    Coordinated multi-track animation plan across a bounded timeline span.
    """
    name: str
    frame_start: int = 1
    frame_end: int = 60
    tracks: List[TimelineTrack] = field(default_factory=list)

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        if self.frame_start < 1 or self.frame_end > 250:
            raise ValueError(f"Timeline frame span [{self.frame_start}, {self.frame_end}] outside valid bounds [1, 250].")
        if self.frame_end <= self.frame_start:
            raise ValueError(f"frame_end ({self.frame_end}) must be greater than frame_start ({self.frame_start}).")

        for track in self.tracks:
            for kf in track.keyframes:
                if not (self.frame_start <= kf.frame <= self.frame_end):
                    raise ValueError(
                        f"Keyframe at frame {kf.frame} for object '{track.object_name}' "
                        f"falls outside plan span [{self.frame_start}, {self.frame_end}]."
                    )

    def add_track(self, track: TimelineTrack) -> None:
        self.tracks.append(track)
        self.validate()


class ShotOrchestrator:
    """
    Executes and coordinates multi-track timeline animation plans.
    """

    def execute_timeline_plan(
        self,
        executor: Any,
        plan: ShotTimelinePlan,
    ) -> Dict[str, Any]:
        """
        Applies all keyframe tracks in a plan deterministically.
        """
        plan.validate()
        total_applied = 0
        track_results: List[Dict[str, Any]] = []

        for track in plan.tracks:
            # Sort keyframes by frame number
            sorted_keyframes = sorted(track.keyframes, key=lambda k: k.frame)
            track_applied = 0

            for kf in sorted_keyframes:
                params = {
                    "name": track.object_name,
                    "property_path": kf.property_path,
                    "action": "insert",
                    "frame": kf.frame,
                    "value": list(kf.value) if isinstance(kf.value, (tuple, list)) else kf.value,
                    "index": kf.index,
                }
                res = executor.execute_tool("manage_keyframe", params)
                track_applied += 1

            total_applied += track_applied
            track_results.append({
                "object_name": track.object_name,
                "property_path": track.property_path,
                "keyframes_count": track_applied,
            })

        return {
            "success": True,
            "plan_name": plan.name,
            "frame_start": plan.frame_start,
            "frame_end": plan.frame_end,
            "tracks_count": len(plan.tracks),
            "total_keyframes_applied": total_applied,
            "track_details": track_results,
        }

    def stage_rigged_ik_motion(
        self,
        executor: Any,
        ik_target_name: str,
        motion_waypoints: Dict[int, Tuple[float, float, float]],
        frame_start: int = 1,
        frame_end: int = 60,
    ) -> Dict[str, Any]:
        """
        Coordinates skeletal limb movement by keyframing the IK target object.
        """
        track = TimelineTrack(object_name=ik_target_name, property_path="location")
        for frame, pos in motion_waypoints.items():
            track.add_keyframe(frame=frame, value=pos)

        plan = ShotTimelinePlan(
            name=f"IKMotion_{ik_target_name}",
            frame_start=frame_start,
            frame_end=frame_end,
            tracks=[track],
        )

        return self.execute_timeline_plan(executor, plan)

