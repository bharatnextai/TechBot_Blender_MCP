from tests.unit.modeling_approval_fixture import approved
import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_CREATE_CURVE_OR_TEXT,
    TOOL_CREATE_CURVE,
    TOOL_CREATE_TEXT,
    TOOL_MANAGE_SHADER_NODES,
    TOOL_CONNECT_SHADER_NODES,
    TOOL_MANAGE_NODES,
    TOOL_BAKE_OBJECT_TEXTURE,
    TOOL_BAKE_TEXTURE,
    TOOL_BAKE_MATERIALS,
    TOOL_MANAGE_COMPOSITOR_NODES,
    TOOL_CONFIGURE_COMPOSITOR,
    TOOL_MANAGE_COMPOSITOR,
    TOOL_CONFIGURE_ANIMATION_CURVE,
    TOOL_MANAGE_FCURVE,
    TOOL_SET_KEYFRAME_INTERPOLATION,
    TOOL_MANAGE_ACTION_SLOTS,
    TOOL_CONFIGURE_PHYSICS,
    TOOL_SETUP_PHYSICS,
    TOOL_MANAGE_PHYSICS,
    TOOL_OPEN_BLEND_FILE,
    TOOL_OPEN_PROJECT,
    TOOL_LOAD_BLEND_FILE,
    validate_tool_input,
)
from mcp_service.agents.modeling import (
    ModelingAgent,
    CAPABILITY_MODELING_OBJECT_OPS,
    CAPABILITY_MODELING_KEYFRAME,
    CAPABILITY_MODELING_ASSET_IO,
)
from mcp_service.agents.materials import (
    MaterialsAgent,
    CAPABILITY_MATERIALS_MANAGE,
)
from mcp_service.agents.render_lighting import (
    RenderLightingAgent,
    CAPABILITY_WORLD_MANAGE,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_create_curve_or_text,
    handle_manage_shader_nodes,
    handle_bake_object_texture,
    handle_manage_compositor_nodes,
    handle_configure_animation_curve,
    handle_configure_physics,
    handle_open_blend_file,
    handle_execute_blender_code,
    ALL_HANDLERS,
)


class TestTask76Capabilities(unittest.TestCase):
    """
    Unit tests for TASK-UMCP-0076: 100% Blender 5.2.2 LTS Functional Coverage Closure.
    Covers the 7 remaining capabilities, schemas, input validations, agent routing,
    approval gating, and handler logic.
    """

    def test_schema_definitions_and_aliases_registered(self):
        tools_to_check = [
            (TOOL_CREATE_CURVE_OR_TEXT, TOOL_CREATE_CURVE, TOOL_CREATE_TEXT),
            (TOOL_MANAGE_SHADER_NODES, TOOL_CONNECT_SHADER_NODES, TOOL_MANAGE_NODES),
            (TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS),
            (TOOL_MANAGE_COMPOSITOR_NODES, TOOL_CONFIGURE_COMPOSITOR, TOOL_MANAGE_COMPOSITOR),
            (TOOL_CONFIGURE_ANIMATION_CURVE, TOOL_MANAGE_FCURVE, TOOL_SET_KEYFRAME_INTERPOLATION, TOOL_MANAGE_ACTION_SLOTS),
            (TOOL_CONFIGURE_PHYSICS, TOOL_SETUP_PHYSICS, TOOL_MANAGE_PHYSICS),
            (TOOL_OPEN_BLEND_FILE, TOOL_OPEN_PROJECT, TOOL_LOAD_BLEND_FILE),
        ]
        for primary_and_aliases in tools_to_check:
            primary = primary_and_aliases[0]
            self.assertIn(primary, TOOL_DEFINITIONS)
            self.assertIn(primary, ALL_HANDLERS)
            for alias in primary_and_aliases[1:]:
                self.assertIn(alias, TOOL_DEFINITIONS)
                self.assertIn(alias, ALL_HANDLERS)

    def test_input_validation_rules(self):
        # 1. create_curve_or_text
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_CURVE_OR_TEXT, {"name": ""}, trusted_approval=True)
        sanitized = validate_tool_input(TOOL_CREATE_CURVE_OR_TEXT, {"name": "MyCurve", "curve_type": "bezier"}, trusted_approval=True)
        self.assertEqual(sanitized["curve_type"], "BEZIER")

        # 2. manage_shader_nodes
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_MANAGE_SHADER_NODES, {"target_name": ""}, trusted_approval=True)
        sanitized = validate_tool_input(TOOL_MANAGE_SHADER_NODES, {"target_name": "Mat1", "action": "list_nodes"}, trusted_approval=True)
        self.assertEqual(sanitized["action"], "list_nodes")

        # 3. bake_object_texture
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_BAKE_OBJECT_TEXTURE, {"object_name": ""}, trusted_approval=True)
        sanitized = validate_tool_input(TOOL_BAKE_OBJECT_TEXTURE, {"object_name": "Cube", "bake_type": "diffuse"}, trusted_approval=True)
        self.assertEqual(sanitized["bake_type"], "DIFFUSE")

        # 4. manage_compositor_nodes
        sanitized = validate_tool_input(TOOL_MANAGE_COMPOSITOR_NODES, {"action": "enable"}, trusted_approval=True)
        self.assertEqual(sanitized["action"], "enable")

        # 5. configure_animation_curve
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_ANIMATION_CURVE, {"object_name": ""}, trusted_approval=True)
        sanitized = validate_tool_input(TOOL_CONFIGURE_ANIMATION_CURVE, {"object_name": "Cube", "interpolation": "linear"}, trusted_approval=True)
        self.assertEqual(sanitized["interpolation"], "LINEAR")

        # 6. configure_physics
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_PHYSICS, {"object_name": ""}, trusted_approval=True)
        sanitized = validate_tool_input(TOOL_CONFIGURE_PHYSICS, {"object_name": "Cube", "physics_type": "cloth"}, trusted_approval=True)
        self.assertEqual(sanitized["physics_type"], "CLOTH")

        # 7. open_blend_file
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_OPEN_BLEND_FILE, {"filepath": ""}, trusted_approval=True)
        sanitized = validate_tool_input(TOOL_OPEN_BLEND_FILE, {"filepath": "project.blend", "confirm_discard_unsaved": True}, trusted_approval=True)
        self.assertTrue(sanitized["confirm_discard_unsaved"])

    def test_agent_capability_registration(self):
        # ModelingAgent checks
        modeling = ModelingAgent()
        manifest_m = modeling.get_manifest()
        caps_m = {c.capability_id: c.supported_task_types for c in manifest_m.capabilities}

        self.assertIn(TOOL_CREATE_CURVE_OR_TEXT, caps_m[CAPABILITY_MODELING_OBJECT_OPS])
        self.assertIn(TOOL_CONFIGURE_PHYSICS, caps_m[CAPABILITY_MODELING_OBJECT_OPS])
        self.assertIn(TOOL_CONFIGURE_ANIMATION_CURVE, caps_m[CAPABILITY_MODELING_KEYFRAME])
        self.assertIn(TOOL_OPEN_BLEND_FILE, caps_m[CAPABILITY_MODELING_ASSET_IO])

        # MaterialsAgent checks
        materials = MaterialsAgent()
        manifest_mat = materials.get_manifest()
        caps_mat = {c.capability_id: c.supported_task_types for c in manifest_mat.capabilities}
        self.assertIn(TOOL_MANAGE_SHADER_NODES, caps_mat[CAPABILITY_MATERIALS_MANAGE])
        self.assertIn(TOOL_BAKE_OBJECT_TEXTURE, caps_mat[CAPABILITY_MATERIALS_MANAGE])

        # RenderLightingAgent checks
        lighting = RenderLightingAgent()
        manifest_l = lighting.get_manifest()
        caps_l = {c.capability_id: c.supported_task_types for c in manifest_l.capabilities}
        self.assertIn(TOOL_MANAGE_COMPOSITOR_NODES, caps_l[CAPABILITY_WORLD_MANAGE])

    def test_approval_rejection_fail_closed(self):
        mock_bpy = MagicMock()
        mock_reg = MagicMock()

        with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=mock_reg), \
             patch("blender_addon.universal_mcp.bridge.handlers.is_approval_required", return_value=True):
            
            mutating_calls = [
                (handle_create_curve_or_text, {"name": "C1"}),
                (handle_manage_shader_nodes, {"target_name": "M1", "action": "create_node", "node_type": "ShaderNodeBsdfDiffuse"}),
                (handle_bake_object_texture, {"object_name": "Cube"}),
                (handle_manage_compositor_nodes, {"action": "create_node", "node_type": "CompositorNodeBlur"}),
                (handle_configure_animation_curve, {"object_name": "Cube", "action": "set_interpolation"}),
                (handle_configure_physics, {"object_name": "Cube", "action": "add"}),
                (handle_open_blend_file, {"filepath": "scene.blend"}),
            ]
            for handler_fn, params in mutating_calls:
                # 1. Missing credentials
                with self.assertRaises(PermissionError):
                    handler_fn(bpy_module=mock_bpy, params=dict(params))

                # 2. Untrusted approved=True
                with self.assertRaises(PermissionError):
                    p = dict(params)
                    p["approved"] = True
                    handler_fn(bpy_module=mock_bpy, params=p)

    def test_handle_create_curve_or_text_logic(self):
        # Mapping/authorization fixture only; native geometry is tested through MCP.
        from unittest.mock import patch
        mock_bpy=MagicMock()
        mock_bpy.data.objects.__getitem__.return_value.location=[0,0,0]
        with patch("blender_addon.universal_mcp.bridge.curve_tools._configure_curve_after_approval",return_value={"name":"TestCurve","success":True,"verified":True}) as core:
            res=handle_create_curve_or_text(mock_bpy,approved('create_curve_or_text',{'name':'TestCurve','curve_type':'BEZIER'}))
        self.assertTrue(res['created']);self.assertEqual(res['curve_type'],'BEZIER')
        self.assertEqual(core.call_args.args[1]['splines'][0]['type'],'BEZIER')
        self.assertEqual(len(core.call_args.args[1]['splines'][0]['points']),2)

    def test_handle_manage_shader_nodes_logic(self):
        mock_bpy = MagicMock()
        mock_mat = MagicMock()
        mock_node = MagicMock()
        mock_node.name = "Emission"
        mock_node.type = "EMISSION"
        mock_mat.node_tree.nodes.new.return_value = mock_node
        mock_bpy.data.materials.get.return_value = mock_mat

        res = handle_manage_shader_nodes(
            bpy_module=mock_bpy,
            params={
                "target_name": "Mat1",
                "action": "create_node",
                "node_type": "ShaderNodeEmission",
                "trusted_approval": True,
                "_trusted_test_override": True,
            },
        )
        self.assertTrue(res["created"])
        self.assertEqual(res["node_name"], "Emission")

    def test_handle_configure_physics_logic(self):
        mock_bpy = MagicMock()
        mock_obj = MagicMock()
        mock_obj.name = "RigidCube"
        mock_rb = MagicMock()
        mock_rb.type = "ACTIVE"
        mock_rb.mass = 2.5
        mock_obj.rigid_body = mock_rb
        mock_bpy.data.objects.get.return_value = mock_obj

        res = handle_configure_physics(
            bpy_module=mock_bpy,
            params={
                "object_name": "RigidCube",
                "physics_type": "RIGID_BODY",
                "action": "configure",
                "mass": 2.5,
                "trusted_approval": True,
                "_trusted_test_override": True,
            },
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["physics_type"], "RIGID_BODY")
        self.assertEqual(res["mass"], 2.5)

    def test_handle_open_blend_file_logic(self):
        mock_bpy = MagicMock()
        mock_bpy.data.is_dirty = False
        mock_bpy.data.objects = [MagicMock(), MagicMock()]

        with tempfile.NamedTemporaryFile(suffix=".blend", delete=False) as f:
            temp_blend_path = f.name

        try:
            res = handle_open_blend_file(
                bpy_module=mock_bpy,
                params={
                    "filepath": temp_blend_path,
                    "confirm_discard_unsaved": True,
                    "trusted_approval": True,
                "_trusted_test_override": True,
                },
            )
            self.assertTrue(res["opened"])
            self.assertEqual(res["object_count"], 2)
            mock_bpy.ops.wm.open_mainfile.assert_called_once()
        finally:
            if os.path.exists(temp_blend_path):
                os.remove(temp_blend_path)


if __name__ == "__main__":
    unittest.main()
