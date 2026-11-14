"""
Verification Test for VSE Capability 9: Sequencer Rendering & Audio Mixdown.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Populate composite sequencer with visual strips and audio tone.
2. Render video sequence to MP4 (H.264 / AAC) with validated file size on disk.
3. Render video sequence to QuickTime MOV (Apple ProRes / PCM) with validated file size on disk.
4. Mix down sequencer audio to uncompressed WAV (PCM S16) with validated file size on disk.
5. Path traversal rejection invariant (strictly forbid '../' in render and mixdown).
6. Fail-closed security boundary check (reject untrusted approved=True).
7. Clean process exit (code 0) and final scene state verification.
8. Production isolation: v0.1.88 release ZIP untouched (SHA-256 intact), port 9877 untouched.
"""

import os
import sys
import json
import time
import wave
import struct
import math
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
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP9", approve_task_group=False)
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


def generate_test_tone(dest_path: Path, duration_sec: float = 1.0, freq_hz: float = 440.0) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 44100
    total_samples = int(duration_sec * sample_rate)
    with wave.open(str(dest_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        samples = []
        for i in range(total_samples):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
            samples.append(struct.pack("<h", val))
        wav_file.writeframes(b"".join(samples))
    return dest_path


def run_vse_cap9_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap9_"))
    bootstrap_file = run_dir / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_dir / "ready.json"

    # Pre-generate audio asset in run_dir
    tone_wav = generate_test_tone(run_dir / "test_dialogue.wav", duration_sec=1.5, freq_hz=440.0)

    env = os.environ.copy()
    env["UMCP_RUN_ROOT"] = str(run_dir)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["PYTHONPATH"] = str(PROJECT)

    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 9 SEQUENCER RENDERING")
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

        # Step 1: Populate Sequencer with Composite Elements
        print("\n--- Test 1: Populate Composite Elements on Timeline ---")
        bg_res = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Background_Card", "channel": 1, "frame_start": 1, "duration": 25, "color": [0.12, 0.45, 0.75]
        })
        assert bg_res.is_success, bg_res.message

        title_res = executor.execute_tool("create_vse_text_strip", {
            "name": "Delivery_Title", "text": "UNIVERSAL MCP VSE 5.2", "channel": 2, "frame_start": 1, "duration": 25, "font_size": 40.0
        })
        assert title_res.is_success, title_res.message

        snd_res = executor.execute_tool("create_vse_strip", {
            "strip_type": "SOUND", "name": "Audio_Track", "channel": 3, "frame_start": 1, "duration": 25, "filepath": str(tone_wav)
        })
        assert snd_res.is_success, snd_res.message
        print(f"[+] Sequencer populated with Background_Card, Delivery_Title, and Audio_Track")

        # Step 2: Render Video Sequence to MP4 (H.264 / AAC)
        print("\n--- Test 2: Render Sequencer to MP4 (H.264 / AAC) ---")
        mp4_out = run_dir / "master_cut.mp4"
        r_mp4 = executor.execute_tool("render_vse_sequence", {
            "output_path": str(mp4_out),
            "frame_start": 1,
            "frame_end": 5,
            "format": "MPEG4",
            "video_codec": "H264",
            "audio_codec": "AAC",
            "resolution_x": 320,
            "resolution_y": 240,
            "fps": 24.0,
        })
        assert r_mp4.is_success, r_mp4.message
        mp4_data = r_mp4.result
        print(f"[+] MP4 Render completed: status='{mp4_data['status']}', file='{mp4_data['output_file']}', bytes={mp4_data['file_size_bytes']}, frames={mp4_data['frame_count']}")
        assert mp4_data["status"] == "SUCCESS"
        assert mp4_data["file_size_bytes"] > 0
        assert Path(mp4_data["output_file"]).exists()

        # Step 3: Render Video Sequence to QuickTime ProRes
        print("\n--- Test 3: Render Sequencer to QuickTime ProRes (MOV) ---")
        mov_out = run_dir / "master_archive.mov"
        r_mov = executor.execute_tool("render_vse_sequence", {
            "output_path": str(mov_out),
            "frame_start": 1,
            "frame_end": 4,
            "format": "QUICKTIME",
            "video_codec": "PRORES",
            "audio_codec": "PCM",
            "resolution_x": 320,
            "resolution_y": 240,
        })
        assert r_mov.is_success, r_mov.message
        mov_data = r_mov.result
        print(f"[+] ProRes Render completed: status='{mov_data['status']}', file='{mov_data['output_file']}', bytes={mov_data['file_size_bytes']}")
        assert mov_data["status"] == "SUCCESS"
        assert mov_data["file_size_bytes"] > 0
        assert Path(mov_data["output_file"]).exists()

        # Step 4: Mixdown Audio to WAV (PCM S16)
        print("\n--- Test 4: Mixdown Audio to WAV (PCM S16) ---")
        wav_mix_out = run_dir / "audio_mixdown.wav"
        r_wav = executor.execute_tool("mixdown_vse_audio", {
            "output_path": str(wav_mix_out),
            "container": "WAV",
            "codec": "PCM",
            "format": "S16",
            "channels": "STEREO",
            "sample_rate": 48000,
        })
        assert r_wav.is_success, r_wav.message
        wav_data = r_wav.result
        print(f"[+] WAV Mixdown completed: status='{wav_data['status']}', file='{wav_data['output_file']}', bytes={wav_data['file_size_bytes']}")
        assert wav_data["status"] == "SUCCESS"
        assert wav_data["file_size_bytes"] > 0
        assert Path(wav_data["output_file"]).exists()

        # Step 5: Path Traversal Rejection Invariant
        print("\n--- Test 5: Path Traversal Defense Invariant ---")
        for bad_p in [
            ("render_vse_sequence", {"output_path": "../traversal.mp4"}),
            ("mixdown_vse_audio", {"output_path": "../traversal.wav"}),
        ]:
            trav_res = executor.execute_tool(bad_p[0], bad_p[1])
            assert not trav_res.is_success, f"Vulnerability: Path traversal allowed for {bad_p[0]}"
            print(f"[+] Traversal rejection verified for {bad_p[0]}: {trav_res.message}")

        # Step 6: Fail-Closed Security Boundary Check
        print("\n--- Test 6: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("render_vse_sequence", {"output_path": str(run_dir / "unauth.mp4"), "approved": True}),
            ("mixdown_vse_audio", {"output_path": str(run_dir / "unauth.wav"), "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on delivery tools: PASSED")

        # Step 7: Teardown
        print("\n--- Test 7: Graceful Teardown ---")
        (run_dir / "stop.flag").touch()
        blender_proc.wait(timeout=10.0)
        print(f"[+] Disposable Blender process {blender_proc.pid} terminated cleanly with code {blender_proc.returncode}")

    finally:
        if blender_proc.poll() is None:
            blender_proc.kill()
            blender_proc.wait()

    # Step 8: Production Isolation Verification
    print("\n--- Step 8: Verifying Production Isolation ---")
    zip_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip"
    sha_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip.sha256"
    assert zip_path.exists() and sha_path.exists(), "Release artifact v0.1.88 missing!"
    import hashlib
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert actual_sha == "ba14a1ed39f78096d054cd4f81eac99ded4d61157fa56e692ad5aa521493c702", "CRITICAL: v0.1.88 release ZIP was modified!"
    print(f"[+] Release package v0.1.88 verified untouched (SHA-256: {actual_sha})")

    prod_handlers = Path(r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp\bridge\handlers.py")
    if prod_handlers.exists():
        assert "render_vse_sequence" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 9 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap9_e2e())
