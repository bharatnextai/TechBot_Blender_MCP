from tests.unit.modeling_approval_fixture import approved
"""
Unit and Integration Tests for TASK-UMCP-0075 Capabilities:
1. select_object (and select) - Object selection & active-object management.
2. purge_orphaned_datablocks (and purge_orphans) - Datablock lifecycle cleanup.
"""

import unittest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_SELECT_OBJECT,
    TOOL_SELECT,
    TOOL_PURGE_ORPHANED_DATABLOCKS,
    TOOL_PURGE_ORPHANS,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_DESTRUCTIVE,
    ALLOWED_MODELING_ACTIONS,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.agents.modeling import (
    ModelingAgent,
    MODELING_AGENT_ID,
    CAPABILITY_MODELING_OBJECT_OPS,
    CAPABILITY_MODELING_EXECUTION,
)
from shared.models.agent_contracts import AgentTask, TaskStatus
from blender_addon.universal_mcp.bridge.handlers import (
    handle_select_object,
    handle_purge_orphaned_datablocks,
    handle_execute_blender_code,
    ALL_HANDLERS,
)


class TestTask75Capabilities(unittest.TestCase):
    """Test suite for select_object and purge_orphaned_datablocks."""

    def setUp(self):
        self.agent = ModelingAgent()
        self.registry = ToolRegistry()

    def test_tool_definitions_and_tiers(self):
        """Verify tool schemas, permission tiers, and aliases."""
        for tool_name in (TOOL_SELECT_OBJECT, TOOL_SELECT):
            self.assertIn(tool_name, TOOL_DEFINITIONS)
            spec = TOOL_DEFINITIONS[tool_name]
            self.assertEqual(spec["permission_tier"], PERMISSION_SCENE_MUTATION)
            props = spec["input_schema"]["properties"]
            self.assertIn("name", props)
            self.assertIn("state", props)
            self.assertIn("deselect_all", props)
            self.assertIn("make_active", props)
            self.assertIn("approved", props)
            self.assertEqual(spec["input_schema"]["required"], ["name"])

        for tool_name in (TOOL_PURGE_ORPHANED_DATABLOCKS, TOOL_PURGE_ORPHANS):
            self.assertIn(tool_name, TOOL_DEFINITIONS)
            spec = TOOL_DEFINITIONS[tool_name]
            self.assertEqual(spec["permission_tier"], PERMISSION_DESTRUCTIVE)
            props = spec["input_schema"]["properties"]
            self.assertIn("do_recursive", props)
            self.assertIn("do_local_ids", props)
            self.assertIn("do_linked_ids", props)
            self.assertIn("approved", props)

        # Check registered in ToolRegistry for MCP discovery
        tools = {t.name: t for t in self.registry.get_mcp_tools()}
        self.assertIn(TOOL_SELECT_OBJECT, tools)
        self.assertIn(TOOL_SELECT, tools)
        self.assertIn(TOOL_PURGE_ORPHANED_DATABLOCKS, tools)
        self.assertIn(TOOL_PURGE_ORPHANS, tools)

        # Check in ALLOWED_MODELING_ACTIONS
        self.assertIn("select_object", ALLOWED_MODELING_ACTIONS)
        self.assertIn("select", ALLOWED_MODELING_ACTIONS)
        self.assertIn("purge_orphaned_datablocks", ALLOWED_MODELING_ACTIONS)
        self.assertIn("purge_orphans", ALLOWED_MODELING_ACTIONS)

        # Check in ALL_HANDLERS
        self.assertIn(TOOL_SELECT_OBJECT, ALL_HANDLERS)
        self.assertIn(TOOL_SELECT, ALL_HANDLERS)
        self.assertIn(TOOL_PURGE_ORPHANED_DATABLOCKS, ALL_HANDLERS)
        self.assertIn(TOOL_PURGE_ORPHANS, ALL_HANDLERS)

    def test_approval_fail_closed_and_untrusted_flag(self):
        """Verify rejection of missing approval and untrusted approved=True."""
        # 1. select_object requires approval
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_SELECT_OBJECT, {"name": "Cube"}, trusted_approval=False)
        self.assertIn("requires explicit user approval", str(ctx.exception))

        # Rejection of client approved=True
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_SELECT_OBJECT, {"name": "Cube", "approved": True}, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize", str(ctx.exception))

        # 2. purge_orphaned_datablocks requires approval
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_PURGE_ORPHANED_DATABLOCKS, {}, trusted_approval=False)
        self.assertIn("requires explicit user approval", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_PURGE_ORPHANED_DATABLOCKS, {"approved": True}, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize", str(ctx.exception))

    def test_validation_constraints(self):
        """Verify strict input validation constraints."""
        # select_object empty name
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SELECT_OBJECT, {"name": "   "}, trusted_approval=True)

        # select_object invalid state type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SELECT_OBJECT, {"name": "Cube", "state": "not_bool"}, trusted_approval=True)

        # select_object invalid deselect_all type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SELECT_OBJECT, {"name": "Cube", "deselect_all": 123}, trusted_approval=True)

        # select_object invalid make_active type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SELECT_OBJECT, {"name": "Cube", "make_active": "yes"}, trusted_approval=True)

        # purge_orphaned_datablocks invalid do_recursive type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_PURGE_ORPHANED_DATABLOCKS, {"do_recursive": "no"}, trusted_approval=True)

        # Valid inputs sanitize properly
        sanitized_sel = validate_tool_input(
            TOOL_SELECT_OBJECT,
            {"name": "Cube", "state": True, "deselect_all": True, "make_active": True},
            trusted_approval=True,
        )
        self.assertEqual(sanitized_sel["name"], "Cube")
        self.assertTrue(sanitized_sel["state"])
        self.assertTrue(sanitized_sel["deselect_all"])
        self.assertTrue(sanitized_sel["make_active"])

        sanitized_purge = validate_tool_input(
            TOOL_PURGE_ORPHANED_DATABLOCKS,
            {"do_recursive": True, "do_local_ids": True, "do_linked_ids": False},
            trusted_approval=True,
        )
        self.assertTrue(sanitized_purge["do_recursive"])
        self.assertTrue(sanitized_purge["do_local_ids"])
        self.assertFalse(sanitized_purge["do_linked_ids"])

    def test_agent_capability_routing(self):
        """Verify deterministic routing to ModelingAgent capabilities."""
        manifest = self.agent.get_manifest()
        caps = {c.capability_id: c for c in manifest.capabilities}

        # select_object belongs to CAPABILITY_MODELING_OBJECT_OPS
        self.assertIn(CAPABILITY_MODELING_OBJECT_OPS, caps)
        obj_cap = caps[CAPABILITY_MODELING_OBJECT_OPS]
        self.assertIn(TOOL_SELECT_OBJECT, obj_cap.supported_task_types)
        self.assertIn(TOOL_SELECT, obj_cap.supported_task_types)

        # purge_orphaned_datablocks belongs to CAPABILITY_MODELING_EXECUTION
        self.assertIn(CAPABILITY_MODELING_EXECUTION, caps)
        exec_cap = caps[CAPABILITY_MODELING_EXECUTION]
        self.assertIn(TOOL_PURGE_ORPHANED_DATABLOCKS, exec_cap.supported_task_types)
        self.assertIn(TOOL_PURGE_ORPHANS, exec_cap.supported_task_types)

        # Agent can_handle check
        task_sel = AgentTask(
            task_id="t1",
            required_capability=CAPABILITY_MODELING_OBJECT_OPS,
            task_type=TOOL_SELECT_OBJECT,
            input_params={"name": "Cube"},
        )
        self.assertTrue(self.agent.can_handle(task_sel))

        task_purge = AgentTask(
            task_id="t2",
            required_capability=CAPABILITY_MODELING_EXECUTION,
            task_type=TOOL_PURGE_ORPHANED_DATABLOCKS,
            input_params={"do_recursive": True},
        )
        self.assertTrue(self.agent.can_handle(task_purge))

    def test_handle_select_object_logic(self):
        """Verify select_object handler behavior with mocked bpy context."""
        mock_bpy = MagicMock()
        mock_cube = MagicMock()
        mock_cube.name = "Cube"
        mock_cube.selected=False
        mock_cube.select_get.side_effect=lambda:mock_cube.selected
        mock_cube.select_set.side_effect=lambda state:setattr(mock_cube,"selected",state)

        mock_light = MagicMock()
        mock_light.name = "Light"
        mock_light.selected=True
        mock_light.select_get.side_effect=lambda:mock_light.selected
        mock_light.select_set.side_effect=lambda state:setattr(mock_light,"selected",state)

        mock_objects = {"Cube": mock_cube, "Light": mock_light}
        mock_bpy.data.objects.get.side_effect = lambda n: mock_objects.get(n)
        mock_bpy.data.objects.__contains__.side_effect = lambda n: n in mock_objects
        mock_bpy.data.objects.__iter__.return_value = iter([mock_cube, mock_light])

        mock_vl_objects = MagicMock()
        mock_vl_objects.__iter__.side_effect = lambda:iter([mock_cube, mock_light])
        mock_vl_objects.__contains__.side_effect = lambda n: n in ("Cube", "Light", mock_cube, mock_light)
        mock_vl_objects.active = mock_light

        mock_view_layer = MagicMock()
        mock_view_layer.objects = mock_vl_objects
        mock_bpy.context.view_layer = mock_view_layer
        mock_bpy.context.mode="OBJECT"
        mock_bpy.context.scene.objects.get.side_effect=lambda name:mock_objects.get(name)

        # 1. Nonexistent object
        with self.assertRaises(ValueError):
            handle_select_object(
                bpy_module=mock_bpy,
                params=approved('select_object',{"name": "Nonexistent", "trusted_approval": True, "_trusted_test_override": True}),
            )

        # 2. Select Cube with deselect_all=True and make_active=True
        res = handle_select_object(
            bpy_module=mock_bpy,
            params=approved('select_object',{
                "name": "Cube",
                "state": True,
                "deselect_all": True,
                "make_active": True,
                "trusted_approval": True,
                "_trusted_test_override": True,
            }),
        )
        mock_light.select_set.assert_called_with(False)
        mock_cube.select_set.assert_called_with(True)
        self.assertEqual(mock_view_layer.objects.active, mock_cube)
        self.assertTrue(res["success"])
        self.assertEqual(res["name"], "Cube")
        self.assertTrue(res["state"])

        # 3. Deselect Cube, leaving unrelated active object alone if make_active not requested
        res2 = handle_select_object(
            bpy_module=mock_bpy,
            params=approved('select_object',{
                "name": "Light",
                "state": False,
                "deselect_all": False,
                "make_active": False,
                "trusted_approval": True,
                "_trusted_test_override": True,
            }),
        )
        mock_light.select_set.assert_called_with(False)
        self.assertTrue(res2["success"])
        self.assertFalse(res2["state"])

    def test_handle_purge_orphaned_datablocks_logic(self):
        """Verify purge_orphaned_datablocks handler invokes bpy.data.orphans_purge."""
        mock_bpy = MagicMock()
        mock_bpy.data.orphans_purge.return_value = 5

        res = handle_purge_orphaned_datablocks(
            bpy_module=mock_bpy,
            params=approved('purge_orphaned_datablocks',{
                "do_recursive": True,
                "do_local_ids": True,
                "do_linked_ids": True,
                "trusted_approval": True,
                "_trusted_test_override": True,
            }),
        )
        mock_bpy.data.orphans_purge.assert_called_once_with(
            do_local_ids=True,
            do_linked_ids=True,
            do_recursive=True,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["purged_count"], 5)
        self.assertTrue(res["do_recursive"])

        # Verify error handling when orphans_purge raises
        mock_bpy.data.orphans_purge.side_effect = RuntimeError("Internal purge failed")
        with self.assertRaises(RuntimeError):
            handle_purge_orphaned_datablocks(
                bpy_module=mock_bpy,
                params=approved('purge_orphaned_datablocks',{"trusted_approval": True, "_trusted_test_override": True}),
            )

    def test_execute_blender_code_integration(self):
        """Verify select_object and purge_orphaned_datablocks inside execute_blender_code operations."""
        mock_bpy = MagicMock()
        mock_cube = MagicMock()
        mock_cube.name = "Cube"
        mock_cube.select_get.return_value = True
        mock_bpy.data.objects.get.side_effect = lambda n: mock_cube if n == "Cube" else None
        mock_vl_objects = MagicMock()
        mock_vl_objects.__iter__.side_effect = lambda:iter([mock_cube])
        mock_vl_objects.__contains__.side_effect = lambda n: n in ("Cube", mock_cube)
        mock_vl_objects.active = mock_cube

        mock_view_layer = MagicMock()
        mock_view_layer.objects = mock_vl_objects
        mock_bpy.context.view_layer = mock_view_layer
        mock_bpy.context.mode="OBJECT"
        mock_bpy.context.scene.objects.get.side_effect=lambda name:mock_cube if name=="Cube" else None
        mock_bpy.data.orphans_purge.return_value = 2

        ops = [
            {"action": "select_object", "target": "Cube", "state": True, "make_active": True},
            {"action": "purge_orphaned_datablocks", "do_recursive": True},
        ]
        from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
        registry=get_approval_registry();params={"operations":ops}
        request=registry.create_request("execute_blender_code",params)
        ok,token=registry.resolve_request(request.request_id,"approved");self.assertTrue(ok)
        res=handle_execute_blender_code(bpy_module=mock_bpy,
            params={**params,"request_id":request.request_id,"approval_token":token})
        self.assertTrue(res["executed"])
        self.assertEqual(len(res["operations"]), 2)
        self.assertEqual(res["operations"][0]["action"], "select_object")
        self.assertEqual(res["operations"][1]["action"], "purge_orphaned_datablocks")
        self.assertEqual(res["operations"][1]["purged_count"], 2)


if __name__ == "__main__":
    unittest.main()
