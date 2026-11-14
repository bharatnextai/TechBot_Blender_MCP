"""
Camera Choreography & Cinematic Shot Production (Phase 3.4).

Provides director-level camera staging and path planning:
1. Turntable / Orbital Shots: 360-degree or partial orbital camera movement around target bounds.
2. Dolly / Tracking Moves: Keyframed linear and curved coordinate & look-at transitions.
3. Closed-Form Look-At Orientation: Exact Euler angles aiming the camera at target centers.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
import math
import logging

logger = logging.getLogger("UniversalMCP_CameraChoreography")


class CameraShotType(str, Enum):
    TURNTABLE = "TURNTABLE"
    TRACKING = "TRACKING"
    DOLLY = "DOLLY"
    STATIC_AIM = "STATIC_AIM"


def calculate_camera_look_at_euler(
    camera_pos: Tuple[float, float, float],
    target_pos: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """
    Computes exact Blender camera Euler XYZ rotation angles (in radians)
    so that the camera (natively pointing along -Z with +Y up)
    aims precisely at target_pos from camera_pos.
    """
    dx = target_pos[0] - camera_pos[0]
    dy = target_pos[1] - camera_pos[1]
    dz = target_pos[2] - camera_pos[2]

    dist_xy = math.sqrt(dx * dx + dy * dy)
    if dist_xy < 1e-6:
        # Camera is directly above or below target
        rx = 0.0 if dz <= 0 else math.pi
        return (rx, 0.0, 0.0)

    # Yaw (rotation around world Z)
    rz = math.atan2(dy, dx) - (math.pi / 2.0)

    # Pitch (rotation around camera X):
    # When target is horizontal (dz = 0), rx = 90 deg (pi/2)
    # When target is below camera (dz < 0), camera pitches downward (rx < 90 deg)
    elevation_angle = math.atan2(dz, dist_xy)
    rx = (math.pi / 2.0) + elevation_angle

    ry = 0.0
    return (rx, ry, rz)


@dataclass
class TurntableConfig:
    """Configuration for automated orbital turntable camera choreography."""
    target_name: str
    camera_name: str = "ActiveCamera"
    radius: Optional[float] = None
    elevation: Optional[float] = None
    start_angle_deg: float = 0.0
    end_angle_deg: float = 360.0
    frame_start: int = 1
    frame_end: int = 60
    step_frames: int = 10

    def __post_init__(self):
        if self.frame_start < 1 or self.frame_end > 250:
            raise ValueError(f"Timeline frame range [{self.frame_start}, {self.frame_end}] must be within [1, 250].")
        if self.frame_end <= self.frame_start:
            raise ValueError(f"frame_end ({self.frame_end}) must be greater than frame_start ({self.frame_start}).")
        if self.step_frames < 1:
            raise ValueError(f"step_frames ({self.step_frames}) must be at least 1.")


@dataclass
class DollyShotConfig:
    """Configuration for linear camera dolly / crane transitions."""
    camera_name: str = "ActiveCamera"
    start_location: Tuple[float, float, float] = (0.0, -10.0, 2.0)
    end_location: Tuple[float, float, float] = (0.0, -3.0, 1.0)
    target_point: Tuple[float, float, float] = (0.0, 0.0, 0.5)
    frame_start: int = 1
    frame_end: int = 60
    step_frames: int = 10

    def __post_init__(self):
        if self.frame_start < 1 or self.frame_end > 250:
            raise ValueError(f"Timeline frame range [{self.frame_start}, {self.frame_end}] must be within [1, 250].")
        if self.frame_end <= self.frame_start:
            raise ValueError(f"frame_end ({self.frame_end}) must be greater than frame_start ({self.frame_start}).")


class CameraChoreographer:
    """
    Synthesizes and keyframes cinematic camera trajectories.
    """

    def compute_turntable_waypoints(
        self,
        config: TurntableConfig,
        target_center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        effective_radius: float = 5.0,
        effective_elevation: float = 1.5,
    ) -> List[Dict[str, Any]]:
        """
        Generates deterministic time-sampled camera waypoints along a circular orbit.
        """
        total_frames = config.frame_end - config.frame_start
        waypoints: List[Dict[str, Any]] = []

        curr_frame = config.frame_start
        frames_to_sample = []
        while curr_frame <= config.frame_end:
            frames_to_sample.append(curr_frame)
            curr_frame += config.step_frames
        if frames_to_sample[-1] != config.frame_end:
            frames_to_sample.append(config.frame_end)

        for f in frames_to_sample:
            t = (f - config.frame_start) / float(max(total_frames, 1))
            angle_deg = config.start_angle_deg + t * (config.end_angle_deg - config.start_angle_deg)
            angle_rad = math.radians(angle_deg)

            # Circular coordinates around target_center
            cx = target_center[0] + effective_radius * math.cos(angle_rad)
            cy = target_center[1] + effective_radius * math.sin(angle_rad)
            cz = target_center[2] + effective_elevation

            cam_pos = (cx, cy, cz)
            cam_rot = calculate_camera_look_at_euler(cam_pos, target_center)

            waypoints.append({
                "frame": f,
                "location": [round(v, 4) for v in cam_pos],
                "rotation_euler": [round(v, 4) for v in cam_rot],
                "angle_deg": round(angle_deg, 2),
            })

        return waypoints

    def compute_dolly_waypoints(
        self,
        config: DollyShotConfig,
    ) -> List[Dict[str, Any]]:
        """
        Generates time-sampled linear dolly waypoints with dynamic look-at tracking.
        """
        total_frames = config.frame_end - config.frame_start
        waypoints: List[Dict[str, Any]] = []

        curr_frame = config.frame_start
        frames_to_sample = []
        while curr_frame <= config.frame_end:
            frames_to_sample.append(curr_frame)
            curr_frame += config.step_frames
        if frames_to_sample[-1] != config.frame_end:
            frames_to_sample.append(config.frame_end)

        sx, sy, sz = config.start_location
        ex, ey, ez = config.end_location

        for f in frames_to_sample:
            t = (f - config.frame_start) / float(max(total_frames, 1))
            cx = sx + t * (ex - sx)
            cy = sy + t * (ey - sy)
            cz = sz + t * (ez - sz)
            cam_pos = (cx, cy, cz)
            cam_rot = calculate_camera_look_at_euler(cam_pos, config.target_point)

            waypoints.append({
                "frame": f,
                "location": [round(v, 4) for v in cam_pos],
                "rotation_euler": [round(v, 4) for v in cam_rot],
            })

        return waypoints

    def setup_turntable(
        self,
        executor: Any,
        config: TurntableConfig,
        scene_graph: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Coordinates a full turntable shot by keyframing the camera across the timeline.
        Reuses SceneGraph geometry if provided to automatically derive target center and radius.
        """
        target_center = (0.0, 0.0, 0.0)
        target_size = (1.0, 1.0, 1.0)

        if scene_graph and hasattr(scene_graph, "get_node"):
            target_node = scene_graph.get_node(config.target_name)
            if target_node:
                if target_node.aabb:
                    target_center = target_node.aabb.center
                    target_size = target_node.aabb.size
                else:
                    target_center = target_node.location
                    target_size = target_node.dimensions

        max_dim = max(target_size)
        effective_radius = config.radius if config.radius is not None else max(max_dim * 2.5, 3.5)
        effective_elevation = config.elevation if config.elevation is not None else max(max_dim * 0.8, 1.2)

        waypoints = self.compute_turntable_waypoints(
            config,
            target_center=target_center,
            effective_radius=effective_radius,
            effective_elevation=effective_elevation,
        )

        keyframes_applied = 0
        for wp in waypoints:
            f = wp["frame"]
            # 1. Location keyframe
            res_loc = executor.execute_tool(
                "manage_keyframe",
                {
                    "name": config.camera_name,
                    "property_path": "location",
                    "action": "insert",
                    "frame": f,
                    "value": wp["location"],
                },
            )
            # 2. Rotation keyframe
            res_rot = executor.execute_tool(
                "manage_keyframe",
                {
                    "name": config.camera_name,
                    "property_path": "rotation_euler",
                    "action": "insert",
                    "frame": f,
                    "value": wp["rotation_euler"],
                },
            )
            keyframes_applied += 2

        return {
            "success": True,
            "shot_type": CameraShotType.TURNTABLE.value,
            "camera_name": config.camera_name,
            "target_name": config.target_name,
            "target_center": target_center,
            "effective_radius": effective_radius,
            "effective_elevation": effective_elevation,
            "frame_start": config.frame_start,
            "frame_end": config.frame_end,
            "waypoints_count": len(waypoints),
            "keyframes_applied": keyframes_applied,
            "waypoints": waypoints,
        }

    def setup_dolly(
        self,
        executor: Any,
        config: DollyShotConfig,
    ) -> Dict[str, Any]:
        """
        Coordinates a dolly move by keyframing camera translation and look-at rotation.
        """
        waypoints = self.compute_dolly_waypoints(config)
        keyframes_applied = 0

        for wp in waypoints:
            f = wp["frame"]
            executor.execute_tool(
                "manage_keyframe",
                {
                    "name": config.camera_name,
                    "property_path": "location",
                    "action": "insert",
                    "frame": f,
                    "value": wp["location"],
                },
            )
            executor.execute_tool(
                "manage_keyframe",
                {
                    "name": config.camera_name,
                    "property_path": "rotation_euler",
                    "action": "insert",
                    "frame": f,
                    "value": wp["rotation_euler"],
                },
            )
            keyframes_applied += 2

        return {
            "success": True,
            "shot_type": CameraShotType.DOLLY.value,
            "camera_name": config.camera_name,
            "frame_start": config.frame_start,
            "frame_end": config.frame_end,
            "waypoints_count": len(waypoints),
            "keyframes_applied": keyframes_applied,
            "waypoints": waypoints,
        }

