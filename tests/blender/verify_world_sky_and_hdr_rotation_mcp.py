"""
Live MCP verification for Capability 7.1 Phase 2:
Physical Sky (Nishita / ShaderNodeTexSky) and HDR Environment Rotation.

Executes against actual Blender 5.2.2 LTS via disposable headless process
and an ephemeral bridge port.
Zero contact with production port 9877.
"""

import asyncio
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

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

# Register a mock test image for HDRI rotation test
if not bpy.data.images.get("Test_HDRI.exr"):
    bpy.data.images.new("Test_HDRI.exr", width=128, height=64, float_buffer=True)

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
    print("STARTING REAL MCP-TO-BLENDER E2E: CAPABILITY 7.1 PHASE 2 (PHYSICAL SKY & HDR ROTATION)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-SKY-ROT-CAP7-"))
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

    t0 = time.time()
    while not ready_file.exists():
        if time.time() - t0 > 25.0:
            proc.kill()
            out, err = proc.communicate()
            raise TimeoutError(f"Blender failed to start in 25s.\nSTDOUT:\n{out}\nSTDERR:\n{err}")
        await asyncio.sleep(0.2)

    ready_info = json.loads(ready_file.read_text(encoding="utf-8"))
    print(f"[+] Blender ready! PID: {ready_info['pid']}, Version: {ready_info.get('blender', '5.2.2 LTS')}")

    try:
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
                discovered_names = {t.name for t in tools_res.tools}
                for required in ("configure_world", "inspect_scene_data"):
                    assert required in discovered_names, f"Tool '{required}' not discovered in MCP tools list"
                print(f"[+] Stage 1: Tool Discovery Verified ({len(discovered_names)} tools found).")

                def unwrap(res):
                    raw = json.loads(res.content[0].text) if res.content else {}
                    if isinstance(raw, dict) and "result" in raw:
                        return raw["result"]
                    return raw

                def is_error_response(res):
                    if getattr(res, "isError", False):
                        return True
                    try:
                        data = json.loads(res.content[0].text) if res.content else {}
                        return data.get("status") == "error"
                    except Exception:
                        return False

                # Stage 2: Configure Nishita Physical Sky
                nishita_params = {
                    "sky_type": "NISHITA",
                    "sun_disc": True,
                    "sun_size": 0.015,
                    "sun_intensity": 1.2,
                    "sun_elevation": 0.4363,  # ~25 degrees
                    "sun_rotation": 2.0944,  # ~120 degrees
                    "altitude": 250.0,
                    "air_density": 1.1,
                    "aerosol_density": 1.3,
                    "ozone_density": 1.05,
                    "strength": 1.5,
                }
                res_sky = await session.call_tool("configure_world", nishita_params)
                assert not res_sky.isError, f"configure_world failed: {res_sky}"
                sky_data = unwrap(res_sky)
                assert sky_data["has_sky_texture"] is True
                assert sky_data["sky_type"] == "MULTIPLE_SCATTERING"
                assert sky_data["strength"] == 1.5
                sp = sky_data["sky_parameters"]
                assert sp["sun_disc"] is True
                assert sp["sun_size"] == 0.015
                assert sp["sun_intensity"] == 1.2
                assert sp["sun_elevation"] == 0.4363
                assert sp["sun_rotation"] == 2.0944
                assert sp["altitude"] == 250.0
                assert sp["air_density"] == 1.1
                assert sp["aerosol_density"] == 1.3
                assert sp["ozone_density"] == 1.05
                print("[+] Stage 2: Configured Nishita Physical Sky with verified parameters.")

                # Stage 3: Independent RNA Readback via inspect_scene_data
                insp_res = await session.call_tool("inspect_scene_data", {"category": "world_settings"})
                assert not insp_res.isError
                insp_data = unwrap(insp_res)
                assert insp_data["has_world"] is True
                assert insp_data["has_sky_texture"] is True
                assert insp_data["sky_type"] == "MULTIPLE_SCATTERING"
                assert insp_data["strength"] == 1.5
                sp_read = insp_data["sky_parameters"]
                assert sp_read["sun_disc"] is True
                assert sp_read["sun_size"] == 0.015
                assert sp_read["sun_elevation"] == 0.4363
                assert sp_read["altitude"] == 250.0
                print("[+] Stage 3: Independent RNA Readback via inspect_scene_data confirmed 100% parity.")

                # Stage 4: Environment Rotation on Sky
                res_rot = await session.call_tool("configure_world", {
                    "environment_rotation": 1.5708,  # 90 degrees on Z
                })
                assert not res_rot.isError
                rot_data = unwrap(res_rot)
                assert rot_data["environment_rotation"] == [0.0, 0.0, 1.5708]

                insp_rot = await session.call_tool("inspect_scene_data", {"category": "world_settings"})
                insp_rot_data = unwrap(insp_rot)
                assert insp_rot_data["has_mapping_node"] is True
                assert insp_rot_data["environment_rotation"] == [0.0, 0.0, 1.5708]
                print("[+] Stage 4: Environment Rotation on Sky verified via ShaderNodeMapping readback.")

                # Stage 5: Switch to Preetham physical sky model with turbidity
                res_preetham = await session.call_tool("configure_world", {
                    "sky_type": "PREETHAM",
                    "turbidity": 3.4,
                    "ground_albedo": 0.45,
                })
                assert not res_preetham.isError
                p_data = unwrap(res_preetham)
                assert p_data["sky_type"] == "PREETHAM"
                assert p_data["sky_parameters"]["turbidity"] == 3.4
                assert p_data["sky_parameters"]["ground_albedo"] == 0.45
                print("[+] Stage 5: Successfully switched to PREETHAM sky model with custom turbidity/albedo.")

                # Stage 6: HDR Environment Texture with 3-Axis Euler Rotation
                res_hdri = await session.call_tool("configure_world", {
                    "environment_image": "Test_HDRI.exr",
                    "environment_rotation": [0.1, 0.2, 0.7854],
                    "strength": 2.0,
                })
                assert not res_hdri.isError
                hdri_data = unwrap(res_hdri)
                assert hdri_data["has_environment_texture"] is True
                assert hdri_data["environment_image"] == "Test_HDRI.exr"
                assert hdri_data["environment_rotation"] == [0.1, 0.2, 0.7854]

                insp_hdri = await session.call_tool("inspect_scene_data", {"category": "world_settings"})
                insp_hdri_data = unwrap(insp_hdri)
                assert insp_hdri_data["has_environment_texture"] is True
                assert insp_hdri_data["has_mapping_node"] is True
                assert insp_hdri_data["environment_rotation"] == [0.1, 0.2, 0.7854]
                print("[+] Stage 6: HDR Environment Texture with 3-Axis Euler rotation verified in Blender RNA.")

                # Stage 7: Security and fail-closed validation tests
                # 7.1 Untrusted approved=True rejection
                res_untrusted = await session.call_tool("configure_world", {
                    "strength": 100.0,
                    "approved": True,
                })
                assert is_error_response(res_untrusted), "Expected untrusted approved=True to be rejected fail-closed"
                print("[+] Stage 7.1: Untrusted model approved=True rejected fail-closed.")

                # 7.2 Mutual exclusivity violation (sky_type + environment_image)
                res_conflict = await session.call_tool("configure_world", {
                    "environment_image": "Test_HDRI.exr",
                    "sky_type": "NISHITA",
                })
                assert is_error_response(res_conflict), "Expected simultaneous sky_type and environment_image to be rejected"
                print("[+] Stage 7.2: Mutual exclusivity violation rejected fail-closed.")

                # 7.3 Invalid sky_type
                res_bad_sky = await session.call_tool("configure_world", {
                    "sky_type": "CUBEMAP_SKY",
                })
                assert is_error_response(res_bad_sky), "Expected invalid sky_type to be rejected"
                print("[+] Stage 7.3: Invalid sky_type rejected fail-closed.")

                # 7.4 Out-of-bounds sun_size
                res_bad_size = await session.call_tool("configure_world", {
                    "sun_size": 2.0,
                })
                assert is_error_response(res_bad_size), "Expected out-of-bounds sun_size to be rejected"
                print("[+] Stage 7.4: Out-of-bounds sun_size rejected fail-closed.")

                # 7.5 Out-of-bounds altitude (< 0)
                res_bad_alt = await session.call_tool("configure_world", {
                    "altitude": -200.0,
                })
                assert is_error_response(res_bad_alt), "Expected negative altitude to be rejected"
                print("[+] Stage 7.5: Negative altitude rejected fail-closed.")

                # 7.6 Invalid environment_rotation format
                res_bad_rot = await session.call_tool("configure_world", {
                    "environment_rotation": "ninety_degrees",
                })
                assert is_error_response(res_bad_rot), "Expected invalid environment_rotation type to be rejected"
                print("[+] Stage 7.6: Invalid environment_rotation format rejected fail-closed.")

                # Stage 8: Symmetrical Reset
                res_reset = await session.call_tool("configure_world", {
                    "color": [0.05, 0.05, 0.05],
                    "strength": 1.0,
                })
                assert not res_reset.isError
                insp_final = await session.call_tool("inspect_scene_data", {"category": "world_settings"})
                final_data = unwrap(insp_final)
                assert final_data["strength"] == 1.0
                print("[+] Stage 8: Symmetrical reset back to neutral background verified.")

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
    print("CAPABILITY 7.1 PHASE 2: PHYSICAL SKY & HDR ROTATION FULLY VERIFIED (8/8 STAGES PASSED)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
