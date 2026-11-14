"""
Unit test suite for Milestone 9.2: Dedicated VideoEditorAgent Integration.
Verifies:
1. Manifest structure, priority 70, version, and descriptors.
2. Complete coverage of all 9 typed capabilities and all 22 VSE tools.
3. Default AgentRegistry and AgentDispatcher registration.
4. CapabilityRouter priority routing for video capabilities.
5. Fail-closed human approval gating and rejection of untrusted approved=True.
6. Read-only timeline inspection execution without mutation approval.
7. Strict path traversal and symlink escape defenses on media inputs and render exports.
8. DirectorAgent editorial brief decomposition and delegation.
9. End-to-end task execution for all 22 VSE tools with MockExecutor.
"""

import os
import tempfile
import unittest
from unittest.mock import patch
from typing import Dict, Any, List, Optional

from shared.models.agent_contracts import (
    AgentManifest,
    AgentTask,
    AgentResult,
    TaskStatus,
    DelegationContract,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_INSPECT_VSE_TIMELINE,
    TOOL_CREATE_VSE_STRIP,
    TOOL_MODIFY_VSE_STRIP,
    TOOL_DELETE_VSE_STRIP,
    TOOL_MANAGE_TIMELINE_MARKERS,
    TOOL_TRIM_VSE_STRIP,
    TOOL_SPLIT_VSE_STRIP,
    TOOL_REORDER_VSE_STRIPS,
    TOOL_CREATE_VSE_TRANSITION,
    TOOL_CONFIGURE_VSE_EFFECT,
    TOOL_CONFIGURE_VSE_AUDIO,
    TOOL_MANAGE_VSE_SOUND_MODIFIERS,
    TOOL_TRANSFORM_VSE_STRIP,
    TOOL_CROP_VSE_STRIP,
    TOOL_ANIMATE_VSE_STRIP,
    TOOL_MANAGE_VSE_STRIP_MODIFIERS,
    TOOL_CREATE_VSE_TEXT_STRIP,
    TOOL_CONFIGURE_VSE_TEXT_STYLE,
    TOOL_GROUP_VSE_META_STRIP,
    TOOL_CREATE_VSE_SCENE_STRIP,
    TOOL_RENDER_VSE_SEQUENCE,
    TOOL_MIXDOWN_VSE_AUDIO,
    PERMISSION_READ_ONLY,
    PERMISSION_SCENE_MUTATION,
    TOOL_DEFINITIONS,
)
from mcp_service.agents.video_editor import (
    VideoEditorAgent,
    VIDEO_EDITOR_AGENT_ID,
    CAPABILITY_VSE_TIMELINE,
    CAPABILITY_VSE_EDITORIAL,
    CAPABILITY_VSE_TRANSITIONS,
    CAPABILITY_VSE_AUDIO,
    CAPABILITY_VSE_TRANSFORMS,
    CAPABILITY_VSE_GRADING,
    CAPABILITY_VSE_TITLES,
    CAPABILITY_VSE_SEQUENCES,
    CAPABILITY_VSE_RENDERING,
    SUPPORTED_VSE_TOOLS,
    create_video_editor_manifest,
    validate_vse_path,
)
from mcp_service.agents.registry import create_default_registry
from mcp_service.agents.router import CapabilityRouter
from mcp_service.agents.dispatcher import AgentDispatcher
from mcp_service.agents.director import DirectorAgent, DIRECTOR_AGENT_ID


class MockExecutor:
    """Mock BlenderExecutor recording calls and returning synthetic success responses."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def call_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        task_id: str = "",
        session_id: str = "",
        trusted_approval: Any = None,
    ) -> BridgeResponse:
        self.calls.append({
            "tool_name": tool_name,
            "params": params,
            "task_id": task_id,
            "session_id": session_id,
            "trusted_approval": trusted_approval,
        })
        return BridgeResponse(
            status="success",
            result={"tool": tool_name, "verified": True, "name": params.get("name", "Strip1")},
            message=f"{tool_name} executed successfully",
        )

    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        task_id: str = "",
        session_id: str = "",
        trusted_approval: Any = None,
    ) -> BridgeResponse:
        return self.call_tool(
            tool_name, params, task_id=task_id, session_id=session_id, trusted_approval=trusted_approval
        )


class TestVideoEditorManifestAndRegistration(unittest.TestCase):
    """Verifies manifest metadata, priority, capabilities, and system registrations."""

    def setUp(self):
        self.manifest = create_video_editor_manifest()

    def test_manifest_metadata(self):
        self.assertEqual(self.manifest.agent_id, VIDEO_EDITOR_AGENT_ID)
        self.assertEqual(self.manifest.name, "Video Editor and Sequencer Agent")
        self.assertEqual(self.manifest.priority, 70)
        self.assertTrue(self.manifest.enabled)
        self.assertEqual(self.manifest.version, "0.1.92")

    def test_nine_typed_capabilities_present(self):
        expected_caps = {
            CAPABILITY_VSE_TIMELINE,
            CAPABILITY_VSE_EDITORIAL,
            CAPABILITY_VSE_TRANSITIONS,
            CAPABILITY_VSE_AUDIO,
            CAPABILITY_VSE_TRANSFORMS,
            CAPABILITY_VSE_GRADING,
            CAPABILITY_VSE_TITLES,
            CAPABILITY_VSE_SEQUENCES,
            CAPABILITY_VSE_RENDERING,
        }
        manifest_caps = {cap.capability_id for cap in self.manifest.capabilities}
        self.assertEqual(manifest_caps, expected_caps)

        for cap in self.manifest.capabilities:
            self.assertEqual(cap.read_write, "SCENE_MUTATION")
            self.assertEqual(cap.verification_status, "VERIFIED")
            self.assertEqual(cap.version, "1.0.0")
            self.assertTrue(len(cap.supported_task_types) > 0)

    def test_all_22_vse_tools_covered(self):
        self.assertEqual(len(SUPPORTED_VSE_TOOLS), 22)

        # All 22 tools must have input schemas in manifest
        self.assertEqual(set(self.manifest.input_schemas.keys()), SUPPORTED_VSE_TOOLS)

        # All 22 tools must be mapped across the 9 capability descriptors
        mapped_tools = set()
        for cap in self.manifest.capabilities:
            mapped_tools.update(cap.supported_task_types)
        self.assertEqual(mapped_tools, SUPPORTED_VSE_TOOLS)

    def test_default_registry_includes_video_editor(self):
        registry = create_default_registry()
        agent_manifest = registry.get_agent(VIDEO_EDITOR_AGENT_ID)
        self.assertIsNotNone(agent_manifest)
        self.assertEqual(agent_manifest.agent_id, VIDEO_EDITOR_AGENT_ID)
        self.assertEqual(agent_manifest.priority, 70)

    def test_capability_router_resolves_all_nine_capabilities(self):
        registry = create_default_registry()
        router = CapabilityRouter(registry)

        capabilities = [
            CAPABILITY_VSE_TIMELINE,
            CAPABILITY_VSE_EDITORIAL,
            CAPABILITY_VSE_TRANSITIONS,
            CAPABILITY_VSE_AUDIO,
            CAPABILITY_VSE_TRANSFORMS,
            CAPABILITY_VSE_GRADING,
            CAPABILITY_VSE_TITLES,
            CAPABILITY_VSE_SEQUENCES,
            CAPABILITY_VSE_RENDERING,
        ]

        for cap in capabilities:
            task = AgentTask(task_id=f"t_{cap}", required_capability=cap)
            routing = router.route(task)
            self.assertTrue(routing.success, f"Failed to route {cap}")
            self.assertEqual(routing.agent.agent_id, VIDEO_EDITOR_AGENT_ID)

    def test_dispatcher_registers_video_editor_runner(self):
        executor = MockExecutor()
        dispatcher = AgentDispatcher(executor=executor)
        self.assertIn(VIDEO_EDITOR_AGENT_ID, dispatcher._agent_runners)
        runner = dispatcher._agent_runners[VIDEO_EDITOR_AGENT_ID]
        self.assertIsInstance(runner, VideoEditorAgent)


class TestApprovalAndSecurityGating(unittest.TestCase):
    """Verifies fail-closed approval barriers and untrusted injection rejections."""

    def setUp(self):
        self.agent = VideoEditorAgent()
        self.executor = MockExecutor()

    def test_untrusted_approved_true_rejected(self):
        task = AgentTask(
            task_id="sec_1",
            required_capability=CAPABILITY_VSE_EDITORIAL,
            task_type=TOOL_TRIM_VSE_STRIP,
            input_params={"name": "Strip1", "frame_final_start": 10, "approved": True},
        )
        res = self.agent.execute_task(task, self.executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])
        self.assertEqual(len(self.executor.calls), 0)

    def test_untrusted_trusted_approval_param_rejected(self):
        task = AgentTask(
            task_id="sec_2",
            required_capability=CAPABILITY_VSE_TIMELINE,
            task_type=TOOL_CREATE_VSE_STRIP,
            input_params={
                "strip_type": "COLOR",
                "channel": 1,
                "frame_start": 1,
                "duration": 30,
                "color": [1.0, 0.0, 0.0],
                "trusted_approval": True,
            },
        )
        res = self.agent.execute_task(task, self.executor)
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("Approval denied", res.errors[0])
        self.assertEqual(len(self.executor.calls), 0)

    def test_mutating_vse_tools_require_trusted_approval(self):
        mutating_tools = [
            (TOOL_CREATE_VSE_STRIP, {"strip_type": "COLOR", "channel": 1, "frame_start": 1, "duration": 30, "color": [0.0, 1.0, 0.0]}),
            (TOOL_MODIFY_VSE_STRIP, {"name": "Strip1", "channel": 2}),
            (TOOL_DELETE_VSE_STRIP, {"name": "Strip1"}),
            (TOOL_MANAGE_TIMELINE_MARKERS, {"action": "ADD", "name": "Marker1", "frame": 10}),
            (TOOL_TRIM_VSE_STRIP, {"name": "Strip1", "left_handle": 10, "right_handle": 50}),
            (TOOL_SPLIT_VSE_STRIP, {"name": "Strip1", "split_frame": 15}),
            (TOOL_REORDER_VSE_STRIPS, {"action": "MOVE", "name": "Strip1", "channel": 2, "target_frame": 30}),
            (TOOL_CREATE_VSE_TRANSITION, {"transition_type": "CROSS", "input1": "Strip1", "input2": "Strip2"}),
            (TOOL_CONFIGURE_VSE_EFFECT, {"action": "CREATE", "effect_type": "GLOW", "channel": 1, "frame_start": 1, "duration": 30, "input_strip": "Strip1"}),
            (TOOL_CONFIGURE_VSE_AUDIO, {"name": "Audio1", "volume": 0.8}),
            (TOOL_MANAGE_VSE_SOUND_MODIFIERS, {"action": "ADD", "name": "Audio1", "modifier_type": "PITCH"}),
            (TOOL_TRANSFORM_VSE_STRIP, {"name": "Strip1", "scale_x": 1.5}),
            (TOOL_CROP_VSE_STRIP, {"name": "Strip1", "min_x": 10}),
            (TOOL_ANIMATE_VSE_STRIP, {"name": "Strip1", "action": "INSERT_KEYFRAME", "property": "VOLUME", "frame": 10, "value": 1.0}),
            (TOOL_MANAGE_VSE_STRIP_MODIFIERS, {"action": "ADD", "name": "Strip1", "modifier_type": "COLOR_BALANCE"}),
            (TOOL_CREATE_VSE_TEXT_STRIP, {"text": "Title", "channel": 2, "frame_start": 1, "duration": 30}),
            (TOOL_CONFIGURE_VSE_TEXT_STYLE, {"name": "Text1", "font_size": 48}),
            (TOOL_GROUP_VSE_META_STRIP, {"action": "CREATE", "strip_names": ["Strip1", "Strip2"]}),
            (TOOL_CREATE_VSE_SCENE_STRIP, {"scene_name": "Scene", "channel": 1, "frame_start": 1}),
            (TOOL_RENDER_VSE_SEQUENCE, {"output_path": "render_test.mp4"}),
            (TOOL_MIXDOWN_VSE_AUDIO, {"output_path": "audio_test.flac"}),
        ]

        # Ensure autoapprove is disabled for testing strict approval enforcement
        orig_autoapprove = os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE")
        os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "0"
        try:
            for tool_name, params in mutating_tools:
                task = AgentTask(
                    task_id=f"t_no_app_{tool_name}",
                    required_capability=CAPABILITY_VSE_TIMELINE,
                    task_type=tool_name,
                    input_params=params,
                )
                res = self.agent.execute_task(task, self.executor, trusted_approval=False)
                self.assertEqual(res.status, TaskStatus.FAILED, f"Tool {tool_name} executed without approval")
                self.assertIn("Approval required", res.errors[0])
                self.assertEqual(len(self.executor.calls), 0)
        finally:
            if orig_autoapprove is not None:
                os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = orig_autoapprove
            else:
                os.environ.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)

    def test_read_only_inspect_vse_timeline_without_approval(self):
        task = AgentTask(
            task_id="t_inspect",
            required_capability=CAPABILITY_VSE_TIMELINE,
            task_type=TOOL_INSPECT_VSE_TIMELINE,
            input_params={"include_strips": True, "include_markers": True},
        )
        res = self.agent.execute_task(task, self.executor, trusted_approval=False)
        self.assertEqual(res.status, TaskStatus.SUCCEEDED)
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual(self.executor.calls[0]["tool_name"], TOOL_INSPECT_VSE_TIMELINE)


class TestPathTraversalAndSymlinkEscapeDefense(unittest.TestCase):
    """Verifies strict path sanitization, traversal defenses, and symlink escape checks."""

    def setUp(self):
        self.agent = VideoEditorAgent()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validate_vse_path_rejects_empty(self):
        with self.assertRaises(ValueError):
            validate_vse_path("")
        with self.assertRaises(ValueError):
            validate_vse_path("   ")
        with self.assertRaises(ValueError):
            validate_vse_path(None)

    def test_validate_vse_path_rejects_parent_traversal(self):
        traversal_paths = [
            "../secret.mp4",
            "..\\secret.mp4",
            "media/../../secret.mp4",
            "C:/videos/../secret.mp4",
        ]
        for p in traversal_paths:
            with self.assertRaises(ValueError):
                validate_vse_path(p, allowed_root=self.workspace_root)

    def test_validate_vse_path_accepts_valid_workspace_file(self):
        target = os.path.join(self.workspace_root, "video.mp4")
        with open(target, "w") as f:
            f.write("mock")

        resolved = validate_vse_path(target, allowed_root=self.workspace_root)
        self.assertEqual(resolved, os.path.realpath(target))

        # Also accepts relative path inside workspace
        rel_resolved = validate_vse_path("video.mp4", allowed_root=self.workspace_root)
        self.assertEqual(rel_resolved, os.path.realpath(target))

    def test_validate_vse_path_rejects_symlink_escape(self):
        outside_path = os.path.abspath(os.path.join(self.workspace_root, "..", "outside", "secret.mp4"))
        with patch("os.path.realpath", side_effect=lambda p: outside_path if "secret" in p else os.path.abspath(p)):
            fake_symlink = os.path.join(self.workspace_root, "link_to_secret.mp4")
            with self.assertRaises(PermissionError):
                validate_vse_path(fake_symlink, allowed_root=self.workspace_root)

    def test_validate_task_parameters_catches_traversal(self):
        task_render = AgentTask(
            task_id="t_render_bad",
            required_capability=CAPABILITY_VSE_RENDERING,
            task_type=TOOL_RENDER_VSE_SEQUENCE,
            input_params={"output_path": "../escape.mp4"},
        )
        errors = self.agent.validate_task_parameters(task_render)
        self.assertTrue(any("Path traversal" in err or "forbidden" in err for err in errors))

        task_mixdown = AgentTask(
            task_id="t_mixdown_bad",
            required_capability=CAPABILITY_VSE_AUDIO,
            task_type=TOOL_MIXDOWN_VSE_AUDIO,
            input_params={"output_path": "out/../../escape.wav"},
        )
        errors_m = self.agent.validate_task_parameters(task_mixdown)
        self.assertTrue(any("Path traversal" in err or "forbidden" in err for err in errors_m))


class TestDirectorEditorialBriefDelegation(unittest.TestCase):
    """Verifies DirectorAgent parsing, decomposition, and execution of editorial briefs."""

    def setUp(self):
        self.director = DirectorAgent()
        self.executor = MockExecutor()
        self.dispatcher = AgentDispatcher(executor=self.executor)

    def test_decompose_editorial_brief_into_vse_tasks(self):
        brief = "Assemble a video timeline with cut strips, add crossfade transition, mix audio volume, and render sequence to MP4."
        contract = self.director.decompose_brief(brief, title="Commercial Edit")

        self.assertEqual(contract.director_agent_id, DIRECTOR_AGENT_ID)
        self.assertIn(VIDEO_EDITOR_AGENT_ID, contract.domain_tasks)

        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        self.assertTrue(len(tasks) >= 4)

        task_types = [t.task_type for t in tasks]
        self.assertIn(TOOL_CREATE_VSE_STRIP, task_types)
        self.assertIn(TOOL_CREATE_VSE_TRANSITION, task_types)
        self.assertIn(TOOL_CONFIGURE_VSE_AUDIO, task_types)
        self.assertIn(TOOL_RENDER_VSE_SEQUENCE, task_types)

    def test_decompose_compound_brief_timeline_titles_audio_render(self):
        brief = "Assemble a video timeline with color strip, add title card, configure audio volume, and render sequence to MP4."
        contract = self.director.decompose_brief(brief, title="Full Editorial Pipeline")

        self.assertIn(VIDEO_EDITOR_AGENT_ID, contract.domain_tasks)
        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        self.assertEqual(len(tasks), 4)

        # Verify ordering and types
        self.assertEqual(tasks[0].task_type, TOOL_CREATE_VSE_STRIP)
        self.assertEqual(tasks[1].task_type, TOOL_CREATE_VSE_TEXT_STRIP)
        self.assertEqual(tasks[2].task_type, TOOL_CONFIGURE_VSE_AUDIO)
        self.assertEqual(tasks[3].task_type, TOOL_RENDER_VSE_SEQUENCE)

        # Verify sequential dependencies (rendering must follow editing)
        self.assertEqual(tasks[0].dependencies, [])
        self.assertEqual(tasks[1].dependencies, [tasks[0].task_id])
        self.assertEqual(tasks[2].dependencies, [tasks[1].task_id])
        self.assertEqual(tasks[3].dependencies, [tasks[2].task_id])

    def test_decompose_compound_brief_cuts_transitions_render(self):
        brief = "Cut video strip, add crossfade transition, and render sequence to MP4."
        contract = self.director.decompose_brief(brief, title="Cut Transition Render")

        self.assertIn(VIDEO_EDITOR_AGENT_ID, contract.domain_tasks)
        tasks = contract.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        self.assertEqual(len(tasks), 3)

        self.assertEqual(tasks[0].task_type, TOOL_SPLIT_VSE_STRIP)
        self.assertEqual(tasks[1].task_type, TOOL_CREATE_VSE_TRANSITION)
        self.assertEqual(tasks[2].task_type, TOOL_RENDER_VSE_SEQUENCE)

        # Verify dependencies
        self.assertEqual(tasks[1].dependencies, [tasks[0].task_id])
        self.assertEqual(tasks[2].dependencies, [tasks[1].task_id])

    def test_decompose_single_intent_backward_compatibility(self):
        # Single title
        c_title = self.director.decompose_brief("Add video title card")
        self.assertEqual(len(c_title.domain_tasks[VIDEO_EDITOR_AGENT_ID]), 1)
        self.assertEqual(c_title.domain_tasks[VIDEO_EDITOR_AGENT_ID][0].task_type, TOOL_CREATE_VSE_TEXT_STRIP)

        # Single audio
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

    def test_decompose_empty_ambiguous_and_repeated_keywords(self):
        # Empty brief
        c_empty = self.director.decompose_brief("")
        self.assertNotIn(VIDEO_EDITOR_AGENT_ID, c_empty.domain_tasks)

        # Ambiguous non-video brief
        c_mesh = self.director.decompose_brief("Create a metallic cylinder mesh and export to GLB")
        self.assertNotIn(VIDEO_EDITOR_AGENT_ID, c_mesh.domain_tasks)

        # Repeated keywords within same intent should NOT duplicate tasks
        c_repeat = self.director.decompose_brief("Configure video audio volume and audio music and audio sound")
        tasks = c_repeat.domain_tasks[VIDEO_EDITOR_AGENT_ID]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].task_type, TOOL_CONFIGURE_VSE_AUDIO)

    def test_compound_editorial_requires_approval_and_executes_when_approved(self):
        contract = self.director.decompose_brief(
            "Assemble a video timeline with color strip, add title card, configure audio volume, and render sequence to MP4."
        )
        orig_autoapprove = os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE")
        os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "0"
        try:
            # Without trusted approval -> halts in AWAITING_APPROVAL, zero executor calls
            plan, results = self.director.submit_contract(contract, self.dispatcher, trusted_approval=False)
            self.assertEqual(plan.status, TaskStatus.AWAITING_APPROVAL)
            self.assertEqual(len(self.executor.calls), 0)
            self.assertTrue(all(r.status == TaskStatus.AWAITING_APPROVAL for r in results))

            # With trusted approval -> executes all 4 tasks sequentially
            plan_app, results_app = self.director.submit_contract(contract, self.dispatcher, trusted_approval=True)
            self.assertEqual(plan_app.status, TaskStatus.SUCCEEDED)
            self.assertEqual(len(results_app), 4)
            self.assertTrue(all(r.status == TaskStatus.SUCCEEDED for r in results_app))
            self.assertEqual(len(self.executor.calls), 4)
        finally:
            if orig_autoapprove is not None:
                os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = orig_autoapprove
            else:
                os.environ.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)

    def test_submit_editorial_contract_requires_approval(self):
        contract = self.director.decompose_brief("Cut video and render sequence")
        orig_autoapprove = os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE")
        os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "0"
        try:
            plan, results = self.director.submit_contract(contract, self.dispatcher, trusted_approval=False)
            self.assertEqual(plan.status, TaskStatus.AWAITING_APPROVAL)
            self.assertEqual(len(self.executor.calls), 0)
        finally:
            if orig_autoapprove is not None:
                os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = orig_autoapprove
            else:
                os.environ.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)

    def test_submit_editorial_contract_approved_executes_successfully(self):
        contract = self.director.decompose_brief("Inspect timeline and cut video")
        plan, results = self.director.submit_contract(contract, self.dispatcher, trusted_approval=True)
        self.assertEqual(plan.status, TaskStatus.SUCCEEDED)
        self.assertTrue(all(r.status == TaskStatus.SUCCEEDED for r in results))
        self.assertTrue(len(self.executor.calls) >= 2)


class TestAll22VSEToolsExecution(unittest.TestCase):
    """Executes all 22 VSE tools end-to-end through VideoEditorAgent with valid parameters."""

    def setUp(self):
        self.agent = VideoEditorAgent()
        self.executor = MockExecutor()

    def test_execute_all_22_tools_with_approval(self):
        valid_payloads = {
            TOOL_INSPECT_VSE_TIMELINE: {},
            TOOL_CREATE_VSE_STRIP: {
                "strip_type": "COLOR",
                "channel": 1,
                "frame_start": 1,
                "duration": 30,
                "color": [1.0, 0.0, 0.0],
            },
            TOOL_MODIFY_VSE_STRIP: {"name": "Strip1", "channel": 2},
            TOOL_DELETE_VSE_STRIP: {"name": "Strip1"},
            TOOL_MANAGE_TIMELINE_MARKERS: {"action": "ADD", "name": "Marker1", "frame": 10},
            TOOL_TRIM_VSE_STRIP: {"name": "Strip1", "left_handle": 10, "right_handle": 50},
            TOOL_SPLIT_VSE_STRIP: {"name": "Strip1", "split_frame": 15},
            TOOL_REORDER_VSE_STRIPS: {"action": "MOVE", "name": "Strip1", "channel": 2, "target_frame": 30},
            TOOL_CREATE_VSE_TRANSITION: {"transition_type": "CROSS", "input1": "Strip1", "input2": "Strip2"},
            TOOL_CONFIGURE_VSE_EFFECT: {
                "action": "CREATE",
                "effect_type": "GLOW",
                "channel": 1,
                "frame_start": 1,
                "duration": 30,
                "input_strip": "Strip1",
            },
            TOOL_CONFIGURE_VSE_AUDIO: {"name": "Audio1", "volume": 0.8},
            TOOL_MANAGE_VSE_SOUND_MODIFIERS: {"action": "ADD", "name": "Audio1", "modifier_type": "PITCH"},
            TOOL_TRANSFORM_VSE_STRIP: {"name": "Strip1", "scale_x": 1.5},
            TOOL_CROP_VSE_STRIP: {"name": "Strip1", "min_x": 10},
            TOOL_ANIMATE_VSE_STRIP: {
                "name": "Strip1",
                "action": "INSERT_KEYFRAME",
                "property": "VOLUME",
                "frame": 10,
                "value": 1.0,
            },
            TOOL_MANAGE_VSE_STRIP_MODIFIERS: {
                "action": "ADD",
                "name": "Strip1",
                "modifier_type": "COLOR_BALANCE",
            },
            TOOL_CREATE_VSE_TEXT_STRIP: {"text": "Hello World", "channel": 2, "frame_start": 1, "duration": 30},
            TOOL_CONFIGURE_VSE_TEXT_STYLE: {"name": "Text1", "font_size": 48},
            TOOL_GROUP_VSE_META_STRIP: {"action": "CREATE", "strip_names": ["Strip1", "Strip2"]},
            TOOL_CREATE_VSE_SCENE_STRIP: {"scene_name": "Scene", "channel": 1, "frame_start": 1},
            TOOL_RENDER_VSE_SEQUENCE: {"output_path": "render_seq.mp4"},
            TOOL_MIXDOWN_VSE_AUDIO: {"output_path": "audio_mixdown.flac"},
        }

        self.assertEqual(len(valid_payloads), 22)

        for tool_name in sorted(SUPPORTED_VSE_TOOLS):
            params = valid_payloads[tool_name]
            task = AgentTask(
                task_id=f"t_{tool_name}",
                required_capability=CAPABILITY_VSE_TIMELINE,
                task_type=tool_name,
                input_params=params,
            )
            res = self.agent.execute_task(task, self.executor, trusted_approval=True)
            self.assertEqual(
                res.status,
                TaskStatus.SUCCEEDED,
                f"Tool {tool_name} failed: {res.errors}",
            )
            self.assertEqual(res.verification.status, "PASS")

        self.assertEqual(len(self.executor.calls), 22)


if __name__ == "__main__":
    unittest.main()
