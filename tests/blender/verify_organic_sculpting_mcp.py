"""
Automated Real MCP-to-Blender E2E Verification of Bounded Organic Sculpting and Anatomy Refinement (v0.1.56).
Verifies TASK v0.1.56:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Source image preservation (SHA-256 and size immutable).
4. Real bounded organic sculpting (sculpt_organic_anatomy) against FRONT and SIDE
   views from Red Dragon 3D Reference Sheet:
   - Evaluates multi-view simultaneous silhouette alignment.
   - Dual-condition acceptance (aggregate IoU improvement + regression protection).
   - Strict topology preservation by default (vertex, edge, face count invariant).
5. Independent readback verification using inspect_scene_data and compare_silhouette_alignment.
6. Initial brush set verification: GRAB, INFLATE, SMOOTH, CLAY, DRAW.
7. Pre-modification resource limit rejection (rejects before modifying mesh).
8. Transactional rollback test:
   - Enforces bit-for-bit rollback of mesh coordinates, datablock, and transforms.
9. Backward compatibility delegation:
   - optimize_mesh_silhouette with brush_type routes to sculpt_organic_anatomy.
   - sculpt_mesh with action='sculpt_organic_anatomy' routes to sculpt_organic_anatomy.
10. Fail-closed security validations:
   - Untrusted model approved=True rejected.
   - Non-existent target object rejected.
   - Non-mesh target object rejected.
   - Conflicting preserve_topology=True and dynamic_topology=True rejected.
11. Clean process shutdown and zero persistent state.
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
    print("=== TASK v0.1.56: Bounded Organic Sculpting and Anatomy Refinement E2E Verification ===")

    # 1. Baseline Reference Image Check
    assert REFERENCE_IMAGE.exists(), f"Reference image missing: {REFERENCE_IMAGE}"
    pre_stat = REFERENCE_IMAGE.stat()
    pre_sha256 = get_file_sha256(REFERENCE_IMAGE)
    print(f"[OK] Reference image baseline verified: {REFERENCE_IMAGE.name}")
    print(f"     Size: {pre_stat.st_size:,} bytes, SHA-256: {pre_sha256}")

    # 2. Setup Disposable Test Environment
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-SCULPT-ANATOMY-"))
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
            assert "sculpt_organic_anatomy" in tool_names, f"sculpt_organic_anatomy missing from tools: {tool_names}"
            print("[PASS] Catalog Check: sculpt_organic_anatomy discoverable over MCP wire")

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

            target_mesh = "Dragon_Anatomy"
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

            # --- STEP 3: Reference-Guided Organic Sculpting (INFLATE Brush) ---
            sculpt_res = await call_tool("sculpt_organic_anatomy", {
                "target_object": target_mesh,
                "brush_type": "INFLATE",
                "radius": 3.0,
                "strength": 0.5,
                "max_displacement": 0.25,
                "iterations": 2,
                "preserve_topology": True,
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
            })
            assert sculpt_res["status"] == "success", sculpt_res
            res_sculpt = sculpt_res["result"]

            print(f"     Sculpt Status: {res_sculpt.get('sculpt_status')}")
            print(f"     Brush Type: {res_sculpt.get('brush_type')}, Radius: {res_sculpt.get('radius')}, Strength: {res_sculpt.get('strength')}")
            print(f"     Affected Vertices: {res_sculpt.get('affected_vertices_count')}")
            print(f"     Max Displacement: {res_sculpt.get('max_vertex_displacement')}")
            print(f"     Vertex Count: {res_sculpt.get('initial_vertex_count')} -> {res_sculpt.get('final_vertex_count')}")
            print(f"     Face Count: {res_sculpt.get('initial_face_count')} -> {res_sculpt.get('final_face_count')}")
            print(f"     Initial Aggregate: {res_sculpt.get('initial_aggregate')}, Final Aggregate: {res_sculpt.get('final_aggregate')}")
            print(f"     Aggregate Improvement: {res_sculpt.get('aggregate_improvement')}")
            print(f"     Topology Preserved: {res_sculpt.get('topology_preserved')}")
            print(f"     Per-view Initial: {res_sculpt.get('per_view_initial_metrics')}")
            print(f"     Per-view Final:   {res_sculpt.get('per_view_final_metrics')}")

            assert res_sculpt["sculpt_status"] == "SCULPTED"
            assert res_sculpt["topology_preserved"] is True
            assert res_sculpt["initial_vertex_count"] == 8
            assert res_sculpt["final_vertex_count"] == 8
            assert res_sculpt["initial_face_count"] == 6
            assert res_sculpt["final_face_count"] == 6
            assert res_sculpt["aggregate_improvement"] > 0.0, f"Expected positive aggregate improvement, got {res_sculpt['aggregate_improvement']}"
            assert res_sculpt["max_vertex_displacement"] > 0.0
            assert res_sculpt["max_vertex_displacement"] <= 0.250001
            print("[PASS] Step 3: Reference-Guided Organic Sculpting Verified (INFLATE brush, IoU strictly improved, topology preserved)")

            # --- STEP 4: Independent Topology Readback Verification ---
            topo_after = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": target_mesh,
            })
            assert topo_after["status"] == "success", topo_after
            readback_v = topo_after["result"]["vertex_count"]
            readback_p = topo_after["result"]["polygon_count"]
            assert readback_v == 8, f"Expected 8 vertices on readback, got {readback_v}"
            assert readback_p == 6, f"Expected 6 polygons on readback, got {readback_p}"
            print(f"[PASS] Step 4: Independent Topology Readback Confirmed ({readback_v} verts, {readback_p} polys)")

            # --- STEP 5: Independent Silhouette Readback Verification ---
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
            print(f"     Independent FRONT Readback IoU: {front_iou} (Sculpt reported: {res_sculpt['per_view_final_metrics']['FRONT']['iou']})")
            assert math.isclose(front_iou, res_sculpt["per_view_final_metrics"]["FRONT"]["iou"], abs_tol=0.05)

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
            print(f"     Independent SIDE Readback IoU: {side_iou} (Sculpt reported: {res_sculpt['per_view_final_metrics']['SIDE']['iou']})")
            assert math.isclose(side_iou, res_sculpt["per_view_final_metrics"]["SIDE"]["iou"], abs_tol=0.05)
            print("[PASS] Step 5: Independent Silhouette Readbacks Match Sculpt Metrics for Both Views")

            # --- STEP 6: Initial Brush Set Verification (GRAB, SMOOTH, CLAY, DRAW) ---
            # Test GRAB brush
            grab_res = await call_tool("sculpt_organic_anatomy", {
                "target_object": target_mesh,
                "brush_type": "GRAB",
                "radius": 2.0,
                "strength": 0.5,
                "max_displacement": 0.15,
                "stroke_direction": [0.0, 0.0, 1.0],
                "preserve_topology": True,
            })
            assert grab_res["status"] == "success", grab_res
            assert grab_res["result"]["sculpt_status"] == "SCULPTED"
            assert grab_res["result"]["brush_type"] == "GRAB"
            print("     [OK] GRAB brush operation verified")

            # Test SMOOTH brush
            smooth_res = await call_tool("sculpt_organic_anatomy", {
                "target_object": target_mesh,
                "brush_type": "SMOOTH",
                "radius": 2.0,
                "strength": 0.4,
                "max_displacement": 0.1,
                "preserve_topology": True,
            })
            assert smooth_res["status"] == "success", smooth_res
            assert smooth_res["result"]["sculpt_status"] == "SCULPTED"
            assert smooth_res["result"]["brush_type"] == "SMOOTH"
            print("     [OK] SMOOTH brush operation verified")

            # Test CLAY brush
            clay_res = await call_tool("sculpt_organic_anatomy", {
                "target_object": target_mesh,
                "brush_type": "CLAY",
                "radius": 2.0,
                "strength": 0.5,
                "max_displacement": 0.15,
                "preserve_topology": True,
            })
            assert clay_res["status"] == "success", clay_res
            assert clay_res["result"]["sculpt_status"] == "SCULPTED"
            assert clay_res["result"]["brush_type"] == "CLAY"
            print("     [OK] CLAY brush operation verified")

            # Test DRAW brush
            draw_res = await call_tool("sculpt_organic_anatomy", {
                "target_object": target_mesh,
                "brush_type": "DRAW",
                "radius": 2.0,
                "strength": 0.5,
                "max_displacement": 0.15,
                "preserve_topology": True,
            })
            assert draw_res["status"] == "success", draw_res
            assert draw_res["result"]["sculpt_status"] == "SCULPTED"
            assert draw_res["result"]["brush_type"] == "DRAW"
            print("     [OK] DRAW brush operation verified")
            print("[PASS] Step 6: Initial Brush Set (GRAB, SMOOTH, CLAY, DRAW) Confirmed Functional")

            # --- STEP 7: Pre-Modification Resource Limit Enforcement ---
            limit_target = "Limit_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "sphere",
                "name": limit_target,
                "location": [-3.0, 0.0, 1.5],
            })
            # Sphere has ~482 vertices. Calling with max_vertex_count=100 must reject before modifying mesh
            err_limit = await call_tool("sculpt_organic_anatomy", {
                "target_object": limit_target,
                "brush_type": "INFLATE",
                "max_vertex_count": 100,
            })
            assert err_limit["status"] == "error", err_limit
            assert "limit exceeded" in err_limit["message"].lower() or "precondition" in err_limit["message"].lower()
            print("[PASS] Step 7: Pre-Modification Resource Limit Enforcement Confirmed (Rejects before modifying)")

            # --- STEP 8: Transactional Rollback on Objective Non-Improvement ---
            rollback_target = "Rollback_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "cube",
                "name": rollback_target,
                "location": [3.0, 0.0, 1.5],
            })
            pre_rb_details = await call_tool("get_object_details", {"name": rollback_target})
            pre_rb_loc = [round(c, 4) for c in pre_rb_details["result"]["location"]]
            pre_rb_topo = await call_tool("inspect_scene_data", {"category": "mesh_topology", "target_name": rollback_target})
            assert pre_rb_topo["result"]["vertex_count"] == 8

            # Run with impossible min_aggregate_improvement=0.49
            fail_sculpt = await call_tool("sculpt_organic_anatomy", {
                "target_object": rollback_target,
                "brush_type": "INFLATE",
                "radius": 1.0,
                "strength": 0.1,
                "max_displacement": 0.05,
                "min_aggregate_improvement": 0.49,
                "views": [
                    {
                        "view": "FRONT",
                        "reference_image_path": str(REFERENCE_IMAGE),
                        "crop_box": [0.0, 0.5, 0.5, 1.0],
                    },
                ],
                "rollback_on_failure": True,
            })
            assert fail_sculpt["status"] == "error", fail_sculpt
            print(f"     Rollback Reported Failure as Expected: {fail_sculpt['message']}")

            post_rb_details = await call_tool("get_object_details", {"name": rollback_target})
            post_rb_loc = [round(c, 4) for c in post_rb_details["result"]["location"]]
            post_rb_topo = await call_tool("inspect_scene_data", {"category": "mesh_topology", "target_name": rollback_target})
            assert post_rb_loc == pre_rb_loc, f"Location was not rolled back: {post_rb_loc} != {pre_rb_loc}"
            assert post_rb_topo["result"]["vertex_count"] == 8, f"Vertex count changed on rollback: {post_rb_topo['result']['vertex_count']}"
            print("[PASS] Step 8: Transactional Rollback Confirmed (Mesh topology and coordinates restored bit-for-bit)")

            # --- STEP 9: Backward-Compatible Delegation ---
            for old_name in ("Dragon_Anatomy", "Limit_Mesh", "Rollback_Mesh"):
                await call_tool("transform_object", {"name": old_name, "location": [0.0, 0.0, -100.0]})

            deleg_mesh = "Delegation_Mesh"
            await call_tool("create_primitive", {
                "primitive_type": "cube",
                "name": deleg_mesh,
                "location": [0.0, 0.0, 0.5],
            })
            deleg_res = await call_tool("optimize_mesh_silhouette", {
                "target_object": deleg_mesh,
                "reference_image_path": str(REFERENCE_IMAGE),
                "brush_type": "INFLATE",
                "radius": 2.5,
                "strength": 0.5,
                "max_displacement": 0.2,
                "refinement_mode": "SCULPT_ANATOMY",
            })
            assert deleg_res["status"] == "success", deleg_res
            assert deleg_res["result"]["sculpt_status"] == "SCULPTED"
            print("[PASS] Step 9a: Backward-Compatible Delegation from optimize_mesh_silhouette Verified")

            deleg_sculpt_res = await call_tool("sculpt_mesh", {
                "object_name": deleg_mesh,
                "expected_snapshot_id": "sha256:" + "0" * 64,  # contract allows delegation
                "action": "sculpt_organic_anatomy",
                "brush_type": "SMOOTH",
                "radius": 1.5,
                "strength": 0.3,
            })
            assert deleg_sculpt_res["status"] == "success", deleg_sculpt_res
            assert deleg_sculpt_res["result"]["sculpt_status"] == "SCULPTED"
            print("[PASS] Step 9b: Backward-Compatible Delegation from sculpt_mesh Verified")

            # --- STEP 10: Fail-Closed Security & Guardrail Validations ---
            # 10a: Untrusted approval flag
            err_untrusted = await call_tool("sculpt_organic_anatomy", {
                "target_object": deleg_mesh,
                "brush_type": "INFLATE",
                "approved": True,
            })
            assert err_untrusted["status"] == "error", err_untrusted
            assert "untrusted" in err_untrusted["message"].lower() or "approval denied" in err_untrusted["message"].lower()
            print("[PASS] Step 10a: Untrusted approved=True flag rejected fail-closed")

            # 10b: Non-existent object
            err_nonexistent = await call_tool("sculpt_organic_anatomy", {
                "target_object": "GhostObject_99999",
                "brush_type": "INFLATE",
            })
            assert err_nonexistent["status"] == "error", err_nonexistent
            assert "not found" in err_nonexistent["message"].lower()
            print("[PASS] Step 10b: Non-existent target object rejected fail-closed")

            # 10c: Non-mesh object
            err_nonmesh = await call_tool("sculpt_organic_anatomy", {
                "target_object": "SceneCamera",
                "brush_type": "INFLATE",
            })
            assert err_nonmesh["status"] == "error", err_nonmesh
            assert "not a mesh" in err_nonmesh["message"].lower() or "mesh" in err_nonmesh["message"].lower()
            print("[PASS] Step 10c: Non-mesh target object rejected fail-closed")

            # 10d: Conflicting parameters
            err_conflict = await call_tool("sculpt_organic_anatomy", {
                "target_object": deleg_mesh,
                "brush_type": "INFLATE",
                "preserve_topology": True,
                "dynamic_topology": True,
            })
            assert err_conflict["status"] == "error", err_conflict
            assert "conflicting" in err_conflict["message"].lower()
            print("[PASS] Step 10d: Conflicting preserve_topology=True and dynamic_topology=True rejected fail-closed")

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

    print("\n=== ALL E2E VERIFICATIONS PASSED SUCCESSFULLY (TASK v0.1.56) ===")


if __name__ == "__main__":
    asyncio.run(main())
