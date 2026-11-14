"""
Unit tests for VSE Capability 1: Timeline & Strip Lifecycle Foundation.
Tests schema definitions, parameter sanitization, path traversal defenses,
fail-closed approval barriers, and handler execution.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_INSPECT_VSE_TIMELINE,
    TOOL_CREATE_VSE_STRIP,
    TOOL_MODIFY_VSE_STRIP,
    TOOL_DELETE_VSE_STRIP,
    TOOL_MANAGE_TIMELINE_MARKERS,
    PERMISSION_READ_ONLY,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability1Schemas:
    """Tests for VSE tool registrations and schema contracts."""

    def test_vse_tool_definitions_present(self):
        registry = ToolRegistry()
        for tool_name in (
            TOOL_INSPECT_VSE_TIMELINE,
            TOOL_CREATE_VSE_STRIP,
            TOOL_MODIFY_VSE_STRIP,
            TOOL_DELETE_VSE_STRIP,
            TOOL_MANAGE_TIMELINE_MARKERS,
        ):
            assert tool_name in TOOL_DEFINITIONS, f"Tool {tool_name} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(tool_name), f"Tool {tool_name} missing from ToolRegistry"

    def test_permission_tiers(self):
        assert TOOL_DEFINITIONS[TOOL_INSPECT_VSE_TIMELINE]["permission_tier"] == PERMISSION_READ_ONLY
        for mutation_tool in (
            TOOL_CREATE_VSE_STRIP,
            TOOL_MODIFY_VSE_STRIP,
            TOOL_DELETE_VSE_STRIP,
            TOOL_MANAGE_TIMELINE_MARKERS,
        ):
            assert TOOL_DEFINITIONS[mutation_tool]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSEParameterValidation:
    """Tests for parameter validation and security barriers."""

    def test_create_strip_valid_color(self):
        params = {
            "strip_type": "COLOR",
            "channel": 1,
            "frame_start": 1,
            "duration": 60,
            "color": [0.1, 0.5, 0.9],
        }
        sanitized = validate_tool_input(TOOL_CREATE_VSE_STRIP, params, trusted_approval=True)
        assert sanitized["strip_type"] == "COLOR"
        assert sanitized["channel"] == 1
        assert sanitized["frame_start"] == 1
        assert sanitized["duration"] == 60
        assert sanitized["color"] == [0.1, 0.5, 0.9]

    def test_create_strip_invalid_type(self):
        params = {"strip_type": "HOLOGRAM", "channel": 1, "frame_start": 1}
        with pytest.raises(ValueError, match="Invalid value for 'strip_type'"):
            validate_tool_input(TOOL_CREATE_VSE_STRIP, params, trusted_approval=True)

    def test_create_strip_invalid_channel(self):
        params = {"strip_type": "COLOR", "channel": 0, "frame_start": 1}
        with pytest.raises(ValueError, match="Parameter 'channel' must be >= 1"):
            validate_tool_input(TOOL_CREATE_VSE_STRIP, params, trusted_approval=True)

        params_high = {"strip_type": "COLOR", "channel": 129, "frame_start": 1}
        with pytest.raises(ValueError, match="Parameter 'channel' must be <= 128"):
            validate_tool_input(TOOL_CREATE_VSE_STRIP, params_high, trusted_approval=True)

    def test_create_media_strip_path_traversal_defense(self):
        params = {
            "strip_type": "MOVIE",
            "channel": 1,
            "frame_start": 1,
            "filepath": "C:/videos/../../secret.mp4",
        }
        with pytest.raises(ValueError, match="Path traversal sequences"):
            validate_tool_input(TOOL_CREATE_VSE_STRIP, params, trusted_approval=True)

    def test_create_media_strip_invalid_extension(self):
        params = {
            "strip_type": "SOUND",
            "channel": 1,
            "frame_start": 1,
            "filepath": "C:/audio/test.exe",
        }
        with pytest.raises(ValueError, match="File extension for SOUND strip"):
            validate_tool_input(TOOL_CREATE_VSE_STRIP, params, trusted_approval=True)

    def test_create_strip_invalid_color(self):
        params = {
            "strip_type": "COLOR",
            "channel": 1,
            "frame_start": 1,
            "color": [1.5, 0.0, 0.0],
        }
        with pytest.raises(ValueError, match="Item 0 in 'color' must be <= 1.0"):
            validate_tool_input(TOOL_CREATE_VSE_STRIP, params, trusted_approval=True)

    def test_manage_markers_validation(self):
        # Valid add
        p_add = {"action": "add", "name": "Marker1", "frame": 24}
        s_add = validate_tool_input(TOOL_MANAGE_TIMELINE_MARKERS, p_add, trusted_approval=True)
        assert s_add["action"] == "add"
        assert s_add["name"] == "Marker1"
        assert s_add["frame"] == 24

        # Missing frame on add
        with pytest.raises(ValueError, match="Parameter 'frame' must be an integer frame number"):
            validate_tool_input(TOOL_MANAGE_TIMELINE_MARKERS, {"action": "add", "name": "Marker2"}, trusted_approval=True)

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(TOOL_MANAGE_TIMELINE_MARKERS, {"action": "jump"}, trusted_approval=True)

    def test_fail_closed_untrusted_approval_rejection(self):
        params = {
            "strip_type": "COLOR",
            "channel": 1,
            "frame_start": 1,
            "approved": True,  # Untrusted client-injected flag
        }
        with pytest.raises(PermissionError, match="Approval denied"):
            validate_tool_input(TOOL_CREATE_VSE_STRIP, params, trusted_approval=False)


class TestVSEMockHandlers:
    """Tests handler logic with mocked bpy objects."""

    def test_inspect_vse_timeline_no_se(self):
        from blender_addon.universal_mcp.bridge.handlers import handle_inspect_vse_timeline
        mock_bpy = MagicMock()
        mock_bpy.context.scene.sequence_editor = None
        mock_bpy.context.scene.frame_current = 1
        mock_bpy.context.scene.frame_start = 1
        mock_bpy.context.scene.frame_end = 250
        mock_bpy.context.scene.render.fps = 24
        mock_bpy.context.scene.render.fps_base = 1.0
        mock_bpy.context.scene.timeline_markers = []

        res = handle_inspect_vse_timeline(mock_bpy, {})
        assert res["has_sequence_editor"] is False
        assert res["total_strips"] == 0
        assert res["strips"] == []
        assert res["markers"] == []
        assert res["fps"] == 24.0
