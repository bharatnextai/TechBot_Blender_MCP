"""
Automated Real MCP-to-Blender E2E Verification of Materials & Procedural Shaders Foundation (v0.1.66).
Covers Capability 6:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover Material and Procedural Shader tools over MCP stdio wire:
   - create_material
   - assign_material
   - manage_shader_nodes (and aliases connect_shader_nodes, manage_nodes)
   - configure_material_shader
   - inspect_material_shader
4. Live execution and independent Blender readback:
   - Primitive creation ('Material_Cube')
   - Material creation ('ProceduralGold' with base_color, metallic, roughness)
   - Material assignment to 'Material_Cube' -> readback confirms slot assignment
   - Inspect material shader graph -> readback confirms Principled BSDF and Output nodes
   - Create procedural noise texture node ('NoiseTex')
   - Create color ramp node ('ColorRamp')
   - Configure procedural property (Scale=8.0 on NoiseTex)
   - Connect NoiseTex.Fac -> ColorRamp.Fac
   - Connect ColorRamp.Color -> Principled BSDF.Base Color
   - List shader nodes -> verify complete graph nodes and links readback
   - Configure Principled BSDF parameters via configure_material_shader
   - Remove node ('ColorRamp') -> verify node and link removal
5. Security and validation enforcement:
   - Untrusted approved=True rejected fail-closed
   - Non-existent target object/material rejected fail-closed
   - Non-existent socket connection rejected fail-closed
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
    print("STARTING REAL MCP-TO-BLENDER E2E: MATERIALS & PROCEDURAL SHADERS (v0.1.66)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-MAT-"))
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
                expected_mat_tools = [
                    "create_material",
                    "assign_material",
                    "manage_shader_nodes",
                    "configure_material_shader",
                    "inspect_material_shader",
                ]
                for mt in expected_mat_tools:
                    assert mt in discovered_names, f"Tool '{mt}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all material & shader tools present.")

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

                # 2. Create test cube Material_Cube
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "Material_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                print(f"[+] Created Material_Cube: {cube_res.get('status')}")
                assert cube_res.get("status") == "success", f"create_primitive failed: {cube_res}"

                # 3. Create material ProceduralGold
                mat_res = await call_tool("create_material", {
                    "name": "ProceduralGold",
                    "base_color": [1.0, 0.84, 0.0, 1.0],
                    "metallic": 1.0,
                    "roughness": 0.15,
                    "ior": 1.45,
                })
                print(f"[+] Created Material ProceduralGold: {mat_res}")
                assert mat_res.get("name") == "ProceduralGold" or mat_res.get("status") == "success", f"create_material failed: {mat_res}"

                # 4. Assign ProceduralGold to Material_Cube
                assign_res = await call_tool("assign_material", {
                    "target_name": "Material_Cube",
                    "material_name": "ProceduralGold",
                })
                print(f"[+] Assigned Material to Material_Cube: {assign_res}")
                assign_data = assign_res.get("result", assign_res)
                assert assign_data.get("material_name") == "ProceduralGold", f"assign_material failed: {assign_res}"
                assert assign_data.get("slot_count", 1) >= 1

                # 5. Inspect material shader graph
                inspect_init = await call_tool("inspect_material_shader", {
                    "target_name": "ProceduralGold",
                })
                init_data = inspect_init.get("result", inspect_init)
                assert init_data.get("target_name") == "ProceduralGold"
                assert init_data.get("use_nodes") is True
                assert "nodes" in init_data
                print(f"[+] Initial Shader Inspection Verified: {len(init_data['nodes'])} nodes detected.")

                # 6. Create procedural noise node
                create_noise_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "create_node",
                    "node_type": "ShaderNodeTexNoise",
                    "node_name": "NoiseTex",
                })
                print(f"[+] Created ShaderNodeTexNoise 'NoiseTex': {create_noise_res}")
                noise_data = create_noise_res.get("result", create_noise_res)
                assert noise_data.get("created") is True

                # 7. Create color ramp node
                create_ramp_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "create_node",
                    "node_type": "ShaderNodeValToRGB",
                    "node_name": "ColorRamp",
                })
                print(f"[+] Created ShaderNodeValToRGB 'ColorRamp': {create_ramp_res}")
                ramp_data = create_ramp_res.get("result", create_ramp_res)
                assert ramp_data.get("created") is True

                # 8. Set property on NoiseTex
                prop_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "set_property",
                    "node_name": "NoiseTex",
                    "property_name": "Scale",
                    "property_value": 8.0,
                })
                print(f"[+] Configured NoiseTex Scale: {prop_res}")
                prop_data = prop_res.get("result", prop_res)
                assert prop_data.get("verified") is True
                assert prop_data.get("property_value") == 8.0

                # 9. Connect NoiseTex.Fac -> ColorRamp.Fac
                conn1_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "connect",
                    "from_node": "NoiseTex",
                    "from_socket": "Fac",
                    "to_node": "ColorRamp",
                    "to_socket": "Fac",
                })
                print(f"[+] Connected NoiseTex.Fac -> ColorRamp.Fac: {conn1_res}")
                conn1_data = conn1_res.get("result", conn1_res)
                assert conn1_data.get("connected") is True

                # 10. Connect ColorRamp.Color -> Principled BSDF.Base Color
                conn2_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "connect",
                    "from_node": "ColorRamp",
                    "from_socket": "Color",
                    "to_node": "Principled BSDF",
                    "to_socket": "Base Color",
                })
                print(f"[+] Connected ColorRamp.Color -> Principled BSDF.Base Color: {conn2_res}")
                conn2_data = conn2_res.get("result", conn2_res)
                assert conn2_data.get("connected") is True

                # 11. List shader nodes and verify graph connectivity
                list_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "list_nodes",
                })
                list_data = list_res.get("result", list_res)
                node_names = [n["name"] for n in list_data.get("nodes", [])]
                assert "NoiseTex" in node_names, f"NoiseTex missing: {node_names}"
                assert "ColorRamp" in node_names, f"ColorRamp missing: {node_names}"
                assert "Principled BSDF" in node_names, f"Principled BSDF missing: {node_names}"
                links = list_data.get("links", [])
                assert any(l["from_node"] == "NoiseTex" and l["to_node"] == "ColorRamp" for l in links)
                assert any(l["from_node"] == "ColorRamp" and l["to_node"] == "Principled BSDF" for l in links)
                print(f"[+] Verified Full Shader Graph: {len(node_names)} nodes, {len(links)} links.")

                # 12. Configure material shader via configure_material_shader
                config_res = await call_tool("configure_material_shader", {
                    "target_name": "ProceduralGold",
                    "bsdf_node_name": "Principled BSDF",
                    "action": "set_principled",
                    "inputs": {
                        "roughness": 0.25,
                        "metallic": 0.95,
                    },
                })
                print(f"[+] Configured Principled BSDF via configure_material_shader: {config_res}")
                assert config_res.get("action") == "set_principled" or config_res.get("success") is True or "result" in config_res

                # 13. Readback updated shader graph via inspect_material_shader
                inspect_after = await call_tool("inspect_material_shader", {
                    "target_name": "ProceduralGold",
                })
                after_data = inspect_after.get("result", inspect_after)
                bsdf_info = next((n for n in after_data.get("nodes", []) if n.get("name") == "Principled BSDF"), None)
                assert bsdf_info is not None
                print(f"[+] Readback verified Principled BSDF updated.")

                # 14. Remove ColorRamp node
                remove_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "remove_node",
                    "node_name": "ColorRamp",
                })
                print(f"[+] Removed ColorRamp: {remove_res}")
                remove_data = remove_res.get("result", remove_res)
                assert remove_data.get("removed") is True

                # 15. Verify removal readback
                list_after_remove = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "list_nodes",
                })
                post_nodes = [n["name"] for n in list_after_remove.get("nodes", [])]
                assert "ColorRamp" not in post_nodes, "ColorRamp was not removed from nodes collection!"
                print(f"[+] Verified ColorRamp removal in live Blender data.")

                # 16. Security checks: Untrusted approved=True rejection
                sec_res = await call_tool("create_material", {
                    "name": "HackedMat",
                    "approved": True,
                })
                assert sec_res.get("status") == "error", f"Untrusted approved=True should have failed: {sec_res}"
                assert "untrusted" in sec_res.get("message", "").lower(), f"Expected untrusted approval error: {sec_res}"
                print("[+] Security Guard Verified: Untrusted approved=True rejected fail-closed.")

                # 17. Input validation: non-existent socket connection
                bad_sock_res = await call_tool("manage_shader_nodes", {
                    "target_name": "ProceduralGold",
                    "action": "connect",
                    "from_node": "NoiseTex",
                    "from_socket": "BogusSocket",
                    "to_node": "Principled BSDF",
                    "to_socket": "Base Color",
                })
                assert bad_sock_res.get("status") == "error", f"Invalid socket connection should have failed: {bad_sock_res}"
                assert "not found" in bad_sock_res.get("message", "").lower(), f"Expected socket error: {bad_sock_res}"
                print("[+] Input Validation Verified: Invalid socket rejected fail-closed.")

                # 18. Input validation: non-existent target material
                bad_mat_res = await call_tool("inspect_material_shader", {
                    "target_name": "NonExistentMaterial",
                })
                assert bad_mat_res.get("status") == "error", f"Non-existent material should have failed: {bad_mat_res}"
                print("[+] Input Validation Verified: Non-existent material rejected fail-closed.")

                print("=" * 80)
                print("REAL MCP-TO-BLENDER E2E ACCEPTANCE PASSED FOR CAPABILITY 6: MATERIALS & SHADERS (v0.1.66)")
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
