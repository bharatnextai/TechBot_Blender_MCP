"""
Unit tests for VSE Capability 6: Color Grading & Strip Modifiers.
Tests schema definitions, parameter sanitization, validation rules,
and fail-closed approval barriers for color grading and strip modifier tools.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_MANAGE_VSE_STRIP_MODIFIERS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability6Schemas:
    """Tests for VSE Capability 6 tool registrations and schemas."""

    def test_vse_cap6_tools_registered(self):
        registry = ToolRegistry()
        assert TOOL_MANAGE_VSE_STRIP_MODIFIERS in TOOL_DEFINITIONS
        assert registry.has_tool(TOOL_MANAGE_VSE_STRIP_MODIFIERS)
        assert TOOL_DEFINITIONS[TOOL_MANAGE_VSE_STRIP_MODIFIERS]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability6Validation:
    """Tests for parameter validation on strip modifier management."""

    def test_manage_strip_modifiers_add_validation(self):
        # Valid ADD COLOR_BALANCE
        p_cb = {
            "name": "Graded_Clip",
            "action": "ADD",
            "modifier_type": "COLOR_BALANCE",
            "modifier_name": "Grade_Base",
            "correction_method": "LIFT_GAMMA_GAIN",
            "lift": [0.95, 0.95, 1.05],
            "gamma": [1.0, 1.0, 1.0],
            "gain": [1.1, 1.05, 0.95],
            "color_multiply": 1.2,
        }
        s_cb = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_cb, trusted_approval=True)
        assert s_cb["action"] == "ADD"
        assert s_cb["modifier_type"] == "COLOR_BALANCE"
        assert s_cb["modifier_name"] == "Grade_Base"
        assert s_cb["lift"] == [0.95, 0.95, 1.05]
        assert s_cb["color_multiply"] == 1.2

        # Valid ADD BRIGHT_CONTRAST
        p_bc = {
            "name": "Graded_Clip",
            "action": "ADD",
            "modifier_type": "BRIGHT_CONTRAST",
            "bright": 0.15,
            "contrast": 0.25,
        }
        s_bc = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_bc, trusted_approval=True)
        assert s_bc["modifier_type"] == "BRIGHT_CONTRAST"
        assert s_bc["bright"] == 0.15
        assert s_bc["contrast"] == 0.25

        # Valid ADD WHITE_BALANCE
        p_wb = {
            "name": "Graded_Clip",
            "action": "ADD",
            "modifier_type": "WHITE_BALANCE",
            "white_value": [0.9, 0.95, 1.0],
        }
        s_wb = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_wb, trusted_approval=True)
        assert s_wb["modifier_type"] == "WHITE_BALANCE"
        assert s_wb["white_value"] == [0.9, 0.95, 1.0]

        # Valid ADD TONEMAP
        p_tm = {
            "name": "Graded_Clip",
            "action": "ADD",
            "modifier_type": "TONEMAP",
            "tonemap_type": "RD_PHOTORECEPTOR",
            "tonemap_key": 0.2,
            "tonemap_intensity": 0.05,
        }
        s_tm = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_tm, trusted_approval=True)
        assert s_tm["modifier_type"] == "TONEMAP"
        assert s_tm["tonemap_type"].upper() == "RD_PHOTORECEPTOR"

        # Valid ADD MASK
        p_mask = {
            "name": "Graded_Clip",
            "action": "ADD",
            "modifier_type": "MASK",
            "input_mask_type": "STRIP",
            "input_mask_strip": "Matte_Strip",
        }
        s_mask = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_mask, trusted_approval=True)
        assert s_mask["modifier_type"] == "MASK"
        assert s_mask["input_mask_strip"] == "Matte_Strip"

    def test_manage_strip_modifiers_update_remove_list_validation(self):
        # Valid UPDATE
        p_up = {
            "name": "Graded_Clip",
            "action": "UPDATE",
            "modifier_name": "Grade_Base",
            "bright": 0.2,
            "mute": True,
        }
        s_up = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_up, trusted_approval=True)
        assert s_up["action"] == "UPDATE"
        assert s_up["modifier_name"] == "Grade_Base"
        assert s_up["mute"] is True

        # Valid REMOVE
        p_rem = {
            "name": "Graded_Clip",
            "action": "REMOVE",
            "modifier_name": "Grade_Base",
        }
        s_rem = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_rem, trusted_approval=True)
        assert s_rem["action"] == "REMOVE"
        assert s_rem["modifier_name"] == "Grade_Base"

        # Valid LIST
        p_list = {"name": "Graded_Clip", "action": "LIST"}
        s_list = validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, p_list, trusted_approval=True)
        assert s_list["action"] == "LIST"
        assert s_list["name"] == "Graded_Clip"

        # Missing name
        with pytest.raises(ValueError, match="Missing required parameter 'name'"):
            validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, {"action": "LIST"}, trusted_approval=True)

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, {"name": "S1", "action": "CLEAR_ALL"}, trusted_approval=True)

        # ADD missing modifier_type
        with pytest.raises(ValueError, match="Invalid modifier_type ''"):
            validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, {"name": "S1", "action": "ADD"}, trusted_approval=True)

        # UPDATE missing modifier_name
        with pytest.raises(ValueError, match="Action 'UPDATE' requires a non-empty 'modifier_name'"):
            validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, {"name": "S1", "action": "UPDATE"}, trusted_approval=True)

    def test_fail_closed_security_rejections(self):
        for params in [
            {"name": "S1", "action": "ADD", "modifier_type": "COLOR_BALANCE", "approved": True},
            {"name": "S1", "action": "UPDATE", "modifier_name": "M1", "bright": 0.1, "approved": True},
            {"name": "S1", "action": "REMOVE", "modifier_name": "M1", "approved": True},
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(TOOL_MANAGE_VSE_STRIP_MODIFIERS, params, trusted_approval=False)
