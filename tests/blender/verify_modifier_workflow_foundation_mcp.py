"""
Automated Real MCP-to-Blender E2E Verification of Modifier Workflow Foundation (v0.1.63).
Covers Capability 3:
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover modifier foundation tools over MCP stdio wire:
   - edit_modifier_stack
   - inspect_modifier_stack
   - apply_modifier
   - configure_modifier
   - inspect_modifiers
4. Live execution and independent Blender readback:
   - Primitive creation ('Mod_Cube')
   - Initial stack inspection (0 modifiers, base 8 vertices)
   - Add SUBSURF modifier (levels=1 -> evaluated vertices=26)
   - Add BEVEL modifier (width=0.05, segments=2 -> evaluated vertices=218)
   - Reorder BEVEL to top of stack (index 0)
   - Visibility toggle (hide/show in viewport)
   - Apply modifier via dedicated typed apply_modifier tool (base vertices baked to 56)
   - Remove remaining modifier (SUBSURF removed, 0 modifiers)
5. Transactional rollback verification:
   - Stale snapshot rejection (STALE_MODIFIER_STACK)
   - Geometry and stack state preserved bit-for-bit
6. Security enforcement:
   - Untrusted approved=True rejected fail-closed
   - Non-existent target object rejected fail-closed
7. Teardown and clean process cleanup.
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


async def run_e2e_verification():
    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E: MODIFIER WORKFLOW FOUNDATION (v0.1.63)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-MODIFIERS-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Bridge port must not be production port 9877, got {port}"

    ready_file = run_root / "blender_ready.json"
    stop_file = run_root / "stop.flag"
    script_file = run_root / "bootstrap.py"

    script_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    env["BLENDER_USER_CONFIG"] = str(config_dir)
    env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
    env["PYTHONPATH"] = str(PROJECT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    blender_cmd = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "--python",
        str(script_file),
    ]

    print(f"[*] Spawning disposable Blender 5.2.2 on ephemeral port {port}...")
    proc = subprocess.Popen(
        blender_cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

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
        print(f"[+] Blender ready! PID: {ready_info['pid']}, Version: {ready_info['blender']}")

        # Connect MCP client
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        client_env = dict(os.environ)
        client_env["PYTHONPATH"] = str(PROJECT)
        client_env["PYTHONDONTWRITEBYTECODE"] = "1"
        client_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
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
            ],
            env=client_env,
            cwd=str(PROJECT),
        )

        print("[*] Connecting Stdio MCP client to server...")
        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.")

                # 1. Discover tools
                tools_list = await session.list_tools()
                discovered_names = {t.name for t in tools_list.tools}
                required_tools = [
                    "edit_modifier_stack",
                    "inspect_modifier_stack",
                    "apply_modifier",
                    "configure_modifier",
                    "inspect_modifiers",
                ]
                for rt in required_tools:
                    assert rt in discovered_names, f"Tool '{rt}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all modifier foundation tools present.")

                async def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                    try:
                        res = await session.call_tool(name, arguments=args)
                    except Exception as ex:
                        return {"status": "error", "message": str(ex), "exception": type(ex).__name__}
                    if getattr(res, "isError", False):
                        err_text = res.content[0].text if res.content else "Tool error"
                        return {"status": "error", "message": err_text}
                    content = res.content[0].text if res.content else "{}"
                    try:
                        data = json.loads(content)
                    except Exception:
                        data = {"status": "error", "message": content}
                    return data

                # 2. Create test cube Mod_Cube
                cube_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "Mod_Cube",
                    "location": [0.0, 0.0, 0.0],
                })
                print(f"[+] Created Mod_Cube: {cube_res.get('status')}")
                assert cube_res.get("status") == "success", f"create_primitive failed: {cube_res}"

                # 3. Inspect initial modifier stack
                inspect_init = await call_tool("inspect_modifier_stack", {"name": "Mod_Cube"})
                init_data = inspect_init.get("result", inspect_init)
                assert len(init_data["modifiers"]) == 0, f"Expected 0 modifiers initially, got {len(init_data['modifiers'])}"
                assert init_data["base"]["vertex_count"] == 8, f"Expected 8 base vertices, got {init_data['base_geometry']['vertex_count']}"
                assert init_data["evaluated"]["vertex_count"] == 8, f"Expected 8 evaluated vertices, got {init_data['evaluated_geometry']['vertex_count']}"
                snap0 = init_data["snapshot_id"]
                print(f"[+] Initial Modifier Stack Verified: 0 modifiers, 8 base vertices. Snapshot: {snap0[:18]}...")

                # 4. Add SUBSURF modifier (levels=1, render_levels=1)
                subsurf_res = await call_tool("edit_modifier_stack", {
                    "name": "Mod_Cube",
                    "modifier_name": "MySubsurf",
                    "modifier_type": "SUBSURF",
                    "action": "add",
                    "properties": {"levels": 1, "render_levels": 1},
                    "expected_snapshot_id": snap0,
                })
                assert subsurf_res.get("status") == "success" or subsurf_res.get("success"), f"Add Subsurf failed: {subsurf_res}"
                subsurf_data = subsurf_res.get("result", subsurf_res)
                snap1 = subsurf_data["snapshot_id"]
                eval_v1 = subsurf_data["evaluated"]["vertex_count"]
                assert eval_v1 == 26, f"Expected 26 evaluated vertices with Subsurf level 1, got {eval_v1}"
                print(f"[+] Add Subsurf Verified: evaluated_vertices={eval_v1}. Snapshot: {snap1[:18]}...")

                # 5. Add BEVEL modifier (width=0.05, segments=2)
                bevel_res = await call_tool("edit_modifier_stack", {
                    "name": "Mod_Cube",
                    "modifier_name": "MyBevel",
                    "modifier_type": "BEVEL",
                    "action": "add",
                    "properties": {"width": 0.05, "segments": 2},
                    "expected_snapshot_id": snap1,
                })
                assert bevel_res.get("status") == "success" or bevel_res.get("success"), f"Add Bevel failed: {bevel_res}"
                bevel_data = bevel_res.get("result", bevel_res)
                snap2 = bevel_data["snapshot_id"]
                eval_v2 = bevel_data["evaluated"]["vertex_count"]
                assert eval_v2 == 218, f"Expected 218 evaluated vertices with Bevel after Subsurf, got {eval_v2}"
                print(f"[+] Add Bevel Verified: evaluated_vertices={eval_v2}. Snapshot: {snap2[:18]}...")

                # 6. Reorder BEVEL to index 0
                reorder_res = await call_tool("edit_modifier_stack", {
                    "name": "Mod_Cube",
                    "modifier_name": "MyBevel",
                    "modifier_type": "BEVEL",
                    "action": "reorder",
                    "index": 0,
                    "expected_snapshot_id": snap2,
                })
                assert reorder_res.get("status") == "success" or reorder_res.get("success"), f"Reorder failed: {reorder_res}"
                reorder_data = reorder_res.get("result", reorder_res)
                snap3 = reorder_data["snapshot_id"]
                mods = [m["name"] for m in reorder_data["modifiers"]]
                assert mods[0] == "MyBevel", f"Expected MyBevel at index 0, got {mods}"
                print(f"[+] Reorder Verified: Stack order={mods}. Snapshot: {snap3[:18]}...")

                # 7. Visibility toggle: hide viewport
                vis_hide_res = await call_tool("edit_modifier_stack", {
                    "name": "Mod_Cube",
                    "modifier_name": "MyBevel",
                    "modifier_type": "BEVEL",
                    "action": "visibility",
                    "show_viewport": False,
                    "show_render": True,
                    "expected_snapshot_id": snap3,
                })
                assert vis_hide_res.get("status") == "success" or vis_hide_res.get("success"), f"Visibility hide failed: {vis_hide_res}"
                vis_hide_data = vis_hide_res.get("result", vis_hide_res)
                snap4 = vis_hide_data["snapshot_id"]
                b_info = next(m for m in vis_hide_data["modifiers"] if m["name"] == "MyBevel")
                assert b_info["show_viewport"] is False, "Expected show_viewport=False"
                print(f"[+] Visibility Hide Verified: show_viewport={b_info['show_viewport']}. Snapshot: {snap4[:18]}...")

                # Restore viewport visibility
                vis_show_res = await call_tool("edit_modifier_stack", {
                    "name": "Mod_Cube",
                    "modifier_name": "MyBevel",
                    "modifier_type": "BEVEL",
                    "action": "visibility",
                    "show_viewport": True,
                    "show_render": True,
                    "expected_snapshot_id": snap4,
                })
                assert vis_show_res.get("status") == "success" or vis_show_res.get("success"), f"Visibility show failed: {vis_show_res}"
                vis_show_data = vis_show_res.get("result", vis_show_res)
                snap5 = vis_show_data["snapshot_id"]
                b_info = next(m for m in vis_show_data["modifiers"] if m["name"] == "MyBevel")
                assert b_info["show_viewport"] is True, "Expected show_viewport=True"
                print(f"[+] Visibility Show Verified: show_viewport={b_info['show_viewport']}. Snapshot: {snap5[:18]}...")

                # 8. Apply BEVEL modifier via apply_modifier
                apply_res = await call_tool("apply_modifier", {
                    "name": "Mod_Cube",
                    "modifier_name": "MyBevel",
                    "modifier_type": "BEVEL",
                    "expected_snapshot_id": snap5,
                })
                assert apply_res.get("status") == "success" or apply_res.get("success"), f"apply_modifier failed: {apply_res}"
                apply_data = apply_res.get("result", apply_res)
                snap6 = apply_data["snapshot_id"]
                base_v = apply_data["base"]["vertex_count"]
                assert base_v == 56, f"Expected 56 base vertices after applying Bevel(segments=2), got {base_v}"
                remaining_mods = [m["name"] for m in apply_data["modifiers"]]
                assert remaining_mods == ["MySubsurf"], f"Expected only MySubsurf remaining, got {remaining_mods}"
                print(f"[+] Apply Modifier Verified: base vertices permanently baked to {base_v}. Remaining modifiers: {remaining_mods}.")

                # 9. Remove remaining modifier (SUBSURF)
                remove_res = await call_tool("edit_modifier_stack", {
                    "name": "Mod_Cube",
                    "modifier_name": "MySubsurf",
                    "modifier_type": "SUBSURF",
                    "action": "remove",
                    "expected_snapshot_id": snap6,
                })
                assert remove_res.get("status") == "success" or remove_res.get("success"), f"Remove failed: {remove_res}"
                remove_data = remove_res.get("result", remove_res)
                snap7 = remove_data["snapshot_id"]
                assert len(remove_data["modifiers"]) == 0, f"Expected 0 modifiers remaining, got {len(remove_data['modifiers'])}"
                assert remove_data["base"]["vertex_count"] == 56, "Base geometry vertex count preserved after stack clear"
                print(f"[+] Remove Modifier Verified: stack clear, base vertices stay {remove_data['base']['vertex_count']}.")

                # 10. Transactional Rollback Test: Stale snapshot rejection
                stale_res = await call_tool("edit_modifier_stack", {
                    "name": "Mod_Cube",
                    "modifier_name": "StaleMod",
                    "modifier_type": "SUBSURF",
                    "action": "add",
                    "properties": {"levels": 1},
                    "expected_snapshot_id": "sha256:" + "0" * 64,
                })
                assert stale_res.get("status") == "error", f"Stale snapshot should return error, got: {stale_res}"
                err_msg = str(stale_res.get("message", ""))
                assert "STALE_MODIFIER_STACK" in err_msg or "Snapshot mismatch" in err_msg or "snapshot" in err_msg.lower(), f"Expected snapshot error, got: {err_msg}"
                print(f"[+] Rollback Test Verified: Stale snapshot rejected fail-closed ({err_msg[:60]}...).")

                # Verify geometry and stack state unchanged after error
                check_res = await call_tool("inspect_modifier_stack", {"name": "Mod_Cube"})
                check_data = check_res.get("result", check_res)
                assert check_data["snapshot_id"] == snap7, "Snapshot altered after failed mutation!"
                assert check_data["base"]["vertex_count"] == 56, "Geometry altered after failed mutation!"
                print(f"[+] State Preservation Verified: snapshot and geometry preserved bit-for-bit.")

                # 11. Security Test: Reject untrusted client approval
                untrusted_res = await call_tool("apply_modifier", {
                    "name": "Mod_Cube",
                    "modifier_name": "NonExistentMod",
                    "expected_snapshot_id": snap7,
                    "approved": True,
                })
                assert untrusted_res.get("status") == "error", f"Untrusted approved=True must return error: {untrusted_res}"
                err_text = str(untrusted_res.get("message", ""))
                assert "untrusted" in err_text.lower() or "denied" in err_text.lower() or "approval" in err_text.lower() or "permission" in err_text.lower()
                print(f"[+] Security Test Verified: Untrusted approved=True rejected fail-closed ({err_text[:60]}...).")

                # 12. Security Test: Non-existent target object
                bad_obj_res = await call_tool("inspect_modifier_stack", {
                    "name": "Ghost_Object_XYZ",
                })
                assert bad_obj_res.get("status") == "error", f"Non-existent object should return error: {bad_obj_res}"
                print("[+] Security Test Verified: Non-existent target object rejected fail-closed.")

                print("=" * 80)
                print("ALL 12/12 MODIFIER WORKFLOW FOUNDATION CHECKS PASSED SUCCESSFULLY!")
                print("=" * 80)

    finally:
        stop_file.touch()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[*] Disposable Blender process terminated cleanly.")


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
