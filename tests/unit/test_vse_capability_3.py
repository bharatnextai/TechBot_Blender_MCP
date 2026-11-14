"""
Unit tests for VSE Capability 3: Transitions & Visual Effects.
Tests schema definitions, parameter sanitization, validation rules,
and fail-closed approval barriers for transitions and effect strips.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_CREATE_VSE_TRANSITION,
    TOOL_CONFIGURE_VSE_EFFECT,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability3Schemas:
    """Tests for VSE Capability 3 tool registrations and schemas."""

    def test_vse_cap3_tools_registered(self):
        registry = ToolRegistry()
        for t in (TOOL_CREATE_VSE_TRANSITION, TOOL_CONFIGURE_VSE_EFFECT):
            assert t in TOOL_DEFINITIONS, f"Tool {t} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(t), f"Tool {t} missing from ToolRegistry"
            assert TOOL_DEFINITIONS[t]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability3Validation:
    """Tests for parameter validation on transition and effect tools."""

    def test_create_transition_validation(self):
        # Valid cross
        p_cross = {"transition_type": "CROSS", "input1": "StripA", "input2": "StripB"}
        s_cross = validate_tool_input(TOOL_CREATE_VSE_TRANSITION, p_cross, trusted_approval=True)
        assert s_cross["transition_type"] == "CROSS"
        assert s_cross["input1"] == "StripA"
        assert s_cross["input2"] == "StripB"

        # Valid wipe
        p_wipe = {
            "transition_type": "WIPE",
            "input1": "StripA",
            "input2": "StripB",
            "wipe_type": "IRIS",
            "direction": "OUT",
            "blur_width": 0.25,
            "angle": 1.57,
            "duration": 30,
            "channel": 3,
        }
        s_wipe = validate_tool_input(TOOL_CREATE_VSE_TRANSITION, p_wipe, trusted_approval=True)
        assert s_wipe["transition_type"] == "WIPE"
        assert s_wipe["wipe_type"] == "IRIS"
        assert s_wipe["direction"] == "OUT"
        assert s_wipe["blur_width"] == 0.25
        assert s_wipe["duration"] == 30
        assert s_wipe["channel"] == 3

        # Invalid transition type
        with pytest.raises(ValueError, match="Invalid value for 'transition_type'"):
            validate_tool_input(
                TOOL_CREATE_VSE_TRANSITION,
                {"transition_type": "DISSOLVE_3D", "input1": "A", "input2": "B"},
                trusted_approval=True,
            )

        # Identical inputs
        with pytest.raises(ValueError, match="Transition requires distinct 'input1' and 'input2' strips"):
            validate_tool_input(
                TOOL_CREATE_VSE_TRANSITION,
                {"transition_type": "CROSS", "input1": "StripA", "input2": "StripA"},
                trusted_approval=True,
            )

        # Missing input1
        with pytest.raises(ValueError, match="Missing required parameter 'input1'"):
            validate_tool_input(
                TOOL_CREATE_VSE_TRANSITION,
                {"transition_type": "CROSS", "input2": "StripB"},
                trusted_approval=True,
            )

        # Invalid wipe_type
        with pytest.raises(ValueError, match="Invalid value for 'wipe_type'"):
            validate_tool_input(
                TOOL_CREATE_VSE_TRANSITION,
                {"transition_type": "WIPE", "input1": "A", "input2": "B", "wipe_type": "STAR"},
                trusted_approval=True,
            )

        # Invalid direction
        with pytest.raises(ValueError, match="Invalid value for 'direction'"):
            validate_tool_input(
                TOOL_CREATE_VSE_TRANSITION,
                {"transition_type": "WIPE", "input1": "A", "input2": "B", "direction": "SIDEWAYS"},
                trusted_approval=True,
            )

        # Invalid channel
        with pytest.raises(ValueError, match="Parameter 'channel' must be >= 1"):
            validate_tool_input(
                TOOL_CREATE_VSE_TRANSITION,
                {"transition_type": "CROSS", "input1": "A", "input2": "B", "channel": 0},
                trusted_approval=True,
            )

        # Invalid duration
        with pytest.raises(ValueError, match="Parameter 'duration' must be >= 1"):
            validate_tool_input(
                TOOL_CREATE_VSE_TRANSITION,
                {"transition_type": "CROSS", "input1": "A", "input2": "B", "duration": -5},
                trusted_approval=True,
            )

    def test_configure_effect_validation(self):
        # Valid CREATE GAUSSIAN_BLUR
        p_blur = {
            "action": "CREATE",
            "effect_type": "GAUSSIAN_BLUR",
            "input_strip": "Video1",
            "size_x": 10.0,
            "size_y": 15.0,
        }
        s_blur = validate_tool_input(TOOL_CONFIGURE_VSE_EFFECT, p_blur, trusted_approval=True)
        assert s_blur["action"] == "CREATE"
        assert s_blur["effect_type"] == "GAUSSIAN_BLUR"
        assert s_blur["input_strip"] == "Video1"
        assert s_blur["size_x"] == 10.0
        assert s_blur["size_y"] == 15.0

        # Valid CREATE GLOW
        p_glow = {
            "action": "CREATE",
            "effect_type": "GLOW",
            "input_strip": "Video1",
            "threshold": 0.8,
            "boost_factor": 1.5,
            "blur_radius": 5.0,
            "quality": 3,
        }
        s_glow = validate_tool_input(TOOL_CONFIGURE_VSE_EFFECT, p_glow, trusted_approval=True)
        assert s_glow["effect_type"] == "GLOW"
        assert s_glow["threshold"] == 0.8
        assert s_glow["quality"] == 3

        # Valid CREATE ADJUSTMENT (does not require input_strip)
        p_adj = {"action": "CREATE", "effect_type": "ADJUSTMENT", "channel": 3, "frame_start": 1, "duration": 60}
        s_adj = validate_tool_input(TOOL_CONFIGURE_VSE_EFFECT, p_adj, trusted_approval=True)
        assert s_adj["effect_type"] == "ADJUSTMENT"
        assert s_adj["channel"] == 3

        # CREATE GAUSSIAN_BLUR missing input_strip
        with pytest.raises(ValueError, match="Effect type 'GAUSSIAN_BLUR' requires 'input_strip'"):
            validate_tool_input(
                TOOL_CONFIGURE_VSE_EFFECT,
                {"action": "CREATE", "effect_type": "GAUSSIAN_BLUR"},
                trusted_approval=True,
            )

        # Valid UPDATE
        p_up = {"action": "UPDATE", "name": "BlurStrip", "size_x": 20.0, "size_y": 20.0}
        s_up = validate_tool_input(TOOL_CONFIGURE_VSE_EFFECT, p_up, trusted_approval=True)
        assert s_up["action"] == "UPDATE"
        assert s_up["name"] == "BlurStrip"
        assert s_up["size_x"] == 20.0

        # UPDATE missing name
        with pytest.raises(ValueError, match="Action 'UPDATE' requires a non-empty 'name'"):
            validate_tool_input(
                TOOL_CONFIGURE_VSE_EFFECT,
                {"action": "UPDATE", "size_x": 10.0},
                trusted_approval=True,
            )

        # Valid INSPECT
        p_insp = {"action": "INSPECT", "name": "BlurStrip"}
        s_insp = validate_tool_input(TOOL_CONFIGURE_VSE_EFFECT, p_insp, trusted_approval=True)
        assert s_insp["action"] == "INSPECT"
        assert s_insp["name"] == "BlurStrip"

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(
                TOOL_CONFIGURE_VSE_EFFECT,
                {"action": "DESTROY", "name": "BlurStrip"},
                trusted_approval=True,
            )

    def test_fail_closed_security_rejections(self):
        for tool_name, params in [
            (TOOL_CREATE_VSE_TRANSITION, {"transition_type": "CROSS", "input1": "A", "input2": "B", "approved": True}),
            (TOOL_CONFIGURE_VSE_EFFECT, {"action": "CREATE", "effect_type": "ADJUSTMENT", "approved": True}),
            (TOOL_CONFIGURE_VSE_EFFECT, {"action": "UPDATE", "name": "S1", "blend_alpha": 0.5, "approved": True}),
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(tool_name, params, trusted_approval=False)
