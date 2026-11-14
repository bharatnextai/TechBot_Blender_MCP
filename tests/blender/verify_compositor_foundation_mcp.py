"""
Automated Real MCP-to-Blender E2E Verification of Compositor Pipelines Foundation (Phase 2.1 - v0.1.74).
Covers Compositor Pipelines (Phase 2.1):
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy.
3. Discover Compositor tools over MCP stdio wire:
   - manage_compositor_nodes
   - configure_compositor
   - manage_compositor
   - inspect_compositor_pipeline
   - inspect_scene_data (compositor_pipeline, compositor_settings)
   - render_scene
4. Live execution and independent Blender readback:
   - Scene setup: primitive Cube, Camera, Point Light
   - Action 'enable': initialize compositing node group
   - Action 'inspect': read initial default node graph
   - Action 'configure_render_passes': enable Z, Normal, Diffuse, Glossy passes
   - Action 'create_node': add Denoise node (CompositorNodeDenoise)
   - Action 'create_node': add Glare node (CompositorNodeGlare)
   - Action 'set_property': configure Glare type to 'Fog Glow' and threshold to 0.8
   - Action 'connect': link Render Layers -> Denoise -> Glare -> Group Output
   - Action 'inspect': independent readback of nodes and links
   - Execute still render with active compositor pipeline -> verify image file written
   - Inspect composite receipt via inspect_scene_data(category="compositor_pipeline")
   - Action 'remove_node': safely remove node and verify graph consistency
5. Concurrency, security, and whitelist bounds:
   - Stale snapshot rejected with STALE_COMPOSITOR_GRAPH
   - Untrusted approved=True rejected fail-closed
   - Unwhitelisted node type rejected fail-closed
6. Teardown and clean process cleanup.
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
    print("STARTING REAL MCP-TO-BLENDER E2E: COMPOSITOR PIPELINES (Phase 2.1 - v0.1.74)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-COMP-"))
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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "compositor_v1"
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

        print("[*] Connecting Stdio MCP client to server...")
        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.")

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

                # 1. Discover tools
                tools_list = await session.list_tools()
                discovered_names = {t.name for t in tools_list.tools}
                for req_tool in ("manage_compositor_nodes", "configure_compositor", "manage_compositor", "inspect_compositor_pipeline", "inspect_scene_data", "render_scene"):
                    assert req_tool in discovered_names, f"Tool '{req_tool}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all compositor tools present.")

                # 2. Stage 1: Setup scene geometry (cube, camera, light)
                cube_res = await call_tool("create_primitive", {"primitive_type": "cube", "name": "Cube_Target"})
                assert cube_res.get("result", cube_res).get("name") == "Cube_Target"

                cam_res = await call_tool("create_camera", {
                    "name": "Camera_Main",
                    "location": [0.0, -5.0, 2.0],
                    "rotation_euler": [1.2, 0.0, 0.0],
                    "set_active": True,
                })
                assert cam_res.get("result", cam_res).get("name") == "Camera_Main"

                light_res = await call_tool("create_light", {
                    "name": "Light_Point",
                    "light_type": "POINT",
                    "energy": 500.0,
                    "location": [2.0, -2.0, 4.0],
                })
                assert light_res.get("result", light_res).get("name") == "Light_Point"
                print("[+] Stage 1: Scene Geometry Created (Cube, Camera, Light): success")

                # 3. Stage 2: Enable compositor
                enable_res = await call_tool("manage_compositor_nodes", {"action": "enable"})
                enable_data = enable_res.get("result", enable_res)
                assert enable_data.get("enabled") is True
                initial_snap = enable_data.get("snapshot_id")
                assert initial_snap and initial_snap.startswith("sha256:")
                print(f"[+] Stage 2: Compositor Enabled: success (snapshot={initial_snap[:18]}...)")

                # 4. Stage 3: Inspect initial compositor state
                inspect_init = await call_tool("inspect_compositor_pipeline", {})
                inspect_init_data = inspect_init.get("result", inspect_init)
                assert inspect_init_data.get("enabled") is True
                assert inspect_init_data.get("node_count", 0) > 0
                print(f"[+] Stage 3: Inspected Pipeline: {inspect_init_data.get('node_count')} initial nodes found.")

                # 5. Stage 4: Configure render passes (Z, Normal, Diffuse, Glossy)
                pass_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {
                        "z": True,
                        "normal": True,
                        "diffuse": True,
                        "glossy": True,
                    }
                })
                pass_data = pass_res.get("result", pass_res)
                active_passes = pass_data.get("active_passes", {})
                assert active_passes.get("use_pass_z") is True
                assert active_passes.get("use_pass_normal") is True
                assert active_passes.get("use_pass_diffuse_color") is True
                assert active_passes.get("use_pass_glossy_color") is True
                post_pass_snap = pass_data.get("snapshot_id")
                print(f"[+] Stage 4: Configured Render Passes (Z, Normal, Diffuse, Glossy): verified")

                # 6. Stage 5: Create Denoise node
                denoise_res = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "denoise",
                    "node_name": "MyDenoise",
                    "location": [200.0, 200.0],
                })
                denoise_data = denoise_res.get("result", denoise_res)
                assert denoise_data.get("node_name") == "MyDenoise"
                assert denoise_data.get("node_type") == "CompositorNodeDenoise"
                print("[+] Stage 5: Created Denoise Node 'MyDenoise': success")

                # 7. Stage 6: Create Glare node
                glare_res = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "glare",
                    "node_name": "MyGlare",
                    "location": [400.0, 200.0],
                })
                glare_data = glare_res.get("result", glare_res)
                assert glare_data.get("node_name") == "MyGlare"
                assert glare_data.get("node_type") == "CompositorNodeGlare"
                print("[+] Stage 6: Created Glare Node 'MyGlare': success")

                # 8. Stage 7: Set properties on Glare node
                prop_type_res = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "MyGlare",
                    "property_name": "type",
                    "property_value": "Fog Glow",
                })
                assert prop_type_res.get("result", prop_type_res).get("verified") is True

                prop_thresh_res = await call_tool("manage_compositor_nodes", {
                    "action": "set_property",
                    "node_name": "MyGlare",
                    "property_name": "threshold",
                    "property_value": 0.8,
                })
                assert prop_thresh_res.get("result", prop_thresh_res).get("verified") is True
                print("[+] Stage 7: Configured Glare Properties (type='Fog Glow', threshold=0.8): success")

                # 9. Stage 8: Connect nodes (RLayers -> MyDenoise -> MyGlare -> Group Output)
                # Render Layers -> Denoise
                c1_res = await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "Image",
                    "to_node": "MyDenoise",
                    "to_socket": "Image",
                })
                assert c1_res.get("result", c1_res).get("verified") is True

                # Denoise -> Glare
                c2_res = await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "MyDenoise",
                    "from_socket": "Image",
                    "to_node": "MyGlare",
                    "to_socket": "Image",
                })
                assert c2_res.get("result", c2_res).get("verified") is True

                # Glare -> Group Output
                c3_res = await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "MyGlare",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })
                assert c3_res.get("result", c3_res).get("verified") is True
                print("[+] Stage 8: Pipeline Connected (Render Layers -> Denoise -> Glare -> Group Output): verified")

                # 10. Stage 9: Independent pipeline readback
                inspect_pipe = await call_tool("inspect_compositor_pipeline", {})
                pipe_data = inspect_pipe.get("result", inspect_pipe)
                node_names = [n["name"] for n in pipe_data.get("nodes", [])]
                assert "MyDenoise" in node_names
                assert "MyGlare" in node_names
                links = pipe_data.get("links", [])
                assert any(l["from_node"] == "MyDenoise" and l["to_node"] == "MyGlare" for l in links)
                assert any(l["from_node"] == "MyGlare" and l["to_node"] == "Group Output" for l in links)
                current_pipeline_snap = pipe_data.get("snapshot_id")
                print(f"[+] Stage 9: Independent Graph Readback: {len(node_names)} nodes, {len(links)} links verified.")

                # 11. Stage 10: Render Scene Still through Compositor Pipeline
                render_out_path = str(run_root / "compositor_render_result.png")
                render_res = await call_tool("render_scene", {
                    "render_mode": "still",
                    "output_path": render_out_path,
                    "output_format": "PNG",
                })
                render_data = render_res.get("result", render_res)
                assert Path(render_out_path).exists(), f"Rendered image not found at {render_out_path}"
                file_size = Path(render_out_path).stat().st_size
                assert file_size > 1000, f"Rendered file too small: {file_size} bytes"
                print(f"[+] Stage 10: Still Render Executed via Compositor Pipeline: file created ({file_size} bytes)")

                # 12. Stage 11: Inspect composite receipt via inspect_scene_data
                receipt_res = await call_tool("inspect_scene_data", {"category": "compositor_pipeline"})
                receipt_data = receipt_res.get("result", receipt_res)
                assert receipt_data.get("composite_output_connected") is True
                assert len(receipt_data.get("active_passes", [])) >= 4
                print("[+] Stage 11: Compositor Receipt Verified: composite_output_connected=True, passes verified.")

                # 13. Stage 12: Remove Glare node and reconnect Denoise -> Group Output
                remove_res = await call_tool("manage_compositor_nodes", {
                    "action": "remove_node",
                    "node_name": "MyGlare",
                })
                remove_data = remove_res.get("result", remove_res)
                assert remove_data.get("removed_node_name") == "MyGlare"

                # Reconnect Denoise -> Group Output
                reconn_res = await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "MyDenoise",
                    "from_socket": "Image",
                    "to_node": "Group Output",
                    "to_socket": "Image",
                })
                assert reconn_res.get("result", reconn_res).get("verified") is True

                post_rem_inspect = await call_tool("inspect_compositor_pipeline", {})
                post_rem_nodes = [n["name"] for n in post_rem_inspect.get("result", post_rem_inspect).get("nodes", [])]
                assert "MyGlare" not in post_rem_nodes
                latest_snap = post_rem_inspect.get("result", post_rem_inspect).get("snapshot_id")
                print("[+] Stage 12: Node Removal and Reconnection: verified")

                # 14. Stage 13: Concurrency Stale-State Protection Check
                stale_res = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "blur",
                    "expected_snapshot_id": "sha256:stale_fake_hash_1234567890abcdef",
                })
                assert "stale_compositor_graph" in str(stale_res).lower(), f"Expected STALE_COMPOSITOR_GRAPH, got: {stale_res}"
                print("[+] Stage 13: Stale Snapshot Rejected with STALE_COMPOSITOR_GRAPH: verified")

                # 15. Stage 14: Security Fail-Closed on Untrusted approved=True
                sec_res = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "blur",
                    "approved": True,  # Untrusted flag must be rejected
                })
                assert "error" in str(sec_res).lower() or "denied" in str(sec_res).lower(), f"Expected approval denial, got: {sec_res}"
                print("[+] Stage 14: Untrusted approved=True Rejected Fail-Closed: verified")

                # 16. Stage 15: Whitelist Enforcement Check
                invalid_node_res = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "CompositorNodeBilateralblur",
                })
                assert "unsupported compositor node type" in str(invalid_node_res).lower(), f"Expected unwhitelisted rejection, got: {invalid_node_res}"
                print("[+] Stage 15: Unwhitelisted Node Rejected Fail-Closed: verified")

                print("=" * 80)
                print("ALL 15 E2E COMPOSITOR STAGES PASSED CLEANLY ON BLENDER 5.2.2 LTS!")
                print("=" * 80)

    finally:
        print("[*] Tearing down disposable Blender process...")
        (run_root / "stop.flag").touch()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        print("[+] Disposable process cleaned up cleanly.")


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
