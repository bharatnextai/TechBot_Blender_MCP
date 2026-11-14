"""
Live MCP verification for Capability 7.2 Phase 1:
Camera Framing, Composition & Optical Rigging.

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
    print("STARTING REAL MCP-TO-BLENDER E2E: CAPABILITY 7.2 PHASE 1 (CAMERA FRAMING & OPTICAL RIGGING)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CAM-RIG-CAP7-"))
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
    env["UMCP_LOCAL_TEST_SCOPE"] = "camera_rigging_v1"
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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "camera_rigging_v1"
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
                for required in ("create_camera", "configure_camera", "get_object_details", "create_primitive", "delete_object"):
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

                # Stage 2: Create Target Objects for Tracking & Focus
                res_target1 = await session.call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "Subject_Target",
                    "location": [0.0, 0.0, 1.0],
                })
                assert not is_error_response(res_target1), f"Failed to create Subject_Target: {res_target1}"
                print("[+] Stage 2a: Created primary target object 'Subject_Target'.")

                res_target2 = await session.call_tool("create_primitive", {
                    "primitive_type": "sphere",
                    "name": "Secondary_Target",
                    "location": [4.0, 2.0, 2.5],
                })
                assert not is_error_response(res_target2), f"Failed to create Secondary_Target: {res_target2}"
                print("[+] Stage 2b: Created secondary target object 'Secondary_Target'.")

                # Stage 3: Create Camera with Optical Rigging & Composition Guides
                create_cam_params = {
                    "name": "Cinematic_Cam",
                    "focal_length": 85.0,
                    "location": [0.0, -8.0, 3.0],
                    "track_to_object": "Subject_Target",
                    "focus_object": "Subject_Target",
                    "show_composition_thirds": True,
                    "set_active": True,
                }
                res_create = await session.call_tool("create_camera", create_cam_params)
                assert not is_error_response(res_create), f"Failed to create camera: {res_create}"
                data_create = unwrap(res_create)
                print(f"[+] Stage 3 response: {data_create}")

                assert data_create["name"] == "Cinematic_Cam", "Camera name mismatch"
                assert data_create["track_to_object"] == "Subject_Target", f"Expected track_to_object 'Subject_Target', got {data_create.get('track_to_object')}"
                assert data_create["focus_object"] == "Subject_Target", f"Expected focus_object 'Subject_Target', got {data_create.get('focus_object')}"
                assert data_create["show_composition_thirds"] is True, "show_composition_thirds must be True"

                cd_create = data_create["camera_details"]
                assert cd_create["track_to_object"] == "Subject_Target"
                assert cd_create["focus_object"] == "Subject_Target"
                assert cd_create["show_composition_thirds"] is True
                assert cd_create["dof"]["use_dof"] is True, "dof.use_dof should be enabled when focus_object assigned"
                assert cd_create["dof"]["focus_object"] == "Subject_Target"
                print("[+] Stage 3: Camera creation with optical rigging and composition thirds verified.")

                # Stage 4: Independent RNA Inspection via get_object_details
                res_insp1 = await session.call_tool("get_object_details", {"name": "Cinematic_Cam"})
                assert not is_error_response(res_insp1), f"Failed to inspect Cinematic_Cam: {res_insp1}"
                data_insp1 = unwrap(res_insp1)
                cd_insp1 = data_insp1.get("camera_details", {})

                assert cd_insp1.get("track_to_object") == "Subject_Target", f"RNA mismatch track_to_object: {cd_insp1}"
                assert cd_insp1.get("focus_object") == "Subject_Target", f"RNA mismatch focus_object: {cd_insp1}"
                assert cd_insp1.get("show_composition_thirds") is True, f"RNA mismatch show_composition_thirds: {cd_insp1}"
                assert cd_insp1.get("dof", {}).get("focus_object") == "Subject_Target"
                print("[+] Stage 4: Independent RNA readback via get_object_details verified.")

                # Stage 5: Configuration Mutation: Switch Targets & Toggle Thirds
                mutate_params = {
                    "name": "Cinematic_Cam",
                    "focal_length": 50.0,
                    "track_to_object": "Secondary_Target",
                    "focus_object": "Secondary_Target",
                    "show_composition_thirds": False,
                }
                res_mutate = await session.call_tool("configure_camera", mutate_params)
                assert not is_error_response(res_mutate), f"Failed to configure camera: {res_mutate}"
                data_mutate = unwrap(res_mutate)
                cd_mutate = data_mutate.get("camera_details", {})

                assert cd_mutate.get("track_to_object") == "Secondary_Target"
                assert cd_mutate.get("focus_object") == "Secondary_Target"
                assert cd_mutate.get("show_composition_thirds") is False
                assert cd_mutate.get("focal_length") == 50.0

                # Verify via get_object_details
                res_insp2 = await session.call_tool("get_object_details", {"name": "Cinematic_Cam"})
                cd_insp2 = unwrap(res_insp2).get("camera_details", {})
                assert cd_insp2.get("track_to_object") == "Secondary_Target"
                assert cd_insp2.get("focus_object") == "Secondary_Target"
                assert cd_insp2.get("show_composition_thirds") is False
                print("[+] Stage 5: Dynamic mutation to secondary target and composition toggle verified.")

                # Stage 6: Optical De-rigging (Unset Tracking & Focus)
                clear_params = {
                    "name": "Cinematic_Cam",
                    "track_to_object": "",
                    "focus_object": "",
                }
                res_clear = await session.call_tool("configure_camera", clear_params)
                assert not is_error_response(res_clear), f"Failed to clear optical rigging: {res_clear}"
                cd_clear = unwrap(res_clear).get("camera_details", {})

                assert cd_clear.get("track_to_object") is None, f"Expected None track_to_object, got {cd_clear.get('track_to_object')}"
                assert cd_clear.get("focus_object") is None, f"Expected None focus_object, got {cd_clear.get('focus_object')}"

                # Verify constraint removed in get_object_details
                res_insp3 = await session.call_tool("get_object_details", {"name": "Cinematic_Cam"})
                cd_insp3 = unwrap(res_insp3).get("camera_details", {})
                assert cd_insp3.get("track_to_object") is None
                assert cd_insp3.get("focus_object") is None
                print("[+] Stage 6: Symmetrical de-rigging (clearing tracking constraint and DOF focus) verified.")

                # Stage 7: Fail-Closed Security & Self-Targeting Rejection
                # 7a: Camera tracking itself
                res_self_track = await session.call_tool("configure_camera", {
                    "name": "Cinematic_Cam",
                    "track_to_object": "Cinematic_Cam",
                })
                assert is_error_response(res_self_track), "Expected error when camera tracks itself"
                print("[+] Stage 7a: Self-tracking rejected fail-closed.")

                # 7b: Camera focusing on itself
                res_self_focus = await session.call_tool("configure_camera", {
                    "name": "Cinematic_Cam",
                    "focus_object": "Cinematic_Cam",
                })
                assert is_error_response(res_self_focus), "Expected error when camera focuses on itself"
                print("[+] Stage 7b: Self-focus rejected fail-closed.")

                # 7c: Non-existent target object
                res_missing_target = await session.call_tool("configure_camera", {
                    "name": "Cinematic_Cam",
                    "track_to_object": "NonExistentTrackTarget_999",
                })
                assert is_error_response(res_missing_target), "Expected error for non-existent tracking target"
                print("[+] Stage 7c: Non-existent tracking target rejected fail-closed.")

                # 7d: Non-existent focus object
                res_missing_focus = await session.call_tool("configure_camera", {
                    "name": "Cinematic_Cam",
                    "focus_object": "NonExistentFocusTarget_999",
                })
                assert is_error_response(res_missing_focus), "Expected error for non-existent focus target"
                print("[+] Stage 7d: Non-existent focus target rejected fail-closed.")

                # 7e: Invalid composition thirds type
                res_invalid_thirds = await session.call_tool("configure_camera", {
                    "name": "Cinematic_Cam",
                    "show_composition_thirds": "invalid_string_val",
                })
                assert is_error_response(res_invalid_thirds), "Expected error for non-boolean show_composition_thirds"
                print("[+] Stage 7e: Invalid composition thirds type rejected fail-closed.")

                # Stage 8: Symmetrical Scene Cleanup
                res_del_cam = await session.call_tool("delete_object", {"name": "Cinematic_Cam"})
                assert not is_error_response(res_del_cam), f"Failed to delete camera: {res_del_cam}"

                res_del_t1 = await session.call_tool("delete_object", {"name": "Subject_Target"})
                assert not is_error_response(res_del_t1), f"Failed to delete Subject_Target: {res_del_t1}"

                res_del_t2 = await session.call_tool("delete_object", {"name": "Secondary_Target"})
                assert not is_error_response(res_del_t2), f"Failed to delete Secondary_Target: {res_del_t2}"

                print("[+] Stage 8: Complete scene cleanup verified.")

        print("\n" + "=" * 80)
        print("ALL 8 MCP E2E STAGES PASSED FOR CAPABILITY 7.2 PHASE 1!")
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
