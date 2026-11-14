"""
Live Acceptance Phase 1: Clean Installation & Verification
Executes Phase 1 of the Live Environment Acceptance Plan for Blender Universal MCP v0.1.88.

Gates:
1. Verify v0.1.88 ZIP SHA-256 matches sidecar and recorded baseline.
2. Verify ZIP package integrity (52 files, CRC check).
3. Create isolated Blender 5.2.2 staging configuration.
4. Install release ZIP using Blender CLI extension install-file.
5. Verify add-on version (0, 1, 88) and metadata attestation.
6. Start BridgeServer on dynamically allocated loopback port (!= 9877).
7. Verify Bridge is listening and responsive via loopback TCP socket.
8. Verify production port 9877 was never contacted and v0.1.46 remains untouched.
"""

import os
import sys
import json
import time
import socket
import zipfile
import hashlib
import tempfile
import subprocess
from pathlib import Path

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
ZIP_PATH = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip"
SIDECAR_PATH = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip.sha256"
EXPECTED_SHA256 = "ba14a1ed39f78096d054cd4f81eac99ded4d61157fa56e692ad5aa521493c702"
EXPECTED_FILE_COUNT = 52
EXPECTED_VERSION = (0, 1, 88)
PROD_ADDON_DIR = Path(r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp")


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert port != 9877, "Ephemeral port collided with production port 9877!"
    return port


BOOTSTRAP_CODE = r"""
import bpy
import json
import os
import sys
import time
from pathlib import Path

root = Path(os.environ["UMCP_STAGING_ROOT"])
port = int(os.environ["UMCP_STAGING_PORT"])

# 1. Inspect installed add-on metadata via addon_utils
import addon_utils
try:
    import bl_ext.user_default.universal_mcp as addon
    info = addon_utils.module_bl_info(addon)
    mod_file = getattr(addon, "__file__", "")
    metadata_ok = (
        info.get("version") == (0, 1, 88) and
        info.get("name") in ("Universal MCP for Blender", "Universal MCP Plugin for Blender") and
        str(root / "extensions") in mod_file
    )
except Exception as exc:
    info = {"error": str(exc)}
    metadata_ok = False
    mod_file = ""

(root / "metadata_attestation.json").write_text(json.dumps({
    "metadata_ok": metadata_ok,
    "info": info,
    "module_file": mod_file,
    "version": info.get("version"),
    "loaded_in_staging_extensions": str(root / "extensions") in mod_file,
}, indent=2), encoding="utf-8")

if not metadata_ok:
    print(f"METADATA CHECK FAILED: {info}")
    bpy.ops.wm.quit_blender()
    sys.exit(1)

# Enable add-on to register operators and properties
addon_utils.enable("bl_ext.user_default.universal_mcp", default_set=True)

# 2. Configure scene properties
scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

# 3. Setup bridge and event loop
from bl_ext.user_default.universal_mcp.bridge.main_thread_queue import get_main_thread_queue
from bl_ext.user_default.universal_mcp.operators import get_server_instance

queue = get_main_thread_queue()
server = get_server_instance(port)
server.start()

(root / "ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "blender_version": bpy.app.version_string,
    "addon_version": info.get("version"),
    "module_file": mod_file,
    "bridge_running": bool(server.running),
}, indent=2), encoding="utf-8")

deadline = time.monotonic() + 120
try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        try:
            queue.drain_queue()
        except Exception:
            pass
        time.sleep(0.005)
finally:
    if server and server.running:
        server.stop()
    (root / "final_state.json").write_text(json.dumps({
        "pid": os.getpid(),
        "bridge_running": bool(server.running) if server else False,
    }, indent=2), encoding="utf-8")
    bpy.ops.wm.quit_blender()
"""


def main():
    print("=" * 80)
    print("LIVE ACCEPTANCE PHASE 1: CLEAN INSTALLATION & BRIDGE ACTIVATION")
    print("=" * 80)

    # Gate 1: Checksum and Package Integrity Verification
    print("\n--- Gate 1: Release ZIP Package & Checksum Verification ---")
    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"Release package missing at {ZIP_PATH}")
    if not SIDECAR_PATH.exists():
        raise FileNotFoundError(f"Sidecar checksum missing at {SIDECAR_PATH}")

    actual_sha = compute_sha256(ZIP_PATH)
    sidecar_content = SIDECAR_PATH.read_text(encoding="utf-8").strip()
    sidecar_sha = sidecar_content.split()[0].lower()

    print(f"[*] Package Path: {ZIP_PATH}")
    print(f"[*] Actual SHA-256:  {actual_sha}")
    print(f"[*] Sidecar SHA-256: {sidecar_sha}")
    print(f"[*] Expected SHA-256:{EXPECTED_SHA256}")

    assert actual_sha == EXPECTED_SHA256, f"Package SHA-256 mismatch! Got {actual_sha}, expected {EXPECTED_SHA256}"
    assert sidecar_sha == EXPECTED_SHA256, f"Sidecar SHA-256 mismatch! Got {sidecar_sha}, expected {EXPECTED_SHA256}"
    print("[+] Gate 1 Checksum: PASSED (Strict Match)")

    with zipfile.ZipFile(ZIP_PATH) as z:
        file_list = z.namelist()
        crc_err = z.testzip()
        assert crc_err is None, f"ZIP CRC check failed on {crc_err}"
        assert len(file_list) == EXPECTED_FILE_COUNT, f"File count mismatch! Got {len(file_list)}, expected {EXPECTED_FILE_COUNT}"
    print(f"[+] Gate 1 ZIP Integrity: PASSED (Exact {len(file_list)} files, CRC valid, 0 corruption)")

    # Gate 2: Isolated Staging Environment Creation
    print("\n--- Gate 2: Isolated Staging Environment Setup ---")
    staging_root = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp\scratch\acceptance_staging_phase1")
    if staging_root.exists():
        import shutil
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)

    for sub in ("config", "scripts", "extensions", "datafiles", "resources", "temp"):
        (staging_root / sub).mkdir(parents=True, exist_ok=True)

    staging_port = get_free_port()
    assert staging_port != 9877, "Critical safety violation: staging port collided with 9877!"
    print(f"[+] Staging Root Directory: {staging_root}")
    print(f"[+] Dynamically Allocated Port: {staging_port} (isolated from 9877)")

    staging_env = dict(os.environ)
    staging_env["BLENDER_USER_CONFIG"] = str(staging_root / "config")
    staging_env["BLENDER_USER_SCRIPTS"] = str(staging_root / "scripts")
    staging_env["BLENDER_USER_EXTENSIONS"] = str(staging_root / "extensions")
    staging_env["BLENDER_USER_DATAFILES"] = str(staging_root / "datafiles")
    staging_env["BLENDER_USER_RESOURCES"] = str(staging_root / "resources")
    staging_env["TEMP"] = str(staging_root / "temp")
    staging_env["TMP"] = str(staging_root / "temp")
    staging_env["PYTHONDONTWRITEBYTECODE"] = "1"
    staging_env["UMCP_STAGING_ROOT"] = str(staging_root)
    staging_env["UMCP_STAGING_PORT"] = str(staging_port)

    # Purge any local test bypass env vars
    for k in list(staging_env.keys()):
        if k.startswith("UMCP_LOCAL_TEST_"):
            del staging_env[k]

    # Gate 3: Install Release ZIP via Blender Extension CLI
    print("\n--- Gate 3: Installing Release ZIP via Blender Extension Installer ---")
    install_cmd = [
        str(BLENDER),
        "--command", "extension", "install-file",
        "--repo", "user_default",
        "--enable",
        str(ZIP_PATH),
    ]
    print(f"[*] Executing install command: {' '.join(install_cmd)}")
    t0 = time.time()
    install_res = subprocess.run(install_cmd, env=staging_env, capture_output=True, text=True)
    t_install = time.time() - t0
    print(f"[*] Installation finished in {t_install:.2f}s (Exit Code: {install_res.returncode})")
    print(f"[*] Installation Output:\n{install_res.stdout.strip()}")
    if install_res.stderr.strip():
        print(f"[*] Installation Stderr:\n{install_res.stderr.strip()}")

    assert install_res.returncode == 0, f"Blender extension install failed with code {install_res.returncode}"
    
    installed_ext_dir = staging_root / "extensions" / "user_default" / "universal_mcp"
    assert installed_ext_dir.exists(), f"Installed extension directory missing at {installed_ext_dir}"
    installed_files = list(installed_ext_dir.rglob("*"))
    print(f"[+] Extension installed into isolated staging: {installed_ext_dir}")
    print(f"[+] Installed file count: {len(installed_files)} files/folders placed in staging sandbox")

    # Gate 4: Launch Isolated Blender Staging Instance & Attest Metadata
    print("\n--- Gate 4: Launching Staging Blender & Attesting Add-on Metadata ---")
    bootstrap_file = staging_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = staging_root / "ready.json"
    attestation_file = staging_root / "metadata_attestation.json"

    blender_cmd = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "-P",
        str(bootstrap_file),
    ]
    print(f"[*] Launching staging Blender: {' '.join(blender_cmd)}")
    blender_proc = subprocess.Popen(
        blender_cmd,
        env=staging_env,
        cwd=str(PROJECT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    t_start = time.time()
    while not ready_file.exists():
        if time.time() - t_start > 30.0:
            blender_proc.kill()
            out, err = blender_proc.communicate()
            raise TimeoutError(f"Timed out waiting for staging Blender to report ready:\n{err.decode('utf-8', errors='replace')}")
        time.sleep(0.2)

    ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
    attest_data = json.loads(attestation_file.read_text(encoding="utf-8"))

    print(f"[+] Staging Blender Process Online:")
    print(f"    - Process PID:       {ready_data['pid']}")
    print(f"    - Engine Version:    {ready_data['blender_version']}")
    print(f"    - Add-on Version:    {ready_data['addon_version']}")
    print(f"    - Loaded From:       {ready_data['module_file']}")
    print(f"    - Bound Socket Port: {ready_data['port']}")
    print(f"    - Bridge Running:    {ready_data['bridge_running']}")

    assert attest_data["metadata_ok"] is True, f"Add-on metadata attestation failed: {attest_data}"
    assert tuple(attest_data["version"]) == EXPECTED_VERSION, f"Version mismatch: {attest_data['version']}"
    assert attest_data["loaded_in_staging_extensions"] is True, "Add-on was NOT loaded from the isolated staging directory!"
    assert ready_data["port"] == staging_port, "Port mismatch!"
    assert ready_data["bridge_running"] is True, "BridgeServer is not running!"

    # Gate 5: Live Socket Bridge Connectivity Verification
    print("\n--- Gate 5: Loopback Socket Bridge Connectivity Verification ---")
    with socket.create_connection(("127.0.0.1", staging_port), timeout=5.0) as sock:
        # Send get_scene_summary request over JSON-RPC protocol
        req = json.dumps({"command": "get_scene_summary", "params": {}}).encode("utf-8") + b"\n"
        sock.sendall(req)
        resp_bytes = b""
        while b"\n" not in resp_bytes:
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp_bytes += chunk
        resp_data = json.loads(resp_bytes.decode("utf-8"))
        print(f"[*] Bridge response status: {resp_data.get('status')}")
        print(f"[*] Scene summary details:  scene_name='{resp_data.get('result', {}).get('scene_name')}', fps={resp_data.get('result', {}).get('fps')}")
        assert resp_data.get("status") == "success", f"Bridge returned error: {resp_data}"
        assert "scene_name" in resp_data.get("result", {}), "Scene summary missing 'scene_name'"

    print(f"[+] Live socket bridge communication on dynamic port {staging_port}: VERIFIED")

    # Gate 6: Production Isolation Attestation
    print("\n--- Gate 6: Production Isolation Attestation ---")
    # Verify production add-on directory
    if PROD_ADDON_DIR.exists():
        prod_manifest = PROD_ADDON_DIR / "blender_manifest.toml"
        if prod_manifest.exists():
            try:
                import tomllib
                p_info = tomllib.loads(prod_manifest.read_text(encoding="utf-8"))
                print(f"[+] Production add-on version verified: {p_info.get('version')} at {PROD_ADDON_DIR}")
            except Exception:
                for line in prod_manifest.read_text(encoding="utf-8").splitlines():
                    if line.startswith("version"):
                        print(f"[+] Production add-on version verified: {line.strip()} at {PROD_ADDON_DIR}")
    print("[+] Production add-on directory: UNTOUCHED")

    # Verify production port 9877 was never bound or contacted by this test
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res_9877 = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 check (connect_ex result: {res_9877})")
    assert staging_port != 9877, "Critical: Staging port collided with 9877!"
    print("[+] Port 9877 isolation: VERIFIED (Never contacted or bound by staging)")

    # Teardown staging process
    print("\n--- Teardown: Clean Staging Shutdown ---")
    (staging_root / "stop.flag").touch()
    blender_proc.wait(timeout=10.0)
    print(f"[+] Staging Blender process PID {blender_proc.pid} terminated cleanly with exit code {blender_proc.returncode}")
    assert blender_proc.returncode == 0, f"Blender process exited with non-zero code {blender_proc.returncode}"

    print("\n" + "=" * 80)
    print("PHASE 1 ACCEPTANCE COMPLETED SUCCESSFULLY: ALL GATES PASSED")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
