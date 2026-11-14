"""
Live Isolated Acceptance Runner for Agent Manager E2E (Tests 01-08)
Safely runs tests against a disposable Blender 5.2.2 instance on an ephemeral port.
Guarantees:
- Never touches production port 9877 or the Dragon scene.
- Uses --factory-startup with disposable user configuration.
- Bridge approval registry auto-resolves test requests on the main thread timer.
- Clean shutdown and process termination.
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
import unittest

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PYTHON = Path(sys.executable)

bootstrap_code = r"""
import bpy, json, os, sys, time
from pathlib import Path

root = Path(os.environ["UMCP_RUN_ROOT"])
project = Path(os.environ["UMCP_PROJECT"])
sys.path.insert(0, str(project))
import blender_addon.universal_mcp as addon
addon.register()

from blender_addon.universal_mcp.operators import get_server_instance
from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry

port = int(os.environ["UMCP_BRIDGE_PORT"])
scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

def auto_approve_timer():
    try:
        registry = get_approval_registry()
        for req in list(registry.get_pending_requests()):
            registry.resolve_request(req.request_id, "approved", reason="DISPOSABLE_TEST_AUTO_APPROVE")
    except Exception:
        pass
    return 0.05

bpy.app.timers.register(auto_approve_timer)

def observe():
    if (root / "stop").exists():
        server = get_server_instance(port)
        if server and server.running:
            server.stop()
        (root / "final_state.json").write_text(json.dumps({
            "pid": os.getpid(),
            "objects": sorted(bpy.data.objects.keys()),
            "bridge_running": bool(server.running) if server else False,
        }, indent=2), encoding="utf-8")
        bpy.ops.wm.quit_blender()
        return None
    return 0.1

bpy.app.timers.register(observe)

def start_bridge():
    try:
        bpy.ops.umcp.start_bridge()
        (root / "ready.json").write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")
    except Exception as exc:
        (root / "error.json").write_text(str(exc), encoding="utf-8")
    return None

bpy.app.timers.register(start_bridge, first_interval=0.2)
"""


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ping_bridge(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            payload = json.dumps({"command": "get_scene_summary", "params": {}}).encode("utf-8") + b"\n"
            s.sendall(payload)
            resp = b""
            while b"\n" not in resp:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
            data = json.loads(resp.decode("utf-8"))
            return data.get("status") == "success"
    except Exception:
        return False


def main():
    if not BLENDER.exists():
        print(f"Error: Blender executable not found at {BLENDER}")
        sys.exit(1)

    port = get_free_port()
    if port == 9877:
        port = get_free_port()
    print(f"[RUNNER] Allocating ephemeral port {port} (avoiding port 9877)")

    root = Path(tempfile.mkdtemp(prefix="UMCP-AGENT-E2E-"))
    print(f"[RUNNER] Isolated root: {root}")

    # Write bootstrap
    (root / "bootstrap.py").write_text(bootstrap_code, encoding="utf-8")
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "extensions").mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["UMCP_BRIDGE_HOST"] = "127.0.0.1"
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_RUN_ROOT"] = str(root)
    env["BLENDER_USER_CONFIG"] = str(root / "config")
    env["BLENDER_USER_SCRIPTS"] = str(root / "scripts")
    env["BLENDER_USER_EXTENSIONS"] = str(root / "extensions")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    cmd = [
        str(BLENDER),
        "--factory-startup",
        "--disable-autoexec",
        "-P", str(root / "bootstrap.py"),
    ]
    print(f"[RUNNER] Launching disposable Blender: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        deadline = time.time() + 15.0
        ready = False
        while time.time() < deadline:
            if (root / "ready.json").exists():
                ready = True
                break
            if proc.poll() is not None:
                out, err = proc.communicate()
                print(f"[RUNNER] Blender exited unexpectedly ({proc.returncode}):\n{err.decode('utf-8', errors='replace')}")
                sys.exit(1)
            time.sleep(0.2)

        if not ready:
            print("[RUNNER] Timed out waiting for Blender ready.json")
            sys.exit(1)

        # Confirm ping
        ping_ok = False
        for _ in range(30):
            if ping_bridge(port):
                ping_ok = True
                break
            time.sleep(0.1)

        if not ping_ok:
            print(f"[RUNNER] Failed to connect to bridge on ephemeral port {port}")
            sys.exit(1)

        print(f"[RUNNER] Bridge confirmed live and responsive on port {port}")

        # Run test suite
        test_env = dict(os.environ)
        test_env["UMCP_BRIDGE_PORT"] = str(port)
        test_env["PYTHONPATH"] = str(PROJECT)

        test_cmd = [
            str(PYTHON),
            "-m", "unittest",
            "tests.test_agent_manager_e2e_acceptance.AgentManagerE2EAcceptance",
            "-v",
        ]
        print(f"[RUNNER] Executing Agent Manager E2E acceptance suite: {' '.join(test_cmd)}")
        test_proc = subprocess.run(test_cmd, env=test_env, cwd=str(PROJECT))
        test_exit_code = test_proc.returncode

        print(f"[RUNNER] Test suite execution complete with returncode: {test_exit_code}")
        return test_exit_code

    finally:
        print("[RUNNER] Initiating graceful shutdown of disposable Blender instance...")
        (root / "stop").touch()
        try:
            proc.wait(timeout=10.0)
            print(f"[RUNNER] Disposable Blender process {proc.pid} terminated cleanly.")
        except subprocess.TimeoutExpired:
            print(f"[RUNNER] Blender did not quit in 10s, killing PID {proc.pid}...")
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    sys.exit(main())
