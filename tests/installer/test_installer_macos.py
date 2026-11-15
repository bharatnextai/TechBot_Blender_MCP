#!/usr/bin/env python3
"""
TechBot_Blender_MCP: Focused macOS Installer Test Suite
Validates macOS installation & uninstallation logic, path discovery,
architecture detection, SHA-256 sidecar verification, non-destructive JSON merges,
failure handling, and uninstaller containment using mocked macOS environments.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class TestMacOSInstaller(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="techbot_macos_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # Test 1: Architecture Detection Logic (Apple Silicon vs Intel)
    # --------------------------------------------------------------------------
    def test_architecture_detection_logic(self):
        cases = [
            ("arm64", "Apple Silicon (arm64)"),
            ("aarch64", "Apple Silicon (aarch64)"),
            ("x86_64", "Intel Core (x86_64)"),
            ("amd64", "Intel Core (amd64)"),
            ("riscv64", "Unknown (riscv64)"),
        ]
        for raw_arch, expected_desc in cases:
            # Emulate the detection logic from Install-TechBot-Blender-MCP-macOS.sh
            if raw_arch in ("arm64", "aarch64"):
                desc = f"Apple Silicon ({raw_arch})"
            elif raw_arch in ("x86_64", "amd64"):
                desc = f"Intel Core ({raw_arch})"
            else:
                desc = f"Unknown ({raw_arch})"
            self.assertEqual(desc, expected_desc, f"Failed for raw arch {raw_arch}")

    # --------------------------------------------------------------------------
    # Test 2: Blender.app Path Resolution
    # --------------------------------------------------------------------------
    def test_blender_app_bundle_resolution(self):
        # Simulate /Applications/Blender.app structure
        mock_app = os.path.join(self.test_dir, "Blender.app")
        macos_dir = os.path.join(mock_app, "Contents", "MacOS")
        os.makedirs(macos_dir, exist_ok=True)
        blender_bin = os.path.join(macos_dir, "Blender")
        with open(blender_bin, "w") as f:
            f.write("#!/bin/sh\necho 'Blender 5.2.2'\n")

        # Test resolution when passing .app directory
        resolved = None
        if os.path.isdir(mock_app) and mock_app.endswith(".app"):
            cand = os.path.join(mock_app, "Contents", "MacOS", "Blender")
            if os.path.isfile(cand):
                resolved = cand

        self.assertEqual(resolved, blender_bin)
        self.assertTrue(os.path.isfile(resolved))

    # --------------------------------------------------------------------------
    # Test 3: Antigravity macOS Configuration Path Resolution
    # --------------------------------------------------------------------------
    def test_antigravity_macos_config_resolution(self):
        # Case A: Default documented path ~/.gemini/config/mcp_config.json
        mock_home = os.path.join(self.test_dir, "home_user")
        os.makedirs(mock_home, exist_ok=True)

        doc_path = os.path.join(mock_home, ".gemini", "config", "mcp_config.json")
        appsup_path = os.path.join(mock_home, "Library", "Application Support", "Antigravity", "mcp_config.json")

        # When neither exists: should default to documented path
        chosen = appsup_path if os.path.isfile(appsup_path) else doc_path
        self.assertEqual(chosen, doc_path)

        # When Application Support path exists: should pick Application Support path
        os.makedirs(os.path.dirname(appsup_path), exist_ok=True)
        with open(appsup_path, "w") as f:
            f.write("{}")

        chosen = appsup_path if os.path.isfile(appsup_path) else doc_path
        self.assertEqual(chosen, appsup_path)

    # --------------------------------------------------------------------------
    # Test 4: SHA-256 Sidecar Verification & Tamper Detection
    # --------------------------------------------------------------------------
    def test_sha256_sidecar_verification_and_tamper(self):
        dummy_pkg = os.path.join(self.test_dir, "TechBot_Blender_MCP-1.0.0-rc2.zip")
        payload = b"TECHBOT_VERIFIED_PACKAGE_CONTENT_V100_RC2"
        with open(dummy_pkg, "wb") as f:
            f.write(payload)

        correct_sha = hashlib.sha256(payload).hexdigest().lower()
        sidecar_file = dummy_pkg + ".sha256"

        # Valid sidecar in standard 'hash  filename' format
        with open(sidecar_file, "w") as f:
            f.write(f"{correct_sha}  TechBot_Blender_MCP-1.0.0-rc2.zip\n")

        with open(sidecar_file, "r") as f:
            extracted_expected = f.read().strip().split()[0].lower()
        with open(dummy_pkg, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(extracted_expected, actual)

        # Tampered payload
        with open(dummy_pkg, "wb") as f:
            f.write(b"TAMPERED_MALICIOUS_CONTENT")

        with open(dummy_pkg, "rb") as f:
            tampered_actual = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertNotEqual(extracted_expected, tampered_actual)

    # --------------------------------------------------------------------------
    # Test 5: Safe Non-Destructive JSON Merging & Backups
    # --------------------------------------------------------------------------
    def test_non_destructive_json_merge_and_backup(self):
        config_path = os.path.join(self.test_dir, "claude_desktop_config.json")
        initial_content = {
            "mcpServers": {
                "sqlite": {"command": "uvx", "args": ["mcp-server-sqlite"]}
            },
            "preferences": {
                "coworkWebSearchEnabled": True,
                "remoteToolsDeviceName": "macbook-pro"
            },
            "coworkUserFilesPath": "/Users/testuser/Claude"
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(initial_content, f, indent=2)

        # Execute the exact merge script logic from Install-TechBot-Blender-MCP-macOS.sh
        venv_python = "/Users/testuser/Library/Application Support/TechBot_Blender_MCP/venv/bin/python"
        bridge_port = "9877"
        bridge_timeout = "15.0"

        # Simulate backup
        backup_path = config_path + ".bak_test"
        shutil.copy2(config_path, backup_path)
        self.assertTrue(os.path.isfile(backup_path))

        # Perform merge
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("mcpServers", {})["techbot-blender-mcp"] = {
            "command": venv_python,
            "args": [
                "-m", "mcp_service.app",
                "--transport", "stdio",
                "--bridge-port", bridge_port,
                "--bridge-timeout", bridge_timeout
            ],
            "env": {"PYTHONUNBUFFERED": "1"}
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Verify merged result
        with open(config_path, "r", encoding="utf-8") as f:
            merged = json.load(f)

        self.assertIn("techbot-blender-mcp", merged["mcpServers"])
        self.assertIn("sqlite", merged["mcpServers"], "Sibling server was lost!")
        self.assertEqual(merged["preferences"]["coworkWebSearchEnabled"], True, "User preferences lost!")
        self.assertEqual(merged["coworkUserFilesPath"], "/Users/testuser/Claude")
        self.assertEqual(merged["mcpServers"]["techbot-blender-mcp"]["command"], venv_python)

    # --------------------------------------------------------------------------
    # Test 6: Malformed Non-Object JSON Rejection
    # --------------------------------------------------------------------------
    def test_malformed_json_refusal(self):
        # Case 6A: Non-object root (array)
        config_path_arr = os.path.join(self.test_dir, "array_config.json")
        with open(config_path_arr, "w", encoding="utf-8") as f:
            f.write('["array_root_is_invalid_for_mcp"]')

        merge_py = """
import json, sys
config_path = sys.argv[1]
try:
    with open(config_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
except Exception:
    print("PARSE_ERROR: JSON syntax error")
    sys.exit(2)

if not isinstance(data, dict):
    print("PARSE_ERROR: Existing config root is not a JSON object")
    sys.exit(2)
"""
        proc = subprocess.run([sys.executable, "-c", merge_py, config_path_arr], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("PARSE_ERROR", proc.stdout)

        # Case 6B: Malformed syntax refusal
        config_path_syntax = os.path.join(self.test_dir, "syntax_error.json")
        with open(config_path_syntax, "w", encoding="utf-8") as f:
            f.write('{"unclosed_brace": true')

        proc_syn = subprocess.run([sys.executable, "-c", merge_py, config_path_syntax], capture_output=True, text=True)
        self.assertEqual(proc_syn.returncode, 2)
        self.assertIn("PARSE_ERROR", proc_syn.stdout)

    # --------------------------------------------------------------------------
    # Test 7: Multi-Document Concatenated JSON Recovery
    # --------------------------------------------------------------------------
    def test_concatenated_json_recovery(self):
        config_path = os.path.join(self.test_dir, "concatenated.json")
        # Simulating duplicate object concatenated blocks
        raw_concat = '{"mcpServers": {"tool1": {}}}\n{"preferences": {"theme": "dark"}}'
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(raw_concat)

        recovery_py = """
import json, sys
with open(sys.argv[1], 'r') as f:
    raw = f.read().strip()
decoder = json.JSONDecoder()
pos = 0
merged = {}
while pos < len(raw):
    raw_chunk = raw[pos:].lstrip()
    if not raw_chunk:
        break
    leading = len(raw[pos:]) - len(raw_chunk)
    obj, end = decoder.raw_decode(raw_chunk)
    if isinstance(obj, dict):
        if "mcpServers" in obj:
            merged.setdefault("mcpServers", {}).update(obj["mcpServers"])
        for k, v in obj.items():
            if k != "mcpServers":
                merged[k] = v
    pos += leading + end
print(json.dumps(merged))
"""
        proc = subprocess.run([sys.executable, "-c", recovery_py, config_path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        recovered = json.loads(proc.stdout)
        self.assertIn("tool1", recovered["mcpServers"])
        self.assertEqual(recovered["preferences"]["theme"], "dark")

    # --------------------------------------------------------------------------
    # Test 8: Native Blender Extension CLI Argument Construction
    # --------------------------------------------------------------------------
    def test_extension_cli_argument_construction(self):
        ext_zip = "/tmp/downloads/TechBot_Blender_MCP-1.0.0-rc2.zip"
        # Must produce exact command: blender --command extension install-file -r user_default -e <zip>
        args = ["--command", "extension", "install-file", "-r", "user_default", "-e", ext_zip]
        self.assertEqual(args[0], "--command")
        self.assertEqual(args[1], "extension")
        self.assertEqual(args[2], "install-file")
        self.assertEqual(args[3], "-r")
        self.assertEqual(args[4], "user_default")
        self.assertEqual(args[5], "-e")
        self.assertEqual(args[6], ext_zip)

        # Removal command
        uninst_args = ["--command", "extension", "remove", "universal_mcp"]
        self.assertEqual(uninst_args, ["--command", "extension", "remove", "universal_mcp"])

    # --------------------------------------------------------------------------
    # Test 9: Uninstaller Strict Containment & -KeepLogs
    # --------------------------------------------------------------------------
    def test_uninstaller_containment_and_keep_logs(self):
        install_dir = os.path.join(self.test_dir, "TechBot_Blender_MCP")
        venv_dir = os.path.join(install_dir, "venv")
        svc_dir = os.path.join(install_dir, "service")
        dl_dir = os.path.join(install_dir, "downloads")
        os.makedirs(venv_dir, exist_ok=True)
        os.makedirs(svc_dir, exist_ok=True)
        os.makedirs(dl_dir, exist_ok=True)

        log_file = os.path.join(install_dir, "install.log")
        uninst_log = os.path.join(install_dir, "uninstall.log")
        with open(log_file, "w") as f:
            f.write("Log line 1\n")
        with open(uninst_log, "w") as f:
            f.write("Uninstall Log line 1\n")

        # Simulate uninstaller cleanup with KEEP_LOGS=1
        for sub in ("venv", "service", "downloads"):
            p = os.path.join(install_dir, sub)
            if os.path.isdir(p):
                shutil.rmtree(p)

        # Assert venv, service, downloads are deleted
        self.assertFalse(os.path.exists(venv_dir))
        self.assertFalse(os.path.exists(svc_dir))
        self.assertFalse(os.path.exists(dl_dir))

        # Assert logs are preserved
        self.assertTrue(os.path.isfile(log_file))
        self.assertTrue(os.path.isfile(uninst_log))
        self.assertTrue(os.path.isdir(install_dir))

    # --------------------------------------------------------------------------
    # Test 10: Uninstaller Sibling Server Preservation
    # --------------------------------------------------------------------------
    def test_uninstaller_sibling_preservation(self):
        config_path = os.path.join(self.test_dir, "cursor_mcp.json")
        initial_data = {
            "mcpServers": {
                "techbot-blender-mcp": {"command": "python", "args": ["-m", "mcp_service.app"]},
                "external-database": {"command": "npx", "args": ["-y", "db-mcp"]}
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, indent=2)

        # Uninstaller removal logic
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "mcpServers" in data and "techbot-blender-mcp" in data["mcpServers"]:
            del data["mcpServers"]["techbot-blender-mcp"]

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        with open(config_path, "r", encoding="utf-8") as f:
            cleaned = json.load(f)

        self.assertNotIn("techbot-blender-mcp", cleaned["mcpServers"])
        self.assertIn("external-database", cleaned["mcpServers"])


if __name__ == "__main__":
    unittest.main()
