"""
Unit tests for Phase 3.4: Cinematic Animation Production & Shot Orchestration.
Verifies:
1. Exact closed-form camera look-at Euler orientation.
2. Turntable orbital waypoint calculation and bounds adaptation.
3. Dolly shot linear interpolation and dynamic aim.
4. Timeline plan bounds validation (1..250 frame limits).
5. Multi-track shot staging with Mock executor.
6. Physics bake synchronization and marker frame readback.
"""

import unittest
import math
from typing import Dict, Any, List, Optional

from mcp_service.cinematics.camera_choreography import (
    calculate_camera_look_at_euler,
    TurntableConfig,
    DollyShotConfig,
    CameraChoreographer,
)
from mcp_service.cinematics.shot_staging import (
    TimelineKeyframe,
    TimelineTrack,
    ShotTimelinePlan,
    ShotOrchestrator,
)
from mcp_service.cinematics.physics_sync import (
    PhysicsBakeSynchronizer,
)
from shared.models.protocol_models import BridgeResponse


class MockBlenderExecutor:
    """Mock executor tracking keyframe and physics operations."""
    def __init__(self):
        self.tool_calls: List[Dict[str, Any]] = []

    def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None, trusted_approval: Optional[bool] = None) -> BridgeResponse:
        arguments = arguments or {}
        self.tool_calls.append({"tool": tool_name, "args": arguments})
        if tool_name == "manage_keyframe":
            return BridgeResponse.success({"status": "keyframe_inserted", "frame": arguments.get("frame")})
        elif tool_name == "bake_physics_simulation":
            return BridgeResponse.success({"success": True, "frame_count": arguments.get("frame_end", 60)})
        elif tool_name == "inspect_physics":
            frame = arguments.get("frame", 1)
            # Simulated falling object: z drops as frame advances
            z = max(1.0, 5.0 - (frame * 0.1))
            return BridgeResponse.success({
                "success": True,
                "target": {"evaluated_location": [0.0, 0.0, z]},
            })
        return BridgeResponse.error(f"Unhandled tool: {tool_name}")


class TestPhase3Cinematics(unittest.TestCase):

    def test_camera_look_at_euler(self):
        """Verifies exact camera look-at angles pointing at target."""
        # 1. Camera horizontal at (0, -5, 0), target at (0, 0, 0)
        rx, ry, rz = calculate_camera_look_at_euler((0.0, -5.0, 0.0), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(rx, math.pi / 2.0, places=3)  # 90 deg (horizontal)
        self.assertAlmostEqual(ry, 0.0, places=3)
        self.assertAlmostEqual(rz, 0.0, places=3)  # facing +Y

        # 2. Camera above target at (0, -5, 5), target at (0, 0, 0) -> looking downward 45 deg
        rx, ry, rz = calculate_camera_look_at_euler((0.0, -5.0, 5.0), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(rx, math.pi / 4.0, places=3)  # 45 deg tilt
        self.assertAlmostEqual(rz, 0.0, places=3)

        # 3. Camera below target at (0, -5, -5), target at (0, 0, 0) -> looking upward 45 deg
        rx, ry, rz = calculate_camera_look_at_euler((0.0, -5.0, -5.0), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(rx, 3.0 * math.pi / 4.0, places=3)  # 135 deg tilt
        self.assertAlmostEqual(rz, 0.0, places=3)

        # 4. Camera at (5, 0, 0), target at (0, 0, 0) -> along +X looking at -X
        rx, ry, rz = calculate_camera_look_at_euler((5.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(rx, math.pi / 2.0, places=3)
        self.assertAlmostEqual(rz, math.pi / 2.0, places=3)

    def test_turntable_waypoints_computation(self):
        """Verifies circular turntable orbit waypoints generation."""
        choreographer = CameraChoreographer()
        config = TurntableConfig(
            target_name="HeroAsset",
            camera_name="StudioCam",
            radius=6.0,
            elevation=2.0,
            start_angle_deg=0.0,
            end_angle_deg=360.0,
            frame_start=1,
            frame_end=61,
            step_frames=15,
        )

        waypoints = choreographer.compute_turntable_waypoints(config, target_center=(0.0, 0.0, 0.5), effective_radius=6.0, effective_elevation=2.0)
        self.assertGreaterEqual(len(waypoints), 5)

        # Check first waypoint (frame 1, angle 0 deg) -> x = 6.0, y = 0.0, z = 2.5
        wp0 = waypoints[0]
        self.assertEqual(wp0["frame"], 1)
        self.assertAlmostEqual(wp0["location"][0], 6.0, places=2)
        self.assertAlmostEqual(wp0["location"][1], 0.0, places=2)
        self.assertAlmostEqual(wp0["location"][2], 2.5, places=2)

        # Check last waypoint (frame 61, angle 360 deg) -> returns to start
        wp_last = waypoints[-1]
        self.assertEqual(wp_last["frame"], 61)
        self.assertAlmostEqual(wp_last["location"][0], 6.0, places=2)
        self.assertAlmostEqual(wp_last["location"][1], 0.0, places=2)

    def test_dolly_waypoints_computation(self):
        """Verifies linear dolly waypoints and look-at tracking."""
        choreographer = CameraChoreographer()
        config = DollyShotConfig(
            camera_name="DollyCam",
            start_location=(0.0, -10.0, 3.0),
            end_location=(0.0, -2.0, 1.0),
            target_point=(0.0, 0.0, 0.5),
            frame_start=1,
            frame_end=31,
            step_frames=10,
        )

        waypoints = choreographer.compute_dolly_waypoints(config)
        self.assertEqual(len(waypoints), 4)  # frames 1, 11, 21, 31

        # Check start and end locations
        self.assertEqual(waypoints[0]["location"], [0.0, -10.0, 3.0])
        self.assertEqual(waypoints[-1]["location"], [0.0, -2.0, 1.0])

        # As camera pushes in, distance decreases and look-at angle adjusts
        self.assertLess(waypoints[-1]["location"][1], 0.0)

    def test_timeline_plan_validation(self):
        """Verifies timeline frame bounds enforcement [1, 250]."""
        # Valid plan
        track = TimelineTrack(object_name="Cube", property_path="location")
        track.add_keyframe(frame=1, value=(0, 0, 0))
        track.add_keyframe(frame=50, value=(0, 0, 5))
        plan = ShotTimelinePlan(name="ValidPlan", frame_start=1, frame_end=60, tracks=[track])
        self.assertEqual(len(plan.tracks), 1)

        # Invalid frame range: start < 1
        with self.assertRaises(ValueError):
            ShotTimelinePlan(name="BadStart", frame_start=0, frame_end=60)

        # Invalid frame range: end > 250
        with self.assertRaises(ValueError):
            ShotTimelinePlan(name="BadEnd", frame_start=1, frame_end=300)

        # Keyframe outside plan range
        bad_track = TimelineTrack(object_name="Cube", property_path="location")
        bad_track.add_keyframe(frame=70, value=(0, 0, 0))
        with self.assertRaises(ValueError):
            ShotTimelinePlan(name="BadKF", frame_start=1, frame_end=60, tracks=[bad_track])

    def test_shot_orchestrator_execution(self):
        """Verifies multi-track execution with Mock executor."""
        orchestrator = ShotOrchestrator()
        mock_exec = MockBlenderExecutor()

        track1 = TimelineTrack(object_name="Camera", property_path="location")
        track1.add_keyframe(frame=1, value=(0, -5, 2))
        track1.add_keyframe(frame=30, value=(0, -2, 1))

        track2 = TimelineTrack(object_name="KeyLight", property_path="location")
        track2.add_keyframe(frame=1, value=(5, 5, 5))
        track2.add_keyframe(frame=30, value=(5, 5, 8))

        plan = ShotTimelinePlan(name="MultiTrackShot", frame_start=1, frame_end=30, tracks=[track1, track2])
        res = orchestrator.execute_timeline_plan(mock_exec, plan)

        self.assertTrue(res["success"])
        self.assertEqual(res["total_keyframes_applied"], 4)
        self.assertEqual(len(mock_exec.tool_calls), 4)

    def test_physics_bake_synchronizer(self):
        """Verifies physics simulation sync and marker frame trajectory readback."""
        sync = PhysicsBakeSynchronizer()
        mock_exec = MockBlenderExecutor()

        # 1. sync_and_bake
        bake_res = sync.sync_and_bake(mock_exec, physics_type="RIGID_BODY", frame_start=1, frame_end=40)
        self.assertTrue(bake_res["success"])

        # 2. evaluate_marker_frames
        marker_data = sync.evaluate_marker_frames(mock_exec, objects=["FallingSphere"], marker_frames=[1, 20, 40])
        self.assertIn(1, marker_data)
        self.assertIn(20, marker_data)
        self.assertIn(40, marker_data)

        z1 = marker_data[1]["FallingSphere"][2]
        z40 = marker_data[40]["FallingSphere"][2]
        self.assertGreater(z1, z40)  # Dropping trajectory verified


if __name__ == "__main__":
    unittest.main()

