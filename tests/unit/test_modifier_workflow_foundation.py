"""
Unit tests for Modifier Workflow Foundation tools (v0.1.63).
Covers:
1. Tool registry discovery and schema definitions for edit_modifier_stack, inspect_modifier_stack, configure_modifier, inspect_modifiers, apply_modifier.
2. Input validation, alias normalization (target_object, object_name -> name), and parameter bounds.
3. Fail-closed security: rejection of untrusted approved=True without trusted approval.
4. Snapshot ID requirement for modifier stack mutations and apply.
5. ModelingAgent capability and routing verification.
6. Handler registrations in ALL_HANDLERS and _LOCAL_TEST_TOOLS.
"""

import unittest
from unittest.mock import MagicMock

from shared.schemas.tool_schemas import (
    TOOL_EDIT_MODIFIER_STACK,
    TOOL_INSPECT_MODIFIER_STACK,
    TOOL_CONFIGURE_MODIFIER,
    TOOL_INSPECT_MODIFIERS,
    TOOL_APPLY_MODIFIER,
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


class TestModifierWorkflowFoundationUnit(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.agent = ModelingAgent()
        self.valid_snapshot = "sha256:" + "a" * 64

    def test_tool_registry_discovery(self):
        """All modifier foundation tools must be discovered via ToolRegistry."""
        tools = self.registry.get_mcp_tools()
        tool_names = {t.name for t in tools}
        for expected in (
            TOOL_EDIT_MODIFIER_STACK,
            TOOL_INSPECT_MODIFIER_STACK,
            TOOL_CONFIGURE_MODIFIER,
            TOOL_INSPECT_MODIFIERS,
            TOOL_APPLY_MODIFIER,
        ):
            self.assertIn(expected, tool_names, f"Tool '{expected}' missing from registry")

        self.assertEqual(TOOL_DEFINITIONS[TOOL_APPLY_MODIFIER]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_EDIT_MODIFIER_STACK]["permission_tier"], PERMISSION_SCENE_MUTATION)
        self.assertEqual(TOOL_DEFINITIONS[TOOL_INSPECT_MODIFIER_STACK]["permission_tier"], PERMISSION_READ_ONLY)

    def test_untrusted_approval_rejected(self):
        """Untrusted client-supplied approved=True must be rejected fail-closed."""
        tools_to_test = [
            (TOOL_APPLY_MODIFIER, {
                "name": "Cube",
                "modifier_name": "Subsurf",
                "expected_snapshot_id": self.valid_snapshot,
                "approved": True,
            }),
            (TOOL_EDIT_MODIFIER_STACK, {
                "name": "Cube",
                "modifier_name": "Subsurf",
                "modifier_type": "SUBSURF",
                "action": "add",
                "properties": {"levels": 1},
                "expected_snapshot_id": self.valid_snapshot,
                "approved": True,
            }),
            (TOOL_CONFIGURE_MODIFIER, {
                "name": "Cube",
                "modifier_name": "Subsurf",
                "modifier_type": "SUBSURF",
                "action": "add",
                "properties": {"levels": 1},
                "approved": True,
            }),
        ]
        for tool_name, params in tools_to_test:
            with self.subTest(tool=tool_name):
                with self.assertRaises(PermissionError):
                    validate_tool_input(tool_name, params, trusted_approval=False)

    def test_parameter_alias_normalization(self):
        """target_object and object_name should normalize to name."""
        res_target = validate_tool_input(
            TOOL_APPLY_MODIFIER,
            {
                "target_object": "TargetCube",
                "modifier_name": "Subsurf",
                "expected_snapshot_id": self.valid_snapshot,
            },
            trusted_approval=True,
        )
        self.assertEqual(res_target["name"], "TargetCube")
        self.assertNotIn("target_object", res_target)

        res_obj = validate_tool_input(
            TOOL_INSPECT_MODIFIER_STACK,
            {"object_name": "InspectCube"},
            trusted_approval=True,
        )
        self.assertEqual(res_obj["name"], "InspectCube")
        self.assertNotIn("object_name", res_obj)

    def test_apply_modifier_validation_bounds(self):
        """apply_modifier must enforce modifier_name, snapshot pattern, and types."""
        # Missing modifier_name
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_APPLY_MODIFIER,
                {"name": "Cube", "expected_snapshot_id": self.valid_snapshot},
                trusted_approval=True,
            )

        # Missing expected_snapshot_id
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_APPLY_MODIFIER,
                {"name": "Cube", "modifier_name": "Subsurf"},
                trusted_approval=True,
            )

        # Malformed snapshot_id
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_APPLY_MODIFIER,
                {"name": "Cube", "modifier_name": "Subsurf", "expected_snapshot_id": "bad_hash"},
                trusted_approval=True,
            )

        # Valid call with optional modifier_type
        res = validate_tool_input(
            TOOL_APPLY_MODIFIER,
            {
                "name": "Cube",
                "modifier_name": "Subsurf",
                "modifier_type": "SUBSURF",
                "expected_snapshot_id": self.valid_snapshot,
            },
            trusted_approval=True,
        )
        self.assertEqual(res["modifier_type"], "SUBSURF")
        self.assertEqual(res["modifier_name"], "Subsurf")

    def test_modeling_agent_manifest_and_routing(self):
        """ModelingAgent manifest must declare modifier stack capability with apply_modifier."""
        manifest = create_modeling_manifest()
        stack_cap = next(c for c in manifest.capabilities if c.capability_id == "modeling.modifier_stack")
        self.assertIn(TOOL_EDIT_MODIFIER_STACK, stack_cap.supported_task_types)
        self.assertIn(TOOL_APPLY_MODIFIER, stack_cap.supported_task_types)
        self.assertIn(TOOL_APPLY_MODIFIER, SUPPORTED_MODELING_TOOLS)

        # Test execute_task routing
        mock_executor = MagicMock()
        mock_executor.execute = MagicMock(return_value={"status": "SUCCESS", "result": {}})
        self.agent._executor = mock_executor

        task = AgentTask(
            task_id="mod_task_1",
            task_type=TOOL_APPLY_MODIFIER,
            required_capability="modeling.modifier_stack",
            input_params={
                "name": "Cube",
                "modifier_name": "Subsurf",
                "expected_snapshot_id": self.valid_snapshot,
            },
        )
        self.assertTrue(self.agent.can_handle(task))

    def test_handler_registrations(self):
        """All modifier tools must be in ALL_HANDLERS and _LOCAL_TEST_TOOLS."""
        for tool_name in (
            "edit_modifier_stack",
            "inspect_modifier_stack",
            "configure_modifier",
            "inspect_modifiers",
            "apply_modifier",
        ):
            self.assertIn(tool_name, ALL_HANDLERS)
            self.assertIn(tool_name, _LOCAL_TEST_TOOLS)


if __name__ == "__main__":
    unittest.main()

