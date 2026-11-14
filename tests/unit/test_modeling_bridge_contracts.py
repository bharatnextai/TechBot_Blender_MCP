"""Offline regressions for older/mismatched bridge response contracts."""
import unittest
from unittest.mock import Mock

from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.agents.scene_inspector import SceneInspectorAgent
from shared.models.agent_contracts import AgentTask, TaskStatus

MODELING_BRIDGE_TOOLS = (
    "edit_modifier_stack", "inspect_modifier_stack", "configure_curve_geometry", "inspect_curve_geometry",
    "configure_modeling_object", "inspect_modeling_object", "configure_modeling_geometry", "inspect_modeling_geometry",
)


class IndexedBridgeContractTests(unittest.TestCase):
    def setUp(self):
        self.executor = BlenderExecutor()
        self.executor.client = Mock()
        self.args = dict(category="mesh_topology", target_name="Cube", element_domain="vertices", limit=2)
        self.page = dict(category="mesh_topology", target_name="Cube", element_domain="vertices",
            elements=[dict(index=0, co=[0., 0., 0.])], offset=0, limit=2, total=1,
            returned=1, next_offset=None, has_more=False, coordinate_space="LOCAL",
            topology_source="BASE_MESH", mode="OBJECT", snapshot_id="sha256:"+"a"*64,
            state_id="sha256:"+"b"*64, indices_are_snapshot_local=True,
            vertex_count=1, edge_count=0, polygon_count=0, loop_count=0, returned_count=1)

    def run_page(self, page):
        self.executor.client.send_command.return_value = dict(status="success", result=page)
        return self.executor.execute_tool("inspect_scene_data", self.args)

    def test_old_count_only_success_is_failure(self):
        response = self.run_page(dict(vertex_count=8, edge_count=12, polygon_count=6))
        self.assertFalse(response.is_success)
        self.assertIn("INDEXED_TOPOLOGY_UNAVAILABLE", response.message)
        self.executor.client.send_command.assert_called_once()

    def test_legacy_bridge_page_without_returned_count_is_rejected(self):
        legacy = dict(self.page)
        legacy.pop("returned_count")
        response = self.run_page(legacy)
        self.assertFalse(response.is_success)
        self.assertIn("INDEXED_TOPOLOGY_UNAVAILABLE", response.message)

    def test_valid_indexed_page_and_empty_page(self):
        self.assertTrue(self.run_page(self.page).is_success)
        page = dict(self.page, elements=[], total=0, returned=0, returned_count=0, vertex_count=0)
        self.assertTrue(self.run_page(page).is_success)

    def test_malformed_or_mismatched_pages_fail(self):
        for change in [dict(snapshot_id="bad"), dict(element_domain="faces"),
                dict(topology_source="EVALUATED_MESH"), dict(mode="EDIT"),
                dict(returned=2), dict(offset=1), dict(limit=3), dict(total=2),
                dict(returned_count=2),
                dict(elements=[dict(index=0, co=[float("nan"), 0, 0])]),
                dict(elements=[dict(index=1, co=[0, 0, 0])]), dict(has_more=True)]:
            with self.subTest(change=change):
                self.assertFalse(self.run_page(dict(self.page, **change)).is_success)

    def test_snapshot_binding_is_verified(self):
        self.args["expected_snapshot_id"] = "sha256:"+"c"*64
        self.assertFalse(self.run_page(self.page).is_success)

    def test_count_only_compatibility(self):
        self.args.pop("element_domain")
        response = self.run_page(dict(vertex_count=8))
        self.assertTrue(response.is_success)
        self.assertEqual(response.result, dict(vertex_count=8))

    def test_inspector_task_cannot_pass_old_response(self):
        self.executor.client.send_command.return_value = dict(status="success", result=dict(vertex_count=8))
        task = AgentTask(task_id="indexed", required_capability="scene.inspection", task_type="inspect_scene_data", input_params=self.args)
        response = SceneInspectorAgent().execute_task(task, self.executor)
        self.assertEqual(response.status, TaskStatus.FAILED)
        self.assertEqual(response.verification.status, "FAIL")

    def test_inspector_verifies_vertex_edge_and_face_records(self):
        cases = (
            ("vertices", [dict(index=0, co=[0., 0., 0.])], dict(vertex_count=1, edge_count=0, polygon_count=0)),
            ("edges", [dict(index=0, vertices=[0, 1])], dict(vertex_count=2, edge_count=1, polygon_count=0)),
            ("faces", [dict(index=0, vertices=[0, 1, 2])], dict(vertex_count=3, edge_count=3, polygon_count=1)),
        )
        for domain, elements, counts in cases:
            with self.subTest(domain=domain):
                args = dict(category="mesh_topology", target_name="Cube", element_domain=domain, limit=2)
                total = counts[{"vertices": "vertex_count", "edges": "edge_count", "faces": "polygon_count"}[domain]]
                result = dict(self.page, element_domain=domain, elements=elements, total=total,
                    returned=1, returned_count=1, next_offset=None, has_more=False, **counts)
                result.update(category="mesh_topology", target_name="Cube")
                self.executor.client.send_command.return_value = dict(status="success", result=result)
                task = AgentTask(task_id="indexed-valid", required_capability="scene.inspection",
                    task_type="inspect_scene_data", input_params=args)
                observed = SceneInspectorAgent().execute_task(task, self.executor)
                self.assertEqual(observed.status, TaskStatus.SUCCEEDED)
                self.assertEqual(observed.verification.status, "PASS")
                self.assertEqual(observed.verification.observed_results["returned_count"], 1)
                self.assertEqual(observed.verification.observed_results["snapshot_id"], result["snapshot_id"])

    def test_inspector_rejects_missing_returned_count_and_stale_snapshot(self):
        for change in ("missing_returned_count", "stale_snapshot"):
            with self.subTest(change=change):
                args = dict(self.args, expected_snapshot_id="sha256:"+"a"*64)
                result = dict(self.page)
                if change == "missing_returned_count":
                    result.pop("returned_count")
                else:
                    result["snapshot_id"] = "sha256:"+"c"*64
                self.executor.client.send_command.return_value = dict(status="success", result=result)
                task = AgentTask(task_id="indexed-invalid", required_capability="scene.inspection",
                    task_type="inspect_scene_data", input_params=args)
                observed = SceneInspectorAgent().execute_task(task, self.executor)
                self.assertEqual(observed.status, TaskStatus.FAILED)
                self.assertEqual(observed.verification.status, "FAIL")

    def test_connectivity_and_evaluated_pages(self):
        for domain, key, indices in [("edges", "edge_count", [0, 1]), ("faces", "polygon_count", [0, 1, 2])]:
            self.args["element_domain"] = domain
            page = dict(self.page, element_domain=domain, vertex_count=3,
                elements=[dict(index=0, vertices=indices)], **{key: 1})
            self.assertTrue(self.run_page(page).is_success)
            page["elements"][0]["vertices"] = [0, 99]
            self.assertFalse(self.run_page(page).is_success)
        self.args.update(element_domain="vertices", mesh_source="evaluated")
        self.assertTrue(self.run_page(dict(self.page, topology_source="EVALUATED_MESH")).is_success)


class ModelingHandlerParityTests(unittest.TestCase):
    def test_source_registry_and_queue_have_all_eight_handlers(self):
        from blender_addon.universal_mcp.bridge.handlers import ALL_HANDLERS, READ_ONLY_HANDLERS
        from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
        from mcp_service.registry.tool_registry import ToolRegistry
        registry, queue = ToolRegistry(), MainThreadQueue()
        for tool in MODELING_BRIDGE_TOOLS:
            with self.subTest(tool=tool):
                self.assertTrue(registry.has_tool(tool))
                self.assertIs(queue._handlers[tool], ALL_HANDLERS[tool])
                self.assertEqual(tool in READ_ONLY_HANDLERS, tool.startswith("inspect_"))

    def test_older_bridge_has_actionable_failure_without_retry(self):
        for tool in MODELING_BRIDGE_TOOLS:
            if not tool.startswith("inspect_"):
                continue
            with self.subTest(tool=tool):
                executor = BlenderExecutor()
                executor.client = Mock()
                executor.client.send_command.return_value = dict(status="error", message=f"Unknown command: '{tool}'. Available handlers: []")
                args = dict(name="Cube")
                if tool == "inspect_modeling_geometry":
                    args["modifier_name"] = "GeometryNodes"
                response = executor.execute_tool(tool, args)
                self.assertFalse(response.is_success)
                self.assertIn("BRIDGE_CAPABILITY_UNAVAILABLE", response.message)
                self.assertIn(tool, response.message)
                self.assertIn("loaded add-on", response.message)
                executor.client.send_command.assert_called_once()

    def test_unrelated_bridge_errors_remain_unchanged(self):
        executor = BlenderExecutor()
        executor.client = Mock()
        executor.client.send_command.return_value = dict(status="error", message="Object not found")
        response = executor.execute_tool("inspect_modeling_object", dict(name="Cube"))
        self.assertEqual(response.message, "Object not found")

