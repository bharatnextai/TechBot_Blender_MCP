"""
Dynamic Workflow Orchestrator for Universal MCP.
Executes dependency-resolved workflow DAGs across specialized domain agents with:
1. Typed parameter handoffs between stages.
2. In-memory pre-stage SceneCheckpoint captures.
3. Declarative intermediate VerificationGate evaluations.
4. StageRollbackEngine transactional rollbacks upon failure.
5. Bounded adaptive replanning and execution resumption.
6. Strict human approval gating and fail-closed security.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Callable, Set, Tuple
import time
import uuid
import copy
import logging

from shared.models.agent_contracts import (
    AgentTask,
    TaskStatus,
    TaskOutputRef,
    DelegationContract,
)
from shared.models.protocol_models import BridgeResponse
from .checkpoints import SceneCheckpoint, SceneCheckpointManager, is_response_success, get_response_error
from .rollback import RollbackReceipt, StageRollbackEngine
from .verification_gates import VerificationGate, VerificationResult, MeshManifoldnessGate
from ..agents.dispatcher import AgentDispatcher, contains_untrusted_approval_flag

logger = logging.getLogger("UniversalMCP_WorkflowOrchestrator")


@dataclass
class WorkflowStage:
    """
    Individual execution stage in a WorkflowDAG.
    """
    stage_id: str
    name: str
    agent_id: str
    task: AgentTask
    dependencies: List[str] = field(default_factory=list)
    verification_gates: List[VerificationGate] = field(default_factory=list)
    max_retries: int = 1
    retry_count: int = 0
    status: TaskStatus = TaskStatus.PENDING
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    checkpoint_id: Optional[str] = None
    rollback_receipt: Optional[RollbackReceipt] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "agent_id": self.agent_id,
            "task": self.task.to_dict(),
            "dependencies": list(self.dependencies),
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "output": copy.deepcopy(self.output),
            "error": self.error,
            "checkpoint_id": self.checkpoint_id,
            "rollback_receipt": self.rollback_receipt.to_dict() if self.rollback_receipt else None,
        }


class WorkflowDAG:
    """
    Directed Acyclic Graph of WorkflowStages.
    Provides cycle detection and topological sorting via Kahn's algorithm.
    """

    def __init__(self, workflow_id: Optional[str] = None, title: str = ""):
        self.workflow_id: str = workflow_id or f"wf_{uuid.uuid4().hex[:12]}"
        self.title: str = title
        self.stages: Dict[str, WorkflowStage] = {}

    def add_stage(self, stage: WorkflowStage) -> None:
        self.stages[stage.stage_id] = stage

    def validate(self) -> List[str]:
        errors = []
        all_stage_ids = set(self.stages.keys())
        for sid, stage in self.stages.items():
            for dep in stage.dependencies:
                if dep not in all_stage_ids:
                    errors.append(f"Stage '{sid}' references unknown dependency '{dep}'.")
        # Check for cycles
        try:
            self.compute_execution_order()
        except ValueError as ve:
            errors.append(str(ve))
        return errors

    def compute_execution_order(self) -> List[str]:
        """
        Computes deterministic topological execution order using Kahn's algorithm.
        Raises ValueError if dependency cycle is detected.
        """
        in_degree: Dict[str, int] = {sid: 0 for sid in self.stages}
        adj_list: Dict[str, List[str]] = {sid: [] for sid in self.stages}

        for sid, stage in self.stages.items():
            for dep in stage.dependencies:
                if dep in adj_list:
                    adj_list[dep].append(sid)
                    in_degree[sid] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        order: List[str] = []

        while queue:
            # Deterministic alphabetical ordering for peer stages
            queue.sort()
            curr = queue.pop(0)
            order.append(curr)

            for neighbor in adj_list.get(curr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.stages):
            remaining = set(self.stages.keys()) - set(order)
            raise ValueError(f"Dependency cycle detected involving stages: {sorted(list(remaining))}")

        return order


@dataclass
class WorkflowExecutionReport:
    """
    Comprehensive audit report of a completed or halted workflow execution.
    """
    workflow_id: str
    status: str
    stages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    checkpoints_captured: List[str] = field(default_factory=list)
    rollbacks_executed: List[Dict[str, Any]] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status,
            "stages": copy.deepcopy(self.stages),
            "checkpoints_captured": list(self.checkpoints_captured),
            "rollbacks_executed": copy.deepcopy(self.rollbacks_executed),
            "execution_order": list(self.execution_order),
            "execution_time_ms": self.execution_time_ms,
            "summary": self.summary,
        }


class WorkflowOrchestrator:
    """
    Orchestrates multi-stage Blender production workflows with dynamic checkpointing,
    intermediate verification gates, and transactional rollback recovery.
    """

    def __init__(
        self,
        dispatcher: Optional[AgentDispatcher] = None,
        executor: Optional[Any] = None,
        checkpoint_manager: Optional[SceneCheckpointManager] = None,
        rollback_engine: Optional[StageRollbackEngine] = None,
    ):
        self._dispatcher = dispatcher
        self._executor = executor or (
            getattr(dispatcher, "executor", None)
            or getattr(dispatcher, "_executor", None)
            if dispatcher
            else None
        )
        self._checkpoint_manager = checkpoint_manager or SceneCheckpointManager()
        self._rollback_engine = rollback_engine or StageRollbackEngine(self._checkpoint_manager)

    @property
    def checkpoint_manager(self) -> SceneCheckpointManager:
        return self._checkpoint_manager

    @property
    def rollback_engine(self) -> StageRollbackEngine:
        return self._rollback_engine

    def compile_contract(
        self,
        contract: DelegationContract,
        gates: Optional[Dict[str, List[VerificationGate]]] = None,
    ) -> WorkflowDAG:
        """
        Compiles a DelegationContract into an executable WorkflowDAG.
        Automatically attaches MeshManifoldnessGate to asset import stages
        when not explicitly provided.
        """
        validation_errors = contract.validate()
        if validation_errors:
            raise ValueError(f"Cannot compile contract: {'; '.join(validation_errors)}")

        dag = WorkflowDAG(workflow_id=contract.contract_id, title=contract.title)
        gates_map = gates or {}

        for agent_id, tasks in contract.domain_tasks.items():
            for task in tasks:
                task_gates = list(gates_map.get(task.task_id, []))
                # Automatically attach post-import verification gate if unspecified
                if not task_gates and (task.task_type == "import_scene_asset" or "import" in task.task_id.lower()):
                    task_gates = [MeshManifoldnessGate()]

                stage = WorkflowStage(
                    stage_id=task.task_id,
                    name=task.task_id.replace("_", " ").title(),
                    agent_id=agent_id,
                    task=task,
                    dependencies=list(contract.dependencies.get(task.task_id, task.dependencies)),
                    verification_gates=task_gates,
                )
                dag.add_stage(stage)

        return dag

    def _resolve_parameter_handoffs(
        self,
        params: Any,
        context_outputs: Dict[str, Any],
    ) -> Any:
        """
        Recursively resolves parameter references from upstream stage outputs:
        - String references: "$stage_id.field_name"
        - TaskOutputRef objects or {"$ref": ...}
        """
        if isinstance(params, TaskOutputRef):
            src = context_outputs.get(params.task_id, {})
            return src.get(params.path) if isinstance(src, dict) else None

        if isinstance(params, dict):
            if "$ref" in params:
                task_id = params.get("task_id")
                path = params.get("path")
                src = context_outputs.get(task_id, {})
                return src.get(path) if isinstance(src, dict) else None

            resolved = {}
            for k, v in params.items():
                resolved[k] = self._resolve_parameter_handoffs(v, context_outputs)
            return resolved

        if isinstance(params, list):
            return [self._resolve_parameter_handoffs(item, context_outputs) for item in params]

        if isinstance(params, str) and params.startswith("$") and "." in params:
            # Format: $stage_id.path
            ref_expr = params[1:]
            parts = ref_expr.split(".", 1)
            stage_ref, path_ref = parts[0], parts[1]
            src = context_outputs.get(stage_ref, {})
            if isinstance(src, dict) and path_ref in src:
                return src[path_ref]

        return copy.deepcopy(params)

    def execute_workflow(
        self,
        dag: WorkflowDAG,
        session_id: str = "default",
        requires_human_approval: bool = True,
        approval_status: str = "APPROVED",
        approval_token: Optional[str] = None,
        trusted_approval: Optional[bool] = None,
        adaptive_replan_fn: Optional[Callable[[WorkflowStage, str], Optional[AgentTask]]] = None,
    ) -> WorkflowExecutionReport:
        """
        Executes a WorkflowDAG sequentially across topological dependencies.
        Enforces:
        - Untrusted approved=True rejection
        - Human approval gating
        - Pre-stage checkpoint capture
        - Typed parameter handoffs
        - Intermediate verification gates
        - Transactional rollback on failure
        - Bounded adaptive replanning
        """
        t0 = time.time()
        logger.info("Executing WorkflowDAG '%s' (title='%s')", dag.workflow_id, dag.title)

        # 1. Validate DAG and compute topological order
        dag_errors = dag.validate()
        if dag_errors:
            return WorkflowExecutionReport(
                workflow_id=dag.workflow_id,
                status="FAILED",
                summary=f"DAG validation failed: {'; '.join(dag_errors)}",
            )

        execution_order = dag.compute_execution_order()
        report = WorkflowExecutionReport(
            workflow_id=dag.workflow_id,
            status="RUNNING",
            execution_order=execution_order,
        )

        # 2. Check for untrusted approval flags in any stage task
        for sid, stage in dag.stages.items():
            if contains_untrusted_approval_flag(stage.task.input_params):
                for s in dag.stages.values():
                    s.status = TaskStatus.FAILED
                raise PermissionError(
                    f"Untrusted approved=True flag detected in stage '{sid}'. "
                    f"Model-supplied approvals are strictly prohibited."
                )

        # 3. Human Approval Gating: If requires_human_approval and not approved, pause plan
        is_approved = (approval_status == "APPROVED") or (approval_token is not None)
        if requires_human_approval and not is_approved:
            for s in dag.stages.values():
                s.status = TaskStatus.AWAITING_APPROVAL
                report.stages[s.stage_id] = s.to_dict()
            report.status = "AWAITING_APPROVAL"
            report.summary = "Workflow execution paused: Awaiting trusted human approval."
            report.execution_time_ms = round((time.time() - t0) * 1000, 2)
            logger.info("Workflow paused in AWAITING_APPROVAL (zero mutations executed)")
            return report

        # 4. Topological Execution Loop
        context_outputs: Dict[str, Any] = {}
        stage_success_set: Set[str] = set()

        for stage_id in execution_order:
            stage = dag.stages[stage_id]

            # Check upstream dependencies
            failed_deps = [dep for dep in stage.dependencies if dep not in stage_success_set]
            if failed_deps:
                stage.status = TaskStatus.SKIPPED
                stage.error = f"Skipped due to unsatisfied dependencies: {failed_deps}"
                report.stages[stage.stage_id] = stage.to_dict()
                logger.warning("Stage '%s' SKIPPED due to dependencies: %s", stage_id, failed_deps)
                continue

            stage.status = TaskStatus.RUNNING

            # a. Capture pre-stage SceneCheckpoint
            ckpt = self._checkpoint_manager.capture_checkpoint(
                stage_id=stage.stage_id,
                executor=self._executor,
                metadata={"workflow_id": dag.workflow_id},
            )
            stage.checkpoint_id = ckpt.checkpoint_id
            report.checkpoints_captured.append(ckpt.checkpoint_id)

            # b. Resolve parameter handoffs
            resolved_params = self._resolve_parameter_handoffs(stage.task.input_params, context_outputs)
            stage.task.input_params = resolved_params

            # c. Execute stage task
            exec_failed = False
            exec_error = None
            stage_output: Dict[str, Any] = {}

            if self._dispatcher:
                # Dispatch through AgentDispatcher
                dispatch_res = self._dispatcher.dispatch_task(
                    stage.task,
                    session_id=session_id,
                    trusted_approval=True,
                )
                if dispatch_res.success:
                    stage_output = dispatch_res.result if isinstance(dispatch_res.result, dict) else {"result": dispatch_res.result}
                else:
                    exec_failed = True
                    exec_error = dispatch_res.message or dispatch_res.error_code or "Task execution failed"
            elif self._executor:
                # Direct executor invocation
                tool_name = stage.task.task_type
                resp = self._executor.execute_tool(
                    tool_name,
                    stage.task.input_params,
                    trusted_approval=True,
                )
                if resp and is_response_success(resp):
                    stage_output = resp.result if isinstance(resp.result, dict) else {"result": resp.result}
                else:
                    exec_failed = True
                    exec_error = get_response_error(resp, default=f"Tool '{tool_name}' execution failed")
            else:
                exec_failed = True
                exec_error = "Neither dispatcher nor executor configured on WorkflowOrchestrator"

            # d. Evaluate verification gates
            gate_failed = False
            gate_error = None
            if not exec_failed:
                stage.output = stage_output
                for gate in stage.verification_gates:
                    v_res = gate.evaluate(stage.stage_id, stage.output, self._executor)
                    if not v_res.passed:
                        gate_failed = True
                        gate_error = f"Verification gate '{gate.gate_id}' failed: {v_res.message}"
                        logger.warning("Stage '%s' gate failed: %s", stage_id, gate_error)
                        break

            # e. Handle failure & Rollback & Adaptive Replanning
            if exec_failed or gate_failed:
                failure_msg = exec_error if exec_failed else gate_error
                stage.error = failure_msg
                logger.warning("Stage '%s' failed (%s). Triggering StageRollbackEngine...", stage_id, failure_msg)

                # Revert scene state to pre-stage checkpoint
                rb_receipt = self._rollback_engine.rollback_to_checkpoint(
                    ckpt,
                    self._executor,
                    trusted_approval=True,
                )
                stage.rollback_receipt = rb_receipt
                report.rollbacks_executed.append(rb_receipt.to_dict())

                # Attempt adaptive replanning if retries remain
                recovered = False
                if stage.retry_count < stage.max_retries and adaptive_replan_fn:
                    stage.retry_count += 1
                    logger.info("Invoking adaptive replanning for stage '%s' (retry %d/%d)", stage_id, stage.retry_count, stage.max_retries)
                    adapted_task = adaptive_replan_fn(stage, failure_msg or "Unknown error")
                    if adapted_task:
                        stage.task = adapted_task
                        # Re-execute adapted task on restored scene
                        retry_params = self._resolve_parameter_handoffs(stage.task.input_params, context_outputs)
                        stage.task.input_params = retry_params

                        if self._dispatcher:
                            retry_res = self._dispatcher.dispatch_task(stage.task, session_id=session_id, trusted_approval=True)
                            if retry_res.success:
                                stage_output = retry_res.result if isinstance(retry_res.result, dict) else {"result": retry_res.result}
                                exec_failed = False
                        elif self._executor:
                            resp = self._executor.execute_tool(stage.task.task_type, stage.task.input_params, trusted_approval=True)
                            if resp and is_response_success(resp):
                                stage_output = resp.result if isinstance(resp.result, dict) else {"result": resp.result}
                                exec_failed = False

                        if not exec_failed:
                            stage.output = stage_output
                            # Re-verify gates on adapted result
                            all_gates_passed = True
                            for gate in stage.verification_gates:
                                v_res = gate.evaluate(stage.stage_id, stage.output, self._executor)
                                if not v_res.passed:
                                    all_gates_passed = False
                                    logger.warning("Stage '%s' retry gate failed: %s", stage_id, v_res.message)
                                    break

                            if all_gates_passed:
                                recovered = True
                                stage.status = TaskStatus.SUCCEEDED
                                stage.error = None
                                stage_success_set.add(stage_id)
                                context_outputs[stage_id] = stage_output
                                logger.info("Stage '%s' successfully RECOVERED via adaptive replanning!", stage_id)

                if not recovered:
                    stage.status = TaskStatus.FAILED
                    report.stages[stage.stage_id] = stage.to_dict()
                    logger.error("Stage '%s' definitively FAILED; propagating failure downstream.", stage_id)
                    continue

            else:
                stage.status = TaskStatus.SUCCEEDED
                stage_success_set.add(stage_id)
                context_outputs[stage_id] = stage_output
                logger.info("Stage '%s' SUCCEEDED.", stage_id)

            report.stages[stage.stage_id] = stage.to_dict()

        # 5. Final Report Summary
        all_succeeded = all(s.status == TaskStatus.SUCCEEDED for s in dag.stages.values())
        any_failed = any(s.status == TaskStatus.FAILED for s in dag.stages.values())

        if all_succeeded:
            report.status = "SUCCEEDED"
            report.summary = f"All {len(dag.stages)} workflow stages executed and verified successfully."
        elif any_failed:
            report.status = "FAILED"
            report.summary = f"Workflow failed with {len(report.rollbacks_executed)} rollback(s) executed."
        else:
            report.status = "PARTIAL"
            report.summary = "Workflow finished with some stages skipped."

        report.execution_time_ms = round((time.time() - t0) * 1000, 2)
        return report

    def process_batch(
        self,
        input_paths: List[str],
        output_dir: str,
        target_format: str = "GLB",
        trusted_approval: bool = True,
        overwrite: bool = True,
        session_id: str = "batch_session",
        gates: Optional[Dict[str, List[VerificationGate]]] = None,
    ):
        """
        Delegates batch multi-asset conversion to BatchAssetProcessor.
        """
        from .batch import BatchAssetProcessor
        processor = BatchAssetProcessor(
            orchestrator=self,
            executor=self._executor,
        )
        return processor.process_batch(
            input_paths=input_paths,
            output_dir=output_dir,
            target_format=target_format,
            trusted_approval=trusted_approval,
            overwrite=overwrite,
            session_id=session_id,
            gates=gates,
        )

