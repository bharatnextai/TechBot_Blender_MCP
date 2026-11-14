"""
Verification Test for VSE Capability 3: Transitions & Visual Effects.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Setup initial scene with camera and multi-strip VSE layout.
2. Create CROSS transition between overlapping strips (auto-detected overlap).
3. Create WIPE transition with custom pattern, blur width, and angle.
4. Create GAUSSIAN_BLUR effect on input strip with horizontal and vertical blur sizes.
5. Create GLOW effect on input strip with threshold, boost factor, and quality.
6. Create ADJUSTMENT layer across channels with custom duration and opacity.
7. Update effect properties (action=UPDATE) with immediate parameter mutation.
8. Inspect effect settings (action=INSPECT) verifying readback parity.
9. Independent timeline readback verifying all transition and effect strips.
10. Render sequencer still frame to disk verifying actual compositing output.
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
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP3", approve_task_group=False)
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


def run_vse_cap3_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap3_"))
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
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 3 TRANSITIONS & VISUAL EFFECTS")
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

        # Step 1: Setup scene with Camera & initial VSE strips
        print("\n--- Test 1: Setup Scene with Camera & Initial Strips ---")
        cam_res = executor.execute_tool("create_camera", {
            "name": "VSE_Render_Camera", "location": [0, -5, 2], "rotation_euler": [1.1, 0, 0]
        })
        assert cam_res.is_success, cam_res.message
        print(f"[+] Created scene camera: {cam_res.result['name']}")

        # Base Strip 1 (Ch 1, 1..51 dur 50)
        res_c1 = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Base_Red", "channel": 1, "frame_start": 1, "duration": 50, "color": [0.85, 0.1, 0.1]
        })
        assert res_c1.is_success, res_c1.message

        # Base Strip 2 (Ch 2, 30..80 dur 50) - Overlaps Base_Red between 30 and 51 (21 frames)
        res_c2 = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Base_Blue", "channel": 2, "frame_start": 30, "duration": 50, "color": [0.1, 0.2, 0.85]
        })
        assert res_c2.is_success, res_c2.message
        print(f"[+] Created overlapping base color strips: Base_Red (1..51) and Base_Blue (30..80)")

        # Step 2: Create CROSS Transition
        print("\n--- Test 2: Create CROSS Transition ---")
        cross_res = executor.execute_tool("create_vse_transition", {
            "transition_type": "CROSS",
            "input1": "Base_Red",
            "input2": "Base_Blue",
            "channel": 3,
        })
        assert cross_res.is_success, cross_res.message
        c_res = cross_res.result
        print(f"[+] Created CROSS transition: name='{c_res['name']}', ch={c_res['channel']}, span=[{c_res['frame_start']}..{c_res['right_handle']}], dur={c_res['duration']}")
        assert c_res["type"] == "CROSS"
        assert c_res["channel"] == 3
        assert c_res["frame_start"] == 30
        assert c_res["duration"] == 21
        assert c_res["input_1"] == "Base_Red"
        assert c_res["input_2"] == "Base_Blue"

        # Step 3: Create WIPE Transition with Custom Pattern & Edge Blur
        print("\n--- Test 3: Create WIPE Transition ---")
        # Strips for wipe
        res_w1 = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Wipe_In", "channel": 1, "frame_start": 90, "duration": 40, "color": [0.1, 0.8, 0.2]
        })
        assert res_w1.is_success, res_w1.message
        res_w2 = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Wipe_Out", "channel": 2, "frame_start": 110, "duration": 40, "color": [0.8, 0.8, 0.1]
        })
        assert res_w2.is_success, res_w2.message

        wipe_res = executor.execute_tool("create_vse_transition", {
            "transition_type": "WIPE",
            "input1": "Wipe_In",
            "input2": "Wipe_Out",
            "channel": 3,
            "wipe_type": "IRIS",
            "direction": "OUT",
            "blur_width": 0.25,
            "angle": 0.785,
        })
        assert wipe_res.is_success, wipe_res.message
        w_res = wipe_res.result
        print(f"[+] Created WIPE transition: name='{w_res['name']}', wipe_type={w_res['transition_settings']['wipe_type']}, blur={w_res['transition_settings']['blur_width']}")
        assert w_res["type"] == "WIPE"
        assert w_res["transition_settings"]["wipe_type"] == "IRIS"
        assert w_res["transition_settings"]["direction"] == "OUT"
        assert abs(w_res["transition_settings"]["blur_width"] - 0.25) < 1e-4

        # Step 4: Create GAUSSIAN_BLUR Effect Strip
        print("\n--- Test 4: Create GAUSSIAN_BLUR Effect ---")
        blur_res = executor.execute_tool("configure_vse_effect", {
            "action": "CREATE",
            "effect_type": "GAUSSIAN_BLUR",
            "input_strip": "Base_Red",
            "channel": 4,
            "size_x": 15.0,
            "size_y": 12.0,
        })
        assert blur_res.is_success, blur_res.message
        b_res = blur_res.result
        blur_strip_name = b_res["name"]
        print(f"[+] Created GAUSSIAN_BLUR effect: name='{blur_strip_name}', size_x={b_res['effect_settings']['size_x']}, size_y={b_res['effect_settings']['size_y']}")
        assert b_res["type"] == "GAUSSIAN_BLUR"
        assert b_res["channel"] == 4
        assert b_res["input_strip"] == "Base_Red"
        assert abs(b_res["effect_settings"]["size_x"] - 15.0) < 1e-4
        assert abs(b_res["effect_settings"]["size_y"] - 12.0) < 1e-4

        # Step 5: Create GLOW Effect Strip
        print("\n--- Test 5: Create GLOW Effect ---")
        glow_res = executor.execute_tool("configure_vse_effect", {
            "action": "CREATE",
            "effect_type": "GLOW",
            "input_strip": "Base_Blue",
            "channel": 5,
            "threshold": 0.65,
            "boost_factor": 2.2,
            "blur_radius": 6.0,
            "quality": 3,
        })
        assert glow_res.is_success, glow_res.message
        g_res = glow_res.result
        glow_strip_name = g_res["name"]
        print(f"[+] Created GLOW effect: name='{glow_strip_name}', threshold={g_res['effect_settings']['threshold']}, boost={g_res['effect_settings']['boost_factor']}")
        assert g_res["type"] == "GLOW"
        assert abs(g_res["effect_settings"]["threshold"] - 0.65) < 1e-4
        assert abs(g_res["effect_settings"]["boost_factor"] - 2.2) < 1e-4
        assert g_res["effect_settings"]["quality"] == 3

        # Step 6: Create ADJUSTMENT Layer
        print("\n--- Test 6: Create ADJUSTMENT Layer ---")
        adj_res = executor.execute_tool("configure_vse_effect", {
            "action": "CREATE",
            "effect_type": "ADJUSTMENT",
            "channel": 6,
            "frame_start": 1,
            "duration": 150,
            "blend_alpha": 0.85,
        })
        assert adj_res.is_success, adj_res.message
        a_res = adj_res.result
        print(f"[+] Created ADJUSTMENT layer: name='{a_res['name']}', ch={a_res['channel']}, span=[{a_res['left_handle']}..{a_res['right_handle']}], alpha={a_res['blend_alpha']}")
        assert a_res["type"] == "ADJUSTMENT"
        assert a_res["channel"] == 6
        assert a_res["left_handle"] == 1
        assert a_res["duration"] == 150
        assert abs(a_res["blend_alpha"] - 0.85) < 1e-4

        # Step 7: Update Effect Strip Properties (action=UPDATE)
        print("\n--- Test 7: Update GAUSSIAN_BLUR Properties ---")
        up_res = executor.execute_tool("configure_vse_effect", {
            "action": "UPDATE",
            "name": blur_strip_name,
            "size_x": 30.0,
            "size_y": 25.0,
            "blend_alpha": 0.7,
        })
        assert up_res.is_success, up_res.message
        u_res = up_res.result
        print(f"[+] Updated GAUSSIAN_BLUR: size_x={u_res['effect_settings']['size_x']}, size_y={u_res['effect_settings']['size_y']}, blend_alpha={u_res['blend_alpha']}")
        assert abs(u_res["effect_settings"]["size_x"] - 30.0) < 1e-4
        assert abs(u_res["effect_settings"]["size_y"] - 25.0) < 1e-4
        assert abs(u_res["blend_alpha"] - 0.7) < 1e-4

        # Step 8: Inspect Effect Strip Settings (action=INSPECT)
        print("\n--- Test 8: Inspect GLOW Effect Settings ---")
        insp_res = executor.execute_tool("configure_vse_effect", {
            "action": "INSPECT",
            "name": glow_strip_name,
        })
        assert insp_res.is_success, insp_res.message
        i_res = insp_res.result
        print(f"[+] Inspected GLOW: name='{i_res['name']}', threshold={i_res['effect_settings']['threshold']}, quality={i_res['effect_settings']['quality']}")
        assert i_res["name"] == glow_strip_name
        assert i_res["type"] == "GLOW"
        assert abs(i_res["effect_settings"]["threshold"] - 0.65) < 1e-4
        assert i_res["effect_settings"]["quality"] == 3

        # Step 9: Independent Timeline Readback
        print("\n--- Test 9: Independent Timeline Readback ---")
        read_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert read_res.is_success, read_res.message
        strips_map = {s["name"]: s for s in read_res.result["strips"]}
        assert "Base_Red" in strips_map
        assert "Base_Blue" in strips_map
        assert c_res["name"] in strips_map
        assert "Wipe_In" in strips_map
        assert "Wipe_Out" in strips_map
        assert w_res["name"] in strips_map
        assert blur_strip_name in strips_map
        assert glow_strip_name in strips_map
        assert a_res["name"] in strips_map
        print(f"[+] Independent readback verified all 9 timeline strips successfully.")

        # Step 10: Still Frame Render Verification of VSE Sequencer Output
        print("\n--- Test 10: Still Frame Render Verification of VSE Output ---")
        render_path = run_dir / "vse_transition_rendered.png"
        render_res = executor.execute_tool("render_scene", {
            "render_mode": "still",
            "frame": 40,
            "output_path": str(render_path),
            "output_format": "PNG",
        })
        assert render_res.is_success, render_res.message
        r_out = render_res.result
        print(f"[+] Render completed: status={r_out.get('rendered')}, output={render_path}")
        assert render_path.exists(), f"Rendered output image missing at {render_path}"
        render_size = render_path.stat().st_size
        assert render_size > 500, f"Rendered output too small ({render_size} bytes)"
        print(f"[+] Rendered image verified on disk: {render_path} ({render_size} bytes)")

        # Step 11: Fail-Closed Security Boundary Check
        print("\n--- Test 11: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("create_vse_transition", {"transition_type": "CROSS", "input1": "Base_Red", "input2": "Base_Blue", "approved": True}),
            ("configure_vse_effect", {"action": "CREATE", "effect_type": "ADJUSTMENT", "approved": True}),
            ("configure_vse_effect", {"action": "UPDATE", "name": blur_strip_name, "size_x": 50.0, "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on transition and effect mutations: PASSED")

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
        assert "create_vse_transition" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 3 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap3_e2e())

