"""
Unit tests for Reference Image Loading and Viewport Visual Inspection (v0.1.50).
Verifies:
1. Schema contracts for load_reference_image and capture_viewport (view property).
2. Validation rules: required image_path, display_mode enum, view_axis enum, bounds.
3. Fail-closed defense against untrusted approval flags and unapproved execution.
4. Modeling agent capability registration and task validation.
"""

import pytest
from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_LOAD_REFERENCE_IMAGE,
    TOOL_CAPTURE_VIEWPORT,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
    validate_tool_input,
)
from mcp_service.agents.modeling import (
    SUPPORTED_MODELING_TOOLS,
    CAPABILITY_MODELING_OBJECT_OPS,
    create_modeling_manifest,
    ModelingAgent,
)


class TestReferenceImageSchemas:
    """Verify tool definitions and schema specifications."""

    def test_load_reference_image_registered(self):
        assert TOOL_LOAD_REFERENCE_IMAGE in TOOL_DEFINITIONS
        tool_spec = TOOL_DEFINITIONS[TOOL_LOAD_REFERENCE_IMAGE]
        assert tool_spec["name"] == "load_reference_image"
        assert tool_spec["permission_tier"] == PERMISSION_SCENE_MUTATION

        schema = tool_spec["input_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert "image_path" in schema["required"]

        props = schema["properties"]
        assert "image_path" in props
        assert "display_mode" in props
        assert props["display_mode"]["enum"] == ["EMPTY", "PLANE"]
        assert "view_axis" in props
        assert props["view_axis"]["enum"] == ["FRONT", "SIDE", "TOP", "USER"]
        assert "size" in props
        assert props["size"]["minimum"] == 0.01
        assert "opacity" in props
        assert props["opacity"]["minimum"] == 0.0
        assert props["opacity"]["maximum"] == 1.0

    def test_capture_viewport_extended_view_property(self):
        assert TOOL_CAPTURE_VIEWPORT in TOOL_DEFINITIONS
        tool_spec = TOOL_DEFINITIONS[TOOL_CAPTURE_VIEWPORT]
        assert tool_spec["permission_tier"] == PERMISSION_READ_ONLY

        props = tool_spec["input_schema"]["properties"]
        assert "view" in props
        assert props["view"]["enum"] == ["CURRENT", "FRONT", "SIDE", "TOP", "PERSPECTIVE"]
        assert props["view"]["default"] == "CURRENT"


class TestReferenceImageValidation:
    """Verify parameter sanitization and fail-closed validation."""

    def test_valid_load_reference_image_args(self):
        valid_params = {
            "image_path": "C:/path/to/reference.png",
            "name": "Dragon_Front_Ref",
            "display_mode": "EMPTY",
            "view_axis": "FRONT",
            "location": [0.0, -2.0, 1.5],
            "size": 6.5,
            "opacity": 0.75,
            "depth": "FRONT",
        }
        sanitized = validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, valid_params, trusted_approval=True)
        assert sanitized["image_path"] == "C:/path/to/reference.png"
        assert sanitized["name"] == "Dragon_Front_Ref"
        assert sanitized["display_mode"] == "EMPTY"
        assert sanitized["view_axis"] == "FRONT"
        assert sanitized["size"] == 6.5
        assert sanitized["opacity"] == 0.75

    def test_load_reference_image_defaults(self):
        minimal = {"image_path": "test.jpg"}
        sanitized = validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, minimal, trusted_approval=True)
        assert sanitized["name"] == "Reference_Image"
        assert sanitized["display_mode"] == "EMPTY"
        assert sanitized["view_axis"] == "FRONT"
        assert sanitized["size"] == 5.0
        assert sanitized["opacity"] == 0.8
        assert sanitized["depth"] == "DEFAULT"
        assert sanitized["location"] == [0.0, 0.0, 0.0]

    def test_missing_image_path_rejected(self):
        with pytest.raises(ValueError, match="image_path"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, {}, trusted_approval=True)

    def test_empty_image_path_rejected(self):
        with pytest.raises(ValueError, match="image_path"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, {"image_path": "   "}, trusted_approval=True)

    def test_invalid_display_mode_rejected(self):
        with pytest.raises(ValueError, match="display_mode"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, {"image_path": "test.png", "display_mode": "VOLUME"}, trusted_approval=True)

    def test_invalid_view_axis_rejected(self):
        with pytest.raises(ValueError, match="view_axis"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, {"image_path": "test.png", "view_axis": "ISOMETRIC"}, trusted_approval=True)

    def test_negative_size_rejected(self):
        with pytest.raises(ValueError, match="size"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, {"image_path": "test.png", "size": -1.0}, trusted_approval=True)

    def test_out_of_bounds_opacity_rejected(self):
        with pytest.raises(ValueError, match="opacity"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, {"image_path": "test.png", "opacity": 1.5}, trusted_approval=True)

    def test_untrusted_approval_flag_rejected(self):
        tampered = {"image_path": "test.png", "approved": True}
        with pytest.raises(ValueError, match="Unknown parameter 'approved'"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, tampered, trusted_approval=True)

    def test_unapproved_mutation_rejected_fail_closed(self):
        with pytest.raises(PermissionError, match="Approval required"):
            validate_tool_input(TOOL_LOAD_REFERENCE_IMAGE, {"image_path": "test.png"}, trusted_approval=False)


class TestCaptureViewportValidation:
    """Verify capture_viewport view parameter validation."""

    def test_valid_views(self):
        for view_name in ("CURRENT", "FRONT", "SIDE", "TOP", "PERSPECTIVE"):
            sanitized = validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"view": view_name})
            assert sanitized["view"] == view_name

    def test_invalid_view_rejected(self):
        with pytest.raises(ValueError, match="view"):
            validate_tool_input(TOOL_CAPTURE_VIEWPORT, {"view": "OBLIQUE"})


class TestModelingAgentIntegration:
    """Verify modeling agent routes and validates reference image tools."""

    def test_tool_supported_in_agent(self):
        assert TOOL_LOAD_REFERENCE_IMAGE in SUPPORTED_MODELING_TOOLS

    def test_manifest_declares_reference_capability(self):
        manifest = create_modeling_manifest("0.1.50")
        assert len(manifest.capabilities) >= 21
        caps = {c.capability_id: c for c in manifest.capabilities}
        assert CAPABILITY_MODELING_OBJECT_OPS in caps

        obj_ops_cap = caps[CAPABILITY_MODELING_OBJECT_OPS]
        assert TOOL_LOAD_REFERENCE_IMAGE in obj_ops_cap.supported_task_types
        assert obj_ops_cap.read_write == "SCENE_MUTATION"
        assert obj_ops_cap.verification_status == "VERIFIED"

    def test_agent_input_validation(self):
        agent = ModelingAgent()
        valid, _, _ = agent.validate_task_input(TOOL_LOAD_REFERENCE_IMAGE, {"image_path": "valid.png"})
        assert valid is True

        invalid, err_code, err_msg = agent.validate_task_input(TOOL_LOAD_REFERENCE_IMAGE, {})
        assert invalid is False
        assert err_code == "INVALID_PARAMS"
