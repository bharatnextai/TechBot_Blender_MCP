"""
Unit tests for Asset Interchange Foundation (Phase 2.2 - v0.1.75).

Verifies format detection, operator support checks, path traversal guards,
overwrite protection, SHA-256 sidecar generation and verification,
cleanup on export failure, datablock rollback on import failure,
schema compliance, and fail-closed security invariants.
"""

import json
import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_EXPORT_SCENE,
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_IMPORT_SCENE,
    PERMISSION_SCENE_MUTATION,
    validate_tool_input,
)
from mcp_service.registry.tool_registry import ToolRegistry
from blender_addon.universal_mcp.bridge.asset_interchange import (
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_IMPORT_FORMATS,
    MAX_ASSET_FILE_SIZE,
    detect_format_from_path,
    check_format_support,
    validate_asset_path,
    compute_file_sha256,
    generate_sha256_sidecar,
    verify_sha256_sidecar,
    cleanup_partial_export,
    rollback_import,
    inspect_object_summary,
    execute_export_asset,
    execute_import_asset,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_export_scene_asset,
    handle_import_scene_asset,
    _LOCAL_TEST_TOOLS,
)


class TestFormatDetectionAndSupport:
    """Verifies format detection from extensions and operator support inspection."""

    def test_extension_to_format_detection(self):
        assert detect_format_from_path("/path/to/model.glb") == "GLB"
        assert detect_format_from_path("C:\\models\\scene.gltf") == "GLTF"
        assert detect_format_from_path("asset.usd") == "USD"
        assert detect_format_from_path("binary.usdc") == "USDC"
        assert detect_format_from_path("ascii.usda") == "USDA"
        assert detect_format_from_path("character.fbx") == "FBX"
        assert detect_format_from_path("model.obj") == "OBJ"
        assert detect_format_from_path("part.stl") == "STL"
        assert detect_format_from_path("scan.ply") == "PLY"
        assert detect_format_from_path("cache.abc") == "ABC"
        assert detect_format_from_path("unknown.xyz") is None
        assert detect_format_from_path("") is None
        assert detect_format_from_path(None) is None

    def test_check_format_support_available(self):
        mock_bpy = MagicMock()
        mock_bpy.ops.export_scene.gltf = MagicMock()
        mock_bpy.ops.import_scene.gltf = MagicMock()
        mock_bpy.ops.wm.usd_export = MagicMock()
        mock_bpy.ops.wm.usd_import = MagicMock()

        ok, op, _ = check_format_support(mock_bpy, "GLB", is_export=True)
        assert ok is True and op == "export_scene.gltf"

        ok, op, _ = check_format_support(mock_bpy, "GLTF", is_export=False)
        assert ok is True and op == "import_scene.gltf"

        ok, op, _ = check_format_support(mock_bpy, "USDC", is_export=True)
        assert ok is True and op == "wm.usd_export"

        ok, op, _ = check_format_support(mock_bpy, "USDA", is_export=False)
        assert ok is True and op == "wm.usd_import"

    def test_check_format_support_missing_operator(self):
        mock_bpy = MagicMock()
        del mock_bpy.ops.export_scene.gltf

        ok, op, reason = check_format_support(mock_bpy, "GLB", is_export=True)
        assert ok is False
        assert "not installed" in reason or "not available" in reason

    def test_check_format_support_unsupported_format(self):
        mock_bpy = MagicMock()
        ok, op, reason = check_format_support(mock_bpy, "3DS", is_export=True)
        assert ok is False
        assert "not in the supported formats" in reason


class TestPathValidationAndSecurity:
    """Verifies path traversal guards, overwrite protection, and sandbox bounds."""

    def test_validate_empty_path(self):
        with pytest.raises(ValueError, match="required and must be a non-empty string"):
            validate_asset_path("")
        with pytest.raises(ValueError, match="required and must be a non-empty string"):
            validate_asset_path(None)
        with pytest.raises(ValueError, match="cannot be empty or whitespace"):
            validate_asset_path("   ")

    def test_validate_relative_path_rejected(self):
        with pytest.raises(ValueError, match="must be an absolute path"):
            validate_asset_path("relative/path/model.glb")

    def test_validate_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_asset_path("C:/safe/dir/../../windows/system32/cmd.exe")

    def test_validate_allowed_root_enforced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = os.path.join(temp_dir, "sandbox")
            os.makedirs(root, exist_ok=True)
            outside = os.path.join(temp_dir, "outside.glb")

            with pytest.raises(PermissionError, match="outside the authorized root directory"):
                validate_asset_path(outside, allowed_root=root)

            inside = os.path.join(root, "inside.glb")
            validated = validate_asset_path(inside, allowed_root=root)
            assert os.path.realpath(validated) == os.path.realpath(inside)

    def test_overwrite_protection_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            existing = os.path.join(temp_dir, "model.glb")
            with open(existing, "wb") as f:
                f.write(b"existing content")

            with pytest.raises(ValueError, match="already exists and overwrite=False"):
                validate_asset_path(existing, overwrite=False, is_export=True)

            # Allowed when overwrite=True
            validated = validate_asset_path(existing, overwrite=True, is_export=True)
            assert os.path.abspath(existing) == validated

    def test_import_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = os.path.join(temp_dir, "nonexistent.glb")
            with pytest.raises(FileNotFoundError, match="Input asset file not found on disk"):
                validate_asset_path(missing, is_export=False)


class TestSidecarChecksum:
    """Verifies SHA-256 sidecar generation, verification, and tampering detection."""

    def test_sidecar_generation_and_verification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset = os.path.join(temp_dir, "test_model.glb")
            content = b"GLTF-BINARY-MOCK-DATA-12345"
            with open(asset, "wb") as f:
                f.write(content)

            sidecar_path = generate_sha256_sidecar(asset, metadata={"format": "GLB"})
            assert os.path.exists(sidecar_path)

            with open(sidecar_path, "r", encoding="utf-8") as f:
                sidecar_data = json.load(f)

            assert sidecar_data["filename"] == "test_model.glb"
            assert sidecar_data["file_size_bytes"] == len(content)
            assert sidecar_data["sha256"] == compute_file_sha256(asset)
            assert sidecar_data["metadata"]["format"] == "GLB"

            ok, msg, exp = verify_sha256_sidecar(asset)
            assert ok is True
            assert "passed" in msg

    def test_sidecar_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset = os.path.join(temp_dir, "tampered.glb")
            with open(asset, "wb") as f:
                f.write(b"ORIGINAL-CONTENT")
            generate_sha256_sidecar(asset)

            # Tamper with asset
            with open(asset, "wb") as f:
                f.write(b"TAMPERED-CONTENT")
            ok, msg, exp = verify_sha256_sidecar(asset)
            assert ok is False
            assert "mismatch" in msg


class TestRollbackAndCleanup:
    """Verifies cleanup of partial files and datablock rollback on error."""

    def test_cleanup_partial_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            partial_asset = os.path.join(temp_dir, "failed.glb")
            with open(partial_asset, "wb") as f:
                f.write(b"partial")
            sidecar = f"{partial_asset}.sha256"
            with open(sidecar, "wb") as f:
                f.write(b"partial_sidecar")

            assert os.path.exists(partial_asset)
            assert os.path.exists(sidecar)

            cleanup_partial_export(partial_asset, sidecar)
            assert not os.path.exists(partial_asset)
            assert not os.path.exists(sidecar)

    def test_rollback_import(self):
        mock_bpy = MagicMock()
        obj1 = MagicMock(name="Obj1")
        obj_new = MagicMock(name="ObjNew")
        mesh_new = MagicMock(name="MeshNew")
        mat_new = MagicMock(name="MatNew")

        mock_objects = MagicMock()
        mock_objects.items.return_value = [("Obj1", obj1), ("ObjNew", obj_new)]
        mock_bpy.data.objects = mock_objects

        mock_meshes = MagicMock()
        mock_meshes.items.return_value = [("MeshNew", mesh_new)]
        mock_bpy.data.meshes = mock_meshes

        mock_materials = MagicMock()
        mock_materials.items.return_value = [("MatNew", mat_new)]
        mock_bpy.data.materials = mock_materials

        rollback_import(
            mock_bpy,
            before_objects={"Obj1"},
            before_meshes=set(),
            before_materials=set(),
        )

        mock_objects.remove.assert_called_once_with(obj_new, do_unlink=True)
        mock_meshes.remove.assert_called_once_with(mesh_new, do_unlink=True)
        mock_materials.remove.assert_called_once_with(mat_new, do_unlink=True)


class TestObjectSummaryInspection:
    """Verifies topology, transform, and material readback extraction."""

    def test_inspect_object_summary_mesh(self):
        obj = MagicMock()
        obj.name = "HeroObject"
        obj.type = "MESH"
        obj.location = (1.0, 2.0, 3.0)
        obj.rotation_euler = (0.1, 0.2, 0.3)
        obj.scale = (1.0, 1.0, 1.0)

        vert_mock = [MagicMock() for _ in range(8)]
        poly_mock = [MagicMock() for _ in range(6)]
        edge_mock = [MagicMock() for _ in range(12)]
        obj.data.vertices = vert_mock
        obj.data.polygons = poly_mock
        obj.data.edges = edge_mock

        slot1 = MagicMock()
        slot1.material.name = "GoldMaterial"
        obj.material_slots = [slot1]

        summary = inspect_object_summary(obj)
        assert summary["name"] == "HeroObject"
        assert summary["type"] == "MESH"
        assert summary["vertex_count"] == 8
        assert summary["polygon_count"] == 6
        assert summary["edge_count"] == 12
        assert summary["materials"] == ["GoldMaterial"]


class TestFailClosedSecurityAndHandlers:
    """Verifies handlers fail closed when untrusted approval flags or missing tokens are supplied."""

    def test_tools_registered_in_local_test_tools(self):
        for tool in ("export_scene_asset", "export_scene", "import_scene_asset", "import_scene"):
            assert tool in _LOCAL_TEST_TOOLS

    def test_untrusted_approved_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = os.path.join(temp_dir, "out.glb")
            mock_bpy = MagicMock()

            with patch("blender_addon.universal_mcp.bridge.handlers.is_approval_required", return_value=True):
                with patch("blender_addon.universal_mcp.bridge.handlers.get_approval_registry", return_value=MagicMock()):
                    # Untrusted client sends approved=True
                    with pytest.raises(PermissionError, match="Missing trusted human approval credentials"):
                        handle_export_scene_asset(mock_bpy, {"filepath": target, "approved": True})

                    with pytest.raises(PermissionError, match="Missing trusted human approval credentials"):
                        handle_import_scene_asset(mock_bpy, {"filepath": target, "approved": True})

    def test_schema_registration(self):
        reg = ToolRegistry()
        for name in (TOOL_EXPORT_SCENE_ASSET, TOOL_EXPORT_SCENE, TOOL_IMPORT_SCENE_ASSET, TOOL_IMPORT_SCENE):
            assert reg.has_tool(name)
            defn = reg.get_tool_definition(name)
            assert defn is not None
            assert defn["permission_tier"] == PERMISSION_SCENE_MUTATION
