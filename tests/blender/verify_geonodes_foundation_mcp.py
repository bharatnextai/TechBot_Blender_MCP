"""
Automated Real MCP-to-Blender E2E Verification of Geometry Nodes Foundation (v0.1.64).
Covers Capability 4:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover Geometry Nodes foundation tools over MCP stdio wire:
   - configure_geometry_nodes
   - inspect_geometry_nodes
4. Live execution and independent Blender readback:
   - Primitive creation ('GN_Cube')
   - Initial stack inspection (0 modifiers, base 8 vertices)
   - Action 'create': modifier and node group created with Input/Output interface
   - Action 'add_node': SubdivisionSurface node added with initial inputs
   - Action 'add_link': Connect Input.Geometry -> Subdiv.Mesh
   - Action 'add_link': Connect Subdiv.Mesh -> Output.Geometry
   - Evaluate via inspect_geometry_nodes: base verts=8, evaluated verts=98
   - Action 'set_node_input': update Subdiv.Level to 1 -> evaluated verts=26
   - Action 'apply': bake evaluated geometry permanently to base mesh (base verts=26)
5. Transactional rollback verification:
   - Stale snapshot rejection (STALE_GEOMETRY_NODES)
   - Geometry and state preserved bit-for-bit
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
    print("STARTING REAL MCP-TO-BLENDER E2E: GEOMETRY NODES FOUNDATION (v0.1.64)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-GEONODES-"))
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
                self_tools = ["configure_geometry_nodes", "inspect_geometry_nodes"]
                for st in self_tools:
                    assert st in discovered_names, f"Tool '{st}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all Geometry Nodes foundation tools present.")

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

                # 2. Create test cube GN_Cube
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "GN_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                print(f"[+] Created GN_Cube: {cube_res.get('status')}")
                assert cube_res.get("status") == "success", f"create_primitive failed: {cube_res}"

                # 3. Inspect initial modifier state (no GN modifier yet)
                inspect_init = await call_tool("inspect_geometry_nodes", {"name": "GN_Cube"})
                init_data = inspect_init.get("result", inspect_init)
                assert init_data["modifier_exists"] is False
                assert init_data["base_geometry"]["vertex_count"] == 8
                snap0 = init_data["snapshot_id"]
                print(f"[+] Initial GN State Verified: 0 GN modifiers, 8 base vertices. Snapshot: {snap0[:18]}...")

                # 4. Action 'create': Create Geometry Nodes modifier & group
                create_res = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "create",
                    "modifier_name": "GeometryNodes",
                    "expected_snapshot_id": snap0,
                })
                assert create_res.get("status") == "success" or create_res.get("success"), f"create failed: {create_res}"
                create_data = create_res.get("result", create_res)
                assert create_data["modifier_exists"] is True
                assert create_data["node_group_name"] is not None
                snap1 = create_data["snapshot_id"]
                assert snap1 != snap0
                print(f"[+] Create Modifier Verified: group={create_data['node_group_name']}, nodes={len(create_data['nodes'])}. Snapshot: {snap1[:18]}...")

                # 5. Action 'add_node': Add SubdivisionSurface node
                add_subdiv = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "add_node",
                    "node_type": "GeometryNodeSubdivisionSurface",
                    "node_name": "Subdiv",
                    "inputs": {"Level": 2},
                    "expected_snapshot_id": snap1,
                })
                assert add_subdiv.get("status") == "success" or add_subdiv.get("success"), f"add_node failed: {add_subdiv}"
                subdiv_data = add_subdiv.get("result", add_subdiv)
                subdiv_names = [n["name"] for n in subdiv_data["nodes"]]
                assert "Subdiv" in subdiv_names, f"Expected Subdiv node, got {subdiv_names}"
                snap2 = subdiv_data["snapshot_id"]
                print(f"[+] Add Node Verified: Subdiv node present. Snapshot: {snap2[:18]}...")

                # 6. Action 'add_link': Connect Input.Geometry -> Subdiv.Mesh
                link1_res = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "add_link",
                    "from_node": "Input",
                    "from_socket": "Geometry",
                    "to_node": "Subdiv",
                    "to_socket": "Mesh",
                    "expected_snapshot_id": snap2,
                })
                assert link1_res.get("status") == "success" or link1_res.get("success"), f"link1 failed: {link1_res}"
                link1_data = link1_res.get("result", link1_res)
                snap3 = link1_data["snapshot_id"]
                assert len(link1_data["links"]) >= 1
                print(f"[+] Link 1 Verified: Input.Geometry -> Subdiv.Mesh. Snapshot: {snap3[:18]}...")

                # 7. Action 'add_link': Connect Subdiv.Mesh -> Output.Geometry
                link2_res = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "add_link",
                    "from_node": "Subdiv",
                    "from_socket": "Mesh",
                    "to_node": "Output",
                    "to_socket": "Geometry",
                    "expected_snapshot_id": snap3,
                })
                assert link2_res.get("status") == "success" or link2_res.get("success"), f"link2 failed: {link2_res}"
                link2_data = link2_res.get("result", link2_res)
                snap4 = link2_data["snapshot_id"]
                print(f"[+] Link 2 Verified: Subdiv.Mesh -> Output.Geometry. Snapshot: {snap4[:18]}...")

                # 8. Evaluate: verify base vertices=8, evaluated vertices=98
                eval_res = await call_tool("inspect_geometry_nodes", {"name": "GN_Cube"})
                eval_data = eval_res.get("result", eval_res)
                assert eval_data["base_geometry"]["vertex_count"] == 8, f"Base vertices should be 8, got {eval_data['base_geometry']['vertex_count']}"
                assert eval_data["evaluated_geometry"]["vertex_count"] == 98, f"Evaluated vertices should be 98 (level 2), got {eval_data['evaluated_geometry']['vertex_count']}"
                assert eval_data["evaluated_geometry"]["polygon_count"] == 96, f"Evaluated polygons should be 96, got {eval_data['evaluated_geometry']['polygon_count']}"
                snap5 = eval_data["snapshot_id"]
                print(f"[+] Graph Evaluation Verified: base_verts=8 -> evaluated_verts=98, evaluated_polys=96.")

                # 9. Action 'set_node_input': update Subdiv Level to 1
                update_level_res = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "set_node_input",
                    "node_name": "Subdiv",
                    "socket_name": "Level",
                    "value": 1,
                    "expected_snapshot_id": snap5,
                })
                assert update_level_res.get("status") == "success" or update_level_res.get("success"), f"update level failed: {update_level_res}"
                lvl_data = update_level_res.get("result", update_level_res)
                assert lvl_data["evaluated_geometry"]["vertex_count"] == 26, f"Evaluated vertices with level 1 should be 26, got {lvl_data['evaluated_geometry']['vertex_count']}"
                snap6 = lvl_data["snapshot_id"]
                print(f"[+] Set Node Input Verified: Level updated to 1, evaluated_verts=26. Snapshot: {snap6[:18]}...")

                # 10. Action 'apply': bake evaluated geometry permanently to base mesh
                apply_res = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "apply",
                    "modifier_name": "GeometryNodes",
                    "expected_snapshot_id": snap6,
                })
                assert apply_res.get("status") == "success" or apply_res.get("success"), f"apply failed: {apply_res}"
                apply_data = apply_res.get("result", apply_res)
                assert apply_data["base_geometry"]["vertex_count"] == 26, f"Expected 26 base vertices after apply, got {apply_data['base_geometry']['vertex_count']}"
                assert apply_data["modifier_exists"] is False, "Modifier should be removed after apply"
                snap7 = apply_data["snapshot_id"]
                print(f"[+] Apply Verified: base vertices permanently baked to 26, modifier cleanly removed.")

                # 11. Transactional Rollback Test: Stale snapshot rejection
                stale_res = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "create",
                    "expected_snapshot_id": "sha256:" + "0" * 64,
                })
                assert stale_res.get("status") == "error", f"Stale snapshot should return error, got: {stale_res}"
                err_text = str(stale_res.get("message", ""))
                assert "STALE_GEOMETRY_NODES" in err_text or "Snapshot" in err_text or "snapshot" in err_text.lower(), f"Expected snapshot error: {err_text}"
                print(f"[+] Rollback Test Verified: Stale snapshot rejected fail-closed ({err_text[:60]}...).")

                # Verify geometry state unchanged after rejected mutation
                check_res = await call_tool("inspect_geometry_nodes", {"name": "GN_Cube"})
                check_data = check_res.get("result", check_res)
                assert check_data["snapshot_id"] == snap7, "Snapshot altered after failed mutation!"
                assert check_data["base_geometry"]["vertex_count"] == 26, "Geometry altered after failed mutation!"
                print("[+] State Preservation Verified: snapshot and geometry preserved bit-for-bit.")

                # 12. Security Test: Reject untrusted client approval
                untrusted_res = await call_tool("configure_geometry_nodes", {
                    "name": "GN_Cube",
                    "action": "create",
                    "approved": True,
                })
                assert untrusted_res.get("status") == "error", f"Untrusted approved=True must return error: {untrusted_res}"
                err_sec = str(untrusted_res.get("message", ""))
                assert "untrusted" in err_sec.lower() or "denied" in err_sec.lower() or "approval" in err_sec.lower()
                print(f"[+] Security Test Verified: Untrusted approved=True rejected fail-closed ({err_sec[:60]}...).")

                # 13. Security Test: Non-existent target object
                bad_obj_res = await call_tool("inspect_geometry_nodes", {
                    "name": "Ghost_Object_GN",
                })
                assert bad_obj_res.get("status") == "error", f"Non-existent object should return error: {bad_obj_res}"
                print("[+] Security Test Verified: Non-existent target object rejected fail-closed.")

                print("=" * 80)
                print("ALL 13/13 GEOMETRY NODES FOUNDATION CHECKS PASSED SUCCESSFULLY!")
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

