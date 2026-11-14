"""
Unit tests for Phase 3.2: Dynamic Workflow Orchestration & Checkpointing.
Verifies:
1. SceneCheckpointManager in-memory snapshot tree and diffing.
2. StageRollbackEngine delta computation and targeted restoration.
3. VerificationGate assertions (ObjectExistenceGate, GeometryHealthGate, MaterialBindingGate).
4. WorkflowDAG dependency topological sort and cycle detection.
5. WorkflowOrchestrator parameter handoffs, human approval gating, untrusted approval rejection,
   and 4-stage rollback with adaptive replanning recovery.
"""

import unittest
import copy
import time
from typing import Dict, Any, List, Optional

from shared.models.agent_contracts import (
    AgentTask,
    TaskStatus,
    TaskOutputRef,
    DelegationContract,
)
from shared.models.protocol_models import BridgeResponse
from mcp_service.workflow.checkpoints import SceneCheckpoint, SceneCheckpointManager
from mcp_service.workflow.rollback import RollbackReceipt, StageRollbackEngine
from mcp_service.workflow.verification_gates import (
    VerificationGate,
    VerificationResult,
    ObjectExistenceGate,
    GeometryHealthGate,
    MaterialBindingGate,
    CustomPredicateGate,
)
from mcp_service.workflow.orchestrator import (
    WorkflowStage,
    WorkflowDAG,
    WorkflowExecutionReport,
    WorkflowOrchestrator,
)


class MockBlenderExecutor:
    """Mock executor recording calls and simulating scene state."""
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.scene_objects: Dict[str, Dict[str, Any]] = {}
        self.materials: List[str] = []
        self.fail_tools: Dict[str, str] = {}

    def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None, trusted_approval: Optional[bool] = None) -> BridgeResponse:
        self.calls.append({"tool": tool_name, "args": copy.deepcopy(arguments), "trusted_approval": trusted_approval})
        arguments = arguments or {}

        if tool_name in self.fail_tools:
            return BridgeResponse.error(self.fail_tools[tool_name])

        if tool_name == "list_objects":
            objs = [{"name": name, "type": info.get("type", "MESH")} for name, info in self.scene_objects.items()]
            return BridgeResponse.success({"objects": objs})

        elif tool_name == "get_object_details":
            name = arguments.get("name")
            if name in self.scene_objects:
                return BridgeResponse.success(copy.deepcopy(self.scene_objects[name]))
            return BridgeResponse.error(f"Object not found: {name}")

        elif tool_name == "list_materials":
            mats = [{"name": m} for m in self.materials]
            return BridgeResponse.success({"materials": mats})

        elif tool_name == "create_primitive":
            name = arguments.get("name", "Primitive")
            self.scene_objects[name] = {
                "name": name,
                "type": "MESH",
                "location": arguments.get("location", [0.0, 0.0, 0.0]),
                "rotation": arguments.get("rotation", [0.0, 0.0, 0.0]),
                "scale": [1.0, 1.0, 1.0],
                "mesh_stats": {"vertices_count": 8, "polygons_count": 6},
                "materials": [],
                "modifiers": [],
            }
            return BridgeResponse.success({"name": name, "created": True})

        elif tool_name == "create_material":
            m_name = arguments.get("name", "Material")
            if m_name not in self.materials:
                self.materials.append(m_name)
            return BridgeResponse.success({"material_name": m_name, "created": True})

        elif tool_name == "delete_object":
            name = arguments.get("name")
            if name in self.scene_objects:
                del self.scene_objects[name]
                return BridgeResponse.success({"deleted": name})
            return BridgeResponse.error(f"Object not found: {name}")

        elif tool_name == "transform_object":
            name = arguments.get("name")
            if name in self.scene_objects:
                if "location" in arguments:
                    self.scene_objects[name]["location"] = list(arguments["location"])
                if "rotation_euler" in arguments:
                    self.scene_objects[name]["rotation"] = list(arguments["rotation_euler"])
                if "scale" in arguments:
                    self.scene_objects[name]["scale"] = list(arguments["scale"])
                return BridgeResponse.success({"transformed": name})
            return BridgeResponse.error(f"Object not found: {name}")

        elif tool_name == "edit_modifier_stack":
            name = arguments.get("object_name")
            action = arguments.get("action")
            mod_name = arguments.get("modifier_name")
            if name in self.scene_objects:
                mods = self.scene_objects[name].get("modifiers", [])
                if action == "add":
                    mods.append({"name": mod_name, "type": arguments.get("modifier_type", "SUBSURF")})
                elif action == "remove":
                    self.scene_objects[name]["modifiers"] = [m for m in mods if m.get("name") != mod_name]
                return BridgeResponse.success({"object": name, "modifiers": self.scene_objects[name]["modifiers"]})
            return BridgeResponse.error(f"Object not found: {name}")

        elif tool_name == "create_light":
            name = arguments.get("name", "Light")
            self.scene_objects[name] = {
                "name": name,
                "type": "LIGHT",
                "location": arguments.get("location", [0.0, 0.0, 5.0]),
                "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "materials": [],
                "modifiers": [],
            }
            return BridgeResponse.success({"name": name, "created": True})

        return BridgeResponse.success({"status": "ok", "tool": tool_name})


class TestPhase3WorkflowOrchestration(unittest.TestCase):

    def setUp(self):
        self.executor = MockBlenderExecutor()
        self.ckpt_manager = SceneCheckpointManager()
        self.rollback_engine = StageRollbackEngine(self.ckpt_manager)
        self.orchestrator = WorkflowOrchestrator(
            executor=self.executor,
            checkpoint_manager=self.ckpt_manager,
            rollback_engine=self.rollback_engine,
        )

    def test_checkpoint_manager_lifecycle_and_diff(self):
        """Verifies checkpoint capture, snapshot tree links, and diff calculation."""
        # Initial state: Cube
        self.executor.scene_objects["BaseCube"] = {
            "name": "BaseCube",
            "type": "MESH",
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "materials": [],
            "modifiers": [],
        }
        self.executor.materials = ["BaseMat"]

        ckpt1 = self.ckpt_manager.capture_checkpoint(stage_id="stage_1", executor=self.executor)
        self.assertEqual(ckpt1.stage_id, "stage_1")
        self.assertIn("BaseCube", ckpt1.objects)
        self.assertIn("BaseMat", ckpt1.materials)

        # Mutate scene: add Accessory and transform BaseCube
        self.executor.scene_objects["Accessory"] = {
            "name": "Accessory",
            "type": "MESH",
            "location": [1.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "materials": [],
            "modifiers": [],
        }
        self.executor.scene_objects["BaseCube"]["location"] = [0.0, 0.0, 5.0]

        ckpt2 = self.ckpt_manager.capture_checkpoint(stage_id="stage_2", executor=self.executor, parent_checkpoint_id=ckpt1.checkpoint_id)
        self.assertEqual(ckpt2.parent_checkpoint_id, ckpt1.checkpoint_id)

        # Compute diff
        diff = self.ckpt_manager.diff_checkpoints(ckpt1, ckpt2)
        self.assertEqual(diff["added_objects"], ["Accessory"])
        self.assertEqual(diff["removed_objects"], [])
        self.assertIn("BaseCube", diff["modified_objects"])
        self.assertEqual(diff["modified_objects"]["BaseCube"]["location"]["to"], [0.0, 0.0, 5.0])

    def test_rollback_engine_reverts_added_and_modified_objects(self):
        """Verifies StageRollbackEngine deletes added objects and restores modified transforms."""
        # Checkpoint: BaseCube at [0, 0, 0]
        base_ckpt = SceneCheckpoint(
            checkpoint_id="ckpt_baseline",
            stage_id="stage_baseline",
            objects={
                "BaseCube": {
                    "name": "BaseCube",
                    "type": "MESH",
                    "location": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                    "modifiers": [],
                    "materials": [],
                }
            },
        )

        # Live scene state has mutated: FaultyObj added, BaseCube moved to [10, 10, 10]
        self.executor.scene_objects["BaseCube"] = {
            "name": "BaseCube",
            "type": "MESH",
            "location": [10.0, 10.0, 10.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "modifiers": [],
            "materials": [],
        }
        self.executor.scene_objects["FaultyObj"] = {
            "name": "FaultyObj",
            "type": "MESH",
            "location": [2.0, 2.0, 2.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "modifiers": [],
            "materials": [],
        }

        receipt: RollbackReceipt = self.rollback_engine.rollback_to_checkpoint(base_ckpt, self.executor)
        self.assertTrue(receipt.success)
        self.assertTrue(receipt.verified)
        self.assertEqual(receipt.objects_removed, ["FaultyObj"])
        self.assertEqual(receipt.objects_restored, ["BaseCube"])

        # Check live scene: FaultyObj is gone, BaseCube location is [0, 0, 0]
        self.assertNotIn("FaultyObj", self.executor.scene_objects)
        self.assertEqual(self.executor.scene_objects["BaseCube"]["location"], [0.0, 0.0, 0.0])

    def test_verification_gates_evaluations(self):
        """Verifies ObjectExistenceGate and GeometryHealthGate pass and fail correctly."""
        self.executor.scene_objects["TargetMesh"] = {
            "name": "TargetMesh",
            "type": "MESH",
            "mesh_stats": {"vertices_count": 100, "polygons_count": 80},
            "materials": ["PBR_Mat"],
        }

        # ObjectExistenceGate
        g_exist_ok = ObjectExistenceGate(required_objects=["TargetMesh"])
        self.assertTrue(g_exist_ok.evaluate("stage_x", {}, self.executor).passed)

        g_exist_fail = ObjectExistenceGate(required_objects=["MissingMesh"])
        res_fail = g_exist_fail.evaluate("stage_x", {}, self.executor)
        self.assertFalse(res_fail.passed)
        self.assertIn("Missing required objects", res_fail.message)

        # GeometryHealthGate
        g_geom_ok = GeometryHealthGate("TargetMesh", min_vertices=50, min_polygons=50)
        self.assertTrue(g_geom_ok.evaluate("stage_x", {}, self.executor).passed)

        g_geom_fail = GeometryHealthGate("TargetMesh", min_vertices=500, min_polygons=500)
        self.assertFalse(g_geom_fail.evaluate("stage_x", {}, self.executor).passed)

        # MaterialBindingGate
        g_mat_ok = MaterialBindingGate("TargetMesh", expected_material="PBR_Mat")
        self.assertTrue(g_mat_ok.evaluate("stage_x", {}, self.executor).passed)

        g_mat_fail = MaterialBindingGate("TargetMesh", expected_material="Missing_Mat")
        self.assertFalse(g_mat_fail.evaluate("stage_x", {}, self.executor).passed)

    def test_workflow_dag_topological_sort_and_cycle(self):
        """Verifies Kahn's algorithm sorting and cycle detection."""
        dag = WorkflowDAG(title="Test Pipeline")
        s1 = WorkflowStage("s1", "Stage 1", "agent.modeling", AgentTask("s1", "cap", "tool1", {}))
        s2 = WorkflowStage("s2", "Stage 2", "agent.materials", AgentTask("s2", "cap", "tool2", {}), dependencies=["s1"])
        s3 = WorkflowStage("s3", "Stage 3", "agent.render_lighting", AgentTask("s3", "cap", "tool3", {}), dependencies=["s2"])

        dag.add_stage(s3)
        dag.add_stage(s1)
        dag.add_stage(s2)

        order = dag.compute_execution_order()
        self.assertEqual(order, ["s1", "s2", "s3"])

        # Create cycle
        s1.dependencies = ["s3"]
        with self.assertRaises(ValueError) as ctx:
            dag.compute_execution_order()
        self.assertIn("Dependency cycle detected", str(ctx.exception))

    def test_workflow_parameter_handoff_resolution(self):
        """Verifies parameter handoffs resolve from upstream outputs."""
        dag = WorkflowDAG(title="Parameter Handoff Pipeline")
        s1 = WorkflowStage("s1", "Stage 1", "agent.modeling", AgentTask("s1", "cap", "create_primitive", {"name": "HeroBox"}))
        s2 = WorkflowStage(
            "s2",
            "Stage 2",
            "agent.materials",
            AgentTask("s2", "cap", "create_material", {"name": "$s1.name"}),
            dependencies=["s1"],
        )
        dag.add_stage(s1)
        dag.add_stage(s2)

        report = self.orchestrator.execute_workflow(dag, requires_human_approval=False)
        self.assertEqual(report.status, "SUCCEEDED")
        self.assertIn("HeroBox", self.executor.materials)

    def test_workflow_human_approval_gating(self):
        """Verifies unapproved workflow is paused in AWAITING_APPROVAL with zero mutation."""
        dag = WorkflowDAG(title="Gated Pipeline")
        s1 = WorkflowStage("s1", "Stage 1", "agent.modeling", AgentTask("s1", "cap", "create_primitive", {"name": "Box"}))
        dag.add_stage(s1)

        report = self.orchestrator.execute_workflow(
            dag,
            requires_human_approval=True,
            approval_status="PENDING",
            approval_token=None,
        )
        self.assertEqual(report.status, "AWAITING_APPROVAL")
        self.assertEqual(len(self.executor.scene_objects), 0)

    def test_workflow_fail_closed_untrusted_approval(self):
        """Verifies fail-closed rejection when untrusted approved=True flag is injected."""
        dag = WorkflowDAG(title="Malicious Pipeline")
        s1 = WorkflowStage(
            "s1",
            "Stage 1",
            "agent.modeling",
            AgentTask("s1", "cap", "create_primitive", {"name": "Box", "approved": True}),
        )
        dag.add_stage(s1)

        with self.assertRaises(PermissionError) as ctx:
            self.orchestrator.execute_workflow(dag, requires_human_approval=True)
        self.assertIn("Untrusted approved=True flag detected", str(ctx.exception))
        self.assertEqual(len(self.executor.scene_objects), 0)

    def test_workflow_four_stage_rollback_and_adaptive_resumption(self):
        """
        Critical Milestone 3.2 Verification:
        4-stage pipeline where Stage 3 fails initially, StageRollbackEngine restores Stage 2 checkpoint,
        adaptive replanning adjusts Stage 3 task, Stage 3 succeeds on retry, and Stage 4 completes.
        """
        dag = WorkflowDAG(title="4-Stage Resilient Production Pipeline")

        # Stage 1: Modeling (creates HeroMesh)
        s1 = WorkflowStage(
            stage_id="stage_1_model",
            name="Modeling Blockout",
            agent_id="agent.modeling",
            task=AgentTask("stage_1_model", "modeling.primitive", "create_primitive", {"name": "HeroMesh"}),
            verification_gates=[ObjectExistenceGate(["HeroMesh"])],
        )

        # Stage 2: Materials (creates HeroMat)
        s2 = WorkflowStage(
            stage_id="stage_2_mat",
            name="Material Assignment",
            agent_id="agent.materials",
            task=AgentTask("stage_2_mat", "materials.manage", "create_material", {"name": "HeroMat"}),
            dependencies=["stage_1_model"],
            verification_gates=[ObjectExistenceGate(["HeroMesh"])],
        )

        # Stage 3: Physics / Detail (will intentionally fail on first attempt by creating FaultyArtifact)
        s3 = WorkflowStage(
            stage_id="stage_3_physics",
            name="Physics Simulation",
            agent_id="agent.simulation_vfx",
            task=AgentTask("stage_3_physics", "physics.simulation", "create_primitive", {"name": "FaultyArtifact"}),
            dependencies=["stage_2_mat"],
            max_retries=1,
            # Gate requires HeroMesh to have min 20 vertices; FaultyArtifact has 8 so fails
            verification_gates=[GeometryHealthGate("FaultyArtifact", min_vertices=20)],
        )

        # Stage 4: Lighting (creates StudioSun)
        s4 = WorkflowStage(
            stage_id="stage_4_light",
            name="Studio Lighting",
            agent_id="agent.render_lighting",
            task=AgentTask("stage_4_light", "lighting.manage", "create_light", {"name": "StudioSun"}),
            dependencies=["stage_3_physics"],
            verification_gates=[ObjectExistenceGate(["StudioSun"])],
        )

        dag.add_stage(s1)
        dag.add_stage(s2)
        dag.add_stage(s3)
        dag.add_stage(s4)

        # Define adaptive replanner callback
        def adaptive_replanner(stage: WorkflowStage, failure_reason: str) -> Optional[AgentTask]:
            if stage.stage_id == "stage_3_physics":
                # Adaptively replace FaultyArtifact with a valid task
                # Remove the failing gate for the adapted run
                stage.verification_gates = [ObjectExistenceGate(["HeroMesh"])]
                return AgentTask(
                    task_id="stage_3_physics_adapted",
                    required_capability="physics.simulation",
                    task_type="create_primitive",
                    input_params={"name": "ValidAccessory"},
                )
            return None

        report: WorkflowExecutionReport = self.orchestrator.execute_workflow(
            dag,
            requires_human_approval=False,
            adaptive_replan_fn=adaptive_replanner,
        )

        # Verification of orchestration report
        self.assertEqual(report.status, "SUCCEEDED")
        self.assertEqual(len(report.rollbacks_executed), 1)

        # Verify rollback receipt recorded
        rb = report.rollbacks_executed[0]
        self.assertTrue(rb["success"])
        self.assertEqual(rb["stage_id"], "stage_3_physics")
        self.assertIn("FaultyArtifact", rb["objects_removed"])

        # Check all 4 stages succeeded
        self.assertEqual(dag.stages["stage_1_model"].status, TaskStatus.SUCCEEDED)
        self.assertEqual(dag.stages["stage_2_mat"].status, TaskStatus.SUCCEEDED)
        self.assertEqual(dag.stages["stage_3_physics"].status, TaskStatus.SUCCEEDED)
        self.assertEqual(dag.stages["stage_4_light"].status, TaskStatus.SUCCEEDED)

        # Verify live scene has HeroMesh, ValidAccessory, StudioSun; FaultyArtifact is completely absent
        self.assertIn("HeroMesh", self.executor.scene_objects)
        self.assertIn("ValidAccessory", self.executor.scene_objects)
        self.assertIn("StudioSun", self.executor.scene_objects)
        self.assertNotIn("FaultyArtifact", self.executor.scene_objects)


if __name__ == "__main__":
    unittest.main()

