"""Read-only stdio MCP -> real TCP bridge -> real Blender baseline.

Uses a fresh factory child, never port 9877. No approval requests or mutation
tools. The background fixture pumps MainThreadQueue on its owning main thread;
this verifies wire transport, not Blender's interactive timer/UI event loop.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[2]


def fixture(root, port):
    import bpy
    sys.path.insert(0, str(PROJECT))
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    assert bpy.app.background and bpy.data.filepath == "" and port != 9877
    bpy.types.Scene.umcp_bridge_port = bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=True)
    bpy.context.scene.umcp_bridge_port = port
    bpy.context.scene.umcp_require_scene_mutation_approval = True
    def snapshot():
        return {"objects": {o.name: {"type": o.type, "matrix": [list(row) for row in o.matrix_world],
                "vertices": [list(v.co) for v in o.data.vertices] if o.type == "MESH" else None}
                for o in bpy.context.scene.objects}, "materials": sorted(bpy.data.materials.keys()),
                "world": bpy.context.scene.world.name if bpy.context.scene.world else None,
                "filepath": bpy.data.filepath, "dirty": bpy.data.is_dirty}
    before = snapshot()
    queue = MainThreadQueue(bpy)
    server = BridgeServer(port=port, queue=queue)
    server.start()
    (root / "ready.json").write_text(json.dumps({"pid": os.getpid(), "port": port, "version": bpy.app.version_string}))
    deadline = time.monotonic() + 90
    try:
        while not (root / "stop").exists() and time.monotonic() < deadline:
            queue.drain_queue()
            time.sleep(.01)
    finally:
        server.stop()
        after = snapshot()
        from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
        registry = get_approval_registry()
        requests = len(registry._requests)
        (root / "independent.json").write_text(json.dumps({"before": before, "after": after,
            "unchanged": before == after, "approval_requests": requests}, indent=2))
        assert before == after and requests == 0


async def inspect(root, port):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, PYTHONPATH=str(PROJECT), PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
    params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "mcp_service.app",
        "--transport", "stdio", "--bridge-host", "127.0.0.1", "--bridge-port", str(port),
        "--bridge-timeout", "10", "--approval-mode", "blender"], env=env, cwd=str(PROJECT))
    records = []
    with (root / "mcp.log").open("w", encoding="utf-8") as log:
        async with stdio_client(params, errlog=log) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize()
                catalog = await session.list_tools()
                names = {tool.name for tool in catalog.tools}
                required = {"get_scene_summary", "list_objects", "inspect_scene_data", "list_materials",
                            "get_task_status", "check_approval_status", "resolve_pending_approval",
                            "sculpt_mesh", "inspect_sculpt_state"}
                assert required <= names, sorted(required - names)
                (root / "catalog.json").write_text(catalog.model_dump_json(indent=2))
                for tool, args in [("get_scene_summary", {}), ("list_objects", {}), ("list_materials", {}),
                                   ("inspect_scene_data", {"category": "blender_info"}),
                                   ("inspect_scene_data", {"category": "render_settings"}),
                                   ("inspect_scene_data", {"category": "world_settings"}),
                                   ("inspect_scene_data", {"category": "uv_layers", "target_name": "Cube"}),
                                   ("inspect_sculpt_state", {"object_name": "Cube"})]:
                    response = await session.call_tool(tool, arguments=args)
                    record = {"tool": tool, "arguments": args, "response": response.model_dump(mode="json")}
                    records.append(record)
                    (root / "calls.json").write_text(json.dumps(records, indent=2))
                    assert not response.isError, record
                    payload = json.loads(response.content[0].text)
                    assert payload["status"] == "success", record
                return {"service": initialized.serverInfo.model_dump(), "tool_count": len(names),
                        "successful_read_only_calls": len(records)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default=r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
    parser.add_argument("--blender-fixture", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.blender_fixture:
        fixture(args.root, args.port)
        return
    root = Path(tempfile.mkdtemp(prefix="umcp-wire-readonly-"))
    print(str(root), flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
    env.pop("UMCP_LOCAL_TEST_ROOT", None)
    for key in ("CONFIG", "SCRIPTS", "EXTENSIONS", "DATAFILES", "RESOURCES"):
        directory = root / key.lower(); directory.mkdir()
        env["BLENDER_USER_" + key] = str(directory)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    assert port != 9877
    env["UMCP_BRIDGE_PORT"] = str(port)
    # Blender executes this bootstrap as a file and owns the only bpy thread.
    bootstrap = root / "bootstrap.py"
    bootstrap.write_text("import runpy,sys\nsys.argv=" + repr([str(Path(__file__).resolve()),
        "--blender-fixture", "--root", str(root), "--port", str(port)]) +
        "\nrunpy.run_path(" + repr(str(Path(__file__).resolve())) + ",run_name='__main__')\n")
    result = None
    with (root / "blender.log").open("w", encoding="utf-8") as log:
        child = subprocess.Popen([args.blender, "--background", "--factory-startup", "--disable-autoexec",
            "--python-exit-code", "1", "--python", str(bootstrap)], env=env, stdout=log, stderr=subprocess.STDOUT,
            cwd=str(PROJECT))
        try:
            deadline = time.monotonic() + 40
            while not (root / "ready.json").exists():
                assert child.poll() is None, "Fixture exited before ready; inspect blender.log"
                if time.monotonic() > deadline:
                    raise TimeoutError("Disposable bridge startup timed out")
                time.sleep(.1)
            result = asyncio.run(inspect(root, port))
        finally:
            (root / "stop").touch()
            child.wait(timeout=95)
    independent = json.loads((root / "independent.json").read_text())
    assert child.returncode == 0 and independent["unchanged"] and independent["approval_requests"] == 0
    result.update(blender=json.loads((root / "ready.json").read_text()), scene_preserved=True,
                  approval_requests=0, status="PASS", scope="read-only wire baseline only")
    result["fixture_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (root / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
