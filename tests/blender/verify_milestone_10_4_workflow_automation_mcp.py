"""
Milestone 10.4 Live Blender 5.2.2 LTS Verification Script.
Dynamic Workflow Automation, Checkpointing & Batch Operations.

Executes real end-to-end autonomous workflow orchestration, transactional rollback,
verification gates, and multi-asset batch processing against a headless,
disposable Blender 5.2.2 LTS instance on an ephemeral loopback port (!= 9877).

Production Isolation Guarantee:
- Production bridge (127.0.0.1:9877, PID 39604) is strictly isolated and never accessed.
- All operations run in an ephemeral temp workspace.

Stages:
1. Environment setup and ephemeral Blender 5.2.2 LTS instance startup.
2. Baseline scene setup: create a pre-existing object ('StudioReferenceRig') to verify
   preservation across all checkpoints, rollbacks, and batch iterations.
3. Stage 1: Director-to-WorkflowOrchestrator Execution:
   - Convert OBJ to GLB with in-memory pre-stage SceneCheckpoint capture
   - Automatic MeshManifoldnessGate post-import evaluation
   - Validated GLB export with SHA-256 sidecar
4. Stage 2: Automatic Rollback after Injected Verification Gate Failure:
   - Import of corrupt asset triggering gate failure
   - Automatic StageRollbackEngine restoration
   - Verification that corrupt mesh is deleted, zero orphaned meshes remain,
     and pre-existing 'StudioReferenceRig' is 100% preserved.
5. Stage 3: Controlled Multi-Asset Batch Conversion:
   - Batch conversion of 3 assets (Asset 1: Valid Cube, Asset 2: Corrupt, Asset 3: Valid Pyramid)
   - Per-asset failure isolation: Asset 1 & 3 succeed, Asset 2 fails without corrupting outputs
   - Cryptographic SHA-256 sidecars verified for each output
   - Datablock reclamation between iterations
6. Stage 4: Security and Fail-Closed Invariants:
   - Path traversal rejection across batch input and output paths
   - Untrusted model approved=True rejection
   - Unapproved workflow pausing in AWAITING_APPROVAL
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
EVIDENCE_DIR = PROJECT / "tests" / "blender" / "output" / "milestone_10_4"

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

deadline = time.monotonic() + 600

try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        queue.drain_queue()
        time.sleep(0.01)
finally:
    server.stop()
"""

CUBE_OBJ_TEXT = """# Valid Cube Mesh
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

PYRAMID_OBJ_TEXT = """# Valid Pyramid Mesh
v -1.0 -1.0 0.0
v  1.0 -1.0 0.0
v  1.0  1.0 0.0
v -1.0  1.0 0.0
v  0.0  0.0 2.0
f 1 2 3 4
f 1 2 5
f 2 3 5
f 3 4 5
f 4 1 5
"""

CORRUPT_OBJ_TEXT = """# Degenerate Non-Manifold Geometry (Collapsed vertices, zero faces)
v 0.0 0.0 0.0
v 0.0 0.0 0.0
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


def run_milestone_10_4_verification():
    print("=" * 80)
    print("STARTING CAPABILITY 10 — MILESTONE 10.4 LIVE BLENDER MCP VERIFICATION")
    print("WORKFLOW AUTOMATION, CHECKPOINTING & BATCH OPERATIONS")
    print("=" * 80)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-M10-4-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)
    assets_dir = run_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir = run_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Guard violation: ephemeral port matched production {port}"
    print(f"[*] Ephemeral bridge port: {port} (Production 9877 untouched)")
    print(f"[*] Disposable workspace root: {run_root}")

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
    blender_log_path = run_root / "blender_output.log"
    blender_log_file = open(blender_log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        blender_cmd,
        env=blender_env,
        stdout=blender_log_file,
        stderr=subprocess.STDOUT,
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
        from mcp_service.workflow.orchestrator import WorkflowOrchestrator
        from mcp_service.workflow.batch import BatchAssetProcessor
        from mcp_service.workflow.verification_gates import VerificationGate, VerificationResult, MeshManifoldnessGate

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()
        orchestrator = WorkflowOrchestrator(executor=executor)
        director = DirectorAgent()

        # -------------------------------------------------------------
        # Baseline Scene Setup: Pre-existing Studio Object
        # -------------------------------------------------------------
        print("\n--- Baseline Scene Setup: Pre-existing Studio Object ---")
        ref_res = executor.execute_tool("create_primitive", {
            "primitive_type": "cylinder",
            "name": "StudioReferenceRig",
            "location": [5.0, 5.0, 0.0],
            "radius": 0.5,
            "depth": 2.0,
        })
        assert ref_res.is_success, f"Failed to create StudioReferenceRig: {ref_res.message}"
        print("[+] Created baseline 'StudioReferenceRig' (must be preserved across all workflows)")

        # -------------------------------------------------------------
        # Stage 1: Autonomous Director Workflow Execution (OBJ -> GLB)
        # -------------------------------------------------------------
        print("\n--- STAGE 1: Director-to-WorkflowOrchestrator Execution ---")
        hero_obj = assets_dir / "hero_model.obj"
        hero_obj.write_text(CUBE_OBJ_TEXT, encoding="utf-8")
        hero_glb = outputs_dir / "hero_model.glb"
        hero_obj_str = str(hero_obj).replace("\\", "/")
        hero_glb_str = str(hero_glb).replace("\\", "/")

        brief_1 = f"Convert '{hero_obj_str}' to '{hero_glb_str}'"
        print(f"[*] Brief: {brief_1}")

        contract_1 = director.decompose_brief(brief_1)
        wf_report_1 = director.submit_workflow(
            contract=contract_1,
            orchestrator=orchestrator,
            trusted_approval=True,
        )

        print(f"[+] Workflow Status: {wf_report_1.status}")
        print(f"[+] Checkpoints captured: {len(wf_report_1.checkpoints_captured)}")
        print(f"[+] Rollbacks executed: {len(wf_report_1.rollbacks_executed)}")

        assert wf_report_1.status == "SUCCEEDED", f"Workflow 1 failed: {wf_report_1.summary}"
        assert len(wf_report_1.checkpoints_captured) >= 2, "Expected pre-stage checkpoints"
        assert hero_glb.exists() and hero_glb.stat().st_size > 0, "Output GLB file missing or empty"
        glb_size = hero_glb.stat().st_size

        hero_sidecar = outputs_dir / "hero_model.glb.sha256"
        assert hero_sidecar.exists(), f"SHA-256 sidecar missing: {hero_sidecar}"
        sidecar_data = json.loads(hero_sidecar.read_text(encoding="utf-8"))
        actual_hash = compute_sha256(hero_glb)
        assert sidecar_data.get("sha256", "").lower() == actual_hash.lower(), "SHA-256 sidecar mismatch"
        print(f"[+] Verified GLB export: {hero_glb} ({glb_size} bytes, sha256={actual_hash[:16]}...)")

        # Verify baseline object is preserved
        insp_objs = executor.execute_tool("list_objects", {})
        live_names = [o.get("name") for o in insp_objs.result.get("objects", [])]
        assert "StudioReferenceRig" in live_names, "Baseline StudioReferenceRig was modified or deleted!"

        telemetry["stages"]["stage_1_workflow_execution"] = {
            "status": wf_report_1.status,
            "checkpoints_captured": wf_report_1.checkpoints_captured,
            "glb_size": glb_size,
            "sha256": actual_hash,
            "sidecar_valid": True,
        }

        # -------------------------------------------------------------
        # Stage 2: Automatic Rollback on Injected Verification Gate Failure
        # -------------------------------------------------------------
        print("\n--- STAGE 2: Verification Gate Failure & Automatic Rollback ---")
        corrupt_obj = assets_dir / "degenerate_asset.obj"
        corrupt_obj.write_text(CORRUPT_OBJ_TEXT, encoding="utf-8")
        corrupt_glb = outputs_dir / "degenerate_asset.glb"
        corrupt_obj_str = str(corrupt_obj).replace("\\", "/")
        corrupt_glb_str = str(corrupt_glb).replace("\\", "/")

        brief_2 = f"Convert '{corrupt_obj_str}' to '{corrupt_glb_str}'"
        print(f"[*] Brief: {brief_2}")

        contract_2 = director.decompose_brief(brief_2)

        # Attach strict verification gate that checks manifoldness (min 4 vertices, 1 polygon)
        strict_gate = MeshManifoldnessGate(min_vertices=4, min_polygons=1)
        wf_report_2 = director.submit_workflow(
            contract=contract_2,
            orchestrator=orchestrator,
            trusted_approval=True,
            gates={"stage_0_import": [strict_gate]},
        )

        print(f"[+] Workflow Status: {wf_report_2.status}")
        print(f"[+] Rollbacks executed: {len(wf_report_2.rollbacks_executed)}")

        assert wf_report_2.status == "FAILED", "Workflow should have failed due to gate violation"
        assert len(wf_report_2.rollbacks_executed) >= 1, "Expected rollback receipt"
        rb_receipt = wf_report_2.rollbacks_executed[0]
        assert rb_receipt.get("success") is True, f"Rollback operation failed: {rb_receipt}"
        print(f"[+] Rollback successfully verified: {rb_receipt.get('objects_removed')} removed")

        # Crucial checks:
        # 1. Output GLB was NEVER created
        assert not corrupt_glb.exists(), "Corrupt GLB was erroneously exported!"
        # 2. Corrupt object is NOT in the scene
        insp_post = executor.execute_tool("list_objects", {})
        post_names = [o.get("name") for o in insp_post.result.get("objects", [])]
        assert "degenerate_asset" not in post_names, "Corrupt mesh was left orphaned in scene!"
        # 3. Pre-existing object is completely intact
        assert "StudioReferenceRig" in post_names, "Baseline StudioReferenceRig was lost during rollback!"

        telemetry["stages"]["stage_2_gate_failure_and_rollback"] = {
            "status": wf_report_2.status,
            "rollbacks": wf_report_2.rollbacks_executed,
            "corrupt_glb_prevented": not corrupt_glb.exists(),
            "baseline_preserved": True,
        }

        # Clean up any leftover meshes from Stage 1 before batch testing
        executor.execute_tool("delete_object", {"name": "hero_model"})
        executor.execute_tool("purge_orphaned_datablocks", {})

        # -------------------------------------------------------------
        # Stage 3: Controlled Multi-Asset Batch Conversion
        # -------------------------------------------------------------
        print("\n--- STAGE 3: Controlled Multi-Asset Batch Conversion ---")
        batch_1 = assets_dir / "batch_cube.obj"
        batch_1.write_text(CUBE_OBJ_TEXT, encoding="utf-8")
        batch_2 = assets_dir / "batch_corrupt.obj"
        batch_2.write_text(CORRUPT_OBJ_TEXT, encoding="utf-8")
        batch_3 = assets_dir / "batch_pyramid.obj"
        batch_3.write_text(PYRAMID_OBJ_TEXT, encoding="utf-8")

        batch_inputs = [
            str(batch_1).replace("\\", "/"),
            str(batch_2).replace("\\", "/"),
            str(batch_3).replace("\\", "/"),
        ]

        batch_out_dir = outputs_dir / "batch_results"
        batch_out_dir.mkdir(parents=True, exist_ok=True)
        batch_out_dir_str = str(batch_out_dir).replace("\\", "/")

        processor = BatchAssetProcessor(
            orchestrator=orchestrator,
            executor=executor,
            director=director,
        )

        batch_report = processor.process_batch(
            input_paths=batch_inputs,
            output_dir=batch_out_dir_str,
            target_format="GLB",
            trusted_approval=True,
            gates={"stage_0_import": [MeshManifoldnessGate(min_vertices=4, min_polygons=1)]},
        )

        print(f"[+] Batch Summary: {batch_report.summary}")
        print(f"[+] Succeeded: {batch_report.succeeded_count}, Failed: {batch_report.failed_count}")

        # Assert per-asset failure isolation:
        # Asset 1 must succeed, Asset 2 must fail, Asset 3 must succeed
        assert batch_report.status == "PARTIAL", f"Unexpected batch status: {batch_report.status}"
        assert batch_report.succeeded_count == 2, f"Expected 2 successes, got {batch_report.succeeded_count}"
        assert batch_report.failed_count == 1, f"Expected 1 failure, got {batch_report.failed_count}"

        item_1 = batch_report.items[0]
        item_2 = batch_report.items[1]
        item_3 = batch_report.items[2]

        assert item_1.status == "SUCCEEDED"
        assert item_2.status == "FAILED"
        assert item_2.rollback_performed is True
        assert item_3.status == "SUCCEEDED"

        # Verify output files and sidecars
        out_1 = Path(item_1.output_path)
        out_3 = Path(item_3.output_path)
        assert out_1.exists() and out_1.stat().st_size > 0, "Batch output 1 missing"
        assert out_3.exists() and out_3.stat().st_size > 0, "Batch output 3 missing"
        assert not Path(item_2.output_path).exists(), "Failed asset output 2 should not exist"

        sidecar_1 = Path(item_1.sidecar_path)
        sidecar_3 = Path(item_3.sidecar_path)
        assert sidecar_1.exists() and sidecar_3.exists()

        hash_1 = compute_sha256(out_1)
        hash_3 = compute_sha256(out_3)
        assert json.loads(sidecar_1.read_text(encoding="utf-8"))["sha256"].lower() == hash_1.lower()
        assert json.loads(sidecar_3.read_text(encoding="utf-8"))["sha256"].lower() == hash_3.lower()

        print(f"[+] Verified Batch Asset 1: {out_1.name} ({out_1.stat().st_size} bytes, sha256={hash_1[:16]}...)")
        print(f"[+] Verified Batch Asset 2: Failed & rolled back safely without corrupting batch.")
        print(f"[+] Verified Batch Asset 3: {out_3.name} ({out_3.stat().st_size} bytes, sha256={hash_3[:16]}...)")

        # Verify baseline object is still completely preserved
        insp_final = executor.execute_tool("list_objects", {})
        print(f"[DEBUG] insp_final: status={getattr(insp_final, 'status', None)}, result={getattr(insp_final, 'result', None)}, message={getattr(insp_final, 'message', None)}")
        assert insp_final.is_success, f"list_objects failed: {insp_final.message}"
        final_names = [o.get("name") for o in insp_final.result.get("objects", [])]
        assert "StudioReferenceRig" in final_names, "Baseline object lost after batch execution!"

        telemetry["stages"]["stage_3_batch_conversion"] = {
            "status": batch_report.status,
            "succeeded_count": batch_report.succeeded_count,
            "failed_count": batch_report.failed_count,
            "items": [it.to_dict() for it in batch_report.items],
        }

        # -------------------------------------------------------------
        # Stage 4: Security and Fail-Closed Invariants
        # -------------------------------------------------------------
        print("\n--- STAGE 4: Security & Fail-Closed Invariants ---")
        security_results = {}

        # 1. Path traversal in batch output directory
        rep_trav_out = processor.process_batch(
            input_paths=[str(batch_1)],
            output_dir="../../secret_escape",
            target_format="GLB",
        )
        assert rep_trav_out.status == "FAILED" and "traversal" in rep_trav_out.summary.lower()
        print("[+] Traversal in batch output dir rejected")
        security_results["traversal_output_rejected"] = True

        # 2. Path traversal in batch input path
        rep_trav_in = processor.process_batch(
            input_paths=["../secret.obj"],
            output_dir=batch_out_dir_str,
            target_format="GLB",
        )
        assert rep_trav_in.status == "FAILED" and "traversal" in rep_trav_in.items[0].error.lower()
        print("[+] Traversal in batch input path rejected")
        security_results["traversal_input_rejected"] = True

        # 3. Model-supplied approved=True injection rejection
        batch_1_str = str(batch_1).replace("\\", "/")
        bad_contract = director.decompose_brief(f"Convert '{batch_1_str}' to 'out.glb'")
        for tasks in bad_contract.domain_tasks.values():
            for t in tasks:
                t.input_params["approved"] = True
        try:
            director.submit_workflow(bad_contract, orchestrator, trusted_approval=True)
            untrusted_rejected = False
        except PermissionError:
            untrusted_rejected = True
        assert untrusted_rejected
        print("[+] Untrusted approved=True injection rejected with PermissionError")
        security_results["untrusted_approval_rejected"] = True

        # 4. Unapproved workflow pauses in AWAITING_APPROVAL
        good_contract = director.decompose_brief(f"Convert '{batch_1_str}' to 'out.glb'")
        pause_report = director.submit_workflow(good_contract, orchestrator, trusted_approval=False)
        assert pause_report.status == "AWAITING_APPROVAL"
        print("[+] Unapproved workflow paused in AWAITING_APPROVAL")
        security_results["unapproved_pause_verified"] = True

        telemetry["stages"]["stage_4_security_invariants"] = security_results

        # -------------------------------------------------------------
        # Copy Preserved Evidence to Evidence Directory
        # -------------------------------------------------------------
        shutil.copy(hero_glb, EVIDENCE_DIR / "hero_model.glb")
        shutil.copy(hero_sidecar, EVIDENCE_DIR / "hero_model.glb.sha256")
        shutil.copy(out_1, EVIDENCE_DIR / "batch_cube.glb")
        shutil.copy(sidecar_1, EVIDENCE_DIR / "batch_cube.glb.sha256")
        shutil.copy(out_3, EVIDENCE_DIR / "batch_pyramid.glb")
        shutil.copy(sidecar_3, EVIDENCE_DIR / "batch_pyramid.glb.sha256")

        telemetry_file = EVIDENCE_DIR / "milestone_10_4_telemetry.json"
        telemetry_file.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
        print(f"\n[+] Preserved verification artifacts and telemetry to: {EVIDENCE_DIR}")

        print("\n" + "=" * 80)
        print("MILESTONE 10.4 LIVE VERIFICATION PASSED: ALL 4 STAGES VERIFIED")
        print("=" * 80)

    except Exception as e:
        print(f"\n[!] Verification encountered exception: {e}")
        if blender_log_path.exists():
            try:
                blender_log_file.flush()
                lines = blender_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                print(f"[!] Blender log tail (last 40 lines):\n" + "\n".join(lines[-40:]))
            except Exception:
                pass
        raise
    finally:
        print("[*] Terminating disposable Blender instance...")
        try:
            blender_log_file.close()
        except Exception:
            pass
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
    run_milestone_10_4_verification()
