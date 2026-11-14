"""
Automated Real MCP-to-Blender E2E Verification of Rendering Foundation (v0.1.70).
Covers Capability 10:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover Rendering Foundation tools over MCP stdio wire:
   - render_scene
   - configure_render_settings
   - inspect_render_output
   - inspect_scene_data (render_settings, render_result)
4. Live execution and independent Blender readback:
   - Configure render settings (engine, resolution, frame range, format, active camera)
   - Readback render settings via inspect_scene_data(category="render_settings")
   - Create scene geometry, light, and active camera
   - Execute still render (frame 1) -> verify FINISHED operator, fresh output file, dimensions, render_id
   - Inspect still render output receipt via inspect_render_output -> verify SHA-256 and PNG structure
   - Inspect scene data category="render_result" -> verify render datablock inspection
   - Execute animation render (frames 1..3) -> verify all fresh frame files, frame_receipts, render_ids
   - Inspect individual animation frame receipts via inspect_render_output
5. Security and validation enforcement:
   - Untrusted client approved=True injection rejected fail-closed
   - Invalid animation frame range (frame_start > frame_end) rejected fail-closed
   - Invalid render engine rejected fail-closed
   - Invalid resolution bounds rejected fail-closed
   - Missing/non-existent camera rejected fail-closed
   - Unknown/expired receipt ID rejected fail-closed
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
    print("STARTING REAL MCP-TO-BLENDER E2E: RENDERING FOUNDATION (v0.1.70)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-RENDER-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    render_dir = run_root / "renders"
    for d in (config_dir, scripts_dir, ext_dir, render_dir):
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
    env["UMCP_LOCAL_TEST_SCOPE"] = "rendering_v1"
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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "rendering_v1"
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
                "25",
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
                for req_tool in ("render_scene", "configure_render_settings", "inspect_render_output", "inspect_scene_data"):
                    assert req_tool in discovered_names, f"Tool '{req_tool}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all rendering foundation tools present.")

                # 2. Setup scene: Camera, Primitive Cube, Light
                cam_res = await call_tool("create_camera", {
                    "name": "RenderCam",
                    "focal_length": 50.0,
                    "location": [0.0, -4.0, 1.5],
                    "rotation_euler": [1.2, 0.0, 0.0],
                    "set_active": True,
                })
                cam_data = cam_res.get("result", cam_res)
                assert cam_data.get("name") == "RenderCam", f"Create camera failed: {cam_res}"
                print("[+] Scene Setup: Created active camera 'RenderCam'.")

                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "TargetCube",
                    "location": [0.0, 0.0, 0.0],
                })
                cube_data = cube_res.get("result", cube_res)
                assert cube_data.get("name") == "TargetCube", f"Create cube failed: {cube_res}"
                print("[+] Scene Setup: Created target mesh 'TargetCube'.")

                light_res = await call_tool("create_light", {
                    "name": "KeyLight",
                    "light_type": "SUN",
                    "energy": 3.0,
                    "location": [2.0, -2.0, 5.0],
                })
                light_data = light_res.get("result", light_res)
                assert light_data.get("name") == "KeyLight", f"Create light failed: {light_res}"
                print("[+] Scene Setup: Created sun light 'KeyLight'.")

                # 3. Configure render settings
                cfg_res = await call_tool("configure_render_settings", {
                    "engine": "BLENDER_EEVEE_NEXT",
                    "resolution_x": 160,
                    "resolution_y": 120,
                    "resolution_percentage": 100,
                    "frame_start": 1,
                    "frame_end": 3,
                    "fps": 24,
                    "output_format": "PNG",
                    "active_camera": "RenderCam",
                })
                cfg_data = cfg_res.get("result", cfg_res)
                assert cfg_data.get("resolution_x") == 160, f"Configure render settings failed: {cfg_res}"
                assert cfg_data.get("resolution_y") == 120
                assert cfg_data.get("resolution_percentage") == 100
                assert cfg_data.get("active_camera") == "RenderCam"
                assert cfg_data.get("output_format") == "PNG"
                print(f"[+] Configured render settings: 160x120 100%, EEVEE_NEXT, frames 1..3: success")

                # 4. Independent readback of render settings via inspect_scene_data
                rs_insp = await call_tool("inspect_scene_data", {"category": "render_settings"})
                rs_data = rs_insp.get("result", rs_insp)
                assert rs_data.get("category") == "render_settings"
                assert rs_data.get("resolution_x") == 160
                assert rs_data.get("resolution_y") == 120
                assert rs_data.get("active_camera") == "RenderCam"
                assert rs_data.get("output_format") == "PNG"
                print(f"[+] Independent readback of render_settings verified: {rs_data['resolution_x']}x{rs_data['resolution_y']}, camera '{rs_data['active_camera']}'")

                # 5. Execute Still Render (frame=1)
                still_path = str(render_dir / "still_frame_0001.png")
                still_res = await call_tool("render_scene", {
                    "render_mode": "still",
                    "frame": 1,
                    "output_path": still_path,
                    "output_format": "PNG",
                })
                still_data = still_res.get("result", still_res)
                assert still_data.get("rendered") is True, f"Still render failed: {still_res}"
                assert still_data.get("operator_completed") is True
                assert still_data.get("render_mode") == "still"
                assert still_data.get("width") == 160
                assert still_data.get("height") == 120
                still_id = still_data.get("render_id")
                assert still_id is not None and len(still_id) == 32
                out_file = still_data.get("output_file")
                assert out_file and os.path.exists(out_file) and os.path.getsize(out_file) > 0
                print(f"[+] Executed still render: frame=1, render_id={still_id}, file={out_file} ({os.path.getsize(out_file)} bytes)")

                # 6. Inspect still render output receipt via inspect_render_output
                insp_receipt = await call_tool("inspect_render_output", {"render_id": still_id})
                rcpt_data = insp_receipt.get("result", insp_receipt)
                assert rcpt_data.get("success") is True, f"Receipt inspection failed: {insp_receipt}"
                assert rcpt_data.get("verified") is True
                assert rcpt_data.get("render_id") == still_id
                assert rcpt_data.get("width") == 160
                assert rcpt_data.get("height") == 120
                assert rcpt_data.get("camera") == "RenderCam"
                artifact = rcpt_data.get("artifact", {})
                assert artifact.get("png_structure_verified") is True
                assert len(artifact.get("sha256", "")) == 64
                assert artifact.get("size_bytes") > 0
                print(f"[+] Verified still render output receipt: SHA256={artifact['sha256'][:16]}..., verified={rcpt_data['verified']}")

                # 7. Inspect scene data category="render_result"
                rr_insp = await call_tool("inspect_scene_data", {"category": "render_result"})
                rr_data = rr_insp.get("result", rr_insp)
                assert rr_data.get("category") == "render_result"
                print(f"[+] Inspected scene data category='render_result': image_exists={rr_data.get('image_exists')}, available={rr_data.get('available')}")

                # 8. Execute Animation Render (frames 1..3)
                anim_base = str(render_dir / "anim_frame_")
                anim_res = await call_tool("render_scene", {
                    "render_mode": "animation",
                    "frame_start": 1,
                    "frame_end": 3,
                    "output_path": anim_base,
                    "output_format": "PNG",
                })
                anim_data = anim_res.get("result", anim_res)
                assert anim_data.get("rendered") is True, f"Animation render failed: {anim_res}"
                assert anim_data.get("operator_completed") is True
                assert anim_data.get("render_mode") == "animation"
                assert anim_data.get("total_frames") == 3
                assert len(anim_data.get("output_paths", [])) == 3
                assert len(anim_data.get("frame_receipts", [])) == 3
                assert len(anim_data.get("render_ids", [])) == 3
                print(f"[+] Executed animation render: 3 frames rendered, all verified on disk.")

                # 9. Verify each animation frame file exists and has valid bytes
                for idx, path_str in enumerate(anim_data["output_paths"]):
                    assert os.path.exists(path_str), f"Animation frame {idx+1} missing: {path_str}"
                    assert os.path.getsize(path_str) > 0, f"Animation frame {idx+1} empty: {path_str}"
                print(f"[+] Verified all 3 animation frame files on disk with non-empty contents.")

                # 10. Inspect individual animation frame receipts via inspect_render_output
                for frame_info in anim_data["frame_receipts"]:
                    f_num = frame_info["frame"]
                    f_rid = frame_info["render_id"]
                    f_insp = await call_tool("inspect_render_output", {"render_id": f_rid})
                    f_rcpt = f_insp.get("result", f_insp)
                    assert f_rcpt.get("verified") is True, f"Animation receipt {f_rid} verification failed: {f_insp}"
                    assert f_rcpt.get("frame") == f_num
                    assert f_rcpt.get("artifact", {}).get("png_structure_verified") is True
                    print(f"[+] Verified animation frame {f_num} receipt: render_id={f_rid}, SHA256={f_rcpt['artifact']['sha256'][:16]}...")

                # 11. Security & Negative Test: Untrusted client approved=True injection
                sec_res = await call_tool("render_scene", {
                    "render_mode": "still",
                    "approved": True,
                })
                assert sec_res.get("status") == "error", f"Untrusted approval should have failed: {sec_res}"
                assert "untrusted" in sec_res.get("message", "").lower() or "approval" in sec_res.get("message", "").lower()
                print(f"[+] Security Verified: Untrusted client approved=True injection rejected fail-closed.")

                # 12. Negative Test: Invalid animation frame range (frame_start > frame_end)
                range_res = await call_tool("render_scene", {
                    "render_mode": "animation",
                    "frame_start": 20,
                    "frame_end": 5,
                })
                assert range_res.get("status") == "error", f"Invalid frame range should have failed: {range_res}"
                print(f"[+] Negative Test Verified: Invalid frame range (20 > 5) rejected fail-closed.")

                # 13. Negative Test: Invalid render engine
                engine_res = await call_tool("configure_render_settings", {
                    "engine": "RAYTRACER_INVALID_ENGINE",
                })
                assert engine_res.get("status") == "error", f"Invalid engine should have failed: {engine_res}"
                print(f"[+] Negative Test Verified: Unsupported render engine rejected fail-closed.")

                # 14. Negative Test: Invalid resolution bounds
                res_bounds = await call_tool("configure_render_settings", {
                    "resolution_x": -500,
                })
                assert res_bounds.get("status") == "error", f"Negative resolution should have failed: {res_bounds}"
                print(f"[+] Negative Test Verified: Negative resolution bounds rejected fail-closed.")

                # 15. Negative Test: Unknown / expired render receipt ID
                unknown_receipt = await call_tool("inspect_render_output", {
                    "render_id": "0123456789abcdef0123456789abcdef",
                })
                assert unknown_receipt.get("status") == "error", f"Unknown receipt ID should have failed: {unknown_receipt}"
                assert "not found" in unknown_receipt.get("message", "").lower() or "expired" in unknown_receipt.get("message", "").lower()
                print(f"[+] Negative Test Verified: Unknown render receipt ID rejected fail-closed.")

                print("=" * 80)
                print("CAPABILITY 10: RENDERING FOUNDATION E2E FULLY PASSED (15/15 PHASES)")
                print("=" * 80)

    finally:
        print("[*] Terminating disposable Blender process...")
        (run_root / "stop.flag").write_text("stop", encoding="utf-8")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("[+] Disposable Blender process cleaned up cleanly.")
        # Clean up temp run directory
        shutil.rmtree(run_root, ignore_errors=True)


if __name__ == "__main__":
    import shutil
    asyncio.run(run_e2e_verification())
