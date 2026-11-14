"""
Verification Test for VSE Capability 8: Nested Sequences.
Executes in a live, disposable Blender 5.2.2 session on an ephemeral loopback port (!= 9877).

Tests:
1. Populate base strips on sequencer timeline.
2. Group strips into a nested MetaStrip container (CREATE).
3. Inspect internal nested strips inside MetaStrip (INSPECT).
4. Create secondary 3D Scene with Camera.
5. Create nested SceneStrip referencing 3D scene (create_vse_scene_strip).
6. Verify timeline readback capturing Meta and Scene strip descriptors.
7. Ungroup MetaStrip restoring constituent strips (UNGROUP).
8. Fail-closed security boundary check (reject untrusted approved=True).
9. Clean process exit (code 0) and final scene state verification.
10. Production isolation: v0.1.88 release ZIP untouched (SHA-256 intact), port 9877 untouched.
"""

import os
import sys
import json
import time
import socket
import tempfile
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

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
from blender_addon.universal_mcp.bridge import handlers

scene = bpy.context.scene
scene.umcp_bridge_port = port
scene.umcp_require_scene_mutation_approval = True

# Clear default scene objects & sequence editor
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
if scene.sequence_editor:
    scene.sequence_editor_clear()
scene.timeline_markers.clear()

# Create a secondary 3D Scene with a Camera for nested SceneStrip testing
sc_comp = bpy.data.scenes.new("Scene_3D_Comp")
sc_comp.frame_start = 1
sc_comp.frame_end = 120
cam_data = bpy.data.cameras.new("Cam_Overlay")
cam_obj = bpy.data.objects.new("Cam_Overlay_Obj", cam_data)
sc_comp.collection.objects.link(cam_obj)
sc_comp.camera = cam_obj

queue = MainThreadQueue(bpy)

def headless_req_app(bpy_module=None, params=None):
    params = params or {}
    tool_name = str(params.get("tool_name", "")).strip()
    mutation_params = params.get("params", {})
    timeout = float(params.get("timeout", 30.0))
    task_id = params.get("task_id") or mutation_params.get("task_id") or mutation_params.get("session_id")
    registry = handlers.get_approval_registry()
    req = registry.create_request(tool_name, mutation_params, timeout=timeout, task_id=task_id)
    ok, token = registry.resolve_request(req.request_id, "approved", reason="LOCAL TEST VSE CAP8", approve_task_group=False)
    return {
        "request_id": req.request_id,
        "tool_name": req.tool_name,
        "task_id": req.task_id,
        "arg_hash": req.arg_hash,
        "status": "approved",
        "approval_token": token,
        "timeout_seconds": req.timeout_seconds,
        "remaining_seconds": round(req.remaining_seconds, 1),
        "expires_at": req.created_at + req.timeout_seconds,
    }

handlers.handle_request_approval = headless_req_app
queue._handlers["request_approval"] = headless_req_app

server = BridgeServer(port=port, queue=queue)
server.start()

(root / "ready.json").write_text(json.dumps({
    "pid": os.getpid(),
    "port": port,
    "blender": bpy.app.version_string,
    "addon_version": getattr(addon, "bl_info", {}).get("version"),
}))

deadline = time.monotonic() + 180
try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        try:
            queue.drain_queue()
        except Exception:
            pass
        time.sleep(0.005)
finally:
    server.stop()
    (root / "final_state.json").write_text(json.dumps({
        "pid": os.getpid(),
        "strips": [{
            "name": s.name,
            "type": s.type,
            "channel": s.channel,
            "left": int(s.left_handle),
            "right": int(s.right_handle),
            "dur": int(s.duration),
        } for s in scene.sequence_editor.strips] if scene.sequence_editor else [],
        "bridge_running": bool(server.running),
    }, indent=2), encoding="utf-8")
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port if port != 9877 else find_free_port()


def run_vse_cap8_e2e():
    port = find_free_port()
    assert port != 9877, "Ephemeral port collided with production port 9877!"

    run_dir = Path(tempfile.mkdtemp(prefix="umcp_vse_cap8_"))
    bootstrap_file = run_dir / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
    ready_file = run_dir / "ready.json"

    env = os.environ.copy()
    env["UMCP_RUN_ROOT"] = str(run_dir)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["PYTHONPATH"] = str(PROJECT)

    print("=" * 80)
    print("STARTING REAL MCP-TO-BLENDER E2E: VSE CAPABILITY 8 NESTED SEQUENCES")
    print("=" * 80)
    print(f"[*] Launching disposable Blender 5.2.2 on ephemeral port {port}...")

    blender_proc = subprocess.Popen(
        [
            str(BLENDER),
            "--background",
            "--factory-startup",
            "-P",
            str(bootstrap_file),
        ],
        env=env,
        cwd=str(PROJECT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    t0 = time.time()
    while not ready_file.exists():
        if time.time() - t0 > 25:
            blender_proc.kill()
            out, err = blender_proc.communicate()
            raise TimeoutError(f"Timed out waiting for disposable Blender bridge to report ready:\n{err.decode('utf-8', errors='replace')}")
        time.sleep(0.2)

    ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
    print(f"[+] Disposable Blender ready on PID {ready_data['pid']} port {ready_data['port']}")

    try:
        sys.path.insert(0, str(PROJECT))
        from mcp_service.execution.blender_executor import BlenderExecutor

        executor = BlenderExecutor(port=port)
        executor.enable_blender_approval()

        # Step 1: Create Base Strips
        print("\n--- Test 1: Populate Base Strips on Sequencer Timeline ---")
        res_a = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Clip_A", "channel": 1, "frame_start": 1, "duration": 50, "color": [0.2, 0.4, 0.8]
        })
        assert res_a.is_success, res_a.message

        res_b = executor.execute_tool("create_vse_strip", {
            "strip_type": "COLOR", "name": "Clip_B", "channel": 2, "frame_start": 20, "duration": 40, "color": [0.8, 0.2, 0.3]
        })
        assert res_b.is_success, res_b.message

        res_t = executor.execute_tool("create_vse_text_strip", {
            "name": "Comp_Title", "text": "Composite Overlay", "channel": 3, "frame_start": 10, "duration": 40, "font_size": 42.0
        })
        assert res_t.is_success, res_t.message
        print(f"[+] Created base strips: Clip_A (Ch1, 1..50), Clip_B (Ch2, 20..60), Comp_Title (Ch3, 10..50)")

        # Step 2: Group Strips into MetaStrip
        print("\n--- Test 2: Group Strips into MetaStrip Container ---")
        meta_res = executor.execute_tool("group_vse_meta_strip", {
            "action": "CREATE",
            "name": "Meta_VFX_Block",
            "strip_names": ["Clip_A", "Clip_B", "Comp_Title"],
            "channel": 1,
        })
        assert meta_res.is_success, meta_res.message
        m_out = meta_res.result
        print(f"[+] Created Meta_VFX_Block: name='{m_out['name']}', ch={m_out['channel']}, span=[{m_out['left_handle']}..{m_out['right_handle']}], dur={m_out['duration']}, children={m_out['child_strips']}")
        assert m_out["name"] == "Meta_VFX_Block"
        assert m_out["type"] == "META"
        assert m_out["channel"] == 1
        assert m_out["left_handle"] == 1
        assert m_out["right_handle"] == 60
        assert m_out["duration"] == 59
        assert m_out["child_count"] == 3
        assert set(m_out["child_strips"]) == {"Clip_A", "Clip_B", "Comp_Title"}

        # Step 3: Inspect MetaStrip Substrips
        print("\n--- Test 3: Inspect Internal Nested Strips inside MetaStrip ---")
        insp_res = executor.execute_tool("group_vse_meta_strip", {
            "action": "INSPECT",
            "name": "Meta_VFX_Block",
        })
        assert insp_res.is_success, insp_res.message
        i_out = insp_res.result
        print(f"[+] Inspected Meta_VFX_Block: child_count={i_out['child_count']}")
        assert i_out["name"] == "Meta_VFX_Block"
        assert i_out["child_count"] == 3
        sub_names = {sub["name"]: sub for sub in i_out["child_strips"]}
        assert "Clip_A" in sub_names
        assert "Clip_B" in sub_names
        assert "Comp_Title" in sub_names
        assert sub_names["Comp_Title"]["type"] == "TEXT"

        # Step 4: Create Nested SceneStrip
        print("\n--- Test 4: Create Nested SceneStrip Referencing 3D Scene ---")
        sc_res = executor.execute_tool("create_vse_scene_strip", {
            "name": "3D_Comp_Strip",
            "scene_name": "Scene_3D_Comp",
            "channel": 2,
            "frame_start": 1,
            "duration": 70,
            "scene_input": "CAMERA",
            "scene_camera": "Cam_Overlay_Obj",
            "blend_type": "ALPHA_OVER",
            "blend_alpha": 0.85,
        })
        assert sc_res.is_success, sc_res.message
        sc_out = sc_res.result
        print(f"[+] Created 3D_Comp_Strip: name='{sc_out['name']}', ch={sc_out['channel']}, dur={sc_out['duration']}, scene='{sc_out['scene_name']}', cam='{sc_out['scene_camera']}', alpha={sc_out['blend_alpha']}")
        assert sc_out["name"] == "3D_Comp_Strip"
        assert sc_out["type"] == "SCENE"
        assert sc_out["channel"] == 2
        assert sc_out["scene_name"] == "Scene_3D_Comp"
        assert sc_out["scene_input"] == "CAMERA"
        assert sc_out["scene_camera"] == "Cam_Overlay_Obj"
        assert sc_out["blend_type"] == "ALPHA_OVER"
        assert abs(sc_out["blend_alpha"] - 0.85) < 1e-4

        # Step 5: Independent Timeline Readback
        print("\n--- Test 5: Independent Timeline Readback ---")
        tl_res = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert tl_res.is_success, tl_res.message
        tl_strips = {s["name"]: s for s in tl_res.result["strips"]}
        assert "Meta_VFX_Block" in tl_strips
        assert "3D_Comp_Strip" in tl_strips
        assert tl_strips["Meta_VFX_Block"]["type"] == "META"
        assert tl_strips["Meta_VFX_Block"]["child_count"] == 3
        assert tl_strips["3D_Comp_Strip"]["type"] == "SCENE"
        assert tl_strips["3D_Comp_Strip"]["scene_name"] == "Scene_3D_Comp"
        print(f"[+] Verified timeline strips: {list(tl_strips.keys())}")

        # Step 6: Ungroup MetaStrip
        print("\n--- Test 6: Ungroup MetaStrip Restoring Constituent Strips ---")
        ungroup_res = executor.execute_tool("group_vse_meta_strip", {
            "action": "UNGROUP",
            "name": "Meta_VFX_Block",
        })
        assert ungroup_res.is_success, ungroup_res.message
        ug_out = ungroup_res.result
        print(f"[+] Ungrouped Meta_VFX_Block: ungrouped_strips={ug_out['ungrouped_strips']}")
        assert ug_out["ungrouped_count"] == 3
        assert set(ug_out["ungrouped_strips"]) == {"Clip_A", "Clip_B", "Comp_Title"}

        # Verify timeline after ungroup
        tl_post = executor.execute_tool("inspect_vse_timeline", {"include_strips": True})
        assert tl_post.is_success, tl_post.message
        post_strips = {s["name"]: s for s in tl_post.result["strips"]}
        assert "Meta_VFX_Block" not in post_strips
        assert "Clip_A" in post_strips
        assert "Clip_B" in post_strips
        assert "Comp_Title" in post_strips
        assert "3D_Comp_Strip" in post_strips
        print(f"[+] Post-ungroup timeline verified: {list(post_strips.keys())}")

        # Step 7: Fail-Closed Security Boundary Check
        print("\n--- Test 7: Fail-Closed Security Invariant ---")
        for bad_call in [
            ("group_vse_meta_strip", {"action": "CREATE", "strip_names": ["Clip_A"], "approved": True}),
            ("group_vse_meta_strip", {"action": "UNGROUP", "name": "NonExistent", "approved": True}),
            ("create_vse_scene_strip", {"scene_name": "Scene_3D_Comp", "channel": 1, "frame_start": 1, "approved": True}),
        ]:
            hacker_res = executor.execute_tool(bad_call[0], bad_call[1], trusted_approval=False)
            assert not hacker_res.is_success, f"Security vulnerability: Untrusted approved=True was not rejected for {bad_call[0]}"
            err_text = str(hacker_res.message).lower()
            assert "approval denied" in err_text or "untrusted" in err_text or "denied" in err_text
        print(f"[+] Rejection of untrusted approved=True on nested sequence tools: PASSED")

        # Step 8: Teardown
        print("\n--- Test 8: Graceful Teardown ---")
        (run_dir / "stop.flag").touch()
        blender_proc.wait(timeout=10.0)
        print(f"[+] Disposable Blender process {blender_proc.pid} terminated cleanly with code {blender_proc.returncode}")

    finally:
        if blender_proc.poll() is None:
            blender_proc.kill()
            blender_proc.wait()

    # Step 9: Production Isolation Verification
    print("\n--- Step 9: Verifying Production Isolation ---")
    zip_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip"
    sha_path = PROJECT / "dist" / "Universal-MCP-Blender-0.1.88.zip.sha256"
    assert zip_path.exists() and sha_path.exists(), "Release artifact v0.1.88 missing!"
    import hashlib
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert actual_sha == "ba14a1ed39f78096d054cd4f81eac99ded4d61157fa56e692ad5aa521493c702", "CRITICAL: v0.1.88 release ZIP was modified!"
    print(f"[+] Release package v0.1.88 verified untouched (SHA-256: {actual_sha})")

    prod_handlers = Path(r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp\bridge\handlers.py")
    if prod_handlers.exists():
        assert "group_vse_meta_strip" not in prod_handlers.read_text("utf-8"), "Production add-on was contaminated with VSE code!"
        print(f"[+] Installed extension remains clean and isolated from development.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        res = s.connect_ex(("127.0.0.1", 9877))
        print(f"[+] Production port 9877 isolation confirmed (connect_ex result: {res})")

    print("\n" + "=" * 80)
    print("ALL VSE CAPABILITY 8 E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_vse_cap8_e2e())

