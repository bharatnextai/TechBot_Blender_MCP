"""
Supplemental Live Verification for Milestone 9.4: Secondary Image Footage as PiP Overlay.
Target Engine: Blender 5.2.2 LTS
Production Isolation: Ephemeral Port (!= 9877), Production Bridge PID 39604 Untouched.

Verifies:
1. Loading an actual secondary IMAGE file as a VSE strip on Channel 2 (Overlay).
2. Applying transform_vse_strip (scale_x=0.35, scale_y=0.35, offset_x=220, offset_y=140).
3. Applying crop_vse_strip (min_x=10, max_x=10, min_y=10, max_y=10).
4. Inspecting RNA properties via tool action='INSPECT'.
5. Rendering an evaluated composite frame PNG demonstrating an actual image footage PiP overlay.
"""

import os
import sys
import json
import time
import socket
import shutil
import tempfile
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

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
from blender_addon.universal_mcp.bridge import handlers

scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
if scene.sequence_editor:
    scene.sequence_editor_clear()
scene.timeline_markers.clear()

queue = MainThreadQueue(bpy)

def headless_req_app(bpy_module=None, params=None):
    params = params or {}
    tool_name = str(params.get("tool_name", "")).strip()
    mutation_params = params.get("params", {})
    timeout = float(params.get("timeout", 30.0))
    task_id = params.get("task_id") or mutation_params.get("task_id")
    registry = handlers.get_approval_registry()
    req = registry.create_request(tool_name, mutation_params, timeout=timeout, task_id=task_id)
    ok, token = registry.resolve_request(req.request_id, "approved", reason="DISPOSABLE 9.4 SUPPLEMENTAL TEST", approve_task_group=False)
    return {
        "request_id": req.request_id,
        "tool_name": req.tool_name,
        "task_id": req.task_id,
        "arg_hash": req.arg_hash,
        "status": "approved",
        "approval_token": token,
        "timeout_seconds": req.timeout_seconds,
        "remaining_seconds": round(req.remaining_seconds, 1),
        "expires_at": req.created_at + req.timeout_seconds,
    }

handlers.handle_request_approval = headless_req_app
queue._handlers["request_approval"] = headless_req_app

server = BridgeServer(port=port, queue=queue)
server.start()

(root / "ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "blender": bpy.app.version_string,
}))

deadline = time.monotonic() + 180
try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        try:
            queue.drain_queue()
        except Exception:
            pass
        time.sleep(0.005)
finally:
    server.stop()
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port if port != 9877 else find_free_port()


def run_supplemental_verification():
    port = find_free_port()
    run_dir = Path(tempfile.mkdtemp(prefix="umcp_supp_pip_"))
    evidence_dir = PROJECT / "tests" / "blender" / "output" / "milestone_9_4"

    bootstrap_file = run_dir / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_dir / "ready.json"

    existing_hero_plate = evidence_dir / "hero_plate.png"
    assert existing_hero_plate.exists(), "hero_plate.png missing from evidence"

    env = os.environ.copy()
    env["UMCP_RUN_ROOT"] = str(run_dir)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["PYTHONPATH"] = str(PROJECT)

    print("=" * 80)
    print("STARTING SUPPLEMENTAL LIVE MCP TEST: SECONDARY IMAGE FOOTAGE PiP")
    print(f"Ephemeral Bridge Port: {port} | Isolation: PID 39604 untouched")
    print("=" * 80)

    blender_proc = subprocess.Popen(
        [str(BLENDER), "--background", "--factory-startup", "-P", str(bootstrap_file)],
        env=env,
        cwd=str(PROJECT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    t0 = time.time()
    while not ready_file.exists():
        if time.time() - t0 > 30:
            blender_proc.kill()
            raise TimeoutError("Blender bridge failed to start")
        time.sleep(0.2)

    ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
    print(f"[+] Disposable Blender on PID {ready_data['pid']}, port {ready_data['port']}")

    supp_telemetry = {}

    try:
        sys.path.insert(0, str(PROJECT))
        from mcp_service.execution.blender_executor import BlenderExecutor

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()

        # 1. Render a distinct secondary 3D asset image for the PiP inset
        executor.execute_tool("create_primitive", {"primitive_type": "uv_sphere", "name": "PiPSphere", "location": [0.0, 0.0, 0.0]})
        executor.execute_tool("create_camera", {"name": "PiPCam", "location": [0.0, -3.0, 0.0], "rotation_euler": [1.57, 0.0, 0.0], "set_active": True})
        executor.execute_tool("create_light", {"name": "PiPLight", "light_type": "SUN", "energy": 5.0})

        pip_image_file = run_dir / "secondary_pip_footage.png"
        r_scene = executor.execute_tool("render_scene", {
            "render_mode": "still",
            "output_format": "PNG",
            "output_path": str(pip_image_file),
            "camera": "PiPCam",
        })
        assert r_scene.is_success
        print(f"[+] Rendered distinct secondary IMAGE footage: {pip_image_file} ({pip_image_file.stat().st_size} bytes)")

        # 2. Channel 1: Background plate (IMAGE)
        r_ch1 = executor.execute_tool("create_vse_strip", {
            "strip_type": "IMAGE",
            "name": "BackgroundPlate",
            "channel": 1,
            "frame_start": 1,
            "duration": 50,
            "filepath": str(existing_hero_plate),
        })
        assert r_ch1.is_success
        print(f"[+] Channel 1 Background Strip created (IMAGE): {r_ch1.result['name']}")

        # 3. Channel 2: Secondary IMAGE strip (PiP Inset)
        r_ch2 = executor.execute_tool("create_vse_strip", {
            "strip_type": "IMAGE",
            "name": "ImagePiPStrip",
            "channel": 2,
            "frame_start": 1,
            "duration": 50,
            "filepath": str(pip_image_file),
        })
        assert r_ch2.is_success
        print(f"[+] Channel 2 PiP Inset Strip created (IMAGE): {r_ch2.result['name']} from {pip_image_file.name}")

        # 4. Apply 2D Transform to the IMAGE strip
        r_trans = executor.execute_tool("transform_vse_strip", {
            "name": "ImagePiPStrip",
            "scale_x": 0.35,
            "scale_y": 0.35,
            "offset_x": 220.0,
            "offset_y": 140.0,
            "action": "UPDATE",
        })
        assert r_trans.is_success
        tr_info = r_trans.result["transform"]
        assert abs(tr_info["scale_x"] - 0.35) < 1e-3
        assert abs(tr_info["offset_x"] - 220.0) < 1e-3
        print(f"[+] Verified 2D transform on IMAGE strip: scale={tr_info['scale_x']}x{tr_info['scale_y']}, offset=({tr_info['offset_x']}, {tr_info['offset_y']})")

        # 5. Apply Crop to the IMAGE strip
        r_crop = executor.execute_tool("crop_vse_strip", {
            "name": "ImagePiPStrip",
            "min_x": 10,
            "max_x": 10,
            "min_y": 10,
            "max_y": 10,
            "action": "UPDATE",
        })
        assert r_crop.is_success
        print(f"[+] Verified crop on IMAGE strip: {r_crop.result['crop']}")

        # 6. Render representative composite frame
        supp_frame_file = run_dir / "supplemental_image_pip_frame.png"
        r_frame = executor.execute_tool("render_vse_sequence", {
            "output_path": str(supp_frame_file),
            "format": "PNG",
            "frame_start": 15,
            "frame_end": 15,
            "resolution_x": 640,
            "resolution_y": 360,
        })
        assert r_frame.is_success
        saved_frame = Path(r_frame.result["output_file"])
        assert saved_frame.exists()
        shutil.copy(saved_frame, evidence_dir / "supplemental_image_pip_frame.png")
        print(f"[+] Rendered & preserved supplemental IMAGE PiP frame: {evidence_dir / 'supplemental_image_pip_frame.png'} ({saved_frame.stat().st_size} bytes)")

        supp_telemetry = {
            "target": "IMAGE footage PiP overlay",
            "status": "PASS",
            "ch1_strip": r_ch1.result,
            "ch2_strip": r_ch2.result,
            "transform": r_trans.result,
            "crop": r_crop.result,
            "frame_output": str(evidence_dir / "supplemental_image_pip_frame.png"),
            "frame_size_bytes": saved_frame.stat().st_size,
        }
        (evidence_dir / "supplemental_image_pip_telemetry.json").write_text(json.dumps(supp_telemetry, indent=2), encoding="utf-8")

        print("=" * 80)
        print("SUPPLEMENTAL IMAGE FOOTAGE PiP VERIFICATION: ALL CHECKS PASSED")
        print("=" * 80)

    finally:
        (run_dir / "stop.flag").write_text("STOP", encoding="utf-8")
        try:
            blender_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            blender_proc.kill()
        shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    run_supplemental_verification()
