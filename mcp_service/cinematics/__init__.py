"""
Cinematic Animation Production & Shot Orchestration Package (Phase 3.4).

Provides:
1. Camera Choreography (turntable, dolly, look-at math)
2. Multi-track Timeline Staging (simultaneous object/camera/IK keyframing)
3. Physics Bake Synchronization & Marker Frame Readback
"""

from .camera_choreography import (
    CameraShotType,
    calculate_camera_look_at_euler,
    TurntableConfig,
    DollyShotConfig,
    CameraChoreographer,
)
from .shot_staging import (
    TimelineKeyframe,
    TimelineTrack,
    ShotTimelinePlan,
    ShotOrchestrator,
)
from .physics_sync import (
    PhysicsBakeSynchronizer,
)

__all__ = [
    "CameraShotType",
    "calculate_camera_look_at_euler",
    "TurntableConfig",
    "DollyShotConfig",
    "CameraChoreographer",
    "TimelineKeyframe",
    "TimelineTrack",
    "ShotTimelinePlan",
    "ShotOrchestrator",
    "PhysicsBakeSynchronizer",
]

