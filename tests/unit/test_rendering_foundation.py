"""
Unit tests for Capability 10: Rendering Foundation (v0.1.70).
Verifies:
- Still render output verification with fresh file signatures and receipt registration
- Animation multi-frame fresh output verification and frame receipt generation
- Rejection of stale pre-existing files when operator produces no new output
- Rejection of invalid frame ranges (frame_start > frame_end)
- Rejection of scene without active camera or non-camera object
- Fail-closed security against untrusted approved=True injection
- configure_render_settings parameter validation and engine checking
- inspect_scene_data for categories 'render_settings' and 'render_result'
- Agent post-operation readback and verification for animation render tasks
- Rejection of unknown / expired render output receipts
"""

import os
import shutil
import tempfile
import time
import unittest
from types import SimpleNamespace as NS

from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_RENDER_SCENE,
    TOOL_CONFIGURE_RENDER_SETTINGS,
    TOOL_INSPECT_RENDER_OUTPUT,
    TOOL_INSPECT_SCENE_DATA,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import (
    handle_render_scene,
    handle_configure_render_settings,
    handle_inspect_scene_data,
    handle_create_camera,
)
from blender_addon.universal_mcp.bridge import render_outputs
from mcp_service.agents.render_lighting import RenderLightingAgent
from tests.unit.test_render_scene import MockBpy, MockCameraObject, MockNonCameraObject, render_png


class TestRenderingFoundationStill(unittest.TestCase):
    """Tests for still-frame rendering and output receipt inspection."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="umcp_render_test_")
        self.bpy = MockBpy(self.temp_dir, write_files=True)
        self.cam = MockCameraObject("MainCamera")
        self.bpy.data.objects["MainCamera"] = self.cam
        self.bpy.scene.camera = self.cam
        render_outputs._receipts.clear()

    def tearDown(self):
        render_outputs._receipts.clear()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_still_render_generates_fresh_receipt(self):
        out_file = os.path.join(self.temp_dir, "still_output.png")
        params = {
            "render_mode": "still",
            "frame": 1,
            "output_path": out_file,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_render_scene(self.bpy, params)
        self.assertTrue(res["rendered"])
        self.assertTrue(res["operator_completed"])
        self.assertEqual(res["render_mode"], "still")
        self.assertIsNotNone(res["render_id"])
        self.assertEqual(res["total_frames"], 1)
        self.assertTrue(os.path.exists(res["output_file"]))

        # Inspect generated receipt via inspect_render_output
        insp = render_outputs.handle_inspect_render_output(
            bpy_module=self.bpy,
            params={"render_id": res["render_id"]}
        )
        self.assertTrue(insp["success"])
        self.assertTrue(insp["verified"])
        self.assertEqual(insp["render_id"], res["render_id"])
        self.assertEqual(insp["frame"], 1)
        self.assertEqual(insp["camera"], "MainCamera")
        self.assertTrue(insp["artifact"]["png_structure_verified"])
        self.assertEqual(insp["artifact"]["path"], res["output_file"])

    def test_still_render_rejects_stale_preexisting_file(self):
        out_file = os.path.join(self.temp_dir, "stale_render.png")
        # Write pre-existing bytes
        with open(out_file, "wb") as f:
            f.write(b"PRE_EXISTING_OLD_BYTES")

        # Disable mock operator from writing fresh bytes
        self.bpy.ops.render.render = lambda write_still=False: {"FINISHED"}
        params = {
            "render_mode": "still",
            "frame": 1,
            "output_path": out_file,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            handle_render_scene(self.bpy, params)
        self.assertIn("No fresh output was verified", str(ctx.exception))


class TestRenderingFoundationAnimation(unittest.TestCase):
    """Tests for multi-frame animation rendering and receipts."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="umcp_anim_test_")
        self.bpy = MockBpy(self.temp_dir, write_files=True)
        self.cam = MockCameraObject("AnimCamera")
        self.bpy.data.objects["AnimCamera"] = self.cam
        self.bpy.scene.camera = self.cam
        render_outputs._receipts.clear()

    def tearDown(self):
        render_outputs._receipts.clear()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_animation_render_all_frames_and_receipts(self):
        out_base = os.path.join(self.temp_dir, "seq_")
        self.bpy.scene.render.filepath = out_base
        params = {
            "render_mode": "animation",
            "frame_start": 1,
            "frame_end": 3,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_render_scene(self.bpy, params)
        self.assertTrue(res["rendered"])
        self.assertTrue(res["operator_completed"])
        self.assertEqual(res["render_mode"], "animation")
        self.assertEqual(res["total_frames"], 3)
        self.assertEqual(len(res["output_paths"]), 3)
        self.assertEqual(len(res["frame_receipts"]), 3)
        self.assertEqual(len(res["render_ids"]), 3)

        # Verify each frame receipt is valid and inspectable
        for f_receipt in res["frame_receipts"]:
            rid = f_receipt["render_id"]
            insp = render_outputs.handle_inspect_render_output(
                bpy_module=self.bpy,
                params={"render_id": rid}
            )
            self.assertTrue(insp["verified"])
            self.assertEqual(insp["frame"], f_receipt["frame"])
            self.assertEqual(insp["artifact"]["path"], f_receipt["output_path"])
            self.assertTrue(insp["artifact"]["png_structure_verified"])

    def test_animation_render_rejects_stale_preexisting_frames(self):
        # Pre-create candidate files with stale bytes
        for f in range(1, 4):
            path = self.bpy.scene.render.frame_path(frame=f)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fp:
                fp.write(b"STALE_FRAME_BYTES")

        # Mock operator that finishes but writes no new frames
        self.bpy.ops.render.render = lambda animation=True, write_still=True: {"FINISHED"}

        params = {
            "render_mode": "animation",
            "frame_start": 1,
            "frame_end": 3,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            handle_render_scene(self.bpy, params)
        self.assertIn("stale contents", str(ctx.exception))

    def test_animation_render_invalid_frame_range(self):
        params = {
            "render_mode": "animation",
            "frame_start": 10,
            "frame_end": 5,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(ValueError) as ctx:
            handle_render_scene(self.bpy, params)
        self.assertIn("greater than frame_end", str(ctx.exception))


class TestRenderingFoundationSettingsAndSceneData(unittest.TestCase):
    """Tests for configure_render_settings and inspect_scene_data."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="umcp_settings_test_")
        self.bpy = MockBpy(self.temp_dir, write_files=True)
        self.cam = MockCameraObject("Cam1")
        self.bpy.data.objects["Cam1"] = self.cam
        self.bpy.scene.camera = self.cam

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_configure_render_settings_validation(self):
        # Valid settings
        params = {
            "engine": "CYCLES",
            "resolution_x": 1280,
            "resolution_y": 720,
            "resolution_percentage": 50,
            "frame_start": 1,
            "frame_end": 10,
            "fps": 30,
            "output_format": "PNG",
            "active_camera": "Cam1",
        }
        res = handle_configure_render_settings(self.bpy, params)
        self.assertEqual(res["engine"], "CYCLES")
        self.assertEqual(res["resolution_x"], 1280)
        self.assertEqual(res["resolution_y"], 720)
        self.assertEqual(res["resolution_percentage"], 50)
        self.assertEqual(res["active_camera"], "Cam1")

        # Invalid engine
        with self.assertRaises(ValueError) as ctx:
            handle_configure_render_settings(self.bpy, {"engine": "UNKNOWN_ENGINE"})
        self.assertIn("Unsupported render engine", str(ctx.exception))

        # Invalid bounds
        with self.assertRaises(ValueError):
            handle_configure_render_settings(self.bpy, {"resolution_x": 0})
        with self.assertRaises(ValueError):
            handle_configure_render_settings(self.bpy, {"resolution_percentage": 2000})

        # Non-camera active_camera
        mesh_obj = MockNonCameraObject("Cube")
        self.bpy.data.objects["Cube"] = mesh_obj
        with self.assertRaises(ValueError) as ctx:
            handle_configure_render_settings(self.bpy, {"active_camera": "Cube"})
        self.assertIn("is not of type CAMERA", str(ctx.exception))

    def test_inspect_scene_data_render_settings_and_result(self):
        # inspect render_settings
        res_settings = handle_inspect_scene_data(self.bpy, {"category": "render_settings"})
        self.assertEqual(res_settings["category"], "render_settings")
        self.assertIn("engine", res_settings)
        self.assertIn("resolution_x", res_settings)
        self.assertIn("resolution_y", res_settings)
        self.assertIn("output_format", res_settings)

        # inspect render_result
        res_result = handle_inspect_scene_data(self.bpy, {"category": "render_result"})
        self.assertEqual(res_result["category"], "render_result")
        self.assertIn("available", res_result)
        self.assertIn("width", res_result)
        self.assertIn("height", res_result)


class TestRenderingFoundationSecurity(unittest.TestCase):
    """Tests security boundaries, untrusted approved=True rejection, and receipt limits."""

    def test_untrusted_approved_true_rejected_in_schema(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_RENDER_SCENE, {"approved": True}, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize", str(ctx.exception))

    def test_unknown_or_expired_receipt_rejected(self):
        render_outputs._receipts.clear()
        with self.assertRaises(ValueError) as ctx:
            render_outputs.handle_inspect_render_output(
                params={"render_id": "0123456789abcdef0123456789abcdef"}
            )
        self.assertIn("not found", str(ctx.exception))

    def test_invalid_render_id_format_rejected(self):
        with self.assertRaises(ValueError):
            render_outputs.validate_render_id({"render_id": "short"})
        with self.assertRaises(ValueError):
            render_outputs.validate_render_id({"render_id": "uppercase"*2 + "1234567890"})


class TestRenderingFoundationAgentVerification(unittest.TestCase):
    """Tests agent execution and post-operation verification for animation render."""

    def test_agent_animation_render_verification_success(self):
        agent = RenderLightingAgent()
        receipt_id = "f" * 32

        class MockExecutor:
            def execute_tool(self, tool_name, params, **kwargs):
                if tool_name == "inspect_render_output":
                    return BridgeResponse.success({
                        "success": True,
                        "verified": True,
                        "render_id": params.get("render_id"),
                        "width": 64,
                        "height": 64,
                        "frame": 1,
                        "camera": "Cam",
                        "file_format": "PNG",
                        "artifact": {
                            "path": "/tmp/frame_0001.png",
                            "sha256": "c" * 64,
                            "size_bytes": 128,
                            "width": 64,
                            "height": 64,
                            "png_structure_verified": True,
                        },
                    })
                return BridgeResponse.success({
                    "rendered": True,
                    "operator_completed": True,
                    "render_mode": "animation",
                    "frame_start": 1,
                    "frame_end": 2,
                    "total_frames": 2,
                    "output_paths": ["/tmp/frame_0001.png", "/tmp/frame_0002.png"],
                    "output_file": "/tmp/frame_0001.png",
                    "render_ids": [receipt_id, "e" * 32],
                    "frame_receipts": [
                        {"frame": 1, "render_id": receipt_id, "output_path": "/tmp/frame_0001.png"},
                        {"frame": 2, "render_id": "e" * 32, "output_path": "/tmp/frame_0002.png"},
                    ],
                    "camera": "Cam",
                    "render_duration_seconds": 0.5,
                })

        task = AgentTask(
            task_id="anim-task-1",
            required_capability="world.manage",
            task_type=TOOL_RENDER_SCENE,
            input_params={"render_mode": "animation", "frame_start": 1, "frame_end": 2},
        )
        res = agent.execute_task(task, executor=MockExecutor(), trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.verification.status, "PASS")
        self.assertTrue(res.verification.observed_results["render_verified"])


class TestCapability73Phase1RenderSettings(unittest.TestCase):
    """Unit tests for Capability 7.3 Phase 1: Production Rendering, Color Management & Alpha Output."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="umcp_cap73_test_")
        self.bpy = MockBpy(self.temp_dir, write_files=True)
        self.cam = MockCameraObject("MainCam")
        self.bpy.data.objects["MainCam"] = self.cam
        self.bpy.scene.camera = self.cam

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_configure_film_transparency(self):
        """Configure film_transparent for alpha output and verify readback."""
        res = handle_configure_render_settings(self.bpy, {"film_transparent": True})
        self.assertTrue(res["film_transparent"])
        self.assertTrue(self.bpy.scene.render.film_transparent)

        insp = handle_inspect_scene_data(self.bpy, {"category": "render_settings"})
        self.assertTrue(insp["film_transparent"])

        # Reset back to False
        res2 = handle_configure_render_settings(self.bpy, {"film_transparent": False})
        self.assertFalse(res2["film_transparent"])
        self.assertFalse(self.bpy.scene.render.film_transparent)

    def test_configure_color_management_flat_and_nested(self):
        """Configure view_transform, look, exposure via flat parameters and nested dict."""
        # Flat configuration
        res1 = handle_configure_render_settings(self.bpy, {
            "view_transform": "AgX",
            "look": "Medium Contrast",
            "exposure": 1.25,
        })
        self.assertEqual(res1["view_transform"], "AgX")
        self.assertEqual(res1["look"], "Medium Contrast")
        self.assertEqual(res1["exposure"], 1.25)
        self.assertEqual(res1["color_management"]["view_transform"], "AgX")
        self.assertEqual(self.bpy.scene.view_settings.view_transform, "AgX")
        self.assertEqual(self.bpy.scene.view_settings.look, "Medium Contrast")
        self.assertEqual(self.bpy.scene.view_settings.exposure, 1.25)

        # Nested configuration
        res2 = handle_configure_render_settings(self.bpy, {
            "color_management": {
                "view_transform": "Filmic",
                "look": "High Contrast",
                "exposure": -0.5,
            }
        })
        self.assertEqual(res2["view_transform"], "Filmic")
        self.assertEqual(res2["look"], "High Contrast")
        self.assertEqual(res2["exposure"], -0.5)

        insp = handle_inspect_scene_data(self.bpy, {"category": "render_settings"})
        self.assertEqual(insp["view_transform"], "Filmic")
        self.assertEqual(insp["look"], "High Contrast")
        self.assertEqual(insp["exposure"], -0.5)

    def test_configure_cycles_denoising(self):
        """Configure Cycles denoising and denoiser selection."""
        res = handle_configure_render_settings(self.bpy, {
            "engine": "CYCLES",
            "use_denoising": True,
            "denoiser": "OPENIMAGEDENOISE",
        })
        self.assertEqual(res["engine"], "CYCLES")
        self.assertTrue(res["use_denoising"])
        self.assertEqual(res["denoiser"], "OPENIMAGEDENOISE")
        self.assertTrue(self.bpy.scene.cycles.use_denoising)
        self.assertEqual(self.bpy.scene.cycles.denoiser, "OPENIMAGEDENOISE")

        insp = handle_inspect_scene_data(self.bpy, {"category": "render_settings"})
        self.assertTrue(insp["cycles"]["use_denoising"])
        self.assertEqual(insp["cycles"]["denoiser"], "OPENIMAGEDENOISE")

        # Switch to OPTIX
        res_optix = handle_configure_render_settings(self.bpy, {"denoiser": "OPTIX"})
        self.assertEqual(res_optix["denoiser"], "OPTIX")
        self.assertEqual(self.bpy.scene.cycles.denoiser, "OPTIX")

    def test_configure_cycles_bounce_limits_flat_and_nested(self):
        """Configure Cycles light-path bounce limits via flat parameters and nested dict."""
        # Flat configuration
        bounces_params = {
            "max_bounces": 16,
            "diffuse_bounces": 6,
            "glossy_bounces": 6,
            "transmission_bounces": 12,
            "volume_bounces": 2,
            "transparent_max_bounces": 10,
        }
        res1 = handle_configure_render_settings(self.bpy, bounces_params)
        self.assertEqual(res1["max_bounces"], 16)
        self.assertEqual(res1["diffuse_bounces"], 6)
        self.assertEqual(res1["glossy_bounces"], 6)
        self.assertEqual(res1["transmission_bounces"], 12)
        self.assertEqual(res1["volume_bounces"], 2)
        self.assertEqual(res1["transparent_max_bounces"], 10)

        c = self.bpy.scene.cycles
        self.assertEqual(c.max_bounces, 16)
        self.assertEqual(c.diffuse_bounces, 6)
        self.assertEqual(c.glossy_bounces, 6)
        self.assertEqual(c.transmission_bounces, 12)
        self.assertEqual(c.volume_bounces, 2)
        self.assertEqual(c.transparent_max_bounces, 10)

        # Nested configuration
        res2 = handle_configure_render_settings(self.bpy, {
            "cycles": {
                "max_bounces": 8,
                "diffuse_bounces": 2,
                "glossy_bounces": 2,
            }
        })
        self.assertEqual(res2["max_bounces"], 8)
        self.assertEqual(res2["diffuse_bounces"], 2)
        self.assertEqual(res2["glossy_bounces"], 2)

    def test_validation_fail_closed_color_management_and_cycles(self):
        """Fail-closed validation on invalid enums, bounds, and types."""
        # Invalid view_transform
        with self.assertRaises(ValueError) as ctx1:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"view_transform": "INVALID_TRANSFORM"}, trusted_approval=True)
        self.assertIn("view_transform", str(ctx1.exception))

        # Invalid look
        with self.assertRaises(ValueError) as ctx2:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"look": "SUPER_HIGH_CONTRAST"}, trusted_approval=True)
        self.assertIn("look", str(ctx2.exception))

        # Out-of-bounds exposure
        with self.assertRaises(ValueError) as ctx3:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"exposure": 50.0}, trusted_approval=True)
        self.assertIn("exposure", str(ctx3.exception))

        # Invalid denoiser
        with self.assertRaises(ValueError) as ctx4:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"denoiser": "UNKNOWN_DENOISER"}, trusted_approval=True)
        self.assertIn("denoiser", str(ctx4.exception))

        # Out-of-bounds bounce limit
        with self.assertRaises(ValueError) as ctx5:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"max_bounces": 2000}, trusted_approval=True)
        self.assertIn("max_bounces", str(ctx5.exception))

        with self.assertRaises(ValueError) as ctx6:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"diffuse_bounces": -1}, trusted_approval=True)
        self.assertIn("diffuse_bounces", str(ctx6.exception))

        # Non-boolean film_transparent
        with self.assertRaises(ValueError) as ctx7:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"film_transparent": "yes"}, trusted_approval=True)
        self.assertIn("film_transparent", str(ctx7.exception))


class TestCapability73Phase2RenderOptimization(unittest.TestCase):
    """Unit tests for Capability 7.3 Phase 2: Render Engine & Output Optimization."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="umcp_opt_test_")
        self.bpy = MockBpy(self.temp_dir)
        self.cam = MockCameraObject("OptCamera")
        self.bpy.data.objects["OptCamera"] = self.cam
        self.bpy.scene.camera = self.cam

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_configure_image_settings_flat_and_readback(self):
        """Configure image format properties (color_mode, color_depth, compression, quality) and verify readback."""
        res = handle_configure_render_settings(self.bpy, {
            "output_format": "PNG",
            "color_mode": "RGBA",
            "color_depth": "16",
            "compression": 50,
            "quality": 95,
        })
        self.assertEqual(res["output_format"], "PNG")
        self.assertEqual(res["color_mode"], "RGBA")
        self.assertEqual(res["color_depth"], "16")
        self.assertEqual(res["compression"], 50)
        self.assertEqual(res["quality"], 95)

        img_set = self.bpy.scene.render.image_settings
        self.assertEqual(img_set.color_mode, "RGBA")
        self.assertEqual(img_set.color_depth, "16")
        self.assertEqual(img_set.compression, 50)
        self.assertEqual(img_set.quality, 95)

        insp = handle_inspect_scene_data(self.bpy, {"category": "render_settings"})
        self.assertEqual(insp["output_format"], "PNG")
        self.assertEqual(insp["color_mode"], "RGBA")
        self.assertEqual(insp["color_depth"], "16")
        self.assertEqual(insp["compression"], 50)
        self.assertEqual(insp["quality"], 95)

    def test_configure_gamma_flat_and_nested(self):
        """Configure color management gamma adjustment flat and nested."""
        # Flat configuration
        res1 = handle_configure_render_settings(self.bpy, {"gamma": 1.25})
        self.assertEqual(res1["gamma"], 1.25)
        self.assertEqual(res1["color_management"]["gamma"], 1.25)
        self.assertEqual(self.bpy.scene.view_settings.gamma, 1.25)

        # Nested configuration
        res2 = handle_configure_render_settings(self.bpy, {
            "color_management": {"gamma": 0.9}
        })
        self.assertEqual(res2["gamma"], 0.9)
        self.assertEqual(res2["color_management"]["gamma"], 0.9)
        self.assertEqual(self.bpy.scene.view_settings.gamma, 0.9)

        # Scene inspection
        insp = handle_inspect_scene_data(self.bpy, {"category": "render_settings"})
        self.assertEqual(insp["gamma"], 0.9)
        self.assertEqual(insp["color_management"]["gamma"], 0.9)

    def test_configure_cycles_adaptive_sampling_and_time_limit_flat_and_nested(self):
        """Configure Cycles engine optimization: time_limit, adaptive sampling threshold, and min samples."""
        # Flat configuration
        res1 = handle_configure_render_settings(self.bpy, {
            "time_limit": 45.0,
            "use_adaptive_sampling": True,
            "adaptive_threshold": 0.03,
            "adaptive_min_samples": 64,
        })
        self.assertEqual(res1["time_limit"], 45.0)
        self.assertTrue(res1["use_adaptive_sampling"])
        self.assertEqual(res1["adaptive_threshold"], 0.03)
        self.assertEqual(res1["adaptive_min_samples"], 64)
        self.assertEqual(res1["cycles"]["time_limit"], 45.0)
        self.assertTrue(res1["cycles"]["use_adaptive_sampling"])
        self.assertEqual(res1["cycles"]["adaptive_threshold"], 0.03)
        self.assertEqual(res1["cycles"]["adaptive_min_samples"], 64)

        c = self.bpy.scene.cycles
        self.assertEqual(c.time_limit, 45.0)
        self.assertTrue(c.use_adaptive_sampling)
        self.assertEqual(c.adaptive_threshold, 0.03)
        self.assertEqual(c.adaptive_min_samples, 64)

        # Nested configuration
        res2 = handle_configure_render_settings(self.bpy, {
            "cycles": {
                "time_limit": 15.5,
                "use_adaptive_sampling": False,
                "adaptive_threshold": 0.01,
                "adaptive_min_samples": 16,
            }
        })
        self.assertEqual(res2["time_limit"], 15.5)
        self.assertFalse(res2["use_adaptive_sampling"])
        self.assertEqual(res2["adaptive_threshold"], 0.01)
        self.assertEqual(res2["adaptive_min_samples"], 16)
        self.assertEqual(c.time_limit, 15.5)
        self.assertFalse(c.use_adaptive_sampling)
        self.assertEqual(c.adaptive_threshold, 0.01)
        self.assertEqual(c.adaptive_min_samples, 16)

        # Inspection readback
        insp = handle_inspect_scene_data(self.bpy, {"category": "render_settings"})
        self.assertEqual(insp["time_limit"], 15.5)
        self.assertFalse(insp["use_adaptive_sampling"])
        self.assertEqual(insp["adaptive_threshold"], 0.01)
        self.assertEqual(insp["adaptive_min_samples"], 16)
        self.assertEqual(insp["cycles"]["time_limit"], 15.5)
        self.assertFalse(insp["cycles"]["use_adaptive_sampling"])
        self.assertEqual(insp["cycles"]["adaptive_threshold"], 0.01)
        self.assertEqual(insp["cycles"]["adaptive_min_samples"], 16)

    def test_validation_fail_closed_image_settings_and_engine_limits(self):
        """Verify fail-closed rejection for invalid output settings and engine parameters."""
        # Invalid color mode
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"color_mode": "CMYK"}, trusted_approval=True)
        self.assertIn("color_mode", str(ctx.exception))

        # Invalid color depth
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"color_depth": "24"}, trusted_approval=True)
        self.assertIn("color_depth", str(ctx.exception))

        # Out-of-bounds compression
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"compression": 105}, trusted_approval=True)
        self.assertIn("compression", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"compression": -1}, trusted_approval=True)
        self.assertIn("compression", str(ctx.exception))

        # Out-of-bounds quality
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"quality": 0}, trusted_approval=True)
        self.assertIn("quality", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"quality": 101}, trusted_approval=True)
        self.assertIn("quality", str(ctx.exception))

        # Out-of-bounds gamma
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"gamma": 40.0}, trusted_approval=True)
        self.assertIn("gamma", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"color_management": {"gamma": -35.0}}, trusted_approval=True)
        self.assertIn("gamma", str(ctx.exception))

        # Negative time_limit
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"time_limit": -10.0}, trusted_approval=True)
        self.assertIn("time_limit", str(ctx.exception))

        # Out-of-bounds adaptive threshold
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"adaptive_threshold": 1.5}, trusted_approval=True)
        self.assertIn("adaptive_threshold", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"cycles": {"adaptive_threshold": -0.05}}, trusted_approval=True)
        self.assertIn("adaptive_threshold", str(ctx.exception))

        # Out-of-bounds adaptive min samples
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"adaptive_min_samples": 70000}, trusted_approval=True)
        self.assertIn("adaptive_min_samples", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_RENDER_SETTINGS, {"cycles": {"adaptive_min_samples": -5}}, trusted_approval=True)
        self.assertIn("adaptive_min_samples", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

