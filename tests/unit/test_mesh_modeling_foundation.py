"""
Unit tests for Mesh Modeling Foundation tools (v0.1.62).
Covers:
1. Tool registry discovery and schema definitions for bevel_mesh, split_mesh, dissolve_mesh, merge_mesh, recalculate_normals and their aliases.
2. Input validation, alias normalization, and bounds enforcement.
3. Fail-closed security: rejection of untrusted approved=True without trusted approval.
4. Snapshot ID requirement for explicit element index lists.
5. ModelingAgent capability and routing verification.
6. Handler registrations in ALL_HANDLERS and _LOCAL_TEST_TOOLS.
"""

import math
import unittest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_BEVEL_MESH,
    TOOL_BEVEL_EDGES,
    TOOL_SPLIT_MESH,
    TOOL_KNIFE_MESH,
    TOOL_BISECT_MESH,
    TOOL_DISSOLVE_MESH,
    TOOL_MERGE_MESH,
    TOOL_RECALCULATE_NORMALS,
    TOOL_ALIGN_NORMALS,
    TOOL_DEFINITIONS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.agents.modeling import (
    ModelingAgent,
    create_modeling_manifest,
    CAPABILITY_MODELING_EDIT,
    SUPPORTED_MODELING_TOOLS,
)
from shared.models.agent_contracts import AgentTask
from blender_addon.universal_mcp.bridge.handlers import ALL_HANDLERS, _LOCAL_TEST_TOOLS


class TestMeshModelingFoundationUnit(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.agent = ModelingAgent()
        self.valid_snapshot = "sha256:" + "a" * 64

    def test_tool_registry_discovery(self):
        """All mesh modeling foundation tools must be discovered via ToolRegistry."""
        tools = self.registry.get_mcp_tools()
        tool_names = {t.name for t in tools}
        for expected in (
            TOOL_BEVEL_MESH, TOOL_BEVEL_EDGES,
            TOOL_SPLIT_MESH, TOOL_KNIFE_MESH, TOOL_BISECT_MESH,
            TOOL_DISSOLVE_MESH, TOOL_MERGE_MESH,
            TOOL_RECALCULATE_NORMALS, TOOL_ALIGN_NORMALS,
        ):
            self.assertIn(expected, tool_names, f"Tool '{expected}' missing from registry")
            tool_def = TOOL_DEFINITIONS[expected]
            self.assertEqual(tool_def["permission_tier"], PERMISSION_SCENE_MUTATION)

    def test_untrusted_approval_rejected(self):
        """Untrusted client-supplied approved=True must be rejected fail-closed."""
        tools_to_test = [
            (TOOL_BEVEL_MESH, {"name": "Cube", "offset": 0.1, "approved": True}),
            (TOOL_SPLIT_MESH, {"name": "Cube", "method": "BISECT", "approved": True}),
            (TOOL_DISSOLVE_MESH, {"name": "Cube", "dissolve_type": "EDGES", "approved": True}),
            (TOOL_MERGE_MESH, {"name": "Cube", "mode": "CENTER", "approved": True}),
            (TOOL_RECALCULATE_NORMALS, {"name": "Cube", "action": "RECALCULATE_OUTSIDE", "approved": True}),
        ]
        for tool_name, params in tools_to_test:
            with self.subTest(tool=tool_name):
                with self.assertRaises(PermissionError):
                    validate_tool_input(tool_name, params, trusted_approval=False)

    def test_parameter_alias_normalization(self):
        """target_object and object_name should normalize to name."""
        res_target = validate_tool_input(
            TOOL_BEVEL_MESH,
            {"target_object": "TargetObj", "offset": 0.2},
            trusted_approval=True,
        )
        self.assertEqual(res_target["name"], "TargetObj")
        self.assertEqual(res_target["offset"], 0.2)

        res_obj = validate_tool_input(
            TOOL_SPLIT_MESH,
            {"object_name": "ObjectObj", "method": "BISECT"},
            trusted_approval=True,
        )
        self.assertEqual(res_obj["name"], "ObjectObj")
        self.assertEqual(res_obj["method"], "BISECT")

    def test_bevel_validation_bounds(self):
        """Bevel parameters must enforce offset, segments, profile, and affect bounds."""
        # Negative offset
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BEVEL_MESH, {"name": "Cube", "offset": -0.5}, trusted_approval=True)

        # Invalid segments (0 or > 64)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BEVEL_MESH, {"name": "Cube", "segments": 0}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BEVEL_MESH, {"name": "Cube", "segments": 100}, trusted_approval=True)

        # Invalid profile (< 0 or > 1)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BEVEL_MESH, {"name": "Cube", "profile": 1.5}, trusted_approval=True)

        # Invalid affect
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BEVEL_MESH, {"name": "Cube", "affect": "FACES"}, trusted_approval=True)

        # Explicit edges list requires expected_snapshot_id
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BEVEL_MESH, {"name": "Cube", "edges": [0, 1, 2]}, trusted_approval=True)

        # Explicit edges with snapshot_id succeeds
        res = validate_tool_input(
            TOOL_BEVEL_MESH,
            {"name": "Cube", "edges": [0, 1, 2], "expected_snapshot_id": self.valid_snapshot},
            trusted_approval=True,
        )
        self.assertEqual(res["edges"], [0, 1, 2])

    def test_split_validation_bounds(self):
        """Split parameters must enforce method, vectors, and cut bounds."""
        # Invalid method
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SPLIT_MESH, {"name": "Cube", "method": "INVALID"}, trusted_approval=True)

        # Invalid cuts for subdivide
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SPLIT_MESH, {"name": "Cube", "method": "SUBDIVIDE", "cuts": 0}, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_SPLIT_MESH, {"name": "Cube", "method": "SUBDIVIDE", "cuts": 20}, trusted_approval=True)

        # Zero plane normal for bisect
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_SPLIT_MESH,
                {"name": "Cube", "method": "BISECT", "plane_no": [0.0, 0.0, 0.0]},
                trusted_approval=True,
            )

        # Explicit edges requires expected_snapshot_id
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_SPLIT_MESH,
                {"name": "Cube", "method": "SUBDIVIDE", "edges": [1, 2]},
                trusted_approval=True,
            )

    def test_dissolve_validation_bounds(self):
        """Dissolve parameters must enforce element type and snapshot requirements."""
        # Invalid dissolve type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_DISSOLVE_MESH, {"name": "Cube", "dissolve_type": "CORNER"}, trusted_approval=True)

        # Explicit indices without snapshot fails
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_DISSOLVE_MESH, {"name": "Cube", "indices": [0, 1]}, trusted_approval=True)

        # Valid with snapshot
        res = validate_tool_input(
            TOOL_DISSOLVE_MESH,
            {"name": "Cube", "dissolve_type": "EDGES", "indices": [0, 1], "expected_snapshot_id": self.valid_snapshot},
            trusted_approval=True,
        )
        self.assertEqual(res["dissolve_type"], "EDGES")
        self.assertEqual(res["indices"], [0, 1])

    def test_merge_validation_bounds(self):
        """Merge parameters must enforce mode, location, and distance threshold."""
        # Invalid mode
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_MERGE_MESH, {"name": "Cube", "mode": "RANDOM"}, trusted_approval=True)

        # Mode CURSOR requires target_location
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_MERGE_MESH, {"name": "Cube", "mode": "CURSOR"}, trusted_approval=True)

        # Mode DISTANCE negative threshold fails
        with self.assertRaises(ValueError):
            validate_tool_input(
                TOOL_MERGE_MESH,
                {"name": "Cube", "mode": "DISTANCE", "distance_threshold": -0.01},
                trusted_approval=True,
            )

        # Explicit vertices require snapshot
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_MERGE_MESH, {"name": "Cube", "vertices": [0, 1]}, trusted_approval=True)

    def test_recalculate_normals_validation(self):
        """Recalculate normals must enforce action bounds and explicit faces requirements."""
        # Invalid action
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_RECALCULATE_NORMALS, {"name": "Cube", "action": "INVERT_ALL"}, trusted_approval=True)

        # Valid actions
        for action in ("RECALCULATE_OUTSIDE", "RECALCULATE_INSIDE", "FLIP"):
            res = validate_tool_input(
                TOOL_RECALCULATE_NORMALS,
                {"name": "Cube", "action": action},
                trusted_approval=True,
            )
            self.assertEqual(res["action"], action)

    def test_modeling_agent_manifest_and_routing(self):
        """ModelingAgent manifest must declare CAPABILITY_MODELING_EDIT with foundation tools."""
        manifest = create_modeling_manifest()
        edit_cap = next(c for c in manifest.capabilities if c.capability_id == CAPABILITY_MODELING_EDIT)
        for expected_tool in (
            TOOL_BEVEL_MESH, TOOL_BEVEL_EDGES,
            TOOL_SPLIT_MESH, TOOL_KNIFE_MESH, TOOL_BISECT_MESH,
            TOOL_DISSOLVE_MESH, TOOL_MERGE_MESH,
            TOOL_RECALCULATE_NORMALS, TOOL_ALIGN_NORMALS,
        ):
            self.assertIn(expected_tool, edit_cap.supported_task_types)
            self.assertIn(expected_tool, SUPPORTED_MODELING_TOOLS)

        # Test execute_task routing
        mock_executor = MagicMock()
        mock_executor.execute = MagicMock(return_value={"status": "SUCCESS", "result": {}})
        self.agent._executor = mock_executor

        task = AgentTask(
            task_id="t1",
            task_type=TOOL_BEVEL_MESH,
            required_capability=CAPABILITY_MODELING_EDIT,
            input_params={"name": "Cube", "offset": 0.1},
        )
        self.assertTrue(self.agent.can_handle(task))

    def test_handler_registrations(self):
        """All tools must be in ALL_HANDLERS and _LOCAL_TEST_TOOLS."""
        for tool_name in (
            "bevel_mesh", "bevel_edges",
            "split_mesh", "knife_mesh", "bisect_mesh",
            "dissolve_mesh", "merge_mesh",
            "recalculate_normals", "align_normals",
        ):
            self.assertIn(tool_name, ALL_HANDLERS)
            self.assertIn(tool_name, _LOCAL_TEST_TOOLS)


if __name__ == "__main__":
    unittest.main()
