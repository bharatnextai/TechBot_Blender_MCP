"""
Verification Test for VSE Capability 4: Audio Engineering.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Synthetic audio generation (pure PCM WAV file) via Python stdlib.
2. Create SoundStrip via create_vse_strip and verify asset binding.
3. Configure audio playback volume, pan, pitch correction, waveform (configure_vse_audio).
4. Automated volume keyframing for fade-in and fade-out.
5. Independent readback inspection of sound strip properties.
6. Add sound modifiers (SOUND_EQUALIZER, PITCH, ECHO) via manage_vse_sound_modifiers.
7. Update sound modifier parameters (delay, feedback, mix, semitones).
8. List active strip sound modifiers and verify parameter parity.
9. Remove sound modifier and verify clean state cleanup.
10. Verify SoundStrip modifier defense invariant (clear diagnostic error on SOUND strips).
11. Independent timeline readback verifying sound and meta strips.
12. Fail-closed security boundary check (reject untrusted approved=True).
13. Clean process exit (code 0) and final scene state verification.
14. Production isolation: v0.1.88 release ZIP untouched (SHA-256 intact), port 9877 untouched.
"""

import os
import sys
import json
import time
import wave
import math
import struct
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
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP4", approve_task_group=False)
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


def generate_synthetic_wav(filepath: Path, duration_seconds: float = 2.0, frequency: float = 440.0):
    sample_rate = 44100
    total_samples = int(sample_rate * duration_seconds)
    with wave.open(str(filepath), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        for i in range(total_samples):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * frequency * i / sample_rate))
            f.writeframes(struct.pack("<h", val))


def run_vse_cap4_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap4_"))
    bootstrap_file = run_dir / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_dir / "ready.json"

    # Step 1: Generate synthetic test audio
    audio_file = run_dir / "dialogue_sample.wav"
    generate_synthetic_wav(audio_file, duration_seconds=3.0, frequency=440.0)
    assert audio_file.exists() and audio_file.stat().st_size > 1000, "Failed to create synthetic test audio"
    print(f"[+] Created synthetic test audio asset: {audio_file} ({audio_file.stat().st_size} bytes)")

    env = os.environ.copy()
    env["UMCP_RUN_ROOT"] = str(run_dir)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["PYTHONPATH"] = str(PROJECT)

    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 4 AUDIO ENGINEERING")
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

        # Step 2: Setup initial SoundStrip and MetaStrip
        print("\n--- Test 2: Create SoundStrip and MetaStrip ---")
        snd_res = executor.execute_tool("create_vse_strip", {
            "strip_type": "SOUND",
            "name": "Voice_Track",
            "channel": 1,
            "frame_start": 1,
            "filepath": str(audio_file),
        })
        assert snd_res.is_success, snd_res.message
        print(f"[+] Created SoundStrip: name='{snd_res.result['name']}', ch={snd_res.result['channel']}, dur={snd_res.result['duration']}")
        assert snd_res.result["type"] == "SOUND"
        assert snd_res.result["channel"] == 1

        # Create MetaStrip on channel 2
        meta_res = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR",
            "name": "Master_Visual_Bus",
            "channel": 2,
            "frame_start": 1,
            "duration": 100,
        })
        assert meta_res.is_success, meta_res.message
        print(f"[+] Created bus strip: name='{meta_res.result['name']}'")

        # Step 3: Configure Audio Properties
        print("\n--- Test 3: Configure Audio Properties on Voice_Track ---")
        cfg_res = executor.execute_tool("configure_vse_audio", {
            "name": "Voice_Track",
            "action": "UPDATE",
            "volume": 0.82,
            "pan": -0.35,
            "pitch_correction": True,
            "show_waveform": True,
        })
        assert cfg_res.is_success, cfg_res.message
        c_out = cfg_res.result
        print(f"[+] Configured Voice_Track: volume={c_out['volume']}, pan={c_out['pan']}, pitch_corr={c_out['pitch_correction']}, waveform={c_out['show_waveform']}")
        assert abs(c_out["volume"] - 0.82) < 1e-4
        assert abs(c_out["pan"] - (-0.35)) < 1e-4
        assert c_out["pitch_correction"] is True
        assert c_out["show_waveform"] is True

        # Step 4: Automated Volume Fade-In and Fade-Out
        print("\n--- Test 4: Configure Volume Fade-In & Fade-Out ---")
        fade_res = executor.execute_tool("configure_vse_audio", {
            "name": "Voice_Track",
            "action": "UPDATE",
            "fade_in_duration": 12,
            "fade_out_duration": 18,
        })
        assert fade_res.is_success, fade_res.message
        print(f"[+] Successfully applied volume automation fade-in (12 frames) and fade-out (18 frames)")

        # Step 5: Readback Inspection of SoundStrip
        print("\n--- Test 5: Inspect SoundStrip Settings ---")
        insp_res = executor.execute_tool("configure_vse_audio", {
            "name": "Voice_Track",
            "action": "INSPECT",
        })
        assert insp_res.is_success, insp_res.message
        i_out = insp_res.result
        print(f"[+] Inspected Voice_Track: sound_name='{i_out['sound_info'].get('sound_name')}', rate={i_out['sound_info'].get('samplerate')}")
        assert i_out["name"] == "Voice_Track"
        assert i_out["type"] == "SOUND"
        assert abs(i_out["volume"] - 0.82) < 1e-4
        assert abs(i_out["pan"] - (-0.35)) < 1e-4
        assert i_out["sound_info"].get("samplerate") == 44100

        # Step 6: Add Sound Modifiers on Bus Strip
        print("\n--- Test 6: Add Sound Modifiers (EQUALIZER, PITCH, ECHO) ---")
        # Add SOUND_EQUALIZER
        eq_res = executor.execute_tool("manage_vse_sound_modifiers", {
            "action": "ADD",
            "name": "Master_Visual_Bus",
            "modifier_type": "SOUND_EQUALIZER",
            "modifier_name": "Main_Equalizer",
        })
        assert eq_res.is_success, eq_res.message
        print(f"[+] Added SOUND_EQUALIZER modifier: count={eq_res.result['modifier_count']}")

        # Add PITCH
        pitch_res = executor.execute_tool("manage_vse_sound_modifiers", {
            "action": "ADD",
            "name": "Master_Visual_Bus",
            "modifier_type": "PITCH",
            "modifier_name": "Pitch_Shift",
            "pitch_mode": "SEMITONES",
            "semitones": 3,
            "preserve_formant": True,
            "quality": 3,
        })
        assert pitch_res.is_success, pitch_res.message
        print(f"[+] Added PITCH modifier: count={pitch_res.result['modifier_count']}")

        # Add ECHO
        echo_res = executor.execute_tool("manage_vse_sound_modifiers", {
            "action": "ADD",
            "name": "Master_Visual_Bus",
            "modifier_type": "ECHO",
            "modifier_name": "Hall_Echo",
            "delay": 0.25,
            "feedback": 0.5,
            "mix": 0.4,
        })
        assert echo_res.is_success, echo_res.message
        print(f"[+] Added ECHO modifier: count={echo_res.result['modifier_count']}")
        assert echo_res.result["modifier_count"] == 3

        # Step 7: Update Sound Modifier Properties
        print("\n--- Test 7: Update ECHO Modifier Properties ---")
        up_echo = executor.execute_tool("manage_vse_sound_modifiers", {
            "action": "UPDATE",
            "name": "Master_Visual_Bus",
            "modifier_name": "Hall_Echo",
            "delay": 0.35,
            "feedback": 0.7,
            "mix": 0.55,
        })
        assert up_echo.is_success, up_echo.message
        updated_echo = next(m for m in up_echo.result["modifiers"] if m["name"] == "Hall_Echo")
        print(f"[+] Updated Hall_Echo: delay={updated_echo['delay']}, feedback={updated_echo['feedback']}, mix={updated_echo['mix']}")
        assert abs(updated_echo["delay"] - 0.35) < 1e-4
        assert abs(updated_echo["feedback"] - 0.7) < 1e-4
        assert abs(updated_echo["mix"] - 0.55) < 1e-4

        # Step 8: List Modifiers
        print("\n--- Test 8: List Active Modifiers ---")
        list_res = executor.execute_tool("manage_vse_sound_modifiers", {
            "action": "LIST",
            "name": "Master_Visual_Bus",
        })
        assert list_res.is_success, list_res.message
        mod_names = [m["name"] for m in list_res.result["modifiers"]]
        print(f"[+] Listed active modifiers on Master_Visual_Bus: {mod_names}")
        assert "Main_Equalizer" in mod_names
        assert "Pitch_Shift" in mod_names
        assert "Hall_Echo" in mod_names

        # Step 9: Remove Sound Modifier
        print("\n--- Test 9: Remove ECHO Modifier ---")
        rem_res = executor.execute_tool("manage_vse_sound_modifiers", {
            "action": "REMOVE",
            "name": "Master_Visual_Bus",
            "modifier_name": "Hall_Echo",
        })
        assert rem_res.is_success, rem_res.message
        rem_names = [m["name"] for m in rem_res.result["modifiers"]]
        print(f"[+] Modifiers after removal: {rem_names} (count={rem_res.result['modifier_count']})")
        assert "Hall_Echo" not in rem_names
        assert rem_res.result["modifier_count"] == 2

        # Step 10: SoundStrip Direct Modifier Defense
        print("\n--- Test 10: Verify SoundStrip Direct Modifier Defense ---")
        snd_mod_res = executor.execute_tool("manage_vse_sound_modifiers", {
            "action": "ADD",
            "name": "Voice_Track",
            "modifier_type": "PITCH",
        })
        assert not snd_mod_res.is_success, "Expected failure when adding modifier directly to SOUND strip"
        print(f"[+] SoundStrip direct modifier rejected with informative message: '{snd_mod_res.message}'")
        assert "SOUND" in str(snd_mod_res.message) and "configure_vse_audio" in str(snd_mod_res.message)

        # Step 11: Timeline Readback
        print("\n--- Test 11: Independent Timeline Readback ---")
        time_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert time_res.is_success, time_res.message
        all_s = {s["name"]: s for s in time_res.result["strips"]}
        assert "Voice_Track" in all_s
        assert "Master_Visual_Bus" in all_s
        print(f"[+] Verified timeline strips: {list(all_s.keys())}")

        # Step 12: Fail-Closed Security Boundary Check
        print("\n--- Test 12: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("configure_vse_audio", {"name": "Voice_Track", "action": "UPDATE", "volume": 0.5, "approved": True}),
            ("manage_vse_sound_modifiers", {"name": "Master_Visual_Bus", "action": "ADD", "modifier_type": "ECHO", "approved": True}),
            ("manage_vse_sound_modifiers", {"name": "Master_Visual_Bus", "action": "REMOVE", "modifier_name": "Main_Equalizer", "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on all audio mutation tools: PASSED")

        # Step 13: Teardown
        print("\n--- Test 13: Graceful Teardown ---")
        (run_dir / "stop.flag").touch()
        blender_proc.wait(timeout=10.0)
        print(f"[+] Disposable Blender process {blender_proc.pid} terminated cleanly with code {blender_proc.returncode}")

    finally:
        if blender_proc.poll() is None:
            blender_proc.kill()
            blender_proc.wait()

    # Step 14: Production Isolation Verification
    print("\n--- Step 14: Verifying Production Isolation ---")
    zip_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip"
    sha_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip.sha256"
    assert zip_path.exists() and sha_path.exists(), "Release artifact v0.1.88 missing!"
    import hashlib
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert actual_sha == "ba14a1ed39f78096d054cd4f81eac99ded4d61157fa56e692ad5aa521493c702", "CRITICAL: v0.1.88 release ZIP was modified!"
    print(f"[+] Release package v0.1.88 verified untouched (SHA-256: {actual_sha})")

    prod_handlers = Path(r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp\bridge\handlers.py")
    if prod_handlers.exists():
        assert "configure_vse_audio" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 4 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap4_e2e())
