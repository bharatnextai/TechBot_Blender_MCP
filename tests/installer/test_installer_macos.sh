#!/usr/bin/env bash
# ==============================================================================
# TechBot_Blender_MCP: Native macOS Installer Test Runner (Bash)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "================================================================="
echo "Starting TechBot_Blender_MCP macOS Installer Test Suite"
echo "Repository Root: ${REPO_ROOT}"
echo "================================================================="

# Locate Python 3
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "ERROR: python3 executable not found!" >&2
    exit 1
fi

echo "Using Python: ${PYTHON_BIN}"
"${PYTHON_BIN}" "${SCRIPT_DIR}/test_installer_macos.py" -v

echo "================================================================="
echo "macOS Installer Test Suite Complete: ALL TESTS PASSED"
echo "================================================================="
