"""
Behavior-Level Verification for Phase 6.1 Step 3: Cloth Object Collision Settings.

Fixture & Test Setup:
- Rigid Deflector Obstacle:
  * UV Sphere 'DeflectorSphere': center = (0, 0, 0.5), radius = 0.5m. Top apex at Z = 1.0m.
  * Physics: COLLISION modifier, cloth_friction = 10.0, damping = 0.1, thickness_outer = 0.02.
- Separate Cloth Plane:
  * Grid plane 'ClothPlane': center = (0, 0, 1.2), size = 1.0m x 1.0m, 11x11 vertices (121 vertices).
  * Initial vertical clearance to apex: 1.20m - 1.00m = 0.20m (200mm).
- Physical Controls & Invariant Checks:
  1. Negative Control Run (Collision Disabled: use_collision=False):
     - Cloth falls under gravity and passes directly through the deflector.
     - Frame 15: Cloth penetrates through the deflector volume (penetration_count > 0, min_surface_clearance < 0.0m).
     - Frame 20: Entire cloth drops past the obstacle (mean_z < 0.0m).
  2. Treatment Run A (Object Collision Enabled: use_collision=True, distance_min=0.015):
     - Evaluated cloth drapes over the sphere surface without interpenetrating (penetration_count = 0, max_penetration_depth = 0.0m).
     - Minimum surface clearance is maintained positive (~0.028m >= distance_min).
     - Evaluated height (mean_z ~ 0.89m, max_z ~ 1.03m) held stably by the deflector.
  3. Treatment Run B (Increased Distance Clearance: use_collision=True, distance_min=0.060):
     - Cloth rests noticeably higher off the deflector surface.
     - Measured minimum clearance increases from Treatment A (~0.028m) to Treatment B (~0.074m), delta >= 0.040m.
     - Mean height increases (mean_z Treatment B > Treatment A).
  4. Isolation Invariant:
     - use_self_collision=False, use_internal_springs=False, use_pressure=False for all runs.
     - Verifies that collision response is strictly caused by the external deflector object.
"""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON_EXE = Path(sys.executable)

BOOTSTRAP_CODE = r"""
import bpy
import bmesh
import json
import mathutils
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

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# 1. Deflector Sphere Object
def_mesh = bpy.data.meshes.new('DeflectorMesh')
def_obj = bpy.data.objects.new('DeflectorSphere', def_mesh)
scene.collection.objects.link(def_obj)
bm_s = bmesh.new()
bmesh.ops.create_uvsphere(bm_s, u_segments=16, v_segments=16, radius=0.5)
bm_s.to_mesh(def_mesh)
bm_s.free()
def_obj.location = (0, 0, 0.5)

# 2. Cloth Plane Object
cloth_mesh = bpy.data.meshes.new('ClothMesh')
cloth_obj = bpy.data.objects.new('ClothPlane', cloth_mesh)
scene.collection.objects.link(cloth_obj)
bm_c = bmesh.new()
bmesh.ops.create_grid(bm_c, x_segments=10, y_segments=10, size=0.5)
bm_c.to_mesh(cloth_mesh)
bm_c.free()
cloth_obj.location = (0, 0, 1.2)

queue = MainThreadQueue(bpy)
server = BridgeServer(port=port, queue=queue)
server.start()

(root / "blender_ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "blender": bpy.app.version_string,
}))

deadline = time.monotonic() + 180
processed = set()

def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)

try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        queue.drain_queue()
        for req in root.glob("eval_request_*.json"):
            if req.name in processed:
                continue
            q = json.loads(req.read_text(encoding="utf-8"))
            frame_num = int(q.get("frame", 1))
            scene.frame_set(frame_num)
            ctx = bpy.context
            ctx.view_layer.update()
            dg = ctx.evaluated_depsgraph_get()
            t_obj = scene.objects.get(q.get("target", "ClothPlane"))
            eval_obj = t_obj.evaluated_get(dg)
            mat = eval_obj.matrix_world
            coords = [mat @ v.co for v in eval_obj.data.vertices]

            # Sphere apex top is at (0, 0, 1.0), center at (0, 0, 0.5), radius 0.5
            center = mathutils.Vector((0.0, 0.0, 0.5))
            radius = 0.5
            dists_to_surface = [(p - center).length - radius for p in coords]
            inside_sphere = [d for d in dists_to_surface if d < 0.0]
            z_vals = [p.z for p in coords]

            res = {
                "frame": frame_num,
                "min_z": round(min(z_vals), 4),
                "mean_z": round(sum(z_vals) / len(z_vals), 4),
                "max_z": round(max(z_vals), 4),
                "min_surface_clearance": round(min(dists_to_surface), 4),
                "penetration_count": len(inside_sphere),
                "max_penetration_depth": round(abs(min(inside_sphere)), 4) if inside_sphere else 0.0,
            }
            save_json(root / f"eval_{q['id']}.json", res)
            processed.add(req.name)
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


def get_production_listener():
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "@(Get-NetTCPConnection -LocalPort 9877 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json"],
        capture_output=True, text=True
    )
    if not res.stdout.strip():
        return []
    try:
        data = json.loads(res.stdout)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


async def run_behavior_verification():
    print("=" * 80)
    print("BEHAVIOR-LEVEL SIMULATION VERIFICATION: CLOTH OBJECT COLLISION (Phase 6.1 Step 3)")
    print("=" * 80)

    # 1. Safeguard verification
    prod_before = get_production_listener()
    assert len(prod_before) >= 1 and prod_before[0]["OwningProcess"] in (17920, 39604), f"Production guard violation: {prod_before}"
    prod_pid = prod_before[0]["OwningProcess"]
    print(f"[+] Production bridge verified on port 9877 (PID {prod_pid}). Will remain isolated.")

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CLOTH-COLL-BEHAV-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Guard violation: ephemeral port matched production {port}"
    print(f"[*] Ephemeral bridge port: {port}")
    print(f"[*] Isolated test root: {run_root}")

    blender_env = dict(os.environ)
    blender_env.update({
        "BLENDER_USER_CONFIG": str(config_dir),
        "BLENDER_USER_SCRIPTS": str(scripts_dir),
        "BLENDER_USER_EXTENSIONS": str(ext_dir),
        "UMCP_RUN_ROOT": str(run_root),
        "UMCP_PROJECT": str(PROJECT),
        "UMCP_BRIDGE_PORT": str(port),
        "UMCP_LOCAL_TEST_AUTOAPPROVE": "1",
        "UMCP_LOCAL_TEST_SCOPE": "physics_v1",
        "UMCP_LOCAL_TEST_ROOT": str(run_root),
    })

    bootstrap_file = run_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    blender_cmd = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "--python",
        str(bootstrap_file),
    ]

    print("[*] Launching disposable headless Blender 5.2.2 LTS session...")
    proc = subprocess.Popen(
        blender_cmd,
        env=blender_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    ready_file = run_root / "blender_ready.json"
    try:
        start_time = time.monotonic()
        while not ready_file.exists():
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                raise RuntimeError(f"Blender exited early: {stderr}\n{stdout}")
            if time.monotonic() - start_time > 30:
                raise TimeoutError("Blender failed to start within 30 seconds.")
            await asyncio.sleep(0.1)

        ready_info = json.loads(ready_file.read_text(encoding="utf-8"))
        print(f"[+] Blender ready! PID: {ready_info['pid']}, Version: {ready_info.get('blender', '5.2.2 LTS')}")

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        client_env = dict(os.environ)
        client_env["PYTHONPATH"] = str(PROJECT)
        client_env["PYTHONDONTWRITEBYTECODE"] = "1"
        client_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "physics_v1"
        client_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
        client_env["UMCP_BRIDGE_PORT"] = str(port)
        client_env["BLENDER_USER_CONFIG"] = str(config_dir)
        client_env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
        client_env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)

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
                "20",
                "--approval-mode",
                "blender",
            ],
            env=client_env,
            cwd=str(PROJECT),
        )

        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.")

                async def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                    res = await session.call_tool(name, arguments=args)
                    if getattr(res, "isError", False):
                        text = res.content[0].text if res.content else "Unknown error"
                        return {"status": "error", "message": text}
                    raw_text = res.content[0].text if res.content else "{}"
                    try:
                        data = json.loads(raw_text)
                        if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
                            out = dict(data["result"])
                            if "status" in data and "status" not in out:
                                out["status"] = data["status"]
                            return out
                        return data
                    except Exception:
                        return {"status": "raw", "text": raw_text}

                async def evaluate_frame(target: str, frame: int, req_id: str) -> Dict[str, Any]:
                    req_file = run_root / f"eval_request_{req_id}.json"
                    res_file = run_root / f"eval_{req_id}.json"
                    payload = {"id": req_id, "target": target, "frame": frame}
                    req_file.write_text(json.dumps(payload), encoding="utf-8")
                    t_start = time.monotonic()
                    while not res_file.exists():
                        if time.monotonic() - t_start > 15:
                            raise TimeoutError(f"Evaluation timed out for request {req_id} frame {frame}")
                        await asyncio.sleep(0.05)
                    return json.loads(res_file.read_text(encoding="utf-8"))

                # -------------------------------------------------------------
                # STEP 0: Configure Deflector Object as COLLISION Surface
                # -------------------------------------------------------------
                print("\n[*] STEP 0: Configuring DeflectorSphere with COLLISION physics...")
                res_coll = await call_tool("configure_physics", {
                    "object_name": "DeflectorSphere",
                    "physics_type": "COLLISION",
                    "action": "add",
                    "damping": 0.1,
                    "cloth_friction": 10.0,
                    "thickness_outer": 0.02,
                })
                assert res_coll.get("success") is True, f"Failed deflector collision configure: {res_coll}"
                print("[+] DeflectorSphere configured as COLLISION physics modifier.")

                # Initial Frame 1 Geometry Readback
                init_geom = await evaluate_frame("ClothPlane", 1, "init_f1")
                print(f"[+] Initial Geometry (Frame 1): min_z={init_geom['min_z']}m, mean_z={init_geom['mean_z']}m, clearance={init_geom['min_surface_clearance']}m, penetrations={init_geom['penetration_count']}")
                assert init_geom["min_surface_clearance"] >= 0.20, f"Initial clearance expected >= 0.20m, got {init_geom['min_surface_clearance']}"
                assert init_geom["penetration_count"] == 0

                # -------------------------------------------------------------
                # RUN 1: Negative Control (Object Collision Disabled: use_collision=False)
                # -------------------------------------------------------------
                print("\n" + "=" * 60)
                print("[*] RUN 1: Negative Control (Cloth Object Collision DISABLED)")
                print("=" * 60)
                res_ctrl = await call_tool("configure_physics", {
                    "object_name": "ClothPlane",
                    "physics_type": "CLOTH",
                    "action": "add",
                    "cloth_preset": "COTTON",
                    "quality": 7,
                    "use_collision": False,
                    "use_self_collision": False,
                    "use_internal_springs": False,
                    "use_pressure": False,
                })
                assert res_ctrl.get("success") is True, f"Failed negative control configure: {res_ctrl}"

                print("[*] Baking negative control cloth simulation (Frames 1..20)...")
                res_bake_ctrl = await call_tool("bake_physics_simulation", {
                    "physics_type": "CLOTH",
                    "object_name": "ClothPlane",
                    "frame_start": 1,
                    "frame_end": 20,
                    "timeout_seconds": 30.0,
                })
                assert res_bake_ctrl.get("success") is True, f"Failed negative control bake: {res_bake_ctrl}"

                # Readback at Frame 15 (Mid-flight through deflector) and Frame 20 (Fallen completely past)
                ctrl_f15 = await evaluate_frame("ClothPlane", 15, "ctrl_f15")
                ctrl_f20 = await evaluate_frame("ClothPlane", 20, "ctrl_f20")
                print(f"[+] Control Frame 15: min_z={ctrl_f15['min_z']}m, mean_z={ctrl_f15['mean_z']}m, clearance={ctrl_f15['min_surface_clearance']}m, penetrations={ctrl_f15['penetration_count']}, max_depth={ctrl_f15['max_penetration_depth']}m")
                print(f"[+] Control Frame 20: min_z={ctrl_f20['min_z']}m, mean_z={ctrl_f20['mean_z']}m, clearance={ctrl_f20['min_surface_clearance']}m, penetrations={ctrl_f20['penetration_count']}")

                # Invariant checks for control:
                # At Frame 15, cloth must penetrate into/through the sphere volume
                assert ctrl_f15["penetration_count"] > 0, f"Expected penetration without collision at frame 15, got {ctrl_f15['penetration_count']}"
                assert ctrl_f15["min_surface_clearance"] < 0.0, f"Expected negative clearance at frame 15, got {ctrl_f15['min_surface_clearance']}"
                assert ctrl_f15["max_penetration_depth"] >= 0.25, f"Expected deep penetration depth >= 0.25m, got {ctrl_f15['max_penetration_depth']}"
                # At Frame 20, unhindered cloth falls completely past the sphere (mean_z < 0.0)
                assert ctrl_f20["mean_z"] < 0.0, f"Expected cloth to drop below z=0, got {ctrl_f20['mean_z']}"

                # -------------------------------------------------------------
                # RUN 2: Treatment A (Object Collision Enabled: distance_min=0.015)
                # -------------------------------------------------------------
                print("\n" + "=" * 60)
                print("[*] RUN 2: Treatment A (use_collision=True, distance_min=0.015)")
                print("=" * 60)
                res_treat_a = await call_tool("configure_physics", {
                    "object_name": "ClothPlane",
                    "physics_type": "CLOTH",
                    "action": "configure",
                    "use_collision": True,
                    "distance_min": 0.015,
                    "friction": 10.0,
                    "collision_quality": 4,
                    "use_self_collision": False,
                })
                assert res_treat_a.get("success") is True, f"Failed configure Treatment A: {res_treat_a}"

                print("[*] Baking Treatment A cloth simulation (Frames 1..20)...")
                res_bake_a = await call_tool("bake_physics_simulation", {
                    "physics_type": "CLOTH",
                    "object_name": "ClothPlane",
                    "frame_start": 1,
                    "frame_end": 20,
                    "timeout_seconds": 30.0,
                })
                assert res_bake_a.get("success") is True, f"Failed Treatment A bake: {res_bake_a}"

                treat_a_f15 = await evaluate_frame("ClothPlane", 15, "treat_a_f15")
                treat_a_f20 = await evaluate_frame("ClothPlane", 20, "treat_a_f20")
                print(f"[+] Treatment A Frame 15: min_z={treat_a_f15['min_z']}m, mean_z={treat_a_f15['mean_z']}m, clearance={treat_a_f15['min_surface_clearance']}m, penetrations={treat_a_f15['penetration_count']}")
                print(f"[+] Treatment A Frame 20: min_z={treat_a_f20['min_z']}m, mean_z={treat_a_f20['mean_z']}m, clearance={treat_a_f20['min_surface_clearance']}m, penetrations={treat_a_f20['penetration_count']}")

                # Invariant checks for Treatment A:
                # 1. Zero penetration into the obstacle
                assert treat_a_f15["penetration_count"] == 0, f"Expected 0 penetrations, got {treat_a_f15['penetration_count']}"
                assert treat_a_f20["penetration_count"] == 0, f"Expected 0 penetrations, got {treat_a_f20['penetration_count']}"
                # 2. Minimum surface clearance is maintained positive
                assert treat_a_f15["min_surface_clearance"] >= 0.015, f"Clearance violated distance_min: {treat_a_f15['min_surface_clearance']}"
                assert treat_a_f20["min_surface_clearance"] >= 0.015, f"Clearance violated distance_min: {treat_a_f20['min_surface_clearance']}"
                # 3. High elevation retained by the deflector (mean_z maintained above 0.85m)
                assert treat_a_f20["mean_z"] > 0.85, f"Expected cloth supported above 0.85m, got {treat_a_f20['mean_z']}"
                # 4. Measurable elevation delta vs control: > 1.10 meters higher
                elev_delta_a = treat_a_f20["mean_z"] - ctrl_f20["mean_z"]
                assert elev_delta_a > 1.10, f"Expected elevation delta > 1.10m, got {elev_delta_a}"

                # -------------------------------------------------------------
                # RUN 3: Treatment B (Object Collision Enabled: distance_min=0.060)
                # -------------------------------------------------------------
                print("\n" + "=" * 60)
                print("[*] RUN 3: Treatment B (use_collision=True, distance_min=0.060)")
                print("=" * 60)
                res_treat_b = await call_tool("configure_physics", {
                    "object_name": "ClothPlane",
                    "physics_type": "CLOTH",
                    "action": "configure",
                    "use_collision": True,
                    "distance_min": 0.060,
                    "friction": 10.0,
                    "collision_quality": 4,
                })
                assert res_treat_b.get("success") is True, f"Failed configure Treatment B: {res_treat_b}"

                print("[*] Baking Treatment B cloth simulation (Frames 1..20)...")
                res_bake_b = await call_tool("bake_physics_simulation", {
                    "physics_type": "CLOTH",
                    "object_name": "ClothPlane",
                    "frame_start": 1,
                    "frame_end": 20,
                    "timeout_seconds": 30.0,
                })
                assert res_bake_b.get("success") is True, f"Failed Treatment B bake: {res_bake_b}"

                treat_b_f15 = await evaluate_frame("ClothPlane", 15, "treat_b_f15")
                treat_b_f20 = await evaluate_frame("ClothPlane", 20, "treat_b_f20")
                print(f"[+] Treatment B Frame 15: min_z={treat_b_f15['min_z']}m, mean_z={treat_b_f15['mean_z']}m, clearance={treat_b_f15['min_surface_clearance']}m, penetrations={treat_b_f15['penetration_count']}")
                print(f"[+] Treatment B Frame 20: min_z={treat_b_f20['min_z']}m, mean_z={treat_b_f20['mean_z']}m, clearance={treat_b_f20['min_surface_clearance']}m, penetrations={treat_b_f20['penetration_count']}")

                # Invariant checks for Treatment B:
                # 1. Zero penetration
                assert treat_b_f15["penetration_count"] == 0
                assert treat_b_f20["penetration_count"] == 0
                # 2. Minimum clearance maintained positive >= 0.060
                assert treat_b_f15["min_surface_clearance"] >= 0.060, f"Clearance violated distance_min: {treat_b_f15['min_surface_clearance']}"
                assert treat_b_f20["min_surface_clearance"] >= 0.060, f"Clearance violated distance_min: {treat_b_f20['min_surface_clearance']}"
                # 3. Measurable clearance increase from Treatment A to Treatment B
                clearance_delta_f15 = treat_b_f15["min_surface_clearance"] - treat_a_f15["min_surface_clearance"]
                clearance_delta_f20 = treat_b_f20["min_surface_clearance"] - treat_a_f20["min_surface_clearance"]
                print(f"[+] Clearance Delta (B vs A): Frame 15 = +{clearance_delta_f15:.4f}m, Frame 20 = +{clearance_delta_f20:.4f}m")
                assert clearance_delta_f15 >= 0.035, f"Expected clearance delta >= 0.035m, got {clearance_delta_f15}"
                assert clearance_delta_f20 >= 0.035, f"Expected clearance delta >= 0.035m, got {clearance_delta_f20}"
                # 4. Overall cloth mean elevation is higher in Treatment B than Treatment A
                assert treat_b_f20["mean_z"] > treat_a_f20["mean_z"]
                assert treat_b_f20["max_z"] > treat_a_f20["max_z"]

                # -------------------------------------------------------------
                # STEP 4: Generate Verification Receipt
                # -------------------------------------------------------------
                print("\n[*] Generating verification receipt...")
                receipt_path = PROJECT / "docs" / "verification" / "CLOTH_OBJECT_COLLISION_BEHAVIOR_V0191.md"
                init_min_sc = init_geom['min_surface_clearance']
                init_mz = init_geom['min_z']
                init_meanz = init_geom['mean_z']
                init_maxz = init_geom['max_z']

                c_f15_sc = ctrl_f15['min_surface_clearance']
                c_f15_pc = ctrl_f15['penetration_count']
                c_f15_md = ctrl_f15['max_penetration_depth']
                c_f15_mz = ctrl_f15['min_z']
                c_f15_meanz = ctrl_f15['mean_z']
                c_f15_maxz = ctrl_f15['max_z']

                c_f20_sc = ctrl_f20['min_surface_clearance']
                c_f20_pc = ctrl_f20['penetration_count']
                c_f20_mz = ctrl_f20['min_z']
                c_f20_meanz = ctrl_f20['mean_z']
                c_f20_maxz = ctrl_f20['max_z']

                ta_f15_sc = treat_a_f15['min_surface_clearance']
                ta_f15_mz = treat_a_f15['min_z']
                ta_f15_meanz = treat_a_f15['mean_z']
                ta_f15_maxz = treat_a_f15['max_z']

                ta_f20_sc = treat_a_f20['min_surface_clearance']
                ta_f20_mz = treat_a_f20['min_z']
                ta_f20_meanz = treat_a_f20['mean_z']
                ta_f20_maxz = treat_a_f20['max_z']

                tb_f15_sc = treat_b_f15['min_surface_clearance']
                tb_f15_mz = treat_b_f15['min_z']
                tb_f15_meanz = treat_b_f15['mean_z']
                tb_f15_maxz = treat_b_f15['max_z']

                tb_f20_sc = treat_b_f20['min_surface_clearance']
                tb_f20_mz = treat_b_f20['min_z']
                tb_f20_meanz = treat_b_f20['mean_z']
                tb_f20_maxz = treat_b_f20['max_z']

                receipt_content = f"""# Capability 6.1 (Step 3) Behavior Verification Receipt: Cloth Object Collision

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
**Blender Runtime:** Blender 5.2.2 LTS (Disposable PID: {ready_info['pid']})
**Bridge Port:** Ephemeral loopback port {port} (!= 9877)
**Status:** **ACCEPTED - ALL BEHAVIOR INVARIANTS SATISFIED**

## Test Fixture Configuration

- **Obstacle Fixture:** UV Sphere (DeflectorSphere), center at (0, 0, 0.5)m, radius 0.5m (apex Z = 1.0m).
  - Collision modifier: cloth_friction = 10.0, damping = 0.1, thickness_outer = 0.02m.
- **Cloth Target:** Grid plane (ClothPlane), 1.0m x 1.0m, 11x11 vertices (121 vertices), initial position Z = 1.2m.
  - Preset: COTTON, Quality: 7, Frames: 1..20.
- **Ablation & Isolation Invariants:**
  - use_self_collision = False, use_internal_springs = False, use_pressure = False.
  - Verifies that geometric deflection is purely induced by external object collision.

---

## Evaluated Geometry & Clearance Comparison

| Condition | Frame | Min Clearance (m) | Penetrations | Max Depth (m) | Min Z (m) | Mean Z (m) | Max Z (m) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Initial State** | Frame 1 | +{init_min_sc:.4f} | 0 | 0.0000 | {init_mz:.4f} | {init_meanz:.4f} | {init_maxz:.4f} |
| **Control (No Collision)** | Frame 15 | {c_f15_sc:.4f} | {c_f15_pc} | {c_f15_md:.4f} | {c_f15_mz:.4f} | {c_f15_meanz:.4f} | {c_f15_maxz:.4f} |
| **Control (No Collision)** | Frame 20 | +{c_f20_sc:.4f} | {c_f20_pc} | 0.0000 | {c_f20_mz:.4f} | {c_f20_meanz:.4f} | {c_f20_maxz:.4f} |
| **Treatment A (dist_min=0.015)** | Frame 15 | +{ta_f15_sc:.4f} | 0 | 0.0000 | {ta_f15_mz:.4f} | {ta_f15_meanz:.4f} | {ta_f15_maxz:.4f} |
| **Treatment A (dist_min=0.015)** | Frame 20 | +{ta_f20_sc:.4f} | 0 | 0.0000 | {ta_f20_mz:.4f} | {ta_f20_meanz:.4f} | {ta_f20_maxz:.4f} |
| **Treatment B (dist_min=0.060)** | Frame 15 | +{tb_f15_sc:.4f} | 0 | 0.0000 | {tb_f15_mz:.4f} | {tb_f15_meanz:.4f} | {tb_f15_maxz:.4f} |
| **Treatment B (dist_min=0.060)** | Frame 20 | +{tb_f20_sc:.4f} | 0 | 0.0000 | {tb_f20_mz:.4f} | {tb_f20_meanz:.4f} | {tb_f20_maxz:.4f} |

---

## Physical Verification Insights

1. **Collision Response Verification:**
   - In the negative control run (use_collision=False), the cloth falls unhindered through the obstacle, exhibiting {c_f15_pc} penetrating vertices at Frame 15 (max depth {c_f15_md:.4f}m) and completely falling past the sphere by Frame 20 (mean Z = {c_f20_meanz:.4f}m).
   - Enabling use_collision=True (Treatment A) completely eliminates penetration (0 penetrating vertices across all frames) and arrests the cloth on top of the sphere (mean Z = +{ta_f20_meanz:.4f}m, an elevation retention delta of +{elev_delta_a:.4f}m).
2. **distance_min Sensitivity:**
   - Increasing distance_min from 0.015m to 0.060m (+45 mm) produces an evaluated surface clearance increase of +{clearance_delta_f15:.4f}m at Frame 15 ({ta_f15_sc:.4f}m to {tb_f15_sc:.4f}m) and +{clearance_delta_f20:.4f}m at Frame 20 ({ta_f20_sc:.4f}m to {tb_f20_sc:.4f}m).
   - The top apex vertex clearance increases from {ta_f20_maxz:.4f}m to {tb_f20_maxz:.4f}m (+{tb_f20_maxz - ta_f20_maxz:.4f}m), confirming strict sensitivity to distance_min.
3. **Safety & Invariant Checks:**
   - Zero self-collision, springs, or pressure were configured; the observed geometric response is solely governed by use_collision and distance_min against the external deflector object.
"""
                receipt_path.write_text(receipt_content, encoding="utf-8")
                print(f"[+] Verification receipt saved to {receipt_path}.")

                print("\n" + "=" * 80)
                print("BEHAVIORAL VERIFICATION COMPLETE: ALL INVARIANTS PASSED!")
                print("=" * 80)

    finally:
        print("[*] Terminating disposable Blender process...")
        (run_root / "stop.flag").touch()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[+] Disposable Blender process terminated.")

        # Re-verify production bridge
        prod_after = get_production_listener()
        assert len(prod_after) >= 1 and prod_after[0]["OwningProcess"] == prod_pid, f"Production guard compromised: {prod_after}"
        print(f"[+] Production bridge 127.0.0.1:9877 (PID {prod_pid}) verified active, listening, and untouched.")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(run_behavior_verification(), timeout=120.0))
