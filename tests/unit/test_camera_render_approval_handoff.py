"""Provider -> pending binding -> registry approval -> original task resume."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from tests.unit.test_blender_material_approval_resumption import _FakeBlenderBridge
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from mcp_service.agents.dispatcher import AgentDispatcher
from mcp_service.agents.render_lighting import RenderLightingAgent
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.security.approval import ApprovalManager, ApprovalDecision
from shared.models.agent_contracts import AgentTask, TaskStatus
from shared.schemas.tool_schemas import validate_tool_input
import tests.unit.test_scoped_test_policy as isolation


class RenderBridge(_FakeBlenderBridge):
    def __init__(self, registry):
        super().__init__(registry); self.executions = []; self.fail_with = None; self.receipt = None
    def send_command(self, command, params):
        if command in ("create_camera", "render_scene"):
            ok, reason = self.registry.consume_approval(params.get("request_id"), params.get("approval_token"), command, params)
            if not ok:
                return {"status": "error", "message": reason}
            self.executions.append((command, dict(params)))
            if self.fail_with:
                return {"status": "error", "message": self.fail_with}
            result = {"name": params["name"], "lens": params.get("lens", 50)} if command == "create_camera" else {"rendered": True, "output_file": params["output_path"], "render_id": "a"*32,
                "operator_completed": True, "width": 64, "height": 64, "frame": 1, "camera": "Camera"}
            if command == "render_scene":
                self.receipt = {"success": True, "verified": True, "render_id": "a"*32, "width": 64, "height": 64,
                    "frame": 1, "camera": "Camera", "file_format": "PNG", "artifact": {"path": params["output_path"],
                    "sha256": "b"*64, "size_bytes": 100, "width": 64, "height": 64, "png_structure_verified": True}}
            return {"status": "success", "result": result}
        if command == "inspect_render_output":
            return {"status": "success", "result": self.receipt}
        if command == "list_objects":
            return {"status": "success", "result": {"objects": [{"name": args["name"], "type": "CAMERA"} for tool, args in self.executions if tool == "create_camera"]}}
        return super().send_command(command, params)


class CameraRenderHandoffTests(unittest.TestCase):
    def test_policy_accepts_schema_normalized_format_without_widening_paths(self):
        fixture = isolation.TestFixtureLedger(); self.addCleanup(fixture.doCleanups); fixture.setUp()
        params = validate_tool_input("render_scene", {"render_mode": "still", "output_format": "PNG",
            "output_path": str(fixture.root / "fresh.png")}, trusted_approval=True)
        params.pop("trusted_approval", None); params.pop("approved", None)
        self.assertEqual(params["output_format"], "png")
        self.assertTrue(fixture.allowed("render_scene", params))
        (fixture.root / "fresh.png").touch()
        self.assertFalse(fixture.allowed("render_scene", params))
    def environment(self):
        registry = ApprovalRegistry(); bridge = RenderBridge(registry)
        executor = BlenderExecutor(timeout=.001); executor.client = bridge
        executor.enable_blender_approval(timeout=.001, pending_ttl=30)
        return registry, bridge, AgentDispatcher(executor=executor)

    def start(self, dispatcher, tool):
        args = {"name": "ApprovalCamera", "lens": 42} if tool == "create_camera" else {"render_mode": "still", "output_path": "unit-test-render.png", "output_format": "PNG"}
        task = AgentTask(task_id="task-"+tool, session_id="render-session", required_capability="lighting.manage" if tool == "create_camera" else "world.manage", task_type=tool, input_params=args)
        result = dispatcher.dispatch_task(task, session_id="render-session")
        self.assertEqual(result.status, TaskStatus.AWAITING_APPROVAL)
        pending = result.result["pending_approval"]
        self.assertTrue(pending["approval_request_id"])
        return pending

    def resolve(self, dispatcher, pending):
        return dispatcher.resolve_pending_approval(task_id=pending["task_id"], session_id=pending["session_id"],
            decision="approved", nonce=pending["nonce"], param_hash=pending["param_hash"])

    def test_pending_is_inspectable_and_credentials_alone_cannot_approve(self):
        for tool in ("create_camera", "render_scene"):
            with self.subTest(tool=tool):
                registry, bridge, dispatcher = self.environment(); pending = self.start(dispatcher, tool)
                self.assertEqual(self.resolve(dispatcher, pending).status, TaskStatus.AWAITING_APPROVAL)
                self.assertEqual(bridge.executions, [])
                self.assertEqual(registry.get_request(pending["approval_request_id"]).status, "pending")

    def test_human_registry_approval_resumes_original_task_once(self):
        for tool in ("create_camera", "render_scene"):
            with self.subTest(tool=tool):
                registry, bridge, dispatcher = self.environment(); pending = self.start(dispatcher, tool)
                self.assertTrue(registry.resolve_request(pending["approval_request_id"], "approved")[0])
                result = self.resolve(dispatcher, pending)
                self.assertTrue(result.success, result.message)
                self.assertEqual(result.task_id, pending["task_id"])
                self.assertEqual(result.status, TaskStatus.SUCCEEDED)
                self.assertEqual(len(bridge.executions), 1)
                self.assertTrue(registry.get_request(pending["approval_request_id"]).executed)
                self.assertFalse(self.resolve(dispatcher, pending).success)
                self.assertEqual(len(bridge.executions), 1)

    def test_denial_expiry_invalid_token_and_execution_error_fail_closed(self):
        for mode in ("denied", "expired", "invalid_token", "execution_error"):
            with self.subTest(mode=mode):
                registry, bridge, dispatcher = self.environment(); pending = self.start(dispatcher, "create_camera")
                req = registry.get_request(pending["approval_request_id"])
                if mode == "denied":
                    registry.resolve_request(req.request_id, "denied")
                elif mode == "expired":
                    req.created_at -= 1000
                else:
                    registry.resolve_request(req.request_id, "approved")
                    if mode == "invalid_token":
                        bridge.invalid_status_token = "not-a-registry-token"
                    else:
                        bridge.fail_with = "Confirmed Blender execution error"
                result = self.resolve(dispatcher, pending)
                self.assertFalse(result.success)
                self.assertEqual(result.status, TaskStatus.FAILED)
                self.assertEqual(len(bridge.executions), int(mode == "execution_error"))

    def test_boolean_provider_approval_is_not_executable_credentials(self):
        executor = NS(approval_manager=ApprovalManager(provider=lambda *args: ApprovalDecision(True, status="approved")), execute_tool=Mock())
        task = AgentTask(task_id="missing-token", required_capability="lighting.manage", task_type="create_camera", input_params={"name": "Camera"})
        result = RenderLightingAgent().execute_task(task, executor)
        self.assertEqual(result.status, TaskStatus.FAILED)
        executor.execute_tool.assert_not_called()

    def test_explicit_internal_false_does_not_call_provider(self):
        provider = Mock(return_value=ApprovalDecision(True, request_id="id", approval_token="token"))
        executor = NS(approval_manager=ApprovalManager(provider=provider), execute_tool=Mock())
        task = AgentTask(task_id="explicit-false", required_capability="lighting.manage", task_type="create_camera", input_params={"name": "Camera"})
        self.assertEqual(RenderLightingAgent().execute_task(task, executor, trusted_approval=False).status, TaskStatus.AWAITING_APPROVAL)
        provider.assert_not_called(); executor.execute_tool.assert_not_called()
