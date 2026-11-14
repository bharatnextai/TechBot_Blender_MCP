"""
Disposable Blender 5.2.2 Live Viewport Capture Verification
Verifies TASK-UMCP-0024 / Item 5:
1. Disposable Blender 5.2.2 instance on an ephemeral loopback bridge port.
2. Official MCP stdio ClientSession calling capture_viewport.
3. CAMERA mode capture producing valid base64-encoded PNG.
4. Non-mutating render settings restoration via try...finally.
5. Pre- and post-capture scene inventory comparison.
6. Clean shutdown and zero persistent state.
"""

import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import struct
import sys
import tempfile
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

bootstrap_code = r"""
import bpy, json, os, sys, time
from pathlib import Path

root = Path(os.environ["UMCP_RUN_ROOT"])
project = Path(os.environ["UMCP_PROJECT"])
sys.path.insert(0, str(project))
import blender_addon.universal_mcp as addon
addon.register()

from blender_addon.universal_mcp.operators import get_server_instance

port = int(os.environ["UMCP_BRIDGE_PORT"])
scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

def write(name, val):
    (root / name).write_text(json.dumps(val, indent=2, sort_keys=True, default=str), encoding="utf-8")

def state_snapshot():
    scene = bpy.context.scene
    render = scene.render
    viewport = []
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region_3d = area.spaces.active.region_3d
            viewport.append({
                "view_location": list(region_3d.view_location),
                "view_rotation": list(region_3d.view_rotation),
                "view_distance": float(region_3d.view_distance),
                "view_perspective": region_3d.view_perspective,
                "lens": float(area.spaces.active.lens),
            })
    return {
        "objects": sorted(bpy.data.objects.keys()),
        "materials": sorted(bpy.data.materials.keys()),
        "active_object": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        "mode": bpy.context.mode,
        "filepath": bpy.data.filepath,
        "dirty": bool(bpy.data.is_dirty),
        "render": {
            "resolution_x": int(render.resolution_x),
            "resolution_y": int(render.resolution_y),
            "resolution_percentage": int(render.resolution_percentage),
            "filepath": render.filepath,
            "file_format": render.image_settings.file_format,
        },
        "viewports": viewport,
    }

write("state_before.json", state_snapshot())

def observe():
    if (root / "stop").exists():
        server = get_server_instance(port)
        if server and server.running:
            server.stop()
        write("final_state.json", {
            "pid": os.getpid(),
            "objects": sorted(bpy.data.objects.keys()),
            "bridge_running": bool(server.running) if server else False,
            "state": state_snapshot(),
        })
        bpy.ops.wm.quit_blender()
        return None
    return 0.1

def start_bridge():
    try:
        server = get_server_instance(port)
        if not server.running:
            outcome = bpy.ops.umcp.start_bridge()
            if "FINISHED" not in outcome:
                raise RuntimeError("Failed to start bridge: " + repr(outcome))
        write("ready.json", {
            "pid": os.getpid(),
            "port": port,
            "blender": bpy.app.version_string,
            "background": bpy.app.background,
            "objects": sorted(bpy.data.objects.keys()),
        })
    except Exception as exc:
        write("startup_error.json", {"error": str(exc)})
    return None

bpy.app.timers.register(observe, first_interval=0.1, persistent=True)
bpy.app.timers.register(start_bridge, first_interval=1.0)
"""


def main():
    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CAPTURE-LIVE-"))
    boot = run_root / "bootstrap.py"
    boot.write_text(bootstrap_code, encoding="utf-8")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    if port == 9877:
        raise RuntimeError("Refusing production port 9877")

    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(PROJECT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UMCP_PROJECT": str(PROJECT),
        "UMCP_RUN_ROOT": str(run_root),
        "UMCP_BRIDGE_PORT": str(port),
    })
    for key in ("CONFIG", "SCRIPTS", "EXTENSIONS", "DATAFILES", "RESOURCES"):
        folder = run_root / key.lower()
        folder.mkdir(exist_ok=True)
        env["BLENDER_USER_" + key] = str(folder)
    private_temp = run_root / "temp"
    private_temp.mkdir(exist_ok=True)
    env["TEMP"] = str(private_temp)
    env["TMP"] = str(private_temp)
    env["TMPDIR"] = str(private_temp)

    log = (run_root / "blender.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(BLENDER), "--factory-startup", "--disable-autoexec", "--python", str(boot)],
        cwd=str(PROJECT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )

    print("CAPTURE_LIVE_ROOT=" + str(run_root), flush=True)
    print("BLENDER_PID=" + str(process.pid) + " EPHEMERAL_PORT=" + str(port), flush=True)

    try:
        deadline = time.monotonic() + 45
        while not (run_root / "ready.json").exists():
            if (run_root / "startup_error.json").exists() or process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Disposable Blender failed to start or become ready")
            time.sleep(0.1)

        async def run_mcp_probes():
            stdio_env = dict(env)
            params = StdioServerParameters(
                command=sys.executable,
                args=[
                    "-B", "-m", "mcp_service.app",
                    "--transport", "stdio",
                    "--bridge-host", "127.0.0.1",
                    "--bridge-port", str(port),
                    "--bridge-timeout", "15.0",
                ],
                env=stdio_env,
                cwd=str(PROJECT),
            )
            with (run_root / "mcp_stderr.log").open("w", encoding="utf-8") as errlog:
                async with stdio_client(params, errlog=errlog) as streams:
                    async with ClientSession(*streams) as session:
                        init = await session.initialize()
                        tools = await session.list_tools()
                        names = {t.name for t in tools.tools}
                        if "capture_viewport" not in names:
                            raise RuntimeError("capture_viewport not found in MCP tool list: " + repr(names))

                        # Read scene summary before
                        summary_before = await session.call_tool("get_scene_summary", arguments={})
                        summary_before_data = json.loads(summary_before.content[0].text).get("result", {})
                        render_before_response = await session.call_tool(
                            "inspect_scene_data", arguments={"category": "render_settings"}
                        )
                        render_before_payload = json.loads(render_before_response.content[0].text)
                        render_before = render_before_payload.get("result", {})
                        (run_root / "render_settings_before.json").write_text(
                            json.dumps(render_before, indent=2), encoding="utf-8"
                        )

                        # Probe 1: CAMERA mode capture
                        cam_res = await session.call_tool("capture_viewport", arguments={
                            "mode": "CAMERA",
                            "width": 320,
                            "height": 240,
                        })
                        cam_payload = json.loads(cam_res.content[0].text)
                        (run_root / "capture_camera_response.json").write_text(
                            json.dumps(cam_payload, indent=2), encoding="utf-8"
                        )
                        if cam_payload.get("status") != "success":
                            raise RuntimeError("capture_viewport CAMERA mode failed: " + repr(cam_payload))

                        cam_result = cam_payload.get("result", {})
                        raw_bytes = base64.b64decode(cam_result.get("image_base64", ""), validate=True)
                        png_header_valid = raw_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                        png_dimensions = struct.unpack(">II", raw_bytes[16:24]) if png_header_valid and len(raw_bytes) >= 24 else None
                        (run_root / "capture_camera.png").write_bytes(raw_bytes)

                        # Probe 2: VIEWPORT mode capture from the disposable interactive 3D View.
                        viewport_res = await session.call_tool("capture_viewport", arguments={
                            "mode": "VIEWPORT",
                            "width": 256,
                            "height": 192,
                        })
                        viewport_payload = json.loads(viewport_res.content[0].text)
                        (run_root / "capture_viewport_response.json").write_text(
                            json.dumps(viewport_payload, indent=2), encoding="utf-8"
                        )
                        if viewport_payload.get("status") != "success":
                            raise RuntimeError("capture_viewport VIEWPORT mode failed: " + repr(viewport_payload))
                        viewport_result = viewport_payload.get("result", {})
                        viewport_bytes = base64.b64decode(viewport_result.get("image_base64", ""), validate=True)
                        viewport_png_valid = viewport_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                        viewport_dimensions = struct.unpack(">II", viewport_bytes[16:24]) if viewport_png_valid and len(viewport_bytes) >= 24 else None
                        (run_root / "capture_viewport.png").write_bytes(viewport_bytes)

                        # Read scene summary after
                        summary_after = await session.call_tool("get_scene_summary", arguments={})
                        summary_after_data = json.loads(summary_after.content[0].text).get("result", {})

                        # Probe 2: Settings preservation check via inspect_scene_data
                        render_inspect = await session.call_tool("inspect_scene_data", arguments={"category": "render_settings"})
                        render_data = json.loads(render_inspect.content[0].text).get("result", {})

                        expected_render_keys = ("resolution_x", "resolution_y", "resolution_percentage", "filepath", "file_format")
                        render_restored = all(render_data.get(key) == render_before.get(key) for key in expected_render_keys)

                        evidence = {
                            "camera_capture_success": cam_payload.get("status") == "success",
                            "png_bytes_length": len(raw_bytes),
                            "png_header_valid": png_header_valid,
                            "declared_width": cam_result.get("width"),
                            "declared_height": cam_result.get("height"),
                            "declared_mode": cam_result.get("mode"),
                            "declared_format": cam_result.get("format"),
                            "declared_size_bytes": cam_result.get("size_bytes"),
                            "png_dimensions": list(png_dimensions) if png_dimensions else None,
                            "read_only_tier": cam_result.get("read_only"),
                            "viewport_capture_success": viewport_payload.get("status") == "success",
                            "viewport_png_header_valid": viewport_png_valid,
                            "viewport_png_dimensions": list(viewport_dimensions) if viewport_dimensions else None,
                            "viewport_png_dimensions_match_request": viewport_dimensions == (256, 192),
                            "viewport_reported_dimensions_match_request": (viewport_result.get("width"), viewport_result.get("height")) == (256, 192),
                            "viewport_reported_size_matches_bytes": viewport_result.get("size_bytes") == len(viewport_bytes),
                            "viewport_declared_mode_matches_request": viewport_result.get("mode") == "VIEWPORT",
                            "viewport_declared_format_is_png": viewport_result.get("format") == "png",
                            "viewport_read_only_tier": viewport_result.get("read_only") is True,
                            "render_settings_before": render_before,
                            "render_settings_after": render_data,
                            "render_settings_restored": render_restored,
                            "scene_objects_before": summary_before_data.get("total_objects"),
                            "scene_objects_after": summary_after_data.get("total_objects"),
                            "scene_unmutated": summary_before_data.get("total_objects") == summary_after_data.get("total_objects"),
                            "service_version": init.serverInfo.version,
                            "port": port,
                            "pid": process.pid,
                        }
                        evidence["png_dimensions_match_request"] = png_dimensions == (320, 240)
                        evidence["reported_dimensions_match_request"] = (cam_result.get("width"), cam_result.get("height")) == (320, 240)
                        evidence["reported_size_matches_bytes"] = cam_result.get("size_bytes") == len(raw_bytes)
                        evidence["declared_mode_matches_request"] = cam_result.get("mode") == "CAMERA"
                        evidence["declared_format_is_png"] = cam_result.get("format") == "png"
                        evidence["read_only_tier"] = cam_result.get("read_only") is True
                        evidence["scene_unmutated"] = summary_before_data.get("total_objects") == summary_after_data.get("total_objects")
                        if not (png_header_valid and evidence["scene_unmutated"] and len(raw_bytes) > 100
                                and evidence["png_dimensions_match_request"] and evidence["reported_dimensions_match_request"]
                                and evidence["reported_size_matches_bytes"] and evidence["declared_mode_matches_request"]
                                and evidence["declared_format_is_png"] and evidence["read_only_tier"] and render_restored
                                and evidence["viewport_capture_success"] and viewport_png_valid and len(viewport_bytes) > 100
                                and evidence["viewport_png_dimensions_match_request"]
                                and evidence["viewport_reported_dimensions_match_request"]
                                and evidence["viewport_reported_size_matches_bytes"]
                                and evidence["viewport_declared_mode_matches_request"]
                                and evidence["viewport_declared_format_is_png"] and evidence["viewport_read_only_tier"]):
                            raise AssertionError("Live capture validation assertions failed: " + repr(evidence))

                        (run_root / "capture_verification_evidence.json").write_text(
                            json.dumps(evidence, indent=2), encoding="utf-8"
                        )

                        print("CAPTURE_LIVE_VERIFIED camera_png=True viewport_png=True dims=320x240,256x192", flush=True)

        asyncio.run(run_mcp_probes())

    finally:
        (run_root / "stop").touch()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()
        (run_root / "process_exit.json").write_text(json.dumps({"returncode": process.returncode}), encoding="utf-8")
        if (run_root / "state_before.json").exists() and (run_root / "final_state.json").exists():
            before_state = json.loads((run_root / "state_before.json").read_text(encoding="utf-8"))
            final_record = json.loads((run_root / "final_state.json").read_text(encoding="utf-8"))
            after_state = final_record.get("state", {})
            state_unchanged = before_state == after_state
            final_evidence = {
                "state_before": before_state,
                "state_after": after_state,
                "state_unchanged": state_unchanged,
                "bridge_stopped": final_record.get("bridge_running") is False,
                "blender_exit_code": process.returncode,
            }
            (run_root / "capture_final_state_evidence.json").write_text(
                json.dumps(final_evidence, indent=2), encoding="utf-8"
            )
            if state_unchanged and (run_root / "capture_verification_evidence.json").exists():
                evidence_path = run_root / "capture_verification_evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence.update(final_evidence)
                evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            if not state_unchanged or final_record.get("bridge_running") is not False or process.returncode != 0:
                raise AssertionError("Capture changed Blender state or failed clean shutdown: " + json.dumps(final_evidence))
        print("EVIDENCE_ROOT=" + str(run_root), flush=True)


if __name__ == "__main__":
    main()
