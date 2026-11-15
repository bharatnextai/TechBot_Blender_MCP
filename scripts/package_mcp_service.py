"""Build and verify a standalone MCP Service distribution ZIP for TechBot_Blender_MCP.

This distribution package contains the external MCP service, shared schemas,
minimal required bridge constants, pyproject.toml, and dependencies needed
to install the MCP service in an isolated virtual environment.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = "1.0.0"
ARCHIVE = DIST / f"TechBot_Blender_MCP_Service-{VERSION}.zip"
SIDECAR = Path(str(ARCHIVE) + ".sha256")

EXCLUDED_DIRS = {
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "tests", "test", "fixtures", "output", "dist", "scratch",
}
ALLOWED_SUFFIXES = {".py", ".toml", ".png", ".jpg", ".jpeg", ".svg", ".md", ".txt", ".lock"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pyd", ".blend", ".blend1", ".log", ".tmp"}


def discover_files() -> list[tuple[Path, str]]:
    """Return files to include with their relative archive paths."""
    files: list[tuple[Path, str]] = []

    # 1. Root metadata
    for name in ("pyproject.toml", "uv.lock", "LICENSE", "README.md"):
        p = ROOT / name
        if p.is_file():
            files.append((p, name))

    # 2. Package directories: mcp_service, shared, blender_addon
    for pkg_dir in ("mcp_service", "shared", "blender_addon"):
        base = ROOT / pkg_dir
        if not base.is_dir():
            continue
        for current, dirs, names in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith("."))
            for name in names:
                path = Path(current) / name
                suffix = path.suffix.lower()
                if name.startswith(".") or suffix in EXCLUDED_SUFFIXES:
                    continue
                if suffix not in ALLOWED_SUFFIXES:
                    continue
                if name.startswith("test_") or name.endswith("_test.py"):
                    continue
                rel = path.relative_to(ROOT).as_posix()
                files.append((path, rel))

    return sorted(files, key=lambda x: x[1])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    files = discover_files()
    if not files:
        raise RuntimeError("No files discovered for MCP service distribution")

    print(f"Packaging {len(files)} files into {ARCHIVE.name}...")

    # Write archive deterministically
    with ARCHIVE.open("wb") as raw_zip:
        with zipfile.ZipFile(raw_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, rel in files:
                info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    # Verify CRC
    with zipfile.ZipFile(ARCHIVE, "r") as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"CRC check failed in {bad}")
        names = archive.namelist()

    digest = sha256_file(ARCHIVE)
    with SIDECAR.open("w", encoding="ascii", newline="\n") as checksum:
        checksum.write(f"{digest} *{ARCHIVE.name}\n")

    print(f"Archive:  {ARCHIVE}")
    print(f"Entries:  {len(names)}")
    print(f"Size:     {ARCHIVE.stat().st_size} bytes")
    print(f"SHA-256:  {digest}")
    print(f"Sidecar:  {SIDECAR}")


if __name__ == "__main__":
    main()
