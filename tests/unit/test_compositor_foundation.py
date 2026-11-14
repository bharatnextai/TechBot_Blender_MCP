"""
Unit tests for Compositor Pipelines Foundation (Phase 2.1 - v0.1.74).
Verifies node whitelisting, alias resolution, parameter bounds,
render pass validation, snapshot determinism, stale-state protection,
and fail-closed approval invariants without requiring live Blender.
"""

import pytest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_MANAGE_COMPOSITOR_NODES,
    TOOL_CONFIGURE_COMPOSITOR,
    TOOL_MANAGE_COMPOSITOR,
    TOOL_INSPECT_COMPOSITOR_PIPELINE,
    ALLOWED_INSPECT_CATEGORIES,
    PERMISSION_READ_ONLY,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from blender_addon.universal_mcp.bridge.compositor_foundation import (
    WHITELISTED_COMPOSITOR_NODES,
    ALLOWED_RENDER_PASSES,
    GLARE_TYPE_MAP,
    QUALITY_MAP,
    canonical_node_type,
    compute_compositor_snapshot,
    find_socket,
    execute_compositor_action,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_manage_compositor_nodes,
    handle_inspect_compositor_pipeline,
    ALL_HANDLERS,
    READ_ONLY_HANDLERS,
    _LOCAL_TEST_TOOLS,
)


class TestCompositorWhitelisting:
    """Verifies strict whitelisting for the 9 supported compositor node types."""

    def test_canonical_aliases(self):
        # 1. Render Layers
        assert canonical_node_type("render_layers") == "CompositorNodeRLayers"
        assert canonical_node_type("compositor_rlayers") == "CompositorNodeRLayers"
        assert canonical_node_type("rlayers") == "CompositorNodeRLayers"
        assert canonical_node_type("CompositorNodeRLayers") == "CompositorNodeRLayers"

        # 2. Composite / Group Output
        assert canonical_node_type("composite") == "NodeGroupOutput"
        assert canonical_node_type("group_output") == "NodeGroupOutput"
        assert canonical_node_type("NodeGroupOutput") == "NodeGroupOutput"

        # 3. Viewer
        assert canonical_node_type("viewer") == "CompositorNodeViewer"
        assert canonical_node_type("CompositorNodeViewer") == "CompositorNodeViewer"

        # 4. Denoise
        assert canonical_node_type("denoise") == "CompositorNodeDenoise"
        assert canonical_node_type("CompositorNodeDenoise") == "CompositorNodeDenoise"

        # 5. Color Balance
        assert canonical_node_type("color_balance") == "CompositorNodeColorBalance"
        assert canonical_node_type("colorbalance") == "CompositorNodeColorBalance"
        assert canonical_node_type("CompositorNodeColorBalance") == "CompositorNodeColorBalance"

        # 6. Blur
        assert canonical_node_type("blur") == "CompositorNodeBlur"
        assert canonical_node_type("CompositorNodeBlur") == "CompositorNodeBlur"

        # 7. Glare
        assert canonical_node_type("glare") == "CompositorNodeGlare"
        assert canonical_node_type("CompositorNodeGlare") == "CompositorNodeGlare"

        # 8. Alpha Over
        assert canonical_node_type("alpha_over") == "CompositorNodeAlphaOver"
        assert canonical_node_type("alphaover") == "CompositorNodeAlphaOver"
        assert canonical_node_type("CompositorNodeAlphaOver") == "CompositorNodeAlphaOver"

        # 9. Output File
        assert canonical_node_type("output_file") == "CompositorNodeOutputFile"
        assert canonical_node_type("file_output") == "CompositorNodeOutputFile"
        assert canonical_node_type("CompositorNodeOutputFile") == "CompositorNodeOutputFile"

        # 10. Cryptomatte (Milestone 9.1B)
        assert canonical_node_type("cryptomatte") == "CompositorNodeCryptomatteV2"
        assert canonical_node_type("cryptomatte_v2") == "CompositorNodeCryptomatteV2"
        assert canonical_node_type("compositornodecryptomattev2") == "CompositorNodeCryptomatteV2"
        assert canonical_node_type("CompositorNodeCryptomatteV2") == "CompositorNodeCryptomatteV2"

        # 11. Color Correction Nodes (Milestone 9.1C)
        # Curve RGB / Curve Color
        assert canonical_node_type("curve_color") == "CompositorNodeCurveRGB"
        assert canonical_node_type("curve_rgb") == "CompositorNodeCurveRGB"
        assert canonical_node_type("rgb_curves") == "CompositorNodeCurveRGB"
        assert canonical_node_type("curves") == "CompositorNodeCurveRGB"
        assert canonical_node_type("CompositorNodeCurveColor") == "CompositorNodeCurveRGB"
        assert canonical_node_type("CompositorNodeCurveRGB") == "CompositorNodeCurveRGB"

        # Hue Saturation Value
        assert canonical_node_type("hue_sat") == "CompositorNodeHueSat"
        assert canonical_node_type("huesat") == "CompositorNodeHueSat"
        assert canonical_node_type("hue_saturation") == "CompositorNodeHueSat"
        assert canonical_node_type("hsv") == "CompositorNodeHueSat"
        assert canonical_node_type("CompositorNodeHueSat") == "CompositorNodeHueSat"

        # Exposure
        assert canonical_node_type("exposure") == "CompositorNodeExposure"
        assert canonical_node_type("CompositorNodeExposure") == "CompositorNodeExposure"

        # Tonemap
        assert canonical_node_type("tonemap") == "CompositorNodeTonemap"
        assert canonical_node_type("tone_map") == "CompositorNodeTonemap"
        assert canonical_node_type("CompositorNodeTonemap") == "CompositorNodeTonemap"

    def test_unknown_node_type_rejected(self):
        unsupported = [
            "CompositorNodeBilateralblur",
            "CompositorNodeDisplace",
            "CompositorNodeMapValue",
            "CompositorNodeInvert",
            "ShaderNodeBsdfPrincipled",
            "ArbitraryMaliciousNode",
        ]
        for node_type in unsupported:
            with pytest.raises(ValueError, match="Unsupported compositor node type"):
                canonical_node_type(node_type)


class TestCompositorRenderPasses:
    """Verifies bounded render-pass whitelist and validation."""

    def test_allowed_render_passes(self):
        # Baseline passes
        assert "z" in ALLOWED_RENDER_PASSES
        assert "depth" in ALLOWED_RENDER_PASSES
        assert "normal" in ALLOWED_RENDER_PASSES
        assert "diffuse" in ALLOWED_RENDER_PASSES
        assert "glossy" in ALLOWED_RENDER_PASSES
        # Milestone 9.1A expanded passes
        assert "ao" in ALLOWED_RENDER_PASSES
        assert "ambient_occlusion" in ALLOWED_RENDER_PASSES
        assert "ambient occlusion" in ALLOWED_RENDER_PASSES
        assert "shadow" in ALLOWED_RENDER_PASSES
        assert "emission" in ALLOWED_RENDER_PASSES
        assert "emit" in ALLOWED_RENDER_PASSES
        assert "environment" in ALLOWED_RENDER_PASSES
        assert "env" in ALLOWED_RENDER_PASSES
        assert "mist" in ALLOWED_RENDER_PASSES

    def test_configure_expanded_render_passes_success(self):
        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = []
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_vl.name = "ViewLayer"
        mock_vl.use_pass_ambient_occlusion = False
        mock_vl.use_pass_shadow = False
        mock_vl.use_pass_emit = False
        mock_vl.use_pass_environment = False
        mock_vl.use_pass_mist = False

        mock_scene = MagicMock()
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = mock_vl

        res = execute_compositor_action(mock_bpy, {
            "action": "configure_render_passes",
            "passes": {
                "ao": True,
                "shadow": True,
                "emission": True,
                "environment": True,
                "mist": True,
            }
        })
        assert res["status"] == "success"
        assert res["verified"] is True
        assert mock_vl.use_pass_ambient_occlusion is True
        assert mock_vl.use_pass_shadow is True
        assert mock_vl.use_pass_emit is True
        assert mock_vl.use_pass_environment is True
        assert mock_vl.use_pass_mist is True
        assert res["snapshot_id"].startswith("sha256:")

    def test_cryptomatte_requires_dedicated_node_not_simple_toggle(self):
        """Cryptomatte is rejected as a standard render pass toggle and requires dedicated node support."""
        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = []
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_vl.name = "ViewLayer"

        mock_scene = MagicMock()
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = mock_vl

        with pytest.raises(ValueError, match="Unsupported render pass 'cryptomatte'"):
            execute_compositor_action(mock_bpy, {
                "action": "configure_render_passes",
                "passes": {"cryptomatte": True}
            })

    def test_unsupported_render_pass_rejected(self):
        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = []
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_vl.name = "ViewLayer"

        mock_scene = MagicMock()
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = mock_vl

        with pytest.raises(ValueError, match="Unsupported render pass 'specular'"):
            execute_compositor_action(mock_bpy, {
                "action": "configure_render_passes",
                "passes": {"specular": True}
            })

    def test_render_pass_value_must_be_bool(self):
        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = []
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_vl.name = "ViewLayer"

        mock_scene = MagicMock()
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = mock_vl

        with pytest.raises(ValueError, match="must be boolean"):
            execute_compositor_action(mock_bpy, {
                "action": "configure_render_passes",
                "passes": {"z": "not_a_bool"}
            })

    def test_socket_alias_resolution_for_new_passes(self):
        """Verifies find_socket resolves aliases for AO, shadow, emission, environment, and mist."""
        mock_node = MagicMock()
        mock_ao = MagicMock()
        mock_ao.name = "Ambient Occlusion"
        mock_shadow = MagicMock()
        mock_shadow.name = "Shadow"
        mock_emit = MagicMock()
        mock_emit.name = "Emission"
        mock_env = MagicMock()
        mock_env.name = "Environment"
        mock_mist = MagicMock()
        mock_mist.name = "Mist"
        mock_node.outputs = [mock_ao, mock_shadow, mock_emit, mock_env, mock_mist]

        assert find_socket(mock_node, "ao", is_output=True) == mock_ao
        assert find_socket(mock_node, "ambient_occlusion", is_output=True) == mock_ao
        assert find_socket(mock_node, "shadow", is_output=True) == mock_shadow
        assert find_socket(mock_node, "emission", is_output=True) == mock_emit
        assert find_socket(mock_node, "emit", is_output=True) == mock_emit
        assert find_socket(mock_node, "environment", is_output=True) == mock_env
        assert find_socket(mock_node, "env", is_output=True) == mock_env
        assert find_socket(mock_node, "mist", is_output=True) == mock_mist


class TestCompositorSnapshotAndConcurrency:
    """Verifies deterministic hashing and optimistic concurrency control."""

    def test_deterministic_snapshot(self):
        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = []
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_vl.use_pass_z = True
        mock_vl.use_pass_normal = False
        mock_vl.use_pass_diffuse_color = False
        mock_vl.use_pass_glossy_color = False

        snap1, _ = compute_compositor_snapshot(mock_tree, mock_vl)
        snap2, _ = compute_compositor_snapshot(mock_tree, mock_vl)
        assert snap1 == snap2
        assert snap1.startswith("sha256:")

        mock_vl.use_pass_normal = True
        snap3, _ = compute_compositor_snapshot(mock_tree, mock_vl)
        assert snap3 != snap1

    def test_stale_snapshot_rejection(self):
        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = []
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_scene = MagicMock()
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = mock_vl

        with pytest.raises(ValueError, match="STALE_COMPOSITOR_GRAPH"):
            execute_compositor_action(mock_bpy, {
                "action": "inspect",
                "expected_snapshot_id": "sha256:stale_hash_value_123456"
            })


class TestCompositorSchemasAndRegistry:
    """Verifies schema definitions, registry entries, and payload sanitization."""

    def test_tool_definitions_and_registry(self):
        registry = ToolRegistry()
        names = registry.tool_names

        assert TOOL_MANAGE_COMPOSITOR_NODES in names
        assert TOOL_CONFIGURE_COMPOSITOR in names
        assert TOOL_MANAGE_COMPOSITOR in names
        assert TOOL_INSPECT_COMPOSITOR_PIPELINE in names

        # Read-only verification
        inspect_def = registry.get_tool_definition(TOOL_INSPECT_COMPOSITOR_PIPELINE)
        assert inspect_def["permission_tier"] == PERMISSION_READ_ONLY

        # Mutation verification
        manage_def = registry.get_tool_definition(TOOL_MANAGE_COMPOSITOR_NODES)
        assert manage_def["permission_tier"] == PERMISSION_SCENE_MUTATION

    def test_allowed_inspect_categories(self):
        assert "compositor_pipeline" in ALLOWED_INSPECT_CATEGORIES
        assert "compositor_settings" in ALLOWED_INSPECT_CATEGORIES

    def test_handlers_registered(self):
        assert "manage_compositor_nodes" in ALL_HANDLERS
        assert "configure_compositor" in ALL_HANDLERS
        assert "manage_compositor" in ALL_HANDLERS
        assert "inspect_compositor_pipeline" in ALL_HANDLERS
        assert "inspect_compositor_pipeline" in READ_ONLY_HANDLERS
        assert "manage_compositor_nodes" in _LOCAL_TEST_TOOLS

    def test_validate_tool_input_actions(self):
        # Without trusted approval, mutation tool must raise PermissionError
        with pytest.raises(PermissionError, match="Approval required"):
            validate_tool_input(TOOL_MANAGE_COMPOSITOR_NODES, {"action": "enable"}, trusted_approval=False)

        # Valid actions with trusted approval
        for act in ("enable", "inspect", "create_node", "remove_node", "connect", "disconnect", "set_property", "list_nodes"):
            res = validate_tool_input(TOOL_MANAGE_COMPOSITOR_NODES, {"action": act}, trusted_approval=True)
            assert res["action"] == act

        # Configure render passes requires 'passes'
        with pytest.raises(ValueError, match="Parameter 'passes' .* is required"):
            validate_tool_input(TOOL_MANAGE_COMPOSITOR_NODES, {"action": "configure_render_passes"}, trusted_approval=True)

        res_passes = validate_tool_input(TOOL_MANAGE_COMPOSITOR_NODES, {
            "action": "configure_render_passes",
            "passes": {"z": True, "normal": True}
        }, trusted_approval=True)
        assert res_passes["action"] == "configure_render_passes"

        # Invalid action rejected by schema enum validation
        with pytest.raises(ValueError, match="Invalid value for 'action'"):
            validate_tool_input(TOOL_MANAGE_COMPOSITOR_NODES, {"action": "destroy_everything"}, trusted_approval=True)


class TestCompositorSecurityInvariants:
    """Verifies fail-closed security and rejection of untrusted approval."""

    def test_fail_closed_untrusted_approved(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene = MagicMock()

        with patch("blender_addon.universal_mcp.bridge.handlers.is_approval_required", return_value=True):
            with patch("blender_addon.universal_mcp.bridge.handlers._local_test_autoapproval", return_value=False):
                with pytest.raises(PermissionError, match="Missing trusted human approval credentials"):
                    handle_manage_compositor_nodes(mock_bpy, {
                        "action": "create_node",
                        "node_type": "glare",
                        "approved": True  # Untrusted client flag MUST NOT bypass approval!
                    })


class TestCryptomatteNodeFoundation:
    """Verifies dedicated CryptomatteV2 node support, properties, and fail-closed validation."""

    def test_cryptomatte_properties_and_socket_aliases(self):
        mock_cm = MagicMock()
        mock_cm.name = "MyCrypto"
        mock_in_img = MagicMock()
        mock_in_img.name = "Image"
        mock_cm.inputs = [mock_in_img]

        mock_out_img = MagicMock()
        mock_out_img.name = "Image"
        mock_out_mat = MagicMock()
        mock_out_mat.name = "Matte"
        mock_out_pick = MagicMock()
        mock_out_pick.name = "Pick"
        mock_cm.outputs = [mock_out_img, mock_out_mat, mock_out_pick]

        assert find_socket(mock_cm, "image", is_output=False) == mock_in_img
        assert find_socket(mock_cm, "Image", is_output=False) == mock_in_img
        assert find_socket(mock_cm, "matte", is_output=True) == mock_out_mat
        assert find_socket(mock_cm, "Matte", is_output=True) == mock_out_mat
        assert find_socket(mock_cm, "pick", is_output=True) == mock_out_pick
        assert find_socket(mock_cm, "Pick", is_output=True) == mock_out_pick

    def test_cryptomatte_set_property_success(self):
        mock_node = MagicMock()
        mock_node.name = "MyCrypto"
        mock_node.bl_idname = "CompositorNodeCryptomatteV2"
        mock_node.type = "CRYPTOMATTE_V2"
        mock_node.inputs = []
        mock_node.layer_name = "ViewLayer.CryptoObject"
        mock_node.matte_id = ""
        mock_node.source = "RENDER"

        mock_nodes = MagicMock()
        mock_nodes.get.return_value = mock_node
        mock_nodes.__iter__.return_value = [mock_node]

        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = mock_nodes
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_vl.name = "ViewLayer"

        mock_scene = MagicMock()
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = mock_vl

        # Test setting layer_name to material
        res_layer = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyCrypto",
            "property_name": "layer_name",
            "property_value": "material",
        })
        assert res_layer["status"] == "success"
        assert mock_node.layer_name == "ViewLayer.CryptoMaterial"

        # Test setting matte_id
        res_matte = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyCrypto",
            "property_name": "matte_id",
            "property_value": "Cube,Sphere",
        })
        assert res_matte["status"] == "success"
        assert mock_node.matte_id == "Cube,Sphere"

        # Test setting source to IMAGE
        res_source = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyCrypto",
            "property_name": "source",
            "property_value": "IMAGE",
        })
        assert res_source["status"] == "success"
        assert mock_node.source == "IMAGE"

    def test_cryptomatte_invalid_property_rejected(self):
        mock_node = MagicMock()
        mock_node.name = "MyCrypto"
        mock_node.bl_idname = "CompositorNodeCryptomatteV2"
        mock_node.type = "CRYPTOMATTE_V2"
        mock_node.inputs = []
        mock_node.layer_name = "ViewLayer.CryptoObject"
        mock_node.source = "RENDER"

        mock_nodes = MagicMock()
        mock_nodes.get.return_value = mock_node
        mock_nodes.__iter__.return_value = [mock_node]

        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = mock_nodes
        mock_tree.links = []

        mock_vl = MagicMock()
        mock_vl.name = "ViewLayer"

        mock_scene = MagicMock()
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree

        mock_bpy = MagicMock()
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = mock_vl

        # Invalid layer name target
        with pytest.raises(ValueError, match="Invalid Cryptomatte layer selection"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyCrypto",
                "property_name": "layer_name",
                "property_value": "invalid_lights_layer",
            })

        # Invalid source value
        with pytest.raises(ValueError, match="Invalid Cryptomatte source"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyCrypto",
                "property_name": "source",
                "property_value": "UNSUPPORTED_SOURCE",
            })

    def test_color_correction_socket_aliases(self):
        """Verifies find_socket resolves aliases for Exposure, HueSat, Tonemap, and CurveRGB."""
        mock_node = MagicMock()
        mock_exp = MagicMock(name="Exposure")
        mock_exp.name = "Exposure"
        mock_hue = MagicMock(name="Hue")
        mock_hue.name = "Hue"
        mock_sat = MagicMock(name="Saturation")
        mock_sat.name = "Saturation"
        mock_val = MagicMock(name="Value")
        mock_val.name = "Value"
        mock_fac = MagicMock(name="Factor")
        mock_fac.name = "Factor"
        mock_type = MagicMock(name="Type")
        mock_type.name = "Type"
        mock_key = MagicMock(name="Key")
        mock_key.name = "Key"
        mock_gamma = MagicMock(name="Gamma")
        mock_gamma.name = "Gamma"
        mock_black = MagicMock(name="Black Level")
        mock_black.name = "Black Level"
        mock_white = MagicMock(name="White Level")
        mock_white.name = "White Level"

        mock_node.inputs = [mock_exp, mock_hue, mock_sat, mock_val, mock_fac, mock_type, mock_key, mock_gamma, mock_black, mock_white]

        assert find_socket(mock_node, "exp") == mock_exp
        assert find_socket(mock_node, "exposure") == mock_exp
        assert find_socket(mock_node, "hue") == mock_hue
        assert find_socket(mock_node, "sat") == mock_sat
        assert find_socket(mock_node, "saturation") == mock_sat
        assert find_socket(mock_node, "val") == mock_val
        assert find_socket(mock_node, "value") == mock_val
        assert find_socket(mock_node, "fac") == mock_fac
        assert find_socket(mock_node, "factor") == mock_fac
        assert find_socket(mock_node, "type") == mock_type
        assert find_socket(mock_node, "key") == mock_key
        assert find_socket(mock_node, "gamma") == mock_gamma
        assert find_socket(mock_node, "black") == mock_black
        assert find_socket(mock_node, "black_level") == mock_black
        assert find_socket(mock_node, "white") == mock_white
        assert find_socket(mock_node, "white_level") == mock_white

    def test_color_correction_property_bounds_and_validations(self):
        """Verifies fail-closed validation for Exposure, HueSat, Tonemap, and CurveRGB."""
        # 1. Exposure
        mock_exp = MagicMock()
        mock_exp.name = "MyExp"
        mock_exp.bl_idname = "CompositorNodeExposure"
        s_exp = MagicMock()
        s_exp.name = "Exposure"
        mock_exp.inputs = [s_exp]

        mock_nodes = MagicMock()
        mock_nodes.get.return_value = mock_exp
        mock_nodes.__iter__.return_value = [mock_exp]

        mock_tree = MagicMock()
        mock_tree.name = "Scene_Compositor"
        mock_tree.nodes = mock_nodes
        mock_tree.links = []

        mock_bpy = MagicMock()
        mock_bpy.context.scene.compositing_node_group = mock_tree
        mock_bpy.context.view_layer.name = "ViewLayer"

        # Valid exposure
        res = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyExp",
            "property_name": "exposure",
            "property_value": 2.5,
        })
        assert res["status"] == "success"
        assert s_exp.default_value == 2.5

        # Out-of-bounds exposure (> 20.0)
        with pytest.raises(ValueError, match="Exposure must be between"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyExp",
                "property_name": "exposure",
                "property_value": 50.0,
            })

        # 2. Tonemap
        mock_tonemap = MagicMock()
        mock_tonemap.name = "MyTonemap"
        mock_tonemap.bl_idname = "CompositorNodeTonemap"
        s_type = MagicMock()
        s_type.name = "Type"
        s_key = MagicMock()
        s_key.name = "Key"
        mock_tonemap.inputs = [s_type, s_key]
        mock_nodes.get.return_value = mock_tonemap
        mock_nodes.__iter__.return_value = [mock_tonemap]

        # Valid Tonemap type
        res_tm = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyTonemap",
            "property_name": "type",
            "property_value": "rh_simple",
        })
        assert res_tm["status"] == "success"
        assert s_type.default_value == "Rh Simple"

        # Invalid Tonemap type
        with pytest.raises(ValueError, match="Invalid Tonemap type"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyTonemap",
                "property_name": "type",
                "property_value": "unsupported_hdr",
            })

        # 3. Curve RGB
        mock_curve = MagicMock()
        mock_curve.name = "MyCurves"
        mock_curve.bl_idname = "CompositorNodeCurveRGB"
        mock_c0 = MagicMock()
        p0 = MagicMock()
        p0.location = (0.0, 0.0)
        p1 = MagicMock()
        p1.location = (1.0, 1.0)
        mock_c0.points = [p0, p1]
        mock_curve.mapping.curves = [mock_c0, MagicMock(), MagicMock(), MagicMock()]
        mock_curve.inputs = []
        mock_nodes.get.return_value = mock_curve
        mock_nodes.__iter__.return_value = [mock_curve]

        # Valid curve point update
        res_cp = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyCurves",
            "property_name": "curve_point",
            "property_value": {"curve": "C", "point": [0.5, 0.75]},
        })
        assert res_cp["status"] == "success"
        mock_curve.mapping.update.assert_called()

        # Out-of-bounds curve point
        with pytest.raises(ValueError, match="must be within"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyCurves",
                "property_name": "curve_point",
                "property_value": {"curve": "C", "point": [1.5, 0.5]},
            })

    def test_vfx_nodes_whitelisted_and_properties(self):
        """Milestone 9.1D: Verifies Lensdist, Defocus, and Filter node validation."""
        # 1. Whitelist resolution
        assert canonical_node_type("lens_distortion") == "CompositorNodeLensdist"
        assert canonical_node_type("lensdist") == "CompositorNodeLensdist"
        assert canonical_node_type("defocus") == "CompositorNodeDefocus"
        assert canonical_node_type("filter") == "CompositorNodeFilter"

        mock_bpy = MagicMock()
        mock_scene = MagicMock()
        mock_tree = MagicMock()
        mock_nodes = MagicMock()
        mock_tree.nodes = mock_nodes
        mock_tree.name = "TestCompositor"
        mock_tree.links = []
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = None

        # 2. Lensdist node property tests
        mock_lens = MagicMock()
        mock_lens.name = "MyLens"
        mock_lens.bl_idname = "CompositorNodeLensdist"
        s_dist = MagicMock()
        s_dist.name = "Distortion"
        s_disp = MagicMock()
        s_disp.name = "Dispersion"
        s_type = MagicMock()
        s_type.name = "Type"
        mock_lens.inputs = [s_dist, s_disp, s_type]
        mock_nodes.get.return_value = mock_lens
        mock_nodes.__iter__.return_value = [mock_lens]

        # Valid distortion
        res_d = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyLens",
            "property_name": "distortion",
            "property_value": 0.45,
        })
        assert res_d["status"] == "success"
        assert s_dist.default_value == 0.45

        # Out-of-bounds distortion
        with pytest.raises(ValueError, match="Lens distortion must be between"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyLens",
                "property_name": "distortion",
                "property_value": 5.0,
            })

        # Valid type
        res_lt = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyLens",
            "property_name": "lensdist_type",
            "property_value": "radial",
        })
        assert res_lt["status"] == "success"
        assert s_type.default_value == "Radial"

        # Invalid type
        with pytest.raises(ValueError, match="Invalid Lensdist type"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyLens",
                "property_name": "type",
                "property_value": "fisheye",
            })

        # 3. Defocus node property tests
        mock_defocus = MagicMock()
        mock_defocus.name = "MyDefocus"
        mock_defocus.bl_idname = "CompositorNodeDefocus"
        mock_defocus.f_stop = 128.0
        mock_defocus.blur_max = 16.0
        mock_defocus.bokeh = "CIRCLE"
        mock_defocus.use_zbuffer = False
        mock_nodes.get.return_value = mock_defocus
        mock_nodes.__iter__.return_value = [mock_defocus]

        # Valid f_stop
        res_fs = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyDefocus",
            "property_name": "f_stop",
            "property_value": 2.8,
        })
        assert res_fs["status"] == "success"
        assert mock_defocus.f_stop == 2.8

        # Out-of-bounds f_stop
        with pytest.raises(ValueError, match="Defocus f_stop must be between"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyDefocus",
                "property_name": "f_stop",
                "property_value": 0.05,
            })

        # Valid bokeh
        res_bk = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyDefocus",
            "property_name": "bokeh",
            "property_value": "hexagon",
        })
        assert res_bk["status"] == "success"
        assert mock_defocus.bokeh == "HEXAGON"

        # Invalid bokeh
        with pytest.raises(ValueError, match="Invalid Defocus bokeh type"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyDefocus",
                "property_name": "bokeh",
                "property_value": "star",
            })

        # 4. Filter node property tests
        mock_filt = MagicMock()
        mock_filt.name = "MyFilter"
        mock_filt.bl_idname = "CompositorNodeFilter"
        s_ftype = MagicMock()
        s_ftype.name = "Type"
        mock_filt.inputs = [s_ftype]
        mock_nodes.get.return_value = mock_filt
        mock_nodes.__iter__.return_value = [mock_filt]

        # Valid filter type
        res_fl = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyFilter",
            "property_name": "filter_type",
            "property_value": "sobel",
        })
        assert res_fl["status"] == "success"
        assert s_ftype.default_value == "Sobel"

        # Invalid filter type
        with pytest.raises(ValueError, match="Invalid Filter type"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyFilter",
                "property_name": "filter_type",
                "property_value": "gaussian",
            })

    def test_geometric_and_id_mask_nodes(self):
        """Milestone 9.1E: Verifies BoxMask, EllipseMask, and IDMask whitelist and properties."""
        # 1. Whitelist resolution
        assert canonical_node_type("box_mask") == "CompositorNodeBoxMask"
        assert canonical_node_type("boxmask") == "CompositorNodeBoxMask"
        assert canonical_node_type("ellipse_mask") == "CompositorNodeEllipseMask"
        assert canonical_node_type("ellipsemask") == "CompositorNodeEllipseMask"
        assert canonical_node_type("circle_mask") == "CompositorNodeEllipseMask"
        assert canonical_node_type("id_mask") == "CompositorNodeIDMask"
        assert canonical_node_type("idmask") == "CompositorNodeIDMask"

        # Allowed render passes for index
        assert "object_index" in ALLOWED_RENDER_PASSES
        assert "material_index" in ALLOWED_RENDER_PASSES

        mock_bpy = MagicMock()
        mock_scene = MagicMock()
        mock_tree = MagicMock()
        mock_nodes = MagicMock()
        mock_tree.nodes = mock_nodes
        mock_tree.name = "TestCompositor"
        mock_tree.links = []
        mock_scene.name = "Scene"
        mock_scene.compositing_node_group = mock_tree
        mock_bpy.context.scene = mock_scene
        mock_bpy.context.view_layer = None

        # 2. Box Mask property tests
        mock_box = MagicMock()
        mock_box.name = "MyBoxMask"
        mock_box.bl_idname = "CompositorNodeBoxMask"
        s_op = MagicMock()
        s_op.name = "Operation"
        s_op.default_value = "Add"
        s_pos = MagicMock()
        s_pos.name = "Position"
        s_pos.default_value = (0.5, 0.5)
        s_size = MagicMock()
        s_size.name = "Size"
        s_size.default_value = (0.2, 0.2)
        s_rot = MagicMock()
        s_rot.name = "Rotation"
        s_rot.default_value = 0.0
        mock_box.inputs = [s_op, s_pos, s_size, s_rot]
        mock_nodes.get.return_value = mock_box
        mock_nodes.__iter__.return_value = [mock_box]

        # Valid operation
        res_op = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyBoxMask",
            "property_name": "operation",
            "property_value": "multiply",
        })
        assert res_op["status"] == "success"
        assert s_op.default_value == "Multiply"

        # Invalid operation
        with pytest.raises(ValueError, match="Invalid Mask operation"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyBoxMask",
                "property_name": "operation",
                "property_value": "intersect",
            })

        # Valid position & size
        res_pos = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyBoxMask",
            "property_name": "position",
            "property_value": [0.3, 0.7],
        })
        assert res_pos["status"] == "success"
        assert s_pos.default_value == (0.3, 0.7)

        # Out-of-bounds position
        with pytest.raises(ValueError, match="coordinates must be in"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyBoxMask",
                "property_name": "position",
                "property_value": [1.5, 0.5],
            })

        # 3. ID Mask property tests
        mock_idm = MagicMock()
        mock_idm.name = "MyIDMask"
        mock_idm.bl_idname = "CompositorNodeIDMask"
        s_idval = MagicMock()
        s_idval.name = "ID value"
        s_idval.default_value = 1.0
        s_idx = MagicMock()
        s_idx.name = "Index"
        s_idx.default_value = 0
        s_aa = MagicMock()
        s_aa.name = "Anti-Alias"
        s_aa.default_value = False
        mock_idm.inputs = [s_idval, s_idx, s_aa]
        mock_nodes.get.return_value = mock_idm
        mock_nodes.__iter__.return_value = [mock_idm]

        # Valid index
        res_idx = execute_compositor_action(mock_bpy, {
            "action": "set_property",
            "node_name": "MyIDMask",
            "property_name": "index",
            "property_value": 42,
        })
        assert res_idx["status"] == "success"
        assert s_idx.default_value == 42

        # Negative index
        with pytest.raises(ValueError, match="index must be in"):
            execute_compositor_action(mock_bpy, {
                "action": "set_property",
                "node_name": "MyIDMask",
                "property_name": "index",
                "property_value": -1,
            })
