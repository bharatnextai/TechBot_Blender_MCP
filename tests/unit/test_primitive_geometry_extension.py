"""
Unit tests for TASK-UMCP-0009: Primitive Geometry Schema Extension & Validation.
Tests schema definitions, parameter validation, primitive-specific parameter enforcement,
boundary and non-finite value checks, approval hashing, tampering/replay rejection, and mock handler execution.
"""

import math
import unittest
from typing import Dict, Any

from shared.schemas.tool_schemas import (
    TOOL_CREATE_PRIMITIVE,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.approval_registry import (
    ApprovalRegistry,
    compute_arg_hash,
)
from blender_addon.universal_mcp.bridge.handlers import handle_create_primitive


class TestPrimitiveGeometryExtension(unittest.TestCase):
    """Test suite for extended create_primitive geometry parameters and validation."""

    def test_schema_properties_registered(self):
        """Verify that all new primitive-specific geometry properties are present in tool definition."""
        schema = TOOL_DEFINITIONS[TOOL_CREATE_PRIMITIVE]["input_schema"]
        props = schema["properties"]
        self.assertFalse(schema.get("additionalProperties", True))
        for expected in ("radius", "depth", "size", "segments", "ring_count", "vertices"):
            self.assertIn(expected, props)

    def test_sphere_geometry_parameters_valid(self):
        """Verify custom sphere parameters and dynamic dimensions resolution."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "sphere",
            "name": "CustomSphere",
            "radius": 2.5,
            "segments": 64,
            "ring_count": 32,
        }, trusted_approval=True)
        self.assertEqual(params["primitive_type"], "sphere")
        self.assertEqual(params["radius"], 2.5)
        self.assertEqual(params["segments"], 64)
        self.assertEqual(params["ring_count"], 32)
        # Dimensions dynamically calculated as diameter (2 * 2.5 = 5.0)
        self.assertEqual(params["dimensions"], [5.0, 5.0, 5.0])

    def test_sphere_geometry_defaults(self):
        """Verify default sphere parameters when omitted."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "sphere",
            "name": "DefaultSphere",
        }, trusted_approval=True)
        self.assertEqual(params["radius"], 0.5)
        self.assertEqual(params["segments"], 32)
        self.assertEqual(params["ring_count"], 16)
        self.assertEqual(params["dimensions"], [1.0, 1.0, 1.0])

    def test_cylinder_geometry_parameters_valid(self):
        """Verify custom cylinder parameters and dynamic dimensions resolution."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cylinder",
            "name": "CustomCylinder",
            "radius": 1.5,
            "depth": 4.0,
            "vertices": 48,
        }, trusted_approval=True)
        self.assertEqual(params["primitive_type"], "cylinder")
        self.assertEqual(params["radius"], 1.5)
        self.assertEqual(params["depth"], 4.0)
        self.assertEqual(params["vertices"], 48)
        # Dimensions dynamically calculated as [2*r, 2*r, depth]
        self.assertEqual(params["dimensions"], [3.0, 3.0, 4.0])

    def test_cylinder_geometry_defaults(self):
        """Verify default cylinder parameters when omitted."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cylinder",
            "name": "DefaultCylinder",
        }, trusted_approval=True)
        self.assertEqual(params["radius"], 0.5)
        self.assertEqual(params["depth"], 1.0)
        self.assertEqual(params["vertices"], 32)
        self.assertEqual(params["dimensions"], [1.0, 1.0, 1.0])

    def test_plane_geometry_parameters_valid(self):
        """Verify custom plane parameters and dynamic dimensions resolution."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "plane",
            "name": "CustomPlane",
            "size": 3.5,
        }, trusted_approval=True)
        self.assertEqual(params["primitive_type"], "plane")
        self.assertEqual(params["size"], 3.5)
        self.assertEqual(params["dimensions"], [3.5, 3.5, 0.0001])

    def test_plane_geometry_defaults(self):
        """Verify default plane parameters when omitted."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "plane",
            "name": "DefaultPlane",
        }, trusted_approval=True)
        self.assertEqual(params["size"], 1.0)
        self.assertEqual(params["dimensions"], [1.0, 1.0, 0.0001])

    def test_cube_geometry_defaults(self):
        """Verify cube maintains existing dimensions default."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "DefaultCube",
        }, trusted_approval=True)
        self.assertEqual(params["dimensions"], [1.0, 1.0, 1.0])

    def test_explicit_dimensions_overrides_dynamic(self):
        """Verify that explicit dimensions argument takes precedence over dynamic computation."""
        params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "sphere",
            "name": "SquashedSphere",
            "radius": 1.0,
            "dimensions": [2.0, 2.0, 0.5],
        }, trusted_approval=True)
        self.assertEqual(params["dimensions"], [2.0, 2.0, 0.5])

    def test_incompatible_parameters_rejected(self):
        """Verify that parameters not applicable to the selected primitive are strictly rejected."""
        # Cube rejects primitive-specific parameters
        for bad_param in ({"radius": 1.0}, {"size": 2.0}, {"depth": 1.0}, {"segments": 32}):
            with self.assertRaises(ValueError) as ctx:
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cube",
                    "name": "BadCube",
                    **bad_param,
                }, trusted_approval=True)
            self.assertIn("not applicable", str(ctx.exception))

        # Sphere rejects cylinder/plane parameters
        for bad_param in ({"depth": 2.0}, {"vertices": 48}, {"size": 1.0}):
            with self.assertRaises(ValueError) as ctx:
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "sphere",
                    "name": "BadSphere",
                    **bad_param,
                }, trusted_approval=True)
            self.assertIn("not applicable", str(ctx.exception))

        # Cylinder rejects sphere/plane parameters
        for bad_param in ({"segments": 64}, {"ring_count": 32}, {"size": 2.0}):
            with self.assertRaises(ValueError) as ctx:
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cylinder",
                    "name": "BadCylinder",
                    **bad_param,
                }, trusted_approval=True)
            self.assertIn("not applicable", str(ctx.exception))

        # Plane rejects sphere/cylinder parameters
        for bad_param in ({"radius": 1.0}, {"depth": 2.0}, {"segments": 32}, {"vertices": 32}):
            with self.assertRaises(ValueError) as ctx:
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "plane",
                    "name": "BadPlane",
                    **bad_param,
                }, trusted_approval=True)
            self.assertIn("not applicable", str(ctx.exception))

    def test_invalid_values_and_bounds_rejected(self):
        """Verify rejection of non-positive numbers, out-of-range counts, and non-finite values."""
        # Non-positive numbers
        for val in (0, -1.0, -0.0001):
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "sphere", "name": "S", "radius": val,
                }, trusted_approval=True)
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cylinder", "name": "C", "depth": val,
                }, trusted_approval=True)
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "plane", "name": "P", "size": val,
                }, trusted_approval=True)

        # Exceeding maximum float bound (10000.0)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "sphere", "name": "S", "radius": 10001.0,
            }, trusted_approval=True)

        # Non-finite numbers (NaN, Inf, -Inf)
        for non_finite in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "sphere", "name": "S", "radius": non_finite,
                }, trusted_approval=True)
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cube", "name": "C", "location": [non_finite, 0.0, 0.0],
                }, trusted_approval=True)
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cube", "name": "C", "dimensions": [1.0, non_finite, 1.0],
                }, trusted_approval=True)

        # Integer counts out of bounds (< 3 or > 500)
        for bad_count in (0, 1, 2, 501, 1000):
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "sphere", "name": "S", "segments": bad_count,
                }, trusted_approval=True)
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "sphere", "name": "S", "ring_count": bad_count,
                }, trusted_approval=True)
            with self.assertRaises(ValueError):
                validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cylinder", "name": "C", "vertices": bad_count,
                }, trusted_approval=True)

        # Float passed for integer count
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "sphere", "name": "S", "segments": 32.5,
            }, trusted_approval=True)

        # Boolean passed for number or integer
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "sphere", "name": "S", "radius": True,
            }, trusted_approval=True)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "sphere", "name": "S", "segments": False,
            }, trusted_approval=True)

    def test_approval_hash_and_tampering_defense(self):
        """Verify that extended parameters bind securely to approval hashes and prevent tampering."""
        registry = ApprovalRegistry()

        # Clean normalized parameters for a sphere
        approved_params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "sphere",
            "name": "SecureSphere",
            "radius": 2.0,
            "segments": 64,
            "ring_count": 32,
        }, trusted_approval=True)

        # Create and approve request to generate token
        req = registry.create_request("create_primitive", approved_params, timeout=30.0)
        registry.resolve_request(req.request_id, "approved")
        token = req.approval_token

        # Compute hash consistency
        h1 = compute_arg_hash("create_primitive", approved_params)
        self.assertEqual(req.arg_hash, h1)

        # Tampering with radius must be rejected
        tampered_radius = dict(approved_params)
        tampered_radius["radius"] = 3.0
        consumed, err = registry.consume_approval(req.request_id, token, "create_primitive", tampered_radius)
        self.assertFalse(consumed)
        self.assertIn("tampering", err.lower())

        # Tampering with segments must be rejected
        tampered_segments = dict(approved_params)
        tampered_segments["segments"] = 128
        consumed, err = registry.consume_approval(req.request_id, token, "create_primitive", tampered_segments)
        self.assertFalse(consumed)
        self.assertIn("tampering", err.lower())

        # Exact matching parameters succeed
        consumed, msg = registry.consume_approval(req.request_id, token, "create_primitive", approved_params)
        self.assertTrue(consumed)

        # Replay attempt must be rejected
        replayed, msg = registry.consume_approval(req.request_id, token, "create_primitive", approved_params)
        self.assertFalse(replayed)
        self.assertIn("already been consumed", msg.lower())

    def test_mock_handler_primitive_ops_invocation(self):
        """Verify that handlers correctly extract extended parameters and invoke bpy.ops."""
        class MockObj:
            def __init__(self, name):
                self.name = name
                self.type = "MESH"
                self.location = [0.0, 0.0, 0.0]
                self.dimensions = [1.0, 1.0, 1.0]
                self.users_collection = []

        class MockContext:
            def __init__(self):
                self.active_object = None
                class MockViewLayer:
                    def update(self):
                        pass
                self.view_layer = MockViewLayer()
                class MockScene:
                    objects = []
                self.scene = MockScene()

        class MockOpsMesh:
            def __init__(self, ctx):
                self.ctx = ctx
                self.last_call = None

            def primitive_cube_add(self, size, location):
                self.last_call = ("cube", {"size": size, "location": location})
                self.ctx.active_object = MockObj("TempCube")

            def primitive_uv_sphere_add(self, radius, segments, ring_count, location):
                self.last_call = ("sphere", {"radius": radius, "segments": segments, "ring_count": ring_count, "location": location})
                self.ctx.active_object = MockObj("TempSphere")

            def primitive_cylinder_add(self, radius, depth, vertices, location):
                self.last_call = ("cylinder", {"radius": radius, "depth": depth, "vertices": vertices, "location": location})
                self.ctx.active_object = MockObj("TempCylinder")

            def primitive_plane_add(self, size, location):
                self.last_call = ("plane", {"size": size, "location": location})
                self.ctx.active_object = MockObj("TempPlane")

        class MockOpsObj:
            def select_all(self, action):
                pass

        class MockBpy:
            def __init__(self):
                self.context = MockContext()
                class MockData:
                    objects = {}
                self.data = MockData()
                class MockOps:
                    def __init__(self, ctx):
                        self.object = MockOpsObj()
                        self.mesh = MockOpsMesh(ctx)
                self.ops = MockOps(self.context)

        mock_bpy = MockBpy()

        # 1. Sphere execution
        sphere_params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "sphere",
            "name": "HandlerSphere",
            "radius": 1.75,
            "segments": 48,
            "ring_count": 24,
            "location": [1.0, 2.0, 3.0],
        }, trusted_approval=True)
        sphere_params["_trusted_test_override"] = True
        res = handle_create_primitive(bpy_module=mock_bpy, params=_host_approved("create_primitive",sphere_params))
        self.assertEqual(res["created"], True)
        self.assertEqual(res["name"], "HandlerSphere")
        self.assertEqual(res["radius"], 1.75)
        self.assertEqual(res["segments"], 48)
        self.assertEqual(res["ring_count"], 24)
        self.assertEqual(mock_bpy.ops.mesh.last_call[0], "sphere")
        self.assertEqual(mock_bpy.ops.mesh.last_call[1]["radius"], 1.75)
        self.assertEqual(mock_bpy.ops.mesh.last_call[1]["segments"], 48)
        self.assertEqual(mock_bpy.ops.mesh.last_call[1]["ring_count"], 24)

        # 2. Cylinder execution
        cyl_params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cylinder",
            "name": "HandlerCylinder",
            "radius": 1.25,
            "depth": 3.5,
            "vertices": 40,
        }, trusted_approval=True)
        cyl_params["_trusted_test_override"] = True
        res = handle_create_primitive(bpy_module=mock_bpy, params=_host_approved("create_primitive",cyl_params))
        self.assertEqual(res["created"], True)
        self.assertEqual(res["name"], "HandlerCylinder")
        self.assertEqual(res["radius"], 1.25)
        self.assertEqual(res["depth"], 3.5)
        self.assertEqual(res["vertices"], 40)
        self.assertEqual(mock_bpy.ops.mesh.last_call[0], "cylinder")
        self.assertEqual(mock_bpy.ops.mesh.last_call[1]["radius"], 1.25)
        self.assertEqual(mock_bpy.ops.mesh.last_call[1]["depth"], 3.5)
        self.assertEqual(mock_bpy.ops.mesh.last_call[1]["vertices"], 40)

        # 3. Plane execution
        plane_params = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "plane",
            "name": "HandlerPlane",
            "size": 4.5,
        }, trusted_approval=True)
        plane_params["_trusted_test_override"] = True
        res = handle_create_primitive(bpy_module=mock_bpy, params=_host_approved("create_primitive",plane_params))
        self.assertEqual(res["created"], True)
        self.assertEqual(res["name"], "HandlerPlane")
        self.assertEqual(res["size"], 4.5)
        self.assertEqual(mock_bpy.ops.mesh.last_call[0], "plane")
        self.assertEqual(mock_bpy.ops.mesh.last_call[1]["size"], 4.5)


from tests.unit.modeling_approval_fixture import approved as _host_approved


if __name__ == "__main__":
    unittest.main()

