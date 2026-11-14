"""Public camera/render provider handoff plus pending-task resumption in Blender.

Existing local shader/render authorization only; no production connection or UI
approval claim. Socket I/O queues work; Blender's main thread pumps the queue.
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
sys.path.insert(0, str(PROJECT))
from shared.models.agent_contracts import TaskStatus


def fixture(root, port):
    import bpy
    sys.path.insert(0, str(PROJECT))
    from blender_addon import universal_mcp
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    assert bpy.app.background and bpy.data.filepath == "" and port != 9877
    bpy.types.Scene.umcp_bridge_port = bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=True)
    bpy.context.scene.umcp_bridge_port = port
    bpy.context.scene.umcp_require_scene_mutation_approval = True
    originals = list(bpy.context.scene.objects)
    original_materials = list(bpy.data.materials)
    def graph(material):
        if not material.use_nodes:
            return {"use_nodes": False, "nodes": [], "links": []}
        nodes = []
        for node in material.node_tree.nodes:
            inputs = {}
            wanted = {"Base Color", "Metallic", "Roughness", "IOR"} if node.bl_idname == "ShaderNodeBsdfPrincipled" else {"Scale", "Detail", "Roughness", "Distortion"} if node.bl_idname == "ShaderNodeTexNoise" else set()
            for item in node.inputs:
                if item.identifier in wanted:
                    try:
                        inputs[item.identifier] = float(item.default_value)
                    except TypeError:
                        inputs[item.identifier] = list(item.default_value)
            nodes.append({"name": node.name, "type": node.bl_idname, "inputs": inputs})
        return {"use_nodes": True, "nodes": nodes, "links": [
            [link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier]
            for link in material.node_tree.links]}
    def protected():
        return {"objects": {obj.name: {"type": obj.type, "matrix": [list(row) for row in obj.matrix_world],
                    "vertices": [list(vertex.co) for vertex in obj.data.vertices] if obj.type == "MESH" else None} for obj in originals},
                "materials": {mat.name: graph(mat) for mat in original_materials}}
    before = protected()
    bpy.ops.mesh.primitive_cube_add(location=(10, 0, 0))
    owned_name = "ShaderOwnedSurface_" + root.name[-8:]
    bpy.context.object.name = owned_name
    source_vertices = [list(vertex.co) for vertex in bpy.context.object.data.vertices]
    plain = bpy.data.materials.new("ShaderPlainEmpty")
    initial_flag = bool(plain.use_nodes)
    plain.use_nodes = False
    (root / "material_flag_probe.json").write_text(json.dumps({"before": initial_flag, "after_false_assignment": bool(plain.use_nodes), "blender": bpy.app.version_string}))
    plain.use_nodes = True
    plain.node_tree.nodes.clear()
    plain_before = graph(plain)
    queue = MainThreadQueue(bpy); server = BridgeServer(port=port, queue=queue)
    inspection_calls = [0]; original_handler = queue._handlers["inspect_material_shader"]
    executions = {"create_camera": 0, "render_scene": 0}
    for command in executions:
        actual_handler = queue._handlers[command]
        def tracked(bpy_module=None, params=None, handler=actual_handler, name=command):
            executions[name] += 1
            return handler(bpy_module=bpy_module, params=params)
        queue.register_handler(command, tracked)
    def instrumented(**kwargs):
        inspection_calls[0] += 1
        return original_handler(**kwargs)
    queue.register_handler("inspect_material_shader", instrumented)
    server.start(); states = []; previous = None; handled = set()
    (root / "ready.json").write_text(json.dumps({"pid": os.getpid(), "port": port, "blender": bpy.app.version_string,
        "source_addon_version": list(universal_mcp.bl_info["version"]), "owned_object": owned_name}))
    deadline = time.monotonic() + 180
    try:
        while not (root / "stop").exists() and time.monotonic() < deadline:
            if (root / "pause_policy").exists():
                os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = ""
                (root / "policy_paused.json").write_text(json.dumps({"paused": True}))
            if (root / "authorize_planned.json").exists():
                try:
                    planned_id = json.loads((root / "authorize_planned.json").read_text())["request_id"]
                except (json.JSONDecodeError, KeyError):
                    planned_id = None
                if planned_id and planned_id not in handled:
                    req = get_approval_registry().get_request(planned_id)
                    assert req is not None and req.status == "pending"
                    if req.tool_name == "create_camera":
                        expected = {"name": "HandoffPendingCamera", "lens": 42, "sensor_width": 30,
                            "clip_start": .2, "clip_end": 90, "set_active": False,
                            "location": [10, -6, 3], "rotation_euler": [1.107148718, 0, 0]}
                    else:
                        assert req.tool_name == "render_scene"
                        expected = {"render_mode": "still", "frame": 1, "output_path": str(root / "pending_render.png"),
                            "output_format": "png", "camera": "ShaderCamera"}
                    assert {key: value for key, value in req.params.items() if key != "approved"} == expected
                    # Trusted host fixture decision for the original request;
                    # same guards and registry token issuance, no new request,
                    # caller flag or claim of a human UI action.
                    from blender_addon.universal_mcp.bridge.handlers import _local_test_autoapproval
                    os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
                    assert _local_test_autoapproval(bpy, req.tool_name, req.params)
                    ok, _ = get_approval_registry().resolve_request(planned_id, "approved",
                        reason="LOCAL TEST AUTO-APPROVAL: isolated background process", approve_task_group=False)
                    assert ok
                    handled.add(planned_id)
                    (root / "planned_authorized.json").write_text(json.dumps({"request_id": planned_id, "decision": "LOCAL TEST POLICY"}))
                    os.environ["UMCP_LOCAL_TEST_AUTOAPPROVE"] = ""
            queue.drain_queue()
            material = bpy.data.materials.get("ShaderTypedMaterial")
            if material:
                current = graph(material)
                if current != previous:
                    states.append(current); previous = current
                    (root / "states.json").write_text(json.dumps(states, indent=2))
            time.sleep(.01)
    finally:
        server.stop()
        registry = get_approval_registry()
        material = bpy.data.materials.get("ShaderTypedMaterial")
        after = protected()
        owned = bpy.data.objects[owned_name]
        camera_state = {name: {"lens": bpy.data.objects[name].data.lens,
            "clip_start": bpy.data.objects[name].data.clip_start, "clip_end": bpy.data.objects[name].data.clip_end,
            "sensor_width": bpy.data.objects[name].data.sensor_width, "location": list(bpy.data.objects[name].location),
            "rotation_euler": list(bpy.data.objects[name].rotation_euler)}
            for name in ("ShaderCamera", "HandoffPendingCamera") if name in bpy.data.objects}
        (root / "independent.json").write_text(json.dumps({"before": before, "after": after, "preserved": before == after,
            "states": states, "final_graph": graph(material) if material else None,
            "source_mesh_preserved": source_vertices == [list(vertex.co) for vertex in owned.data.vertices],
            "plain_graph_preserved": plain_before == graph(plain), "inspection_handler_calls": inspection_calls[0],
            "execution_handler_calls": executions,
            "cameras": camera_state, "active_camera": bpy.context.scene.camera.name,
            "pending_camera_copies": [obj.name for obj in bpy.data.objects if obj.name.startswith("HandoffPendingCamera")],
            "render_settings": {"engine": bpy.context.scene.render.engine, "width": bpy.context.scene.render.resolution_x,
                                "height": bpy.context.scene.render.resolution_y, "samples": bpy.context.scene.cycles.samples},
            "requests": [registry.inspect_request_status(rid) for rid in registry._requests]}, indent=2))
        assert before == after


async def client(root, port):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, PYTHONPATH=str(PROJECT), PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
    params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "mcp_service.app", "--transport", "stdio",
        "--bridge-port", str(port), "--bridge-timeout", "25", "--approval-mode", "blender"], env=env, cwd=str(PROJECT))
    calls = []
    with (root / "mcp.log").open("w", encoding="utf-8") as log:
        async with stdio_client(params, errlog=log) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize(); catalog = await session.list_tools()
                assert {"configure_material_shader", "inspect_material_shader"} <= {tool.name for tool in catalog.tools}
                (root / "catalog.json").write_text(catalog.model_dump_json(indent=2))
                async def call(tool, args, success=True):
                    response = await session.call_tool(tool, arguments=args)
                    calls.append({"tool": tool, "arguments": args, "response": response.model_dump(mode="json"), "expected_success": success})
                    (root / "calls.json").write_text(json.dumps(calls, indent=2))
                    if response.isError:
                        assert not success, calls[-1]
                        return
                    result = json.loads(response.content[0].text)
                    assert (result.get("status") == "success") == success, calls[-1]
                    return result
                async def inspect():
                    return await call("inspect_material_shader", {"target_name": "ShaderTypedMaterial"})
                async def render(name):
                    await call("render_scene", {"render_mode": "still", "frame": 1, "output_path": str(root / name), "output_format": "PNG"})
                owned_name = json.loads((root / "ready.json").read_text())["owned_object"]
                identity = await call("get_object_details", {"name": owned_name})
                assert identity["result"]["name"] == owned_name
                await call("create_material", {"name": "ShaderTypedMaterial"})
                await call("assign_material", {"target_name": owned_name, "material_name": "ShaderTypedMaterial"})
                await call("create_camera", {"name": "ShaderCamera", "location": [10, -6, 3], "rotation_euler": [1.107148718, 0, 0],
                    "lens": 45, "sensor_width": 32, "clip_start": .2, "clip_end": 200, "set_active": True})
                await call("create_light", {"name": "ShaderLight", "light_type": "AREA", "energy": 1000, "size": 4,
                    "location": [10, -3, 5], "rotation_euler": [.5404195, 0, 0]})
                await call("configure_render_settings", {"engine": "CYCLES", "cycles_device": "CPU", "cycles_samples": 8,
                    "resolution_x": 64, "resolution_y": 64, "resolution_percentage": 100, "output_format": "PNG"})
                await inspect()
                empty = await call("inspect_material_shader", {"target_name": "ShaderPlainEmpty"})
                assert empty["result"]["nodes"] == []
                base = {"target_name": "ShaderTypedMaterial", "bsdf_node_name": "Principled BSDF"}
                await call("configure_material_shader", {**base, "action": "set_principled", "inputs": {
                    "base_color": [.38, .035, .018, 1], "roughness": .68, "metallic": .2, "ior": 1.45}})
                await inspect(); await render("baseline.png")
                noise = {**base, "noise_node_name": "ShaderTypedNoise"}
                await call("configure_material_shader", {**noise, "action": "add_noise", "noise_inputs": {"scale": 2, "detail": 2, "roughness": .5, "distortion": .1}})
                await inspect(); await render("noise_added.png")
                await call("configure_material_shader", {**noise, "action": "update_noise", "noise_inputs": {"scale": 8, "detail": 3, "roughness": .7, "distortion": .3}})
                await inspect(); await render("noise_updated.png")
                await call("configure_material_shader", {**base, "action": "set_principled", "inputs": {"base_color": [.1, .1, .1, 1]}}, success=False)
                await call("configure_material_shader", {**noise, "action": "remove_noise"})
                await inspect(); await render("restored.png")
                for invalid in ({"roughness": True}, {"base_color": [1, 0, 0]}, {"unknown": 1}, {"ior": 0}):
                    await call("configure_material_shader", {**base, "action": "set_principled", "inputs": invalid}, success=False)
                await call("inspect_material_shader", {"target_name": "NoSuchShaderMaterial"}, success=False)
                return {"service": initialized.serverInfo.model_dump(), "catalog_names": len(catalog.tools),
                        "client_calls": len(calls), "expected_errors": sum(not call["expected_success"] for call in calls)}


async def wait_json(path, predicate):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            value = json.loads(path.read_text())
            if predicate(value):
                return value
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        await asyncio.sleep(.02)
    raise TimeoutError(f"Fixture control was not acknowledged: {path.name}")


async def pending_client(root, port):
    """Real pending request -> authorized LOCAL TEST policy -> same-task resolve."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, PYTHONPATH=str(PROJECT), PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
    params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "mcp_service.app", "--transport", "stdio",
        "--bridge-port", str(port), "--bridge-timeout", "3", "--approval-mode", "blender"], env=env, cwd=str(PROJECT))
    (root / "pause_policy").touch()
    await wait_json(root / "policy_paused.json", lambda value: value["paused"])
    calls, summaries = [], []
    with (root / "pending_mcp.log").open("w", encoding="utf-8") as log:
        async with stdio_client(params, errlog=log) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                async def call(tool, arguments, success=True):
                    response = await session.call_tool(tool, arguments=arguments)
                    calls.append({"tool": tool, "arguments": arguments, "response": response.model_dump(mode="json"), "expected_success": success})
                    (root / "pending_calls.json").write_text(json.dumps(calls, indent=2))
                    assert not response.isError, calls[-1]
                    payload = json.loads(response.content[0].text)
                    assert (payload["status"] == "success") == success, calls[-1]
                    assert "approval_token" not in json.dumps(payload)
                    return payload
                for tool, arguments in [
                    ("create_camera", {"name": "HandoffPendingCamera", "lens": 42, "sensor_width": 30, "clip_start": .2, "clip_end": 90,
                        "set_active": False, "location": [10, -6, 3], "rotation_euler": [1.107148718, 0, 0]}),
                    ("render_scene", {"render_mode": "still", "frame": 1, "output_path": str(root / "pending_render.png"), "output_format": "PNG", "camera": "ShaderCamera"})]:
                    waiting = await call(tool, arguments, success=False)
                    pending = waiting["result"]["pending_approval"]
                    status_args = {"task_id": pending["task_id"], "session_id": pending["session_id"]}
                    before = await call("get_task_status", status_args)
                    assert before["result"]["status"] == TaskStatus.AWAITING_APPROVAL.value
                    resolution = {**status_args, "decision": "approved", "nonce": pending["nonce"], "param_hash": pending["param_hash"]}
                    await call("resolve_pending_approval", resolution, success=False)
                    if tool == "render_scene":
                        assert not (root / "pending_render.png").exists()
                    (root / "authorize_planned.json").write_text(json.dumps({"request_id": pending["approval_request_id"]}))
                    await wait_json(root / "planned_authorized.json", lambda value: value["request_id"] == pending["approval_request_id"])
                    await call("resolve_pending_approval", resolution)
                    after = await call("get_task_status", status_args)
                    assert after["result"]["status"] == TaskStatus.SUCCEEDED.value and after["result"]["task_id"] == pending["task_id"]
                    approval = await call("check_approval_status", {"request_id": pending["approval_request_id"]})
                    assert approval["result"]["token_consumed"] is True
                    await call("resolve_pending_approval", resolution, success=False)
                    summaries.append({"tool": tool, "task_id": pending["task_id"], "request_id": pending["approval_request_id"],
                        "final_task_status": after["result"]["status"], "token_consumed": True, "replay_rejected": True,
                        "decision_source": "LOCAL TEST POLICY, not human UI"})
    return {"calls": len(calls), "tasks": summaries}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--root", type=Path); parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.fixture:
        fixture(args.root, args.port); return
    root = Path(tempfile.mkdtemp(prefix="umcp-camera-render-handoff-")); print(root, flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", UMCP_LOCAL_TEST_AUTOAPPROVE="1", UMCP_LOCAL_TEST_ROOT=str(root))
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
            pending = asyncio.run(pending_client(root, port))
        finally:
            (root / "stop").touch(); process.wait(timeout=190)
    observed = json.loads((root / "independent.json").read_text())
    assert process.returncode == 0 and observed["preserved"] and observed["source_mesh_preserved"] and observed["plain_graph_preserved"]
    assert len(observed["requests"]) == 16 and all(req["token_consumed"] for req in observed["requests"])
    assert observed["inspection_handler_calls"] == 11 and all("approval_token" not in req for req in observed["requests"])
    final = observed["final_graph"]; baseline = observed["states"][1]
    assert final == baseline and len(final["nodes"]) == 2
    assert observed["pending_camera_copies"] == ["HandoffPendingCamera"]
    assert observed["execution_handler_calls"] == {"create_camera": 2, "render_scene": 5}
    assert observed["active_camera"] == "ShaderCamera"
    camera = observed["cameras"]["ShaderCamera"]
    assert camera["lens"] == 45 and camera["sensor_width"] == 32 and abs(camera["clip_start"]-.2) < 1e-6 and camera["clip_end"] == 200
    resumed = observed["cameras"]["HandoffPendingCamera"]
    assert resumed["lens"] == 42 and resumed["sensor_width"] == 30 and resumed["clip_end"] == 90
    assert observed["render_settings"] == {"engine": "CYCLES", "width": 64, "height": 64, "samples": 8}
    from PIL import Image, ImageChops, ImageStat
    images = {name: Image.open(root / name).convert("RGB") for name in ("baseline.png", "noise_added.png", "noise_updated.png", "restored.png", "pending_render.png")}
    assert all(image.size == (64, 64) for image in images.values())
    def difference(first, second):
        return sum(ImageStat.Stat(ImageChops.difference(images[first], images[second])).mean) / (3 * 255)
    pixels = {name: hashlib.sha256(image.tobytes()).hexdigest() for name, image in images.items()}
    metrics = {"noise_vs_baseline": difference("baseline.png", "noise_added.png"), "update_vs_noise": difference("noise_added.png", "noise_updated.png"),
               "restored_vs_baseline": difference("baseline.png", "restored.png")}
    assert metrics["noise_vs_baseline"] > .005 and metrics["update_vs_noise"] > .001 and metrics["restored_vs_baseline"] <= .002, metrics
    assert pixels["pending_render.png"] == pixels["restored.png"]
    result.update(status="PASS", scope="public camera/render approval handoff", runtime=json.loads((root / "ready.json").read_text()),
                  consumed_tokens=16, public_mcp_renders=5, pending_resumption=pending, protected_data_preserved=True, pixels_sha256=pixels, pixel_mean_differences=metrics)
    (root / "result.json").write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
