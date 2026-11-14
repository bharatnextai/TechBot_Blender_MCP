"""
Delivery Manifest and Artifact Ledger (Phase 3.5).

Tracks all multi-format published artifacts with cryptographic SHA-256 hashes,
file sizes, format classifications, and automated integrity validation.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
import hashlib
import json
import time
import uuid
import logging

logger = logging.getLogger("UniversalMCP_DeliveryManifest")


def compute_file_sha256(filepath: Union[str, Path]) -> str:
    """Computes exact SHA-256 cryptographic digest of a file on disk."""
    p = Path(filepath)
    if not p.is_file():
        raise FileNotFoundError(f"Cannot compute SHA-256: file not found at {p}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class DeliveryArtifact:
    """An individual published asset file within a delivery package."""
    name: str
    relative_path: str
    absolute_path: str
    format: str
    file_size_bytes: int
    sha256: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path,
            "format": self.format,
            "file_size_bytes": self.file_size_bytes,
            "sha256": self.sha256,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeliveryArtifact":
        return cls(
            name=data["name"],
            relative_path=data["relative_path"],
            absolute_path=data["absolute_path"],
            format=data["format"],
            file_size_bytes=int(data["file_size_bytes"]),
            sha256=data["sha256"],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class DeliveryManifest:
    """
    Authoritative delivery manifest indexing all artifacts in a distribution package.
    """
    manifest_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str = "UniversalMCP_Production"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    blender_version: str = "5.2.2 LTS"
    artifacts: List[DeliveryArtifact] = field(default_factory=list)

    def add_artifact(self, artifact: DeliveryArtifact) -> None:
        self.artifacts.append(artifact)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": "1.0",
            "manifest_id": self.manifest_id,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "blender_version": self.blender_version,
            "artifact_count": len(self.artifacts),
            "artifacts": [a.to_dict() for a in self.artifacts],
        }

    def save_to_disk(self, directory: Union[str, Path]) -> Path:
        """Writes DELIVERY_MANIFEST.json to the output directory."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        manifest_path = dir_path / "DELIVERY_MANIFEST.json"
        manifest_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return manifest_path

    @classmethod
    def load_from_disk(cls, manifest_path: Union[str, Path]) -> "DeliveryManifest":
        p = Path(manifest_path)
        data = json.loads(p.read_text(encoding="utf-8"))
        manifest = cls(
            manifest_id=data.get("manifest_id", str(uuid.uuid4())),
            project_name=data.get("project_name", "UniversalMCP_Production"),
            created_at=data.get("created_at", ""),
            blender_version=data.get("blender_version", "5.2.2 LTS"),
        )
        for a_data in data.get("artifacts", []):
            manifest.add_artifact(DeliveryArtifact.from_dict(a_data))
        return manifest

    def verify_checksums(self) -> Tuple[bool, List[str]]:
        """
        Verifies all indexed artifacts against their actual disk files.
        Returns (all_valid, list_of_errors).
        """
        errors = []
        for a in self.artifacts:
            p = Path(a.absolute_path)
            if not p.is_file():
                errors.append(f"Missing artifact file: {a.relative_path} ({a.absolute_path})")
                continue
            actual_size = p.stat().st_size
            if actual_size != a.file_size_bytes:
                errors.append(f"Size mismatch on {a.name}: expected {a.file_size_bytes}, got {actual_size}")
                continue
            actual_hash = compute_file_sha256(p)
            if actual_hash != a.sha256:
                errors.append(f"Checksum mismatch on {a.name}: expected {a.sha256}, got {actual_hash}")

        return (len(errors) == 0, errors)

