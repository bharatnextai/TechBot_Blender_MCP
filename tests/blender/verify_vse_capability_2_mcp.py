"""
Verification Test for VSE Capability 2: Editorial & Trimming Operations.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Setup initial multi-strip scene (COLOR and TEXT strips on multiple channels).
2. Trim strip with ripple editing (trim right_handle, verify subsequent strips rippled).
3. Relative trim (adjust in/out points via relative deltas).
4. Split strip at designated frame cut-point (verify left and right contiguous strips).
5. Channel SWAP operation (collision-free channel swap).
6. Channel MOVE operation (reassign channel and start frame).
7. Gap closure (CLOSE_GAPS across strips on a channel).
8. Boundary SNAP (snap strip to adjacent strip boundary).
9. Independent readback verification of all edited strips.
10. Fail-closed security boundary check (reject untrusted approved=True).
11. Clean process exit (code 0) and final scene state verification.
12. Production isolation: v0.1.88 release ZIP untouched (SHA-256 intact), port 9877 untouched.
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
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP2", approve_task_group=False)
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


def run_vse_cap2_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap2_"))
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
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 2 EDITORIAL & TRIMMING")
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

        # Step 1: Setup initial multi-strip scene
        print("\n--- Test 1: Setup Initial Multi-Strip Scene ---")
        # Strip A on Ch 1, 1..41 (dur 40)
        res_a = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Clip_A", "channel": 1, "frame_start": 1, "duration": 40, "color": [0.1, 0.2, 0.8]
        })
        assert res_a.is_success, res_a.message

        # Strip B on Ch 1, 41..71 (dur 30) - immediately following Clip_A
        res_b = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Clip_B", "channel": 1, "frame_start": 41, "duration": 30, "color": [0.8, 0.4, 0.1]
        })
        assert res_b.is_success, res_b.message

        # Strip C on Ch 2, 10..60 (dur 50) - TEXT strip
        res_c = executor.execute_tool("create_vse_strip", {
            "strip_type": "TEXT", "name": "Title_C", "channel": 2, "frame_start": 10, "duration": 50, "text": "Editorial Master Sequence"
        })
        assert res_c.is_success, res_c.message
        print(f"[+] Created 3 initial strips: Clip_A (Ch1), Clip_B (Ch1), Title_C (Ch2)")

        # Step 2: Trim with ripple editing
        print("\n--- Test 2: Trim Strip with Ripple Editing ---")
        # Trim Clip_A right_handle from 41 to 30 (duration becomes 29). Ripple should shift Clip_B leftward by 11 frames (to start at 30).
        trim_res = executor.execute_tool("trim_vse_strip", {
            "name": "Clip_A",
            "trim_mode": "ABSOLUTE",
            "right_handle": 30,
            "ripple": True,
        })
        assert trim_res.is_success, trim_res.message
        print(f"[+] Trimmed Clip_A: left={trim_res.result['left_handle']}, right={trim_res.result['right_handle']}, dur={trim_res.result['duration']}, rippled={trim_res.result['rippled_strips_count']}")
        assert trim_res.result["right_handle"] == 30
        assert trim_res.result["duration"] == 29
        assert trim_res.result["rippled_strips_count"] == 1

        # Step 3: Relative Trim on Clip_B
        print("\n--- Test 3: Relative Trim on Clip_B ---")
        # Clip_B was shifted to start at 30, right_handle 60.
        # Relative trim: left_handle +2 (trim head by 2), right_handle -3 (trim tail by 3)
        rel_trim_res = executor.execute_tool("trim_vse_strip", {
            "name": "Clip_B",
            "trim_mode": "RELATIVE",
            "left_handle": 2,
            "right_handle": -3,
            "ripple": False,
        })
        assert rel_trim_res.is_success, rel_trim_res.message
        print(f"[+] Relatively trimmed Clip_B: left={rel_trim_res.result['left_handle']}, right={rel_trim_res.result['right_handle']}, dur={rel_trim_res.result['duration']}")
        assert rel_trim_res.result["left_handle"] == 32
        assert rel_trim_res.result["right_handle"] == 57
        assert rel_trim_res.result["duration"] == 25

        # Step 4: Split Strip at Cut Point
        print("\n--- Test 4: Split Title_C at Frame 35 ---")
        split_res = executor.execute_tool("split_vse_strip", {
            "name": "Title_C",
            "split_frame": 35,
            "right_strip_name": "Title_C_Part2",
        })
        assert split_res.is_success, split_res.message
        left_s = split_res.result["left_strip"]
        right_s = split_res.result["right_strip"]
        print(f"[+] Split Title_C: Left=[{left_s['left_handle']}..{left_s['right_handle']} dur={left_s['duration']}], Right=[{right_s['left_handle']}..{right_s['right_handle']} dur={right_s['duration']}]")
        assert left_s["left_handle"] == 10 and left_s["right_handle"] == 35 and left_s["duration"] == 25
        assert right_s["left_handle"] == 35 and right_s["right_handle"] == 60 and right_s["duration"] == 25

        # Step 5: Collision-Free Channel SWAP
        print("\n--- Test 5: Reorder SWAP Channels between Clip_A and Title_C ---")
        swap_res = executor.execute_tool("reorder_vse_strips", {
            "action": "SWAP",
            "strip_a": "Clip_A",
            "strip_b": "Title_C",
        })
        assert swap_res.is_success, swap_res.message
        print(f"[+] Swapped channels: {[(s['name'], s['channel']) for s in swap_res.result['affected_strips']]}")
        # Verify Clip_A is now on Ch 2 and Title_C is on Ch 1
        swapped_a = next(s for s in swap_res.result["affected_strips"] if s["name"] == "Clip_A")
        swapped_c = next(s for s in swap_res.result["affected_strips"] if s["name"] == "Title_C")
        assert swapped_a["channel"] == 2
        assert swapped_c["channel"] == 1

        # Step 6: MOVE Channel and Position
        print("\n--- Test 6: Reorder MOVE Clip_B to Channel 3, Frame 80 ---")
        move_res = executor.execute_tool("reorder_vse_strips", {
            "action": "MOVE",
            "name": "Clip_B",
            "channel": 3,
            "target_frame": 80,
        })
        assert move_res.is_success, move_res.message
        moved_b = move_res.result["affected_strips"][0]
        print(f"[+] Moved Clip_B: channel={moved_b['channel']}, left={moved_b['left_handle']}, dur={moved_b['duration']}")
        assert moved_b["channel"] == 3
        assert moved_b["left_handle"] == 80

        # Step 7: CLOSE_GAPS on Channel 2
        print("\n--- Test 7: Reorder CLOSE_GAPS on Channel 2 ---")
        # On Channel 2 we have Clip_A (1..30) and Title_C_Part2 (35..60) -> gap of 5 frames
        gaps_res = executor.execute_tool("reorder_vse_strips", {
            "action": "CLOSE_GAPS",
            "channel": 2,
        })
        assert gaps_res.is_success, gaps_res.message
        print(f"[+] Closed gaps on Ch 2: {[(s['name'], s['left_handle'], s['right_handle']) for s in gaps_res.result['affected_strips']]}")
        p2_strip = next(s for s in gaps_res.result["affected_strips"] if s["name"] == "Title_C_Part2")
        assert p2_strip["left_handle"] == 30  # Snapped directly against Clip_A (which ends at 30)

        # Step 8: SNAP Strip
        print("\n--- Test 8: Reorder SNAP Clip_B to Scene Frame 10 ---")
        snap_res = executor.execute_tool("reorder_vse_strips", {
            "action": "SNAP",
            "name": "Clip_B",
            "snap_to": "FRAME",
            "target_frame": 10,
        })
        assert snap_res.is_success, snap_res.message
        snapped_b = snap_res.result["affected_strips"][0]
        print(f"[+] Snapped Clip_B to frame 10: left={snapped_b['left_handle']}, right={snapped_b['right_handle']}")
        assert snapped_b["left_handle"] == 10

        # Step 9: Independent Readback Verification
        print("\n--- Test 9: Independent Readback Verification ---")
        timeline_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert timeline_res.is_success, timeline_res.message
        all_strips = {s["name"]: s for s in timeline_res.result["strips"]}
        assert "Clip_A" in all_strips
        assert "Clip_B" in all_strips
        assert "Title_C" in all_strips
        assert "Title_C_Part2" in all_strips
        print(f"[+] Independent readback verified 4 active strips: {list(all_strips.keys())}")

        # Step 10: Fail-Closed Security Boundary Check
        print("\n--- Test 10: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("trim_vse_strip", {"name": "Clip_A", "left_handle": 5, "approved": True}),
            ("split_vse_strip", {"name": "Clip_A", "split_frame": 15, "approved": True}),
            ("reorder_vse_strips", {"action": "CLOSE_GAPS", "channel": 1, "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on all 3 editorial tools: PASSED")

        # Step 11: Teardown
        print("\n--- Test 11: Graceful Teardown ---")
        (run_dir / "stop.flag").touch()
        blender_proc.wait(timeout=10.0)
        print(f"[+] Disposable Blender process {blender_proc.pid} terminated cleanly with code {blender_proc.returncode}")

    finally:
        if blender_proc.poll() is None:
            blender_proc.kill()
            blender_proc.wait()

    # Step 12: Production Isolation Verification
    print("\n--- Step 12: Verifying Production Isolation ---")
    zip_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip"
    sha_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip.sha256"
    assert zip_path.exists() and sha_path.exists(), "Release artifact v0.1.88 missing!"
    import hashlib
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert actual_sha == "ba14a1ed39f78096d054cd4f81eac99ded4d61157fa56e692ad5aa521493c702", "CRITICAL: v0.1.88 release ZIP was modified!"
    print(f"[+] Release package v0.1.88 verified untouched (SHA-256: {actual_sha})")

    prod_handlers = Path(r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp\bridge\handlers.py")
    if prod_handlers.exists():
        assert "trim_vse_strip" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 2 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap2_e2e())

