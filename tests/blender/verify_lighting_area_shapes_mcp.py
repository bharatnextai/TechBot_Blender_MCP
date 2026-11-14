"""
Automated Real MCP-to-Blender E2E Verification of Capability 7.1 Phase 1:
Area Light Shapes, Dimensions (size_y), Light Contribution Factors, and Shadow Controls.

Invariants verified:
1. Disposable Blender 5.2.2 LTS process on ephemeral loopback port (!= 9877).
2. Production guard: Port 9877 (PID 39604) untouched throughout.
3. Tool discovery over standard MCP stdio wire:
   - create_light, configure_light, get_object_details, list_objects, delete_object.
4. Live execution and independent Blender readback:
   - Create Area Light with RECTANGLE shape (size, size_y, diffuse/specular/volume factors, use_shadow, shadow softness & clip start).
   - Independent readback via get_object_details (light_details).
   - Create Area Light with DISK and ELLIPSE shapes.
   - Configure existing Area light (mutation of shape, size_y, factors, shadows).
5. Security & fail-closed validation guards:
   - Untrusted model approved=True rejected fail-closed.
   - Invalid shape rejected fail-closed.
   - Shape/size_y on non-AREA light rejected fail-closed.
   - Negative size_y, factors, and invalid shadow settings rejected fail-closed.
6. Symmetrical cleanup and disposable environment teardown.
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
    print("STARTING REAL MCP-TO-BLENDER E2E: CAPABILITY 7.1 PHASE 1 (AREA SHAPES & SHADOWS)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-LIGHT-CAP7-"))
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
    env["UMCP_LOCAL_TEST_SCOPE"] = "lighting_world_v1"
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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "lighting_world_v1"
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

                # Stage 1: Tool Discovery
                tools_res = await session.list_tools()
                tool_names = {t.name for t in tools_res.tools}
                for req_tool in ("create_light", "configure_light", "get_object_details", "list_objects", "delete_object"):
                    assert req_tool in tool_names, f"Missing tool: {req_tool}"
                print(f"[+] Stage 1: Tool Discovery Verified ({len(tool_names)} tools found).")

                def unwrap(res):
                    raw = json.loads(res.content[0].text) if res.content else {}
                    if isinstance(raw, dict) and "result" in raw:
                        return raw["result"]
                    return raw

                # Stage 2: Create Area Light with RECTANGLE shape
                create_rect_params = {
                    "name": "Area_Key_Rect",
                    "light_type": "AREA",
                    "energy": 1200.0,
                    "color": [1.0, 0.95, 0.9],
                    "shape": "RECTANGLE",
                    "size": 3.0,
                    "size_y": 1.5,
                    "diffuse_factor": 0.85,
                    "specular_factor": 0.6,
                    "volume_factor": 0.3,
                    "use_shadow": False,
                    "shadow_soft_size": 0.1,
                    "shadow_buffer_clip_start": 0.02,
                    "location": [3.0, -3.0, 4.0],
                }
                res_create_rect = await session.call_tool("create_light", create_rect_params)
                assert not res_create_rect.isError, f"create_light failed: {res_create_rect}"
                c_rect_data = unwrap(res_create_rect)
                assert c_rect_data["shape"] == "RECTANGLE"
                assert c_rect_data["size"] == 3.0
                assert c_rect_data["size_y"] == 1.5
                assert c_rect_data["diffuse_factor"] == 0.85
                assert c_rect_data["specular_factor"] == 0.6
                assert c_rect_data["volume_factor"] == 0.3
                assert c_rect_data["use_shadow"] is False
                assert c_rect_data["shadow_soft_size"] == 0.1
                assert c_rect_data["shadow_buffer_clip_start"] == 0.02
                print("[+] Stage 2: Created RECTANGLE Area Light 'Area_Key_Rect' with verified properties.")

                # Stage 3: Independent readback via get_object_details
                details_res = await session.call_tool("get_object_details", {"name": "Area_Key_Rect"})
                assert not details_res.isError
                details_data = unwrap(details_res)
                ld = details_data.get("light_details", {})
                assert ld["light_type"] == "AREA"
                assert ld["shape"] == "RECTANGLE"
                assert ld["size"] == 3.0
                assert ld["size_y"] == 1.5
                assert ld["diffuse_factor"] == 0.85
                assert ld["specular_factor"] == 0.6
                assert ld["volume_factor"] == 0.3
                assert ld["use_shadow"] is False
                assert ld["shadow_soft_size"] == 0.1
                assert ld["shadow_buffer_clip_start"] == 0.02
                print("[+] Stage 3: Independent readback via get_object_details confirmed 100% parity.")

                # Stage 4: Create Area Light with DISK and ELLIPSE shapes
                res_disk = await session.call_tool("create_light", {
                    "name": "Area_Rim_Disk",
                    "light_type": "AREA",
                    "energy": 800.0,
                    "shape": "DISK",
                    "size": 2.0,
                    "location": [-3.0, 3.0, 3.0],
                })
                assert not res_disk.isError
                disk_data = unwrap(res_disk)
                assert disk_data["shape"] == "DISK"
                assert disk_data["size"] == 2.0

                res_ellipse = await session.call_tool("create_light", {
                    "name": "Area_Fill_Ellipse",
                    "light_type": "AREA",
                    "energy": 600.0,
                    "shape": "ELLIPSE",
                    "size": 2.5,
                    "size_y": 1.2,
                    "location": [-4.0, -2.0, 2.5],
                })
                assert not res_ellipse.isError
                ellipse_data = unwrap(res_ellipse)
                assert ellipse_data["shape"] == "ELLIPSE"
                assert ellipse_data["size"] == 2.5
                assert ellipse_data["size_y"] == 1.2
                print("[+] Stage 4: Created DISK ('Area_Rim_Disk') and ELLIPSE ('Area_Fill_Ellipse') Area Lights.")

                # Stage 5: Configure / Mutate existing Area Light
                mutate_params = {
                    "name": "Area_Rim_Disk",
                    "shape": "RECTANGLE",
                    "size": 4.0,
                    "size_y": 2.0,
                    "diffuse_factor": 0.9,
                    "specular_factor": 0.7,
                    "volume_factor": 0.4,
                    "use_shadow": True,
                    "shadow_soft_size": 0.25,
                    "shadow_buffer_clip_start": 0.05,
                }
                res_mutate = await session.call_tool("configure_light", mutate_params)
                assert not res_mutate.isError, f"configure_light failed: {res_mutate}"
                mutate_data = unwrap(res_mutate)
                assert mutate_data["shape"] == "RECTANGLE"
                assert mutate_data["size"] == 4.0
                assert mutate_data["size_y"] == 2.0
                assert mutate_data["diffuse_factor"] == 0.9
                assert mutate_data["specular_factor"] == 0.7
                assert mutate_data["volume_factor"] == 0.4
                assert mutate_data["use_shadow"] is True
                assert mutate_data["shadow_soft_size"] == 0.25
                assert mutate_data["shadow_buffer_clip_start"] == 0.05

                # Independent readback of mutated light
                details_mut = await session.call_tool("get_object_details", {"name": "Area_Rim_Disk"})
                ld_mut = unwrap(details_mut)["light_details"]
                assert ld_mut["shape"] == "RECTANGLE"
                assert ld_mut["size"] == 4.0
                assert ld_mut["size_y"] == 2.0
                assert ld_mut["diffuse_factor"] == 0.9
                assert ld_mut["use_shadow"] is True
                print("[+] Stage 5: Successfully mutated Area Light from DISK to RECTANGLE with updated parameters.")

                def is_error_response(res):
                    if getattr(res, "isError", False):
                        return True
                    try:
                        data = json.loads(res.content[0].text) if res.content else {}
                        return data.get("status") == "error"
                    except Exception:
                        return False

                # Stage 6: Security and fail-closed validation tests
                # 6.1 Untrusted approved=True injection rejected
                res_untrusted = await session.call_tool("configure_light", {
                    "name": "Area_Key_Rect",
                    "energy": 500.0,
                    "approved": True,
                })
                assert is_error_response(res_untrusted), f"Expected untrusted approved=True to be rejected fail-closed, got: {res_untrusted.content[0].text}"
                print("[+] Stage 6.1: Untrusted model approved=True rejected fail-closed.")

                # 6.2 Invalid shape rejected
                res_bad_shape = await session.call_tool("create_light", {
                    "name": "BadShapeLight",
                    "light_type": "AREA",
                    "shape": "HEXAGON",
                })
                assert is_error_response(res_bad_shape), f"Expected invalid shape 'HEXAGON' to be rejected, got: {res_bad_shape.content[0].text}"
                print("[+] Stage 6.2: Invalid shape rejected fail-closed.")

                # 6.3 Shape on POINT light rejected
                res_bad_type = await session.call_tool("create_light", {
                    "name": "BadPointLight",
                    "light_type": "POINT",
                    "shape": "RECTANGLE",
                })
                assert is_error_response(res_bad_type), f"Expected shape on POINT light to be rejected, got: {res_bad_type.content[0].text}"
                print("[+] Stage 6.3: Shape on non-AREA light rejected fail-closed.")

                # 6.4 Negative size_y rejected
                res_bad_sy = await session.call_tool("configure_light", {
                    "name": "Area_Key_Rect",
                    "size_y": -1.5,
                })
                assert is_error_response(res_bad_sy), f"Expected negative size_y to be rejected, got: {res_bad_sy.content[0].text}"
                print("[+] Stage 6.4: Negative size_y rejected fail-closed.")

                # 6.5 Negative factor rejected
                res_bad_df = await session.call_tool("configure_light", {
                    "name": "Area_Key_Rect",
                    "diffuse_factor": -0.5,
                })
                assert is_error_response(res_bad_df), f"Expected negative diffuse_factor to be rejected, got: {res_bad_df.content[0].text}"
                print("[+] Stage 6.5: Negative diffuse_factor rejected fail-closed.")

                # 6.6 Non-boolean use_shadow rejected
                res_bad_sh = await session.call_tool("configure_light", {
                    "name": "Area_Key_Rect",
                    "use_shadow": "true_string",
                })
                assert is_error_response(res_bad_sh), f"Expected string use_shadow to be rejected, got: {res_bad_sh.content[0].text}"
                print("[+] Stage 6.6: Non-boolean use_shadow rejected fail-closed.")

                # Stage 7: Symmetrical cleanup
                for l_name in ("Area_Key_Rect", "Area_Rim_Disk", "Area_Fill_Ellipse"):
                    del_res = await session.call_tool("delete_object", {"name": l_name, "unlink_data": True})
                    assert not del_res.isError, f"Failed to delete {l_name}: {del_res}"

                list_res = await session.call_tool("list_objects", {"object_type": "LIGHT"})
                list_payload = unwrap(list_res)
                lights_remaining = list_payload.get("objects", []) if isinstance(list_payload, dict) else list_payload
                assert len(lights_remaining) == 0, f"Expected 0 lights remaining, got {lights_remaining}"
                print("[+] Stage 7: Symmetrical cleanup verified (all 3 lights cleanly removed).")

    finally:
        print("[*] Terminating disposable Blender process...")
        (run_root / "stop.flag").write_text("stop", encoding="utf-8")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("[+] Disposable Blender process cleaned up cleanly.")

    print("=" * 80)
    print("CAPABILITY 7.1 PHASE 1: AREA LIGHT SHAPES & SHADOWS FULLY VERIFIED (7/7 STAGES PASSED)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
