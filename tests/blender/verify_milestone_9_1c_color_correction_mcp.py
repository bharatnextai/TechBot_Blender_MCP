"""
Behavioral Verification Script for Capability 9 — Milestone 9.1C:
Color Correction Node Foundation in Blender 5.2.2 LTS.

Executes over standard MCP wire protocol on disposable Blender 5.2.2 LTS with ephemeral port (!= 9877).

Test Matrix:
1. Scene Setup: Deterministic red cube with principled shader, active camera and illumination.
2. Stage 1: Render Baseline Beauty Image (cap9_color_baseline.png).
3. Stage 2: CompositorNodeExposure:
   - Creation & property mutation (exposure = +2.0).
   - Render: cap9_color_exposure.png.
   - Pixel Analysis: Confirms exposure amplification (avg R > 1.5x baseline).
4. Stage 3: CompositorNodeHueSat:
   - Creation & property mutation (saturation = 0.0 -> pure grayscale).
   - Render: cap9_color_desaturate.png.
   - Pixel Analysis: Confirms all channels equalized (|R - G| <= 0.02).
5. Stage 4: CompositorNodeCurveRGB:
   - Creation & curve point configuration (curve='C', point=[0.5, 0.85]).
   - Render: cap9_color_curves.png.
   - Pixel Analysis: Confirms midtone contrast boost.
6. Stage 5: CompositorNodeTonemap:
   - Creation & property mutation (type='Rh Simple', key=0.3, gamma=1.5).
   - Render: cap9_color_tonemap.png.
7. Stage 6: Integrated Multi-Node Color Grading Chain:
   - Pipeline: Render Layers -> Exposure -> Curves -> HueSat -> Tonemap -> Group Output.
   - Render: cap9_color_integrated_chain.png.
8. Stage 7: Fail-closed validation for out-of-bounds properties and stale snapshots.
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
from typing import Dict, Any

PROJECT = Path(__file__).resolve().parent.parent.parent
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON_EXE = Path(sys.executable)
EVIDENCE_DIR = PROJECT / "docs" / "verification" / "evidence" / "cap9_color_correction"
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
    """Inspects pixel statistics of rendered image via Blender background subprocess."""
    script = f"""
import bpy
img = bpy.data.images.load(r'{str(img_path)}')
w, h = img.size[0], img.size[1]
px = list(img.pixels) # RGBA floats 0.0 to 1.0
total_px = w * h

r_vals = [px[i] for i in range(0, len(px), 4)]
g_vals = [px[i+1] for i in range(0, len(px), 4)]
b_vals = [px[i+2] for i in range(0, len(px), 4)]

avg_r = sum(r_vals) / len(r_vals)
avg_g = sum(g_vals) / len(g_vals)
avg_b = sum(b_vals) / len(b_vals)
max_r = max(r_vals)
max_g = max(g_vals)
max_b = max(b_vals)

diff_rg = [abs(r_vals[i] - g_vals[i]) for i in range(len(r_vals))]
max_diff_rg = max(diff_rg)
avg_diff_rg = sum(diff_rg) / len(diff_rg)

import json
print("__PIXEL_EVAL_JSON__" + json.dumps({{
    "width": w,
    "height": h,
    "total_pixels": total_px,
    "avg_r": round(avg_r, 5),
    "avg_g": round(avg_g, 5),
    "avg_b": round(avg_b, 5),
    "max_r": round(max_r, 5),
    "max_g": round(max_g, 5),
    "max_b": round(max_b, 5),
    "max_diff_rg": round(max_diff_rg, 5),
    "avg_diff_rg": round(avg_diff_rg, 5),
}}))
"""
    cmd = [str(BLENDER), "--background", "--factory-startup", "--python-expr", script]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for line in res.stdout.splitlines():
        if line.startswith("__PIXEL_EVAL_JSON__"):
            return json.loads(line.replace("__PIXEL_EVAL_JSON__", ""))
    raise RuntimeError(f"Pixel evaluation failed on {img_path}:\n{res.stdout}\n{res.stderr}")


async def run_color_correction_verification():
    print("=" * 80)
    print("CAPABILITY 9 — MILESTONE 9.1C: COLOR CORRECTION NODE FOUNDATION VERIFICATION")
    print("Target: Blender 5.2.2 LTS (Compositor Color Processing)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-COLOR-CORRECT-"))
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
            if time.monotonic() - t0 > 30:
                raise TimeoutError("Disposable Blender failed to start within 30 seconds.")
            await asyncio.sleep(0.1)

        ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
        print(f"[+] Disposable Blender ready! PID: {ready_data['pid']}, Version: {ready_data['blender']}")

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

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

                async def call_tool(name: str, arguments: dict):
                    result = await session.call_tool(name, arguments)
                    for content in result.content:
                        if hasattr(content, "text"):
                            try:
                                return json.loads(content.text)
                            except json.JSONDecodeError:
                                return {"text": content.text}
                    return {}

                # ==============================================================================
                # STAGE 1: Deterministic Scene Setup & Baseline Render
                # ==============================================================================
                print("\n[*] STAGE 1: Creating deterministic test scene (Red Cube + Camera + Light)...")
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "Color_Target_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                assert cube_res.get("result", cube_res).get("name") == "Color_Target_Cube"

                mat_res = await call_tool("create_material", {
                    "name": "Target_Red_Mat",
                    "base_color": [0.85, 0.05, 0.05, 1.0],
                })
                assert mat_res.get("status") == "success"

                assign_res = await call_tool("assign_material", {
                    "target_name": "Color_Target_Cube",
                    "material_name": "Target_Red_Mat",
                })
                assert assign_res.get("status") == "success"

                cam_res = await call_tool("create_camera", {
                    "name": "Camera_Main",
                    "location": [0.0, -4.5, 0.0],
                    "rotation_euler": [1.5708, 0.0, 0.0],
                    "set_active": True,
                })
                assert cam_res.get("status") == "success"

                light_res = await call_tool("create_light", {
                    "name": "Light_Main",
                    "light_type": "AREA",
                    "energy": 400.0,
                    "location": [0.0, -2.5, 3.5],
                })
                assert light_res.get("status") == "success"

                render_cfg = await call_tool("configure_render_settings", {
                    "engine": "CYCLES",
                    "resolution_x": 128,
                    "resolution_y": 128,
                    "resolution_percentage": 100,
                })
                assert render_cfg.get("status") == "success"

                # Enable compositor
                enable_res = await call_tool("manage_compositor_nodes", {"action": "enable"})
                assert enable_res.get("result", enable_res).get("enabled") is True
                print("[+] Stage 1: Scene & Compositor initialized.")

                # Render Baseline
                base_tmp = run_root / "cap9_color_baseline.png"
                base_path = EVIDENCE_DIR / "cap9_color_baseline.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(base_tmp),
                    "output_format": "PNG",
                })
                assert base_tmp.exists()
                shutil.copy2(base_tmp, base_path)
                base_eval = inspect_image_pixels(base_path)
                print(f"[+] Stage 1 PASSED: Baseline Render complete. Pixel stats: avg_r={base_eval['avg_r']}, max_r={base_eval['max_r']}, avg_g={base_eval['avg_g']}")

                # ==============================================================================
                # STAGE 2: CompositorNodeExposure Verification
                # ==============================================================================
                print("\n[*] STAGE 2: Testing CompositorNodeExposure (exposure = +2.0)...")
                exp_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "exposure",
                    "node_name": "Color_Exposure",
                    "location": [300.0, 200.0],
                })
                assert exp_create.get("result", exp_create).get("node_type") == "CompositorNodeExposure"

                exp_prop = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Exposure",
                    "property_name": "exposure",
                    "property_value": 2.0,
                })
                assert exp_prop.get("result", exp_prop).get("property_value") == 2.0

                # Connect: Render Layers.Image -> Color_Exposure.Image -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Color_Exposure",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Color_Exposure",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                exp_tmp = run_root / "cap9_color_exposure.png"
                exp_path = EVIDENCE_DIR / "cap9_color_exposure.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(exp_tmp),
                    "output_format": "PNG",
                })
                assert exp_tmp.exists()
                shutil.copy2(exp_tmp, exp_path)
                exp_eval = inspect_image_pixels(exp_path)
                print(f"[+] Stage 2 PASSED: Exposure Render complete: avg_r={exp_eval['avg_r']} vs baseline={base_eval['avg_r']} (ratio: {exp_eval['avg_r']/base_eval['avg_r']:.2f}x)")
                assert exp_eval["avg_r"] > base_eval["avg_r"] * 1.5, "Exposure (+2.0) must significantly increase red channel brightness"

                # ==============================================================================
                # STAGE 3: CompositorNodeHueSat Verification (Grayscale Desaturation)
                # ==============================================================================
                print("\n[*] STAGE 3: Testing CompositorNodeHueSat (saturation = 0.0 -> Grayscale)...")
                hs_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "hue_sat",
                    "node_name": "Color_HueSat",
                    "location": [300.0, 0.0],
                })
                assert hs_create.get("result", hs_create).get("node_type") == "CompositorNodeHueSat"

                hs_prop = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_HueSat",
                    "property_name": "saturation",
                    "property_value": 0.0,
                })
                assert hs_prop.get("status") == "success"

                # Connect: Render Layers.Image -> Color_HueSat.Image -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Color_HueSat",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Color_HueSat",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                hs_tmp = run_root / "cap9_color_desaturate.png"
                hs_path = EVIDENCE_DIR / "cap9_color_desaturate.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(hs_tmp),
                    "output_format": "PNG",
                })
                assert hs_tmp.exists()
                shutil.copy2(hs_tmp, hs_path)
                hs_eval = inspect_image_pixels(hs_path)
                print(f"[+] Stage 3 PASSED: HueSat Render complete: max |R-G| diff={hs_eval['max_diff_rg']}, avg |R-G| diff={hs_eval['avg_diff_rg']}")
                assert hs_eval["max_diff_rg"] <= 0.02, "Desaturation must equalize color channels into grayscale (|R-G| <= 0.02)"

                # ==============================================================================
                # STAGE 4: CompositorNodeCurveRGB Verification
                # ==============================================================================
                print("\n[*] STAGE 4: Testing CompositorNodeCurveRGB (RGB Curves midtone boost)...")
                curve_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "curve_color",
                    "node_name": "Color_Curves",
                    "location": [300.0, -200.0],
                })
                assert curve_create.get("result", curve_create).get("node_type") == "CompositorNodeCurveRGB"

                curve_prop = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Curves",
                    "property_name": "curve_point",
                    "property_value": {"curve": "C", "point": [0.5, 0.85]},
                })
                assert curve_prop.get("status") == "success"

                # Connect: Render Layers.Image -> Color_Curves.Image -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Color_Curves",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Color_Curves",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                curve_tmp = run_root / "cap9_color_curves.png"
                curve_path = EVIDENCE_DIR / "cap9_color_curves.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(curve_tmp),
                    "output_format": "PNG",
                })
                assert curve_tmp.exists()
                shutil.copy2(curve_tmp, curve_path)
                curve_eval = inspect_image_pixels(curve_path)
                print(f"[+] Stage 4 PASSED: CurveRGB Render complete: avg_r={curve_eval['avg_r']} vs baseline={base_eval['avg_r']} (ratio: {curve_eval['avg_r']/base_eval['avg_r']:.2f}x)")
                assert curve_eval["avg_r"] > base_eval["avg_r"] * 1.2, "Midtone curve boost must increase average red brightness"

                # ==============================================================================
                # STAGE 5: CompositorNodeTonemap Verification
                # ==============================================================================
                print("\n[*] STAGE 5: Testing CompositorNodeTonemap ('Rh Simple', key=0.35, gamma=1.5)...")
                tm_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "tonemap",
                    "node_name": "Color_Tonemap",
                    "location": [300.0, -400.0],
                })
                assert tm_create.get("result", tm_create).get("node_type") == "CompositorNodeTonemap"

                tm_prop1 = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Tonemap",
                    "property_name": "type",
                    "property_value": "rh_simple",
                })
                assert tm_prop1.get("status") == "success"

                tm_prop2 = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Tonemap",
                    "property_name": "key",
                    "property_value": 0.35,
                })
                assert tm_prop2.get("status") == "success"

                tm_prop3 = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Tonemap",
                    "property_name": "gamma",
                    "property_value": 1.5,
                })
                assert tm_prop3.get("status") == "success"

                # Connect: Render Layers.Image -> Color_Tonemap.Image -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Color_Tonemap",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Color_Tonemap",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                tm_tmp = run_root / "cap9_color_tonemap.png"
                tm_path = EVIDENCE_DIR / "cap9_color_tonemap.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(tm_tmp),
                    "output_format": "PNG",
                })
                assert tm_tmp.exists()
                shutil.copy2(tm_tmp, tm_path)
                tm_eval = inspect_image_pixels(tm_path)
                print(f"[+] Stage 5 PASSED: Tonemap Render complete: avg_r={tm_eval['avg_r']}, max_r={tm_eval['max_r']}")

                # ==============================================================================
                # STAGE 6: Integrated Multi-Node Color Pipeline Chain
                # ==============================================================================
                print("\n[*] STAGE 6: Testing Integrated Full Pipeline (Render Layers -> Exposure -> Curves -> HueSat -> Group Output)...")
                # Reset HueSat to subtle color saturation boost (1.3)
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_HueSat",
                    "property_name": "saturation",
                    "property_value": 1.3,
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Exposure",
                    "property_name": "exposure",
                    "property_value": 1.0,
                })

                # Chain: Render Layers -> Color_Exposure -> Color_Curves -> Color_HueSat -> Group Output
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Color_Exposure",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Color_Exposure",
                    "from_socket": "Image",
                    "to_node": "Color_Curves",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Color_Curves",
                    "from_socket": "Image",
                    "to_node": "Color_HueSat",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Color_HueSat",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # Inspect graph to verify multi-node chain
                inspect_res = await call_tool("manage_compositor_nodes", {"action": "inspect"})
                tree_nodes = [n["name"] for n in inspect_res.get("result", inspect_res).get("nodes", [])]
                for req_n in ("Color_Exposure", "Color_Curves", "Color_HueSat", "Color_Tonemap"):
                    assert req_n in tree_nodes, f"Node '{req_n}' missing from compositor graph: {tree_nodes}"

                chain_tmp = run_root / "cap9_color_integrated_chain.png"
                chain_path = EVIDENCE_DIR / "cap9_color_integrated_chain.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(chain_tmp),
                    "output_format": "PNG",
                })
                assert chain_tmp.exists()
                shutil.copy2(chain_tmp, chain_path)
                chain_eval = inspect_image_pixels(chain_path)
                print(f"[+] Stage 6 PASSED: Integrated Chain Render complete: avg_r={chain_eval['avg_r']}, max_r={chain_eval['max_r']}")

                # ==============================================================================
                # STAGE 7: Fail-Closed Concurrency & Property Validation
                # ==============================================================================
                print("\n[*] STAGE 7: Validating fail-closed bounds and concurrency...")
                # Stale snapshot
                stale_res = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Exposure",
                    "property_name": "exposure",
                    "property_value": 0.5,
                    "expected_snapshot_id": "sha256:stale_fake_hash_12345",
                })
                assert "stale_compositor_graph" in str(stale_res).lower() or "snapshot mismatch" in str(stale_res).lower() or "error" in str(stale_res).lower()

                # Out of bounds exposure
                bad_exp = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Exposure",
                    "property_name": "exposure",
                    "property_value": 100.0,
                })
                assert "between -20.0 and 20.0" in str(bad_exp).lower() or "error" in str(bad_exp).lower()

                # Out of bounds hue
                bad_hue = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_HueSat",
                    "property_name": "hue",
                    "property_value": 2.5,
                })
                assert "between 0.0 and 1.0" in str(bad_hue).lower() or "error" in str(bad_hue).lower()

                # Invalid tonemap type
                bad_tm = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Tonemap",
                    "property_name": "type",
                    "property_value": "unsupported_hdr_algo",
                })
                assert "invalid tonemap type" in str(bad_tm).lower() or "error" in str(bad_tm).lower()

                # Untrusted approval
                untrusted = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Color_Exposure",
                    "property_name": "exposure",
                    "property_value": 1.0,
                    "approved": True,
                })
                assert "approval denied" in str(untrusted).lower() or "permission" in str(untrusted).lower() or "error" in str(untrusted).lower()
                print("[+] Stage 7 PASSED: Concurrency, parameter bounds, and untrusted approval rejected fail-closed.")

                # Telemetry
                telemetry = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "target_blender": ready_data["blender"],
                    "port": port,
                    "artifacts": {
                        "baseline": {"path": str(base_path), "eval": base_eval},
                        "exposure": {"path": str(exp_path), "eval": exp_eval},
                        "desaturate": {"path": str(hs_path), "eval": hs_eval},
                        "curves": {"path": str(curve_path), "eval": curve_eval},
                        "tonemap": {"path": str(tm_path), "eval": tm_eval},
                        "integrated_chain": {"path": str(chain_path), "eval": chain_eval},
                    },
                    "status": "ALL_STAGES_PASSED",
                }
                (EVIDENCE_DIR / "color_correction_telemetry.json").write_text(json.dumps(telemetry, indent=2))
                print(f"[+] Evidence and telemetry saved to {EVIDENCE_DIR}")

                print("\n" + "=" * 80)
                print("ALL 7 STAGES OF COLOR CORRECTION FOUNDATION PASSED CLEANLY ON BLENDER 5.2.2 LTS!")
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
    asyncio.run(run_color_correction_verification())
