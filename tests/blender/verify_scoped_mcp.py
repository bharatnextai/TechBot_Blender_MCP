"""Approved isolated modifier/bake subset, actual stdio MCP/TCP/Blender path.

Local test tokens are not human-approval UI evidence. Main thread pumps queue.
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
    protected_objects = set(bpy.data.objects.keys())
    protected_materials = set(bpy.data.materials.keys())
    def snapshot():
        return {"objects": {o.name: {"type": o.type, "matrix": [list(row) for row in o.matrix_world],
                "vertices": [list(v.co) for v in o.data.vertices] if o.type == "MESH" else None}
                for o in bpy.context.scene.objects if o.name in protected_objects}, "materials": sorted(n for n in bpy.data.materials.keys() if n in protected_materials),
                "world": bpy.context.scene.world.name if bpy.context.scene.world else None,
                "filepath": bpy.data.filepath, "render_engine": bpy.context.scene.render.engine}
    before = snapshot()
    bpy.ops.mesh.primitive_cube_add()
    owned = bpy.context.object
    owned.name = "OwnedMesh"
    seeded = owned.modifiers.new("OwnedSubsurf", "SUBSURF")
    seeded.levels = 0
    seeded.render_levels = 0
    material = bpy.data.materials.new("OwnedMaterial")
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .68
    owned.data.materials.append(material)
    from blender_addon.universal_mcp.bridge.local_test_scope import configure_fixture
    configure_fixture(bpy, root, [owned], [material])
    before = snapshot()  # Start protocol preservation check after owned setup.
    queue = MainThreadQueue(bpy)
    server = BridgeServer(port=port, queue=queue)
    server.start()
    from blender_addon import universal_mcp
    (root / "ready.json").write_text(json.dumps({"pid": os.getpid(), "port": port,
        "version": bpy.app.version_string, "source_addon_version": list(universal_mcp.bl_info["version"])}))
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
        requests = [registry.inspect_request_status(rid) for rid in registry._requests]
        (root / "request_parameters.json").write_text(json.dumps([
            {"tool": r.tool_name, "params": r.params, "decision_reason": r.decision_reason}
            for r in registry._requests.values()], indent=2))
        bevel = owned.modifiers.get("NewBevel")
        pixels = list(bpy.data.images["FreshImage"].pixels) if "FreshImage" in bpy.data.images else []
        red = pixels[::4]
        independent = {"bevel_width": bevel.width if bevel else None,
                       "bevel_segments": bevel.segments if bevel else None,
                       "subsurf_removed": owned.modifiers.get("OwnedSubsurf") is None,
                       "solidify_thickness": owned.modifiers["NewSolidify"].thickness if owned.modifiers.get("NewSolidify") else None,
                       "image_size": list(bpy.data.images["FreshImage"].size) if "FreshImage" in bpy.data.images else None,
                       "pixel_sample": list(bpy.data.images["FreshImage"].pixels[:4]) if "FreshImage" in bpy.data.images else None,
                       "red_max": max(red) if red else None,
                       "covered_pixels": sum(value > .1 for value in red),
                       "material_node_names": sorted(material.node_tree.nodes.keys())}
        (root / "independent.json").write_text(json.dumps({"before": before, "after": after,
            "unchanged": before == after, "approval_requests": requests, "owned_results": independent}, indent=2))
        assert before == after


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
                            "get_task_status", "check_approval_status", "resolve_pending_approval"}
                assert required <= names, sorted(required - names)
                (root / "catalog.json").write_text(catalog.model_dump_json(indent=2))
                calls = [
                    ("execute_blender_code", {"operations": [{"action": "add_modifier", "target": "OwnedMesh", "params": {"modifier_type": "BEVEL", "modifier_name": "NewBevel", "properties": {"width": .02, "segments": 2}}}]}),
                    ("execute_blender_code", {"operations": [{"action": "modify_modifier", "target": "OwnedMesh", "params": {"modifier_name": "OwnedSubsurf", "properties": {"levels": 1}}}]}),
                    ("inspect_scene_data", {"category": "object_modifiers", "target_name": "OwnedMesh"}),
                    ("execute_blender_code", {"operations": [{"action": "remove_modifier", "target": "OwnedMesh", "params": {"modifier_name": "OwnedSubsurf"}}]}),
                    ("execute_blender_code", {"operations": [{"action": "add_modifier", "target": "OwnedMesh", "params": {"modifier_type": "SOLIDIFY", "modifier_name": "NewSolidify", "properties": {"thickness": .02}}}]}),
                    ("bake_object_texture", {"object_name": "OwnedMesh", "image_name": "FreshImage", "bake_type": "ROUGHNESS", "width": 64, "height": 64, "margin": 2, "save_filepath": str(root / "bake.png")}),
                ]
                for tool, args in calls:
                    response = await session.call_tool(tool, arguments=args)
                    record = {"tool": tool, "arguments": args, "response": response.model_dump(mode="json")}
                    records.append(record)
                    (root / "calls.json").write_text(json.dumps(records, indent=2))
                    assert not response.isError, record
                    payload = json.loads(response.content[0].text)
                    assert payload["status"] == "success", record
                return {"service": initialized.serverInfo.model_dump(), "tool_count": len(names),
                        "successful_wire_calls": len(records)}


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
    root = Path(tempfile.mkdtemp(prefix="umcp-wire-scoped-"))
    print(str(root), flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.update(UMCP_LOCAL_TEST_AUTOAPPROVE="1", UMCP_LOCAL_TEST_ROOT=str(root), UMCP_LOCAL_TEST_SCOPE="modifier_bake_v1")
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
    assert child.returncode == 0 and independent["unchanged"]
    observed = independent["owned_results"]
    assert abs(observed["bevel_width"] - .02) < 1e-6 and observed["bevel_segments"] == 2
    assert observed["subsurf_removed"] and observed["image_size"] == [64, 64]
    assert abs(observed["solidify_thickness"] - .02) < 1e-6
    assert abs(observed["red_max"] - .68) < .01 and observed["covered_pixels"] > 409, observed
    assert len(independent["approval_requests"]) == 5 and all(r["token_consumed"] for r in independent["approval_requests"])
    assert not any("token" in r for r in independent["approval_requests"])
    import struct
    image = (root / "bake.png").read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", image[16:24]) == (64, 64)
    result.update(blender=json.loads((root / "ready.json").read_text()), scene_preserved=True,
                  approval_requests=5, status="PASS", scope="isolated modifier/bake subset only",
                  baked_png_sha256=hashlib.sha256(image).hexdigest())
    result["fixture_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (root / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
