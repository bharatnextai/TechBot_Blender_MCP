"""Build and verify a fresh v0.1.90 Blender add-on candidate ZIP.

This helper only writes the new candidate filename and its checksum sidecar.
It refuses to overwrite either file and never touches historical releases.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "blender_addon" / "universal_mcp"
DIST = ROOT / "dist"
ARCHIVE = DIST / "Universal-MCP-Blender-0.1.90-candidate.zip"
SIDECAR = Path(str(ARCHIVE) + ".sha256")
VERSION = "0.1.90"
EXCLUDED_DIRS = {
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "tests", "test", "fixtures", "docs", "examples", "dev", "development",
}
ALLOWED_SUFFIXES = {".py", ".toml", ".png", ".jpg", ".jpeg", ".svg"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pyd", ".blend", ".blend1", ".log", ".tmp"}


def package_files() -> list[Path]:
    """Return a dynamically discovered, deterministic add-on runtime file list."""
    files = []
    for current, dirs, names in os.walk(SOURCE):
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS and not d.startswith(".")
        )
        current_path = Path(current)
        for name in names:
            path = current_path / name
            rel = path.relative_to(SOURCE)
            suffix = path.suffix.lower()
            if name.startswith(".") or suffix in EXCLUDED_SUFFIXES:
                continue
            if suffix not in ALLOWED_SUFFIXES:
                continue
            if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
                continue
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(SOURCE).as_posix())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_candidate(paths: list[Path]) -> tuple[str, int]:
    source_by_name = {p.relative_to(SOURCE).as_posix(): p for p in paths}
    with zipfile.ZipFile(ARCHIVE, "r") as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"ZIP CRC failure in {bad_member}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("ZIP contains duplicate member names")
        if set(names) != set(source_by_name):
            missing = sorted(set(source_by_name) - set(names))
            extra = sorted(set(names) - set(source_by_name))
            raise RuntimeError(f"Archive/source member mismatch; missing={missing}, extra={extra}")
        if any("__pycache__" in n or n.endswith((".pyc", ".pyo", ".pyd")) for n in names):
            raise RuntimeError("Archive contains cache or bytecode files")

        for name, source_path in source_by_name.items():
            if archive.read(name) != source_path.read_bytes():
                raise RuntimeError(f"Packaged bytes differ from source: {name}")

        manifest = archive.read("blender_manifest.toml").decode("utf-8")
        legacy_manifest = archive.read("manifest.toml").decode("utf-8")
        version_line = f'version = "{VERSION}"'
        if version_line not in manifest.splitlines():
            raise RuntimeError("blender_manifest.toml does not declare v0.1.90")
        if version_line not in legacy_manifest.splitlines():
            raise RuntimeError("One or more packaged manifests do not declare v0.1.90")
        init_text = archive.read("__init__.py").decode("utf-8")
        if '"version": (0, 1, 90)' not in init_text:
            raise RuntimeError("Packaged bl_info does not declare v0.1.90")
        if "branding.py" not in names or "assets/techbot81_icon.png" not in names:
            raise RuntimeError("Required Techbot81 branding files are absent")
        if any(
            name.lower().startswith("test") and name.lower().endswith(".py")
            for name in names
        ):
            raise RuntimeError("Development test file found in add-on archive")
        return sha256_file(ARCHIVE), len(names)


def main() -> None:
    if not SOURCE.is_dir():
        raise FileNotFoundError(f"Add-on source directory not found: {SOURCE}")
    DIST.mkdir(parents=True, exist_ok=True)
    if SIDECAR.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing checksum sidecar: {SIDECAR}"
        )

    paths = package_files()
    if not paths:
        raise RuntimeError("No packageable add-on files were discovered")
    for required in ("__init__.py", "manifest.toml", "blender_manifest.toml", "branding.py", "assets/techbot81_icon.png"):
        if required not in {p.relative_to(SOURCE).as_posix() for p in paths}:
            raise RuntimeError(f"Required source file is absent from candidate inventory: {required}")

    if ARCHIVE.exists():
        print(f"Candidate already exists; verifying without replacement: {ARCHIVE}")
    else:
        # Exclusive create guarantees this helper cannot overwrite an existing ZIP.
        with ARCHIVE.open("xb") as raw_zip:
            with zipfile.ZipFile(raw_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path in paths:
                    rel = path.relative_to(SOURCE).as_posix()
                    info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    digest, count = verify_candidate(paths)
    with SIDECAR.open("x", encoding="ascii", newline="\n") as checksum:
        checksum.write(f"{digest} *{ARCHIVE.name}\n")

    print(f"Candidate: {ARCHIVE}")
    print(f"Entries: {count} (discovered dynamically)")
    print(f"Size: {ARCHIVE.stat().st_size} bytes")
    print(f"SHA-256: {digest}")
    print(f"Sidecar: {SIDECAR}")
    print("CRC, manifests, source parity, required branding files, and cache exclusions: PASS")


if __name__ == "__main__":
    main()
