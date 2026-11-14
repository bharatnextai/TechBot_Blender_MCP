"""
Offline Unit Tests for Shared Schemas and Protocol Models.
Runs purely on CPU without requiring Blender or network access.
"""

import unittest
from shared.models.protocol_models import (
    BridgeCommand,
    BridgeResponse,
    SceneSummaryData,
    ObjectItemData,
    ObjectDetailsData,
    MaterialItemData,
)
from shared.schemas.tool_schemas import (
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_LIST_MATERIALS,
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_EXECUTE_BLENDER_CODE,
    validate_tool_input,
    get_all_tool_definitions,
    TOOL_DEFINITIONS,
)


class TestProtocolModels(unittest.TestCase):
    def test_bridge_command_roundtrip(self):
        cmd = BridgeCommand(command="get_scene_summary", params={"include_collections": True})
        d = cmd.to_dict()
        self.assertEqual(d["type"], "get_scene_summary")
        self.assertEqual(d["params"], {"include_collections": True})
        self.assertTrue("command_id" in d)

        # Deserialize
        cmd2 = BridgeCommand.from_dict(d)
        self.assertEqual(cmd2.command, "get_scene_summary")
        self.assertEqual(cmd2.params, {"include_collections": True})
        self.assertEqual(cmd2.command_id, cmd.command_id)

    def test_bridge_response_envelopes(self):
        # Success
        res_ok = BridgeResponse.success({"scene_name": "TestScene"}, duration_ms=12.5)
        self.assertTrue(res_ok.is_success)
        d_ok = res_ok.to_dict()
        self.assertEqual(d_ok["status"], "success")
        self.assertEqual(d_ok["result"]["scene_name"], "TestScene")
        self.assertEqual(d_ok["execution_time_ms"], 12.5)

        # Error
        res_err = BridgeResponse.error("Object not found", duration_ms=5.0)
        self.assertFalse(res_err.is_success)
        d_err = res_err.to_dict()
        self.assertEqual(d_err["status"], "error")
        self.assertEqual(d_err["message"], "Object not found")

    def test_dataclass_serializations(self):
        summary = SceneSummaryData(
            scene_name="MainScene",
            frame_current=1,
            frame_start=1,
            frame_end=250,
            fps=24,
            unit_system="METRIC",
            total_objects=3,
            object_counts_by_type={"MESH": 2, "CAMERA": 1},
            active_camera="Camera",
            active_object="Cube",
        )
        s_dict = summary.to_dict()
        self.assertEqual(s_dict["scene_name"], "MainScene")
        self.assertEqual(s_dict["total_objects"], 3)


class TestToolSchemas(unittest.TestCase):
    def test_tool_discovery_count(self):
        tools = get_all_tool_definitions()
        self.assertGreaterEqual(len(tools), 8)
        names = {t["name"] for t in tools}
        baseline_tools = {
            TOOL_GET_SCENE_SUMMARY,
            TOOL_LIST_OBJECTS,
            TOOL_GET_OBJECT_DETAILS,
            TOOL_LIST_MATERIALS,
            TOOL_CREATE_PRIMITIVE,
            TOOL_TRANSFORM_OBJECT,
            TOOL_INSPECT_SCENE_DATA,
            TOOL_EXECUTE_BLENDER_CODE,
        }
        for b_tool in baseline_tools:
            self.assertIn(b_tool, names)

    def test_validate_get_scene_summary(self):
        # Default application
        p = validate_tool_input(TOOL_GET_SCENE_SUMMARY, {})
        self.assertEqual(p, {"include_collections": True})

        # Explicit valid param
        p2 = validate_tool_input(TOOL_GET_SCENE_SUMMARY, {"include_collections": False})
        self.assertEqual(p2, {"include_collections": False})

        # Invalid type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_GET_SCENE_SUMMARY, {"include_collections": "not_a_bool"})

        # Unknown param
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_GET_SCENE_SUMMARY, {"unknown_field": 123})

    def test_validate_list_objects(self):
        # Defaults
        p = validate_tool_input(TOOL_LIST_OBJECTS, {})
        self.assertEqual(p["limit"], 100)
        self.assertEqual(p["offset"], 0)
        self.assertEqual(p["include_hidden"], True)

        # Filters
        p2 = validate_tool_input(TOOL_LIST_OBJECTS, {"object_type": "MESH", "limit": 50})
        self.assertEqual(p2["object_type"], "MESH")
        self.assertEqual(p2["limit"], 50)

        # Out-of-bounds limit
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_LIST_OBJECTS, {"limit": 0})
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_LIST_OBJECTS, {"limit": 1001})

    def test_validate_get_object_details(self):
        # Missing required 'name'
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_GET_OBJECT_DETAILS, {})

        # Empty name
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_GET_OBJECT_DETAILS, {"name": "   "})

        # Valid with defaults applied
        p = validate_tool_input(TOOL_GET_OBJECT_DETAILS, {"name": "Cube"})
        self.assertEqual(p["name"], "Cube")
        self.assertEqual(p["include_mesh_stats"], True)
        self.assertEqual(p["include_materials"], True)
        self.assertEqual(p["include_modifiers"], True)
        self.assertEqual(p["include_custom_properties"], False)

    def test_validate_list_materials(self):
        p = validate_tool_input(TOOL_LIST_MATERIALS, {"filter_name": "Gold", "limit": 20})
        self.assertEqual(p["filter_name"], "Gold")
        self.assertEqual(p["limit"], 20)
        self.assertEqual(p["offset"], 0)

    def test_validate_create_primitive_valid_approved(self):
        p = validate_tool_input(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "MyBox",
            "location": [1.0, 2.0, 3.0],
            "dimensions": [2.0, 2.0, 2.0],
        }, trusted_approval=True)
        self.assertEqual(p["primitive_type"], "cube")
        self.assertEqual(p["name"], "MyBox")
        self.assertEqual(p["location"], [1.0, 2.0, 3.0])
        self.assertEqual(p["dimensions"], [2.0, 2.0, 2.0])
        self.assertTrue(p["trusted_approval"])

    def test_validate_create_primitive_approval_denial(self):
        # Missing trusted approval raises PermissionError (read-only mode by default)
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "MyBox",
            }, trusted_approval=False)
        self.assertIn("Approval required", str(ctx.exception))

        # Explicit approved=False raises PermissionError
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "MyBox",
                "approved": False
            }, trusted_approval=False)
        self.assertIn("Approval required", str(ctx.exception))

        # Attempting to bypass approval via model-supplied approved=True is rejected as untrusted
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "MyBox",
                "approved": True
            }, trusted_approval=False)
        self.assertIn("untrusted", str(ctx.exception))

    def test_validate_create_primitive_invalid_inputs(self):
        # Invalid primitive type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "donut",
                "name": "MyBox",
            }, trusted_approval=True)

        # Empty name
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "   ",
            }, trusted_approval=True)

        # Non-numeric location
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "MyBox",
                "location": ["a", "b", "c"],
            }, trusted_approval=True)

        # Wrong location dimensions (2 instead of 3)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "MyBox",
                "location": [1.0, 2.0],
            }, trusted_approval=True)

        # Negative dimensions
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "MyBox",
                "dimensions": [-1.0, 2.0, 2.0],
            }, trusted_approval=True)


if __name__ == "__main__":
    unittest.main()

