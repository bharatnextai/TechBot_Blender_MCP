"""
Unit tests for the render_scene tool in Universal MCP (v0.1.16).
Tests schema definition, input validation, permission tiers, approval enforcement,
still-frame rendering, animation rendering, output file verification, and agent routing.
"""

import unittest
import tempfile
import os
import time
import struct
import zlib
from typing import Dict, Any, Optional

from shared.models.agent_contracts import (
    AgentManifest,
    AgentTask,
    AgentResult,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_RENDER_SCENE,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_render_scene,
    handle_create_camera,
)
from mcp_service.security.approval import ApprovalManager
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.agents.render_lighting import (
    RenderLightingAgent,
    RENDER_LIGHTING_AGENT_ID,
    CAPABILITY_WORLD_MANAGE,
)
from mcp_service.agents.dispatcher import AgentDispatcher


class MockCameraObject:
    def __init__(self, name: str):
        self.name = name
        self.type = "CAMERA"
        self.location = (0.0, 0.0, 0.0)
        self.rotation_euler = (0.0, 0.0, 0.0)


class MockNonCameraObject:
    def __init__(self, name: str):
        self.name = name
        self.type = "MESH"


class MockImageSettings:
    def __init__(self):
        self.file_format = "PNG"
        self.color_mode = "RGBA"
        self.color_depth = "8"
        self.compression = 15
        self.quality = 90


class MockViewSettings:
    def __init__(self):
        self.view_transform = "AgX"
        self.look = "None"
        self.exposure = 0.0
        self.gamma = 1.0


class MockCyclesSettings:
    def __init__(self):
        self.use_denoising = True
        self.denoiser = "OPENIMAGEDENOISE"
        self.samples = 128
        self.device = "CPU"
        self.max_bounces = 12
        self.diffuse_bounces = 4
        self.glossy_bounces = 4
        self.transmission_bounces = 12
        self.volume_bounces = 0
        self.transparent_max_bounces = 8
        self.time_limit = 0.0
        self.use_adaptive_sampling = True
        self.adaptive_threshold = 0.01
        self.adaptive_min_samples = 0


class MockRenderSettings:
    def __init__(self, test_dir: str):
        self.engine = "BLENDER_EEVEE_NEXT"
        self.resolution_x = 1920
        self.resolution_y = 1080
        self.resolution_percentage = 100
        self.fps = 24
        self.fps_base = 1.0
        self.filepath = os.path.join(test_dir, "render_output.png")
        self.image_settings = MockImageSettings()
        self.film_transparent = False

    def frame_path(self, frame: int) -> str:
        base, _ = os.path.splitext(self.filepath)
        ext = ".png" if self.image_settings.file_format == "PNG" else ".jpg"
        return f"{base}_{frame:04d}{ext}"


class MockSceneCollectionObjects:
    def __init__(self, scene):
        self.scene = scene

    def link(self, obj):
        self.scene.objects_in_scene[obj.name] = obj

    def unlink(self, obj):
        self.scene.objects_in_scene.pop(obj.name, None)


class MockSceneCollection:
    def __init__(self, scene):
        self.objects = MockSceneCollectionObjects(scene)


class MockScene:
    def __init__(self, test_dir: str):
        self.camera = None
        self.render = MockRenderSettings(test_dir)
        self.view_settings = MockViewSettings()
        self.cycles = MockCyclesSettings()
        self.umcp_require_scene_mutation_approval = False
        self.frame_current = 1
        self.frame_start = 1
        self.frame_end = 5
        self.objects_in_scene: Dict[str, Any] = {}
        self.collection = MockSceneCollection(self)

    def frame_set(self, frame: int):
        self.frame_current = frame

    @property
    def objects(self):
        return list(self.objects_in_scene.values())


def render_png(width, height):
    """Real encoded PNG for output-validation tests, not a nonempty placeholder."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes((1 + width * 4) * height))) + chunk(b"IEND", b""))


class MockRenderOps:
    def __init__(self, scene: MockScene, write_files: bool = True):
        self.scene = scene
        self.write_files = write_files
        self.rendered_stills = []
        self.rendered_animations = []

    def render(self, write_still: bool = False, animation: bool = False):
        if animation:
            self.rendered_animations.append((self.scene.frame_start, self.scene.frame_end))
            if self.write_files:
                for f in range(self.scene.frame_start, self.scene.frame_end + 1):
                    path = self.scene.render.frame_path(frame=f)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as fp:
                        fp.write(render_png(self.scene.render.resolution_x, self.scene.render.resolution_y))
        else:
            self.rendered_stills.append(self.scene.frame_current)
            if self.write_files:
                out_path = self.scene.render.filepath
                # If path has no extension, frame_path
                if not out_path.endswith(".png") and not out_path.endswith(".jpg"):
                    out_path = self.scene.render.frame_path(frame=self.scene.frame_current)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as fp:
                    fp.write(render_png(self.scene.render.resolution_x, self.scene.render.resolution_y))
        return {"FINISHED"}


class MockOps:
    def __init__(self, scene: MockScene, write_files: bool = True):
        self.render = MockRenderOps(scene, write_files=write_files)


class MockData:
    def __init__(self, scene: MockScene):
        self.scene = scene
        self.objects: Dict[str, Any] = {}

    def get(self, name: str, default=None):
        return self.objects.get(name, default)


class MockContext:
    def __init__(self, scene: MockScene):
        self.scene = scene


class MockPath:
    @staticmethod
    def abspath(path: str) -> str:
        return os.path.abspath(path.replace("//", "./"))


class MockBpy:
    def __init__(self, test_dir: str, write_files: bool = True):
        self.test_dir = test_dir
        self.scene = MockScene(test_dir)
        self.context = MockContext(self.scene)
        self.data = MockData(self.scene)
        self.ops = MockOps(self.scene, write_files=write_files)
        self.path = MockPath()


class TestRenderSceneSchemaAndValidation(unittest.TestCase):
    """Tests schema declaration and validate_tool_input for render_scene."""

    def test_schema_registration_and_tier(self):
        self.assertIn(TOOL_RENDER_SCENE, TOOL_DEFINITIONS)
        spec = TOOL_DEFINITIONS[TOOL_RENDER_SCENE]
        self.assertEqual(spec["name"], "render_scene")
        self.assertEqual(spec["permission_tier"], PERMISSION_SCENE_MUTATION)
        schema = spec["input_schema"]
        self.assertEqual(schema["type"], "object")
        props = schema["properties"]
        self.assertIn("render_mode", props)
        self.assertEqual(props["render_mode"]["default"], "still")
        self.assertEqual(props["render_mode"]["enum"], ["still", "animation"])
        self.assertIn("frame", props)
        self.assertIn("frame_start", props)
        self.assertIn("frame_end", props)
        self.assertIn("output_path", props)
        self.assertIn("output_format", props)
        self.assertIn("camera", props)

    def test_validate_tool_input_valid_still(self):
        params = {"render_mode": "still", "frame": 10}
        sanitized = validate_tool_input(TOOL_RENDER_SCENE, params, trusted_approval=True)
        self.assertEqual(sanitized["render_mode"], "still")
        self.assertEqual(sanitized["frame"], 10)
        self.assertTrue(sanitized.get("trusted_approval"))

    def test_validate_tool_input_valid_animation(self):
        params = {"render_mode": "animation", "frame_start": 1, "frame_end": 24}
        sanitized = validate_tool_input(TOOL_RENDER_SCENE, params, trusted_approval=True)
        self.assertEqual(sanitized["render_mode"], "animation")
        self.assertEqual(sanitized["frame_start"], 1)
        self.assertEqual(sanitized["frame_end"], 24)

    def test_validate_tool_input_default_mode(self):
        sanitized = validate_tool_input(TOOL_RENDER_SCENE, {}, trusted_approval=True)
        self.assertEqual(sanitized["render_mode"], "still")

    def test_validate_tool_input_invalid_mode(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_RENDER_SCENE, {"render_mode": "interactive"}, trusted_approval=True)
        self.assertIn("render_mode", str(ctx.exception))

    def test_validate_tool_input_invalid_frame_range(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(
                TOOL_RENDER_SCENE,
                {"render_mode": "animation", "frame_start": 50, "frame_end": 10},
                trusted_approval=True,
            )
        self.assertIn("frame_start (50) cannot exceed frame_end (10)", str(ctx.exception))

    def test_validate_tool_input_untrusted_approved_rejected(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_RENDER_SCENE, {"approved": True}, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize", str(ctx.exception))

    def test_validate_tool_input_missing_approval_raises(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_RENDER_SCENE, {}, trusted_approval=False)
        self.assertIn("requires explicit user approval", str(ctx.exception))


class TestRenderSceneSecurityAndApproval(unittest.TestCase):
    """Tests ApprovalManager integration for render_scene."""

    def setUp(self):
        self.approval_mgr = ApprovalManager()

    def test_requires_approval(self):
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_RENDER_SCENE))

    def test_verify_approval_untrusted_model_bypass(self):
        decision = self.approval_mgr.verify_approval(TOOL_RENDER_SCENE, {"approved": True})
        self.assertFalse(decision.approved)
        self.assertIn("untrusted", decision.reason or "")

    def test_verify_approval_without_provider(self):
        decision = self.approval_mgr.verify_approval(TOOL_RENDER_SCENE, {})
        self.assertFalse(decision.approved)
        self.assertIn("requires explicit user approval", decision.reason or "")


class TestRenderSceneExecutionHandler(unittest.TestCase):
    """Tests handle_render_scene with mock Blender execution environment."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.bpy = MockBpy(self.temp_dir, write_files=True)
        # Create default active camera
        cam = MockCameraObject("Camera")
        self.bpy.data.objects["Camera"] = cam
        self.bpy.scene.camera = cam

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_render_still_success(self):
        out_file = os.path.join(self.temp_dir, "my_still.png")
        params = {
            "render_mode": "still",
            "frame": 5,
            "output_path": out_file,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_render_scene(self.bpy, params)
        self.assertTrue(res["rendered"])
        self.assertEqual(res["render_mode"], "still")
        self.assertEqual(res["frame"], 5)
        self.assertEqual(res["total_frames"], 1)
        self.assertEqual(res["output_file"], os.path.realpath(out_file))
        self.assertTrue(os.path.exists(out_file))
        self.assertGreater(os.path.getsize(out_file), 0)
        self.assertEqual(res["camera"], "Camera")
        self.assertIn("render_duration_seconds", res)
        self.assertGreaterEqual(res["render_duration_seconds"], 0.0)

    def test_render_animation_success(self):
        out_base = os.path.join(self.temp_dir, "anim_")
        self.bpy.scene.render.filepath = out_base
        params = {
            "render_mode": "animation",
            "frame_start": 2,
            "frame_end": 4,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_render_scene(self.bpy, params)
        self.assertTrue(res["rendered"])
        self.assertEqual(res["render_mode"], "animation")
        self.assertEqual(res["frame_start"], 2)
        self.assertEqual(res["frame_end"], 4)
        self.assertEqual(res["total_frames"], 3)
        self.assertEqual(len(res["output_paths"]), 3)
        for p in res["output_paths"]:
            self.assertTrue(os.path.exists(p))
            self.assertGreater(os.path.getsize(p), 0)

    def test_render_missing_active_camera(self):
        self.bpy.scene.camera = None
        params = {
            "render_mode": "still",
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(ValueError) as ctx:
            handle_render_scene(self.bpy, params)
        self.assertIn("Scene has no active camera", str(ctx.exception))

    def test_render_specified_camera_not_found(self):
        params = {
            "render_mode": "still",
            "camera": "NonExistentCam",
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(ValueError) as ctx:
            handle_render_scene(self.bpy, params)
        self.assertIn("camera 'NonExistentCam' not found", str(ctx.exception))

    def test_render_specified_camera_wrong_type(self):
        mesh_obj = MockNonCameraObject("Cube")
        self.bpy.data.objects["Cube"] = mesh_obj
        params = {
            "render_mode": "still",
            "camera": "Cube",
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(ValueError) as ctx:
            handle_render_scene(self.bpy, params)
        self.assertIn("is not a camera", str(ctx.exception))

    def test_render_failed_output_file_missing(self):
        # Create bpy mock that doesn't write files
        no_write_bpy = MockBpy(self.temp_dir, write_files=False)
        cam = MockCameraObject("Camera")
        no_write_bpy.data.objects["Camera"] = cam
        no_write_bpy.scene.camera = cam

        params = {
            "render_mode": "still",
            "output_path": os.path.join(self.temp_dir, "ghost.png"),
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            handle_render_scene(no_write_bpy, params)
        self.assertIn("Render failed: Output file", str(ctx.exception))

    def test_render_animation_frame_missing(self):
        # Simulate an animation render where files fail to write
        no_write_bpy = MockBpy(self.temp_dir, write_files=False)
        cam = MockCameraObject("Camera")
        no_write_bpy.data.objects["Camera"] = cam
        no_write_bpy.scene.camera = cam

        params = {
            "render_mode": "animation",
            "frame_start": 1,
            "frame_end": 3,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            handle_render_scene(no_write_bpy, params)
        self.assertIn("Animation render incomplete", str(ctx.exception))


class TestRenderLightingAgentRenderScene(unittest.TestCase):
    """Tests RenderLightingAgent task handling for render_scene."""

    def setUp(self):
        self.agent = RenderLightingAgent()

    def test_manifest_declares_render_scene(self):
        manifest = self.agent.manifest
        found = False
        for cap in manifest.capabilities:
            if TOOL_RENDER_SCENE in cap.supported_task_types:
                found = True
                self.assertEqual(cap.capability_id, CAPABILITY_WORLD_MANAGE)
        self.assertTrue(found, "TOOL_RENDER_SCENE must be declared in world.manage capability")
        self.assertIn(TOOL_RENDER_SCENE, manifest.input_schemas)

    def test_can_handle_render_scene(self):
        task = AgentTask(
            task_id="task-1",
            required_capability=CAPABILITY_WORLD_MANAGE,
            task_type=TOOL_RENDER_SCENE,
        )
        self.assertTrue(self.agent.can_handle(task))

    def test_validate_task_input_valid(self):
        ok, code, msg = self.agent.validate_task_input(
            TOOL_RENDER_SCENE, {"render_mode": "still", "frame": 1}
        )
        self.assertTrue(ok)
        self.assertIsNone(code)

    def test_validate_task_input_invalid_frame_range(self):
        ok, code, msg = self.agent.validate_task_input(
            TOOL_RENDER_SCENE, {"render_mode": "animation", "frame_start": 100, "frame_end": 10}
        )
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_PARAMS")
        self.assertIn("frame_start (100) cannot exceed frame_end (10)", msg)

    def test_execute_task_model_approved_rejected(self):
        task = AgentTask(
            task_id="task-2",
            required_capability=CAPABILITY_WORLD_MANAGE,
            task_type=TOOL_RENDER_SCENE,
            input_params={"render_mode": "still", "approved": True},
        )
        res = self.agent.execute_task(task, executor=None, trusted_approval=False)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])

    def test_execute_task_awaiting_approval(self):
        task = AgentTask(
            task_id="task-3",
            required_capability=CAPABILITY_WORLD_MANAGE,
            task_type=TOOL_RENDER_SCENE,
            input_params={"render_mode": "still"},
        )
        res = self.agent.execute_task(task, executor=None, trusted_approval=None)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)

    def test_execute_task_trusted_approval_success(self):
        class MockExecutor:
            def execute_tool(self, tool_name, params, **kwargs):
                if tool_name == "inspect_render_output":
                    return BridgeResponse.success({"success": True, "verified": True, "render_id": "a"*32,
                        "width": 64, "height": 64, "frame": 1, "camera": "Camera", "file_format": "PNG",
                        "artifact": {"path": "/tmp/test.png", "sha256": "b"*64, "size_bytes": 100,
                            "width": 64, "height": 64, "png_structure_verified": True}})
                return BridgeResponse.success({
                    "render_id": "a"*32, "operator_completed": True, "width": 64, "height": 64, "frame": 1, "camera": "Camera",
                    "rendered": True,
                    "render_mode": "still",
                    "output_file": "/tmp/test.png",
                    "total_frames": 1,
                    "render_duration_seconds": 0.42,
                })

        task = AgentTask(
            task_id="task-4",
            required_capability=CAPABILITY_WORLD_MANAGE,
            task_type=TOOL_RENDER_SCENE,
            input_params={"render_mode": "still"},
        )
        res = self.agent.execute_task(task, executor=MockExecutor(), trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.verification.status, "PASS")
        self.assertTrue(res.verification.observed_results["render_verified"])


class TestToolRegistryAndDiscovery(unittest.TestCase):
    """Tests MCP tool discovery and ToolRegistry presence."""

    def test_registry_contains_render_scene(self):
        registry = ToolRegistry()
        self.assertTrue(registry.has_tool("render_scene"))
        mcp_tools = registry.get_mcp_tools()
        names = [t.name for t in mcp_tools]
        self.assertIn("render_scene", names)
        render_tool = next(t for t in mcp_tools if t.name == "render_scene")
        self.assertIn("render_mode", render_tool.inputSchema["properties"])


if __name__ == "__main__":
    unittest.main()
