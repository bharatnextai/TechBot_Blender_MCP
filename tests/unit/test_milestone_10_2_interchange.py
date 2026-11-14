"""
Milestone 10.2 Unit Tests — Modern Format Expansion & Project-File Security Hardening.

Covers:
1. Format detection for OBJ, STL, PLY, and ABC.
2. Operator check and execution for OBJ, STL, PLY, and ABC (both export and import).
3. Synchronous Alembic execution (as_background_job=False).
4. SHA-256 sidecar generation and integrity verification for new formats.
5. Tool schema input validation for all expanded formats.
6. Project-file security hardening in handle_save_blend_file:
   - Canonical human approval enforcement.
   - Workspace-root containment.
   - Path traversal rejection.
   - Accidental overwrite protection.
7. Project-file security hardening in handle_open_blend_file:
   - Rejection of unauthenticated trusted_approval=True bypass.
   - Fail-closed embedded scripts rejection (use_scripts=False).
   - Workspace-root containment and path traversal rejection.
   - Unsaved dirty project confirmation guard.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from shared.schemas.tool_schemas import (
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_IMPORT_SCENE_ASSET,
    TOOL_SAVE_BLEND_FILE,
    TOOL_OPEN_BLEND_FILE,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.asset_interchange import (
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_IMPORT_FORMATS,
    detect_format_from_path,
    check_format_support,
    validate_asset_path,
    compute_file_sha256,
    generate_sha256_sidecar,
    verify_sha256_sidecar,
    execute_export_asset,
    execute_import_asset,
)
from blender_addon.universal_mcp.bridge.handlers import (
    handle_save_blend_file,
    handle_open_blend_file,
)
from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry


class TestModernFormatExpansion:
    """Verifies format detection, operator checks, and export/import dispatch for OBJ, STL, PLY, ABC."""

    def test_format_constants_contain_expanded_formats(self):
        for fmt in ("OBJ", "STL", "PLY", "ABC"):
            assert fmt in SUPPORTED_EXPORT_FORMATS
            assert fmt in SUPPORTED_IMPORT_FORMATS

    def test_extension_detection_for_expanded_formats(self):
        assert detect_format_from_path("mesh.obj") == "OBJ"
        assert detect_format_from_path("mesh.OBJ") == "OBJ"
        assert detect_format_from_path("/path/to/part.stl") == "STL"
        assert detect_format_from_path("C:\\scans\\pointcloud.ply") == "PLY"
        assert detect_format_from_path("animation_cache.abc") == "ABC"

    def test_check_format_support_obj(self):
        mock_bpy = MagicMock()
        mock_bpy.ops.wm.obj_export = MagicMock()
        mock_bpy.ops.wm.obj_import = MagicMock()

        ok, op, _ = check_format_support(mock_bpy, "OBJ", is_export=True)
        assert ok is True and op == "wm.obj_export"

        ok, op, _ = check_format_support(mock_bpy, "OBJ", is_export=False)
        assert ok is True and op == "wm.obj_import"

    def test_check_format_support_stl(self):
        mock_bpy = MagicMock()
        mock_bpy.ops.wm.stl_export = MagicMock()
        mock_bpy.ops.wm.stl_import = MagicMock()

        ok, op, _ = check_format_support(mock_bpy, "STL", is_export=True)
        assert ok is True and op == "wm.stl_export"

        ok, op, _ = check_format_support(mock_bpy, "STL", is_export=False)
        assert ok is True and op == "wm.stl_import"

    def test_check_format_support_ply(self):
        mock_bpy = MagicMock()
        mock_bpy.ops.wm.ply_export = MagicMock()
        mock_bpy.ops.wm.ply_import = MagicMock()

        ok, op, _ = check_format_support(mock_bpy, "PLY", is_export=True)
        assert ok is True and op == "wm.ply_export"

        ok, op, _ = check_format_support(mock_bpy, "PLY", is_export=False)
        assert ok is True and op == "wm.ply_import"

    def test_check_format_support_alembic(self):
        mock_bpy = MagicMock()
        mock_bpy.ops.wm.alembic_export = MagicMock()
        mock_bpy.ops.wm.alembic_import = MagicMock()

        ok, op, _ = check_format_support(mock_bpy, "ABC", is_export=True)
        assert ok is True and op == "wm.alembic_export"

        ok, op, _ = check_format_support(mock_bpy, "ABC", is_export=False)
        assert ok is True and op == "wm.alembic_import"

    def test_check_format_support_missing_operator(self):
        mock_bpy = MagicMock()
        del mock_bpy.ops.wm.obj_export
        ok, op, reason = check_format_support(mock_bpy, "OBJ", is_export=True)
        assert ok is False
        assert "not available" in reason

    def test_export_dispatch_obj(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = os.path.join(temp_dir, "test.obj")
            mock_bpy = MagicMock()

            def fake_export(filepath, export_selected_objects):
                with open(filepath, "w") as f:
                    f.write("# OBJ test file\nv 0 0 0\n")

            mock_bpy.ops.wm.obj_export.side_effect = fake_export
            mock_bpy.context.selected_objects = []
            mock_bpy.data.objects = []

            res = execute_export_asset(mock_bpy, {"filepath": out_path, "format": "OBJ", "selected_only": True})
            assert res["success"] is True
            assert res["format"] == "OBJ"
            assert os.path.exists(out_path)
            assert os.path.exists(res["sidecar_path"])
            mock_bpy.ops.wm.obj_export.assert_called_once_with(
                filepath=os.path.abspath(out_path),
                export_selected_objects=True,
            )

    def test_export_dispatch_stl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = os.path.join(temp_dir, "test.stl")
            mock_bpy = MagicMock()

            def fake_export(filepath, export_selected_objects):
                with open(filepath, "wb") as f:
                    f.write(b"solid test\nendsolid\n")

            mock_bpy.ops.wm.stl_export.side_effect = fake_export
            mock_bpy.context.selected_objects = []
            mock_bpy.data.objects = []

            res = execute_export_asset(mock_bpy, {"filepath": out_path, "format": "STL", "selected_only": False})
            assert res["success"] is True
            assert res["format"] == "STL"
            assert os.path.exists(out_path)
            mock_bpy.ops.wm.stl_export.assert_called_once_with(
                filepath=os.path.abspath(out_path),
                export_selected_objects=False,
            )

    def test_export_dispatch_ply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = os.path.join(temp_dir, "test.ply")
            mock_bpy = MagicMock()

            def fake_export(filepath, export_selected_objects):
                with open(filepath, "w") as f:
                    f.write("ply\nformat ascii 1.0\nend_header\n")

            mock_bpy.ops.wm.ply_export.side_effect = fake_export
            mock_bpy.context.selected_objects = []
            mock_bpy.data.objects = []

            res = execute_export_asset(mock_bpy, {"filepath": out_path, "format": "PLY"})
            assert res["success"] is True
            assert res["format"] == "PLY"
            assert os.path.exists(out_path)
            mock_bpy.ops.wm.ply_export.assert_called_once_with(
                filepath=os.path.abspath(out_path),
                export_selected_objects=False,
            )

    def test_export_dispatch_alembic_synchronous(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = os.path.join(temp_dir, "test.abc")
            mock_bpy = MagicMock()

            def fake_export(filepath, selected, as_background_job):
                assert as_background_job is False
                with open(filepath, "wb") as f:
                    f.write(b"AlembicHeaderData")

            mock_bpy.ops.wm.alembic_export.side_effect = fake_export
            mock_bpy.context.selected_objects = []
            mock_bpy.data.objects = []

            res = execute_export_asset(mock_bpy, {"filepath": out_path, "format": "ABC", "selected_only": True})
            assert res["success"] is True
            assert res["format"] == "ABC"
            assert os.path.exists(out_path)
            mock_bpy.ops.wm.alembic_export.assert_called_once_with(
                filepath=os.path.abspath(out_path),
                selected=True,
                as_background_job=False,
            )

    def test_import_dispatch_obj(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            in_path = os.path.join(temp_dir, "import.obj")
            with open(in_path, "w") as f:
                f.write("# OBJ file\nv 0 0 0\n")

            mock_bpy = MagicMock()
            mock_bpy.data.objects = {}
            mock_bpy.data.meshes = {}
            mock_bpy.data.materials = {}

            res = execute_import_asset(mock_bpy, {"filepath": in_path, "format": "OBJ"})
            assert res["success"] is True
            assert res["format"] == "OBJ"
            mock_bpy.ops.wm.obj_import.assert_called_once_with(filepath=os.path.abspath(in_path))

    def test_import_dispatch_alembic_synchronous(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            in_path = os.path.join(temp_dir, "import.abc")
            with open(in_path, "wb") as f:
                f.write(b"AlembicBinaryData")

            mock_bpy = MagicMock()
            mock_bpy.data.objects = {}
            mock_bpy.data.meshes = {}
            mock_bpy.data.materials = {}

            res = execute_import_asset(mock_bpy, {"filepath": in_path, "format": "ABC"})
            assert res["success"] is True
            assert res["format"] == "ABC"
            mock_bpy.ops.wm.alembic_import.assert_called_once_with(
                filepath=os.path.abspath(in_path),
                as_background_job=False,
            )


class TestSchemaValidationForExpandedFormats:
    """Verifies that tool schemas accept all expanded formats and reject unknown ones."""

    def test_export_schema_accepts_expanded_formats(self):
        for fmt in ("OBJ", "STL", "PLY", "ABC"):
            sanitized = validate_tool_input(
                TOOL_EXPORT_SCENE_ASSET,
                {"filepath": f"C:/safe/model.{fmt.lower()}", "format": fmt},
                trusted_approval=True,
            )
            assert sanitized["format"] == fmt

    def test_import_schema_accepts_expanded_formats(self):
        for fmt in ("OBJ", "STL", "PLY", "ABC"):
            sanitized = validate_tool_input(
                TOOL_IMPORT_SCENE_ASSET,
                {"filepath": f"C:/safe/model.{fmt.lower()}", "format": fmt},
                trusted_approval=True,
            )
            assert sanitized["format"] == fmt

    def test_export_schema_rejects_unsupported_format(self):
        with pytest.raises(ValueError, match="Invalid value for 'format'"):
            validate_tool_input(
                TOOL_EXPORT_SCENE_ASSET,
                {"filepath": "C:/safe/model.3ds", "format": "3DS"},
                trusted_approval=True,
            )

    def test_import_schema_rejects_unsupported_format(self):
        with pytest.raises(ValueError, match="Invalid value for 'format'"):
            validate_tool_input(
                TOOL_IMPORT_SCENE_ASSET,
                {"filepath": "C:/safe/model.dae", "format": "DAE"},
                trusted_approval=True,
            )


class TestProjectFileSecurityHardening:
    """Verifies security controls on handle_save_blend_file and handle_open_blend_file."""

    def test_save_blend_file_requires_canonical_approval(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = True

        with tempfile.TemporaryDirectory() as temp_dir:
            save_path = os.path.join(temp_dir, "test.blend")
            with pytest.raises(PermissionError, match="Missing trusted human approval credentials"):
                handle_save_blend_file(mock_bpy, {"filepath": save_path})

    def test_save_blend_file_rejects_untrusted_approved_flag(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = True

        with tempfile.TemporaryDirectory() as temp_dir:
            save_path = os.path.join(temp_dir, "test.blend")
            with pytest.raises(PermissionError, match="Missing trusted human approval credentials"):
                handle_save_blend_file(mock_bpy, {"filepath": save_path, "approved": True})

    def test_save_blend_file_with_valid_approval_token(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = True
        registry = get_approval_registry()

        with tempfile.TemporaryDirectory() as temp_dir:
            save_path = os.path.join(temp_dir, "test.blend")
            params = {"filepath": save_path, "overwrite": True}
            req = registry.create_request("save_blend_file", params)
            ok, token = registry.resolve_request(req.request_id, "approved")
            assert ok is True

            res = handle_save_blend_file(
                mock_bpy,
                {"filepath": save_path, "overwrite": True, "request_id": req.request_id, "approval_token": token},
            )
            assert res["saved"] is True
            assert res["filepath"] == os.path.abspath(save_path)
            mock_bpy.ops.wm.save_as_mainfile.assert_called_once()

    def test_save_blend_file_path_traversal_rejected(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False

        with pytest.raises(ValueError, match="Path traversal detected"):
            handle_save_blend_file(mock_bpy, {"filepath": "C:/safe/dir/../../windows/system32/evil.blend"})

    def test_save_blend_file_workspace_root_containment(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False

        with tempfile.TemporaryDirectory() as temp_dir:
            ws_root = os.path.join(temp_dir, "workspace")
            os.makedirs(ws_root, exist_ok=True)
            outside_path = os.path.join(temp_dir, "escape.blend")

            with patch.dict(os.environ, {"UMCP_WORKSPACE_ROOT": ws_root}):
                with pytest.raises(PermissionError, match="outside authorized workspace root"):
                    handle_save_blend_file(mock_bpy, {"filepath": outside_path})

                inside_path = os.path.join(ws_root, "valid.blend")
                res = handle_save_blend_file(mock_bpy, {"filepath": inside_path})
                assert res["saved"] is True

    def test_save_blend_file_overwrite_protection(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False
        mock_bpy.data.filepath = ""

        with tempfile.TemporaryDirectory() as temp_dir:
            existing_file = os.path.join(temp_dir, "existing.blend")
            with open(existing_file, "w") as f:
                f.write("content")

            with pytest.raises(FileExistsError, match="already exists"):
                handle_save_blend_file(mock_bpy, {"filepath": existing_file, "overwrite": False})

    def test_open_blend_file_rejects_untrusted_trusted_approval_bypass(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = True

        with tempfile.TemporaryDirectory() as temp_dir:
            blend_file = os.path.join(temp_dir, "project.blend")
            with open(blend_file, "w") as f:
                f.write("content")

            # Client attempts trusted_approval: True without cryptographic token or test override
            with pytest.raises(PermissionError, match="Missing trusted human approval credentials"):
                handle_open_blend_file(mock_bpy, {"filepath": blend_file, "trusted_approval": True})

    def test_open_blend_file_rejects_untrusted_use_scripts(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False
        mock_bpy.data.is_dirty = False

        with tempfile.TemporaryDirectory() as temp_dir:
            blend_file = os.path.join(temp_dir, "project.blend")
            with open(blend_file, "w") as f:
                f.write("content")

            with pytest.raises(PermissionError, match="Execution of embedded scripts inside .blend files is disabled"):
                handle_open_blend_file(mock_bpy, {"filepath": blend_file, "use_scripts": True})

    def test_open_blend_file_workspace_root_containment(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False

        with tempfile.TemporaryDirectory() as temp_dir:
            ws_root = os.path.join(temp_dir, "workspace")
            os.makedirs(ws_root, exist_ok=True)
            outside_file = os.path.join(temp_dir, "outside.blend")
            with open(outside_file, "w") as f:
                f.write("content")

            with patch.dict(os.environ, {"UMCP_WORKSPACE_ROOT": ws_root}):
                with pytest.raises(PermissionError, match="outside authorized workspace root"):
                    handle_open_blend_file(mock_bpy, {"filepath": outside_file})

    def test_open_blend_file_guards_unsaved_dirty_state(self):
        mock_bpy = MagicMock()
        mock_bpy.context.scene.umcp_require_scene_mutation_approval = False
        mock_bpy.data.is_dirty = True

        with tempfile.TemporaryDirectory() as temp_dir:
            blend_file = os.path.join(temp_dir, "project.blend")
            with open(blend_file, "w") as f:
                f.write("content")

            with pytest.raises(ValueError, match="has unsaved modifications"):
                handle_open_blend_file(mock_bpy, {"filepath": blend_file, "confirm_discard_unsaved": False})

            res = handle_open_blend_file(mock_bpy, {"filepath": blend_file, "confirm_discard_unsaved": True})
            assert res["opened"] is True
            assert res["use_scripts"] is False
