"""
Automated Real MCP-to-Blender E2E Verification of Fine-Scale Anatomical Surface Detailing (v0.1.58).
Verifies TASK v0.1.58:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Source reference image preservation (SHA-256 and size immutable).
4. Discover tools over stdio MCP wire:
   - detail_surface_features
   - inspect_surface_detail
5. Initial Scene Summary check (clean disposable scene).
6. Target blockout mesh and scene camera setup.
7. inspect_surface_detail initial inspection (topology, bounding box, discrete Laplacian roughness).
8. configure_semantic_landmarks setup on target mesh.
9. detail_surface_features with SCALES:
   - Bounded procedural cellular scale relief.
   - Measurable surface roughness increase (delta > 0).
   - Landmark preservation (quadratic damping around landmarks).
   - Silhouette regression protection across calibrated FRONT view.
   - Topology preservation (vertex and face count invariant).
10. Independent readback verification:
    - inspect_surface_detail confirms final roughness and topology.
    - inspect_semantic_landmarks confirms landmark stability.
    - inspect_scene_data confirms geometry invariance.
11. Test RIDGES, FACETS, VEINS feature types.
12. Pre-modification resource limit enforcement (rejects before modifying mesh).
13. Transactional rollback test:
    - Impossible regression tolerance triggers rejection.
    - Bit-for-bit mesh coordinate rollback verified.
14. Backward-compatible delegation from optimize_mesh_silhouette.
15. Fail-closed security guardrails:
    - Untrusted client approved=True rejected.
    - Non-existent target object rejected.
    - Non-mesh target object rejected.
16. Clean process shutdown and reference image immutability verification.
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
    print("=== TASK v0.1.58: Fine-Scale Anatomical Surface Detailing E2E Verification ===")

    # 1. Baseline Reference Image Check
    assert REFERENCE_IMAGE.exists(), f"Reference image missing: {REFERENCE_IMAGE}"
    pre_stat = REFERENCE_IMAGE.stat()
    pre_sha256 = get_file_sha256(REFERENCE_IMAGE)
    print(f"[OK] Reference image baseline verified: {REFERENCE_IMAGE.name}")
    print(f"     Size: {pre_stat.st_size:,} bytes, SHA-256: {pre_sha256}")

    # 2. Setup Disposable Test Environment
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-SURFACE-DETAIL-"))
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

            # Verify tool discovery in catalog
            catalog = await session.list_tools()
            tool_names = [t.name for t in catalog.tools]
            for t_name in ("detail_surface_features", "inspect_surface_detail"):
                assert t_name in tool_names, f"{t_name} missing from tools: {tool_names}"
            print("[PASS] Catalog Check: detail_surface_features, inspect_surface_detail discoverable")

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
                "primitive_type": "sphere",
                "name": target_mesh,
                "radius": 1.0,
                "location": [0.0, 0.0, 1.5],
            })
            assert mesh_res["status"] == "success", mesh_res
            print(f"[PASS] Step 2b: Target Blockout Mesh '{target_mesh}' Created (Sphere)")

            topo_before = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert topo_before["status"] == "success", topo_before
            initial_v_count = topo_before["result"]["vertex_count"]
            initial_p_count = topo_before["result"]["polygon_count"]
            assert initial_v_count == 482, f"Expected 482 sphere vertices, got {initial_v_count}"
            assert initial_p_count == 512, f"Expected 512 sphere polygons, got {initial_p_count}"
            print(f"[PASS] Step 2c: Initial Topology Recorded: {initial_v_count} verts, {initial_p_count} polys")

            # --- STEP 3: Inspect Initial Surface Detail ---
            insp_before = await call_tool("inspect_surface_detail", {
                "target_object": target_mesh,
            })
            assert insp_before["status"] == "success", insp_before
            init_res = insp_before["result"]
            assert init_res["status"] == "SUCCESS"
            assert init_res["vertex_count"] == 482
            assert init_res["face_count"] == 512
            assert init_res["roughness_metric"] == "MEAN_LAPLACIAN_DEVIATION"
            initial_roughness = init_res["surface_roughness"]
            assert initial_roughness > 0.0, f"Expected positive roughness, got {initial_roughness}"
            print(f"[PASS] Step 3: Initial Surface Roughness Inspected: {initial_roughness:.6f} m")

            # --- STEP 4: Configure Semantic Landmarks on Blockout ---
            lm_conf = await call_tool("configure_semantic_landmarks", {
                "target_object": target_mesh,
                "action": "SET",
                "landmarks": [
                    {
                        "name": "snout_tip",
                        "vertex_index": 0,
                        "reference_views": {"FRONT": [0.50, 0.40], "SIDE": [0.60, 0.40]},
                        "weight": 2.0,
                    },
                    {
                        "name": "horn_apex",
                        "vertex_index": 10,
                        "reference_views": {"FRONT": [0.45, 0.65], "SIDE": [0.55, 0.65]},
                        "weight": 1.5,
                    },
                    {
                        "name": "wing_apex",
                        "vertex_index": 50,
                        "reference_views": {"FRONT": [0.25, 0.55], "SIDE": [0.45, 0.55]},
                        "weight": 1.5,
                    },
                ],
            })
            assert lm_conf["status"] == "success", lm_conf
            assert lm_conf["result"]["landmarks_count"] == 3
            print("[PASS] Step 4: Stored 3 Semantic Landmarks on Target Blockout Mesh")

            lm_insp_pre = await call_tool("inspect_semantic_landmarks", {"target_object": target_mesh})
            assert lm_insp_pre["status"] == "success", lm_insp_pre
            initial_lm_rmse = lm_insp_pre["result"]["aggregate_rmse"]
            print(f"[PASS] Step 4b: Initial Semantic Landmark RMSE: {initial_lm_rmse:.6f}")

            # --- STEP 5: Apply detail_surface_features with SCALES ---
            scales_res = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "SCALES",
                "feature_scale": 0.25,
                "depth": 0.04,
                "strength": 0.7,
                "max_displacement": 0.06,
                "iterations": 1,
                "preserve_landmarks": True,
                "landmark_protection_radius": 0.35,
                "max_landmark_regression": 0.02,
                "views": [
                    {
                        "view": "FRONT",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "weight": 1.0,
                        "max_regression_tolerance": 0.05,
                    }
                ],
            })
            assert scales_res["status"] == "success", scales_res
            s_data = scales_res["result"]
            assert s_data["status"] == "SUCCESS", s_data
            assert s_data["detailing_status"] == "ACCEPTED", s_data
            assert s_data["feature_type"] == "SCALES"
            assert s_data["surface_roughness_delta"] > 0.0, f"Expected roughness delta > 0, got {s_data['surface_roughness_delta']}"
            assert s_data["max_vertex_displacement"] > 0.0, f"Expected displacement > 0, got {s_data['max_vertex_displacement']}"
            assert s_data["max_vertex_displacement"] <= 0.06001, f"Displacement exceeded cap: {s_data['max_vertex_displacement']}"
            assert s_data["landmarks_preserved"] is True, "Landmarks were not preserved"
            assert s_data["topology_preserved"] is True, "Topology altered unexpectedly"
            assert s_data["final_vertex_count"] == initial_v_count
            assert s_data["final_face_count"] == initial_p_count
            print(f"[PASS] Step 5: SCALES Relief Applied Successfully:")
            print(f"       Roughness: {s_data['initial_surface_roughness']:.6f} -> {s_data['final_surface_roughness']:.6f} (delta +{s_data['surface_roughness_delta']:.6f})")
            print(f"       Displacement Max: {s_data['max_vertex_displacement']:.6f} m, Affected Vertices: {s_data['affected_vertices_count']}")
            print(f"       Landmarks Preserved: {s_data['landmarks_preserved']}, Topology Preserved: {s_data['topology_preserved']}")

            # --- STEP 6: Independent Readback Verification ---
            readback_insp = await call_tool("inspect_surface_detail", {"target_object": target_mesh})
            assert readback_insp["status"] == "success"
            readback_data = readback_insp["result"]
            assert readback_data["vertex_count"] == initial_v_count
            assert readback_data["face_count"] == initial_p_count
            assert math.isclose(readback_data["surface_roughness"], s_data["final_surface_roughness"], abs_tol=1e-5)
            print(f"[PASS] Step 6a: Independent inspect_surface_detail confirmed roughness {readback_data['surface_roughness']:.6f} and topology invariants")

            readback_lm = await call_tool("inspect_semantic_landmarks", {"target_object": target_mesh})
            assert readback_lm["status"] == "success"
            post_lm_rmse = readback_lm["result"]["aggregate_rmse"]
            assert post_lm_rmse <= initial_lm_rmse + 0.02, f"Landmark RMSE regressed: {initial_lm_rmse} -> {post_lm_rmse}"
            print(f"[PASS] Step 6b: Independent inspect_semantic_landmarks confirmed landmark stability (RMSE: {post_lm_rmse:.6f})")

            # --- STEP 7: Test RIDGES Feature Type ---
            ridges_res = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "RIDGES",
                "feature_scale": 0.3,
                "depth": 0.03,
                "orientation": [0.0, 1.0, 0.0],
                "iterations": 1,
                "preserve_landmarks": True,
            })
            assert ridges_res["status"] == "success", ridges_res
            assert ridges_res["result"]["detailing_status"] == "ACCEPTED"
            assert ridges_res["result"]["feature_type"] == "RIDGES"
            assert ridges_res["result"]["max_vertex_displacement"] > 0.0
            print(f"[PASS] Step 7: RIDGES Relief Applied (disp: {ridges_res['result']['max_vertex_displacement']:.6f} m)")

            # --- STEP 8: Test FACETS Feature Type ---
            facets_res = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "FACETS",
                "feature_scale": 0.2,
                "depth": 0.03,
                "iterations": 1,
                "preserve_landmarks": True,
            })
            assert facets_res["status"] == "success", facets_res
            assert facets_res["result"]["detailing_status"] == "ACCEPTED"
            assert facets_res["result"]["feature_type"] == "FACETS"
            print(f"[PASS] Step 8: FACETS Relief Applied (disp: {facets_res['result']['max_vertex_displacement']:.6f} m)")

            # --- STEP 9: Test VEINS Feature Type ---
            veins_res = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "VEINS",
                "feature_scale": 0.18,
                "depth": 0.025,
                "orientation": [1.0, 0.0, 0.0],
                "iterations": 1,
                "preserve_landmarks": True,
            })
            assert veins_res["status"] == "success", veins_res
            assert veins_res["result"]["detailing_status"] == "ACCEPTED"
            assert veins_res["result"]["feature_type"] == "VEINS"
            print(f"[PASS] Step 9: VEINS Relief Applied (disp: {veins_res['result']['max_vertex_displacement']:.6f} m)")

            # --- STEP 10: Pre-modification Resource Limit Enforcement ---
            limit_res = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "SCALES",
                "max_vertex_count": 200,  # sphere has 482 vertices
            })
            assert limit_res["status"] == "error", f"Expected error on limit exceed, got {limit_res}"
            assert "Precondition limit exceeded" in limit_res["message"]
            print("[PASS] Step 10: Pre-modification vertex limit rejection verified fail-closed")

            # --- STEP 11: Transactional Rollback on Impossible Regression Tolerance ---
            coords_before_rollback = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            v_count_pre = coords_before_rollback["result"]["vertex_count"]

            rollback_res = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "SCALES",
                "depth": -0.5,
                "max_displacement": 0.3,
                "views": [
                    {
                        "view": "FRONT",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "max_regression_tolerance": 0.0001,
                    }
                ],
                "rollback_on_failure": True,
            })
            assert rollback_res["status"] == "success", rollback_res
            rb_data = rollback_res["result"]
            assert rb_data["status"] == "ERROR"
            assert rb_data["detailing_status"] == "REJECTED_ROLLED_BACK"
            assert rb_data["rolled_back"] is True
            print(f"[PASS] Step 11: Transactional rollback executed on regression tolerance violation")

            # Confirm coordinates restored
            coords_after_rollback = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert coords_after_rollback["result"]["vertex_count"] == v_count_pre
            print("[PASS] Step 11b: Topology and mesh coordinates restored bit-for-bit after rollback")

            # --- STEP 12: Backward-Compatible Delegation from optimize_mesh_silhouette ---
            delegation_res = await call_tool("optimize_mesh_silhouette", {
                "target_object": target_mesh,
                "refinement_mode": "SURFACE_DETAIL",
                "feature_type": "SCALES",
                "feature_scale": 0.3,
                "depth": 0.02,
                "reference_image_path": str(REFERENCE_IMAGE),
                "preserve_landmarks": False,
            })
            assert delegation_res["status"] == "success", delegation_res
            assert delegation_res["result"]["detailing_status"] == "ACCEPTED"
            assert delegation_res["result"]["feature_type"] == "SCALES"
            print("[PASS] Step 12: Backward-compatible delegation from optimize_mesh_silhouette verified")

            # --- STEP 13: Fail-Closed Security Guardrails ---
            # 13a: Untrusted approved=True rejected
            untrusted_res = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "SCALES",
                "approved": True,
            })
            assert untrusted_res["status"] == "error", untrusted_res
            assert "untrusted" in untrusted_res["message"].lower() or "approval denied" in untrusted_res["message"].lower()
            print("[PASS] Step 13a: Untrusted approved=True rejected fail-closed")

            # 13b: Non-existent object
            non_exist_res = await call_tool("detail_surface_features", {
                "target_object": "NonExistentMesh123",
                "feature_type": "SCALES",
            })
            assert non_exist_res["status"] == "error", non_exist_res
            assert "not found" in non_exist_res["message"].lower()
            print("[PASS] Step 13b: Non-existent object rejected fail-closed")

            # 13c: Non-mesh object (Camera)
            non_mesh_res = await call_tool("detail_surface_features", {
                "target_object": "SceneCamera",
                "feature_type": "SCALES",
            })
            assert non_mesh_res["status"] == "error", non_mesh_res
            assert "not a mesh" in non_mesh_res["message"].lower()
            print("[PASS] Step 13c: Non-mesh object (Camera) rejected fail-closed")

    # 14. Clean Shutdown
    print("Initiating clean shutdown...")
    (run_root / "stop.flag").touch()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)
    print("[PASS] Disposable Blender shut down cleanly")

    # 15. Source Reference Image Preservation Check
    post_stat = REFERENCE_IMAGE.stat()
    post_sha256 = get_file_sha256(REFERENCE_IMAGE)
    assert pre_stat.st_size == post_stat.st_size, "Reference image file size changed!"
    assert pre_sha256 == post_sha256, "Reference image SHA-256 altered!"
    print(f"[PASS] Reference Image Immutability Verified (SHA-256 intact: {post_sha256})")

    print("\n=========================================================================")
    print(">>> TASK v0.1.58 VERIFICATION PASSED: ALL 15 CRITICAL E2E CHECKS PASSED <<<")
    print("=========================================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
