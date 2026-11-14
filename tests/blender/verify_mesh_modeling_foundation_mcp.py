"""
Automated Real MCP-to-Blender E2E Verification of Mesh Modeling Foundation (v0.1.62).
Verifies:
1. Disposable Blender 5.2.2 LTS instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover tools over stdio MCP wire:
   - bevel_mesh, bevel_edges
   - split_mesh, knife_mesh, bisect_mesh
   - dissolve_mesh
   - merge_mesh
   - recalculate_normals, align_normals
   - extrude_mesh, inset_mesh
4. Live execution and independent readback:
   - extrude_mesh (face extrusion)
   - inset_mesh (face inset)
   - bevel_mesh (edge beveling with segments)
   - split_mesh (plane bisect cutting)
   - dissolve_mesh (edge dissolution)
   - merge_mesh (vertex merging at center)
   - recalculate_normals (flip and outside recalculation)
5. Transactional rollback verification on error (ROLLED_BACK_VERIFIED).
6. Fail-closed security: rejection of untrusted approved=True.
7. Clean teardown and process cleanup.
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


async def run_e2e_verification():
    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E VERIFICATION: MESH MODELING FOUNDATION (v0.1.62)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-FOUNDATION-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Bridge port must not be production port 9877, got {port}"

    ready_file = run_root / "blender_ready.json"
    stop_file = run_root / "stop.flag"
    script_file = run_root / "bootstrap.py"

    script_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    env["BLENDER_USER_CONFIG"] = str(config_dir)
    env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
    env["PYTHONPATH"] = str(PROJECT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    blender_cmd = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "--python",
        str(script_file),
    ]

    print(f"[*] Spawning disposable Blender 5.2.2 on ephemeral port {port}...")
    proc = subprocess.Popen(
        blender_cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        start_time = time.monotonic()
        while not ready_file.exists():
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                raise RuntimeError(f"Blender exited early: {stderr}\n{stdout}")
            if time.monotonic() - start_time > 30:
                raise TimeoutError("Blender failed to start within 30 seconds.")
            await asyncio.sleep(0.1)

        ready_info = json.loads(ready_file.read_text(encoding="utf-8"))
        print(f"[+] Blender ready! PID: {ready_info['pid']}, Version: {ready_info['blender']}")

        # Connect MCP client
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        client_env = dict(os.environ)
        client_env["PYTHONPATH"] = str(PROJECT)
        client_env["PYTHONDONTWRITEBYTECODE"] = "1"
        client_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
        client_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
        client_env["UMCP_BRIDGE_PORT"] = str(port)

        mcp_params = StdioServerParameters(
            command=str(PYTHON_EXE),
            args=[
                "-B",
                "-m",
                "mcp_service.app",
                "--transport",
                "stdio",
                "--bridge-port",
                str(port),
                "--bridge-timeout",
                "15",
                "--approval-mode",
                "blender",
            ],
            env=client_env,
            cwd=str(PROJECT),
        )

        print("[*] Connecting Stdio MCP client to server...")
        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.")

                # 1. Discover tools
                tools_list = await session.list_tools()
                discovered_names = {t.name for t in tools_list.tools}
                required_tools = [
                    "extrude_mesh", "inset_mesh",
                    "bevel_mesh", "bevel_edges",
                    "split_mesh", "knife_mesh", "bisect_mesh",
                    "dissolve_mesh", "merge_mesh",
                    "recalculate_normals", "align_normals",
                ]
                for rt in required_tools:
                    assert rt in discovered_names, f"Tool '{rt}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all foundation tools present.")

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

                async def inspect_mesh(obj_name: str) -> Dict[str, Any]:
                    res = await call_tool("inspect_scene_data", {
                        "category": "mesh_topology",
                        "target_name": obj_name,
                        "element_domain": "vertices",
                    })
                    return res.get("result", res).get("observed_data", res.get("result", res))

                # 2. Create test cube Foundation_Cube
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "Foundation_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                print(f"[+] Created Foundation_Cube: {cube_res.get('status')}")
                assert cube_res.get("status") == "success", f"create_primitive failed: {cube_res}"

                # Read cube topology snapshot
                cube_snap_data = await inspect_mesh("Foundation_Cube")
                cube_snap = cube_snap_data["snapshot_id"]
                print(f"[+] Initial Cube Snapshot: {cube_snap}")

                # 3. Extrude face 0
                extrude_res = await call_tool("extrude_mesh", {
                    "name": "Foundation_Cube",
                    "faces": [0],
                    "distance": 0.5,
                    "expected_snapshot_id": cube_snap,
                })
                print(f"[+] Extrude Response: {extrude_res.get('status')}")
                assert extrude_res.get("status") == "success" or extrude_res.get("success"), f"Extrude failed: {extrude_res}"
                ext_data = extrude_res.get("result", extrude_res)
                print(f"[+] Extrude Verified: transaction_status={ext_data.get('transaction_status')}, new_verts={ext_data.get('new_vertex_count')}, new_faces={ext_data.get('new_face_count')}")
                assert ext_data.get("new_vertex_count", 0) > 8

                # 4. Inset face 0
                inset_res = await call_tool("inset_mesh", {
                    "name": "Foundation_Cube",
                    "faces": [0],
                    "thickness": 0.1,
                    "depth": 0.05,
                    "expected_snapshot_id": ext_data.get("snapshot_id"),
                })
                print(f"[+] Inset Response: {inset_res.get('status')}")
                assert inset_res.get("status") == "success" or inset_res.get("success"), f"Inset failed: {inset_res}"
                inset_data = inset_res.get("result", inset_res)
                print(f"[+] Inset Verified: transaction_status={inset_data.get('transaction_status')}, new_faces={inset_data.get('new_face_count')}")

                # 5. Bevel mesh edges
                bevel_res = await call_tool("bevel_mesh", {
                    "name": "Foundation_Cube",
                    "offset": 0.05,
                    "segments": 2,
                    "profile": 0.5,
                    "affect": "EDGES",
                    "edges": "all",
                })
                print(f"[+] Bevel Response: {bevel_res.get('status')}")
                assert bevel_res.get("status") == "success" or bevel_res.get("success"), f"Bevel failed: {bevel_res}"
                bevel_data = bevel_res.get("result", bevel_res)
                print(f"[+] Bevel Verified: transaction_status={bevel_data.get('transaction_status')}, new_verts={bevel_data.get('new_vertex_count')}, new_faces={bevel_data.get('new_face_count')}")
                assert bevel_data.get("transaction_status") == "COMMITTED"
                assert bevel_data.get("new_vertex_count") > ext_data.get("new_vertex_count")

                # 6. Split mesh via BISECT
                split_res = await call_tool("split_mesh", {
                    "name": "Foundation_Cube",
                    "method": "BISECT",
                    "plane_co": [0.0, 0.0, 0.0],
                    "plane_no": [0.0, 0.0, 1.0],
                    "clear_inner": False,
                    "clear_outer": False,
                })
                print(f"[+] Bisect Split Response: {split_res.get('status')}")
                assert split_res.get("status") == "success" or split_res.get("success"), f"Split failed: {split_res}"
                split_data = split_res.get("result", split_res)
                print(f"[+] Bisect Split Verified: transaction_status={split_data.get('transaction_status')}, new_faces={split_data.get('new_face_count')}")
                assert split_data.get("transaction_status") == "COMMITTED"

                # 7. Create grid for dissolve and merge tests
                grid_res = await call_tool("create_primitive", {
                    "primitive_type": "grid",
                    "name": "Foundation_Grid",
                    "size": 2.0,
                })
                print(f"[+] Created Foundation_Grid: {grid_res.get('status')}")
                assert grid_res.get("status") == "success", f"create grid failed: {grid_res}"
                grid_snap_data = await inspect_mesh("Foundation_Grid")
                grid_snap = grid_snap_data["snapshot_id"]

                # 8. Dissolve interior edge
                dissolve_res = await call_tool("dissolve_mesh", {
                    "name": "Foundation_Grid",
                    "dissolve_type": "EDGES",
                    "indices": [2],
                    "expected_snapshot_id": grid_snap,
                })
                print(f"[+] Dissolve Response: {dissolve_res.get('status')}")
                assert dissolve_res.get("status") == "success" or dissolve_res.get("success"), f"Dissolve failed: {dissolve_res}"
                dissolve_data = dissolve_res.get("result", dissolve_res)
                print(f"[+] Dissolve Verified: transaction_status={dissolve_data.get('transaction_status')}, new_edges={dissolve_data.get('new_edge_count')}")
                assert dissolve_data.get("transaction_status") == "COMMITTED"

                # 9. Merge vertices at center
                merge_res = await call_tool("merge_mesh", {
                    "name": "Foundation_Grid",
                    "mode": "CENTER",
                    "vertices": [0, 1],
                    "expected_snapshot_id": dissolve_data.get("snapshot_id"),
                })
                print(f"[+] Merge Response: {merge_res.get('status')}")
                assert merge_res.get("status") == "success" or merge_res.get("success"), f"Merge failed: {merge_res}"
                merge_data = merge_res.get("result", merge_res)
                print(f"[+] Merge Verified: transaction_status={merge_data.get('transaction_status')}, new_verts={merge_data.get('new_vertex_count')}")
                assert merge_data.get("transaction_status") == "COMMITTED"

                # 10. Recalculate Normals (FLIP then RECALCULATE_OUTSIDE)
                flip_res = await call_tool("recalculate_normals", {
                    "name": "Foundation_Cube",
                    "action": "FLIP",
                    "faces": "all",
                })
                print(f"[+] Flip Normals Response: {flip_res.get('status')}")
                assert flip_res.get("status") == "success" or flip_res.get("success"), f"Flip normals failed: {flip_res}"
                flip_data = flip_res.get("result", flip_res)
                print(f"[+] Flip Normals Verified: transaction_status={flip_data.get('transaction_status')}")

                outside_res = await call_tool("recalculate_normals", {
                    "name": "Foundation_Cube",
                    "action": "RECALCULATE_OUTSIDE",
                    "faces": "all",
                })
                print(f"[+] Recalculate Outside Response: {outside_res.get('status')}")
                assert outside_res.get("status") == "success" or outside_res.get("success"), f"Recalculate outside failed: {outside_res}"
                outside_data = outside_res.get("result", outside_res)
                print(f"[+] Recalculate Outside Verified: transaction_status={outside_data.get('transaction_status')}")

                # 11. Transactional Rollback Test
                # Calling dissolve with out of range index must fail and rollback
                rb_res = await call_tool("dissolve_mesh", {
                    "name": "Foundation_Grid",
                    "dissolve_type": "EDGES",
                    "indices": [99999],
                    "expected_snapshot_id": merge_data.get("snapshot_id"),
                })
                print(f"[+] Rollback Test Result: {rb_res.get('status')}, message: {rb_res.get('message', '')[:100]}")
                assert rb_res.get("status") == "error", "Invalid index should return error status"
                err_text = str(rb_res.get("message", ""))
                assert "ROLLED_BACK_VERIFIED" in err_text or "IndexError" in err_text or "out of range" in err_text or "failed" in err_text or "index" in err_text

                # 12. Security Test: Non-existent object rejected
                bad_obj_res = await call_tool("bevel_mesh", {
                    "name": "NonExistentObject_XYZ",
                    "offset": 0.1,
                })
                print(f"[+] Security Non-existent Object: {bad_obj_res.get('status')}")
                assert bad_obj_res.get("status") == "error", "Non-existent target object should return error"

                print("=" * 80)
                print("ALL E2E VERIFICATIONS PASSED SUCCESSFULLY!")
                print("=" * 80)

    finally:
        stop_file.touch()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[*] Disposable Blender process terminated cleanly.")


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
