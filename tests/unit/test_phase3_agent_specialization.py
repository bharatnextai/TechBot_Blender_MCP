"""
Unit tests for Milestone Phase 3.1: Domain Agent Specialization & Hierarchical Delegation.
Verifies:
1. DelegationContract structure, validation, serialization, and plan compilation.
2. DirectorAgent brief decomposition into multi-domain task plans.
3. Fail-closed human approval gating and untrusted approved=True rejection.
4. Specialized domain agents: RiggingAnimationAgent, SimulationVFXAgent,
   InterchangeDeliveryAgent, CompositorAgent.
5. Deterministic CapabilityRouter resolution across all 9 registered agents.
"""

import unittest
import uuid
import time
from typing import Dict, Any, List

from shared.models.agent_contracts import (
    DelegationContract,
    AgentTask,
    TaskStatus,
    TaskPlan,
    TaskOutputRef,
)
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.registry import create_default_registry, AgentRegistry
from mcp_service.agents.router import CapabilityRouter
from mcp_service.agents.manager import AgentManager
from mcp_service.agents.dispatcher import AgentDispatcher, DispatchResult
from mcp_service.agents.director import DirectorAgent, DIRECTOR_AGENT_ID, CAPABILITY_DIRECTOR_ORCHESTRATION
from mcp_service.agents.rigging_animation import (
    RiggingAnimationAgent,
    RIGGING_ANIMATION_AGENT_ID,
    CAPABILITY_RIGGING_ARMATURES,
    CAPABILITY_ANIMATION_KEYFRAME,
)
from mcp_service.agents.simulation_vfx import (
    SimulationVFXAgent,
    SIMULATION_VFX_AGENT_ID,
    CAPABILITY_PHYSICS_SIMULATION,
)
from mcp_service.agents.interchange_delivery import (
    InterchangeDeliveryAgent,
    INTERCHANGE_DELIVERY_AGENT_ID,
    CAPABILITY_INTERCHANGE_ASSET_IO,
)
from mcp_service.agents.compositor import (
    CompositorAgent,
    COMPOSITOR_AGENT_ID,
    CAPABILITY_COMPOSITOR_PIPELINE,
)
from mcp_service.agents.modeling import MODELING_AGENT_ID
from mcp_service.agents.materials import MATERIALS_AGENT_ID
from mcp_service.agents.render_lighting import RENDER_LIGHTING_AGENT_ID
from mcp_service.agents.scene_inspector import SCENE_INSPECTOR_AGENT_ID


class MockExecutor:
    """Mock BlenderExecutor recording calls and returning synthetic success responses."""
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def call_tool(self, tool_name: str, params: Dict[str, Any], task_id: str = "", session_id: str = "", trusted_approval: Any = None) -> BridgeResponse:
        self.calls.append({
            "tool_name": tool_name,
            "params": params,
            "task_id": task_id,
            "session_id": session_id,
            "trusted_approval": trusted_approval,
        })
        return BridgeResponse(
            status="success",
            result={"name": params.get("name", "MockObject"), "tool": tool_name, "verified": True},
            message=f"{tool_name} executed successfully",
        )

    def execute_tool(self, tool_name: str, params: Dict[str, Any], task_id: str = "", session_id: str = "", trusted_approval: Any = None) -> BridgeResponse:
        return self.call_tool(tool_name, params, task_id=task_id, session_id=session_id, trusted_approval=trusted_approval)


class TestDelegationContract(unittest.TestCase):
    """Verifies DelegationContract data model and compilation."""

    def test_delegation_contract_creation_and_validation(self):
        contract = DelegationContract(
            title="Hero Asset Production",
            brief="Create a rigged, textured, and lit character asset.",
            domain_tasks={
                MODELING_AGENT_ID: [
                    AgentTask(task_id="t_model", required_capability="modeling.primitive", task_type="create_primitive", input_params={"primitive_type": "CUBE"})
                ],
                RIGGING_ANIMATION_AGENT_ID: [
                    AgentTask(task_id="t_rig", required_capability="rigging.armatures", task_type="create_armature", input_params={"name": "Rig"})
                ],
            },
            dependencies={"t_rig": ["t_model"]},
        )
        errors = contract.validate()
        self.assertEqual(len(errors), 0)

        plan = contract.compile_plan(session_id="session_test")
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(plan.tasks["t_model"].target_agent_id, MODELING_AGENT_ID)
        self.assertEqual(plan.tasks["t_rig"].target_agent_id, RIGGING_ANIMATION_AGENT_ID)
        self.assertEqual(plan.tasks["t_rig"].dependencies, ["t_model"])

    def test_delegation_contract_serialization_roundtrip(self):
        contract = DelegationContract(
            title="Roundtrip Test",
            brief="Serialization test brief",
            domain_tasks={
                MATERIALS_AGENT_ID: [
                    AgentTask(task_id="t_mat", required_capability="materials.manage", task_type="create_material", input_params={"material_name": "Gold"})
                ]
            },
            bindings=[TaskOutputRef(task_id="t_model", path="name", expected_type="string")],
        )
        data = contract.to_dict()
        reconstructed = DelegationContract.from_dict(data)
        self.assertEqual(reconstructed.title, contract.title)
        self.assertEqual(len(reconstructed.domain_tasks[MATERIALS_AGENT_ID]), 1)
        self.assertEqual(len(reconstructed.bindings), 1)
        self.assertEqual(reconstructed.bindings[0].task_id, "t_model")


class TestDirectorAgent(unittest.TestCase):
    """Verifies DirectorAgent decomposition and human approval gating."""

    def setUp(self):
        self.director = DirectorAgent()

    def test_decompose_production_brief(self):
        brief = "Create a model with cylinder mesh, assign shiny metallic material, rig with armature, add rigid body physics, setup sun light, configure compositor denoise, and export to GLB."
        contract = self.director.decompose_brief(brief, title="Full Studio Pipeline")
        self.assertEqual(contract.director_agent_id, DIRECTOR_AGENT_ID)
        self.assertIn(MODELING_AGENT_ID, contract.domain_tasks)
        self.assertIn(MATERIALS_AGENT_ID, contract.domain_tasks)
        self.assertIn(RIGGING_ANIMATION_AGENT_ID, contract.domain_tasks)
        self.assertIn(SIMULATION_VFX_AGENT_ID, contract.domain_tasks)
        self.assertIn(RENDER_LIGHTING_AGENT_ID, contract.domain_tasks)
        self.assertIn(COMPOSITOR_AGENT_ID, contract.domain_tasks)
        self.assertIn(INTERCHANGE_DELIVERY_AGENT_ID, contract.domain_tasks)

    def test_submit_contract_requires_human_approval_without_token(self):
        contract = self.director.decompose_brief("Create a cube and export to GLB")
        executor = MockExecutor()
        dispatcher = AgentDispatcher(executor=executor)

        # Without trusted_approval (and auto-approve off), plan must pause in AWAITING_APPROVAL
        plan, results = self.director.submit_contract(contract, dispatcher, trusted_approval=False)
        self.assertEqual(plan.status, TaskStatus.AWAITING_APPROVAL)
        self.assertTrue(all(r.status == TaskStatus.AWAITING_APPROVAL for r in results))
        self.assertEqual(len(executor.calls), 0)  # No mutation executed!

    def test_submit_contract_untrusted_approval_rejected(self):
        contract = DelegationContract(
            title="Malicious Injection",
            brief="Inject approved=True",
            domain_tasks={
                MODELING_AGENT_ID: [
                    AgentTask(task_id="bad_task", required_capability="modeling.primitive", task_type="create_primitive", input_params={"approved": True})
                ]
            }
        )
        executor = MockExecutor()
        dispatcher = AgentDispatcher(executor=executor)
        with self.assertRaises(PermissionError):
            self.director.submit_contract(contract, dispatcher)

    def test_submit_contract_approved_executes_across_agents(self):
        contract = DelegationContract(
            title="Approved Delegation Plan",
            brief="Model, rig, and export asset",
            domain_tasks={
                MODELING_AGENT_ID: [
                    AgentTask(task_id="t1", required_capability="modeling.primitive", task_type="create_primitive", input_params={"primitive_type": "CUBE", "name": "HeroCube"})
                ],
                RIGGING_ANIMATION_AGENT_ID: [
                    AgentTask(task_id="t2", required_capability="rigging.armatures", task_type="create_armature", input_params={"name": "TestRig"}, dependencies=["t1"])
                ],
                INTERCHANGE_DELIVERY_AGENT_ID: [
                    AgentTask(task_id="t3", required_capability="interchange.asset_io", task_type="export_scene_asset", input_params={"filepath": "out.glb", "format": "GLB"}, dependencies=["t2"])
                ]
            },
            dependencies={"t2": ["t1"], "t3": ["t2"]},
        )
        executor = MockExecutor()
        dispatcher = AgentDispatcher(executor=executor)
        plan, results = self.director.submit_contract(contract, dispatcher, trusted_approval=True)
        self.assertEqual(plan.status, TaskStatus.SUCCEEDED)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.status == TaskStatus.SUCCEEDED for r in results))
        self.assertEqual(len(executor.calls), 3)


class TestSpecializedDomainAgents(unittest.TestCase):
    """Verifies individual specialized domain agent runners."""

    def test_rigging_animation_agent_untrusted_approval(self):
        agent = RiggingAnimationAgent()
        executor = MockExecutor()
        task = AgentTask(task_id="r1", required_capability="rigging.armatures", task_type="create_armature", input_params={"approved": True})
        res = agent.execute_task(task, executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])
        self.assertEqual(len(executor.calls), 0)

    def test_simulation_vfx_agent_untrusted_approval(self):
        agent = SimulationVFXAgent()
        executor = MockExecutor()
        task = AgentTask(task_id="s1", required_capability="physics.simulation", task_type="configure_physics", input_params={"approved": True})
        res = agent.execute_task(task, executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])
        self.assertEqual(len(executor.calls), 0)

    def test_interchange_delivery_agent_untrusted_approval(self):
        agent = InterchangeDeliveryAgent()
        executor = MockExecutor()
        task = AgentTask(task_id="i1", required_capability="interchange.asset_io", task_type="export_scene_asset", input_params={"approved": True})
        res = agent.execute_task(task, executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])
        self.assertEqual(len(executor.calls), 0)

    def test_compositor_agent_untrusted_approval(self):
        agent = CompositorAgent()
        executor = MockExecutor()
        task = AgentTask(task_id="c1", required_capability="compositor.pipeline", task_type="manage_compositor_nodes", input_params={"approved": True})
        res = agent.execute_task(task, executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])
        self.assertEqual(len(executor.calls), 0)


class TestNineAgentDeterministicRouting(unittest.TestCase):
    """Verifies CapabilityRouter priority routing across all 9 agents."""

    def setUp(self):
        self.registry = create_default_registry()
        self.router = CapabilityRouter(self.registry)

    def test_specialized_agents_preferred_over_generic_modeling(self):
        # Rigging
        res_rig = self.router.route(AgentTask(task_id="t1", required_capability=CAPABILITY_RIGGING_ARMATURES, task_type="create_armature"))
        self.assertTrue(res_rig.success)
        self.assertEqual(res_rig.agent.agent_id, RIGGING_ANIMATION_AGENT_ID)

        # Physics
        res_phys = self.router.route(AgentTask(task_id="t2", required_capability=CAPABILITY_PHYSICS_SIMULATION, task_type="configure_physics"))
        self.assertTrue(res_phys.success)
        self.assertEqual(res_phys.agent.agent_id, SIMULATION_VFX_AGENT_ID)

        # Asset IO
        res_io = self.router.route(AgentTask(task_id="t3", required_capability=CAPABILITY_INTERCHANGE_ASSET_IO, task_type="export_scene_asset"))
        self.assertTrue(res_io.success)
        self.assertEqual(res_io.agent.agent_id, INTERCHANGE_DELIVERY_AGENT_ID)

        # Compositor
        res_comp = self.router.route(AgentTask(task_id="t4", required_capability=CAPABILITY_COMPOSITOR_PIPELINE, task_type="manage_compositor_nodes"))
        self.assertTrue(res_comp.success)
        self.assertEqual(res_comp.agent.agent_id, COMPOSITOR_AGENT_ID)

        # Primitives still route to ModelingAgent
        res_model = self.router.route(AgentTask(task_id="t5", required_capability="modeling.primitive", task_type="create_primitive"))
        self.assertTrue(res_model.success)
        self.assertEqual(res_model.agent.agent_id, MODELING_AGENT_ID)


if __name__ == "__main__":
    unittest.main()
