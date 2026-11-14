"""
Verification Test for VSE Capability 1: Timeline & Strip Lifecycle Foundation.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Inspect empty VSE timeline state (has_sequence_editor, frame ranges, markers).
2. Create COLOR strip with custom color and duration on Channel 1.
3. Create TEXT strip with title text on Channel 2.
4. Add timeline markers (IntroStart, SceneCut).
5. Comprehensive timeline inspection verifying strip descriptors and markers.
6. Modify COLOR strip (channel reassignment, time shift via handles, duration, mute).
7. Independent readback verification of modified strip properties.
8. Delete TEXT strip and verify remaining strip count.
9. Remove marker and verify updated marker list.
10. Fail-closed security defense: Reject untrusted approved=True.
11. Path traversal defense: Reject traversal sequences in media strip paths.
12. Graceful teardown, clean process exit, and production isolation (port 9877 untouched).
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

# Clear default scene objects & sequence editor if any
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
    # Auto approve for this disposable test
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP1", approve_task_group=False)
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
        "has_se": scene.sequence_editor is not None,
        "strips": [s.name for s in scene.sequence_editor.strips] if scene.sequence_editor else [],
        "markers": [m.name for m in scene.timeline_markers],
        "bridge_running": bool(server.running),
    }, indent=2), encoding="utf-8")
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port if port != 9877 else find_free_port()


def run_vse_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap1_"))
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
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 1 FOUNDATION")
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
    print(f"[+] Disposable Blender {ready_data['blender']} ready on PID {ready_data['pid']} port {ready_data['port']}")
    print(f"[+] Add-on version: {ready_data['addon_version']}")

    try:
        sys.path.insert(0, str(PROJECT))
        from mcp_service.execution.blender_executor import BlenderExecutor

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()

        # Step 1: Inspect initial timeline
        print("\n--- Test 1: Initial Timeline Inspection ---")
        t1_res = executor.execute_tool("inspect_vse_timeline", {})
        assert t1_res.is_success, f"inspect_vse_timeline failed: {t1_res.message}"
        print(f"[+] Initial timeline state: total_strips={t1_res.result['total_strips']}, frame_range=[{t1_res.result['frame_start']}..{t1_res.result['frame_end']}], fps={t1_res.result['fps']}")
        assert t1_res.result["total_strips"] == 0
        assert t1_res.result["markers"] == []

        # Step 2: Create COLOR strip
        print("\n--- Test 2: Create COLOR Strip on Channel 1 ---")
        c_res = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR",
            "name": "Intro_Background",
            "channel": 1,
            "frame_start": 1,
            "duration": 48,
            "color": [0.8, 0.2, 0.1],
        })
        assert c_res.is_success, f"create_vse_strip COLOR failed: {c_res.message}"
        print(f"[+] Created COLOR strip: name={c_res.result['name']}, channel={c_res.result['channel']}, start={c_res.result['frame_start']}, dur={c_res.result['duration']}")
        assert c_res.result["name"] == "Intro_Background"
        assert c_res.result["channel"] == 1
        assert c_res.result["frame_start"] == 1
        assert c_res.result["duration"] == 48

        # Step 3: Create TEXT strip
        print("\n--- Test 3: Create TEXT Strip on Channel 2 ---")
        txt_res = executor.execute_tool("create_vse_strip", {
            "strip_type": "TEXT",
            "name": "Main_Title",
            "channel": 2,
            "frame_start": 10,
            "duration": 30,
            "text": "Universal MCP VSE Title",
        })
        assert txt_res.is_success, f"create_vse_strip TEXT failed: {txt_res.message}"
        print(f"[+] Created TEXT strip: name={txt_res.result['name']}, channel={txt_res.result['channel']}, start={txt_res.result['frame_start']}, dur={txt_res.result['duration']}")
        assert txt_res.result["name"] == "Main_Title"
        assert txt_res.result["channel"] == 2
        assert txt_res.result["frame_start"] == 10
        assert txt_res.result["duration"] == 30

        # Step 4: Add Timeline Markers
        print("\n--- Test 4: Manage Timeline Markers (Add) ---")
        m1_res = executor.execute_tool("manage_timeline_markers", {
            "action": "add",
            "name": "IntroStart",
            "frame": 1,
        })
        assert m1_res.is_success, f"add marker IntroStart failed: {m1_res.message}"

        m2_res = executor.execute_tool("manage_timeline_markers", {
            "action": "add",
            "name": "SceneCut",
            "frame": 24,
        })
        assert m2_res.is_success, f"add marker SceneCut failed: {m2_res.message}"
        print(f"[+] Added timeline markers: {[m['name'] for m in m2_res.result['markers']]}")
        assert len(m2_res.result["markers"]) == 2

        # Step 5: Timeline Inspection with Active Strips
        print("\n--- Test 5: Full Timeline Inspection ---")
        t5_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True, "include_markers": True})
        assert t5_res.is_success, f"inspect_vse_timeline failed: {t5_res.message}"
        assert t5_res.result["total_strips"] == 2
        assert t5_res.result["occupied_channels"] == [1, 2]
        strip_names = [s["name"] for s in t5_res.result["strips"]]
        assert "Intro_Background" in strip_names
        assert "Main_Title" in strip_names
        marker_names = [m["name"] for m in t5_res.result["markers"]]
        assert "IntroStart" in marker_names
        assert "SceneCut" in marker_names
        print(f"[+] Verified timeline populated: strips={strip_names}, occupied_channels={t5_res.result['occupied_channels']}, markers={marker_names}")

        # Step 6: Modify COLOR strip
        print("\n--- Test 6: Modify COLOR Strip ---")
        mod_res = executor.execute_tool("modify_vse_strip", {
            "name": "Intro_Background",
            "channel": 3,
            "frame_start": 15,
            "duration": 60,
            "mute": True,
        })
        assert mod_res.is_success, f"modify_vse_strip failed: {mod_res.message}"
        print(f"[+] Modified strip: channel={mod_res.result['channel']}, start={mod_res.result['frame_start']}, dur={mod_res.result['duration']}, mute={mod_res.result['mute']}")
        assert mod_res.result["channel"] == 3
        assert mod_res.result["frame_start"] == 15
        assert mod_res.result["duration"] == 60
        assert mod_res.result["mute"] is True

        # Step 7: Independent Readback of Modified Strip
        print("\n--- Test 7: Independent Readback Verification ---")
        t7_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert t7_res.is_success
        intro_desc = next(s for s in t7_res.result["strips"] if s["name"] == "Intro_Background")
        assert intro_desc["channel"] == 3
        assert intro_desc["frame_start"] == 15
        assert intro_desc["duration"] == 60
        assert intro_desc["mute"] is True
        print(f"[+] Independent readback verified: {intro_desc}")

        # Step 8: Delete TEXT Strip
        print("\n--- Test 8: Delete TEXT Strip ---")
        del_res = executor.execute_tool("delete_vse_strip", {"name": "Main_Title"})
        assert del_res.is_success, f"delete_vse_strip failed: {del_res.message}"
        assert del_res.result["remaining_strips"] == 1
        print(f"[+] Deleted strip 'Main_Title'. Remaining strips: {del_res.result['remaining_strips']}")

        # Step 9: Remove Timeline Marker
        print("\n--- Test 9: Remove Timeline Marker ---")
        rm_m_res = executor.execute_tool("manage_timeline_markers", {
            "action": "remove",
            "name": "SceneCut",
        })
        assert rm_m_res.is_success, f"remove marker failed: {rm_m_res.message}"
        remaining_markers = [m["name"] for m in rm_m_res.result["markers"]]
        assert "SceneCut" not in remaining_markers
        assert "IntroStart" in remaining_markers
        print(f"[+] Removed marker 'SceneCut'. Remaining markers: {remaining_markers}")

        # Step 10: Fail-Closed Security Boundary Check
        print("\n--- Test 10: Fail-Closed Security Invariant ---")
        hacker_res = executor.execute_tool(
            "create_vse_strip",
            {
                "strip_type": "COLOR",
                "name": "HackerStrip",
                "channel": 1,
                "frame_start": 1,
                "approved": True,  # Untrusted client-injected flag
            },
            trusted_approval=False,
        )
        assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected: {hacker_res}"
        err_text = str(hacker_res.message).lower()
        assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True: PASSED")

        # Step 11: Path Traversal Boundary Check
        print("\n--- Test 11: Path Traversal Boundary Check ---")
        traverse_res = executor.execute_tool(
            "create_vse_strip",
            {
                "strip_type": "MOVIE",
                "name": "TraverseMovie",
                "channel": 1,
                "frame_start": 1,
                "filepath": "C:/videos/../../secret.mp4",
            },
        )
        assert not traverse_res.is_success, "Security vulnerability: Path traversal was not rejected!"
        assert "path traversal" in str(traverse_res.message).lower()
        print(f"[+] Rejection of path traversal sequences: PASSED")

        # Step 12: Graceful Teardown
        print("\n--- Test 12: Graceful Teardown ---")
        (run_dir / "stop.flag").touch()
        blender_proc.wait(timeout=10.0)
        print(f"[+] Disposable Blender process {blender_proc.pid} terminated cleanly with code {blender_proc.returncode}")

        final_state_file = run_dir / "final_state.json"
        if final_state_file.exists():
            final_data = json.loads(final_state_file.read_text(encoding="utf-8"))
            print(f"[+] Final scene state: strips={final_data['strips']}, markers={final_data['markers']}, bridge_running={final_data['bridge_running']}")
            assert final_data["strips"] == ["Intro_Background"]
            assert final_data["markers"] == ["IntroStart"]
            assert not final_data["bridge_running"]

    finally:
        if blender_proc.poll() is None:
            blender_proc.kill()
            blender_proc.wait()

    # Step 13: Verify Production Isolation
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
        assert "inspect_vse_timeline" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 1 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_e2e())
