from tests.unit.modeling_approval_fixture import approved
"""
Focused unit tests for TASK-UMCP-0073:
1. Keyframe manipulation (manage_keyframe, insert_keyframe, delete_keyframe)
2. Geometry Nodes (configure_geometry_nodes, inspect_geometry_nodes)
3. File import/export (export_scene_asset, import_scene_asset, glTF/GLB, FBX, USD)
4. Object duplication and renaming (duplicate_object, rename_object)

Validates schemas, approval fail-closed enforcement, agent routing, mock bridge handlers,
data independence, and parameter validation.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_MANAGE_KEYFRAME,
    TOOL_INSERT_KEYFRAME,
    TOOL_DELETE_KEYFRAME,
    TOOL_CONFIGURE_GEOMETRY_NODES,
    TOOL_INSPECT_GEOMETRY_NODES,
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_EXPORT_SCENE,
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_IMPORT_SCENE,
    TOOL_DUPLICATE_OBJECT,
    TOOL_DUPLICATE,
    TOOL_RENAME_OBJECT,
    TOOL_RENAME,
    TOOL_DEFINITIONS,
    ALLOWED_MODELING_ACTIONS,
    validate_tool_input,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    CAPABILITY_MODELING_KEYFRAME,
    CAPABILITY_MODELING_GEONODES,
    CAPABILITY_MODELING_ASSET_IO,
    CAPABILITY_MODELING_OBJECT_OPS,
    SUPPORTED_MODELING_TOOLS,
)
from mcp_service.agents.registry import create_default_registry
from mcp_service.agents.manager import AgentManager
from shared.models.agent_contracts import AgentTask
from blender_addon.universal_mcp.bridge.handlers import (
    handle_manage_keyframe,
    handle_configure_geometry_nodes,
    handle_export_scene_asset,
    handle_import_scene_asset,
    handle_duplicate_object,
    handle_rename_object,
    handle_execute_blender_code,
    ALL_HANDLERS,
    READ_ONLY_HANDLERS,
)


class TestTask73SchemasAndValidation(unittest.TestCase):
    """Tests schemas, definitions, and parameter validation for Task 73 tools."""

    def test_tool_definitions_present(self):
        for tool_name in (
            TOOL_MANAGE_KEYFRAME, TOOL_INSERT_KEYFRAME, TOOL_DELETE_KEYFRAME,
            TOOL_CONFIGURE_GEOMETRY_NODES, TOOL_INSPECT_GEOMETRY_NODES,
            TOOL_EXPORT_SCENE_ASSET, TOOL_EXPORT_SCENE,
            TOOL_IMPORT_SCENE_ASSET, TOOL_IMPORT_SCENE,
            TOOL_DUPLICATE_OBJECT, TOOL_DUPLICATE,
            TOOL_RENAME_OBJECT, TOOL_RENAME,
        ):
            self.assertIn(tool_name, TOOL_DEFINITIONS, f"Missing definition for {tool_name}")
            self.assertIn(tool_name, ALL_HANDLERS, f"Missing handler mapping for {tool_name}")

    def test_read_only_handlers(self):
        self.assertIn("inspect_geometry_nodes", READ_ONLY_HANDLERS)

    def test_allowed_modeling_actions(self):
        for action in (
            "manage_keyframe", "insert_keyframe", "delete_keyframe",
            "configure_geometry_nodes", "inspect_geometry_nodes",
            "export_scene_asset", "export_scene",
            "import_scene_asset", "import_scene",
            "duplicate_object", "duplicate",
            "rename_object", "rename",
        ):
            self.assertIn(action, ALLOWED_MODELING_ACTIONS)

    def test_untrusted_approval_rejected(self):
        """Model-supplied approved=True must be rejected fail-closed for all mutation tools."""
        mutation_tools = [
            (TOOL_MANAGE_KEYFRAME, {"name": "Cube", "property_path": "location", "frame": 1, "approved": True}),
            (TOOL_CONFIGURE_GEOMETRY_NODES, {"name": "Cube", "action": "create", "approved": True}),
            (TOOL_EXPORT_SCENE_ASSET, {"filepath": "C:/tmp/test.glb", "approved": True}),
            (TOOL_IMPORT_SCENE_ASSET, {"filepath": "C:/tmp/test.glb", "approved": True}),
            (TOOL_DUPLICATE_OBJECT, {"name": "Cube", "approved": True}),
            (TOOL_RENAME_OBJECT, {"name": "Cube", "new_name": "NewCube", "approved": True}),
        ]
        for tool_name, params in mutation_tools:
            with self.assertRaises(PermissionError, msg=f"Should reject untrusted approved=True for {tool_name}"):
                validate_tool_input(tool_name, params, trusted_approval=False)

    def test_keyframe_validation(self):
        # Valid input with trusted approval
        valid = validate_tool_input(
            TOOL_MANAGE_KEYFRAME,
            {"name": "Cube", "property_path": "location", "frame": 10, "action": "insert"},
            trusted_approval=True,
        )
        self.assertEqual(valid["name"], "Cube")
        self.assertEqual(valid["property_path"], "location")
        self.assertEqual(valid["frame"], 10)

        # Invalid property path
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_MANAGE_KEYFRAME,
                {"name": "Cube", "property_path": "invalid_path", "frame": 10},
                trusted_approval=True,
            )

        # Invalid index
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_MANAGE_KEYFRAME,
                {"name": "Cube", "property_path": "location", "frame": 10, "index": 5},
                trusted_approval=True,
            )

    def test_geometry_nodes_validation(self):
        # Valid configure input
        valid = validate_tool_input(
            TOOL_CONFIGURE_GEOMETRY_NODES,
            {"name": "Cube", "action": "create", "modifier_name": "GeometryNodes"},
            trusted_approval=True,
        )
        self.assertEqual(valid["action"], "create")

        # Invalid action
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_GEOMETRY_NODES,
                {"name": "Cube", "action": "destroy_everything"},
                trusted_approval=True,
            )

        # Invalid socket_type
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_CONFIGURE_GEOMETRY_NODES,
                {"name": "Cube", "action": "add_socket", "socket_name": "Val", "socket_type": "InvalidSocket"},
                trusted_approval=True,
            )

    def test_asset_io_validation(self):
        # Valid export
        valid = validate_tool_input(
            TOOL_EXPORT_SCENE_ASSET,
            {"filepath": "C:/tmp/export.glb", "format": "GLB", "overwrite": True},
            trusted_approval=True,
        )
        self.assertEqual(valid["format"], "GLB")
        self.assertTrue(valid["overwrite"])

        # Invalid export format
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_EXPORT_SCENE_ASSET,
                {"filepath": "C:/tmp/export.xyz", "format": "XYZ"},
                trusted_approval=True,
            )

        # Missing filepath
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_EXPORT_SCENE_ASSET,
                {"format": "GLB"},
                trusted_approval=True,
            )

    def test_object_ops_validation(self):
        # Valid duplication
        valid_dup = validate_tool_input(
            TOOL_DUPLICATE_OBJECT,
            {"name": "Cube", "new_name": "CubeCopy", "linked": False},
            trusted_approval=True,
        )
        self.assertEqual(valid_dup["name"], "Cube")
        self.assertEqual(valid_dup["new_name"], "CubeCopy")

        # Missing rename new_name
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_RENAME_OBJECT,
                {"name": "Cube"},
                trusted_approval=True,
            )


class TestTask73AgentRouting(unittest.TestCase):
    """Tests Agent Manager deterministic routing of new capabilities."""

    def setUp(self):
        self.registry = create_default_registry()
        self.manager = AgentManager(registry=self.registry)

    def test_routing_capabilities(self):
        cases = [
            (TOOL_MANAGE_KEYFRAME, CAPABILITY_MODELING_KEYFRAME),
            (TOOL_CONFIGURE_GEOMETRY_NODES, CAPABILITY_MODELING_GEONODES),
            (TOOL_EXPORT_SCENE_ASSET, CAPABILITY_MODELING_ASSET_IO),
            (TOOL_DUPLICATE_OBJECT, CAPABILITY_MODELING_OBJECT_OPS),
        ]
        for tool, cap_id in cases:
            task = AgentTask(
                task_id=f"test-route-{tool}",
                required_capability=cap_id,
                task_type=tool,
            )
            res = self.manager.route_task(task, require_verified=True)
            self.assertTrue(res.success, f"Failed to route {tool}")
            self.assertEqual(res.agent.agent_id, "agent.modeling")
            self.assertEqual(res.capability.read_write, "SCENE_MUTATION")


class TestTask73MockBridgeHandlers(unittest.TestCase):
    """Tests bridge handler logic with mock Blender datablocks."""

    def _create_mock_bpy(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Cube"
        mock_obj.type = "MESH"
        mock_obj.location = [0.0, 0.0, 0.0]
        mock_obj.rotation_euler = [0.0, 0.0, 0.0]
        mock_obj.scale = [1.0, 1.0, 1.0]
        mock_obj.animation_data = None
        mock_obj.modifiers = MagicMock()
        mock_obj.modifiers.get.return_value = None
        mock_obj.data = MagicMock()
        mock_obj.data.name = "CubeMesh"
        mock_obj.users_collection = [MagicMock(name="Scene Collection")]

        mock_bpy.data.objects = {"Cube": mock_obj}
        mock_bpy.context.scene.objects = mock_bpy.data.objects
        mock_bpy.context.scene.collection.objects.link = MagicMock()
        return mock_bpy, mock_obj

    def test_keyframe_insert_and_delete(self):
        mock_bpy, mock_obj = self._create_mock_bpy()
        mock_obj.keyframe_insert.return_value = True
        mock_obj.keyframe_delete.return_value = True

        # Insert keyframe on location
        res_insert = handle_manage_keyframe(
            bpy_module=mock_bpy,
            params={
                "name": "Cube",
                "property_path": "location",
                "frame": 10.0,
                "action": "insert",
                "value": [1.0, 2.0, 3.0],
                "trusted_approval": True,
                "_trusted_test_override": True,
            },
        )
        self.assertTrue(res_insert["success"])
        self.assertEqual(res_insert["frame"], 10.0)
        self.assertEqual(mock_obj.location, [1.0, 2.0, 3.0])
        mock_obj.keyframe_insert.assert_called_once_with(data_path="location", frame=10.0, index=-1)

        # Delete keyframe
        res_delete = handle_manage_keyframe(
            bpy_module=mock_bpy,
            params={
                "name": "Cube",
                "property_path": "location",
                "frame": 10.0,
                "action": "delete",
                "trusted_approval": True,
                "_trusted_test_override": True,
            },
        )
        self.assertTrue(res_delete["success"])
        mock_obj.keyframe_delete.assert_called_once_with(data_path="location", frame=10.0, index=-1)

    def test_geometry_nodes_inspect_and_configure(self):
        mock_bpy, mock_obj = self._create_mock_bpy()

        # Inspect (no approval required)
        res_inspect = handle_configure_geometry_nodes(
            bpy_module=mock_bpy,
            params={"name": "Cube", "action": "inspect"},
        )
        self.assertEqual(res_inspect["action"], "inspect")
        self.assertFalse(res_inspect["modifier_exists"])

        # Create modifier & node tree
        mock_mod = MagicMock()
        mock_mod.name = "GeometryNodes"
        mock_mod.type = "NODES"
        mock_tree = MagicMock()
        mock_tree.name = "Cube_GeometryNodes"
        mock_tree.interface.items_tree = []
        mock_mod.node_group = mock_tree

        mock_obj.modifiers.new.return_value = mock_mod
        mock_bpy.data.node_groups.get.return_value = None
        mock_bpy.data.node_groups.new.return_value = mock_tree

        res_create = handle_configure_geometry_nodes(
            bpy_module=mock_bpy,
            params=approved('configure_geometry_nodes',{
                "name": "Cube",
                "action": "create",
                "trusted_approval": True,
                "_trusted_test_override": True,
            }),
        )
        self.assertEqual(res_create["action"], "create")
        self.assertTrue(res_create["modifier_exists"])

    def test_duplicate_object_independent_data(self):
        mock_bpy, mock_obj = self._create_mock_bpy()
        mock_dup = MagicMock()
        mock_dup.name = "Cube_Copy"
        mock_dup.data = MagicMock()
        mock_dup.data.name = "CubeMesh_Copy"
        mock_obj.copy.return_value = mock_dup

        res = handle_duplicate_object(
            bpy_module=mock_bpy,
            params=approved('duplicate_object',{
                "name": "Cube",
                "new_name": "Cube_Copy",
                "linked": False,
                "trusted_approval": True,
                "_trusted_test_override": True,
            }),
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["duplicate_name"], "Cube_Copy")
        self.assertTrue(res["data_independent"])
        mock_obj.copy.assert_called_once()
        mock_obj.data.copy.assert_called_once()

    def test_duplicate_object_with_transforms_and_linked(self):
        mock_bpy, mock_obj = self._create_mock_bpy()
        mock_dup = MagicMock()
        mock_dup.name = "Cube_Symmetric"
        mock_dup.data = mock_obj.data
        mock_dup.location = [0.0, 0.0, 0.0]
        mock_dup.rotation_euler = [0.0, 0.0, 0.0]
        mock_dup.scale = [1.0, 1.0, 1.0]
        mock_obj.copy.return_value = mock_dup

        res = handle_duplicate_object(
            bpy_module=mock_bpy,
            params=approved('duplicate_object', {
                "name": "Cube",
                "new_name": "Cube_Symmetric",
                "linked": True,
                "location": [-2.0, 3.0, 1.5],
                "rotation_euler": [0.0, 0.0, 3.14159],
                "scale": [1.0, 1.0, 1.0],
                "trusted_approval": True,
                "_trusted_test_override": True,
            }),
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["duplicate_name"], "Cube_Symmetric")
        self.assertTrue(res["linked"])
        self.assertFalse(res["data_independent"])
        self.assertEqual(mock_dup.location, (-2.0, 3.0, 1.5))
        self.assertEqual(mock_dup.rotation_euler, (0.0, 0.0, 3.14159))
        self.assertEqual(mock_dup.scale, (1.0, 1.0, 1.0))

    def test_rename_object(self):
        mock_bpy, mock_obj = self._create_mock_bpy()

        # Normal rename
        res = handle_rename_object(
            bpy_module=mock_bpy,
            params=approved('rename_object',{
                "name": "Cube",
                "new_name": "RenamedCube",
                "trusted_approval": True,
                "_trusted_test_override": True,
            }),
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["old_name"], "Cube")
        self.assertEqual(mock_obj.name, "RenamedCube")

        # Collision rejection
        mock_bpy.data.objects["ExistingOther"] = MagicMock()
        with self.assertRaises(ValueError):
            handle_rename_object(
                bpy_module=mock_bpy,
                params=approved('rename_object',{
                    "name": "Cube",
                    "new_name": "ExistingOther",
                    "trusted_approval": True,
                    "_trusted_test_override": True,
                }),
            )

    def test_export_and_import_path_validation(self):
        mock_bpy, _ = self._create_mock_bpy()

        # Missing import file raises FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            handle_import_scene_asset(
                bpy_module=mock_bpy,
                params={
                    "filepath": "C:/non_existent_dir_12345/missing.glb",
                    "trusted_approval": True,
                    "_trusted_test_override": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
