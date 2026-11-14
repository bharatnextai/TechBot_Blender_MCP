"""
Unit tests for VSE Capability 9: Sequencer Rendering & Audio Mixdown.
Tests schema definitions, parameter sanitization, validation rules,
path traversal defenses, and fail-closed approval barriers for rendering and mixdown.
"""

import pytest

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_RENDER_VSE_SEQUENCE,
    TOOL_MIXDOWN_VSE_AUDIO,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry


class TestVSECapability9Schemas:
    """Tests for VSE Capability 9 tool registrations and schemas."""

    def test_vse_cap9_tools_registered(self):
        registry = ToolRegistry()
        for t in (TOOL_RENDER_VSE_SEQUENCE, TOOL_MIXDOWN_VSE_AUDIO):
            assert t in TOOL_DEFINITIONS, f"Tool {t} missing from TOOL_DEFINITIONS"
            assert registry.has_tool(t), f"Tool {t} missing from ToolRegistry"
            assert TOOL_DEFINITIONS[t]["permission_tier"] == PERMISSION_SCENE_MUTATION


class TestVSECapability9Validation:
    """Tests for parameter validation on rendering and mixdown tools."""

    def test_render_vse_sequence_validation(self):
        # Valid MP4 render
        p_render = {
            "output_path": "d:/renders/final_cut.mp4",
            "frame_start": 1,
            "frame_end": 120,
            "format": "MPEG4",
            "video_codec": "H264",
            "audio_codec": "AAC",
            "resolution_x": 1920,
            "resolution_y": 1080,
            "resolution_percentage": 100,
            "fps": 30.0,
        }
        s_render = validate_tool_input(TOOL_RENDER_VSE_SEQUENCE, p_render, trusted_approval=True)
        assert s_render["output_path"] == "d:/renders/final_cut.mp4"
        assert s_render["frame_start"] == 1
        assert s_render["frame_end"] == 120
        assert s_render["format"] == "MPEG4"
        assert s_render["video_codec"] == "H264"
        assert s_render["audio_codec"] == "AAC"
        assert s_render["resolution_x"] == 1920

        # Valid ProRes MOV render
        p_prores = {
            "output_path": "d:/renders/master.mov",
            "format": "QUICKTIME",
            "video_codec": "PRORES",
            "audio_codec": "PCM",
        }
        s_prores = validate_tool_input(TOOL_RENDER_VSE_SEQUENCE, p_prores, trusted_approval=True)
        assert s_prores["format"] == "QUICKTIME"
        assert s_prores["video_codec"] == "PRORES"
        assert s_prores["audio_codec"] == "PCM"

        # Missing required parameter output_path
        with pytest.raises(ValueError, match="Missing required parameter 'output_path'"):
            validate_tool_input(TOOL_RENDER_VSE_SEQUENCE, {"frame_start": 1}, trusted_approval=True)

        # Path traversal forbidden
        with pytest.raises(ValueError, match="Directory traversal|forbidden"):
            validate_tool_input(TOOL_RENDER_VSE_SEQUENCE, {"output_path": "../evil.mp4"}, trusted_approval=True)

        # Invalid extension
        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_tool_input(TOOL_RENDER_VSE_SEQUENCE, {"output_path": "d:/renders/output.exe"}, trusted_approval=True)

        # frame_start > frame_end
        with pytest.raises(ValueError, match="frame_start .* must be <= frame_end"):
            validate_tool_input(
                TOOL_RENDER_VSE_SEQUENCE,
                {"output_path": "d:/renders/cut.mp4", "frame_start": 100, "frame_end": 50},
                trusted_approval=True,
            )

        # Invalid format
        with pytest.raises(ValueError, match="Invalid value for 'format'|Invalid format"):
            validate_tool_input(
                TOOL_RENDER_VSE_SEQUENCE,
                {"output_path": "d:/renders/cut.mp4", "format": "REALMEDIA"},
                trusted_approval=True,
            )

    def test_mixdown_vse_audio_validation(self):
        # Valid WAV mixdown
        p_mix = {
            "output_path": "d:/audio/mixdown.wav",
            "container": "WAV",
            "codec": "PCM",
            "format": "S16",
            "channels": "STEREO",
            "sample_rate": 48000,
        }
        s_mix = validate_tool_input(TOOL_MIXDOWN_VSE_AUDIO, p_mix, trusted_approval=True)
        assert s_mix["output_path"] == "d:/audio/mixdown.wav"
        assert s_mix["container"] == "WAV"
        assert s_mix["codec"] == "PCM"
        assert s_mix["format"] == "S16"
        assert s_mix["channels"] == "STEREO"
        assert s_mix["sample_rate"] == 48000

        # Valid FLAC mixdown
        p_flac = {
            "output_path": "d:/audio/soundtrack.flac",
            "container": "FLAC",
            "codec": "FLAC",
            "format": "S24",
        }
        s_flac = validate_tool_input(TOOL_MIXDOWN_VSE_AUDIO, p_flac, trusted_approval=True)
        assert s_flac["container"] == "FLAC"
        assert s_flac["codec"] == "FLAC"
        assert s_flac["format"] == "S24"

        # Missing required parameter output_path
        with pytest.raises(ValueError, match="Missing required parameter 'output_path'"):
            validate_tool_input(TOOL_MIXDOWN_VSE_AUDIO, {"container": "WAV"}, trusted_approval=True)

        # Path traversal forbidden
        with pytest.raises(ValueError, match="Directory traversal|forbidden"):
            validate_tool_input(TOOL_MIXDOWN_VSE_AUDIO, {"output_path": "../evil.wav"}, trusted_approval=True)

        # Invalid audio extension
        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_tool_input(TOOL_MIXDOWN_VSE_AUDIO, {"output_path": "d:/audio/sound.bmp"}, trusted_approval=True)

        # Invalid container
        with pytest.raises(ValueError, match="Invalid value for 'container'|Invalid container"):
            validate_tool_input(
                TOOL_MIXDOWN_VSE_AUDIO,
                {"output_path": "d:/audio/sound.wav", "container": "MIDI"},
                trusted_approval=True,
            )

    def test_fail_closed_security_rejections(self):
        for tool_name, params in [
            (
                TOOL_RENDER_VSE_SEQUENCE,
                {"output_path": "d:/renders/unauth.mp4", "approved": True},
            ),
            (
                TOOL_MIXDOWN_VSE_AUDIO,
                {"output_path": "d:/audio/unauth.wav", "approved": True},
            ),
        ]:
            with pytest.raises(PermissionError, match="Approval denied"):
                validate_tool_input(tool_name, params, trusted_approval=False)

