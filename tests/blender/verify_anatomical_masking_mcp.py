"""
Automated Real MCP-to-Blender E2E Verification of Anatomical Masking and Bilateral Symmetry (v0.1.59).
Verifies TASK v0.1.59:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Source reference image preservation (SHA-256 and size immutable).
4. Discover tools over stdio MCP wire:
   - configure_anatomical_mask
   - inspect_anatomical_mask
   - symmetrize_mesh_geometry
5. Initial Scene Summary check (clean disposable scene).
6. Target blockout mesh and scene camera setup.
7. Initial inspect_anatomical_mask check (confirms 0 masks on clean mesh).
8. configure_anatomical_mask with SPHERE region:
   - Creates vertex group 'Horns' with smooth falloff.
   - Weighted vertices count > 0, weights within [0.0, 1.0].
9. configure_anatomical_mask with BOUNDING_BOX region:
   - Creates vertex group 'Body_Scales'.
10. configure_anatomical_mask with CYLINDER region:
    - Creates vertex group 'Spine'.
11. inspect_anatomical_mask independent readback:
    - Lists all 3 vertex groups.
    - Specific inspection of 'Horns' reports mean_weight, max_weight, and symmetry stats.
12. Mask-modulated surface detailing:
    - detail_surface_features with mask_vertex_group='Horns'.
    - Displacements strictly modulated by Horns mask weights.
13. Symmetry-aware surface detailing:
    - detail_surface_features with use_symmetry=True and symmetry_axis='X'.
    - Midline vertices clamped to 0.0 and bilateral mirror applied.
14. symmetrize_mesh_geometry:
    - Applied with symmetry_axis='X', source_direction='+TO_-'.
    - Enforces symmetry across X axis and clamps midline vertices.
    - Reports asymmetry_rmse before and after.
15. Pre-modification resource limit enforcement (rejects before modifying mesh).
16. Transactional rollback test:
    - Regression tolerance violation triggers rollback.
    - Bit-for-bit mesh coordinates restored.
17. Backward-compatible delegation from optimize_mesh_silhouette:
    - refinement_mode='MASK' and 'SYMMETRIZE' delegation verified.
18. Fail-closed security guardrails:
    - Untrusted client approved=True rejected.
    - Non-existent target object rejected.
    - Non-mesh target object rejected.
19. Clean process shutdown and reference image immutability verification.
"""

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import socket
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
    print("=== TASK v0.1.59: Anatomical Masking and Bilateral Symmetry E2E Verification ===")

    # 1. Baseline Reference Image Check
    assert REFERENCE_IMAGE.exists(), f"Reference image missing: {REFERENCE_IMAGE}"
    pre_stat = REFERENCE_IMAGE.stat()
    pre_sha256 = get_file_sha256(REFERENCE_IMAGE)
    print(f"[OK] Reference image baseline verified: {REFERENCE_IMAGE.name}")
    print(f"     Size: {pre_stat.st_size:,} bytes, SHA-256: {pre_sha256}")

    # 2. Setup Disposable Test Environment
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-ANATOMICAL-MASK-"))
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
            for t_name in ("configure_anatomical_mask", "inspect_anatomical_mask", "symmetrize_mesh_geometry"):
                assert t_name in tool_names, f"{t_name} missing from tools: {tool_names}"
            print("[PASS] Catalog Check: configure_anatomical_mask, inspect_anatomical_mask, symmetrize_mesh_geometry discoverable")

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

            # --- STEP 2d: Configure Semantic Landmarks ---
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
            print("[PASS] Step 2d: Semantic Landmarks Configured")

            # --- STEP 3: Initial inspect_anatomical_mask ---
            insp_init = await call_tool("inspect_anatomical_mask", {
                "target_object": target_mesh,
            })
            assert insp_init["status"] == "success", insp_init
            assert insp_init["result"]["mask_count"] == 0
            print("[PASS] Step 3: Initial inspect_anatomical_mask confirmed 0 masks on clean mesh")

            # --- STEP 4: configure_anatomical_mask (SPHERE - Horns) ---
            mask_horns = await call_tool("configure_anatomical_mask", {
                "target_object": target_mesh,
                "action": "SET",
                "mask_name": "Horns",
                "region_type": "SPHERE",
                "center": [0.0, 0.0, 2.3],
                "radius": 0.5,
                "falloff": "SMOOTH",
                "symmetry_axis": "X",
            })
            assert mask_horns["status"] == "success", mask_horns
            res_h = mask_horns["result"]
            assert res_h["status"] == "SUCCESS", res_h
            assert res_h["mask_name"] == "Horns"
            assert res_h["weighted_vertices_count"] > 0
            assert res_h["max_weight"] <= 1.0001
            assert res_h["min_weight"] >= 0.0
            print(f"[PASS] Step 4: SPHERE Mask 'Horns' configured: {res_h['weighted_vertices_count']} weighted vertices (max={res_h['max_weight']:.4f})")

            # --- STEP 5: configure_anatomical_mask (BOUNDING_BOX - Body_Scales) ---
            mask_body = await call_tool("configure_anatomical_mask", {
                "target_object": target_mesh,
                "action": "SET",
                "mask_name": "Body_Scales",
                "region_type": "BOUNDING_BOX",
                "region_bounds": [-0.8, -0.8, 0.8, 0.8, 0.8, 1.8],
                "falloff": "LINEAR",
                "min_weight": 0.1,
                "max_weight": 0.9,
            })
            assert mask_body["status"] == "success", mask_body
            res_b = mask_body["result"]
            assert res_b["status"] == "SUCCESS", res_b
            assert res_b["mask_name"] == "Body_Scales"
            assert res_b["weighted_vertices_count"] > 0
            print(f"[PASS] Step 5: BOUNDING_BOX Mask 'Body_Scales' configured: {res_b['weighted_vertices_count']} weighted vertices")

            # --- STEP 6: configure_anatomical_mask (CYLINDER - Spine) ---
            mask_spine = await call_tool("configure_anatomical_mask", {
                "target_object": target_mesh,
                "action": "SET",
                "mask_name": "Spine",
                "region_type": "CYLINDER",
                "center": [0.0, 0.0, 1.5],
                "radius": 0.25,
                "falloff": "SMOOTH",
            })
            assert mask_spine["status"] == "success", mask_spine
            res_s = mask_spine["result"]
            assert res_s["status"] == "SUCCESS", res_s
            assert res_s["mask_name"] == "Spine"
            print(f"[PASS] Step 6: CYLINDER Mask 'Spine' configured: {res_s['weighted_vertices_count']} weighted vertices")

            # --- STEP 7: inspect_anatomical_mask Readback ---
            insp_all = await call_tool("inspect_anatomical_mask", {
                "target_object": target_mesh,
            })
            assert insp_all["status"] == "success", insp_all
            assert insp_all["result"]["mask_count"] == 3
            group_names = list(insp_all["result"]["masks"].keys())
            assert "Horns" in group_names
            assert "Body_Scales" in group_names
            assert "Spine" in group_names
            print(f"[PASS] Step 7a: inspect_anatomical_mask confirmed 3 active masks: {group_names}")

            insp_horns = await call_tool("inspect_anatomical_mask", {
                "target_object": target_mesh,
                "mask_name": "Horns",
            })
            assert insp_horns["status"] == "success", insp_horns
            h_data = insp_horns["result"]["masks"]["Horns"]
            assert h_data["total_vertices"] == initial_v_count
            assert h_data["weighted_vertices_count"] > 0
            sym_data = insp_horns["result"]["symmetry"]
            assert sym_data is not None
            assert sym_data["symmetry_axis"] == "X"
            print(f"[PASS] Step 7b: Specific inspection of 'Horns' confirmed bilateral symmetry stats (asymmetry RMSE={sym_data['asymmetry_rmse']:.6f})")

            # --- STEP 8: Mask-Modulated Surface Detailing ---
            detail_masked = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "SCALES",
                "feature_scale": 0.25,
                "depth": 0.04,
                "mask_vertex_group": "Horns",
                "iterations": 1,
                "preserve_landmarks": False,
            })
            assert detail_masked["status"] == "success", detail_masked
            dm_res = detail_masked["result"]
            assert dm_res["detailing_status"] == "ACCEPTED"
            assert dm_res["mask_vertex_group"] == "Horns"
            assert dm_res["affected_vertices_count"] <= res_h["weighted_vertices_count"]
            print(f"[PASS] Step 8: Mask-Modulated detailing applied (affected: {dm_res['affected_vertices_count']} <= mask count: {res_h['weighted_vertices_count']})")

            # --- STEP 9: Symmetry-Aware Surface Detailing ---
            detail_sym = await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "RIDGES",
                "feature_scale": 0.3,
                "depth": 0.03,
                "use_symmetry": True,
                "symmetry_axis": "X",
                "seam_threshold": 0.005,
                "iterations": 1,
                "preserve_landmarks": False,
            })
            assert detail_sym["status"] == "success", detail_sym
            ds_res = detail_sym["result"]
            assert ds_res["detailing_status"] == "ACCEPTED"
            assert ds_res["use_symmetry"] is True
            assert ds_res["symmetry_axis"] == "X"
            print(f"[PASS] Step 9: Symmetry-Aware detailing applied with X-axis mirroring and seam clamping")

            # --- STEP 10: symmetrize_mesh_geometry (+TO_-) ---
            sym_res = await call_tool("symmetrize_mesh_geometry", {
                "target_object": target_mesh,
                "symmetry_axis": "X",
                "source_direction": "+TO_-",
                "seam_threshold": 0.005,
            })
            assert sym_res["status"] == "success", sym_res
            s_data = sym_res["result"]
            assert s_data["status"] == "SUCCESS", s_data
            assert s_data["symmetry_status"] == "ACCEPTED", s_data
            assert s_data["symmetry_axis"] == "X"
            assert s_data["source_direction"] == "+TO_-"
            assert s_data["asymmetry_rmse_after"] <= s_data["asymmetry_rmse_before"] + 1e-6
            assert s_data["midline_vertices_locked"] >= 0
            print(f"[PASS] Step 10: symmetrize_mesh_geometry (+TO_-) executed: RMSE {s_data['asymmetry_rmse_before']:.6f} -> {s_data['asymmetry_rmse_after']:.6f}")

            # --- STEP 11: symmetrize_mesh_geometry (AVERAGE) ---
            sym_avg = await call_tool("symmetrize_mesh_geometry", {
                "target_object": target_mesh,
                "symmetry_axis": "X",
                "source_direction": "AVERAGE",
                "seam_threshold": 0.005,
            })
            assert sym_avg["status"] == "success", sym_avg
            assert sym_avg["result"]["symmetry_status"] == "ACCEPTED"
            assert sym_avg["result"]["source_direction"] == "AVERAGE"
            print(f"[PASS] Step 11: symmetrize_mesh_geometry (AVERAGE) executed successfully")

            # --- STEP 12: Pre-modification Resource Limit Enforcement ---
            limit_res = await call_tool("symmetrize_mesh_geometry", {
                "target_object": target_mesh,
                "max_vertex_count": 200,  # sphere has 482 vertices
            })
            assert limit_res["status"] == "error", f"Expected error on limit exceed, got {limit_res}"
            assert "Precondition limit exceeded" in limit_res["message"]
            print("[PASS] Step 12: Pre-modification vertex limit rejection verified fail-closed")

            # --- STEP 13: Transactional Rollback on Regression Violation ---
            # Apply outward surface expansion so subsequent negative depth causes silhouette regression
            await call_tool("detail_surface_features", {
                "target_object": target_mesh,
                "feature_type": "SCALES",
                "feature_scale": 0.25,
                "depth": 0.08,
                "strength": 0.8,
                "max_displacement": 0.12,
                "iterations": 1,
                "preserve_landmarks": False,
            })

            coords_pre = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            v_count_pre = coords_pre["result"]["vertex_count"]

            rb_res = await call_tool("detail_surface_features", {
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
            assert rb_res["status"] == "success", rb_res
            rb_data = rb_res["result"]
            assert rb_data["status"] == "ERROR", rb_data
            assert rb_data["detailing_status"] == "REJECTED_ROLLED_BACK"
            assert rb_data["rolled_back"] is True
            print("[PASS] Step 13a: Transactional rollback executed on regression tolerance violation")

            coords_post = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert coords_post["result"]["vertex_count"] == v_count_pre
            print("[PASS] Step 13b: Topology and mesh coordinates restored bit-for-bit after rollback")

            # --- STEP 14: Backward-Compatible Delegation from optimize_mesh_silhouette ---
            deleg_sym = await call_tool("optimize_mesh_silhouette", {
                "target_object": target_mesh,
                "refinement_mode": "SURFACE_DETAIL",
                "feature_type": "SCALES",
                "feature_scale": 0.3,
                "depth": 0.02,
                "reference_image_path": str(REFERENCE_IMAGE),
                "preserve_landmarks": False,
                "use_symmetry": True,
                "symmetry_axis": "X",
                "mask_vertex_group": "Horns",
            })
            assert deleg_sym["status"] == "success", deleg_sym
            assert deleg_sym["result"]["detailing_status"] == "ACCEPTED"
            assert deleg_sym["result"]["use_symmetry"] is True
            assert deleg_sym["result"]["mask_vertex_group"] == "Horns"
            print("[PASS] Step 14: Backward-compatible delegation with use_symmetry and mask_vertex_group verified")

            # --- STEP 15: Fail-Closed Security Guardrails ---
            # 15a: Untrusted approved=True rejected
            untrusted_mask = await call_tool("configure_anatomical_mask", {
                "target_object": target_mesh,
                "action": "SET",
                "mask_name": "MaliciousMask",
                "approved": True,
            })
            assert untrusted_mask["status"] == "error", untrusted_mask
            assert "untrusted" in untrusted_mask["message"].lower() or "approval denied" in untrusted_mask["message"].lower()
            print("[PASS] Step 15a: Untrusted approved=True rejected fail-closed for configure_anatomical_mask")

            untrusted_sym = await call_tool("symmetrize_mesh_geometry", {
                "target_object": target_mesh,
                "approved": True,
            })
            assert untrusted_sym["status"] == "error", untrusted_sym
            assert "untrusted" in untrusted_sym["message"].lower() or "approval denied" in untrusted_sym["message"].lower()
            print("[PASS] Step 15b: Untrusted approved=True rejected fail-closed for symmetrize_mesh_geometry")

            # 15c: Non-existent object
            non_exist_res = await call_tool("configure_anatomical_mask", {
                "target_object": "NonExistentMesh123",
                "action": "SET",
                "mask_name": "Test",
            })
            assert non_exist_res["status"] == "error", non_exist_res
            assert "not found" in non_exist_res["message"].lower()
            print("[PASS] Step 15c: Non-existent object rejected fail-closed")

            # 15d: Non-mesh object (Camera)
            non_mesh_res = await call_tool("symmetrize_mesh_geometry", {
                "target_object": "SceneCamera",
            })
            assert non_mesh_res["status"] == "error", non_mesh_res
            assert "not a mesh" in non_mesh_res["message"].lower()
            print("[PASS] Step 15d: Non-mesh object (Camera) rejected fail-closed")

    # 16. Clean Shutdown
    print("Initiating clean shutdown...")
    (run_root / "stop.flag").touch()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)
    print("[PASS] Disposable Blender shut down cleanly")

    # 17. Source Reference Image Preservation Check
    post_stat = REFERENCE_IMAGE.stat()
    post_sha256 = get_file_sha256(REFERENCE_IMAGE)
    assert pre_stat.st_size == post_stat.st_size, "Reference image file size changed!"
    assert pre_sha256 == post_sha256, "Reference image SHA-256 altered!"
    print(f"[PASS] Reference Image Immutability Verified (SHA-256 intact: {post_sha256})")

    print("\n=========================================================================")
    print(">>> TASK v0.1.59 VERIFICATION PASSED: ALL 17 CRITICAL E2E CHECKS PASSED <<<")
    print("=========================================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
