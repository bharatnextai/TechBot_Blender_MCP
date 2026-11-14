"""
Live MCP verification for Capability 7.3 Phase 1:
Production Rendering, Color Management & Alpha Output.

Executes against actual Blender 5.2.2 LTS via disposable headless process
and an ephemeral bridge port.
Zero contact with production port 9877.
"""

import asyncio
import json
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
    print("STARTING REAL MCP-TO-BLENDER E2E: CAPABILITY 7.3 PHASE 1 (COLOR MGMT, ALPHA & CYCLES)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-RENDER-CAP7-"))
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
    env["UMCP_LOCAL_TEST_SCOPE"] = "render_settings_v1"
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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "render_settings_v1"
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
                for required in ("configure_render_settings", "inspect_scene_data"):
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

                # Stage 2: Film Transparency (Alpha output)
                res_trans = await session.call_tool("configure_render_settings", {
                    "film_transparent": True,
                })
                assert not is_error_response(res_trans), f"Failed to set film_transparent: {res_trans}"
                data_trans = unwrap(res_trans)
                assert data_trans["film_transparent"] is True, f"Expected film_transparent True, got {data_trans}"

                # Verify evaluated RNA via inspect_scene_data
                res_insp1 = await session.call_tool("inspect_scene_data", {"category": "render_settings"})
                assert not is_error_response(res_insp1)
                data_insp1 = unwrap(res_insp1)
                assert data_insp1["film_transparent"] is True
                print("[+] Stage 2: Film transparency for alpha output verified in Blender RNA.")

                # Stage 3: Color Management (AgX + Medium High Contrast + Exposure)
                cm_params = {
                    "view_transform": "AgX",
                    "look": "Medium High Contrast",
                    "exposure": 0.75,
                }
                res_cm = await session.call_tool("configure_render_settings", cm_params)
                assert not is_error_response(res_cm), f"Failed to set color management: {res_cm}"
                data_cm = unwrap(res_cm)
                assert data_cm["view_transform"] == "AgX"
                assert data_cm["look"] in ("Medium High Contrast", "AgX - Medium High Contrast")
                assert abs(data_cm["exposure"] - 0.75) < 1e-4

                # RNA inspection
                res_insp2 = await session.call_tool("inspect_scene_data", {"category": "render_settings"})
                data_insp2 = unwrap(res_insp2)
                assert data_insp2["view_transform"] == "AgX"
                assert data_insp2["look"] in ("Medium High Contrast", "AgX - Medium High Contrast")
                assert abs(data_insp2["exposure"] - 0.75) < 1e-4
                assert data_insp2["color_management"]["view_transform"] == "AgX"
                print("[+] Stage 3: AgX view transform, look, and exposure verified in Blender RNA.")

                # Stage 4: Color Management (Filmic + High Contrast + Negative Exposure via nested dict)
                cm_nested = {
                    "color_management": {
                        "view_transform": "Filmic",
                        "look": "High Contrast",
                        "exposure": -1.25,
                    }
                }
                res_cm2 = await session.call_tool("configure_render_settings", cm_nested)
                assert not is_error_response(res_cm2), f"Failed nested color management: {res_cm2}"
                data_cm2 = unwrap(res_cm2)
                assert data_cm2["view_transform"] == "Filmic"
                assert data_cm2["look"] == "High Contrast"
                assert abs(data_cm2["exposure"] - (-1.25)) < 1e-4
                print("[+] Stage 4: Nested color management configuration verified.")

                # Stage 5: Cycles Denoising with OPENIMAGEDENOISE
                cycles_denoise = {
                    "engine": "CYCLES",
                    "use_denoising": True,
                    "denoiser": "OPENIMAGEDENOISE",
                }
                res_denoise = await session.call_tool("configure_render_settings", cycles_denoise)
                assert not is_error_response(res_denoise), f"Failed Cycles denoising: {res_denoise}"
                data_denoise = unwrap(res_denoise)
                assert data_denoise["engine"] == "CYCLES"
                assert data_denoise["use_denoising"] is True
                assert data_denoise["denoiser"] == "OPENIMAGEDENOISE"

                # RNA inspection
                res_insp3 = await session.call_tool("inspect_scene_data", {"category": "render_settings"})
                data_insp3 = unwrap(res_insp3)
                assert data_insp3["engine"] == "CYCLES"
                assert data_insp3["cycles"]["use_denoising"] is True
                assert data_insp3["cycles"]["denoiser"] == "OPENIMAGEDENOISE"
                print("[+] Stage 5: Cycles denoising with OPENIMAGEDENOISE verified in Blender RNA.")

                # Stage 6: Cycles Light-Path Bounce Limits
                bounces_params = {
                    "max_bounces": 16,
                    "diffuse_bounces": 6,
                    "glossy_bounces": 6,
                    "transmission_bounces": 12,
                    "volume_bounces": 2,
                    "transparent_max_bounces": 10,
                }
                res_bounces = await session.call_tool("configure_render_settings", bounces_params)
                assert not is_error_response(res_bounces), f"Failed bounce limits: {res_bounces}"
                data_bounces = unwrap(res_bounces)
                assert data_bounces["max_bounces"] == 16
                assert data_bounces["diffuse_bounces"] == 6
                assert data_bounces["glossy_bounces"] == 6
                assert data_bounces["transmission_bounces"] == 12
                assert data_bounces["volume_bounces"] == 2
                assert data_bounces["transparent_max_bounces"] == 10

                # RNA inspection
                res_insp4 = await session.call_tool("inspect_scene_data", {"category": "render_settings"})
                data_insp4 = unwrap(res_insp4)
                cyc_info = data_insp4["cycles"]
                assert cyc_info["max_bounces"] == 16
                assert cyc_info["diffuse_bounces"] == 6
                assert cyc_info["glossy_bounces"] == 6
                assert cyc_info["transmission_bounces"] == 12
                assert cyc_info["volume_bounces"] == 2
                assert cyc_info["transparent_max_bounces"] == 10
                print("[+] Stage 6: Cycles light-path bounce limits verified in Blender RNA.")

                # Stage 7: Fail-Closed Security & Parameter Bounds Rejection
                # 7a: Invalid view_transform
                res_bad_vt = await session.call_tool("configure_render_settings", {
                    "view_transform": "NonExistentTransformXYZ",
                })
                assert is_error_response(res_bad_vt), "Expected error for invalid view_transform"
                print("[+] Stage 7a: Invalid view_transform rejected fail-closed.")

                # 7b: Invalid look
                res_bad_look = await session.call_tool("configure_render_settings", {
                    "look": "UltraInsaneContrast",
                })
                assert is_error_response(res_bad_look), "Expected error for invalid look"
                print("[+] Stage 7b: Invalid look rejected fail-closed.")

                # 7c: Out-of-bounds exposure
                res_bad_exp = await session.call_tool("configure_render_settings", {
                    "exposure": 100.0,
                })
                assert is_error_response(res_bad_exp), "Expected error for out-of-bounds exposure"
                print("[+] Stage 7c: Out-of-bounds exposure rejected fail-closed.")

                # 7d: Invalid denoiser
                res_bad_dn = await session.call_tool("configure_render_settings", {
                    "denoiser": "UNKNOWN_DENOISER",
                })
                assert is_error_response(res_bad_dn), "Expected error for invalid denoiser"
                print("[+] Stage 7d: Invalid denoiser rejected fail-closed.")

                # 7e: Out-of-bounds bounces
                res_bad_mb = await session.call_tool("configure_render_settings", {
                    "max_bounces": 5000,
                })
                assert is_error_response(res_bad_mb), "Expected error for out-of-bounds max_bounces"
                print("[+] Stage 7e: Out-of-bounds max_bounces rejected fail-closed.")

                # 7f: Non-boolean film_transparent
                res_bad_ft = await session.call_tool("configure_render_settings", {
                    "film_transparent": "invalid_boolean_string",
                })
                assert is_error_response(res_bad_ft), "Expected error for non-boolean film_transparent"
                print("[+] Stage 7f: Non-boolean film_transparent rejected fail-closed.")

                # Stage 8: Symmetrical Reset to Neutral Defaults
                reset_params = {
                    "film_transparent": False,
                    "view_transform": "Standard",
                    "look": "None",
                    "exposure": 0.0,
                }
                res_reset = await session.call_tool("configure_render_settings", reset_params)
                assert not is_error_response(res_reset)
                res_insp_final = await session.call_tool("inspect_scene_data", {"category": "render_settings"})
                final_data = unwrap(res_insp_final)
                assert final_data["film_transparent"] is False
                assert final_data["view_transform"] == "Standard"
                assert final_data["look"] == "None"
                assert abs(final_data["exposure"]) < 1e-4
                print("[+] Stage 8: Symmetrical reset to neutral defaults verified.")

        print("\n" + "=" * 80)
        print("ALL 8 MCP E2E STAGES PASSED FOR CAPABILITY 7.3 PHASE 1!")
        print("=" * 80)

    finally:
        (run_root / "stop.flag").write_text("1")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())

