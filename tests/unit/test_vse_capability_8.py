"""
Unit tests for VSE Capability 8: Nested Sequences.
Tests schema definitions, parameter sanitization, validation rules,
and fail-closed approval barriers for meta strips and scene strips.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_GROUP_VSE_META_STRIP,
    TOOL_CREATE_VSE_SCENE_STRIP,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability8Schemas:
    """Tests for VSE Capability 8 tool registrations and schemas."""

    def test_vse_cap8_tools_registered(self):
        registry = ToolRegistry()
        for t in (TOOL_GROUP_VSE_META_STRIP, TOOL_CREATE_VSE_SCENE_STRIP):
            assert t in TOOL_DEFINITIONS, f"Tool {t} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(t), f"Tool {t} missing from ToolRegistry"
            assert TOOL_DEFINITIONS[t]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability8Validation:
    """Tests for parameter validation on nested sequence tools."""

    def test_group_vse_meta_strip_create_validation(self):
        # Valid CREATE
        p_create = {
            "action": "CREATE",
            "name": "Intro_Comp_Meta",
            "strip_names": ["Clip_A", "Clip_B", "Text_Overlay"],
            "channel": 3,
        }
        s_create = validate_tool_input(TOOL_GROUP_VSE_META_STRIP, p_create, trusted_approval=True)
        assert s_create["action"].upper() == "CREATE"
        assert s_create["name"] == "Intro_Comp_Meta"
        assert s_create["strip_names"] == ["Clip_A", "Clip_B", "Text_Overlay"]
        assert s_create["channel"] == 3

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'|Invalid action"):
            validate_tool_input(
                TOOL_GROUP_VSE_META_STRIP,
                {"action": "COLLAPSE_ALL", "name": "M1"},
                trusted_approval=True,
            )

        # CREATE without strip_names
        with pytest.raises(ValueError, match="requires a non-empty list of 'strip_names'|strip_names"):
            validate_tool_input(
                TOOL_GROUP_VSE_META_STRIP,
                {"action": "CREATE", "name": "M1", "strip_names": []},
                trusted_approval=True,
            )

        # CREATE with invalid channel
        with pytest.raises(ValueError, match="Parameter 'channel' must be"):
            validate_tool_input(
                TOOL_GROUP_VSE_META_STRIP,
                {"action": "CREATE", "strip_names": ["A"], "channel": 0},
                trusted_approval=True,
            )

    def test_group_vse_meta_strip_ungroup_and_inspect_validation(self):
        # Valid UNGROUP
        p_ungroup = {"action": "UNGROUP", "name": "Intro_Comp_Meta"}
        s_ungroup = validate_tool_input(TOOL_GROUP_VSE_META_STRIP, p_ungroup, trusted_approval=True)
        assert s_ungroup["action"].upper() == "UNGROUP"
        assert s_ungroup["name"] == "Intro_Comp_Meta"

        # Valid INSPECT
        p_inspect = {"action": "INSPECT", "name": "Intro_Comp_Meta"}
        s_inspect = validate_tool_input(TOOL_GROUP_VSE_META_STRIP, p_inspect, trusted_approval=True)
        assert s_inspect["action"].upper() == "INSPECT"
        assert s_inspect["name"] == "Intro_Comp_Meta"

        # Missing name for UNGROUP
        with pytest.raises(ValueError, match="requires a non-empty 'name'|Missing required parameter 'name'"):
            validate_tool_input(
                TOOL_GROUP_VSE_META_STRIP,
                {"action": "UNGROUP"},
                trusted_approval=True,
            )

    def test_create_vse_scene_strip_validation(self):
        # Valid scene strip creation
        p_scene = {
            "scene_name": "Scene_Overlay",
            "name": "3D_Overlay_Track",
            "channel": 2,
            "frame_start": 1,
            "duration": 150,
            "scene_input": "CAMERA",
            "scene_camera": "Camera_3D",
            "blend_type": "ALPHA_OVER",
            "blend_alpha": 0.9,
        }
        s_scene = validate_tool_input(TOOL_CREATE_VSE_SCENE_STRIP, p_scene, trusted_approval=True)
        assert s_scene["scene_name"] == "Scene_Overlay"
        assert s_scene["name"] == "3D_Overlay_Track"
        assert s_scene["channel"] == 2
        assert s_scene["frame_start"] == 1
        assert s_scene["duration"] == 150
        assert s_scene["scene_input"].upper() == "CAMERA"
        assert s_scene["scene_camera"] == "Camera_3D"
        assert s_scene["blend_type"].upper() == "ALPHA_OVER"
        assert s_scene["blend_alpha"] == 0.9

        # Missing required parameter scene_name
        with pytest.raises(ValueError, match="Missing required parameter 'scene_name'"):
            validate_tool_input(
                TOOL_CREATE_VSE_SCENE_STRIP,
                {"channel": 1, "frame_start": 1},
                trusted_approval=True,
            )

        # Invalid channel
        with pytest.raises(ValueError, match="Parameter 'channel' must be >= 1"):
            validate_tool_input(
                TOOL_CREATE_VSE_SCENE_STRIP,
                {"scene_name": "S1", "channel": -1, "frame_start": 1},
                trusted_approval=True,
            )

        # Invalid duration
        with pytest.raises(ValueError, match="Parameter 'duration' must be >= 1"):
            validate_tool_input(
                TOOL_CREATE_VSE_SCENE_STRIP,
                {"scene_name": "S1", "channel": 1, "frame_start": 1, "duration": 0},
                trusted_approval=True,
            )

        # Invalid scene_input
        with pytest.raises(ValueError, match="Invalid value for 'scene_input'|Invalid scene_input"):
            validate_tool_input(
                TOOL_CREATE_VSE_SCENE_STRIP,
                {"scene_name": "S1", "channel": 1, "frame_start": 1, "scene_input": "VIEWPORT_CAM"},
                trusted_approval=True,
            )

    def test_fail_closed_security_rejections(self):
        for tool_name, params in [
            (
                TOOL_GROUP_VSE_META_STRIP,
                {"action": "CREATE", "strip_names": ["S1", "S2"], "approved": True},
            ),
            (
                TOOL_GROUP_VSE_META_STRIP,
                {"action": "UNGROUP", "name": "Meta1", "approved": True},
            ),
            (
                TOOL_CREATE_VSE_SCENE_STRIP,
                {"scene_name": "S1", "channel": 1, "frame_start": 1, "approved": True},
            ),
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(tool_name, params, trusted_approval=False)

