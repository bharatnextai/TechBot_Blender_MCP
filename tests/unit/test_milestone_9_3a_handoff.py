"""
Unit Tests for Milestone 9.3A: Rendered Media Handoff Foundation.
Verifies:
1. Director render-to-VSE TaskOutputRef compilation and binding.
2. Dynamic reference resolution against upstream render receipts in AgentDispatcher.
3. Fail-closed rejection of missing, failed, null, or type-mismatched render receipts.
4. Render-before-import dependency DAG ordering.
5. VSE still-image duration configuration and boundary validation in handle_create_vse_strip.
6. Actual planned strip references for transitions (no hardcoded Strip1/Strip2).
7. Audio strip creation and configuration dependency chaining.
8. Trusted approval enforcement and untrusted approved=True rejection on compound workflows.
9. Backward compatibility with existing single-intent briefs.
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
    TaskOutputRef,
    VerificationResult,
)
from shared.schemas.tool_schemas import (
    TOOL_CREATE_VSE_STRIP,
    TOOL_CREATE_VSE_TEXT_STRIP,
    TOOL_CREATE_VSE_TRANSITION,
    TOOL_CONFIGURE_VSE_AUDIO,
    TOOL_RENDER_VSE_SEQUENCE,
    TOOL_SPLIT_VSE_STRIP,
    TOOL_RENDER_SCENE,
    TOOL_MANAGE_COMPOSITOR_NODES,
)
from mcp_service.agents.director import DirectorAgent, DIRECTOR_AGENT_ID
from mcp_service.agents.video_editor import (
    VideoEditorAgent,
    VIDEO_EDITOR_AGENT_ID,
    create_video_editor_manifest,
)
from mcp_service.agents.render_lighting import (
    RenderLightingAgent,
    RENDER_LIGHTING_AGENT_ID,
)
from mcp_service.agents.compositor import (
    CompositorAgent,
    COMPOSITOR_AGENT_ID,
)
from mcp_service.agents.registry import AgentRegistry
from mcp_service.agents.dispatcher import (
    AgentDispatcher,
    DispatchResult,
    BindingResolutionError,
    resolve_task_references,
)
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.router import CapabilityRouter
from shared.models.protocol_models import BridgeResponse
from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
from blender_addon.universal_mcp.bridge.handlers import handle_create_vse_strip


class MockExecutor:
    """Mock executor tracking dispatched tool calls and returning structured receipts."""

    def __init__(self):
        self.calls = []

    def execute_tool(self, tool_name: str, params: dict, context=None, **kwargs) -> Any:
        self.calls.append({"tool": tool_name, "params": copy.deepcopy(params)})
        if tool_name == TOOL_RENDER_SCENE:
            res = {
                "output_file": "C:/workspace/renders/rendered_plate_001.png",
                "output_paths": ["C:/workspace/renders/rendered_plate_001.png"],
                "render_id": "a" * 32,
                "width": 1920,
                "height": 1080,
                "frame": 1,
                "camera": "Camera",
                "rendered": True,
                "operator_completed": True,
                "action": "render_scene",
            }
        elif tool_name == "inspect_render_output":
            rid = params.get("render_id", "a" * 32)
            res = {
                "success": True,
                "verified": True,
                "render_id": rid,
                "width": 1920,
                "height": 1080,
                "frame": 1,
                "camera": "Camera",
                "file_format": "PNG",
                "artifact": {
                    "path": "C:/workspace/renders/rendered_plate_001.png",
                    "sha256": "a" * 64,
                    "size_bytes": 1048576,
                    "png_structure_verified": True,
                    "width": 1920,
                    "height": 1080,
                },
            }
        elif tool_name == TOOL_MANAGE_COMPOSITOR_NODES:
            res = {"status": "SUCCESS", "action": "enable", "node_count": 5}
        elif tool_name == TOOL_CREATE_VSE_STRIP:
            stype = params.get("strip_type", "COLOR")
            dur = int(params.get("duration", 50))
            res = {
                "name": params.get("name", f"Strip_{stype}"),
                "type": stype,
                "channel": params.get("channel", 1),
                "frame_start": params.get("frame_start", 1),
                "duration": dur,
                "left_handle": params.get("frame_start", 1),
                "right_handle": params.get("frame_start", 1) + dur,
            }
        elif tool_name == TOOL_CREATE_VSE_TRANSITION:
            res = {
                "name": "Crossfade_001",
                "type": params.get("transition_type", "CROSS"),
                "input1": params.get("input1"),
                "input2": params.get("input2"),
            }
        elif tool_name == TOOL_CONFIGURE_VSE_AUDIO:
            res = {
                "name": params.get("name", "AudioTrack"),
                "volume": params.get("volume", 1.0),
                "status": "CONFIGURED",
            }
        elif tool_name == TOOL_RENDER_VSE_SEQUENCE:
            res = {
                "output_file": "C:/workspace/renders/editorial_render.mp4",
                "file_size_bytes": 1048576,
                "frame_count": 50,
                "status": "SUCCESS",
            }
        else:
            res = {"status": "SUCCESS", "tool": tool_name}
        return BridgeResponse.success(result=res)


class TestRenderedMediaHandoffFoundation(unittest.TestCase):
    """Focused unit tests for Milestone 9.3A: Rendered Media Handoff Foundation."""

    def setUp(self):
        self.director = DirectorAgent()
        self.executor = MockExecutor()
        self.dispatcher = AgentDispatcher(executor=self.executor)
        self.planner = self.dispatcher.manager.planner

        # Register specialized agents
        self.video_agent = VideoEditorAgent()
        self.render_agent = RenderLightingAgent()
        self.comp_agent = CompositorAgent()

        self.dispatcher.register_agent_runner(VIDEO_EDITOR_AGENT_ID, self.video_agent)
        self.dispatcher.register_agent_runner(RENDER_LIGHTING_AGENT_ID, self.render_agent)
        self.dispatcher.register_agent_runner(COMPOSITOR_AGENT_ID, self.comp_agent)

    # -------------------------------------------------------------------------
    # 1. Director render-to-VSE TaskOutputRef compilation
    # -------------------------------------------------------------------------
    def test_decompose_scene_render_editorial_handoff_binding(self):
        brief = "Render 3D scene, composite with denoise, and assemble into video timeline with rendered plate."
        contract = self.director.decompose_brief(brief, title="Render Handoff")

        # 1. Verify domain task assignment
        self.assertIn(RENDER_LIGHTING_AGENT_ID, contract.domain_tasks)
        self.assertIn(COMPOSITOR_AGENT_ID, contract.domain_tasks)
        self.assertIn(VIDEO_EDITOR_AGENT_ID, contract.domain_tasks)

        render_tasks = contract.domain_tasks[RENDER_LIGHTING_AGENT_ID]
        comp_tasks = contract.domain_tasks[COMPOSITOR_AGENT_ID]
        vse_tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]

        # 2. Verify stage_scene_render properties
        scene_render_task = next(t for t in render_tasks if t.task_type == TOOL_RENDER_SCENE)
        self.assertEqual(scene_render_task.task_id, "stage_scene_render")
        self.assertEqual(scene_render_task.required_capability, "world.manage")
        self.assertEqual(scene_render_task.input_params, {"render_mode": "still"})

        # 3. Verify stage_vse_timeline binding
        timeline_task = next(t for t in vse_tasks if t.task_type == TOOL_CREATE_VSE_STRIP)
        self.assertEqual(timeline_task.task_id, "stage_vse_timeline")
        self.assertEqual(timeline_task.input_params["strip_type"], "IMAGE")
        self.assertEqual(timeline_task.input_params["name"], "RenderPlate")

        # TaskOutputRef must point to stage_scene_render.output_file
        ref = timeline_task.input_params["filepath"]
        self.assertEqual(
            ref,
            {"$ref": {"task_id": "stage_scene_render", "path": "output_file", "type": "string"}},
        )

        # 4. Verify dependency ordering
        self.assertIn(comp_tasks[-1].task_id, scene_render_task.dependencies)
        self.assertIn(scene_render_task.task_id, timeline_task.dependencies)

    # -------------------------------------------------------------------------
    # 2. Dynamic reference resolution against upstream render receipt
    # -------------------------------------------------------------------------
    def test_render_receipt_to_vse_filepath_resolution(self):
        # Construct upstream succeeded render result
        upstream_render_result = AgentResult(
            task_id="stage_scene_render",
            status=TaskStatus.SUCCEEDED,
            output={
                "output_file": "C:/workspace/renders/shot_01.png",
                "output_paths": ["C:/workspace/renders/shot_01.png"],
                "render_id": "rnd_001",
                "width": 1920,
                "height": 1080,
                "rendered": True,
                "action": "render_scene",
            },
        )

        session_results = {"stage_scene_render": upstream_render_result}

        # Downstream VSE strip task with TaskOutputRef
        downstream_task = AgentTask(
            task_id="stage_vse_timeline",
            required_capability="video.timeline",
            task_type="create_vse_strip",
            input_params={
                "strip_type": "IMAGE",
                "name": "RenderPlate",
                "channel": 1,
                "frame_start": 1,
                "duration": 50,
                "filepath": TaskOutputRef(
                    task_id="stage_scene_render",
                    path="output_file",
                    expected_type="string",
                ).to_dict(),
            },
            dependencies=["stage_scene_render"],
        )

        # Verify resolution
        resolved_params, traces = resolve_task_references(
            downstream_task,
            session_results=session_results,
        )

        self.assertEqual(resolved_params["filepath"], "C:/workspace/renders/shot_01.png")
        self.assertEqual(resolved_params["name"], "RenderPlate")
        self.assertEqual(resolved_params["duration"], 50)

        # Original task.input_params must remain unchanged (immutability)
        self.assertIn("$ref", downstream_task.input_params["filepath"])
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["status"], "RESOLVED")

    # -------------------------------------------------------------------------
    # 3. Fail-closed rejection of missing or invalid render receipts
    # -------------------------------------------------------------------------
    def test_missing_or_failed_render_receipt_fails_closed(self):
        downstream_task = AgentTask(
            task_id="stage_vse_timeline",
            required_capability="video.timeline",
            task_type="create_vse_strip",
            input_params={
                "strip_type": "IMAGE",
                "name": "RenderPlate",
                "filepath": {"$ref": {"task_id": "stage_scene_render", "path": "output_file", "type": "string"}},
            },
            dependencies=["stage_scene_render"],
        )

        # Case A: Prerequisite task failed
        failed_res = AgentResult(task_id="stage_scene_render", status=TaskStatus.FAILED, output=None)
        with self.assertRaises(BindingResolutionError) as ctx_failed:
            resolve_task_references(downstream_task, session_results={"stage_scene_render": failed_res})
        self.assertEqual(ctx_failed.exception.code, "PREREQUISITE_NOT_SUCCEEDED")

        # Case B: Prerequisite task output is null
        null_res = AgentResult(task_id="stage_scene_render", status=TaskStatus.SUCCEEDED, output=None)
        with self.assertRaises(BindingResolutionError) as ctx_null:
            resolve_task_references(downstream_task, session_results={"stage_scene_render": null_res})
        self.assertEqual(ctx_null.exception.code, "DATA_UNAVAILABLE")

        # Case C: Field missing from output
        missing_field_res = AgentResult(task_id="stage_scene_render", status=TaskStatus.SUCCEEDED, output={"width": 1920})
        with self.assertRaises(BindingResolutionError) as ctx_missing:
            resolve_task_references(downstream_task, session_results={"stage_scene_render": missing_field_res})
        self.assertEqual(ctx_missing.exception.code, "FIELD_NOT_FOUND")

        # Case D: Type mismatch (expected string, got int)
        type_mismatch_res = AgentResult(task_id="stage_scene_render", status=TaskStatus.SUCCEEDED, output={"output_file": 12345})
        with self.assertRaises(BindingResolutionError) as ctx_type:
            resolve_task_references(downstream_task, session_results={"stage_scene_render": type_mismatch_res})
        self.assertEqual(ctx_type.exception.code, "TYPE_MISMATCH")

        # Case E: Undeclared dependency
        undeclared_task = AgentTask(
            task_id="stage_vse_timeline",
            required_capability="video.timeline",
            task_type="create_vse_strip",
            input_params={"filepath": {"$ref": {"task_id": "stage_scene_render", "path": "output_file"}}},
            dependencies=[],  # Omitted!
        )
        with self.assertRaises(BindingResolutionError) as ctx_undep:
            resolve_task_references(undeclared_task, session_results={"stage_scene_render": failed_res})
        self.assertEqual(ctx_undep.exception.code, "UNDECLARED_DEPENDENCY")

    # -------------------------------------------------------------------------
    # 4. Render-before-import dependency DAG ordering
    # -------------------------------------------------------------------------
    def test_render_before_import_dependency_dag_ordering(self):
        brief = "Render scene, assemble timeline with plate, add title, and render sequence to MP4."
        contract = self.director.decompose_brief(brief, title="Full Roundtrip Plan")
        plan = contract.compile_plan(session_id="test_ordering")

        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])

        execution_order = self.planner.compute_execution_order(plan)
        self.assertIn("stage_scene_render", execution_order)
        self.assertIn("stage_vse_timeline", execution_order)
        self.assertIn("stage_vse_title", execution_order)
        self.assertIn("stage_vse_render", execution_order)

        idx_render = execution_order.index("stage_scene_render")
        idx_timeline = execution_order.index("stage_vse_timeline")
        idx_title = execution_order.index("stage_vse_title")
        idx_vse_render = execution_order.index("stage_vse_render")

        self.assertLess(idx_render, idx_timeline, "Scene rendering must precede timeline strip creation.")
        self.assertLess(idx_timeline, idx_title, "Timeline creation must precede title strip creation.")
        self.assertLess(idx_title, idx_vse_render, "Title creation must precede final sequence rendering.")

    # -------------------------------------------------------------------------
    # 5. VSE still-image duration configuration and boundary validation
    # -------------------------------------------------------------------------
    def _issue_approval(self, tool_name: str, params: dict):
        reg = get_approval_registry()
        req = reg.create_request(tool_name, params)
        ok, reason = reg.resolve_request(req.request_id, "approved")
        params["request_id"] = req.request_id
        params["approval_token"] = req.approval_token

    def test_vse_still_image_duration_configuration(self):
        # Mock Blender scene and sequence editor
        mock_strip = MagicMock()
        mock_strip.name = "RenderPlate"
        mock_strip.type = "IMAGE"
        mock_strip.channel = 1
        mock_strip.left_handle = 1
        mock_strip.right_handle = 2
        mock_strip.duration = 1
        mock_strip.frame_final_duration = 1

        mock_se = MagicMock()
        mock_se.strips.new_image.return_value = mock_strip

        mock_scene = MagicMock()
        mock_scene.sequence_editor = mock_se

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene

        params = {
            "strip_type": "IMAGE",
            "name": "RenderPlate",
            "channel": 1,
            "frame_start": 1,
            "duration": 75,
            "filepath": "workspace/renders/plate.png",
        }
        self._issue_approval("create_vse_strip", params)

        # Call handle_create_vse_strip with duration = 75
        receipt = handle_create_vse_strip(
            bpy_module=mock_bpy,
            params=params,
        )

        # Verify that duration and handles were applied to the image strip
        self.assertEqual(mock_strip.duration, 75)
        self.assertEqual(mock_strip.frame_final_duration, 75)
        self.assertEqual(mock_strip.right_handle, 76)
        self.assertEqual(receipt["duration"], 75)
        self.assertEqual(receipt["right_handle"], 76)

    def test_vse_duration_boundary_rejection(self):
        mock_bpy = MagicMock()
        # Zero duration
        params_zero = {
            "strip_type": "IMAGE",
            "channel": 1,
            "frame_start": 1,
            "duration": 0,
            "filepath": "plate.png",
        }
        self._issue_approval("create_vse_strip", params_zero)
        with self.assertRaises(ValueError) as ctx_zero:
            handle_create_vse_strip(
                bpy_module=mock_bpy,
                params=params_zero,
            )
        self.assertIn("must be greater than 0", str(ctx_zero.exception))

        # Negative duration
        params_neg = {
            "strip_type": "IMAGE",
            "channel": 1,
            "frame_start": 1,
            "duration": -25,
            "filepath": "plate.png",
        }
        self._issue_approval("create_vse_strip", params_neg)
        with self.assertRaises(ValueError) as ctx_neg:
            handle_create_vse_strip(
                bpy_module=mock_bpy,
                params=params_neg,
            )
        self.assertIn("must be greater than 0", str(ctx_neg.exception))

    # -------------------------------------------------------------------------
    # 6. Actual planned strip references for transitions
    # -------------------------------------------------------------------------
    def test_transition_uses_actual_planned_strip_references(self):
        # Case A: Scene render handoff with transition
        brief_render = "Render 3D scene, assemble timeline with plate, and add crossfade transition."
        contract_render = self.director.decompose_brief(brief_render, title="Render Crossfade")
        vse_tasks = contract_render.domain_tasks[VIDEO_EDITOR_AGENT_ID]

        trans_task = next(t for t in vse_tasks if t.task_type == TOOL_CREATE_VSE_TRANSITION)
        self.assertEqual(trans_task.input_params["input1"], "RenderPlate")
        self.assertEqual(trans_task.input_params["input2"], "RenderPlate_B")
        self.assertNotEqual(trans_task.input_params["input1"], "Strip1")
        self.assertNotEqual(trans_task.input_params["input2"], "Strip2")

        # Case B: Cut and transition
        brief_cut = "Cut video strip, add crossfade transition, and render sequence to MP4."
        contract_cut = self.director.decompose_brief(brief_cut, title="Cut Crossfade")
        vse_cut_tasks = contract_cut.domain_tasks[VIDEO_EDITOR_AGENT_ID]

        trans_cut_task = next(t for t in vse_cut_tasks if t.task_type == TOOL_CREATE_VSE_TRANSITION)
        self.assertEqual(trans_cut_task.input_params["input1"], "ColorStrip")
        self.assertEqual(trans_cut_task.input_params["input2"], "ColorStrip_split")

    # -------------------------------------------------------------------------
    # 7. Audio strip creation and configuration dependencies
    # -------------------------------------------------------------------------
    def test_audio_strip_creation_and_configuration_dependencies(self):
        brief = "Assemble video timeline with color strip, add audio track voiceover.wav, configure audio volume, and render sequence to MP4."
        contract = self.director.decompose_brief(brief, title="Audio Integration")
        vse_tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]

        # Verify both audio strip creation and configuration tasks exist
        audio_strip_task = next(t for t in vse_tasks if t.task_id == "stage_vse_audio_strip")
        audio_config_task = next(t for t in vse_tasks if t.task_id == "stage_vse_audio")

        self.assertEqual(audio_strip_task.task_type, TOOL_CREATE_VSE_STRIP)
        self.assertEqual(audio_strip_task.input_params["strip_type"], "SOUND")
        self.assertEqual(audio_strip_task.input_params["name"], "AudioTrack")
        self.assertEqual(audio_strip_task.input_params["filepath"], "voiceover.wav")

        self.assertEqual(audio_config_task.task_type, TOOL_CONFIGURE_VSE_AUDIO)
        self.assertEqual(audio_config_task.input_params["name"], "AudioTrack")

        # Verify audio configuration explicitly depends on audio strip creation
        self.assertIn(audio_strip_task.task_id, audio_config_task.dependencies)

    # -------------------------------------------------------------------------
    # 8. Trusted approval enforcement and execution across agents
    # -------------------------------------------------------------------------
    def test_approval_enforcement_on_compound_handoff_workflow(self):
        brief = "Render 3D scene, assemble timeline with plate, and render sequence to MP4."
        contract = self.director.decompose_brief(brief, title="Approval Review")

        # A: Submit without trusted approval -> must pause in AWAITING_APPROVAL
        plan, results = self.director.submit_contract(contract, self.dispatcher, trusted_approval=False)
        self.assertEqual(plan.status, TaskStatus.AWAITING_APPROVAL)
        self.assertTrue(all(r.status == TaskStatus.AWAITING_APPROVAL for r in results))
        self.assertEqual(len(self.executor.calls), 0)

        # B: Submit with untrusted model-supplied approval -> must raise PermissionError
        contract_malicious = copy.deepcopy(contract)
        first_aid = next(iter(contract_malicious.domain_tasks))
        contract_malicious.domain_tasks[first_aid][0].input_params["approved"] = True

        with self.assertRaises(PermissionError):
            self.director.submit_contract(contract_malicious, self.dispatcher, trusted_approval=False)

        # C: Submit with trusted approval -> executes all tasks across agents
        self.executor.calls.clear()
        contract_approved = self.director.decompose_brief(brief, title="Approval Review")
        plan_approved, results_approved = self.director.submit_contract(
            contract_approved,
            self.dispatcher,
            trusted_approval=True,
        )

        self.assertEqual(plan_approved.status, TaskStatus.SUCCEEDED)
        self.assertTrue(all(r.success for r in results_approved))

        # Verify executor executed render_scene, create_vse_strip (with resolved filepath), and render_vse_sequence
        executed_tools = [c["tool"] for c in self.executor.calls]
        self.assertIn(TOOL_RENDER_SCENE, executed_tools)
        self.assertIn(TOOL_CREATE_VSE_STRIP, executed_tools)
        self.assertIn(TOOL_RENDER_VSE_SEQUENCE, executed_tools)

        # Verify that create_vse_strip received the resolved render output_file
        vse_call = next(c for c in self.executor.calls if c["tool"] == TOOL_CREATE_VSE_STRIP)
        self.assertEqual(vse_call["params"]["filepath"], "C:/workspace/renders/rendered_plate_001.png")
        self.assertEqual(vse_call["params"]["strip_type"], "IMAGE")
        self.assertEqual(vse_call["params"]["name"], "RenderPlate")

    # -------------------------------------------------------------------------
    # 9. Backward compatibility with existing single-intent briefs
    # -------------------------------------------------------------------------
    def test_single_intent_backward_compatibility(self):
        # Single title card
        c_title = self.director.decompose_brief("Add video title card")
        self.assertEqual(len(c_title.domain_tasks[VIDEO_EDITOR_AGENT_ID]), 1)
        self.assertEqual(c_title.domain_tasks[VIDEO_EDITOR_AGENT_ID][0].task_type, TOOL_CREATE_VSE_TEXT_STRIP)

        # Single audio volume
        c_audio = self.director.decompose_brief("Configure video soundtrack volume")
        self.assertEqual(len(c_audio.domain_tasks[VIDEO_EDITOR_AGENT_ID]), 1)
        self.assertEqual(c_audio.domain_tasks[VIDEO_EDITOR_AGENT_ID][0].task_type, TOOL_CONFIGURE_VSE_AUDIO)

        # Single render
        c_render = self.director.decompose_brief("Render video sequence to MP4")
        self.assertEqual(len(c_render.domain_tasks[VIDEO_EDITOR_AGENT_ID]), 1)
        self.assertEqual(c_render.domain_tasks[VIDEO_EDITOR_AGENT_ID][0].task_type, TOOL_RENDER_VSE_SEQUENCE)

        # Generic video edit
        c_edit = self.director.decompose_brief("Edit video in VSE")
        self.assertEqual(len(c_edit.domain_tasks[VIDEO_EDITOR_AGENT_ID]), 1)
        self.assertEqual(c_edit.domain_tasks[VIDEO_EDITOR_AGENT_ID][0].task_type, TOOL_CREATE_VSE_STRIP)


if __name__ == "__main__":
    unittest.main()
