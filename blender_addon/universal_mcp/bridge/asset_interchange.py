"""
Asset Interchange Foundation for Blender Universal MCP (Phase 2.2 - v0.1.75).

Provides typed, verified export and import workflows for 3D asset interchange:
- glTF 2.0 (GLB binary, GLTF separate) via bpy.ops.export_scene.gltf / import_scene.gltf
- Universal Scene Description (USD, USDC binary, USDA ascii) via bpy.ops.wm.usd_export / wm.usd_import
- FBX support when bpy.ops.export_scene.fbx / import_scene.fbx is available
- SHA-256 sidecar generation (.sha256 JSON) and integrity verification
- Overwrite protection, directory traversal guards, and file size checks
- Partial file cleanup on export failure
- Scene datablock rollback on import failure
- Post-import topology, transform, and material inspection readback
"""

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple


SUPPORTED_EXPORT_FORMATS = ("GLTF", "GLB", "FBX", "USD", "USDC", "USDA", "OBJ", "STL", "PLY", "ABC")
SUPPORTED_IMPORT_FORMATS = ("GLTF", "GLB", "FBX", "USD", "USDC", "USDA", "OBJ", "STL", "PLY", "ABC")

EXTENSION_TO_FORMAT = {
    ".gltf": "GLTF",
    ".glb": "GLB",
    ".fbx": "FBX",
    ".usd": "USD",
    ".usdc": "USDC",
    ".usda": "USDA",
    ".obj": "OBJ",
    ".stl": "STL",
    ".ply": "PLY",
    ".abc": "ABC",
}

FORMAT_TO_PRIMARY_EXTENSION = {
    "GLTF": ".gltf",
    "GLB": ".glb",
    "FBX": ".fbx",
    "USD": ".usd",
    "USDC": ".usdc",
    "USDA": ".usda",
    "OBJ": ".obj",
    "STL": ".stl",
    "PLY": ".ply",
    "ABC": ".abc",
}

MAX_ASSET_FILE_SIZE = 500 * 1024 * 1024  # 500 MB bound


def detect_format_from_path(filepath: str) -> Optional[str]:
    """Infers canonical format name from file extension."""
    if not filepath or not isinstance(filepath, str):
        return None
    ext = os.path.splitext(filepath.strip())[1].lower()
    return EXTENSION_TO_FORMAT.get(ext)


def check_format_support(bpy_module: Any, format_name: str, is_export: bool = True) -> Tuple[bool, str, str]:
    """
    Checks whether the requested format operator is available on bpy_module.
    Returns (is_supported: bool, operator_id: str, reason: str).
    """
    fmt = str(format_name).strip().upper()
    if fmt not in (SUPPORTED_EXPORT_FORMATS if is_export else SUPPORTED_IMPORT_FORMATS):
        return False, "", f"Format '{fmt}' is not in the supported formats list."

    if fmt in ("GLTF", "GLB"):
        op_path = "export_scene.gltf" if is_export else "import_scene.gltf"
        mod = getattr(getattr(bpy_module, "ops", None), "export_scene" if is_export else "import_scene", None)
        if mod is None or not hasattr(mod, "gltf"):
            return False, op_path, f"Blender glTF operator 'bpy.ops.{op_path}' is not installed or enabled."
        return True, op_path, "Available"

    if fmt in ("USD", "USDC", "USDA"):
        op_path = "wm.usd_export" if is_export else "wm.usd_import"
        mod = getattr(getattr(bpy_module, "ops", None), "wm", None)
        target_op = "usd_export" if is_export else "usd_import"
        if mod is None or not hasattr(mod, target_op):
            return False, op_path, f"Blender USD operator 'bpy.ops.{op_path}' is not available in this build."
        return True, op_path, "Available"

    if fmt == "FBX":
        op_path = "export_scene.fbx" if is_export else "import_scene.fbx"
        mod = getattr(getattr(bpy_module, "ops", None), "export_scene" if is_export else "import_scene", None)
        if mod is None or not hasattr(mod, "fbx"):
            return False, op_path, f"Blender FBX operator 'bpy.ops.{op_path}' is not installed or enabled."
        return True, op_path, "Available"

    if fmt == "OBJ":
        op_path = "wm.obj_export" if is_export else "wm.obj_import"
        mod = getattr(getattr(bpy_module, "ops", None), "wm", None)
        target_op = "obj_export" if is_export else "obj_import"
        if mod is None or not hasattr(mod, target_op):
            return False, op_path, f"Blender OBJ operator 'bpy.ops.{op_path}' is not available."
        return True, op_path, "Available"

    if fmt == "STL":
        op_path = "wm.stl_export" if is_export else "wm.stl_import"
        mod = getattr(getattr(bpy_module, "ops", None), "wm", None)
        target_op = "stl_export" if is_export else "stl_import"
        if mod is None or not hasattr(mod, target_op):
            return False, op_path, f"Blender STL operator 'bpy.ops.{op_path}' is not available."
        return True, op_path, "Available"

    if fmt == "PLY":
        op_path = "wm.ply_export" if is_export else "wm.ply_import"
        mod = getattr(getattr(bpy_module, "ops", None), "wm", None)
        target_op = "ply_export" if is_export else "ply_import"
        if mod is None or not hasattr(mod, target_op):
            return False, op_path, f"Blender PLY operator 'bpy.ops.{op_path}' is not available."
        return True, op_path, "Available"

    if fmt == "ABC":
        op_path = "wm.alembic_export" if is_export else "wm.alembic_import"
        mod = getattr(getattr(bpy_module, "ops", None), "wm", None)
        target_op = "alembic_export" if is_export else "alembic_import"
        if mod is None or not hasattr(mod, target_op):
            return False, op_path, f"Blender Alembic operator 'bpy.ops.{op_path}' is not available."
        return True, op_path, "Available"

    return False, "", f"Unhandled format '{fmt}'"


def validate_asset_path(
    filepath: Any,
    overwrite: bool = False,
    is_export: bool = True,
    allowed_root: Optional[str] = None,
) -> str:
    """
    Validates asset filepaths:
    - Non-empty string
    - Absolute path
    - Path traversal ('..') rejection
    - Allowed root containment (if allowed_root provided)
    - Overwrite protection for export
    - File existence & size check for import
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError("Parameter 'filepath' is required and must be a non-empty string.")

    clean_path = filepath.strip()
    if not clean_path:
        raise ValueError("Parameter 'filepath' cannot be empty or whitespace.")

    norm_segments = clean_path.replace("\\", "/").split("/")
    if ".." in norm_segments:
        raise ValueError(f"Path traversal detected in 'filepath': '{clean_path}'. Parent references '..' are forbidden.")

    if not os.path.isabs(clean_path):
        raise ValueError(f"Parameter 'filepath' must be an absolute path: '{clean_path}'.")

    norm_path = os.path.abspath(clean_path)

    if allowed_root:
        root_real = os.path.realpath(allowed_root)
        path_real = os.path.realpath(norm_path)
        if os.path.commonpath((path_real, root_real)) != root_real:
            raise PermissionError(f"Filepath '{norm_path}' is outside the authorized root directory '{allowed_root}'.")

    if is_export:
        if os.path.exists(norm_path) and not overwrite:
            raise ValueError(
                f"Destination file '{norm_path}' already exists and overwrite=False. Enable 'overwrite' to replace."
            )
        parent_dir = os.path.dirname(norm_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
    else:
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Input asset file not found on disk: '{norm_path}'.")
        if not os.path.isfile(norm_path):
            raise ValueError(f"Asset path '{norm_path}' is not a regular file.")
        file_size = os.path.getsize(norm_path)
        if file_size > MAX_ASSET_FILE_SIZE:
            raise ValueError(
                f"Asset file size {file_size} bytes exceeds maximum permitted size of {MAX_ASSET_FILE_SIZE} bytes."
            )

    return norm_path


def compute_file_sha256(filepath: str) -> str:
    """Computes SHA-256 hex digest for a file on disk."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_sha256_sidecar(filepath: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Generates a .sha256 JSON sidecar file alongside the asset.
    Returns the absolute path to the sidecar file.
    """
    sha256_hash = compute_file_sha256(filepath)
    file_size = os.path.getsize(filepath)
    sidecar_path = f"{filepath}.sha256"

    sidecar_data = {
        "filepath": os.path.abspath(filepath),
        "filename": os.path.basename(filepath),
        "sha256": sha256_hash,
        "file_size_bytes": file_size,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if metadata:
        sidecar_data["metadata"] = metadata

    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, indent=2)

    return sidecar_path


def verify_sha256_sidecar(filepath: str) -> Tuple[bool, str, Optional[str]]:
    """
    Verifies that filepath matches its .sha256 sidecar file if present.
    Returns (verified: bool, message: str, expected_sha256: Optional[str]).
    """
    sidecar_path = f"{filepath}.sha256"
    if not os.path.exists(sidecar_path):
        return False, f"Sidecar file '{sidecar_path}' does not exist.", None

    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            sidecar_data = json.load(f)
        expected_hash = sidecar_data.get("sha256")
        if not expected_hash:
            return False, "Sidecar file is missing 'sha256' field.", None

        actual_hash = compute_file_sha256(filepath)
        if actual_hash.lower() != expected_hash.lower():
            return (
                False,
                f"SHA-256 mismatch: expected {expected_hash}, computed {actual_hash}.",
                expected_hash,
            )
        return True, "SHA-256 integrity verification passed.", expected_hash
    except Exception as exc:
        return False, f"Failed to read/verify sidecar: {exc}", None


def cleanup_partial_export(filepath: str, sidecar_path: Optional[str] = None) -> None:
    """Removes partial destination file and sidecar file upon export failure."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass
    try:
        sidecar = sidecar_path or (f"{filepath}.sha256" if filepath else None)
        if sidecar and os.path.exists(sidecar):
            os.remove(sidecar)
    except Exception:
        pass


def rollback_import(
    bpy_module: Any,
    before_objects: Set[str],
    before_meshes: Set[str],
    before_materials: Set[str],
) -> None:
    """Removes newly created objects, meshes, and materials added during a failed import."""
    if not hasattr(bpy_module, "data"):
        return

    # 1. Unlink and remove new objects
    if hasattr(bpy_module.data, "objects"):
        new_objs = [obj for name, obj in bpy_module.data.objects.items() if name not in before_objects]
        for obj in new_objs:
            try:
                bpy_module.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass

    # 2. Remove new meshes
    if hasattr(bpy_module.data, "meshes"):
        new_meshes = [mesh for name, mesh in bpy_module.data.meshes.items() if name not in before_meshes]
        for mesh in new_meshes:
            try:
                bpy_module.data.meshes.remove(mesh, do_unlink=True)
            except Exception:
                pass

    # 3. Remove new materials
    if hasattr(bpy_module.data, "materials"):
        new_mats = [mat for name, mat in bpy_module.data.materials.items() if name not in before_materials]
        for mat in new_mats:
            try:
                bpy_module.data.materials.remove(mat, do_unlink=True)
            except Exception:
                pass


def inspect_object_summary(obj: Any) -> Dict[str, Any]:
    """Extracts topology, transforms, and materials for an imported object."""
    summary: Dict[str, Any] = {
        "name": getattr(obj, "name", "unknown"),
        "type": getattr(obj, "type", "UNKNOWN"),
        "location": [round(float(v), 5) for v in getattr(obj, "location", (0.0, 0.0, 0.0))],
        "rotation_euler": [round(float(v), 5) for v in getattr(obj, "rotation_euler", (0.0, 0.0, 0.0))],
        "scale": [round(float(v), 5) for v in getattr(obj, "scale", (1.0, 1.0, 1.0))],
    }

    data = getattr(obj, "data", None)
    if summary["type"] == "MESH" and data is not None:
        summary["vertex_count"] = len(getattr(data, "vertices", []))
        summary["polygon_count"] = len(getattr(data, "polygons", []))
        summary["edge_count"] = len(getattr(data, "edges", []))

    mat_slots = getattr(obj, "material_slots", [])
    materials: List[str] = []
    for slot in mat_slots:
        mat = getattr(slot, "material", None)
        if mat:
            materials.append(getattr(mat, "name", ""))
    summary["materials"] = materials
    return summary


def execute_export_asset(bpy_module: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes bounded scene/object export with operator verification,
    sidecar checksum generation, and partial file cleanup.
    """
    raw_path = params.get("filepath")
    overwrite = bool(params.get("overwrite", False))
    selected_only = bool(params.get("selected_only", False))
    generate_sidecar = bool(params.get("generate_sidecar", True))

    allowed_root = os.environ.get("UMCP_WORKSPACE_ROOT") or (
        os.environ.get("UMCP_LOCAL_TEST_ROOT") if os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE") == "1" else None
    )
    norm_path = validate_asset_path(raw_path, overwrite=overwrite, is_export=True, allowed_root=allowed_root)

    fmt = params.get("format")
    if fmt:
        fmt = str(fmt).strip().upper()
    else:
        fmt = detect_format_from_path(norm_path)
        if not fmt:
            raise ValueError(
                f"Cannot auto-detect export format from extension '{os.path.splitext(norm_path)[1]}'. "
                "Specify 'format' parameter explicitly."
            )

    supported, op_name, reason = check_format_support(bpy_module, fmt, is_export=True)
    if not supported:
        raise RuntimeError(f"Export format '{fmt}' is unavailable: {reason}")

    exported_objects: List[str] = []
    if hasattr(bpy_module, "context"):
        if selected_only:
            sel = getattr(bpy_module.context, "selected_objects", [])
            exported_objects = [getattr(o, "name", "") for o in sel if hasattr(o, "name")]
        elif hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
            exported_objects = [getattr(o, "name", "") for o in bpy_module.data.objects if hasattr(o, "name")]

    sidecar_path = None
    try:
        if fmt in ("GLTF", "GLB"):
            export_fmt = "GLTF_SEPARATE" if fmt == "GLTF" else "GLB"
            bpy_module.ops.export_scene.gltf(
                filepath=norm_path,
                export_format=export_fmt,
                use_selection=selected_only,
            )
        elif fmt == "FBX":
            bpy_module.ops.export_scene.fbx(
                filepath=norm_path,
                use_selection=selected_only,
            )
        elif fmt in ("USD", "USDC", "USDA"):
            bpy_module.ops.wm.usd_export(
                filepath=norm_path,
                selected_objects_only=selected_only,
            )
        elif fmt == "OBJ":
            bpy_module.ops.wm.obj_export(
                filepath=norm_path,
                export_selected_objects=selected_only,
            )
        elif fmt == "STL":
            bpy_module.ops.wm.stl_export(
                filepath=norm_path,
                export_selected_objects=selected_only,
            )
        elif fmt == "PLY":
            bpy_module.ops.wm.ply_export(
                filepath=norm_path,
                export_selected_objects=selected_only,
            )
        elif fmt == "ABC":
            bpy_module.ops.wm.alembic_export(
                filepath=norm_path,
                selected=selected_only,
                as_background_job=False,
            )
        else:
            raise ValueError(f"Unhandled export format '{fmt}'")

        if not os.path.exists(norm_path):
            raise RuntimeError(f"Export operator completed but destination file '{norm_path}' was not created.")

        file_size = os.path.getsize(norm_path)
        if file_size == 0:
            raise RuntimeError(f"Export operator produced an empty 0-byte file: '{norm_path}'.")

        sha256_hash = compute_file_sha256(norm_path)
        if generate_sidecar:
            sidecar_path = generate_sha256_sidecar(
                norm_path,
                metadata={
                    "format": fmt,
                    "selected_only": selected_only,
                    "exported_objects": exported_objects,
                },
            )

        return {
            "success": True,
            "action": "export_scene_asset",
            "filepath": norm_path,
            "format": fmt,
            "file_size_bytes": file_size,
            "sha256": sha256_hash,
            "sidecar_path": sidecar_path,
            "selected_only": selected_only,
            "overwrite": overwrite,
            "exported_objects": exported_objects,
            "exported_count": len(exported_objects),
        }

    except Exception as exc:
        cleanup_partial_export(norm_path, sidecar_path)
        raise RuntimeError(f"Asset export failed for format '{fmt}': {exc}") from exc


def execute_import_asset(bpy_module: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes bounded 3D asset import with integrity verification,
    post-import topology readback, and rollback on error.
    """
    raw_path = params.get("filepath")
    verify_checksum = bool(params.get("verify_checksum", False))

    allowed_root = os.environ.get("UMCP_WORKSPACE_ROOT") or (
        os.environ.get("UMCP_LOCAL_TEST_ROOT") if os.environ.get("UMCP_LOCAL_TEST_AUTOAPPROVE") == "1" else None
    )
    norm_path = validate_asset_path(raw_path, overwrite=False, is_export=False, allowed_root=allowed_root)

    fmt = params.get("format")
    if fmt:
        fmt = str(fmt).strip().upper()
    else:
        fmt = detect_format_from_path(norm_path)
        if not fmt:
            raise ValueError(
                f"Cannot auto-detect import format from extension '{os.path.splitext(norm_path)[1]}'. "
                "Specify 'format' parameter explicitly."
            )

    supported, op_name, reason = check_format_support(bpy_module, fmt, is_export=False)
    if not supported:
        raise RuntimeError(f"Import format '{fmt}' is unavailable: {reason}")

    checksum_verified = False
    sidecar_msg = ""
    if verify_checksum:
        ok, msg, expected = verify_sha256_sidecar(norm_path)
        if not ok:
            raise ValueError(f"Asset integrity check failed: {msg}")
        checksum_verified = True
        sidecar_msg = msg

    # Snapshot existing datablocks for rollback on error
    before_objects: Set[str] = set(bpy_module.data.objects.keys()) if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects") else set()
    before_meshes: Set[str] = set(bpy_module.data.meshes.keys()) if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "meshes") else set()
    before_materials: Set[str] = set(bpy_module.data.materials.keys()) if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "materials") else set()

    try:
        if fmt in ("GLTF", "GLB"):
            bpy_module.ops.import_scene.gltf(filepath=norm_path)
        elif fmt == "FBX":
            bpy_module.ops.import_scene.fbx(filepath=norm_path)
        elif fmt in ("USD", "USDC", "USDA"):
            bpy_module.ops.wm.usd_import(filepath=norm_path)
        elif fmt == "OBJ":
            bpy_module.ops.wm.obj_import(filepath=norm_path)
        elif fmt == "STL":
            bpy_module.ops.wm.stl_import(filepath=norm_path)
        elif fmt == "PLY":
            bpy_module.ops.wm.ply_import(filepath=norm_path)
        elif fmt == "ABC":
            bpy_module.ops.wm.alembic_import(filepath=norm_path, as_background_job=False)
        else:
            raise ValueError(f"Unhandled import format '{fmt}'")

        after_objects: Set[str] = set(bpy_module.data.objects.keys()) if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects") else set()
        imported_names = sorted(list(after_objects - before_objects))

        object_details: List[Dict[str, Any]] = []
        if hasattr(bpy_module, "data") and hasattr(bpy_module.data, "objects"):
            for name in imported_names:
                obj = bpy_module.data.objects.get(name)
                if obj is not None:
                    object_details.append(inspect_object_summary(obj))

        return {
            "success": True,
            "action": "import_scene_asset",
            "filepath": norm_path,
            "format": fmt,
            "imported_count": len(imported_names),
            "imported_objects": imported_names,
            "object_details": object_details,
            "checksum_verified": checksum_verified,
            "sidecar_message": sidecar_msg,
        }

    except Exception as exc:
        rollback_import(bpy_module, before_objects, before_meshes, before_materials)
        raise RuntimeError(f"Asset import failed for format '{fmt}': {exc}") from exc

