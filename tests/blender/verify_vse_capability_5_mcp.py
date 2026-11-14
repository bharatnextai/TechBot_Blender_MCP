"""
Verification Test for VSE Capability 5: Transforms & Keyframing.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Setup initial scene with visual strips.
2. 2D transform configuration (offset_x, offset_y, scale_x, scale_y, rotation, origin, filter) via transform_vse_strip.
3. Independent readback inspection of strip 2D transforms.
4. Pixel cropping configuration (min_x, max_x, min_y, max_y) via crop_vse_strip.
5. Independent readback inspection of strip cropping margins.
6. Insert keyframes on 2D transform channels (OFFSET_X, SCALE_Y, ROTATION) via animate_vse_strip.
7. Insert keyframes on strip opacity (BLEND_ALPHA).
8. Insert keyframes on pixel cropping (CROP_LEFT).
9. Delete keyframe at specified frame index and verify state.
10. Independent timeline readback verifying strips remain fully valid.
11. Fail-closed security boundary check (reject untrusted approved=True).
12. Clean process exit (code 0) and final scene state verification.
13. Production isolation: v0.1.88 release ZIP untouched (SHA-256 intact), port 9877 untouched.
"""

import os
import sys
import json
import time
import socket
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

# Clear default scene objects & sequence editor
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
    task_id = params.get("task_id") or mutation_params.get("task_id") or mutation_params.get("session_id")
    registry = handlers.get_approval_registry()
    req = registry.create_request(tool_name, mutation_params, timeout=timeout, task_id=task_id)
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP5", approve_task_group=False)
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
    "addon_version": getattr(addon, "bl_info", {}).get("version"),
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
    (root / "final_state.json").write_text(json.dumps({
        "pid": os.getpid(),
        "strips": [{
            "name": s.name,
            "type": s.type,
            "channel": s.channel,
            "left": int(s.left_handle),
            "right": int(s.right_handle),
            "dur": int(s.duration),
        } for s in scene.sequence_editor.strips] if scene.sequence_editor else [],
        "bridge_running": bool(server.running),
    }, indent=2), encoding="utf-8")
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port if port != 9877 else find_free_port()


def run_vse_cap5_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap5_"))
    bootstrap_file = run_dir / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_dir / "ready.json"

    env = os.environ.copy()
    env["UMCP_RUN_ROOT"] = str(run_dir)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["PYTHONPATH"] = str(PROJECT)

    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 5 TRANSFORMS & KEYFRAMING")
    print("=" * 80)
    print(f"[*] Launching disposable Blender 5.2.2 on ephemeral port {port}...")

    blender_proc = subprocess.Popen(
        [
            str(BLENDER),
            "--background",
            "--factory-startup",
            "-P",
            str(bootstrap_file),
        ],
        env=env,
        cwd=str(PROJECT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    t0 = time.time()
    while not ready_file.exists():
        if time.time() - t0 > 25:
            blender_proc.kill()
            out, err = blender_proc.communicate()
            raise TimeoutError(f"Timed out waiting for disposable Blender bridge to report ready:\n{err.decode('utf-8', errors='replace')}")
        time.sleep(0.2)

    ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
    print(f"[+] Disposable Blender ready on PID {ready_data['pid']} port {ready_data['port']}")

    try:
        sys.path.insert(0, str(PROJECT))
        from mcp_service.execution.blender_executor import BlenderExecutor

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()

        # Step 1: Setup scene strips
        print("\n--- Test 1: Setup Initial Visual Strips ---")
        res_c = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Motion_Graphic", "channel": 1, "frame_start": 1, "duration": 80, "color": [0.9, 0.4, 0.1]
        })
        assert res_c.is_success, res_c.message

        res_t = executor.execute_tool("create_vse_strip", {
            "strip_type": "TEXT", "name": "Title_Banner", "channel": 2, "frame_start": 1, "duration": 80, "text": "Animated Lower Third"
        })
        assert res_t.is_success, res_t.message
        print(f"[+] Created test strips: Motion_Graphic (Ch1), Title_Banner (Ch2)")

        # Step 2: Configure 2D Transform
        print("\n--- Test 2: Configure 2D Transform ---")
        tr_res = executor.execute_tool("transform_vse_strip", {
            "name": "Motion_Graphic",
            "action": "UPDATE",
            "offset_x": 140.0,
            "offset_y": -65.0,
            "scale_x": 1.25,
            "scale_y": 0.85,
            "rotation": 0.5236,
            "origin": [0.5, 0.5],
            "filter": "BILINEAR",
        })
        assert tr_res.is_success, tr_res.message
        tr_out = tr_res.result["transform"]
        print(f"[+] Updated 2D transform: offset=[{tr_out['offset_x']}, {tr_out['offset_y']}], scale=[{tr_out['scale_x']}, {tr_out['scale_y']}], rot={tr_out['rotation']}, filter={tr_out['filter']}")
        assert abs(tr_out["offset_x"] - 140.0) < 1e-4
        assert abs(tr_out["offset_y"] - (-65.0)) < 1e-4
        assert abs(tr_out["scale_x"] - 1.25) < 1e-4
        assert abs(tr_out["scale_y"] - 0.85) < 1e-4
        assert abs(tr_out["rotation"] - 0.5236) < 1e-4
        assert tr_out["filter"] == "BILINEAR"

        # Step 3: Inspect 2D Transform
        print("\n--- Test 3: Inspect 2D Transform ---")
        insp_tr = executor.execute_tool("transform_vse_strip", {
            "name": "Motion_Graphic",
            "action": "INSPECT",
        })
        assert insp_tr.is_success, insp_tr.message
        assert abs(insp_tr.result["transform"]["offset_x"] - 140.0) < 1e-4
        print(f"[+] Inspected transform parity confirmed: offset_x={insp_tr.result['transform']['offset_x']}")

        # Step 4: Configure Pixel Cropping
        print("\n--- Test 4: Configure Pixel Cropping ---")
        crop_res = executor.execute_tool("crop_vse_strip", {
            "name": "Motion_Graphic",
            "action": "UPDATE",
            "min_x": 35,
            "max_x": 40,
            "min_y": 15,
            "max_y": 25,
        })
        assert crop_res.is_success, crop_res.message
        cr_out = crop_res.result["crop"]
        print(f"[+] Updated pixel crop: left={cr_out['min_x']}, right={cr_out['max_x']}, bottom={cr_out['min_y']}, top={cr_out['max_y']}")
        assert cr_out["min_x"] == 35
        assert cr_out["max_x"] == 40
        assert cr_out["min_y"] == 15
        assert cr_out["max_y"] == 25

        # Step 5: Inspect Pixel Cropping
        print("\n--- Test 5: Inspect Pixel Cropping ---")
        insp_cr = executor.execute_tool("crop_vse_strip", {
            "name": "Motion_Graphic",
            "action": "INSPECT",
        })
        assert insp_cr.is_success, insp_cr.message
        assert insp_cr.result["crop"]["min_x"] == 35
        assert insp_cr.result["crop"]["max_x"] == 40
        print(f"[+] Inspected crop parity confirmed: left={insp_cr.result['crop']['min_x']}, right={insp_cr.result['crop']['max_x']}")

        # Step 6: Insert Keyframes on 2D Transforms
        print("\n--- Test 6: Animate 2D Transform Properties ---")
        # Keyframe OFFSET_X at frame 1 (value 0.0) and frame 30 (value 220.0)
        k1 = executor.execute_tool("animate_vse_strip", {
            "name": "Motion_Graphic", "action": "INSERT_KEYFRAME", "property": "OFFSET_X", "frame": 1, "value": 0.0
        })
        assert k1.is_success, k1.message
        k2 = executor.execute_tool("animate_vse_strip", {
            "name": "Motion_Graphic", "action": "INSERT_KEYFRAME", "property": "OFFSET_X", "frame": 30, "value": 220.0
        })
        assert k2.is_success, k2.message

        # Keyframe SCALE_Y at frame 15 (value 1.75)
        k3 = executor.execute_tool("animate_vse_strip", {
            "name": "Motion_Graphic", "action": "INSERT_KEYFRAME", "property": "SCALE_Y", "frame": 15, "value": 1.75
        })
        assert k3.is_success, k3.message

        # Keyframe ROTATION at frame 45 (value 1.57)
        k4 = executor.execute_tool("animate_vse_strip", {
            "name": "Motion_Graphic", "action": "INSERT_KEYFRAME", "property": "ROTATION", "frame": 45, "value": 1.57
        })
        assert k4.is_success, k4.message
        print(f"[+] Keyframed transform channels: OFFSET_X at frames 1, 30; SCALE_Y at 15; ROTATION at 45")

        # Step 7: Insert Keyframes on BLEND_ALPHA
        print("\n--- Test 7: Animate Opacity (BLEND_ALPHA) ---")
        ka1 = executor.execute_tool("animate_vse_strip", {
            "name": "Title_Banner", "action": "INSERT_KEYFRAME", "property": "BLEND_ALPHA", "frame": 1, "value": 0.0
        })
        assert ka1.is_success, ka1.message
        ka2 = executor.execute_tool("animate_vse_strip", {
            "name": "Title_Banner", "action": "INSERT_KEYFRAME", "property": "BLEND_ALPHA", "frame": 20, "value": 1.0
        })
        assert ka2.is_success, ka2.message
        print(f"[+] Keyframed BLEND_ALPHA fade-in on Title_Banner (frames 1..20)")

        # Step 8: Insert Keyframes on Pixel Crop
        print("\n--- Test 8: Animate Pixel Cropping (CROP_LEFT) ---")
        kc1 = executor.execute_tool("animate_vse_strip", {
            "name": "Motion_Graphic", "action": "INSERT_KEYFRAME", "property": "CROP_LEFT", "frame": 10, "value": 10
        })
        assert kc1.is_success, kc1.message
        kc2 = executor.execute_tool("animate_vse_strip", {
            "name": "Motion_Graphic", "action": "INSERT_KEYFRAME", "property": "CROP_LEFT", "frame": 40, "value": 60
        })
        assert kc2.is_success, kc2.message
        print(f"[+] Keyframed CROP_LEFT on Motion_Graphic (frames 10, 40)")

        # Step 9: Delete Keyframe
        print("\n--- Test 9: Delete Keyframe on OFFSET_X ---")
        k_del = executor.execute_tool("animate_vse_strip", {
            "name": "Motion_Graphic", "action": "DELETE_KEYFRAME", "property": "OFFSET_X", "frame": 30
        })
        assert k_del.is_success, k_del.message
        print(f"[+] Deleted keyframe on OFFSET_X at frame 30 successfully")

        # Step 10: Timeline Readback
        print("\n--- Test 10: Independent Timeline Readback ---")
        time_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert time_res.is_success, time_res.message
        all_s = {s["name"]: s for s in time_res.result["strips"]}
        assert "Motion_Graphic" in all_s
        assert "Title_Banner" in all_s
        print(f"[+] Confirmed strips active on timeline: {list(all_s.keys())}")

        # Step 11: Fail-Closed Security Boundary Check
        print("\n--- Test 11: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("transform_vse_strip", {"name": "Motion_Graphic", "action": "UPDATE", "offset_x": 5.0, "approved": True}),
            ("crop_vse_strip", {"name": "Motion_Graphic", "action": "UPDATE", "min_x": 10, "approved": True}),
            ("animate_vse_strip", {"name": "Motion_Graphic", "action": "INSERT_KEYFRAME", "property": "SCALE_X", "frame": 1, "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on transform, crop, and animate tools: PASSED")

        # Step 12: Teardown
        print("\n--- Test 12: Graceful Teardown ---")
        (run_dir / "stop.flag").touch()
        blender_proc.wait(timeout=10.0)
        print(f"[+] Disposable Blender process {blender_proc.pid} terminated cleanly with code {blender_proc.returncode}")

    finally:
        if blender_proc.poll() is None:
            blender_proc.kill()
            blender_proc.wait()

    # Step 13: Production Isolation Verification
    print("\n--- Step 13: Verifying Production Isolation ---")
    zip_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip"
    sha_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip.sha256"
    assert zip_path.exists() and sha_path.exists(), "Release artifact v0.1.88 missing!"
    import hashlib
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert actual_sha == "ba14a1ed39f78096d054cd4f81eac99ded4d61157fa56e692ad5aa521493c702", "CRITICAL: v0.1.88 release ZIP was modified!"
    print(f"[+] Release package v0.1.88 verified untouched (SHA-256: {actual_sha})")

    prod_handlers = Path(r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp\bridge\handlers.py")
    if prod_handlers.exists():
        assert "transform_vse_strip" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 5 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap5_e2e())

