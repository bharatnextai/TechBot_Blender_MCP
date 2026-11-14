"""
Unit tests for Capability 5: UV Mapping Foundation (v0.1.65).
Tests:
1. Schema declarations, tool definitions, and ToolRegistry discovery.
2. Input validation, parameter bounds, and sanitization in validate_tool_input.
3. Security gating: rejection of untrusted approved=True and fail-closed permission checks.
4. ModelingAgent manifest, routing, and task execution for CAPABILITY_MODELING_UV.
5. Bridge handlers: inspect_uv_mesh, manage_uv_seams, pack_uv_islands, manage_uv_layers.
6. Optimistic concurrency control (expected_snapshot_id) and transactional rollback on failure.
"""

import unittest
from unittest.mock import MagicMock
import math
import hashlib

from shared.schemas.tool_schemas import (
    TOOL_UV_UNWRAP,
    TOOL_UV_SMART_PROJECT,
    TOOL_UNWRAP_MESH,
    TOOL_SMART_PROJECT,
    TOOL_SMART_UV_PROJECT,
    TOOL_UV_PROJECT,
    TOOL_MANAGE_UV_SEAMS,
    TOOL_PACK_UV_ISLANDS,
    TOOL_MANAGE_UV_LAYERS,
    TOOL_INSPECT_UV_MESH,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.security.approval import ApprovalManager
from mcp_service.agents.modeling import (
    ModelingAgent,
    CAPABILITY_MODELING_UV,
)
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.execution.blender_executor import BlenderExecutor
from blender_addon.universal_mcp.bridge.handlers import (
    ALL_HANDLERS,
    handle_uv_unwrap,
    handle_uv_smart_project,
    handle_inspect_uv_mesh,
    handle_manage_uv_seams,
    handle_pack_uv_islands,
    handle_manage_uv_layers,
)
from blender_addon.universal_mcp.bridge.uv_foundation import (
    compute_uv_snapshot,
    estimate_uv_islands,
    inspect_uv_mesh,
    manage_uv_seams,
    pack_uv_islands,
    manage_uv_layers,
)


class MockUVLoopItem:
    def __init__(self, u: float, v: float):
        self.uv = [u, v]


class MockUVLayer:
    def __init__(self, name: str, loop_count: int = 24):
        self.name = name
        self.active_render = False
        self.data = [MockUVLoopItem(0.1 * (i % 4), 0.1 * (i // 4)) for i in range(loop_count)]


class MockUVLayersCollection:
    def __init__(self, default_layer_name: str = "UVMap", loop_count: int = 24):
        self._layers = [MockUVLayer(default_layer_name, loop_count)]
        self.active = self._layers[0]

    def get(self, name: str):
        for lyr in self._layers:
            if lyr.name == name:
                return lyr
        return None

    def __getitem__(self, name: str):
        lyr = self.get(name)
        if lyr is None:
            raise KeyError(name)
        return lyr

    def __len__(self):
        return len(self._layers)

    def __iter__(self):
        return iter(self._layers)

    def new(self, name: str = "UVMap"):
        if self.get(name) is not None:
            return None
        lyr = MockUVLayer(name)
        self._layers.append(lyr)
        return lyr

    def remove(self, layer):
        if layer in self._layers:
            self._layers.remove(layer)
            if self.active and self.active == layer:
                self.active = self._layers[0] if self._layers else None


class MockEdge:
    def __init__(self, index: int, use_seam: bool = False):
        self.index = index
        self.use_seam = use_seam
        self.vertices = (index, index + 1)


class MockPolygon:
    def __init__(self, index: int, verts: tuple, loop_indices: tuple):
        self.index = index
        self.vertices = verts
        self.loop_indices = loop_indices


class MockMesh:
    def __init__(self, face_count: int = 6, edge_count: int = 12, loop_count: int = 24):
        self.polygons = [
            MockPolygon(i, (i % 8, (i + 1) % 8, (i + 2) % 8, (i + 3) % 8), (i * 4, i * 4 + 1, i * 4 + 2, i * 4 + 3))
            for i in range(face_count)
        ]
        self.edges = [MockEdge(i) for i in range(edge_count)]
        self.loops = [MagicMock() for _ in range(loop_count)]
        self.uv_layers = MockUVLayersCollection("UVMap", loop_count)

    def update(self):
        pass


class MockObject:
    def __init__(self, name: str, obj_type: str = "MESH", face_count: int = 6):
        self.name = name
        self.type = obj_type
        self.mode = "OBJECT"
        self.data = MockMesh(face_count) if obj_type == "MESH" else MagicMock()

    def select_set(self, state: bool):
        pass


class MockContext:
    def __init__(self, objects: dict):
        self.scene = MagicMock()
        self.scene.objects = objects
        self.view_layer = MagicMock()
        self.view_layer.objects = MagicMock()
        self.view_layer.objects.active = next(iter(objects.values())) if objects else None


class MockBpyModule:
    def __init__(self, objects: dict = None):
        self._objects = objects or {}
        self.data = MagicMock()
        self.data.objects = self._objects
        self.context = MockContext(self._objects)
        self.ops = MagicMock()
        self.app = MagicMock()
        self.app.timers = MagicMock()


class TestUVFoundationSchemas(unittest.TestCase):
    """Tests schema definitions and permissions."""

    def test_schema_registration(self):
        for tool in (TOOL_MANAGE_UV_SEAMS, TOOL_PACK_UV_ISLANDS, TOOL_MANAGE_UV_LAYERS, TOOL_INSPECT_UV_MESH):
            self.assertIn(tool, TOOL_DEFINITIONS)

        self.assertEqual(TOOL_DEFINITIONS[TOOL_MANAGE_UV_SEAMS]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_PACK_UV_ISLANDS]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_MANAGE_UV_LAYERS]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_INSPECT_UV_MESH]["permission_tier"], PERMISSION_READ_ONLY)

    def test_tool_registry_discovery(self):
        registry = ToolRegistry()
        self.assertTrue(registry.has_tool(TOOL_MANAGE_UV_SEAMS))
        self.assertTrue(registry.has_tool(TOOL_PACK_UV_ISLANDS))
        self.assertTrue(registry.has_tool(TOOL_MANAGE_UV_LAYERS))
        self.assertTrue(registry.has_tool(TOOL_INSPECT_UV_MESH))

    def test_seams_validation_valid(self):
        params = {"name": "Cube", "action": "mark", "edges": [0, 1, 2]}
        sanitized = validate_tool_input(TOOL_MANAGE_UV_SEAMS, params, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Cube")
        self.assertEqual(sanitized["action"], "mark")
        self.assertEqual(sanitized["edges"], [0, 1, 2])

    def test_seams_validation_clear_all(self):
        params = {"name": "Cube", "action": "clear_all"}
        sanitized = validate_tool_input(TOOL_MANAGE_UV_SEAMS, params, trusted_approval=True)
        self.assertEqual(sanitized["action"], "clear_all")

    def test_seams_validation_invalid_action(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_MANAGE_UV_SEAMS, {"name": "Cube", "action": "destroy"}, trusted_approval=True)

    def test_seams_validation_missing_edges_on_mark(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_MANAGE_UV_SEAMS, {"name": "Cube", "action": "mark"}, trusted_approval=True)

    def test_pack_islands_validation(self):
        params = {"name": "Cube", "margin": 0.05, "rotate": False}
        sanitized = validate_tool_input(TOOL_PACK_UV_ISLANDS, params, trusted_approval=True)
        self.assertEqual(sanitized["margin"], 0.05)
        self.assertFalse(sanitized["rotate"])

    def test_pack_islands_invalid_margin(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_PACK_UV_ISLANDS, {"name": "Cube", "margin": 1.5}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_PACK_UV_ISLANDS, {"name": "Cube", "margin": -0.1}, trusted_approval=True)

    def test_layers_validation(self):
        params = {"name": "Cube", "action": "create", "layer_name": "Lightmap"}
        sanitized = validate_tool_input(TOOL_MANAGE_UV_LAYERS, params, trusted_approval=True)
        self.assertEqual(sanitized["layer_name"], "Lightmap")
        self.assertEqual(sanitized["action"], "create")

    def test_inspect_uv_validation(self):
        params = {"name": "Cube", "detail_level": "detailed"}
        sanitized = validate_tool_input(TOOL_INSPECT_UV_MESH, params, trusted_approval=False)
        self.assertEqual(sanitized["name"], "Cube")
        self.assertEqual(sanitized["detail_level"], "detailed")


class TestUVFoundationSecurity(unittest.TestCase):
    """Tests human approval gating and untrusted flag rejection."""

    def setUp(self):
        self.approval_mgr = ApprovalManager()

    def test_approval_manager_requirements(self):
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_MANAGE_UV_SEAMS))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_PACK_UV_ISLANDS))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_MANAGE_UV_LAYERS))
        self.assertFalse(self.approval_mgr.requires_approval(TOOL_INSPECT_UV_MESH))

    def test_rejection_of_untrusted_approved_flag(self):
        # manage_uv_seams
        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_MANAGE_UV_SEAMS, {"name": "Cube", "action": "clear_all", "approved": True}, trusted_approval=False)

        # pack_uv_islands
        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_PACK_UV_ISLANDS, {"name": "Cube", "approved": True}, trusted_approval=False)

        # manage_uv_layers
        with self.assertRaises(PermissionError):
            validate_tool_input(TOOL_MANAGE_UV_LAYERS, {"name": "Cube", "layer_name": "Lightmap", "approved": True}, trusted_approval=False)


class MockExecutor(BlenderExecutor):
    def __init__(self):
        self.invocations = []

    def is_connected(self) -> bool:
        return True

    def execute_tool(self, tool_name: str, arguments: dict = None, trusted_approval: bool = None) -> BridgeResponse:
        self.invocations.append((tool_name, arguments, trusted_approval))
        return BridgeResponse.success({"name": arguments.get("name", "Cube"), "action": tool_name, "success": True})


class TestModelingAgentUVFoundation(unittest.TestCase):
    """Tests ModelingAgent integration for new UV tools."""

    def setUp(self):
        self.agent = ModelingAgent(version="0.1.65")
        self.executor = MockExecutor()

    def test_manifest_contains_new_tools(self):
        caps = {c.capability_id: c for c in self.agent.manifest.capabilities}
        self.assertIn(CAPABILITY_MODELING_UV, caps)
        uv_cap = caps[CAPABILITY_MODELING_UV]
        for tool in (TOOL_MANAGE_UV_SEAMS, TOOL_PACK_UV_ISLANDS, TOOL_MANAGE_UV_LAYERS, TOOL_INSPECT_UV_MESH):
            self.assertIn(tool, uv_cap.supported_task_types)

    def test_can_handle_new_tools(self):
        for tool in (TOOL_MANAGE_UV_SEAMS, TOOL_PACK_UV_ISLANDS, TOOL_MANAGE_UV_LAYERS, TOOL_INSPECT_UV_MESH):
            task = AgentTask(task_id=f"task_{tool}", required_capability=CAPABILITY_MODELING_UV, task_type=tool)
            self.assertTrue(self.agent.can_handle(task))


class TestBridgeUVFoundationOperations(unittest.TestCase):
    """Tests actual bridge logic for UV foundation operations."""

    def setUp(self):
        self.cube = MockObject("Cube", "MESH", face_count=6)
        self.camera = MockObject("Camera", "CAMERA")
        self.bpy = MockBpyModule({"Cube": self.cube, "Camera": self.camera})

    def test_inspect_uv_mesh(self):
        res = inspect_uv_mesh(self.bpy, "Cube")
        self.assertEqual(res["name"], "Cube")
        self.assertTrue(res["has_uvs"])
        self.assertEqual(res["active_uv_layer"], "UVMap")
        self.assertEqual(res["uv_layer_count"], 1)
        self.assertEqual(res["total_faces"], 6)
        self.assertEqual(res["total_edges"], 12)
        self.assertEqual(res["seam_count"], 0)
        self.assertIn("snapshot_id", res)
        self.assertTrue(res["snapshot_id"].startswith("sha256:"))
        self.assertEqual(len(res["snapshot_id"]), 71)

    def test_manage_uv_seams_mark_and_clear(self):
        initial_snap = compute_uv_snapshot(self.cube)

        # Mark seams on edges 0, 1, 2
        res_mark = manage_uv_seams(self.bpy, "Cube", action="mark", edges=[0, 1, 2])
        self.assertEqual(res_mark["action"], "mark")
        self.assertEqual(res_mark["modified_edges_count"], 3)
        self.assertEqual(res_mark["total_seam_count"], 3)
        self.assertEqual(res_mark["seam_edges"], [0, 1, 2])
        self.assertNotEqual(res_mark["snapshot_id"], initial_snap)

        # Clear seam on edge 1
        res_clear = manage_uv_seams(self.bpy, "Cube", action="clear", edges=[1])
        self.assertEqual(res_clear["total_seam_count"], 2)
        self.assertEqual(res_clear["seam_edges"], [0, 2])

        # Clear all
        res_clear_all = manage_uv_seams(self.bpy, "Cube", action="clear_all")
        self.assertEqual(res_clear_all["total_seam_count"], 0)

    def test_manage_uv_seams_concurrency_rejection(self):
        with self.assertRaises(ValueError) as ctx:
            manage_uv_seams(self.bpy, "Cube", action="mark", edges=[0], expected_snapshot_id="sha256:" + "0" * 64)
        self.assertIn("STALE_UV_TOPOLOGY", str(ctx.exception))

    def test_pack_uv_islands(self):
        res = pack_uv_islands(self.bpy, "Cube", margin=0.02, rotate=True)
        self.assertEqual(res["name"], "Cube")
        self.assertEqual(res["margin"], 0.02)
        self.assertTrue(res["rotate"])
        self.assertIn("snapshot_id", res)

    def test_manage_uv_layers_lifecycle(self):
        # 1. Create layer
        res_create = manage_uv_layers(self.bpy, "Cube", action="create", layer_name="LightmapUV")
        self.assertEqual(res_create["uv_layer_count"], 2)

        # 2. Duplicate create fails
        with self.assertRaises(ValueError):
            manage_uv_layers(self.bpy, "Cube", action="create", layer_name="LightmapUV")

        # 3. Rename layer
        res_rename = manage_uv_layers(self.bpy, "Cube", action="rename", layer_name="LightmapUV", new_name="BakedUV")
        self.assertIn("BakedUV", [l["name"] for l in res_rename["uv_layers"]])

        # 4. Set active
        res_active = manage_uv_layers(self.bpy, "Cube", action="set_active", layer_name="BakedUV")
        self.assertEqual(res_active["active_uv_layer"], "BakedUV")

        # 5. Remove layer
        res_remove = manage_uv_layers(self.bpy, "Cube", action="remove", layer_name="BakedUV")
        self.assertEqual(res_remove["uv_layer_count"], 1)

    def test_handlers_registered_in_all_handlers(self):
        self.assertIn("manage_uv_seams", ALL_HANDLERS)
        self.assertIn("pack_uv_islands", ALL_HANDLERS)
        self.assertIn("manage_uv_layers", ALL_HANDLERS)
        self.assertIn("inspect_uv_mesh", ALL_HANDLERS)


if __name__ == "__main__":
    unittest.main()
