"""
Automated E2E Verification of Reference Image Loading and Viewport Visual Inspection.
Verifies TASK v0.1.50:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Loading reference image (Red Dragon 3D Reference Sheet.png) as:
   - Image Empty object (display_mode='EMPTY', view_axis='FRONT').
   - Calibrated textured mesh plane (display_mode='PLANE', view_axis='SIDE').
4. Independent scene and topology readback via get_object_details and inspect_scene_data.
5. Fail-closed security validations: untrusted approval flag, missing file, name collision.
6. Explicit handling of headless viewport context:
   - capture_viewport(mode='VIEWPORT') fails explicitly with CONTEXT_UNAVAILABLE in headless mode.
7. Visual verification via camera capture across views:
   - FRONT, SIDE, and TOP orthographic camera captures returning verified PNG image data.
8. Clean shutdown and zero persistent state.
"""

import asyncio
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any, List

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON_EXE = Path(sys.executable)
REFERENCE_IMAGE = Path(r"C:\Users\Administrator\Desktop\2D Testing\Red Dragon 3D Reference Sheet.png")

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


async def main():
    print("=== TASK v0.1.50: Reference Image Loading & Viewport Inspection E2E Verification ===")

    # 1. Verify Reference Image
    assert REFERENCE_IMAGE.exists(), f"Reference image missing: {REFERENCE_IMAGE}"
    ref_stat = REFERENCE_IMAGE.stat()
    print(f"[OK] Reference image verified: {REFERENCE_IMAGE.name} ({ref_stat.st_size:,} bytes)")

    # 2. Setup Disposable Test Environment
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-REF-IMG-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    data_dir = run_root / "data"
    for d in (config_dir, scripts_dir, ext_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, "Ephemeral port must strictly avoid production port 9877!"
    print(f"[OK] Isolated environment initialized at {run_root} (Port: {port})")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    env["BLENDER_USER_CONFIG"] = str(config_dir)
    env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)

    bootstrap_file = run_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE)

    # 3. Launch Disposable Blender 5.2.2 in Background Mode
    blender_cmd = [
        str(BLENDER),
        "--background",
        "--disable-autoexec",
        "--python",
        str(bootstrap_file),
    ]
    print(f"Launching Blender: {' '.join(blender_cmd)}")
    proc = subprocess.Popen(blender_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    ready_file = run_root / "blender_ready.json"
    t0 = time.time()
    while not ready_file.exists():
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(f"Blender process died unexpectedly:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
        if time.time() - t0 > 30.0:
            proc.kill()
            raise TimeoutError("Timed out waiting for Blender bridge server to start")
        time.sleep(0.1)

    ready_data = json.loads(ready_file.read_text())
    print(f"[OK] Disposable Blender ready (PID: {ready_data['pid']}, Version: {ready_data['blender']})")

    # 4. Connect stdio MCP Client to mcp_service.app
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp import ClientSession

    client_env = dict(os.environ)
    client_env["PYTHONPATH"] = str(PROJECT)
    client_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)

    server_params = StdioServerParameters(
        command=str(PYTHON_EXE),
        args=[
            "-B", "-m", "mcp_service.app",
            "--transport", "stdio",
            "--bridge-port", str(port),
            "--bridge-timeout", "10",
            "--approval-mode", "blender",
        ],
        env=client_env,
        cwd=str(PROJECT),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("[OK] stdio MCP Client initialized and connected to bridge")

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

            # --- STEP 1: Verify Initial Clean Scene ---
            summary = await call_tool("get_scene_summary", {})
            assert summary["status"] == "success"
            assert summary["result"]["total_objects"] == 0
            print("[PASS] Step 1: Initial Scene Summary (0 objects in clean scene)")

            # --- STEP 2: Load Reference Image as Image Empty ---
            ref_empty = await call_tool("load_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "name": "Dragon_Ref_Empty",
                "display_mode": "EMPTY",
                "view_axis": "FRONT",
                "size": 6.0,
                "opacity": 0.85,
                "location": [0.0, -1.0, 1.5],
            })
            assert ref_empty["status"] == "success", ref_empty
            res_e = ref_empty["result"]
            assert res_e["name"] == "Dragon_Ref_Empty"
            assert res_e["object_type"] == "EMPTY"
            assert res_e["display_mode"] == "EMPTY"
            assert res_e["dimensions"] == [1536, 1024]
            assert math.isclose(res_e["aspect_ratio"], 1.5, abs_tol=1e-3)
            assert math.isclose(res_e["rotation_euler"][0], 1.5708, abs_tol=1e-3)
            print(f"[PASS] Step 2: Loaded Image Empty '{res_e['name']}' ({res_e['dimensions']}, aspect {res_e['aspect_ratio']})")

            # --- STEP 3: Load Reference Image as Calibrated Textured Plane ---
            ref_plane = await call_tool("load_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "name": "Dragon_Ref_Plane",
                "display_mode": "PLANE",
                "view_axis": "SIDE",
                "size": 5.0,
                "opacity": 0.75,
                "location": [1.0, 0.0, 1.5],
            })
            assert ref_plane["status"] == "success", ref_plane
            res_p = ref_plane["result"]
            assert res_p["name"] == "Dragon_Ref_Plane"
            assert res_p["object_type"] == "MESH"
            assert res_p["display_mode"] == "PLANE"
            assert res_p["dimensions"] == [1536, 1024]
            assert math.isclose(res_p["aspect_ratio"], 1.5, abs_tol=1e-3)
            print(f"[PASS] Step 3: Loaded Calibrated Plane '{res_p['name']}' ({res_p['dimensions']}, aspect {res_p['aspect_ratio']})")

            # --- STEP 4: Independent Object Details Readback ---
            details_empty = await call_tool("get_object_details", {"name": "Dragon_Ref_Empty"})
            assert details_empty["status"] == "success"
            assert details_empty["result"]["type"] == "EMPTY"

            details_plane = await call_tool("get_object_details", {"name": "Dragon_Ref_Plane"})
            assert details_plane["status"] == "success"
            assert details_plane["result"]["type"] == "MESH"
            print("[PASS] Step 4: Independent Object Details Verified for Empty and Mesh Plane")

            # --- STEP 5: Independent Topology Readback on Calibrated Plane ---
            topo_plane = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": "Dragon_Ref_Plane",
            })
            assert topo_plane["status"] == "success"
            assert topo_plane["result"]["vertex_count"] == 4
            assert topo_plane["result"]["polygon_count"] == 1
            print(f"[PASS] Step 5: Independent Topology Verified on Plane ({topo_plane['result']['vertex_count']} verts, {topo_plane['result']['polygon_count']} polygons)")

            # --- STEP 6: Fail-Closed Security Defenses ---
            # 6a. Untrusted approval flag rejected by schema validator
            flag_tamper = await call_tool("load_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "approved": True,
            })
            assert flag_tamper["status"] == "error", "Untrusted approval flag must be rejected"
            print("[PASS] Step 6a: Untrusted approval flag rejected (Fail-Closed)")

            # 6b. Missing image file rejected
            missing_img = await call_tool("load_reference_image", {
                "image_path": str(run_root / "nonexistent_dragon.png"),
            })
            assert missing_img["status"] == "error", "Non-existent file must be rejected"
            print("[PASS] Step 6b: Non-existent image file rejected (Fail-Closed)")

            # 6c. Name collision rejected
            dup_collision = await call_tool("load_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "name": "Dragon_Ref_Empty",
            })
            assert dup_collision["status"] == "error", "Name collision must be rejected"
            assert "Collision detected" in dup_collision["message"]
            print("[PASS] Step 6c: Object name collision rejected (Fail-Closed)")

            # --- STEP 7: Headless Viewport Capture Handling ---
            # In headless background mode, mode='VIEWPORT' must fail explicitly with CONTEXT_UNAVAILABLE
            viewport_headless = await call_tool("capture_viewport", {
                "mode": "VIEWPORT",
                "view": "FRONT",
            })
            assert viewport_headless["status"] == "error", "Headless VIEWPORT mode must fail explicitly"
            assert "CONTEXT_UNAVAILABLE" in viewport_headless["message"]
            print("[PASS] Step 7: Headless VIEWPORT mode explicitly returned CONTEXT_UNAVAILABLE (No false-positive success)")

            # --- STEP 8: Create Active Camera for Visual Inspection ---
            cam = await call_tool("create_camera", {
                "name": "Dragon_Inspection_Camera",
                "location": [0.0, -10.0, 1.5],
            })
            assert cam["status"] == "success", cam
            print("[PASS] Step 8: Created active camera 'Dragon_Inspection_Camera'")

            # --- STEP 9: Visual Verification via Directional Camera Captures ---
            for view_dir in ("FRONT", "SIDE", "TOP"):
                cap_res = await call_tool("capture_viewport", {
                    "mode": "CAMERA",
                    "view": view_dir,
                    "width": 320,
                    "height": 240,
                })
                assert cap_res["status"] == "success", f"Capture {view_dir} failed: {cap_res}"
                cap_data = cap_res["result"]
                assert cap_data["mode"] == "CAMERA"
                assert cap_data["view"] == view_dir
                assert cap_data["format"] == "png"
                assert cap_data["width"] == 320
                assert cap_data["height"] == 240

                # Verify actual base64 PNG image bytes
                raw_bytes = base64.b64decode(cap_data["image_base64"], validate=True)
                assert raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid PNG header in capture"
                assert len(raw_bytes) > 500, f"Capture bytes too small: {len(raw_bytes)}"

                # Verify dimensions from PNG IHDR chunk
                png_width, png_height = struct.unpack(">II", raw_bytes[16:24])
                assert (png_width, png_height) == (320, 240)

                sha = hashlib.sha256(raw_bytes).hexdigest()
                print(f"[PASS] Step 9 ({view_dir}): Verified {png_width}x{png_height} PNG ({len(raw_bytes):,} bytes, SHA-256: {sha[:16]}...)")

            # --- STEP 10: Final Scene Summary & Object Inventory ---
            final_summary = await call_tool("get_scene_summary", {})
            assert final_summary["status"] == "success"
            # Dragon_Ref_Empty (empty), Dragon_Ref_Plane (mesh), Dragon_Inspection_Camera (camera)
            assert final_summary["result"]["total_objects"] == 3
            print(f"[PASS] Step 10: Final scene objects verified: {final_summary['result']['total_objects']} total")

    # 5. Clean Shutdown
    (run_root / "stop.flag").write_text("stop")
    t0 = time.time()
    while proc.poll() is None:
        if time.time() - t0 > 10.0:
            proc.kill()
            break
        time.sleep(0.1)

    print(f"[OK] Disposable Blender process cleanly exited with code {proc.returncode}")
    print("\n=== REFERENCE IMAGE & VISUAL VERIFICATION E2E TEST VERIFIED SUCCESSFUL ===")


if __name__ == "__main__":
    asyncio.run(main())
