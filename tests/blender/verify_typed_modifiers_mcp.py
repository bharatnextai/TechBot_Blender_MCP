"""Real stdio MCP/TCP/Blender typed modifier checks in an owned factory child.

Uses the existing modifier_bake_v1 limits/tokens. Host-only planned-output
enrollment follows independent Blender readback. No production connection.
Background fixture pumps the real queue on its main thread, not UI event-loop proof.
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
PLAN = {"TypedSubsurf": ("SUBSURF", {"levels": 1, "render_levels": 1}, {"levels": 2}),
        "TypedBevel": ("BEVEL", {"width": .02, "segments": 2}, {"width": .04, "segments": 3}),
        "TypedSolidify": ("SOLIDIFY", {"thickness": .02}, {"thickness": .04})}


def fixture(root, port):
    import bpy
    sys.path.insert(0, str(PROJECT))
    from blender_addon import universal_mcp
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge.local_test_scope import configure_fixture, record_fixture_modifier
    from blender_addon.universal_mcp.bridge.modifier_contract import PROPERTY_SPECS
    assert bpy.app.background and bpy.data.filepath == "" and port != 9877
    bpy.types.Scene.umcp_bridge_port = bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=True)
    bpy.context.scene.umcp_bridge_port = port
    bpy.context.scene.umcp_require_scene_mutation_approval = True
    protected = list(bpy.context.scene.objects)
    def snapshot():
        return {o.name: {"type": o.type, "matrix": [list(row) for row in o.matrix_world],
                "vertices": [list(v.co) for v in o.data.vertices] if o.type == "MESH" else None}
                for o in protected}
    before = snapshot()
    bpy.ops.mesh.primitive_cube_add()
    owned = bpy.context.object; owned.name = "TypedOwnedMesh"
    source_vertices = [list(vertex.co) for vertex in owned.data.vertices]
    guard = owned.modifiers.new("GuardSubsurf", "SUBSURF"); guard.levels = guard.render_levels = 0
    configure_fixture(bpy, root, [owned], [])
    queue = MainThreadQueue(bpy); server = BridgeServer(port=port, queue=queue)
    inspection_calls = [0]
    original_inspection = queue._handlers["inspect_modifiers"]
    def instrumented_inspection(**kwargs):
        inspection_calls[0] += 1
        return original_inspection(**kwargs)
    queue.register_handler("inspect_modifiers", instrumented_inspection)
    server.start()
    events, previous, enrolled = [], None, set()
    (root / "ready.json").write_text(json.dumps({"pid": os.getpid(), "port": port,
        "blender": bpy.app.version_string, "source_addon_version": list(universal_mcp.bl_info["version"])}))
    deadline = time.monotonic() + 120
    try:
        while not (root / "stop").exists() and time.monotonic() < deadline:
            if (root / "enter_edit").exists() and not (root / "leave_edit").exists() and bpy.context.mode == "OBJECT":
                bpy.ops.object.mode_set(mode="EDIT")
            if (root / "leave_edit").exists() and bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            (root / "mode.json").write_text(json.dumps({"mode": bpy.context.mode}))
            queue.drain_queue()
            for name, (kind, initial, _) in PLAN.items():
                mod = owned.modifiers.get(name)
                if mod is not None and name not in enrolled:
                    assert mod.type == kind and all(abs(getattr(mod, key) - value) < 1e-6 for key, value in initial.items())
                    record_fixture_modifier(bpy, owned, mod)
                    enrolled.add(name)
            state = [{"name": mod.name, "type": mod.type,
                      "properties": {key: getattr(mod, key) for key in PROPERTY_SPECS[mod.type]}}
                     for mod in owned.modifiers]
            if state != previous:
                bpy.context.view_layer.update()
                evaluated = owned.evaluated_get(bpy.context.evaluated_depsgraph_get())
                mesh = evaluated.to_mesh()
                try:
                    geometry = [list(vertex.co) for vertex in mesh.vertices]
                    events.append({"modifiers": state, "evaluated_vertices": len(mesh.vertices), "evaluated_faces": len(mesh.polygons),
                                   "evaluated_geometry_sha256": hashlib.sha256(json.dumps(geometry).encode()).hexdigest()})
                finally:
                    evaluated.to_mesh_clear()
                previous = state
                (root / "states.json").write_text(json.dumps(events, indent=2))
            time.sleep(.01)
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        server.stop()
        registry = get_approval_registry()
        requests = [registry.inspect_request_status(rid) for rid in registry._requests]
        after = snapshot()
        (root / "independent.json").write_text(json.dumps({"before": before, "after": after,
            "preserved": before == after, "requests": requests, "events": events,
            "remaining_modifiers": [mod.name for mod in owned.modifiers], "guard_levels": guard.levels,
            "source_mesh_preserved": source_vertices == [list(vertex.co) for vertex in owned.data.vertices],
            "inspection_handler_calls": inspection_calls[0]}, indent=2))
        assert before == after


async def wait_json(path, predicate):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            value = json.loads(path.read_text())
            if predicate(value):
                return value
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        await asyncio.sleep(.02)
    raise TimeoutError(f"Independent fixture state not observed: {path.name}")


async def client(root, port):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, PYTHONPATH=str(PROJECT), PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
    params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "mcp_service.app", "--transport", "stdio",
        "--bridge-port", str(port), "--bridge-timeout", "10", "--approval-mode", "blender"], env=env, cwd=str(PROJECT))
    calls = []
    with (root / "mcp.log").open("w", encoding="utf-8") as log:
        async with stdio_client(params, errlog=log) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize()
                catalog = await session.list_tools()
                assert {"configure_modifier", "inspect_modifiers"} <= {tool.name for tool in catalog.tools}
                (root / "catalog.json").write_text(catalog.model_dump_json(indent=2))
                async def call(tool, arguments, success=True):
                    response = await session.call_tool(tool, arguments=arguments)
                    calls.append({"tool": tool, "arguments": arguments, "response": response.model_dump(mode="json")})
                    (root / "calls.json").write_text(json.dumps(calls, indent=2))
                    if response.isError:
                        assert not success, calls[-1]
                        return
                    payload = json.loads(response.content[0].text)
                    assert (payload.get("status") == "success") == success, calls[-1]
                    return payload
                await call("inspect_modifiers", {"name": "TypedOwnedMesh"})
                events = 1
                await wait_json(root / "states.json", lambda states: len(states) >= events)
                for name, (kind, initial, updated) in PLAN.items():
                    added_geometry = None
                    for action, props in (("add", initial), ("update", updated), ("remove", {})):
                        args = dict(name="TypedOwnedMesh", modifier_name=name, modifier_type=kind, action=action)
                        if props:
                            args["properties"] = props
                        await call("configure_modifier", args)
                        events += 1
                        states = await wait_json(root / "states.json", lambda states: len(states) >= events)
                        matching = [mod for mod in states[-1]["modifiers"] if mod["name"] == name]
                        assert bool(matching) == (action != "remove")
                        if props:
                            assert matching[0]["type"] == kind and all(abs(matching[0]["properties"][key] - value) < 1e-6 for key, value in props.items())
                        if kind == "SUBSURF" and action != "remove":
                            assert states[-1]["evaluated_vertices"] > 8
                        if action == "add":
                            added_geometry = states[-1]["evaluated_geometry_sha256"]
                        elif action == "update":
                            assert states[-1]["evaluated_geometry_sha256"] != added_geometry
                        else:
                            assert states[-1]["evaluated_geometry_sha256"] == states[0]["evaluated_geometry_sha256"]
                        await call("inspect_modifiers", {"name": "TypedOwnedMesh"})
                base = dict(name="TypedOwnedMesh", modifier_name="Invalid", modifier_type="BEVEL", action="add")
                for props in ({"width": -1}, {"segments": True}, {"levels": 1}, {"unknown_property": .1}):
                    await call("configure_modifier", {**base, "properties": props}, success=False)
                await call("inspect_modifiers", {"name": "NoSuchOwnedMesh"}, success=False)
                (root / "enter_edit").touch()
                await wait_json(root / "mode.json", lambda state: state["mode"] == "EDIT_MESH")
                await call("configure_modifier", dict(name="TypedOwnedMesh", modifier_name="GuardSubsurf", modifier_type="SUBSURF", action="update", properties={"levels": 1}), success=False)
                (root / "leave_edit").touch()
                await wait_json(root / "mode.json", lambda state: state["mode"] == "OBJECT")
                return {"service": initialized.serverInfo.model_dump(), "catalog_names": len(catalog.tools),
                        "client_calls": len(calls), "expected_errors": 6}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--root", type=Path); parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.fixture:
        fixture(args.root, args.port); return
    root = Path(tempfile.mkdtemp(prefix="umcp-typed-modifiers-")); print(root, flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", UMCP_LOCAL_TEST_AUTOAPPROVE="1",
               UMCP_LOCAL_TEST_ROOT=str(root), UMCP_LOCAL_TEST_SCOPE="modifier_bake_v1")
    for key in ("CONFIG", "SCRIPTS", "EXTENSIONS", "DATAFILES", "RESOURCES"):
        folder = root / key.lower(); folder.mkdir(); env["BLENDER_USER_" + key] = str(folder)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0)); port = reservation.getsockname()[1]
    assert port != 9877
    env["UMCP_BRIDGE_PORT"] = str(port)
    bootstrap = root / "bootstrap.py"
    bootstrap.write_text("import runpy,sys\nsys.argv=" + repr([str(Path(__file__).resolve()), "--fixture", "--root", str(root), "--port", str(port)]) +
                         "\nrunpy.run_path(" + repr(str(Path(__file__).resolve())) + ",run_name='__main__')\n")
    with (root / "blender.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe", "--background", "--factory-startup",
            "--disable-autoexec", "--python-exit-code", "1", "--python", str(bootstrap)], env=env, cwd=str(PROJECT), stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 40
            while not (root / "ready.json").exists():
                assert process.poll() is None and time.monotonic() < deadline, "Fixture failed to start; inspect blender.log"
                time.sleep(.1)
            result = asyncio.run(client(root, port))
        finally:
            (root / "stop").touch(); process.wait(timeout=130)
    observed = json.loads((root / "independent.json").read_text())
    assert process.returncode == 0 and observed["preserved"] and observed["source_mesh_preserved"]
    assert observed["remaining_modifiers"] == ["GuardSubsurf"] and observed["guard_levels"] == 0
    assert len(observed["requests"]) == 10 and all(req["token_consumed"] for req in observed["requests"])
    assert all("approval_token" not in req for req in observed["requests"])
    assert observed["inspection_handler_calls"] == 20  # 11 client + 9 agent readbacks.
    result.update(status="PASS", scope="typed three-modifier contract only", runtime=json.loads((root / "ready.json").read_text()),
                  consumed_tokens=10, protected_factory_objects_preserved=True)
    (root / "result.json").write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
