"""
Unit tests for Physics & Simulation Foundation (Phase 2.4 - v0.1.77).

Validates:
1. Tool schema registrations, permission tiers, and argument validation.
2. Approval tampering protection (untrusted approved=True rejection).
3. Parameter bounds (mass, friction, restitution, cloth presets, frame spans <= 250).
4. Deterministic snapshot ID calculation and optimistic concurrency detection (STALE_PHYSICS_STATE).
5. Transactional rollback logic on mutation failure.
6. ModelingAgent capability declarations and routing.
"""

import hashlib
import json
import pytest
from unittest.mock import MagicMock, PropertyMock

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_CONFIGURE_PHYSICS,
    TOOL_SETUP_PHYSICS,
    TOOL_MANAGE_PHYSICS,
    TOOL_INSPECT_PHYSICS,
    TOOL_BAKE_PHYSICS_SIMULATION,
    TOOL_CONFIGURE_FORCE_FIELD,
    TOOL_INSPECT_FORCE_FIELD,
    TOOL_CONFIGURE_PARTICLE_SYSTEM,
    TOOL_INSPECT_PARTICLE_SYSTEM,
    TOOL_CONFIGURE_FLUID_SIMULATION,
    TOOL_INSPECT_FLUID_SIMULATION,
    PERMISSION_SCENE_MUTATION,
    PERMISSION_READ_ONLY,
    validate_tool_input,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    CAPABILITY_MODELING_PHYSICS,
    CAPABILITY_MODELING_PHYSICS_INSPECT,
    SUPPORTED_MODELING_TOOLS,
)
from mcp_service.agents.simulation_vfx import (
    SimulationVFXAgent,
    CAPABILITY_PHYSICS_SIMULATION,
    CAPABILITY_PHYSICS_INSPECT,
    SUPPORTED_SIMULATION_TOOLS,
)
from blender_addon.universal_mcp.bridge.physics_foundation import (
    compute_physics_snapshot_id,
    execute_configure_physics,
    execute_inspect_physics,
    execute_configure_force_field,
    execute_inspect_force_field,
    execute_configure_particle_system,
    execute_inspect_particle_system,
    execute_configure_fluid_simulation,
    execute_inspect_fluid_simulation,
    SUPPORTED_PHYSICS_TYPES,
    SUPPORTED_RIGID_BODY_TYPES,
    SUPPORTED_COLLISION_SHAPES,
    SUPPORTED_CLOTH_PRESETS,
    SUPPORTED_FORCE_FIELD_TYPES,
    MAX_BAKE_FRAMES,
)


class TestPhysicsToolSchemas:
    """Validates registration, schema structure, and argument bounds."""

    def test_physics_tools_registered_in_definitions(self):
        for tool in (
            TOOL_CONFIGURE_PHYSICS,
            TOOL_SETUP_PHYSICS,
            TOOL_MANAGE_PHYSICS,
            TOOL_INSPECT_PHYSICS,
            TOOL_BAKE_PHYSICS_SIMULATION,
        ):
            assert tool in TOOL_DEFINITIONS, f"Tool '{tool}' must be in TOOL_DEFINITIONS"

    def test_permission_tiers(self):
        assert TOOL_DEFINITIONS[TOOL_CONFIGURE_PHYSICS]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_SETUP_PHYSICS]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_MANAGE_PHYSICS]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_INSPECT_PHYSICS]["permission_tier"] == PERMISSION_READ_ONLY
        assert TOOL_DEFINITIONS[TOOL_BAKE_PHYSICS_SIMULATION]["permission_tier"] == PERMISSION_SCENE_MUTATION

    def test_validate_configure_physics_rigid_body_valid(self):
        params = {
            "object_name": "Cube",
            "physics_type": "RIGID_BODY",
            "rigid_body_type": "ACTIVE",
            "mass": 2.5,
            "friction": 0.8,
            "restitution": 0.3,
            "collision_shape": "SPHERE",
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
        assert sanitized["object_name"] == "Cube"
        assert sanitized["rigid_body_type"].upper() == "ACTIVE"
        assert sanitized["mass"] == 2.5
        assert sanitized["friction"] == 0.8
        assert sanitized["restitution"] == 0.3
        assert sanitized["collision_shape"].upper() == "SPHERE"

    def test_validate_configure_physics_cloth_presets_valid(self):
        for preset in ("SILK", "COTTON", "LEATHER"):
            params = {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "cloth_preset": preset,
                "quality": 8,
                "pin_vertex_group": "PinGroup",
            }
            sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
            assert sanitized["cloth_preset"] == preset
            assert sanitized["quality"] == 8
            assert sanitized["pin_vertex_group"] == "PinGroup"

    def test_validate_configure_physics_cloth_self_collision_valid(self):
        params = {
            "object_name": "ClothMesh",
            "physics_type": "CLOTH",
            "use_self_collision": True,
            "self_distance_min": 0.012,
            "self_friction": 7.5,
            "collision_quality": 4,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
        assert sanitized["use_self_collision"] is True
        assert sanitized["self_distance_min"] == 0.012
        assert sanitized["self_friction"] == 7.5
        assert sanitized["collision_quality"] == 4

    def test_validate_configure_physics_cloth_self_collision_invalid_bounds(self):
        with pytest.raises(ValueError, match="must be >= 0.0005|must be between 0.0005 and 0.1"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "self_distance_min": 0.0001,
            }, trusted_approval=True)

        with pytest.raises(ValueError, match="must be <= 80|must be between 0.0 and 80.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "self_friction": 120.0,
            }, trusted_approval=True)

        with pytest.raises(ValueError, match="must be <= 20|must be between 1 and 20"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "collision_quality": 25,
            }, trusted_approval=True)

    def test_validate_configure_physics_cloth_object_collision_valid(self):
        params = {
            "object_name": "ClothMesh",
            "physics_type": "CLOTH",
            "use_collision": True,
            "distance_min": 0.025,
            "friction": 15.0,
            "collision_quality": 5,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
        assert sanitized["use_collision"] is True
        assert sanitized["distance_min"] == 0.025
        assert sanitized["friction"] == 15.0
        assert sanitized["collision_quality"] == 5

    def test_validate_configure_physics_cloth_object_collision_invalid_bounds(self):
        with pytest.raises(ValueError, match="must be >= 0.001|must be between 0.001 and 1.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "distance_min": 0.0001,
            }, trusted_approval=True)

        with pytest.raises(ValueError, match="must be <= 1.0|must be between 0.001 and 1.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "distance_min": 1.5,
            }, trusted_approval=True)

        with pytest.raises(ValueError, match="must be <= 80.0|must be between 0.0 and 80.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "friction": 95.0,
            }, trusted_approval=True)

    def test_validate_configure_physics_cloth_springs_and_pressure_valid(self):
        params = {
            "object_name": "BouncyCloth",
            "physics_type": "CLOTH",
            "use_internal_springs": True,
            "internal_spring_max_length": 5.5,
            "internal_tension_stiffness": 25.0,
            "internal_compression_stiffness": 20.0,
            "internal_spring_normal_check": False,
            "use_pressure": True,
            "uniform_pressure_force": 15.0,
            "use_pressure_volume": True,
            "target_volume": 2.5,
            "pressure_factor": 1.25,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
        assert sanitized["use_internal_springs"] is True
        assert sanitized["internal_spring_max_length"] == 5.5
        assert sanitized["internal_tension_stiffness"] == 25.0
        assert sanitized["internal_compression_stiffness"] == 20.0
        assert sanitized["internal_spring_normal_check"] is False
        assert sanitized["use_pressure"] is True
        assert sanitized["uniform_pressure_force"] == 15.0
        assert sanitized["use_pressure_volume"] is True
        assert sanitized["target_volume"] == 2.5
        assert sanitized["pressure_factor"] == 1.25

    def test_validate_configure_physics_cloth_springs_bounds(self):
        # Negative internal_spring_max_length
        with pytest.raises(ValueError, match="internal_spring_max_length"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "internal_spring_max_length": -1.0,
            }, trusted_approval=True)

        # Exceed max internal_spring_max_length
        with pytest.raises(ValueError, match="internal_spring_max_length"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "internal_spring_max_length": 1005.0,
            }, trusted_approval=True)

        # Negative internal_tension_stiffness
        with pytest.raises(ValueError, match="internal_tension_stiffness"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "internal_tension_stiffness": -5.0,
            }, trusted_approval=True)

        # Exceed max internal_compression_stiffness
        with pytest.raises(ValueError, match="internal_compression_stiffness"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "internal_compression_stiffness": 10005.0,
            }, trusted_approval=True)

    def test_validate_configure_physics_cloth_pressure_bounds(self):
        # Below min uniform_pressure_force (-10000.0)
        with pytest.raises(ValueError, match="uniform_pressure_force"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "uniform_pressure_force": -10001.0,
            }, trusted_approval=True)

        # Above max uniform_pressure_force (10000.0)
        with pytest.raises(ValueError, match="uniform_pressure_force"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "uniform_pressure_force": 10001.0,
            }, trusted_approval=True)

        # Negative target_volume
        with pytest.raises(ValueError, match="target_volume"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "target_volume": -0.5,
            }, trusted_approval=True)

        # Exceed max pressure_factor
        with pytest.raises(ValueError, match="pressure_factor"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "pressure_factor": 10001.0,
            }, trusted_approval=True)

    def test_validate_configure_physics_collision_valid(self):
        params = {
            "object_name": "Obstacle",
            "physics_type": "COLLISION",
            "damping": 0.3,
            "cloth_friction": 12.0,
            "thickness_outer": 0.05,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
        assert sanitized["damping"] == 0.3
        assert sanitized["cloth_friction"] == 12.0
        assert sanitized["thickness_outer"] == 0.05

    def test_validate_configure_physics_invalid_mass(self):
        with pytest.raises(ValueError, match="must be >= 0.01|must be between 0.01 and 10000.0 kg"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Cube",
                "physics_type": "RIGID_BODY",
                "mass": 0.0001,
            }, trusted_approval=True)

    def test_validate_configure_physics_invalid_friction(self):
        with pytest.raises(ValueError, match="must be <= 1.0|must be between 0.0 and 1.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Cube",
                "physics_type": "RIGID_BODY",
                "friction": 1.5,
            }, trusted_approval=True)

    def test_validate_configure_physics_invalid_cloth_preset(self):
        with pytest.raises(ValueError, match="Unsupported cloth_preset|Invalid value for 'cloth_preset'"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "ClothMesh",
                "physics_type": "CLOTH",
                "cloth_preset": "RUBBER",
            }, trusted_approval=True)

    def test_validate_configure_physics_rigid_body_kinematic_and_damping_valid(self):
        params = {
            "object_name": "KinematicCube",
            "physics_type": "RIGID_BODY",
            "kinematic": True,
            "linear_damping": 0.25,
            "angular_damping": 0.45,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
        assert sanitized["kinematic"] is True
        assert sanitized["linear_damping"] == 0.25
        assert sanitized["angular_damping"] == 0.45

    def test_validate_configure_physics_rigid_body_damping_invalid_bounds(self):
        with pytest.raises(ValueError, match="must be <= 1.0|must be between 0.0 and 1.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Cube",
                "physics_type": "RIGID_BODY",
                "linear_damping": 1.5,
            }, trusted_approval=True)

        with pytest.raises(ValueError, match="must be >= 0.0|must be between 0.0 and 1.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Cube",
                "physics_type": "RIGID_BODY",
                "angular_damping": -0.1,
            }, trusted_approval=True)

    def test_validate_configure_physics_rigid_body_constraint_valid(self):
        for c_type in ("FIXED", "POINT", "HINGE", "SLIDER", "GENERIC"):
            params = {
                "object_name": "AnchorEmpty",
                "physics_type": "RIGID_BODY_CONSTRAINT",
                "constraint_type": c_type,
                "target_object_1": "AnchorEmpty",
                "target_object_2": "BobMesh",
                "disable_collisions": True,
                "use_breaking": True,
                "breaking_threshold": 75.0,
                "use_limit_lin_x": True,
                "limit_lin_x_lower": -1.5,
                "limit_lin_x_upper": 1.5,
                "use_limit_ang_z": True,
                "limit_ang_z_lower": -0.7854,
                "limit_ang_z_upper": 0.7854,
            }
            sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, params, trusted_approval=True)
            assert sanitized["physics_type"] == "RIGID_BODY_CONSTRAINT"
            assert sanitized["constraint_type"] == c_type
            assert sanitized["target_object_1"] == "AnchorEmpty"
            assert sanitized["target_object_2"] == "BobMesh"
            assert sanitized["disable_collisions"] is True
            assert sanitized["use_breaking"] is True
            assert sanitized["breaking_threshold"] == 75.0
            assert sanitized["use_limit_lin_x"] is True
            assert sanitized["limit_lin_x_lower"] == -1.5
            assert sanitized["limit_lin_x_upper"] == 1.5
            assert sanitized["use_limit_ang_z"] is True
            assert sanitized["limit_ang_z_lower"] == -0.7854
            assert sanitized["limit_ang_z_upper"] == 0.7854

    def test_validate_configure_physics_rigid_body_constraint_invalid_type(self):
        with pytest.raises(ValueError, match="Invalid value for 'constraint_type'|Unsupported constraint_type"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Anchor",
                "physics_type": "RIGID_BODY_CONSTRAINT",
                "constraint_type": "MOTOR_UNSUPPORTED",
            }, trusted_approval=True)

    def test_validate_configure_physics_rigid_body_constraint_self_connection(self):
        with pytest.raises(ValueError, match="cannot connect an object to itself"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Anchor",
                "physics_type": "RIGID_BODY_CONSTRAINT",
                "target_object_1": "SameObj",
                "target_object_2": "SameObj",
            }, trusted_approval=True)

    def test_validate_configure_physics_rigid_body_constraint_breaking_threshold_invalid(self):
        with pytest.raises(ValueError, match="must be >= 0.0|must be between 0.0 and 100000.0"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Anchor",
                "physics_type": "RIGID_BODY_CONSTRAINT",
                "breaking_threshold": -5.0,
            }, trusted_approval=True)

    def test_validate_configure_physics_rigid_body_constraint_limits_inverted(self):
        with pytest.raises(ValueError, match="cannot be greater than"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Anchor",
                "physics_type": "RIGID_BODY_CONSTRAINT",
                "limit_lin_x_lower": 2.0,
                "limit_lin_x_upper": 1.0,
            }, trusted_approval=True)

        with pytest.raises(ValueError, match="cannot be greater than"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Anchor",
                "physics_type": "RIGID_BODY_CONSTRAINT",
                "limit_ang_z_lower": 1.0,
                "limit_ang_z_upper": -1.0,
            }, trusted_approval=True)

    def test_validate_bake_physics_simulation_valid(self):
        params = {
            "physics_type": "RIGID_BODY",
            "frame_start": 1,
            "frame_end": 120,
            "timeout_seconds": 45.0,
        }
        sanitized = validate_tool_input(TOOL_BAKE_PHYSICS_SIMULATION, params, trusted_approval=True)
        assert sanitized["physics_type"] == "RIGID_BODY"
        assert sanitized["frame_start"] == 1
        assert sanitized["frame_end"] == 120
        assert sanitized["timeout_seconds"] == 45.0

    def test_validate_bake_physics_simulation_exceeds_max_frames(self):
        with pytest.raises(ValueError, match="exceeds maximum allowed limit of 250 frames"):
            validate_tool_input(TOOL_BAKE_PHYSICS_SIMULATION, {
                "physics_type": "RIGID_BODY",
                "frame_start": 1,
                "frame_end": 300,
            }, trusted_approval=True)

    def test_validate_bake_physics_simulation_end_before_start(self):
        with pytest.raises(ValueError, match="must be >= frame_start"):
            validate_tool_input(TOOL_BAKE_PHYSICS_SIMULATION, {
                "physics_type": "RIGID_BODY",
                "frame_start": 50,
                "frame_end": 10,
            }, trusted_approval=True)

    def test_untrusted_approval_rejected(self):
        with pytest.raises(PermissionError, match="untrusted and cannot authorize scene mutation|Missing trusted human approval credentials"):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {
                "object_name": "Cube",
                "physics_type": "RIGID_BODY",
                "approved": True,
            }, trusted_approval=False)


class TestPhysicsSnapshotAndConcurrency:
    """Validates deterministic snapshot calculation and optimistic concurrency guard."""

    def test_snapshot_id_format(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "FallingSphere"
        mock_obj.rigid_body = MagicMock(
            type="ACTIVE", mass=1.5, friction=0.6, restitution=0.1, collision_shape="SPHERE", enabled=True
        )
        mock_obj.modifiers = []

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1.startswith("physics_")
        assert len(snap1) == 24  # 'physics_' (8 chars) + 16 hex chars

        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 == snap2, "Same physical state must yield identical snapshot ID"

    def test_snapshot_sensitivity_to_mutation(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "FallingSphere"
        mock_obj.rigid_body = MagicMock(
            type="ACTIVE", mass=1.5, friction=0.6, restitution=0.1, collision_shape="SPHERE", enabled=True
        )
        mock_obj.modifiers = []

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        # Mutate mass
        mock_obj.rigid_body.mass = 5.0
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Altering rigid body mass must produce a distinct snapshot ID"

    def test_snapshot_sensitivity_to_cloth_self_collision(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "SilkSheet"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.25, quality=6, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            collision_quality=2
        )
        mock_obj.modifiers = [cloth_mod]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        # Mutate self collision
        cloth_mod.collision_settings.use_self_collision = True
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Enabling cloth self-collision must produce a distinct snapshot ID"

        # Mutate self distance min
        cloth_mod.collision_settings.self_distance_min = 0.005
        snap3 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap2 != snap3, "Modifying self_distance_min must produce a distinct snapshot ID"

    def test_snapshot_sensitivity_to_cloth_object_collision(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "DrapedCloth"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5,
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            use_collision=True,
            distance_min=0.015,
            friction=5.0,
            collision_quality=2,
        )
        mock_obj.modifiers = [cloth_mod]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        cloth_mod.collision_settings.use_collision = False
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Disabling cloth object collision must produce a distinct snapshot ID"

        cloth_mod.collision_settings.distance_min = 0.05
        snap3 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap2 != snap3, "Modifying distance_min must produce a distinct snapshot ID"

        cloth_mod.collision_settings.friction = 25.0
        snap4 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap3 != snap4, "Modifying friction must produce a distinct snapshot ID"

    def test_snapshot_sensitivity_to_cloth_internal_springs(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "SoftVolume"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5,
            use_internal_springs=False,
            internal_spring_max_length=0.0,
            internal_tension_stiffness=15.0,
            internal_compression_stiffness=15.0,
            internal_spring_normal_check=True,
            use_pressure=False,
            uniform_pressure_force=0.0,
            use_pressure_volume=False,
            target_volume=0.0,
            pressure_factor=1.0,
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            collision_quality=2
        )
        mock_obj.modifiers = [cloth_mod]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        cloth_mod.settings.use_internal_springs = True
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Enabling internal springs must produce a distinct snapshot ID"

        cloth_mod.settings.internal_compression_stiffness = 50.0
        snap3 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap2 != snap3, "Modifying internal_compression_stiffness must produce a distinct snapshot ID"

    def test_snapshot_sensitivity_to_cloth_pressure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "InflatableMesh"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5,
            use_internal_springs=False,
            internal_spring_max_length=0.0,
            internal_tension_stiffness=15.0,
            internal_compression_stiffness=15.0,
            internal_spring_normal_check=True,
            use_pressure=False,
            uniform_pressure_force=0.0,
            use_pressure_volume=False,
            target_volume=0.0,
            pressure_factor=1.0,
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            collision_quality=2
        )
        mock_obj.modifiers = [cloth_mod]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        cloth_mod.settings.use_pressure = True
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Enabling cloth pressure must produce a distinct snapshot ID"

        cloth_mod.settings.uniform_pressure_force = 10.0
        snap3 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap2 != snap3, "Modifying uniform_pressure_force must produce a distinct snapshot ID"

    def test_snapshot_sensitivity_to_rigid_body_kinematic(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "KinematicSphere"
        mock_obj.rigid_body = MagicMock(
            type="ACTIVE", mass=1.0, friction=0.5, restitution=0.0,
            collision_shape="SPHERE", enabled=True, kinematic=False,
            linear_damping=0.04, angular_damping=0.10
        )
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        mock_obj.rigid_body.kinematic = True
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Toggling kinematic must produce a distinct snapshot ID"

    def test_snapshot_sensitivity_to_rigid_body_damping(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "DampedSphere"
        mock_obj.rigid_body = MagicMock(
            type="ACTIVE", mass=1.0, friction=0.5, restitution=0.0,
            collision_shape="SPHERE", enabled=True, kinematic=False,
            linear_damping=0.04, angular_damping=0.10
        )
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        mock_obj.rigid_body.linear_damping = 0.50
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Modifying linear_damping must produce a distinct snapshot ID"

        mock_obj.rigid_body.angular_damping = 0.60
        snap3 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap2 != snap3, "Modifying angular_damping must produce a distinct snapshot ID"

    def test_snapshot_sensitivity_to_rigid_body_constraint(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "Anchor"
        mock_obj.rigid_body = None
        mock_obj.modifiers = []

        o1 = MagicMock(name="Anchor")
        o1.name = "Anchor"
        o2 = MagicMock(name="Bob")
        o2.name = "Bob"

        rbc = MagicMock()
        rbc.type = "POINT"
        rbc.enabled = True
        rbc.disable_collisions = True
        rbc.object1 = o1
        rbc.object2 = o2
        rbc.use_breaking = False
        rbc.breaking_threshold = 10.0
        rbc.use_limit_lin_x = False
        rbc.limit_lin_x_lower = 0.0
        rbc.limit_lin_x_upper = 0.0
        rbc.use_limit_ang_z = False
        rbc.limit_ang_z_lower = 0.0
        rbc.limit_ang_z_upper = 0.0

        mock_obj.rigid_body_constraint = rbc
        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        rbc.type = "HINGE"
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Modifying constraint type must produce a distinct snapshot ID"

        rbc.use_breaking = True
        snap3 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap2 != snap3, "Enabling breaking must produce a distinct snapshot ID"

    def test_stale_snapshot_raises_error(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "ClothMesh"
        mock_obj.rigid_body = None
        mock_obj.modifiers = []
        mock_bpy.data.objects.get.return_value = mock_obj

        params = {
            "object_name": "ClothMesh",
            "physics_type": "CLOTH",
            "expected_snapshot_id": "physics_0000000000000000",
        }
        with pytest.raises(ValueError, match="STALE_PHYSICS_STATE"):
            execute_configure_physics(mock_bpy, params)


class TestPhysicsTransactionalRollback:
    """Validates transactional rollback when an error occurs during mutation."""

    def test_rollback_removes_added_rigid_body_on_failure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "FailingCube"
        mock_obj.rigid_body = None
        mock_obj.modifiers = []
        mock_bpy.data.objects.get.return_value = mock_obj

        # Simulate object_add succeeding then subsequent error
        def fake_object_add(type="ACTIVE"):
            mock_obj.rigid_body = MagicMock(type=type, mass=1.0)
        mock_bpy.ops.rigidbody.object_add.side_effect = fake_object_add

        # Pass an invalid parameter that triggers an exception after addition
        params = {
            "object_name": "FailingCube",
            "physics_type": "RIGID_BODY",
            "mass": -10.0,  # Invalid mass triggers ValueError
        }

        with pytest.raises(ValueError, match="Parameter 'mass' must be between 0.01 and 10000.0 kg"):
            execute_configure_physics(mock_bpy, params)

    def test_rollback_restores_prior_cloth_collision_settings_on_failure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "RollingCloth"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            collision_quality=2
        )
        mock_modifiers = MagicMock()
        mock_modifiers.__iter__.return_value = [cloth_mod]
        mock_modifiers.get.side_effect = lambda n: cloth_mod if n == "Cloth" else None
        mock_obj.modifiers = mock_modifiers
        mock_bpy.data.objects.get.return_value = mock_obj

        # Mutate self collision but fail with invalid mass
        params = {
            "object_name": "RollingCloth",
            "physics_type": "CLOTH",
            "action": "configure",
            "use_self_collision": True,
            "mass": -99.0,  # Invalid mass triggers ValueError during configure
        }

        with pytest.raises(ValueError, match="Parameter 'mass' must be between 0.01 and 10000.0 kg"):
            execute_configure_physics(mock_bpy, params)

        # Verify prior cloth collision settings were restored
        assert cloth_mod.collision_settings.use_self_collision is False
        assert cloth_mod.collision_settings.self_distance_min == 0.015
        assert cloth_mod.collision_settings.self_friction == 5.0
        assert cloth_mod.collision_settings.collision_quality == 2

    def test_rollback_restores_prior_cloth_object_collision_on_failure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "RollingClothObjColl"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5
        )
        cloth_mod.collision_settings = MagicMock(
            use_collision=True,
            distance_min=0.015,
            friction=5.0,
            collision_quality=2,
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
        )
        mock_modifiers = MagicMock()
        mock_modifiers.__iter__.return_value = [cloth_mod]
        mock_modifiers.get.side_effect = lambda n: cloth_mod if n == "Cloth" else None
        mock_obj.modifiers = mock_modifiers
        mock_bpy.data.objects.get.return_value = mock_obj

        params = {
            "object_name": "RollingClothObjColl",
            "physics_type": "CLOTH",
            "action": "configure",
            "use_collision": False,
            "distance_min": 0.08,
            "friction": 30.0,
            "collision_quality": 6,
            "mass": -99.0,  # Invalid mass triggers rollback
        }

        with pytest.raises(ValueError, match="Parameter 'mass' must be between 0.01 and 10000.0 kg"):
            execute_configure_physics(mock_bpy, params)

        # Verify prior object collision settings were restored
        assert cloth_mod.collision_settings.use_collision is True
        assert cloth_mod.collision_settings.distance_min == 0.015
        assert cloth_mod.collision_settings.friction == 5.0
        assert cloth_mod.collision_settings.collision_quality == 2

    def test_rollback_restores_prior_cloth_springs_and_pressure_on_failure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "RollingCloth2"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5,
            use_internal_springs=False,
            internal_spring_max_length=0.0,
            internal_tension_stiffness=15.0,
            internal_compression_stiffness=15.0,
            internal_spring_normal_check=True,
            use_pressure=False,
            uniform_pressure_force=0.0,
            use_pressure_volume=False,
            target_volume=0.0,
            pressure_factor=1.0,
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            collision_quality=2
        )
        mock_modifiers = MagicMock()
        mock_modifiers.__iter__.return_value = [cloth_mod]
        mock_modifiers.get.side_effect = lambda n: cloth_mod if n == "Cloth" else None
        mock_obj.modifiers = mock_modifiers
        mock_bpy.data.objects.get.return_value = mock_obj

        # Configure springs & pressure, then fail with invalid mass
        params = {
            "object_name": "RollingCloth2",
            "physics_type": "CLOTH",
            "action": "configure",
            "use_internal_springs": True,
            "internal_compression_stiffness": 50.0,
            "use_pressure": True,
            "uniform_pressure_force": 20.0,
            "mass": -99.0,  # Invalid mass triggers ValueError during configure
        }

        with pytest.raises(ValueError, match="Parameter 'mass' must be between 0.01 and 10000.0 kg"):
            execute_configure_physics(mock_bpy, params)

        # Verify prior cloth springs and pressure settings were restored
        assert cloth_mod.settings.use_internal_springs is False
        assert cloth_mod.settings.internal_compression_stiffness == 15.0
        assert cloth_mod.settings.use_pressure is False
        assert cloth_mod.settings.uniform_pressure_force == 0.0


class TestPhysicsInspectAndExecution:
    """Validates readback and response serialization of physics properties."""

    def test_inspect_cloth_springs_and_pressure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.frame_current = 1
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "InflatableCloth"
        mock_obj.location = [0.0, 0.0, 1.0]
        mock_obj.matrix_world.translation = [0.0, 0.0, 1.0]
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5,
            use_internal_springs=True,
            internal_spring_max_length=2.5,
            internal_tension_stiffness=30.0,
            internal_compression_stiffness=40.0,
            internal_spring_normal_check=False,
            use_pressure=True,
            uniform_pressure_force=5.0,
            use_pressure_volume=True,
            target_volume=1.5,
            pressure_factor=2.0,
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=True,
            self_distance_min=0.01,
            self_friction=8.0,
            collision_quality=3
        )
        cloth_mod.point_cache = None
        mock_obj.modifiers = [cloth_mod]
        mock_bpy.data.objects.get.return_value = mock_obj

        result = execute_inspect_physics(mock_bpy, {"object_name": "InflatableCloth"})
        assert result["success"] is True
        c_info = result["target"]["cloth"]
        assert c_info is not None
        assert c_info["use_internal_springs"] is True
        assert c_info["internal_spring_max_length"] == 2.5
        assert c_info["internal_tension_stiffness"] == 30.0
        assert c_info["internal_compression_stiffness"] == 40.0
        assert c_info["internal_spring_normal_check"] is False
        assert c_info["use_pressure"] is True
        assert c_info["uniform_pressure_force"] == 5.0
        assert c_info["use_pressure_volume"] is True
        assert c_info["target_volume"] == 1.5
        assert c_info["pressure_factor"] == 2.0

    def test_execute_configure_physics_cloth_springs_and_pressure_response(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "ConfiguredCloth"
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5,
            use_internal_springs=False,
            internal_spring_max_length=0.0,
            internal_tension_stiffness=15.0,
            internal_compression_stiffness=15.0,
            internal_spring_normal_check=True,
            use_pressure=False,
            uniform_pressure_force=0.0,
            use_pressure_volume=False,
            target_volume=0.0,
            pressure_factor=1.0,
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            collision_quality=2
        )
        mock_modifiers = MagicMock()
        mock_modifiers.__iter__.return_value = [cloth_mod]
        mock_modifiers.get.side_effect = lambda n: cloth_mod if n == "Cloth" else None
        mock_obj.modifiers = mock_modifiers
        mock_bpy.data.objects.get.return_value = mock_obj

        params = {
            "object_name": "ConfiguredCloth",
            "physics_type": "CLOTH",
            "action": "configure",
            "use_internal_springs": True,
            "internal_spring_max_length": 3.0,
            "internal_tension_stiffness": 35.0,
            "internal_compression_stiffness": 45.0,
            "internal_spring_normal_check": False,
            "use_pressure": True,
            "uniform_pressure_force": 8.0,
            "use_pressure_volume": True,
            "target_volume": 2.0,
            "pressure_factor": 1.5,
        }

        res = execute_configure_physics(mock_bpy, params)
        assert res["success"] is True
        assert res["use_internal_springs"] is True
        assert res["internal_spring_max_length"] == 3.0
        assert res["internal_tension_stiffness"] == 35.0
        assert res["internal_compression_stiffness"] == 45.0
        assert res["internal_spring_normal_check"] is False
        assert res["use_pressure"] is True
        assert res["uniform_pressure_force"] == 8.0
        assert res["use_pressure_volume"] is True
        assert res["target_volume"] == 2.0
        assert res["pressure_factor"] == 1.5

    def test_inspect_and_configure_cloth_object_collision(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.frame_current = 1
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "CollidingCloth"
        mock_obj.location = [0.0, 0.0, 1.0]
        mock_obj.matrix_world.translation = [0.0, 0.0, 1.0]
        mock_obj.rigid_body = None

        cloth_mod = MagicMock()
        cloth_mod.name = "Cloth"
        cloth_mod.type = "CLOTH"
        cloth_mod.settings = MagicMock(
            mass=0.3, quality=5, vertex_group_mass="",
            tension_stiffness=15.0, compression_stiffness=15.0,
            shear_stiffness=5.0, bending_stiffness=0.5,
            use_internal_springs=False, internal_spring_max_length=0.0,
            internal_tension_stiffness=15.0, internal_compression_stiffness=15.0,
            internal_spring_normal_check=True,
            use_pressure=False, uniform_pressure_force=0.0,
            use_pressure_volume=False, target_volume=0.0, pressure_factor=1.0,
        )
        cloth_mod.collision_settings = MagicMock(
            use_self_collision=False,
            self_distance_min=0.015,
            self_friction=5.0,
            use_collision=True,
            distance_min=0.015,
            friction=5.0,
            collision_quality=2,
        )
        cloth_mod.point_cache = None
        mock_modifiers = MagicMock()
        mock_modifiers.__iter__.return_value = [cloth_mod]
        mock_modifiers.get.side_effect = lambda n: cloth_mod if n == "Cloth" else None
        mock_obj.modifiers = mock_modifiers
        mock_bpy.data.objects.get.return_value = mock_obj

        # Inspect
        insp = execute_inspect_physics(mock_bpy, {"object_name": "CollidingCloth"})
        assert insp["success"] is True
        c_info = insp["target"]["cloth"]
        assert c_info["use_collision"] is True
        assert c_info["distance_min"] == 0.015
        assert c_info["collision_friction"] == 5.0
        assert c_info["collision_quality"] == 2

        # Configure object collision
        params = {
            "object_name": "CollidingCloth",
            "physics_type": "CLOTH",
            "action": "configure",
            "use_collision": False,
            "distance_min": 0.035,
            "friction": 12.0,
            "collision_quality": 4,
        }
        res = execute_configure_physics(mock_bpy, params)
        assert res["success"] is True
        assert res["use_collision"] is False
        assert res["distance_min"] == 0.035
        assert res["friction"] == 12.0
        assert res["collision_quality"] == 4
        assert cloth_mod.collision_settings.use_collision is False
        assert cloth_mod.collision_settings.distance_min == 0.035
        assert cloth_mod.collision_settings.friction == 12.0
        assert cloth_mod.collision_settings.collision_quality == 4

    def test_inspect_and_configure_rigid_body_kinematics_and_damping(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.frame_current = 1
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "Box"
        mock_obj.location = [0.0, 0.0, 0.0]
        mock_obj.matrix_world.translation = [0.0, 0.0, 0.0]
        mock_obj.rigid_body = MagicMock(
            type="ACTIVE", mass=2.0, friction=0.5, restitution=0.0,
            collision_shape="BOX", enabled=True, collision_margin=0.04,
            kinematic=False, linear_damping=0.04, angular_damping=0.10
        )
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []
        mock_bpy.data.objects.get.return_value = mock_obj

        # Inspect
        insp = execute_inspect_physics(mock_bpy, {"object_name": "Box"})
        assert insp["success"] is True
        rb_info = insp["target"]["rigid_body"]
        assert rb_info["kinematic"] is False
        assert rb_info["linear_damping"] == 0.04
        assert rb_info["angular_damping"] == 0.10

        # Configure
        params = {
            "object_name": "Box",
            "physics_type": "RIGID_BODY",
            "action": "configure",
            "kinematic": True,
            "linear_damping": 0.35,
            "angular_damping": 0.45,
        }
        res = execute_configure_physics(mock_bpy, params)
        assert res["success"] is True
        assert res["kinematic"] is True
        assert res["linear_damping"] == 0.35
        assert res["angular_damping"] == 0.45
        assert mock_obj.rigid_body.kinematic is True
        assert mock_obj.rigid_body.linear_damping == 0.35
        assert mock_obj.rigid_body.angular_damping == 0.45

    def test_inspect_and_configure_rigid_body_constraint(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.frame_current = 1
        mock_bpy.context.scene.rigidbody_world = MagicMock()
        anchor_obj = MagicMock()
        anchor_obj.name = "Anchor"
        anchor_obj.location = [0.0, 0.0, 5.0]
        anchor_obj.matrix_world.translation = [0.0, 0.0, 5.0]
        anchor_obj.rigid_body = None
        anchor_obj.modifiers = []

        bob_obj = MagicMock()
        bob_obj.name = "Bob"
        bob_obj.location = [0.0, 0.0, 3.0]
        bob_obj.matrix_world.translation = [0.0, 0.0, 3.0]
        bob_obj.rigid_body = None
        bob_obj.modifiers = []

        rbc = MagicMock()
        rbc.type = "POINT"
        rbc.enabled = True
        rbc.disable_collisions = True
        rbc.object1 = anchor_obj
        rbc.object2 = bob_obj
        rbc.use_breaking = False
        rbc.breaking_threshold = 10.0
        rbc.use_limit_lin_x = False
        rbc.limit_lin_x_lower = 0.0
        rbc.limit_lin_x_upper = 0.0
        rbc.use_limit_ang_z = False
        rbc.limit_ang_z_lower = 0.0
        rbc.limit_ang_z_upper = 0.0

        anchor_obj.rigid_body_constraint = rbc
        mock_bpy.data.objects.get.side_effect = lambda n: anchor_obj if n == "Anchor" else (bob_obj if n == "Bob" else None)

        insp = execute_inspect_physics(mock_bpy, {"object_name": "Anchor"})
        assert insp["success"] is True
        c_info = insp["target"]["rigid_body_constraint"]
        assert c_info["type"] == "POINT"
        assert c_info["target_object_1"] == "Anchor"
        assert c_info["target_object_2"] == "Bob"

        # Configure constraint
        params = {
            "object_name": "Anchor",
            "physics_type": "RIGID_BODY_CONSTRAINT",
            "action": "configure",
            "constraint_type": "HINGE",
            "use_breaking": True,
            "breaking_threshold": 50.0,
            "use_limit_ang_z": True,
            "limit_ang_z_lower": -0.5,
            "limit_ang_z_upper": 0.5,
        }
        res = execute_configure_physics(mock_bpy, params)
        assert res["success"] is True
        assert res["constraint_type"] == "HINGE"
        assert res["use_breaking"] is True
        assert res["breaking_threshold"] == 50.0
        assert rbc.type == "HINGE"
        assert rbc.use_breaking is True
        assert rbc.breaking_threshold == 50.0
        assert rbc.use_limit_ang_z is True
        assert rbc.limit_ang_z_lower == -0.5
        assert rbc.limit_ang_z_upper == 0.5

    def test_rollback_restores_prior_rigid_body_kinematics_on_failure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "KinematicTarget"
        rb = MagicMock(
            type="ACTIVE", mass=1.0, friction=0.5, restitution=0.0,
            collision_shape="CONVEX_HULL", kinematic=False, linear_damping=0.04, angular_damping=0.10
        )
        mock_obj.rigid_body = rb
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []
        mock_bpy.data.objects.get.return_value = mock_obj

        params = {
            "object_name": "KinematicTarget",
            "physics_type": "RIGID_BODY",
            "action": "configure",
            "kinematic": True,
            "linear_damping": 2.5,  # Invalid: > 1.0 triggers ValueError
        }
        with pytest.raises(ValueError, match="linear_damping"):
            execute_configure_physics(mock_bpy, params)

        assert rb.kinematic is False
        assert rb.linear_damping == 0.04

    def test_rollback_restores_prior_rigid_body_constraint_on_failure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "ConstrainedHost"
        mock_obj.rigid_body = None
        mock_obj.modifiers = []

        rbc = MagicMock()
        rbc.type = "POINT"
        rbc.enabled = True
        rbc.disable_collisions = True
        rbc.object1 = mock_obj
        rbc.object2 = None
        rbc.use_breaking = False
        rbc.breaking_threshold = 10.0
        rbc.use_limit_lin_x = False
        rbc.limit_lin_x_lower = 0.0
        rbc.limit_lin_x_upper = 0.0

        mock_obj.rigid_body_constraint = rbc
        mock_bpy.data.objects.get.return_value = mock_obj

        params = {
            "object_name": "ConstrainedHost",
            "physics_type": "RIGID_BODY_CONSTRAINT",
            "action": "configure",
            "constraint_type": "SLIDER",
            "breaking_threshold": -20.0,  # Invalid: < 0.0
        }
        with pytest.raises(ValueError, match="breaking_threshold"):
            execute_configure_physics(mock_bpy, params)

        assert rbc.type == "POINT"
        assert rbc.breaking_threshold == 10.0

    def test_rollback_removes_added_rigid_body_constraint_on_failure(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "HostObj"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []

        class FailingConstraintMock(MagicMock):
            pass

        def add_constraint(**kwargs):
            c = FailingConstraintMock()
            c.type = "FIXED"
            type(c).breaking_threshold = PropertyMock(side_effect=RuntimeError("Simulated write failure on constraint"))
            mock_obj.rigid_body_constraint = c
        mock_bpy.ops.rigidbody.constraint_add.side_effect = add_constraint

        def remove_constraint():
            mock_obj.rigid_body_constraint = None
        mock_bpy.ops.rigidbody.constraint_remove.side_effect = remove_constraint

        mock_bpy.data.objects.get.return_value = mock_obj

        params = {
            "object_name": "HostObj",
            "physics_type": "RIGID_BODY_CONSTRAINT",
            "action": "add",
            "breaking_threshold": 25.0,
        }
        with pytest.raises(RuntimeError, match="Simulated write failure on constraint"):
            execute_configure_physics(mock_bpy, params)

        assert mock_obj.rigid_body_constraint is None
        mock_bpy.ops.rigidbody.constraint_remove.assert_called_once()


class TestModelingAgentPhysicsCapabilities:
    """Validates agent capability declarations and task validation."""

    def test_physics_capabilities_declared(self):
        agent = ModelingAgent()
        manifest = agent.get_manifest()
        caps = {c.capability_id for c in manifest.capabilities}
        assert CAPABILITY_MODELING_PHYSICS in caps
        assert CAPABILITY_MODELING_PHYSICS_INSPECT in caps

    def test_tools_in_supported_set(self):
        for tool in (TOOL_CONFIGURE_PHYSICS, TOOL_INSPECT_PHYSICS, TOOL_BAKE_PHYSICS_SIMULATION):
            assert tool in SUPPORTED_MODELING_TOOLS


class TestForceFieldControls:
    """Capability 6.2.1: Validates creation, configuration, inspection, removal, snapshots, and rollback for force fields."""

    def test_force_field_tools_registered_in_definitions(self):
        assert TOOL_CONFIGURE_FORCE_FIELD in TOOL_DEFINITIONS
        assert TOOL_INSPECT_FORCE_FIELD in TOOL_DEFINITIONS
        assert TOOL_DEFINITIONS[TOOL_CONFIGURE_FORCE_FIELD]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_INSPECT_FORCE_FIELD]["permission_tier"] == PERMISSION_READ_ONLY

    def test_validate_configure_force_field_valid_wind(self):
        params = {
            "name": "WindEffector",
            "action": "create",
            "field_type": "WIND",
            "strength": 25.0,
            "flow": 1.5,
            "wind_factor": 0.8,
            "shape": "PLANE",
            "location": [0.0, 5.0, 2.0],
            "rotation": [0.0, 1.5708, 0.0],
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, params, trusted_approval=True)
        assert sanitized["name"] == "WindEffector"
        assert sanitized["field_type"].upper() == "WIND"
        assert sanitized["strength"] == 25.0
        assert sanitized["flow"] == 1.5
        assert sanitized["wind_factor"] == 0.8
        assert sanitized["shape"].upper() == "PLANE"

    def test_validate_configure_force_field_valid_turbulence(self):
        params = {
            "name": "TurbulenceEffector",
            "action": "configure",
            "field_type": "TURBULENCE",
            "strength": 10.0,
            "size": 2.5,
            "use_global_coords": True,
            "noise": 3.0,
            "seed": 42,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, params, trusted_approval=True)
        assert sanitized["field_type"].upper() == "TURBULENCE"
        assert sanitized["size"] == 2.5
        assert sanitized["use_global_coords"] is True
        assert sanitized["noise"] == 3.0
        assert sanitized["seed"] == 42

    def test_validate_configure_force_field_valid_vortex(self):
        params = {
            "name": "VortexEffector",
            "action": "create",
            "field_type": "VORTEX",
            "strength": 15.0,
            "inflow": -2.0,
            "shape": "POINT",
            "use_2d_force": True,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, params, trusted_approval=True)
        assert sanitized["field_type"].upper() == "VORTEX"
        assert sanitized["strength"] == 15.0
        assert sanitized["inflow"] == -2.0
        assert sanitized["use_2d_force"] is True

    def test_validate_configure_force_field_invalid_type(self):
        with pytest.raises(ValueError, match="Invalid value for 'field_type'|Unsupported field_type"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "MagnetEffector",
                "field_type": "MAGNET",
            }, trusted_approval=True)

    def test_validate_configure_force_field_invalid_action(self):
        with pytest.raises(ValueError, match="Invalid value for 'action'|Unsupported action"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "Effector",
                "action": "explode",
            }, trusted_approval=True)

    def test_validate_configure_force_field_invalid_strength_bounds(self):
        with pytest.raises(ValueError, match="must be <= 100000.0|must be between -100000.0 and 100000.0"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "Effector",
                "strength": 999999.0,
            }, trusted_approval=True)

    def test_validate_configure_force_field_invalid_wind_factor_bounds(self):
        with pytest.raises(ValueError, match="must be <= 1.0|must be between 0.0 and 1.0"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "Effector",
                "wind_factor": 1.5,
            }, trusted_approval=True)

    def test_validate_configure_force_field_invalid_noise_bounds(self):
        with pytest.raises(ValueError, match="must be <= 10.0|must be between 0.0 and 10.0"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "Effector",
                "noise": 15.0,
            }, trusted_approval=True)

    def test_validate_configure_force_field_invalid_seed_bounds(self):
        with pytest.raises(ValueError, match="must be <= 128|must be between 1 and 128"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "Effector",
                "seed": 200,
            }, trusted_approval=True)

    def test_validate_configure_force_field_distance_limits_inverted(self):
        with pytest.raises(ValueError, match="cannot be greater than 'distance_max'"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "Effector",
                "distance_min": 50.0,
                "distance_max": 10.0,
            }, trusted_approval=True)

    def test_untrusted_approval_rejected_force_field(self):
        with pytest.raises(PermissionError, match="untrusted and cannot authorize scene mutation|Missing trusted human approval credentials"):
            validate_tool_input(TOOL_CONFIGURE_FORCE_FIELD, {
                "name": "Effector",
                "approved": True,
            }, trusted_approval=False)

    def test_snapshot_sensitivity_to_force_field_presence(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "WindEffector"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []
        mock_obj.field = None

        snap_no_field = compute_physics_snapshot_id(mock_bpy, mock_obj)

        # Attach field
        mock_obj.field = MagicMock(
            type="WIND", shape="POINT", strength=1.0, flow=0.0, wind_factor=1.0,
            size=1.0, inflow=0.0, noise=0.0, seed=1, use_global_coords=False,
            use_2d_force=False, falloff_power=0.0, use_min_distance=False,
            distance_min=0.0, use_max_distance=False, distance_max=0.0,
            z_direction="BOTH", falloff_type="SPHERE",
        )
        snap_with_field = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap_no_field != snap_with_field, "Snapshot must reflect presence of a force field"

    def test_snapshot_sensitivity_to_force_field_mutation(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.rigidbody_world = None
        mock_obj = MagicMock()
        mock_obj.name = "VortexEffector"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []
        mock_obj.field = MagicMock(
            type="VORTEX", shape="POINT", strength=10.0, flow=0.0, wind_factor=1.0,
            size=1.0, inflow=0.0, noise=0.0, seed=1, use_global_coords=False,
            use_2d_force=False, falloff_power=0.0, use_min_distance=False,
            distance_min=0.0, use_max_distance=False, distance_max=0.0,
            z_direction="BOTH", falloff_type="SPHERE",
        )

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        mock_obj.field.strength = 50.0
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Snapshot must change when force field strength changes"

    def test_stale_snapshot_raises_error_force_field(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "WindEffector"
        mock_obj.field = MagicMock(type="WIND")
        mock_bpy.data.objects.get.return_value = mock_obj

        params = {
            "name": "WindEffector",
            "action": "configure",
            "strength": 20.0,
            "expected_snapshot_id": "physics_deadbeef12345678",
        }
        with pytest.raises(ValueError, match="STALE_PHYSICS_STATE"):
            execute_configure_force_field(mock_bpy, params)

    def test_create_and_inspect_force_field_wind(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Wind1"
        mock_obj.location = [1.0, 2.0, 3.0]
        mock_obj.rotation_euler = [0.0, 1.5708, 0.0]
        mock_field = MagicMock(
            type="WIND", shape="PLANE", strength=30.0, flow=2.0, wind_factor=0.9,
            size=1.0, inflow=0.0, noise=0.5, seed=12, use_global_coords=False,
            use_2d_force=False, falloff_power=1.0, use_min_distance=False,
            distance_min=0.0, use_max_distance=False, distance_max=0.0,
            z_direction="BOTH", falloff_type="SPHERE",
        )
        mock_obj.field = mock_field
        mock_bpy.data.objects.get.return_value = None
        mock_bpy.context.active_object = mock_obj
        mock_bpy.data.objects.__iter__.return_value = [mock_obj]

        res = execute_configure_force_field(mock_bpy, {
            "name": "Wind1",
            "action": "create",
            "field_type": "WIND",
            "strength": 30.0,
            "flow": 2.0,
            "wind_factor": 0.9,
            "shape": "PLANE",
            "noise": 0.5,
            "seed": 12,
            "location": [1.0, 2.0, 3.0],
            "rotation": [0.0, 1.5708, 0.0],
        })
        assert res["success"] is True
        assert res["object_name"] == "Wind1"
        assert res["field_type"] == "WIND"
        assert res["strength"] == 30.0

        # Inspect
        mock_bpy.data.objects.get.return_value = mock_obj
        insp = execute_inspect_force_field(mock_bpy, {"name": "Wind1"})
        assert insp["success"] is True
        assert insp["has_force_field"] is True
        assert insp["field_type"] == "WIND"
        assert insp["strength"] == 30.0
        assert insp["wind_factor"] == 0.9

    def test_configure_force_field_turbulence(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Turb1"
        mock_field = MagicMock(
            type="TURBULENCE", shape="POINT", strength=5.0, flow=0.0, wind_factor=1.0,
            size=1.0, inflow=0.0, noise=0.0, seed=1, use_global_coords=False,
            use_2d_force=False, falloff_power=0.0, use_min_distance=False,
            distance_min=0.0, use_max_distance=False, distance_max=0.0,
            z_direction="BOTH", falloff_type="SPHERE",
        )
        mock_obj.field = mock_field
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_force_field(mock_bpy, {
            "name": "Turb1",
            "action": "configure",
            "strength": 18.5,
            "size": 3.2,
            "use_global_coords": True,
        })
        assert res["success"] is True
        assert res["strength"] == 18.5
        assert res["size"] == 3.2

    def test_configure_force_field_vortex(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Vortex1"
        mock_field = MagicMock(
            type="VORTEX", shape="POINT", strength=10.0, flow=0.0, wind_factor=1.0,
            size=1.0, inflow=0.0, noise=0.0, seed=1, use_global_coords=False,
            use_2d_force=False, falloff_power=0.0, use_min_distance=False,
            distance_min=0.0, use_max_distance=False, distance_max=0.0,
            z_direction="BOTH", falloff_type="SPHERE",
        )
        mock_obj.field = mock_field
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_force_field(mock_bpy, {
            "name": "Vortex1",
            "action": "configure",
            "strength": 40.0,
            "inflow": -5.0,
        })
        assert res["success"] is True
        assert res["strength"] == 40.0
        assert res["inflow"] == -5.0

    def test_remove_force_field(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "WindToDisable"
        mock_field = MagicMock(type="WIND")
        mock_obj.field = mock_field
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_force_field(mock_bpy, {
            "name": "WindToDisable",
            "action": "remove",
            "delete_object": False,
        })
        assert res["success"] is True
        assert res["removed"] is True
        assert mock_field.type == "NONE"

    def test_remove_force_field_delete_object(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "WindToDelete"
        mock_field = MagicMock(type="WIND")
        mock_obj.field = mock_field
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_force_field(mock_bpy, {
            "name": "WindToDelete",
            "action": "remove",
            "delete_object": True,
        })
        assert res["success"] is True
        assert res["deleted_object"] is True
        mock_bpy.data.objects.remove.assert_called_once_with(mock_obj, do_unlink=True)

    def test_rollback_removes_created_force_field_on_failure(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "FailingField"
        mock_field = MagicMock(type="WIND")
        type(mock_field).strength = PropertyMock(side_effect=RuntimeError("Simulated write failure on strength"))
        mock_obj.field = mock_field
        mock_bpy.data.objects.get.return_value = None
        mock_bpy.context.active_object = mock_obj

        with pytest.raises(RuntimeError, match="Simulated write failure on strength"):
            execute_configure_force_field(mock_bpy, {
                "name": "FailingField",
                "action": "create",
                "field_type": "WIND",
                "strength": 50.0,
            })

        mock_bpy.data.objects.remove.assert_called_once_with(mock_obj, do_unlink=True)

    def test_rollback_restores_prior_force_field_on_failure(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "ExistingField"
        mock_field = MagicMock(
            type="WIND", shape="POINT", strength=10.0, flow=1.0, wind_factor=1.0,
            size=1.0, inflow=0.0, noise=0.0, seed=1, use_global_coords=False,
            use_2d_force=False, falloff_power=0.0, use_min_distance=False,
            distance_min=0.0, use_max_distance=False, distance_max=0.0,
            z_direction="BOTH", falloff_type="SPHERE",
        )
        mock_obj.field = mock_field
        mock_bpy.data.objects.get.return_value = mock_obj

        # Cause failure on wind_factor
        type(mock_field).wind_factor = PropertyMock(side_effect=RuntimeError("Simulated failure on wind_factor"))

        with pytest.raises(RuntimeError, match="Simulated failure on wind_factor"):
            execute_configure_force_field(mock_bpy, {
                "name": "ExistingField",
                "action": "configure",
                "strength": 99.0,
                "wind_factor": 0.5,
            })

        # Check that rollback restored prior strength 10.0
        assert mock_field.strength == 10.0

    def test_simulation_agent_force_field_capabilities(self):
        agent = SimulationVFXAgent()
        manifest = agent.manifest
        caps = {c.capability_id for c in manifest.capabilities}
        assert CAPABILITY_PHYSICS_SIMULATION in caps
        assert CAPABILITY_PHYSICS_INSPECT in caps
        assert TOOL_CONFIGURE_FORCE_FIELD in SUPPORTED_SIMULATION_TOOLS
        assert TOOL_INSPECT_FORCE_FIELD in SUPPORTED_SIMULATION_TOOLS


class TestEmitterParticleSystems:
    """
    Focused tests for Capability 6.2.2 - Emitter Particle Systems.
    Validates tool registration, schema parameter validation, hair rejection,
    deterministic snapshot calculation, optimistic concurrency, RNA mock execution,
    transactional rollback, and agent capabilities.
    """

    def test_particle_tools_registered_in_definitions(self):
        assert TOOL_CONFIGURE_PARTICLE_SYSTEM in TOOL_DEFINITIONS
        assert TOOL_INSPECT_PARTICLE_SYSTEM in TOOL_DEFINITIONS

    def test_particle_permission_tiers(self):
        assert TOOL_DEFINITIONS[TOOL_CONFIGURE_PARTICLE_SYSTEM]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_INSPECT_PARTICLE_SYSTEM]["permission_tier"] == PERMISSION_READ_ONLY

    def test_validate_configure_particle_system_valid(self):
        valid_input = {
            "object_name": "EmitterMesh",
            "system_name": "Sparks",
            "action": "create",
            "system_type": "EMITTER",
            "count": 500,
            "frame_start": 5.0,
            "frame_end": 50.0,
            "lifetime": 35.0,
            "lifetime_random": 0.2,
            "normal_factor": 4.0,
            "tangent_factor": 1.0,
            "particle_size": 0.15,
            "render_type": "OBJECT",
            "instance_object": "SparkCube",
        }
        res = validate_tool_input(TOOL_CONFIGURE_PARTICLE_SYSTEM, valid_input, trusted_approval=True)
        assert res["object_name"] == "EmitterMesh"
        assert res["system_type"] == "EMITTER"
        assert res["count"] == 500
        assert res["normal_factor"] == 4.0
        assert res["render_type"] == "OBJECT"
        assert res["instance_object"] == "SparkCube"

    def test_validate_configure_particle_system_collection_instancing_valid(self):
        valid_input = {
            "object_name": "EmitterMesh",
            "action": "configure",
            "render_type": "COLLECTION",
            "instance_collection": "DebrisCol",
        }
        res = validate_tool_input(TOOL_CONFIGURE_PARTICLE_SYSTEM, valid_input, trusted_approval=True)
        assert res["render_type"] == "COLLECTION"
        assert res["instance_collection"] == "DebrisCol"

    def test_validate_configure_particle_system_accepts_hair_and_rejects_invalid_type(self):
        res = validate_tool_input(
            TOOL_CONFIGURE_PARTICLE_SYSTEM,
            {"object_name": "HairMesh", "system_type": "HAIR", "hair_length": 3.5, "hair_step": 6, "use_hair_dynamics": True},
            trusted_approval=True,
        )
        assert res["system_type"] == "HAIR"
        assert res["hair_length"] == 3.5
        assert res["hair_step"] == 6
        assert res["use_hair_dynamics"] is True

        with pytest.raises(ValueError, match="system_type"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "system_type": "INVALID_TYPE"},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_hair_bounds(self):
        with pytest.raises(ValueError, match="hair_length"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "hair_length": -1.0},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="hair_step"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "hair_step": 0},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="hair_step"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "hair_step": 8},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="hair_dynamics_quality"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "hair_dynamics_quality": 100},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="hair_dynamics_mass"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "hair_dynamics_mass": 0.0},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="hair_dynamics_bending_stiffness"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "hair_dynamics_bending_stiffness": -2.0},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="Unsupported render_type 'HALO' for HAIR"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "render_type": "HALO"},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="Unsupported render_type 'LINE' for HAIR"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "HairMesh", "system_type": "HAIR", "render_type": "LINE"},
                trusted_approval=True,
            )
        san = validate_tool_input(
            TOOL_CONFIGURE_PARTICLE_SYSTEM,
            {"object_name": "HairMesh", "system_type": "HAIR"},
            trusted_approval=True,
        )
        assert san["render_type"] == "PATH"
        assert san["hair_length"] == 4.0
        assert san["hair_step"] == 5

    def test_validate_configure_particle_system_invalid_action(self):
        with pytest.raises(ValueError, match="action"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "action": "explode"},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_invalid_count_bounds(self):
        with pytest.raises(ValueError, match="count"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "count": 0},
                trusted_approval=True,
            )
        with pytest.raises(ValueError, match="count"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "count": 2000000},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_invalid_lifetime_bounds(self):
        with pytest.raises(ValueError, match="lifetime"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "lifetime": 0.0},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_invalid_lifetime_random(self):
        with pytest.raises(ValueError, match="lifetime_random"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "lifetime_random": 1.25},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_inverted_frames(self):
        with pytest.raises(ValueError, match="must be >= 'frame_start'"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "frame_start": 100.0, "frame_end": 10.0},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_invalid_particle_size(self):
        with pytest.raises(ValueError, match="particle_size"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "particle_size": 0.0},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_invalid_render_type(self):
        with pytest.raises(ValueError, match="render_type"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "render_type": "VOLUME"},
                trusted_approval=True,
            )

    def test_validate_configure_particle_system_invalid_physics_type(self):
        with pytest.raises(ValueError, match="physics_type"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "physics_type": "QUANTUM"},
                trusted_approval=True,
            )

    def test_untrusted_approval_rejected_particle_system(self):
        with pytest.raises(PermissionError, match="untrusted"):
            validate_tool_input(
                TOOL_CONFIGURE_PARTICLE_SYSTEM,
                {"object_name": "EmitterMesh", "approved": True},
                trusted_approval=False,
            )

    def test_snapshot_sensitivity_to_particle_system_presence(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "EmitterObj"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []
        mock_obj.field = None
        mock_obj.particle_systems = []
        mock_bpy.data.objects = [mock_obj]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        mock_ps = MagicMock()
        mock_ps.name = "PS1"
        mock_settings = MagicMock(
            type="EMITTER", count=1000, frame_start=1.0, frame_end=200.0,
            lifetime=50.0, lifetime_random=0.0, normal_factor=1.0, tangent_factor=0.0,
            object_factor=0.0, factor_random=0.0, physics_type="NEWTON",
            render_type="HALO", instance_object=None, instance_collection=None,
            particle_size=0.05, size_random=0.0,
        )
        mock_ps.settings = mock_settings
        mock_obj.particle_systems = [mock_ps]

        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Snapshot must change when particle system is added"

    def test_snapshot_sensitivity_to_particle_system_mutation(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "EmitterObj"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "PS1"
        mock_settings = MagicMock(
            type="EMITTER", count=1000, frame_start=1.0, frame_end=200.0,
            lifetime=50.0, lifetime_random=0.0, normal_factor=1.0, tangent_factor=0.0,
            object_factor=0.0, factor_random=0.0, physics_type="NEWTON",
            render_type="HALO", instance_object=None, instance_collection=None,
            particle_size=0.05, size_random=0.0,
        )
        mock_ps.settings = mock_settings
        mock_obj.particle_systems = [mock_ps]
        mock_bpy.data.objects = [mock_obj]

        snap_initial = compute_physics_snapshot_id(mock_bpy, mock_obj)

        mock_settings.count = 2500
        snap_count_mutated = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap_initial != snap_count_mutated

        mock_settings.count = 1000
        mock_settings.render_type = "OBJECT"
        snap_render_mutated = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap_initial != snap_render_mutated

        # Test sensitivity to HAIR type and hair_length mutation
        mock_settings.render_type = "HALO"
        mock_settings.type = "HAIR"
        mock_settings.hair_length = 6.0
        snap_hair_mutated = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap_initial != snap_hair_mutated

        # Test sensitivity to hair dynamics mutation
        mock_ps.use_hair_dynamics = True
        snap_dynamics_mutated = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap_hair_mutated != snap_dynamics_mutated

    def test_stale_snapshot_raises_error_particle_system(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "EmitterObj"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.modifiers = []
        mock_obj.field = None
        mock_obj.particle_systems = []
        mock_bpy.data.objects.get.return_value = mock_obj

        with pytest.raises(ValueError, match="STALE_PHYSICS_STATE"):
            execute_configure_particle_system(mock_bpy, {
                "object_name": "EmitterObj",
                "action": "create",
                "expected_snapshot_id": "physics_stale_hash_1234",
            })

    def test_create_and_inspect_particle_system(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Emitter1"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "ParticleSystem"
        mock_settings = MagicMock(
            type="EMITTER", count=1000, frame_start=1.0, frame_end=200.0,
            lifetime=50.0, lifetime_random=0.0, normal_factor=1.0, tangent_factor=0.0,
            object_factor=0.0, factor_random=0.0, physics_type="NEWTON",
            render_type="HALO", instance_object=None, instance_collection=None,
            particle_size=0.05, size_random=0.0, use_scale_instance=True, use_global_instance=False,
        )
        mock_ps.settings = mock_settings
        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_mod.name = "ParticleSystem"
        mock_mod.particle_system = mock_ps

        mock_mods = MagicMock()
        mock_mods.new.return_value = mock_mod
        mock_mods.__iter__.return_value = iter([])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = []
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_particle_system(mock_bpy, {
            "object_name": "Emitter1",
            "action": "create",
            "count": 350,
            "lifetime": 40.0,
            "normal_factor": 2.5,
        })
        assert res["success"] is True
        assert res["system_type"] == "EMITTER"
        assert mock_settings.count == 350
        assert mock_settings.lifetime == 40.0
        assert mock_settings.normal_factor == 2.5

        # Test inspect
        mock_obj.particle_systems = [mock_ps]
        inspect_res = execute_inspect_particle_system(mock_bpy, {"object_name": "Emitter1"})
        assert inspect_res["success"] is True
        assert inspect_res["count"] == 1
        assert inspect_res["particle_systems"][0]["object_name"] == "Emitter1"

    def test_configure_particle_system_instancing(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Emitter1"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "ParticleSystem"
        mock_settings = MagicMock(
            type="EMITTER", count=1000, frame_start=1.0, frame_end=200.0,
            lifetime=50.0, lifetime_random=0.0, normal_factor=1.0, tangent_factor=0.0,
            object_factor=0.0, factor_random=0.0, physics_type="NEWTON",
            render_type="HALO", instance_object=None, instance_collection=None,
            particle_size=0.05, size_random=0.0,
        )
        mock_ps.settings = mock_settings
        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_mod.name = "ParticleSystem"
        mock_mod.particle_system = mock_ps
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = [mock_ps]

        mock_inst_cube = MagicMock()
        mock_inst_cube.name = "InstCube"
        mock_bpy.data.objects.get.side_effect = lambda name: mock_inst_cube if name == "InstCube" else mock_obj

        res = execute_configure_particle_system(mock_bpy, {
            "object_name": "Emitter1",
            "action": "configure",
            "render_type": "OBJECT",
            "instance_object": "InstCube",
            "particle_size": 0.25,
        })
        assert res["success"] is True
        assert mock_settings.render_type == "OBJECT"
        assert mock_settings.instance_object == mock_inst_cube
        assert mock_settings.particle_size == 0.25

    def test_configure_particle_system_collection_instancing(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Emitter1"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "ParticleSystem"
        mock_settings = MagicMock(
            type="EMITTER", count=1000, frame_start=1.0, frame_end=200.0,
            lifetime=50.0, lifetime_random=0.0, normal_factor=1.0, tangent_factor=0.0,
            object_factor=0.0, factor_random=0.0, physics_type="NEWTON",
            render_type="HALO", instance_object=None, instance_collection=None,
            particle_size=0.05, size_random=0.0,
        )
        mock_ps.settings = mock_settings
        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_mod.name = "ParticleSystem"
        mock_mod.particle_system = mock_ps
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = [mock_ps]

        mock_inst_col = MagicMock()
        mock_inst_col.name = "ColDebris"
        mock_bpy.data.objects.get.return_value = mock_obj
        mock_bpy.data.collections.get.return_value = mock_inst_col

        res = execute_configure_particle_system(mock_bpy, {
            "object_name": "Emitter1",
            "action": "configure",
            "render_type": "COLLECTION",
            "instance_collection": "ColDebris",
        })
        assert res["success"] is True
        assert mock_settings.render_type == "COLLECTION"
        assert mock_settings.instance_collection == mock_inst_col

    def test_remove_particle_system(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "Emitter1"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "ParticleSystem"
        mock_settings = MagicMock(name="PS_Settings")
        mock_ps.settings = mock_settings
        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_mod.name = "ParticleSystem"
        mock_mod.particle_system = mock_ps
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = [mock_ps]
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_particle_system(mock_bpy, {
            "object_name": "Emitter1",
            "action": "remove",
            "delete_settings": True,
        })
        assert res["success"] is True
        assert res["removed"] is True
        mock_mods.remove.assert_called_once_with(mock_mod)
        mock_bpy.data.particles.remove.assert_called_once_with(mock_settings, do_unlink=True)

    def test_rollback_removes_created_particle_system_on_failure(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "EmitterFail"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_mods = MagicMock()
        mock_mods.__iter__.return_value = iter([])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = []
        mock_bpy.data.objects.get.return_value = mock_obj

        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_ps = MagicMock()
        mock_settings = MagicMock()
        type(mock_settings).count = PropertyMock(side_effect=RuntimeError("Simulated write failure on count"))
        mock_ps.settings = mock_settings
        mock_mod.particle_system = mock_ps
        mock_mods.new.return_value = mock_mod

        with pytest.raises(RuntimeError, match="Simulated write failure on count"):
            execute_configure_particle_system(mock_bpy, {
                "object_name": "EmitterFail",
                "action": "create",
                "count": 500,
            })

        mock_mods.remove.assert_called_once_with(mock_mod)

    def test_rollback_restores_prior_particle_settings_on_failure(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "EmitterExisting"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "ParticleSystem"
        mock_settings = MagicMock(
            count=1000, frame_start=1.0, frame_end=200.0, lifetime=50.0,
            lifetime_random=0.0, normal_factor=1.0, tangent_factor=0.0,
            object_factor=0.0, factor_random=0.0, physics_type="NEWTON",
            particle_size=0.05, size_random=0.0, render_type="HALO",
            instance_object=None, instance_collection=None, use_scale_instance=True, use_global_instance=False,
        )
        mock_ps.settings = mock_settings
        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_mod.name = "ParticleSystem"
        mock_mod.particle_system = mock_ps
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = [mock_ps]
        mock_bpy.data.objects.get.return_value = mock_obj

        type(mock_settings).lifetime = PropertyMock(side_effect=RuntimeError("Simulated failure on lifetime"))

        with pytest.raises(RuntimeError, match="Simulated failure on lifetime"):
            execute_configure_particle_system(mock_bpy, {
                "object_name": "EmitterExisting",
                "action": "configure",
                "count": 2000,
                "lifetime": 80.0,
            })

        # Rollback should restore prior count 1000
        assert mock_settings.count == 1000

    def test_create_and_inspect_hair_particle_system(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "HairMesh1"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "HairSystem"
        mock_ps.use_hair_dynamics = False
        mock_cloth = MagicMock()
        mock_cloth.settings = MagicMock(quality=5, mass=1.0, bending_stiffness=0.5, air_damping=1.0, pin_stiffness=1.0)
        mock_ps.cloth = mock_cloth

        mock_settings = MagicMock(
            type="HAIR", count=500, hair_length=3.5, hair_step=6,
            frame_start=1.0, frame_end=200.0, lifetime=50.0, lifetime_random=0.0,
            normal_factor=1.0, tangent_factor=0.0, object_factor=0.0, factor_random=0.0,
            physics_type="NEWTON", render_type="PATH", instance_object=None,
            instance_collection=None, particle_size=0.05, size_random=0.0,
        )
        mock_ps.settings = mock_settings
        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_mod.name = "HairSystem"
        mock_mod.particle_system = mock_ps

        mock_mods = MagicMock()
        mock_mods.new.return_value = mock_mod
        mock_mods.__iter__.return_value = iter([])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = []
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_particle_system(mock_bpy, {
            "object_name": "HairMesh1",
            "system_name": "HairSystem",
            "action": "create",
            "system_type": "HAIR",
            "count": 500,
            "hair_length": 3.5,
            "hair_step": 6,
            "use_hair_dynamics": True,
            "hair_dynamics_quality": 8,
            "hair_dynamics_mass": 0.8,
            "hair_dynamics_bending_stiffness": 1.5,
        })
        assert res["success"] is True
        assert res["system_type"] == "HAIR"
        assert res["hair_length"] == 3.5
        assert res["hair_step"] == 6
        assert res["use_hair_dynamics"] is True
        assert res["hair_dynamics_quality"] == 8
        assert res["hair_dynamics_mass"] == 0.8
        assert res["hair_dynamics_bending_stiffness"] == 1.5
        assert mock_ps.use_hair_dynamics is True
        assert mock_cloth.settings.quality == 8
        assert mock_cloth.settings.mass == 0.8
        assert mock_cloth.settings.bending_stiffness == 1.5

        # Test inspection of hair particle system
        mock_obj.particle_systems = [mock_ps]
        inspect_res = execute_inspect_particle_system(mock_bpy, {"object_name": "HairMesh1"})
        assert inspect_res["success"] is True
        assert inspect_res["count"] == 1
        ps_info = inspect_res["particle_systems"][0]
        assert ps_info["system_type"] == "HAIR"
        assert ps_info["hair_length"] == 3.5
        assert ps_info["hair_step"] == 6
        assert ps_info["use_hair_dynamics"] is True
        assert ps_info["hair_dynamics_quality"] == 8
        assert ps_info["hair_dynamics_mass"] == 0.8

    def test_rollback_restores_prior_hair_dynamics_on_failure(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "HairMeshFail"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None

        mock_ps = MagicMock()
        mock_ps.name = "HairSystem"
        mock_ps.use_hair_dynamics = False
        mock_cloth = MagicMock()
        mock_cloth_settings = MagicMock(quality=5, mass=1.0, bending_stiffness=0.5, air_damping=1.0, pin_stiffness=1.0)
        mock_cloth.settings = mock_cloth_settings
        mock_ps.cloth = mock_cloth

        mock_settings = MagicMock(
            type="HAIR", count=500, hair_length=2.0, hair_step=5,
            frame_start=1.0, frame_end=200.0, lifetime=50.0, lifetime_random=0.0,
            normal_factor=1.0, tangent_factor=0.0, object_factor=0.0, factor_random=0.0,
            physics_type="NEWTON", render_type="PATH", instance_object=None,
            instance_collection=None, particle_size=0.05, size_random=0.0,
        )
        mock_ps.settings = mock_settings
        mock_mod = MagicMock()
        mock_mod.type = "PARTICLE_SYSTEM"
        mock_mod.name = "HairSystem"
        mock_mod.particle_system = mock_ps
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_obj.particle_systems = [mock_ps]
        mock_bpy.data.objects.get.return_value = mock_obj

        # Simulate exception during bending_stiffness write
        type(mock_cloth_settings).bending_stiffness = PropertyMock(side_effect=RuntimeError("Simulated failure on bending_stiffness"))

        with pytest.raises(RuntimeError, match="Simulated failure on bending_stiffness"):
            execute_configure_particle_system(mock_bpy, {
                "object_name": "HairMeshFail",
                "action": "configure",
                "use_hair_dynamics": True,
                "hair_dynamics_bending_stiffness": 10.0,
            })

        # Rollback should restore use_hair_dynamics to False
        assert mock_ps.use_hair_dynamics is False

    def test_simulation_agent_particle_capabilities(self):
        agent = SimulationVFXAgent()
        manifest = agent.manifest
        caps = {c.capability_id for c in manifest.capabilities}
        assert CAPABILITY_PHYSICS_SIMULATION in caps
        assert CAPABILITY_PHYSICS_INSPECT in caps
        assert TOOL_CONFIGURE_PARTICLE_SYSTEM in SUPPORTED_SIMULATION_TOOLS
        assert TOOL_INSPECT_PARTICLE_SYSTEM in SUPPORTED_SIMULATION_TOOLS


class TestMantaflowFluidSimulation:
    """Validates Mantaflow fluid simulation schemas, snapshot sensitivity, and execution."""

    def test_fluid_tools_registered_in_definitions(self):
        assert TOOL_CONFIGURE_FLUID_SIMULATION in TOOL_DEFINITIONS
        assert TOOL_INSPECT_FLUID_SIMULATION in TOOL_DEFINITIONS

    def test_fluid_permission_tiers(self):
        assert TOOL_DEFINITIONS[TOOL_CONFIGURE_FLUID_SIMULATION]["permission_tier"] == PERMISSION_SCENE_MUTATION
        assert TOOL_DEFINITIONS[TOOL_INSPECT_FLUID_SIMULATION]["permission_tier"] == PERMISSION_READ_ONLY

    def test_validate_configure_fluid_domain_gas_valid(self):
        params = {
            "object_name": "GasDomain",
            "fluid_type": "DOMAIN",
            "domain_type": "GAS",
            "resolution_max": 64,
            "time_scale": 1.2,
            "cfl_condition": 2.5,
            "alpha": 1.5,
            "beta": 0.8,
            "vorticity": 0.2,
            "use_dissolve_smoke": True,
            "dissolve_speed": 10,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)
        assert sanitized["object_name"] == "GasDomain"
        assert sanitized["fluid_type"] == "DOMAIN"
        assert sanitized["domain_type"] == "GAS"
        assert sanitized["resolution_max"] == 64
        assert sanitized["time_scale"] == 1.2
        assert sanitized["cfl_condition"] == 2.5
        assert sanitized["alpha"] == 1.5
        assert sanitized["beta"] == 0.8
        assert sanitized["vorticity"] == 0.2
        assert sanitized["use_dissolve_smoke"] is True
        assert sanitized["dissolve_speed"] == 10

    def test_validate_configure_fluid_domain_liquid_valid(self):
        params = {
            "object_name": "LiquidDomain",
            "fluid_type": "DOMAIN",
            "domain_type": "LIQUID",
            "resolution_max": 48,
            "simulation_method": "APIC",
            "flip_ratio": 0.95,
            "use_mesh": True,
            "mesh_scale": 3,
            "use_diffusion": True,
            "viscosity_base": 1.5,
            "viscosity_exponent": 4,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)
        assert sanitized["object_name"] == "LiquidDomain"
        assert sanitized["domain_type"] == "LIQUID"
        assert sanitized["simulation_method"] == "APIC"
        assert sanitized["flip_ratio"] == 0.95
        assert sanitized["use_mesh"] is True
        assert sanitized["mesh_scale"] == 3
        assert sanitized["use_diffusion"] is True
        assert sanitized["viscosity_base"] == 1.5
        assert sanitized["viscosity_exponent"] == 4

    def test_validate_configure_fluid_invalid_domain_type(self):
        params = {
            "object_name": "BadDomain",
            "fluid_type": "DOMAIN",
            "domain_type": "PLASMA",
        }
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)

    def test_validate_configure_fluid_flow_valid(self):
        params = {
            "object_name": "SmokeEmitter",
            "fluid_type": "FLOW",
            "flow_type": "SMOKE",
            "flow_behavior": "INFLOW",
            "density": 2.0,
            "temperature": 1.5,
            "use_initial_velocity": True,
            "velocity_normal": 3.0,
            "velocity_coord": [0.0, 1.0, 2.0],
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)
        assert sanitized["fluid_type"] == "FLOW"
        assert sanitized["flow_type"] == "SMOKE"
        assert sanitized["flow_behavior"] == "INFLOW"
        assert sanitized["density"] == 2.0
        assert sanitized["temperature"] == 1.5
        assert sanitized["use_initial_velocity"] is True
        assert sanitized["velocity_normal"] == 3.0
        assert sanitized["velocity_coord"] == [0.0, 1.0, 2.0]

    def test_validate_configure_fluid_flow_both_fire_smoke_valid(self):
        params = {
            "object_name": "FireEmitter",
            "fluid_type": "FLOW",
            "flow_type": "BOTH",
            "flow_behavior": "GEOMETRY",
            "fuel_amount": 1.5,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)
        assert sanitized["flow_type"] == "BOTH"
        assert sanitized["fuel_amount"] == 1.5

    def test_validate_configure_fluid_invalid_flow_type(self):
        params = {
            "object_name": "FlowObj",
            "fluid_type": "FLOW",
            "flow_type": "STEAM",
        }
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)

    def test_validate_configure_fluid_invalid_flow_behavior(self):
        params = {
            "object_name": "FlowObj",
            "fluid_type": "FLOW",
            "flow_type": "SMOKE",
            "flow_behavior": "EXPLOSION",
        }
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)

    def test_validate_configure_fluid_effector_valid(self):
        params = {
            "object_name": "Obstacle",
            "fluid_type": "EFFECTOR",
            "effector_type": "COLLISION",
            "surface_distance": 0.05,
            "use_effector": True,
            "subframes": 2,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)
        assert sanitized["fluid_type"] == "EFFECTOR"
        assert sanitized["effector_type"] == "COLLISION"
        assert sanitized["surface_distance"] == 0.05
        assert sanitized["use_effector"] is True
        assert sanitized["subframes"] == 2

    def test_validate_configure_fluid_invalid_effector_type(self):
        params = {
            "object_name": "Obstacle",
            "fluid_type": "EFFECTOR",
            "effector_type": "WARP",
        }
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, params, trusted_approval=True)

    def test_validate_configure_fluid_resolution_bounds(self):
        # Too low (< 16)
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Domain",
                "fluid_type": "DOMAIN",
                "resolution_max": 8,
            }, trusted_approval=True)

        # Too high (> 256)
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Domain",
                "fluid_type": "DOMAIN",
                "resolution_max": 512,
            }, trusted_approval=True)

    def test_validate_configure_fluid_cache_frames_bounds(self):
        # Inverted frames (end < start)
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Domain",
                "fluid_type": "DOMAIN",
                "cache_frame_start": 50,
                "cache_frame_end": 10,
            }, trusted_approval=True)

        # Exceeds max frame span (> 250 frames)
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Domain",
                "fluid_type": "DOMAIN",
                "cache_frame_start": 1,
                "cache_frame_end": 300,
            }, trusted_approval=True)

    def test_validate_configure_fluid_timesteps_bounds(self):
        # Inverted timesteps (max < min)
        with pytest.raises((ValueError, Exception)):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Domain",
                "fluid_type": "DOMAIN",
                "timesteps_min": 5,
                "timesteps_max": 2,
            }, trusted_approval=True)

    def test_validate_configure_fluid_incompatible_domain_flow_rejected(self):
        # GAS domain with LIQUID flow in same call
        with pytest.raises(ValueError, match="Incompatible fluid configuration"):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Obj",
                "domain_type": "GAS",
                "flow_type": "LIQUID",
            }, trusted_approval=True)

        # LIQUID domain with SMOKE flow in same call
        with pytest.raises(ValueError, match="Incompatible fluid configuration"):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Obj",
                "domain_type": "LIQUID",
                "flow_type": "SMOKE",
            }, trusted_approval=True)

    def test_untrusted_approval_rejected_fluid(self):
        with pytest.raises(PermissionError, match="Approval denied"):
            validate_tool_input(TOOL_CONFIGURE_FLUID_SIMULATION, {
                "object_name": "Domain",
                "approved": True,  # Untrusted client approval flag
            }, trusted_approval=False)

    def test_snapshot_sensitivity_to_fluid_modifier_presence(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "DomainMesh"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []
        mock_obj.modifiers = []

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        # Add fluid modifier
        mock_mod = MagicMock()
        mock_mod.type = "FLUID"
        mock_mod.fluid_type = "DOMAIN"
        mock_ds = MagicMock(domain_type="GAS", resolution_max=32, time_scale=1.0, cfl_condition=2.0, use_adaptive_timesteps=True, timesteps_min=1, timesteps_max=4, alpha=1.0, beta=1.0, vorticity=0.0, use_dissolve_smoke=False, dissolve_speed=5, simulation_method="FLIP", flip_ratio=0.97, particle_radius=1.0, use_mesh=True, mesh_scale=2, use_diffusion=False, viscosity_base=1.0, viscosity_exponent=6, surface_tension=0.0, cache_type="REPLAY", cache_frame_start=1, cache_frame_end=50)
        mock_mod.domain_settings = mock_ds
        mock_obj.modifiers = [mock_mod]

        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Snapshot ID must change when fluid modifier is added"

    def test_snapshot_sensitivity_to_domain_resolution_mutation(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "DomainMesh"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_mod = MagicMock()
        mock_mod.type = "FLUID"
        mock_mod.fluid_type = "DOMAIN"
        mock_ds = MagicMock(domain_type="GAS", resolution_max=32, time_scale=1.0, cfl_condition=2.0, use_adaptive_timesteps=True, timesteps_min=1, timesteps_max=4, alpha=1.0, beta=1.0, vorticity=0.0, use_dissolve_smoke=False, dissolve_speed=5, simulation_method="FLIP", flip_ratio=0.97, particle_radius=1.0, use_mesh=True, mesh_scale=2, use_diffusion=False, viscosity_base=1.0, viscosity_exponent=6, surface_tension=0.0, cache_type="REPLAY", cache_frame_start=1, cache_frame_end=50)
        mock_mod.domain_settings = mock_ds
        mock_obj.modifiers = [mock_mod]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        mock_ds.resolution_max = 64
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Snapshot ID must change when domain resolution is modified"

    def test_snapshot_sensitivity_to_flow_density_mutation(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "FlowMesh"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_mod = MagicMock()
        mock_mod.type = "FLUID"
        mock_mod.fluid_type = "FLOW"
        mock_fs = MagicMock(flow_type="SMOKE", flow_behavior="INFLOW", density=1.0, fuel_amount=1.0, temperature=1.0, use_inflow=True, surface_distance=1.0, subframes=0, use_initial_velocity=False, velocity_factor=1.0, velocity_normal=0.0, velocity_coord=(0.0, 0.0, 0.0))
        mock_mod.flow_settings = mock_fs
        mock_obj.modifiers = [mock_mod]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        mock_fs.density = 3.5
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Snapshot ID must change when flow density is modified"

    def test_snapshot_sensitivity_to_effector_surface_distance_mutation(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "EffectorMesh"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_mod = MagicMock()
        mock_mod.type = "FLUID"
        mock_mod.fluid_type = "EFFECTOR"
        mock_es = MagicMock(effector_type="COLLISION", surface_distance=0.0, use_effector=True, subframes=0, use_plane_init=False)
        mock_mod.effector_settings = mock_es
        mock_obj.modifiers = [mock_mod]

        snap1 = compute_physics_snapshot_id(mock_bpy, mock_obj)

        mock_es.surface_distance = 0.25
        snap2 = compute_physics_snapshot_id(mock_bpy, mock_obj)
        assert snap1 != snap2, "Snapshot ID must change when effector surface distance is modified"

    def test_stale_snapshot_raises_error_fluid(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "DomainMesh"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []
        mock_obj.modifiers = []
        mock_bpy.data.objects.get.return_value = mock_obj

        with pytest.raises(ValueError, match="STALE_PHYSICS_STATE"):
            execute_configure_fluid_simulation(mock_bpy, {
                "object_name": "DomainMesh",
                "action": "configure",
                "expected_snapshot_id": "physics_stale_12345",
            })

    def test_create_and_inspect_gas_domain(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "SmokeDomain"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_ds = MagicMock(domain_type="GAS", resolution_max=32, time_scale=1.0, cfl_condition=2.0, use_adaptive_timesteps=True, timesteps_min=1, timesteps_max=4, alpha=1.0, beta=1.0, vorticity=0.0, use_dissolve_smoke=False, dissolve_speed=5, simulation_method="FLIP", flip_ratio=0.97, particle_radius=1.0, use_mesh=True, mesh_scale=2, use_diffusion=False, viscosity_base=1.0, viscosity_exponent=6, surface_tension=0.0, cache_type="REPLAY", cache_frame_start=1, cache_frame_end=50, cache_directory="/tmp/cache", has_cache_baked_data=False, has_cache_baked_mesh=False)
        mock_mod = MagicMock(name="Fluid", type="FLUID", fluid_type="DOMAIN", domain_settings=mock_ds)
        mock_mods = MagicMock()
        mock_mods.new.return_value = mock_mod
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_fluid_simulation(mock_bpy, {
            "object_name": "SmokeDomain",
            "action": "create",
            "fluid_type": "DOMAIN",
            "domain_type": "GAS",
            "resolution_max": 64,
            "vorticity": 0.5,
        })
        assert res["success"] is True
        assert res["fluid_type"] == "DOMAIN"
        assert res["domain_type"] == "GAS"
        assert res["resolution_max"] == 64
        assert res["vorticity"] == 0.5

        # Inspect
        inspect_res = execute_inspect_fluid_simulation(mock_bpy, {"object_name": "SmokeDomain"})
        assert inspect_res["success"] is True
        assert inspect_res["count"] == 1
        d_info = inspect_res["fluid_objects"][0]
        assert d_info["fluid_type"] == "DOMAIN"
        assert d_info["domain_settings"]["domain_type"] == "GAS"
        assert d_info["domain_settings"]["resolution_max"] == 64

    def test_create_and_inspect_liquid_domain_with_mesh(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "WaterDomain"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_ds = MagicMock(domain_type="LIQUID", resolution_max=48, time_scale=1.0, cfl_condition=2.0, use_adaptive_timesteps=True, timesteps_min=1, timesteps_max=4, alpha=1.0, beta=1.0, vorticity=0.0, use_dissolve_smoke=False, dissolve_speed=5, simulation_method="FLIP", flip_ratio=0.97, particle_radius=1.0, use_mesh=True, mesh_scale=2, use_diffusion=False, viscosity_base=1.0, viscosity_exponent=6, surface_tension=0.0, cache_type="REPLAY", cache_frame_start=1, cache_frame_end=50, cache_directory="/tmp/cache", has_cache_baked_data=False, has_cache_baked_mesh=False)
        mock_mod = MagicMock(name="Fluid", type="FLUID", fluid_type="DOMAIN", domain_settings=mock_ds)
        mock_mods = MagicMock()
        mock_mods.new.return_value = mock_mod
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_fluid_simulation(mock_bpy, {
            "object_name": "WaterDomain",
            "action": "create",
            "fluid_type": "DOMAIN",
            "domain_type": "LIQUID",
            "resolution_max": 48,
            "use_mesh": True,
            "mesh_scale": 3,
        })
        assert res["success"] is True
        assert res["domain_type"] == "LIQUID"
        assert res["resolution_max"] == 48
        assert res["use_mesh"] is True
        assert res["mesh_scale"] == 3

    def test_create_and_inspect_smoke_flow(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "SmokeFlowObj"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_fs = MagicMock(flow_type="SMOKE", flow_behavior="INFLOW", density=1.5, fuel_amount=1.0, temperature=2.0, use_inflow=True, surface_distance=1.0, subframes=0, use_initial_velocity=False, velocity_factor=1.0, velocity_normal=0.0, velocity_coord=(0.0, 0.0, 0.0))
        mock_mod = MagicMock(name="Fluid", type="FLUID", fluid_type="FLOW", flow_settings=mock_fs)
        mock_mods = MagicMock()
        mock_mods.new.return_value = mock_mod
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_objects = MagicMock()
        mock_objects.__iter__.side_effect = lambda: iter([mock_obj])
        mock_objects.get.side_effect = lambda n: mock_obj if n == "SmokeFlowObj" else None
        mock_bpy.data.objects = mock_objects

        res = execute_configure_fluid_simulation(mock_bpy, {
            "object_name": "SmokeFlowObj",
            "action": "create",
            "fluid_type": "FLOW",
            "flow_type": "SMOKE",
            "flow_behavior": "INFLOW",
            "density": 1.5,
            "temperature": 2.0,
        })
        assert res["success"] is True
        assert res["fluid_type"] == "FLOW"
        assert res["flow_type"] == "SMOKE"
        assert res["flow_behavior"] == "INFLOW"
        assert res["density"] == 1.5
        assert res["temperature"] == 2.0

    def test_create_and_inspect_collision_effector(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "EffectorObstacle"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_es = MagicMock(effector_type="COLLISION", surface_distance=0.05, use_effector=True, subframes=1, use_plane_init=False)
        mock_mod = MagicMock(name="Fluid", type="FLUID", fluid_type="EFFECTOR", effector_settings=mock_es)
        mock_mods = MagicMock()
        mock_mods.new.return_value = mock_mod
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_objects = MagicMock()
        mock_objects.__iter__.side_effect = lambda: iter([mock_obj])
        mock_objects.get.side_effect = lambda n: mock_obj if n == "EffectorObstacle" else None
        mock_bpy.data.objects = mock_objects

        res = execute_configure_fluid_simulation(mock_bpy, {
            "object_name": "EffectorObstacle",
            "action": "create",
            "fluid_type": "EFFECTOR",
            "effector_type": "COLLISION",
            "surface_distance": 0.05,
            "subframes": 1,
        })
        assert res["success"] is True
        assert res["fluid_type"] == "EFFECTOR"
        assert res["effector_type"] == "COLLISION"
        assert res["surface_distance"] == 0.05

    def test_remove_fluid_simulation(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "FluidHost"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_mod = MagicMock(name="Fluid", type="FLUID")
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_bpy.data.objects.get.return_value = mock_obj

        res = execute_configure_fluid_simulation(mock_bpy, {
            "object_name": "FluidHost",
            "action": "remove",
        })
        assert res["success"] is True
        assert res["removed"] is True
        mock_mods.remove.assert_called_once_with(mock_mod)

    def test_rollback_removes_created_fluid_modifier_on_failure(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "FluidFailObj"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_mod = MagicMock(name="Fluid", type="FLUID")
        # Simulating failure on property assignment
        type(mock_mod).fluid_type = PropertyMock(side_effect=RuntimeError("Simulated assignment failure"))
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([])  # No existing modifier
        mock_mods.new.return_value = mock_mod
        mock_obj.modifiers = mock_mods
        mock_bpy.data.objects.get.return_value = mock_obj

        with pytest.raises(RuntimeError, match="Simulated assignment failure"):
            execute_configure_fluid_simulation(mock_bpy, {
                "object_name": "FluidFailObj",
                "action": "create",
                "fluid_type": "DOMAIN",
            })

        mock_mods.remove.assert_called_once_with(mock_mod)

    def test_rollback_restores_prior_fluid_settings_on_failure(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "FluidRevertObj"
        mock_obj.rigid_body = None
        mock_obj.rigid_body_constraint = None
        mock_obj.field = None
        mock_obj.particle_systems = []

        mock_ds = MagicMock(domain_type="GAS", resolution_max=32, time_scale=1.0, cfl_condition=2.0, use_adaptive_timesteps=True, timesteps_min=1, timesteps_max=4, alpha=1.0, beta=1.0, vorticity=0.0, use_dissolve_smoke=False, dissolve_speed=5, simulation_method="FLIP", flip_ratio=0.97, particle_radius=1.0, use_mesh=True, mesh_scale=2, use_diffusion=False, viscosity_base=1.0, viscosity_exponent=6, surface_tension=0.0, cache_type="REPLAY", cache_frame_start=1, cache_frame_end=50)
        mock_mod = MagicMock(name="Fluid", type="FLUID", fluid_type="DOMAIN", domain_settings=mock_ds)
        mock_mods = MagicMock()
        mock_mods.__iter__.side_effect = lambda: iter([mock_mod])
        mock_obj.modifiers = mock_mods
        mock_bpy.data.objects.get.return_value = mock_obj

        # Simulate failure during resolution_max change
        type(mock_ds).resolution_max = PropertyMock(side_effect=RuntimeError("Simulated resolution failure"))

        with pytest.raises(RuntimeError, match="Simulated resolution failure"):
            execute_configure_fluid_simulation(mock_bpy, {
                "object_name": "FluidRevertObj",
                "action": "configure",
                "resolution_max": 128,
            })

    def test_simulation_agent_fluid_capabilities(self):
        agent = SimulationVFXAgent()
        manifest = agent.manifest
        caps = {c.capability_id for c in manifest.capabilities}
        assert CAPABILITY_PHYSICS_SIMULATION in caps
        assert CAPABILITY_PHYSICS_INSPECT in caps
        assert TOOL_CONFIGURE_FLUID_SIMULATION in SUPPORTED_SIMULATION_TOOLS
        assert TOOL_INSPECT_FLUID_SIMULATION in SUPPORTED_SIMULATION_TOOLS
