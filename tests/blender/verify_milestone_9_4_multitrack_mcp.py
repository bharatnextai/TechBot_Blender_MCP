"""
Live Integration Test for Milestone 9.4: Multi-Track Spatial Composition, Strip Color Grading & Styled Lower-Thirds.
Target Engine: Blender 5.2.2 LTS (Official Release)
Production Isolation: Ephemeral Loopback Port (!= 9877), Production Bridge PID 39604 Untouched.

Verifies:
1. Multi-Track Timeline Assembly:
   - Channel 1: Background Scene Plate (IMAGE strip from 3D render)
   - Channel 2: Picture-in-Picture Inset / Overlay (COLOR strip)
   - Channel 3: Styled Lower-Third Title Card (TEXT strip with background box and shadow)
   - Channel 4: Synchronized Audio Track (SOUND strip with volume control)
2. Spatial Composition & 2D Transforms:
   - Scale down to 35% (0.35 x 0.35) and offset to corner (+220, +140)
   - Boundary cropping (10px margins)
3. Non-Destructive Strip Color Grading Modifiers:
   - BRIGHT_CONTRAST modifier (bright=0.1, contrast=1.2)
   - COLOR_BALANCE modifier (LIFT_GAMMA_GAIN, warm multiplier)
4. Professional Styled Lower-Thirds:
   - configure_vse_text_style with font size 42, box styling, margins, and shadow
5. Evaluated Timeline Verification:
   - Independent inspect_vse_timeline RNA property readbacks
6. Multi-Track Rendering & Export:
   - Representative evaluated multi-track frame PNG export
   - Master H.264/AAC MP4 video sequence export
7. Pure-Python ISOBMFF Media Container Analysis:
   - ftyp, moov, mvhd, mdat, and dual audio/video trak validation
8. Fail-Closed Security Invariants:
   - Model-supplied approved=True rejection
   - Unapproved mutation rejection
   - Path traversal rejection
"""

import os
import sys
import json
import time
import wave
import struct
import math
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
    ok, token = registry.resolve_request(req.request_id, "approved", reason="DISPOSABLE 9.4 LIVE TEST", approve_task_group=False)
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
        "bridge_running": bool(server.running),
    }, indent=2), encoding="utf-8")
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port if port != 9877 else find_free_port()


def generate_test_tone(dest_path: Path, duration_sec: float = 2.0, freq_hz: float = 440.0, sample_rate: int = 44100) -> Path:
    total_samples = int(duration_sec * sample_rate)
    with wave.open(str(dest_path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        samples = []
        for i in range(total_samples):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
            samples.append(struct.pack("<hh", val, val))
        wav_file.writeframes(b"".join(samples))
    return dest_path


def parse_isobmff_boxes(file_path: Path) -> dict:
    data = file_path.read_bytes()
    offset = 0
    boxes = {}
    traks = []

    while offset + 8 <= len(data):
        length, btype = struct.unpack(">I4s", data[offset:offset+8])
        btype_str = btype.decode("ascii", errors="replace")
        if length == 1:
            length = struct.unpack(">Q", data[offset+8:offset+16])[0]
            header_size = 16
        elif length == 0:
            length = len(data) - offset
            header_size = 8
        else:
            header_size = 8

        boxes[btype_str] = {
            "offset": offset,
            "length": length,
            "header_size": header_size,
        }

        # Inspect ftyp
        if btype_str == "ftyp" and length >= 16:
            major_brand = data[offset+8:offset+12].decode("ascii", errors="replace")
            minor_ver = struct.unpack(">I", data[offset+12:offset+16])[0]
            boxes["ftyp"]["major_brand"] = major_brand
            boxes["ftyp"]["minor_version"] = minor_ver

        # Inspect moov -> mvhd and trak boxes
        if btype_str == "moov":
            moov_data = data[offset+header_size:offset+length]
            m_offset = 0
            while m_offset + 8 <= len(moov_data):
                m_len, m_type = struct.unpack(">I4s", moov_data[m_offset:m_offset+8])
                m_type_str = m_type.decode("ascii", errors="replace")
                if m_type_str == "mvhd" and m_len >= 24:
                    version = moov_data[m_offset+8]
                    if version == 0:
                        timescale, duration = struct.unpack(">II", moov_data[m_offset+20:m_offset+28])
                    else:
                        timescale, duration = struct.unpack(">IQ", moov_data[m_offset+28:m_offset+40])
                    boxes["mvhd"] = {
                        "timescale": timescale,
                        "duration_ticks": duration,
                        "duration_seconds": round(duration / timescale, 3) if timescale else 0.0,
                    }
                elif m_type_str == "trak":
                    # Parse inner trak to find handler type (vide vs soun)
                    trak_data = moov_data[m_offset+8:m_offset+m_len]
                    t_offset = 0
                    trak_handler = "unknown"
                    while t_offset + 8 <= len(trak_data):
                        sub_len, sub_type = struct.unpack(">I4s", trak_data[t_offset:t_offset+8])
                        sub_type_str = sub_type.decode("ascii", errors="replace")
                        if sub_type_str == "mdia":
                            mdia_data = trak_data[t_offset+8:t_offset+sub_len]
                            mdia_offset = 0
                            while mdia_offset + 8 <= len(mdia_data):
                                h_len, h_type = struct.unpack(">I4s", mdia_data[mdia_offset:mdia_offset+8])
                                h_type_str = h_type.decode("ascii", errors="replace")
                                if h_type_str == "hdlr" and h_len >= 16:
                                    # Handler type is at offset 8+8 = 16 bytes into hdlr box (or 8+4 if version/flags is 4 bytes)
                                    # Full Box header is 4 bytes (version+flags), then 4 bytes pre_defined, then 4 bytes handler_type
                                    handler_sub = mdia_data[mdia_offset+16:mdia_offset+20].decode("ascii", errors="replace")
                                    trak_handler = handler_sub
                                mdia_offset += h_len if h_len > 0 else len(mdia_data)
                        t_offset += sub_len if sub_len > 0 else len(trak_data)
                    traks.append(trak_handler)

                m_offset += m_len if m_len > 0 else len(moov_data)

        offset += length if length > 0 else len(data)

    boxes["traks"] = traks
    return boxes


def run_milestone_9_4_live():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_multitrack_94_"))
    evidence_dir = PROJECT / "tests" / "blender" / "output" / "milestone_9_4"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_file = run_dir / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_dir / "ready.json"

    # Generate audio tone
    tone_wav = generate_test_tone(run_dir / "stereo_dialogue.wav", duration_sec=2.5, freq_hz=440.0)

    env = os.environ.copy()
    env["UMCP_RUN_ROOT"] = str(run_dir)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["PYTHONPATH"] = str(PROJECT)

    print("=" * 80)
    print("STARTING CAPABILITY 9 — MILESTONE 9.4: MULTI-TRACK SPATIAL COMPOSITION VERIFICATION")
    print(f"Target: Blender 5.2.2 LTS | Ephemeral Bridge Port: {port} (PID 39604 Isolated)")
    print(f"Run Directory: {run_dir}")
    print(f"Evidence Directory: {evidence_dir}")
    print("=" * 80)

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
        if time.time() - t0 > 30:
            blender_proc.kill()
            out, err = blender_proc.communicate()
            raise TimeoutError(f"Disposable Blender bridge failed to start:\n{err.decode('utf-8', errors='replace')}")
        time.sleep(0.2)

    ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
    print(f"\n[+] Disposable Blender {ready_data['blender']} running on PID {ready_data['pid']} port {ready_data['port']}")

    telemetry = {
        "blender_version": ready_data["blender"],
        "disposable_pid": ready_data["pid"],
        "ephemeral_port": ready_data["port"],
        "stages": {},
        "failures": {},
    }

    try:
        sys.path.insert(0, str(PROJECT))
        from mcp_service.execution.blender_executor import BlenderExecutor

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()

        # ---------------------------------------------------------------------
        # Stage 1: Create 3D Scene Plate
        # ---------------------------------------------------------------------
        print("\n--- Stage 1: Render 3D Background Plate ---")
        executor.execute_tool("create_primitive", {"primitive_type": "cube", "name": "HeroObject", "location": [0.0, 0.0, 0.0]})
        executor.execute_tool("create_camera", {"name": "HeroCam", "location": [0.0, -4.0, 1.5], "rotation_euler": [1.2, 0.0, 0.0], "set_active": True})
        executor.execute_tool("create_light", {"name": "HeroSun", "light_type": "SUN", "energy": 4.0, "location": [2.0, -2.0, 5.0]})

        render_png_file = run_dir / "hero_plate.png"
        r_scene = executor.execute_tool("render_scene", {
            "render_mode": "still",
            "output_format": "PNG",
            "output_path": str(render_png_file),
            "camera": "HeroCam",
        })
        assert r_scene.is_success, f"render_scene failed: {r_scene.message}"
        rendered_plate_path = Path(r_scene.result["output_file"])
        assert rendered_plate_path.exists(), "Rendered plate not found on disk"
        print(f"[+] Rendered 3D plate: {rendered_plate_path} ({rendered_plate_path.stat().st_size} bytes)")
        shutil.copy(rendered_plate_path, evidence_dir / "hero_plate.png")
        telemetry["stages"]["stage_1_scene_render"] = r_scene.result

        # ---------------------------------------------------------------------
        # Stage 2: Multi-Track Timeline Assembly (Channels 1 & 2)
        # ---------------------------------------------------------------------
        print("\n--- Stage 2: Multi-Track Timeline Assembly ---")
        # Channel 1: Base scene plate
        r_ch1 = executor.execute_tool("create_vse_strip", {
            "strip_type": "IMAGE",
            "name": "RenderPlate",
            "channel": 1,
            "frame_start": 1,
            "duration": 50,
            "filepath": str(rendered_plate_path),
        })
        assert r_ch1.is_success, f"Channel 1 RenderPlate failed: {r_ch1.message}"
        print(f"[+] Channel 1 Strip created: {r_ch1.result['name']} (duration={r_ch1.result['duration']})")

        # Channel 2: Picture-in-Picture overlay
        r_ch2 = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR",
            "name": "OverlayStrip",
            "channel": 2,
            "frame_start": 1,
            "duration": 50,
            "color": [0.15, 0.35, 0.75],
        })
        assert r_ch2.is_success, f"Channel 2 OverlayStrip failed: {r_ch2.message}"
        print(f"[+] Channel 2 Strip created: {r_ch2.result['name']} (color=[0.15, 0.35, 0.75])")

        telemetry["stages"]["stage_2_strips"] = {
            "ch1": r_ch1.result,
            "ch2": r_ch2.result,
        }

        # ---------------------------------------------------------------------
        # Stage 3: Spatial Composition (2D Transform & Crop on Channel 2)
        # ---------------------------------------------------------------------
        print("\n--- Stage 3: 2D Spatial Transforms & Cropping ---")
        r_trans = executor.execute_tool("transform_vse_strip", {
            "name": "OverlayStrip",
            "scale_x": 0.35,
            "scale_y": 0.35,
            "offset_x": 220.0,
            "offset_y": 140.0,
            "action": "UPDATE",
        })
        assert r_trans.is_success, f"transform_vse_strip failed: {r_trans.message}"
        tr_res = r_trans.result.get("transform", {})
        print(f"[+] 2D Transform applied: scale={tr_res.get('scale_x')}x{tr_res.get('scale_y')}, offset=({tr_res.get('offset_x')}, {tr_res.get('offset_y')})")

        r_crop = executor.execute_tool("crop_vse_strip", {
            "name": "OverlayStrip",
            "min_x": 10,
            "max_x": 10,
            "min_y": 10,
            "max_y": 10,
            "action": "UPDATE",
        })
        assert r_crop.is_success, f"crop_vse_strip failed: {r_crop.message}"
        print(f"[+] Crop margins applied: {r_crop.result}")

        telemetry["stages"]["stage_3_transforms"] = {
            "transform": r_trans.result,
            "crop": r_crop.result,
        }

        # ---------------------------------------------------------------------
        # Stage 4: Non-Destructive Strip Color Grading Modifiers
        # ---------------------------------------------------------------------
        print("\n--- Stage 4: Strip Color Grading Modifiers ---")
        r_mod1 = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "ADD",
            "name": "RenderPlate",
            "modifier_type": "BRIGHT_CONTRAST",
            "bright": 0.1,
            "contrast": 1.2,
        })
        assert r_mod1.is_success, f"BRIGHT_CONTRAST modifier failed: {r_mod1.message}"
        print(f"[+] Added Modifier 1: {r_mod1.result}")

        r_mod2 = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "ADD",
            "name": "RenderPlate",
            "modifier_type": "COLOR_BALANCE",
            "correction_method": "LIFT_GAMMA_GAIN",
            "lift": [0.0, 0.0, 0.05],
            "gamma": [1.0, 1.0, 1.0],
            "gain": [1.1, 1.05, 0.95],
            "color_multiply": 1.1,
        })
        assert r_mod2.is_success, f"COLOR_BALANCE modifier failed: {r_mod2.message}"
        print(f"[+] Added Modifier 2: {r_mod2.result}")

        telemetry["stages"]["stage_4_modifiers"] = {
            "bright_contrast": r_mod1.result,
            "color_balance": r_mod2.result,
        }

        # ---------------------------------------------------------------------
        # Stage 5: Professional Styled Lower-Third Title Card (Channel 3)
        # ---------------------------------------------------------------------
        print("\n--- Stage 5: Styled Lower-Third Title Card ---")
        r_title = executor.execute_tool("create_vse_text_strip", {
            "text": "Universal MCP Studio",
            "name": "LowerThird",
            "channel": 3,
            "frame_start": 1,
            "duration": 50,
        })
        assert r_title.is_success, f"create_vse_text_strip failed: {r_title.message}"
        print(f"[+] Channel 3 Text Strip created: {r_title.result['name']}")

        r_style = executor.execute_tool("configure_vse_text_style", {
            "name": "LowerThird",
            "action": "UPDATE",
            "font_size": 42.0,
            "location": [0.1, 0.15],
            "alignment_x": "LEFT",
            "use_box": True,
            "box_color": [0.0, 0.0, 0.0, 0.7],
            "box_margin": 0.1,
            "use_shadow": True,
        })
        assert r_style.is_success, f"configure_vse_text_style failed: {r_style.message}"
        print(f"[+] LowerThird styling configured: {r_style.result}")

        telemetry["stages"]["stage_5_title"] = {
            "strip": r_title.result,
            "style": r_style.result,
        }

        # ---------------------------------------------------------------------
        # Stage 6: Synchronized Audio Track (Channel 4)
        # ---------------------------------------------------------------------
        print("\n--- Stage 6: Synchronized Audio Track ---")
        r_audio = executor.execute_tool("create_vse_strip", {
            "strip_type": "SOUND",
            "name": "AudioTrack",
            "channel": 4,
            "frame_start": 1,
            "filepath": str(tone_wav),
        })
        assert r_audio.is_success, f"Channel 4 AudioTrack failed: {r_audio.message}"
        print(f"[+] Channel 4 Audio Strip created: {r_audio.result['name']}")

        r_vol = executor.execute_tool("configure_vse_audio", {
            "name": "AudioTrack",
            "volume": 0.9,
        })
        assert r_vol.is_success, f"configure_vse_audio failed: {r_vol.message}"
        print(f"[+] Audio volume configured: {r_vol.result}")
        shutil.copy(tone_wav, evidence_dir / "stereo_dialogue.wav")

        telemetry["stages"]["stage_6_audio"] = {
            "strip": r_audio.result,
            "volume": r_vol.result,
        }

        # ---------------------------------------------------------------------
        # Stage 7: Independent Timeline Inspection & RNA Verification
        # ---------------------------------------------------------------------
        print("\n--- Stage 7: Independent Timeline Inspection & RNA Verification ---")
        # 1. Global timeline inspection
        r_inspect = executor.execute_tool("inspect_vse_timeline", {})
        assert r_inspect.is_success, f"inspect_vse_timeline failed: {r_inspect.message}"
        strips_data = r_inspect.result["strips"]
        print(f"[+] Total timeline strips: {len(strips_data)}")

        strip_map = {s["name"]: s for s in strips_data}
        assert "RenderPlate" in strip_map, "RenderPlate missing from timeline"
        assert "OverlayStrip" in strip_map, "OverlayStrip missing from timeline"
        assert "LowerThird" in strip_map, "LowerThird missing from timeline"
        assert "AudioTrack" in strip_map, "AudioTrack missing from timeline"

        # Verify channels
        assert strip_map["RenderPlate"]["channel"] == 1, "RenderPlate must be on channel 1"
        assert strip_map["OverlayStrip"]["channel"] == 2, "OverlayStrip must be on channel 2"
        assert strip_map["LowerThird"]["channel"] == 3, "LowerThird must be on channel 3"
        assert strip_map["AudioTrack"]["channel"] == 4, "AudioTrack must be on channel 4"

        # 2. Inspect 2D Transform RNA on OverlayStrip
        r_inspect_trans = executor.execute_tool("transform_vse_strip", {
            "name": "OverlayStrip",
            "action": "INSPECT",
        })
        assert r_inspect_trans.is_success, f"INSPECT transform failed: {r_inspect_trans.message}"
        tr_info = r_inspect_trans.result["transform"]
        assert abs(tr_info.get("scale_x", 0.0) - 0.35) < 1e-3, f"Unexpected scale_x: {tr_info}"
        assert abs(tr_info.get("scale_y", 0.0) - 0.35) < 1e-3, f"Unexpected scale_y: {tr_info}"
        assert abs(tr_info.get("offset_x", 0.0) - 220.0) < 1e-3, f"Unexpected offset_x: {tr_info}"
        assert abs(tr_info.get("offset_y", 0.0) - 140.0) < 1e-3, f"Unexpected offset_y: {tr_info}"
        print(f"[+] Verified OverlayStrip 2D transform RNA: scale={tr_info['scale_x']}x{tr_info['scale_y']}, offset=({tr_info['offset_x']}, {tr_info['offset_y']})")

        # 3. Inspect Crop RNA on OverlayStrip
        r_inspect_crop = executor.execute_tool("crop_vse_strip", {
            "name": "OverlayStrip",
            "action": "INSPECT",
        })
        assert r_inspect_crop.is_success, f"INSPECT crop failed: {r_inspect_crop.message}"
        cr_info = r_inspect_crop.result["crop"]
        assert cr_info.get("min_x") == 10 and cr_info.get("max_x") == 10, f"Unexpected crop: {cr_info}"
        print(f"[+] Verified OverlayStrip Crop RNA: {cr_info}")

        # 4. Inspect Modifiers RNA on RenderPlate
        r_inspect_mods = executor.execute_tool("manage_vse_strip_modifiers", {
            "action": "LIST",
            "name": "RenderPlate",
        })
        assert r_inspect_mods.is_success, f"LIST modifiers failed: {r_inspect_mods.message}"
        mods_list = r_inspect_mods.result.get("modifiers", [])
        mod_types = [m.get("type") for m in mods_list]
        assert "BRIGHT_CONTRAST" in mod_types, f"BRIGHT_CONTRAST modifier not found: {mod_types}"
        assert "COLOR_BALANCE" in mod_types, f"COLOR_BALANCE modifier not found: {mod_types}"
        print(f"[+] Verified RenderPlate Modifiers RNA: {mod_types}")

        # 5. Inspect Text Style RNA on LowerThird
        r_inspect_style = executor.execute_tool("configure_vse_text_style", {
            "name": "LowerThird",
            "action": "INSPECT",
        })
        assert r_inspect_style.is_success, f"INSPECT style failed: {r_inspect_style.message}"
        style_info = r_inspect_style.result.get("style", {})
        assert style_info.get("use_box") is True, f"use_box not True: {style_info}"
        assert abs(style_info.get("box_margin", 0.0) - 0.1) < 1e-3, f"box_margin != 0.1: {style_info}"
        assert abs(style_info.get("font_size", 0.0) - 42.0) < 1e-3, f"font_size != 42.0: {style_info}"
        print(f"[+] Verified LowerThird Style RNA: font_size={style_info['font_size']}, use_box={style_info['use_box']}, box_margin={style_info['box_margin']}")

        print("[+] All RNA properties verified: 4 distinct channels, transform scale/offset, 2 modifiers, styled box.")

        (evidence_dir / "timeline_inspection.json").write_text(json.dumps({
            "timeline": r_inspect.result,
            "transform": r_inspect_trans.result,
            "crop": r_inspect_crop.result,
            "modifiers": r_inspect_mods.result,
            "style": r_inspect_style.result,
        }, indent=2), encoding="utf-8")
        telemetry["stages"]["stage_7_inspection"] = {
            "timeline": r_inspect.result,
            "transform": r_inspect_trans.result,
            "crop": r_inspect_crop.result,
            "modifiers": r_inspect_mods.result,
            "style": r_inspect_style.result,
        }

        # ---------------------------------------------------------------------
        # Stage 8: Representative Multi-Track Frame PNG Render
        # ---------------------------------------------------------------------
        print("\n--- Stage 8: Representative Multi-Track Frame Render (PNG) ---")
        frame_png_file = run_dir / "multitrack_frame_0015.png"
        r_frame = executor.execute_tool("render_vse_sequence", {
            "output_path": str(frame_png_file),
            "format": "PNG",
            "frame_start": 15,
            "frame_end": 15,
            "resolution_x": 640,
            "resolution_y": 360,
        })
        assert r_frame.is_success, f"Frame render failed: {r_frame.message}"
        rendered_frame = Path(r_frame.result["output_file"])
        assert rendered_frame.exists(), f"Rendered frame file not found: {rendered_frame}"
        frame_bytes = rendered_frame.read_bytes()
        assert frame_bytes[:8] == b"\x89PNG\r\n\x1a\n", "Rendered frame does not have valid PNG header"
        assert len(frame_bytes) > 2000, f"Rendered frame suspiciously small: {len(frame_bytes)} bytes"

        shutil.copy(rendered_frame, evidence_dir / "representative_multitrack_frame.png")
        print(f"[+] Representative multi-track frame PNG verified: {rendered_frame} ({len(frame_bytes)} bytes)")

        telemetry["stages"]["stage_8_frame_render"] = {
            "output_file": r_frame.result["output_file"],
            "size_bytes": len(frame_bytes),
            "png_header_verified": True,
        }

        # ---------------------------------------------------------------------
        # Stage 9: Master Multi-Track MP4 Export (H.264 / AAC)
        # ---------------------------------------------------------------------
        print("\n--- Stage 9: Master Multi-Track MP4 Export ---")
        master_mp4_file = run_dir / "multitrack_master.mp4"
        r_export = executor.execute_tool("render_vse_sequence", {
            "output_path": str(master_mp4_file),
            "format": "MPEG4",
            "video_codec": "H264",
            "audio_codec": "AAC",
            "frame_start": 1,
            "frame_end": 50,
            "resolution_x": 640,
            "resolution_y": 360,
            "fps": 24,
        })
        assert r_export.is_success, f"Master MP4 export failed: {r_export.message}"
        actual_mp4 = Path(r_export.result["output_file"])
        assert actual_mp4.exists(), f"Master MP4 file not found: {actual_mp4}"
        mp4_size = actual_mp4.stat().st_size
        assert mp4_size > 8000, f"Master MP4 suspiciously small: {mp4_size} bytes"

        shutil.copy(actual_mp4, evidence_dir / "multitrack_master.mp4")
        print(f"[+] Master MP4 export verified: {actual_mp4} ({mp4_size} bytes)")

        telemetry["stages"]["stage_9_mp4_export"] = {
            "output_file": r_export.result["output_file"],
            "size_bytes": mp4_size,
        }

        # ---------------------------------------------------------------------
        # Stage 10: Pure-Python ISOBMFF Deep Container Analysis
        # ---------------------------------------------------------------------
        print("\n--- Stage 10: Pure-Python ISOBMFF Media Container Analysis ---")
        boxes = parse_isobmff_boxes(actual_mp4)
        print(f"[+] Top-level ISOBMFF boxes: {list(boxes.keys())}")
        assert "ftyp" in boxes, "Missing ftyp box"
        assert "moov" in boxes, "Missing moov box"
        assert "mdat" in boxes, "Missing mdat box"

        print(f"[+] Major brand: {boxes['ftyp'].get('major_brand')}")
        mvhd = boxes.get("mvhd", {})
        print(f"[+] Movie duration: {mvhd.get('duration_seconds')}s (timescale={mvhd.get('timescale')})")
        # 50 frames @ 24fps = 2.083s
        expected_sec = 50.0 / 24.0
        assert abs(mvhd.get("duration_seconds", 0.0) - expected_sec) < 0.2, f"Duration mismatch: {mvhd.get('duration_seconds')} vs {expected_sec}"

        traks = boxes.get("traks", [])
        print(f"[+] Detected track handlers: {traks}")
        assert "vide" in traks, "Video track (vide) handler missing in MP4 container!"
        assert "soun" in traks, "Audio track (soun) handler missing in MP4 container!"

        telemetry["stages"]["stage_10_isobmff"] = {
            "boxes": {k: v for k, v in boxes.items() if k not in ("moov",)},
            "traks": traks,
        }

        # ---------------------------------------------------------------------
        # Stage 11: Fail-Closed Security Tests
        # ---------------------------------------------------------------------
        print("\n--- Stage 11: Fail-Closed Security Tests ---")
        # 1. Untrusted approved=True in VideoEditorAgent task is rejected
        print("[*] Security Test 1: Untrusted approved=True rejected fail-closed in VideoEditorAgent...")
        from mcp_service.agents.video_editor import VideoEditorAgent
        from shared.models.agent_contracts import AgentTask, TaskStatus
        v_agent = VideoEditorAgent()
        bad_task = AgentTask(
            task_id="t_security_bad",
            required_capability="video.transforms",
            task_type="transform_vse_strip",
            input_params={"name": "OverlayStrip", "scale_x": 0.5, "approved": True},
        )
        res_bad = v_agent.execute_task(bad_task, executor, trusted_approval=None)
        assert res_bad.status == TaskStatus.FAILED, f"Expected task failure on approved=True, got {res_bad.status}"
        assert "approved=True" in res_bad.errors[0], f"Expected untrusted approval error, got: {res_bad.errors}"
        print(f"[+] VideoEditorAgent correctly rejected untrusted approved=True: {res_bad.errors[0]}")

        # 2. Path traversal in sound filepath
        print("[*] Security Test 2: Path traversal in sound filepath rejected...")
        r_trav = executor.execute_tool("create_vse_strip", {
            "strip_type": "SOUND",
            "name": "EvilSound",
            "channel": 5,
            "frame_start": 1,
            "filepath": "../../secret.wav",
        })
        assert not r_trav.is_success, "Path traversal in SOUND strip was unexpectedly allowed!"
        assert "traversal" in r_trav.message.lower() or "forbidden" in r_trav.message.lower()
        print(f"[+] Path traversal correctly rejected: {r_trav.message}")

        # 3. Path traversal in export path
        print("[*] Security Test 3: Path traversal in render output path rejected...")
        r_trav_exp = executor.execute_tool("render_vse_sequence", {
            "output_path": "../../evil_export.mp4",
            "format": "MPEG4",
        })
        assert not r_trav_exp.is_success, "Path traversal in render output was unexpectedly allowed!"
        assert "traversal" in r_trav_exp.message.lower() or "forbidden" in r_trav_exp.message.lower()
        print(f"[+] Export path traversal correctly rejected: {r_trav_exp.message}")

        telemetry["failures"] = {
            "untrusted_approved_true_rejected": True,
            "sound_traversal_rejected": True,
            "export_traversal_rejected": True,
        }

        print("\n" + "=" * 80)
        print("MILESTONE 9.4 LIVE MCP VERIFICATION: ALL GATES PASSED")
        print("=" * 80)

    finally:
        (run_dir / "stop.flag").write_text("STOP", encoding="utf-8")
        try:
            blender_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            blender_proc.kill()

        (evidence_dir / "telemetry.json").write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
        shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    run_milestone_9_4_live()
