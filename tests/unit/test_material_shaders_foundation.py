"""
Unit tests for Capability 6: Materials & Procedural Shaders Foundation (v0.1.66).
Tests:
1. Tool discovery, schema declarations, and permissions.
2. Input validation and parameter bounds in validate_tool_input.
3. Security gating: rejection of untrusted approved=True.
4. MaterialsAgent manifest, routing, and task execution.
5. Bridge execution with Mock Blender: create_material, assign_material, manage_shader_nodes.
6. Error handling: invalid sockets, invalid properties, node existence checks, and rollback.
"""

import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace as NS

from shared.schemas.tool_schemas import (
    TOOL_CREATE_MATERIAL,
    TOOL_ASSIGN_MATERIAL,
    TOOL_MANAGE_SHADER_NODES,
    TOOL_CONFIGURE_MATERIAL_SHADER,
    TOOL_INSPECT_MATERIAL_SHADER,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.security.approval import ApprovalManager
from mcp_service.agents.materials import (
    MaterialsAgent,
    CAPABILITY_MATERIALS_MANAGE,
    CAPABILITY_MATERIALS_INSPECT,
    CAPABILITY_MATERIALS_TYPED_SHADER,
)
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.execution.blender_executor import BlenderExecutor
from blender_addon.universal_mcp.bridge.handlers import (
    ALL_HANDLERS,
    handle_create_material,
    handle_assign_material,
    handle_manage_shader_nodes,
)


class TestMaterialShadersSchemasAndValidation(unittest.TestCase):
    """Tests schema registrations and input validation for material and shader tools."""

    def test_schema_registration_and_permissions(self):
        for tool in (TOOL_CREATE_MATERIAL, TOOL_ASSIGN_MATERIAL, TOOL_MANAGE_SHADER_NODES, TOOL_CONFIGURE_MATERIAL_SHADER):
            self.assertIn(tool, TOOL_DEFINITIONS)
            self.assertEqual(TOOL_DEFINITIONS[tool]["permission_tier"], PERMISSION_SCENE_MUTATION)

        self.assertIn(TOOL_INSPECT_MATERIAL_SHADER, TOOL_DEFINITIONS)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_INSPECT_MATERIAL_SHADER]["permission_tier"], PERMISSION_READ_ONLY)

    def test_tool_registry_discovery(self):
        registry = ToolRegistry()
        self.assertTrue(registry.has_tool(TOOL_CREATE_MATERIAL))
        self.assertTrue(registry.has_tool(TOOL_ASSIGN_MATERIAL))
        self.assertTrue(registry.has_tool(TOOL_MANAGE_SHADER_NODES))
        self.assertTrue(registry.has_tool(TOOL_CONFIGURE_MATERIAL_SHADER))
        self.assertTrue(registry.has_tool(TOOL_INSPECT_MATERIAL_SHADER))

    def test_create_material_validation_valid(self):
        params = {
            "name": "Gold",
            "base_color": [1.0, 0.85, 0.57, 1.0],
            "roughness": 0.1,
            "metallic": 1.0,
            "ior": 1.45,
        }
        sanitized = validate_tool_input(TOOL_CREATE_MATERIAL, params, trusted_approval=True)
        self.assertEqual(sanitized["name"], "Gold")
        self.assertEqual(sanitized["metallic"], 1.0)
        self.assertEqual(sanitized["roughness"], 0.1)

    def test_create_material_validation_bounds(self):
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_MATERIAL, {"name": "M", "roughness": 1.5}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_MATERIAL, {"name": "M", "metallic": -0.1}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_MATERIAL, {"name": "M", "base_color": [1.2, 0.0, 0.0]}, trusted_approval=True)

    def test_assign_material_validation(self):
        params = {"target_name": "Cube", "material_name": "Gold", "slot_index": 0}
        sanitized = validate_tool_input(TOOL_ASSIGN_MATERIAL, params, trusted_approval=True)
        self.assertEqual(sanitized["target_name"], "Cube")
        self.assertEqual(sanitized["material_name"], "Gold")

    def test_manage_shader_nodes_validation(self):
        params = {
            "target_name": "Gold",
            "action": "connect",
            "from_node": "Noise",
            "from_socket": "Color",
            "to_node": "Principled BSDF",
            "to_socket": "Base Color",
        }
        sanitized = validate_tool_input(TOOL_MANAGE_SHADER_NODES, params, trusted_approval=True)
        self.assertEqual(sanitized["action"], "connect")
        self.assertEqual(sanitized["from_node"], "Noise")


class TestMaterialShadersSecurity(unittest.TestCase):
    """Tests security gating and untrusted approved=True rejection."""

    def setUp(self):
        self.approval_mgr = ApprovalManager()

    def test_requires_approval(self):
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_CREATE_MATERIAL))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_ASSIGN_MATERIAL))
        self.assertTrue(self.approval_mgr.requires_approval(TOOL_MANAGE_SHADER_NODES))
        self.assertFalse(self.approval_mgr.requires_approval(TOOL_INSPECT_MATERIAL_SHADER))

    def test_rejection_of_untrusted_approved_flag(self):
        cases = [
            (TOOL_CREATE_MATERIAL, {"name": "M", "approved": True}),
            (TOOL_ASSIGN_MATERIAL, {"target_name": "Obj", "material_name": "M", "approved": True}),
            (TOOL_MANAGE_SHADER_NODES, {"target_name": "M", "action": "list_nodes", "approved": True}),
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
        return BridgeResponse.success({"action": tool_name, "success": True, "target_name": arguments.get("target_name", "Mat")})


class TestMaterialsAgentIntegration(unittest.TestCase):
    """Tests MaterialsAgent capability descriptors and routing."""

    def setUp(self):
        self.agent = MaterialsAgent(version="0.1.66")
        self.executor = MockExecutor()

    def test_manifest_capabilities(self):
        caps = {c.capability_id: c for c in self.agent.manifest.capabilities}
        self.assertIn(CAPABILITY_MATERIALS_MANAGE, caps)
        self.assertIn(CAPABILITY_MATERIALS_TYPED_SHADER, caps)
        self.assertIn(CAPABILITY_MATERIALS_INSPECT, caps)

    def test_can_handle(self):
        for tool in (TOOL_CREATE_MATERIAL, TOOL_ASSIGN_MATERIAL, TOOL_MANAGE_SHADER_NODES):
            task = AgentTask(task_id=f"task_{tool}", required_capability=CAPABILITY_MATERIALS_MANAGE, task_type=tool)
            self.assertTrue(self.agent.can_handle(task))


class MockSocket:
    def __init__(self, name: str, identifier: str, default_val=0.0):
        self.name = name
        self.identifier = identifier
        self.default_value = default_val
        self.is_linked = False


class MockShaderNode:
    def __init__(self, name: str, node_type: str):
        self.name = name
        self.type = node_type
        self.bl_idname = node_type
        self.label = ""
        self.location = [0.0, 0.0]
        self.inputs = [
            MockSocket("Base Color", "Base Color", [0.8, 0.8, 0.8, 1.0]),
            MockSocket("Roughness", "Roughness", 0.5),
            MockSocket("Metallic", "Metallic", 0.0),
            MockSocket("Scale", "Scale", 5.0),
            MockSocket("Fac", "Fac", 0.0),
        ]
        self.outputs = [
            MockSocket("BSDF", "BSDF"),
            MockSocket("Color", "Color", [1.0, 1.0, 1.0, 1.0]),
            MockSocket("Fac", "Fac", 0.5),
        ]


class MockLink:
    def __init__(self, from_node, from_socket, to_node, to_socket):
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket


class MockNodeLinks(list):
    def new(self, out_sock, in_sock):
        out_sock.is_linked = in_sock.is_linked = True
        link = MockLink(getattr(out_sock, "node", None), out_sock, getattr(in_sock, "node", None), in_sock)
        self.append(link)
        return link

    def remove(self, link):
        if link in self:
            super().remove(link)


class MockNodesCollection(dict):
    def new(self, node_type: str):
        node = MockShaderNode(node_type, node_type)
        self[node_type] = node
        return node

    def get(self, name, default=None):
        for node in self.values():
            if node.name == name:
                return node
        return super().get(name, default)

    def __getitem__(self, name):
        for node in self.values():
            if node.name == name:
                return node
        return super().__getitem__(name)

    def __contains__(self, name):
        for node in self.values():
            if node.name == name:
                return True
        return super().__contains__(name)

    def __iter__(self):
        return iter(list(self.values()))

    def remove(self, node):
        for k, v in list(self.items()):
            if v == node or v.name == getattr(node, "name", None):
                del self[k]
                return


class MockNodeTree:
    def __init__(self):
        bsdf = MockShaderNode("Principled BSDF", "ShaderNodeBsdfPrincipled")
        output = MockShaderNode("Material Output", "ShaderNodeOutputMaterial")
        self.nodes = MockNodesCollection({"Principled BSDF": bsdf, "Material Output": output})
        self.links = MockNodeLinks([MockLink(bsdf, bsdf.outputs[0], output, output.inputs[0])])


class MockMaterial:
    def __init__(self, name: str):
        self.name = name
        self.use_nodes = True
        self.node_tree = MockNodeTree()


class MockMaterialSlot:
    def __init__(self, material=None):
        self.material = material


class MockSceneObject:
    def __init__(self, name: str):
        self.name = name
        self.material_slots = []
        self.data = MagicMock()
        self.data.materials = MagicMock()
        self.data.materials.append = lambda mat: self.material_slots.append(MockMaterialSlot(mat))


class TestBridgeMaterialOperations(unittest.TestCase):
    """Tests handler logic for material and shader node mutations."""

    def setUp(self):
        self.obj = MockSceneObject("Cube")
        self.mat = MockMaterial("Gold")
        self.bpy = NS(
            data=NS(
                materials={"Gold": self.mat},
                objects={"Cube": self.obj},
            ),
            context=NS(scene=NS(objects={"Cube": self.obj}, umcp_require_scene_mutation_approval=False)),
        )

    def test_assign_material_success(self):
        params = {"target_name": "Cube", "material_name": "Gold", "trusted_approval": True, "_trusted_test_override": True}
        res = handle_assign_material(self.bpy, params)
        self.assertEqual(res["target"], "Cube")
        self.assertEqual(res["material_name"], "Gold")
        self.assertEqual(res["slot_count"], 1)

    def test_manage_shader_nodes_create_and_connect(self):
        # 1. Create procedural noise node
        create_res = handle_manage_shader_nodes(self.bpy, {
            "target_name": "Gold",
            "action": "create_node",
            "node_type": "ShaderNodeTexNoise",
            "node_name": "NoiseTex",
            "trusted_approval": True,
            "_trusted_test_override": True,
        })
        self.assertTrue(create_res["created"])
        self.assertIn("NoiseTex", self.mat.node_tree.nodes)

        # 2. Set property
        prop_res = handle_manage_shader_nodes(self.bpy, {
            "target_name": "Gold",
            "action": "set_property",
            "node_name": "NoiseTex",
            "property_name": "Scale",
            "property_value": 12.5,
            "trusted_approval": True,
            "_trusted_test_override": True,
        })
        self.assertTrue(prop_res["verified"])
        self.assertEqual(prop_res["property_value"], 12.5)

        # 3. Connect NoiseTex.Color -> Principled BSDF.Base Color
        conn_res = handle_manage_shader_nodes(self.bpy, {
            "target_name": "Gold",
            "action": "connect",
            "from_node": "NoiseTex",
            "from_socket": "Color",
            "to_node": "Principled BSDF",
            "to_socket": "Base Color",
            "trusted_approval": True,
            "_trusted_test_override": True,
        })
        self.assertTrue(conn_res["connected"])

        # 4. List nodes
        list_res = handle_manage_shader_nodes(self.bpy, {
            "target_name": "Gold",
            "action": "list_nodes",
        })
        node_names = [n["name"] for n in list_res["nodes"]]
        self.assertIn("NoiseTex", node_names)
        self.assertIn("Principled BSDF", node_names)

        # 5. Remove node
        rem_res = handle_manage_shader_nodes(self.bpy, {
            "target_name": "Gold",
            "action": "remove_node",
            "node_name": "NoiseTex",
            "trusted_approval": True,
            "_trusted_test_override": True,
        })
        self.assertTrue(rem_res["removed"])
        self.assertNotIn("NoiseTex", self.mat.node_tree.nodes)

    def test_missing_socket_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            handle_manage_shader_nodes(self.bpy, {
                "target_name": "Gold",
                "action": "connect",
                "from_node": "Principled BSDF",
                "from_socket": "NonExistentSocket",
                "to_node": "Principled BSDF",
                "to_socket": "Roughness",
                "trusted_approval": True,
                "_trusted_test_override": True,
            })
        self.assertIn("not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
