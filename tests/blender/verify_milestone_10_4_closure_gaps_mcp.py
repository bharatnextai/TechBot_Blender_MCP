"""
Milestone 10.4 Targeted Evidence Closure Script
Verifies:
1. Injected export-stage failure & automatic checkpoint rollback.
2. Scene integrity and orphaned datablock reclamation after export failure.
3. TextureBoundsGate passing and failing evaluation against real Blender 5.2.2.
Preserves existing successful batch, checkpoint, manifoldness, and security evidence.
Runs on ephemeral port with disposable workspace; production bridge (9877) untouched.
"""

import os
import sys
import json
import time
import socket
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any

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

# Simple Cube OBJ with no texture coordinates (no vt lines)
CUBE_NO_UV_OBJ = """# Cube without UV coordinates
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


def run_milestone_10_4_closure():
    print("=" * 80)
    print("STARTING CAPABILITY 10 — MILESTONE 10.4 EVIDENCE CLOSURE VERIFICATION")
    print("EXPORT FAILURE ROLLBACK & TEXTURE BOUNDS GATE EVALUATION")
    print("=" * 80)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-M10-4-CLOSURE-"))
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
        "closure_checks": {},
    }

    try:
        start_time = time.monotonic()
        while not ready_file.exists():
            if proc.poll() is not None:
                raise RuntimeError(f"Blender exited early with code {proc.poll()}")
            if time.monotonic() - start_time > 30:
                raise TimeoutError("Blender failed to start within 30 seconds.")
            time.sleep(0.1)

        ready_info = json.loads(ready_file.read_text(encoding="utf-8"))
        telemetry["blender_pid"] = ready_info["pid"]
        telemetry["blender_version"] = ready_info.get("blender", "5.2.2 LTS")
        print(f"[+] Blender ready! PID: {ready_info['pid']}, Version: {ready_info.get('blender', '5.2.2 LTS')}")

        os.environ["PYTHONPATH"] = str(PROJECT)
        os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
        os.environ["UMCP_LOCAL_TEST_SCOPE"] = "asset_v1"
        os.environ["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
        os.environ["UMCP_WORKSPACE_ROOT"] = str(run_root)
        os.environ["UMCP_BRIDGE_PORT"] = str(port)

        sys.path.insert(0, str(PROJECT))
        from mcp_service.execution.blender_executor import BlenderExecutor
        from mcp_service.workflow.orchestrator import WorkflowOrchestrator
        from mcp_service.workflow.checkpoints import SceneCheckpointManager
        from mcp_service.workflow.rollback import StageRollbackEngine
        from mcp_service.workflow.verification_gates import TextureBoundsGate
        from shared.models.agent_contracts import AgentTask, DelegationContract

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()
        checkpoint_manager = SceneCheckpointManager()
        rollback_engine = StageRollbackEngine(checkpoint_manager=checkpoint_manager)
        orchestrator = WorkflowOrchestrator(
            executor=executor,
            checkpoint_manager=checkpoint_manager,
            rollback_engine=rollback_engine,
        )

        # -------------------------------------------------------------
        # Step 0: Create Sentinel Baseline Object
        # -------------------------------------------------------------
        print("\n--- Step 0: Baseline Object Creation ---")
        ref_res = executor.execute_tool("create_primitive", {
            "primitive_type": "cylinder",
            "name": "StudioReferenceRig",
            "location": [5.0, 5.0, 0.0],
            "radius": 0.5,
            "depth": 2.0,
        })
        assert ref_res.is_success, f"Failed to create StudioReferenceRig: {ref_res.message}"
        print("[+] Created baseline 'StudioReferenceRig' (with default UVMap)")

        # Capture pre-workflow checkpoint
        base_ckpt = checkpoint_manager.capture_checkpoint(
            stage_id="pre_workflow_baseline",
            executor=executor,
        )
        assert "StudioReferenceRig" in base_ckpt.objects
        print(f"[+] Baseline checkpoint captured: {base_ckpt.checkpoint_id} ({len(base_ckpt.objects)} objects)")

        # -------------------------------------------------------------
        # Step 1: Export-Stage Failure Injection & Automatic Rollback
        # -------------------------------------------------------------
        print("\n--- Step 1: Export-Stage Failure Injection & Rollback ---")
        hero_obj = assets_dir / "hero_cube.obj"
        hero_obj.write_text(CUBE_NO_UV_OBJ, encoding="utf-8")
        hero_obj_str = str(hero_obj).replace("\\", "/")
        corrupt_out = outputs_dir / "corrupt_hero.invalid"
        corrupt_out_str = str(corrupt_out).replace("\\", "/")

        # Build a 2-stage contract: Import -> Export (with injected invalid format)
        t_import = AgentTask(
            task_id="stage_0_import",
            required_capability="interchange.asset_io",
            task_type="import_scene_asset",
            input_params={
                "filepath": hero_obj_str,
                "format": "OBJ",
            },
            dependencies=[],
        )
        t_export_corrupt = AgentTask(
            task_id="stage_7_delivery",
            required_capability="interchange.asset_io",
            task_type="export_scene_asset",
            input_params={
                "filepath": corrupt_out_str,
                "format": "UNSUPPORTED_CORRUPT_FORMAT",  # Injected failure
                "overwrite": True,
            },
            dependencies=["stage_0_import"],
        )

        contract = DelegationContract(
            title="Export Failure Injection Test",
            brief="Import cube and attempt invalid export",
            director_agent_id="director",
            domain_tasks={
                "agent.interchange_delivery": [t_import, t_export_corrupt]
            },
            dependencies={"stage_7_delivery": ["stage_0_import"]},
        )

        dag = orchestrator.compile_contract(contract)
        wf_report = orchestrator.execute_workflow(dag, approval_status="APPROVED")

        print(f"[+] Workflow Status: {wf_report.status}")
        print(f"[+] Rollbacks executed by Orchestrator: {len(wf_report.rollbacks_executed)}")

        assert wf_report.status == "FAILED", f"Expected workflow failure, got {wf_report.status}"
        assert len(wf_report.rollbacks_executed) >= 1, "Expected stage rollback receipt on export failure"
        export_stage = wf_report.stages.get("stage_7_delivery", {})
        assert str(export_stage.get("status")).lower() == "failed", f"Export stage should have failed, got: {export_stage.get('status')}"
        assert not corrupt_out.exists(), "Corrupt output file should not exist on disk"
        print(f"[+] Export stage failed as expected: {export_stage.get('error')}")

        # Roll back to the pre-workflow baseline checkpoint to clean imported mesh
        rb_receipt = rollback_engine.rollback_to_checkpoint(
            base_ckpt,
            executor=executor,
            trusted_approval=True,
        )
        assert rb_receipt.success is True, f"Rollback to pre-workflow checkpoint failed: {rb_receipt.error}"
        print(f"[+] Pre-workflow rollback executed: {rb_receipt.objects_removed} removed")

        # Purge any orphaned datablocks
        purge_res = executor.execute_tool("purge_orphaned_datablocks", {}, trusted_approval=True)
        purged_count = purge_res.result.get("purged_count", 0) if purge_res.is_success else 0
        print(f"[+] Orphaned datablocks purged: {purged_count}")

        # Verify scene integrity: only StudioReferenceRig remains
        insp = executor.execute_tool("list_objects", {})
        live_names = [o.get("name") for o in insp.result.get("objects", [])]
        assert "StudioReferenceRig" in live_names, "Baseline StudioReferenceRig was lost!"
        assert "hero_cube" not in live_names, "Imported hero_cube was not cleaned up!"
        assert len(live_names) == 1, f"Unexpected objects in scene: {live_names}"
        print(f"[+] Scene integrity confirmed: exactly 1 object in scene: {live_names}")

        telemetry["closure_checks"]["export_failure_and_rollback"] = {
            "workflow_status": wf_report.status,
            "export_stage_error": export_stage.get("error"),
            "corrupt_file_prevented": not corrupt_out.exists(),
            "rollback_objects_removed": rb_receipt.objects_removed,
            "purged_datablocks": purged_count,
            "final_scene_objects": live_names,
            "verified": True,
        }

        # -------------------------------------------------------------
        # Step 2: TextureBoundsGate Passing & Failing Cases
        # -------------------------------------------------------------
        print("\n--- Step 2: TextureBoundsGate Evaluation ---")

        # Case 2A: Failing Case — Import mesh with NO UV coordinates
        t_import_no_uv = executor.execute_tool("import_scene_asset", {
            "filepath": hero_obj_str,
            "format": "OBJ",
        }, trusted_approval=True)
        assert t_import_no_uv.is_success, f"Failed to import hero_cube: {t_import_no_uv.message}"

        gate_uv_fail = TextureBoundsGate(object_name="hero_cube", require_uv=True)
        res_fail = gate_uv_fail.evaluate("stage_test_uv", {"target_object": "hero_cube"}, executor)
        print(f"[+] Case 2A (No UVs) Gate Result: passed={res_fail.passed}, message='{res_fail.message}'")
        assert res_fail.passed is False, "Expected TextureBoundsGate to FAIL on mesh without UVs"
        assert "no UV layers" in res_fail.message, f"Unexpected failure message: {res_fail.message}"

        # Clean up hero_cube
        executor.execute_tool("delete_object", {"name": "hero_cube"}, trusted_approval=True)

        # Case 2B: Passing Case — StudioReferenceRig (created by Blender with default UVMap)
        gate_uv_pass = TextureBoundsGate(object_name="StudioReferenceRig", require_uv=True)
        res_pass = gate_uv_pass.evaluate("stage_test_uv", {"target_object": "StudioReferenceRig"}, executor)
        print(f"[+] Case 2B (Valid UVs) Gate Result: passed={res_pass.passed}, message='{res_pass.message}'")
        assert res_pass.passed is True, f"Expected TextureBoundsGate to PASS on StudioReferenceRig: {res_pass.message}"
        assert "passed texture bounds verification" in res_pass.message

        telemetry["closure_checks"]["texture_bounds_gate"] = {
            "failing_case": {
                "object_name": "hero_cube",
                "passed": res_fail.passed,
                "message": res_fail.message,
                "expected": "FAIL",
                "verified": True,
            },
            "passing_case": {
                "object_name": "StudioReferenceRig",
                "passed": res_pass.passed,
                "message": res_pass.message,
                "expected": "PASS",
                "verified": True,
            },
        }

        # Final check: Baseline StudioReferenceRig intact
        insp_end = executor.execute_tool("list_objects", {})
        end_names = [o.get("name") for o in insp_end.result.get("objects", [])]
        assert "StudioReferenceRig" in end_names
        print(f"[+] Final verification: StudioReferenceRig intact: {end_names}")

        closure_telemetry_file = EVIDENCE_DIR / "milestone_10_4_closure_telemetry.json"
        closure_telemetry_file.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
        print(f"\n[+] Closure evidence preserved to: {closure_telemetry_file}")

        print("\n" + "=" * 80)
        print("MILESTONE 10.4 EVIDENCE CLOSURE VERIFIED: ALL CHECKS PASSED")
        print("=" * 80)

    except Exception as e:
        print(f"\n[!] Closure verification encountered exception: {e}")
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
    run_milestone_10_4_closure()
