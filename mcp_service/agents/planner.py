"""
Dependency-Aware Task Planner and Graph Validator for Universal MCP.
Validates task dependencies, detects cycles, establishes deterministic topological execution order,
and manages task lifecycle state transitions without executing mutations.
"""

from collections import deque
from typing import Dict, Any, List, Optional, Set, Tuple, Union
from shared.models.agent_contracts import (
    TaskPlan,
    AgentTask,
    TaskStatus,
    TaskOutputRef,
)
from .router import CapabilityRouter


class TaskPlanner:
    """
    Validates task graph dependencies and establishes deterministic topological execution order.
    Separates planning from execution and approval.
    """

    def __init__(self, router: Optional[CapabilityRouter] = None):
        self.router = router

    @staticmethod
    def _scan_task_references(
        node: Any, breadcrumb: str = ""
    ) -> List[Tuple[str, Optional[TaskOutputRef], Optional[str]]]:
        """
        Recursively scans task parameter data structures for TaskOutputRef instances or
        canonical structured {'$ref': {...}} dictionaries.
        Returns a list of (param_path, ref_instance_or_none, error_message_or_none).
        Pure read-only traversal; leaves the parameter structure completely unmodified.
        """
        findings: List[Tuple[str, Optional[TaskOutputRef], Optional[str]]] = []

        if isinstance(node, TaskOutputRef):
            try:
                node.validate()
                findings.append((breadcrumb, node, None))
            except ValueError as ve:
                findings.append((breadcrumb, None, str(ve)))
            return findings

        if isinstance(node, dict):
            if "$ref" in node:
                # Reference detected in dictionary
                try:
                    ref = TaskOutputRef.from_dict(node)
                    findings.append((breadcrumb, ref, None))
                except ValueError as ve:
                    findings.append((breadcrumb, None, str(ve)))
                return findings

            # Regular dictionary: recurse into children maintaining parameter path
            for key, val in node.items():
                child_path = f"{breadcrumb}.{key}" if breadcrumb else str(key)
                findings.extend(TaskPlanner._scan_task_references(val, child_path))
            return findings

        if isinstance(node, (list, tuple)):
            for idx, item in enumerate(node):
                child_path = f"{breadcrumb}[{idx}]"
                findings.extend(TaskPlanner._scan_task_references(item, child_path))
            return findings

        if isinstance(node, str) and node.startswith("$ref:"):
            # Explicitly reject shorthand syntax as specified in roadmap / contracts
            findings.append((
                breadcrumb,
                None,
                f"Shorthand '$ref:' syntax is not supported: '{node}'. "
                f"Use canonical structured format: {{'$ref': {{'task_id': ..., 'path': ...}}}}"
            ))
            return findings

        return findings

    def validate_plan(
        self,
        plan: TaskPlan,
        require_verified_capabilities: bool = True,
    ) -> List[str]:
        """
        Performs comprehensive static validation on a TaskPlan:
        - Non-empty plan and tasks.
        - Valid, unique task IDs.
        - Valid dependency references.
        - Task output reference validation (declared dependency, existence, valid path/type).
        - Cycle detection.
        - Capability availability and verification.
        Returns a list of error messages (empty if valid).
        """
        errors: List[str] = []

        if not plan.plan_id or not str(plan.plan_id).strip():
            errors.append("Plan 'plan_id' cannot be empty.")

        if not plan.tasks:
            errors.append(f"Plan '{plan.plan_id}' contains no tasks.")
            return errors

        all_task_ids: Set[str] = set(plan.tasks.keys())

        # 1. Validate individual tasks, dependency references, and task output references
        for tid, task in plan.tasks.items():
            if tid != task.task_id:
                errors.append(f"Dictionary key '{tid}' does not match task_id '{task.task_id}'.")

            if not task.required_capability or not str(task.required_capability).strip():
                errors.append(f"Task '{tid}' must declare a 'required_capability'.")

            # Check self-dependency
            if tid in task.dependencies:
                errors.append(f"Task '{tid}' cannot depend on itself (self-dependency detected).")

            # Check missing dependency references
            for dep_id in task.dependencies:
                if dep_id not in all_task_ids:
                    errors.append(f"Task '{tid}' depends on non-existent task '{dep_id}'.")

            # Check task output references in input_params
            if task.input_params and isinstance(task.input_params, dict):
                ref_findings = self._scan_task_references(task.input_params)
                for param_path, ref, ref_err in ref_findings:
                    if ref_err:
                        errors.append(
                            f"Task '{tid}' parameter '{param_path}' has malformed reference: {ref_err}"
                        )
                        continue

                    if ref is not None:
                        # Self-reference
                        if ref.task_id == tid:
                            errors.append(
                                f"Task '{tid}' parameter '{param_path}' references itself (self-dependency detected)."
                            )
                        # Target nonexistent task
                        elif ref.task_id not in all_task_ids:
                            errors.append(
                                f"Task '{tid}' parameter '{param_path}' references non-existent task '{ref.task_id}'."
                            )
                        # Target task not declared in direct dependencies
                        elif ref.task_id not in task.dependencies:
                            errors.append(
                                f"Task '{tid}' parameter '{param_path}' references task '{ref.task_id}' "
                                f"which is not declared in direct dependencies: {task.dependencies}."
                            )

        # 2. Cycle detection & Topological Sort
        if not any("depends on non-existent task" in e for e in errors):
            try:
                self.compute_execution_order(plan)
            except ValueError as cycle_err:
                errors.append(str(cycle_err))

        # 3. Capability verification check via router if provided
        if self.router:
            for tid, task in plan.tasks.items():
                res = self.router.route(task, require_verified=require_verified_capabilities)
                if not res.success:
                    errors.append(
                        f"Task '{tid}' requires capability '{task.required_capability}' "
                        f"which cannot be routed: {res.message}"
                    )

        return errors

    def compute_execution_order(self, plan: TaskPlan) -> List[str]:
        """
        Computes a deterministic topological execution order using Kahn's algorithm.
        Sorts tie-breaks alphabetically by task_id for strictly reproducible execution.
        Raises ValueError if a dependency cycle is detected.
        """
        tasks = plan.tasks
        in_degree: Dict[str, int] = {tid: len(t.dependencies) for tid, t in tasks.items()}
        adjacency: Dict[str, List[str]] = {tid: [] for tid in tasks}

        for tid, task in tasks.items():
            for dep_id in task.dependencies:
                if dep_id in adjacency:
                    adjacency[dep_id].append(tid)

        # Start with all nodes having 0 in-degree, sorted alphabetically
        ready_queue = sorted([tid for tid, deg in in_degree.items() if deg == 0])
        ordered: List[str] = []

        while ready_queue:
            curr = ready_queue.pop(0)
            ordered.append(curr)

            # For all downstream dependent tasks, decrement in-degree
            newly_ready = []
            for downstream in sorted(adjacency[curr]):
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    newly_ready.append(downstream)

            # Insert newly ready nodes maintaining sorted order
            ready_queue.extend(newly_ready)
            ready_queue.sort()

        if len(ordered) != len(tasks):
            # Cycle detected
            remaining = [tid for tid, deg in in_degree.items() if deg > 0]
            raise ValueError(
                f"Dependency cycle detected in task plan '{plan.plan_id}'. "
                f"Cyclic or unresolvable tasks: {sorted(remaining)}"
            )

        plan.execution_order = ordered
        return ordered

    def advance_plan_state(self, plan: TaskPlan) -> None:
        """
        Updates task lifecycle states based on dependency outcomes:
        - PENDING tasks with all dependencies SUCCEEDED transition to READY.
        - PENDING tasks with any dependency FAILED/SKIPPED/CANCELLED transition to SKIPPED.
        - If all tasks reach terminal states, transitions overall plan status.
        """
        tasks = plan.tasks
        for tid, task in tasks.items():
            if task.status != TaskStatus.PENDING:
                continue

            # Check dependencies
            dep_tasks = [tasks.get(dep_id) for dep_id in task.dependencies if dep_id in tasks]
            
            # Check for failed/skipped dependencies
            if any(d.status in (TaskStatus.FAILED, TaskStatus.SKIPPED, TaskStatus.CANCELLED) for d in dep_tasks):
                task.transition_to(TaskStatus.SKIPPED)
            elif all(d.status == TaskStatus.SUCCEEDED for d in dep_tasks):
                task.transition_to(TaskStatus.READY)

        # Check overall plan status
        all_terminal = all(t.is_terminal for t in tasks.values())
        if all_terminal:
            if any(t.status == TaskStatus.FAILED for t in tasks.values()):
                plan.transition_to(TaskStatus.FAILED)
            elif any(t.status == TaskStatus.CANCELLED for t in tasks.values()):
                plan.transition_to(TaskStatus.CANCELLED)
            else:
                if plan.status == TaskStatus.READY:
                    plan.transition_to(TaskStatus.RUNNING)
                elif plan.status == TaskStatus.PENDING:
                    plan.transition_to(TaskStatus.READY)
                    plan.transition_to(TaskStatus.RUNNING)
                plan.transition_to(TaskStatus.SUCCEEDED)
        elif any(t.status == TaskStatus.RUNNING for t in tasks.values()):
            if plan.status == TaskStatus.PENDING or plan.status == TaskStatus.READY:
                plan.transition_to(TaskStatus.RUNNING)
        elif any(t.status == TaskStatus.READY for t in tasks.values()):
            if plan.status == TaskStatus.PENDING:
                plan.transition_to(TaskStatus.READY)
