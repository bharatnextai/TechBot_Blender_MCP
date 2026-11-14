"""
Unit Tests for Viewport Capture Operator Compatibility (TASK-UMCP-0024).

Validates:
1. Supported modes: VIEWPORT (view_context=True) and CAMERA (view_context=False).
2. Operator properties: keyword 'view' is never passed; 'view_context' is passed.
3. Input validation: width, height, valid modes, and invalid mode rejection.
4. Context-unavailable handling: background mode without 3D view, GUI without 3D view,
   and operator poll/no-opengl-context runtime error translation.
5. Render settings preservation via try...finally without scene mutation.
"""

import base64
import os
import unittest
from unittest.mock import MagicMock

from blender_addon.universal_mcp.bridge.handlers import handle_capture_viewport
from shared.schemas.tool_schemas import (
    validate_tool_input,
    TOOL_CAPTURE_VIEWPORT,
    PERMISSION_READ_ONLY,
    TOOL_DEFINITIONS,
)


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestViewportCaptureOperator(unittest.TestCase):
    def setUp(self):
        self.mock_bpy = MagicMock()
        self.mock_bpy.app.background = False

        self.scene = MagicMock()
        self.scene.render.resolution_x = 1920
        self.scene.render.resolution_y = 1080
        self.scene.render.resolution_percentage = 100
        self.scene.render.filepath = "//original/render.png"
        self.scene.render.image_settings.file_format = "JPEG"
        self.scene.camera = MagicMock()
        self.mock_bpy.context.scene = self.scene

        # Setup active window with a VIEW_3D area
        self.region = MagicMock()
        self.region.type = "WINDOW"
        self.area = MagicMock()
        self.area.type = "VIEW_3D"
        self.area.regions = [self.region]
        self.screen = MagicMock()
        self.screen.areas = [self.area]
        self.window = MagicMock()
        self.window.screen = self.screen
        self.mock_bpy.context.window_manager.windows = [self.window]
        self.mock_bpy.context.area = self.area

        # Default side effect for mock render to produce a valid PNG file
        def fake_render(*args, **kwargs):
            out_path = self.scene.render.filepath
            with open(out_path, "wb") as f:
                f.write(TINY_PNG)

        self.mock_bpy.ops.render.opengl.side_effect = fake_render
        self.mock_bpy.ops.render.render.side_effect = fake_render

    def test_permission_tier_read_only(self):
        defn = TOOL_DEFINITIONS[TOOL_CAPTURE_VIEWPORT]
        self.assertEqual(defn["permission_tier"], PERMISSION_READ_ONLY)

    def test_viewport_mode_passes_view_context_true_and_no_view_kwarg(self):
        params = {"width": 640, "height": 480, "mode": "VIEWPORT"}
        res = handle_capture_viewport(bpy_module=self.mock_bpy, params=params)

        self.assertTrue(self.mock_bpy.ops.render.opengl.called)
        _, kwargs = self.mock_bpy.ops.render.opengl.call_args
        self.assertTrue(kwargs.get("write_still"))
        self.assertTrue(kwargs.get("view_context"))
        self.assertNotIn("view", kwargs, "Keyword 'view' must not be passed to bpy.ops.render.opengl")

        self.assertEqual(res["format"], "png")
        self.assertEqual(res["width"], 640)
        self.assertEqual(res["height"], 480)
        self.assertEqual(res["mode"], "VIEWPORT")
        self.assertTrue(res["read_only"])
        decoded = base64.b64decode(res["image_base64"])
        self.assertEqual(decoded, TINY_PNG)

    def test_camera_mode_passes_view_context_false_and_no_view_kwarg(self):
        params = {"width": 800, "height": 600, "mode": "CAMERA"}
        res = handle_capture_viewport(bpy_module=self.mock_bpy, params=params)

        self.assertTrue(self.mock_bpy.ops.render.opengl.called)
        _, kwargs = self.mock_bpy.ops.render.opengl.call_args
        self.assertTrue(kwargs.get("write_still"))
        self.assertFalse(kwargs.get("view_context"))
        self.assertNotIn("view", kwargs, "Keyword 'view' must not be passed to bpy.ops.render.opengl")

        self.assertEqual(res["mode"], "CAMERA")
        self.assertEqual(res["width"], 800)
        self.assertEqual(res["height"], 600)

    def test_camera_mode_requires_active_camera(self):
        self.scene.camera = None
        with self.assertRaises(ValueError) as ctx:
            handle_capture_viewport(bpy_module=self.mock_bpy, params={"mode": "CAMERA"})
        self.assertIn("DATA_UNAVAILABLE", str(ctx.exception))
        self.assertIn("active camera", str(ctx.exception))

    def test_schema_validation_modes_and_bounds(self):
        # Valid modes
        v1 = validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"mode": "viewport", "width": 128, "height": 128})
        self.assertEqual(v1["mode"], "VIEWPORT")
        v2 = validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"mode": "camera"})
        self.assertEqual(v2["mode"], "CAMERA")

        # Invalid mode
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"mode": "ORTHOGRAPHIC"})

        # Out-of-bounds resolution
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"width": 32})
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"width": 4096})

    def test_context_unavailable_headless_background_rejection(self):
        self.mock_bpy.app.background = True
        self.mock_bpy.context.window_manager.windows = []

        with self.assertRaises(RuntimeError) as ctx:
            handle_capture_viewport(bpy_module=self.mock_bpy, params={"mode": "VIEWPORT"})
        self.assertIn("CONTEXT_UNAVAILABLE", str(ctx.exception))
        self.assertIn("Headless background mode does not have an active 3D viewport", str(ctx.exception))

    def test_context_unavailable_gui_without_3d_viewport(self):
        # Window exists but has only text or properties editor, no VIEW_3D
        non_3d_area = MagicMock()
        non_3d_area.type = "TEXT_EDITOR"
        self.screen.areas = [non_3d_area]
        self.mock_bpy.context.area = non_3d_area

        with self.assertRaises(RuntimeError) as ctx:
            handle_capture_viewport(bpy_module=self.mock_bpy, params={"mode": "VIEWPORT"})
        self.assertIn("CONTEXT_UNAVAILABLE", str(ctx.exception))
        self.assertIn("No active 3D Viewport area was found", str(ctx.exception))

    def test_context_unavailable_on_operator_poll_failure(self):
        self.mock_bpy.ops.render.opengl.side_effect = RuntimeError(
            "Operator bpy.ops.render.opengl.poll() failed, context is incorrect"
        )
        with self.assertRaises(RuntimeError) as ctx:
            handle_capture_viewport(bpy_module=self.mock_bpy, params={"mode": "VIEWPORT"})
        self.assertIn("CONTEXT_UNAVAILABLE", str(ctx.exception))
        self.assertIn("unavailable GUI/OpenGL context", str(ctx.exception))

    def test_context_unavailable_on_no_opengl_context(self):
        self.mock_bpy.ops.render.opengl.side_effect = RuntimeError(
            "Error: Cannot use OpenGL render in background mode (no opengl context)"
        )
        with self.assertRaises(RuntimeError) as ctx:
            handle_capture_viewport(bpy_module=self.mock_bpy, params={"mode": "VIEWPORT"})
        self.assertIn("CONTEXT_UNAVAILABLE", str(ctx.exception))
        self.assertIn("unavailable GUI/OpenGL context", str(ctx.exception))

    def test_render_settings_restored_on_success_and_failure(self):
        # 1. Success case
        handle_capture_viewport(bpy_module=self.mock_bpy, params={"width": 640, "height": 480})
        self.assertEqual(self.scene.render.resolution_x, 1920)
        self.assertEqual(self.scene.render.resolution_y, 1080)
        self.assertEqual(self.scene.render.resolution_percentage, 100)
        self.assertEqual(self.scene.render.filepath, "//original/render.png")
        self.assertEqual(self.scene.render.image_settings.file_format, "JPEG")

        # 2. Failure case
        self.mock_bpy.ops.render.opengl.side_effect = RuntimeError("Render crash")
        with self.assertRaises(RuntimeError):
            handle_capture_viewport(bpy_module=self.mock_bpy, params={"width": 1024, "height": 768})

        self.assertEqual(self.scene.render.resolution_x, 1920)
        self.assertEqual(self.scene.render.resolution_y, 1080)
        self.assertEqual(self.scene.render.resolution_percentage, 100)
        self.assertEqual(self.scene.render.filepath, "//original/render.png")
        self.assertEqual(self.scene.render.image_settings.file_format, "JPEG")


if __name__ == "__main__":
    unittest.main()
