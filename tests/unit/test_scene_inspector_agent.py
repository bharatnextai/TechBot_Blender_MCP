"""
Unit and Integration Tests for TASK-UMCP-0016 (Phase 3):
Scene Inspector Agent & Verified Read-Only Integration.

Validates:
- Manifest and explicit read-only capability registration.
- Routing through Agent Manager, AgentRegistry, and CapabilityRouter.
- Successful execution across all verified read-only inspection tools:
  get_scene_summary, list_objects, get_object_details, list_materials, inspect_scene_data.
- Full coverage of all 7 inspect_scene_data categories.
- Factual evidence references without hallucinating scene state.
- Differentiation of empty results, unavailable data, unsupported requests, and inspection errors.
- Strict read-only invariants: rejection of mutation tools, rejection of model-supplied approved=True.
- Dispatcher integration and verification tracking.
- Zero regressions in existing 8 MCP tools and schemas.
"""

import unittest
from typing import Dict, Any, Optional, List

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
    VerificationResult,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_LIST_MATERIALS,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_EXECUTE_BLENDER_CODE,
    TOOL_DEFINITIONS,
    ALLOWED_INSPECT_CATEGORIES,
)
from mcp_service.agents.scene_inspector import (
    SceneInspectorAgent,
    create_scene_inspector_manifest,
    SCENE_INSPECTOR_AGENT_ID,
    SCENE_INSPECTION_CAPABILITY_ID,
    SUPPORTED_INSPECTION_TOOLS,
)
from mcp_service.agents.registry import AgentRegistry, create_default_registry
from mcp_service.agents.manager import AgentManager
from mcp_service.agents.session_coordinator import SessionCoordinator
from mcp_service.agents.dispatcher import AgentDispatcher, DispatchResult
from mcp_service.execution.blender_executor import BlenderExecutor


class MockInspectorExecutor(BlenderExecutor):
    """
    Mock BlenderExecutor that tracks tool calls and returns realistic,
    evidence-based Blender data structures without modifying any state.
    """

    def __init__(self):
        self.invocations: List[tuple] = []
        self.mutation_invoked = False
        self.scene_objects = [
            {"name": "Camera", "type": "CAMERA"},
            {"name": "Light", "type": "LIGHT"},
            {"name": "Dragon_Asset", "type": "MESH"},
            {"name": "Coffer_Asset", "type": "MESH"},
        ]
        self.materials = [
            {"name": "Gold_Material"},
            {"name": "Stone_Material"},
        ]

    def is_connected(self) -> bool:
        return True

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        trusted_approval: Optional[bool] = None,
    ) -> BridgeResponse:
        self.invocations.append((tool_name, arguments, trusted_approval))
        args = dict(arguments or {})

        # Track any mutation invocation attempt
        if tool_name in (TOOL_CREATE_PRIMITIVE, TOOL_TRANSFORM_OBJECT, TOOL_EXECUTE_BLENDER_CODE):
            self.mutation_invoked = True
            return BridgeResponse.error(f"Mutation tool '{tool_name}' invoked on mock executor.")

        if tool_name == TOOL_GET_SCENE_SUMMARY:
            return BridgeResponse.success({
                "scene_name": "ProductionScene",
                "total_objects": len(self.scene_objects),
                "collections": ["Master Collection", "Hero Assets"],
            })

        elif tool_name == TOOL_LIST_OBJECTS:
            obj_type = args.get("object_type")
            if obj_type:
                matched = [o for o in self.scene_objects if o["type"] == obj_type.upper()]
            else:
                matched = list(self.scene_objects)
            return BridgeResponse.success({
                "total_matching": len(matched),
                "objects": matched,
            })

        elif tool_name == TOOL_GET_OBJECT_DETAILS:
            target = args.get("name") or args.get("target_name")
            found = next((o for o in self.scene_objects if o["name"] == target), None)
            if not found:
                return BridgeResponse.error(f"Object '{target}' not found in active scene.")
            return BridgeResponse.success({
                "name": found["name"],
                "type": found["type"],
                "location": [1.0, 2.0, 3.0],
                "rotation_euler": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
            })

        elif tool_name == TOOL_LIST_MATERIALS:
            return BridgeResponse.success({
                "total_materials": len(self.materials),
                "materials": self.materials,
            })

        elif tool_name == TOOL_INSPECT_SCENE_DATA:
            cat = args.get("category")
            target = args.get("target_name")

            if cat == "scene_summary":
                return BridgeResponse.success({
                    "category": "scene_summary",
                    "scene_name": "ProductionScene",
                    "total_objects": len(self.scene_objects),
                })
            elif cat == "mesh_topology":
                if target not in [o["name"] for o in self.scene_objects]:
                    return BridgeResponse.error(f"Target object '{target}' not found for mesh_topology.")
                return BridgeResponse.success({
                    "category": "mesh_topology",
                    "target_name": target,
                    "vertex_count": 500,
                    "polygon_count": 450,
                    "edge_count": 950,
                })
            elif cat == "object_modifiers":
                return BridgeResponse.success({
                    "category": "object_modifiers",
                    "target_name": target,
                    "modifiers": [
                        {"name": "Subsurf", "type": "SUBSURF", "render_levels": 2},
                    ],
                })
            elif cat == "object_materials":
                return BridgeResponse.success({
                    "category": "object_materials",
                    "target_name": target,
                    "materials": [{"slot": 0, "material": "Gold_Material"}],
                })
            elif cat == "scene_hierarchy":
                return BridgeResponse.success({
                    "category": "scene_hierarchy",
                    "hierarchy": [{"name": "Master Collection", "objects": ["Camera", "Light"]}],
                })
            elif cat == "collection_tree":
                return BridgeResponse.success({
                    "category": "collection_tree",
                    "collections": [{"name": "Hero Assets", "children": []}],
                })
            elif cat == "world_settings":
                return BridgeResponse.success({
                    "category": "world_settings",
                    "has_world": True,
                    "name": "StudioWorld",
                    "use_nodes": True,
                    "color": [0.05, 0.05, 0.05],
                })
            elif cat == "render_settings":
                return BridgeResponse.success({
                    "category": "render_settings",
                    "engine": "BLENDER_EEVEE_NEXT",
                    "resolution_x": 1920,
                    "resolution_y": 1080,
                    "resolution_percentage": 100,
                    "frame_start": 1,
                    "frame_end": 250,
                    "fps": 24,
                    "fps_base": 1.0,
                    "output_format": "PNG",
                    "output_path": "//render/",
                    "active_camera": "Camera",
                })
            elif cat == "blender_info":
                return BridgeResponse.success({
                    "category": "blender_info",
                    "version": "5.2.2",
                    "is_saved": False,
                    "is_dirty": False,
                    "file_status": "unsaved",
                    "filepath": None,
                    "raw_filepath": "",
                })
            elif cat == "uv_layers":
                return BridgeResponse.success({
                    "category": "uv_layers", "target_name": target,
                    "uv_layer_count": 1, "active_layer": "UVMap",
                    "uv_layers": [{"index": 0, "name": "UVMap", "active": True,
                                   "active_render": True, "loop_count": 24}],
                })
            elif cat == "render_result":
                return BridgeResponse.success({
                    "category": "render_result", "image_exists": False,
                    "available": False, "has_data": False,
                    "width": 0, "height": 0, "channels": 0,
                })
            elif cat == "compositor_pipeline":
                return BridgeResponse.success({
                    "category": "compositor_pipeline",
                    "use_nodes": False,
                    "nodes_count": 0,
                    "links_count": 0,
                })
            elif cat == "physics_settings":
                return BridgeResponse.success({
                    "category": "physics_settings",
                    "target_name": target,
                    "has_physics": False,
                })
            elif cat == "compositor_settings":
                return BridgeResponse.success({
                    "category": "compositor_settings",
                    "use_nodes": False,
                })
            elif cat == "animation_data":
                return BridgeResponse.success({
                    "category": "animation_data",
                    "target_name": target,
                    "has_animation": False,
                    "fcurves_count": 0,
                })
            else:
                return BridgeResponse.error(f"Category '{cat}' not supported.")

        return BridgeResponse.error(f"Unknown mock tool: {tool_name}")


class TestSceneInspectorManifestAndRegistry(unittest.TestCase):
    """Validates Scene Inspector manifest, capabilities, and registry discovery."""

    def test_manifest_structure(self):
        manifest = create_scene_inspector_manifest(version="0.1.9")
        manifest.validate()
        self.assertEqual(manifest.agent_id, SCENE_INSPECTOR_AGENT_ID)
        self.assertEqual(manifest.version, "0.1.9")
        self.assertEqual(len(manifest.capabilities), 2)

        caps = {c.capability_id: c for c in manifest.capabilities}
        self.assertIn(SCENE_INSPECTION_CAPABILITY_ID, caps)
        self.assertIn("visual.capture", caps)

        for cap in manifest.capabilities:
            self.assertEqual(cap.read_write, "READ_ONLY")
            self.assertEqual(cap.verification_status, "VERIFIED")

        # Input schemas must be populated
        for tool in SUPPORTED_INSPECTION_TOOLS:
            self.assertIn(tool, manifest.input_schemas)

    def test_registry_discovery(self):
        registry = create_default_registry()
        inspector = registry.get_agent(SCENE_INSPECTOR_AGENT_ID)
        self.assertIsNotNone(inspector)
        self.assertEqual(inspector.version, "0.1.13")

        # Discover by capability
        agents = registry.find_agents_by_capability(SCENE_INSPECTION_CAPABILITY_ID)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].agent_id, SCENE_INSPECTOR_AGENT_ID)

        # Discover by individual inspection task types
        for tool in SUPPORTED_INSPECTION_TOOLS:
            cap = registry.find_capability_by_task_type(tool)
            self.assertIsNotNone(cap, f"Capability not found for tool {tool}")
            expected_cap_id = "visual.capture" if tool == "capture_viewport" else SCENE_INSPECTION_CAPABILITY_ID
            self.assertEqual(cap.capability_id, expected_cap_id)
            self.assertEqual(cap.read_write, "READ_ONLY")

    def test_routing_via_agent_manager(self):
        manager = AgentManager()
        task = AgentTask(
            task_id="inspect-001",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_SCENE_SUMMARY,
        )
        res = manager.route_task(task, require_verified=True)
        self.assertTrue(res.success)
        self.assertEqual(res.agent.agent_id, SCENE_INSPECTOR_AGENT_ID)
        self.assertEqual(res.capability.read_write, "READ_ONLY")


class TestSceneInspectorAgentExecution(unittest.TestCase):
    """Validates SceneInspectorAgent read-only execution, evidence references, and error differentiation."""

    def setUp(self):
        self.agent = SceneInspectorAgent(version="0.1.9")
        self.executor = MockInspectorExecutor()

    def test_world_bridge_contract_empty_and_nonempty(self):
        from tests.unit.test_inspect_scene_data import MockBpy
        from blender_addon.universal_mcp.bridge.handlers import handle_inspect_scene_data
        from unittest.mock import Mock
        bpy = MockBpy()
        world = bpy.context.scene.world
        for present, nodes in ((False, False), (True, True), (True, False)):
            with self.subTest(present=present, nodes=nodes):
                world.use_nodes = nodes
                bpy.context.scene.world = world if present else None
                raw = handle_inspect_scene_data(bpy, {"category": "world_settings"})
                executor = Mock()
                executor.execute_tool.return_value = BridgeResponse.success(raw)
                task = AgentTask(task_id="world-contract", required_capability=SCENE_INSPECTION_CAPABILITY_ID,
                                 task_type=TOOL_INSPECT_SCENE_DATA, input_params={"category": "world_settings"})
                result = self.agent.execute_task(task, executor)
                self.assertEqual(result.status, TaskStatus.SUCCEEDED, result.errors)
                self.assertEqual(result.output["is_empty"], not present)
                self.assertEqual(f"world:{world.name}" in result.evidence_references, present)

    def test_get_scene_summary_structured_result(self):
        task = AgentTask(
            task_id="t-summary",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_SCENE_SUMMARY,
        )
        result = self.agent.execute_task(task, self.executor)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertFalse(result.output["is_empty"])
        self.assertEqual(result.output["scene_name"], "ProductionScene")
        self.assertEqual(result.output["total_objects"], 4)
        self.assertIn("scene:ProductionScene", result.evidence_references)
        self.assertIn("objects_total:4", result.evidence_references)
        self.assertEqual(result.verification.status, "PASS")

    def test_get_scene_summary_empty_scene(self):
        # Empty scene mock
        empty_executor = MockInspectorExecutor()
        empty_executor.scene_objects = []
        task = AgentTask(
            task_id="t-summary-empty",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_SCENE_SUMMARY,
        )
        result = self.agent.execute_task(task, empty_executor)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertTrue(result.output["is_empty"])
        self.assertEqual(result.output["total_objects"], 0)
        self.assertEqual(result.verification.observed_results["is_empty"], True)

    def test_list_objects_and_empty_query(self):
        # Query with matches
        task1 = AgentTask(
            task_id="t-list-1",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_LIST_OBJECTS,
            input_params={"object_type": "MESH"},
        )
        result1 = self.agent.execute_task(task1, self.executor)
        self.assertEqual(result1.status, TaskStatus.SUCCEEDED)
        self.assertFalse(result1.output["is_empty"])
        self.assertEqual(result1.output["total_matching"], 2)
        self.assertIn("object:Dragon_Asset:MESH", result1.evidence_references)
        self.assertIn("object:Coffer_Asset:MESH", result1.evidence_references)

        # Query with 0 matches (Empty result, NOT an error)
        task2 = AgentTask(
            task_id="t-list-2",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_LIST_OBJECTS,
            input_params={"object_type": "CURVE"},
        )
        result2 = self.agent.execute_task(task2, self.executor)
        self.assertEqual(result2.status, TaskStatus.SUCCEEDED)
        self.assertTrue(result2.output["is_empty"])
        self.assertEqual(result2.output["total_matching"], 0)
        self.assertEqual(result2.verification.status, "PASS")

    def test_get_object_details_found_and_not_found(self):
        # Object found
        task_found = AgentTask(
            task_id="t-details-1",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_OBJECT_DETAILS,
            input_params={"name": "Dragon_Asset"},
        )
        result_found = self.agent.execute_task(task_found, self.executor)
        self.assertEqual(result_found.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result_found.output["name"], "Dragon_Asset")
        self.assertIn("object:Dragon_Asset", result_found.evidence_references)
        self.assertIn("location:[1.0, 2.0, 3.0]", result_found.evidence_references)

        # Object not found -> DATA_UNAVAILABLE (FAILED with specific unavailable flag)
        task_missing = AgentTask(
            task_id="t-details-2",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_OBJECT_DETAILS,
            input_params={"name": "NonExistentObject"},
        )
        result_missing = self.agent.execute_task(task_missing, self.executor)
        self.assertEqual(result_missing.status, TaskStatus.FAILED)
        self.assertIn("not found", result_missing.errors[0].lower())
        self.assertEqual(result_missing.verification.status, "FAIL")
        self.assertTrue(result_missing.verification.observed_results["data_unavailable"])

    def test_list_materials(self):
        task = AgentTask(
            task_id="t-mats",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_LIST_MATERIALS,
        )
        result = self.agent.execute_task(task, self.executor)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertFalse(result.output["is_empty"])
        self.assertEqual(result.output["total_materials"], 2)
        self.assertIn("material:Gold_Material", result.evidence_references)
        self.assertIn("material:Stone_Material", result.evidence_references)

    def test_inspect_scene_data_all_allowed_categories(self):
        for cat in ALLOWED_INSPECT_CATEGORIES:
            task = AgentTask(
                task_id=f"t-inspect-{cat}",
                required_capability=SCENE_INSPECTION_CAPABILITY_ID,
                task_type=TOOL_INSPECT_SCENE_DATA,
                input_params={"category": cat, "target_name": "Dragon_Asset"},
            )
            result = self.agent.execute_task(task, self.executor)
            self.assertEqual(
                result.status,
                TaskStatus.SUCCEEDED,
                f"Category '{cat}' inspection failed: {result.errors}",
            )
            self.assertIn(f"category:{cat}", result.evidence_references)
            self.assertEqual(result.output["inspection_scope"]["category"], cat)

    def test_inspect_scene_data_unsupported_category_rejected(self):
        task = AgentTask(
            task_id="t-invalid-cat",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_INSPECT_SCENE_DATA,
            input_params={"category": "unsupported_shader_graph"},
        )
        result = self.agent.execute_task(task, self.executor)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("Unsupported inspect_scene_data category", result.errors[0])
        self.assertFalse(self.executor.invocations)  # Not sent to executor

    def test_strictly_rejects_mutation_tools(self):
        """SceneInspectorAgent must reject mutation tools and NEVER invoke executor."""
        mutations = [
            (TOOL_CREATE_PRIMITIVE, {"primitive_type": "CUBE"}),
            (TOOL_TRANSFORM_OBJECT, {"name": "Dragon_Asset", "location": [0, 0, 0]}),
            (TOOL_EXECUTE_BLENDER_CODE, {"operation": "delete_object"}),
        ]
        for tool, params in mutations:
            task = AgentTask(
                task_id=f"t-mutation-{tool}",
                required_capability=SCENE_INSPECTION_CAPABILITY_ID,
                task_type=tool,
                input_params=params,
            )
            result = self.agent.execute_task(task, self.executor)
            self.assertEqual(result.status, TaskStatus.FAILED)
            self.assertIn("Permission denied", result.errors[0])
            self.assertIn("strictly read-only", result.errors[0])

        # Confirm zero mutation calls reached executor
        self.assertFalse(self.executor.mutation_invoked)


class TestSceneInspectorDispatcherIntegration(unittest.TestCase):
    """Validates routing and dispatching Scene Inspector tasks through AgentDispatcher."""

    def setUp(self):
        self.executor = MockInspectorExecutor()
        self.coordinator = SessionCoordinator()
        self.manager = AgentManager()
        self.dispatcher = AgentDispatcher(
            manager=self.manager,
            coordinator=self.coordinator,
            executor=self.executor,
        )

    def test_dispatch_scene_summary_via_dispatcher(self):
        task = AgentTask(
            task_id="disp-task-001",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_SCENE_SUMMARY,
        )
        res: DispatchResult = self.dispatcher.dispatch_task(task)
        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.agent_id, SCENE_INSPECTOR_AGENT_ID)
        self.assertEqual(res.result["scene_name"], "ProductionScene")
        self.assertIsNotNone(res.verification)
        self.assertEqual(res.verification.status, "PASS")

    def test_dispatch_tool_call_backward_compatibility(self):
        resp: BridgeResponse = self.dispatcher.dispatch_tool_call(
            TOOL_LIST_OBJECTS,
            {"object_type": "MESH"},
        )
        self.assertTrue(resp.is_success)
        self.assertEqual(resp.result["total_matching"], 2)
        self.assertEqual(len(resp.result["objects"]), 2)
        # Verify enriched observations are available
        self.assertIn("observed_data", resp.result)
        self.assertIn("inspection_scope", resp.result)

    def test_dispatch_data_unavailable_error_categorization(self):
        task = AgentTask(
            task_id="disp-task-missing",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_OBJECT_DETAILS,
            input_params={"name": "Unknown_Asset"},
        )
        res: DispatchResult = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "DATA_UNAVAILABLE")

    def test_dispatch_unsupported_category_categorization(self):
        task = AgentTask(
            task_id="disp-task-bad-cat",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_INSPECT_SCENE_DATA,
            input_params={"category": "non_existent_category"},
        )
        res: DispatchResult = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "UNSUPPORTED_REQUEST")

    def test_model_supplied_approved_true_rejected_at_dispatcher_level(self):
        """Model attempting to supply approved=True must be rejected regardless of read-only/mutation."""
        task = AgentTask(
            task_id="disp-security-001",
            required_capability=SCENE_INSPECTION_CAPABILITY_ID,
            task_type=TOOL_GET_SCENE_SUMMARY,
            input_params={"approved": True},
        )
        res: DispatchResult = self.dispatcher.dispatch_task(task)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertIn("Approval denied", res.message)
        # Executor must not be invoked
        self.assertFalse(self.executor.invocations)

    def test_no_mutation_executed_under_scene_inspector(self):
        """Routing guarantees mutations are not dispatched through SceneInspectorAgent."""
        # A primitive creation task routed via dispatcher routes to agent.modeling, NOT scene inspector
        task = AgentTask(
            task_id="disp-mutation-check",
            required_capability="modeling.primitive",
            task_type=TOOL_CREATE_PRIMITIVE,
            input_params={"primitive_type": "CUBE"},
        )
        # Without approval, it must pause in AWAITING_APPROVAL without executing
        res: DispatchResult = self.dispatcher.dispatch_task(task)
        self.assertEqual(res.agent_id, "agent.modeling")
        self.assertEqual(res.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(res.error_code, "APPROVAL_REQUIRED")
        self.assertFalse(self.executor.mutation_invoked)


class TestMCPToolsAndSchemasRegression(unittest.TestCase):
    """Confirms all 8 baseline MCP tools and schemas remain registered and backward-compatible."""

    EXPECTED_TOOLS = [
        "get_scene_summary",
        "list_objects",
        "get_object_details",
        "list_materials",
        "create_primitive",
        "transform_object",
        "inspect_scene_data",
        "execute_blender_code",
    ]

    def test_all_eight_tools_registered(self):
        self.assertGreaterEqual(len(TOOL_DEFINITIONS), 8)
        for tool in self.EXPECTED_TOOLS:
            self.assertIn(tool, TOOL_DEFINITIONS, f"Tool '{tool}' missing from TOOL_DEFINITIONS")

    def test_all_tool_schemas_valid(self):
        for tool, definition in TOOL_DEFINITIONS.items():
            self.assertIn("name", definition)
            self.assertIn("description", definition)
            self.assertIn("input_schema", definition)
            schema = definition["input_schema"]
            self.assertEqual(schema["type"], "object")
            self.assertIn("properties", schema)


if __name__ == "__main__":
    unittest.main()
