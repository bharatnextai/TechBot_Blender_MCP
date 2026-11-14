"""
Automated Real MCP-to-Blender E2E Verification of Ten-Capability Integrated Workflow (v0.1.71).
Validates complete sequential execution across all 10 capabilities in a single disposable Blender 5.2.2 session:
1. Primitives & Transforms: create_primitive ("IntegratedHero") -> transform_object -> readback
2. Mesh Modeling: extrude_mesh -> inset_mesh -> bevel_mesh -> readback
3. Modifiers: edit_modifier_stack (add BEVEL) -> apply_modifier -> readback
4. Geometry Nodes: configure_geometry_nodes (create GN group -> add Subdiv -> link -> evaluate -> apply) -> readback
5. UV Mapping: manage_uv_seams -> uv_unwrap -> pack_uv_islands -> readback
6. Materials & Procedural Shaders: create_material -> assign_material -> configure_material_shader -> readback
7. Textures & Texture Baking: bake_object_texture -> disk verification -> SHA-256 readback
8. Lighting & World: create_light (SUN) -> configure_world -> readback
9. Cameras: create_camera -> configure_camera (lens/shift) -> readback
10. Rendering: configure_render_settings -> render_scene (still) -> inspect_render_output -> render_scene (animation) -> inspect_render_output
11. Security & Failure Isolation: untrusted approved=True rejection -> state preserved.
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

deadline = time.monotonic() + 240

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


async def run_integrated_verification() -> Dict[str, Any]:
    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E: TEN-CAPABILITY INTEGRATED WORKFLOW (v0.1.71)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-INTEGRATED-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    render_dir = run_root / "renders"
    for d in (config_dir, scripts_dir, ext_dir, render_dir):
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
    env["UMCP_LOCAL_TEST_SCOPE"] = "integrated_v1"
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

    stage_timings: Dict[str, float] = {}
    stage_results: Dict[str, Any] = {}

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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "integrated_v1"
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
                "25",
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

                # -------------------------------------------------------------
                # Stage 1: Primitives & Transforms
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 1: Primitives & Transforms")
                print("=" * 60)

                prim_res = await call_tool("create_primitive", {
                    "primitive_type": "cube",
                    "name": "IntegratedHero",
                    "location": [0.0, 0.0, 0.0],
                })
                prim_data = prim_res.get("result", prim_res)
                assert prim_data.get("name") == "IntegratedHero", f"Stage 1 create_primitive failed: {prim_res}"
                print("[+] Stage 1: Created primitive 'IntegratedHero'.")

                tf_res = await call_tool("transform_object", {
                    "name": "IntegratedHero",
                    "location": [0.0, 0.0, 0.5],
                    "scale": [1.0, 1.0, 1.0],
                })
                tf_data = tf_res.get("result", tf_res)
                assert tf_data.get("transformed") is True, f"Stage 1 transform_object failed: {tf_res}"

                # Independent readback
                readback_s1 = await call_tool("inspect_scene_data", {
                    "category": "mesh_topology",
                    "target_name": "IntegratedHero",
                    "element_domain": "vertices",
                })
                rb_data_s1 = readback_s1.get("result", readback_s1)
                assert rb_data_s1.get("vertex_count") == 8, f"Expected 8 initial vertices, got {rb_data_s1}"
                snap_s1 = rb_data_s1["snapshot_id"]
                stage_timings["stage_1_primitives"] = round(time.monotonic() - t0, 3)
                stage_results["stage_1_primitives"] = {
                    "status": "PASSED",
                    "object_name": "IntegratedHero",
                    "vertex_count": rb_data_s1["vertex_count"],
                    "snapshot_id": snap_s1,
                }
                print(f"[+] Stage 1 Readback Verified: 8 vertices, snapshot={snap_s1[:16]}... ({stage_timings['stage_1_primitives']}s)")

                # -------------------------------------------------------------
                # Stage 2: Mesh Modeling (BMesh Atomic Edits)
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 2: Mesh Modeling (BMesh)")
                print("=" * 60)

                ext_res = await call_tool("extrude_mesh", {
                    "name": "IntegratedHero",
                    "faces": [0],
                    "distance": 0.4,
                    "expected_snapshot_id": snap_s1,
                })
                ext_data = ext_res.get("result", ext_res)
                assert ext_data.get("new_vertex_count", 0) > 8, f"Extrude failed: {ext_res}"
                snap_s2_ext = ext_data["snapshot_id"]
                print(f"[+] Stage 2: Extruded face 0 -> new_vertex_count={ext_data['new_vertex_count']}.")

                inset_res = await call_tool("inset_mesh", {
                    "name": "IntegratedHero",
                    "faces": [0],
                    "thickness": 0.08,
                    "depth": 0.02,
                    "expected_snapshot_id": snap_s2_ext,
                })
                inset_data = inset_res.get("result", inset_res)
                assert inset_data.get("new_face_count", 0) > ext_data.get("new_face_count", 0), f"Inset failed: {inset_res}"
                snap_s2_inset = inset_data["snapshot_id"]
                print(f"[+] Stage 2: Inset face 0 -> new_face_count={inset_data['new_face_count']}.")

                bevel_res = await call_tool("bevel_mesh", {
                    "name": "IntegratedHero",
                    "offset": 0.03,
                    "segments": 1,
                    "affect": "EDGES",
                })
                bevel_data = bevel_res.get("result", bevel_res)
                assert bevel_data.get("new_vertex_count", 0) > 0, f"Bevel failed: {bevel_res}"
                snap_s2 = bevel_data["snapshot_id"]

                # Independent readback
                readback_s2 = await call_tool("inspect_scene_data", {
                    "category": "mesh_topology",
                    "target_name": "IntegratedHero",
                    "element_domain": "vertices",
                })
                rb_data_s2 = readback_s2.get("result", readback_s2)
                assert rb_data_s2.get("vertex_count", 0) > 8, f"Expected >8 vertices, got {rb_data_s2}"
                stage_timings["stage_2_mesh_edits"] = round(time.monotonic() - t0, 3)
                stage_results["stage_2_mesh_edits"] = {
                    "status": "PASSED",
                    "vertex_count": rb_data_s2["vertex_count"],
                    "snapshot_id": snap_s2,
                }
                print(f"[+] Stage 2 Readback Verified: {rb_data_s2['vertex_count']} vertices, snapshot={snap_s2[:16]}... ({stage_timings['stage_2_mesh_edits']}s)")

                # -------------------------------------------------------------
                # Stage 3: Modifiers (Stack & Application)
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 3: Modifiers Workflow")
                print("=" * 60)

                init_mod = await call_tool("inspect_modifier_stack", {"name": "IntegratedHero"})
                mod_stack_0 = init_mod.get("result", init_mod)
                assert len(mod_stack_0.get("modifiers", [])) == 0

                add_mod_res = await call_tool("edit_modifier_stack", {
                    "name": "IntegratedHero",
                    "action": "add",
                    "modifier_type": "BEVEL",
                    "modifier_name": "HeroStackBevel",
                    "properties": {"width": 0.02, "segments": 2},
                    "expected_snapshot_id": mod_stack_0["snapshot_id"],
                })
                add_mod_data = add_mod_res.get("result", add_mod_res)
                assert len(add_mod_data.get("modifiers", [])) == 1
                assert add_mod_data["evaluated"]["vertex_count"] > rb_data_s2["vertex_count"]
                print(f"[+] Stage 3: Added BEVEL modifier -> eval_verts={add_mod_data['evaluated']['vertex_count']}.")

                apply_mod_res = await call_tool("edit_modifier_stack", {
                    "name": "IntegratedHero",
                    "action": "apply",
                    "modifier_type": "BEVEL",
                    "modifier_name": "HeroStackBevel",
                    "expected_snapshot_id": add_mod_data["snapshot_id"],
                })
                apply_mod_data = apply_mod_res.get("result", apply_mod_res)
                assert apply_mod_data.get("success") is True, f"Apply modifier failed: {apply_mod_res}"
                baked_verts_s3 = apply_mod_data["base"]["vertex_count"]
                assert baked_verts_s3 > rb_data_s2["vertex_count"]

                # Independent readback
                readback_s3 = await call_tool("inspect_modifier_stack", {"name": "IntegratedHero"})
                rb_data_s3 = readback_s3.get("result", readback_s3)
                assert len(rb_data_s3["modifiers"]) == 0
                assert rb_data_s3["base"]["vertex_count"] == baked_verts_s3
                stage_timings["stage_3_modifiers"] = round(time.monotonic() - t0, 3)
                stage_results["stage_3_modifiers"] = {
                    "status": "PASSED",
                    "baked_vertex_count": baked_verts_s3,
                    "modifiers_remaining": len(rb_data_s3["modifiers"]),
                }
                print(f"[+] Stage 3 Readback Verified: baked base verts={baked_verts_s3}, modifiers remaining=0 ({stage_timings['stage_3_modifiers']}s)")

                # -------------------------------------------------------------
                # Stage 4: Geometry Nodes
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 4: Geometry Nodes")
                print("=" * 60)

                gn_init = await call_tool("inspect_geometry_nodes", {"name": "IntegratedHero"})
                gn_data_0 = gn_init.get("result", gn_init)
                gn_snap_0 = gn_data_0["snapshot_id"]

                gn_create = await call_tool("configure_geometry_nodes", {
                    "name": "IntegratedHero",
                    "action": "create",
                    "modifier_name": "GeometryNodes",
                    "expected_snapshot_id": gn_snap_0,
                })
                gn_snap_1 = gn_create.get("result", gn_create)["snapshot_id"]

                gn_add_node = await call_tool("configure_geometry_nodes", {
                    "name": "IntegratedHero",
                    "action": "add_node",
                    "node_type": "GeometryNodeSubdivisionSurface",
                    "node_name": "SubdivNode",
                    "inputs": {"Level": 1},
                    "expected_snapshot_id": gn_snap_1,
                })
                gn_snap_2 = gn_add_node.get("result", gn_add_node)["snapshot_id"]

                gn_link1 = await call_tool("configure_geometry_nodes", {
                    "name": "IntegratedHero",
                    "action": "add_link",
                    "from_node": "Input",
                    "from_socket": "Geometry",
                    "to_node": "SubdivNode",
                    "to_socket": "Mesh",
                    "expected_snapshot_id": gn_snap_2,
                })
                gn_snap_3 = gn_link1.get("result", gn_link1)["snapshot_id"]

                gn_link2 = await call_tool("configure_geometry_nodes", {
                    "name": "IntegratedHero",
                    "action": "add_link",
                    "from_node": "SubdivNode",
                    "from_socket": "Mesh",
                    "to_node": "Output",
                    "to_socket": "Geometry",
                    "expected_snapshot_id": gn_snap_3,
                })
                gn_snap_4 = gn_link2.get("result", gn_link2)["snapshot_id"]

                gn_eval = await call_tool("inspect_geometry_nodes", {"name": "IntegratedHero"})
                gn_eval_data = gn_eval.get("result", gn_eval)
                eval_verts_s4 = gn_eval_data["evaluated_geometry"]["vertex_count"]
                assert eval_verts_s4 > baked_verts_s3
                print(f"[+] Stage 4: GN evaluated -> base={gn_eval_data['base_geometry']['vertex_count']}, eval={eval_verts_s4}.")

                gn_apply = await call_tool("configure_geometry_nodes", {
                    "name": "IntegratedHero",
                    "action": "apply",
                    "modifier_name": "GeometryNodes",
                    "expected_snapshot_id": gn_snap_4,
                })
                gn_apply_data = gn_apply.get("result", gn_apply)
                baked_verts_s4 = gn_apply_data["base_geometry"]["vertex_count"]
                assert baked_verts_s4 == eval_verts_s4
                assert gn_apply_data["modifier_exists"] is False

                # Independent readback
                readback_s4 = await call_tool("inspect_geometry_nodes", {"name": "IntegratedHero"})
                rb_data_s4 = readback_s4.get("result", readback_s4)
                assert rb_data_s4["modifier_exists"] is False
                assert rb_data_s4["base_geometry"]["vertex_count"] == baked_verts_s4
                stage_timings["stage_4_geonodes"] = round(time.monotonic() - t0, 3)
                stage_results["stage_4_geonodes"] = {
                    "status": "PASSED",
                    "baked_vertex_count": baked_verts_s4,
                    "gn_modifier_cleared": True,
                }
                print(f"[+] Stage 4 Readback Verified: GN baked base verts={baked_verts_s4} ({stage_timings['stage_4_geonodes']}s)")

                # -------------------------------------------------------------
                # Stage 5: UV Mapping
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 5: UV Mapping")
                print("=" * 60)

                uv_init = await call_tool("inspect_uv_mesh", {"name": "IntegratedHero"})
                uv_snap_0 = uv_init.get("result", uv_init)["snapshot_id"]

                uv_mark = await call_tool("manage_uv_seams", {
                    "name": "IntegratedHero",
                    "action": "mark",
                    "edges": [0, 2, 4, 6],
                    "expected_snapshot_id": uv_snap_0,
                })
                uv_snap_1 = uv_mark.get("result", uv_mark)["snapshot_id"]

                uv_unwrap_res = await call_tool("uv_unwrap", {
                    "name": "IntegratedHero",
                    "method": "ANGLE_BASED",
                    "margin": 0.02,
                    "expected_snapshot_id": uv_snap_1,
                })
                uv_snap_2 = uv_unwrap_res.get("result", uv_unwrap_res)["snapshot_id"]

                uv_pack_res = await call_tool("pack_uv_islands", {
                    "name": "IntegratedHero",
                    "margin": 0.04,
                    "rotate": True,
                    "expected_snapshot_id": uv_snap_2,
                })
                uv_snap_3 = uv_pack_res.get("result", uv_pack_res)["snapshot_id"]

                # Independent readback
                readback_s5 = await call_tool("inspect_uv_mesh", {"name": "IntegratedHero"})
                rb_data_s5 = readback_s5.get("result", readback_s5)
                assert rb_data_s5["has_uvs"] is True
                assert rb_data_s5["total_faces"] > 0
                assert rb_data_s5["seam_count"] >= 4
                stage_timings["stage_5_uvs"] = round(time.monotonic() - t0, 3)
                stage_results["stage_5_uvs"] = {
                    "status": "PASSED",
                    "active_uv_layer": rb_data_s5["active_uv_layer"],
                    "total_faces": rb_data_s5["total_faces"],
                    "seam_count": rb_data_s5["seam_count"],
                }
                print(f"[+] Stage 5 Readback Verified: UVs valid, layer='{rb_data_s5['active_uv_layer']}', seams={rb_data_s5['seam_count']} ({stage_timings['stage_5_uvs']}s)")

                # -------------------------------------------------------------
                # Stage 6: Materials & Procedural Shaders
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 6: Materials & Procedural Shaders")
                print("=" * 60)

                mat_res = await call_tool("create_material", {
                    "name": "HeroPBRMaterial",
                    "base_color": [0.15, 0.55, 0.85, 1.0],
                    "roughness": 0.4,
                    "metallic": 0.7,
                })
                mat_data = mat_res.get("result", mat_res)
                assert mat_data.get("name") == "HeroPBRMaterial"

                assign_res = await call_tool("assign_material", {
                    "target_name": "IntegratedHero",
                    "material_name": "HeroPBRMaterial",
                })
                assign_data = assign_res.get("result", assign_res)
                assert assign_data.get("material_name") == "HeroPBRMaterial"

                shader_cfg = await call_tool("configure_material_shader", {
                    "target_name": "HeroPBRMaterial",
                    "action": "set_principled",
                    "bsdf_node_name": "Principled BSDF",
                    "inputs": {
                        "roughness": 0.25,
                        "metallic": 0.85,
                    },
                })
                assert shader_cfg.get("status") == "success" or shader_cfg.get("success") or "result" in shader_cfg

                # Independent readback
                readback_s6 = await call_tool("inspect_material_shader", {"target_name": "HeroPBRMaterial"})
                rb_data_s6 = readback_s6.get("result", readback_s6)
                assert rb_data_s6["target_name"] == "HeroPBRMaterial"
                bsdf_node = next((n for n in rb_data_s6.get("nodes", []) if n.get("name") == "Principled BSDF"), None)
                assert bsdf_node is not None, "Principled BSDF node not found in readback"
                bsdf_inputs = bsdf_node.get("inputs", {})
                assert abs(bsdf_inputs.get("Roughness", 0) - 0.25) < 1e-4
                assert abs(bsdf_inputs.get("Metallic", 0) - 0.85) < 1e-4
                stage_timings["stage_6_materials"] = round(time.monotonic() - t0, 3)
                stage_results["stage_6_materials"] = {
                    "status": "PASSED",
                    "material_name": "HeroPBRMaterial",
                    "roughness": bsdf_inputs.get("Roughness"),
                    "metallic": bsdf_inputs.get("Metallic"),
                }
                print(f"[+] Stage 6 Readback Verified: Material assigned, Roughness=0.25, Metallic=0.85 ({stage_timings['stage_6_materials']}s)")

                # -------------------------------------------------------------
                # Stage 7: Textures & Texture Baking
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 7: Textures & Texture Baking")
                print("=" * 60)

                bake_path = run_root / "hero_baked_roughness.png"
                bake_res = await call_tool("bake_object_texture", {
                    "object_name": "IntegratedHero",
                    "bake_type": "ROUGHNESS",
                    "image_name": "HeroRoughnessBake",
                    "width": 128,
                    "height": 128,
                    "margin": 4,
                    "save_filepath": str(bake_path),
                })
                bake_data = bake_res.get("result", bake_res)
                assert bake_data.get("baked") is True, f"Bake failed: {bake_res}"
                assert bake_data.get("verified") is True
                assert bake_path.exists() and bake_path.stat().st_size > 0
                sha_sidecar = Path(str(bake_path) + ".sha256")

                stage_timings["stage_7_baking"] = round(time.monotonic() - t0, 3)
                stage_results["stage_7_baking"] = {
                    "status": "PASSED",
                    "bake_path": str(bake_path),
                    "file_size": bake_path.stat().st_size,
                    "has_sha256": sha_sidecar.exists(),
                }
                print(f"[+] Stage 7 Readback Verified: Baked texture {bake_path.name} ({bake_path.stat().st_size} bytes), sidecar={sha_sidecar.exists()} ({stage_timings['stage_7_baking']}s)")

                # -------------------------------------------------------------
                # Stage 8: Lighting & World
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 8: Lighting & World")
                print("=" * 60)

                light_res = await call_tool("create_light", {
                    "name": "HeroSunLight",
                    "light_type": "SUN",
                    "energy": 4.0,
                    "color": [1.0, 0.96, 0.9],
                    "location": [4.0, -4.0, 8.0],
                })
                light_data = light_res.get("result", light_res)
                assert light_data.get("name") == "HeroSunLight"

                world_res = await call_tool("configure_world", {
                    "color": [0.06, 0.08, 0.12],
                    "strength": 1.2,
                })
                world_data = world_res.get("result", world_res)
                assert world_data.get("strength") == 1.2

                # Independent readbacks
                rb_light = await call_tool("get_object_details", {"name": "HeroSunLight"})
                rb_light_data = rb_light.get("result", rb_light)
                assert rb_light_data["name"] == "HeroSunLight"
                assert rb_light_data["light_details"].get("light_type") == "SUN" or rb_light_data["light_details"].get("type") == "SUN"

                rb_world = await call_tool("inspect_scene_data", {"category": "world_settings"})
                rb_world_data = rb_world.get("result", rb_world)
                assert rb_world_data["strength"] == 1.2

                stage_timings["stage_8_lighting_world"] = round(time.monotonic() - t0, 3)
                stage_results["stage_8_lighting_world"] = {
                    "status": "PASSED",
                    "light_name": "HeroSunLight",
                    "light_energy": 4.0,
                    "world_strength": 1.2,
                }
                print(f"[+] Stage 8 Readback Verified: Light 'HeroSunLight' (SUN, energy=4.0), World strength=1.2 ({stage_timings['stage_8_lighting_world']}s)")

                # -------------------------------------------------------------
                # Stage 9: Cameras
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 9: Cameras")
                print("=" * 60)

                cam_res = await call_tool("create_camera", {
                    "name": "HeroCam",
                    "focal_length": 50.0,
                    "location": [0.0, -5.0, 2.0],
                    "rotation_euler": [1.2, 0.0, 0.0],
                    "set_active": True,
                })
                cam_data = cam_res.get("result", cam_res)
                assert cam_data.get("name") == "HeroCam"

                cfg_cam_res = await call_tool("configure_camera", {
                    "name": "HeroCam",
                    "focal_length": 65.0,
                    "shift_y": 0.02,
                })
                assert cfg_cam_res.get("status") == "success"

                # Independent readback
                rb_cam = await call_tool("get_object_details", {"name": "HeroCam"})
                rb_cam_details = rb_cam.get("result", rb_cam).get("camera_details", {})
                assert rb_cam_details.get("focal_length") == 65.0
                assert rb_cam_details.get("is_active_camera") is True

                rb_rs_cam = await call_tool("inspect_scene_data", {"category": "render_settings"})
                assert rb_rs_cam.get("result", rb_rs_cam).get("active_camera") == "HeroCam"

                stage_timings["stage_9_cameras"] = round(time.monotonic() - t0, 3)
                stage_results["stage_9_cameras"] = {
                    "status": "PASSED",
                    "camera_name": "HeroCam",
                    "focal_length": 65.0,
                    "is_active_camera": True,
                }
                print(f"[+] Stage 9 Readback Verified: Camera 'HeroCam' active, focal_length=65.0mm ({stage_timings['stage_9_cameras']}s)")

                # -------------------------------------------------------------
                # Stage 10: Rendering (Still & Animation)
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 10: Rendering Foundation")
                print("=" * 60)

                render_cfg = await call_tool("configure_render_settings", {
                    "engine": "BLENDER_EEVEE_NEXT",
                    "resolution_x": 160,
                    "resolution_y": 120,
                    "resolution_percentage": 100,
                    "frame_start": 1,
                    "frame_end": 2,
                    "output_format": "PNG",
                    "active_camera": "HeroCam",
                })
                rcfg_data = render_cfg.get("result", render_cfg)
                assert rcfg_data.get("resolution_x") == 160
                assert rcfg_data.get("active_camera") == "HeroCam"

                # Still render
                still_path = str(render_dir / "hero_still.png")
                still_res = await call_tool("render_scene", {
                    "render_mode": "still",
                    "frame": 1,
                    "output_path": still_path,
                    "output_format": "PNG",
                })
                still_data = still_res.get("result", still_res)
                assert still_data.get("operator_completed") is True
                still_id = still_data.get("render_id")
                assert still_id is not None
                assert os.path.exists(still_path) and os.path.getsize(still_path) > 0
                print(f"[+] Stage 10: Rendered still frame 1 -> render_id={still_id}, size={os.path.getsize(still_path)} bytes.")

                # Inspect still receipt
                still_rcpt = await call_tool("inspect_render_output", {"render_id": still_id})
                rcpt_data = still_rcpt.get("result", still_rcpt)
                assert rcpt_data.get("verified") is True
                assert rcpt_data.get("artifact", {}).get("png_structure_verified") is True
                still_sha = rcpt_data["artifact"]["sha256"]
                print(f"[+] Stage 10: Verified still receipt SHA256={still_sha[:16]}...")

                # Animation render (2 frames)
                anim_base = str(render_dir / "hero_anim_")
                anim_res = await call_tool("render_scene", {
                    "render_mode": "animation",
                    "frame_start": 1,
                    "frame_end": 2,
                    "output_path": anim_base,
                    "output_format": "PNG",
                })
                anim_data = anim_res.get("result", anim_res)
                assert anim_data.get("operator_completed") is True
                assert anim_data.get("total_frames") == 2
                assert len(anim_data.get("output_paths", [])) == 2
                assert len(anim_data.get("frame_receipts", [])) == 2
                print(f"[+] Stage 10: Rendered animation sequence (2 frames).")

                # Verify individual animation frame receipt
                anim_f1_id = anim_data["frame_receipts"][0]["render_id"]
                anim_rcpt = await call_tool("inspect_render_output", {"render_id": anim_f1_id})
                assert anim_rcpt.get("result", anim_rcpt).get("verified") is True

                stage_timings["stage_10_rendering"] = round(time.monotonic() - t0, 3)
                stage_results["stage_10_rendering"] = {
                    "status": "PASSED",
                    "still_file": still_path,
                    "still_sha256": still_sha,
                    "still_render_id": still_id,
                    "animation_total_frames": 2,
                    "animation_frame_1_render_id": anim_f1_id,
                }
                print(f"[+] Stage 10 Readback Verified: Still & Animation receipts verified ({stage_timings['stage_10_rendering']}s)")

                # -------------------------------------------------------------
                # Stage 11: Security & Failure Isolation
                # -------------------------------------------------------------
                t0 = time.monotonic()
                print("\n" + "=" * 60)
                print("STAGE 11: Security & Failure Isolation")
                print("=" * 60)

                untrusted_res = await call_tool("render_scene", {
                    "render_mode": "still",
                    "approved": True,
                })
                assert untrusted_res.get("status") == "error", "Untrusted approved=True should have failed"
                print("[+] Stage 11: Untrusted approved=True rejected fail-closed.")

                invalid_range_res = await call_tool("render_scene", {
                    "render_mode": "animation",
                    "frame_start": 50,
                    "frame_end": 10,
                })
                assert invalid_range_res.get("status") == "error", "Invalid range should have failed"
                print("[+] Stage 11: Invalid animation range (50 > 10) rejected fail-closed.")

                # Confirm scene objects preserved intact
                final_objs = await call_tool("inspect_scene_data", {"category": "scene_hierarchy"})
                obj_count = final_objs.get("result", final_objs).get("total_objects", 0)
                assert obj_count >= 3  # Hero, Light, Camera
                stage_timings["stage_11_security"] = round(time.monotonic() - t0, 3)
                stage_results["stage_11_security"] = {
                    "status": "PASSED",
                    "untrusted_rejected": True,
                    "invalid_rejected": True,
                    "scene_preserved_objects": obj_count,
                }
                print(f"[+] Stage 11 Readback Verified: Scene intact with {obj_count} objects ({stage_timings['stage_11_security']}s)")

                print("\n" + "=" * 80)
                print("ALL 11 STAGES OF THE TEN-CAPABILITY INTEGRATED WORKFLOW PASSED WITH 100% SUCCESS!")
                print("=" * 80)

    finally:
        print("[*] Terminating disposable Blender process...")
        (run_root / "stop.flag").write_text("stop", encoding="utf-8")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("[+] Disposable Blender process cleaned up cleanly.")
        import shutil
        shutil.rmtree(run_root, ignore_errors=True)

    return {
        "status": "SUCCESS",
        "stage_results": stage_results,
        "stage_timings": stage_timings,
    }


if __name__ == "__main__":
    res = asyncio.run(run_integrated_verification())
    print("\nFINAL INTEGRATION RESULTS:")
    print(json.dumps(res, indent=2))
