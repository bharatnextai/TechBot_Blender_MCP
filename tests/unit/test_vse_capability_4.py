"""
Unit tests for VSE Capability 4: Audio Engineering.
Tests schema definitions, parameter sanitization, validation rules,
and fail-closed approval barriers for audio configuration and sound modifiers.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_CONFIGURE_VSE_AUDIO,
    TOOL_MANAGE_VSE_SOUND_MODIFIERS,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability4Schemas:
    """Tests for VSE Capability 4 tool registrations and schemas."""

    def test_vse_cap4_tools_registered(self):
        registry = ToolRegistry()
        for t in (TOOL_CONFIGURE_VSE_AUDIO, TOOL_MANAGE_VSE_SOUND_MODIFIERS):
            assert t in TOOL_DEFINITIONS, f"Tool {t} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(t), f"Tool {t} missing from ToolRegistry"
            assert TOOL_DEFINITIONS[t]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability4Validation:
    """Tests for parameter validation on audio engineering tools."""

    def test_configure_audio_validation(self):
        # Valid UPDATE
        p_up = {
            "name": "Audio_Track_1",
            "action": "UPDATE",
            "volume": 0.85,
            "pan": -0.25,
            "pitch_correction": True,
            "show_waveform": True,
            "fade_in_duration": 15,
            "fade_out_duration": 20,
        }
        s_up = validate_tool_input(TOOL_CONFIGURE_VSE_AUDIO, p_up, trusted_approval=True)
        assert s_up["name"] == "Audio_Track_1"
        assert s_up["action"] == "UPDATE"
        assert s_up["volume"] == 0.85
        assert s_up["pan"] == -0.25
        assert s_up["pitch_correction"] is True
        assert s_up["show_waveform"] is True
        assert s_up["fade_in_duration"] == 15
        assert s_up["fade_out_duration"] == 20

        # Valid INSPECT
        p_insp = {"name": "Audio_Track_1", "action": "INSPECT"}
        s_insp = validate_tool_input(TOOL_CONFIGURE_VSE_AUDIO, p_insp, trusted_approval=True)
        assert s_insp["action"] == "INSPECT"
        assert s_insp["name"] == "Audio_Track_1"

        # Missing name
        with pytest.raises(ValueError, match="Missing required parameter 'name'"):
            validate_tool_input(TOOL_CONFIGURE_VSE_AUDIO, {"action": "UPDATE", "volume": 1.0}, trusted_approval=True)

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(TOOL_CONFIGURE_VSE_AUDIO, {"name": "Audio1", "action": "MUTE_ALL"}, trusted_approval=True)

        # Negative volume
        with pytest.raises(ValueError, match="Parameter 'volume' must be >= 0"):
            validate_tool_input(TOOL_CONFIGURE_VSE_AUDIO, {"name": "Audio1", "volume": -0.5}, trusted_approval=True)

        # Pan out of range
        with pytest.raises(ValueError, match="Parameter 'pan' must be <= 1.0"):
            validate_tool_input(TOOL_CONFIGURE_VSE_AUDIO, {"name": "Audio1", "pan": 2.5}, trusted_approval=True)

    def test_manage_sound_modifiers_validation(self):
        # Valid ADD EQUALIZER
        p_eq = {
            "name": "Meta_Master",
            "action": "ADD",
            "modifier_type": "SOUND_EQUALIZER",
            "modifier_name": "Master_EQ",
        }
        s_eq = validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, p_eq, trusted_approval=True)
        assert s_eq["action"] == "ADD"
        assert s_eq["modifier_type"] == "SOUND_EQUALIZER"
        assert s_eq["modifier_name"] == "Master_EQ"

        # Valid ADD PITCH
        p_pitch = {
            "name": "Meta_Voice",
            "action": "ADD",
            "modifier_type": "PITCH",
            "pitch_mode": "SEMITONES",
            "semitones": 4.0,
            "preserve_formant": True,
            "quality": 3,
        }
        s_pitch = validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, p_pitch, trusted_approval=True)
        assert s_pitch["modifier_type"] == "PITCH"
        assert s_pitch["semitones"] == 4.0
        assert s_pitch["preserve_formant"] is True

        # Valid ADD ECHO
        p_echo = {
            "name": "Meta_SFX",
            "action": "ADD",
            "modifier_type": "ECHO",
            "delay": 0.35,
            "feedback": 0.6,
            "mix": 0.4,
        }
        s_echo = validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, p_echo, trusted_approval=True)
        assert s_echo["modifier_type"] == "ECHO"
        assert s_echo["delay"] == 0.35
        assert s_echo["feedback"] == 0.6

        # Valid UPDATE
        p_up = {
            "name": "Meta_SFX",
            "action": "UPDATE",
            "modifier_name": "Echo_1",
            "feedback": 0.8,
            "mute": False,
        }
        s_up = validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, p_up, trusted_approval=True)
        assert s_up["action"] == "UPDATE"
        assert s_up["modifier_name"] == "Echo_1"
        assert s_up["feedback"] == 0.8

        # Valid REMOVE
        p_rem = {
            "name": "Meta_SFX",
            "action": "REMOVE",
            "modifier_name": "Echo_1",
        }
        s_rem = validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, p_rem, trusted_approval=True)
        assert s_rem["action"] == "REMOVE"
        assert s_rem["modifier_name"] == "Echo_1"

        # Valid LIST
        p_list = {"name": "Meta_SFX", "action": "LIST"}
        s_list = validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, p_list, trusted_approval=True)
        assert s_list["action"] == "LIST"
        assert s_list["name"] == "Meta_SFX"

        # Invalid action
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, {"name": "S1", "action": "PURGE"}, trusted_approval=True)

        # ADD missing modifier_type
        with pytest.raises(ValueError, match="Invalid modifier_type ''"):
            validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, {"name": "S1", "action": "ADD"}, trusted_approval=True)

        # UPDATE missing modifier_name
        with pytest.raises(ValueError, match="Action 'UPDATE' requires a non-empty 'modifier_name'"):
            validate_tool_input(TOOL_MANAGE_VSE_SOUND_MODIFIERS, {"name": "S1", "action": "UPDATE"}, trusted_approval=True)

    def test_fail_closed_security_rejections(self):
        for tool_name, params in [
            (TOOL_CONFIGURE_VSE_AUDIO, {"name": "Audio1", "action": "UPDATE", "volume": 0.5, "approved": True}),
            (TOOL_MANAGE_VSE_SOUND_MODIFIERS, {"name": "Meta1", "action": "ADD", "modifier_type": "ECHO", "approved": True}),
            (TOOL_MANAGE_VSE_SOUND_MODIFIERS, {"name": "Meta1", "action": "REMOVE", "modifier_name": "M1", "approved": True}),
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(tool_name, params, trusted_approval=False)

