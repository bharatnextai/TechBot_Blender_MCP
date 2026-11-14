"""
Behavioral Verification Script for Capability 9 — Milestone 9.1D:
Visual Effects Node Foundation in Blender 5.2.2 LTS.

Executes over standard MCP wire protocol on disposable Blender 5.2.2 LTS with ephemeral port (!= 9877).

Test Matrix:
1. Scene Setup: Deterministic high-contrast scene with cube, active camera, and lighting.
2. Stage 1: Render Baseline Beauty Image (cap9_vfx_baseline.png).
3. Stage 2: CompositorNodeLensdist:
   - Creation & property mutation (distortion = 0.5, dispersion = 0.2).
   - Render: cap9_vfx_lensdist.png.
   - Pixel Analysis: Confirms geometric distortion (avg diff > 0.05 vs baseline, max diff >= 0.5).
4. Stage 3: CompositorNodeDefocus:
   - Creation & property mutation (use_zbuffer = False, f_stop = 0.5, blur_max = 64.0).
   - Render: cap9_vfx_defocus.png.
   - Pixel Analysis: Confirms optical blur / sharpness change (measurable pixel divergence).
5. Stage 4: CompositorNodeFilter:
   - Creation & property mutation (filter_type = 'Sobel').
   - Render: cap9_vfx_filter.png.
   - Pixel Analysis: Confirms edge extraction / high-pass filtering (avg diff > 0.10 vs baseline).
6. Stage 5: Integrated VFX Multi-Node Pipeline:
   - Render Layers -> Lensdist -> Filter -> Defocus -> Group Output.
   - Render: cap9_vfx_integrated_chain.png.
7. Stage 6: Fail-closed validation for out-of-bounds properties and stale snapshots.
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
EVIDENCE_DIR = PROJECT / "docs" / "verification" / "evidence" / "cap9_vfx_foundation"
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

avg_r = sum(r_vals) / len(r_vals)
avg_g = sum(g_vals) / len(g_vals)
avg_b = sum(b_vals) / len(b_vals)
max_r = max(r_vals)
max_g = max(g_vals)
max_b = max(b_vals)

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
}}))
"""
    cmd = [str(BLENDER), "--background", "--factory-startup", "--python-expr", script]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for line in res.stdout.splitlines():
        if line.startswith("__PIXEL_EVAL_JSON__"):
            return json.loads(line.replace("__PIXEL_EVAL_JSON__", ""))
    raise RuntimeError(f"Pixel evaluation failed on {img_path}:\n{res.stdout}\n{res.stderr}")


def compute_image_difference(img_path_a: Path, img_path_b: Path) -> Dict[str, float]:
    """Computes pixel-by-pixel difference between two rendered images."""
    script = f"""
import bpy
img_a = bpy.data.images.load(r'{str(img_path_a)}')
img_b = bpy.data.images.load(r'{str(img_path_b)}')
px_a = list(img_a.pixels)
px_b = list(img_b.pixels)

diffs = [abs(a - b) for a, b in zip(px_a, px_b)]
avg_diff = sum(diffs) / len(diffs)
max_diff = max(diffs)
changed_px = sum(1 for d in diffs if d > 0.005)

import json
print("__DIFF_EVAL_JSON__" + json.dumps({{
    "avg_diff": round(avg_diff, 6),
    "max_diff": round(max_diff, 6),
    "changed_pixels": changed_px,
    "total_values": len(diffs)
}}))
"""
    cmd = [str(BLENDER), "--background", "--factory-startup", "--python-expr", script]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for line in res.stdout.splitlines():
        if line.startswith("__DIFF_EVAL_JSON__"):
            return json.loads(line.replace("__DIFF_EVAL_JSON__", ""))
    raise RuntimeError(f"Image diff calculation failed:\n{res.stdout}\n{res.stderr}")


async def run_vfx_verification():
    print("=" * 80)
    print("CAPABILITY 9 — MILESTONE 9.1D: VISUAL EFFECTS NODE FOUNDATION VERIFICATION")
    print("Target: Blender 5.2.2 LTS (Lens Distortion, Defocus, Filter)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-VFX-FOUNDATION-"))
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
                print("\n[*] STAGE 1: Creating deterministic test scene...")
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "VFX_Subject_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                assert cube_res.get("result", cube_res).get("name") == "VFX_Subject_Cube"

                mat_res = await call_tool("create_material", {
                    "name": "Target_Red_Mat",
                    "base_color": [0.85, 0.05, 0.05, 1.0],
                })
                assert mat_res.get("status") == "success"

                assign_res = await call_tool("assign_material", {
                    "target_name": "VFX_Subject_Cube",
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
                base_tmp = run_root / "cap9_vfx_baseline.png"
                base_path = EVIDENCE_DIR / "cap9_vfx_baseline.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(base_tmp),
                    "output_format": "PNG",
                })
                assert base_tmp.exists()
                shutil.copy2(base_tmp, base_path)
                base_eval = inspect_image_pixels(base_path)
                print(f"[+] Stage 1 PASSED: Baseline Render complete: avg_r={base_eval['avg_r']}")

                # ==============================================================================
                # STAGE 2: CompositorNodeLensdist Verification
                # ==============================================================================
                print("\n[*] STAGE 2: Testing CompositorNodeLensdist (distortion=0.5, dispersion=0.2)...")
                lens_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "lens_distortion",
                    "node_name": "VFX_Lens",
                    "location": [300.0, 200.0],
                })
                assert lens_create.get("result", lens_create).get("node_type") == "CompositorNodeLensdist"

                # Set properties
                lens_prop1 = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Lens",
                    "property_name": "distortion",
                    "property_value": 0.5,
                })
                assert lens_prop1.get("result", lens_prop1).get("property_value") == 0.5

                lens_prop2 = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Lens",
                    "property_name": "dispersion",
                    "property_value": 0.2,
                })
                assert lens_prop2.get("result", lens_prop2).get("property_value") == 0.2

                # Connect: Render Layers -> Lens -> Group Output
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "VFX_Lens",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "VFX_Lens",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                lens_tmp = run_root / "cap9_vfx_lensdist.png"
                lens_path = EVIDENCE_DIR / "cap9_vfx_lensdist.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(lens_tmp),
                    "output_format": "PNG",
                })
                assert lens_tmp.exists()
                shutil.copy2(lens_tmp, lens_path)
                lens_diff = compute_image_difference(base_path, lens_path)
                print(f"[+] Stage 2 PASSED: Lens Distortion Render complete. Diff vs baseline: avg_diff={lens_diff['avg_diff']}, max_diff={lens_diff['max_diff']}, changed_px={lens_diff['changed_pixels']}")
                assert lens_diff["avg_diff"] > 0.05, "Lens distortion must produce measurable geometric change"
                assert lens_diff["max_diff"] >= 0.5, "Lens distortion edge shifts must be pronounced"

                # Disconnect Lensdist
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "VFX_Lens",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "VFX_Lens",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # ==============================================================================
                # STAGE 3: CompositorNodeDefocus Verification
                # ==============================================================================
                print("\n[*] STAGE 3: Testing CompositorNodeDefocus (blur_max=64.0, f_stop=0.5)...")
                defocus_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "defocus",
                    "node_name": "VFX_Defocus",
                    "location": [300.0, 0.0],
                })
                assert defocus_create.get("result", defocus_create).get("node_type") == "CompositorNodeDefocus"

                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Defocus",
                    "property_name": "f_stop",
                    "property_value": 0.5,
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Defocus",
                    "property_name": "blur_max",
                    "property_value": 64.0,
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Defocus",
                    "property_name": "use_zbuffer",
                    "property_value": False,
                })

                # Connect: Render Layers -> Defocus -> Group Output
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "VFX_Defocus",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "VFX_Defocus",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                defocus_tmp = run_root / "cap9_vfx_defocus.png"
                defocus_path = EVIDENCE_DIR / "cap9_vfx_defocus.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(defocus_tmp),
                    "output_format": "PNG",
                })
                assert defocus_tmp.exists()
                shutil.copy2(defocus_tmp, defocus_path)
                defocus_diff = compute_image_difference(base_path, defocus_path)
                print(f"[+] Stage 3 PASSED: Defocus Render complete. Diff vs baseline: avg_diff={defocus_diff['avg_diff']}, max_diff={defocus_diff['max_diff']}, changed_px={defocus_diff['changed_pixels']}")
                assert defocus_diff["changed_pixels"] > 500, "Defocus must blur silhouette edge pixels measurably"

                # Disconnect Defocus
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "VFX_Defocus",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "VFX_Defocus",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # ==============================================================================
                # STAGE 4: CompositorNodeFilter Verification
                # ==============================================================================
                print("\n[*] STAGE 4: Testing CompositorNodeFilter (filter_type='Sobel')...")
                filter_create = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "filter",
                    "node_name": "VFX_Filter",
                    "location": [300.0, -200.0],
                })
                assert filter_create.get("result", filter_create).get("node_type") == "CompositorNodeFilter"

                await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Filter",
                    "property_name": "filter_type",
                    "property_value": "sobel",
                })

                # Connect: Render Layers -> Filter -> Group Output
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "VFX_Filter",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "VFX_Filter",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                filter_tmp = run_root / "cap9_vfx_filter.png"
                filter_path = EVIDENCE_DIR / "cap9_vfx_filter.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(filter_tmp),
                    "output_format": "PNG",
                })
                assert filter_tmp.exists()
                shutil.copy2(filter_tmp, filter_path)
                filter_diff = compute_image_difference(base_path, filter_path)
                print(f"[+] Stage 4 PASSED: Filter Render complete. Diff vs baseline: avg_diff={filter_diff['avg_diff']}, max_diff={filter_diff['max_diff']}, changed_px={filter_diff['changed_pixels']}")
                assert filter_diff["avg_diff"] > 0.10, "Sobel filter must transform color render into high-pass edge gradient"

                # Disconnect Filter
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "VFX_Filter",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "disconnect",
                    "from_node": "VFX_Filter",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                # ==============================================================================
                # STAGE 5: Integrated VFX Pipeline Verification
                # ==============================================================================
                print("\n[*] STAGE 5: Testing Chained VFX Pipeline (RLayers -> Lensdist -> Filter -> Defocus -> Group Output)...")
                # Connect: RLayers -> Lensdist -> Filter -> Defocus -> Group Output
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "VFX_Lens",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "VFX_Lens",
                    "from_socket": "Image",
                    "to_node": "VFX_Filter",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "VFX_Filter",
                    "from_socket": "Image",
                    "to_node": "VFX_Defocus",
                    "to_socket": "Image",
                })
                await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "VFX_Defocus",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })

                chain_tmp = run_root / "cap9_vfx_integrated_chain.png"
                chain_path = EVIDENCE_DIR / "cap9_vfx_integrated_chain.png"
                await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": str(chain_tmp),
                    "output_format": "PNG",
                })
                assert chain_tmp.exists()
                shutil.copy2(chain_tmp, chain_path)
                chain_diff = compute_image_difference(base_path, chain_path)
                print(f"[+] Stage 5 PASSED: Integrated Chain Render complete: avg_diff={chain_diff['avg_diff']}, max_diff={chain_diff['max_diff']}")
                assert chain_diff["avg_diff"] > 0.05, "Chained pipeline must produce composite transformation"

                # ==============================================================================
                # STAGE 6: Fail-Closed Concurrency, Bounds & Security Validation
                # ==============================================================================
                print("\n[*] STAGE 6: Security, Bounds & Optimistic Concurrency Invariants...")

                # 6.1 Stale Snapshot Rejection
                stale_res = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Lens",
                    "property_name": "distortion",
                    "property_value": 0.1,
                    "expected_snapshot_id": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                })
                assert "stale_compositor_graph" in str(stale_res).lower() or "error" in str(stale_res).lower()
                print("[+] 6.1 PASSED: Stale snapshot rejected fail-closed.")

                # 6.2 Out-of-bounds parameter rejection
                lens_err = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Lens",
                    "property_name": "distortion",
                    "property_value": 99.0,
                })
                assert "out of bounds" in str(lens_err).lower() or "error" in str(lens_err).lower() or "between" in str(lens_err).lower()
                print("[+] 6.2 PASSED: Out-of-bounds distortion rejected.")

                filter_err = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "VFX_Filter",
                    "property_name": "filter_type",
                    "property_value": "unsupported_magic_filter",
                })
                assert "invalid filter type" in str(filter_err).lower() or "error" in str(filter_err).lower()
                print("[+] 6.3 PASSED: Invalid filter type rejected.")

                # Save telemetry receipt
                telemetry = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "target_blender": "5.2.2 LTS",
                    "port": port,
                    "diffs": {
                        "lensdist": lens_diff,
                        "defocus": defocus_diff,
                        "filter": filter_diff,
                        "integrated_chain": chain_diff,
                    },
                    "status": "ALL_STAGES_PASSED",
                }
                telem_path = EVIDENCE_DIR / "vfx_foundation_telemetry.json"
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
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_vfx_verification())
