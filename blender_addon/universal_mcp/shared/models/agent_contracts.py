"""
Agent Manager Contracts and Foundational Models for Universal MCP.
Defines versioned models for AgentManifest, CapabilityDescriptor, AgentTask,
TaskPlan, TaskStatus, AgentResult, and VerificationResult.
Pure standard library only (zero external wheel dependencies).
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple
import uuid
import time


class TaskStatus(str, Enum):
    """
    Explicit lifecycle states for tasks and plans within the Agent Manager.
    Includes human approval gating state.
    """
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


VALID_STATUS_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.READY, TaskStatus.FAILED, TaskStatus.SKIPPED, TaskStatus.CANCELLED},
    TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.AWAITING_APPROVAL, TaskStatus.CANCELLED},
    TaskStatus.SUCCEEDED: set(),  # Terminal state
    TaskStatus.FAILED: set(),     # Terminal state
    TaskStatus.SKIPPED: set(),    # Terminal state
    TaskStatus.CANCELLED: set(),  # Terminal state
}


@dataclass
class CapabilityDescriptor:
    """
    Describes an atomic capability declared by an agent.
    Includes task types supported, read/write classification, and verification status.
    """
    capability_id: str
    description: str = ""
    supported_task_types: List[str] = field(default_factory=list)
    read_write: str = "READ_ONLY"  # "READ_ONLY" or "SCENE_MUTATION"
    verification_status: str = "UNVERIFIED"  # "VERIFIED", "PARTIAL", "UNVERIFIED"
    constraints: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityDescriptor":
        return cls(
            capability_id=str(data.get("capability_id", "")),
            description=str(data.get("description", "")),
            supported_task_types=list(data.get("supported_task_types", [])),
            read_write=str(data.get("read_write", "READ_ONLY")),
            verification_status=str(data.get("verification_status", "UNVERIFIED")),
            constraints=dict(data.get("constraints", {})),
            version=str(data.get("version", "1.0.0")),
        )


@dataclass
class AgentManifest:
    """
    Declared identity, capabilities, constraints, and dependencies for a specialized agent.
    """
    agent_id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    capabilities: List[CapabilityDescriptor] = field(default_factory=list)
    input_schemas: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    enabled: bool = True
    priority: int = 100  # Lower number = higher priority for deterministic tie-breaking

    def validate(self) -> None:
        """Validates manifest integrity; raises ValueError if invalid."""
        if not self.agent_id or not str(self.agent_id).strip():
            raise ValueError("AgentManifest 'agent_id' cannot be empty.")
        if not self.name or not str(self.name).strip():
            raise ValueError(f"AgentManifest '{self.agent_id}' requires a non-empty 'name'.")
        if not self.version or not str(self.version).strip():
            raise ValueError(f"AgentManifest '{self.agent_id}' requires a valid 'version'.")
        if not self.capabilities:
            raise ValueError(f"AgentManifest '{self.agent_id}' must declare at least one CapabilityDescriptor.")
        for cap in self.capabilities:
            if not cap.capability_id or not str(cap.capability_id).strip():
                raise ValueError(f"AgentManifest '{self.agent_id}' contains a capability without 'capability_id'.")

    def has_capability(self, capability_id: str, task_type: Optional[str] = None) -> bool:
        """Checks if agent declares the specified capability and optional task type."""
        for cap in self.capabilities:
            if cap.capability_id == capability_id:
                if task_type is None:
                    return True
                if not cap.supported_task_types or task_type in cap.supported_task_types:
                    return True
        return False

    def get_capability(self, capability_id: str) -> Optional[CapabilityDescriptor]:
        """Returns specific CapabilityDescriptor if declared by this agent."""
        for cap in self.capabilities:
            if cap.capability_id == capability_id:
                return cap
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "input_schemas": self.input_schemas,
            "constraints": self.constraints,
            "dependencies": self.dependencies,
            "enabled": self.enabled,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentManifest":
        caps = [CapabilityDescriptor.from_dict(c) for c in data.get("capabilities", [])]
        return cls(
            agent_id=str(data.get("agent_id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "0.1.0")),
            description=str(data.get("description", "")),
            capabilities=caps,
            input_schemas=dict(data.get("input_schemas", {})),
            constraints=dict(data.get("constraints", {})),
            dependencies=list(data.get("dependencies", [])),
            enabled=bool(data.get("enabled", True)),
            priority=int(data.get("priority", 100)),
        )


@dataclass
class VerificationResult:
    """
    Structured outcome of post-operation verification.
    """
    expected_conditions: Dict[str, Any] = field(default_factory=dict)
    observed_results: Dict[str, Any] = field(default_factory=dict)
    status: str = "UNVERIFIED"  # "PASS", "FAIL", "UNVERIFIED"
    details: str = ""

    @property
    def verified(self) -> bool:
        return self.status == "PASS"

    @property
    def transaction_state(self) -> str:
        return self.observed_results.get("transaction_status", "NOT_APPLICABLE")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        return cls(
            expected_conditions=dict(data.get("expected_conditions", {})),
            observed_results=dict(data.get("observed_results", {})),
            status=str(data.get("status", "UNVERIFIED")),
            details=str(data.get("details", "")),
        )


@dataclass
class AgentResult:
    """
    Standard output envelope returned by an agent task execution.
    """
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    output: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list)
    verification: Optional[VerificationResult] = None
    execution_time_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == TaskStatus.SUCCEEDED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "output": self.output,
            "errors": self.errors,
            "evidence_references": self.evidence_references,
            "verification": self.verification.to_dict() if self.verification else None,
            "execution_time_ms": self.execution_time_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResult":
        v_data = data.get("verification")
        verification = VerificationResult.from_dict(v_data) if v_data else None
        st_raw = data.get("status", "pending")
        try:
            st = TaskStatus(st_raw)
        except ValueError:
            st = TaskStatus.PENDING
        return cls(
            task_id=str(data.get("task_id", "")),
            status=st,
            output=data.get("output"),
            errors=list(data.get("errors", [])),
            evidence_references=list(data.get("evidence_references", [])),
            verification=verification,
            execution_time_ms=float(data.get("execution_time_ms", 0.0)),
        )


SUPPORTED_REF_TYPES: Set[str] = {
    "string", "number", "integer", "boolean", "array", "object",
    "str", "int", "float", "bool", "list", "dict",
}


@dataclass(frozen=True)
class TaskOutputRef:
    """
    Strongly typed reference to an upstream task's verified output field.
    Enforces canonical structured representation:
        {"$ref": {"task_id": "...", "path": "...", "type": "..."}}
    """
    task_id: str
    path: str
    expected_type: Optional[str] = None

    def validate(self) -> None:
        """Validates reference integrity; raises ValueError if malformed."""
        if not self.task_id or not str(self.task_id).strip():
            raise ValueError("TaskOutputRef 'task_id' cannot be empty.")
        if not self.path or not str(self.path).strip():
            raise ValueError("TaskOutputRef 'path' cannot be empty.")

        segments = self.path.split(".")
        for idx, seg in enumerate(segments):
            if not seg or not seg.strip():
                raise ValueError(f"TaskOutputRef 'path' contains empty segment at index {idx}: '{self.path}'.")
            if not (seg.isidentifier() or seg.isdigit()):
                raise ValueError(
                    f"TaskOutputRef path segment '{seg}' is neither a valid identifier nor a non-negative integer index."
                )

        if self.expected_type is not None:
            if not self.expected_type or not str(self.expected_type).strip():
                raise ValueError("TaskOutputRef 'expected_type' cannot be empty string.")
            norm_type = str(self.expected_type).strip().lower()
            if norm_type not in SUPPORTED_REF_TYPES:
                raise ValueError(
                    f"Unsupported type declaration '{self.expected_type}' in TaskOutputRef. "
                    f"Supported types: {sorted(SUPPORTED_REF_TYPES)}"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes reference to the canonical structured representation."""
        ref_body: Dict[str, Any] = {
            "task_id": self.task_id,
            "path": self.path,
        }
        if self.expected_type is not None:
            ref_body["type"] = self.expected_type
        return {"$ref": ref_body}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskOutputRef":
        """
        Parses a canonical structured reference dictionary.
        Canonical format: {"$ref": {"task_id": "...", "path": "...", "type": "..."}}
        Raises ValueError if data is not a valid structured reference.
        """
        if not isinstance(data, dict):
            raise ValueError(f"Reference must be a dictionary, got {type(data).__name__}.")
        if "$ref" not in data:
            raise ValueError("Missing '$ref' key in reference dictionary.")
        ref_body = data["$ref"]
        if not isinstance(ref_body, dict):
            raise ValueError(f"'$ref' payload must be a dictionary, got {type(ref_body).__name__}.")

        allowed_keys = {"task_id", "task", "path", "type", "expected_type"}
        unknown_keys = set(ref_body.keys()) - allowed_keys
        if unknown_keys:
            raise ValueError(f"Unknown key(s) in '$ref' payload: {sorted(unknown_keys)}.")

        task_id = ref_body.get("task_id") or ref_body.get("task")
        if not task_id or not isinstance(task_id, str) or not str(task_id).strip():
            raise ValueError("'$ref' payload must contain a non-empty string 'task_id'.")

        path = ref_body.get("path")
        if not path or not isinstance(path, str) or not str(path).strip():
            raise ValueError("'$ref' payload must contain a non-empty string 'path'.")

        exp_type = ref_body.get("type") or ref_body.get("expected_type")
        if exp_type is not None and (not isinstance(exp_type, str) or not str(exp_type).strip()):
            raise ValueError("'$ref' 'type' must be a non-empty string if specified.")

        ref = cls(
            task_id=str(task_id).strip(),
            path=str(path).strip(),
            expected_type=str(exp_type).strip() if exp_type else None,
        )
        ref.validate()
        return ref


@dataclass
class AgentTask:
    """
    Represents an atomic task assigned to a specialized agent within a TaskPlan.
    """
    task_id: str
    required_capability: str
    task_type: str = ""
    input_params: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    preconditions: Dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[AgentResult] = None
    target_agent_id: Optional[str] = None
    session_id: str = "default"
    correlation_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    resolved_input_params: Optional[Dict[str, Any]] = None
    binding_traces: List[Dict[str, Any]] = field(default_factory=list)
    approval_binding: Optional[Dict[str, Any]] = None

    def transition_to(self, new_status: TaskStatus) -> None:
        """
        Explicitly validates and executes a task state transition.
        Raises ValueError if transition is invalid.
        """
        if self.status == new_status:
            return
        allowed = VALID_STATUS_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid task status transition for '{self.task_id}': cannot transition from "
                f"'{self.status.value}' to '{new_status.value}'. Allowed: {[s.value for s in allowed]}"
            )
        self.status = new_status
        self.updated_at = time.time()

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.SKIPPED, TaskStatus.CANCELLED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "required_capability": self.required_capability,
            "task_type": self.task_type,
            "input_params": self.input_params,
            "dependencies": self.dependencies,
            "preconditions": self.preconditions,
            "acceptance_criteria": self.acceptance_criteria,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "result": self.result.to_dict() if self.result else None,
            "target_agent_id": self.target_agent_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_input_params": self.resolved_input_params,
            "binding_traces": self.binding_traces,
            "approval_binding": self.approval_binding,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTask":
        res_data = data.get("result")
        res = AgentResult.from_dict(res_data) if res_data else None
        st_raw = data.get("status", "pending")
        try:
            st = TaskStatus(st_raw)
        except ValueError:
            st = TaskStatus.PENDING
        return cls(
            task_id=str(data.get("task_id", "")),
            required_capability=str(data.get("required_capability", "")),
            task_type=str(data.get("task_type", "")),
            input_params=dict(data.get("input_params", {})),
            dependencies=list(data.get("dependencies", [])),
            preconditions=dict(data.get("preconditions", {})),
            acceptance_criteria=dict(data.get("acceptance_criteria", {})),
            status=st,
            result=res,
            target_agent_id=data.get("target_agent_id"),
            session_id=str(data.get("session_id", "default")),
            correlation_id=data.get("correlation_id"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            resolved_input_params=data.get("resolved_input_params"),
            binding_traces=list(data.get("binding_traces", [])),
            approval_binding=data.get("approval_binding"),
        )


@dataclass
class TaskPlan:
    """
    Represents an ordered, dependency-aware plan containing multiple AgentTasks.
    """
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    tasks: Dict[str, AgentTask] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def add_task(self, task: AgentTask) -> None:
        """Adds a task to the plan dictionary."""
        if not task.task_id or not str(task.task_id).strip():
            raise ValueError("Task ID cannot be empty.")
        if task.task_id in self.tasks:
            raise ValueError(f"Duplicate task ID '{task.task_id}' in plan '{self.plan_id}'.")
        self.tasks[task.task_id] = task

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        return self.tasks.get(task_id)

    def transition_to(self, new_status: TaskStatus) -> None:
        """Explicitly validates and transitions the overall plan status."""
        if self.status == new_status:
            return
        allowed = VALID_STATUS_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid plan status transition for '{self.plan_id}': cannot transition from "
                f"'{self.status.value}' to '{new_status.value}'. Allowed: {[s.value for s in allowed]}"
            )
        self.status = new_status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "execution_order": self.execution_order,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskPlan":
        tasks_map = {}
        for tid, t_data in data.get("tasks", {}).items():
            tasks_map[tid] = AgentTask.from_dict(t_data)
        st_raw = data.get("status", "pending")
        try:
            st = TaskStatus(st_raw)
        except ValueError:
            st = TaskStatus.PENDING
        return cls(
            plan_id=str(data.get("plan_id", str(uuid.uuid4()))),
            title=str(data.get("title", "")),
            tasks=tasks_map,
            execution_order=list(data.get("execution_order", [])),
            status=st,
            metadata=dict(data.get("metadata", {})),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class DelegationContract:
    """
    Contract representing the delegation of high-level production briefs
    across specialized domain agents.
    Enforces deterministic stage boundaries, dependency graphs, and human approval gating.
    """
    contract_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    brief: str = ""
    director_agent_id: str = "agent.director"
    domain_tasks: Dict[str, List[AgentTask]] = field(default_factory=dict)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)  # task_id -> list of prerequisite task_ids
    bindings: List[TaskOutputRef] = field(default_factory=list)
    requires_human_approval: bool = True
    approval_status: str = "PENDING"  # "PENDING", "APPROVED", "REJECTED"
    approval_token: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> List[str]:
        errors = []
        if not self.contract_id:
            errors.append("DelegationContract 'contract_id' cannot be empty.")
        if not self.title:
            errors.append("DelegationContract 'title' cannot be empty.")
        all_task_ids = set()
        for agent_id, tasks in self.domain_tasks.items():
            if not agent_id:
                errors.append("Domain task entry has empty agent_id.")
            for t in tasks:
                if t.task_id in all_task_ids:
                    errors.append(f"Duplicate task_id '{t.task_id}' in DelegationContract.")
                all_task_ids.add(t.task_id)
        for tid, deps in self.dependencies.items():
            if tid not in all_task_ids:
                errors.append(f"Dependency references unknown target task '{tid}'.")
            for dep in deps:
                if dep not in all_task_ids:
                    errors.append(f"Task '{tid}' references unknown prerequisite task '{dep}'.")
        return errors

    def compile_plan(self, session_id: str = "default") -> TaskPlan:
        """
        Compiles the contract into a standard TaskPlan for execution.
        """
        errors = self.validate()
        if errors:
            raise ValueError(f"DelegationContract validation failed: {'; '.join(errors)}")
        plan = TaskPlan(
            plan_id=self.contract_id,
            title=self.title,
            metadata={
                "brief": self.brief,
                "director_agent_id": self.director_agent_id,
                "requires_human_approval": self.requires_human_approval,
                "approval_status": self.approval_status,
                "approval_token": self.approval_token,
                **self.metadata,
            }
        )
        for agent_id, tasks in self.domain_tasks.items():
            for t in tasks:
                t.target_agent_id = agent_id
                t.session_id = session_id
                if t.task_id in self.dependencies:
                    t.dependencies = list(self.dependencies[t.task_id])
                plan.add_task(t)
        return plan

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "title": self.title,
            "brief": self.brief,
            "director_agent_id": self.director_agent_id,
            "domain_tasks": {
                aid: [t.to_dict() for t in tasks]
                for aid, tasks in self.domain_tasks.items()
            },
            "dependencies": self.dependencies,
            "bindings": [asdict(b) for b in self.bindings],
            "requires_human_approval": self.requires_human_approval,
            "approval_status": self.approval_status,
            "approval_token": self.approval_token,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationContract":
        tasks_map = {}
        for aid, tlist in data.get("domain_tasks", {}).items():
            tasks_map[aid] = [AgentTask.from_dict(t) for t in tlist]
        bindings = [
            TaskOutputRef(task_id=b["task_id"], path=b["path"], expected_type=b.get("expected_type"))
            for b in data.get("bindings", [])
        ]
        return cls(
            contract_id=data.get("contract_id", str(uuid.uuid4())),
            title=data.get("title", ""),
            brief=data.get("brief", ""),
            director_agent_id=data.get("director_agent_id", "agent.director"),
            domain_tasks=tasks_map,
            dependencies=data.get("dependencies", {}),
            bindings=bindings,
            requires_human_approval=data.get("requires_human_approval", True),
            approval_status=data.get("approval_status", "PENDING"),
            approval_token=data.get("approval_token"),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
        )
