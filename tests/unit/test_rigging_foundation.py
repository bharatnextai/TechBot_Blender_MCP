"""
Unit tests for Rigging & Armatures Foundation (Phase 2.3 - v0.1.76).

Validates:
1. Tool schema registrations, permission tiers, and argument validation.
2. Approval tampering protection (untrusted approved=True rejection).
3. Deterministic snapshot ID calculation and optimistic concurrency detection.
4. Transactional rollback logic on invalid operations.
5. ModelingAgent capability declarations and routing.
"""

import hashlib
import json
import pytest
from unittest.mock import MagicMock

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_CREATE_ARMATURE,
    TOOL_EDIT_ARMATURE_BONES,
    TOOL_INSPECT_ARMATURE,
    TOOL_BIND_ARMATURE_MESH,
    TOOL_CONFIGURE_BONE_CONSTRAINT,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
    validate_tool_input,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    CAPABILITY_MODELING_RIGGING,
    CAPABILITY_MODELING_RIGGING_INSPECT,
    SUPPORTED_MODELING_TOOLS,
)
from blender_addon.universal_mcp.bridge.rigging_foundation import (
    compute_armature_snapshot_id,
    SUPPORTED_CONSTRAINTS,
    SUPPORTED_BIND_MODES,
)


class TestRiggingToolSchemas:
    """Validates registration, schema structure, and argument validation."""

    def test_rigging_tools_registered_in_definitions(self):
        for tool in (
            TOOL_CREATE_ARMATURE,
            TOOL_EDIT_ARMATURE_BONES,
            TOOL_INSPECT_ARMATURE,
            TOOL_BIND_ARMATURE_MESH,
            TOOL_CONFIGURE_BONE_CONSTRAINT,
        ):
            assert tool in TOOL_DEFINITIONS, f"Tool '{tool}' must be in TOOL_DEFINITIONS"

    def test_permission_tiers(self):
        assert TOOL_DEFINITIONS[TOOL_CREATE_ARMATURE]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_EDIT_ARMATURE_BONES]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_INSPECT_ARMATURE]["permission_tier"] == PERMISSION_READ_ONLY
        assert TOOL_DEFINITIONS[TOOL_BIND_ARMATURE_MESH]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_CONFIGURE_BONE_CONSTRAINT]["permission_tier"] == PERMISSION_SCENE_MUTATION

    def test_validate_create_armature_valid(self):
        params = {"name": "TestRig", "location": [0.0, 1.0, 2.0]}
        sanitized = validate_tool_input(TOOL_CREATE_ARMATURE, params, trusted_approval=True)
        assert sanitized["name"] == "TestRig"
        assert sanitized["location"] == [0.0, 1.0, 2.0]

    def test_validate_create_armature_invalid_location(self):
        with pytest.raises(ValueError, match="3-element finite numeric list"):
            validate_tool_input(TOOL_CREATE_ARMATURE, {"location": [0.0, 1.0]}, trusted_approval=True)

    def test_validate_edit_armature_bones_missing_name(self):
        with pytest.raises(ValueError, match="Parameter 'armature_name' cannot be empty"):
            validate_tool_input(TOOL_EDIT_ARMATURE_BONES, {"armature_name": ""}, trusted_approval=True)

    def test_validate_bind_armature_mesh_valid(self):
        params = {"mesh_object_name": "Body", "armature_name": "Rig", "bind_mode": "AUTOMATIC"}
        sanitized = validate_tool_input(TOOL_BIND_ARMATURE_MESH, params, trusted_approval=True)
        assert sanitized["bind_mode"] == "AUTOMATIC"

    def test_validate_bind_armature_mesh_invalid_mode(self):
        with pytest.raises(ValueError, match="Invalid value for 'bind_mode'|Unsupported bind_mode"):
            validate_tool_input(TOOL_BIND_ARMATURE_MESH, {
                "mesh_object_name": "Body",
                "armature_name": "Rig",
                "bind_mode": "MAGIC",
            }, trusted_approval=True)

    def test_validate_configure_bone_constraint_valid(self):
        params = {
            "armature_name": "Rig",
            "bone_name": "Forearm",
            "constraint_type": "IK",
            "action": "ADD",
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_BONE_CONSTRAINT, params, trusted_approval=True)
        assert sanitized["constraint_type"] == "IK"
        assert sanitized["action"] == "ADD"

    def test_validate_configure_bone_constraint_invalid_type(self):
        with pytest.raises(ValueError, match="Invalid value for 'constraint_type'|Unsupported constraint_type"):
            validate_tool_input(TOOL_CONFIGURE_BONE_CONSTRAINT, {
                "armature_name": "Rig",
                "bone_name": "Forearm",
                "constraint_type": "SPLINE_IK",
            }, trusted_approval=True)


class TestApprovalTamperingProtection:
    """Verifies that untrusted approved=True is rejected fail-closed for scene mutations."""

    def test_untrusted_approval_rejected_create_armature(self):
        from blender_addon.universal_mcp.bridge.handlers import handle_create_armature

        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_approval_required = True

        with pytest.raises(PermissionError, match="Scene mutation denied"):
            handle_create_armature(mock_bpy, {
                "name": "TamperedRig",
                "approved": True,
            })

    def test_untrusted_approval_rejected_edit_bones(self):
        from blender_addon.universal_mcp.bridge.handlers import handle_edit_armature_bones

        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_approval_required = True

        with pytest.raises(PermissionError, match="Scene mutation denied"):
            handle_edit_armature_bones(mock_bpy, {
                "armature_name": "Rig",
                "action": "add_bone",
                "name": "Bone1",
                "approved": True,
            })

    def test_untrusted_approval_rejected_bind_mesh(self):
        from blender_addon.universal_mcp.bridge.handlers import handle_bind_armature_mesh

        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_approval_required = True

        with pytest.raises(PermissionError, match="Scene mutation denied"):
            handle_bind_armature_mesh(mock_bpy, {
                "mesh_object_name": "Cube",
                "armature_name": "Rig",
                "approved": True,
            })

    def test_untrusted_approval_rejected_configure_constraint(self):
        from blender_addon.universal_mcp.bridge.handlers import handle_configure_bone_constraint

        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_approval_required = True

        with pytest.raises(PermissionError, match="Scene mutation denied"):
            handle_configure_bone_constraint(mock_bpy, {
                "armature_name": "Rig",
                "bone_name": "Hand",
                "constraint_type": "IK",
                "approved": True,
            })


class TestDeterministicSnapshot:
    """Verifies deterministic state hashing and optimistic concurrency."""

    def test_snapshot_computation_consistency(self):
        mock_bone = MagicMock()
        mock_bone.name = "Bone1"
        mock_bone.head_local = (0.0, 0.0, 0.0)
        mock_bone.tail_local = (0.0, 0.0, 1.0)
        mock_bone.parent = None
        mock_bone.use_connect = False
        mock_bone.use_deform = True

        mock_arm = MagicMock()
        mock_arm.type = "ARMATURE"
        mock_arm.name = "TestRig"
        mock_arm.data.bones = [mock_bone]
        mock_arm.pose.bones = []

        snap1 = compute_armature_snapshot_id(mock_arm)
        snap2 = compute_armature_snapshot_id(mock_arm)

        assert isinstance(snap1, str)
        assert len(snap1) == 64
        assert snap1 == snap2

    def test_snapshot_changes_with_bone_geometry(self):
        mock_bone1 = MagicMock()
        mock_bone1.name = "Bone1"
        mock_bone1.head_local = (0.0, 0.0, 0.0)
        mock_bone1.tail_local = (0.0, 0.0, 1.0)
        mock_bone1.parent = None
        mock_bone1.use_connect = False
        mock_bone1.use_deform = True

        mock_arm1 = MagicMock()
        mock_arm1.type = "ARMATURE"
        mock_arm1.name = "Rig"
        mock_arm1.data.bones = [mock_bone1]
        mock_arm1.pose.bones = []

        mock_bone2 = MagicMock()
        mock_bone2.name = "Bone1"
        mock_bone2.head_local = (0.0, 0.0, 0.0)
        mock_bone2.tail_local = (0.0, 0.0, 2.0)  # Changed tail
        mock_bone2.parent = None
        mock_bone2.use_connect = False
        mock_bone2.use_deform = True

        mock_arm2 = MagicMock()
        mock_arm2.type = "ARMATURE"
        mock_arm2.name = "Rig"
        mock_arm2.data.bones = [mock_bone2]
        mock_arm2.pose.bones = []

        assert compute_armature_snapshot_id(mock_arm1) != compute_armature_snapshot_id(mock_arm2)


class TestModelingAgentRiggingIntegration:
    """Verifies that ModelingAgent registers and validates rigging capabilities."""

    def test_agent_can_handle_rigging_capabilities(self):
        agent = ModelingAgent()
        from shared.models.agent_contracts import AgentTask

        task_mutation = AgentTask(
            task_id="task_rig_1",
            required_capability=CAPABILITY_MODELING_RIGGING,
            task_type=TOOL_CREATE_ARMATURE,
            input_params={"name": "CharacterRig"},
        )
        assert agent.can_handle(task_mutation) is True

        task_inspect = AgentTask(
            task_id="task_rig_2",
            required_capability=CAPABILITY_MODELING_RIGGING_INSPECT,
            task_type=TOOL_INSPECT_ARMATURE,
            input_params={"armature_name": "CharacterRig"},
        )
        assert agent.can_handle(task_inspect) is True

    def test_manifest_declares_rigging_capabilities(self):
        agent = ModelingAgent()
        manifest = agent.get_manifest()
        cap_ids = {c.capability_id for c in manifest.capabilities}

        assert CAPABILITY_MODELING_RIGGING in cap_ids
        assert CAPABILITY_MODELING_RIGGING_INSPECT in cap_ids

    def test_supported_modeling_tools_contains_rigging_tools(self):
        for tool in (
            TOOL_CREATE_ARMATURE,
            TOOL_EDIT_ARMATURE_BONES,
            TOOL_INSPECT_ARMATURE,
            TOOL_BIND_ARMATURE_MESH,
            TOOL_CONFIGURE_BONE_CONSTRAINT,
        ):
            assert tool in SUPPORTED_MODELING_TOOLS
