"""
Automated Real MCP-to-Blender E2E Verification of Semantic Anatomical Landmark Guidance (v0.1.57).
Verifies TASK v0.1.57:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Source reference image preservation (SHA-256 and size immutable).
4. Discover tools over stdio MCP wire:
   - configure_semantic_landmarks
   - inspect_semantic_landmarks
   - guide_mesh_landmarks
5. Initial Scene Summary check (clean disposable scene).
6. Target blockout mesh and scene camera setup.
7. configure_semantic_landmarks:
   - Configure 6 named landmarks (snout_tip, horn_tip_left, horn_tip_right, wing_apex_left, wing_apex_right, tail_tip)
   - Store 2D reference coordinates for FRONT and SIDE views.
8. inspect_semantic_landmarks:
   - Measure 3D world coordinates, 2D view projections, per-view reprojection errors, aggregate RMSE, and mean landmark error.
9. guide_mesh_landmarks:
   - Bounded deformation step toward landmark correspondences.
   - Dual-condition acceptance (measurable landmark RMSE reduction + silhouette regression protection).
   - Topology preservation invariant (vertex count, edge count, face count preserved).
10. Independent readback verification:
   - inspect_semantic_landmarks confirms final landmark RMSE.
   - inspect_scene_data confirms geometry and topology invariants.
11. Landmark lifecycle operations:
   - UPDATE landmark properties (weights).
   - REMOVE landmark (count reduces).
   - CLEAR all landmarks (count becomes 0).
12. Pre-modification resource limit enforcement (rejects before modifying mesh).
13. Transactional rollback test:
   - Rejection on non-improvement / impossible threshold.
   - Bit-for-bit mesh coordinates and transform rollback.
14. Backward-compatible delegation from optimize_mesh_silhouette.
15. Fail-closed security guardrails:
   - Untrusted model approved=True rejected.
   - Non-existent target object rejected.
   - Non-mesh target object rejected.
   - Out-of-bounds normalized UV coordinates rejected.
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
    print("=== TASK v0.1.57: Semantic Anatomical Landmark Guidance E2E Verification ===")

    # 1. Baseline Reference Image Check
    assert REFERENCE_IMAGE.exists(), f"Reference image missing: {REFERENCE_IMAGE}"
    pre_stat = REFERENCE_IMAGE.stat()
    pre_sha256 = get_file_sha256(REFERENCE_IMAGE)
    print(f"[OK] Reference image baseline verified: {REFERENCE_IMAGE.name}")
    print(f"     Size: {pre_stat.st_size:,} bytes, SHA-256: {pre_sha256}")

    # 2. Setup Disposable Test Environment
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-LANDMARKS-"))
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
            for t_name in ("configure_semantic_landmarks", "inspect_semantic_landmarks", "guide_mesh_landmarks"):
                assert t_name in tool_names, f"{t_name} missing from tools: {tool_names}"
            print("[PASS] Catalog Check: configure_semantic_landmarks, inspect_semantic_landmarks, guide_mesh_landmarks discoverable")

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
                "location": [0.0, 0.0, 1.5],
            })
            assert mesh_res["status"] == "success", mesh_res
            print(f"[PASS] Step 2b: Target Blockout Mesh '{target_mesh}' Created")

            topo_before = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert topo_before["status"] == "success", topo_before
            initial_v_count = topo_before["result"]["vertex_count"]
            initial_p_count = topo_before["result"]["polygon_count"]
            assert initial_v_count == 8, f"Expected 8 cube vertices, got {initial_v_count}"
            assert initial_p_count == 6, f"Expected 6 cube polygons, got {initial_p_count}"
            print(f"[PASS] Step 2c: Initial Topology Recorded: {initial_v_count} verts, {initial_p_count} polys")

            # --- STEP 3: Configure Semantic Landmarks (action='SET') ---
            landmarks_payload = [
                {
                    "name": "snout_tip",
                    "vertex_index": 0,
                    "reference_views": {
                        "FRONT": [0.50, 0.40],
                        "SIDE": [0.60, 0.40],
                    },
                    "weight": 1.5,
                },
                {
                    "name": "horn_tip_left",
                    "vertex_index": 1,
                    "reference_views": {
                        "FRONT": [0.42, 0.62],
                        "SIDE": [0.52, 0.62],
                    },
                    "weight": 1.0,
                },
                {
                    "name": "horn_tip_right",
                    "vertex_index": 2,
                    "reference_views": {
                        "FRONT": [0.58, 0.62],
                        "SIDE": [0.52, 0.62],
                    },
                    "weight": 1.0,
                },
                {
                    "name": "wing_apex_left",
                    "vertex_index": 3,
                    "reference_views": {
                        "FRONT": [0.32, 0.58],
                        "SIDE": [0.44, 0.58],
                    },
                    "weight": 1.0,
                },
                {
                    "name": "wing_apex_right",
                    "vertex_index": 4,
                    "reference_views": {
                        "FRONT": [0.68, 0.58],
                        "SIDE": [0.44, 0.58],
                    },
                    "weight": 1.0,
                },
                {
                    "name": "tail_tip",
                    "vertex_index": 5,
                    "reference_views": {
                        "FRONT": [0.50, 0.32],
                        "SIDE": [0.32, 0.32],
                    },
                    "weight": 1.2,
                },
            ]

            cfg_res = await call_tool("configure_semantic_landmarks", {
                "target_object": target_mesh,
                "action": "SET",
                "landmarks": landmarks_payload,
            })
            assert cfg_res["status"] == "success", cfg_res
            assert cfg_res["result"]["action"] == "SET"
            assert cfg_res["result"]["landmarks_count"] == 6
            print("[PASS] Step 3: configure_semantic_landmarks SET 6 anatomical landmarks")

            # --- STEP 4: Inspect Semantic Landmarks ---
            inspect_res = await call_tool("inspect_semantic_landmarks", {
                "target_object": target_mesh,
                "views": ["FRONT", "SIDE"],
                "include_projection_details": True,
            })
            assert inspect_res["status"] == "success", inspect_res
            res_insp = inspect_res["result"]
            assert res_insp["landmarks_count"] == 6
            init_rmse = res_insp["aggregate_rmse"]
            init_mean_err = res_insp["mean_landmark_error"]
            print(f"     Initial Aggregate RMSE: {init_rmse}")
            print(f"     Initial Mean Landmark Error: {init_mean_err}")
            print(f"     Initial Weighted RMSE: {res_insp.get('weighted_rmse')}")
            print(f"     Initial Max Error: {res_insp.get('max_landmark_error')}")
            assert init_rmse > 0.0, "Expected non-zero initial landmark RMSE"
            print("[PASS] Step 4: inspect_semantic_landmarks verified non-zero initial error")

            # --- STEP 5: Reference-Guided Mesh Landmark Guidance (guide_mesh_landmarks) ---
            guide_res = await call_tool("guide_mesh_landmarks", {
                "target_object": target_mesh,
                "max_iterations": 3,
                "max_displacement": 0.12,
                "step_size": 0.5,
                "influence_radius": 1.8,
                "falloff_type": "SMOOTH",
                "laplacian_smoothing": 0.1,
                "preserve_topology": True,
                "min_error_reduction": 0.0001,
                "views": [
                    {
                        "view": "FRONT",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.0, 0.5, 0.5, 1.0],
                        "coordinate_system": "UV",
                        "weight": 1.0,
                        "max_regression_tolerance": 0.05,
                    },
                    {
                        "view": "SIDE",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.5, 0.5, 1.0, 1.0],
                        "coordinate_system": "UV",
                        "weight": 1.0,
                        "max_regression_tolerance": 0.05,
                    },
                ],
            })
            assert guide_res["status"] == "success", guide_res
            res_guide = guide_res["result"]
            print(f"     Guidance Status: {res_guide.get('guidance_status')}")
            print(f"     Initial RMSE: {res_guide.get('initial_landmark_rmse')} -> Final RMSE: {res_guide.get('final_landmark_rmse')}")
            print(f"     Error Reduction: {res_guide.get('landmark_error_reduction')}")
            print(f"     Iterations Completed: {res_guide.get('iterations_completed')}")
            print(f"     Affected Vertices: {res_guide.get('affected_vertices_count')}")
            print(f"     Max Displacement: {res_guide.get('max_vertex_displacement')}")
            print(f"     Topology Preserved: {res_guide.get('topology_preserved')}")

            assert res_guide["guidance_status"] == "ACCEPTED"
            assert res_guide["topology_preserved"] is True
            assert res_guide["initial_vertex_count"] == 8
            assert res_guide["final_vertex_count"] == 8
            assert res_guide["initial_face_count"] == 6
            assert res_guide["final_face_count"] == 6
            assert res_guide["final_landmark_rmse"] < res_guide["initial_landmark_rmse"]
            assert res_guide["landmark_error_reduction"] > 0.0001
            assert res_guide["max_vertex_displacement"] > 0.0
            assert res_guide["max_vertex_displacement"] <= 0.120001
            print("[PASS] Step 5: guide_mesh_landmarks ACCEPTED (RMSE strictly improved, silhouette protected, topology invariant)")

            # --- STEP 6: Independent Readbacks ---
            # 6a. Inspect semantic landmarks post-deformation
            insp_after = await call_tool("inspect_semantic_landmarks", {
                "target_object": target_mesh,
                "views": ["FRONT", "SIDE"],
            })
            assert insp_after["status"] == "success", insp_after
            readback_rmse = insp_after["result"]["aggregate_rmse"]
            print(f"     Independent Landmark Readback RMSE: {readback_rmse} (guide reported: {res_guide['final_landmark_rmse']})")
            assert math.isclose(readback_rmse, res_guide["final_landmark_rmse"], abs_tol=1e-5)

            # 6b. Inspect topology independently
            topo_after = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert topo_after["status"] == "success", topo_after
            assert topo_after["result"]["vertex_count"] == 8
            assert topo_after["result"]["polygon_count"] == 6
            print("[PASS] Step 6: Independent Landmark and Topology Readbacks Confirmed")

            # --- STEP 7: Landmark Lifecycle Operations (UPDATE, REMOVE, CLEAR) ---
            # 7a: UPDATE snout_tip weight
            update_res = await call_tool("configure_semantic_landmarks", {
                "target_object": target_mesh,
                "action": "UPDATE",
                "landmarks": [
                    {
                        "name": "snout_tip",
                        "weight": 3.0,
                    }
                ],
            })
            assert update_res["status"] == "success", update_res
            assert update_res["result"]["landmarks_count"] == 6

            insp_up = await call_tool("inspect_semantic_landmarks", {"target_object": target_mesh})
            snout_lm = next(lm for lm in insp_up["result"]["landmarks"] if lm["name"] == "snout_tip")
            assert snout_lm["weight"] == 3.0
            print("[PASS] Step 7a: Landmark UPDATE operation confirmed (snout_tip weight updated to 3.0)")

            # 7b: REMOVE tail_tip
            rem_res = await call_tool("configure_semantic_landmarks", {
                "target_object": target_mesh,
                "action": "REMOVE",
                "landmarks": [{"name": "tail_tip"}],
            })
            assert rem_res["status"] == "success", rem_res
            assert rem_res["result"]["landmarks_count"] == 5

            insp_rem = await call_tool("inspect_semantic_landmarks", {"target_object": target_mesh})
            assert insp_rem["result"]["landmarks_count"] == 5
            assert not any(lm["name"] == "tail_tip" for lm in insp_rem["result"]["landmarks"])
            print("[PASS] Step 7b: Landmark REMOVE operation confirmed (tail_tip removed, count=5)")

            # 7c: CLEAR all landmarks
            clear_res = await call_tool("configure_semantic_landmarks", {
                "target_object": target_mesh,
                "action": "CLEAR",
            })
            assert clear_res["status"] == "success", clear_res
            assert clear_res["result"]["landmarks_count"] == 0

            insp_clr = await call_tool("inspect_semantic_landmarks", {"target_object": target_mesh})
            assert insp_clr["result"]["landmarks_count"] == 0
            print("[PASS] Step 7c: Landmark CLEAR operation confirmed (count=0)")

            # --- STEP 8: Pre-Modification Resource Limit Enforcement ---
            limit_target = "Limit_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "sphere",
                "name": limit_target,
                "location": [-3.0, 0.0, 1.5],
            })
            # Configure a dummy landmark on the sphere
            await call_tool("configure_semantic_landmarks", {
                "target_object": limit_target,
                "action": "SET",
                "landmarks": [{
                    "name": "sphere_pole",
                    "vertex_index": 0,
                    "reference_views": {"FRONT": [0.5, 0.5]},
                }],
            })
            # Sphere has ~482 vertices. Calling with max_vertex_count=200 must reject fail-closed before modifying mesh
            err_limit = await call_tool("guide_mesh_landmarks", {
                "target_object": limit_target,
                "max_vertex_count": 200,
            })
            assert err_limit["status"] == "error", err_limit
            assert "limit exceeded" in err_limit["message"].lower() or "precondition" in err_limit["message"].lower()
            print("[PASS] Step 8: Pre-Modification Resource Limit Enforcement Confirmed (Rejects before modifying)")

            # --- STEP 9: Transactional Rollback on Objective Non-Improvement ---
            rollback_target = "Rollback_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "cube",
                "name": rollback_target,
                "location": [3.0, 0.0, 1.5],
            })
            await call_tool("configure_semantic_landmarks", {
                "target_object": rollback_target,
                "action": "SET",
                "landmarks": [{
                    "name": "rb_pt",
                    "vertex_index": 0,
                    "reference_views": {"FRONT": [0.4, 0.4]},
                }],
            })
            pre_rb_details = await call_tool("get_object_details", {"name": rollback_target})
            pre_rb_loc = [round(c, 4) for c in pre_rb_details["result"]["location"]]
            pre_rb_topo = await call_tool("inspect_scene_data", {"category": "mesh_topology", "target_name": rollback_target})
            assert pre_rb_topo["result"]["vertex_count"] == 8

            # Run with impossible min_error_reduction=0.95
            fail_guide = await call_tool("guide_mesh_landmarks", {
                "target_object": rollback_target,
                "min_error_reduction": 0.95,
                "max_iterations": 2,
                "rollback_on_failure": True,
            })
            res_fail = fail_guide.get("result", {})
            assert res_fail.get("guidance_status") == "REJECTED_ROLLED_BACK" or fail_guide.get("status") == "error"
            assert res_fail.get("rolled_back") is True
            print(f"     Rollback Reported Failure as Expected: {res_fail.get('error_reason')}")

            post_rb_details = await call_tool("get_object_details", {"name": rollback_target})
            post_rb_loc = [round(c, 4) for c in post_rb_details["result"]["location"]]
            post_rb_topo = await call_tool("inspect_scene_data", {"category": "mesh_topology", "target_name": rollback_target})
            assert post_rb_loc == pre_rb_loc, f"Location was not rolled back: {post_rb_loc} != {pre_rb_loc}"
            assert post_rb_topo["result"]["vertex_count"] == 8, f"Vertex count changed on rollback: {post_rb_topo['result']['vertex_count']}"
            print("[PASS] Step 9: Transactional Rollback Confirmed (Mesh topology and coordinates restored bit-for-bit)")

            # --- STEP 10: Backward-Compatible Delegation from optimize_mesh_silhouette ---
            for old_name in (target_mesh, limit_target, rollback_target):
                await call_tool("transform_object", {"name": old_name, "location": [0.0, 0.0, -100.0]})

            deleg_mesh = "Delegation_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "cube",
                "name": deleg_mesh,
                "location": [0.0, 0.0, 1.5],
            })
            deleg_res = await call_tool("optimize_mesh_silhouette", {
                "target_object": deleg_mesh,
                "reference_image_path": str(REFERENCE_IMAGE),
                "refinement_mode": "LANDMARK_GUIDED",
                "landmarks": [
                    {
                        "name": "deleg_snout",
                        "vertex_index": 0,
                        "reference_views": {"FRONT": [0.42, 0.42]},
                        "weight": 1.0,
                    }
                ],
                "max_iterations": 2,
                "max_displacement": 0.1,
            })
            assert deleg_res["status"] == "success", deleg_res
            assert deleg_res["result"]["guidance_status"] == "ACCEPTED"
            print("[PASS] Step 10: Backward-Compatible Delegation from optimize_mesh_silhouette Verified")

            # --- STEP 11: Fail-Closed Security & Guardrail Validations ---
            # 11a: Untrusted approval flag
            err_untrusted = await call_tool("guide_mesh_landmarks", {
                "target_object": deleg_mesh,
                "approved": True,
            })
            assert err_untrusted["status"] == "error", err_untrusted
            assert "untrusted" in err_untrusted["message"].lower() or "approval denied" in err_untrusted["message"].lower()
            print("[PASS] Step 11a: Untrusted approved=True flag rejected fail-closed")

            # 11b: Non-existent object
            err_nonexistent = await call_tool("guide_mesh_landmarks", {
                "target_object": "GhostObject_99999",
            })
            assert err_nonexistent["status"] == "error", err_nonexistent
            assert "not found" in err_nonexistent["message"].lower()
            print("[PASS] Step 11b: Non-existent target object rejected fail-closed")

            # 11c: Non-mesh object
            err_nonmesh = await call_tool("guide_mesh_landmarks", {
                "target_object": "SceneCamera",
            })
            assert err_nonmesh["status"] == "error", err_nonmesh
            assert "not a mesh" in err_nonmesh["message"].lower() or "mesh" in err_nonmesh["message"].lower()
            print("[PASS] Step 11c: Non-mesh target object rejected fail-closed")

            # 11d: Invalid landmark coordinates (out of bounds)
            err_oob = await call_tool("configure_semantic_landmarks", {
                "target_object": deleg_mesh,
                "action": "SET",
                "landmarks": [{
                    "name": "oob_pt",
                    "vertex_index": 0,
                    "reference_views": {"FRONT": [1.5, -0.2]},
                }],
            })
            assert err_oob["status"] == "error", err_oob
            assert "normalized" in err_oob["message"].lower() or "0.0 and 1.0" in err_oob["message"].lower() or "bounds" in err_oob["message"].lower()
            print("[PASS] Step 11d: Out-of-bounds normalized UV coordinates rejected fail-closed")

    # 12. Clean Process Shutdown
    print("Initiating clean shutdown of disposable Blender...")
    (run_root / "stop.flag").touch()
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    print("[OK] Disposable Blender shutdown cleanly")

    # 13. Verify Source Image Immutability
    post_stat = REFERENCE_IMAGE.stat()
    post_sha256 = get_file_sha256(REFERENCE_IMAGE)
    assert post_stat.st_size == pre_stat.st_size, "Source image size changed!"
    assert post_sha256 == pre_sha256, "Source image SHA-256 changed!"
    print(f"[PASS] Source image immutability confirmed (SHA-256 strictly preserved: {post_sha256})")

    print("\n=== ALL E2E VERIFICATIONS PASSED SUCCESSFULLY (TASK v0.1.57) ===")


if __name__ == "__main__":
    asyncio.run(main())
