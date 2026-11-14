"""
Unit Tests for transform_object schema, validation, security hashing, and handler execution.
Executes purely in-memory on CPU without requiring live Blender or network services.
"""

import math
import unittest
from unittest.mock import MagicMock

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_TRANSFORM_OBJECT,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
    get_all_tool_definitions,
)
from blender_addon.universal_mcp.bridge.approval_registry import (
    ApprovalRegistry,
    compute_arg_hash,
)
from blender_addon.universal_mcp.bridge.handlers import handle_transform_object


class MockBlenderObject:
    """Mock Blender Object for headless unit testing."""

    def __init__(self, name="TestObject", location=None, rotation=None, scale=None, dimensions=None):
        self.name = name
        self.location = list(location) if location else [0.0, 0.0, 0.0]
        self.rotation_euler = list(rotation) if rotation else [0.0, 0.0, 0.0]
        self.scale = list(scale) if scale else [1.0, 1.0, 1.0]
        self.dimensions = list(dimensions) if dimensions else [2.0, 2.0, 2.0]


class MockBpyContext:
    def __init__(self):
        self.view_layer = MagicMock()
        self.view_layer.update = MagicMock()


class MockBpyData:
    def __init__(self, objects_dict=None):
        self.objects = objects_dict or {}


class MockBpyModule:
    def __init__(self, objects_dict=None):
        self.data = MockBpyData(objects_dict)
        self.context = MockBpyContext()


class TestTransformObjectSchemaAndValidation(unittest.TestCase):
    """Test suite for transform_object schema registration and parameter validation."""

    def test_schema_definition(self):
        self.assertIn(TOOL_TRANSFORM_OBJECT, TOOL_DEFINITIONS)
        tool_def = TOOL_DEFINITIONS[TOOL_TRANSFORM_OBJECT]
        self.assertEqual(tool_def["permission_tier"], PERMISSION_SCENE_MUTATION)
        schema = tool_def["input_schema"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["name"])
        props = schema["properties"]
        self.assertIn("name", props)
        self.assertIn("location", props)
        self.assertIn("rotation_euler", props)
        self.assertIn("scale", props)
        self.assertIn("relative", props)
        self.assertIn("approved", props)

    def test_valid_absolute_translation(self):
        params = {
            "name": "Cube1",
            "location": [1.0, 2.5, -3.0],
        }
        res = validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=True)
        self.assertEqual(res["name"], "Cube1")
        self.assertEqual(res["location"], [1.0, 2.5, -3.0])
        self.assertEqual(res["relative"], False)
        self.assertTrue(res["trusted_approval"])

    def test_valid_rotation_and_scale(self):
        params = {
            "name": "Sphere1",
            "rotation_euler": [0.0, 1.5708, 3.1415],
            "scale": [2.0, 2.0, 0.5],
            "relative": True,
        }
        res = validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=True)
        self.assertEqual(res["name"], "Sphere1")
        self.assertEqual(res["rotation_euler"], [0.0, 1.5708, 3.1415])
        self.assertEqual(res["scale"], [2.0, 2.0, 0.5])
        self.assertTrue(res["relative"])

    def test_missing_name_fails(self):
        params = {"location": [1.0, 2.0, 3.0]}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=True)
        self.assertIn("Missing required parameter 'name'", str(ctx.exception))

    def test_empty_name_fails(self):
        params = {"name": "   ", "location": [1.0, 2.0, 3.0]}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=True)
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_no_transform_property_fails(self):
        params = {"name": "Cube1"}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=True)
        self.assertIn("At least one transform property", str(ctx.exception))

    def test_non_finite_location_rejected(self):
        params = {"name": "Cube1", "location": [1.0, float("nan"), 3.0]}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=True)
        self.assertIn("must be a finite number", str(ctx.exception))

    def test_invalid_scale_rejected(self):
        # Scale must be >= 0.0001
        params = {"name": "Cube1", "scale": [1.0, 0.0, 1.0]}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=True)
        self.assertIn("must be >= 0.0001", str(ctx.exception))

        params_neg = {"name": "Cube1", "scale": [1.0, -0.5, 1.0]}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params_neg, trusted_approval=True)
        self.assertIn("must be >= 0.0001", str(ctx.exception))

    def test_untrusted_model_approval_denied(self):
        params = {"name": "Cube1", "location": [0.0, 1.0, 0.0], "approved": True}
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize", str(ctx.exception))

    def test_default_read_only_approval_required(self):
        params = {"name": "Cube1", "location": [0.0, 1.0, 0.0]}
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_TRANSFORM_OBJECT, params, trusted_approval=False)
        self.assertIn("requires explicit user approval", str(ctx.exception))


class TestTransformObjectApprovalAndSecurity(unittest.TestCase):
    """Test suite for approval lifecycle, parameter hashing, and tamper/replay rejection."""

    def setUp(self):
        self.registry = ApprovalRegistry()

    def test_tamper_detection_location(self):
        approved_params = {
            "name": "TargetCube",
            "location": [1.0, 2.0, 3.0],
            "relative": False,
        }
        req = self.registry.create_request(TOOL_TRANSFORM_OBJECT, approved_params, timeout=30.0)
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # Attempt consumption with tampered location
        tampered_params = dict(approved_params)
        tampered_params["location"] = [99.0, 99.0, 99.0]
        consumed, err = self.registry.consume_approval(req.request_id, token, TOOL_TRANSFORM_OBJECT, tampered_params)
        self.assertFalse(consumed)
        self.assertIn("tampering detected", err.lower())

    def test_tamper_detection_mode(self):
        approved_params = {
            "name": "TargetCube",
            "location": [1.0, 2.0, 3.0],
            "relative": False,
        }
        req = self.registry.create_request(TOOL_TRANSFORM_OBJECT, approved_params, timeout=30.0)
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # Attempt consumption with flipped relative mode
        tampered_params = dict(approved_params)
        tampered_params["relative"] = True
        consumed, err = self.registry.consume_approval(req.request_id, token, TOOL_TRANSFORM_OBJECT, tampered_params)
        self.assertFalse(consumed)
        self.assertIn("tampering detected", err.lower())

    def test_single_use_replay_prevention(self):
        approved_params = {
            "name": "TargetCube",
            "scale": [1.5, 1.5, 1.5],
            "relative": False,
        }
        req = self.registry.create_request(TOOL_TRANSFORM_OBJECT, approved_params, timeout=30.0)
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # First consumption succeeds
        c1, msg1 = self.registry.consume_approval(req.request_id, token, TOOL_TRANSFORM_OBJECT, approved_params)
        self.assertTrue(c1)

        # Replay attempt fails
        c2, msg2 = self.registry.consume_approval(req.request_id, token, TOOL_TRANSFORM_OBJECT, approved_params)
        self.assertFalse(c2)
        self.assertIn("Replay rejected", msg2)


class TestTransformObjectHandler(unittest.TestCase):
    """Test suite for handle_transform_object execution and state updates."""

    def setUp(self):
        self.obj = MockBlenderObject(
            name="MyCube",
            location=[1.0, 1.0, 1.0],
            rotation=[0.0, 0.0, 0.0],
            scale=[1.0, 1.0, 1.0],
            dimensions=[2.0, 2.0, 2.0],
        )
        self.mock_bpy = MockBpyModule(objects_dict={"MyCube": self.obj})

    def test_missing_credentials_denied(self):
        params = {"name": "MyCube", "location": [2.0, 3.0, 4.0]}
        with self.assertRaises(PermissionError) as ctx:
            handle_transform_object(bpy_module=self.mock_bpy, params=params)
        self.assertIn("Missing trusted human approval credentials", str(ctx.exception))

    def test_nonexistent_object_fails(self):
        params = {
            "name": "GhostObject",
            "location": [2.0, 3.0, 4.0],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        with self.assertRaises(ValueError) as ctx:
            handle_transform_object(bpy_module=self.mock_bpy, params=_host_approved("transform_object",params))
        self.assertIn("Object not found in scene: 'GhostObject'", str(ctx.exception))

    def test_absolute_transform_execution(self):
        params = {
            "name": "MyCube",
            "location": [5.0, 6.0, 7.0],
            "rotation_euler": [0.5, 1.0, 1.5],
            "scale": [2.0, 3.0, 4.0],
            "relative": False,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_transform_object(bpy_module=self.mock_bpy, params=_host_approved("transform_object",params))

        self.assertTrue(res["transformed"])
        self.assertEqual(res["name"], "MyCube")
        self.assertEqual(res["relative"], False)
        self.assertEqual(res["location"], [5.0, 6.0, 7.0])
        self.assertEqual(res["rotation_euler"], [0.5, 1.0, 1.5])
        self.assertEqual(res["scale"], [2.0, 3.0, 4.0])
        self.assertEqual(res["previous"]["location"], [1.0, 1.0, 1.0])
        self.assertEqual(res["previous"]["rotation_euler"], [0.0, 0.0, 0.0])
        self.assertEqual(res["previous"]["scale"], [1.0, 1.0, 1.0])

        # Verify underlying object was modified
        self.assertEqual(self.obj.location, (5.0, 6.0, 7.0))
        self.assertEqual(self.obj.rotation_euler, (0.5, 1.0, 1.5))
        self.assertEqual(self.obj.scale, (2.0, 3.0, 4.0))
        self.mock_bpy.context.view_layer.update.assert_called_once()

    def test_relative_transform_execution(self):
        params = {
            "name": "MyCube",
            "location": [2.0, -1.0, 3.0],
            "rotation_euler": [0.1, 0.2, 0.3],
            "scale": [2.0, 0.5, 1.5],
            "relative": True,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_transform_object(bpy_module=self.mock_bpy, params=_host_approved("transform_object",params))

        self.assertTrue(res["transformed"])
        self.assertTrue(res["relative"])
        # Original: [1.0, 1.0, 1.0], Delta: [2.0, -1.0, 3.0] -> [3.0, 0.0, 4.0]
        self.assertEqual(res["location"], [3.0, 0.0, 4.0])
        # Original: [0.0, 0.0, 0.0], Delta: [0.1, 0.2, 0.3] -> [0.1, 0.2, 0.3]
        self.assertEqual(res["rotation_euler"], [0.1, 0.2, 0.3])
        # Original: [1.0, 1.0, 1.0], Multiplier: [2.0, 0.5, 1.5] -> [2.0, 0.5, 1.5]
        self.assertEqual(res["scale"], [2.0, 0.5, 1.5])

    def test_partial_transform_only_location(self):
        params = {
            "name": "MyCube",
            "location": [10.0, 20.0, 30.0],
            "trusted_approval": True,
            "_trusted_test_override": True,
        }
        res = handle_transform_object(bpy_module=self.mock_bpy, params=_host_approved("transform_object",params))

        self.assertEqual(res["location"], [10.0, 20.0, 30.0])
        # Rotation and scale remain at original values
        self.assertEqual(res["rotation_euler"], [0.0, 0.0, 0.0])
        self.assertEqual(res["scale"], [1.0, 1.0, 1.0])


from tests.unit.modeling_approval_fixture import approved as _host_approved


if __name__ == "__main__":
    unittest.main()

