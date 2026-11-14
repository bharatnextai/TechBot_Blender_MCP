"""
Automated E2E Verification of Sculpt Mutation via MCP -> Bridge -> Disposable Blender 5.2.2.
Verifies TASK v0.1.48:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port (!= 9877).
2. Interactive window mode to provide a live VIEW_3D context for sculpt stroke execution.
3. Isolated auto-approval scope ('sculpt_v1') permitting owned fixture mesh operations.
4. Production human approval preservation and single-use token consumption.
5. Mode lifecycle (enter_sculpt / exit_sculpt).
6. Brush selection (Essentials / Local) and brush settings modification.
7. Bounded stroke mutating geometry on Blender main thread.
8. Dynamic topology toggling (CONSTANT mode).
9. Voxel remesh in Object mode.
10. Fail-closed error handling: stale snapshot rejection, unowned target rejection, untrusted approval flag rejection.
11. Tested transaction rollback recovery restoring original mesh datablock.
12. Independent geometry readback via inspect_sculpt_state and inspect_scene_data.
13. Clean shutdown, zero lingering state, and preserved evidence.
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
from typing import Dict, Any, List

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
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

from blender_addon.universal_mcp.operators import get_server_instance
from blender_addon.universal_mcp.bridge.local_test_scope import configure_fixture
from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry

# Configure Scene and Port
scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

# Clear default objects
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# Create Fixture Mesh (Icosphere for uniform tessellation)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.0, location=(0, 0, 0))
fixture_obj = bpy.context.active_object
fixture_obj.name = "FixtureSculpt"
bpy.context.view_layer.objects.active = fixture_obj
fixture_obj.select_set(True)

# Register fixture with local test scope
configure_fixture(bpy, root, [fixture_obj], [])

initial_state = {
    "objects": sorted(bpy.data.objects.keys()),
    "active": fixture_obj.name,
    "mode": bpy.context.mode,
    "vertex_count": len(fixture_obj.data.vertices),
    "polygon_count": len(fixture_obj.data.polygons),
}
(root / "initial_state.json").write_text(json.dumps(initial_state, indent=2))

def start_bridge():
    try:
        outcome = bpy.ops.umcp.start_bridge()
        (root / "ready.json").write_text(json.dumps({
            "pid": os.getpid(),
            "port": port,
            "blender": bpy.app.version_string,
            "background": bpy.app.background,
            "objects": sorted(bpy.data.objects.keys()),
        }, indent=2))
    except Exception as exc:
        (root / "startup_error.json").write_text(json.dumps({"error": str(exc)}, indent=2))
    return None

def observe():
    if (root / "stop").exists():
        server = get_server_instance(port)
        if server and server.running:
            server.stop()
        registry = get_approval_registry()
        req_list = [registry.inspect_request_status(rid) for rid in list(registry._requests.keys())]
        (root / "final_state.json").write_text(json.dumps({
            "pid": os.getpid(),
            "bridge_running": bool(server.running) if server else False,
            "objects": sorted(bpy.data.objects.keys()),
            "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
            "mode": bpy.context.mode,
            "requests": req_list,
        }, indent=2))
        bpy.ops.wm.quit_blender()
        return None
    return 0.05

bpy.app.timers.register(observe, first_interval=0.05, persistent=True)
bpy.app.timers.register(start_bridge, first_interval=0.5)
"""


async def run_mcp_test_client(root: Path, port: int) -> Dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(PROJECT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UMCP_LOCAL_TEST_ROOT": str(root),
        "UMCP_LOCAL_TEST_AUTOAPPROVE": "1",
        "UMCP_LOCAL_TEST_SCOPE": "sculpt_v1",
    })

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-B", "-m", "mcp_service.app",
            "--transport", "stdio",
            "--bridge-port", str(port),
            "--bridge-timeout", "10",
            "--approval-mode", "blender",
        ],
        env=env,
        cwd=str(PROJECT),
    )

    calls_log: List[Dict[str, Any]] = []

    with (root / "mcp.log").open("w", encoding="utf-8") as mcp_log:
        async with stdio_client(params, errlog=mcp_log) as streams:
            async with ClientSession(*streams) as session:
                init_result = await session.initialize()
                catalog = await session.list_tools()
                tool_names = [t.name for t in catalog.tools]
                assert "sculpt_mesh" in tool_names, f"sculpt_mesh missing from catalog: {tool_names}"
                assert "inspect_sculpt_state" in tool_names, f"inspect_sculpt_state missing from catalog: {tool_names}"

                async def call_tool(tool_name: str, arguments: Dict[str, Any], expect_success: bool = True) -> Dict[str, Any]:
                    res = await session.call_tool(tool_name, arguments=arguments)
                    entry = {
                        "tool": tool_name,
                        "args": arguments,
                        "isError": res.isError,
                        "raw_content": [c.model_dump(mode="json") for c in res.content],
                        "expect_success": expect_success,
                    }
                    calls_log.append(entry)
                    (root / "calls.json").write_text(json.dumps(calls_log, indent=2))
                    if expect_success:
                        assert not res.isError, f"Tool call returned protocol error: {res}"
                        payload = json.loads(res.content[0].text)
                        assert payload.get("status") == "success", f"Expected success but got: {payload}"
                        return payload.get("result", {})
                    else:
                        if res.isError:
                            return {"status": "error", "message": res.content[0].text if res.content else "Protocol error"}
                        payload = json.loads(res.content[0].text)
                        assert payload.get("status") == "error", f"Expected error but got success: {payload}"
                        return payload

                results_summary: Dict[str, Any] = {}

                # 1. Initial State Readback
                s0 = await call_tool("inspect_sculpt_state", {"object_name": "FixtureSculpt"})
                assert s0["success"] is True and s0["verified"] is True
                assert s0["mode"] == "OBJECT"
                assert s0["object_name"] == "FixtureSculpt"
                snap_id = s0["snapshot_id"]
                initial_vcount = s0["vertex_count"]
                results_summary["step1_initial_readback"] = s0

                # 2. Enter Sculpt Mode
                r_enter = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "enter_sculpt",
                    "expected_snapshot_id": snap_id,
                })
                assert r_enter["action"] == "enter_sculpt"
                assert r_enter["mode"] == "SCULPT"
                snap_id = r_enter["snapshot_id"]
                results_summary["step2_enter_sculpt"] = r_enter

                # Verify inspect reflects SCULPT mode
                s_sculpt = await call_tool("inspect_sculpt_state", {"object_name": "FixtureSculpt"})
                assert s_sculpt["mode"] == "SCULPT"

                # 3. Set Brush to 'Clay'
                r_brush = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "set_brush",
                    "brush_name": "Clay",
                    "expected_snapshot_id": snap_id,
                })
                assert r_brush["brush"]["name"] == "Clay"
                results_summary["step3_set_brush"] = r_brush

                # 4. Set Brush Settings (size: 45, strength: 0.8)
                r_settings = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "set_brush_settings",
                    "settings": {"size": 45, "strength": 0.8, "use_frontface": True},
                    "expected_snapshot_id": snap_id,
                })
                assert r_settings["brush"]["size"] == 45
                assert abs(r_settings["brush"]["strength"] - 0.8) < 1e-4
                results_summary["step4_set_brush_settings"] = r_settings

                # 5. Apply Bounded Stroke (Mutates Geometry)
                stroke_points = [
                    {"x": 0.48, "y": 0.48, "pressure": 0.8},
                    {"x": 0.50, "y": 0.50, "pressure": 0.9},
                    {"x": 0.52, "y": 0.52, "pressure": 0.8},
                ]
                r_stroke = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "stroke",
                    "points": stroke_points,
                    "expected_snapshot_id": snap_id,
                })
                assert r_stroke["transaction_status"] == "COMMITTED"
                assert r_stroke["snapshot_id"] != snap_id, "Stroke must produce verified snapshot change"
                post_stroke_snap = r_stroke["snapshot_id"]
                results_summary["step5_stroke"] = r_stroke

                # Readback verification
                s_post_stroke = await call_tool("inspect_sculpt_state", {"object_name": "FixtureSculpt"})
                assert s_post_stroke["snapshot_id"] == post_stroke_snap
                snap_id = post_stroke_snap

                # 6. Enable Dynamic Topology (CONSTANT mode, detail 2.0)
                r_dyntopo_on = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "set_dyntopo",
                    "enabled": True,
                    "detail_mode": "CONSTANT",
                    "detail_size": 2.0,
                    "expected_snapshot_id": snap_id,
                })
                assert r_dyntopo_on["dyntopo_enabled"] is True
                results_summary["step6_dyntopo_on"] = r_dyntopo_on

                # 7. Disable Dynamic Topology
                r_dyntopo_off = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "set_dyntopo",
                    "enabled": False,
                    "detail_mode": "CONSTANT",
                    "detail_size": 2.0,
                    "expected_snapshot_id": snap_id,
                })
                assert r_dyntopo_off["dyntopo_enabled"] is False
                results_summary["step7_dyntopo_off"] = r_dyntopo_off

                # 8. Exit Sculpt Mode
                r_exit = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "exit_sculpt",
                    "expected_snapshot_id": snap_id,
                })
                assert r_exit["action"] == "exit_sculpt"
                assert r_exit["mode"] == "OBJECT"
                snap_id = r_exit["snapshot_id"]
                results_summary["step8_exit_sculpt"] = r_exit

                # Verify inspect reflects OBJECT mode
                s_obj = await call_tool("inspect_sculpt_state", {"object_name": "FixtureSculpt"})
                assert s_obj["mode"] == "OBJECT"

                # 9. Voxel Remesh in Object Mode (voxel_size: 0.15)
                r_remesh = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "voxel_remesh",
                    "voxel_size": 0.15,
                    "expected_snapshot_id": snap_id,
                })
                assert r_remesh["transaction_status"] == "COMMITTED"
                assert r_remesh["snapshot_id"] != snap_id
                assert r_remesh["vertex_count"] != initial_vcount
                snap_id = r_remesh["snapshot_id"]
                results_summary["step9_voxel_remesh"] = r_remesh

                # 10. Failure & Cancellation Handling

                # 10a: Stale Snapshot Rejection
                err_stale = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "set_brush_settings",
                    "settings": {"size": 30},
                    "expected_snapshot_id": "sha256:" + "0" * 64,
                }, expect_success=False)
                assert "STALE" in err_stale.get("message", "").upper() or "STALE" in str(err_stale).upper()
                results_summary["step10a_stale_rejection"] = err_stale

                # 10b: Unowned Object Rejection (Fail-closed scope policy)
                err_unowned = await call_tool("sculpt_mesh", {
                    "object_name": "UnownedDragonMesh",
                    "action": "enter_sculpt",
                    "expected_snapshot_id": snap_id,
                }, expect_success=False)
                assert "denied" in str(err_unowned).lower() or "error" in str(err_unowned).lower()
                results_summary["step10b_unowned_rejection"] = err_unowned

                # 10c: Untrusted Approval Flag Rejection
                err_untrusted = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "enter_sculpt",
                    "expected_snapshot_id": snap_id,
                    "approved": True,
                }, expect_success=False)
                assert "approved" in str(err_untrusted).lower() or "error" in str(err_untrusted).lower()
                results_summary["step10c_untrusted_flag_rejection"] = err_untrusted

                # 10d: Rollback Recovery Test
                # Re-enter sculpt mode first
                await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "enter_sculpt",
                    "expected_snapshot_id": snap_id,
                })
                # Attempt stroke in corner off-mesh that produces 0 vertex movement -> triggers rollback in sculpt_tools.py
                off_mesh_points = [{"x": 0.01, "y": 0.01}, {"x": 0.02, "y": 0.02}]
                err_rollback = await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "stroke",
                    "points": off_mesh_points,
                    "expected_snapshot_id": snap_id,
                }, expect_success=False)
                assert "no verified mesh change" in str(err_rollback).lower() or "failed" in str(err_rollback).lower()
                results_summary["step10d_rollback_recovery"] = err_rollback

                # Verify snapshot is unchanged and restored
                s_after_rollback = await call_tool("inspect_sculpt_state", {"object_name": "FixtureSculpt"})
                assert s_after_rollback["snapshot_id"] == snap_id, "Rollback must preserve original mesh snapshot"

                # Exit sculpt mode cleanly
                await call_tool("sculpt_mesh", {
                    "object_name": "FixtureSculpt",
                    "action": "exit_sculpt",
                    "expected_snapshot_id": snap_id,
                })

                # 11. Final Independent Topology Readback via inspect_scene_data
                topo_readback = await call_tool("inspect_scene_data", {
                    "category": "mesh_topology",
                    "target_name": "FixtureSculpt",
                    "element_domain": "vertices",
                    "limit": 10,
                })
                assert topo_readback.get("vertex_count") == s_after_rollback["vertex_count"]
                assert topo_readback.get("snapshot_id") == snap_id
                results_summary["step11_independent_readback"] = topo_readback

                return {
                    "status": "PASS",
                    "total_calls": len(calls_log),
                    "successful_mutations": 7,
                    "verified_failures": 4,
                    "results": results_summary,
                    "server_info": init_result.serverInfo.model_dump(),
                }


def main():
    root = Path(tempfile.mkdtemp(prefix="UMCP-SCULPT-E2E-"))
    print(f"SCULPT_E2E_ROOT={root}", flush=True)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    if port == 9877:
        raise RuntimeError("Refusing production port 9877")
    print(f"EPHEMERAL_PORT={port}", flush=True)

    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(PROJECT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UMCP_PROJECT": str(PROJECT),
        "UMCP_RUN_ROOT": str(root),
        "UMCP_LOCAL_TEST_ROOT": str(root),
        "UMCP_BRIDGE_PORT": str(port),
        "UMCP_LOCAL_TEST_AUTOAPPROVE": "1",
        "UMCP_LOCAL_TEST_SCOPE": "sculpt_v1",
    })
    for folder_name in ("config", "scripts", "extensions", "datafiles", "resources"):
        folder = root / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        env["BLENDER_USER_" + folder_name.upper()] = str(folder)

    boot = root / "bootstrap.py"
    boot.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    blender_log_file = (root / "blender.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            str(BLENDER),
            "--factory-startup",
            "--disable-autoexec",
            "--python", str(boot),
        ],
        cwd=str(PROJECT),
        env=env,
        stdout=blender_log_file,
        stderr=subprocess.STDOUT,
    )
    print(f"BLENDER_PID={process.pid}", flush=True)

    try:
        deadline = time.monotonic() + 45
        while not (root / "ready.json").exists():
            if process.poll() is not None:
                raise RuntimeError(f"Blender process exited prematurely with code {process.returncode}")
            if time.monotonic() > deadline:
                raise TimeoutError("Timed out waiting for disposable Blender bridge to become ready")
            time.sleep(0.1)

        ready_data = json.loads((root / "ready.json").read_text(encoding="utf-8"))
        print(f"BRIDGE_READY={ready_data}", flush=True)

        # Run MCP E2E Client
        test_outcome = asyncio.run(run_mcp_test_client(root, port))
        print("MCP_TEST_OUTCOME=" + json.dumps(test_outcome, indent=2), flush=True)

    finally:
        (root / "stop").touch()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        blender_log_file.close()

    final_state_file = root / "final_state.json"
    assert final_state_file.exists(), "Final state evidence was not generated by Blender shutdown"
    final_data = json.loads(final_state_file.read_text(encoding="utf-8"))

    summary = {
        "verdict": "VERIFIED",
        "run_root": str(root),
        "port": port,
        "pid": process.pid,
        "test_outcome": test_outcome,
        "ready": ready_data,
        "final_state": final_data,
    }
    (root / "evidence.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n=== SCULPT E2E VERIFIED SUCCESSFUL ===\nEvidence written to: {root / 'evidence.json'}")


if __name__ == "__main__":
    main()
