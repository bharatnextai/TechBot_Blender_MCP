"""
Unit tests for anatomical masking and bilateral symmetry (v0.1.59).
Tests schema validation, handler mocking, and agent manifest.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.schemas.tool_schemas import (
    validate_tool_input,
    TOOL_CONFIGURE_ANATOMICAL_MASK,
    TOOL_INSPECT_ANATOMICAL_MASK,
    TOOL_SYMMETRIZE_MESH_GEOMETRY,
    TOOL_DETAIL_SURFACE_FEATURES,
    TOOL_SCULPT_ORGANIC_ANATOMY,
)
from mcp_service.agents.modeling import (
    create_modeling_manifest,
    SUPPORTED_MODELING_TOOLS,
    CAPABILITY_MODELING_ANATOMICAL_MASK,
    CAPABILITY_MODELING_ANATOMICAL_MASK_INSPECT,
    CAPABILITY_MODELING_SYMMETRIZE,
)


def _validate_ok(tool_name, params, trusted=False):
    """Returns (True, None, None) if validation passes, (False, err_type, msg) otherwise."""
    try:
        validate_tool_input(tool_name, params, trusted_approval=trusted)
        return True, None, None
    except (ValueError, PermissionError, TypeError) as e:
        return False, type(e).__name__, str(e)


class TestConfigureAnatomicalMaskSchema(unittest.TestCase):
    """Schema validation for configure_anatomical_mask."""

    def _base(self):
        return {
            "target_object": "Dragon_Blockout",
            "action": "SET",
            "mask_name": "Horns",
            "region_type": "SPHERE",
            "center": [0.0, 0.0, 1.5],
            "radius": 0.3,
        }

    def test_valid_create(self):
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, self._base(), trusted=True)
        self.assertTrue(ok, msg)

    def test_valid_bounding_box(self):
        p = self._base()
        p["region_type"] = "BOUNDING_BOX"
        p["region_bounds"] = [-0.5, -0.5, 0.5, 0.5, 0.5, 1.5]
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_valid_cylinder(self):
        p = self._base()
        p["region_type"] = "CYLINDER"
        p["radius"] = 0.2
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_valid_all_region(self):
        p = self._base()
        p["region_type"] = "ALL"
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_missing_mask_name_rejects(self):
        p = self._base()
        del p["mask_name"]
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertFalse(ok)

    def test_missing_target_object_rejects(self):
        p = self._base()
        del p["target_object"]
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertFalse(ok)

    def test_invalid_action_rejects(self):
        p = self._base()
        p["action"] = "destroy"  # not in SET/ADD/SUBTRACT/CLEAR
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertFalse(ok)

    def test_invalid_region_type_rejects(self):
        p = self._base()
        p["region_type"] = "CUBE"
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertFalse(ok)

    def test_invalid_symmetry_axis_rejects(self):
        p = self._base()
        p["symmetry_axis"] = "W"
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertFalse(ok)

    def test_center_non_three_element_rejects(self):
        p = self._base()
        p["center"] = [0.0, 0.0]
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertFalse(ok)

    def test_region_bounds_wrong_length_rejects(self):
        p = self._base()
        p["region_type"] = "BOUNDING_BOX"
        p["region_bounds"] = [0.0, 0.0, 0.0, 1.0]  # must be 6 elements
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertFalse(ok)

    def test_untrusted_approval_rejected_by_permission_guard(self):
        """approved=True without trusted_approval=True must be rejected fail-closed."""
        p = self._base()
        p["approved"] = True
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=False)
        # Bridge rejects untrusted approval; PermissionError expected
        self.assertFalse(ok)
        self.assertEqual(err, "PermissionError", msg)

    def test_subtract_action(self):
        p = self._base()
        p["action"] = "SUBTRACT"
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_clear_action(self):
        p = self._base()
        p["action"] = "CLEAR"
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_add_action(self):
        p = self._base()
        p["action"] = "ADD"
        ok, err, msg = _validate_ok(TOOL_CONFIGURE_ANATOMICAL_MASK, p, trusted=True)
        self.assertTrue(ok, msg)


class TestInspectAnatomicalMaskSchema(unittest.TestCase):
    """Schema validation for inspect_anatomical_mask (READ_ONLY — no approval needed)."""

    def test_valid_params(self):
        p = {"target_object": "Dragon_Blockout"}
        ok, err, msg = _validate_ok(TOOL_INSPECT_ANATOMICAL_MASK, p)
        self.assertTrue(ok, msg)

    def test_valid_with_mask_name(self):
        p = {"target_object": "Dragon_Blockout", "mask_name": "Horns"}
        ok, err, msg = _validate_ok(TOOL_INSPECT_ANATOMICAL_MASK, p)
        self.assertTrue(ok, msg)

    def test_missing_target_rejects(self):
        ok, err, msg = _validate_ok(TOOL_INSPECT_ANATOMICAL_MASK, {})
        self.assertFalse(ok)


class TestSymmetrizeMeshGeometrySchema(unittest.TestCase):
    """Schema validation for symmetrize_mesh_geometry."""

    def _base(self):
        return {
            "target_object": "Dragon_Blockout",
            "symmetry_axis": "X",
            "source_direction": "+TO_-",
            "seam_threshold": 0.001,
        }

    def test_valid_params(self):
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, self._base(), trusted=True)
        self.assertTrue(ok, msg)

    def test_valid_minus_to_plus(self):
        p = self._base()
        p["source_direction"] = "-TO_+"
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_valid_average(self):
        p = self._base()
        p["source_direction"] = "AVERAGE"
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_invalid_axis_rejects(self):
        p = self._base()
        p["symmetry_axis"] = "W"
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, p, trusted=True)
        self.assertFalse(ok)

    def test_invalid_source_direction_rejects(self):
        p = self._base()
        p["source_direction"] = "LEFT_TO_RIGHT"
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, p, trusted=True)
        self.assertFalse(ok)

    def test_missing_target_rejects(self):
        p = self._base()
        del p["target_object"]
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, p, trusted=True)
        self.assertFalse(ok)

    def test_y_axis(self):
        p = self._base()
        p["symmetry_axis"] = "Y"
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_z_axis(self):
        p = self._base()
        p["symmetry_axis"] = "Z"
        ok, err, msg = _validate_ok(TOOL_SYMMETRIZE_MESH_GEOMETRY, p, trusted=True)
        self.assertTrue(ok, msg)


class TestDetailSurfaceFeaturesSymmetryParams(unittest.TestCase):
    """Schema validation for new symmetry/mask params on detail_surface_features."""

    def _base(self):
        return {
            "target_object": "Dragon_Blockout",
            "feature_type": "SCALES",
            "feature_scale": 0.05,
            "depth": 0.01,
        }

    def test_valid_with_mask(self):
        p = self._base()
        p["mask_vertex_group"] = "Horns"
        ok, err, msg = _validate_ok(TOOL_DETAIL_SURFACE_FEATURES, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_valid_with_symmetry(self):
        p = self._base()
        p["use_symmetry"] = True
        p["symmetry_axis"] = "X"
        ok, err, msg = _validate_ok(TOOL_DETAIL_SURFACE_FEATURES, p, trusted=True)
        self.assertTrue(ok, msg)

    def test_invalid_symmetry_axis_rejects(self):
        p = self._base()
        p["use_symmetry"] = True
        p["symmetry_axis"] = "W"
        ok, err, msg = _validate_ok(TOOL_DETAIL_SURFACE_FEATURES, p, trusted=True)
        self.assertFalse(ok)


class TestSculptOrganicAnatomySymmetryParams(unittest.TestCase):
    """Schema validation for sculpt_organic_anatomy — confirms tool exists and is importable."""

    def _base(self):
        return {
            "target_object": "Dragon_Blockout",
        }

    def test_valid_minimal_params(self):
        # sculpt_organic_anatomy requires only target_object
        ok, err, msg = _validate_ok(TOOL_SCULPT_ORGANIC_ANATOMY, self._base(), trusted=True)
        self.assertTrue(ok, msg)

    def test_missing_target_rejects(self):
        ok, err, msg = _validate_ok(TOOL_SCULPT_ORGANIC_ANATOMY, {}, trusted=True)
        self.assertFalse(ok)


class TestModelingAgentManifest(unittest.TestCase):
    """Agent manifest includes new capabilities."""

    def test_manifest_has_28_capabilities(self):
        manifest = create_modeling_manifest(version="0.1.59")
        self.assertGreaterEqual(len(manifest.capabilities), 30)

    def test_new_capabilities_present(self):
        manifest = create_modeling_manifest(version="0.1.59")
        caps = {c.capability_id for c in manifest.capabilities}
        self.assertIn("modeling.anatomical_mask", caps)
        self.assertIn("modeling.anatomical_mask_inspect", caps)
        self.assertIn("modeling.symmetrize", caps)

    def test_new_tools_in_supported_set(self):
        self.assertIn(TOOL_CONFIGURE_ANATOMICAL_MASK, SUPPORTED_MODELING_TOOLS)
        self.assertIn(TOOL_INSPECT_ANATOMICAL_MASK, SUPPORTED_MODELING_TOOLS)
        self.assertIn(TOOL_SYMMETRIZE_MESH_GEOMETRY, SUPPORTED_MODELING_TOOLS)

    def test_anatomical_mask_inspect_is_read_only(self):
        manifest = create_modeling_manifest(version="0.1.59")
        cap = next(c for c in manifest.capabilities if c.capability_id == CAPABILITY_MODELING_ANATOMICAL_MASK_INSPECT)
        self.assertEqual(cap.read_write, "READ_ONLY")

    def test_configure_anatomical_mask_is_mutation(self):
        manifest = create_modeling_manifest(version="0.1.59")
        cap = next(c for c in manifest.capabilities if c.capability_id == CAPABILITY_MODELING_ANATOMICAL_MASK)
        self.assertEqual(cap.read_write, "SCENE_MUTATION")

    def test_symmetrize_is_mutation(self):
        manifest = create_modeling_manifest(version="0.1.59")
        cap = next(c for c in manifest.capabilities if c.capability_id == CAPABILITY_MODELING_SYMMETRIZE)
        self.assertEqual(cap.read_write, "SCENE_MUTATION")


if __name__ == "__main__":
    unittest.main()
