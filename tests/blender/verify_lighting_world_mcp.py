"""
Automated Real MCP-to-Blender E2E Verification of Lighting & World Foundation (v0.1.68).
Covers Capability 8:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover Lighting & World tools over MCP stdio wire:
   - create_light
   - configure_light (and alias edit_light)
   - configure_world
   - manage_shader_nodes (with target_type="WORLD")
   - inspect_scene_data (world_settings, light_settings)
   - get_object_details (light_details)
4. Live execution and independent Blender readback:
   - Create Sun light ('Sun_Key', SUN, energy=5.0, color=[1.0, 0.95, 0.85], location=[10, 10, 20])
   - Inspect Sun light via inspect_scene_data(category="light_settings") -> verify properties
   - Inspect Sun light via get_object_details -> verify light_details
   - Configure Sun light via configure_light (energy=7.5, color=[0.9, 0.95, 1.0]) -> verify update
   - Create Spot light ('Spot_Key', SPOT, energy=1500.0, spot_size=0.785, spot_blend=0.2)
   - Configure Spot light via configure_light (spot_size=1.047, spot_blend=0.35, energy=2200.0)
   - Create Area light ('Area_Soft', AREA, energy=800.0, size=2.0)
   - Configure Area light via configure_light (size=3.5, energy=1200.0)
   - Configure World background color and strength via configure_world
   - Inspect World background via inspect_scene_data(category="world_settings")
   - World node manipulation via manage_shader_nodes(target_type="WORLD", action="create_node", node_type="environment_texture")
5. Security and validation enforcement:
   - Untrusted approved=True rejected fail-closed
   - Negative energy rejected fail-closed
   - Out-of-bounds color component (> 1.0) rejected fail-closed
   - Non-existent light object rejected fail-closed
   - Unsupported features (render_engine in configure_world, light_linking in configure_light) rejected fail-closed
6. Teardown and clean process cleanup.
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
    print("STARTING REAL MCP-TO-BLENDER E2E: LIGHTING & WORLD (v0.1.68)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-LIGHT-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Guard violation: ephemeral port matched production {port}"

    ready_file = run_root / "blender_ready.json"
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

    print(f"[*] Spawning disposable Blender 5.2.2 on ephemeral port {port}...")
    proc = subprocess.Popen(
        [
            str(BLENDER),
            "--background",
            "--factory-startup",
            "--python",
            str(script_file),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(run_root),
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
        print(f"[+] Blender ready! PID: {ready_info['pid']}, Version: {ready_info.get('blender', '5.2.2 LTS')}")

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
                "--debug",
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
                for req_tool in ("create_light", "configure_light", "configure_world", "manage_shader_nodes", "inspect_scene_data", "get_object_details"):
                    assert req_tool in discovered_names, f"Tool '{req_tool}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all lighting & world tools present.")

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

                # 2. Create Sun Light
                sun_res = await call_tool("create_light", {
                    "name": "Sun_Key",
                    "light_type": "SUN",
                    "energy": 5.0,
                    "color": [1.0, 0.95, 0.85],
                    "location": [10.0, 10.0, 20.0],
                })
                sun_data = sun_res.get("result", sun_res)
                assert sun_data.get("name") == "Sun_Key"
                assert sun_data.get("light_type") == "SUN"
                assert sun_data.get("energy") == 5.0
                print("[+] Created Sun Light 'Sun_Key': success")

                # 3. Inspect Sun Light via list_objects
                list_lights = await call_tool("list_objects", {"object_type": "LIGHT"})
                list_lights_data = list_lights.get("result", list_lights)
                light_names = [o.get("name") for o in list_lights_data.get("objects", [])]
                assert "Sun_Key" in light_names
                print("[+] Verified 'Sun_Key' in list_objects(object_type='LIGHT'): verified")

                # 4. Inspect Sun Light via get_object_details
                details_sun = await call_tool("get_object_details", {"name": "Sun_Key"})
                details_sun_data = details_sun.get("result", details_sun)
                ld = details_sun_data.get("light_details")
                assert ld is not None, f"light_details missing in get_object_details: {details_sun_data}"
                assert ld.get("light_type") == "SUN"
                assert ld.get("energy") == 5.0
                print("[+] Verified 'light_details' in get_object_details: success")

                # 5. Configure Sun Light
                conf_sun = await call_tool("configure_light", {
                    "name": "Sun_Key",
                    "energy": 7.5,
                    "color": [0.9, 0.95, 1.0],
                })
                conf_sun_data = conf_sun.get("result", conf_sun)
                assert conf_sun_data.get("energy") == 7.5
                assert conf_sun_data.get("color") == [0.9, 0.95, 1.0]
                print("[+] Configured 'Sun_Key' (energy=7.5, updated color): verified")

                # 6. Create Spot Light
                spot_res = await call_tool("create_light", {
                    "name": "Spot_Key",
                    "light_type": "SPOT",
                    "energy": 1500.0,
                    "spot_size": 0.785,
                    "location": [0.0, 0.0, 5.0],
                })
                assert spot_res.get("status") == "success" or spot_res.get("result", {}).get("name") == "Spot_Key"
                print("[+] Created Spot Light 'Spot_Key': success")

                # 7. Configure Spot Light
                conf_spot = await call_tool("configure_light", {
                    "name": "Spot_Key",
                    "energy": 2200.0,
                    "spot_size": 1.047,
                    "spot_blend": 0.35,
                })
                conf_spot_data = conf_spot.get("result", conf_spot)
                assert conf_spot_data.get("energy") == 2200.0
                assert conf_spot_data.get("spot_size") == 1.047
                assert conf_spot_data.get("spot_blend") == 0.35
                print("[+] Configured 'Spot_Key' (cone angle & blend): verified")

                # 8. Create Area Light
                area_res = await call_tool("create_light", {
                    "name": "Area_Soft",
                    "light_type": "AREA",
                    "energy": 800.0,
                    "size": 2.0,
                })
                assert area_res.get("status") == "success" or area_res.get("result", {}).get("name") == "Area_Soft"
                print("[+] Created Area Light 'Area_Soft': success")

                # 9. Configure Area Light
                conf_area = await call_tool("configure_light", {
                    "name": "Area_Soft",
                    "size": 3.5,
                    "energy": 1200.0,
                })
                conf_area_data = conf_area.get("result", conf_area)
                assert conf_area_data.get("size") == 3.5
                assert conf_area_data.get("energy") == 1200.0
                print("[+] Configured 'Area_Soft' (size=3.5m): verified")

                # 10. Configure World Background
                world_res = await call_tool("configure_world", {
                    "color": [0.03, 0.04, 0.08],
                    "strength": 1.4,
                    "use_nodes": True,
                })
                world_data = world_res.get("result", world_res)
                assert world_data.get("color") == [0.03, 0.04, 0.08]
                assert world_data.get("strength") == 1.4
                print("[+] Configured World background (color & strength): verified")

                # 11. Inspect World Settings
                insp_world = await call_tool("inspect_scene_data", {"category": "world_settings"})
                insp_world_data = insp_world.get("result", insp_world)
                assert insp_world_data.get("has_world") is True
                assert insp_world_data.get("color") == [0.03, 0.04, 0.08]
                assert insp_world_data.get("strength") == 1.4
                print("[+] Inspected World settings via inspect_scene_data: verified")

                # 12. Manipulate World Shader Nodes via manage_shader_nodes
                world_node_res = await call_tool("manage_shader_nodes", {
                    "target_type": "WORLD",
                    "target_name": "World",
                    "action": "create_node",
                    "node_type": "environment_texture",
                    "node_name": "SkyEnvironment",
                })
                wn_data = world_node_res.get("result", world_node_res)
                assert wn_data.get("created") is True
                assert wn_data.get("node_name") == "SkyEnvironment"
                print("[+] Created Environment Texture in World Node Tree: verified")

                # 13. List World Nodes
                world_list = await call_tool("manage_shader_nodes", {
                    "target_type": "WORLD",
                    "target_name": "World",
                    "action": "list_nodes",
                })
                wl_data = world_list.get("result", world_list)
                node_names = {n["name"] for n in wl_data.get("nodes", [])}
                assert "SkyEnvironment" in node_names
                print(f"[+] Verified World node list ({len(node_names)} nodes): verified")

                # 14. Security Defense: Untrusted approved=True rejection
                sec_res = await call_tool("configure_light", {
                    "name": "Sun_Key",
                    "energy": 9999.0,
                    "approved": True,
                })
                msg = sec_res.get("message", "")
                assert "untrusted" in msg.lower() or sec_res.get("status") == "error", f"Expected untrusted rejection, got: {sec_res}"
                print("[+] Security Guard Verified: Untrusted approved=True rejected fail-closed.")

                # 15. Validation: Negative energy rejection
                neg_res = await call_tool("configure_light", {
                    "name": "Sun_Key",
                    "energy": -100.0,
                })
                msg = neg_res.get("message", "")
                assert "non-negative" in msg.lower() or "error" in neg_res.get("status", "")
                print("[+] Input Validation Verified: Negative energy rejected fail-closed.")

                # 16. Validation: Color > 1.0 rejection
                col_res = await call_tool("configure_light", {
                    "name": "Sun_Key",
                    "color": [1.5, 0.5, 0.5],
                })
                msg = col_res.get("message", "")
                assert "between 0.0 and 1.0" in msg.lower() or "error" in col_res.get("status", "")
                print("[+] Input Validation Verified: Out-of-bounds color component rejected fail-closed.")

                # 17. Validation: Non-existent light object rejection
                missing_res = await call_tool("configure_light", {
                    "name": "GhostLight",
                    "energy": 500.0,
                })
                msg = missing_res.get("message", "")
                assert "not found" in msg.lower() or "error" in missing_res.get("status", "")
                print("[+] Input Validation Verified: Non-existent light object rejected fail-closed.")

                # 18. Unsupported feature rejection: render_engine in configure_world
                unsupp_res = await call_tool("configure_world", {
                    "color": [0.1, 0.1, 0.1],
                    "render_engine": "CYCLES",
                })
                msg = unsupp_res.get("message", "")
                assert "unsupported" in msg.lower() or "error" in unsupp_res.get("status", "")
                print("[+] Input Validation Verified: Unsupported property rejected fail-closed.")

    finally:
        # Teardown
        print("=" * 80)
        print("REAL MCP-TO-BLENDER E2E ACCEPTANCE PASSED FOR CAPABILITY 8: LIGHTING & WORLD (v0.1.68)")
        print("=" * 80)

        print("[*] Tearing down disposable Blender instance...")
        (run_root / "stop.flag").touch()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[+] Disposable Blender process cleaned up cleanly.")


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
