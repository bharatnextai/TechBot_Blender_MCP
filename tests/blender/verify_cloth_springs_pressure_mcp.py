"""
Automated Real MCP-to-Blender E2E Verification of Cloth Internal Springs and Pressure (Phase 6.1, Step 2).

Validates:
1. Ephemeral disposable Blender 5.2.2 LTS instance on an OS-assigned loopback port (!= 9877).
2. Production port 9877 guard: verified listening on PID 17920 and untouched throughout.
3. Discover physics tools over MCP stdio wire.
4. Live execution and independent Blender readback:
   - Stage 1: Create mesh primitive via create_primitive.
   - Stage 2: Configure cloth physics with internal springs and pressure via configure_physics:
     (use_internal_springs, internal_spring_max_length, internal_tension_stiffness,
      internal_compression_stiffness, internal_spring_normal_check,
      use_pressure, uniform_pressure_force, use_pressure_volume, target_volume, pressure_factor).
   - Stage 3: Read-only inspection of cloth internal springs and pressure properties via inspect_physics.
   - Stage 4: Optimistic concurrency protection with expected_snapshot_id (STALE_PHYSICS_STATE).
   - Stage 5: Parameter boundary enforcement fail-closed (uniform_pressure_force, internal_tension_stiffness, etc.).
   - Stage 6: Transactional rollback on invalid mutation preserving pre-mutation settings.
   - Stage 7: Point cache simulation baking with cloth simulation active.
   - Stage 8: Process teardown & evidence receipt.
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


async def run_e2e_verification():
    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER VERIFICATION: CLOTH INTERNAL SPRINGS & PRESSURE (Phase 6.1 Step 2)")
    print("=" * 80)

    # Verify production bridge 9877 is untouched
    prod_before = get_production_listener()
    assert len(prod_before) >= 1 and prod_before[0]["OwningProcess"] == 17920, f"Production guard failed: {prod_before}"
    print(f"[+] Production bridge verified on port 9877 (PID 17920). Will remain isolated.")

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CLOTH-SPRINGS-PRESS-"))
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
                "15",
            ],
            env=client_env,
        )

        print("[*] Connecting MCP ClientSession over stdio transport...")
        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_res = await session.initialize()
                print(f"[+] MCP Session initialized: {init_res.serverInfo.name} {init_res.serverInfo.version}")

                async def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                    try:
                        res = await session.call_tool(name, arguments=args)
                    except Exception as ex:
                        return {"status": "error", "message": str(ex), "exception": type(ex).__name__}
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

                # Stage 1: Create mesh cube
                print("\n[*] Stage 1: Creating mesh primitive via create_primitive...")
                res_content = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "ClothPressureCube",
                })
                print(f"[+] create_primitive response: {res_content}")
                assert res_content.get("created") is True or res_content.get("status") == "success", f"Failed create_primitive: {res_content}"

                # Stage 2: Configure cloth physics with internal springs and pressure
                print("\n[*] Stage 2: Configuring cloth internal springs and pressure via configure_physics...")
                conf_data = await call_tool("configure_physics", {
                    "object_name": "ClothPressureCube",
                    "physics_type": "CLOTH",
                    "action": "add",
                    "cloth_preset": "COTTON",
                    "quality": 6,
                    "use_internal_springs": True,
                    "internal_spring_max_length": 2.5,
                    "internal_tension_stiffness": 25.0,
                    "internal_compression_stiffness": 35.0,
                    "internal_spring_normal_check": False,
                    "use_pressure": True,
                    "uniform_pressure_force": 4.5,
                    "use_pressure_volume": True,
                    "target_volume": 1.2,
                    "pressure_factor": 1.5,
                })
                print(f"[+] configure_physics response:\n{json.dumps(conf_data, indent=2)}")
                assert conf_data.get("success") is True, f"configure_physics failed: {conf_data}"
                assert conf_data.get("use_internal_springs") is True
                assert conf_data.get("internal_spring_max_length") == 2.5
                assert conf_data.get("internal_tension_stiffness") == 25.0
                assert conf_data.get("internal_compression_stiffness") == 35.0
                assert conf_data.get("internal_spring_normal_check") is False
                assert conf_data.get("use_pressure") is True
                assert conf_data.get("uniform_pressure_force") == 4.5
                assert conf_data.get("use_pressure_volume") is True
                assert conf_data.get("target_volume") == 1.2
                assert conf_data.get("pressure_factor") == 1.5
                snapshot_id_1 = conf_data.get("snapshot_id")
                assert snapshot_id_1 and snapshot_id_1.startswith("physics_")

                # Stage 3: Inspect physics via inspect_physics
                print("\n[*] Stage 3: Inspecting physics via inspect_physics...")
                insp_data = await call_tool("inspect_physics", {
                    "object_name": "ClothPressureCube",
                })
                print(f"[+] inspect_physics response:\n{json.dumps(insp_data, indent=2)}")
                assert insp_data.get("success") is True
                cloth_info = insp_data["target"]["cloth"]
                assert cloth_info["use_internal_springs"] is True
                assert round(cloth_info["internal_spring_max_length"], 4) == 2.5
                assert round(cloth_info["internal_tension_stiffness"], 4) == 25.0
                assert round(cloth_info["internal_compression_stiffness"], 4) == 35.0
                assert cloth_info["internal_spring_normal_check"] is False
                assert cloth_info["use_pressure"] is True
                assert round(cloth_info["uniform_pressure_force"], 4) == 4.5
                assert cloth_info["use_pressure_volume"] is True
                assert round(cloth_info["target_volume"], 4) == 1.2
                assert round(cloth_info["pressure_factor"], 4) == 1.5
                assert insp_data["snapshot_id"] == snapshot_id_1

                # Stage 4: Concurrency control check (STALE_PHYSICS_STATE)
                print("\n[*] Stage 4: Testing optimistic concurrency protection...")
                stale_data = await call_tool("configure_physics", {
                    "object_name": "ClothPressureCube",
                    "physics_type": "CLOTH",
                    "action": "configure",
                    "uniform_pressure_force": 6.0,
                    "expected_snapshot_id": "physics_0000000000000000",
                })
                print(f"[+] Stale snapshot response: {stale_data}")
                assert "STALE_PHYSICS_STATE" in str(stale_data) or stale_data.get("status") == "error", "Expected STALE_PHYSICS_STATE rejection"

                # Valid expected snapshot succeeds
                valid_data = await call_tool("configure_physics", {
                    "object_name": "ClothPressureCube",
                    "physics_type": "CLOTH",
                    "action": "configure",
                    "uniform_pressure_force": 8.0,
                    "expected_snapshot_id": snapshot_id_1,
                })
                print(f"[+] Stage 4 valid_data: {valid_data}")
                assert valid_data.get("success") is True
                assert valid_data.get("uniform_pressure_force") == 8.0
                snapshot_id_2 = valid_data.get("snapshot_id")
                assert snapshot_id_2 != snapshot_id_1
                print(f"[+] Snapshot progressed on mutation: {snapshot_id_1} -> {snapshot_id_2}")

                # Stage 5: Parameter boundary enforcement fail-closed
                print("\n[*] Stage 5: Parameter boundary enforcement...")
                bound_tests = [
                    {"uniform_pressure_force": 15000.0},
                    {"uniform_pressure_force": -15000.0},
                    {"internal_spring_max_length": -2.0},
                    {"internal_spring_max_length": 1500.0},
                    {"internal_tension_stiffness": -1.0},
                    {"internal_compression_stiffness": 20000.0},
                    {"target_volume": -1.0},
                    {"pressure_factor": 15000.0},
                ]
                for invalid_param in bound_tests:
                    p = {
                        "object_name": "ClothPressureCube",
                        "physics_type": "CLOTH",
                        "action": "configure",
                    }
                    p.update(invalid_param)
                    err_res = await call_tool("configure_physics", p)
                    print(f"    Tested invalid param {invalid_param}: {err_res}")
                    assert err_res.get("status") == "error" or "error" in str(err_res).lower() or "valueerror" in str(err_res).lower()

                # Stage 6: Transactional rollback
                print("\n[*] Stage 6: Testing transactional rollback on mutation failure...")
                # Try setting internal springs to new values, but pair with invalid mass to trigger failure
                fail_data = await call_tool("configure_physics", {
                    "object_name": "ClothPressureCube",
                    "physics_type": "CLOTH",
                    "action": "configure",
                    "internal_compression_stiffness": 99.0,
                    "uniform_pressure_force": 99.0,
                    "mass": -50.0,  # Invalid mass triggers rollback
                })
                assert fail_data.get("status") == "error" or "valueerror" in str(fail_data).lower()
                print(f"[+] Failed configure correctly rejected: {str(fail_data)[:100]}...")

                # Inspect to verify state was rolled back to snapshot_id_2 settings
                post_fail_data = await call_tool("inspect_physics", {
                    "object_name": "ClothPressureCube",
                })
                post_cloth = post_fail_data["target"]["cloth"]
                assert post_cloth["internal_compression_stiffness"] == 35.0, f"Rollback failed: expected 35.0, got {post_cloth['internal_compression_stiffness']}"
                assert post_cloth["uniform_pressure_force"] == 8.0, f"Rollback failed: expected 8.0, got {post_cloth['uniform_pressure_force']}"
                print("[+] Transactional rollback verified: prior springs and pressure values preserved.")

                # Stage 7: Bake simulation cache
                print("\n[*] Stage 7: Baking cloth simulation cache via bake_physics_simulation...")
                bake_data = await call_tool("bake_physics_simulation", {
                    "physics_type": "CLOTH",
                    "frame_start": 1,
                    "frame_end": 15,
                    "timeout_seconds": 30.0,
                })
                print(f"[+] bake_physics_simulation response:\n{json.dumps(bake_data, indent=2)}")
                assert bake_data.get("success") is True
                assert bake_data.get("frame_count") == 15 or bake_data.get("frames_baked") == 15

                print("\n" + "=" * 80)
                print("E2E LIVE VERIFICATION SUCCESSFUL: ALL 7 STAGES PASSED")
                print("=" * 80)

    finally:
        (run_root / "stop.flag").write_text("STOP", encoding="utf-8")
        try:
            out, err = proc.communicate(timeout=5)
            print("--- BLENDER STDOUT ---")
            print(out)
            print("--- BLENDER STDERR ---")
            print(err)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

        prod_after = get_production_listener()
        assert len(prod_after) >= 1 and prod_after[0]["OwningProcess"] == 17920, f"Production guard compromised: {prod_after}"
        print(f"[+] Production bridge verified still intact on port 9877 (PID 17920).")


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
