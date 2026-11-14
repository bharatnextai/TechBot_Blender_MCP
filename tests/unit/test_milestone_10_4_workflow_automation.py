"""
Unit Tests for Capability 10 — Milestone 10.4: Dynamic Workflow Automation,
Checkpointing & Batch Operations.

Verifies:
1. Director-to-WorkflowOrchestrator integration and DAG execution.
2. In-memory pre-stage SceneCheckpoint capture before import stages.
3. Verification gates (MeshManifoldnessGate, TextureBoundsGate) pass and failure behavior.
4. Automatic rollback to checkpoint after injected import/gate failure.
5. Automatic rollback to checkpoint after injected export failure.
6. Preservation of pre-existing scene content and cleanup of orphaned objects.
7. Batch multi-asset conversion (OBJ/FBX -> GLB) with SHA-256 sidecar generation.
8. Per-asset failure isolation in batch runs (failure in asset K does not contaminate K-1 or K+1).
9. Security invariants: Path traversal rejection across batch input and output paths.
10. Trusted approval gating: Model-supplied approved=True rejection and unapproved pause.
"""

from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock
import os
import copy
import json
import tempfile
from pathlib import Path

from shared.models.agent_contracts import (
    DelegationContract,
    AgentTask,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.director import DirectorAgent
from mcp_service.agents.dispatcher import AgentDispatcher
from mcp_service.workflow.checkpoints import (
    SceneCheckpoint,
    SceneCheckpointManager,
    is_response_success,
)
from mcp_service.workflow.rollback import (
    RollbackReceipt,
    StageRollbackEngine,
)
from mcp_service.workflow.verification_gates import (
    VerificationResult,
    VerificationGate,
    MeshManifoldnessGate,
    TextureBoundsGate,
    GeometryHealthGate,
    ObjectExistenceGate,
)
from mcp_service.workflow.orchestrator import (
    WorkflowStage,
    WorkflowDAG,
    WorkflowExecutionReport,
    WorkflowOrchestrator,
)
from mcp_service.workflow.batch import (
    BatchItemResult,
    BatchExecutionReport,
    BatchAssetProcessor,
)


class MockWorkflowBlenderExecutor:
    """Mock BlenderExecutor maintaining in-memory scene state for checkpointing and rollback."""

    def __init__(self, fail_tool: Optional[str] = None):
        self.objects: Dict[str, Dict[str, Any]] = {}
        self.materials: List[str] = ["InitialMaterial"]
        self.calls: List[Dict[str, Any]] = []
        self.fail_tool = fail_tool
        self.purged_count = 0

    def execute_tool(self, tool_name: str, params: dict, context=None, **kwargs) -> BridgeResponse:
        self.calls.append({"tool": tool_name, "params": copy.deepcopy(params)})

        if self.fail_tool and tool_name == self.fail_tool:
            return BridgeResponse(status="error", message=f"Injected synthetic failure for '{tool_name}'")

        if tool_name == "list_objects":
            obj_list = [{"name": name, "type": data.get("type", "MESH")} for name, data in self.objects.items()]
            return BridgeResponse(status="success", result={"objects": obj_list})

        elif tool_name == "get_object_details":
            name = params.get("name")
            if name not in self.objects:
                return BridgeResponse(status="error", message=f"Object not found: '{name}'")
            return BridgeResponse(status="success", result=copy.deepcopy(self.objects[name]))

        elif tool_name == "list_materials":
            mat_list = [{"name": m} for m in self.materials]
            return BridgeResponse(status="success", result={"materials": mat_list})

        elif tool_name == "delete_object":
            name = params.get("name")
            if name in self.objects:
                del self.objects[name]
                return BridgeResponse(status="success", result={"deleted": name})
            return BridgeResponse(status="error", message=f"Cannot delete non-existent object: '{name}'")

        elif tool_name == "transform_object":
            name = params.get("name")
            if name in self.objects:
                if "location" in params:
                    self.objects[name]["location"] = list(params["location"])
                if "rotation_euler" in params:
                    self.objects[name]["rotation"] = list(params["rotation_euler"])
                if "scale" in params:
                    self.objects[name]["scale"] = list(params["scale"])
                return BridgeResponse(status="success", result={"name": name, "transformed": True})
            return BridgeResponse(status="error", message=f"Object not found for transform: '{name}'")

        elif tool_name == "purge_orphaned_datablocks":
            self.purged_count += 1
            return BridgeResponse(status="success", result={"purged_count": 3, "purged": True})

        elif tool_name == "inspect_scene_data":
            cat = params.get("category")
            target = params.get("target_name")
            if cat == "mesh_topology":
                if target in self.objects:
                    stats = self.objects[target].get("mesh_stats", {})
                    return BridgeResponse(
                        status="success",
                        result={
                            "category": "mesh_topology",
                            "target_name": target,
                            "vertex_count": stats.get("vertices_count", 8),
                            "polygon_count": stats.get("polygons_count", 6),
                            "edge_count": stats.get("edges_count", 12),
                            "dimensions": self.objects[target].get("dimensions", [2.0, 2.0, 2.0]),
                        },
                    )
                return BridgeResponse(status="error", message=f"Object not found: '{target}'")

            elif cat == "uv_layers":
                if target in self.objects:
                    uv_layers = self.objects[target].get("uv_layers", [])
                    return BridgeResponse(
                        status="success",
                        result={
                            "category": "uv_layers",
                            "target_name": target,
                            "layers": uv_layers,
                            "active_layer": uv_layers[0]["name"] if uv_layers else None,
                        },
                    )
                return BridgeResponse(status="error", message=f"Object not found: '{target}'")

            return BridgeResponse(status="success", result={})

        elif tool_name == "import_scene_asset":
            filepath = params.get("filepath", "asset.obj")
            stem = Path(filepath).stem
            # Register imported object into mock scene
            self.objects[stem] = {
                "name": stem,
                "type": "MESH",
                "location": [0.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "dimensions": [2.0, 2.0, 2.0],
                "materials": [],
                "modifiers": [],
                "mesh_stats": {"vertices_count": 8, "edges_count": 12, "polygons_count": 6},
                "uv_layers": [{"name": "UVMap", "active": True}],
            }
            return BridgeResponse(
                status="success",
                result={
                    "success": True,
                    "filepath": filepath,
                    "format": params.get("format", "OBJ"),
                    "imported_objects": [stem],
                },
            )

        elif tool_name == "export_scene_asset":
            filepath = params.get("filepath", "out.glb")
            # Write a small file on disk if path exists to simulate real exporter
            try:
                p = Path(filepath)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"GLTF_MOCK_DATA")
                sidecar = Path(f"{filepath}.sha256")
                sidecar.write_text(json.dumps({"sha256": "mock_hash_12345", "filepath": str(p)}), encoding="utf-8")
            except Exception:
                pass
            return BridgeResponse(
                status="success",
                result={
                    "success": True,
                    "filepath": filepath,
                    "format": params.get("format", "GLB"),
                    "sha256": "mock_hash_12345",
                },
            )

        elif tool_name == "create_material":
            name = params.get("name", "NewMaterial")
            self.materials.append(name)
            return BridgeResponse(status="success", result={"name": name, "created": True})

        return BridgeResponse(status="success", result={"action": tool_name})


class TestWorkflowOrchestratorIntegration(unittest.TestCase):
    """Verifies DirectorAgent integration with WorkflowOrchestrator."""

    def setUp(self):
        self.executor = MockWorkflowBlenderExecutor()
        # Add a pre-existing object that must survive rollbacks
        self.executor.objects["PreExistingEnvironment"] = {
            "name": "PreExistingEnvironment",
            "type": "MESH",
            "location": [10.0, 10.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "dimensions": [5.0, 5.0, 1.0],
            "materials": ["InitialMaterial"],
            "modifiers": [],
            "mesh_stats": {"vertices_count": 4, "edges_count": 4, "polygons_count": 1},
        }
        self.orchestrator = WorkflowOrchestrator(executor=self.executor)
        self.director = DirectorAgent()

    def test_director_submits_workflow_and_captures_checkpoints(self):
        brief = "Convert 'assets/hero.obj' to 'deliverables/hero.glb'"
        contract = self.director.decompose_brief(brief)

        report = self.director.submit_workflow(
            contract=contract,
            orchestrator=self.orchestrator,
            trusted_approval=True,
        )

        self.assertEqual(report.status, "SUCCEEDED")
        self.assertGreaterEqual(len(report.checkpoints_captured), 2)
        # Verify stages were executed in topological order
        self.assertEqual(report.execution_order, ["stage_0_import", "stage_7_delivery"])
        # Verify pre-existing object is completely intact
        self.assertIn("PreExistingEnvironment", self.executor.objects)
        # Verify imported object was registered
        self.assertIn("hero", self.executor.objects)

    def test_unapproved_workflow_pauses_in_awaiting_approval(self):
        brief = "Convert 'assets/hero.obj' to 'deliverables/hero.glb'"
        contract = self.director.decompose_brief(brief)

        report = self.director.submit_workflow(
            contract=contract,
            orchestrator=self.orchestrator,
            trusted_approval=False,  # Unapproved
        )

        self.assertEqual(report.status, "AWAITING_APPROVAL")
        self.assertIn("Awaiting trusted human approval", report.summary)
        # Zero tools should have been executed
        self.assertEqual(len(self.executor.calls), 0)

    def test_untrusted_model_approval_rejected(self):
        brief = "Convert 'assets/hero.obj' to 'deliverables/hero.glb'"
        contract = self.director.decompose_brief(brief)
        # Inject untrusted approved=True in task params
        for tasks in contract.domain_tasks.values():
            for t in tasks:
                t.input_params["approved"] = True

        with self.assertRaises(PermissionError) as ctx:
            self.director.submit_workflow(
                contract=contract,
                orchestrator=self.orchestrator,
                trusted_approval=True,
            )
        self.assertIn("Model-supplied approvals are strictly prohibited", str(ctx.exception))


class TestVerificationGatesAndRollback(unittest.TestCase):
    """Verifies VerificationGates and automatic rollback behavior."""

    def setUp(self):
        self.executor = MockWorkflowBlenderExecutor()
        self.executor.objects["GroundPlane"] = {
            "name": "GroundPlane",
            "type": "MESH",
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "dimensions": [10.0, 10.0, 0.1],
            "mesh_stats": {"vertices_count": 4, "edges_count": 4, "polygons_count": 1},
        }
        self.orchestrator = WorkflowOrchestrator(executor=self.executor)
        self.director = DirectorAgent()

    def test_mesh_manifoldness_gate_passes_healthy_geometry(self):
        self.executor.objects["HealthyMesh"] = {
            "name": "HealthyMesh",
            "type": "MESH",
            "dimensions": [1.0, 1.0, 1.0],
            "mesh_stats": {"vertices_count": 8, "edges_count": 12, "polygons_count": 6},
        }
        gate = MeshManifoldnessGate(object_name="HealthyMesh")
        res = gate.evaluate("stage_import", {"target_object": "HealthyMesh"}, self.executor)
        self.assertTrue(res.passed)
        self.assertIn("passed manifoldness verification", res.message)

    def test_mesh_manifoldness_gate_fails_degenerate_geometry(self):
        # Zero polygons
        self.executor.objects["DegenerateMesh"] = {
            "name": "DegenerateMesh",
            "type": "MESH",
            "dimensions": [0.0, 0.0, 0.0],
            "mesh_stats": {"vertices_count": 2, "edges_count": 1, "polygons_count": 0},
        }
        gate = MeshManifoldnessGate(object_name="DegenerateMesh")
        res = gate.evaluate("stage_import", {"target_object": "DegenerateMesh"}, self.executor)
        self.assertFalse(res.passed)
        self.assertIn("failed manifoldness/topology check", res.message)

    def test_texture_bounds_gate_passes_with_uv_layer(self):
        self.executor.objects["TexturedAsset"] = {
            "name": "TexturedAsset",
            "type": "MESH",
            "uv_layers": [{"name": "UVMap", "active": True}],
        }
        gate = TextureBoundsGate(object_name="TexturedAsset", require_uv=True)
        res = gate.evaluate("stage_import", {"target_object": "TexturedAsset"}, self.executor)
        self.assertTrue(res.passed)

    def test_texture_bounds_gate_fails_when_uv_missing(self):
        self.executor.objects["UntexturedAsset"] = {
            "name": "UntexturedAsset",
            "type": "MESH",
            "uv_layers": [],
        }
        gate = TextureBoundsGate(object_name="UntexturedAsset", require_uv=True)
        res = gate.evaluate("stage_import", {"target_object": "UntexturedAsset"}, self.executor)
        self.assertFalse(res.passed)
        self.assertIn("has no UV layers", res.message)

    def test_automatic_rollback_on_gate_failure_purges_unwanted_mesh(self):
        brief = "Convert 'assets/corrupt.obj' to 'deliverables/corrupt.glb'"
        contract = self.director.decompose_brief(brief)

        # Inject custom gate that will fail on stage_0_import
        class AlwaysFailGate(VerificationGate):
            gate_id = "injected_fail"
            def evaluate(self, s, o, ex):
                return VerificationResult(passed=False, gate_id=self.gate_id, message="Forced failure")

        custom_gates = {"stage_0_import": [AlwaysFailGate()]}

        report = self.director.submit_workflow(
            contract=contract,
            orchestrator=self.orchestrator,
            trusted_approval=True,
            gates=custom_gates,
        )

        self.assertEqual(report.status, "FAILED")
        self.assertGreaterEqual(len(report.rollbacks_executed), 1)

        # Verify: corrupted mesh was deleted from scene by rollback engine
        self.assertNotIn("corrupt", self.executor.objects)
        # Verify: pre-existing scene object was completely preserved
        self.assertIn("GroundPlane", self.executor.objects)
        # Verify: downstream export was SKIPPED and never reached
        self.assertEqual(report.stages["stage_7_delivery"]["status"], "skipped")

    def test_automatic_rollback_on_export_failure(self):
        # Create executor where export_scene_asset fails
        fail_exec = MockWorkflowBlenderExecutor(fail_tool="export_scene_asset")
        fail_exec.objects["SceneLight"] = {
            "name": "SceneLight",
            "type": "LIGHT",
            "location": [0.0, 0.0, 5.0],
        }
        orch = WorkflowOrchestrator(executor=fail_exec)

        brief = "Convert 'assets/good.obj' to 'deliverables/good.glb'"
        contract = self.director.decompose_brief(brief)

        report = self.director.submit_workflow(
            contract=contract,
            orchestrator=orch,
            trusted_approval=True,
        )

        self.assertEqual(report.status, "FAILED")
        self.assertEqual(report.stages["stage_0_import"]["status"], "succeeded")
        self.assertEqual(report.stages["stage_7_delivery"]["status"], "failed")
        # Pre-existing light is preserved
        self.assertIn("SceneLight", fail_exec.objects)


class TestBatchAssetProcessor(unittest.TestCase):
    """Verifies BatchAssetProcessor multi-asset conversions and failure isolation."""

    def setUp(self):
        self.executor = MockWorkflowBlenderExecutor()
        self.orchestrator = WorkflowOrchestrator(executor=self.executor)
        self.director = DirectorAgent()
        self.temp_dir = tempfile.mkdtemp(prefix="umcp_batch_test_")
        self.output_dir = os.path.join(self.temp_dir, "output").replace("\\", "/")
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_batch_convert_multiple_assets_success(self):
        inputs = [
            os.path.join(self.temp_dir, "model_a.obj").replace("\\", "/"),
            os.path.join(self.temp_dir, "model_b.fbx").replace("\\", "/"),
            os.path.join(self.temp_dir, "model_c.obj").replace("\\", "/"),
        ]
        processor = BatchAssetProcessor(
            orchestrator=self.orchestrator,
            executor=self.executor,
            director=self.director,
        )

        report = processor.process_batch(
            input_paths=inputs,
            output_dir=self.output_dir,
            target_format="GLB",
            trusted_approval=True,
        )

        self.assertEqual(report.status, "SUCCEEDED")
        self.assertEqual(report.total_assets, 3)
        self.assertEqual(report.succeeded_count, 3)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(len(report.items), 3)

        for item in report.items:
            self.assertEqual(item.status, "SUCCEEDED")
            self.assertTrue(item.output_path.endswith(".glb"))
            self.assertTrue(item.sidecar_path.endswith(".glb.sha256"))
            self.assertEqual(item.sha256, "mock_hash_12345")

        # Datablocks should have been safely purged between iterations
        self.assertGreaterEqual(self.executor.purged_count, 3)

    def test_batch_failure_isolation_between_assets(self):
        # We simulate a batch of 3 assets where the 2nd asset has non-manifold geometry
        inputs = [
            os.path.join(self.temp_dir, "good_asset_1.obj").replace("\\", "/"),
            os.path.join(self.temp_dir, "bad_corrupt_asset_2.obj").replace("\\", "/"),
            os.path.join(self.temp_dir, "good_asset_3.fbx").replace("\\", "/"),
        ]

        class FailSecondAssetGate(VerificationGate):
            gate_id = "fail_second_gate"
            def evaluate(self, sid, out, ex):
                if isinstance(out, dict) and "bad_corrupt_asset_2" in out.get("imported_objects", []):
                    return VerificationResult(passed=False, gate_id=self.gate_id, message="Non-manifold mesh geometry")
                return VerificationResult(passed=True, gate_id=self.gate_id, message="OK")

        processor = BatchAssetProcessor(
            orchestrator=self.orchestrator,
            executor=self.executor,
            director=self.director,
        )

        report = processor.process_batch(
            input_paths=inputs,
            output_dir=self.output_dir,
            target_format="GLB",
            trusted_approval=True,
            gates={"stage_0_import": [FailSecondAssetGate()]},
        )

        # Report must be PARTIAL: asset 1 succeeded, asset 2 failed, asset 3 succeeded
        self.assertEqual(report.status, "PARTIAL")
        self.assertEqual(report.total_assets, 3)
        self.assertEqual(report.succeeded_count, 2)
        self.assertEqual(report.failed_count, 1)

        self.assertEqual(report.items[0].status, "SUCCEEDED")
        self.assertEqual(report.items[1].status, "FAILED")
        self.assertTrue(report.items[1].rollback_performed)
        self.assertIn("Non-manifold", report.items[1].error)
        self.assertEqual(report.items[2].status, "SUCCEEDED")

        # Asset 1 and 3 outputs must exist on disk
        self.assertTrue(Path(report.items[0].output_path).exists())
        self.assertTrue(Path(report.items[2].output_path).exists())

    def test_batch_path_traversal_rejection(self):
        processor = BatchAssetProcessor(
            orchestrator=self.orchestrator,
            executor=self.executor,
            director=self.director,
        )

        # Path traversal in output directory
        report = processor.process_batch(
            input_paths=["model.obj"],
            output_dir="../../secret_dir",
            target_format="GLB",
        )
        self.assertEqual(report.status, "FAILED")
        self.assertIn("Path traversal detected", report.summary)

        # Path traversal in one input path
        report2 = processor.process_batch(
            input_paths=["../bad_file.obj"],
            output_dir=self.output_dir,
            target_format="GLB",
        )
        self.assertEqual(report2.status, "FAILED")
        self.assertIn("Path traversal detected", report2.items[0].error)


if __name__ == "__main__":
    unittest.main()
