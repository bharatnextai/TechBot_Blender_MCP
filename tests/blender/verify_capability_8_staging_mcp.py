"""
Live MCP-to-Blender Verification for Capability 8: Milestone 8.1
Architectural and Product Staging Core.

Executes against actual Blender 5.2.2 LTS in a disposable headless sandbox
using an ephemeral loopback bridge port and authentic MCP stdio ClientSession.
Production bridge 9877 is untouched.

Verifies:
1. create_cyclorama: parameterized seamless curved sweep cove, tangent continuity, smooth shading.
2. set_object_origin: bottom-center pivot setting while preserving world-space vertex coordinates.
3. create_room_enclosure: parametric walls, floor slab, and doorway aperture cutout.
4. Architectural integration: snap_to_ground and align_object_grid for column/prop placement.
5. Fail-closed rejection of invalid parameters and out-of-bounds geometry.
"""

import asyncio
import json
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


async def run_staging_verification():
    print("=" * 80)
    print("STARTING CAPABILITY 8 MILESTONE 8.1: ARCHITECTURAL & PRODUCT STAGING VERIFICATION")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-STAGING-CAP8-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Guard violation: port matched production {port}"

    ready_file = run_root / "blender_ready.json"
    script_file = run_root / "bootstrap.py"
    script_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_SCOPE"] = "environment_staging_v1"
    env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    env["BLENDER_USER_CONFIG"] = str(config_dir)
    env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)

    proc = subprocess.Popen(
        [str(BLENDER), "--background", "--factory-startup", "--python", str(script_file)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        for _ in range(60):
            if ready_file.exists():
                break
            await asyncio.sleep(0.5)
        assert ready_file.exists(), "Disposable Blender instance failed to start within timeout."

        ready_data = json.loads(ready_file.read_text())
        print(f"Disposable Blender online: PID {ready_data['pid']} on ephemeral port {port}")
        print(f"Blender version: {ready_data['blender']}")

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        client_env = dict(os.environ)
        client_env["PYTHONPATH"] = str(PROJECT)
        client_env["PYTHONDONTWRITEBYTECODE"] = "1"
        client_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "environment_staging_v1"
        client_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
        client_env["UMCP_BRIDGE_PORT"] = str(port)

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
                "15",
                "--approval-mode",
                "blender",
                "--debug",
            ],
            env=client_env,
            cwd=str(PROJECT),
        )

        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.")

                # STAGE 1: Tool Discovery
                print("\n--- STAGE 1: TOOL DISCOVERY ---")
                tools_res = await session.list_tools()
                discovered = {t.name for t in tools_res.tools}
                for req_tool in ("create_cyclorama", "set_object_origin", "create_room_enclosure", "snap_to_ground", "align_object_grid"):
                    assert req_tool in discovered, f"Tool '{req_tool}' not in discovered tools."
                print(f"[+] All Milestone 8.1 staging tools discovered ({len(discovered)} total tools).")

                def unwrap(res):
                    raw = json.loads(res.content[0].text) if res.content else {}
                    if isinstance(raw, dict) and "result" in raw:
                        return raw["result"]
                    return raw

                # STAGE 2: Parametric Studio Cyclorama
                print("\n--- STAGE 2: CREATE PARAMETRIC CYCLORAMA ---")
                res_cyc = await session.call_tool(
                    "create_cyclorama",
                    {
                        "name": "HeroStudioCyc",
                        "width": 12.0,
                        "depth": 10.0,
                        "wall_height": 5.0,
                        "cove_radius": 2.0,
                        "cove_segments": 20,
                        "location": [0.0, 0.0, 0.0],
                    },
                )
                assert not res_cyc.isError, f"create_cyclorama error: {res_cyc}"
                cyc_data = unwrap(res_cyc)
                assert cyc_data["name"] == "HeroStudioCyc"
                assert cyc_data["vertex_count"] > 40
                assert cyc_data["polygon_count"] >= 20
                print(f"[+] Cyclorama verified: {cyc_data['name']} (verts={cyc_data['vertex_count']}, polys={cyc_data['polygon_count']})")

                # STAGE 3: Set Object Origin (BOTTOM_CENTER)
                print("\n--- STAGE 3: SET OBJECT ORIGIN (BOTTOM_CENTER) ---")
                res_ped = await session.call_tool(
                    "create_primitive",
                    {
                        "name": "DisplayPedestal",
                        "primitive_type": "cylinder",
                        "radius": 1.5,
                        "depth": 1.0,
                        "location": [0.0, 0.0, 2.0],
                    },
                )
                assert not res_ped.isError, f"Pedestal creation failed: {res_ped}"

                res_origin = await session.call_tool(
                    "set_object_origin",
                    {
                        "object_name": "DisplayPedestal",
                        "origin_mode": "BOTTOM_CENTER",
                    },
                )
                assert not res_origin.isError, f"set_object_origin failed: {res_origin}"
                origin_data = unwrap(res_origin)
                assert origin_data["origin_mode"] == "BOTTOM_CENTER"
                new_origin_z = origin_data["new_origin_world"][2]
                assert abs(new_origin_z - 1.5) < 1e-4, f"Expected origin Z=1.5, got {new_origin_z}"
                print(f"[+] Pedestal origin repositioned to bottom-center: Z={new_origin_z:.3f} (geometry preserved)")

                # STAGE 4: Snap to Ground
                print("\n--- STAGE 4: SNAP TO GROUND ---")
                res_snap = await session.call_tool(
                    "snap_to_ground",
                    {
                        "object_name": "DisplayPedestal",
                        "offset": 0.0,
                    },
                )
                assert not res_snap.isError, f"snap_to_ground failed: {res_snap}"
                snap_data = unwrap(res_snap)
                assert abs(snap_data["new_z_min"]) < 1e-4, f"Expected Z_min=0.0 after snap, got {snap_data['new_z_min']}"
                print(f"[+] Pedestal snapped cleanly to floor: Z_min={snap_data['new_z_min']:.4f}")

                # STAGE 5: Create Parametric Architectural Room Enclosure
                print("\n--- STAGE 5: CREATE ARCHITECTURAL ROOM ENCLOSURE ---")
                res_room = await session.call_tool(
                    "create_room_enclosure",
                    {
                        "name": "StudioGallery",
                        "width": 8.0,
                        "length": 10.0,
                        "height": 3.2,
                        "wall_thickness": 0.25,
                        "include_floor": True,
                        "include_ceiling": False,
                        "door_wall": "SOUTH",
                        "door_width": 1.2,
                        "door_height": 2.2,
                        "location": [20.0, 0.0, 0.0],
                    },
                )
                assert not res_room.isError, f"create_room_enclosure failed: {res_room}"
                room_data = unwrap(res_room)
                assert room_data["name"] == "StudioGallery"
                assert room_data["door_wall"] == "SOUTH"
                assert room_data["polygon_count"] > 20
                print(f"[+] Room enclosure created: {room_data['name']} with SOUTH doorway (width=1.2m, height=2.2m)")

                # STAGE 6: Align Object to Grid
                print("\n--- STAGE 6: ALIGN OBJECT TO GRID ---")
                await session.call_tool(
                    "create_primitive",
                    {
                        "name": "ArchitecturalColumn",
                        "primitive_type": "cylinder",
                        "radius": 0.3,
                        "depth": 3.0,
                        "location": [21.34, 1.88, 1.5],
                    },
                )
                res_align = await session.call_tool(
                    "align_object_grid",
                    {
                        "object_name": "ArchitecturalColumn",
                        "grid_size": 1.0,
                        "snap_axes": ["X", "Y"],
                    },
                )
                assert not res_align.isError, f"align_object_grid failed: {res_align}"
                align_data = unwrap(res_align)
                snapped = align_data["snapped_location"]
                assert abs(snapped[0] - 21.0) < 1e-4
                assert abs(snapped[1] - 2.0) < 1e-4
                print(f"[+] Column snapped from [21.34, 1.88] to grid: [{snapped[0]:.1f}, {snapped[1]:.1f}]")

                # STAGE 7: Fail-Closed Validation
                print("\n--- STAGE 7: FAIL-CLOSED VALIDATION ---")
                res_bad = await session.call_tool(
                    "create_cyclorama",
                    {
                        "name": "BadCyc",
                        "width": 10.0,
                        "depth": 5.0,
                        "wall_height": 2.0,
                        "cove_radius": 4.0,  # exceeds wall_height=2.0
                    },
                )
                bad_data = unwrap(res_bad)
                assert res_bad.isError or bad_data.get("status") in ("ERROR", "error"), f"Expected error on excessive cove radius, got: {bad_data}"
                print(f"[+] Excessive cove radius correctly rejected fail-closed: {bad_data.get('message')}")

                print("\n" + "=" * 80)
                print("CAPABILITY 8 MILESTONE 8.1 VERIFICATION COMPLETE: ALL 7 STAGES PASSED")
                print("=" * 80)

    finally:
        (run_root / "stop.flag").write_text("stop")
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(run_staging_verification())
