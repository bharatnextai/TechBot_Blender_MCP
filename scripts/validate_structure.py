#!/usr/bin/env python3
"""
Validates that the Universal MCP Plugin for Blender repository structure
adheres strictly to the architectural specifications.
"""

import os
import sys

REQUIRED_DIRECTORIES = [
    "docs",
    "blender_addon/universal_mcp",
    "blender_addon/universal_mcp/ui",
    "blender_addon/universal_mcp/bridge",
    "blender_addon/universal_mcp/lifecycle",
    "mcp_service",
    "mcp_service/server",
    "mcp_service/client",
    "mcp_service/transports",
    "mcp_service/registry",
    "mcp_service/security",
    "mcp_service/execution",
    "mcp_service/configuration",
    "mcp_service/observability",
    "shared",
    "shared/schemas",
    "shared/models",
    "tests/unit",
    "tests/protocol",
    "tests/security",
    "tests/blender_integration",
    "scripts",
    "examples/client_configuration",
]

REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "docs/ARCHITECTURE.md",
    "docs/SECURITY.md",
    "docs/CLIENT_SETUP.md",
    "docs/DEVELOPMENT.md",
    "docs/COMPATIBILITY.md",
]

PACKAGE_INIT_DIRECTORIES = [
    "blender_addon",
    "blender_addon/universal_mcp",
    "blender_addon/universal_mcp/ui",
    "blender_addon/universal_mcp/bridge",
    "blender_addon/universal_mcp/lifecycle",
    "mcp_service",
    "mcp_service/server",
    "mcp_service/client",
    "mcp_service/transports",
    "mcp_service/registry",
    "mcp_service/security",
    "mcp_service/execution",
    "mcp_service/configuration",
    "mcp_service/observability",
    "shared",
    "shared/schemas",
    "shared/models",
    "tests",
    "tests/unit",
    "tests/protocol",
    "tests/security",
    "tests/blender_integration",
]


def validate(root_dir: str) -> bool:
    print(f"Validating Universal MCP repository structure at: {root_dir}")
    all_passed = True

    print("\n1. Checking Required Directories:")
    for d in REQUIRED_DIRECTORIES:
        full_d = os.path.join(root_dir, d.replace("/", os.sep))
        if os.path.isdir(full_d):
            print(f"  [OK] {d}")
        else:
            print(f"  [MISSING DIR] {d}")
            all_passed = False

    print("\n2. Checking Required Files:")
    for f in REQUIRED_FILES:
        full_f = os.path.join(root_dir, f.replace("/", os.sep))
        if os.path.isfile(full_f):
            print(f"  [OK] {f}")
        else:
            print(f"  [MISSING FILE] {f}")
            all_passed = False

    print("\n3. Checking Python Package __init__.py files:")
    for p in PACKAGE_INIT_DIRECTORIES:
        init_file = os.path.join(root_dir, p.replace("/", os.sep), "__init__.py")
        if os.path.isfile(init_file):
            print(f"  [OK] {p}/__init__.py")
        else:
            print(f"  [MISSING INIT] {p}/__init__.py")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL REPOSITORY STRUCTURE CHECKS PASSED SUCCESSFULLY!")
        print("=" * 60)
        return True
    else:
        print("STRUCTURE VALIDATION FAILED: Some required directories or files are missing.")
        print("=" * 60)
        return False


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    success = validate(project_root)
    sys.exit(0 if success else 1)
