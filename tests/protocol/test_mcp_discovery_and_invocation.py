"""
Offline Protocol Tests for MCP Tool Discovery, Invocation, Validation, and Errors.
Validates official MCP SDK Server compliance with mocked Blender execution.
"""

import unittest
import asyncio
import json
from typing import Dict, Any, Optional, List

import mcp.types as types
from mcp_service.server.mcp_server import create_mcp_server
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.execution.blender_executor import BlenderExecutor
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_LIST_MATERIALS,
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_EXECUTE_BLENDER_CODE,
)



class MockBlenderExecutor(BlenderExecutor):
    """In-memory mock executor that avoids socket operations."""

    def __init__(self):
        self.invocations = []
        self.should_timeout = False
        self.should_fail = False
        from mcp_service.security.approval import ApprovalManager
        self.approval_manager = ApprovalManager()

    def is_connected(self) -> bool:
        return True

    def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> BridgeResponse:
        self.invocations.append((tool_name, arguments))

        if self.should_timeout:
            return BridgeResponse.error(f"Bridge timed out waiting for Blender response: timeout after 30s")
        if self.should_fail:
            return BridgeResponse.error("Simulated internal Blender error")

        # 1. Trusted Approval check
        is_approved, reason = self.approval_manager.verify_approval(tool_name, arguments or {})
        if not is_approved:
            return BridgeResponse.error(reason)

        # 2. Delegate validation to real schema validation
        from shared.schemas.tool_schemas import validate_tool_input
        try:
            sanitized = validate_tool_input(tool_name, arguments or {}, trusted_approval=is_approved)
        except PermissionError as pe:
            return BridgeResponse.error(f"Approval denied: {pe}")
        except ValueError as ve:
            return BridgeResponse.error(f"Parameter validation failed: {ve}")

        # Return mock scene results based on tool
        if tool_name == TOOL_GET_SCENE_SUMMARY:
            return BridgeResponse.success({
                "scene_name": "TestScene",
                "total_objects": 3,
                "active_camera": "Camera",
                "collections": ["Collection 1"] if sanitized.get("include_collections") else [],
            })
        elif tool_name == TOOL_LIST_OBJECTS:
            return BridgeResponse.success({
                "total_matching": 1,
                "objects": [{"name": "Cube", "type": sanitized.get("object_type", "MESH")}],
            })
        elif tool_name == TOOL_GET_OBJECT_DETAILS:
            return BridgeResponse.success({
                "name": sanitized["name"],
                "type": "MESH",
                "location": [0.0, 0.0, 0.0],
                "materials": ["Material_1"],
            })
        elif tool_name == TOOL_LIST_MATERIALS:
            return BridgeResponse.success({
                "total_materials": 1,
                "materials": [{"name": "Material_1", "diffuse_color": [0.8, 0.8, 0.8, 1.0]}],
            })
        elif tool_name == TOOL_CREATE_PRIMITIVE:
            if sanitized["name"] == "Cube":
                return BridgeResponse.error("Collision detected: An object named 'Cube' already exists in the scene.")
            return BridgeResponse.success({
                "created": True,
                "name": sanitized["name"],
                "type": "MESH",
                "primitive_type": sanitized["primitive_type"],
                "location": sanitized["location"],
                "dimensions": sanitized["dimensions"],
            })
        return BridgeResponse.error(f"Unhandled tool: {tool_name}")


class TestMCPDiscoveryAndInvocation(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MockBlenderExecutor()
        self.server = create_mcp_server(executor=self.mock_executor)

    def _call_list_tools(self) -> List[types.Tool]:
        handler = self.server.request_handlers[types.ListToolsRequest]
        res = asyncio.run(handler(types.ListToolsRequest()))
        return res.root.tools

    def _call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        handler = self.server.request_handlers[types.CallToolRequest]
        req = types.CallToolRequest(
            params=types.CallToolRequestParams(name=name, arguments=arguments or {})
        )
        res = asyncio.run(handler(req))
        text_content = res.root.content[0].text if res.root.content else ""
        is_error = getattr(res.root, "isError", False)
        try:
            parsed = json.loads(text_content)
            if is_error:
                parsed["status"] = "error"
            return parsed
        except Exception:
            return {"status": "error", "message": text_content, "isError": is_error}

    def test_mcp_tool_discovery_contains_all_tools(self):
        tools = self._call_list_tools()
        self.assertGreaterEqual(len(tools), 8)

        names = {t.name for t in tools}
        expected_names = {
            "check_approval_status",
            TOOL_GET_SCENE_SUMMARY,
            TOOL_LIST_OBJECTS,
            TOOL_GET_OBJECT_DETAILS,
            TOOL_LIST_MATERIALS,
            TOOL_CREATE_PRIMITIVE,
            TOOL_TRANSFORM_OBJECT,
            TOOL_INSPECT_SCENE_DATA,
            TOOL_EXECUTE_BLENDER_CODE,
        }
        for exp in expected_names:
            self.assertIn(exp, names)

        # Verify tool schemas
        for t in tools:
            self.assertTrue(bool(t.description))
            self.assertIsInstance(t.inputSchema, dict)
            self.assertEqual(t.inputSchema.get("type"), "object")

    def test_initialization_metadata_attributes_creator_and_safeguards(self):
        options = self.server.create_initialization_options()
        self.assertIn("Techbot81", options.instructions)
        self.assertIn("human-approval", options.instructions)
        custom = create_mcp_server(
            executor=self.mock_executor,
            server_instructions="Maintainer-provided server instructions",
        )
        custom_options = custom.create_initialization_options()
        self.assertEqual(custom_options.instructions, "Maintainer-provided server instructions")


    def test_invoke_get_scene_summary(self):
        res = self._call_tool(TOOL_GET_SCENE_SUMMARY, {"include_collections": True})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["result"]["scene_name"], "TestScene")
        self.assertIn("Collection 1", res["result"]["collections"])

    def test_invoke_list_objects_with_filtering(self):
        res = self._call_tool(TOOL_LIST_OBJECTS, {"object_type": "MESH", "limit": 10})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["result"]["total_matching"], 1)
        self.assertEqual(res["result"]["objects"][0]["type"], "MESH")

    def test_invoke_get_object_details(self):
        res = self._call_tool(TOOL_GET_OBJECT_DETAILS, {"name": "Cube"})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["result"]["name"], "Cube")
        self.assertEqual(res["result"]["location"], [0.0, 0.0, 0.0])

    def test_invoke_list_materials(self):
        res = self._call_tool(TOOL_LIST_MATERIALS, {"limit": 50})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["result"]["total_materials"], 1)
        self.assertEqual(res["result"]["materials"][0]["name"], "Material_1")

    def test_invoke_unknown_tool_returns_error(self):
        res = self._call_tool("non_existent_tool", {})
        self.assertEqual(res["status"], "error")
        self.assertIn("Unknown tool", res["message"])

    def test_validation_missing_required_parameter(self):
        # Missing 'name' for get_object_details
        res = self._call_tool(TOOL_GET_OBJECT_DETAILS, {})
        self.assertEqual(res["status"], "error")
        self.assertTrue(
            "name" in res["message"] and ("required" in res["message"] or "Missing" in res["message"])
        )

    def test_validation_out_of_bounds_parameter(self):
        # limit < 1
        res = self._call_tool(TOOL_LIST_OBJECTS, {"limit": 0})
        self.assertEqual(res["status"], "error")
        self.assertTrue("minimum" in res["message"] or ">= 1" in res["message"])

        # limit > 1000
        res2 = self._call_tool(TOOL_LIST_OBJECTS, {"limit": 5000})
        self.assertEqual(res2["status"], "error")
        self.assertTrue("maximum" in res2["message"] or "<= 1000" in res2["message"])

    def test_timeout_error_handling(self):
        self.mock_executor.should_timeout = True
        res = self._call_tool(TOOL_GET_SCENE_SUMMARY, {})
        self.assertEqual(res["status"], "error")
        self.assertIn("timed out", res["message"])

    def test_execution_failure_handling(self):
        self.mock_executor.should_fail = True
        res = self._call_tool(TOOL_GET_SCENE_SUMMARY, {})
        self.assertEqual(res["status"], "error")
        self.assertIn("Simulated internal Blender error", res["message"])

    def test_invoke_create_primitive_missing_approval(self):
        # Default state: no trusted provider configured
        res = self._call_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "Box1",
            "location": [0.0, 0.0, 0.0],
            "dimensions": [1.0, 1.0, 1.0],
        })
        self.assertEqual(res["status"], "error")
        self.assertIn("Approval required", res["message"])

    def test_invoke_create_primitive_denied_approval(self):
        # Trusted provider explicitly denies
        self.mock_executor.approval_manager.set_provider(lambda tool, params: False)
        res = self._call_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "Box1",
            "location": [0.0, 0.0, 0.0],
            "dimensions": [1.0, 1.0, 1.0],
        })
        self.assertEqual(res["status"], "error")
        self.assertIn("Approval denied", res["message"])

    def test_invoke_create_primitive_attempt_bypass_via_arguments_rejected(self):
        # Caller supplies approved=True without trusted approval provider
        res = self._call_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "Box1",
            "location": [0.0, 0.0, 0.0],
            "dimensions": [1.0, 1.0, 1.0],
            "approved": True,
        })
        self.assertEqual(res["status"], "error")
        self.assertIn("Approval denied", res["message"])
        self.assertIn("untrusted", res["message"])

    def test_invoke_create_primitive_approved_success(self):
        # Trusted provider explicitly approves
        self.mock_executor.approval_manager.set_provider(lambda tool, params: True)
        res = self._call_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "Box1",
            "location": [1.0, 2.0, 3.0],
            "dimensions": [1.5, 1.5, 1.5],
        })
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["result"]["created"])
        self.assertEqual(res["result"]["name"], "Box1")
        self.assertEqual(res["result"]["location"], [1.0, 2.0, 3.0])
        self.assertEqual(res["result"]["dimensions"], [1.5, 1.5, 1.5])

    def test_invoke_create_primitive_name_collision(self):
        # Approved, but name "Cube" exists in mock scene
        self.mock_executor.approval_manager.set_provider(lambda tool, params: True)
        res = self._call_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "Cube",
        })
        self.assertEqual(res["status"], "error")
        self.assertIn("Collision detected", res["message"])

    def test_invoke_create_primitive_invalid_input(self):
        # Approved, but invalid primitive type fails schema validation
        self.mock_executor.approval_manager.set_provider(lambda tool, params: True)
        res = self._call_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "invalid_type",
            "name": "BoxX",
        })
        self.assertEqual(res["status"], "error")
        self.assertTrue("validation" in res["message"].lower() or "invalid_type" in res["message"])



if __name__ == "__main__":
    unittest.main()

