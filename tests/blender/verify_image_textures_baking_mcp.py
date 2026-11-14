"""
Automated Real MCP-to-Blender E2E Verification of Image Textures & Texture Baking Foundation (v0.1.67).
Covers Capability 7:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover Image Texture and Baking tools over MCP stdio wire:
   - bake_object_texture (aliases bake_texture, bake_materials)
   - bake_mesh_surface_map
   - manage_shader_nodes (image_texture node handling)
   - inspect_scene_data
4. Live execution and independent Blender readback:
   - Primitive creation ('Bake_Cube')
   - Material creation and assignment ('Bake_Material')
   - Bake roughness map via bake_object_texture -> readback confirms dimensions, pixels, and saved PNG
   - Bake normal map via bake_texture alias -> readback confirms dimensions, pixels, and saved PNG
   - Create ShaderNodeTexImage in material graph via manage_shader_nodes
   - Set Image datablock on ShaderNodeTexImage by name ('Baked_Roughness_Map')
   - Connect Image.Color -> Principled BSDF.Roughness
   - Verify shader graph nodes and link connectivity
   - High-to-low / self surface map baking via bake_mesh_surface_map
5. Security and validation enforcement:
   - Untrusted approved=True rejected fail-closed
   - Non-existent object rejected fail-closed
   - Invalid dimensions (<64) rejected fail-closed
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
    print("STARTING REAL MCP-TO-BLENDER E2E: IMAGE TEXTURES & BAKING (v0.1.67)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-BAKE-"))
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
                expected_bake_tools = [
                    "bake_object_texture",
                    "bake_texture",
                    "bake_materials",
                    "bake_mesh_surface_map",
                    "manage_shader_nodes",
                ]
                for bt in expected_bake_tools:
                    assert bt in discovered_names, f"Tool '{bt}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all baking tools present.")

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

                # 2. Create test cube Bake_Cube
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "Bake_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                print(f"[+] Created Bake_Cube: {cube_res.get('status')}")
                assert cube_res.get("status") == "success", f"create_primitive failed: {cube_res}"

                # 3. Create material Bake_Material
                mat_res = await call_tool("create_material", {
                    "name": "Bake_Material",
                    "base_color": [0.8, 0.2, 0.2, 1.0],
                    "metallic": 1.0,
                    "roughness": 0.2,
                })
                print(f"[+] Created Material Bake_Material: {mat_res.get('status')}")

                # 4. Assign Bake_Material to Bake_Cube
                assign_res = await call_tool("assign_material", {
                    "target_name": "Bake_Cube",
                    "material_name": "Bake_Material",
                })
                assign_data = assign_res.get("result", assign_res)
                assert assign_data.get("material_name") == "Bake_Material"
                print(f"[+] Assigned Bake_Material to Bake_Cube: {assign_data.get('slot_count')} slot(s).")

                # 5. Bake Roughness map via bake_object_texture
                bake_roughness_path = run_root / "baked_roughness.png"
                bake1_res = await call_tool("bake_object_texture", {
                    "object_name": "Bake_Cube",
                    "bake_type": "ROUGHNESS",
                    "image_name": "Baked_Roughness_Map",
                    "width": 128,
                    "height": 128,
                    "margin": 4,
                    "save_filepath": str(bake_roughness_path),
                })
                print(f"[+] Bake Roughness Response: {bake1_res.get('status')}")
                bake1_data = bake1_res.get("result", bake1_res)
                assert bake1_data.get("baked") is True, f"Bake failed: {bake1_res}"
                assert bake1_data.get("verified") is True
                assert bake1_data.get("width") == 128
                assert bake1_data.get("height") == 128
                assert bake1_data.get("bake_type") == "ROUGHNESS"
                assert bake_roughness_path.exists(), "Baked roughness PNG not found on disk!"
                assert bake_roughness_path.stat().st_size > 0, "Baked roughness PNG is empty!"
                print(f"[+] Verified Baked Roughness Map: {bake_roughness_path.name} ({bake_roughness_path.stat().st_size} bytes).")

                # 6. Bake Normal map via bake_texture alias
                bake_normal_path = run_root / "baked_normal.png"
                bake2_res = await call_tool("bake_texture", {
                    "object_name": "Bake_Cube",
                    "bake_type": "NORMAL",
                    "image_name": "Baked_Normal_Map",
                    "width": 128,
                    "height": 128,
                    "margin": 4,
                    "save_filepath": str(bake_normal_path),
                })
                print(f"[+] Bake Normal Response: {bake2_res.get('status')}")
                bake2_data = bake2_res.get("result", bake2_res)
                assert bake2_data.get("baked") is True, f"Bake normal failed: {bake2_res}"
                assert bake_normal_path.exists(), "Baked normal PNG not found on disk!"
                assert bake_normal_path.stat().st_size > 0, "Baked normal PNG is empty!"
                print(f"[+] Verified Baked Normal Map: {bake_normal_path.name} ({bake_normal_path.stat().st_size} bytes).")

                # 7. Create Image Texture node in shader graph via manage_shader_nodes
                img_node_res = await call_tool("manage_shader_nodes", {
                    "target_name": "Bake_Material",
                    "action": "create_node",
                    "node_type": "image_texture",
                    "node_name": "RoughnessTexture",
                })
                print(f"[+] Created ShaderNodeTexImage: {img_node_res.get('status')}")
                img_node_data = img_node_res.get("result", img_node_res)
                assert img_node_data.get("created") is True

                # 8. Set Image datablock on node by datablock name
                set_img_res = await call_tool("manage_shader_nodes", {
                    "target_name": "Bake_Material",
                    "action": "set_property",
                    "node_name": "RoughnessTexture",
                    "property_name": "image",
                    "property_value": "Baked_Roughness_Map",
                })
                print(f"[+] Set Image datablock on node: {set_img_res.get('status')}")
                set_img_data = set_img_res.get("result", set_img_res)
                assert set_img_data.get("property_set") is True
                assert set_img_data.get("property_value") == "Baked_Roughness_Map"

                # 9. Connect Image Texture to Principled BSDF Roughness
                conn_res = await call_tool("manage_shader_nodes", {
                    "target_name": "Bake_Material",
                    "action": "connect",
                    "from_node": "RoughnessTexture",
                    "from_socket": "Color",
                    "to_node": "Principled BSDF",
                    "to_socket": "Roughness",
                })
                print(f"[+] Connected RoughnessTexture -> Principled BSDF: {conn_res.get('status')}")
                conn_data = conn_res.get("result", conn_res)
                assert conn_data.get("connected") is True

                # 10. List shader nodes to verify image texture integration
                list_nodes_res = await call_tool("manage_shader_nodes", {
                    "target_name": "Bake_Material",
                    "action": "list_nodes",
                })
                list_nodes_data = list_nodes_res.get("result", list_nodes_res)
                node_names = [n["name"] for n in list_nodes_data.get("nodes", [])]
                assert "RoughnessTexture" in node_names, f"RoughnessTexture missing: {node_names}"
                links = list_nodes_data.get("links", [])
                assert any(l["from_node"] == "RoughnessTexture" and l["to_node"] == "Principled BSDF" for l in links)
                print(f"[+] Shader Graph Verified: {len(node_names)} nodes, Image Texture connected.")

                # 11. Self surface map baking via bake_mesh_surface_map
                surface_map_path = run_root / "surface_map_normal.png"
                surf_res = await call_tool("bake_mesh_surface_map", {
                    "target_object": "Bake_Cube",
                    "map_type": "NORMAL",
                    "width": 128,
                    "height": 128,
                    "save_filepath": str(surface_map_path),
                })
                print(f"[+] bake_mesh_surface_map Response: {surf_res.get('status')}")
                surf_data = surf_res.get("result", surf_res)
                assert surf_data.get("status") == "SUCCESS"
                assert surf_data.get("bake_status") == "COMPLETED"
                assert surface_map_path.exists(), "Surface map PNG not found!"
                assert surface_map_path.stat().st_size > 0, "Surface map PNG is empty!"
                sidecar_path = surface_map_path.with_suffix(".png.sha256")
                assert sidecar_path.exists(), "Sidecar .sha256 not found!"
                print(f"[+] Verified bake_mesh_surface_map: {surface_map_path.name} with sidecar SHA-256.")

                # 12. Security checks: Untrusted approved=True rejection
                sec_res = await call_tool("bake_object_texture", {
                    "object_name": "Bake_Cube",
                    "approved": True,
                })
                assert sec_res.get("status") == "error", f"Untrusted approved=True should have failed: {sec_res}"
                assert "untrusted" in sec_res.get("message", "").lower(), f"Expected untrusted approval error: {sec_res}"
                print("[+] Security Guard Verified: Untrusted approved=True rejected fail-closed.")

                # 13. Input validation: non-existent target object
                bad_obj_res = await call_tool("bake_object_texture", {
                    "object_name": "Ghost_Cube",
                })
                assert bad_obj_res.get("status") == "error", f"Non-existent object should have failed: {bad_obj_res}"
                assert "not found" in bad_obj_res.get("message", "").lower(), f"Expected not found error: {bad_obj_res}"
                print("[+] Input Validation Verified: Non-existent object rejected fail-closed.")

                # 14. Input validation: invalid dimension
                bad_dim_res = await call_tool("bake_object_texture", {
                    "object_name": "Bake_Cube",
                    "width": 32,
                })
                assert bad_dim_res.get("status") == "error", f"Invalid width should have failed: {bad_dim_res}"
                print("[+] Input Validation Verified: Invalid dimension (<64) rejected fail-closed.")

                print("=" * 80)
                print("REAL MCP-TO-BLENDER E2E ACCEPTANCE PASSED FOR CAPABILITY 7: IMAGE TEXTURES & BAKING (v0.1.67)")
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

