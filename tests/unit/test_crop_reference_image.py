"""
Unit tests for Reference Sheet Cropping for Multi-View Modeling (v0.1.51).
Verifies:
1. Schema contracts for crop_reference_image and extended load_reference_image.
2. Validation rules: required image_path & crop_box, bounds checks (u_min < u_max, v_min < v_max),
   coordinate_system enum, output_path overwrite prevention, fail-closed security.
3. Execution contract: crop dimensions, aspect ratio, source preservation, PIL/fallback handling.
4. Modeling agent capability registration and task validation.
"""

import math
import os
from pathlib import Path
import tempfile
import pytest
from PIL import Image

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_LOAD_REFERENCE_IMAGE,
    TOOL_CROP_REFERENCE_IMAGE,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_crop_reference_image,
)
from mcp_service.agents.modeling import (
    SUPPORTED_MODELING_TOOLS,
    CAPABILITY_MODELING_OBJECT_OPS,
    create_modeling_manifest,
    ModelingAgent,
)


class TestCropReferenceImageSchemas:
    """Verify tool definitions and schema specifications."""

    def test_crop_reference_image_registered(self):
        assert TOOL_CROP_REFERENCE_IMAGE in TOOL_DEFINITIONS
        tool_spec = TOOL_DEFINITIONS[TOOL_CROP_REFERENCE_IMAGE]
        assert tool_spec["name"] == "crop_reference_image"
        assert tool_spec["permission_tier"] == PERMISSION_SCENE_MUTATION

        schema = tool_spec["input_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert "image_path" in schema["required"]
        assert "crop_box" in schema["required"]

        props = schema["properties"]
        assert "image_path" in props
        assert "crop_box" in props
        assert props["crop_box"]["type"] == "array"
        assert props["crop_box"]["minItems"] == 4
        assert props["crop_box"]["maxItems"] == 4

        assert "coordinate_system" in props
        assert props["coordinate_system"]["enum"] == ["UV", "IMAGE_SPACE"]

        assert "output_path" in props
        assert "load_as_reference" in props
        assert "display_mode" in props
        assert props["display_mode"]["enum"] == ["EMPTY", "PLANE"]
        assert "view_axis" in props
        assert props["view_axis"]["enum"] == ["FRONT", "SIDE", "TOP", "USER"]

    def test_load_reference_image_extended_crop_properties(self):
        tool_spec = TOOL_DEFINITIONS[TOOL_LOAD_REFERENCE_IMAGE]
        props = tool_spec["input_schema"]["properties"]
        assert "crop_box" in props
        assert "coordinate_system" in props
        assert "output_path" in props


class TestCropReferenceImageValidation:
    """Verify parameter sanitization, bounds checking, and fail-closed validation."""

    def test_valid_crop_reference_image_args(self):
        params = {
            "image_path": "C:/path/to/reference_sheet.png",
            "crop_box": [0.1, 0.2, 0.45, 0.85],
            "coordinate_system": "UV",
            "output_path": "C:/path/to/crop_front.png",
            "load_as_reference": True,
            "name": "Dragon_Front_Ref",
            "display_mode": "PLANE",
            "view_axis": "FRONT",
            "size": 6.0,
            "opacity": 0.85,
        }
        sanitized = validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, params, trusted_approval=True)
        assert sanitized["image_path"] == "C:/path/to/reference_sheet.png"
        assert sanitized["crop_box"] == [0.1, 0.2, 0.45, 0.85]
        assert sanitized["coordinate_system"] == "UV"
        assert sanitized["output_path"] == "C:/path/to/crop_front.png"
        assert sanitized["load_as_reference"] is True
        assert sanitized["name"] == "Dragon_Front_Ref"
        assert sanitized["display_mode"] == "PLANE"
        assert sanitized["view_axis"] == "FRONT"
        assert sanitized["size"] == 6.0
        assert sanitized["opacity"] == 0.85

    def test_crop_reference_image_defaults(self):
        minimal = {
            "image_path": "test_sheet.png",
            "crop_box": [0.0, 0.0, 0.5, 0.5],
        }
        sanitized = validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, minimal, trusted_approval=True)
        assert sanitized["coordinate_system"] == "UV"
        assert sanitized["load_as_reference"] is True
        assert sanitized["name"] == "Reference_Crop"
        assert sanitized["display_mode"] == "EMPTY"
        assert sanitized["view_axis"] == "FRONT"
        assert sanitized["size"] == 5.0
        assert sanitized["opacity"] == 0.8
        assert sanitized["depth"] == "DEFAULT"

    def test_image_space_coordinate_system(self):
        params = {
            "image_path": "sheet.png",
            "crop_box": [0.0, 0.0, 0.5, 0.5],
            "coordinate_system": "IMAGE_SPACE",
        }
        sanitized = validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, params, trusted_approval=True)
        assert sanitized["coordinate_system"] == "IMAGE_SPACE"

    def test_missing_crop_box_rejected(self):
        with pytest.raises(ValueError, match="crop_box"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {"image_path": "sheet.png"}, trusted_approval=True)

    def test_invalid_crop_box_length_rejected(self):
        with pytest.raises(ValueError, match="crop_box"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {"image_path": "sheet.png", "crop_box": [0.0, 0.5, 1.0]}, trusted_approval=True)

    def test_inverted_u_bounds_rejected(self):
        with pytest.raises(ValueError, match="u_min.*strictly less than u_max"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {"image_path": "sheet.png", "crop_box": [0.8, 0.1, 0.2, 0.9]}, trusted_approval=True)

    def test_inverted_v_bounds_rejected(self):
        with pytest.raises(ValueError, match="v_min.*strictly less than v_max"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {"image_path": "sheet.png", "crop_box": [0.1, 0.9, 0.5, 0.2]}, trusted_approval=True)

    def test_out_of_range_crop_box_rejected(self):
        with pytest.raises(ValueError, match="crop_box"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {"image_path": "sheet.png", "crop_box": [-0.1, 0.0, 0.5, 1.0]}, trusted_approval=True)

        with pytest.raises(ValueError, match="crop_box"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {"image_path": "sheet.png", "crop_box": [0.0, 0.0, 0.5, 1.5]}, trusted_approval=True)

    def test_output_path_overwrite_source_rejected(self):
        with pytest.raises(ValueError, match="overwrite source"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {
                "image_path": "C:/images/sheet.png",
                "crop_box": [0.0, 0.0, 0.5, 0.5],
                "output_path": "C:/images/sheet.png",
            }, trusted_approval=True)

    def test_untrusted_approval_flag_rejected(self):
        tampered = {
            "image_path": "sheet.png",
            "crop_box": [0.0, 0.0, 0.5, 0.5],
            "approved": True,
        }
        with pytest.raises(ValueError, match="Unknown parameter 'approved'"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, tampered, trusted_approval=True)

    def test_unapproved_mutation_rejected_fail_closed(self):
        with pytest.raises(PermissionError, match="Approval required"):
            validate_tool_input(TOOL_CROP_REFERENCE_IMAGE, {
                "image_path": "sheet.png",
                "crop_box": [0.0, 0.0, 0.5, 0.5],
            }, trusted_approval=False)


class TestCropReferenceImageExecution:
    """Verify cropping execution logic, file generation, and source preservation."""

    @pytest.fixture
    def test_image(self, tmp_path):
        img_path = tmp_path / "test_sheet.png"
        img = Image.new("RGB", (200, 100), color=(120, 150, 180))
        img.save(str(img_path))
        orig_bytes = img_path.read_bytes()
        return img_path, orig_bytes

    def test_crop_execution_without_blender_load(self, test_image, tmp_path):
        img_path, orig_bytes = test_image
        out_path = tmp_path / "cropped_result.png"

        params = {
            "image_path": str(img_path),
            "crop_box": [0.1, 0.2, 0.6, 0.7],  # u: 20 to 120 (w=100), v in UV: y_top=(1-0.7)*100=30, y_bottom=(1-0.2)*100=80 (h=50)
            "coordinate_system": "UV",
            "output_path": str(out_path),
            "load_as_reference": False,
        }
        res = handle_crop_reference_image(bpy_module=None, params=params)

        assert res["created"] is True
        assert res["load_as_reference"] is False
        assert res["crop_dimensions"] == [100, 50]
        assert res["crop_aspect_ratio"] == 2.0
        assert res["source_dimensions"] == [200, 100]

        # Verify output file
        assert out_path.exists()
        with Image.open(str(out_path)) as c_img:
            assert c_img.size == (100, 50)

        # Verify source image was strictly preserved
        assert img_path.read_bytes() == orig_bytes

    def test_crop_image_space_execution(self, test_image, tmp_path):
        img_path, _ = test_image
        out_path = tmp_path / "cropped_image_space.png"

        params = {
            "image_path": str(img_path),
            "crop_box": [0.0, 0.0, 0.5, 0.5],
            "coordinate_system": "IMAGE_SPACE",
            "output_path": str(out_path),
            "load_as_reference": False,
        }
        res = handle_crop_reference_image(bpy_module=None, params=params)

        assert res["created"] is True
        assert res["crop_dimensions"] == [100, 50]
        assert out_path.exists()
        with Image.open(str(out_path)) as c_img:
            assert c_img.size == (100, 50)

    def test_crop_handler_rejects_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            handle_crop_reference_image(bpy_module=None, params={
                "image_path": str(tmp_path / "nonexistent.png"),
                "crop_box": [0.0, 0.0, 0.5, 0.5],
                "load_as_reference": False,
            })

    def test_crop_handler_rejects_overwrite_source(self, test_image):
        img_path, _ = test_image
        with pytest.raises(ValueError, match="cannot overwrite source"):
            handle_crop_reference_image(bpy_module=None, params={
                "image_path": str(img_path),
                "crop_box": [0.0, 0.0, 0.5, 0.5],
                "output_path": str(img_path),
                "load_as_reference": False,
            })


class TestModelingAgentCropIntegration:
    """Verify modeling agent routes and validates crop reference image tool."""

    def test_crop_tool_supported_in_agent(self):
        assert TOOL_CROP_REFERENCE_IMAGE in SUPPORTED_MODELING_TOOLS

    def test_manifest_declares_crop_in_object_ops(self):
        manifest = create_modeling_manifest("0.1.51")
        assert len(manifest.capabilities) >= 21
        caps = {c.capability_id: c for c in manifest.capabilities}
        assert CAPABILITY_MODELING_OBJECT_OPS in caps

        obj_ops_cap = caps[CAPABILITY_MODELING_OBJECT_OPS]
        assert TOOL_CROP_REFERENCE_IMAGE in obj_ops_cap.supported_task_types
        assert obj_ops_cap.read_write == "SCENE_MUTATION"
        assert obj_ops_cap.verification_status == "VERIFIED"

    def test_agent_crop_task_validation(self):
        agent = ModelingAgent()
        valid, _, _ = agent.validate_task_input(TOOL_CROP_REFERENCE_IMAGE, {
            "image_path": "sheet.png",
            "crop_box": [0.0, 0.0, 0.5, 0.5],
        })
        assert valid is True

        # Missing crop_box
        invalid, err_code, err_msg = agent.validate_task_input(TOOL_CROP_REFERENCE_IMAGE, {
            "image_path": "sheet.png",
        })
        assert invalid is False
        assert err_code == "INVALID_PARAMS"
        assert "crop_box" in err_msg

        # Missing image_path
        invalid2, err_code2, err_msg2 = agent.validate_task_input(TOOL_CROP_REFERENCE_IMAGE, {
            "crop_box": [0.0, 0.0, 0.5, 0.5],
        })
        assert invalid2 is False
        assert err_code2 == "INVALID_PARAMS"
        assert "image_path" in err_msg2
