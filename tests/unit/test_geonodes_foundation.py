"""
Unit tests for Geometry Nodes Foundation tools (v0.1.64).
Covers:
1. Tool registry discovery and schema definitions for configure_geometry_nodes and inspect_geometry_nodes.
2. Input validation, alias normalization (target_object, object_name -> name), and parameter bounds.
3. Fail-closed security: rejection of untrusted approved=True without trusted approval.
4. Snapshot ID pattern validation for optimistic concurrency.
5. Node type normalization and validation.
6. ModelingAgent capability and routing verification.
7. Handler registrations in ALL_HANDLERS and _LOCAL_TEST_TOOLS.
"""

import unittest
from unittest.mock import MagicMock

from shared.schemas.tool_schemas import (
    TOOL_CONFIGURE_GEOMETRY_NODES,
    TOOL_INSPECT_GEOMETRY_NODES,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.agents.modeling import (
    ModelingAgent,
    create_modeling_manifest,
    SUPPORTED_MODELING_TOOLS,
)
from shared.models.agent_contracts import AgentTask
from blender_addon.universal_mcp.bridge.handlers import ALL_HANDLERS, _LOCAL_TEST_TOOLS
from blender_addon.universal_mcp.bridge.geonodes_foundation import (
    normalize_node_type,
    ALLOWED_NODE_TYPES,
)


class TestGeometryNodesFoundationUnit(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.agent = ModelingAgent()
        self.valid_snapshot = "sha256:" + "a" * 64

    def test_tool_registry_discovery(self):
        """configure_geometry_nodes and inspect_geometry_nodes must be discovered via ToolRegistry."""
        tools = self.registry.get_mcp_tools()
        tool_names = {t.name for t in tools}
        self.assertIn(TOOL_CONFIGURE_GEOMETRY_NODES, tool_names)
        self.assertIn(TOOL_INSPECT_GEOMETRY_NODES, tool_names)

        self.assertEqual(
            TOOL_DEFINITIONS[TOOL_CONFIGURE_GEOMETRY_NODES]["permission_tier"],
            PERMISSION_SCENE_MUTATION,
        )
        self.assertEqual(
            TOOL_DEFINITIONS[TOOL_INSPECT_GEOMETRY_NODES]["permission_tier"],
            PERMISSION_READ_ONLY,
        )

    def test_untrusted_approval_rejected(self):
        """Untrusted client-supplied approved=True must be rejected fail-closed."""
        with self.assertRaises(PermissionError):
            validate_tool_input(
                TOOL_CONFIGURE_GEOMETRY_NODES,
                {
                    "name": "Cube",
                    "action": "create",
                    "approved": True,
                },
                trusted_approval=False,
            )

    def test_parameter_alias_normalization(self):
        """target_object and object_name should normalize to name."""
        res_target = validate_tool_input(
            TOOL_CONFIGURE_GEOMETRY_NODES,
            {
                "target_object": "TargetMesh",
                "action": "create",
            },
            trusted_approval=True,
        )
        self.assertEqual(res_target["name"], "TargetMesh")
        self.assertNotIn("target_object", res_target)

        res_obj = validate_tool_input(
            TOOL_INSPECT_GEOMETRY_NODES,
            {"object_name": "InspectMesh"},
            trusted_approval=True,
        )
        self.assertEqual(res_obj["name"], "InspectMesh")
        self.assertNotIn("object_name", res_obj)

    def test_actions_validation(self):
        """All supported graph actions must be accepted; invalid ones rejected."""
        valid_actions = [
            "inspect", "create", "assign_group", "add_node", "remove_node",
            "add_link", "remove_link", "set_node_input", "add_socket",
            "set_socket_default", "configure_graph", "update_graph", "evaluate", "apply"
        ]
        for act in valid_actions:
            with self.subTest(action=act):
                res = validate_tool_input(
                    TOOL_CONFIGURE_GEOMETRY_NODES,
                    {"name": "Cube", "action": act},
                    trusted_approval=True,
                )
                self.assertEqual(res["action"], act)

        # Invalid action rejected
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_GEOMETRY_NODES,
                {"name": "Cube", "action": "forbidden_hack"},
                trusted_approval=True,
            )

    def test_snapshot_id_validation(self):
        """Malformed snapshot_id must be rejected; valid one accepted."""
        # Valid snapshot
        res = validate_tool_input(
            TOOL_CONFIGURE_GEOMETRY_NODES,
            {
                "name": "Cube",
                "action": "add_node",
                "node_type": "GeometryNodeSubdivisionSurface",
                "expected_snapshot_id": self.valid_snapshot,
            },
            trusted_approval=True,
        )
        self.assertEqual(res["expected_snapshot_id"], self.valid_snapshot)

        # Malformed snapshot
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_GEOMETRY_NODES,
                {
                    "name": "Cube",
                    "action": "add_node",
                    "expected_snapshot_id": "not_a_valid_hash",
                },
                trusted_approval=True,
            )

    def test_node_type_normalization(self):
        """node_type should normalize aliases and reject unsupported types."""
        self.assertEqual(normalize_node_type("Transform"), "GeometryNodeTransform")
        self.assertEqual(normalize_node_type("Subsurf"), "GeometryNodeSubdivisionSurface")
        self.assertEqual(normalize_node_type("MeshCube"), "GeometryNodeMeshCube")
        self.assertEqual(normalize_node_type("CombineXYZ"), "ShaderNodeCombineXYZ")
        self.assertEqual(normalize_node_type("Math"), "ShaderNodeMath")
        self.assertEqual(normalize_node_type("GeometryNodeTriangulate"), "GeometryNodeTriangulate")

        # Unsupported node rejected
        with self.assertRaises(ValueError):
            normalize_node_type("ArbitraryMaliciousClass")

    def test_modeling_agent_manifest_and_routing(self):
        """ModelingAgent manifest must declare geometry_nodes capability."""
        manifest = create_modeling_manifest()
        gn_cap = next(c for c in manifest.capabilities if c.capability_id == "modeling.geometry_nodes")
        self.assertIn(TOOL_CONFIGURE_GEOMETRY_NODES, gn_cap.supported_task_types)
        self.assertIn(TOOL_INSPECT_GEOMETRY_NODES, gn_cap.supported_task_types)

        task = AgentTask(
            task_id="gn_task_1",
            task_type=TOOL_CONFIGURE_GEOMETRY_NODES,
            required_capability="modeling.geometry_nodes",
            input_params={
                "name": "Cube",
                "action": "create",
            },
        )
        self.assertTrue(self.agent.can_handle(task))

    def test_handler_registrations(self):
        """Geometry Nodes tools must be in ALL_HANDLERS and _LOCAL_TEST_TOOLS."""
        for tool_name in (
            "configure_geometry_nodes",
            "inspect_geometry_nodes",
            "configure_modeling_geometry",
            "inspect_modeling_geometry",
        ):
            self.assertIn(tool_name, ALL_HANDLERS)
            self.assertIn(tool_name, _LOCAL_TEST_TOOLS)


if __name__ == "__main__":
    unittest.main()

