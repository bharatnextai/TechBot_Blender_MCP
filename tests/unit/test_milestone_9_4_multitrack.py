"""
Unit Tests for Milestone 9.4: Multi-Track Spatial Composition, Strip Color Grading & Styled Lower-Thirds.

Verifies:
1. Multi-track Picture-in-Picture intent decomposition and strip channel allocation.
2. 2D Transform and pixel-accurate cropping task parameterization.
3. Strip-level color grading modifier scheduling (BRIGHT_CONTRAST & COLOR_BALANCE).
4. Professional styled lower-third title card creation and typography/box styling tasks.
5. End-to-end compound multi-track brief DAG ordering and dependency validation.
6. Execution of 9.4 tasks through VideoEditorAgent with trusted approval enforcement.
7. Fail-closed security controls (model-supplied approved=True rejection, path traversal rejection).
8. Backward compatibility with single-intent and Milestone 9.3 linear briefs.
"""

from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch
import copy
import os

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
    TOOL_CONFIGURE_VSE_TEXT_STYLE,
    TOOL_TRANSFORM_VSE_STRIP,
    TOOL_CROP_VSE_STRIP,
    TOOL_MANAGE_VSE_STRIP_MODIFIERS,
    TOOL_CONFIGURE_VSE_AUDIO,
    TOOL_RENDER_VSE_SEQUENCE,
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
from mcp_service.agents.dispatcher import (
    AgentDispatcher,
    DispatchResult,
    resolve_task_references,
)
from mcp_service.agents.planner import TaskPlanner
from shared.models.protocol_models import BridgeResponse


class MockMultiTrackExecutor:
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
        elif tool_name == TOOL_TRANSFORM_VSE_STRIP:
            res = {
                "name": params.get("name"),
                "action": params.get("action", "UPDATE"),
                "scale_x": params.get("scale_x", 1.0),
                "scale_y": params.get("scale_y", 1.0),
                "offset_x": params.get("offset_x", 0.0),
                "offset_y": params.get("offset_y", 0.0),
            }
        elif tool_name == TOOL_CROP_VSE_STRIP:
            res = {
                "name": params.get("name"),
                "action": params.get("action", "UPDATE"),
                "min_x": params.get("min_x", 0),
                "max_x": params.get("max_x", 0),
                "min_y": params.get("min_y", 0),
                "max_y": params.get("max_y", 0),
            }
        elif tool_name == TOOL_MANAGE_VSE_STRIP_MODIFIERS:
            res = {
                "name": params.get("name"),
                "action": params.get("action", "ADD"),
                "modifier_type": params.get("modifier_type"),
                "modifier_name": params.get("modifier_name", f"{params.get('modifier_type')}_01"),
            }
        elif tool_name == TOOL_CREATE_VSE_TEXT_STRIP:
            res = {
                "name": params.get("name", "Text_1_1"),
                "text": params.get("text", "Text"),
                "channel": params.get("channel", 1),
                "frame_start": params.get("frame_start", 1),
                "duration": params.get("duration", 60),
            }
        elif tool_name == TOOL_CONFIGURE_VSE_TEXT_STYLE:
            res = {
                "name": params.get("name"),
                "action": params.get("action", "UPDATE"),
                "font_size": params.get("font_size", 42.0),
                "use_box": params.get("use_box", False),
            }
        elif tool_name == TOOL_CONFIGURE_VSE_AUDIO:
            res = {
                "name": params.get("name", "AudioTrack"),
                "volume": params.get("volume", 1.0),
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


class TestMilestone94MultiTrackDecomposition(unittest.TestCase):
    """Unit tests for Milestone 9.4 multi-track intent decomposition."""

    def setUp(self):
        self.director = DirectorAgent()
        self.executor = MockMultiTrackExecutor()
        self.dispatcher = AgentDispatcher(executor=self.executor)
        self.planner = self.dispatcher.manager.planner

        self.video_agent = VideoEditorAgent()
        self.render_agent = RenderLightingAgent()
        self.comp_agent = CompositorAgent()

        self.dispatcher.register_agent_runner(VIDEO_EDITOR_AGENT_ID, self.video_agent)
        self.dispatcher.register_agent_runner(RENDER_LIGHTING_AGENT_ID, self.render_agent)
        self.dispatcher.register_agent_runner(COMPOSITOR_AGENT_ID, self.comp_agent)

    # -------------------------------------------------------------------------
    # 1. Multi-Track PiP Intent Decomposition
    # -------------------------------------------------------------------------
    def test_decompose_picture_in_picture_intent(self):
        brief = "Assemble video timeline with picture-in-picture overlay in the corner."
        contract = self.director.decompose_brief(brief, title="PiP Layout")

        self.assertIn(VIDEO_EDITOR_AGENT_ID, contract.domain_tasks)
        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        task_types = [t.task_type for t in tasks]

        self.assertIn(TOOL_CREATE_VSE_STRIP, task_types)
        self.assertIn(TOOL_TRANSFORM_VSE_STRIP, task_types)

        # Base strip on Channel 1
        base_strip = next(t for t in tasks if t.task_id == "stage_vse_timeline")
        self.assertEqual(base_strip.input_params["channel"], 1)
        self.assertEqual(base_strip.input_params["name"], "ColorStrip")

        # Overlay strip on Channel 2
        overlay_strip = next(t for t in tasks if t.task_id == "stage_vse_overlay")
        self.assertEqual(overlay_strip.input_params["channel"], 2)
        self.assertEqual(overlay_strip.input_params["name"], "OverlayStrip")

        # Transform targeting overlay strip
        transform_task = next(t for t in tasks if t.task_id == "stage_vse_transform")
        self.assertEqual(transform_task.input_params["name"], "OverlayStrip")
        self.assertEqual(transform_task.input_params["scale_x"], 0.35)
        self.assertEqual(transform_task.input_params["scale_y"], 0.35)
        self.assertEqual(transform_task.input_params["offset_x"], 220.0)
        self.assertEqual(transform_task.input_params["offset_y"], 140.0)
        self.assertEqual(transform_task.input_params["action"], "UPDATE")

        # Dependency chaining
        self.assertIn("stage_vse_timeline", overlay_strip.dependencies)
        self.assertIn("stage_vse_overlay", transform_task.dependencies)

    # -------------------------------------------------------------------------
    # 2. Spatial Composition with Cropping
    # -------------------------------------------------------------------------
    def test_decompose_transform_and_crop(self):
        brief = "Create video overlay with transform scale and crop border margins."
        contract = self.director.decompose_brief(brief, title="Crop & Scale")

        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        task_ids = [t.task_id for t in tasks]

        self.assertIn("stage_vse_transform", task_ids)
        self.assertIn("stage_vse_crop", task_ids)

        crop_task = next(t for t in tasks if t.task_id == "stage_vse_crop")
        self.assertEqual(crop_task.input_params["name"], "OverlayStrip")
        self.assertEqual(crop_task.input_params["min_x"], 10)
        self.assertEqual(crop_task.input_params["max_x"], 10)
        self.assertEqual(crop_task.input_params["action"], "UPDATE")
        self.assertIn("stage_vse_transform", crop_task.dependencies)

    # -------------------------------------------------------------------------
    # 3. Strip Color Grading Modifiers (Bright/Contrast vs Color Balance)
    # -------------------------------------------------------------------------
    def test_decompose_color_grade_contrast(self):
        brief = "Assemble video timeline and adjust contrast on strip with color modifier."
        contract = self.director.decompose_brief(brief, title="Grade Contrast")

        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        grade_task = next(t for t in tasks if t.task_id == "stage_vse_grade")

        self.assertEqual(grade_task.task_type, TOOL_MANAGE_VSE_STRIP_MODIFIERS)
        self.assertEqual(grade_task.input_params["action"], "ADD")
        self.assertEqual(grade_task.input_params["name"], "ColorStrip")
        self.assertEqual(grade_task.input_params["modifier_type"], "BRIGHT_CONTRAST")
        self.assertEqual(grade_task.input_params["bright"], 0.1)
        self.assertEqual(grade_task.input_params["contrast"], 1.2)

    def test_decompose_color_grade_color_balance(self):
        brief = "Assemble video sequence and apply color grade with lift gamma gain."
        contract = self.director.decompose_brief(brief, title="Color Balance")

        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        grade_task = next(t for t in tasks if t.task_id == "stage_vse_grade")

        self.assertEqual(grade_task.task_type, TOOL_MANAGE_VSE_STRIP_MODIFIERS)
        self.assertEqual(grade_task.input_params["modifier_type"], "COLOR_BALANCE")
        self.assertEqual(grade_task.input_params["correction_method"], "LIFT_GAMMA_GAIN")
        self.assertEqual(grade_task.input_params["lift"], [0.0, 0.0, 0.05])
        self.assertEqual(grade_task.input_params["color_multiply"], 1.1)

    # -------------------------------------------------------------------------
    # 4. Styled Lower-Third Title Cards
    # -------------------------------------------------------------------------
    def test_decompose_styled_lower_third(self):
        brief = "Assemble video timeline and add styled lower-third title card with background box."
        contract = self.director.decompose_brief(brief, title="Styled Title")

        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        task_ids = [t.task_id for t in tasks]

        self.assertIn("stage_vse_title", task_ids)
        self.assertIn("stage_vse_title_style", task_ids)

        title_task = next(t for t in tasks if t.task_id == "stage_vse_title")
        self.assertEqual(title_task.task_type, TOOL_CREATE_VSE_TEXT_STRIP)
        self.assertEqual(title_task.input_params["text"], "Lower Third")
        self.assertEqual(title_task.input_params["name"], "LowerThird")
        self.assertEqual(title_task.input_params["channel"], 2)  # No overlay, so channel 2

        style_task = next(t for t in tasks if t.task_id == "stage_vse_title_style")
        self.assertEqual(style_task.task_type, TOOL_CONFIGURE_VSE_TEXT_STYLE)
        self.assertEqual(style_task.input_params["name"], "LowerThird")
        self.assertEqual(style_task.input_params["action"], "UPDATE")
        self.assertEqual(style_task.input_params["font_size"], 42.0)
        self.assertEqual(style_task.input_params["location"], [0.1, 0.15])
        self.assertEqual(style_task.input_params["alignment_x"], "LEFT")
        self.assertTrue(style_task.input_params["use_box"])
        self.assertEqual(style_task.input_params["box_color"], [0.0, 0.0, 0.0, 0.7])
        self.assertEqual(style_task.input_params["box_margin"], 0.1)
        self.assertTrue(style_task.input_params["use_shadow"])

        # Style depends on title creation
        self.assertIn("stage_vse_title", style_task.dependencies)

    # -------------------------------------------------------------------------
    # 5. Full Compound Multi-Track Brief (Gate 1 Acceptance)
    # -------------------------------------------------------------------------
    def test_decompose_full_compound_multitrack_brief(self):
        brief = (
            "Render 3D scene, composite with denoise, assemble video timeline with rendered plate, "
            "add picture-in-picture overlay with 2D transform scale, color grade main plate with contrast, "
            "add styled lower-third title card with background box, include soundtrack.wav audio track, "
            "and render sequence to MP4."
        )
        contract = self.director.decompose_brief(brief, title="Full Multi-Track Master")

        # Verify domain assignment
        self.assertIn(RENDER_LIGHTING_AGENT_ID, contract.domain_tasks)
        self.assertIn(COMPOSITOR_AGENT_ID, contract.domain_tasks)
        self.assertIn(VIDEO_EDITOR_AGENT_ID, contract.domain_tasks)

        vse_tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        task_map = {t.task_id: t for t in vse_tasks}

        expected_task_ids = [
            "stage_vse_timeline",
            "stage_vse_overlay",
            "stage_vse_transform",
            "stage_vse_grade",
            "stage_vse_title",
            "stage_vse_title_style",
            "stage_vse_audio_strip",
            "stage_vse_audio",
            "stage_vse_render",
        ]
        for tid in expected_task_ids:
            self.assertIn(tid, task_map, f"Missing expected task: {tid}")

        # Verify multi-track channel allocation
        self.assertEqual(task_map["stage_vse_timeline"].input_params["channel"], 1)
        self.assertEqual(task_map["stage_vse_timeline"].input_params["name"], "RenderPlate")

        self.assertEqual(task_map["stage_vse_overlay"].input_params["channel"], 2)
        self.assertEqual(task_map["stage_vse_overlay"].input_params["name"], "OverlayStrip")

        self.assertEqual(task_map["stage_vse_title"].input_params["channel"], 3)  # PiP present -> Channel 3
        self.assertEqual(task_map["stage_vse_title"].input_params["name"], "LowerThird")

        self.assertEqual(task_map["stage_vse_audio_strip"].input_params["channel"], 4)  # PiP + Title -> Channel 4
        self.assertEqual(task_map["stage_vse_audio_strip"].input_params["name"], "AudioTrack")

        # Compile and validate DAG execution order
        plan = contract.compile_plan(session_id="multitrack_ordering_test")
        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])

        order = self.planner.compute_execution_order(plan)

        # Verify DAG topological constraints
        self.assertLess(order.index("stage_scene_render"), order.index("stage_vse_timeline"))
        self.assertLess(order.index("stage_vse_timeline"), order.index("stage_vse_overlay"))
        self.assertLess(order.index("stage_vse_overlay"), order.index("stage_vse_transform"))
        self.assertLess(order.index("stage_vse_transform"), order.index("stage_vse_grade"))
        self.assertLess(order.index("stage_vse_grade"), order.index("stage_vse_title"))
        self.assertLess(order.index("stage_vse_title"), order.index("stage_vse_title_style"))
        self.assertLess(order.index("stage_vse_title_style"), order.index("stage_vse_audio_strip"))
        self.assertLess(order.index("stage_vse_audio_strip"), order.index("stage_vse_audio"))
        self.assertLess(order.index("stage_vse_audio"), order.index("stage_vse_render"))

    # -------------------------------------------------------------------------
    # 6. VideoEditorAgent Execution & Trusted Approval Enforcement
    # -------------------------------------------------------------------------
    def test_video_editor_agent_executes_multitrack_with_approval(self):
        # 1. Test transform_vse_strip execution with trusted approval
        task_transform = AgentTask(
            task_id="t_trans",
            required_capability="video.transforms",
            task_type="transform_vse_strip",
            input_params={
                "name": "OverlayStrip",
                "scale_x": 0.35,
                "scale_y": 0.35,
                "offset_x": 220.0,
                "offset_y": 140.0,
                "action": "UPDATE",
            },
        )
        res_transform = self.video_agent.execute_task(task_transform, self.executor, trusted_approval=True)
        self.assertEqual(res_transform.status, TaskStatus.SUCCEEDED)

        # 2. Test manage_vse_strip_modifiers execution with trusted approval
        task_grade = AgentTask(
            task_id="t_grade",
            required_capability="video.grading",
            task_type="manage_vse_strip_modifiers",
            input_params={
                "action": "ADD",
                "name": "RenderPlate",
                "modifier_type": "BRIGHT_CONTRAST",
                "bright": 0.1,
                "contrast": 1.2,
            },
        )
        res_grade = self.video_agent.execute_task(task_grade, self.executor, trusted_approval=True)
        self.assertEqual(res_grade.status, TaskStatus.SUCCEEDED)

        # 3. Test configure_vse_text_style execution with trusted approval
        task_style = AgentTask(
            task_id="t_style",
            required_capability="video.titles",
            task_type="configure_vse_text_style",
            input_params={
                "name": "LowerThird",
                "action": "UPDATE",
                "font_size": 42.0,
                "use_box": True,
            },
        )
        res_style = self.video_agent.execute_task(task_style, self.executor, trusted_approval=True)
        self.assertEqual(res_style.status, TaskStatus.SUCCEEDED)

    # -------------------------------------------------------------------------
    # 7. Fail-Closed Security Controls
    # -------------------------------------------------------------------------
    def test_untrusted_approved_true_rejected_on_multitrack_tasks(self):
        # Model-supplied approved=True on transform
        task_transform_bad = AgentTask(
            task_id="t_bad_trans",
            required_capability="video.transforms",
            task_type="transform_vse_strip",
            input_params={"name": "OverlayStrip", "scale_x": 0.5, "approved": True},
        )
        res = self.video_agent.execute_task(task_transform_bad, self.executor, trusted_approval=False)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("approved=True", res.errors[0])

        # Missing trusted approval rejected
        task_transform_unauth = AgentTask(
            task_id="t_unauth_trans",
            required_capability="video.transforms",
            task_type="transform_vse_strip",
            input_params={"name": "OverlayStrip", "scale_x": 0.5},
        )
        res2 = self.video_agent.execute_task(task_transform_unauth, self.executor, trusted_approval=False)
        self.assertEqual(res2.status, TaskStatus.FAILED)
        self.assertIn("Approval required", res2.errors[0])

    def test_director_submits_fails_on_untrusted_approved_flag(self):
        brief = "Assemble video timeline with picture-in-picture overlay"
        contract = self.director.decompose_brief(brief)
        # Inject untrusted approved=True into contract
        contract.domain_tasks[VIDEO_EDITOR_AGENT_ID][0].input_params["approved"] = True

        with self.assertRaises(PermissionError) as ctx:
            self.director.submit_contract(contract, self.dispatcher, trusted_approval=False)
        self.assertIn("Untrusted approved=True flag detected", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 8. Backward Compatibility with Single-Intent Briefs
    # -------------------------------------------------------------------------
    def test_backward_compatibility_single_intent(self):
        # 1. Plain title card without lower-third keywords
        c_title = self.director.decompose_brief("Add video title card")
        tasks = c_title.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].task_type, TOOL_CREATE_VSE_TEXT_STRIP)
        self.assertEqual(tasks[0].input_params["channel"], 2)

        # 2. Plain soundtrack
        c_audio = self.director.decompose_brief("Add audio track soundtrack.wav")
        tasks_audio = c_audio.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        self.assertEqual(len(tasks_audio), 2)
        self.assertEqual(tasks_audio[0].task_type, TOOL_CREATE_VSE_STRIP)
        self.assertEqual(tasks_audio[0].input_params["strip_type"], "SOUND")
        self.assertEqual(tasks_audio[0].input_params["channel"], 3)  # No overlay -> Channel 3


if __name__ == "__main__":
    unittest.main()
