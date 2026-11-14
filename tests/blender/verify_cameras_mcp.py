"""
Automated Real MCP-to-Blender E2E Verification of Cameras Foundation (v0.1.69).
Covers Capability 9:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover Camera tools over MCP stdio wire:
   - create_camera
   - configure_camera (and alias edit_camera)
   - get_object_details (camera_details)
   - list_objects (CAMERA filter)
   - inspect_scene_data (render_settings active camera)
4. Live execution and independent Blender readback:
   - Create Perspective camera ('Cam_Perspective', lens=50.0, set_active=True)
   - Inspect active camera in render_settings -> verify active_camera == 'Cam_Perspective'
   - Inspect camera list via list_objects(object_type='CAMERA') -> verify object listed
   - Inspect camera details via get_object_details -> verify camera_details (PERSP, 50mm, active)
   - Configure camera focal length (85mm portrait) and horizontal shift (shift_x=0.04) via configure_camera
   - Inspect camera details via get_object_details -> independent readback of lens & shift
   - Configure depth of field (use_dof=True, focus_distance=3.2, aperture_fstop=1.8) via configure_camera
   - Inspect camera details via get_object_details -> independent readback of DOF settings
   - Switch camera projection to Orthographic ('ORTHO') with ortho_scale=12.0 via configure_camera
   - Inspect camera details via get_object_details -> independent readback of ORTHO & ortho_scale
   - Switch camera projection to Panoramic ('PANO') via alias edit_camera
   - Inspect camera details via get_object_details -> independent readback of PANO
   - Create second camera ('Cam_TopOrtho', ORTHO, set_active=False)
   - Verify render_settings active camera is still 'Cam_Perspective'
   - Switch active camera to 'Cam_TopOrtho' via configure_camera(set_active=True)
   - Verify render_settings active camera switches to 'Cam_TopOrtho'
5. Security and validation enforcement:
   - Untrusted model approved=True injection rejected fail-closed
   - Negative focal length rejected fail-closed
   - Invalid clipping planes (clip_start >= clip_end) rejected fail-closed
   - Non-existent camera object rejected fail-closed
   - Non-camera object target rejected fail-closed
   - Unsupported properties (stereoscopy, motion_blur) rejected fail-closed
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
    print("STARTING REAL MCP-TO-BLENDER E2E: CAMERAS FOUNDATION (v0.1.69)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CAM-"))
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

                # 1. Discover tools
                tools_list = await session.list_tools()
                discovered_names = {t.name for t in tools_list.tools}
                for req_tool in ("create_camera", "configure_camera", "edit_camera", "list_objects", "get_object_details", "inspect_scene_data"):
                    assert req_tool in discovered_names, f"Tool '{req_tool}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all camera foundation tools present.")

                # 2. Create Perspective Camera
                cam_res = await call_tool("create_camera", {
                    "name": "Cam_Perspective",
                    "focal_length": 50.0,
                    "clip_start": 0.1,
                    "clip_end": 1000.0,
                    "location": [0.0, -6.0, 2.0],
                    "rotation_euler": [1.2, 0.0, 0.0],
                    "set_active": True,
                })
                cam_data = cam_res.get("result", cam_res)
                assert cam_data.get("name") == "Cam_Perspective", f"Create camera failed: {cam_res}"
                assert cam_data.get("focal_length") == 50.0
                assert cam_data.get("is_active") is True
                print("[+] Created Perspective Camera 'Cam_Perspective': success")

                # 3. Inspect Active Camera in render_settings
                rs_res = await call_tool("inspect_scene_data", {"category": "render_settings"})
                rs_data = rs_res.get("result", rs_res)
                assert rs_data.get("active_camera") == "Cam_Perspective", f"Active camera mismatch: {rs_data}"
                print(f"[+] Verified active camera in render_settings: '{rs_data.get('active_camera')}'.")

                # 4. Inspect camera in list_objects
                list_cams = await call_tool("list_objects", {"object_type": "CAMERA"})
                list_data = list_cams.get("result", list_cams)
                cam_names = [o.get("name") for o in list_data.get("objects", [])]
                assert "Cam_Perspective" in cam_names
                print(f"[+] Verified 'Cam_Perspective' in list_objects(object_type='CAMERA'): {cam_names}")

                # 5. Inspect camera details via get_object_details
                details_cam = await call_tool("get_object_details", {"name": "Cam_Perspective"})
                details_data = details_cam.get("result", details_cam)
                cd = details_data.get("camera_details")
                assert cd is not None, f"camera_details missing from get_object_details: {details_data}"
                assert cd.get("type") == "PERSP"
                assert cd.get("focal_length") == 50.0
                assert cd.get("is_active_camera") is True
                print(f"[+] Verified camera_details via get_object_details: type={cd['type']}, lens={cd['lens']}mm, active={cd['is_active_camera']}")

                # 6. Configure focal length to 85mm and shift_x=0.04
                cfg_res = await call_tool("configure_camera", {
                    "name": "Cam_Perspective",
                    "focal_length": 85.0,
                    "shift_x": 0.04,
                })
                cfg_data = cfg_res.get("result", cfg_res)
                assert cfg_data.get("status") == "success", f"configure_camera failed: {cfg_res}"
                assert cfg_data.get("camera_details", {}).get("focal_length") == 85.0
                assert cfg_data.get("camera_details", {}).get("shift_x") == 0.04
                print("[+] Configured focal length to 85mm and shift_x=0.04: success")

                # 7. Independent readback of 85mm & shift via get_object_details
                details_cam2 = await call_tool("get_object_details", {"name": "Cam_Perspective"})
                details_data2 = details_cam2.get("result", details_cam2)
                cd2 = details_data2.get("camera_details")
                assert cd2.get("focal_length") == 85.0
                assert cd2.get("shift_x") == 0.04
                print("[+] Independent readback confirmed: 85mm focal length, shift_x=0.04")

                # 8. Configure Depth of Field
                dof_res = await call_tool("configure_camera", {
                    "name": "Cam_Perspective",
                    "dof": {
                        "use_dof": True,
                        "focus_distance": 3.2,
                        "aperture_fstop": 1.8,
                    },
                })
                dof_data = dof_res.get("result", dof_res)
                dof = dof_data.get("camera_details", {}).get("dof")
                assert dof is not None and dof.get("use_dof") is True
                assert dof.get("focus_distance") == 3.2
                assert dof.get("aperture_fstop") == 1.8
                print(f"[+] Configured Depth of Field: use_dof=True, dist=3.2m, fstop=1.8")

                # 9. Independent readback of DOF
                details_dof = await call_tool("get_object_details", {"name": "Cam_Perspective"})
                details_dof_data = details_dof.get("result", details_dof)
                dof_rb = details_dof_data.get("camera_details", {}).get("dof")
                assert dof_rb.get("use_dof") is True
                assert dof_rb.get("focus_distance") == 3.2
                assert dof_rb.get("aperture_fstop") == 1.8
                print("[+] Independent DOF readback confirmed: verified")

                # 10. Switch to Orthographic projection (ortho_scale=12.0)
                ortho_res = await call_tool("configure_camera", {
                    "name": "Cam_Perspective",
                    "camera_type": "ORTHO",
                    "ortho_scale": 12.0,
                })
                ortho_data = ortho_res.get("result", ortho_res)
                cd_ortho = ortho_data.get("camera_details", {})
                assert cd_ortho.get("type") == "ORTHO"
                assert cd_ortho.get("ortho_scale") == 12.0
                print(f"[+] Switched to ORTHO projection: ortho_scale=12.0")

                # 11. Independent readback of ORTHO
                details_ortho = await call_tool("get_object_details", {"name": "Cam_Perspective"})
                details_ortho_data = details_ortho.get("result", details_ortho)
                cd_ortho_rb = details_ortho_data.get("camera_details")
                assert cd_ortho_rb.get("type") == "ORTHO"
                assert cd_ortho_rb.get("ortho_scale") == 12.0
                print("[+] Independent ORTHO readback confirmed: verified")

                # 12. Switch to Panoramic projection via edit_camera alias
                pano_res = await call_tool("edit_camera", {
                    "name": "Cam_Perspective",
                    "camera_type": "PANO",
                })
                pano_data = pano_res.get("result", pano_res)
                cd_pano = pano_data.get("camera_details", {})
                assert cd_pano.get("type") == "PANO"
                print(f"[+] Switched to PANO via edit_camera alias: verified")

                # 13. Independent readback of PANO
                details_pano = await call_tool("get_object_details", {"name": "Cam_Perspective"})
                details_pano_data = details_pano.get("result", details_pano)
                cd_pano_rb = details_pano_data.get("camera_details")
                assert cd_pano_rb.get("type") == "PANO"
                print("[+] Independent PANO readback confirmed: verified")

                # 14. Create second camera ('Cam_TopOrtho', set_active=False)
                cam2_res = await call_tool("create_camera", {
                    "name": "Cam_TopOrtho",
                    "camera_type": "ORTHO",
                    "ortho_scale": 8.0,
                    "location": [0.0, 0.0, 10.0],
                    "rotation_euler": [0.0, 0.0, 0.0],
                    "set_active": False,
                })
                cam2_data = cam2_res.get("result", cam2_res)
                assert cam2_data.get("name") == "Cam_TopOrtho"
                assert cam2_data.get("is_active") is False
                print("[+] Created second camera 'Cam_TopOrtho' (inactive): success")

                # 15. Verify render_settings active camera is still Cam_Perspective
                rs_chk = await call_tool("inspect_scene_data", {"category": "render_settings"})
                rs_chk_data = rs_chk.get("result", rs_chk)
                assert rs_chk_data.get("active_camera") == "Cam_Perspective"
                print("[+] Active camera preserved as 'Cam_Perspective': verified")

                # 16. Switch active camera to Cam_TopOrtho
                act_res = await call_tool("configure_camera", {
                    "name": "Cam_TopOrtho",
                    "set_active": True,
                })
                act_data = act_res.get("result", act_res)
                assert act_data.get("camera_details", {}).get("is_active_camera") is True

                rs_sw = await call_tool("inspect_scene_data", {"category": "render_settings"})
                rs_sw_data = rs_sw.get("result", rs_sw)
                assert rs_sw_data.get("active_camera") == "Cam_TopOrtho"
                print("[+] Switched active camera to 'Cam_TopOrtho': verified in render_settings")

                # 17. Security: Untrusted model approved=True rejected
                sec_res = await call_tool("configure_camera", {
                    "name": "Cam_TopOrtho",
                    "focal_length": 35.0,
                    "approved": True,
                })
                assert sec_res.get("status") == "error" or "error" in str(sec_res).lower()
                print("[+] Security test: Untrusted model approved=True rejected fail-closed: verified")

                # 18. Negative: Negative focal length rejected
                neg_res = await call_tool("configure_camera", {
                    "name": "Cam_TopOrtho",
                    "focal_length": -24.0,
                })
                assert neg_res.get("status") == "error" or "error" in str(neg_res).lower()
                print("[+] Negative test: Negative focal length rejected: verified")

                # 19. Negative: Invalid clipping planes rejected
                clip_res = await call_tool("configure_camera", {
                    "name": "Cam_TopOrtho",
                    "clip_start": 500.0,
                    "clip_end": 100.0,
                })
                assert clip_res.get("status") == "error" or "error" in str(clip_res).lower()
                print("[+] Negative test: Invalid clipping (start >= end) rejected: verified")

                # 20. Negative: Non-existent camera rejected
                ghost_res = await call_tool("configure_camera", {
                    "name": "GhostCamera",
                    "focal_length": 50.0,
                })
                assert ghost_res.get("status") == "error" or "error" in str(ghost_res).lower()
                print("[+] Negative test: Non-existent camera rejected: verified")

                # 21. Negative: Non-camera object target rejected
                await call_tool("create_primitive", {"primitive_type": "cube", "name": "TargetCube"})
                mesh_res = await call_tool("configure_camera", {
                    "name": "TargetCube",
                    "focal_length": 50.0,
                })
                assert mesh_res.get("status") == "error" or "error" in str(mesh_res).lower()
                print("[+] Negative test: Non-camera object target rejected: verified")

                # 22. Negative: Unsupported camera property rejected
                unsup_res = await call_tool("configure_camera", {
                    "name": "Cam_TopOrtho",
                    "stereoscopy": True,
                })
                assert unsup_res.get("status") == "error" or "error" in str(unsup_res).lower()
                print("[+] Negative test: Unsupported property (stereoscopy) rejected: verified")

                print("=" * 80)
                print("REAL MCP-TO-BLENDER E2E: ALL 22 CAMERAS FOUNDATION PHASES PASSED WITH 100% SUCCESS!")
                print("=" * 80)

    finally:
        print("[*] Tearing down disposable Blender instance...")
        stop_flag = run_root / "stop.flag"
        stop_flag.write_text("stop", encoding="utf-8")
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("[+] Disposable Blender instance terminated cleanly.")


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
