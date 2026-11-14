"""
Unit tests for VSE Capability 5: Transforms & Keyframing.
Tests schema definitions, parameter sanitization, validation rules,
and fail-closed approval barriers for 2D transforms, pixel cropping, and timeline keyframing.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_TRANSFORM_VSE_STRIP,
    TOOL_CROP_VSE_STRIP,
    TOOL_ANIMATE_VSE_STRIP,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability5Schemas:
    """Tests for VSE Capability 5 tool registrations and schemas."""

    def test_vse_cap5_tools_registered(self):
        registry = ToolRegistry()
        for t in (TOOL_TRANSFORM_VSE_STRIP, TOOL_CROP_VSE_STRIP, TOOL_ANIMATE_VSE_STRIP):
            assert t in TOOL_DEFINITIONS, f"Tool {t} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(t), f"Tool {t} missing from ToolRegistry"
            assert TOOL_DEFINITIONS[t]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability5Validation:
    """Tests for parameter validation on transform, crop, and animation tools."""

    def test_transform_strip_validation(self):
        # Valid UPDATE
        p_up = {
            "name": "Graphic_Overlay",
            "action": "UPDATE",
            "offset_x": 120.0,
            "offset_y": -45.0,
            "scale_x": 1.25,
            "scale_y": 1.25,
            "rotation": 0.785,
            "origin": [0.5, 0.5],
            "filter": "BILINEAR",
        }
        s_up = validate_tool_input(TOOL_TRANSFORM_VSE_STRIP, p_up, trusted_approval=True)
        assert s_up["name"] == "Graphic_Overlay"
        assert s_up["action"] == "UPDATE"
        assert s_up["offset_x"] == 120.0
        assert s_up["offset_y"] == -45.0
        assert s_up["scale_x"] == 1.25
        assert s_up["rotation"] == 0.785
        assert s_up["origin"] == [0.5, 0.5]
        assert s_up["filter"] == "BILINEAR"

        # Valid INSPECT
        p_insp = {"name": "Graphic_Overlay", "action": "INSPECT"}
        s_insp = validate_tool_input(TOOL_TRANSFORM_VSE_STRIP, p_insp, trusted_approval=True)
        assert s_insp["action"] == "INSPECT"
        assert s_insp["name"] == "Graphic_Overlay"

        # Missing name
        with pytest.raises(ValueError, match="Missing required parameter 'name'"):
            validate_tool_input(TOOL_TRANSFORM_VSE_STRIP, {"action": "UPDATE", "offset_x": 10.0}, trusted_approval=True)

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(TOOL_TRANSFORM_VSE_STRIP, {"name": "S1", "action": "WARP"}, trusted_approval=True)

        # Invalid filter
        with pytest.raises(ValueError, match="Invalid value for 'filter'"):
            validate_tool_input(TOOL_TRANSFORM_VSE_STRIP, {"name": "S1", "filter": "CUBIC"}, trusted_approval=True)

    def test_crop_strip_validation(self):
        # Valid UPDATE
        p_up = {
            "name": "Video_Track",
            "action": "UPDATE",
            "min_x": 50,
            "max_x": 50,
            "min_y": 20,
            "max_y": 20,
        }
        s_up = validate_tool_input(TOOL_CROP_VSE_STRIP, p_up, trusted_approval=True)
        assert s_up["name"] == "Video_Track"
        assert s_up["action"] == "UPDATE"
        assert s_up["min_x"] == 50
        assert s_up["max_x"] == 50
        assert s_up["min_y"] == 20
        assert s_up["max_y"] == 20

        # Valid INSPECT
        p_insp = {"name": "Video_Track", "action": "INSPECT"}
        s_insp = validate_tool_input(TOOL_CROP_VSE_STRIP, p_insp, trusted_approval=True)
        assert s_insp["action"] == "INSPECT"
        assert s_insp["name"] == "Video_Track"

        # Negative crop margin
        with pytest.raises(ValueError, match="Parameter 'min_x' must be >= 0"):
            validate_tool_input(TOOL_CROP_VSE_STRIP, {"name": "Video_Track", "min_x": -10}, trusted_approval=True)

        # Missing name
        with pytest.raises(ValueError, match="Missing required parameter 'name'"):
            validate_tool_input(TOOL_CROP_VSE_STRIP, {"action": "UPDATE", "min_y": 5}, trusted_approval=True)

    def test_animate_strip_validation(self):
        # Valid INSERT_KEYFRAME
        p_ins = {
            "name": "Title_Card",
            "action": "INSERT_KEYFRAME",
            "property": "OFFSET_X",
            "frame": 24,
            "value": 150.0,
        }
        s_ins = validate_tool_input(TOOL_ANIMATE_VSE_STRIP, p_ins, trusted_approval=True)
        assert s_ins["name"] == "Title_Card"
        assert s_ins["action"] == "INSERT_KEYFRAME"
        assert s_ins["property"] == "OFFSET_X"
        assert s_ins["frame"] == 24
        assert s_ins["value"] == 150.0

        # Valid DELETE_KEYFRAME
        p_del = {
            "name": "Title_Card",
            "action": "DELETE_KEYFRAME",
            "property": "OFFSET_X",
            "frame": 24,
        }
        s_del = validate_tool_input(TOOL_ANIMATE_VSE_STRIP, p_del, trusted_approval=True)
        assert s_del["action"] == "DELETE_KEYFRAME"
        assert s_del["frame"] == 24

        # Missing frame
        with pytest.raises(ValueError, match="Missing required parameter 'frame'"):
            validate_tool_input(
                TOOL_ANIMATE_VSE_STRIP,
                {"name": "S1", "action": "INSERT_KEYFRAME", "property": "SCALE_X"},
                trusted_approval=True,
            )

        # Invalid property
        with pytest.raises(ValueError, match="Invalid value for 'property'"):
            validate_tool_input(
                TOOL_ANIMATE_VSE_STRIP,
                {"name": "S1", "action": "INSERT_KEYFRAME", "property": "MAGIC_ZOOM", "frame": 10},
                trusted_approval=True,
            )

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(
                TOOL_ANIMATE_VSE_STRIP,
                {"name": "S1", "action": "BAKE_CURVES", "property": "ROTATION", "frame": 10},
                trusted_approval=True,
            )

    def test_fail_closed_security_rejections(self):
        for tool_name, params in [
            (TOOL_TRANSFORM_VSE_STRIP, {"name": "S1", "action": "UPDATE", "offset_x": 10.0, "approved": True}),
            (TOOL_CROP_VSE_STRIP, {"name": "S1", "action": "UPDATE", "min_x": 5, "approved": True}),
            (TOOL_ANIMATE_VSE_STRIP, {"name": "S1", "action": "INSERT_KEYFRAME", "property": "SCALE_X", "frame": 1, "approved": True}),
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(tool_name, params, trusted_approval=False)

