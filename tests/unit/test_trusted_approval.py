"""
Focused unit tests for the Trusted Approval Mechanism.
Validates the approval trust boundary for scene mutations:
- Missing approval rejected by default (read-only mode)
- Denied approval rejected
- Approved execution through trusted mechanism succeeds
- Attempts to bypass approval through tool arguments rejected
- Read-only tools unaffected
"""

import unittest
from unittest.mock import MagicMock

from mcp_service.security.approval import ApprovalManager
from mcp_service.execution.blender_executor import BlenderExecutor
from shared.schemas.tool_schemas import validate_tool_input, TOOL_CREATE_PRIMITIVE, TOOL_GET_SCENE_SUMMARY


class TestTrustedApproval(unittest.TestCase):
    """Test suite for trusted approval verification and trust boundary enforcement."""

    def setUp(self):
        self.approval_mgr = ApprovalManager()
        self.mock_client = MagicMock()
        self.mock_client.ping.return_value = True
        self.mock_client.send_command.return_value = {
            "status": "success",
            "result": {
                "created": True,
                "name": "TestCube",
                "primitive_type": "cube",
                "location": [0.0, 0.0, 0.0],
                "dimensions": [1.0, 1.0, 1.0],
            }
        }
        self.executor = BlenderExecutor(approval_manager=self.approval_mgr)
        self.executor.client = self.mock_client

    def test_missing_approval_rejected_by_default(self):
        """When no trusted approval provider is configured, mutations are rejected by default."""
        self.assertFalse(self.approval_mgr.has_provider)

        resp = self.executor.execute_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "TestCube",
        })

        self.assertEqual(resp.status, "error")
        self.assertIn("Approval required", resp.message)
        self.assertIn("read-only mode", resp.message)
        self.mock_client.send_command.assert_not_called()

    def test_denied_approval_rejected(self):
        """When trusted approval provider denies consent (returns False), mutation is rejected."""
        # Trusted provider explicitly denies
        self.approval_mgr.set_provider(lambda tool, params: False)

        resp = self.executor.execute_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "DeniedCube",
        })

        self.assertEqual(resp.status, "error")
        self.assertIn("Approval denied", resp.message)
        self.mock_client.send_command.assert_not_called()

    def test_approved_execution_through_trusted_mechanism(self):
        """When trusted approval provider grants consent (returns True), mutation executes."""
        # Trusted provider grants approval
        self.approval_mgr.set_provider(lambda tool, params: True)

        resp = self.executor.execute_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "ApprovedCube",
            "location": [1.0, 2.0, 3.0],
            "dimensions": [2.0, 2.0, 2.0],
        })

        self.assertEqual(resp.status, "success")
        self.assertTrue(resp.result.get("created"))
        self.mock_client.send_command.assert_called_once()
        cmd_name, cmd_params = self.mock_client.send_command.call_args[0]
        self.assertEqual(cmd_name, TOOL_CREATE_PRIMITIVE)
        self.assertTrue(cmd_params.get("trusted_approval"))

    def test_attempts_to_bypass_approval_through_tool_arguments_rejected(self):
        """
        Model passing 'approved=True' in tool arguments without trusted approval
        is recognized as an untrusted bypass attempt and rejected.
        """
        # Scenario A: No trusted provider configured, model supplies approved=True
        resp_no_provider = self.executor.execute_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "SneakyCube",
            "approved": True,
        })
        self.assertEqual(resp_no_provider.status, "error")
        self.assertIn("Approval denied", resp_no_provider.message)
        self.assertIn("untrusted", resp_no_provider.message)
        self.mock_client.send_command.assert_not_called()

        # Scenario B: Trusted provider denies, but model supplies approved=True
        self.approval_mgr.set_provider(lambda tool, params: False)
        resp_denied = self.executor.execute_tool(TOOL_CREATE_PRIMITIVE, {
            "primitive_type": "cube",
            "name": "SneakyCube2",
            "approved": True,
        })
        self.assertEqual(resp_denied.status, "error")
        self.assertIn("Approval denied", resp_denied.message)
        self.assertIn("untrusted", resp_denied.message)
        self.mock_client.send_command.assert_not_called()

    def test_schema_validator_rejects_untrusted_bypass_directly(self):
        """validate_tool_input directly rejects unapproved mutation even if approved=True is passed."""
        # Without trusted_approval=True, approved=True in params raises PermissionError
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "BypassBox",
                "approved": True,
            }, trusted_approval=False)
        self.assertIn("untrusted", str(ctx.exception))

    def test_cannot_inject_trusted_approval_via_arguments(self):
        """Clients cannot pass 'trusted_approval' in tool arguments to forge authorization."""
        # Schema rejects unknown parameter 'trusted_approval'
        with self.assertRaises(ValueError) as ctx:
            validate_tool_input(TOOL_CREATE_PRIMITIVE, {
                "primitive_type": "cube",
                "name": "ForgedCube",
                "trusted_approval": True,
            })
        self.assertIn("Unknown parameter 'trusted_approval'", str(ctx.exception))

    def test_read_only_tools_unaffected(self):
        """Read-only tools require no approval and execute normally under default settings."""
        self.assertFalse(self.approval_mgr.requires_approval(TOOL_GET_SCENE_SUMMARY))

        self.mock_client.send_command.return_value = {
            "status": "success",
            "result": {"scene_name": "Scene", "total_objects": 3}
        }

        resp = self.executor.execute_tool(TOOL_GET_SCENE_SUMMARY, {})
        self.assertEqual(resp.status, "success")
        self.mock_client.send_command.assert_called_once_with(TOOL_GET_SCENE_SUMMARY, {"include_collections": True})


if __name__ == "__main__":
    unittest.main()
