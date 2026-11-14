"""
Unit tests for Phase 3.5 Multi-Format Delivery Pipelines & Asset Publishing.
Verifies DeliveryConfig, validate_delivery_path, DeliveryArtifact, DeliveryManifest,
DeliveryPipeline publishing flow, sidecar integrity, and import round-trip contracts.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock

from mcp_service.delivery.manifest import DeliveryArtifact, DeliveryManifest, compute_file_sha256
from mcp_service.delivery.pipeline import (
    DeliveryConfig,
    DeliveryPipeline,
    validate_delivery_path,
)
from shared.models.protocol_models import BridgeResponse


def test_validate_delivery_path():
    """Verifies strict path validation and traversal prevention."""
    with tempfile.TemporaryDirectory() as tmpdir:
        valid_path = Path(tmpdir) / "output.glb"
        validated = validate_delivery_path(str(valid_path))
        assert validated == valid_path

        # Relative paths rejected
        with pytest.raises(ValueError, match="must be an absolute path"):
            validate_delivery_path("relative/path/output.glb")

        # Path traversal rejected
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_delivery_path(str(valid_path / ".." / "escape.glb"))

        # Empty / whitespace rejected
        with pytest.raises(ValueError, match="non-empty string"):
            validate_delivery_path("")


def test_delivery_path_overwrite_check():
    """Verifies pre-flight file existence and overwrite protection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "existing_asset.glb"
        file_path.write_text("dummy content", encoding="utf-8")

        # Should raise FileExistsError when overwrite=False
        with pytest.raises(FileExistsError, match="overwrite=False"):
            validate_delivery_path(str(file_path), check_exists=True, overwrite=False)

        # Passes when overwrite=True
        res = validate_delivery_path(str(file_path), check_exists=True, overwrite=True)
        assert res == file_path


def test_delivery_manifest_roundtrip_and_checksums():
    """Verifies manifest serialization, disk save/load, and cryptographic SHA-256 checks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        glb_file = tmp_path / "hero.glb"
        glb_file.write_bytes(b"GLTF_BINARY_TEST_DATA_PAYLOAD_12345")

        usd_file = tmp_path / "hero.usdc"
        usd_file.write_bytes(b"USD_BINARY_CRATE_PAYLOAD_ABCDE")

        sha_glb = compute_file_sha256(glb_file)
        sha_usd = compute_file_sha256(usd_file)

        manifest = DeliveryManifest(project_name="TestProject")
        manifest.add_artifact(DeliveryArtifact(
            name="hero.glb",
            relative_path="hero.glb",
            absolute_path=str(glb_file),
            format="GLB",
            file_size_bytes=glb_file.stat().st_size,
            sha256=sha_glb,
        ))
        manifest.add_artifact(DeliveryArtifact(
            name="hero.usdc",
            relative_path="hero.usdc",
            absolute_path=str(usd_file),
            format="USDC",
            file_size_bytes=usd_file.stat().st_size,
            sha256=sha_usd,
        ))

        manifest_file = manifest.save_to_disk(tmp_path)
        assert manifest_file.is_file()

        # Reload from disk
        loaded = DeliveryManifest.load_from_disk(manifest_file)
        assert loaded.project_name == "TestProject"
        assert len(loaded.artifacts) == 2

        # Checksums verify
        valid, errors = loaded.verify_checksums()
        assert valid is True
        assert len(errors) == 0

        # Tamper with file (same size, altered content)
        glb_file.write_bytes(b"X" * len(b"GLTF_BINARY_TEST_DATA_PAYLOAD_12345"))
        valid, errors = loaded.verify_checksums()
        assert valid is False
        assert any("Checksum mismatch" in e for e in errors)

        # Truncate file (size mismatch)
        glb_file.write_bytes(b"SHORT")
        valid, errors = loaded.verify_checksums()
        assert valid is False
        assert any("Size mismatch" in e for e in errors)


def test_delivery_config_validation():
    """Verifies DeliveryConfig parameter guards."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Valid config
        cfg = DeliveryConfig(output_dir=tmpdir, base_name="hero_prop")
        cfg.validate()

        # Invalid base_name with path traversal
        with pytest.raises(ValueError, match="Invalid base_name"):
            DeliveryConfig(output_dir=tmpdir, base_name="../hero_prop").validate()

        # Invalid base_name with slash
        with pytest.raises(ValueError, match="Invalid base_name"):
            DeliveryConfig(output_dir=tmpdir, base_name="folder/hero").validate()


def test_delivery_pipeline_mock_execution():
    """Verifies DeliveryPipeline execution flow against mocked executor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = DeliveryConfig(
            output_dir=tmpdir,
            base_name="scene_delivery",
            export_glb=True,
            export_usd=True,
            render_beauty_still=True,
            overwrite=True,
        )
        pipeline = DeliveryPipeline(cfg)

        mock_executor = MagicMock()

        def fake_execute_tool(tool_name, params, trusted_approval=True):
            if tool_name == "export_scene_asset":
                fp = Path(params["filepath"])
                fp.write_bytes(b"EXPORTED_MOCK_3D_BINARY")
                return BridgeResponse.success({
                    "action": "export_scene_asset",
                    "filepath": str(fp),
                    "format": params["format"],
                    "file_size_bytes": fp.stat().st_size,
                    "sha256": compute_file_sha256(fp),
                    "exported_objects": ["Cube", "Light"],
                })
            elif tool_name == "render_scene":
                fp = Path(params["output_path"])
                fp.write_bytes(b"RENDERED_MOCK_PNG_IMAGE")
                return BridgeResponse.success({
                    "action": "render_scene",
                    "output_file": str(fp),
                    "output_paths": [str(fp)],
                    "width": 1920,
                    "height": 1080,
                    "camera": "Camera",
                })
            elif tool_name == "import_scene_asset":
                return BridgeResponse.success({
                    "action": "import_scene_asset",
                    "imported_count": 2,
                    "imported_objects": ["Cube", "Light"],
                    "checksum_verified": True,
                })
            return BridgeResponse.error(f"Unknown tool {tool_name}")

        mock_executor.execute_tool.side_effect = fake_execute_tool

        manifest = pipeline.publish(mock_executor)

        assert len(manifest.artifacts) == 3
        names = {a.name for a in manifest.artifacts}
        assert names == {"scene_delivery.glb", "scene_delivery.usdc", "scene_delivery_beauty.png"}

        # Verify sidecars exist on disk
        assert (Path(tmpdir) / "scene_delivery.glb.sha256").exists()
        assert (Path(tmpdir) / "scene_delivery.usdc.sha256").exists()
        assert (Path(tmpdir) / "scene_delivery_beauty.png.sha256").exists()
        assert (Path(tmpdir) / "DELIVERY_MANIFEST.json").exists()

        # Verify manifest checksum integrity
        valid, errors = manifest.verify_checksums()
        assert valid is True
        assert len(errors) == 0

        # Verify clean import round-trip
        import_result = pipeline.verify_clean_import(mock_executor, manifest)
        assert import_result["status"] == "success"
        assert import_result["verified_artifact_count"] == 2
