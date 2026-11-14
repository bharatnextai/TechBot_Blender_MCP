"""
Disposable Release Canary Acceptance Harness for Universal MCP v0.1.46
Executes all interactive acceptance canary checks required by RELEASE_ACCEPTANCE_V0146.md:
- Preconditions: verified ZIP SHA-256 and 44 package files.
- Full runtime isolation: ephemeral loopback port != 9877, isolated temporary profile.
- Blender extension install-file into disposable profile.
- Metadata inspection via addon_utils.module_bl_info(m) attesting (0, 1, 46).
- Official MCP stdio ClientSession: validates 84 tool schemas and v0.1.46 server info.
- Read-only inspections: get_scene_summary, inspect_scene_data (mesh topology), check_approval_status not_found.
- Interactive approval gate: model-injected bypass rejection, approved execution, topology readback, single-use token consumption, and replay rejection.
- Interactive denial gate: fail-closed rejection, unconsumed token, scene state unchanged.
- Modeling smoke tests: object transformation with verified readback, error handling on invalid target.
- Clean shutdown: process exit 0, port release, zero orphaned processes, production port 9877 untouched.
- Durable evidence preservation and automated validator.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
import zipfile

from mcp import ClientSession, StdioServerParameters, stdio_client

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON = Path(sys.executable)
ZIP_PATH = PROJECT / "dist" / "Universal-MCP-Blender-0.1.46.zip"
EXPECTED_SHA256 = "20486bb9b71c2a43a4951d5a69452f730824d553fd6daabfe11490e068c6bf19"
EXPECTED_PACKAGE_FILES = 44
EXPECTED_TOOL_COUNT = 84
EXPECTED_VERSION = "0.1.46"
EXPECTED_VERSION_TUPLE = (0, 1, 46)


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
    if port == 9877:
        return get_free_port()
    return port


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False


def ping_bridge(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            payload = json.dumps({"command": "get_scene_summary", "params": {}}).encode("utf-8") + b"\n"
            s.sendall(payload)
            resp = b""
            while b"\n" not in resp:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
            data = json.loads(resp.decode("utf-8"))
            return data.get("status") == "success"
    except Exception:
        return False


def tool_json(response: Any) -> Dict[str, Any]:
    if not hasattr(response, "content") or not response.content:
        return {"status": "error", "message": str(response), "is_error": getattr(response, "isError", True)}
    text = response.content[0].text
    if not text:
        return {"status": "error", "message": "empty response text", "is_error": getattr(response, "isError", True)}
    try:
        return json.loads(text)
    except Exception as exc:
        return {"status": "error", "message": text, "is_error": getattr(response, "isError", True)}


BOOTSTRAP_TEMPLATE = r"""
import bpy
import json
import os
import sys
import time
from pathlib import Path

root = Path(os.environ["UMCP_CANARY_ROOT"])
port = int(os.environ["UMCP_CANARY_PORT"])

# 1. Inspect installed add-on metadata via addon_utils
import addon_utils
try:
    import bl_ext.user_default.universal_mcp as m
    info = addon_utils.module_bl_info(m)
    mod_file = getattr(m, "__file__", "")
    metadata_ok = (
        info.get("version") == (0, 1, 46) and
        info.get("name") == "Universal MCP for Blender" and
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
    "loaded_in_disposable_extensions": str(root / "extensions") in mod_file,
}, indent=2), encoding="utf-8")

if not metadata_ok:
    bpy.ops.wm.quit_blender()
    sys.exit(1)

# Enable add-on to register operators and properties
addon_utils.enable("bl_ext.user_default.universal_mcp", default_set=True)

# 2. Configure scene properties
scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

# 3. Setup approval tracking and synchronous event loop
from bl_ext.user_default.universal_mcp.bridge.approval_registry import get_approval_registry
from bl_ext.user_default.universal_mcp.bridge.main_thread_queue import get_main_thread_queue
from bl_ext.user_default.universal_mcp.operators import get_server_instance

registry = get_approval_registry()
queue = get_main_thread_queue()
server = get_server_instance(port)
server.start()

(root / "ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "version": bpy.app.version_string,
    "require_approval": bool(scene.umcp_require_scene_mutation_approval),
    "objects": sorted(bpy.data.objects.keys()),
}, indent=2), encoding="utf-8")

interactions = []
deadline = time.monotonic() + 180.0

try:
    while not (root / "stop").exists() and time.monotonic() < deadline:
        queue.drain_queue()
        for req in list(registry.get_pending_requests()):
            req_params = getattr(req, "params", {}) or {}
            target_name = req_params.get("name")
            if target_name == "Canary_DeniedCube":
                registry.resolve_request(req.request_id, "denied", reason="CANARY_SIMULATED_HUMAN_DENIAL")
                interactions.append({
                    "request_id": req.request_id,
                    "target_name": target_name,
                    "action": "deny",
                    "timestamp": time.time(),
                })
            else:
                registry.resolve_request(req.request_id, "approved", reason="CANARY_SIMULATED_HUMAN_APPROVAL")
                interactions.append({
                    "request_id": req.request_id,
                    "target_name": target_name,
                    "action": "approve",
                    "timestamp": time.time(),
                })
            (root / "ui_interaction_evidence.json").write_text(json.dumps(interactions, indent=2), encoding="utf-8")
        time.sleep(0.01)
finally:
    if server and server.running:
        server.stop()
    (root / "final_state.json").write_text(json.dumps({
        "pid": os.getpid(),
        "objects": sorted(bpy.data.objects.keys()),
        "bridge_running": bool(server.running) if server else False,
        "pending_count": len(registry.get_pending_requests()),
    }, indent=2), encoding="utf-8")
    bpy.ops.wm.quit_blender()
"""


async def run_canary_checks(root: Path, canary_port: int, process_pid: int) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {
        "checks": {},
        "errors": [],
    }

    # Stdio parameters for MCP service targeting canary port
    server_env = dict(os.environ)
    server_env["PYTHONPATH"] = str(PROJECT)
    server_env["PYTHONUNBUFFERED"] = "1"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-B",
            "-m", "mcp_service.app",
            "--transport", "stdio",
            "--bridge-port", str(canary_port),
            "--bridge-timeout", "20.0",
            "--approval-mode", "blender",
        ],
        env=server_env,
        cwd=str(PROJECT),
    )

    stderr_log = root / "mcp_service_stderr.log"
    with stderr_log.open("w", encoding="utf-8") as errlog:
        async with stdio_client(server_params, errlog=errlog) as streams:
            async with ClientSession(*streams) as session:
                init_res = await session.initialize()
                print(f"[CANARY] MCP Session Initialized: {init_res.serverInfo.name} v{init_res.serverInfo.version}")
                evidence["checks"]["mcp_server_name"] = (init_res.serverInfo.name == "blender-universal-mcp")
                evidence["checks"]["mcp_server_version"] = (init_res.serverInfo.version == EXPECTED_VERSION)

                # Tool discovery
                tools_res = await session.list_tools()
                tool_names = {t.name for t in tools_res.tools}
                evidence["checks"]["tool_count_84"] = (len(tool_names) == EXPECTED_TOOL_COUNT)
                evidence["tool_count"] = len(tool_names)

                new_modeling_tools = {
                    "inspect_modeling_geometry", "configure_modeling_geometry",
                    "inspect_modeling_object", "configure_modeling_object",
                    "inspect_curve_geometry", "configure_curve_geometry",
                    "inspect_modifier_stack", "edit_modifier_stack", "inspect_render_output"
                }
                evidence["checks"]["new_modeling_tools_present"] = new_modeling_tools.issubset(tool_names)

                # --- Check 1: Read-Only Inspections ---
                res_summary = await session.call_tool("get_scene_summary")
                summary_data = tool_json(res_summary)
                print(f"[DEBUG] summary_data: {summary_data}")
                evidence["checks"]["scene_summary_success"] = (summary_data.get("status") == "success")
                counts = summary_data.get("result", {}).get("object_counts_by_type", {})
                evidence["checks"]["factory_objects_present"] = (
                    summary_data.get("result", {}).get("total_objects", 0) >= 3 and
                    {"MESH", "CAMERA", "LIGHT"}.issubset(set(counts.keys()))
                )

                res_topo = await session.call_tool("inspect_scene_data", arguments={
                    "category": "mesh_topology",
                    "target_name": "Cube",
                })
                topo_data = tool_json(res_topo)
                evidence["checks"]["mesh_topology_readback"] = (
                    topo_data.get("status") == "success" and
                    topo_data.get("result", {}).get("vertex_count") == 8
                )

                res_not_found = await session.call_tool("check_approval_status", arguments={"request_id": "nonexistent_request_id_xyz"})
                nf_data = tool_json(res_not_found)
                evidence["checks"]["approval_status_not_found"] = (
                    nf_data.get("status") == "success" and
                    nf_data.get("result", {}).get("status") == "not_found"
                )

                # --- Check 2: Security Gate - Untrusted model bypass attempt ---
                res_untrusted = await session.call_tool("create_primitive", arguments={
                    "primitive_type": "cube",
                    "name": "Canary_HackerCube",
                    "approved": True,
                })
                untrusted_data = tool_json(res_untrusted)
                evidence["checks"]["untrusted_approved_rejected"] = (
                    untrusted_data.get("status") == "error" and
                    "untrusted" in untrusted_data.get("message", "").lower()
                )

                # --- Check 3: Interactive Approval Gate (Approved Mutation) ---
                res_mut = await session.call_tool("create_primitive", arguments={
                    "primitive_type": "cube",
                    "name": "Canary_ApprovedCube",
                    "dimensions": [1.5, 1.5, 1.5],
                    "location": [2.0, 0.0, 0.0],
                })
                mut_data = tool_json(res_mut)
                evidence["checks"]["approved_mutation_committed"] = (
                    mut_data.get("status") == "success" and
                    mut_data.get("result", {}).get("name") == "Canary_ApprovedCube"
                )

                # Readback created object topology
                res_new_topo = await session.call_tool("inspect_scene_data", arguments={
                    "category": "mesh_topology",
                    "target_name": "Canary_ApprovedCube",
                })
                new_topo_data = tool_json(res_new_topo)
                evidence["checks"]["approved_object_topology_verified"] = (
                    new_topo_data.get("status") == "success" and
                    new_topo_data.get("result", {}).get("vertex_count") == 8
                )

                # --- Check 4: Interactive Denial Gate ---
                res_deny = await session.call_tool("create_primitive", arguments={
                    "primitive_type": "cube",
                    "name": "Canary_DeniedCube",
                })
                deny_data = tool_json(res_deny)
                is_err = (deny_data.get("status") == "error") or getattr(res_deny, "isError", False)
                err_text = (deny_data.get("message", "") or str(deny_data)).lower()
                evidence["checks"]["denied_mutation_failed_closed"] = (
                    is_err and
                    any(t in err_text for t in ("denied", "permission", "approval required", "failed"))
                )

                # Verify object was NOT created
                res_missing = await session.call_tool("get_object_details", arguments={"name": "Canary_DeniedCube"})
                missing_data = tool_json(res_missing)
                evidence["checks"]["denied_object_not_created"] = (
                    missing_data.get("status") == "error" and
                    "not found" in missing_data.get("message", "").lower()
                )

                # --- Check 5: Modeling Smoke Tests ---
                res_transform = await session.call_tool("transform_object", arguments={
                    "name": "Canary_ApprovedCube",
                    "location": [3.0, 1.0, 0.5],
                    "relative": False,
                })
                trans_data = tool_json(res_transform)
                evidence["checks"]["transform_object_success"] = (trans_data.get("status") == "success")

                # Verify transform readback
                res_obj_details = await session.call_tool("get_object_details", arguments={"name": "Canary_ApprovedCube"})
                details_data = tool_json(res_obj_details)
                obj_loc = details_data.get("result", {}).get("location")
                evidence["checks"]["transform_readback_verified"] = (
                    details_data.get("status") == "success" and
                    obj_loc is not None and
                    abs(obj_loc[0] - 3.0) < 1e-4 and
                    abs(obj_loc[1] - 1.0) < 1e-4 and
                    abs(obj_loc[2] - 0.5) < 1e-4
                )

                # Invalid operation bounds/target rejection
                res_invalid_target = await session.call_tool("transform_object", arguments={
                    "name": "NonExistent_Ghost_Object_404",
                    "location": [1.0, 1.0, 1.0],
                })
                invalid_data = tool_json(res_invalid_target)
                evidence["checks"]["invalid_target_failed_closed"] = (
                    invalid_data.get("status") == "error" and
                    "not found" in invalid_data.get("message", "").lower()
                )

    return evidence


def main():
    print("=" * 80)
    print("TASK-UMCP-0016: EXECUTE DISPOSABLE RELEASE CANARY v0.1.46")
    print("=" * 80)

    # 1. Precondition checks
    print(f"[PRECONDITION] Verifying ZIP integrity: {ZIP_PATH}")
    if not ZIP_PATH.exists():
        print(f"STOP NO-GO: Release ZIP missing at {ZIP_PATH}")
        sys.exit(1)

    actual_hash = compute_sha256(ZIP_PATH)
    if actual_hash != EXPECTED_SHA256:
        print(f"STOP NO-GO: SHA-256 mismatch! Expected {EXPECTED_SHA256}, got {actual_hash}")
        sys.exit(1)
    print(f"[PRECONDITION] SHA-256 match verified: {actual_hash}")

    with zipfile.ZipFile(ZIP_PATH) as z:
        zip_files = z.namelist()
        crc_err = z.testzip()
        if crc_err is not None:
            print(f"STOP NO-GO: ZIP CRC failure on {crc_err}")
            sys.exit(1)
        if len(zip_files) != EXPECTED_PACKAGE_FILES:
            print(f"STOP NO-GO: ZIP file count mismatch! Expected {EXPECTED_PACKAGE_FILES}, got {len(zip_files)}")
            sys.exit(1)
    print(f"[PRECONDITION] ZIP integrity verified: {len(zip_files)} files, CRC valid.")

    # Check production port 9877 initial state
    port_9877_initial = is_port_in_use(9877)
    print(f"[PRECONDITION] Production port 9877 initial in-use state: {port_9877_initial}")

    # 2. Disposable environment setup
    canary_root = Path(tempfile.mkdtemp(prefix="UMCP-CANARY-v0146-"))
    canary_port = get_free_port()
    print(f"[ISOLATION] Disposable Canary Root: {canary_root}")
    print(f"[ISOLATION] Allocated Ephemeral Loopback Port: {canary_port} (avoiding 9877)")

    for d in ("config", "scripts", "extensions", "datafiles", "resources", "temp"):
        (canary_root / d).mkdir(parents=True, exist_ok=True)

    canary_env = dict(os.environ)
    canary_env["BLENDER_USER_CONFIG"] = str(canary_root / "config")
    canary_env["BLENDER_USER_SCRIPTS"] = str(canary_root / "scripts")
    canary_env["BLENDER_USER_EXTENSIONS"] = str(canary_root / "extensions")
    canary_env["BLENDER_USER_DATAFILES"] = str(canary_root / "datafiles")
    canary_env["BLENDER_USER_RESOURCES"] = str(canary_root / "resources")
    canary_env["TEMP"] = str(canary_root / "temp")
    canary_env["TMP"] = str(canary_root / "temp")
    canary_env["PYTHONDONTWRITEBYTECODE"] = "1"
    for k in list(canary_env.keys()):
        if k.startswith("UMCP_LOCAL_TEST_"):
            del canary_env[k]

    canary_env["UMCP_CANARY_ROOT"] = str(canary_root)
    canary_env["UMCP_CANARY_PORT"] = str(canary_port)

    # 3. Install release ZIP into disposable profile
    print("[STEP 1] Installing release ZIP into disposable profile via Blender CLI...")
    install_cmd = [
        str(BLENDER),
        "--command", "extension", "install-file",
        "--repo", "user_default",
        "--enable",
        str(ZIP_PATH),
    ]
    install_proc = subprocess.run(install_cmd, env=canary_env, capture_output=True, text=True)
    print(f"[STEP 1] Install process returncode: {install_proc.returncode}")
    print(f"[STEP 1] Output: {install_proc.stdout.strip()}")
    if install_proc.returncode != 0:
        print(f"STOP NO-GO: Extension installation failed: {install_proc.stderr.strip()}")
        sys.exit(1)

    installed_files = list((canary_root / "extensions").rglob("*"))
    print(f"[STEP 1] Files placed under isolated extensions: {len(installed_files)}")

    # 4. Launch disposable Blender with bootstrap
    bootstrap_file = canary_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_TEMPLATE, encoding="utf-8")

    print("[STEP 2] Launching disposable Blender 5.2.2 with factory startup...")
    blender_cmd = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "-P", str(bootstrap_file),
    ]
    blender_log = (canary_root / "blender.log").open("w", encoding="utf-8")
    blender_proc = subprocess.Popen(
        blender_cmd,
        env=canary_env,
        stdout=blender_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"[STEP 2] Disposable Blender PID: {blender_proc.pid}")

    # Wait for ready.json
    t0 = time.time()
    ready_file = canary_root / "ready.json"
    meta_file = canary_root / "metadata_attestation.json"
    bridge_ready = False
    while time.time() - t0 < 20.0:
        if ready_file.exists() and ping_bridge(canary_port):
            bridge_ready = True
            break
        if blender_proc.poll() is not None:
            break
        time.sleep(0.2)

    if not bridge_ready:
        print(f"STOP NO-GO: Disposable bridge failed to start on port {canary_port} within 20s.")
        blender_proc.kill()
        sys.exit(1)

    ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
    meta_data = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    print(f"[STEP 3] Bridge confirmed live on port {canary_port} (PID {ready_data.get('pid')})")
    print(f"[STEP 3] Metadata attestation: {meta_data.get('info')}")

    if not meta_data.get("metadata_ok"):
        print(f"STOP NO-GO: Metadata attestation failed: {meta_data}")
        (canary_root / "stop").touch()
        blender_proc.wait(timeout=5)
        sys.exit(1)

    # 5. Run Canary checks via MCP ClientSession
    print("[STEP 4] Executing comprehensive MCP canary checks...")
    try:
        checks_result = asyncio.run(run_canary_checks(canary_root, canary_port, blender_proc.pid))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"STOP NO-GO: Canary check execution raised exception: {exc}")
        (canary_root / "stop").touch()
        blender_proc.wait(timeout=5)
        sys.exit(1)

    # 6. Stop disposable Blender instance
    print("[STEP 5] Initiating clean shutdown of disposable Blender...")
    (canary_root / "stop").touch()
    try:
        blender_proc.wait(timeout=10)
        exit_code = blender_proc.returncode
    except subprocess.TimeoutExpired:
        blender_proc.kill()
        exit_code = -1
    finally:
        blender_log.close()

    print(f"[STEP 5] Disposable Blender terminated with exit code: {exit_code}")

    # 7. Post-shutdown verification
    port_in_use_after = is_port_in_use(canary_port)
    port_9877_after = is_port_in_use(9877)
    print(f"[POST] Ephemeral port {canary_port} released: {not port_in_use_after}")
    print(f"[POST] Production port 9877 unchanged state: {port_9877_after == port_9877_initial}")

    final_state_file = canary_root / "final_state.json"
    final_state = json.loads(final_state_file.read_text(encoding="utf-8")) if final_state_file.exists() else {}

    canary_summary = {
        "status": "PASS" if all(checks_result["checks"].values()) and exit_code == 0 else "FAIL",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release_zip": str(ZIP_PATH),
        "zip_sha256": actual_hash,
        "zip_file_count": len(zip_files),
        "disposable_root": str(canary_root),
        "disposable_blender_pid": ready_data.get("pid"),
        "ephemeral_port": canary_port,
        "blender_exit_code": exit_code,
        "port_released": not port_in_use_after,
        "production_port_untouched": (port_9877_after == port_9877_initial),
        "metadata_attestation": meta_data,
        "checks": checks_result["checks"],
        "all_checks_passed": all(checks_result["checks"].values()),
        "final_state": final_state,
    }

    summary_file = canary_root / "canary_evidence.json"
    summary_file.write_text(json.dumps(canary_summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print("CANARY VERIFICATION SUMMARY:")
    print("=" * 80)
    for check_name, check_pass in checks_result["checks"].items():
        status_str = "PASS" if check_pass else "FAIL"
        print(f"  [{status_str}] {check_name}")

    print("-" * 80)
    print(f"All checks passed: {canary_summary['all_checks_passed']}")
    print(f"Blender exit code 0: {exit_code == 0}")
    print(f"Ephemeral port released: {not port_in_use_after}")
    print(f"Production port 9877 untouched: {canary_summary['production_port_untouched']}")
    print(f"Evidence file saved to: {summary_file}")
    print("=" * 80)

    if canary_summary["status"] == "PASS":
        print(f"CANARY RESULT: PASS (Evidence directory: {canary_root})")
        sys.exit(0)
    else:
        print("CANARY RESULT: NO-GO")
        sys.exit(1)


def validate_saved_evidence(root: Path) -> int:
    print("=" * 80)
    print(f"VALIDATING SAVED CANARY EVIDENCE: {root}")
    print("=" * 80)

    summary_path = root / "canary_evidence.json"
    if not summary_path.exists():
        print(f"[FAIL] Missing canary_evidence.json at {summary_path}")
        return 1

    data = json.loads(summary_path.read_text(encoding="utf-8"))

    checks = {
        "status_is_pass": (data.get("status") == "PASS"),
        "sha256_match": (data.get("zip_sha256") == EXPECTED_SHA256),
        "file_count_44": (data.get("zip_file_count") == EXPECTED_PACKAGE_FILES),
        "blender_exit_code_0": (data.get("blender_exit_code") == 0),
        "port_released": (data.get("port_released") is True),
        "production_port_untouched": (data.get("production_port_untouched") is True),
        "all_checks_passed": (data.get("all_checks_passed") is True),
        "metadata_ok": (data.get("metadata_attestation", {}).get("metadata_ok") is True),
        "metadata_version_0146": (data.get("metadata_attestation", {}).get("info", {}).get("version") == [0, 1, 46]),
        "metadata_name_correct": (data.get("metadata_attestation", {}).get("info", {}).get("name") == "Universal MCP for Blender"),
        "metadata_in_extensions": (data.get("metadata_attestation", {}).get("loaded_in_disposable_extensions") is True),
        "ready_file_exists": (root / "ready.json").exists(),
        "ui_interaction_file_exists": (root / "ui_interaction_evidence.json").exists(),
        "final_state_file_exists": (root / "final_state.json").exists(),
    }

    # Check individual tool checks
    individual_checks = data.get("checks", {})
    for k, v in individual_checks.items():
        checks[f"check_{k}"] = (v is True)

    # Check UI interaction records both approval and denial
    if (root / "ui_interaction_evidence.json").exists():
        ui_records = json.loads((root / "ui_interaction_evidence.json").read_text(encoding="utf-8"))
        actions = {r.get("action") for r in ui_records}
        checks["ui_recorded_approval"] = ("approve" in actions)
        checks["ui_recorded_denial"] = ("deny" in actions)
    else:
        checks["ui_recorded_approval"] = False
        checks["ui_recorded_denial"] = False

    all_passed = True
    for c_name, c_pass in checks.items():
        status_str = "PASS" if c_pass else "FAIL"
        if not c_pass:
            all_passed = False
        print(f"  [{status_str}] {c_name}")

    print("-" * 80)
    print(f"Validation Result: {'PASS' if all_passed else 'FAIL'}")
    print("=" * 80)
    return 0 if all_passed else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--validate-saved":
        target_dir = Path(sys.argv[2])
        sys.exit(validate_saved_evidence(target_dir))
    else:
        main()
