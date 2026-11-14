"""
Unit and integration tests for MaterialsAgent, RenderLightingAgent, and Viewport Capture.
Tests:
1. MaterialsAgent: manifest, routing, input validation, unsupported shader nodes,
   approval gating, Principled BSDF creation, slot assignment, and post-verification.
2. RenderLightingAgent: manifest, routing, input validation, light types (POINT, SUN, SPOT, AREA),
   unsupported render engines/compositing, approval gating, and post-verification.
3. capture_viewport: schema, base64 encoding, settings preservation in try...finally,
   resource cleanup, and headless context detection.
4. Dispatcher integration: capability routing, session tracking, and error handling.
"""

import unittest
import base64
import os
import tempfile
from unittest.mock import MagicMock, patch

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    AgentResult,
    VerificationResult,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_CREATE_MATERIAL,
    TOOL_ASSIGN_MATERIAL,
    TOOL_LIST_MATERIALS,
    TOOL_CREATE_LIGHT,
    TOOL_CONFIGURE_WORLD,
    TOOL_LIST_OBJECTS,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_CAPTURE_VIEWPORT,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from mcp_service.agents.materials import (
    MaterialsAgent,
    create_materials_manifest,
    MATERIALS_AGENT_ID,
    CAPABILITY_MATERIALS_MANAGE,
    CAPABILITY_MATERIALS_INSPECT,
    UNSUPPORTED_SHADER_NODES,
    UNSUPPORTED_MATERIAL_PROPERTIES,
)
from mcp_service.agents.render_lighting import (
    RenderLightingAgent,
    create_render_lighting_manifest,
    RENDER_LIGHTING_AGENT_ID,
    CAPABILITY_LIGHTING_MANAGE,
    CAPABILITY_WORLD_MANAGE,
    CAPABILITY_LIGHTING_INSPECT,
    ALLOWED_LIGHT_TYPES,
    UNSUPPORTED_LIGHTING_FEATURES,
)
from mcp_service.agents.scene_inspector import (
    SceneInspectorAgent,
    SCENE_INSPECTOR_AGENT_ID,
)
from mcp_service.agents.dispatcher import AgentDispatcher, DispatchResult
from mcp_service.agents.registry import create_default_registry
from mcp_service.security.approval import ApprovalDecision, ApprovalManager
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import (
    handle_capture_viewport,
    handle_create_light,
    handle_configure_world,
    handle_create_material,
    handle_assign_material,
)


class MockBlenderExecutor:
    """Mock executor simulating Blender bridge responses."""

    def __init__(self):
        self.executed_tools = []
        self.tool_responses = {}
        self.materials_db = {}
        self.lights_db = {}
        self.world_db = {"color": [0.05, 0.05, 0.05], "strength": 1.0, "use_nodes": True}
        self.objects_db = {
            "Cube": {"name": "Cube", "type": "MESH", "materials": []},
        }

    def execute_tool(self, tool_name: str, arguments: dict = None, trusted_approval: bool = None) -> BridgeResponse:
        arguments = arguments or {}
        self.executed_tools.append((tool_name, arguments, trusted_approval))

        if tool_name in self.tool_responses:
            resp = self.tool_responses[tool_name]
            if callable(resp):
                return resp(arguments)
            return resp

        # Default simulated responses
        if tool_name == TOOL_CREATE_MATERIAL:
            name = arguments.get("name") or arguments.get("material_name", "Material")
            self.materials_db[name] = {
                "name": name,
                "base_color": arguments.get("base_color", [0.8, 0.8, 0.8, 1.0]),
                "roughness": arguments.get("roughness", 0.5),
                "metallic": arguments.get("metallic", 0.0),
            }
            return BridgeResponse.success(result=self.materials_db[name])

        elif tool_name == TOOL_ASSIGN_MATERIAL:
            target = arguments.get("target_name") or arguments.get("target", "Cube")
            mat = arguments.get("material_name") or arguments.get("name", "Material")
            if target in self.objects_db:
                self.objects_db[target]["materials"].append(mat)
            return BridgeResponse.success(result={"target": target, "material_name": mat, "slot_index": 0})

        elif tool_name == TOOL_LIST_MATERIALS:
            filter_name = arguments.get("filter_name")
            mats = list(self.materials_db.values())
            if filter_name:
                mats = [m for m in mats if filter_name.lower() in m["name"].lower()]
            return BridgeResponse.success(result={"materials": mats, "total_materials": len(mats)})

        elif tool_name == TOOL_CREATE_LIGHT:
            name = arguments.get("name", "Light")
            self.lights_db[name] = {
                "name": name,
                "type": arguments.get("light_type", "POINT"),
                "energy": arguments.get("energy", 1000.0),
                "color": arguments.get("color", [1.0, 1.0, 1.0]),
            }
            self.objects_db[name] = {"name": name, "type": "LIGHT"}
            return BridgeResponse.success(result=self.lights_db[name])

        elif tool_name == TOOL_CONFIGURE_WORLD:
            self.world_db.update(arguments)
            return BridgeResponse.success(result={"world_name": "World", **self.world_db})

        elif tool_name == TOOL_LIST_OBJECTS:
            obj_type = arguments.get("object_type")
            objs = list(self.objects_db.values())
            if obj_type:
                objs = [o for o in objs if o.get("type") == obj_type]
            return BridgeResponse.success(result={"objects": objs, "total_objects": len(objs)})

        elif tool_name == TOOL_INSPECT_SCENE_DATA:
            cat = arguments.get("category")
            if cat == "object_materials":
                target = arguments.get("target_name", "Cube")
                obj = self.objects_db.get(target, {})
                assigned = [{"slot_index": i, "material_name": m, "assigned": True} for i, m in enumerate(obj.get("materials", []))]
                return BridgeResponse.success(result={"category": cat, "target_name": target, "materials": assigned})
            elif cat == "world_settings":
                return BridgeResponse.success(result={"category": cat, "has_world": True, "world_name": "World", **self.world_db})
            return BridgeResponse.success(result={"category": cat})

        elif tool_name == TOOL_CAPTURE_VIEWPORT:
            return BridgeResponse.success(
                result={
                    "format": "png",
                    "width": arguments.get("width", 512),
                    "height": arguments.get("height", 512),
                    "mode": arguments.get("mode", "VIEWPORT"),
                    "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                    "size_bytes": 70,
                    "read_only": True,
                }
            )

        return BridgeResponse.error(f"Unknown mock tool: {tool_name}")


class TestMaterialsAgent(unittest.TestCase):
    """Tests for MaterialsAgent and Principled BSDF management."""

    def setUp(self):
        self.agent = MaterialsAgent(version="0.1.13")
        self.executor = MockBlenderExecutor()

    def test_manifest_structure(self):
        manifest = self.agent.manifest
        manifest.validate()
        self.assertEqual(manifest.agent_id, MATERIALS_AGENT_ID)
        self.assertEqual(manifest.version, "0.1.13")
        self.assertEqual(len(manifest.capabilities), 3)

        caps = {c.capability_id: c for c in manifest.capabilities}
        self.assertIn(CAPABILITY_MATERIALS_MANAGE, caps)
        self.assertIn(CAPABILITY_MATERIALS_INSPECT, caps)
        self.assertIn("materials.typed_shader", caps)

        self.assertEqual(caps[CAPABILITY_MATERIALS_MANAGE].read_write, "SCENE_MUTATION")
        self.assertEqual(caps[CAPABILITY_MATERIALS_INSPECT].read_write, "READ_ONLY")

        # Schemas defined
        self.assertIn(TOOL_CREATE_MATERIAL, manifest.input_schemas)
        self.assertIn(TOOL_ASSIGN_MATERIAL, manifest.input_schemas)
        self.assertIn(TOOL_LIST_MATERIALS, manifest.input_schemas)

    def test_can_handle(self):
        task1 = AgentTask(task_id="t1", required_capability=CAPABILITY_MATERIALS_MANAGE)
        self.assertTrue(self.agent.can_handle(task1))

        task2 = AgentTask(task_id="t2", required_capability=CAPABILITY_MATERIALS_MANAGE, task_type=TOOL_CREATE_MATERIAL)
        self.assertTrue(self.agent.can_handle(task2))

        task3 = AgentTask(task_id="t3", required_capability=CAPABILITY_MATERIALS_MANAGE, task_type=TOOL_ASSIGN_MATERIAL)
        self.assertTrue(self.agent.can_handle(task3))

        task4 = AgentTask(task_id="t4", required_capability="other.cap", task_type="unrelated_tool")
        self.assertFalse(self.agent.can_handle(task4))

    def test_create_material_input_validation(self):
        # Empty name
        valid, code, msg = self.agent.validate_task_input(TOOL_CREATE_MATERIAL, {"name": "  "})
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_PARAMS")

        # Color out of bounds > 1.0
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL, {"name": "Mat", "base_color": [1.2, 0.5, 0.5, 1.0]}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_PARAMS")

        # Color out of bounds < 0.0
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL, {"name": "Mat", "base_color": [0.5, -0.1, 0.5, 1.0]}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_PARAMS")

        # Roughness out of bounds
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL, {"name": "Mat", "roughness": 1.5}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_PARAMS")

        # Metallic out of bounds
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL, {"name": "Mat", "metallic": -0.2}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_PARAMS")

        # Valid Principled BSDF inputs
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL,
            {
                "name": "Gold",
                "base_color": [1.0, 0.85, 0.57, 1.0],
                "roughness": 0.2,
                "metallic": 1.0,
                "ior": 1.45,
            },
        )
        self.assertTrue(valid)
        self.assertIsNone(code)

    def test_rejection_of_unsupported_shader_nodes_and_properties(self):
        # Unsupported shader node: Glass
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL,
            {"name": "GlassMat", "nodes": [{"type": "GLASS"}]},
        )
        self.assertFalse(valid)
        self.assertEqual(code, "UNSUPPORTED_REQUEST")

        # Unsupported shader property: subsurface
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL,
            {"name": "SkinMat", "subsurface": 0.5},
        )
        self.assertFalse(valid)
        self.assertEqual(code, "UNSUPPORTED_REQUEST")

        # Unsupported shader property: transmission
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_MATERIAL,
            {"name": "WaterMat", "transmission": 1.0},
        )
        self.assertFalse(valid)
        self.assertEqual(code, "UNSUPPORTED_REQUEST")

    def test_approval_enforcement(self):
        # Model-supplied approved=True rejected
        task = AgentTask(
            task_id="mat-appr-1",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "Mat1", "approved": True},
        )
        res = self.agent.execute_task(task, self.executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.verification.observed_results.get("error_code"), "PERMISSION_DENIED")

        # Untrusted call paused in AWAITING_APPROVAL
        task_untrusted = AgentTask(
            task_id="mat-appr-2",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "Mat1"},
        )
        res_untrusted = self.agent.execute_task(task_untrusted, self.executor)
        self.assertEqual(res_untrusted.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res_untrusted.verification.observed_results.get("error_code"), "APPROVAL_REQUIRED")

    def test_blender_approval_provider_is_used_and_credentials_forwarded(self):
        provider_calls = []

        def trusted_provider(tool_name, params):
            provider_calls.append((tool_name, dict(params)))
            return ApprovalDecision(
                True,
                "Approved in Blender",
                request_id="blender-request-1",
                approval_token="blender-token-1",
            )

        self.executor.approval_manager = ApprovalManager(provider=trusted_provider)
        task = AgentTask(
            task_id="mat-ui-appr-1",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "ApprovedMaterial"},
        )

        result = self.agent.execute_task(task, self.executor)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(len(provider_calls), 1)
        self.assertEqual(provider_calls[0][0], TOOL_CREATE_MATERIAL)
        create_call = next(call for call in self.executor.executed_tools if call[0] == TOOL_CREATE_MATERIAL)
        self.assertEqual(create_call[1]["request_id"], "blender-request-1")
        self.assertEqual(create_call[1]["approval_token"], "blender-token-1")

    def test_create_material_handler_rejects_missing_or_invalid_credentials(self):
        registry = MagicMock()
        registry.consume_approval.return_value = (False, "Invalid approval token")
        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry):
            with self.assertRaises(PermissionError) as missing:
                handle_create_material(params={
                    "name": "UnapprovedMaterial",
                    "approved": True,
                    "trusted_approval": True,
                })
            self.assertIn("Missing trusted human approval credentials", str(missing.exception))
            registry.consume_approval.assert_not_called()

            with self.assertRaises(PermissionError) as invalid:
                handle_create_material(params={
                    "name": "InvalidTokenMaterial",
                    "request_id": "request-1",
                    "approval_token": "forged-token",
                })
            self.assertIn("Invalid approval token", str(invalid.exception))
            registry.consume_approval.assert_called_once()

    def test_create_material_handler_consumes_real_registry_token_once(self):
        registry = ApprovalRegistry()
        approved_params = {"name": "RegistryApprovedMaterial"}
        request = registry.create_request("create_material", approved_params)
        resolved, token = registry.resolve_request(request.request_id, "approved")
        self.assertTrue(resolved)

        material = type("Material", (), {"name": "RegistryApprovedMaterial", "node_tree": None})()
        material_store = type("MaterialStore", (), {
            "new": staticmethod(lambda name: material),
        })()
        mock_bpy = type("Bpy", (), {
            "data": type("Data", (), {"materials": material_store})(),
        })()
        call_params = {
            **approved_params,
            "request_id": request.request_id,
            "approval_token": token,
        }

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=registry):
            result = handle_create_material(bpy_module=mock_bpy, params=call_params)
            self.assertEqual(result["name"], "RegistryApprovedMaterial")
            with self.assertRaises(PermissionError) as replay:
                handle_create_material(bpy_module=mock_bpy, params=call_params)

        self.assertIn("Replay rejected", str(replay.exception))

    def test_successful_create_and_verification(self):
        task = AgentTask(
            task_id="mat-exec-1",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "RubyRed", "base_color": [0.8, 0.1, 0.1, 1.0], "roughness": 0.1},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertTrue(res.verification.verified)
        self.assertEqual(res.verification.transaction_state, "COMMITTED")
        self.assertTrue(res.verification.observed_results.get("material_exists"))

    def test_successful_assign_and_verification(self):
        # Create first
        self.executor.materials_db["Wood"] = {"name": "Wood"}
        task = AgentTask(
            task_id="mat-exec-2",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_ASSIGN_MATERIAL,
            input_params={"target_name": "Cube", "material_name": "Wood"},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertTrue(res.verification.verified)
        self.assertEqual(res.verification.transaction_state, "COMMITTED")
        self.assertEqual(res.verification.observed_results.get("assigned_material"), "Wood")

    def test_post_operation_verification_failure(self):
        # Simulate executor returning success but inspection failing to find material
        def mock_create(args):
            return BridgeResponse.success(result={"name": "GhostMat"})

        self.executor.tool_responses[TOOL_CREATE_MATERIAL] = mock_create
        task = AgentTask(
            task_id="mat-ghost-1",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "GhostMat"},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertFalse(res.verification.verified)
        self.assertEqual(res.verification.transaction_state, "ROLLBACK_UNVERIFIED")


class TestRenderLightingAgent(unittest.TestCase):
    """Tests for RenderLightingAgent, light types, and world background configuration."""

    def setUp(self):
        self.agent = RenderLightingAgent(version="0.1.13")
        self.executor = MockBlenderExecutor()

    def test_manifest_structure(self):
        manifest = self.agent.manifest
        manifest.validate()
        self.assertEqual(manifest.agent_id, RENDER_LIGHTING_AGENT_ID)
        self.assertEqual(manifest.version, "0.1.13")
        self.assertEqual(len(manifest.capabilities), 3)

        caps = {c.capability_id: c for c in manifest.capabilities}
        self.assertIn(CAPABILITY_LIGHTING_MANAGE, caps)
        self.assertIn(CAPABILITY_WORLD_MANAGE, caps)
        self.assertIn(CAPABILITY_LIGHTING_INSPECT, caps)

        self.assertEqual(caps[CAPABILITY_LIGHTING_MANAGE].read_write, "SCENE_MUTATION")
        self.assertEqual(caps[CAPABILITY_WORLD_MANAGE].read_write, "SCENE_MUTATION")
        self.assertEqual(caps[CAPABILITY_LIGHTING_INSPECT].read_write, "READ_ONLY")

    def test_supported_light_types(self):
        for lt in ("POINT", "SUN", "SPOT", "AREA"):
            valid, code, msg = self.agent.validate_task_input(
                TOOL_CREATE_LIGHT, {"name": f"L_{lt}", "light_type": lt, "energy": 500.0}
            )
            self.assertTrue(valid, f"Expected {lt} to be valid: {msg}")

    def test_unsupported_light_type_rejection(self):
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_LIGHT, {"name": "L_Bad", "light_type": "HEMI"}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "UNSUPPORTED_REQUEST")

    def test_unsupported_features_rejection(self):
        # Render engine switching rejected
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CONFIGURE_WORLD, {"color": [0.1, 0.1, 0.1], "render_engine": "CYCLES"}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "UNSUPPORTED_REQUEST")

        # Compositing rejected
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_LIGHT, {"name": "L1", "compositing": True}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "UNSUPPORTED_REQUEST")

        # Light linking rejected
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_LIGHT, {"name": "L1", "light_linking": "group_a"}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "UNSUPPORTED_REQUEST")

    def test_create_light_parameter_validation(self):
        # Negative energy
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_LIGHT, {"name": "L1", "energy": -50.0}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_PARAMS")

        # Color out of bounds
        valid, code, msg = self.agent.validate_task_input(
            TOOL_CREATE_LIGHT, {"name": "L1", "color": [1.5, 0.0, 0.0]}
        )
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_PARAMS")

    def test_approval_enforcement(self):
        # Model-supplied approved=True rejected
        task = AgentTask(
            task_id="light-appr-1",
            required_capability=CAPABILITY_LIGHTING_MANAGE,
            task_type=TOOL_CREATE_LIGHT,
            input_params={"name": "KeyLight", "approved": True},
        )
        res = self.agent.execute_task(task, self.executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.verification.observed_results.get("error_code"), "PERMISSION_DENIED")

        # Untrusted call paused in AWAITING_APPROVAL
        task_untrusted = AgentTask(
            task_id="light-appr-2",
            required_capability=CAPABILITY_LIGHTING_MANAGE,
            task_type=TOOL_CREATE_LIGHT,
            input_params={"name": "KeyLight"},
        )
        res_untrusted = self.agent.execute_task(task_untrusted, self.executor)
        self.assertEqual(res_untrusted.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res_untrusted.verification.observed_results.get("error_code"), "APPROVAL_REQUIRED")

    def test_successful_create_light_and_verification(self):
        task = AgentTask(
            task_id="light-exec-1",
            required_capability=CAPABILITY_LIGHTING_MANAGE,
            task_type=TOOL_CREATE_LIGHT,
            input_params={"name": "SunLight", "light_type": "SUN", "energy": 5.0, "color": [1.0, 0.95, 0.9]},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertTrue(res.verification.verified)
        self.assertEqual(res.verification.transaction_state, "COMMITTED")
        self.assertTrue(res.verification.observed_results.get("light_exists"))

    def test_successful_configure_world_and_verification(self):
        task = AgentTask(
            task_id="world-exec-1",
            required_capability=CAPABILITY_WORLD_MANAGE,
            task_type=TOOL_CONFIGURE_WORLD,
            input_params={"color": [0.02, 0.02, 0.05], "strength": 0.8},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertTrue(res.verification.verified)
        self.assertEqual(res.verification.transaction_state, "COMMITTED")
        self.assertTrue(res.verification.observed_results.get("world_configured"))


class TestVisualGroundingCapture(unittest.TestCase):
    """Tests for capture_viewport, schema, base64 encoding, settings preservation, and headless mode."""

    def test_tool_schema_definition(self):
        self.assertIn(TOOL_CAPTURE_VIEWPORT, TOOL_DEFINITIONS)
        defn = TOOL_DEFINITIONS[TOOL_CAPTURE_VIEWPORT]
        self.assertEqual(defn["permission_tier"], "READ_ONLY")

        props = defn["input_schema"]["properties"]
        self.assertIn("width", props)
        self.assertIn("height", props)
        self.assertIn("mode", props)
        self.assertIn("format", props)
        self.assertEqual(props["width"]["minimum"], 64)
        self.assertEqual(props["width"]["maximum"], 2048)

    def test_validate_tool_input(self):
        # Valid input
        sanitized = validate_tool_input(
            TOOL_CAPTURE_VIEWPORT,
            {"width": 1024, "height": 768, "mode": "VIEWPORT"},
        )
        self.assertEqual(sanitized["width"], 1024)
        self.assertEqual(sanitized["height"], 768)
        self.assertEqual(sanitized["mode"], "VIEWPORT")
        self.assertEqual(sanitized["format"], "PNG")

        # Invalid mode
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"mode": "TOP_ORTHO"})

        # Out of bounds width
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"width": 3000})

    def test_capture_viewport_handler_settings_preservation(self):
        """Verify render resolution, filepath, and format are preserved via try...finally."""
        # Setup mock bpy module
        mock_bpy = MagicMock()
        mock_bpy.app.background = False
        scene = MagicMock()
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = 100
        scene.render.filepath = "//render/output.png"
        scene.render.image_settings.file_format = "JPEG"
        mock_bpy.context.scene = scene

        # Setup mock window with 3D View area
        area = MagicMock()
        area.type = "VIEW_3D"
        screen = MagicMock()
        screen.areas = [area]
        window = MagicMock()
        window.screen = screen
        mock_bpy.context.window_manager.windows = [window]

        # Simulate render writing 1-pixel transparent PNG
        tiny_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

        def mock_opengl(**kwargs):
            out_path = scene.render.filepath
            with open(out_path, "wb") as f:
                f.write(tiny_png)

        mock_bpy.ops.render.opengl.side_effect = mock_opengl

        res = handle_capture_viewport(bpy_module=mock_bpy, params={"width": 640, "height": 480})

        # Output verification
        self.assertEqual(res["format"], "png")
        self.assertEqual(res["width"], 640)
        self.assertEqual(res["height"], 480)
        self.assertIn("image_base64", res)
        decoded = base64.b64decode(res["image_base64"])
        self.assertEqual(decoded, tiny_png)
        self.assertTrue(res["read_only"])

        # Invariant: Settings restored to original
        self.assertEqual(scene.render.resolution_x, 1920)
        self.assertEqual(scene.render.resolution_y, 1080)
        self.assertEqual(scene.render.filepath, "//render/output.png")
        self.assertEqual(scene.render.image_settings.file_format, "JPEG")

    def test_capture_viewport_headless_background_rejection(self):
        """Verify background/headless mode cleanly reports CONTEXT_UNAVAILABLE when viewport is unavailable."""
        mock_bpy = MagicMock()
        mock_bpy.app.background = True
        mock_bpy.context.window_manager.windows = []  # No GUI windows

        with self.assertRaises(RuntimeError) as ctx:
            handle_capture_viewport(bpy_module=mock_bpy, params={"mode": "VIEWPORT"})

        self.assertIn("CONTEXT_UNAVAILABLE", str(ctx.exception))
        self.assertIn("Headless background mode does not have an active 3D viewport", str(ctx.exception))


class TestDispatcherIntegrationWithAllAgents(unittest.TestCase):
    """Tests for central AgentDispatcher routing to all 4 specialized agents."""

    def setUp(self):
        self.executor = MockBlenderExecutor()
        self.dispatcher = AgentDispatcher(executor=self.executor)

    def test_route_material_creation(self):
        task = AgentTask(
            task_id="t-disp-mat",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "Emerald", "base_color": [0.0, 0.8, 0.2, 1.0]},
        )
        res = self.dispatcher.dispatch_task(task, trusted_approval=True)
        self.assertTrue(res.success)
        self.assertEqual(res.agent_id, MATERIALS_AGENT_ID)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertTrue(res.verification.verified)

    def test_material_creation_uses_configured_blender_approval_provider(self):
        calls = []

        def trusted_provider(tool_name, params):
            calls.append(tool_name)
            return ApprovalDecision(
                True,
                "Approved in Blender",
                request_id="ui-request",
                approval_token="ui-token",
            )

        self.executor.approval_manager = ApprovalManager(provider=trusted_provider)
        task = AgentTask(
            task_id="t-disp-mat-ui",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "UIApprovedMaterial"},
        )

        result = self.dispatcher.dispatch_task(task)

        self.assertTrue(result.success)
        self.assertEqual(calls, [TOOL_CREATE_MATERIAL])
        create_call = next(call for call in self.executor.executed_tools if call[0] == TOOL_CREATE_MATERIAL)
        self.assertEqual(create_call[1]["request_id"], "ui-request")
        self.assertEqual(create_call[1]["approval_token"], "ui-token")

    def test_route_light_creation(self):
        task = AgentTask(
            task_id="t-disp-light",
            required_capability=CAPABILITY_LIGHTING_MANAGE,
            task_type=TOOL_CREATE_LIGHT,
            input_params={"name": "AreaCeiling", "light_type": "AREA", "energy": 800.0},
        )
        res = self.dispatcher.dispatch_task(task, trusted_approval=True)
        self.assertTrue(res.success)
        self.assertEqual(res.agent_id, RENDER_LIGHTING_AGENT_ID)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertTrue(res.verification.verified)

    def test_route_viewport_capture(self):
        task = AgentTask(
            task_id="t-disp-cap",
            required_capability="visual.capture",
            task_type=TOOL_CAPTURE_VIEWPORT,
            input_params={"width": 512, "height": 512},
        )
        res = self.dispatcher.dispatch_task(task)
        self.assertTrue(res.success)
        self.assertEqual(res.agent_id, SCENE_INSPECTOR_AGENT_ID)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertIn("image_base64", res.result)

    def test_reject_unapproved_material_mutation(self):
        task = AgentTask(
            task_id="t-disp-unappr",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_CREATE_MATERIAL,
            input_params={"name": "UnapprovedMat"},
        )
        res = self.dispatcher.dispatch_task(task, trusted_approval=None)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res.error_code, "APPROVAL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
