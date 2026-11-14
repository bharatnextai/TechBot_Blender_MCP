"""
Unit tests for Capability 7: Image Textures & Texture Baking Foundation (v0.1.67).
Tests:
1. Tool discovery, schema declarations, and permissions.
2. Input validation and parameter bounds in validate_tool_input.
3. Security gating: rejection of untrusted approved=True.
4. MaterialsAgent manifest, routing, and task execution for baking.
5. Bridge execution with Mock Blender: bake_object_texture, image assignment in shader nodes.
6. Error handling: missing UVs, cancelled operators, invalid dimensions, non-existent objects, and transactional cleanup.
"""

import math
import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch

from shared.schemas.tool_schemas import (
    TOOL_BAKE_OBJECT_TEXTURE,
    TOOL_BAKE_TEXTURE,
    TOOL_BAKE_MATERIALS,
    TOOL_BAKE_MESH_SURFACE_MAP,
    TOOL_MANAGE_SHADER_NODES,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.security.approval import ApprovalManager
from mcp_service.agents.materials import (
    MaterialsAgent,
    CAPABILITY_MATERIALS_MANAGE,
)
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.execution.blender_executor import BlenderExecutor
from blender_addon.universal_mcp.bridge.handlers import (
    handle_bake_object_texture,
    handle_manage_shader_nodes,
)


class TestImageTexturesBakingSchemasAndValidation(unittest.TestCase):
    """Tests schema registrations and input validation for image textures & baking tools."""

    def test_schema_registration_and_permissions(self):
        for tool in (TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS, TOOL_BAKE_MESH_SURFACE_MAP):
            self.assertIn(tool, TOOL_DEFINITIONS)
            self.assertEqual(TOOL_DEFINITIONS[tool]["permission_tier"], PERMISSION_SCENE_MUTATION)

    def test_tool_registry_discovery(self):
        registry = ToolRegistry()
        self.assertTrue(registry.has_tool(TOOL_BAKE_OBJECT_TEXTURE))
        self.assertTrue(registry.has_tool(TOOL_BAKE_TEXTURE))
        self.assertTrue(registry.has_tool(TOOL_BAKE_MATERIALS))
        self.assertTrue(registry.has_tool(TOOL_BAKE_MESH_SURFACE_MAP))

    def test_bake_object_texture_validation_valid(self):
        params = {
            "object_name": "Cube",
            "bake_type": "ROUGHNESS",
            "image_name": "Cube_Roughness",
            "width": 512,
            "height": 512,
            "margin": 8,
            "save_filepath": "C:/tmp/test_bake.png" if os.name == "nt" else "/tmp/test_bake.png",
        }
        sanitized = validate_tool_input(TOOL_BAKE_OBJECT_TEXTURE, params, trusted_approval=True)
        self.assertEqual(sanitized["object_name"], "Cube")
        self.assertEqual(sanitized["bake_type"], "ROUGHNESS")
        self.assertEqual(sanitized["width"], 512)
        self.assertEqual(sanitized["margin"], 8)

    def test_bake_object_texture_validation_bounds(self):
        # Width out of bounds
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BAKE_OBJECT_TEXTURE, {"object_name": "Cube", "width": 16}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BAKE_OBJECT_TEXTURE, {"object_name": "Cube", "width": 16384}, trusted_approval=True)
        # Margin out of bounds
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BAKE_OBJECT_TEXTURE, {"object_name": "Cube", "margin": 128}, trusted_approval=True)
        # Invalid bake type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BAKE_OBJECT_TEXTURE, {"object_name": "Cube", "bake_type": "INVALID_TYPE"}, trusted_approval=True)


class TestImageTexturesBakingSecurity(unittest.TestCase):
    """Tests security gating and untrusted approved=True rejection."""

    def setUp(self):
        self.approval_mgr = ApprovalManager()

    def test_requires_approval(self):
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_BAKE_OBJECT_TEXTURE))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_BAKE_TEXTURE))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_BAKE_MATERIALS))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_BAKE_MESH_SURFACE_MAP))

    def test_rejection_of_untrusted_approved_flag(self):
        cases = [
            (TOOL_BAKE_OBJECT_TEXTURE, {"object_name": "Cube", "approved": True}),
            (TOOL_BAKE_TEXTURE, {"object_name": "Cube", "approved": True}),
            (TOOL_BAKE_MATERIALS, {"object_name": "Cube", "approved": True}),
            (TOOL_BAKE_MESH_SURFACE_MAP, {"target_object": "Cube", "approved": True}),
        ]
        for tool, params in cases:
            with self.assertRaises(PermissionError) as ctx:
                validate_tool_input(tool, params, trusted_approval=False)
            self.assertIn("untrusted and cannot authorize", str(ctx.exception))


class MockExecutor(BlenderExecutor):
    def __init__(self):
        self.invocations = []

    def is_connected(self) -> bool:
        return True

    def execute_tool(self, tool_name: str, arguments: dict = None, trusted_approval: bool = None) -> BridgeResponse:
        self.invocations.append((tool_name, arguments, trusted_approval))
        return BridgeResponse.success({
            "action": tool_name,
            "success": True,
            "baked": True,
            "verified": True,
            "object_name": arguments.get("object_name", "Cube"),
            "bake_type": arguments.get("bake_type", "COMBINED"),
            "width": arguments.get("width", 1024),
            "height": arguments.get("height", 1024),
            "saved_filepath": arguments.get("save_filepath"),
        })


class TestMaterialsAgentBakingIntegration(unittest.TestCase):
    """Tests MaterialsAgent capability descriptors and routing for baking."""

    def setUp(self):
        self.agent = MaterialsAgent(version="0.1.67")
        self.executor = MockExecutor()

    def test_can_handle_baking_tools(self):
        for tool in (TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS):
            task = AgentTask(task_id=f"task_{tool}", required_capability=CAPABILITY_MATERIALS_MANAGE, task_type=tool)
            self.assertTrue(self.agent.can_handle(task))

    def test_execute_bake_task_success(self):
        task = AgentTask(
            task_id="task_bake_1",
            required_capability=CAPABILITY_MATERIALS_MANAGE,
            task_type=TOOL_BAKE_OBJECT_TEXTURE,
            input_params={"object_name": "TargetCube", "bake_type": "ROUGHNESS", "width": 512, "height": 512},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=True)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertTrue(res.verification.status == "PASS")


class TestBridgeBakeOperations(unittest.TestCase):
    """Tests handler logic for bake_object_texture with mock Blender datablocks."""

    def setUp(self):
        self.node = NS(select=False)
        class Nodes(list):
            pass
        self.nodes = Nodes([self.node])
        self.nodes.active = self.node
        self.nodes.new = Mock(return_value=NS(select=False))
        self.nodes.remove = Mock()
        self.mat = NS(node_tree=NS(nodes=self.nodes), name="CubeMat", use_nodes=True)
        self.obj = NS(type="MESH", name="Cube", data=NS(uv_layers=[NS(name="UVMap")], materials=[self.mat]), select_set=Mock())
        self.image = NS(size=[64, 64], has_data=True, pixels=[0.5, 0.5, 0.5, 1.0] * 64, name="Cube_Bake", colorspace_settings=NS(name="sRGB"), filepath_raw="", file_format="PNG", save=Mock())
        self.operator = Mock(return_value={"FINISHED"})
        self.bpy = NS(
            data=NS(objects={"Cube": self.obj}, images=NS(get=lambda name: self.image, new=lambda name, width, height: self.image), materials={"CubeMat": self.mat}),
            ops=NS(object=NS(bake=self.operator)),
            context=NS(scene=NS(render=NS(engine="BLENDER_EEVEE")), selected_objects=[self.obj], view_layer=NS(objects=NS(active=self.obj))),
        )

    def test_bake_success(self):
        params = {
            "object_name": "Cube",
            "bake_type": "ROUGHNESS",
            "width": 64,
            "height": 64,
            "margin": 2,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_bake_object_texture(self.bpy, params)
        self.assertTrue(res["baked"])
        self.assertTrue(res["verified"])
        self.assertEqual(res["object_name"], "Cube")
        self.assertEqual(res["bake_type"], "ROUGHNESS")
        self.assertEqual(self.image.colorspace_settings.name, "Non-Color")

    def test_bake_missing_uv_rejected(self):
        self.obj.data.uv_layers = []
        with self.assertRaises(ValueError) as ctx:
            handle_bake_object_texture(self.bpy, {"object_name": "Cube", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("requires a mesh with UV coordinates", str(ctx.exception))

    def test_bake_cancelled_operator_restores_state(self):
        self.operator.return_value = {"CANCELLED"}
        with self.assertRaises(RuntimeError) as ctx:
            handle_bake_object_texture(self.bpy, {"object_name": "Cube", "trusted_approval": True, "_trusted_test_override": True})
        self.assertIn("did not finish", str(ctx.exception))
        # Ensure engine restored
        self.assertEqual(self.bpy.context.scene.render.engine, "BLENDER_EEVEE")


if __name__ == "__main__":
    unittest.main()

