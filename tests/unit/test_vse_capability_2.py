"""
Unit tests for VSE Capability 2: Editorial & Trimming Operations.
Tests schema definitions, parameter sanitization, validation rules,
and fail-closed approval barriers for trim, split, and reorder.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_TRIM_VSE_STRIP,
    TOOL_SPLIT_VSE_STRIP,
    TOOL_REORDER_VSE_STRIPS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability2Schemas:
    """Tests for VSE Capability 2 tool registrations and schemas."""

    def test_vse_cap2_tools_registered(self):
        registry = ToolRegistry()
        for t in (TOOL_TRIM_VSE_STRIP, TOOL_SPLIT_VSE_STRIP, TOOL_REORDER_VSE_STRIPS):
            assert t in TOOL_DEFINITIONS, f"Tool {t} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(t), f"Tool {t} missing from ToolRegistry"
            assert TOOL_DEFINITIONS[t]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability2Validation:
    """Tests for parameter validation on editorial tools."""

    def test_trim_strip_validation(self):
        # Valid absolute
        p_abs = {"name": "Strip1", "left_handle": 10, "right_handle": 50, "ripple": True}
        s_abs = validate_tool_input(TOOL_TRIM_VSE_STRIP, p_abs, trusted_approval=True)
        assert s_abs["name"] == "Strip1"
        assert s_abs["left_handle"] == 10
        assert s_abs["right_handle"] == 50
        assert s_abs["ripple"] is True
        assert s_abs["trim_mode"] == "ABSOLUTE"

        # Valid relative
        p_rel = {"name": "Strip1", "trim_mode": "RELATIVE", "right_handle": -5}
        s_rel = validate_tool_input(TOOL_TRIM_VSE_STRIP, p_rel, trusted_approval=True)
        assert s_rel["trim_mode"] == "RELATIVE"
        assert s_rel["right_handle"] == -5

        # Missing both handles
        with pytest.raises(ValueError, match="At least one of 'left_handle' or 'right_handle'"):
            validate_tool_input(TOOL_TRIM_VSE_STRIP, {"name": "Strip1"}, trusted_approval=True)

        # Invalid mode
        with pytest.raises(ValueError, match="Invalid value for 'trim_mode'"):
            validate_tool_input(TOOL_TRIM_VSE_STRIP, {"name": "Strip1", "trim_mode": "MAGIC", "left_handle": 5}, trusted_approval=True)

    def test_split_strip_validation(self):
        # Valid split
        p_split = {"name": "Strip1", "split_frame": 25, "right_strip_name": "Strip1_tail"}
        s_split = validate_tool_input(TOOL_SPLIT_VSE_STRIP, p_split, trusted_approval=True)
        assert s_split["name"] == "Strip1"
        assert s_split["split_frame"] == 25
        assert s_split["right_strip_name"] == "Strip1_tail"

        # Missing split_frame
        with pytest.raises(ValueError, match="Missing required parameter 'split_frame'"):
            validate_tool_input(TOOL_SPLIT_VSE_STRIP, {"name": "Strip1"}, trusted_approval=True)

    def test_reorder_strip_validation(self):
        # Valid MOVE
        p_move = {"action": "MOVE", "name": "Strip1", "channel": 2, "target_frame": 30}
        s_move = validate_tool_input(TOOL_REORDER_VSE_STRIPS, p_move, trusted_approval=True)
        assert s_move["action"] == "MOVE"
        assert s_move["name"] == "Strip1"
        assert s_move["channel"] == 2
        assert s_move["target_frame"] == 30

        # Valid SWAP
        p_swap = {"action": "SWAP", "strip_a": "Strip1", "strip_b": "Strip2"}
        s_swap = validate_tool_input(TOOL_REORDER_VSE_STRIPS, p_swap, trusted_approval=True)
        assert s_swap["action"] == "SWAP"
        assert s_swap["strip_a"] == "Strip1"
        assert s_swap["strip_b"] == "Strip2"

        # SWAP with identical names
        with pytest.raises(ValueError, match="Action 'SWAP' requires distinct strip names"):
            validate_tool_input(TOOL_REORDER_VSE_STRIPS, {"action": "SWAP", "strip_a": "S1", "strip_b": "S1"}, trusted_approval=True)

        # Valid CLOSE_GAPS
        p_gaps = {"action": "CLOSE_GAPS", "channel": 1}
        s_gaps = validate_tool_input(TOOL_REORDER_VSE_STRIPS, p_gaps, trusted_approval=True)
        assert s_gaps["action"] == "CLOSE_GAPS"
        assert s_gaps["channel"] == 1

        # Valid SNAP
        p_snap = {"action": "SNAP", "name": "Strip2", "snap_to": "PREVIOUS_STRIP"}
        s_snap = validate_tool_input(TOOL_REORDER_VSE_STRIPS, p_snap, trusted_approval=True)
        assert s_snap["action"] == "SNAP"
        assert s_snap["snap_to"] == "PREVIOUS_STRIP"

    def test_fail_closed_security_rejections(self):
        for tool_name, params in [
            (TOOL_TRIM_VSE_STRIP, {"name": "S1", "left_handle": 5, "approved": True}),
            (TOOL_SPLIT_VSE_STRIP, {"name": "S1", "split_frame": 15, "approved": True}),
            (TOOL_REORDER_VSE_STRIPS, {"action": "CLOSE_GAPS", "channel": 1, "approved": True}),
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(tool_name, params, trusted_approval=False)

