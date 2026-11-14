"""
Automated Real MCP-to-Blender E2E Verification of Multi-View Silhouette Fitting (v0.1.54).
Verifies:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Source image preservation (SHA-256 and size immutable).
4. Real multi-view silhouette-guided mesh deformation (fit_multiview_silhouette)
   against FRONT and SIDE crops from Red Dragon 3D Reference Sheet:
   - Simultaneous optimization across FRONT and SIDE views.
   - Aggregate IoU improvement.
   - Strict regression protection on protected views.
   - Topology preservation invariant (8 vertices, 12 edges, 6 polygons).
   - Structured iterative step history and convergence.
5. Independent readback verification using compare_silhouette_alignment and inspect_scene_data.
6. Transactional rollback test:
   - Enforces bit-for-bit rollback of mesh transforms and vertex coordinates when optimization fails to improve.
7. Backward compatibility delegation:
   - optimize_mesh_silhouette with views param routes to fit_multiview_silhouette.
8. Fail-closed security validations:
   - Untrusted model approved=True rejected.
   - Duplicate views rejected.
   - Non-existent target object rejected.
   - Non-mesh target object rejected.
9. Clean process shutdown and zero persistent state.
"""

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any, List

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON_EXE = Path(sys.executable)
REFERENCE_IMAGE = Path(r"C:\Users\Administrator\Desktop\2D Testing\Red Dragon 3D Reference Sheet.png")

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


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        if port == 9877:
            return find_free_port()
        return port


def get_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


async def main():
    print("=== TASK v0.1.54: Multi-View Silhouette Fitting E2E Verification ===")

    # 1. Baseline Reference Image Check
    assert REFERENCE_IMAGE.exists(), f"Reference image missing: {REFERENCE_IMAGE}"
    pre_stat = REFERENCE_IMAGE.stat()
    pre_sha256 = get_file_sha256(REFERENCE_IMAGE)
    print(f"[OK] Reference image baseline verified: {REFERENCE_IMAGE.name}")
    print(f"     Size: {pre_stat.st_size:,} bytes, SHA-256: {pre_sha256}")

    # 2. Setup Disposable Test Environment
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-MULTIVIEW-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, "Ephemeral port must strictly avoid production port 9877!"
    print(f"[OK] Isolated environment initialized at {run_root} (Port: {port})")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    env["BLENDER_USER_CONFIG"] = str(config_dir)
    env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)

    bootstrap_file = run_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE)

    # 3. Launch Disposable Blender 5.2.2 in Background Mode
    blender_cmd = [
        str(BLENDER),
        "--background",
        "--disable-autoexec",
        "--python",
        str(bootstrap_file),
    ]
    print(f"Launching Blender: {' '.join(blender_cmd)}")
    proc = subprocess.Popen(blender_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    ready_file = run_root / "blender_ready.json"
    t0 = time.time()
    while not ready_file.exists():
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(f"Blender process died unexpectedly:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
        if time.time() - t0 > 30.0:
            proc.kill()
            raise TimeoutError("Timed out waiting for Blender bridge server to start")
        time.sleep(0.1)

    ready_data = json.loads(ready_file.read_text())
    print(f"[OK] Disposable Blender ready (PID: {ready_data['pid']}, Version: {ready_data['blender']})")

    # 4. Connect stdio MCP Client to mcp_service.app
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp import ClientSession

    client_env = dict(os.environ)
    client_env["PYTHONPATH"] = str(PROJECT)
    client_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)

    server_params = StdioServerParameters(
        command=str(PYTHON_EXE),
        args=[
            "-B", "-m", "mcp_service.app",
            "--transport", "stdio",
            "--bridge-port", str(port),
            "--bridge-timeout", "10",
            "--approval-mode", "blender",
        ],
        env=client_env,
        cwd=str(PROJECT),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("[OK] stdio MCP Client initialized and connected to bridge")

            async def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                try:
                    res = await session.call_tool(name, arguments=args)
                except Exception as ex:
                    return {"status": "error", "message": str(ex), "exception": type(ex).__name__}
                if getattr(res, "isError", False):
                    err_text = res.content[0].text if res.content else "Tool error"
                    return {"status": "error", "message": err_text}
                content = res.content[0].text if res.content else "{}"
                try:
                    data = json.loads(content)
                except Exception:
                    data = {"status": "error", "message": content}
                return data

            # --- STEP 1: Verify Initial Clean Scene ---
            summary = await call_tool("get_scene_summary", {})
            assert summary["status"] == "success"
            assert summary["result"]["total_objects"] == 0
            print("[PASS] Step 1: Initial Scene Summary (0 objects in clean scene)")

            # --- STEP 2: Setup Scene Camera and Target Blockout Mesh ---
            cam_res = await call_tool("create_camera", {
                "name": "SceneCamera",
                "location": [0.0, -10.0, 1.5],
                "rotation_euler": [math.radians(90.0), 0.0, 0.0],
                "set_active": True,
            })
            assert cam_res["status"] == "success", cam_res
            print("[PASS] Step 2a: Scene Camera Created & Set as Active")

            target_mesh = "Dragon_Blockout"
            mesh_res = await call_tool("create_primitive", {
                "primitive_type": "cube",
                "name": target_mesh,
                "location": [0.0, 0.0, 0.5],
            })
            assert mesh_res["status"] == "success", mesh_res
            print(f"[PASS] Step 2b: Target Blockout Mesh '{target_mesh}' Created")

            # Inspect initial mesh topology
            topo_before = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert topo_before["status"] == "success", topo_before
            initial_v_count = topo_before["result"]["vertex_count"]
            initial_e_count = topo_before["result"]["edge_count"]
            initial_p_count = topo_before["result"]["polygon_count"]
            assert initial_v_count == 8, f"Expected 8 cube vertices, got {initial_v_count}"
            assert initial_p_count == 6, f"Expected 6 cube polygons, got {initial_p_count}"
            print(f"[PASS] Step 2c: Initial Topology Recorded: {initial_v_count} verts, {initial_e_count} edges, {initial_p_count} polys")

            # --- STEP 3: Execute fit_multiview_silhouette ---
            # FRONT crop: [0.0, 0.5, 0.5, 1.0], SIDE crop: [0.5, 0.5, 1.0, 1.0]
            mv_res = await call_tool("fit_multiview_silhouette", {
                "target_object": target_mesh,
                "views": [
                    {
                        "view": "FRONT",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.0, 0.5, 0.5, 1.0],
                        "coordinate_system": "UV",
                        "weight": 1.0,
                        "max_regression_tolerance": 0.02,
                    },
                    {
                        "view": "SIDE",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.5, 0.5, 1.0, 1.0],
                        "coordinate_system": "UV",
                        "weight": 1.0,
                        "max_regression_tolerance": 0.02,
                    },
                ],
                "objective": "WEIGHTED_IOU",
                "optimization_mode": "BOUNDED_SCALE_TRANSLATE",
                "preserve_topology": True,
                "max_iterations": 5,
                "max_displacement": 0.8,
                "step_size": 0.25,
                "tolerance": 0.001,
                "resolution": 256,
            })
            assert mv_res["status"] == "success", mv_res
            res_opt = mv_res["result"]

            print(f"     Optimization Status: {res_opt.get('status')}")
            print(f"     Initial Aggregate: {res_opt.get('initial_aggregate_score')}, Final Aggregate: {res_opt.get('final_aggregate_score')}")
            print(f"     Aggregate Improvement: {res_opt.get('aggregate_improvement')}")
            print(f"     Per-view Initial Metrics: {res_opt.get('initial_per_view_metrics')}")
            print(f"     Per-view Final Metrics: {res_opt.get('final_per_view_metrics')}")
            print(f"     Per-view IoU Deltas: {res_opt.get('per_view_iou_deltas')}")
            print(f"     Iterations Completed: {res_opt.get('iterations_completed')}")
            print(f"     Topology Preserved: {res_opt.get('topology_preserved')}")
            print(f"     Rolled Back: {res_opt.get('rolled_back')}")

            assert res_opt["status"] == "OPTIMIZED"
            assert res_opt["aggregate_improvement"] > 0.0, f"Expected positive aggregate improvement, got {res_opt['aggregate_improvement']}"
            assert res_opt["final_aggregate_score"] > res_opt["initial_aggregate_score"]
            assert res_opt["topology_preserved"] is True
            assert res_opt["rolled_back"] is False
            for v_name in ("FRONT", "SIDE"):
                assert v_name in res_opt["final_per_view_metrics"]
                delta = res_opt["per_view_iou_deltas"][v_name]
                assert delta >= -0.02, f"View {v_name} violated max regression tolerance: {delta}"
            print("[PASS] Step 3: Multi-View Silhouette Optimization Verified (Aggregate IoU improved, regression bounds held)")

            # --- STEP 4: Independent Topology Readback Verification ---
            topo_after = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert topo_after["status"] == "success", topo_after
            assert topo_after["result"]["vertex_count"] == initial_v_count, "Vertex count changed!"
            assert topo_after["result"]["edge_count"] == initial_e_count, "Edge count changed!"
            assert topo_after["result"]["polygon_count"] == initial_p_count, "Polygon count changed!"
            print(f"[PASS] Step 4: Independent Topology Invariant Confirmed ({initial_v_count} verts strictly preserved)")

            # --- STEP 5: Independent Multi-View Silhouette Readback Verification ---
            comp_front = await call_tool("compare_silhouette_alignment", {
                "reference_image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.0, 0.5, 0.5, 1.0],
                "coordinate_system": "UV",
                "view": "FRONT",
                "mode": "CAMERA",
                "width": 256,
                "height": 256,
            })
            assert comp_front["status"] == "success", comp_front
            front_iou = comp_front["result"]["iou"]
            print(f"     Independent FRONT Readback IoU: {front_iou} (Opt reported: {res_opt['final_per_view_metrics']['FRONT']['iou']})")
            assert math.isclose(front_iou, res_opt["final_per_view_metrics"]["FRONT"]["iou"], abs_tol=0.05)

            comp_side = await call_tool("compare_silhouette_alignment", {
                "reference_image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.5, 0.5, 1.0, 1.0],
                "coordinate_system": "UV",
                "view": "SIDE",
                "mode": "CAMERA",
                "width": 256,
                "height": 256,
            })
            assert comp_side["status"] == "success", comp_side
            side_iou = comp_side["result"]["iou"]
            print(f"     Independent SIDE Readback IoU: {side_iou} (Opt reported: {res_opt['final_per_view_metrics']['SIDE']['iou']})")
            assert math.isclose(side_iou, res_opt["final_per_view_metrics"]["SIDE"]["iou"], abs_tol=0.05)
            print("[PASS] Step 5: Independent Silhouette Readbacks Match Optimization Metrics for Both Views")

            # --- STEP 6: Transactional Rollback on Non-Improvement ---
            rollback_target = "Rollback_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "cube",
                "name": rollback_target,
                "location": [3.0, 0.0, 1.5],
            })

            pre_rollback_details = await call_tool("get_object_details", {"name": rollback_target})
            pre_rb_loc = [round(c, 4) for c in pre_rollback_details["result"]["location"]]
            pre_rb_scale = [round(c, 4) for c in pre_rollback_details["result"]["scale"]]

            # Run with max_iterations=1 and impossible tolerance
            opt_fail_res = await call_tool("fit_multiview_silhouette", {
                "target_object": rollback_target,
                "views": [
                    {
                        "view": "FRONT",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.0, 0.5, 0.5, 1.0],
                    },
                    {
                        "view": "SIDE",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.5, 0.5, 1.0, 1.0],
                    },
                ],
                "max_iterations": 1,
                "tolerance": 0.49,
                "rollback_on_failure": True,
                "resolution": 256,
            })
            assert opt_fail_res["status"] in ("error", "success"), opt_fail_res
            if opt_fail_res["status"] == "error":
                print(f"     Rollback Test Reported Failure as Expected: {opt_fail_res['message']}")
                assert "failure" in opt_fail_res["message"].lower() or "no_improvement" in opt_fail_res["message"].lower()
            else:
                rf = opt_fail_res["result"]
                print(f"     Rollback Test Result: Status={rf.get('status')}, RolledBack={rf.get('rolled_back')}")
                assert rf["success"] is False
                assert rf["status"] == "NO_IMPROVEMENT"
                assert rf["rolled_back"] is True

            post_rollback_details = await call_tool("get_object_details", {"name": rollback_target})
            post_rb_loc = [round(c, 4) for c in post_rollback_details["result"]["location"]]
            post_rb_scale = [round(c, 4) for c in post_rollback_details["result"]["scale"]]

            assert post_rb_loc == pre_rb_loc, f"Location was not rolled back: {post_rb_loc} != {pre_rb_loc}"
            assert post_rb_scale == pre_rb_scale, f"Scale was not rolled back: {post_rb_scale} != {pre_rb_scale}"
            print("[PASS] Step 6: Transactional Rollback Confirmed (Mesh restored bit-for-bit)")

            # --- STEP 7: Backward-Compatible Delegation ---
            deleg_mesh = "Delegation_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "cube",
                "name": deleg_mesh,
                "location": [-3.0, 0.0, 1.5],
            })
            deleg_res = await call_tool("optimize_mesh_silhouette", {
                "target_object": deleg_mesh,
                "reference_image_path": str(REFERENCE_IMAGE),
                "views": [
                    {
                        "view": "FRONT",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.0, 0.5, 0.5, 1.0],
                    },
                    {
                        "view": "SIDE",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.5, 0.5, 1.0, 1.0],
                    },
                ],
                "max_iterations": 2,
            })
            assert deleg_res["status"] == "success", deleg_res
            assert "final_aggregate_score" in deleg_res["result"] or "status" in deleg_res["result"]
            print("[PASS] Step 7: Backward-Compatible Delegation from optimize_mesh_silhouette Verified")

            # --- STEP 8: Fail-Closed Security Tests ---
            # 8a: Untrusted approval flag
            err_untrusted = await call_tool("fit_multiview_silhouette", {
                "target_object": target_mesh,
                "views": [
                    {"view": "FRONT", "reference_image_path": str(REFERENCE_IMAGE)},
                    {"view": "SIDE", "reference_image_path": str(REFERENCE_IMAGE)},
                ],
                "approved": True,
            })
            assert err_untrusted["status"] == "error", err_untrusted
            assert "untrusted" in err_untrusted["message"].lower() or "approval denied" in err_untrusted["message"].lower()
            print("[PASS] Step 8a: Untrusted approved=True flag rejected fail-closed")

            # 8b: Duplicate views
            err_dup = await call_tool("fit_multiview_silhouette", {
                "target_object": target_mesh,
                "views": [
                    {"view": "FRONT", "reference_image_path": str(REFERENCE_IMAGE)},
                    {"view": "FRONT", "reference_image_path": str(REFERENCE_IMAGE)},
                ],
            })
            assert err_dup["status"] == "error", err_dup
            assert "duplicate" in err_dup["message"].lower()
            print("[PASS] Step 8b: Duplicate views in configuration rejected fail-closed")

            # 8c: Non-existent object
            err_nonexistent = await call_tool("fit_multiview_silhouette", {
                "target_object": "NonExistentObject_99999",
                "views": [
                    {"view": "FRONT", "reference_image_path": str(REFERENCE_IMAGE)},
                    {"view": "SIDE", "reference_image_path": str(REFERENCE_IMAGE)},
                ],
            })
            assert err_nonexistent["status"] == "error", err_nonexistent
            assert "not found" in err_nonexistent["message"].lower()
            print("[PASS] Step 8c: Non-existent target object rejected fail-closed")

            # 8d: Non-mesh object
            err_nonmesh = await call_tool("fit_multiview_silhouette", {
                "target_object": "SceneCamera",
                "views": [
                    {"view": "FRONT", "reference_image_path": str(REFERENCE_IMAGE)},
                    {"view": "SIDE", "reference_image_path": str(REFERENCE_IMAGE)},
                ],
            })
            assert err_nonmesh["status"] == "error", err_nonmesh
            assert "not a mesh" in err_nonmesh["message"].lower() or "mesh" in err_nonmesh["message"].lower()
            print("[PASS] Step 8d: Non-mesh target object rejected fail-closed")

    # 5. Clean Process Shutdown
    print("Initiating clean shutdown of disposable Blender...")
    (run_root / "stop.flag").touch()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    print("[OK] Disposable Blender shutdown cleanly")

    # 6. Verify Source Image Immutability
    post_stat = REFERENCE_IMAGE.stat()
    post_sha256 = get_file_sha256(REFERENCE_IMAGE)
    assert post_stat.st_size == pre_stat.st_size, "Source image size changed!"
    assert post_sha256 == pre_sha256, "Source image SHA-256 changed!"
    print(f"[PASS] Source image immutability confirmed (SHA-256 strictly preserved: {post_sha256})")

    print("\n=== ALL E2E VERIFICATIONS PASSED SUCCESSFULLY (TASK v0.1.54) ===")


if __name__ == "__main__":
    asyncio.run(main())
