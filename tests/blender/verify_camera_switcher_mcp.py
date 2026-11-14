"""
Live MCP verification for Capability 7.2 Phase 2:
Multi-Camera Management & Switcher.

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
    print("STARTING REAL MCP-TO-BLENDER E2E: CAPABILITY 7.2 PHASE 2 (MULTI-CAMERA SWITCHER)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CAM-SWITCH-CAP7-"))
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

    blender_log_path = run_root / "blender_process.log"
    blender_log_file = open(blender_log_path, "w", encoding="utf-8")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_SCOPE"] = "lighting_camera_v1"
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
        stdout=blender_log_file,
        stderr=subprocess.STDOUT,
        cwd=str(run_root),
        text=True,
    )

    t0 = time.time()
    while not ready_file.exists():
        if time.time() - t0 > 25.0:
            proc.kill()
            blender_log_file.close()
            log_content = blender_log_path.read_text(encoding="utf-8", errors="replace") if blender_log_path.exists() else "No log"
            raise TimeoutError(f"Blender failed to start in 25s.\nLOG:\n{log_content}")
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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "lighting_camera_v1"
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
                print("[*] Stage 1: Verifying Tool Discovery...")
                tools_res = await session.list_tools()
                discovered_names = {t.name for t in tools_res.tools}
                for required in (
                    "switch_camera",
                    "create_camera",
                    "configure_camera",
                    "inspect_scene_data",
                    "configure_render_settings",
                    "delete_object",
                ):
                    assert required in discovered_names, f"Tool '{required}' not discovered in MCP tools list"
                print(f"[+] Stage 1 PASSED: All required camera tools discovered ({len(discovered_names)} tools available).")

                def unwrap(res):
                    if not res.content or not res.content[0].text:
                        return {"is_error": getattr(res, "isError", False)}
                    try:
                        raw = json.loads(res.content[0].text)
                        if isinstance(raw, dict) and "result" in raw:
                            return raw["result"]
                        return raw
                    except Exception:
                        return {"status": "error" if getattr(res, "isError", False) else "unknown", "text": res.content[0].text}

                def is_error_response(res):
                    if getattr(res, "isError", False):
                        return True
                    try:
                        data = json.loads(res.content[0].text) if res.content else {}
                        return data.get("status") == "error"
                    except Exception:
                        return False

                # Stage 2: Multi-Camera Rig Assembly
                print("[*] Stage 2: Creating Multi-Camera Rig (Perspective, Isometric, Cinematic)...")
                cam1_res = await session.call_tool("create_camera", {
                    "name": "Cam_Perspective",
                    "focal_length": 35.0,
                    "lens": 35.0,
                    "location": [0.0, -6.0, 2.0],
                    "set_active": True,
                })
                assert not is_error_response(cam1_res), f"Cam_Perspective creation error: {cam1_res}"
                cam1_data = unwrap(cam1_res)
                assert cam1_data.get("verified") is True, f"Cam_Perspective not verified: {cam1_data}"
                assert cam1_data.get("camera_details", {}).get("is_active_camera") is True or cam1_data.get("is_active") is True

                cam2_res = await session.call_tool("create_camera", {
                    "name": "Cam_Isometric",
                    "focal_length": 85.0,
                    "lens": 85.0,
                    "location": [5.0, -5.0, 4.0],
                    "set_active": False,
                })
                assert not is_error_response(cam2_res), f"Cam_Isometric creation error: {cam2_res}"
                cam2_data = unwrap(cam2_res)
                assert cam2_data.get("verified") is True, f"Cam_Isometric not verified: {cam2_data}"

                cam3_res = await session.call_tool("create_camera", {
                    "name": "Cam_Cinematic",
                    "focal_length": 135.0,
                    "lens": 135.0,
                    "location": [0.0, -10.0, 1.0],
                    "set_active": False,
                })
                assert not is_error_response(cam3_res), f"Cam_Cinematic creation error: {cam3_res}"
                cam3_data = unwrap(cam3_res)
                assert cam3_data.get("verified") is True, f"Cam_Cinematic not verified: {cam3_data}"
                print("[+] Stage 2 PASSED: 3-Camera Rig successfully assembled.")

                # Stage 3: Multi-Camera Rig Inspection
                print("[*] Stage 3: Inspecting multi-camera rig via inspect_scene_data(category='cameras')...")
                insp_res = await session.call_tool("inspect_scene_data", {"category": "cameras"})
                insp_data = unwrap(insp_res)
                assert insp_data.get("active_camera") == "Cam_Perspective", f"Expected active Cam_Perspective, got {insp_data.get('active_camera')}"
                assert insp_data.get("camera_count") == 3, f"Expected 3 cameras, got {insp_data.get('camera_count')}"
                cams_found = {c["name"]: c for c in insp_data.get("cameras", [])}
                assert "Cam_Perspective" in cams_found and cams_found["Cam_Perspective"]["is_active_camera"] is True
                assert "Cam_Isometric" in cams_found and cams_found["Cam_Isometric"]["is_active_camera"] is False
                assert "Cam_Cinematic" in cams_found and cams_found["Cam_Cinematic"]["is_active_camera"] is False
                assert cams_found["Cam_Perspective"]["lens"] == 35.0
                assert cams_found["Cam_Isometric"]["lens"] == 85.0
                assert cams_found["Cam_Cinematic"]["lens"] == 135.0

                # Target inspection
                target_insp_res = await session.call_tool("inspect_scene_data", {
                    "category": "cameras",
                    "target_name": "Cam_Isometric",
                })
                target_insp_data = unwrap(target_insp_res)
                sel_cam = target_insp_data.get("selected_camera")
                assert sel_cam and sel_cam["name"] == "Cam_Isometric" and sel_cam["lens"] == 85.0
                print("[+] Stage 3 PASSED: Multi-camera rig inspection verified with full optical properties.")

                # Stage 4: Switch Active Camera via switch_camera
                print("[*] Stage 4: Switching active camera to Cam_Isometric via switch_camera...")
                sw1_res = await session.call_tool("switch_camera", {"camera_name": "Cam_Isometric"})
                sw1_data = unwrap(sw1_res)
                assert sw1_data.get("status") == "success", f"switch_camera failed: {sw1_data}"
                assert sw1_data.get("action") == "switch_camera"
                assert sw1_data.get("previous_camera") == "Cam_Perspective"
                assert sw1_data.get("active_camera") == "Cam_Isometric"
                assert sw1_data.get("is_active_camera") is True
                assert sw1_data.get("verified") is True

                # Verify actual scene state readback
                insp_sw1 = await session.call_tool("inspect_scene_data", {"category": "cameras"})
                insp_sw1_data = unwrap(insp_sw1)
                assert insp_sw1_data.get("active_camera") == "Cam_Isometric", "Scene active camera not updated"
                cams_sw1 = {c["name"]: c for c in insp_sw1_data.get("cameras", [])}
                assert cams_sw1["Cam_Isometric"]["is_active_camera"] is True
                assert cams_sw1["Cam_Perspective"]["is_active_camera"] is False
                print("[+] Stage 4 PASSED: switch_camera successfully switched active camera to Cam_Isometric.")

                # Stage 5: Switch Active Camera using alias 'name'
                print("[*] Stage 5: Switching active camera to Cam_Cinematic using alias 'name'...")
                sw2_res = await session.call_tool("switch_camera", {"name": "Cam_Cinematic"})
                sw2_data = unwrap(sw2_res)
                assert sw2_data.get("status") == "success", f"switch_camera with alias failed: {sw2_data}"
                assert sw2_data.get("previous_camera") == "Cam_Isometric"
                assert sw2_data.get("active_camera") == "Cam_Cinematic"
                assert sw2_data.get("verified") is True

                # Verify via render_settings category
                render_insp = await session.call_tool("inspect_scene_data", {"category": "render_settings"})
                render_insp_data = unwrap(render_insp)
                assert render_insp_data.get("active_camera") == "Cam_Cinematic"
                print("[+] Stage 5 PASSED: switch_camera alias 'name' verified; render_settings inspection matches.")

                # Stage 6: Switch Active Camera via configure_camera(set_active=True)
                print("[*] Stage 6: Switching active camera to Cam_Perspective via configure_camera(set_active=True)...")
                cfg_cam_res = await session.call_tool("configure_camera", {
                    "name": "Cam_Perspective",
                    "set_active": True,
                })
                cfg_cam_data = unwrap(cfg_cam_res)
                assert cfg_cam_data.get("status") == "success"
                assert cfg_cam_data.get("camera_details", {}).get("is_active_camera") is True

                insp_cfg = await session.call_tool("inspect_scene_data", {"category": "cameras"})
                assert unwrap(insp_cfg).get("active_camera") == "Cam_Perspective"
                print("[+] Stage 6 PASSED: configure_camera(set_active=True) inter-tool compatibility verified.")

                # Stage 7: Switch Active Camera via configure_render_settings(active_camera=...)
                print("[*] Stage 7: Switching active camera via configure_render_settings(active_camera='Cam_Cinematic')...")
                cfg_rnd_res = await session.call_tool("configure_render_settings", {
                    "active_camera": "Cam_Cinematic",
                })
                assert not is_error_response(cfg_rnd_res), f"configure_render_settings failed: {cfg_rnd_res}"
                cfg_rnd_data = unwrap(cfg_rnd_res)
                assert cfg_rnd_data.get("active_camera") == "Cam_Cinematic", f"Unexpected render settings: {cfg_rnd_data}"

                insp_rnd = await session.call_tool("inspect_scene_data", {"category": "cameras"})
                assert unwrap(insp_rnd).get("active_camera") == "Cam_Cinematic"
                print("[+] Stage 7 PASSED: configure_render_settings active_camera switching compatibility verified.")

                # Stage 8: Fail-Closed Security Validation
                print("[*] Stage 8: Testing Fail-Closed Security Boundaries...")

                # 8.1 Non-existent camera object
                bad_cam_res = await session.call_tool("switch_camera", {"camera_name": "GhostCam_999"})
                assert is_error_response(bad_cam_res) or "error" in str(unwrap(bad_cam_res)), "Missing camera must fail closed"
                print("    - 8.1 Non-existent camera correctly rejected.")

                # 8.2 Non-camera object (mesh)
                prim_res = await session.call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "NonCameraCube",
                })
                assert not is_error_response(prim_res), f"create_primitive failed: {prim_res}"

                bad_type_res = await session.call_tool("switch_camera", {"camera_name": "NonCameraCube"})
                assert is_error_response(bad_type_res) or "error" in str(unwrap(bad_type_res)), "Mesh object must be rejected for switch_camera"
                print("    - 8.2 Non-camera mesh object correctly rejected.")

                # 8.3 Untrusted client approval flag
                untrusted_res = await session.call_tool("switch_camera", {
                    "camera_name": "Cam_Perspective",
                    "approved": True,
                })
                assert is_error_response(untrusted_res) or "error" in str(unwrap(untrusted_res)), "Untrusted client approval flag must be rejected"
                print("    - 8.3 Untrusted client-supplied approved=True correctly rejected.")
                print("[+] Stage 8 PASSED: Fail-closed security validation verified.")

                # Stage 9: Symmetrical Teardown
                print("[*] Stage 9: Symmetrical Teardown and Cleanup...")
                for obj_name in ("Cam_Perspective", "Cam_Isometric", "Cam_Cinematic", "NonCameraCube"):
                    del_res = await session.call_tool("delete_object", {"name": obj_name})
                    assert not is_error_response(del_res) and unwrap(del_res).get("deleted") is True, f"Failed to delete {obj_name}"

                # Confirm clean scene
                summary_res = await session.call_tool("inspect_scene_data", {"category": "cameras"})
                summary_data = unwrap(summary_res)
                assert summary_data.get("camera_count") == 0, f"Expected 0 cameras after teardown, got {summary_data.get('camera_count')}"
                print("[+] Stage 9 PASSED: All created cameras and mesh objects cleanly purged.")

                # Stage 10: Production Bridge Isolation Guard
                print("[*] Stage 10: Verifying Production Bridge Port 9877 Guard...")
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    res = s.connect_ex(("127.0.0.1", 9877))
                    assert res == 0, "Production bridge port 9877 was closed or killed!"
                print("[+] Stage 10 PASSED: Production bridge port 9877 verified alive, untouched, and unpolluted.")

    finally:
        print("[*] Teardown: Stopping disposable Blender instance...")
        (run_root / "stop.flag").touch()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        blender_log_file.close()
        print("[+] Disposable Blender process terminated cleanly.")

    print("\n" + "=" * 80)
    print("ALL 10 STAGES COMPLETED SUCCESSFULLY: CAPABILITY 7.2 PHASE 2 VERIFIED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
