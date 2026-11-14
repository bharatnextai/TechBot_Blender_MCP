"""
Unit Tests for Agent Manager Foundation & Deterministic Routing (TASK-UMCP-0014).
Validates agent manifests, deterministic capability routing, dependency cycle detection,
topological task ordering, task state transitions, and security boundaries.
"""

import unittest
from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    TaskPlan,
    TaskStatus,
    AgentResult,
    VerificationResult,
)
from mcp_service.agents.registry import AgentRegistry, create_default_registry
from mcp_service.agents.router import CapabilityRouter, RoutingResult
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.manager import AgentManager
from shared.schemas.tool_schemas import validate_tool_input, TOOL_CREATE_PRIMITIVE


class TestAgentManifestsAndRegistry(unittest.TestCase):
    def test_valid_manifest_validation(self):
        manifest = AgentManifest(
            agent_id="agent.test",
            name="Test Agent",
            version="1.0.0",
            capabilities=[
                CapabilityDescriptor(
                    capability_id="test.capability",
                    supported_task_types=["test_task"],
                    verification_status="VERIFIED",
                )
            ],
        )
        # Should not raise
        manifest.validate()

    def test_invalid_manifest_rejected(self):
        # Empty agent_id
        m1 = AgentManifest(agent_id="", name="Test", version="1.0.0", capabilities=[CapabilityDescriptor("cap1")])
        with self.assertRaises(ValueError):
            m1.validate()

        # Empty name
        m2 = AgentManifest(agent_id="agent.test", name="", version="1.0.0", capabilities=[CapabilityDescriptor("cap1")])
        with self.assertRaises(ValueError):
            m2.validate()

        # Empty capabilities
        m3 = AgentManifest(agent_id="agent.test", name="Test", version="1.0.0", capabilities=[])
        with self.assertRaises(ValueError):
            m3.validate()

        # Capability without capability_id
        m4 = AgentManifest(
            agent_id="agent.test",
            name="Test",
            version="1.0.0",
            capabilities=[CapabilityDescriptor(capability_id="")],
        )
        with self.assertRaises(ValueError):
            m4.validate()

    def test_duplicate_registration_rejected(self):
        reg = AgentRegistry()
        m1 = AgentManifest(agent_id="agent.dup", name="Dup 1", capabilities=[CapabilityDescriptor("cap1")])
        reg.register_agent(m1)

        m2 = AgentManifest(agent_id="agent.dup", name="Dup 2", capabilities=[CapabilityDescriptor("cap2")])
        with self.assertRaises(ValueError) as ctx:
            reg.register_agent(m2, overwrite=False)
        self.assertIn("already registered", str(ctx.exception))

        # With overwrite=True, succeeds
        reg.register_agent(m2, overwrite=True)
        self.assertEqual(reg.get_agent("agent.dup").name, "Dup 2")

    def test_default_registry_has_verified_baseline(self):
        reg = create_default_registry()
        agents = reg.list_agents()
        self.assertEqual(len(agents), 9)
        agent_ids = [a.agent_id for a in agents]
        self.assertIn("agent.director", agent_ids)
        self.assertIn("agent.scene_inspector", agent_ids)
        self.assertIn("agent.modeling", agent_ids)
        self.assertIn("agent.materials", agent_ids)
        self.assertIn("agent.render_lighting", agent_ids)
        self.assertIn("agent.rigging_animation", agent_ids)
        self.assertIn("agent.simulation_vfx", agent_ids)
        self.assertIn("agent.interchange_delivery", agent_ids)
        self.assertIn("agent.compositor", agent_ids)

        verified_caps = [c.capability_id for c in reg.get_verified_capabilities()]
        self.assertIn("scene.inspection", verified_caps)
        self.assertIn("modeling.primitive", verified_caps)
        self.assertIn("modeling.transform", verified_caps)
        self.assertIn("modeling.execution", verified_caps)
        self.assertIn("materials.manage", verified_caps)
        self.assertIn("materials.inspect", verified_caps)
        self.assertIn("lighting.manage", verified_caps)
        self.assertIn("world.manage", verified_caps)
        self.assertIn("lighting.inspect", verified_caps)
        self.assertIn("visual.capture", verified_caps)


class TestDeterministicCapabilityRouting(unittest.TestCase):
    def setUp(self):
        self.reg = AgentRegistry()
        # Primary modeling agent
        self.modeling_v1 = AgentManifest(
            agent_id="agent.modeling.standard",
            name="Standard Modeling",
            version="0.1.0",
            priority=50,
            capabilities=[
                CapabilityDescriptor(
                    capability_id="modeling.primitive",
                    supported_task_types=["create_primitive"],
                    verification_status="VERIFIED",
                ),
                CapabilityDescriptor(
                    capability_id="modeling.sculpting",
                    supported_task_types=["voxel_remesh"],
                    verification_status="UNVERIFIED",  # Unverified
                ),
            ],
        )
        self.reg.register_agent(self.modeling_v1)
        self.router = CapabilityRouter(self.reg)

    def test_exact_capability_and_task_type_match(self):
        task = AgentTask(
            task_id="t1",
            required_capability="modeling.primitive",
            task_type="create_primitive",
        )
        res = self.router.route(task)
        self.assertTrue(res.success)
        self.assertEqual(res.agent.agent_id, "agent.modeling.standard")
        self.assertEqual(res.capability.capability_id, "modeling.primitive")

    def test_incompatible_task_type_rejected(self):
        task = AgentTask(
            task_id="t1",
            required_capability="modeling.primitive",
            task_type="unsupported_sub_operator",
        )
        res = self.router.route(task)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "NO_MATCH")

    def test_unknown_capability_returns_no_match(self):
        task = AgentTask(task_id="t1", required_capability="nonexistent.capability")
        res = self.router.route(task)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "NO_MATCH")

    def test_unverified_capability_rejected_by_default(self):
        task = AgentTask(task_id="t1", required_capability="modeling.sculpting")
        res = self.router.route(task, require_verified=True)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "UNVERIFIED_CAPABILITY")
        self.assertIn("has verification_status='UNVERIFIED'", res.message)

    def test_disabled_agent_excluded(self):
        self.modeling_v1.enabled = False
        task = AgentTask(task_id="t1", required_capability="modeling.primitive")
        res = self.router.route(task)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "NO_MATCH")

    def test_deterministic_tie_breaking_priority(self):
        # Add high-priority agent (priority 10 vs 50)
        high_pri_agent = AgentManifest(
            agent_id="agent.modeling.fast",
            name="Fast Modeling",
            version="0.1.0",
            priority=10,  # Higher priority
            capabilities=[
                CapabilityDescriptor(
                    capability_id="modeling.primitive",
                    supported_task_types=["create_primitive"],
                    verification_status="VERIFIED",
                )
            ],
        )
        self.reg.register_agent(high_pri_agent)

        task = AgentTask(task_id="t1", required_capability="modeling.primitive")
        res = self.router.route(task)
        self.assertTrue(res.success)
        self.assertEqual(res.agent.agent_id, "agent.modeling.fast")

    def test_deterministic_tie_breaking_version(self):
        # Same priority 50, but newer version 0.2.0 vs 0.1.0
        newer_agent = AgentManifest(
            agent_id="agent.modeling.v2",
            name="Modeling V2",
            version="0.2.0",
            priority=50,
            capabilities=[
                CapabilityDescriptor(
                    capability_id="modeling.primitive",
                    supported_task_types=["create_primitive"],
                    verification_status="VERIFIED",
                )
            ],
        )
        self.reg.register_agent(newer_agent)

        task = AgentTask(task_id="t1", required_capability="modeling.primitive")
        res = self.router.route(task)
        self.assertTrue(res.success)
        self.assertEqual(res.agent.agent_id, "agent.modeling.v2")

    def test_strict_ambiguity_mode(self):
        # Identical priority and version
        ambiguous_agent = AgentManifest(
            agent_id="agent.modeling.alt",
            name="Modeling Alt",
            version="0.1.0",
            priority=50,
            capabilities=[
                CapabilityDescriptor(
                    capability_id="modeling.primitive",
                    supported_task_types=["create_primitive"],
                    verification_status="VERIFIED",
                )
            ],
        )
        self.reg.register_agent(ambiguous_agent)

        task = AgentTask(task_id="t1", required_capability="modeling.primitive")
        res = self.router.route(task, strict_ambiguity=True)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "AMBIGUOUS_MATCH")


class TestDependencyAwarePlanning(unittest.TestCase):
    def setUp(self):
        self.reg = create_default_registry()
        self.router = CapabilityRouter(self.reg)
        self.planner = TaskPlanner(self.router)

    def test_valid_plan_topological_order(self):
        plan = TaskPlan(title="Build Scene")
        # Task 1: Inspect scene
        t1 = AgentTask("t_inspect", "scene.inspection", "get_scene_summary")
        # Task 2: Create primitive (depends on inspect)
        t2 = AgentTask("t_create", "modeling.primitive", "create_primitive", dependencies=["t_inspect"])
        # Task 3: Transform primitive (depends on create)
        t3 = AgentTask("t_transform", "modeling.transform", "transform_object", dependencies=["t_create"])

        plan.add_task(t3)
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])

        order = self.planner.compute_execution_order(plan)
        self.assertEqual(order, ["t_inspect", "t_create", "t_transform"])

    def test_missing_dependency_reference_rejected(self):
        plan = TaskPlan(title="Invalid Dep Plan")
        t1 = AgentTask("t1", "scene.inspection", dependencies=["nonexistent_task_id"])
        plan.add_task(t1)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("depends on non-existent task 'nonexistent_task_id'" in e for e in errors))

    def test_self_dependency_rejected(self):
        plan = TaskPlan(title="Self Dep Plan")
        t1 = AgentTask("t1", "scene.inspection", dependencies=["t1"])
        plan.add_task(t1)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("self-dependency detected" in e for e in errors))

    def test_two_node_cycle_rejected(self):
        plan = TaskPlan(title="Cycle Plan")
        t1 = AgentTask("t1", "scene.inspection", dependencies=["t2"])
        t2 = AgentTask("t2", "modeling.primitive", dependencies=["t1"])
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("Dependency cycle detected" in e for e in errors))

    def test_multi_node_cycle_rejected(self):
        plan = TaskPlan(title="Multi Cycle Plan")
        t1 = AgentTask("A", "scene.inspection", dependencies=["C"])
        t2 = AgentTask("B", "modeling.primitive", dependencies=["A"])
        t3 = AgentTask("C", "modeling.transform", dependencies=["B"])
        plan.add_task(t1)
        plan.add_task(t2)
        plan.add_task(t3)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("Dependency cycle detected" in e for e in errors))

    def test_diamond_dependency_graph(self):
        plan = TaskPlan(title="Diamond Plan")
        # D depends on B and C; B and C depend on A
        ta = AgentTask("A", "scene.inspection")
        tb = AgentTask("B", "modeling.primitive", dependencies=["A"])
        tc = AgentTask("C", "modeling.primitive", dependencies=["A"])
        td = AgentTask("D", "modeling.transform", dependencies=["B", "C"])
        plan.add_task(td)
        plan.add_task(tc)
        plan.add_task(tb)
        plan.add_task(ta)

        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])

        order = self.planner.compute_execution_order(plan)
        self.assertEqual(order[0], "A")
        self.assertEqual(order[-1], "D")
        self.assertTrue(order.index("B") < order.index("D"))
        self.assertTrue(order.index("C") < order.index("D"))


class TestTaskStatusLifecycleAndTransitions(unittest.TestCase):
    def test_valid_status_transitions(self):
        task = AgentTask("t1", "scene.inspection")
        self.assertEqual(task.status, TaskStatus.PENDING)

        task.transition_to(TaskStatus.READY)
        self.assertEqual(task.status, TaskStatus.READY)

        task.transition_to(TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING)

        task.transition_to(TaskStatus.SUCCEEDED)
        self.assertEqual(task.status, TaskStatus.SUCCEEDED)

    def test_approval_lifecycle_transitions(self):
        task = AgentTask("t_mutate", "modeling.primitive")
        task.transition_to(TaskStatus.READY)
        task.transition_to(TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(task.status, TaskStatus.AWAITING_APPROVAL)

        # Denied
        task_denied = AgentTask("t_denied", "modeling.primitive")
        task_denied.transition_to(TaskStatus.READY)
        task_denied.transition_to(TaskStatus.AWAITING_APPROVAL)
        task_denied.transition_to(TaskStatus.FAILED)
        self.assertEqual(task_denied.status, TaskStatus.FAILED)

    def test_invalid_status_transition_raises(self):
        task = AgentTask("t1", "scene.inspection")
        # Direct PENDING -> SUCCEEDED is invalid
        with self.assertRaises(ValueError) as ctx:
            task.transition_to(TaskStatus.SUCCEEDED)
        self.assertIn("Invalid task status transition", str(ctx.exception))

        # Terminal state cannot transition
        task.transition_to(TaskStatus.READY)
        task.transition_to(TaskStatus.RUNNING)
        task.transition_to(TaskStatus.SUCCEEDED)
        with self.assertRaises(ValueError):
            task.transition_to(TaskStatus.RUNNING)

    def test_advance_plan_state(self):
        planner = TaskPlanner()
        plan = TaskPlan(title="Advance Test")
        t1 = AgentTask("t1", "scene.inspection")
        t2 = AgentTask("t2", "modeling.primitive", dependencies=["t1"])
        plan.add_task(t1)
        plan.add_task(t2)

        # Initially, t1 has 0 dependencies so it transitions to READY; t2 remains PENDING
        planner.advance_plan_state(plan)
        self.assertEqual(t1.status, TaskStatus.READY)
        self.assertEqual(t2.status, TaskStatus.PENDING)

        # t1 succeeds
        t1.transition_to(TaskStatus.RUNNING)
        t1.transition_to(TaskStatus.SUCCEEDED)

        # Now t2 should transition to READY
        planner.advance_plan_state(plan)
        self.assertEqual(t2.status, TaskStatus.READY)

    def test_dependency_failure_skips_downstream_tasks(self):
        planner = TaskPlanner()
        plan = TaskPlan(title="Skip Test")
        t1 = AgentTask("t1", "scene.inspection")
        t2 = AgentTask("t2", "modeling.primitive", dependencies=["t1"])
        plan.add_task(t1)
        plan.add_task(t2)

        planner.advance_plan_state(plan)
        t1.transition_to(TaskStatus.RUNNING)
        t1.transition_to(TaskStatus.FAILED)

        # t2 should transition to SKIPPED because its prerequisite failed
        planner.advance_plan_state(plan)
        self.assertEqual(t2.status, TaskStatus.SKIPPED)
        self.assertEqual(plan.status, TaskStatus.FAILED)


class TestAgentManagerAndSecurityBoundaries(unittest.TestCase):
    def test_agent_manager_creates_and_orders_plan(self):
        manager = AgentManager()
        tasks = [
            AgentTask("t_summary", "scene.inspection", "get_scene_summary"),
            AgentTask("t_cube", "modeling.primitive", "create_primitive", dependencies=["t_summary"]),
        ]
        plan = manager.create_plan(title="Create Cube Scene", tasks=tasks)
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(plan.execution_order, ["t_summary", "t_cube"])

    def test_planning_failure_does_not_execute_mutation(self):
        manager = AgentManager()
        # Create plan with unverified capability
        tasks = [
            AgentTask("t_invalid", "unverified.capability", "some_op"),
        ]
        with self.assertRaises(ValueError) as ctx:
            manager.create_plan(title="Invalid Plan", tasks=tasks)
        self.assertIn("TaskPlan validation failed", str(ctx.exception))

    def test_security_boundary_model_approved_flag_rejected(self):
        # Verify that schema validator strictly rejects model-supplied approved=True
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {"primitive_type": "cube", "name": "HackCube", "approved": True})
        self.assertIn("untrusted and cannot authorize scene mutation", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
