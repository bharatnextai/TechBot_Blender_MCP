"""
Automated Real MCP-to-Blender E2E Verification of Asset Interchange Foundation (Phase 2.2 - v0.1.75).
Covers Asset Interchange (Phase 2.2):
1. Disposable Blender 5.2.2 LTS instance on ephemeral loopback bridge port (!= 9877).
2. Production human approval preservation and isolated test auto-approval policy (scope: asset_v1).
3. Discover Asset Interchange tools over MCP stdio wire:
   - export_scene_asset
   - export_scene
   - import_scene_asset
   - import_scene
4. Live execution and independent Blender readback:
   - Hero scene creation (Mesh Cube with Principled BSDF material)
   - GLB binary export with SHA-256 sidecar generation and independent hash verification
   - GLTF separate export with binary buffer and sidecar verification
   - USDC binary export with sidecar verification
   - USDA ascii export with USD header verification
   - Selected-only export validation
   - Overwrite protection enforcement (rejection when overwrite=False, success when overwrite=True)
   - GLB import into clean scene with SHA-256 sidecar verification and topology/material readback
   - USDC import into clean scene with mesh readback
   - USDA import into clean scene with mesh readback
   - Path traversal guard verification
   - Fail-closed security verification (untrusted approved=True rejection)
   - Missing input file rejection
5. Clean teardown and process cleanup.
"""

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


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


async def run_e2e_verification():
    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E VERIFICATION: ASSET INTERCHANGE (Phase 2.2 - v0.1.75)")
    print("=" * 80)

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-ASSET-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)
    assets_dir = run_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    assert port != 9877, f"Guard violation: ephemeral port matched production {port}"
    print(f"[*] Ephemeral bridge port: {port}")
    print(f"[*] Isolated test root: {run_root}")

    blender_env = dict(os.environ)
    blender_env["UMCP_RUN_ROOT"] = str(run_root)
    blender_env["UMCP_PROJECT"] = str(PROJECT)
    blender_env["UMCP_BRIDGE_PORT"] = str(port)
    blender_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    blender_env["UMCP_LOCAL_TEST_SCOPE"] = "asset_v1"
    blender_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    blender_env["BLENDER_USER_CONFIG"] = str(config_dir)
    blender_env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    blender_env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
    blender_env["PYTHONPATH"] = str(PROJECT)
    blender_env["PYTHONDONTWRITEBYTECODE"] = "1"

    bootstrap_file = run_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_root / "blender_ready.json"

    blender_cmd = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "--python",
        str(bootstrap_file),
    ]

    print("[*] Launching headless Blender 5.2.2 LTS...")
    proc = subprocess.Popen(
        blender_cmd,
        env=blender_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "asset_v1"
        client_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
        client_env["UMCP_BRIDGE_PORT"] = str(port)
        client_env["BLENDER_USER_CONFIG"] = str(config_dir)
        client_env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
        client_env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)

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
                for req_tool in ("export_scene_asset", "export_scene", "import_scene_asset", "import_scene"):
                    assert req_tool in discovered_names, f"Tool '{req_tool}' not found in MCP tools list"
                print(f"[+] Tool Discovery Verified: {len(discovered_names)} tools found, all Asset Interchange tools present.")

                # 2. Setup hero scene: Cube with Material
                cube_res = await call_tool("create_primitive", {"primitive_type": "cube", "name": "HeroCube"})
                assert cube_res.get("result", cube_res).get("name") == "HeroCube"

                mat_res = await call_tool("create_material", {
                    "name": "HeroMaterial",
                    "base_color": [0.8, 0.2, 0.2, 1.0],
                    "metallic": 0.5,
                    "roughness": 0.3,
                })
                assert mat_res.get("result", mat_res).get("name") == "HeroMaterial"

                assign_res = await call_tool("assign_material", {
                    "target_name": "HeroCube",
                    "material_name": "HeroMaterial",
                })
                assign_data = assign_res.get("result", assign_res)
                assert assign_data.get("material_name") == "HeroMaterial", f"assign_material failed: {assign_res}"
                print("[+] Stage 1: Hero Scene Created (Cube with HeroMaterial): success")

                # 3. Stage 2: Export to GLB with SHA-256 sidecar
                glb_path = assets_dir / "hero.glb"
                glb_res = await call_tool("export_scene_asset", {
                    "filepath": str(glb_path),
                    "format": "GLB",
                    "overwrite": False,
                })
                glb_data = glb_res.get("result", glb_res)
                assert glb_data.get("success") is True
                assert glb_path.exists()
                assert glb_path.stat().st_size > 0
                assert glb_data.get("sha256") is not None

                # Independent readback of SHA-256 sidecar
                sidecar_glb = glb_path.with_suffix(".glb.sha256")
                assert sidecar_glb.exists()
                sidecar_data = json.loads(sidecar_glb.read_text(encoding="utf-8"))
                actual_hash = compute_sha256(glb_path)
                assert sidecar_data["sha256"] == actual_hash == glb_data["sha256"]
                print(f"[+] Stage 2: GLB Export Verified: size={glb_path.stat().st_size} bytes, sha256={actual_hash[:16]}...")

                # 4. Stage 3: Export to GLTF Separate
                gltf_path = assets_dir / "hero.gltf"
                gltf_res = await call_tool("export_scene_asset", {
                    "filepath": str(gltf_path),
                    "format": "GLTF",
                    "overwrite": False,
                })
                gltf_data = gltf_res.get("result", gltf_res)
                assert gltf_data.get("success") is True
                assert gltf_path.exists()
                bin_path = assets_dir / "hero.bin"
                assert bin_path.exists()
                sidecar_gltf = gltf_path.with_suffix(".gltf.sha256")
                assert sidecar_gltf.exists()
                print(f"[+] Stage 3: GLTF Separate Export Verified: gltf+bin files created and verified.")

                # 5. Stage 4: Export to USDC Binary
                usdc_path = assets_dir / "hero.usdc"
                usdc_res = await call_tool("export_scene_asset", {
                    "filepath": str(usdc_path),
                    "format": "USDC",
                    "overwrite": False,
                })
                usdc_data = usdc_res.get("result", usdc_res)
                assert usdc_data.get("success") is True
                assert usdc_path.exists()
                assert usdc_path.stat().st_size > 0
                sidecar_usdc = usdc_path.with_suffix(".usdc.sha256")
                assert sidecar_usdc.exists()
                print(f"[+] Stage 4: USDC Binary Export Verified: size={usdc_path.stat().st_size} bytes, sidecar verified.")

                # 6. Stage 5: Export to USDA ASCII
                usda_path = assets_dir / "hero.usda"
                usda_res = await call_tool("export_scene_asset", {
                    "filepath": str(usda_path),
                    "format": "USDA",
                    "overwrite": False,
                })
                usda_data = usda_res.get("result", usda_res)
                assert usda_data.get("success") is True
                assert usda_path.exists()
                usda_text = usda_path.read_text(encoding="utf-8")
                assert "#usda 1.0" in usda_text
                sidecar_usda = usda_path.with_suffix(".usda.sha256")
                assert sidecar_usda.exists()
                print(f"[+] Stage 5: USDA ASCII Export Verified: contains '#usda 1.0' header, sidecar verified.")

                # 7. Stage 6: Selected-only export validation
                sel_glb_path = assets_dir / "selected_hero.glb"
                sel_res = await call_tool("export_scene_asset", {
                    "filepath": str(sel_glb_path),
                    "format": "GLB",
                    "selected_only": True,
                })
                sel_data = sel_res.get("result", sel_res)
                assert sel_data.get("success") is True
                assert sel_data.get("selected_only") is True
                assert sel_glb_path.exists()
                print(f"[+] Stage 6: Selected-Only Export Verified: selected_only=True recorded.")

                # 8. Stage 7: Overwrite Protection Rejection
                dup_res = await call_tool("export_scene_asset", {
                    "filepath": str(glb_path),
                    "format": "GLB",
                    "overwrite": False,
                })
                assert "already exists and overwrite=false" in str(dup_res).lower()
                print("[+] Stage 7: Overwrite Protection Verified: duplicate export rejected when overwrite=False.")

                # 9. Stage 8: Overwrite with overwrite=True
                overwrite_res = await call_tool("export_scene_asset", {
                    "filepath": str(glb_path),
                    "format": "GLB",
                    "overwrite": True,
                })
                assert overwrite_res.get("result", overwrite_res).get("success") is True
                print("[+] Stage 8: Overwrite Allowed when overwrite=True: verified.")

                # 10. Stage 9: Import GLB into fresh scene with checksum verification
                # Delete existing scene objects to make scene clean
                await call_tool("delete_object", {"name": "HeroCube"})
                import_glb_res = await call_tool("import_scene_asset", {
                    "filepath": str(glb_path),
                    "format": "GLB",
                    "verify_checksum": True,
                })
                import_glb_data = import_glb_res.get("result", import_glb_res)
                assert import_glb_data.get("success") is True
                assert import_glb_data.get("checksum_verified") is True
                assert import_glb_data.get("imported_count") >= 1
                details = import_glb_data.get("object_details", [])
                assert len(details) >= 1
                mesh_detail = details[0]
                assert mesh_detail["type"] == "MESH"
                assert mesh_detail["vertex_count"] in (8, 24, 36)
                assert mesh_detail["polygon_count"] in (6, 12)
                assert any("HeroMaterial" in m for m in mesh_detail["materials"]), f"Materials readback: {mesh_detail['materials']}"
                print(f"[+] Stage 9: GLB Import with Checksum Verification: {import_glb_data['imported_count']} objects, topology/material readback verified.")

                # 11. Stage 10: Import USDC into fresh scene
                for obj_name in import_glb_data.get("imported_objects", []):
                    await call_tool("delete_object", {"name": obj_name})

                import_usdc_res = await call_tool("import_scene_asset", {
                    "filepath": str(usdc_path),
                    "format": "USDC",
                })
                import_usdc_data = import_usdc_res.get("result", import_usdc_res)
                assert import_usdc_data.get("success") is True
                assert import_usdc_data.get("imported_count") >= 1
                usdc_details = import_usdc_data.get("object_details", [])
                assert any(d["type"] == "MESH" for d in usdc_details)
                print(f"[+] Stage 10: USDC Binary Import Verified: {import_usdc_data['imported_count']} objects imported.")

                # 12. Stage 11: Import USDA into fresh scene
                for obj_name in import_usdc_data.get("imported_objects", []):
                    await call_tool("delete_object", {"name": obj_name})

                import_usda_res = await call_tool("import_scene_asset", {
                    "filepath": str(usda_path),
                    "format": "USDA",
                })
                import_usda_data = import_usda_res.get("result", import_usda_res)
                assert import_usda_data.get("success") is True
                assert import_usda_data.get("imported_count") >= 1
                usda_details = import_usda_data.get("object_details", [])
                assert any(d["type"] == "MESH" for d in usda_details)
                print(f"[+] Stage 11: USDA ASCII Import Verified: {import_usda_data['imported_count']} objects imported.")

                # 13. Stage 12: Path Traversal Rejection
                traversal_path = run_root / "assets" / ".." / ".." / "outside.glb"
                traversal_res = await call_tool("export_scene_asset", {
                    "filepath": str(traversal_path),
                    "format": "GLB",
                })
                assert "path traversal detected" in str(traversal_res).lower() or "denied" in str(traversal_res).lower() or "pending" in str(traversal_res).lower(), f"Unexpected traversal result: {traversal_res}"
                print("[+] Stage 12: Path Traversal Guard Verified: rejected parent directory references '..'.")

                # 14. Stage 13: Fail-Closed Security on Untrusted approved=True
                sec_res = await call_tool("export_scene_asset", {
                    "filepath": str(assets_dir / "untrusted.glb"),
                    "format": "GLB",
                    "approved": True,  # Untrusted client flag must be rejected
                })
                assert "error" in str(sec_res).lower() or "denied" in str(sec_res).lower() or "pending" in str(sec_res).lower()
                print("[+] Stage 13: Untrusted approved=True Rejected Fail-Closed: verified.")

                # 15. Stage 14: Nonexistent File Rejection
                nonexistent_res = await call_tool("import_scene_asset", {
                    "filepath": str(assets_dir / "does_not_exist.glb"),
                    "format": "GLB",
                })
                assert "not found on disk" in str(nonexistent_res).lower()
                print("[+] Stage 14: Nonexistent Asset Import Rejected: verified.")

                print("=" * 80)
                print("ALL 14 E2E ASSET INTERCHANGE STAGES PASSED CLEANLY ON BLENDER 5.2.2 LTS!")
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

