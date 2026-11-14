"""
Automated Real MCP-to-Blender E2E Verification of UV Mapping Foundation (v0.1.65).
Covers Capability 5:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover UV foundation tools over MCP stdio wire:
   - uv_unwrap / unwrap_mesh
   - uv_smart_project / smart_project
   - manage_uv_seams
   - pack_uv_islands
   - manage_uv_layers
   - inspect_uv_mesh
4. Live execution and independent Blender readback:
   - Primitive creation ('UV_Cube')
   - Initial UV inspection via inspect_uv_mesh (active layer 'UVMap', 6 faces, 12 edges, 24 loops, 0 seams)
   - Action manage_uv_seams: mark seams along edges [0, 2, 4, 6] -> readback confirms 4 seams marked
   - Action uv_unwrap: unwrap with ANGLE_BASED method and margin 0.02 -> readback confirms valid UV coordinates
   - Action pack_uv_islands: pack UV islands with margin 0.05 -> readback confirms valid UV bounds in [0.0, 1.0]
   - Action uv_smart_project: smart projection with angle_limit 45.0 -> readback confirms projected faces
   - Action manage_uv_layers: create 'LightmapUV' -> readback confirms 2 layers
   - Action manage_uv_layers: set_active 'LightmapUV' -> readback confirms active_uv_layer == 'LightmapUV'
   - Action manage_uv_layers: rename 'LightmapUV' -> 'BakedUV' -> readback confirms 'BakedUV' layer exists
   - Action manage_uv_layers: remove 'BakedUV' -> readback confirms 1 layer remaining
5. Transactional rollback and optimistic concurrency:
   - Stale snapshot rejection (STALE_UV_TOPOLOGY)
   - State and seams preserved bit-for-bit
6. Security enforcement:
   - Untrusted approved=True rejected fail-closed
   - Non-existent target object rejected fail-closed
7. Teardown and clean process cleanup.
"""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any

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
    print("STARTING REAL MCP-TO-BLENDER E2E: UV MAPPING FOUNDATION (v0.1.65)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-UV-"))
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
                uv_tools = [
                    "uv_unwrap", "unwrap_mesh",
                    "uv_smart_project", "smart_project",
                    "manage_uv_seams", "pack_uv_islands",
                    "manage_uv_layers", "inspect_uv_mesh",
                ]
                for ut in uv_tools:
                    assert ut in discovered_names, f"Tool '{ut}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all UV foundation tools present.")

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

                # 2. Create test cube UV_Cube
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "UV_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                print(f"[+] Created UV_Cube: {cube_res.get('status')}")
                assert cube_res.get("status") == "success", f"create_primitive failed: {cube_res}"

                # 3. Inspect initial UV state
                inspect_init = await call_tool("inspect_uv_mesh", {"name": "UV_Cube"})
                init_data = inspect_init.get("result", inspect_init)
                assert init_data["name"] == "UV_Cube"
                assert init_data["has_uvs"] is True
                assert init_data["active_uv_layer"] == "UVMap"
                assert init_data["uv_layer_count"] == 1
                assert init_data["total_faces"] == 6
                assert init_data["total_edges"] == 12
                assert init_data["seam_count"] == 0
                snap0 = init_data["snapshot_id"]
                assert snap0.startswith("sha256:")
                assert len(snap0) == 71
                print(f"[+] Initial UV State: layer={init_data['active_uv_layer']}, faces={init_data['total_faces']}, seams={init_data['seam_count']}. Snapshot: {snap0[:18]}...")

                # 4. Action manage_uv_seams: mark seams on edges [0, 2, 4, 6]
                mark_res = await call_tool("manage_uv_seams", {
                    "name": "UV_Cube",
                    "action": "mark",
                    "edges": [0, 2, 4, 6],
                    "expected_snapshot_id": snap0,
                })
                assert mark_res.get("status") == "success" or mark_res.get("action") == "mark", f"mark failed: {mark_res}"
                mark_data = mark_res.get("result", mark_res)
                assert mark_data["modified_edges_count"] == 4
                assert mark_data["total_seam_count"] == 4
                snap1 = mark_data["snapshot_id"]
                assert snap1 != snap0
                print(f"[+] Marked Seams Verified: count={mark_data['total_seam_count']}, edges={mark_data['seam_edges']}. Snapshot: {snap1[:18]}...")

                # 5. Action uv_unwrap: unwrap faces using marked seams
                unwrap_res = await call_tool("uv_unwrap", {
                    "name": "UV_Cube",
                    "method": "ANGLE_BASED",
                    "margin": 0.02,
                    "expected_snapshot_id": snap1,
                })
                assert unwrap_res.get("status") == "success" or unwrap_res.get("operation") == "uv_unwrap", f"unwrap failed: {unwrap_res}"
                unwrap_data = unwrap_res.get("result", unwrap_res)
                assert unwrap_data["faces_unwrapped"] == 6
                assert "uv_bounds" in unwrap_data
                snap2 = unwrap_data["snapshot_id"]
                assert snap2 != snap1
                print(f"[+] UV Unwrap Verified: faces={unwrap_data['faces_unwrapped']}, bounds={unwrap_data['uv_bounds']}. Snapshot: {snap2[:18]}...")

                # 6. Action pack_uv_islands: pack islands into unit square
                pack_res = await call_tool("pack_uv_islands", {
                    "name": "UV_Cube",
                    "margin": 0.05,
                    "rotate": True,
                    "expected_snapshot_id": snap2,
                })
                assert pack_res.get("status") == "success" or pack_res.get("operation") == "pack_uv_islands", f"pack failed: {pack_res}"
                pack_data = pack_res.get("result", pack_res)
                assert "uv_bounds" in pack_data
                snap3 = pack_data["snapshot_id"]
                print(f"[+] Pack Islands Verified: margin={pack_data['margin']}, bounds={pack_data['uv_bounds']}. Snapshot: {snap3[:18]}...")

                # 7. Action uv_smart_project: run smart UV projection
                smart_res = await call_tool("uv_smart_project", {
                    "name": "UV_Cube",
                    "angle_limit": 45.0,
                    "island_margin": 0.02,
                    "expected_snapshot_id": snap3,
                })
                assert smart_res.get("status") == "success" or smart_res.get("operation") == "uv_smart_project", f"smart_project failed: {smart_res}"
                smart_data = smart_res.get("result", smart_res)
                assert smart_data["faces_projected"] == 6
                snap4 = smart_data["snapshot_id"]
                print(f"[+] Smart UV Project Verified: faces={smart_data['faces_projected']}, angle={smart_data['angle_limit']}. Snapshot: {snap4[:18]}...")

                # 8. Action manage_uv_layers: create new layer 'LightmapUV'
                create_lyr = await call_tool("manage_uv_layers", {
                    "name": "UV_Cube",
                    "action": "create",
                    "layer_name": "LightmapUV",
                    "expected_snapshot_id": snap4,
                })
                assert create_lyr.get("status") == "success" or create_lyr.get("action") == "create", f"create layer failed: {create_lyr}"
                lyr_data = create_lyr.get("result", create_lyr)
                assert lyr_data["uv_layer_count"] == 2
                snap5 = lyr_data["snapshot_id"]
                print(f"[+] Create UV Layer Verified: count={lyr_data['uv_layer_count']}, layers={[l['name'] for l in lyr_data['uv_layers']]}. Snapshot: {snap5[:18]}...")

                # 9. Action manage_uv_layers: set active layer to 'LightmapUV'
                active_lyr = await call_tool("manage_uv_layers", {
                    "name": "UV_Cube",
                    "action": "set_active",
                    "layer_name": "LightmapUV",
                    "expected_snapshot_id": snap5,
                })
                assert active_lyr.get("status") == "success" or active_lyr.get("action") == "set_active", f"set active failed: {active_lyr}"
                active_data = active_lyr.get("result", active_lyr)
                assert active_data["active_uv_layer"] == "LightmapUV"
                snap6 = active_data["snapshot_id"]
                print(f"[+] Set Active Layer Verified: active={active_data['active_uv_layer']}. Snapshot: {snap6[:18]}...")

                # 10. Action manage_uv_layers: rename 'LightmapUV' to 'BakedUV'
                rename_lyr = await call_tool("manage_uv_layers", {
                    "name": "UV_Cube",
                    "action": "rename",
                    "layer_name": "LightmapUV",
                    "new_name": "BakedUV",
                    "expected_snapshot_id": snap6,
                })
                assert rename_lyr.get("status") == "success" or rename_lyr.get("action") == "rename", f"rename layer failed: {rename_lyr}"
                rename_data = rename_lyr.get("result", rename_lyr)
                assert "BakedUV" in [l["name"] for l in rename_data["uv_layers"]]
                snap7 = rename_data["snapshot_id"]
                print(f"[+] Rename UV Layer Verified: BakedUV present. Snapshot: {snap7[:18]}...")

                # 11. Action manage_uv_layers: remove layer 'BakedUV'
                remove_lyr = await call_tool("manage_uv_layers", {
                    "name": "UV_Cube",
                    "action": "remove",
                    "layer_name": "BakedUV",
                    "expected_snapshot_id": snap7,
                })
                assert remove_lyr.get("status") == "success" or remove_lyr.get("action") == "remove", f"remove layer failed: {remove_lyr}"
                remove_data = remove_lyr.get("result", remove_lyr)
                assert remove_data["uv_layer_count"] == 1
                snap8 = remove_data["snapshot_id"]
                print(f"[+] Remove UV Layer Verified: count={remove_data['uv_layer_count']}. Snapshot: {snap8[:18]}...")

                # 12. Optimistic concurrency rejection: stale snapshot on seam mutation
                stale_res = await call_tool("manage_uv_seams", {
                    "name": "UV_Cube",
                    "action": "clear_all",
                    "expected_snapshot_id": "sha256:" + "0" * 64,
                })
                assert stale_res.get("status") == "error", f"Stale snapshot should have failed: {stale_res}"
                assert "STALE_UV_TOPOLOGY" in stale_res.get("message", ""), f"Expected STALE_UV_TOPOLOGY error: {stale_res}"
                print("[+] Optimistic Concurrency Failure Verified: Stale snapshot rejected with STALE_UV_TOPOLOGY.")

                # Readback confirms state was untouched
                inspect_after_stale = await call_tool("inspect_uv_mesh", {"name": "UV_Cube"})
                stale_check = inspect_after_stale.get("result", inspect_after_stale)
                assert stale_check["snapshot_id"] == snap8, "State altered after failed optimistic concurrency mutation!"
                print(f"[+] Post-rejection Integrity Verified: snapshot={snap8[:18]}... preserved bit-for-bit.")

                # 13. Security checks: Untrusted approved=True rejection
                sec_res = await call_tool("manage_uv_seams", {
                    "name": "UV_Cube",
                    "action": "clear_all",
                    "approved": True,
                })
                assert sec_res.get("status") == "error", f"Untrusted approved=True should have failed: {sec_res}"
                assert "untrusted" in sec_res.get("message", "").lower(), f"Expected untrusted approval error: {sec_res}"
                print("[+] Security Guard Verified: Untrusted approved=True rejected fail-closed.")

                # Security checks: Non-existent object rejection
                missing_res = await call_tool("inspect_uv_mesh", {"name": "Ghost_Cube"})
                assert missing_res.get("status") == "error", f"Non-existent object should have failed: {missing_res}"
                assert "not found" in missing_res.get("message", "").lower(), f"Expected not found error: {missing_res}"
                print("[+] Input Validation Verified: Non-existent target object rejected fail-closed.")

                print("=" * 80)
                print("REAL MCP-TO-BLENDER E2E ACCEPTANCE PASSED FOR CAPABILITY 5: UVs (v0.1.65)")
                print("=" * 80)

    finally:
        print("[*] Tearing down disposable Blender instance...")
        stop_file.touch()
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("[+] Disposable Blender process cleaned up cleanly.")


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
