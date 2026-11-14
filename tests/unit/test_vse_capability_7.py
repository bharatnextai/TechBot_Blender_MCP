"""
Unit tests for VSE Capability 7: Titles & Subtitles.
Tests schema definitions, parameter sanitization, validation rules,
and fail-closed approval barriers for text strips, typography, and subtitle overlays.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_CREATE_VSE_TEXT_STRIP,
    TOOL_CONFIGURE_VSE_TEXT_STYLE,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability7Schemas:
    """Tests for VSE Capability 7 tool registrations and schemas."""

    def test_vse_cap7_tools_registered(self):
        registry = ToolRegistry()
        for t in (TOOL_CREATE_VSE_TEXT_STRIP, TOOL_CONFIGURE_VSE_TEXT_STYLE):
            assert t in TOOL_DEFINITIONS, f"Tool {t} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(t), f"Tool {t} missing from ToolRegistry"
            assert TOOL_DEFINITIONS[t]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability7Validation:
    """Tests for parameter validation on title and subtitle tools."""

    def test_create_text_strip_validation(self):
        # Valid text strip
        p_text = {
            "text": "Chapter 1: The Beginning",
            "channel": 3,
            "frame_start": 1,
            "duration": 75,
            "name": "Title_Intro",
            "font_size": 48.0,
            "color": [1.0, 0.9, 0.8, 1.0],
            "location": [0.5, 0.2],
            "alignment_x": "CENTER",
            "anchor_x": "CENTER",
            "anchor_y": "BOTTOM",
            "use_bold": True,
            "use_shadow": True,
            "shadow_color": [0.0, 0.0, 0.0, 0.75],
            "shadow_blur": 0.05,
            "use_box": True,
            "box_color": [0.1, 0.1, 0.1, 0.6],
            "box_margin": 0.02,
        }
        s_text = validate_tool_input(TOOL_CREATE_VSE_TEXT_STRIP, p_text, trusted_approval=True)
        assert s_text["text"] == "Chapter 1: The Beginning"
        assert s_text["channel"] == 3
        assert s_text["frame_start"] == 1
        assert s_text["duration"] == 75
        assert s_text["font_size"] == 48.0
        assert s_text["color"] == [1.0, 0.9, 0.8, 1.0]
        assert s_text["location"] == [0.5, 0.2]
        assert s_text["use_bold"] is True
        assert s_text["use_shadow"] is True
        assert s_text["use_box"] is True

        # Missing required parameter
        with pytest.raises(ValueError, match="Missing required parameter 'text'"):
            validate_tool_input(
                TOOL_CREATE_VSE_TEXT_STRIP,
                {"channel": 1, "frame_start": 1, "duration": 50},
                trusted_approval=True,
            )

        # Empty text
        with pytest.raises(ValueError, match="Parameter 'text' cannot be empty"):
            validate_tool_input(
                TOOL_CREATE_VSE_TEXT_STRIP,
                {"text": "   ", "channel": 1, "frame_start": 1, "duration": 50},
                trusted_approval=True,
            )

        # Invalid channel
        with pytest.raises(ValueError, match="Parameter 'channel' must be >= 1"):
            validate_tool_input(
                TOOL_CREATE_VSE_TEXT_STRIP,
                {"text": "Sub", "channel": 0, "frame_start": 1, "duration": 50},
                trusted_approval=True,
            )

        # Invalid duration
        with pytest.raises(ValueError, match="Parameter 'duration' must be >= 1"):
            validate_tool_input(
                TOOL_CREATE_VSE_TEXT_STRIP,
                {"text": "Sub", "channel": 1, "frame_start": 1, "duration": 0},
                trusted_approval=True,
            )

    def test_configure_text_style_validation(self):
        # Valid UPDATE
        p_up = {
            "name": "Title_Intro",
            "action": "UPDATE",
            "text": "Chapter 1: The Awakening",
            "font_size": 52.0,
            "use_outline": True,
            "outline_color": [0.0, 0.0, 0.0, 0.9],
            "outline_width": 0.03,
        }
        s_up = validate_tool_input(TOOL_CONFIGURE_VSE_TEXT_STYLE, p_up, trusted_approval=True)
        assert s_up["name"] == "Title_Intro"
        assert s_up["action"] == "UPDATE"
        assert s_up["text"] == "Chapter 1: The Awakening"
        assert s_up["font_size"] == 52.0
        assert s_up["use_outline"] is True

        # Valid INSPECT
        p_insp = {"name": "Title_Intro", "action": "INSPECT"}
        s_insp = validate_tool_input(TOOL_CONFIGURE_VSE_TEXT_STYLE, p_insp, trusted_approval=True)
        assert s_insp["action"] == "INSPECT"
        assert s_insp["name"] == "Title_Intro"

        # Missing name
        with pytest.raises(ValueError, match="Missing required parameter 'name'"):
            validate_tool_input(TOOL_CONFIGURE_VSE_TEXT_STYLE, {"action": "UPDATE", "font_size": 30.0}, trusted_approval=True)

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(TOOL_CONFIGURE_VSE_TEXT_STYLE, {"name": "S1", "action": "RESET_ALL"}, trusted_approval=True)

    def test_fail_closed_security_rejections(self):
        for tool_name, params in [
            (TOOL_CREATE_VSE_TEXT_STRIP, {"text": "Sub", "channel": 1, "frame_start": 1, "duration": 30, "approved": True}),
            (TOOL_CONFIGURE_VSE_TEXT_STYLE, {"name": "S1", "action": "UPDATE", "font_size": 60.0, "approved": True}),
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(tool_name, params, trusted_approval=False)

