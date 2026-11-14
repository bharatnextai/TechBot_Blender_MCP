"""
Unit Tests for TASK-UMCP-0030: Runtime Workflow Result Binding.

Validates:
- Deterministic reference resolution helper (resolve_task_references)
- Successful scalar, nested-dictionary, and list-index resolution
- Missing source result, failed/approval-pending prerequisite, missing field,
  invalid index, out-of-bounds index, null traversal, and incompatible type rejection
- Undeclared dependency, malformed reference, and shorthand syntax rejection
- Original task input immutability
- Secret redaction in binding traces
- Resolution occurring before schema validation and authorization
- Forged approved=True rejection after runtime resolution
- Zero tool/executor invocation upon binding failure
- Downstream task skipping in dispatch_plan following binding failure
- Regression preservation for tasks with no references
"""

import copy
import unittest
from typing import Dict, Any, Optional

from shared.models.agent_contracts import (
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
    TaskOutputRef,
)
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.registry import create_default_registry
from mcp_service.agents.router import CapabilityRouter
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.manager import AgentManager
from mcp_service.agents.session_coordinator import SessionCoordinator
from mcp_service.agents.dispatcher import (
    AgentDispatcher,
    DispatchResult,
    BindingResolutionError,
    resolve_task_references,
    is_sensitive_key,
)
from mcp_service.execution.blender_executor import BlenderExecutor
from mcp_service.security.approval import ApprovalManager


class MockBindingExecutor(BlenderExecutor):
    """In-memory mock executor tracking invocations for runtime binding tests."""

    def __init__(self):
        self.invocations = []
        self.approval_manager = ApprovalManager()

    def is_connected(self) -> bool:
        return True

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        trusted_approval: Optional[bool] = None,
    ) -> BridgeResponse:
        self.invocations.append((tool_name, dict(arguments or {}), trusted_approval))

        # Check approval requirements
        if self.approval_manager.requires_approval(tool_name):
            if trusted_approval is False:
                return BridgeResponse.error(f"Approval denied: trusted_approval was False for '{tool_name}'")
            if trusted_approval is not True:
                return BridgeResponse.error(f"Approval required: Scene mutation '{tool_name}' requires approval.")

        if tool_name == "get_scene_summary":
            return BridgeResponse.success({
                "scene_name": "Scene_Main",
                "total_objects": 2,
                "objects": [{"name": "Cube_A"}, {"name": "Light_B"}],
            })
        elif tool_name == "create_primitive":
            name = (arguments or {}).get("name", "GeneratedPrimitive")
            return BridgeResponse.success({
                "name": name,
                "created": True,
                "dimensions": [2.0, 2.0, 2.0],
            })
        elif tool_name == "transform_object":
            return BridgeResponse.success({
                "name": (arguments or {}).get("name", "Unknown"),
                "transformed": True,
            })
        return BridgeResponse.success({"status": "ok", "tool": tool_name})


class TestRuntimeReferenceResolutionHelper(unittest.TestCase):
    """Direct unit tests for the resolve_task_references helper function."""

    def setUp(self):
        self.upstream_result = AgentResult(
            task_id="task_upstream",
            status=TaskStatus.SUCCEEDED,
            output={
                "primitive_name": "BaseCube",
                "dimensions": [2.0, 4.0, 6.0],
                "details": {
                    "vertex_count": 8,
                    "active": True,
                    "metadata": {
                        "category": "mesh",
                        "tags": ["solid", "test"],
                    },
                },
                "nested_list": [
                    {"sub_id": "sub_0", "val": 10},
                    {"sub_id": "sub_1", "val": 20},
                ],
                "secret_token": "super_secret_auth_token_xyz",
            },
        )
        self.session_results = {"task_upstream": self.upstream_result}

    def test_resolve_scalar_string_number_boolean(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name", "type": "string"}},
                "height": {"$ref": {"task_id": "task_upstream", "path": "dimensions.1", "type": "number"}},
                "is_active": {"$ref": {"task_id": "task_upstream", "path": "details.active", "type": "boolean"}},
                "count": {"$ref": {"task_id": "task_upstream", "path": "details.vertex_count", "type": "integer"}},
            },
        )
        resolved, traces = resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(resolved["name"], "BaseCube")
        self.assertEqual(resolved["height"], 4.0)
        self.assertIs(resolved["is_active"], True)
        self.assertEqual(resolved["count"], 8)
        self.assertEqual(len(traces), 4)

    def test_resolve_nested_dictionary_and_list_index(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "sub_val": {"$ref": {"task_id": "task_upstream", "path": "nested_list.1.val", "type": "integer"}},
                "meta": {"$ref": {"task_id": "task_upstream", "path": "details.metadata", "type": "object"}},
                "tags": {"$ref": {"task_id": "task_upstream", "path": "details.metadata.tags", "type": "array"}},
            },
        )
        resolved, traces = resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(resolved["sub_val"], 20)
        self.assertEqual(resolved["meta"], {"category": "mesh", "tags": ["solid", "test"]})
        self.assertEqual(resolved["tags"], ["solid", "test"])

    def test_resolve_with_direct_task_output_ref_instance(self):
        ref_obj = TaskOutputRef(task_id="task_upstream", path="primitive_name", expected_type="string")
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={"target": ref_obj},
        )
        resolved, traces = resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(resolved["target"], "BaseCube")

    def test_expected_type_checking_fail_on_bool_for_int(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "count": {"$ref": {"task_id": "task_upstream", "path": "details.active", "type": "integer"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "TYPE_MISMATCH")

    def test_expected_type_checking_fail_on_str_for_number(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "size": {"$ref": {"task_id": "task_upstream", "path": "primitive_name", "type": "number"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "TYPE_MISMATCH")

    def test_fail_missing_source_result(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results={})
        self.assertEqual(ctx.exception.error_code, "PREREQUISITE_NOT_SUCCEEDED")

    def test_fail_prerequisite_awaiting_approval(self):
        self.upstream_result.status = TaskStatus.AWAITING_APPROVAL
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "PREREQUISITE_NOT_SUCCEEDED")

    def test_fail_prerequisite_failed(self):
        self.upstream_result.status = TaskStatus.FAILED
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "PREREQUISITE_NOT_SUCCEEDED")

    def test_fail_prerequisite_null_output(self):
        self.upstream_result.output = None
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "DATA_UNAVAILABLE")

    def test_fail_missing_field(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "missing": {"$ref": {"task_id": "task_upstream", "path": "details.non_existent"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "FIELD_NOT_FOUND")

    def test_fail_invalid_list_index(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "item": {"$ref": {"task_id": "task_upstream", "path": "nested_list.not_an_index"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "INVALID_INDEX")

    def test_fail_index_out_of_bounds(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "item": {"$ref": {"task_id": "task_upstream", "path": "nested_list.99"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "INDEX_OUT_OF_BOUNDS")

    def test_fail_null_traversal(self):
        self.upstream_result.output["null_container"] = None
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "item": {"$ref": {"task_id": "task_upstream", "path": "null_container.child"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "NULL_TRAVERSAL")

    def test_fail_undeclared_dependency(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=[],  # No declared dependency on task_upstream!
            input_params={
                "name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "UNDECLARED_DEPENDENCY")

    def test_fail_malformed_reference(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "name": {"$ref": "not_a_dictionary"},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "MALFORMED_REFERENCE")

    def test_fail_shorthand_syntax_rejected(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "name": "$ref:task_upstream.primitive_name",
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=self.session_results)
        self.assertEqual(ctx.exception.error_code, "UNSUPPORTED_SYNTAX")

    def test_input_params_immutability(self):
        original_inputs = {
            "name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name"}},
            "nested": [{"$ref": {"task_id": "task_upstream", "path": "dimensions.0"}}],
        }
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params=copy.deepcopy(original_inputs),
        )
        resolved, traces = resolve_task_references(task, session_results=self.session_results)

        # Confirm original input_params is completely intact
        self.assertEqual(task.input_params, original_inputs)
        # Confirm resolved params has concrete resolved values
        self.assertEqual(resolved["name"], "BaseCube")
        self.assertEqual(resolved["nested"], [2.0])

    def test_secret_redaction_in_audit_trace(self):
        task = AgentTask(
            task_id="task_downstream",
            required_capability="modeling.primitive",
            dependencies=["task_upstream"],
            input_params={
                "auth_token": {"$ref": {"task_id": "task_upstream", "path": "secret_token", "type": "string"}},
                "cube_name": {"$ref": {"task_id": "task_upstream", "path": "primitive_name", "type": "string"}},
            },
        )
        resolved, traces = resolve_task_references(task, session_results=self.session_results)

        # Concrete parameter retains the real value for executor
        self.assertEqual(resolved["auth_token"], "super_secret_auth_token_xyz")
        self.assertEqual(resolved["cube_name"], "BaseCube")

        # But audit traces must redact secrets
        token_trace = next(t for t in traces if t["param_path"] == "auth_token")
        name_trace = next(t for t in traces if t["param_path"] == "cube_name")

        self.assertTrue(token_trace["is_redacted"])
        self.assertEqual(token_trace["resolved_value"], "[REDACTED]")

        self.assertFalse(name_trace["is_redacted"])
        self.assertEqual(name_trace["resolved_value"], "BaseCube")


class TestRuntimeReferenceDispatchPipeline(unittest.TestCase):
    """Integration tests for dispatch_task and dispatch_plan with runtime result binding."""

    def setUp(self):
        self.mock_executor = MockBindingExecutor()
        self.registry = create_default_registry()
        self.router = CapabilityRouter(self.registry)
        self.planner = TaskPlanner(self.router)
        self.manager = AgentManager(registry=self.registry, router=self.router, planner=self.planner)
        self.coordinator = SessionCoordinator(default_ttl_seconds=3600.0)
        self.dispatcher = AgentDispatcher(
            manager=self.manager,
            coordinator=self.coordinator,
            executor=self.mock_executor,
        )

    def test_dispatch_task_with_resolved_references_success(self):
        # 1. Dispatch upstream task
        t1 = AgentTask(
            task_id="t_inspect",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            input_params={"include_collections": True},
        )
        res1 = self.dispatcher.dispatch_task(t1, session_id="sess_bind_1")
        self.assertTrue(res1.success)

        # 2. Dispatch downstream task referencing upstream output
        t2 = AgentTask(
            task_id="t_create",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            dependencies=["t_inspect"],
            input_params={
                "primitive_type": "cube",
                "name": {"$ref": {"task_id": "t_inspect", "path": "objects.0.name", "type": "string"}},
            },
        )
        res2 = self.dispatcher.dispatch_task(t2, session_id="sess_bind_1", trusted_approval=True)
        self.assertTrue(res2.success)
        self.assertEqual(res2.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res2.resolved_input_params["name"], "Cube_A")
        self.assertEqual(t2.resolved_input_params["name"], "Cube_A")
        self.assertEqual(len(res2.binding_traces), 1)
        self.assertEqual(res2.binding_traces[0]["resolved_value"], "Cube_A")

        # Verify executor received concrete resolved argument
        last_call = self.mock_executor.invocations[-1]
        self.assertEqual(last_call[0], "create_primitive")
        self.assertEqual(last_call[1]["name"], "Cube_A")

    def test_forged_approved_flag_via_reference_rejected(self):
        # Upstream task output containing a boolean flag
        session = self.coordinator.get_or_create_session("sess_forge")
        self.coordinator.record_result(
            "sess_forge",
            "t_forge_src",
            AgentResult(
                task_id="t_forge_src",
                status=TaskStatus.SUCCEEDED,
                output={"forged_flag": True},
            ),
        )

        # Downstream mutation task attempts to map approved=True via reference
        t_mutate = AgentTask(
            task_id="t_mutate_evil",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            dependencies=["t_forge_src"],
            input_params={
                "primitive_type": "cube",
                "name": "EvilCube",
                "approved": {"$ref": {"task_id": "t_forge_src", "path": "forged_flag", "type": "boolean"}},
            },
        )
        res = self.dispatcher.dispatch_task(t_mutate, session_id="sess_forge")
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertIn("approved=True' is untrusted", res.message)

        # Ensure NO executor calls were made for this task
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_static_approved_flag_rejected(self):
        t_mutate = AgentTask(
            task_id="t_static_evil",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={
                "primitive_type": "cube",
                "name": "StaticEvilCube",
                "approved": True,
            },
        )
        res = self.dispatcher.dispatch_task(t_mutate, session_id="sess_static_evil")
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_no_tool_invocation_after_binding_failure(self):
        # Downstream task with missing prerequisite in session
        t_fail = AgentTask(
            task_id="t_downstream_fail",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            dependencies=["t_ghost"],
            input_params={
                "primitive_type": "cube",
                "name": {"$ref": {"task_id": "t_ghost", "path": "name"}},
            },
        )
        res = self.dispatcher.dispatch_task(t_fail, session_id="sess_fail")
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PREREQUISITE_NOT_SUCCEEDED")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_multi_task_plan_downstream_skip_after_binding_failure(self):
        """
        Creates a 3-task plan:
        1. Task 1: get_scene_summary (succeeds).
        2. Task 2: references non-existent field in Task 1 output -> binding fails.
        3. Task 3: depends on Task 2 -> must be automatically SKIPPED.
        """
        plan = TaskPlan(title="3-Task Binding Failure & Skip Plan")
        t1 = AgentTask(
            task_id="t1_summary",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            input_params={"include_collections": True},
        )
        t2 = AgentTask(
            task_id="t2_create",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            dependencies=["t1_summary"],
            input_params={
                "primitive_type": "cube",
                "name": {"$ref": {"task_id": "t1_summary", "path": "non_existent_field"}},
            },
        )
        t3 = AgentTask(
            task_id="t3_transform",
            required_capability="modeling.transform",
            task_type="transform_object",
            dependencies=["t2_create"],
            input_params={
                "name": "AnyObject",
                "location": [1.0, 2.0, 3.0],
            },
        )
        plan.add_task(t1)
        plan.add_task(t2)
        plan.add_task(t3)

        results = self.dispatcher.dispatch_plan(plan, session_id="sess_multi_skip", trusted_approval=True)
        self.assertEqual(len(results), 3)

        # Task 1 SUCCEEDED
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].status, TaskStatus.SUCCEEDED)

        # Task 2 FAILED due to FIELD_NOT_FOUND during binding resolution
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].status, TaskStatus.FAILED)
        self.assertEqual(results[1].error_code, "FIELD_NOT_FOUND")

        # Task 3 automatically SKIPPED with UPSTREAM_FAILURE
        self.assertFalse(results[2].success)
        self.assertEqual(results[2].status, TaskStatus.SKIPPED)
        self.assertEqual(results[2].error_code, "UPSTREAM_FAILURE")

        # Verify only Task 1 was actually executed on the bridge/executor
        self.assertEqual(len(self.mock_executor.invocations), 1)
        self.assertEqual(self.mock_executor.invocations[0][0], "get_scene_summary")

    def test_preserve_existing_behavior_for_tasks_without_references(self):
        task = AgentTask(
            task_id="task_static",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            input_params={"include_collections": False},
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_plain")
        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(res.resolved_input_params, {"include_collections": False})
        self.assertEqual(res.binding_traces, [])


class TestRuntimeBindingSecurityReview(unittest.TestCase):
    """
    Focused security regression tests for TASK-UMCP-0031.
    Verifies the 6 key security review dimensions:
    1. Approval and authorization bypass rejection (nested, alternate names, forged tokens)
    2. Zero secret leakage across traces, error messages, serialized models, and logs
    3. State consistency and multi-level downstream failure skipping
    4. Session isolation, duplicate dispatch, and retry freshness
    5. Fail-closed handling of malformed paths, unvalidated refs, and ambiguous types
    6. Absolute zero-invocation guarantee across all binding failure codes
    """

    def setUp(self):
        self.mock_executor = MockBindingExecutor()
        self.registry = create_default_registry()
        self.router = CapabilityRouter(self.registry)
        self.planner = TaskPlanner(self.router)
        self.manager = AgentManager(registry=self.registry, router=self.router, planner=self.planner)
        self.coordinator = SessionCoordinator(default_ttl_seconds=3600.0)
        self.dispatcher = AgentDispatcher(
            manager=self.manager,
            coordinator=self.coordinator,
            executor=self.mock_executor,
        )

    # -------------------------------------------------------------------------
    # Dimension 1: Authorization & Approval Bypass Resistance
    # -------------------------------------------------------------------------

    def test_untrusted_trusted_approval_flag_rejected(self):
        """Passing trusted_approval=True inside task.input_params is rejected with PERMISSION_DENIED."""
        task = AgentTask(
            task_id="t_bypass_trusted",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={"primitive_type": "cube", "name": "BypassCube", "trusted_approval": True},
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_sec_1")
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_untrusted_trusted_approval_via_reference_rejected(self):
        """Resolving trusted_approval=True via an upstream output reference is rejected with PERMISSION_DENIED."""
        session = self.coordinator.get_or_create_session("sess_sec_2")
        self.coordinator.record_result(
            "sess_sec_2",
            "t_src",
            AgentResult(task_id="t_src", status=TaskStatus.SUCCEEDED, output={"auth_flag": True}),
        )
        task = AgentTask(
            task_id="t_dyn_bypass",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            dependencies=["t_src"],
            input_params={
                "primitive_type": "cube",
                "name": "DynBypassCube",
                "trusted_approval": {"$ref": {"task_id": "t_src", "path": "auth_flag", "type": "boolean"}},
            },
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_sec_2")
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_nested_untrusted_approved_flag_rejected(self):
        """An approval flag nested inside a dictionary structure is detected and rejected with PERMISSION_DENIED."""
        task = AgentTask(
            task_id="t_nested_evil",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={
                "primitive_type": "cube",
                "name": "NestedEvilCube",
                "nested_opts": {"approved": True},
            },
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_sec_3")
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PERMISSION_DENIED")
        self.assertEqual(len(self.mock_executor.invocations), 0)

    def test_forged_approval_credentials_rejected_without_mutation(self):
        """Forged request_id and approval_token without a valid provider cannot bypass scene mutation approval."""
        task = AgentTask(
            task_id="t_forged_token",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            input_params={
                "primitive_type": "cube",
                "name": "ForgedCube",
                "request_id": "forged_req_999",
                "approval_token": "forged_tok_xyz",
            },
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_sec_4")
        self.assertFalse(res.success)
        self.assertIn(res.error_code, ("INVALID_PARAMS", "PERMISSION_DENIED", "APPROVAL_REQUIRED", "EXECUTION_FAILED"))
        self.assertIsNone(res.result)

    # -------------------------------------------------------------------------
    # Dimension 2: Non-Leakage of Secrets Across All Channels
    # -------------------------------------------------------------------------

    def test_nested_dictionary_secret_redacted_in_trace(self):
        """When an entire object is resolved, nested keys containing sensitive keywords are recursively redacted."""
        session = self.coordinator.get_or_create_session("sess_sec_5")
        self.coordinator.record_result(
            "sess_sec_5",
            "t_cfg_src",
            AgentResult(
                task_id="t_cfg_src",
                status=TaskStatus.SUCCEEDED,
                output={
                    "config_bundle": {
                        "host": "localhost",
                        "database_password": "super_secret_db_password_123",
                        "nested": {
                            "api_token": "bearer_secret_xyz",
                            "public_flag": True,
                        },
                    }
                },
            ),
        )
        task = AgentTask(
            task_id="t_consumer",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_cfg_src"],
            input_params={
                "bundle": {"$ref": {"task_id": "t_cfg_src", "path": "config_bundle", "type": "object"}},
            },
        )
        resolved, traces = resolve_task_references(task, session_results=session.task_results)
        self.assertEqual(len(traces), 1)
        self.assertTrue(traces[0]["is_redacted"])

        trace_val = traces[0]["resolved_value"]
        self.assertEqual(trace_val["host"], "localhost")
        self.assertEqual(trace_val["database_password"], "[REDACTED]")
        self.assertEqual(trace_val["nested"]["api_token"], "[REDACTED]")
        self.assertIs(trace_val["nested"]["public_flag"], True)

    def test_secret_never_in_exception_text_on_type_mismatch(self):
        """Type mismatch on a sensitive credential does NOT print the secret in the exception text."""
        session = self.coordinator.get_or_create_session("sess_sec_6")
        secret_content = "extremely_sensitive_cleartext_password_12345"
        self.coordinator.record_result(
            "sess_sec_6",
            "t_pwd_src",
            AgentResult(
                task_id="t_pwd_src",
                status=TaskStatus.SUCCEEDED,
                output={"user_password": secret_content},
            ),
        )
        task = AgentTask(
            task_id="t_pwd_consumer",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_pwd_src"],
            input_params={
                "auth_password": {"$ref": {"task_id": "t_pwd_src", "path": "user_password", "type": "integer"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=session.task_results)
        self.assertEqual(ctx.exception.error_code, "TYPE_MISMATCH")
        self.assertNotIn(secret_content, str(ctx.exception))
        self.assertNotIn(secret_content, ctx.exception.message)

    def test_secret_never_in_exception_text_on_invalid_traversal(self):
        """Attempting invalid traversal on a secret string scalar does NOT leak the secret in the error."""
        session = self.coordinator.get_or_create_session("sess_sec_7")
        secret_content = "private_key_pem_header_xyz987"
        self.coordinator.record_result(
            "sess_sec_7",
            "t_key_src",
            AgentResult(
                task_id="t_key_src",
                status=TaskStatus.SUCCEEDED,
                output={"private_key": secret_content},
            ),
        )
        task = AgentTask(
            task_id="t_key_consumer",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_key_src"],
            input_params={
                "cert_part": {"$ref": {"task_id": "t_key_src", "path": "private_key.invalid_subfield"}},
            },
        )
        with self.assertRaises(BindingResolutionError) as ctx:
            resolve_task_references(task, session_results=session.task_results)
        self.assertEqual(ctx.exception.error_code, "INVALID_TRAVERSAL")
        self.assertNotIn(secret_content, str(ctx.exception))
        self.assertNotIn(secret_content, ctx.exception.message)

    def test_secret_never_in_serialized_agent_result(self):
        """Serialized task results (AgentResult.to_dict()) never contain resolved parameters."""
        session = self.coordinator.get_or_create_session("sess_sec_8")
        secret_content = "secret_session_token_777"
        self.coordinator.record_result(
            "sess_sec_8",
            "t_tok_src",
            AgentResult(
                task_id="t_tok_src",
                status=TaskStatus.SUCCEEDED,
                output={"secret_token": secret_content},
            ),
        )
        task = AgentTask(
            task_id="t_fail_consumer",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_tok_src"],
            input_params={
                "secret_token": {"$ref": {"task_id": "t_tok_src", "path": "secret_token", "type": "integer"}},
            },
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_sec_8")
        self.assertFalse(res.success)
        task_dict = task.to_dict()
        agent_res_dict = task_dict["result"]
        self.assertNotIn(secret_content, str(agent_res_dict))
        self.assertIsNone(task.resolved_input_params)
        self.assertIsNone(res.resolved_input_params)

    # -------------------------------------------------------------------------
    # Dimension 3: Consistent Task & Session State & Downstream Skipping
    # -------------------------------------------------------------------------

    def test_multi_level_dependency_chain_skipped_on_binding_failure(self):
        """A failure in task A causes dependent task B and downstream task C to be automatically SKIPPED."""
        plan = TaskPlan(title="3-Level Skip Plan")
        t_a = AgentTask(
            task_id="t_a",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            input_params={"include_collections": True},
        )
        t_b = AgentTask(
            task_id="t_b",
            required_capability="modeling.primitive",
            task_type="create_primitive",
            dependencies=["t_a"],
            input_params={
                "primitive_type": "cube",
                "name": {"$ref": {"task_id": "t_a", "path": "non_existent_field"}},
            },
        )
        t_c = AgentTask(
            task_id="t_c",
            required_capability="modeling.transform",
            task_type="transform_object",
            dependencies=["t_b"],
            input_params={"name": "ObjectC", "location": [0.0, 1.0, 2.0]},
        )
        plan.add_task(t_a)
        plan.add_task(t_b)
        plan.add_task(t_c)

        results = self.dispatcher.dispatch_plan(plan, session_id="sess_chain_skip", trusted_approval=True)
        self.assertEqual(len(results), 3)

        self.assertEqual(results[0].status, TaskStatus.SUCCEEDED)
        self.assertEqual(results[1].status, TaskStatus.FAILED)
        self.assertEqual(results[1].error_code, "FIELD_NOT_FOUND")
        self.assertEqual(results[2].status, TaskStatus.SKIPPED)
        self.assertEqual(results[2].error_code, "UPSTREAM_FAILURE")

        self.assertEqual(len(self.mock_executor.invocations), 1)

    # -------------------------------------------------------------------------
    # Dimension 4: Session Isolation & Retries
    # -------------------------------------------------------------------------

    def test_cross_session_isolation_cannot_resolve_other_session(self):
        """Task in sess_B cannot resolve upstream task from sess_A even with valid task_id."""
        sess_a = self.coordinator.get_or_create_session("sess_A")
        self.coordinator.record_result(
            "sess_A",
            "t_shared_id",
            AgentResult(task_id="t_shared_id", status=TaskStatus.SUCCEEDED, output={"val": 42}),
        )

        task_b = AgentTask(
            task_id="t_b",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_shared_id"],
            input_params={"target": {"$ref": {"task_id": "t_shared_id", "path": "val"}}},
        )
        res = self.dispatcher.dispatch_task(task_b, session_id="sess_B")
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PREREQUISITE_NOT_SUCCEEDED")

    def test_resumed_session_prerequisite_rerun_failure_rejects_downstream(self):
        """If a prerequisite previously succeeded but was rerun and failed, downstream task fails closed."""
        session_id = "sess_rerun"
        # 1. Prerequisite succeeds
        self.coordinator.record_result(
            session_id,
            "t_prereq",
            AgentResult(task_id="t_prereq", status=TaskStatus.SUCCEEDED, output={"val": 100}),
        )
        # 2. Prerequisite is rerun and fails
        self.coordinator.record_result(
            session_id,
            "t_prereq",
            AgentResult(task_id="t_prereq", status=TaskStatus.FAILED, errors=["Prerequisite rerun crashed"]),
        )
        # 3. Downstream task attempts resolution
        downstream = AgentTask(
            task_id="t_dependent",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_prereq"],
            input_params={"target": {"$ref": {"task_id": "t_prereq", "path": "val"}}},
        )
        res = self.dispatcher.dispatch_task(downstream, session_id=session_id)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertEqual(res.error_code, "PREREQUISITE_NOT_SUCCEEDED")

    # -------------------------------------------------------------------------
    # Dimension 5: Fail-Closed Malformed & Ambiguous Traversal
    # -------------------------------------------------------------------------

    def test_unvalidated_task_output_ref_with_invalid_path_fails_closed(self):
        """Constructing an unvalidated TaskOutputRef with an invalid path fails closed during dispatch."""
        ref = TaskOutputRef(task_id="t_src", path="invalid--path..segment")
        task = AgentTask(
            task_id="t_mal",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_src"],
            input_params={"arg": ref},
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_mal")
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "MALFORMED_REFERENCE")

    def test_traversal_on_boolean_scalar_fails_closed(self):
        """Attempting to traverse into a boolean scalar fails closed with INVALID_TRAVERSAL."""
        session = self.coordinator.get_or_create_session("sess_bool_trav")
        self.coordinator.record_result(
            "sess_bool_trav",
            "t_src",
            AgentResult(task_id="t_src", status=TaskStatus.SUCCEEDED, output={"flag": True}),
        )
        task = AgentTask(
            task_id="t_consumer",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_src"],
            input_params={"arg": {"$ref": {"task_id": "t_src", "path": "flag.subfield"}}},
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_bool_trav")
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "INVALID_TRAVERSAL")

    def test_float_and_negative_index_on_list_fails_closed(self):
        """List traversal with non-digit segments (e.g. '-1' or '1.0') fails closed with INVALID_INDEX."""
        session = self.coordinator.get_or_create_session("sess_idx_fail")
        self.coordinator.record_result(
            "sess_idx_fail",
            "t_src",
            AgentResult(task_id="t_src", status=TaskStatus.SUCCEEDED, output={"items": ["a", "b"]}),
        )
        task = AgentTask(
            task_id="t_consumer",
            required_capability="scene.inspection",
            task_type="get_scene_summary",
            dependencies=["t_src"],
            input_params={"arg": {"$ref": {"task_id": "t_src", "path": "items.-1"}}},
        )
        res = self.dispatcher.dispatch_task(task, session_id="sess_idx_fail")
        self.assertFalse(res.success)
        self.assertIn(res.error_code, ("INVALID_INDEX", "MALFORMED_REFERENCE"))

    # -------------------------------------------------------------------------
    # Dimension 6: Absolute Zero-Invocation Guarantee
    # -------------------------------------------------------------------------

    def test_zero_executor_invocations_on_all_binding_failures(self):
        """Verifies that across diverse binding failure causes, zero executor invocations occur."""
        session_id = "sess_zero_invocations"
        session = self.coordinator.get_or_create_session(session_id)
        self.coordinator.record_result(
            session_id,
            "t_src_ok",
            AgentResult(task_id="t_src_ok", status=TaskStatus.SUCCEEDED, output={"valid_key": "val"}),
        )

        failure_cases = [
            # Undeclared dependency
            {"dependencies": [], "params": {"p": {"$ref": {"task_id": "t_src_ok", "path": "valid_key"}}}},
            # Missing prerequisite
            {"dependencies": ["t_nonexistent"], "params": {"p": {"$ref": {"task_id": "t_nonexistent", "path": "valid_key"}}}},
            # Field not found
            {"dependencies": ["t_src_ok"], "params": {"p": {"$ref": {"task_id": "t_src_ok", "path": "missing_field"}}}},
            # Type mismatch
            {"dependencies": ["t_src_ok"], "params": {"p": {"$ref": {"task_id": "t_src_ok", "path": "valid_key", "type": "integer"}}}},
            # Unsupported shorthand syntax
            {"dependencies": ["t_src_ok"], "params": {"p": "$ref:t_src_ok.valid_key"}},
        ]

        for idx, case in enumerate(failure_cases):
            task = AgentTask(
                task_id=f"t_fail_{idx}",
                required_capability="scene.inspection",
                task_type="get_scene_summary",
                dependencies=case["dependencies"],
                input_params=case["params"],
            )
            res = self.dispatcher.dispatch_task(task, session_id=session_id)
            self.assertFalse(res.success)
            self.assertEqual(res.status, TaskStatus.FAILED)
            self.assertEqual(
                len(self.mock_executor.invocations),
                0,
                f"Executor was unexpectedly invoked for failure case {idx}: {case}",
            )

    def test_dispatch_plan_all_tasks_succeed_transitions_plan_to_succeeded(self):
        """When all tasks in dispatch_plan succeed, plan transitions to RUNNING then SUCCEEDED without ValueError."""
        plan = TaskPlan(title="Plan All Succeeded")
        t1 = AgentTask("t1", "scene.inspection", "get_scene_summary", input_params={"include_collections": False})
        t2 = AgentTask(
            "t2",
            "modeling.primitive",
            "create_primitive",
            dependencies=["t1"],
            input_params={
                "primitive_type": "cube",
                "name": {"$ref": {"task_id": "t1", "path": "scene_name", "type": "string"}},
            },
        )
        plan.add_task(t1)
        plan.add_task(t2)

        results = self.dispatcher.dispatch_plan(plan, session_id="sess_all_ok", trusted_approval=True)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].success)
        self.assertTrue(results[1].success)
        self.assertEqual(results[0].status, TaskStatus.SUCCEEDED)
        self.assertEqual(results[1].status, TaskStatus.SUCCEEDED)
        self.assertEqual(plan.status, TaskStatus.SUCCEEDED)
        self.assertEqual(len(results[1].binding_traces), 1)
        self.assertEqual(results[1].binding_traces[0]["resolved_value"], "Scene_Main")


if __name__ == "__main__":
    unittest.main()
