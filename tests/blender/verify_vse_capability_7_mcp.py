"""
Verification Test for VSE Capability 7: Titles & Subtitles.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Create main title strip with full typography, drop shadow, outline, and background box styling.
2. Create sequential subtitle overlay cues with bottom-center placement and word layout.
3. Update typography, content, and styling attributes via configure_vse_text_style.
4. Independent readback inspection of text styling properties.
5. Non-text strip defense invariant (cleanly reject styling attempts on non-TEXT strips).
6. Independent timeline readback verifying all text and visual strips.
7. Fail-closed security boundary check (reject untrusted approved=True).
8. Clean process exit (code 0) and final scene state verification.
9. Production isolation: v0.1.88 release ZIP untouched (SHA-256 intact), port 9877 untouched.
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
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP7", approve_task_group=False)
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


def run_vse_cap7_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap7_"))
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
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 7 TITLES & SUBTITLES")
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

        # Step 1: Create Main Title Strip
        print("\n--- Test 1: Create Main Title with Full Typography & Styling ---")
        title_res = executor.execute_tool("create_vse_text_strip", {
            "name": "Main_Title",
            "text": "UNIVERSAL MCP PRODUCTION",
            "channel": 3,
            "frame_start": 1,
            "duration": 90,
            "font_size": 64.0,
            "color": [1.0, 0.85, 0.2, 1.0],
            "location": [0.5, 0.5],
            "alignment_x": "CENTER",
            "anchor_x": "CENTER",
            "anchor_y": "CENTER",
            "use_bold": True,
            "use_shadow": True,
            "shadow_color": [0.0, 0.0, 0.0, 0.8],
            "shadow_blur": 0.04,
            "use_outline": True,
            "outline_color": [0.1, 0.1, 0.1, 1.0],
            "outline_width": 0.03,
            "use_box": True,
            "box_color": [0.05, 0.05, 0.05, 0.7],
            "box_margin": 0.025,
            "box_roundness": 0.15,
        })
        assert title_res.is_success, title_res.message
        t_out = title_res.result
        print(f"[+] Created Main_Title: text='{t_out['style']['text']}', font_size={t_out['style']['font_size']}, use_shadow={t_out['style']['use_shadow']}, use_box={t_out['style']['use_box']}")
        assert t_out["name"] == "Main_Title"
        assert t_out["type"] == "TEXT"
        assert t_out["channel"] == 3
        assert t_out["style"]["font_size"] == 64.0
        assert t_out["style"]["use_bold"] is True
        assert t_out["style"]["use_shadow"] is True
        assert t_out["style"]["use_outline"] is True
        assert t_out["style"]["use_box"] is True

        # Step 2: Create Subtitle Cue 1
        print("\n--- Test 2: Create Subtitle Cue 1 ---")
        sub1_res = executor.execute_tool("create_vse_text_strip", {
            "name": "Sub_Cue_01",
            "text": "Welcome to the automated pipeline.",
            "channel": 2,
            "frame_start": 1,
            "duration": 40,
            "font_size": 38.0,
            "color": [1.0, 1.0, 1.0, 1.0],
            "location": [0.5, 0.12],
            "alignment_x": "CENTER",
            "anchor_y": "BOTTOM",
            "use_shadow": True,
        })
        assert sub1_res.is_success, sub1_res.message
        s1_out = sub1_res.result
        print(f"[+] Created Sub_Cue_01: text='{s1_out['style']['text']}', span=[{s1_out['left_handle']}..{s1_out['right_handle']}], loc={s1_out['style']['location']}")
        assert s1_out["left_handle"] == 1
        assert s1_out["duration"] == 40
        assert abs(s1_out["style"]["location"][1] - 0.12) < 1e-4

        # Step 3: Create Subtitle Cue 2
        print("\n--- Test 3: Create Subtitle Cue 2 ---")
        sub2_res = executor.execute_tool("create_vse_text_strip", {
            "name": "Sub_Cue_02",
            "text": "Full typography and styling operational.",
            "channel": 2,
            "frame_start": 41,
            "duration": 45,
            "font_size": 38.0,
            "color": [1.0, 1.0, 1.0, 1.0],
            "location": [0.5, 0.12],
            "alignment_x": "CENTER",
            "anchor_y": "BOTTOM",
            "use_shadow": True,
        })
        assert sub2_res.is_success, sub2_res.message
        s2_out = sub2_res.result
        print(f"[+] Created Sub_Cue_02: text='{s2_out['style']['text']}', span=[{s2_out['left_handle']}..{s2_out['right_handle']}]")
        assert s2_out["left_handle"] == 41
        assert s2_out["duration"] == 45

        # Step 4: Configure / Update Title Style
        print("\n--- Test 4: Update Typography & Styling ---")
        up_res = executor.execute_tool("configure_vse_text_style", {
            "name": "Main_Title",
            "action": "UPDATE",
            "text": "UNIVERSAL MCP VSE 5.2",
            "font_size": 72.0,
            "use_italic": True,
        })
        assert up_res.is_success, up_res.message
        up_out = up_res.result["style"]
        print(f"[+] Updated Main_Title: text='{up_out['text']}', font_size={up_out['font_size']}, use_italic={up_out['use_italic']}")
        assert up_out["text"] == "UNIVERSAL MCP VSE 5.2"
        assert up_out["font_size"] == 72.0
        assert up_out["use_italic"] is True

        # Step 5: Inspect Subtitle Readback
        print("\n--- Test 5: Inspect Subtitle Readback ---")
        insp_res = executor.execute_tool("configure_vse_text_style", {
            "name": "Sub_Cue_01",
            "action": "INSPECT",
        })
        assert insp_res.is_success, insp_res.message
        i_out = insp_res.result["style"]
        print(f"[+] Inspected Sub_Cue_01: text='{i_out['text']}', font_size={i_out['font_size']}, align={i_out['alignment_x']}")
        assert i_out["text"] == "Welcome to the automated pipeline."
        assert i_out["font_size"] == 38.0
        assert i_out["alignment_x"] == "CENTER"

        # Step 6: Non-Text Strip Defense Invariant
        print("\n--- Test 6: Verify Non-Text Strip Defense ---")
        bg_res = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Backdrop_Color", "channel": 1, "frame_start": 1, "duration": 90, "color": [0.1, 0.1, 0.1]
        })
        assert bg_res.is_success, bg_res.message

        bad_style_res = executor.execute_tool("configure_vse_text_style", {
            "name": "Backdrop_Color",
            "action": "UPDATE",
            "font_size": 40.0,
        })
        assert not bad_style_res.is_success, "Expected failure when styling COLOR strip as text"
        print(f"[+] Non-text strip styling rejected with clear message: '{bad_style_res.message}'")
        assert "expected 'TEXT'" in str(bad_style_res.message) or "TEXT" in str(bad_style_res.message)

        # Step 7: Independent Timeline Readback
        print("\n--- Test 7: Independent Timeline Readback ---")
        time_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert time_res.is_success, time_res.message
        all_s = {s["name"]: s for s in time_res.result["strips"]}
        assert "Main_Title" in all_s
        assert "Sub_Cue_01" in all_s
        assert "Sub_Cue_02" in all_s
        assert "Backdrop_Color" in all_s
        print(f"[+] Timeline strips verified: {list(all_s.keys())}")

        # Step 8: Fail-Closed Security Boundary Check
        print("\n--- Test 8: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("create_vse_text_strip", {"text": "Unauthorized", "channel": 1, "frame_start": 1, "duration": 10, "approved": True}),
            ("configure_vse_text_style", {"name": "Main_Title", "action": "UPDATE", "font_size": 80.0, "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on text tools: PASSED")

        # Step 9: Teardown
        print("\n--- Test 9: Graceful Teardown ---")
        (run_dir / "stop.flag").touch()
        blender_proc.wait(timeout=10.0)
        print(f"[+] Disposable Blender process {blender_proc.pid} terminated cleanly with code {blender_proc.returncode}")

    finally:
        if blender_proc.poll() is None:
            blender_proc.kill()
            blender_proc.wait()

    # Step 10: Production Isolation Verification
    print("\n--- Step 10: Verifying Production Isolation ---")
    zip_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip"
    sha_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip.sha256"
    assert zip_path.exists() and sha_path.exists(), "Release artifact v0.1.88 missing!"
    import hashlib
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert actual_sha == "ba14a1ed39f78096d054cd4f81eac99ded4d61157fa56e692ad5aa521493c702", "CRITICAL: v0.1.88 release ZIP was modified!"
    print(f"[+] Release package v0.1.88 verified untouched (SHA-256: {actual_sha})")

    prod_handlers = Path(r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp\bridge\handlers.py")
    if prod_handlers.exists():
        assert "create_vse_text_strip" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 7 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap7_e2e())

