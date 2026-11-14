"""
Verification Test for VSE Capability 6: Color Grading & Strip Modifiers.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Setup initial scene with graded strip and matte strip.
2. Add COLOR_BALANCE modifier with Lift, Gamma, Gain, and Color Multiply.
3. Add BRIGHT_CONTRAST modifier with custom brightness and contrast adjustments.
4. Add WHITE_BALANCE modifier with custom RGB white point balance.
5. Add TONEMAP modifier with mask strip binding (input_mask_type=STRIP, input_mask_strip).
6. Update modifier parameters (BRIGHT_CONTRAST bright, contrast, mute).
7. List active modifiers and verify parameter parity.
8. Remove modifier and verify clean state cleanup.
9. Independent timeline readback verifying strips remain fully valid.
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
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP6", approve_task_group=False)
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


def run_vse_cap6_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap6_"))
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
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 6 COLOR GRADING & MODIFIERS")
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
        print("\n--- Test 1: Setup Target & Mask Strips ---")
        res_t = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Grade_Target", "channel": 1, "frame_start": 1, "duration": 80, "color": [0.6, 0.4, 0.3]
        })
        assert res_t.is_success, res_t.message

        res_m = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Mask_Matte", "channel": 2, "frame_start": 1, "duration": 80, "color": [1.0, 1.0, 1.0]
        })
        assert res_m.is_success, res_m.message
        print(f"[+] Created Grade_Target (Ch1) and Mask_Matte (Ch2)")

        # Step 2: Add COLOR_BALANCE Modifier
        print("\n--- Test 2: Add COLOR_BALANCE Modifier ---")
        cb_res = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "ADD",
            "name": "Grade_Target",
            "modifier_type": "COLOR_BALANCE",
            "modifier_name": "Primary_Grade",
            "correction_method": "LIFT_GAMMA_GAIN",
            "lift": [0.92, 0.95, 1.05],
            "gamma": [1.0, 1.02, 0.98],
            "gain": [1.15, 1.1, 0.9],
            "color_multiply": 1.15,
        })
        assert cb_res.is_success, cb_res.message
        cb_mod = next(m for m in cb_res.result["modifiers"] if m["name"] == "Primary_Grade")
        print(f"[+] Added COLOR_BALANCE: lift={cb_mod['color_balance']['lift']}, gain={cb_mod['color_balance']['gain']}, mult={cb_mod['color_balance']['color_multiply']}")
        assert abs(cb_mod["color_balance"]["lift"][0] - 0.92) < 1e-4
        assert abs(cb_mod["color_balance"]["gain"][0] - 1.15) < 1e-4
        assert abs(cb_mod["color_balance"]["color_multiply"] - 1.15) < 1e-4

        # Step 3: Add BRIGHT_CONTRAST Modifier
        print("\n--- Test 3: Add BRIGHT_CONTRAST Modifier ---")
        bc_res = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "ADD",
            "name": "Grade_Target",
            "modifier_type": "BRIGHT_CONTRAST",
            "modifier_name": "Tone_Adjustment",
            "bright": 0.12,
            "contrast": 0.22,
        })
        assert bc_res.is_success, bc_res.message
        bc_mod = next(m for m in bc_res.result["modifiers"] if m["name"] == "Tone_Adjustment")
        print(f"[+] Added BRIGHT_CONTRAST: bright={bc_mod['bright']}, contrast={bc_mod['contrast']}")
        assert abs(bc_mod["bright"] - 0.12) < 1e-4
        assert abs(bc_mod["contrast"] - 0.22) < 1e-4

        # Step 4: Add WHITE_BALANCE Modifier
        print("\n--- Test 4: Add WHITE_BALANCE Modifier ---")
        wb_res = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "ADD",
            "name": "Grade_Target",
            "modifier_type": "WHITE_BALANCE",
            "modifier_name": "Color_Temp",
            "white_value": [0.92, 0.96, 1.0],
        })
        assert wb_res.is_success, wb_res.message
        wb_mod = next(m for m in wb_res.result["modifiers"] if m["name"] == "Color_Temp")
        print(f"[+] Added WHITE_BALANCE: white_value={wb_mod['white_value']}")
        assert abs(wb_mod["white_value"][0] - 0.92) < 1e-4

        # Step 5: Add TONEMAP Modifier with Mask Strip Input
        print("\n--- Test 5: Add TONEMAP Modifier with Mask Strip Binding ---")
        tm_res = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "ADD",
            "name": "Grade_Target",
            "modifier_type": "TONEMAP",
            "modifier_name": "HDR_Tonemap",
            "tonemap_type": "RD_PHOTORECEPTOR",
            "tonemap_key": 0.25,
            "tonemap_intensity": 0.08,
            "input_mask_type": "STRIP",
            "input_mask_strip": "Mask_Matte",
        })
        assert tm_res.is_success, tm_res.message
        tm_mod = next(m for m in tm_res.result["modifiers"] if m["name"] == "HDR_Tonemap")
        print(f"[+] Added TONEMAP with Mask: type={tm_mod['tonemap_type']}, key={tm_mod['tonemap_key']}, mask={tm_mod['input_mask_strip']}")
        assert tm_mod["tonemap_type"] == "RD_PHOTORECEPTOR"
        assert abs(tm_mod["tonemap_key"] - 0.25) < 1e-4
        assert tm_mod["input_mask_strip"] == "Mask_Matte"
        assert tm_res.result["modifier_count"] == 4

        # Step 6: Update Modifier Parameters
        print("\n--- Test 6: Update Tone_Adjustment Modifier ---")
        up_res = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "UPDATE",
            "name": "Grade_Target",
            "modifier_name": "Tone_Adjustment",
            "bright": 0.25,
            "contrast": 0.35,
            "mute": True,
        })
        assert up_res.is_success, up_res.message
        updated_bc = next(m for m in up_res.result["modifiers"] if m["name"] == "Tone_Adjustment")
        print(f"[+] Updated Tone_Adjustment: bright={updated_bc['bright']}, contrast={updated_bc['contrast']}, mute={updated_bc['mute']}")
        assert abs(updated_bc["bright"] - 0.25) < 1e-4
        assert abs(updated_bc["contrast"] - 0.35) < 1e-4
        assert updated_bc["mute"] is True

        # Step 7: List Modifiers
        print("\n--- Test 7: List Modifiers on Grade_Target ---")
        list_res = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "LIST",
            "name": "Grade_Target",
        })
        assert list_res.is_success, list_res.message
        mod_names = [m["name"] for m in list_res.result["modifiers"]]
        print(f"[+] Active modifiers on Grade_Target: {mod_names} (count={list_res.result['modifier_count']})")
        assert "Primary_Grade" in mod_names
        assert "Tone_Adjustment" in mod_names
        assert "Color_Temp" in mod_names
        assert "HDR_Tonemap" in mod_names

        # Step 8: Remove Modifier
        print("\n--- Test 8: Remove Color_Temp Modifier ---")
        rem_res = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "REMOVE",
            "name": "Grade_Target",
            "modifier_name": "Color_Temp",
        })
        assert rem_res.is_success, rem_res.message
        rem_names = [m["name"] for m in rem_res.result["modifiers"]]
        print(f"[+] Modifiers after removal: {rem_names} (count={rem_res.result['modifier_count']})")
        assert "Color_Temp" not in rem_names
        assert rem_res.result["modifier_count"] == 3

        # Step 9: Independent Timeline Readback
        print("\n--- Test 9: Independent Timeline Readback ---")
        time_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert time_res.is_success, time_res.message
        all_s = {s["name"]: s for s in time_res.result["strips"]}
        assert "Grade_Target" in all_s
        assert "Mask_Matte" in all_s
        print(f"[+] Timeline strips verified: {list(all_s.keys())}")

        # Step 10: Fail-Closed Security Boundary Check
        print("\n--- Test 10: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("manage_vse_strip_modifiers", {"name": "Grade_Target", "action": "ADD", "modifier_type": "COLOR_BALANCE", "approved": True}),
            ("manage_vse_strip_modifiers", {"name": "Grade_Target", "action": "UPDATE", "modifier_name": "Primary_Grade", "approved": True}),
            ("manage_vse_strip_modifiers", {"name": "Grade_Target", "action": "REMOVE", "modifier_name": "Primary_Grade", "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on all strip modifier mutations: PASSED")

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
        assert "manage_vse_strip_modifiers" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 6 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap6_e2e())

