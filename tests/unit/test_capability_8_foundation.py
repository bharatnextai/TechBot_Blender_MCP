"""
Unit Tests for Capability 8: Architecture and Environments Foundation.
Verifies schemas, parameter validation, fail-closed approval enforcement,
agent registry, and Director brief delegation.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.schemas.tool_schemas import (
    TOOL_CREATE_CYCLORAMA,
    TOOL_SET_OBJECT_ORIGIN,
    TOOL_CREATE_ROOM_ENCLOSURE,
    TOOL_CREATE_ROOF_STRUCTURE,
    TOOL_CREATE_BUILDING_ENVELOPE,
    TOOL_CREATE_TERRAIN,
    TOOL_SCATTER_SURFACE_ASSETS,
    TOOL_SNAP_TO_GROUND,
    TOOL_ALIGN_OBJECT_GRID,
    TOOL_BEGIN_ENVIRONMENT_TRANSACTION,
    TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION,
    TOOL_COMMIT_ENVIRONMENT_TRANSACTION,
    TOOL_EXECUTE_ENVIRONMENT_WORKFLOW,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from mcp_service.agents.registry import create_default_registry
from mcp_service.agents.environment import (
    EnvironmentAgent,
    ENVIRONMENT_AGENT_ID,
    CAPABILITY_ENVIRONMENT_STAGING,
    CAPABILITY_ENVIRONMENT_ARCHITECTURE,
    CAPABILITY_ENVIRONMENT_TERRAIN,
    CAPABILITY_ENVIRONMENT_LAYOUT,
)
from mcp_service.agents.director import DirectorAgent
from shared.models.agent_contracts import AgentTask, TaskStatus


class TestCapability8Schemas:
    """Tests schema discovery, registration, and parameter sanitization."""

    def test_tool_registry_discovery(self):
        reg = ToolRegistry()
        expected_tools = [
            TOOL_CREATE_CYCLORAMA,
            TOOL_SET_OBJECT_ORIGIN,
            TOOL_CREATE_ROOM_ENCLOSURE,
            TOOL_CREATE_ROOF_STRUCTURE,
            TOOL_CREATE_BUILDING_ENVELOPE,
            TOOL_CREATE_TERRAIN,
            TOOL_SCATTER_SURFACE_ASSETS,
            TOOL_SNAP_TO_GROUND,
            TOOL_ALIGN_OBJECT_GRID,
            TOOL_BEGIN_ENVIRONMENT_TRANSACTION,
            TOOL_ROLLBACK_ENVIRONMENT_TRANSACTION,
            TOOL_COMMIT_ENVIRONMENT_TRANSACTION,
            TOOL_EXECUTE_ENVIRONMENT_WORKFLOW,
        ]
        for t in expected_tools:
            assert reg.has_tool(t), f"Tool {t} not found in ToolRegistry."
            defn = reg.get_tool_definition(t)
            assert defn is not None
            assert defn["permission_tier"] == "SCENE_MUTATION"
            assert "input_schema" in defn

    def test_create_cyclorama_validation_success(self):
        params = {
            "name": "HeroCyclorama",
            "width": 15.0,
            "depth": 12.0,
            "wall_height": 6.0,
            "cove_radius": 2.0,
            "cove_segments": 24,
        }
        sanitized = validate_tool_input(TOOL_CREATE_CYCLORAMA, params, trusted_approval=True)
        assert sanitized["name"] == "HeroCyclorama"
        assert sanitized["width"] == 15.0
        assert sanitized["cove_radius"] == 2.0
        assert sanitized["cove_segments"] == 24
        assert sanitized["trusted_approval"] is True

    def test_create_cyclorama_fail_closed_untrusted_approval(self):
        params = {"name": "TestCyc", "approved": True}
        with pytest.raises(PermissionError) as exc_info:
            validate_tool_input(TOOL_CREATE_CYCLORAMA, params, trusted_approval=False)
        assert "untrusted" in str(exc_info.value).lower()

    def test_set_object_origin_validation(self):
        params = {"object_name": "ProductHero", "origin_mode": "BOTTOM_CENTER"}
        sanitized = validate_tool_input(TOOL_SET_OBJECT_ORIGIN, params, trusted_approval=True)
        assert sanitized["object_name"] == "ProductHero"
        assert sanitized["origin_mode"] == "BOTTOM_CENTER"

    def test_create_room_enclosure_validation(self):
        params = {
            "name": "GallerySpace",
            "width": 10.0,
            "length": 12.0,
            "height": 4.0,
            "wall_thickness": 0.25,
            "include_floor": True,
            "include_ceiling": True,
            "door_wall": "SOUTH",
            "door_width": 1.2,
            "door_height": 2.4,
        }
        sanitized = validate_tool_input(TOOL_CREATE_ROOM_ENCLOSURE, params, trusted_approval=True)
        assert sanitized["name"] == "GallerySpace"
        assert sanitized["door_wall"] == "SOUTH"
        assert sanitized["include_ceiling"] is True

    def test_create_terrain_validation(self):
        params = {
            "name": "Highlands",
            "width": 100.0,
            "depth": 100.0,
            "resolution_x": 128,
            "resolution_y": 128,
            "elevation_scale": 12.0,
            "seed": 999,
        }
        sanitized = validate_tool_input(TOOL_CREATE_TERRAIN, params, trusted_approval=True)
        assert sanitized["name"] == "Highlands"
        assert sanitized["resolution_x"] == 128
        assert sanitized["seed"] == 999

    def test_scatter_surface_assets_validation(self):
        params = {
            "surface_name": "Highlands",
            "asset_names": ["PineTree", "Boulder"],
            "count": 50,
            "min_scale": 0.5,
            "max_scale": 1.5,
        }
        sanitized = validate_tool_input(TOOL_SCATTER_SURFACE_ASSETS, params, trusted_approval=True)
        assert sanitized["surface_name"] == "Highlands"
        assert sanitized["asset_names"] == ["PineTree", "Boulder"]
        assert sanitized["count"] == 50

    def test_snap_to_ground_validation(self):
        params = {"object_name": "PropAsset", "ground_name": "StudioFloor", "offset": 0.05}
        sanitized = validate_tool_input(TOOL_SNAP_TO_GROUND, params, trusted_approval=True)
        assert sanitized["object_name"] == "PropAsset"
        assert sanitized["ground_name"] == "StudioFloor"
        assert sanitized["offset"] == 0.05

    def test_align_object_grid_validation(self):
        params = {"object_name": "WallPanel", "grid_size": 2.0, "snap_axes": ["X", "Y"]}
        sanitized = validate_tool_input(TOOL_ALIGN_OBJECT_GRID, params, trusted_approval=True)
        assert sanitized["grid_size"] == 2.0
        assert sanitized["snap_axes"] == ["X", "Y"]

    def test_create_roof_structure_validation_success(self):
        params = {
            "name": "CustomGableRoof",
            "roof_type": "GABLE",
            "width": 10.0,
            "length": 14.0,
            "height": 3.0,
            "overhang": 0.5,
            "thickness": 0.25,
            "base_elevation": 4.0,
            "solid": True,
        }
        sanitized = validate_tool_input(TOOL_CREATE_ROOF_STRUCTURE, params, trusted_approval=True)
        assert sanitized["name"] == "CustomGableRoof"
        assert sanitized["roof_type"] == "GABLE"
        assert sanitized["width"] == 10.0
        assert sanitized["height"] == 3.0
        assert sanitized["overhang"] == 0.5
        assert sanitized["solid"] is True

    def test_create_roof_structure_fail_closed_untrusted_approval(self):
        params = {"name": "BadRoof", "approved": True}
        with pytest.raises(PermissionError) as exc_info:
            validate_tool_input(TOOL_CREATE_ROOF_STRUCTURE, params, trusted_approval=False)
        assert "untrusted" in str(exc_info.value).lower()

    def test_create_building_envelope_validation_success(self):
        params = {
            "name": "CommercialOffice",
            "width": 12.0,
            "length": 16.0,
            "height": 7.0,
            "stories": 2,
            "roof_type": "HIP",
            "roof_height": 3.0,
            "door_wall": "SOUTH",
        }
        sanitized = validate_tool_input(TOOL_CREATE_BUILDING_ENVELOPE, params, trusted_approval=True)
        assert sanitized["name"] == "CommercialOffice"
        assert sanitized["stories"] == 2
        assert sanitized["roof_type"] == "HIP"
        assert sanitized["door_wall"] == "SOUTH"

    def test_create_building_envelope_fail_closed_untrusted_approval(self):
        params = {"name": "BadBuilding", "approved": True}
        with pytest.raises(PermissionError) as exc_info:
            validate_tool_input(TOOL_CREATE_BUILDING_ENVELOPE, params, trusted_approval=False)
        assert "untrusted" in str(exc_info.value).lower()

    def test_transaction_tools_validation_and_fail_closed(self):
        # Transaction begin
        p_begin = {"context_name": "TestTx"}
        s_begin = validate_tool_input(TOOL_BEGIN_ENVIRONMENT_TRANSACTION, p_begin, trusted_approval=True)
        assert s_begin["context_name"] == "TestTx"

        # Workflow execution
        p_wf = {
            "workflow_name": "MultiStepStaging",
            "steps": [
                {"tool": "create_room_enclosure", "params": {"name": "Room1"}},
                {"tool": "create_roof_structure", "params": {"name": "Roof1"}},
            ],
        }
        s_wf = validate_tool_input(TOOL_EXECUTE_ENVIRONMENT_WORKFLOW, p_wf, trusted_approval=True)
        assert len(s_wf["steps"]) == 2

        # Untrusted approval rejection
        with pytest.raises(PermissionError):
            validate_tool_input(
                TOOL_EXECUTE_ENVIRONMENT_WORKFLOW,
                {"steps": [{"tool": "create_cyclorama", "params": {"name": "Cyc"}}], "approved": True},
                trusted_approval=False,
            )


class TestEnvironmentAgentAndRegistry:
    """Tests the EnvironmentAgent manifest, capabilities, and task validation."""

    def test_agent_registration(self):
        registry = create_default_registry()
        env_manifest = registry.get_agent(ENVIRONMENT_AGENT_ID)
        assert env_manifest is not None
        assert env_manifest.agent_id == ENVIRONMENT_AGENT_ID
        assert env_manifest.enabled is True

        cap_ids = [c.capability_id for c in env_manifest.capabilities]
        assert CAPABILITY_ENVIRONMENT_STAGING in cap_ids
        assert CAPABILITY_ENVIRONMENT_ARCHITECTURE in cap_ids
        assert CAPABILITY_ENVIRONMENT_TERRAIN in cap_ids
        assert CAPABILITY_ENVIRONMENT_LAYOUT in cap_ids

    def test_environment_agent_can_handle(self):
        agent = EnvironmentAgent()
        task_staging = AgentTask(
            task_id="t1",
            required_capability=CAPABILITY_ENVIRONMENT_STAGING,
            task_type=TOOL_CREATE_CYCLORAMA,
            input_params={"name": "StudioCyc"},
        )
        assert agent.can_handle(task_staging) is True

        task_unsupported = AgentTask(
            task_id="t2",
            required_capability="unsupported.cap",
            task_type="unsupported_tool",
            input_params={},
        )
        assert agent.can_handle(task_unsupported) is False

    def test_environment_agent_input_validation(self):
        agent = EnvironmentAgent()
        # Valid input
        valid, err_code, err_msg = agent.validate_task_input(
            TOOL_CREATE_CYCLORAMA, {"name": "GoodCyc", "width": 10.0}
        )
        assert valid is True
        assert err_code is None

        # Invalid input (empty name)
        valid, err_code, err_msg = agent.validate_task_input(
            TOOL_CREATE_CYCLORAMA, {"name": "", "width": 10.0}
        )
        assert valid is False
        assert err_code == "INVALID_PARAMS"

    def test_environment_agent_roof_and_building_validation(self):
        agent = EnvironmentAgent()
        # Roof valid
        valid, err_code, err_msg = agent.validate_task_input(
            TOOL_CREATE_ROOF_STRUCTURE, {"name": "GableRoof", "roof_type": "GABLE", "width": 8.0}
        )
        assert valid is True

        # Roof invalid type
        valid, err_code, err_msg = agent.validate_task_input(
            TOOL_CREATE_ROOF_STRUCTURE, {"name": "BadRoof", "roof_type": "UNKNOWN"}
        )
        assert valid is False
        assert err_code == "INVALID_PARAMS"

        # Building valid
        valid, err_code, err_msg = agent.validate_task_input(
            TOOL_CREATE_BUILDING_ENVELOPE, {"name": "HQ", "stories": 3, "roof_type": "HIP"}
        )
        assert valid is True

        # Building invalid stories
        valid, err_code, err_msg = agent.validate_task_input(
            TOOL_CREATE_BUILDING_ENVELOPE, {"name": "HQ", "stories": 0}
        )
        assert valid is False
        assert err_code == "INVALID_PARAMS"

    def test_environment_agent_workflow_execution_atomic(self):
        import asyncio
        from unittest.mock import AsyncMock
        from shared.models.protocol_models import BridgeResponse

        async def _run():
            agent = EnvironmentAgent()
            mock_executor = AsyncMock()

            # Success response
            mock_executor.execute.return_value = BridgeResponse(
                status="SUCCESS",
                result={"steps_executed": 2, "workflow_name": "TestStaging"},
            )

            tasks = [
                AgentTask(task_id="t1", required_capability=CAPABILITY_ENVIRONMENT_ARCHITECTURE, task_type=TOOL_CREATE_ROOM_ENCLOSURE, input_params={"name": "RoomA"}),
                AgentTask(task_id="t2", required_capability=CAPABILITY_ENVIRONMENT_ARCHITECTURE, task_type=TOOL_CREATE_ROOF_STRUCTURE, input_params={"name": "RoofA"}),
            ]

            res = await agent.execute_workflow(tasks, mock_executor, trusted_approval=True)
            assert res.status == TaskStatus.SUCCEEDED or res.is_success
            assert res.output["steps_executed"] == 2
            assert res.verification.verified is True

            # Failure / Rollback response from executor
            mock_executor.execute.return_value = BridgeResponse(
                status="FAILED",
                message="Step 1 failed, rolled back",
                result={"failed_step_index": 1, "rollback_report": {"removed_objects": ["RoomA"]}},
            )

            res_fail = await agent.execute_workflow(tasks, mock_executor, trusted_approval=True)
            assert res_fail.status == TaskStatus.FAILED
            assert res_fail.output["failed_step_index"] == 1
            assert "RoomA" in res_fail.output["rollback_report"]["removed_objects"]

        asyncio.run(_run())


class TestDirectorBriefDelegation:
    """Tests Director brief decomposition to EnvironmentAgent."""

    def test_director_delegates_cyclorama(self):
        director = DirectorAgent()
        contract = director.decompose_brief("Construct a studio cyclorama for a new product visualization")
        assert ENVIRONMENT_AGENT_ID in contract.domain_tasks
        tasks = contract.domain_tasks[ENVIRONMENT_AGENT_ID]
        assert any(t.task_type == TOOL_CREATE_CYCLORAMA for t in tasks)

    def test_director_delegates_interior_room(self):
        director = DirectorAgent()
        contract = director.decompose_brief("Build an interior room enclosure with architectural walls and floor")
        assert ENVIRONMENT_AGENT_ID in contract.domain_tasks
        tasks = contract.domain_tasks[ENVIRONMENT_AGENT_ID]
        assert any(t.task_type == TOOL_CREATE_ROOM_ENCLOSURE for t in tasks)

    def test_director_delegates_landscape_terrain(self):
        director = DirectorAgent()
        contract = director.decompose_brief("Generate a procedural landscape terrain with natural elevation")
        assert ENVIRONMENT_AGENT_ID in contract.domain_tasks
        tasks = contract.domain_tasks[ENVIRONMENT_AGENT_ID]
        assert any(t.task_type == TOOL_CREATE_TERRAIN for t in tasks)
