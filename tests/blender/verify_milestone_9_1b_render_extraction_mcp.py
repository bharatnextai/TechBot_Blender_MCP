"""
Behavioral Verification Script for Capability 9 — Milestone 9.1B:
Cryptomatte V2 Render-Extraction & Pixel Evaluation in Blender 5.2.2 LTS.

Executes over standard MCP wire protocol on disposable Blender 5.2.2 LTS with ephemeral port (!= 9877).

Test Matrix:
1. Scene Setup: Distinguishable Cube_Red (left) and Sphere_Blue (right) with Mat_Red and Mat_Blue.
2. Cycles Engine & Cryptomatte metadata generation (use_pass_cryptomatte_object, use_pass_cryptomatte_material).
3. Beauty Render Execution: cap9_cryptomatte_beauty.png.
4. Object Cryptomatte Render-Extraction:
   - layer_name="CryptoObject", matte_id="Cube_Red".
   - Output: cap9_cryptomatte_object_cube.png.
   - Pixel Analysis: Confirms left half > 1000 white pixels, right half == 0 white pixels.
5. Material Cryptomatte Render-Extraction:
   - layer_name="CryptoMaterial", matte_id="Mat_Blue".
   - Output: cap9_cryptomatte_material_blue.png.
   - Pixel Analysis: Confirms left half == 0 white pixels, right half > 1000 white pixels.
6. Multi-Target Combined Extraction:
   - layer_name="CryptoObject", matte_id="Cube_Red,Sphere_Blue".
   - Output: cap9_cryptomatte_combined_both.png.
   - Pixel Analysis: Confirms both halves contain non-zero white pixels.
7. Non-matching Selection:
   - matte_id="NonExistentTarget".
   - Output: cap9_cryptomatte_empty_mismatch.png.
   - Pixel Analysis: Confirms total white pixels == 0.
8. Fail-closed rejection of invalid layers, sources, and untrusted approvals.
"""

import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON_EXE = Path(sys.executable)
EVIDENCE_DIR = PROJECT / "docs" / "verification" / "evidence" / "cap9_cryptomatte"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

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

# Setup base scene
scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

# Clear default objects
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

queue = MainThreadQueue(bpy)
server = BridgeServer(port=port, queue=queue)
server.start()

(root / "blender_ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "blender": bpy.app.version_string,
}))

deadline = time.monotonic() + 180

try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        queue.drain_queue()
        time.sleep(0.01)
finally:
    server.stop()
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        if port == 9877:
            return find_free_port()
        return port


def inspect_image_pixels(img_path: Path) -> Dict[str, Any]:
    """Inspects pixel statistics of a rendered PNG matte via Blender background subprocess."""
    script = f"""
import bpy
img = bpy.data.images.load(r'{str(img_path)}')
w, h = img.size[0], img.size[1]
px = list(img.pixels) # RGBA floats 0.0 to 1.0
left_white = 0
right_white = 0
total_white = 0
vals = []
for y in range(h):
    for x in range(w):
        idx = (y * w + x) * 4
        v = px[idx] # R channel
        vals.append(v)
        if v > 0.5:
            total_white += 1
            if x < w // 2:
                left_white += 1
            else:
                right_white += 1
import json
print('__PIXEL_EVAL_JSON__' + json.dumps({{
    'width': w,
    'height': h,
    'total_pixels': w * h,
    'total_white': total_white,
    'left_white': left_white,
    'right_white': right_white,
    'min_val': min(vals),
    'max_val': max(vals),
}}))
"""
    cmd = [str(BLENDER), "--background", "--factory-startup", "--python-expr", script]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for line in res.stdout.splitlines():
        if line.startswith("__PIXEL_EVAL_JSON__"):
            return json.loads(line.replace("__PIXEL_EVAL_JSON__", ""))
    raise RuntimeError(f"Pixel evaluation failed on {img_path}:\n{res.stdout}\n{res.stderr}")


async def run_cryptomatte_render_verification():
    print("=" * 80)
    print("CAPABILITY 9 — MILESTONE 9.1B: CRYPTOMATTE RENDER-EXTRACTION VERIFICATION")
    print("Target: Blender 5.2.2 LTS (Cycles Render-Extraction)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CRYPTO-EXTRACT-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Guard violation: ephemeral port matched production {port}"

    ready_file = run_root / "blender_ready.json"
    script_file = run_root / "bootstrap.py"
    script_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_SCOPE"] = "compositor_v1"
    env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    env["BLENDER_USER_CONFIG"] = str(config_dir)
    env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
    env["PYTHONPATH"] = str(PROJECT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    print(f"[*] Spawning disposable Blender 5.2.2 on ephemeral port {port}...")
    proc = subprocess.Popen(
        [
            str(BLENDER),
            "--background",
            "--factory-startup",
            "--python",
            str(script_file),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(run_root),
        text=True,
    )

    try:
        t0 = time.monotonic()
        while not ready_file.exists():
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                raise RuntimeError(f"Blender terminated early. Exit: {proc.returncode}\nOut: {stdout}\nErr: {stderr}")
            if time.monotonic() - t0 > 30:
                raise TimeoutError("Blender disposable instance did not start in 30s")
            time.sleep(0.1)

        ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
        print(f"[+] Disposable Blender ready! PID: {ready_data['pid']}, Version: {ready_data['blender']}")

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
            ],
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": str(PROJECT),
                "PYTHONDONTWRITEBYTECODE": "1",
                "UMCP_BRIDGE_HOST": "127.0.0.1",
                "UMCP_BRIDGE_PORT": str(port),
                "UMCP_LOCAL_TEST_AUTOAPPROVE": "1",
                "UMCP_LOCAL_TEST_SCOPE": "compositor_v1",
                "UMCP_LOCAL_TEST_ROOT": str(run_root),
            },
        )

        print("[*] Connecting Stdio MCP client to server...")
        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.")

                async def call_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                    res = await session.call_tool(tool_name, arguments=args)
                    if hasattr(res, "content"):
                        for block in res.content:
                            text = getattr(block, "text", "")
                            if text:
                                try:
                                    return json.loads(text)
                                except Exception:
                                    return {"text": text}
                    return {"result": str(res)}

                # STAGE 1: Minimal Scene Setup (Cube_Red on left, Sphere_Blue on right)
                print("\n[*] STAGE 1: Creating distinguishable 3D scene (Cube_Red left, Sphere_Blue right)...")

                # Cube on left
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "Cube_Red",
                    "location": [-1.5, 0.0, 0.0],
                })
                assert cube_res.get("result", cube_res).get("name") == "Cube_Red"

                mat_red_res = await call_tool("create_material", {
                    "name": "Mat_Red",
                    "base_color": [0.85, 0.05, 0.05, 1.0],
                })
                assert mat_red_res.get("result", mat_red_res).get("name") == "Mat_Red"

                assign_red = await call_tool("assign_material", {
                    "target_name": "Cube_Red",
                    "material_name": "Mat_Red",
                })
                assert assign_red.get("status") == "success"

                # Sphere on right
                sphere_res = await call_tool("create_primitive", {
                    "primitive_type": "sphere",
                    "name": "Sphere_Blue",
                    "location": [1.5, 0.0, 0.0],
                    "radius": 0.75,
                })
                assert sphere_res.get("result", sphere_res).get("name") == "Sphere_Blue"

                mat_blue_res = await call_tool("create_material", {
                    "name": "Mat_Blue",
                    "base_color": [0.05, 0.05, 0.85, 1.0],
                })
                assert mat_blue_res.get("result", mat_blue_res).get("name") == "Mat_Blue"

                assign_blue = await call_tool("assign_material", {
                    "target_name": "Sphere_Blue",
                    "material_name": "Mat_Blue",
                })
                assert assign_blue.get("status") == "success"

                # Camera framing both
                cam_res = await call_tool("create_camera", {
                    "name": "Cam_Main",
                    "location": [0.0, -6.0, 0.0],
                    "rotation_euler": [1.5708, 0.0, 0.0],
                    "set_active": True,
                })
                assert cam_res.get("result", cam_res).get("name") == "Cam_Main"

                # Lighting
                light_res = await call_tool("create_light", {
                    "name": "Light_Area",
                    "light_type": "AREA",
                    "energy": 500.0,
                    "location": [0.0, -3.0, 5.0],
                })
                assert light_res.get("result", light_res).get("name") == "Light_Area"

                # Configure Render Settings to CYCLES
                render_cfg = await call_tool("configure_render_settings", {
                    "engine": "CYCLES",
                    "cycles_samples": 8,
                    "resolution_x": 320,
                    "resolution_y": 240,
                })
                assert render_cfg.get("status") == "success"
                assert render_cfg.get("result", {}).get("engine") == "CYCLES"
                print("[+] Stage 1 PASSED: Scene setup complete with Cube_Red, Sphere_Blue, Camera, Light, and CYCLES engine.")

                # STAGE 2: Enable Compositor & Cryptomatte Render Passes
                print("\n[*] STAGE 2: Enabling compositor & Cryptomatte passes...")
                await call_tool("manage_compositor_nodes", {"action": "enable"})

                pass_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {
                        "cryptomatte_object": True,
                        "cryptomatte_material": True,
                    }
                })
                pass_data = pass_res.get("result", pass_res)
                assert pass_data.get("active_passes", {}).get("use_pass_cryptomatte_object") is True
                assert pass_data.get("active_passes", {}).get("use_pass_cryptomatte_material") is True
                print("[+] Stage 2 PASSED: Cryptomatte Object and Material pass metadata enabled on ViewLayer.")

                # STAGE 3: Render Beauty Pass (Baseline Image)
                beauty_tmp = run_root / "cap9_cryptomatte_beauty.png"
                beauty_path = EVIDENCE_DIR / "cap9_cryptomatte_beauty.png"
                print(f"\n[*] STAGE 3: Rendering beauty pass to {beauty_path.name}...")
                beauty_render = await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(beauty_tmp),
                    "output_format": "PNG",
                })
                assert beauty_tmp.exists(), f"Beauty image not created at {beauty_tmp} (render response: {beauty_render})"
                shutil.copy2(beauty_tmp, beauty_path)
                b_size = beauty_path.stat().st_size
                assert b_size > 5000, f"Beauty file size too small: {b_size}"
                print(f"[+] Stage 3 PASSED: Beauty render complete ({b_size} bytes).")

                # STAGE 4: Assemble Cryptomatte Pipeline in Compositor Graph
                print("\n[*] STAGE 4: Assembling Cryptomatte extraction node graph...")
                crypto_node = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "cryptomatte",
                    "node_name": "Hero_Cryptomatte",
                    "location": [300.0, 200.0],
                })
                assert crypto_node.get("result", crypto_node).get("node_name") == "Hero_Cryptomatte"

                # Link: Render Layers.Image -> Hero_Cryptomatte.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Hero_Cryptomatte",
                    "to_socket": "Image",
                })

                # Link: Hero_Cryptomatte.Matte -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Hero_Cryptomatte",
                    "from_socket": "matte",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })
                print("[+] Stage 4 PASSED: Pipeline linked: Render Layers.Image -> Hero_Cryptomatte.Matte -> Group Output.Image.")

                # STAGE 5: Object Cryptomatte Render-Extraction (Target: Cube_Red)
                obj_matte_tmp = run_root / "cap9_cryptomatte_object_cube.png"
                obj_matte_path = EVIDENCE_DIR / "cap9_cryptomatte_object_cube.png"
                print(f"\n[*] STAGE 5: Extracting Object Cryptomatte matte for 'Cube_Red' to {obj_matte_path.name}...")
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "layer_name",
                    "property_value": "object",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "matte_id",
                    "property_value": "Cube_Red",
                })

                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(obj_matte_tmp),
                    "output_format": "PNG",
                })
                assert obj_matte_tmp.exists()
                shutil.copy2(obj_matte_tmp, obj_matte_path)
                obj_eval = inspect_image_pixels(obj_matte_path)
                print(f"    [Pixel Eval Object Matte]: total_white={obj_eval['total_white']}, left_white={obj_eval['left_white']}, right_white={obj_eval['right_white']}, max={obj_eval['max_val']}, min={obj_eval['min_val']}")
                assert obj_eval["total_white"] > 1000, "Cube_Red matte must contain non-zero white pixels"
                assert obj_eval["left_white"] > 1000, "Cube_Red (on left) must have white pixels on left half"
                assert obj_eval["right_white"] == 0, "Right half (Sphere_Blue) MUST have 0 white pixels in Cube_Red matte"
                assert obj_eval["max_val"] > 0.7, f"Matte foreground peak must exceed 0.7 (AgX mapping), got {obj_eval['max_val']}"
                assert obj_eval["min_val"] == 0.0, "Matte background floor must equal 0.0"
                print(f"[+] Stage 5 PASSED: Object Cryptomatte cleanly isolates Cube_Red (left={obj_eval['left_white']}, right={obj_eval['right_white']}).")

                # STAGE 6: Material Cryptomatte Render-Extraction (Target: Mat_Blue on Sphere_Blue)
                mat_matte_tmp = run_root / "cap9_cryptomatte_material_blue.png"
                mat_matte_path = EVIDENCE_DIR / "cap9_cryptomatte_material_blue.png"
                print(f"\n[*] STAGE 6: Extracting Material Cryptomatte matte for 'Mat_Blue' to {mat_matte_path.name}...")
                p_layer = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "layer_name",
                    "property_value": "material",
                })
                assert p_layer.get("status") == "success"
                p_matte = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "matte_id",
                    "property_value": "Mat_Blue",
                })
                assert p_matte.get("status") == "success"

                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(mat_matte_tmp),
                    "output_format": "PNG",
                })
                assert mat_matte_tmp.exists()
                shutil.copy2(mat_matte_tmp, mat_matte_path)
                mat_eval = inspect_image_pixels(mat_matte_path)
                print(f"    [Pixel Eval Material Matte]: total_white={mat_eval['total_white']}, left_white={mat_eval['left_white']}, right_white={mat_eval['right_white']}, max={mat_eval['max_val']}, min={mat_eval['min_val']}")
                assert mat_eval["total_white"] > 1000, "Mat_Blue matte must contain non-zero white pixels"
                assert mat_eval["left_white"] == 0, "Left half (Cube_Red with Mat_Red) MUST have 0 white pixels in Mat_Blue matte"
                assert mat_eval["right_white"] > 1000, "Right half (Sphere_Blue with Mat_Blue) must have white pixels"
                assert mat_eval["max_val"] > 0.7, f"Matte foreground peak must exceed 0.7 (AgX mapping), got {mat_eval['max_val']}"
                assert mat_eval["min_val"] == 0.0
                print(f"[+] Stage 6 PASSED: Material Cryptomatte cleanly isolates Mat_Blue (left={mat_eval['left_white']}, right={mat_eval['right_white']}).")

                # STAGE 7: Multi-Target Combined Extraction (Cube_Red,Sphere_Blue)
                both_matte_tmp = run_root / "cap9_cryptomatte_combined_both.png"
                both_matte_path = EVIDENCE_DIR / "cap9_cryptomatte_combined_both.png"
                print(f"\n[*] STAGE 7: Extracting combined matte for 'Cube_Red,Sphere_Blue' to {both_matte_path.name}...")
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "layer_name",
                    "property_value": "object",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "matte_id",
                    "property_value": "Cube_Red,Sphere_Blue",
                })

                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(both_matte_tmp),
                    "output_format": "PNG",
                })
                assert both_matte_tmp.exists()
                shutil.copy2(both_matte_tmp, both_matte_path)
                both_eval = inspect_image_pixels(both_matte_path)
                print(f"    [Pixel Eval Combined Matte]: total_white={both_eval['total_white']}, left_white={both_eval['left_white']}, right_white={both_eval['right_white']}")
                assert both_eval["left_white"] > 1000, "Both targets must include Cube_Red on left"
                assert both_eval["right_white"] > 1000, "Both targets must include Sphere_Blue on right"
                assert both_eval["total_white"] > 14000, "Combined matte must cover both objects"
                print("[+] Stage 7 PASSED: Combined Cryptomatte matte successfully covers both objects.")

                # STAGE 8: Non-matching Target Extraction (Empty Matte)
                empty_matte_tmp = run_root / "cap9_cryptomatte_empty_mismatch.png"
                empty_matte_path = EVIDENCE_DIR / "cap9_cryptomatte_empty_mismatch.png"
                print(f"\n[*] STAGE 8: Extracting matte for non-matching target 'NonExistentObject'...")
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "matte_id",
                    "property_value": "NonExistentObject",
                })

                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(empty_matte_tmp),
                    "output_format": "PNG",
                })
                assert empty_matte_tmp.exists()
                shutil.copy2(empty_matte_tmp, empty_matte_path)
                empty_eval = inspect_image_pixels(empty_matte_path)
                print(f"    [Pixel Eval Empty Matte]: total_white={empty_eval['total_white']}, max_val={empty_eval['max_val']}")
                assert empty_eval["total_white"] == 0, f"Non-matching target must yield 0 white pixels, got {empty_eval['total_white']}"
                assert empty_eval["max_val"] < 0.01, f"Max value must be below 0.01 (zero floor), got {empty_eval['max_val']}"
                print("[+] Stage 8 PASSED: Non-matching target yields completely zero/black matte.")

                # STAGE 9: Fail-Closed Concurrency and Parameter Validation
                print("\n[*] STAGE 9: Validating fail-closed bounds and concurrency...")
                # Stale snapshot
                stale_res = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "matte_id",
                    "property_value": "Cube_Red",
                    "expected_snapshot_id": "sha256:stale_fake_hash_12345",
                })
                assert "stale_compositor_graph" in str(stale_res).lower()

                # Invalid layer
                bad_layer = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "layer_name",
                    "property_value": "lights",
                })
                assert "invalid cryptomatte layer" in str(bad_layer).lower() or "error" in str(bad_layer).lower()

                # Untrusted approval
                untrusted = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Hero_Cryptomatte",
                    "property_name": "matte_id",
                    "property_value": "Hacked",
                    "approved": True,
                })
                assert "approval denied" in str(untrusted).lower() or "permission" in str(untrusted).lower() or "error" in str(untrusted).lower()
                print("[+] Stage 9 PASSED: Concurrency, invalid property, and untrusted approval rejected fail-closed.")

                # Save verification telemetry
                telemetry = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "target_blender": ready_data["blender"],
                    "port": port,
                    "artifacts": {
                        "beauty": {"path": str(beauty_path), "size": b_size},
                        "object_cube": {"path": str(obj_matte_path), "eval": obj_eval},
                        "material_blue": {"path": str(mat_matte_path), "eval": mat_eval},
                        "combined_both": {"path": str(both_matte_path), "eval": both_eval},
                        "empty_mismatch": {"path": str(empty_matte_path), "eval": empty_eval},
                    },
                    "status": "ALL_STAGES_PASSED",
                }
                (EVIDENCE_DIR / "cryptomatte_extraction_telemetry.json").write_text(json.dumps(telemetry, indent=2))
                print(f"[+] Evidence and telemetry saved to {EVIDENCE_DIR}")

                print("\n" + "=" * 80)
                print("ALL 9 STAGES OF CRYPTOMATTE RENDER-EXTRACTION PASSED CLEANLY ON BLENDER 5.2.2 LTS!")
                print("=" * 80)

    finally:
        print("\n[*] Cleaning up disposable Blender sandbox...")
        (run_root / "stop.flag").touch()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        print("[+] Disposable process cleaned up cleanly.")


if __name__ == "__main__":
    asyncio.run(run_cryptomatte_render_verification())
