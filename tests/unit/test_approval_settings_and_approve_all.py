"""
Unit tests for Optional Scene Mutation Approval and Task-Group Approve All.
Tests:
- Default setting is ON (Require Scene Mutation Approval = True)
- Setting persistence across mock preferences / scene property
- Task group Approve All (batch approval with correlated unique tokens)
- Mixed task IDs isolation (approving Task A never approves Task B or unassigned tasks)
- Expired request handling during batch approval (expired requests fail closed)
- Duplicate / already-resolved request rejection
- Deny behavior remains isolated to target request
- Automatic approval when setting is OFF (no dialog, full authorization & consumption flow)
- Verification that validation, collision detection, and replay prevention remain enforced
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.approval_registry import (
    ApprovalRegistry,
    compute_arg_hash,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_request_approval,
    handle_check_approval_status,
    handle_resolve_approval,
    handle_get_approval_settings,
    handle_set_approval_settings,
    handle_create_primitive,
    handle_transform_object,
    is_approval_required,
)


class MockBlenderObject:
    def __init__(self, name="TestObj", location=None, rotation=None, scale=None, dimensions=None):
        self.name = name
        self.type = "MESH"
        self.location = list(location) if location else [0.0, 0.0, 0.0]
        self.rotation_euler = list(rotation) if rotation else [0.0, 0.0, 0.0]
        self.scale = list(scale) if scale else [1.0, 1.0, 1.0]
        self.dimensions = list(dimensions) if dimensions else [1.0, 1.0, 1.0]
        self.users_collection = []


class MockBpyScene:
    def __init__(self):
        self.objects = []
        self.umcp_require_scene_mutation_approval = True


class MockBpyOps:
    def __init__(self):
        self.wm = MagicMock()
        self.wm.save_userpref = MagicMock(return_value={'FINISHED'})
        self.mesh = MagicMock()
        self.mesh.primitive_cube_add = MagicMock()
        self.mesh.primitive_uv_sphere_add = MagicMock()


class MockBpyContext:
    def __init__(self, scene=None):
        self.scene = scene or MockBpyScene()
        self.active_object = None
        self.view_layer = MagicMock()
        self.view_layer.update = MagicMock()
        self.window_manager = MagicMock()


class MockBpyData:
    def __init__(self):
        self.objects = {}


class MockBpyModule:
    def __init__(self):
        self.context = MockBpyContext()
        self.data = MockBpyData()
        self.ops = MockBpyOps()
        self.app = MagicMock()
        self.app.timers = MagicMock()
        self.app.timers.register = MagicMock()


class TestApprovalSettingsAndApproveAll(unittest.TestCase):
    """Test suite covering optional approval setting and task group approve all logic."""

    def setUp(self):
        self.registry = ApprovalRegistry()

    def test_default_approval_setting_is_on(self):
        """Setting defaults to ON (True) ensuring fail-closed security by default."""
        self.assertTrue(self.registry.require_scene_mutation_approval)

    def test_setting_toggle(self):
        """Toggling setting reflects immediately in registry state."""
        self.registry.require_scene_mutation_approval = False
        self.assertFalse(self.registry.require_scene_mutation_approval)
        self.registry.require_scene_mutation_approval = True
        self.assertTrue(self.registry.require_scene_mutation_approval)

    def test_approve_all_same_task_group(self):
        """
        When multiple requests share the same task_id, approving one request
        with approve_task_group=True automatically approves all other eligible
        pending requests in that same task group with unique approval tokens.
        """
        task_id = "task-batch-001"
        req1 = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "Cube1"}, task_id=task_id)
        req2 = self.registry.create_request("create_primitive", {"primitive_type": "sphere", "name": "Sphere1"}, task_id=task_id)
        req3 = self.registry.create_request("transform_object", {"name": "Cube1", "location": [1.0, 2.0, 3.0]}, task_id=task_id)

        self.assertEqual(req1.status, "pending")
        self.assertEqual(req2.status, "pending")
        self.assertEqual(req3.status, "pending")

        # User approves req1
        ok, token1 = self.registry.resolve_request(req1.request_id, "approved", approve_task_group=True)
        self.assertTrue(ok)
        self.assertIsNotNone(token1)

        # Verify req1 is approved
        self.assertEqual(req1.status, "approved")
        self.assertEqual(req1.approval_token, token1)

        # Verify req2 and req3 were also approved in the same task group
        self.assertEqual(req2.status, "approved")
        self.assertEqual(req3.status, "approved")
        self.assertIsNotNone(req2.approval_token)
        self.assertIsNotNone(req3.approval_token)

        # Tokens must be distinct for each request (cryptographic separation)
        self.assertNotEqual(token1, req2.approval_token)
        self.assertNotEqual(token1, req3.approval_token)
        self.assertNotEqual(req2.approval_token, req3.approval_token)

        # All 3 tokens must be consumable for their exact respective requests
        ok_c1, _ = self.registry.consume_approval(req1.request_id, token1, "create_primitive", {"primitive_type": "cube", "name": "Cube1"})
        self.assertTrue(ok_c1)

        ok_c2, _ = self.registry.consume_approval(req2.request_id, req2.approval_token, "create_primitive", {"primitive_type": "sphere", "name": "Sphere1"})
        self.assertTrue(ok_c2)

        ok_c3, _ = self.registry.consume_approval(req3.request_id, req3.approval_token, "transform_object", {"name": "Cube1", "location": [1.0, 2.0, 3.0]})
        self.assertTrue(ok_c3)

    def test_approve_all_mixed_task_ids_isolation(self):
        """
        Approving a request belonging to Task A must NEVER approve requests
        belonging to Task B or requests with no task_id.
        """
        req_a1 = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "CubeA1"}, task_id="task-A")
        req_a2 = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "CubeA2"}, task_id="task-A")
        req_b1 = self.registry.create_request("create_primitive", {"primitive_type": "sphere", "name": "SphereB1"}, task_id="task-B")
        req_none = self.registry.create_request("create_primitive", {"primitive_type": "plane", "name": "PlaneNone"}, task_id=None)

        ok, token_a1 = self.registry.resolve_request(req_a1.request_id, "approved", approve_task_group=True)
        self.assertTrue(ok)

        # Task A requests are approved
        self.assertEqual(req_a1.status, "approved")
        self.assertEqual(req_a2.status, "approved")

        # Task B and untasked requests MUST remain pending
        self.assertEqual(req_b1.status, "pending")
        self.assertIsNone(req_b1.approval_token)
        self.assertEqual(req_none.status, "pending")
        self.assertIsNone(req_none.approval_token)

    def test_approve_all_unassigned_task_id_does_not_approve_other_unassigned(self):
        """
        If a request has task_id=None, approving it only approves that single request,
        never other requests with task_id=None.
        """
        req1 = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "Cube1"}, task_id=None)
        req2 = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "Cube2"}, task_id=None)

        ok, token1 = self.registry.resolve_request(req1.request_id, "approved", approve_task_group=True)
        self.assertTrue(ok)
        self.assertEqual(req1.status, "approved")
        self.assertEqual(req2.status, "pending")
        self.assertIsNone(req2.approval_token)

    def test_approve_all_rejects_expired_requests_in_group(self):
        """
        Expired requests in the same task group must NOT be approved.
        They must be marked expired and fail closed.
        """
        task_id = "task-expiry-test"
        req_valid = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "ValidCube"}, timeout=30.0, task_id=task_id)
        req_expired = self.registry.create_request("create_primitive", {"primitive_type": "sphere", "name": "ExpiredSphere"}, timeout=0.01, task_id=task_id)

        # Force req_expired to be expired
        time.sleep(0.02)
        self.assertTrue(req_expired.is_expired)

        ok, token_valid = self.registry.resolve_request(req_valid.request_id, "approved", approve_task_group=True)
        self.assertTrue(ok)
        self.assertEqual(req_valid.status, "approved")

        # The expired request in the group must be marked expired, NOT approved
        self.assertEqual(req_expired.status, "expired")
        self.assertIsNone(req_expired.approval_token)

    def test_duplicate_or_already_resolved_request_rejected(self):
        """
        Resolving an already-resolved request must be rejected to prevent duplicate decisions.
        """
        req = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "Cube1"})
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # Duplicate resolution attempt
        ok_dup, msg_dup = self.registry.resolve_request(req.request_id, "approved")
        self.assertFalse(ok_dup)
        self.assertIn("already resolved", msg_dup)

        # Duplicate resolution with different decision
        ok_deny, msg_deny = self.registry.resolve_request(req.request_id, "denied")
        self.assertFalse(ok_deny)
        self.assertIn("already resolved", msg_deny)

    def test_deny_behavior_unchanged_and_isolated(self):
        """
        Denying a request affects ONLY that request, even if other requests share the same task_id.
        """
        task_id = "task-deny-test"
        req1 = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "Cube1"}, task_id=task_id)
        req2 = self.registry.create_request("create_primitive", {"primitive_type": "sphere", "name": "Sphere1"}, task_id=task_id)

        ok, msg = self.registry.resolve_request(req1.request_id, "denied", approve_task_group=True)
        self.assertTrue(ok)
        self.assertEqual(req1.status, "denied")

        # req2 remains pending and unaffected
        self.assertEqual(req2.status, "pending")
        self.assertIsNone(req2.approval_token)

    def test_automatic_approval_when_setting_off(self):
        """
        When Require Scene Mutation Approval is OFF:
        - handle_request_approval creates the request and immediately resolves it as 'approved'
        - Generates valid approval token
        - Does not trigger UI dialog timers
        """
        mock_bpy = MockBpyModule()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            test_reg.require_scene_mutation_approval = False
            mock_get_reg.return_value = test_reg

            resp = handle_request_approval(
                bpy_module=mock_bpy,
                params={
                    "tool_name": "create_primitive",
                    "params": {"primitive_type": "cube", "name": "AutoCube"},
                    "timeout": 30.0,
                    "task_id": "auto-task-1",
                }
            )

            self.assertEqual(resp["status"], "approved")
            self.assertIsNotNone(resp.get("approval_token"))
            self.assertEqual(resp["task_id"], "auto-task-1")

            # Verify no UI dialog timers were registered
            mock_bpy.app.timers.register.assert_not_called()

            # Verify the token is strictly verified and consumable
            ok, msg = test_reg.consume_approval(
                resp["request_id"],
                resp["approval_token"],
                "create_primitive",
                {"primitive_type": "cube", "name": "AutoCube", "task_id": "auto-task-1"}
            )
            self.assertTrue(ok)

    def test_automatic_approval_preserves_tamper_rejection(self):
        """
        Even when auto-approved, parameter tampering (mismatched parameters)
        is strictly rejected during consumption.
        """
        mock_bpy = MockBpyModule()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            test_reg.require_scene_mutation_approval = False
            mock_get_reg.return_value = test_reg

            resp = handle_request_approval(
                bpy_module=mock_bpy,
                params={
                    "tool_name": "create_primitive",
                    "params": {"primitive_type": "cube", "name": "TargetCube", "location": [0.0, 0.0, 0.0]},
                }
            )
            req_id = resp["request_id"]
            token = resp["approval_token"]

            # Attempt to consume with tampered parameters (different location)
            ok, msg = test_reg.consume_approval(
                req_id,
                token,
                "create_primitive",
                {"primitive_type": "cube", "name": "TargetCube", "location": [99.0, 99.0, 99.0]}
            )
            self.assertFalse(ok)
            self.assertIn("Argument tampering detected", msg)

    def test_automatic_approval_preserves_single_use_replay_rejection(self):
        """
        Even when auto-approved, tokens cannot be replayed more than once.
        """
        mock_bpy = MockBpyModule()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            test_reg.require_scene_mutation_approval = False
            mock_get_reg.return_value = test_reg

            resp = handle_request_approval(
                bpy_module=mock_bpy,
                params={
                    "tool_name": "create_primitive",
                    "params": {"primitive_type": "cube", "name": "ReplayCube"},
                }
            )
            req_id = resp["request_id"]
            token = resp["approval_token"]

            # First consumption succeeds
            ok1, _ = test_reg.consume_approval(req_id, token, "create_primitive", {"primitive_type": "cube", "name": "ReplayCube"})
            self.assertTrue(ok1)

            # Second consumption (replay) fails
            ok2, msg2 = test_reg.consume_approval(req_id, token, "create_primitive", {"primitive_type": "cube", "name": "ReplayCube"})
            self.assertFalse(ok2)
            self.assertIn("Replay rejected", msg2)

    def test_task_id_correlation_enforced(self):
        """
        If a request has task_id='TaskAlpha' and execution params specify task_id='TaskBeta',
        consumption must fail closed with task correlation mismatch.
        """
        req = self.registry.create_request("create_primitive", {"primitive_type": "cube", "name": "CorrCube"}, task_id="TaskAlpha")
        ok, token = self.registry.resolve_request(req.request_id, "approved")
        self.assertTrue(ok)

        # Consume with mismatched task_id
        ok_bad, msg_bad = self.registry.consume_approval(
            req.request_id,
            token,
            "create_primitive",
            {"primitive_type": "cube", "name": "CorrCube", "task_id": "TaskBeta"}
        )
        self.assertFalse(ok_bad)
        self.assertIn("Task correlation mismatch", msg_bad)

        # Consume with matching task_id succeeds
        ok_good, _ = self.registry.consume_approval(
            req.request_id,
            token,
            "create_primitive",
            {"primitive_type": "cube", "name": "CorrCube", "task_id": "TaskAlpha"}
        )
        self.assertTrue(ok_good)

    def test_bridge_get_and_set_approval_settings(self):
        """
        Tests handle_get_approval_settings and handle_set_approval_settings.
        """
        mock_bpy = MockBpyModule()

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry") as mock_get_reg:
            test_reg = ApprovalRegistry()
            mock_get_reg.return_value = test_reg

            # Initially True
            res1 = handle_get_approval_settings(bpy_module=mock_bpy)
            self.assertTrue(res1["require_scene_mutation_approval"])

            # Set to False
            res2 = handle_set_approval_settings(bpy_module=mock_bpy, params={"require_scene_mutation_approval": False})
            self.assertFalse(res2["require_scene_mutation_approval"])
            self.assertFalse(test_reg.require_scene_mutation_approval)
            self.assertFalse(mock_bpy.context.scene.umcp_require_scene_mutation_approval)

            # Query again
            res3 = handle_get_approval_settings(bpy_module=mock_bpy)
            self.assertFalse(res3["require_scene_mutation_approval"])

            # Set back to True
            res4 = handle_set_approval_settings(bpy_module=mock_bpy, params={"require_scene_mutation_approval": True})
            self.assertTrue(res4["require_scene_mutation_approval"])
            self.assertTrue(test_reg.require_scene_mutation_approval)
            self.assertTrue(mock_bpy.context.scene.umcp_require_scene_mutation_approval)


if __name__ == "__main__":
    unittest.main()
