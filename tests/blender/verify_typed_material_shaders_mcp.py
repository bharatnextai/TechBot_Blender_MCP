"""Real MCP shader contract + matched Cycles pixels in a disposable factory child.

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
    camera_data = bpy.data.cameras.new("ShaderFixtureCamera")
    camera = bpy.data.objects.new("ShaderFixtureCamera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (10, -6, 3); camera.rotation_euler = (1.107148718, 0, 0)
    bpy.context.scene.camera = camera
    light_data = bpy.data.lights.new("ShaderFixtureLight", "AREA"); light_data.energy = 1000; light_data.shape = "DISK"; light_data.size = 4
    light = bpy.data.objects.new("ShaderFixtureLight", light_data); bpy.context.scene.collection.objects.link(light)
    light.location = (10, -3, 5); light.rotation_euler = (.5404195, 0, 0)
    scene = bpy.context.scene; scene.render.engine = "CYCLES"; scene.cycles.device = "CPU"; scene.cycles.samples = 8
    scene.render.resolution_x = scene.render.resolution_y = 64; scene.render.resolution_percentage = 100
    plain = bpy.data.materials.new("ShaderPlainEmpty")
    initial_flag = bool(plain.use_nodes)
    plain.use_nodes = False
    (root / "material_flag_probe.json").write_text(json.dumps({"before": initial_flag, "after_false_assignment": bool(plain.use_nodes), "blender": bpy.app.version_string}))
    plain.use_nodes = True
    plain.node_tree.nodes.clear()
    plain_before = graph(plain)
    queue = MainThreadQueue(bpy); server = BridgeServer(port=port, queue=queue)
    inspection_calls = [0]; original_handler = queue._handlers["inspect_material_shader"]
    def instrumented(**kwargs):
        inspection_calls[0] += 1
        return original_handler(**kwargs)
    queue.register_handler("inspect_material_shader", instrumented)
    server.start(); states = []; previous = None
    (root / "ready.json").write_text(json.dumps({"pid": os.getpid(), "port": port, "blender": bpy.app.version_string,
        "source_addon_version": list(universal_mcp.bl_info["version"]), "owned_object": owned_name}))
    deadline = time.monotonic() + 180
    try:
        while not (root / "stop").exists() and time.monotonic() < deadline:
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
        (root / "independent.json").write_text(json.dumps({"before": before, "after": after, "preserved": before == after,
            "states": states, "final_graph": graph(material) if material else None,
            "source_mesh_preserved": source_vertices == [list(vertex.co) for vertex in owned.data.vertices],
            "plain_graph_preserved": plain_before == graph(plain), "inspection_handler_calls": inspection_calls[0],
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
                    # Independent fixture observation, not a public MCP rendering
                    # acceptance claim. Normal registry tokens and real TCP queue.
                    from blender_addon.universal_mcp.bridge.bridge_client import BridgeClient
                    bridge = BridgeClient(host="127.0.0.1", port=port, timeout=25)
                    args = {"render_mode": "still", "frame": 1, "output_path": str(root / name), "output_format": "PNG"}
                    approval = await asyncio.to_thread(bridge.send_command, "request_approval", {"tool_name": "render_scene", "params": args, "timeout": 60})
                    assert approval["status"] == "success" and approval["result"]["status"] == "approved", approval.get("message")
                    secret = approval["result"]
                    response = await asyncio.to_thread(bridge.send_command, "render_scene", {**args, "request_id": secret["request_id"], "approval_token": secret["approval_token"]})
                    assert response["status"] == "success", response
                owned_name = json.loads((root / "ready.json").read_text())["owned_object"]
                identity = await call("get_object_details", {"name": owned_name})
                assert identity["result"]["name"] == owned_name
                await call("create_material", {"name": "ShaderTypedMaterial"})
                await call("assign_material", {"target_name": owned_name, "material_name": "ShaderTypedMaterial"})
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


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--root", type=Path); parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.fixture:
        fixture(args.root, args.port); return
    root = Path(tempfile.mkdtemp(prefix="umcp-typed-shaders-")); print(root, flush=True)
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
        finally:
            (root / "stop").touch(); process.wait(timeout=190)
    observed = json.loads((root / "independent.json").read_text())
    assert process.returncode == 0 and observed["preserved"] and observed["source_mesh_preserved"] and observed["plain_graph_preserved"]
    assert len(observed["requests"]) == 11 and all(req["token_consumed"] for req in observed["requests"])
    assert observed["inspection_handler_calls"] == 11 and all("approval_token" not in req for req in observed["requests"])
    final = observed["final_graph"]; baseline = observed["states"][1]
    assert final == baseline and len(final["nodes"]) == 2
    from PIL import Image, ImageChops, ImageStat
    images = {name: Image.open(root / name).convert("RGB") for name in ("baseline.png", "noise_added.png", "noise_updated.png", "restored.png")}
    assert all(image.size == (64, 64) for image in images.values())
    def difference(first, second):
        return sum(ImageStat.Stat(ImageChops.difference(images[first], images[second])).mean) / (3 * 255)
    pixels = {name: hashlib.sha256(image.tobytes()).hexdigest() for name, image in images.items()}
    metrics = {"noise_vs_baseline": difference("baseline.png", "noise_added.png"), "update_vs_noise": difference("noise_added.png", "noise_updated.png"),
               "restored_vs_baseline": difference("baseline.png", "restored.png")}
    assert metrics["noise_vs_baseline"] > .005 and metrics["update_vs_noise"] > .001 and metrics["restored_vs_baseline"] <= .002, metrics
    result.update(status="PASS", scope="typed Principled/Noise contract only", runtime=json.loads((root / "ready.json").read_text()),
                  consumed_tokens=11, independent_bridge_renders=4, protected_data_preserved=True, pixels_sha256=pixels, pixel_mean_differences=metrics)
    (root / "result.json").write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
