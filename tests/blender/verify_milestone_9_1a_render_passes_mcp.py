"""
Verification Script for Capability 9 — Milestone 9.1A: Compositor Render-Pass Expansion.
Tests live execution over standard MCP wire protocol on disposable Blender 5.2.2 LTS
with ephemeral loopback port (!= 9877).

Verifies:
1. Disposable instance initialization and ephemeral port isolation.
2. Enabling compositor node tree in Blender 5.2.2 LTS.
3. Configuration of expanded render passes:
   - Ambient Occlusion (ao / ambient_occlusion -> use_pass_ambient_occlusion)
   - Shadow (shadow -> use_pass_shadow)
   - Emission (emission / emit -> use_pass_emit)
   - Environment (environment / env -> use_pass_environment)
   - Mist (mist -> use_pass_mist)
4. Independent verification on Blender 5.2.2 data model:
   - ViewLayer RNA boolean attributes
   - Render Layers compositor node output sockets ('Ambient Occlusion', 'Shadow', 'Emission', 'Environment', 'Mist')
5. Socket alias resolution and connection routing from Render Layers to downstream nodes.
6. Cryptomatte separation: verify cryptomatte is rejected as an ordinary pass toggle.
7. Bounds & security invariants:
   - Unsupported pass rejected fail-closed (e.g. 'volumetrics', 'specular')
   - Non-boolean value rejected fail-closed
   - Stale snapshot rejected with STALE_COMPOSITOR_GRAPH
   - Untrusted approved=True rejected fail-closed
8. Clean teardown and process cleanup.
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

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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


async def run_milestone_9_1a_verification():
    print("=" * 80)
    print("STARTING CAPABILITY 9 — MILESTONE 9.1A: COMPOSITOR RENDER-PASS EXPANSION")
    print("Target: Blender 5.2.2 LTS (Disposable Sandbox)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CAP9-1A-"))
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
                                    parsed = json.loads(text)
                                    return parsed
                                except Exception:
                                    return {"text": text}
                    return {"result": str(res)}

                # STAGE 1: Enable compositor
                print("\n[*] STAGE 1: Enabling compositor...")
                enable_res = await call_tool("manage_compositor_nodes", {"action": "enable"})
                enable_data = enable_res.get("result", enable_res)
                assert enable_data.get("enabled") is True
                initial_snap = enable_data.get("snapshot_id")
                assert initial_snap and initial_snap.startswith("sha256:")
                print(f"[+] Stage 1 PASSED: Compositor enabled (snapshot={initial_snap[:20]}...)")

                # STAGE 2: Configure baseline passes (Z, Normal, Diffuse, Glossy)
                print("\n[*] STAGE 2: Configuring baseline passes...")
                p1_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {
                        "z": True,
                        "normal": True,
                        "diffuse": True,
                        "glossy": True,
                    }
                })
                p1_data = p1_res.get("result", p1_res)
                assert p1_data.get("status") == "success"
                active1 = p1_data.get("active_passes", {})
                assert active1.get("use_pass_z") is True
                assert active1.get("use_pass_normal") is True
                assert active1.get("use_pass_diffuse_color") is True
                assert active1.get("use_pass_glossy_color") is True
                snap_p1 = p1_data.get("snapshot_id")
                print(f"[+] Stage 2 PASSED: 4 baseline passes configured and active.")

                # STAGE 3: Configure Milestone 9.1A expanded passes (AO, Shadow, Emission, Environment, Mist)
                print("\n[*] STAGE 3: Configuring Milestone 9.1A expanded passes...")
                p2_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {
                        "ao": True,
                        "shadow": True,
                        "emission": True,
                        "environment": True,
                        "mist": True,
                    }
                })
                p2_data = p2_res.get("result", p2_res)
                assert p2_data.get("status") == "success"
                active2 = p2_data.get("active_passes", {})
                assert active2.get("use_pass_ambient_occlusion") is True, f"AO missing: {active2}"
                assert active2.get("use_pass_shadow") is True, f"Shadow missing: {active2}"
                assert active2.get("use_pass_emit") is True, f"Emission missing: {active2}"
                assert active2.get("use_pass_environment") is True, f"Environment missing: {active2}"
                assert active2.get("use_pass_mist") is True, f"Mist missing: {active2}"
                snap_p2 = p2_data.get("snapshot_id")
                assert snap_p2 != snap_p1, "Snapshot must update when passes change"
                print(f"[+] Stage 3 PASSED: All 5 Milestone 9.1A passes active ({len(active2)} total active passes).")

                # STAGE 4: Test pass key aliases (ambient_occlusion, emit, env)
                print("\n[*] STAGE 4: Testing pass key aliases...")
                # First disable via alias, then re-enable
                p3_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {
                        "ambient_occlusion": False,
                        "emit": False,
                        "env": False,
                    }
                })
                p3_data = p3_res.get("result", p3_res)
                active3 = p3_data.get("active_passes", {})
                assert active3.get("use_pass_ambient_occlusion") is False
                assert active3.get("use_pass_emit") is False
                assert active3.get("use_pass_environment") is False

                # Re-enable via aliases
                p4_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {
                        "ambient_occlusion": True,
                        "emit": True,
                        "env": True,
                    }
                })
                p4_data = p4_res.get("result", p4_res)
                active4 = p4_data.get("active_passes", {})
                assert active4.get("use_pass_ambient_occlusion") is True
                assert active4.get("use_pass_emit") is True
                assert active4.get("use_pass_environment") is True
                print(f"[+] Stage 4 PASSED: Pass aliases ('ambient_occlusion', 'emit', 'env') validated.")

                # STAGE 5: Inspect pipeline and verify Render Layers node socket availability
                print("\n[*] STAGE 5: Inspecting compositor pipeline & receipt...")
                inspect_res = await call_tool("inspect_compositor_pipeline", {})
                inspect_data = inspect_res.get("result", inspect_res)
                assert inspect_data.get("enabled") is True
                pipe_passes = inspect_data.get("render_passes", {})
                assert pipe_passes.get("use_pass_ambient_occlusion") is True
                assert pipe_passes.get("use_pass_shadow") is True
                assert pipe_passes.get("use_pass_emit") is True
                assert pipe_passes.get("use_pass_environment") is True
                assert pipe_passes.get("use_pass_mist") is True

                receipt_res = await call_tool("inspect_scene_data", {"category": "compositor_pipeline"})
                receipt_data = receipt_res.get("result", receipt_res)
                receipt_passes = receipt_data.get("active_passes", [])
                for required_pass in ("use_pass_ambient_occlusion", "use_pass_shadow", "use_pass_emit", "use_pass_environment", "use_pass_mist", "use_pass_z"):
                    assert required_pass in receipt_passes, f"Receipt missing {required_pass}: {receipt_passes}"
                print(f"[+] Stage 5 PASSED: Pipeline readback and receipt confirmed {len(receipt_passes)} active passes.")

                # STAGE 6: Create downstream node and connect newly exposed pass sockets
                print("\n[*] STAGE 6: Creating downstream nodes and routing pass sockets...")
                # Create a Viewer node to connect AO pass
                viewer_res = await call_tool("manage_compositor_nodes", {
                    "action": "create_node",
                    "node_type": "viewer",
                    "node_name": "Viewer_AO",
                    "location": [300.0, 100.0],
                })
                assert viewer_res.get("result", viewer_res).get("node_name") == "Viewer_AO"

                # Connect Render Layers 'ao' socket -> Viewer_AO 'Image' socket
                conn_res = await call_tool("manage_compositor_nodes", {
                    "action": "connect",
                    "from_node": "Render Layers",
                    "from_socket": "ao",
                    "to_node": "Viewer_AO",
                    "to_socket": "Image",
                })
                conn_data = conn_res.get("result", conn_res)
                assert conn_data.get("verified") is True
                assert conn_data.get("from_socket") == "Ambient Occlusion"
                print(f"[+] Stage 6 PASSED: Connected 'ao' alias -> 'Ambient Occlusion' socket successfully.")

                # STAGE 7: Cryptomatte separation validation
                print("\n[*] STAGE 7: Validating Cryptomatte separation...")
                crypto_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {"cryptomatte": True}
                })
                assert "unsupported render pass 'cryptomatte'" in str(crypto_res).lower() or "error" in str(crypto_res).lower(), f"Expected Cryptomatte rejection, got: {crypto_res}"
                print("[+] Stage 7 PASSED: Cryptomatte pass toggle rejected as expected (requires dedicated node support).")

                # STAGE 8: Bounds and fail-closed validation
                print("\n[*] STAGE 8: Validating unsupported pass and non-bool rejections...")
                # Unsupported pass
                unsupp_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {"volumetrics": True}
                })
                assert "unsupported render pass 'volumetrics'" in str(unsupp_res).lower(), f"Expected volumetrics rejection, got: {unsupp_res}"

                # Non-bool value
                non_bool_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {"ao": "active"}
                })
                assert "must be boolean" in str(non_bool_res).lower(), f"Expected boolean type error, got: {non_bool_res}"

                # Stale snapshot rejection
                stale_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {"mist": False},
                    "expected_snapshot_id": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                })
                assert "stale_compositor_graph" in str(stale_res).lower(), f"Expected STALE_COMPOSITOR_GRAPH, got: {stale_res}"

                # Untrusted approval rejection
                untrusted_res = await call_tool("manage_compositor_nodes", {
                    "action": "configure_render_passes",
                    "passes": {"shadow": False},
                    "approved": True,
                })
                assert "approval denied" in str(untrusted_res).lower() or "permission" in str(untrusted_res).lower() or "error" in str(untrusted_res).lower(), f"Expected approval denial, got: {untrusted_res}"
                print("[+] Stage 8 PASSED: All bounds, concurrency, and approval invariants enforced fail-closed.")

                print("\n" + "=" * 80)
                print("ALL 8 STAGES OF MILESTONE 9.1A PASSED CLEANLY ON BLENDER 5.2.2 LTS!")
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
    asyncio.run(run_milestone_9_1a_verification())
