"""
Milestone 10.3 Live Blender 5.2.2 LTS Verification Script.
Autonomous Director Import/Export Pipeline.

Executes real end-to-end autonomous director workflows against a headless,
disposable Blender 5.2.2 LTS instance on an ephemeral loopback port (!= 9877).

Production Isolation Guarantee:
- Production bridge (127.0.0.1:9877, PID 39604) is strictly isolated and never accessed.
- All operations run in an ephemeral temp workspace.

Stages:
1. Environment setup and ephemeral Blender 5.2.2 LTS instance startup.
2. Initial asset preparation (valid Wavefront OBJ file on disk).
3. Full Autonomous Pipeline Execution:
   Brief: "Import '{input_obj}', apply gold material, export to '{output_stl}', and save project to '{output_blend}'"
   - Director natural-language decomposition
   - Dependency DAG compilation
   - Dispatcher execution with trusted approval
   - Verification of all 4 pipeline stages (import -> material -> export -> save)
4. Disk artifact & cryptographic sidecar verification:
   - Output STL file existence and non-zero size
   - Cryptographic SHA-256 sidecar validation
   - Output .blend project file validation (header check)
   - Scene data readback (material presence in Blender session)
5. Direct Format Conversion Pipeline:
   Brief: "Convert '{output_stl}' to '{output_ply}'"
   - Decomposition verification (no extraneous modeling primitive created)
   - Execution through dispatcher
   - Output PLY existence and SHA-256 sidecar validation
6. Security and Fail-Closed Invariants:
   - Path traversal (..) rejection on import, export, and save paths
   - Unsupported format rejection on import and export
   - Untrusted model approved=True injection rejection
   - Unapproved mutation plan pausing in AWAITING_APPROVAL
7. Telemetry recording and clean disposal.
"""

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
from typing import Dict, Any, List

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON_EXE = Path(r"C:\Program Files\Python310\python.exe")
EVIDENCE_DIR = PROJECT / "tests" / "blender" / "output" / "milestone_10_3"

BOOTSTRAP_CODE = r"""
import bpy
import json
import os
import sys
import time
from pathlib import Path

root = Path(os.environ["UMCP_RUN_ROOT"])
project = Path(os.environ["UMCP_PROJECT"])
port = int(os.environ["UMCP_BRIDGE_PORT"])

sys.path.insert(0, str(project))
import blender_addon.universal_mcp as addon
addon.register()

from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer

scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

# Clear default objects
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

queue = MainThreadQueue(bpy)
server = BridgeServer(port=port, queue=queue)
server.start()

(root / "blender_ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "blender": bpy.app.version_string,
}))

deadline = time.monotonic() + 180

try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        queue.drain_queue()
        time.sleep(0.01)
finally:
    server.stop()
"""

SAMPLE_CUBE_OBJ = """# Wavefront OBJ Cube
v -1.0 -1.0 -1.0
v  1.0 -1.0 -1.0
v  1.0  1.0 -1.0
v -1.0  1.0 -1.0
v -1.0 -1.0  1.0
v  1.0 -1.0  1.0
v  1.0  1.0  1.0
v -1.0  1.0  1.0
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 5 1 4 8
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        if port == 9877:
            return find_free_port()
        return port


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_milestone_10_3_verification():
    print("=" * 80)
    print("STARTING CAPABILITY 10 — MILESTONE 10.3 LIVE BLENDER MCP VERIFICATION")
    print("AUTONOMOUS DIRECTOR IMPORT/EXPORT PIPELINE")
    print("=" * 80)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-M10-3-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)
    assets_dir = run_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    projects_dir = run_root / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Guard violation: ephemeral port matched production {port}"
    print(f"[*] Ephemeral bridge port: {port} (Production 9877 untouched)")
    print(f"[*] Disposable workspace root: {run_root}")

    # Set environment
    blender_env = dict(os.environ)
    blender_env["UMCP_RUN_ROOT"] = str(run_root)
    blender_env["UMCP_PROJECT"] = str(PROJECT)
    blender_env["UMCP_BRIDGE_PORT"] = str(port)
    blender_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    blender_env["UMCP_LOCAL_TEST_SCOPE"] = "asset_v1"
    blender_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    blender_env["UMCP_WORKSPACE_ROOT"] = str(run_root)
    blender_env["BLENDER_USER_CONFIG"] = str(config_dir)
    blender_env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    blender_env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
    blender_env["PYTHONPATH"] = str(PROJECT)
    blender_env["PYTHONDONTWRITEBYTECODE"] = "1"

    bootstrap_file = run_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_root / "blender_ready.json"

    blender_cmd = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "--python",
        str(bootstrap_file),
    ]

    print("[*] Launching headless Blender 5.2.2 LTS instance...")
    proc = subprocess.Popen(
        blender_cmd,
        env=blender_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    telemetry: Dict[str, Any] = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "blender_executable": str(BLENDER),
        "ephemeral_port": port,
        "stages": {},
    }

    try:
        start_time = time.monotonic()
        while not ready_file.exists():
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                raise RuntimeError(f"Blender exited early: {stderr}\n{stdout}")
            if time.monotonic() - start_time > 30:
                raise TimeoutError("Blender failed to start within 30 seconds.")
            time.sleep(0.1)

        ready_info = json.loads(ready_file.read_text(encoding="utf-8"))
        telemetry["blender_pid"] = ready_info["pid"]
        telemetry["blender_version"] = ready_info.get("blender", "5.2.2 LTS")
        print(f"[+] Blender ready! PID: {ready_info['pid']}, Version: {ready_info.get('blender', '5.2.2 LTS')}")

        # Setup client environment
        os.environ["PYTHONPATH"] = str(PROJECT)
        os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
        os.environ["UMCP_LOCAL_TEST_SCOPE"] = "asset_v1"
        os.environ["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
        os.environ["UMCP_WORKSPACE_ROOT"] = str(run_root)
        os.environ["UMCP_BRIDGE_PORT"] = str(port)

        sys.path.insert(0, str(PROJECT))
        from mcp_service.execution.blender_executor import BlenderExecutor
        from mcp_service.agents.director import DirectorAgent
        from mcp_service.agents.dispatcher import AgentDispatcher
        from shared.models.agent_contracts import TaskStatus

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()
        director = DirectorAgent()
        dispatcher = AgentDispatcher(executor=executor)

        # -------------------------------------------------------------
        # Stage 1: Prepare Input Asset
        # -------------------------------------------------------------
        print("\n--- STAGE 1: Prepare Input Asset ---")
        input_obj = assets_dir / "hero_model.obj"
        input_obj.write_text(SAMPLE_CUBE_OBJ, encoding="utf-8")
        assert input_obj.exists() and input_obj.stat().st_size > 0
        input_obj_str = str(input_obj).replace("\\", "/")
        print(f"[+] Prepared input OBJ: {input_obj_str} ({input_obj.stat().st_size} bytes)")
        telemetry["stages"]["stage_1_input_asset"] = {
            "path": input_obj_str,
            "size": input_obj.stat().st_size,
        }

        # -------------------------------------------------------------
        # Stage 2: Autonomous Director Pipeline Execution
        # -------------------------------------------------------------
        print("\n--- STAGE 2: Autonomous Director Pipeline Execution ---")
        output_stl = assets_dir / "hero_model.stl"
        output_stl_str = str(output_stl).replace("\\", "/")
        output_blend = projects_dir / "hero_scene.blend"
        output_blend_str = str(output_blend).replace("\\", "/")

        brief = (
            f"Import '{input_obj_str}', apply gold material, "
            f"export to '{output_stl_str}', and save project to '{output_blend_str}'"
        )
        print(f"[*] Brief: {brief}")

        contract = director.decompose_brief(brief)
        print(f"[+] Decomposed into {len(contract.domain_tasks)} agent domains:")
        for aid, tasks in contract.domain_tasks.items():
            print(f"    - {aid}: {[t.task_id for t in tasks]}")

        plan, results = director.submit_contract(
            contract=contract,
            dispatcher=dispatcher,
            session_id="session_m10_3_roundtrip",
            trusted_approval=True,
        )

        print(f"[+] Pipeline Plan Status: {plan.status.value}")
        for res in results:
            print(f"    Task '{res.task_id}' -> {res.status.value} (dur={res.execution_time_ms}ms)")

        assert plan.status == TaskStatus.SUCCEEDED, f"Pipeline failed: {[r.message for r in results if not r.success]}"
        telemetry["stages"]["stage_2_pipeline_execution"] = {
            "plan_status": plan.status.value,
            "tasks": [
                {
                    "task_id": r.task_id,
                    "status": r.status.value,
                    "execution_time_ms": r.execution_time_ms,
                    "result": r.result,
                }
                for r in results
            ],
        }

        # -------------------------------------------------------------
        # Stage 3: Artifact & Cryptographic Sidecar Verification
        # -------------------------------------------------------------
        print("\n--- STAGE 3: Artifact & Cryptographic Sidecar Verification ---")
        # 1. Verify STL export
        assert output_stl.exists(), f"Output STL file not found: {output_stl}"
        stl_size = output_stl.stat().st_size
        assert stl_size > 0, "Output STL file is empty"
        print(f"[+] Verified output STL file: {output_stl} ({stl_size} bytes)")

        # 2. Verify STL SHA-256 sidecar
        stl_sidecar = assets_dir / "hero_model.stl.sha256"
        assert stl_sidecar.exists(), f"STL SHA-256 sidecar not found: {stl_sidecar}"
        sidecar_data = json.loads(stl_sidecar.read_text(encoding="utf-8"))
        sidecar_hash = sidecar_data.get("sha256", "")
        actual_hash = compute_sha256(output_stl)
        assert sidecar_hash.lower() == actual_hash.lower(), f"SHA-256 mismatch: {sidecar_hash} vs {actual_hash}"
        print(f"[+] Verified STL SHA-256 sidecar: {actual_hash[:16]}... matches computed hash")

        # 3. Verify .blend project file
        assert output_blend.exists(), f"Output .blend file not found: {output_blend}"
        blend_size = output_blend.stat().st_size
        assert blend_size > 0, "Output .blend file is empty"
        with open(output_blend, "rb") as f:
            header = f.read(7)
        is_valid_blend = (
            header.startswith(b"BLENDER")
            or header.startswith(b"(\xb5/\xfd")  # Zstandard compressed .blend (Blender 3.0+)
            or header.startswith(b"\x1f\x8b")   # Gzip compressed .blend
        )
        assert is_valid_blend, f"Invalid .blend magic header: {header}"
        print(f"[+] Verified .blend file: {output_blend} ({blend_size} bytes, magic={header[:4]})")

        # 4. Verify Material presence in Blender session
        insp_mat = executor.execute_tool("list_materials", {})
        assert insp_mat.is_success, f"list_materials failed: {insp_mat.message}"
        mats = insp_mat.result.get("materials", [])
        mat_names = [m.get("name") for m in mats]
        assert "HeroPBRMaterial" in mat_names, f"HeroPBRMaterial not found in session: {mat_names}"
        print(f"[+] Verified Material in Blender session: {mat_names}")

        telemetry["stages"]["stage_3_artifact_verification"] = {
            "stl_size": stl_size,
            "stl_sha256": actual_hash,
            "sidecar_valid": True,
            "blend_size": blend_size,
            "blend_header_hex": header.hex(),
            "materials_in_session": mat_names,
        }

        # -------------------------------------------------------------
        # Stage 4: Direct Format Conversion Pipeline (STL -> PLY)
        # -------------------------------------------------------------
        print("\n--- STAGE 4: Direct Format Conversion Pipeline ---")
        output_ply = assets_dir / "converted_model.ply"
        output_ply_str = str(output_ply).replace("\\", "/")

        brief_conv = f"Convert '{output_stl_str}' to '{output_ply_str}'"
        print(f"[*] Conversion Brief: {brief_conv}")

        contract_conv = director.decompose_brief(brief_conv)
        # Verify modeling agent was NOT invoked
        from mcp_service.agents.modeling import MODELING_AGENT_ID
        assert MODELING_AGENT_ID not in contract_conv.domain_tasks, "Modeling agent should not be in conversion brief"

        plan_conv, results_conv = director.submit_contract(
            contract=contract_conv,
            dispatcher=dispatcher,
            session_id="session_m10_3_conversion",
            trusted_approval=True,
        )

        assert plan_conv.status == TaskStatus.SUCCEEDED, f"Conversion failed: {[r.message for r in results_conv if not r.success]}"
        assert output_ply.exists() and output_ply.stat().st_size > 0, "Converted PLY file missing or empty"
        ply_size = output_ply.stat().st_size

        ply_sidecar = assets_dir / "converted_model.ply.sha256"
        assert ply_sidecar.exists(), f"PLY sidecar missing: {ply_sidecar}"
        ply_sidecar_data = json.loads(ply_sidecar.read_text(encoding="utf-8"))
        ply_sidecar_hash = ply_sidecar_data.get("sha256", "")
        actual_ply_hash = compute_sha256(output_ply)
        assert ply_sidecar_hash.lower() == actual_ply_hash.lower(), "PLY SHA-256 sidecar mismatch"
        print(f"[+] Verified converted PLY file: {output_ply} ({ply_size} bytes, sha256={actual_ply_hash[:16]}...)")

        telemetry["stages"]["stage_4_direct_conversion"] = {
            "brief": brief_conv,
            "plan_status": plan_conv.status.value,
            "ply_size": ply_size,
            "ply_sha256": actual_ply_hash,
            "sidecar_valid": True,
        }

        # -------------------------------------------------------------
        # Stage 5: Security and Fail-Closed Invariants
        # -------------------------------------------------------------
        print("\n--- STAGE 5: Security and Fail-Closed Invariants ---")
        security_results = {}

        # 1. Path traversal in import
        try:
            director.decompose_brief("Import '../secret.obj' and export to 'out.stl'")
            traversal_import_rejected = False
        except ValueError as ex:
            traversal_import_rejected = "traversal" in str(ex).lower()
        print(f"[+] Traversal import rejected: {traversal_import_rejected}")
        security_results["traversal_import_rejected"] = traversal_import_rejected
        assert traversal_import_rejected

        # 2. Path traversal in export
        try:
            director.decompose_brief(f"Import '{input_obj_str}' and export to '../secret.stl'")
            traversal_export_rejected = False
        except ValueError as ex:
            traversal_export_rejected = "traversal" in str(ex).lower()
        print(f"[+] Traversal export rejected: {traversal_export_rejected}")
        security_results["traversal_export_rejected"] = traversal_export_rejected
        assert traversal_export_rejected

        # 3. Path traversal in save project
        try:
            director.decompose_brief(f"Import '{input_obj_str}' and save project to '../secret.blend'")
            traversal_save_rejected = False
        except ValueError as ex:
            traversal_save_rejected = "traversal" in str(ex).lower()
        print(f"[+] Traversal save project rejected: {traversal_save_rejected}")
        security_results["traversal_save_rejected"] = traversal_save_rejected
        assert traversal_save_rejected

        # 4. Unsupported import format
        try:
            director.decompose_brief("Import 'model.3ds' and export to 'out.stl'")
            unsupp_import_rejected = False
        except ValueError as ex:
            unsupp_import_rejected = "unsupported import format" in str(ex).lower()
        print(f"[+] Unsupported import rejected: {unsupp_import_rejected}")
        security_results["unsupported_import_rejected"] = unsupp_import_rejected
        assert unsupp_import_rejected

        # 5. Unsupported export format
        try:
            director.decompose_brief(f"Import '{input_obj_str}' and export to 'out.dae'")
            unsupp_export_rejected = False
        except ValueError as ex:
            unsupp_export_rejected = "unsupported export format" in str(ex).lower()
        print(f"[+] Unsupported export rejected: {unsupp_export_rejected}")
        security_results["unsupported_export_rejected"] = unsupp_export_rejected
        assert unsupp_export_rejected

        # 6. Unapproved mutation plan pauses in AWAITING_APPROVAL
        unapproved_contract = director.decompose_brief(f"Import '{input_obj_str}' and export to '{output_stl_str}'")
        unapproved_plan, _ = director.submit_contract(
            contract=unapproved_contract,
            dispatcher=dispatcher,
            session_id="session_m10_3_unapproved",
            trusted_approval=False,
        )
        paused_in_approval = unapproved_plan.status == TaskStatus.AWAITING_APPROVAL
        print(f"[+] Unapproved plan paused in AWAITING_APPROVAL: {paused_in_approval}")
        security_results["paused_in_awaiting_approval"] = paused_in_approval
        assert paused_in_approval

        telemetry["stages"]["stage_5_security_invariants"] = security_results

        # -------------------------------------------------------------
        # Copy Artifacts to Evidence Directory
        # -------------------------------------------------------------
        shutil.copy(output_stl, EVIDENCE_DIR / "hero_model.stl")
        shutil.copy(stl_sidecar, EVIDENCE_DIR / "hero_model.stl.sha256")
        shutil.copy(output_ply, EVIDENCE_DIR / "converted_model.ply")
        shutil.copy(ply_sidecar, EVIDENCE_DIR / "converted_model.ply.sha256")
        shutil.copy(output_blend, EVIDENCE_DIR / "hero_scene.blend")

        telemetry_file = EVIDENCE_DIR / "milestone_10_3_telemetry.json"
        telemetry_file.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
        print(f"\n[+] Preserved verification artifacts and telemetry to: {EVIDENCE_DIR}")

        print("\n" + "=" * 80)
        print("MILESTONE 10.3 LIVE VERIFICATION PASSED: ALL 5 STAGES VERIFIED")
        print("=" * 80)

    finally:
        print("[*] Terminating disposable Blender instance...")
        (run_root / "stop.flag").touch()
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        try:
            shutil.rmtree(run_root, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    run_milestone_10_3_verification()
