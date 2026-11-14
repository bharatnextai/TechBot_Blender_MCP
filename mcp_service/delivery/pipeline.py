"""
Multi-Format Delivery Pipeline Engine (Phase 3.5).

Orchestrates multi-format delivery packages for production 3D assets:
- Web binary transmission (glTF / .glb)
- Production VFX interchange (USD / .usdc)
- Composited beauty still renders (.png)
- Cryptographic manifests (DELIVERY_MANIFEST.json) with SHA-256 sidecars
- Clean-session round-trip import sanity verification
- Strict path traversal prevention and overwrite collision guards
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import os
import time
import logging

from shared.models.protocol_models import BridgeResponse
from .manifest import DeliveryManifest, DeliveryArtifact, compute_file_sha256
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_DeliveryPipeline")


def validate_delivery_path(path_str: str, check_exists: bool = False, overwrite: bool = False) -> Path:
    """
    Validates a path against path traversal ('..') and absolute path requirements.
    Fails closed if parent traversal or forbidden relative references are detected.
    """
    if not path_str or not isinstance(path_str, str):
        raise ValueError("Delivery path must be a non-empty string.")

    clean = path_str.strip()
    if not clean:
        raise ValueError("Delivery path cannot be whitespace.")

    norm_segments = clean.replace("\\", "/").split("/")
    if ".." in norm_segments:
        raise ValueError(f"Path traversal detected: '..' segments are strictly forbidden: '{clean}'")

    p = Path(clean)
    if not p.is_absolute():
        raise ValueError(f"Delivery path must be an absolute path, got: '{clean}'")

    if check_exists and p.exists() and not overwrite:
        raise FileExistsError(f"Destination file already exists and overwrite=False: '{clean}'")

    return p


@dataclass
class DeliveryConfig:
    """Configuration for multi-format production asset publishing."""
    output_dir: str
    base_name: str = "asset_delivery"
    project_name: str = "UniversalMCP_Production"
    blender_version: str = "5.2.2 LTS"
    export_glb: bool = True
    export_usd: bool = True
    render_beauty_still: bool = True
    overwrite: bool = False
    camera_name: Optional[str] = None
    selected_only: bool = False
    render_frame: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validates configuration parameters and safety boundaries."""
        if not self.base_name or not self.base_name.strip():
            raise ValueError("base_name must be a non-empty string.")
        if ".." in self.base_name or "/" in self.base_name or "\\" in self.base_name:
            raise ValueError(f"Invalid base_name '{self.base_name}': cannot contain path separators or '..'.")
        validate_delivery_path(self.output_dir)


class DeliveryPipeline:
    """
    Automated multi-format packaging engine.
    Publishes Web (GLB), VFX (USDC), and Beauty Stills with cryptographic manifests.
    """

    def __init__(self, config: DeliveryConfig):
        config.validate()
        self.config = config
        self.out_dir = Path(config.output_dir)

    def publish(self, executor: BlenderExecutor, trusted_approval: bool = True) -> DeliveryManifest:
        """
        Executes multi-format publishing against Blender via the executor.
        Generates GLB, USDC, beauty still PNG, SHA-256 sidecars, and DELIVERY_MANIFEST.json.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)
        manifest = DeliveryManifest(
            project_name=self.config.project_name,
            blender_version=self.config.blender_version,
        )

        artifacts_to_publish = []
        if self.config.export_glb:
            artifacts_to_publish.append(("GLB", f"{self.config.base_name}.glb", "web_binary_gltf"))
        if self.config.export_usd:
            artifacts_to_publish.append(("USDC", f"{self.config.base_name}.usdc", "vfx_universal_scene_description"))

        # 1. Pre-flight overwrite checks
        for fmt, filename, _ in artifacts_to_publish:
            target_file = self.out_dir / filename
            if target_file.exists() and not self.config.overwrite:
                raise FileExistsError(
                    f"Destination artifact already exists: '{target_file}'. "
                    "Set overwrite=True to allow replacing existing deliveries."
                )

        if self.config.render_beauty_still:
            target_still = self.out_dir / f"{self.config.base_name}_beauty.png"
            if target_still.exists() and not self.config.overwrite:
                raise FileExistsError(
                    f"Destination still render already exists: '{target_still}'. "
                    "Set overwrite=True to allow replacing existing deliveries."
                )

        # 2. Execute 3D Asset Exports
        for fmt, filename, role in artifacts_to_publish:
            target_file = self.out_dir / filename
            export_args = {
                "filepath": str(target_file),
                "format": fmt,
                "overwrite": self.config.overwrite,
                "selected_only": self.config.selected_only,
                "generate_sidecar": True,
            }
            res = executor.execute_tool("export_scene_asset", export_args, trusted_approval=trusted_approval)
            if not res.is_success:
                raise RuntimeError(f"Failed to export {fmt} delivery artifact: {res.error}")

            if not target_file.is_file():
                raise FileNotFoundError(f"Export succeeded but file not found on disk: {target_file}")

            file_size = target_file.stat().st_size
            sha256_hash = compute_file_sha256(target_file)

            # Ensure sidecar exists for the 3D asset
            sidecar_file = target_file.with_name(f"{target_file.name}.sha256")
            if not sidecar_file.exists():
                import json
                sidecar_payload = {
                    "filepath": str(target_file.resolve()),
                    "filename": target_file.name,
                    "sha256": sha256_hash,
                    "file_size_bytes": file_size,
                    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "format": fmt,
                }
                sidecar_file.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")

            artifact = DeliveryArtifact(
                name=filename,
                relative_path=filename,
                absolute_path=str(target_file),
                format=fmt,
                file_size_bytes=file_size,
                sha256=sha256_hash,
                metadata={
                    "role": role,
                    "exported_objects": res.result.get("exported_objects", []) if res.result else [],
                    "selected_only": self.config.selected_only,
                },
            )
            manifest.add_artifact(artifact)

        # 3. Execute Beauty Still Render
        if self.config.render_beauty_still:
            target_still = self.out_dir / f"{self.config.base_name}_beauty.png"
            render_args = {
                "render_mode": "still",
                "output_path": str(target_still),
                "output_format": "PNG",
            }
            if self.config.camera_name:
                render_args["camera"] = self.config.camera_name
            if self.config.render_frame is not None:
                render_args["frame"] = self.config.render_frame

            res = executor.execute_tool("render_scene", render_args, trusted_approval=trusted_approval)
            if not res.is_success:
                raise RuntimeError(f"Failed to render beauty still delivery artifact: {res.error}")

            # Blender may output target_still or resolve output_file
            actual_file = target_still
            if res.result and res.result.get("output_file"):
                reported = Path(res.result["output_file"])
                if reported.is_file():
                    actual_file = reported

            if not actual_file.is_file():
                raise FileNotFoundError(f"Render succeeded but still image not found on disk: {actual_file}")

            still_size = actual_file.stat().st_size
            still_hash = compute_file_sha256(actual_file)

            # Generate sidecar for still image
            still_sidecar = actual_file.with_name(f"{actual_file.name}.sha256")
            import json
            sidecar_payload = {
                "filepath": str(actual_file.resolve()),
                "filename": actual_file.name,
                "sha256": still_hash,
                "file_size_bytes": still_size,
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "format": "PNG",
            }
            still_sidecar.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")

            still_artifact = DeliveryArtifact(
                name=actual_file.name,
                relative_path=actual_file.name,
                absolute_path=str(actual_file),
                format="PNG",
                file_size_bytes=still_size,
                sha256=still_hash,
                metadata={
                    "role": "beauty_still_render",
                    "camera": res.result.get("camera") if res.result else None,
                    "resolution": [res.result.get("width"), res.result.get("height")] if res.result else None,
                },
            )
            manifest.add_artifact(still_artifact)

        # 4. Save Authoritative Manifest
        manifest.save_to_disk(self.out_dir)
        return manifest

    def verify_clean_import(
        self,
        executor: BlenderExecutor,
        manifest: DeliveryManifest,
        trusted_approval: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes round-trip import sanity verification for published 3D assets.
        Validates that published formats load cleanly back into Blender.
        """
        results = []
        for artifact in manifest.artifacts:
            if artifact.format in ("GLB", "GLTF", "USDC", "USD", "USDA", "FBX"):
                import_args = {
                    "filepath": artifact.absolute_path,
                    "format": artifact.format,
                    "verify_checksum": True,
                }
                res = executor.execute_tool("import_scene_asset", import_args, trusted_approval=trusted_approval)
                if not res.is_success:
                    raise RuntimeError(
                        f"Round-trip import sanity verification failed for artifact '{artifact.name}': {res.error}"
                    )
                results.append({
                    "artifact": artifact.name,
                    "format": artifact.format,
                    "imported_count": res.result.get("imported_count", 0) if res.result else 0,
                    "imported_objects": res.result.get("imported_objects", []) if res.result else [],
                    "checksum_verified": res.result.get("checksum_verified", False) if res.result else False,
                })

        return {
            "status": "success",
            "verified_artifact_count": len(results),
            "results": results,
        }
