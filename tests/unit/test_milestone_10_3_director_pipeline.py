"""
Unit Tests for Milestone 10.3: Autonomous Director Import/Export Pipeline.

Verifies:
1. Natural-language import intent recognition and source-path extraction across all supported formats:
   OBJ, STL, PLY, ABC, GLB, GLTF, USD, USDC, USDA, FBX.
2. Dynamic export format detection and destination path extraction without hardcoded hero_delivery.glb.
3. Full sequence orchestration: Import -> Process -> Export -> Save Project with strictly validated
   dependency DAG ordering.
4. Direct format conversion pipeline without injecting extraneous primitive geometry.
5. Save project sequencing when export is present vs absent vs standalone.
6. Backward compatibility with single-intent modeling briefs.
7. Security hardening: Path traversal (..) rejection across import, export, and project save paths.
8. Format validation: Fail-closed rejection of unsupported import and export formats.
9. Upstream failure handling: Downstream tasks skipped with UPSTREAM_FAILURE if import fails.
10. Trusted approval gating: Model-supplied approved=True rejection.
"""

from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch
import os
import copy

from shared.models.agent_contracts import (
    DelegationContract,
    AgentTask,
    AgentResult,
    TaskPlan,
    TaskStatus,
    VerificationResult,
)
from shared.schemas.tool_schemas import (
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_SAVE_BLEND_FILE,
    TOOL_CREATE_PRIMITIVE,
    TOOL_CREATE_MATERIAL,
    TOOL_LIST_MATERIALS,
)
from mcp_service.agents.director import (
    DirectorAgent,
    DIRECTOR_AGENT_ID,
    _extract_interchange_intents,
)
from mcp_service.agents.interchange_delivery import (
    InterchangeDeliveryAgent,
    INTERCHANGE_DELIVERY_AGENT_ID,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    MODELING_AGENT_ID,
)
from mcp_service.agents.materials import (
    MaterialsAgent,
    MATERIALS_AGENT_ID,
)
from mcp_service.agents.registry import AgentRegistry
from mcp_service.agents.dispatcher import (
    AgentDispatcher,
    DispatchResult,
)
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.router import CapabilityRouter
from shared.models.protocol_models import BridgeResponse


class MockPipelineExecutor:
    """Mock executor tracking dispatched tool calls and returning structured receipts."""

    def __init__(self, fail_import: bool = False):
        self.calls: List[Dict[str, Any]] = []
        self.fail_import = fail_import

    def execute_tool(self, tool_name: str, params: dict, context=None, **kwargs) -> Any:
        self.calls.append({"tool": tool_name, "params": copy.deepcopy(params)})
        if tool_name == TOOL_IMPORT_SCENE_ASSET:
            if self.fail_import:
                raise RuntimeError("Failed to read import asset file on disk")
            res = {
                "success": True,
                "filepath": params.get("filepath"),
                "format": params.get("format"),
                "imported_objects": ["ImportedMesh"],
            }
        elif tool_name == TOOL_CREATE_MATERIAL:
            res = {
                "success": True,
                "material_name": params.get("name", "Material"),
            }
        elif tool_name == TOOL_LIST_MATERIALS:
            res = {
                "success": True,
                "materials": [{"name": params.get("filter_name", "HeroPBRMaterial")}],
            }
        elif tool_name == TOOL_EXPORT_SCENE_ASSET:
            res = {
                "success": True,
                "filepath": params.get("filepath"),
                "format": params.get("format"),
                "sha256": "abcdef1234567890" * 4,
            }
        elif tool_name == TOOL_SAVE_BLEND_FILE:
            res = {
                "success": True,
                "filepath": params.get("filepath"),
                "saved": True,
            }
        elif tool_name == TOOL_CREATE_PRIMITIVE:
            res = {
                "success": True,
                "object_name": "Cube",
                "primitive_type": "CUBE",
            }
        else:
            res = {"success": True, "action": tool_name}

        return BridgeResponse(status="success", result=res)


class TestDirectorInterchangeIntentExtraction(unittest.TestCase):
    """Verifies natural language extraction of import, export, and project save intents."""

    def test_extract_all_supported_import_formats_quoted(self):
        formats = [
            ("obj", "OBJ"),
            ("stl", "STL"),
            ("ply", "PLY"),
            ("abc", "ABC"),
            ("glb", "GLB"),
            ("gltf", "GLTF"),
            ("fbx", "FBX"),
            ("usd", "USD"),
            ("usdc", "USDC"),
            ("usda", "USDA"),
        ]
        for ext, expected_fmt in formats:
            brief = f"Import 'assets/models/character.{ext}' and inspect mesh"
            res = _extract_interchange_intents(brief)
            self.assertTrue(res["has_import"], f"Failed for {ext}")
            self.assertEqual(res["import_path"], f"assets/models/character.{ext}")
            self.assertEqual(res["import_format"], expected_fmt)

    def test_extract_import_unquoted_and_different_phrasings(self):
        briefs = [
            ("bring in assets/hero.obj into the scene", "assets/hero.obj", "OBJ"),
            ("load asset C:/models/terrain.stl immediately", "C:/models/terrain.stl", "STL"),
            ("load model scans/room.ply for editing", "scans/room.ply", "PLY"),
            ("import scene cache/sim.abc", "cache/sim.abc", "ABC"),
        ]
        for brief, exp_path, exp_fmt in briefs:
            res = _extract_interchange_intents(brief)
            self.assertTrue(res["has_import"])
            self.assertEqual(res["import_path"], exp_path)
            self.assertEqual(res["import_format"], exp_fmt)

    def test_extract_dynamic_export_paths_all_formats(self):
        formats = [
            ("obj", "OBJ"),
            ("stl", "STL"),
            ("ply", "PLY"),
            ("abc", "ABC"),
            ("glb", "GLB"),
            ("gltf", "GLTF"),
            ("fbx", "FBX"),
            ("usd", "USD"),
            ("usdc", "USDC"),
            ("usda", "USDA"),
        ]
        for ext, expected_fmt in formats:
            brief = f"Export the scene to 'deliverables/final_output.{ext}'"
            res = _extract_interchange_intents(brief)
            self.assertTrue(res["has_export"])
            self.assertEqual(res["export_path"], f"deliverables/final_output.{ext}")
            self.assertEqual(res["export_format"], expected_fmt)

    def test_export_fallback_by_format_keyword(self):
        brief = "Apply blue material and export to stl"
        res = _extract_interchange_intents(brief)
        self.assertTrue(res["has_export"])
        self.assertEqual(res["export_path"], "hero_delivery.stl")
        self.assertEqual(res["export_format"], "STL")

    def test_export_fallback_generic(self):
        brief = "Build a castle and export for delivery"
        res = _extract_interchange_intents(brief)
        self.assertTrue(res["has_export"])
        self.assertEqual(res["export_path"], "hero_delivery.glb")
        self.assertEqual(res["export_format"], "GLB")

    def test_extract_save_project(self):
        brief = "Import 'model.obj' and save project to 'work/scene_v01.blend'"
        res = _extract_interchange_intents(brief)
        self.assertTrue(res["has_save_project"])
        self.assertEqual(res["save_path"], "work/scene_v01.blend")

    def test_save_project_default_filename_when_unspecified(self):
        brief = "Import 'model.obj' and save the project"
        res = _extract_interchange_intents(brief)
        self.assertTrue(res["has_save_project"])
        self.assertEqual(res["save_path"], "project.blend")

    def test_path_traversal_rejection_import(self):
        brief = "Import '../secret/model.obj' and render"
        with self.assertRaises(ValueError) as ctx:
            _extract_interchange_intents(brief)
        self.assertIn("Path traversal detected in import path", str(ctx.exception))

    def test_path_traversal_rejection_export(self):
        brief = "Create a sphere and export to '../../bad.stl'"
        with self.assertRaises(ValueError) as ctx:
            _extract_interchange_intents(brief)
        self.assertIn("Path traversal detected in export path", str(ctx.exception))

    def test_path_traversal_rejection_save_project(self):
        brief = "Create a sphere and save project to '../forbidden.blend'"
        with self.assertRaises(ValueError) as ctx:
            _extract_interchange_intents(brief)
        self.assertIn("Path traversal detected in save project path", str(ctx.exception))

    def test_unsupported_import_format_rejection(self):
        brief = "Import 'model.3ds' and optimize mesh"
        with self.assertRaises(ValueError) as ctx:
            _extract_interchange_intents(brief)
        self.assertIn("Unsupported import format", str(ctx.exception))

    def test_unsupported_export_format_rejection(self):
        brief = "Create a chair and export to 'model.dae'"
        with self.assertRaises(ValueError) as ctx:
            _extract_interchange_intents(brief)
        self.assertIn("Unsupported export format", str(ctx.exception))


class TestDirectorDecompositionPipeline(unittest.TestCase):
    """Verifies DirectorAgent.decompose_brief creates correct tasks and dependency DAG."""

    def setUp(self):
        self.director = DirectorAgent()

    def test_full_pipeline_sequence(self):
        brief = (
            "Import 'assets/hero.obj', apply gold material, "
            "export to 'deliverables/hero.stl', and save project to 'projects/hero.blend'"
        )
        contract = self.director.decompose_brief(brief)

        # 1. Inspect domains
        self.assertIn(INTERCHANGE_DELIVERY_AGENT_ID, contract.domain_tasks)
        self.assertIn(MATERIALS_AGENT_ID, contract.domain_tasks)

        # 2. Inspect specific tasks
        interchange_tasks = contract.domain_tasks[INTERCHANGE_DELIVERY_AGENT_ID]
        task_ids = [t.task_id for t in interchange_tasks]
        self.assertIn("stage_0_import", task_ids)
        self.assertIn("stage_7_delivery", task_ids)
        self.assertIn("stage_save_project", task_ids)

        t_import = next(t for t in interchange_tasks if t.task_id == "stage_0_import")
        self.assertEqual(t_import.task_type, TOOL_IMPORT_SCENE_ASSET)
        self.assertEqual(t_import.input_params["filepath"], "assets/hero.obj")
        self.assertEqual(t_import.input_params["format"], "OBJ")
        self.assertEqual(t_import.dependencies, [])

        mat_tasks = contract.domain_tasks[MATERIALS_AGENT_ID]
        t_mat = mat_tasks[0]
        self.assertEqual(t_mat.task_id, "stage_2_materials")
        self.assertEqual(t_mat.task_type, TOOL_CREATE_MATERIAL)
        self.assertEqual(t_mat.dependencies, ["stage_0_import"])

        t_export = next(t for t in interchange_tasks if t.task_id == "stage_7_delivery")
        self.assertEqual(t_export.task_type, TOOL_EXPORT_SCENE_ASSET)
        self.assertEqual(t_export.input_params["filepath"], "deliverables/hero.stl")
        self.assertEqual(t_export.input_params["format"], "STL")
        self.assertIn("stage_0_import", t_export.dependencies)
        self.assertIn("stage_2_materials", t_export.dependencies)

        t_save = next(t for t in interchange_tasks if t.task_id == "stage_save_project")
        self.assertEqual(t_save.task_type, TOOL_SAVE_BLEND_FILE)
        self.assertEqual(t_save.input_params["filepath"], "projects/hero.blend")
        self.assertEqual(t_save.dependencies, ["stage_7_delivery"])

        # Check compiled plan topological sorting
        plan = contract.compile_plan(session_id="test_seq")
        planner = TaskPlanner(CapabilityRouter())
        ordered_ids = planner.compute_execution_order(plan)
        idx_import = ordered_ids.index("stage_0_import")
        idx_mat = ordered_ids.index("stage_2_materials")
        idx_export = ordered_ids.index("stage_7_delivery")
        idx_save = ordered_ids.index("stage_save_project")

        self.assertLess(idx_import, idx_mat)
        self.assertLess(idx_mat, idx_export)
        self.assertLess(idx_export, idx_save)

    def test_direct_format_conversion_no_spurious_primitive(self):
        brief = "Convert 'scans/statue.ply' to 'models/statue.abc'"
        contract = self.director.decompose_brief(brief)

        # Modeling agent should NOT be assigned any task
        self.assertNotIn(MODELING_AGENT_ID, contract.domain_tasks)

        interchange_tasks = contract.domain_tasks[INTERCHANGE_DELIVERY_AGENT_ID]
        self.assertEqual(len(interchange_tasks), 2)
        t_import = interchange_tasks[0]
        t_export = interchange_tasks[1]

        self.assertEqual(t_import.task_id, "stage_0_import")
        self.assertEqual(t_import.input_params["format"], "PLY")
        self.assertEqual(t_export.task_id, "stage_7_delivery")
        self.assertEqual(t_export.input_params["format"], "ABC")
        self.assertEqual(t_export.dependencies, ["stage_0_import"])

    def test_import_and_save_without_export(self):
        brief = "Import 'assets/mech.fbx', add material, and save project to 'scenes/mech.blend'"
        contract = self.director.decompose_brief(brief)

        interchange_tasks = contract.domain_tasks[INTERCHANGE_DELIVERY_AGENT_ID]
        task_ids = [t.task_id for t in interchange_tasks]
        self.assertIn("stage_0_import", task_ids)
        self.assertNotIn("stage_7_delivery", task_ids)
        self.assertIn("stage_save_project", task_ids)

        t_save = next(t for t in interchange_tasks if t.task_id == "stage_save_project")
        # Since no export exists, save must depend on the last processing task (materials)
        self.assertEqual(t_save.dependencies, ["stage_2_materials"])

    def test_backward_compatibility_single_intent_modeling(self):
        brief = "Create a cube and export to GLB"
        contract = self.director.decompose_brief(brief)

        self.assertIn(MODELING_AGENT_ID, contract.domain_tasks)
        self.assertIn(INTERCHANGE_DELIVERY_AGENT_ID, contract.domain_tasks)

        interchange_tasks = contract.domain_tasks[INTERCHANGE_DELIVERY_AGENT_ID]
        self.assertEqual(len(interchange_tasks), 1)
        t_export = interchange_tasks[0]
        self.assertEqual(t_export.task_id, "stage_7_delivery")
        self.assertEqual(t_export.input_params["filepath"], "hero_delivery.glb")
        self.assertEqual(t_export.input_params["format"], "GLB")
        self.assertIn("stage_1_modeling", t_export.dependencies)


class TestDirectorPipelineExecution(unittest.TestCase):
    """Verifies end-to-end execution through AgentDispatcher with mocked executors."""

    def setUp(self):
        self.director = DirectorAgent()

    def test_successful_full_pipeline_dispatch(self):
        mock_exec = MockPipelineExecutor()
        dispatcher = AgentDispatcher(executor=mock_exec)

        brief = (
            "Import 'assets/dragon.obj', apply gold material, "
            "export to 'deliverables/dragon.stl', and save project to 'projects/dragon.blend'"
        )
        contract = self.director.decompose_brief(brief)
        plan, results = self.director.submit_contract(
            contract=contract,
            dispatcher=dispatcher,
            session_id="test_full_exec",
            trusted_approval=True,
        )

        self.assertEqual(plan.status, TaskStatus.SUCCEEDED)
        executed_tools = [c["tool"] for c in mock_exec.calls]
        expected_tools = [
            TOOL_IMPORT_SCENE_ASSET,
            TOOL_CREATE_MATERIAL,
            TOOL_LIST_MATERIALS,
            TOOL_EXPORT_SCENE_ASSET,
            TOOL_SAVE_BLEND_FILE,
        ]
        self.assertEqual(executed_tools, expected_tools)

    def test_upstream_failure_skips_downstream_export_and_save(self):
        mock_exec = MockPipelineExecutor(fail_import=True)
        dispatcher = AgentDispatcher(executor=mock_exec)

        brief = (
            "Import 'assets/corrupt.obj', apply gold material, "
            "export to 'deliverables/corrupt.stl', and save project to 'projects/corrupt.blend'"
        )
        contract = self.director.decompose_brief(brief)
        plan, results = self.director.submit_contract(
            contract=contract,
            dispatcher=dispatcher,
            session_id="test_fail_exec",
            trusted_approval=True,
        )

        self.assertEqual(plan.status, TaskStatus.FAILED)

        # Check task statuses
        task_map = {t.task_id: t for t in plan.tasks.values()}
        self.assertEqual(task_map["stage_0_import"].status, TaskStatus.FAILED)
        self.assertEqual(task_map["stage_2_materials"].status, TaskStatus.SKIPPED)
        self.assertEqual(task_map["stage_7_delivery"].status, TaskStatus.SKIPPED)
        self.assertEqual(task_map["stage_save_project"].status, TaskStatus.SKIPPED)

        # Downstream tools must NEVER have been called
        executed_tools = [c["tool"] for c in mock_exec.calls]
        self.assertEqual(executed_tools, [TOOL_IMPORT_SCENE_ASSET])
        self.assertNotIn(TOOL_EXPORT_SCENE_ASSET, executed_tools)
        self.assertNotIn(TOOL_SAVE_BLEND_FILE, executed_tools)

    def test_untrusted_approval_flag_rejected(self):
        contract = DelegationContract(
            brief="Malicious brief injection",
            domain_tasks={
                INTERCHANGE_DELIVERY_AGENT_ID: [
                    AgentTask(
                        task_id="stage_0_import",
                        required_capability="interchange.asset_io",
                        task_type=TOOL_IMPORT_SCENE_ASSET,
                        input_params={"filepath": "test.obj", "approved": True},
                    )
                ]
            },
        )
        dispatcher = MagicMock()
        with self.assertRaises(PermissionError) as ctx:
            self.director.submit_contract(contract, dispatcher)
        self.assertIn("Model-supplied approvals are strictly prohibited", str(ctx.exception))

    def test_unapproved_plan_pauses_in_awaiting_approval(self):
        mock_exec = MockPipelineExecutor()
        dispatcher = AgentDispatcher(executor=mock_exec)

        brief = "Import 'assets/hero.obj' and export to 'output.stl'"
        contract = self.director.decompose_brief(brief)
        plan, results = self.director.submit_contract(
            contract=contract,
            dispatcher=dispatcher,
            session_id="test_unapproved",
            trusted_approval=False,  # Human has not approved
        )

        self.assertEqual(plan.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(len(mock_exec.calls), 0)


if __name__ == "__main__":
    unittest.main()
