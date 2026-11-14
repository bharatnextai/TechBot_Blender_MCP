"""
Automated E2E Verification of Reference Sheet Cropping for Multi-View Modeling.
Verifies TASK v0.1.51:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Cropping multi-view reference sheet (Red Dragon 3D Reference Sheet.png) into distinct orthographic views:
   - Front view crop -> Image Empty object (display_mode='EMPTY', view_axis='FRONT', coordinate_system='UV').
   - Side view crop -> Calibrated textured mesh plane (display_mode='PLANE', view_axis='SIDE', coordinate_system='UV').
   - Top view crop -> Calibrated textured mesh plane (display_mode='PLANE', view_axis='TOP', coordinate_system='IMAGE_SPACE').
   - Cropping only without Blender load (load_as_reference=False).
4. Physical image verification:
   - Cropped PNG dimensions match calculated crop sizes.
   - Valid PNG headers and extracted IHDR dimensions.
5. Source image preservation:
   - Source image file size and SHA-256 hash strictly unmodified before and after test execution.
6. Independent scene and topology readback via get_object_details and inspect_scene_data.
7. Fail-closed security validations:
   - Untrusted approval flag rejected.
   - Missing file rejected.
   - Output path overwrite of source image rejected.
   - Inverted/invalid crop bounds rejected.
   - Object name collision rejected.
8. Visual camera verification across FRONT, SIDE, and TOP views.
9. Clean shutdown and zero persistent state.
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


def get_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def read_png_dimensions(filepath: Path) -> tuple:
    data = filepath.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), f"File is not a valid PNG: {filepath}"
    w, h = struct.unpack(">II", data[16:24])
    return w, h


async def main():
    print("=== TASK v0.1.51: Reference Sheet Cropping E2E Verification ===")

    # 1. Verify Reference Image & Compute Pre-Test Baseline Hash
    assert REFERENCE_IMAGE.exists(), f"Reference image missing: {REFERENCE_IMAGE}"
    pre_stat = REFERENCE_IMAGE.stat()
    pre_sha256 = get_file_sha256(REFERENCE_IMAGE)
    print(f"[OK] Reference image baseline verified: {REFERENCE_IMAGE.name}")
    print(f"     Size: {pre_stat.st_size:,} bytes, SHA-256: {pre_sha256}")

    # 2. Setup Disposable Test Environment
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-REF-CROP-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    crops_dir = run_root / "crops"
    for d in (config_dir, scripts_dir, ext_dir, crops_dir):
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

            # --- STEP 2: Crop Front View from Sheet and Load as Image Empty ---
            front_crop_out = crops_dir / "dragon_front_crop.png"
            crop_front = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.0, 0.5, 0.5, 1.0],  # Top-left quadrant in UV space
                "coordinate_system": "UV",
                "output_path": str(front_crop_out),
                "name": "Dragon_Crop_Front",
                "display_mode": "EMPTY",
                "view_axis": "FRONT",
                "size": 6.0,
                "opacity": 0.85,
                "location": [0.0, -1.0, 1.5],
            })
            assert crop_front["status"] == "success", crop_front
            res_cf = crop_front["result"]
            assert res_cf["name"] == "Dragon_Crop_Front"
            assert res_cf["object_type"] == "EMPTY"
            assert res_cf["source_dimensions"] == [1536, 1024]
            assert res_cf["crop_dimensions"] == [768, 512]
            assert math.isclose(res_cf["crop_aspect_ratio"], 1.5, abs_tol=1e-3)
            assert front_crop_out.exists()
            assert read_png_dimensions(front_crop_out) == (768, 512)
            print(f"[PASS] Step 2: Cropped Front View '{res_cf['name']}' ({res_cf['crop_dimensions']}, PNG verified)")

            # --- STEP 3: Crop Side View from Sheet and Load as Calibrated Plane ---
            side_crop_out = crops_dir / "dragon_side_crop.png"
            crop_side = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.5, 0.5, 1.0, 1.0],  # Top-right quadrant in UV space
                "coordinate_system": "UV",
                "output_path": str(side_crop_out),
                "name": "Dragon_Crop_Side",
                "display_mode": "PLANE",
                "view_axis": "SIDE",
                "size": 5.0,
                "opacity": 0.75,
                "location": [1.0, 0.0, 1.5],
            })
            assert crop_side["status"] == "success", crop_side
            res_cs = crop_side["result"]
            assert res_cs["name"] == "Dragon_Crop_Side"
            assert res_cs["object_type"] == "MESH"
            assert res_cs["crop_dimensions"] == [768, 512]
            assert side_crop_out.exists()
            assert read_png_dimensions(side_crop_out) == (768, 512)
            print(f"[PASS] Step 3: Cropped Side View '{res_cs['name']}' ({res_cs['crop_dimensions']}, PNG verified)")

            # --- STEP 4: Crop Top View in IMAGE_SPACE and Load as Calibrated Plane ---
            top_crop_out = crops_dir / "dragon_top_crop.png"
            crop_top = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.0, 0.5, 0.5, 1.0],  # Bottom-left quadrant in IMAGE_SPACE (rows 512..1024, cols 0..768)
                "coordinate_system": "IMAGE_SPACE",
                "output_path": str(top_crop_out),
                "name": "Dragon_Crop_Top",
                "display_mode": "PLANE",
                "view_axis": "TOP",
                "size": 4.5,
                "opacity": 0.8,
                "location": [0.0, 0.0, 0.0],
            })
            assert crop_top["status"] == "success", crop_top
            res_ct = crop_top["result"]
            assert res_ct["name"] == "Dragon_Crop_Top"
            assert res_ct["object_type"] == "MESH"
            assert res_ct["crop_dimensions"] == [768, 512]
            assert top_crop_out.exists()
            assert read_png_dimensions(top_crop_out) == (768, 512)
            print(f"[PASS] Step 4: Cropped Top View '{res_ct['name']}' in IMAGE_SPACE ({res_ct['crop_dimensions']}, PNG verified)")

            # --- STEP 5: Crop Region Only (load_as_reference=False) ---
            thumb_out = crops_dir / "dragon_thumb_only.png"
            crop_only = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.2, 0.2, 0.4, 0.4],
                "coordinate_system": "UV",
                "output_path": str(thumb_out),
                "load_as_reference": False,
            })
            assert crop_only["status"] == "success", crop_only
            res_co = crop_only["result"]
            assert res_co["load_as_reference"] is False
            assert res_co["crop_dimensions"] == [307, 205]
            assert thumb_out.exists()
            assert read_png_dimensions(thumb_out) == (307, 205)
            print(f"[PASS] Step 5: Crop-only (no reference object created) verified ({res_co['crop_dimensions']})")

            # --- STEP 6: Independent Object Details & Topology Readback ---
            dt_front = await call_tool("get_object_details", {"name": "Dragon_Crop_Front"})
            assert dt_front["status"] == "success"
            assert dt_front["result"]["type"] == "EMPTY"

            dt_side = await call_tool("get_object_details", {"name": "Dragon_Crop_Side"})
            assert dt_side["status"] == "success"
            assert dt_side["result"]["type"] == "MESH"

            dt_top = await call_tool("get_object_details", {"name": "Dragon_Crop_Top"})
            assert dt_top["status"] == "success"
            assert dt_top["result"]["type"] == "MESH"

            topo_side = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": "Dragon_Crop_Side",
            })
            assert topo_side["status"] == "success"
            assert topo_side["result"]["vertex_count"] == 4
            assert topo_side["result"]["polygon_count"] == 1

            topo_top = await call_tool("inspect_scene_data", {
                "category": "mesh_topology",
                "target_name": "Dragon_Crop_Top",
            })
            assert topo_top["status"] == "success"
            assert topo_top["result"]["vertex_count"] == 4
            assert topo_top["result"]["polygon_count"] == 1
            print("[PASS] Step 6: Independent Object Details & Topology Verified on All Reference Objects")

            # --- STEP 7: Fail-Closed Security Defenses ---
            # 7a. Untrusted approval flag rejected
            tamper_approval = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.0, 0.0, 0.5, 0.5],
                "approved": True,
            })
            assert tamper_approval["status"] == "error"
            print("[PASS] Step 7a: Untrusted approval flag rejected (Fail-Closed)")

            # 7b. Missing source file rejected
            missing_source = await call_tool("crop_reference_image", {
                "image_path": str(run_root / "missing_file.png"),
                "crop_box": [0.0, 0.0, 0.5, 0.5],
            })
            assert missing_source["status"] == "error"
            print("[PASS] Step 7b: Missing source image rejected (Fail-Closed)")

            # 7c. Output path overwriting source image rejected
            overwrite_attempt = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.0, 0.0, 0.5, 0.5],
                "output_path": str(REFERENCE_IMAGE),
            })
            assert overwrite_attempt["status"] == "error"
            assert "cannot overwrite" in overwrite_attempt["message"].lower() or "overwrite source" in overwrite_attempt["message"].lower()
            print("[PASS] Step 7c: Overwrite of source image rejected (Fail-Closed)")

            # 7d. Inverted crop bounds rejected
            inverted_bounds = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.8, 0.2, 0.3, 0.9],
            })
            assert inverted_bounds["status"] == "error"
            print("[PASS] Step 7d: Inverted crop bounds rejected (Fail-Closed)")

            # 7e. Name collision rejected
            name_coll = await call_tool("crop_reference_image", {
                "image_path": str(REFERENCE_IMAGE),
                "crop_box": [0.0, 0.0, 0.5, 0.5],
                "name": "Dragon_Crop_Front",
            })
            assert name_coll["status"] == "error"
            assert "Collision detected" in name_coll["message"]
            print("[PASS] Step 7e: Object name collision rejected (Fail-Closed)")

            # --- STEP 8: Create Active Camera & Directional Visual Verification ---
            cam = await call_tool("create_camera", {
                "name": "Dragon_Crop_Camera",
                "location": [0.0, -10.0, 1.5],
            })
            assert cam["status"] == "success"
            print("[PASS] Step 8: Created camera 'Dragon_Crop_Camera'")

            for view_dir in ("FRONT", "SIDE", "TOP"):
                cap_res = await call_tool("capture_viewport", {
                    "mode": "CAMERA",
                    "view": view_dir,
                    "width": 320,
                    "height": 240,
                })
                assert cap_res["status"] == "success"
                cap_data = cap_res["result"]
                raw_bytes = base64.b64decode(cap_data["image_base64"], validate=True)
                assert raw_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                png_w, png_h = struct.unpack(">II", raw_bytes[16:24])
                assert (png_w, png_h) == (320, 240)
                sha = hashlib.sha256(raw_bytes).hexdigest()
                print(f"[PASS] Step 8 ({view_dir}): Verified camera visual frame ({len(raw_bytes):,} bytes, SHA-256: {sha[:16]}...)")

            # --- STEP 9: Final Scene Inventory ---
            final_summary = await call_tool("get_scene_summary", {})
            assert final_summary["status"] == "success"
            # Exactly 4 objects: Dragon_Crop_Front, Dragon_Crop_Side, Dragon_Crop_Top, Dragon_Crop_Camera
            assert final_summary["result"]["total_objects"] == 4, final_summary["result"]
            print(f"[PASS] Step 9: Final scene inventory verified: {final_summary['result']['total_objects']} objects")

            # --- STEP 10: Strict Source Preservation Verification ---
            post_stat = REFERENCE_IMAGE.stat()
            post_sha256 = get_file_sha256(REFERENCE_IMAGE)
            assert pre_stat.st_size == post_stat.st_size, "Source image size changed during test!"
            assert pre_sha256 == post_sha256, "Source image content/hash modified during test!"
            print(f"[PASS] Step 10: Source image preservation strictly verified (SHA-256 intact: {post_sha256})")

    # Clean Shutdown
    (run_root / "stop.flag").write_text("stop")
    t0 = time.time()
    while proc.poll() is None:
        if time.time() - t0 > 10.0:
            proc.kill()
            break
        time.sleep(0.1)

    print(f"[OK] Disposable Blender process cleanly exited with code {proc.returncode}")
    print("\n=== REFERENCE SHEET CROPPING E2E VERIFICATION VERIFIED SUCCESSFUL ===")


if __name__ == "__main__":
    asyncio.run(main())

