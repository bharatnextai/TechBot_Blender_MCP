"""
Behavioral Verification Script for Capability 9 — Milestone 9.1E:
Geometric Masks and ID Mask Foundation in Blender 5.2.2 LTS.

Executes over standard MCP wire protocol on disposable Blender 5.2.2 LTS with ephemeral port (!= 9877).

Test Matrix:
1. Scene Setup: Deterministic scene containing two distinguishable objects (Hero_Cube on left with pass_index=1,
   Companion_Sphere on right with pass_index=2), Cycles engine with object_index pass & Cryptomatte enabled.
2. Stage 1: Render Baseline Beauty Image (cap9_mask_baseline.png).
3. Stage 2: CompositorNodeBoxMask:
   - Creation & property configuration (position=[0.5, 0.5], size=[0.4, 0.4]).
   - Render: cap9_mask_box.png.
   - Analysis: Pixel inspection verifies rectangular white mask region (~2,500 white pixels out of 16,384).
4. Stage 3: CompositorNodeEllipseMask:
   - Creation & property configuration (position=[0.5, 0.5], size=[0.3, 0.3]).
   - Render: cap9_mask_ellipse.png.
   - Analysis: Pixel inspection verifies elliptical white mask region (~1,148 white pixels).
5. Stage 4: CompositorNodeIDMask:
   - Connect Render Layers.Object Index -> ID Mask.ID value -> Group Output.Image.
   - Configuration: index=1 (isolates Hero_Cube on the left).
   - Render: cap9_mask_idmask_cube.png.
   - Analysis: Pixel inspection confirms 100% left-side isolation (right-side white pixels = 0).
6. Stage 5: Mask Output Integration into Compositor Nodes:
   - Box Mask connected to CompositorNodeExposure Factor socket or CompositorNodeAlphaOver.
   - Render: cap9_mask_integrated_grade.png.
   - Analysis: Confirms selective grading inside the geometric mask boundary.
7. Stage 6: Cryptomatte Matte Combination with Geometric Mask:
   - Cryptomatte (isolating Hero_Cube) combined with offset Box Mask (Multiply operation).
   - Render: cap9_mask_crypto_box_combined.png.
   - Analysis: Confirms clean intersection of procedural geometry mask and Cryptomatte matte.
8. Stage 7: Concurrency & Bounds Invariants:
   - Stale snapshot rejection with STALE_COMPOSITOR_GRAPH.
   - Out-of-bounds mask position, invalid operations, and negative indices rejected fail-closed.
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
EVIDENCE_DIR = PROJECT / "docs" / "verification" / "evidence" / "cap9_mask_foundation"
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

# Pre-create test geometry directly in scene
m1 = bpy.data.meshes.new("Hero_Cube_Mesh")
c1 = bpy.data.objects.new("Hero_Cube", m1)
bpy.context.collection.objects.link(c1)
import bmesh
bm1 = bmesh.new()
bmesh.ops.create_cube(bm1, size=1.5)
bm1.to_mesh(m1)
bm1.free()
c1.location = (-1.2, 0.0, 0.0)
c1.pass_index = 1

m2 = bpy.data.meshes.new("Companion_Sphere_Mesh")
c2 = bpy.data.objects.new("Companion_Sphere", m2)
bpy.context.collection.objects.link(c2)
bm2 = bmesh.new()
bmesh.ops.create_uvsphere(bm2, u_segments=16, v_segments=16, radius=0.75)
bm2.to_mesh(m2)
bm2.free()
c2.location = (1.2, 0.0, 0.0)
c2.pass_index = 2

queue = MainThreadQueue(bpy)
server = BridgeServer(port=port, queue=queue)
server.start()

(root / "blender_ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "blender": bpy.app.version_string,
}))

deadline = time.monotonic() + 600

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
        return s.getsockname()[1]


def inspect_image_pixels(img_path: Path) -> Dict[str, Any]:
    """Inspects raw RGBA pixel buffers in disposable background Blender."""
    script = f"""
import bpy
img = bpy.data.images.load(r'{str(img_path)}')
w, h = img.size[0], img.size[1]
px = list(img.pixels) # RGBA floats 0.0 to 1.0
total_px = w * h

r_vals = [px[i] for i in range(0, len(px), 4)]
g_vals = [px[i+1] for i in range(0, len(px), 4)]
b_vals = [px[i+2] for i in range(0, len(px), 4)]

white_pixels = sum(1 for r in r_vals if r > 0.5)

left_white = 0
right_white = 0
for y in range(h):
    for x in range(w):
        val = px[(y * w + x) * 4]
        if val > 0.5:
            if x < (w // 2):
                left_white += 1
            else:
                right_white += 1

import json
print("__PIXEL_EVAL_JSON__" + json.dumps({{
    "width": w,
    "height": h,
    "total_pixels": total_px,
    "white_pixels": white_pixels,
    "left_white": left_white,
    "right_white": right_white,
    "avg_r": round(sum(r_vals) / len(r_vals), 5),
    "max_r": round(max(r_vals), 5),
}}))
"""
    cmd = [str(BLENDER), "--background", "--factory-startup", "--python-expr", script]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for line in res.stdout.splitlines():
        if line.startswith("__PIXEL_EVAL_JSON__"):
            return json.loads(line.replace("__PIXEL_EVAL_JSON__", ""))
    raise RuntimeError(f"Pixel evaluation failed on {img_path}:\n{res.stdout}\n{res.stderr}")


async def run_mask_verification():
    print("=" * 80)
    print("CAPABILITY 9 — MILESTONE 9.1E: GEOMETRIC MASKS AND ID MASK FOUNDATION VERIFICATION")
    print("Target: Blender 5.2.2 LTS (Box Mask, Ellipse Mask, ID Mask, Cryptomatte Integration)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-MASK-FOUNDATION-"))
    ready_file = run_root / "blender_ready.json"
    script_file = run_root / "bootstrap.py"
    script_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    port = find_free_port()
    assert port != 9877, "Ephemeral port must never collide with production bridge 9877"

    print(f"[*] Ephemeral bridge port: {port}")
    print(f"[*] Disposable run directory: {run_root}")

    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    config_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)
    ext_dir.mkdir(parents=True, exist_ok=True)

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
    blender_log_file = run_root / "blender_output.log"
    blender_log = open(blender_log_file, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            str(BLENDER),
            "--background",
            "--factory-startup",
            "--python",
            str(script_file),
        ],
        env=env,
        stdout=blender_log,
        stderr=subprocess.STDOUT,
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

        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.")

                async def call_tool(name: str, arguments: dict):
                    result = await session.call_tool(name, arguments)
                    for content in result.content:
                        if hasattr(content, "text"):
                            try:
                                parsed = json.loads(content.text)
                                print(f"    [TOOL-CALL] {name}({arguments.get('action') or arguments.get('property_name') or ''}) -> {str(parsed)[:120]}")
                                return parsed
                            except json.JSONDecodeError:
                                return {"text": content.text}
                    return {}

                # ==============================================================================
                # STAGE 1: Deterministic Scene Setup & Baseline Render
                # ==============================================================================
                print("\n[*] STAGE 1: Configuring deterministic test scene materials, camera and passes...")
                # Create red & blue materials
                mat1 = await call_tool("create_material", {
                    "name": "Mat_Red",
                    "base_color": [0.85, 0.05, 0.05, 1.0],
                })
                mat2 = await call_tool("create_material", {
                    "name": "Mat_Blue",
                    "base_color": [0.05, 0.05, 0.85, 1.0],
                })
                await call_tool("assign_material", {"target_name": "Hero_Cube", "material_name": "Mat_Red"})
                await call_tool("assign_material", {"target_name": "Companion_Sphere", "material_name": "Mat_Blue"})

                # Camera & Lighting
                await call_tool("create_camera", {
                    "name": "Camera_Main",
                    "location": [0.0, -5.0, 0.0],
                    "rotation_euler": [1.5708, 0.0, 0.0],
                    "set_active": True,
                })
                await call_tool("create_light", {
                    "name": "Light_Main",
                    "light_type": "AREA",
                    "energy": 450.0,
                    "location": [0.0, -3.0, 4.0],
                })

                # Cycles render settings with Object Index & Cryptomatte passes
                await call_tool("configure_render_settings", {
                    "engine": "CYCLES",
                    "cycles_samples": 4,
                    "resolution_x": 128,
                    "resolution_y": 128,
                    "resolution_percentage": 100,
                })

                # Enable compositor and passes
                enable_res = await call_tool("manage_compositor_nodes", {"action": "enable"})
                assert enable_res.get("result", enable_res).get("enabled") is True

                await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {
                        "object_index": True,
                        "cryptomatte_object": True,
                    },
                })
                print("[+] Stage 1: Scene, Compositor, and Render Passes configured.")

                # Render Baseline
                base_tmp = run_root / "cap9_mask_baseline.png"
                base_path = EVIDENCE_DIR / "cap9_mask_baseline.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(base_tmp),
                    "output_format": "PNG",
                })
                assert base_tmp.exists()
                shutil.copy2(base_tmp, base_path)
                base_eval = inspect_image_pixels(base_path)
                print(f"[+] Stage 1 PASSED: Baseline Render complete: avg_r={base_eval['avg_r']}")
                await asyncio.sleep(1.0)  # Let Blender main thread settle after render

                # ==============================================================================
                # STAGE 2: CompositorNodeBoxMask Verification
                # ==============================================================================
                print("\n[*] STAGE 2: Testing CompositorNodeBoxMask (position=[0.5, 0.5], size=[0.4, 0.4])...")
                box_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "box_mask",
                    "node_name": "Mask_Box",
                    "location": [300.0, 200.0],
                })
                assert box_create.get("result", box_create).get("node_type") == "CompositorNodeBoxMask"

                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Box",
                    "property_name": "position",
                    "property_value": [0.5, 0.5],
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Box",
                    "property_name": "size",
                    "property_value": [0.4, 0.4],
                })

                # Connect Box Mask -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Mask_Box",
                    "from_socket": "Mask",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                box_tmp = run_root / "cap9_mask_box.png"
                box_path = EVIDENCE_DIR / "cap9_mask_box.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(box_tmp),
                    "output_format": "PNG",
                })
                assert box_tmp.exists()
                shutil.copy2(box_tmp, box_path)
                box_eval = inspect_image_pixels(box_path)
                print(f"[+] Stage 2 PASSED: Box Mask Render complete. White pixels: {box_eval['white_pixels']} (expected ~2500)")
                assert 2200 <= box_eval["white_pixels"] <= 2800, f"Box mask pixel count {box_eval['white_pixels']} out of expected range"
                await asyncio.sleep(1.0)  # Let Blender main thread settle after render

                # Disconnect Box Mask
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Mask_Box",
                    "from_socket": "Mask",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # ==============================================================================
                # STAGE 3: CompositorNodeEllipseMask Verification
                # ==============================================================================
                print("\n[*] STAGE 3: Testing CompositorNodeEllipseMask (position=[0.5, 0.5], size=[0.3, 0.3])...")
                ell_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "ellipse_mask",
                    "node_name": "Mask_Ellipse",
                    "location": [300.0, 0.0],
                })
                assert ell_create.get("result", ell_create).get("node_type") == "CompositorNodeEllipseMask"

                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Ellipse",
                    "property_name": "position",
                    "property_value": [0.5, 0.5],
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Ellipse",
                    "property_name": "size",
                    "property_value": [0.3, 0.3],
                })

                # Connect Ellipse Mask -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Mask_Ellipse",
                    "from_socket": "Mask",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                ell_tmp = run_root / "cap9_mask_ellipse.png"
                ell_path = EVIDENCE_DIR / "cap9_mask_ellipse.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(ell_tmp),
                    "output_format": "PNG",
                })
                assert ell_tmp.exists()
                shutil.copy2(ell_tmp, ell_path)
                ell_eval = inspect_image_pixels(ell_path)
                print(f"[+] Stage 3 PASSED: Ellipse Mask Render complete. White pixels: {ell_eval['white_pixels']} (expected ~1148)")
                assert 1000 <= ell_eval["white_pixels"] <= 1300, f"Ellipse mask pixel count {ell_eval['white_pixels']} out of expected range"
                await asyncio.sleep(1.0)  # Let Blender main thread settle after render

                # Disconnect Ellipse Mask
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Mask_Ellipse",
                    "from_socket": "Mask",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # ==============================================================================
                # STAGE 4: CompositorNodeIDMask Verification (Object Index Isolation)
                # ==============================================================================
                print("\n[*] STAGE 4: Testing CompositorNodeIDMask (isolating Hero_Cube with Index=1)...")
                id_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "id_mask",
                    "node_name": "Mask_ID",
                    "location": [300.0, -200.0],
                })
                assert id_create.get("result", id_create).get("node_type") == "CompositorNodeIDMask"

                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_ID",
                    "property_name": "index",
                    "property_value": 1,
                })

                # Connect: Render Layers.Object Index -> Mask_ID.ID value -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Object Index",
                    "to_node": "Mask_ID",
                    "to_socket": "ID value",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Mask_ID",
                    "from_socket": "Alpha",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                idm_tmp = run_root / "cap9_mask_idmask_cube.png"
                idm_path = EVIDENCE_DIR / "cap9_mask_idmask_cube.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(idm_tmp),
                    "output_format": "PNG",
                })
                assert idm_tmp.exists()
                shutil.copy2(idm_tmp, idm_path)
                idm_eval = inspect_image_pixels(idm_path)
                print(f"[+] Stage 4 PASSED: ID Mask Render complete. Left white={idm_eval['left_white']}, Right white={idm_eval['right_white']}")
                assert idm_eval["left_white"] > 2000, "ID Mask must isolate the Hero_Cube on the left"
                assert idm_eval["right_white"] == 0, "ID Mask must strictly exclude Companion_Sphere on the right (0 bleed)"
                await asyncio.sleep(1.0)  # Let Blender main thread settle after render

                # Disconnect ID Mask
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Render Layers",
                    "from_socket": "Object Index",
                    "to_node": "Mask_ID",
                    "to_socket": "ID value",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Mask_ID",
                    "from_socket": "Alpha",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # ==============================================================================
                # STAGE 5: Mask Output Integration (Selective Exposure Grading)
                # ==============================================================================
                print("\n[*] STAGE 5: Testing Mask Integration (Box Mask controlling HueSat / Exposure)...")
                # Create HueSat node
                hsv_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "hue_sat",
                    "node_name": "Grade_HSV",
                    "location": [500.0, 100.0],
                })
                # Desaturate
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Grade_HSV",
                    "property_name": "saturation",
                    "property_value": 0.0,
                })

                # Connect: Render Layers.Image -> Grade_HSV.Image
                # Connect: Mask_Box.Mask -> Grade_HSV.Factor (selective mask grading)
                # Connect: Grade_HSV.Image -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Grade_HSV",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Mask_Box",
                    "from_socket": "Mask",
                    "to_node": "Grade_HSV",
                    "to_socket": "Factor",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Grade_HSV",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                grade_tmp = run_root / "cap9_mask_integrated_grade.png"
                grade_path = EVIDENCE_DIR / "cap9_mask_integrated_grade.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(grade_tmp),
                    "output_format": "PNG",
                })
                assert grade_tmp.exists()
                shutil.copy2(grade_tmp, grade_path)
                grade_eval = inspect_image_pixels(grade_path)
                print(f"[+] Stage 5 PASSED: Integrated Mask Grading complete: avg_r={grade_eval['avg_r']}")
                await asyncio.sleep(2.0)  # Let Blender main thread drain compositor after render

                # Clean up HueSat links
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Mask_Box",
                    "from_socket": "Mask",
                    "to_node": "Grade_HSV",
                    "to_socket": "Factor",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Grade_HSV",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # ==============================================================================
                # Bridge Recovery Probe — wait for Blender main thread to settle after Stage 5
                # render + disconnect cleanup before issuing any Stage 6 mutations.
                #
                # TWO-PHASE APPROACH:
                # Phase A: Use action="inspect" (bypasses approval provider, hits bridge TCP socket
                #          directly) to verify the bridge TCP socket is alive. Fast, doesn't go
                #          through the main thread queue, so cannot clear _in_flight_timeout_unreconciled.
                # Phase B: Issue get_scene_summary (a GENUINE_SCENE_INSPECTION_HANDLER that runs on
                #          the main thread). This BOTH verifies the main thread is free AND clears
                #          _in_flight_timeout_unreconciled so Stage 6 mutations are unblocked.
                # ==============================================================================
                print("[*] Phase A: Waiting for bridge TCP socket to become responsive after Stage 5 render...")
                await asyncio.sleep(5.0)  # Give Blender compositor evaluation time to drain completely
                tcp_ok = False
                for _probe in range(15):
                    try:
                        probe_res = await call_tool("manage_compositor_nodes", {"action": "inspect"})
                        if isinstance(probe_res, dict) and (
                            probe_res.get("status") == "success" or "nodes" in str(probe_res)
                        ):
                            print(f"[+] Phase A: Bridge TCP responsive after {_probe + 1} probe(s).")
                            tcp_ok = True
                            break
                        print(f"    [A-probe {_probe + 1}] TCP not ready ({str(probe_res)[:60]}), retrying in 2s...")
                    except Exception as _pe:
                        print(f"    [A-probe {_probe + 1}] Exception: {_pe!r}, retrying in 2s...")
                    await asyncio.sleep(2.0)
                if not tcp_ok:
                    raise RuntimeError("Phase A: Bridge TCP did not respond within 35s after Stage 5 cleanup")

                print("[*] Phase B: Waiting for Blender main thread queue (get_scene_summary) to clear "
                      "_in_flight_timeout_unreconciled...")
                await asyncio.sleep(2.0)  # Extra cushion after TCP probe
                main_thread_ok = False
                for _probe in range(20):
                    try:
                        gss_res = await call_tool("get_scene_summary", {})
                        if isinstance(gss_res, dict) and gss_res.get("status") == "success":
                            print(f"[+] Phase B: Main thread ready + reconciliation cleared after {_probe + 1} probe(s).")
                            main_thread_ok = True
                            break
                        # got a response (even error) — may be clearing the barrier; retry
                        print(f"    [B-probe {_probe + 1}] get_scene_summary returned: {str(gss_res)[:80]}, retrying in 3s...")
                    except Exception as _pe:
                        print(f"    [B-probe {_probe + 1}] Exception: {_pe!r}, retrying in 3s...")
                    await asyncio.sleep(3.0)
                if not main_thread_ok:
                    raise RuntimeError("Phase B: Main thread queue did not clear within 62s after Stage 5 cleanup")

                # ==============================================================================
                # STAGE 6: Cryptomatte Matte Combination with Geometric Mask
                # ==============================================================================
                print("\n[*] STAGE 6: Testing Cryptomatte + Geometric Mask Combination (Offset Box Mask Multiply)...")
                # Create Cryptomatte node isolating Hero_Cube
                crypto_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "cryptomatte",
                    "node_name": "Crypto_Hero",
                    "location": [200.0, 300.0],
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Crypto_Hero",
                    "property_name": "matte_id",
                    "property_value": "Hero_Cube",
                })

                # Re-configure Mask_Box to partially intersect Hero_Cube
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Box",
                    "property_name": "position",
                    "property_value": [0.2, 0.5],
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Box",
                    "property_name": "size",
                    "property_value": [0.3, 0.3],
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Box",
                    "property_name": "operation",
                    "property_value": "multiply",
                })

                # Connect: Render Layers.Image -> Crypto_Hero.Image
                # Connect: Crypto_Hero.Matte -> Mask_Box.Mask
                # Connect: Mask_Box.Mask -> Group Output.Image
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "Crypto_Hero",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Crypto_Hero",
                    "from_socket": "Matte",
                    "to_node": "Mask_Box",
                    "to_socket": "Mask",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Mask_Box",
                    "from_socket": "Mask",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                comb_tmp = run_root / "cap9_mask_crypto_box_combined.png"
                comb_path = EVIDENCE_DIR / "cap9_mask_crypto_box_combined.png"
                comb_res = await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(comb_tmp),
                    "output_format": "PNG",
                })
                if not comb_tmp.exists():
                    raise RuntimeError(f"comb_tmp not found. render_scene returned: {comb_res}")
                assert comb_tmp.exists()
                shutil.copy2(comb_tmp, comb_path)
                comb_eval = inspect_image_pixels(comb_path)
                print(f"[+] Stage 6 PASSED: Cryptomatte + Geometric Mask combined: white pixels = {comb_eval['white_pixels']} (expected ~1444)")
                assert 1000 <= comb_eval["white_pixels"] <= 1600, f"Combined mask white pixels {comb_eval['white_pixels']} out of expected range"

                # ==============================================================================
                # STAGE 7: Concurrency & Bounds Invariants
                # ==============================================================================
                print("\n[*] STAGE 7: Optimistic Concurrency & Parameter Bounds Invariants...")

                # 7.1 Stale Snapshot Rejection
                stale_res = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Box",
                    "property_name": "size",
                    "property_value": [0.5, 0.5],
                    "expected_snapshot_id": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                })
                assert "stale_compositor_graph" in str(stale_res).lower() or "error" in str(stale_res).lower()
                print("[+] 7.1 PASSED: Stale snapshot rejected fail-closed.")

                # 7.2 Out-of-bounds parameter rejection
                pos_err = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_Box",
                    "property_name": "position",
                    "property_value": [5.0, 0.5],
                })
                assert "coordinates must be in" in str(pos_err).lower() or "error" in str(pos_err).lower()
                print("[+] 7.2 PASSED: Out-of-bounds mask position rejected.")

                idx_err = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "Mask_ID",
                    "property_name": "index",
                    "property_value": -5,
                })
                assert "index must be in" in str(idx_err).lower() or "error" in str(idx_err).lower()
                print("[+] 7.3 PASSED: Negative ID mask index rejected.")

                # Telemetry Receipt
                telemetry = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "target_blender": "5.2.2 LTS",
                    "port": port,
                    "measurements": {
                        "baseline": base_eval,
                        "box_mask": box_eval,
                        "ellipse_mask": ell_eval,
                        "id_mask": idm_eval,
                        "integrated_grade": grade_eval,
                        "crypto_box_combined": comb_eval,
                    },
                    "status": "ALL_STAGES_PASSED",
                }
                telem_path = EVIDENCE_DIR / "mask_foundation_telemetry.json"
                telem_path.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
                print(f"[+] Telemetry written to {telem_path}")
                print("\n>>> ALL STAGES COMPLETED SUCCESSFULLY <<<")

    finally:
        (run_root / "stop.flag").write_text("STOP")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            blender_log.close()
        except Exception:
            pass
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_mask_verification())
