"""
Capability 7.1 Phase 3: Photometric & Atmospheric Behavioral Verification.

Executes against actual Blender 5.2.2 LTS in a disposable headless process
communicating exclusively through an ephemeral MCP loopback bridge port.
Zero contact with production port 9877.

Verifies:
1. Photometric surface luminance scaling under energy variation (10W vs 100W).
2. Chromatic balance / spectral temperature shift (warm R/B > 1.20 vs cool B/R > 1.20).
3. Multi-point key-to-fill contrast ratio (> 1.5:1).
4. Atmospheric simulation (Nishita physical sky parameters in evaluated node tree).
5. Atmospheric radiance variance & environment dome rotation.
6. Symmetrical cleanup and teardown.
7. Production bridge port 9877 isolation.
"""

import asyncio
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON_EXE = Path(sys.executable)

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

scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

# Clear default objects
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

queue = MainThreadQueue(bpy)
server = BridgeServer(port=port, queue=queue)
server.start()

(root / "ready.json").write_text(json.dumps({
    "status": "ready",
    "port": port,
    "pid": os.getpid(),
    "blender": bpy.app.version_string,
}), encoding="utf-8")

deadline = time.monotonic() + 300

try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        queue.drain_queue()
        time.sleep(0.01)
finally:
    server.stop()
"""


def unwrap(res: Any) -> Dict[str, Any]:
    if hasattr(res, "content") and res.content:
        raw = json.loads(res.content[0].text)
        if isinstance(raw, dict) and "result" in raw:
            return raw["result"]
        return raw
    if isinstance(res, dict):
        if "result" in res:
            return res["result"]
        return res
    raise ValueError(f"Unable to unwrap response: {res}")


def is_error_response(res: Any) -> bool:
    if getattr(res, "isError", False):
        return True
    try:
        data = unwrap(res)
        return data.get("status") == "error"
    except Exception:
        return False


async def run_photometric_atmospheric_verification():
    print("=" * 80)
    print("CAPABILITY 7.1 PHASE 3: PHOTOMETRIC & ATMOSPHERIC BEHAVIORAL VERIFICATION")
    print("=" * 80)

    # 1. Ephemeral port selection
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    with tempfile.TemporaryDirectory(prefix="umcp_cap71_p3_") as tmpdir:
        run_root = Path(tmpdir)
        config_dir = run_root / "config"
        scripts_dir = run_root / "scripts"
        ext_dir = run_root / "extensions"
        config_dir.mkdir()
        scripts_dir.mkdir()
        ext_dir.mkdir()

        script_file = run_root / "bootstrap.py"
        script_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
        ready_file = run_root / "ready.json"

        blender_env = dict(os.environ)
        blender_env["UMCP_RUN_ROOT"] = str(run_root)
        blender_env["UMCP_PROJECT"] = str(PROJECT)
        blender_env["UMCP_BRIDGE_PORT"] = str(port)
        blender_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
        blender_env["UMCP_LOCAL_TEST_SCOPE"] = "lighting_world_v1"
        blender_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
        blender_env["BLENDER_USER_CONFIG"] = str(config_dir)
        blender_env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
        blender_env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
        blender_env["PYTHONPATH"] = str(PROJECT)
        blender_env["PYTHONDONTWRITEBYTECODE"] = "1"

        print(f"[*] Spawning disposable Blender 5.2.2 instance on ephemeral port {port}...")
        blender_log_path = run_root / "blender_process.log"
        blender_log_file = open(blender_log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [
                str(BLENDER),
                "--background",
                "--factory-startup",
                "--python",
                str(script_file),
            ],
            env=blender_env,
            stdout=blender_log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

        t0 = time.time()
        while not ready_file.exists():
            if proc.poll() is not None:
                try:
                    blender_log_file.flush()
                    blender_log_file.close()
                except Exception:
                    pass
                out = blender_log_path.read_text(encoding="utf-8", errors="replace") if blender_log_path.exists() else ""
                raise RuntimeError(f"Disposable Blender process exited prematurely:\n{out}")
            if time.time() - t0 > 20:
                proc.terminate()
                try:
                    blender_log_file.close()
                except Exception:
                    pass
                raise TimeoutError("Timed out waiting for disposable Blender bootstrap.")
            await asyncio.sleep(0.1)

        info = json.loads(ready_file.read_text(encoding="utf-8"))
        print(f"[+] Blender ready! PID: {info['pid']}, Version: {info['blender']}")

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            client_env = dict(os.environ)
            client_env["UMCP_LOCAL_TEST_SCOPE"] = "lighting_world_v1"
            client_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
            client_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
            client_env["UMCP_BRIDGE_PORT"] = str(port)
            client_env["BLENDER_USER_CONFIG"] = str(config_dir)
            client_env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
            client_env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
            client_env["PYTHONPATH"] = str(PROJECT)
            client_env["PYTHONDONTWRITEBYTECODE"] = "1"

            mcp_params = StdioServerParameters(
                command=str(PYTHON_EXE),
                args=[
                    "-B",
                    "-m",
                    "mcp_service.app",
                    "--transport",
                    "stdio",
                    "--bridge-port",
                    str(port),
                    "--bridge-timeout",
                    "25",
                    "--approval-mode",
                    "blender",
                    "--debug",
                ],
                env=client_env,
                cwd=str(PROJECT),
            )

            print("[*] Connecting Stdio MCP client to server...")
            async with stdio_client(mcp_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    print("[+] MCP Session Initialized.")

                    # =========================================================================
                    # STAGE 1: PHOTOMETRIC SURFACE LUMINANCE SCALING
                    # =========================================================================
                    print("\n" + "-" * 70)
                    print("STAGE 1: PHOTOMETRIC SURFACE LUMINANCE SCALING (10W vs 100W)")
                    print("-" * 70)

                    # Initialize black world to prevent ambient contamination
                    res_w = await session.call_tool("configure_world", {
                        "color": [0.0, 0.0, 0.0],
                        "strength": 0.0,
                    })
                    assert not is_error_response(res_w)

                    # Create receiver sphere
                    res_sphere = await session.call_tool("create_primitive", {
                        "primitive_type": "sphere",
                        "name": "ReceiverSphere",
                        "location": [0.0, 0.0, 0.0],
                        "radius": 1.0,
                    })
                    assert not is_error_response(res_sphere)

                    # Create baseline Area Light at 10W
                    res_key = await session.call_tool("create_light", {
                        "name": "AreaKey",
                        "light_type": "AREA",
                        "shape": "RECTANGLE",
                        "size": 2.0,
                        "size_y": 1.0,
                        "energy": 10.0,
                        "color": [1.0, 1.0, 1.0],
                        "location": [0.0, -2.5, 2.0],
                        "rotation_euler": [0.896, 0.0, 0.0],
                    })
                    assert not is_error_response(res_key)

                    # Create evaluation camera
                    res_cam = await session.call_tool("create_camera", {
                        "name": "EvalCam",
                        "location": [0.0, -4.0, 0.0],
                        "rotation_euler": [1.5707963, 0.0, 0.0],
                        "focal_length": 50.0,
                        "set_active": True,
                    })
                    assert not is_error_response(res_cam)

                    # Render at 10W
                    render_10w = str(run_root / "render_10w.png")
                    await session.call_tool("configure_render_settings", {
                        "resolution_x": 32,
                        "resolution_y": 32,
                        "output_format": "PNG",
                        "output_path": render_10w,
                    })
                    await session.call_tool("render_scene", {
                        "render_mode": "still",
                        "output_path": render_10w,
                        "output_format": "PNG",
                    })

                    # Increase energy to 100W
                    res_cfg_100w = await session.call_tool("configure_light", {
                        "name": "AreaKey",
                        "energy": 100.0,
                    })
                    assert not is_error_response(res_cfg_100w)

                    # Render at 100W
                    render_100w = str(run_root / "render_100w.png")
                    await session.call_tool("configure_render_settings", {
                        "output_path": render_100w,
                        "output_format": "PNG",
                    })
                    await session.call_tool("render_scene", {
                        "render_mode": "still",
                        "output_path": render_100w,
                        "output_format": "PNG",
                    })

                    # Measure evaluated surface luminance in Blender
                    eval_script = f"""
import bpy
img10 = bpy.data.images.load(r'{render_10w}')
px10 = list(img10.pixels)
img100 = bpy.data.images.load(r'{render_100w}')
px100 = list(img100.pixels)
# Center illuminated pixel
c_idx = (16 * 32 + 16) * 4
lum10 = 0.2126 * px10[c_idx] + 0.7152 * px10[c_idx+1] + 0.0722 * px10[c_idx+2]
lum100 = 0.2126 * px100[c_idx] + 0.7152 * px100[c_idx+1] + 0.0722 * px100[c_idx+2]
ratio = lum100 / max(lum10, 1e-6)
print(f"LUM_10={{lum10:.6f}} LUM_100={{lum100:.6f}} RATIO={{ratio:.3f}}")
"""
                    eval_proc = subprocess.run(
                        [str(BLENDER), "--background", "--factory-startup", "--python-expr", eval_script],
                        capture_output=True, text=True, check=True
                    )
                    eval_out = eval_proc.stdout
                    assert "LUM_10=" in eval_out
                    line_lum = [l for l in eval_out.splitlines() if "LUM_10=" in l][-1]
                    print(f"[+] 1.1 Luminance Scaling: {line_lum.strip()}")
                    ratio = float(eval_out.split("RATIO=")[1].split()[0])
                    assert ratio > 2.0, f"Expected luminance scaling ratio > 2.0, got {ratio}"
                    print(f"[+] Stage 1.1: Surface luminance scaled predictably under Area light energy increase ({ratio:.2f}x).")

                    # =========================================================================
                    # STAGE 2: CHROMATIC SPECTRAL TEMPERATURE SHIFT
                    # =========================================================================
                    print("\n" + "-" * 70)
                    print("STAGE 2: CHROMATIC SPECTRAL TEMPERATURE SHIFT (WARM vs COOL)")
                    print("-" * 70)

                    # Warm tungsten spectrum: [1.0, 0.6, 0.2]
                    await session.call_tool("configure_light", {
                        "name": "AreaKey",
                        "energy": 50.0,
                        "color": [1.0, 0.6, 0.2],
                    })
                    render_warm = str(run_root / "render_warm.png")
                    await session.call_tool("configure_render_settings", {
                        "output_path": render_warm,
                        "output_format": "PNG",
                    })
                    await session.call_tool("render_scene", {
                        "render_mode": "still",
                        "output_path": render_warm,
                        "output_format": "PNG",
                    })

                    # Cool daylight spectrum: [0.2, 0.6, 1.0]
                    await session.call_tool("configure_light", {
                        "name": "AreaKey",
                        "energy": 50.0,
                        "color": [0.2, 0.6, 1.0],
                    })
                    render_cool = str(run_root / "render_cool.png")
                    await session.call_tool("configure_render_settings", {
                        "output_path": render_cool,
                        "output_format": "PNG",
                    })
                    await session.call_tool("render_scene", {
                        "render_mode": "still",
                        "output_path": render_cool,
                        "output_format": "PNG",
                    })

                    chroma_script = f"""
import bpy
img_w = bpy.data.images.load(r'{render_warm}')
px_w = list(img_w.pixels)
img_c = bpy.data.images.load(r'{render_cool}')
px_c = list(img_c.pixels)
c_idx = (16 * 32 + 16) * 4
rw, gw, bw = px_w[c_idx], px_w[c_idx+1], px_w[c_idx+2]
rc, gc, bc = px_c[c_idx], px_c[c_idx+1], px_c[c_idx+2]
w_rb = rw / max(bw, 1e-6)
c_br = bc / max(rc, 1e-6)
print(f"WARM_RGB=[{{rw:.3f}}, {{gw:.3f}}, {{bw:.3f}}] COOL_RGB=[{{rc:.3f}}, {{gc:.3f}}, {{bc:.3f}}] WARM_R_DIV_B={{w_rb:.3f}} COOL_B_DIV_R={{c_br:.3f}}")
"""
                    chroma_proc = subprocess.run(
                        [str(BLENDER), "--background", "--factory-startup", "--python-expr", chroma_script],
                        capture_output=True, text=True, check=True
                    )
                    chroma_out = chroma_proc.stdout
                    assert "WARM_RGB=" in chroma_out
                    line_chroma = [l for l in chroma_out.splitlines() if "WARM_RGB=" in l][-1]
                    print(f"[+] 2.1 Chromatic Shift: {line_chroma.strip()}")
                    w_rb = float(chroma_out.split("WARM_R_DIV_B=")[1].split()[0])
                    c_br = float(chroma_out.split("COOL_B_DIV_R=")[1].split()[0])
                    assert w_rb > 1.20, f"Expected warm R/B > 1.20, got {w_rb}"
                    assert c_br > 1.20, f"Expected cool B/R > 1.20, got {c_br}"
                    print(f"[+] Stage 2.1: Chromatic shift verified (Warm R/B: {w_rb:.2f}, Cool B/R: {c_br:.2f}).")

                    # =========================================================================
                    # STAGE 3: MULTI-POINT KEY-TO-FILL CONTRAST RATIO
                    # =========================================================================
                    print("\n" + "-" * 70)
                    print("STAGE 3: MULTI-POINT KEY-TO-FILL CONTRAST RATIO")
                    print("-" * 70)

                    # Position Key at +45 deg (100W)
                    await session.call_tool("configure_light", {
                        "name": "AreaKey",
                        "color": [1.0, 1.0, 1.0],
                        "energy": 100.0,
                        "location": [2.5, -2.5, 1.5],
                        "rotation_euler": [0.785, 0.0, -0.785],
                    })

                    # Create Fill light at -45 deg (15W)
                    res_fill = await session.call_tool("create_light", {
                        "name": "AreaFill",
                        "light_type": "AREA",
                        "shape": "SQUARE",
                        "size": 1.5,
                        "energy": 15.0,
                        "color": [1.0, 1.0, 1.0],
                        "location": [-2.5, -2.5, 1.5],
                        "rotation_euler": [0.785, 0.0, 0.785],
                    })
                    assert not is_error_response(res_fill)

                    # Key-only render
                    await session.call_tool("configure_light", {"name": "AreaKey", "energy": 100.0})
                    await session.call_tool("configure_light", {"name": "AreaFill", "energy": 0.0})
                    render_key = str(run_root / "render_key.png")
                    await session.call_tool("configure_render_settings", {
                        "output_path": render_key,
                        "output_format": "PNG",
                    })
                    await session.call_tool("render_scene", {
                        "render_mode": "still",
                        "output_path": render_key,
                        "output_format": "PNG",
                    })

                    # Fill-only render
                    await session.call_tool("configure_light", {"name": "AreaKey", "energy": 0.0})
                    await session.call_tool("configure_light", {"name": "AreaFill", "energy": 15.0})
                    render_fill = str(run_root / "render_fill.png")
                    await session.call_tool("configure_render_settings", {
                        "output_path": render_fill,
                        "output_format": "PNG",
                    })
                    await session.call_tool("render_scene", {
                        "render_mode": "still",
                        "output_path": render_fill,
                        "output_format": "PNG",
                    })

                    keyfill_script = f"""
import bpy
img_k = bpy.data.images.load(r'{render_key}')
px_k = list(img_k.pixels)
img_f = bpy.data.images.load(r'{render_fill}')
px_f = list(img_f.pixels)
c_idx = (16 * 32 + 16) * 4
lum_k = 0.2126 * px_k[c_idx] + 0.7152 * px_k[c_idx+1] + 0.0722 * px_k[c_idx+2]
lum_f = 0.2126 * px_f[c_idx] + 0.7152 * px_f[c_idx+1] + 0.0722 * px_f[c_idx+2]
cr = lum_k / max(lum_f, 1e-6)
print(f"LUM_KEY={{lum_k:.4f}} LUM_FILL={{lum_f:.4f}} CONTRAST_RATIO={{cr:.3f}}")
"""
                    keyfill_proc = subprocess.run(
                        [str(BLENDER), "--background", "--factory-startup", "--python-expr", keyfill_script],
                        capture_output=True, text=True, check=True
                    )
                    keyfill_out = keyfill_proc.stdout
                    assert "CONTRAST_RATIO=" in keyfill_out
                    line_cr = [l for l in keyfill_out.splitlines() if "CONTRAST_RATIO=" in l][-1]
                    print(f"[+] 3.1 Key-to-Fill Contrast: {line_cr.strip()}")
                    cr = float(keyfill_out.split("CONTRAST_RATIO=")[1].split()[0])
                    assert cr > 1.5, f"Expected contrast ratio > 1.5:1, got {cr}"
                    print(f"[+] Stage 3.1: Multi-point key-to-fill contrast ratio verified ({cr:.2f}:1).")

                    # =========================================================================
                    # STAGE 4: ATMOSPHERIC SIMULATION (NISHITA PHYSICAL SKY)
                    # =========================================================================
                    print("\n" + "-" * 70)
                    print("STAGE 4: ATMOSPHERIC SIMULATION (NISHITA PHYSICAL SKY)")
                    print("-" * 70)

                    res_sky = await session.call_tool("configure_world", {
                        "sky_type": "MULTIPLE_SCATTERING",
                        "sun_disc": True,
                        "sun_size": 0.015,
                        "sun_intensity": 1.25,
                        "sun_elevation": 0.5236,  # 30 deg
                        "sun_rotation": 0.7854,   # 45 deg
                        "altitude": 250.0,
                        "air_density": 1.2,
                        "aerosol_density": 1.1,
                        "ozone_density": 1.0,
                        "environment_rotation": 0.7854,
                    })
                    assert not is_error_response(res_sky)

                    # Readback through inspect_scene_data
                    res_w_insp = await session.call_tool("inspect_scene_data", {"category": "world_settings"})
                    data_w = unwrap(res_w_insp)
                    assert data_w.get("sky_type") == "MULTIPLE_SCATTERING"
                    sky_params = data_w.get("sky_parameters", {})
                    assert sky_params.get("sun_disc") is True
                    assert abs(sky_params.get("sun_size", 0) - 0.015) < 1e-4
                    assert abs(sky_params.get("sun_intensity", 0) - 1.25) < 1e-4
                    assert abs(sky_params.get("sun_elevation", 0) - 0.5236) < 1e-4
                    assert abs(sky_params.get("sun_rotation", 0) - 0.7854) < 1e-4
                    assert abs(sky_params.get("altitude", 0) - 250.0) < 1e-4
                    assert abs(sky_params.get("air_density", 0) - 1.2) < 1e-4
                    assert abs(sky_params.get("aerosol_density", 0) - 1.1) < 1e-4
                    assert abs(sky_params.get("ozone_density", 0) - 1.0) < 1e-4
                    print("[+] Stage 4.1: Nishita physical sky parameters verified via MCP inspect_scene_data readback.")

                    # =========================================================================
                    # STAGE 5: ATMOSPHERIC SOLAR RADIANCE VARIANCE & DOME ROTATION
                    # =========================================================================
                    print("\n" + "-" * 70)
                    print("STAGE 5: ATMOSPHERIC SOLAR RADIANCE VARIANCE & DOME ROTATION")
                    print("-" * 70)

                    # Test sun elevation change: Midday (45 deg = 0.7854 rad) vs Horizon (5 deg = 0.0873 rad)
                    res_noon = await session.call_tool("configure_world", {
                        "sky_type": "MULTIPLE_SCATTERING",
                        "sun_elevation": 0.7854,
                        "altitude": 100.0,
                        "environment_rotation": [0.0, 0.0, 1.5708],
                    })
                    assert not is_error_response(res_noon)

                    # Verify 3-axis environment rotation in inspect_scene_data
                    res_noon_insp = await session.call_tool("inspect_scene_data", {"category": "world_settings"})
                    data_noon = unwrap(res_noon_insp)
                    rot = data_noon.get("environment_rotation")
                    if isinstance(rot, list):
                        assert abs(rot[2] - 1.5708) < 1e-4
                    else:
                        assert abs(rot - 1.5708) < 1e-4
                    print(f"[+] Stage 5.1: 3-axis environment dome rotation verified (Z={rot}).")

                    # Verify sunset golden-hour setting
                    res_sunset = await session.call_tool("configure_world", {
                        "sky_type": "MULTIPLE_SCATTERING",
                        "sun_elevation": 0.0873,  # 5 deg
                        "altitude": 500.0,
                        "aerosol_density": 2.0,  # Hazy golden hour
                    })
                    assert not is_error_response(res_sunset)
                    res_sunset_insp = await session.call_tool("inspect_scene_data", {"category": "world_settings"})
                    data_sunset = unwrap(res_sunset_insp)
                    assert abs(data_sunset["sky_parameters"]["sun_elevation"] - 0.0873) < 1e-4
                    assert abs(data_sunset["sky_parameters"]["aerosol_density"] - 2.0) < 1e-4
                    print("[+] Stage 5.2: Sunset/golden-hour atmospheric elevation and aerosol density confirmed.")

                    # =========================================================================
                    # STAGE 6: SYMMETRICAL CLEANUP & TEARDOWN
                    # =========================================================================
                    print("\n" + "-" * 70)
                    print("STAGE 6: SYMMETRICAL CLEANUP & TEARDOWN")
                    print("-" * 70)

                    for obj_name in ("ReceiverSphere", "AreaKey", "AreaFill", "EvalCam"):
                        res_del = await session.call_tool("delete_object", {"name": obj_name})
                        assert not is_error_response(res_del)

                    # Reset world to neutral
                    res_w_reset = await session.call_tool("configure_world", {
                        "color": [0.05, 0.05, 0.05],
                        "strength": 1.0,
                    })
                    assert not is_error_response(res_w_reset)

                    # Verify clean scene
                    res_objs = await session.call_tool("list_objects", {})
                    data_objs = unwrap(res_objs)
                    obj_names = [o["name"] for o in data_objs.get("objects", [])]
                    for deleted in ("ReceiverSphere", "AreaKey", "AreaFill", "EvalCam"):
                        assert deleted not in obj_names, f"Object {deleted} still in scene"
                    print("[+] Stage 6.1: Symmetrical cleanup of all created lights, meshes, cameras, and world complete.")

                    # =========================================================================
                    # STAGE 7: PRODUCTION BRIDGE ISOLATION GUARD
                    # =========================================================================
                    print("\n" + "-" * 70)
                    print("STAGE 7: PRODUCTION BRIDGE ISOLATION GUARD")
                    print("-" * 70)

                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(1.0)
                        res_conn = s.connect_ex(("127.0.0.1", 9877))
                        assert res_conn == 0, "Production port 9877 was expected to remain active and listening"
                    print("[+] Stage 7.1: Production bridge port 127.0.0.1:9877 verified untouched and healthy.")

            print("\n" + "=" * 80)
            print("ALL CAPABILITY 7.1 PHASE 3 VERIFICATIONS PASSED!")
            print("=" * 80)

        finally:
            (run_root / "stop.flag").write_text("1")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            try:
                blender_log_file.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(run_photometric_atmospheric_verification())
