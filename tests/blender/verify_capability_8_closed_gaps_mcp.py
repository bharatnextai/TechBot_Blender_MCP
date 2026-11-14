"""
Capability 8 — Live MCP Verification for Closed Gaps (GAP-8-01 and GAP-8-03).

Executes against a disposable headless Blender 5.2.2 LTS instance using
an ephemeral loopback bridge port and authentic MCP stdio ClientSession.
Production bridge 9877 is NEVER touched.

Sections:
  A. GAP-8-01: Parametric Roof Structures (Gable, Hip, Pitched, Shed, Flat, Target Snapping)
  B. GAP-8-01: Complete Exterior Building Envelope Construction (Foundation, Facade, Lintel, Integrated Roof)
  C. GAP-8-03: Multi-Step Transaction Rollback & UniversalMutationJournal Integration
  D. Fail-Closed Approval & Parameter Invariants
  E. Evaluated RNA State & Final Beauty Still Render
"""

import asyncio
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

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

deadline = time.monotonic() + 900

try:
    while not (root / "stop.flag").exists() and time.monotonic() < deadline:
        queue.drain_queue()
        time.sleep(0.01)
finally:
    server.stop()
"""

OUTPUT_DIR = PROJECT / "tests" / "blender" / "output"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        if port == 9877:
            return find_free_port()
        return port


def unwrap(res) -> Dict[str, Any]:
    """Parse MCP tool call result, handling the result wrapper."""
    if not res.content:
        return {"status": "error", "message": "empty response"}
    txt = res.content[0].text
    try:
        raw = json.loads(txt)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "message": str(txt)}
    if isinstance(raw, dict) and "result" in raw:
        inner = raw["result"]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except Exception:
                pass
        return inner
    return raw


TOTAL_CHECKS = 0
PASSED_CHECKS = 0
FAILED_CHECKS = 0


def check(name: str, cond: bool, detail: str = ""):
    global TOTAL_CHECKS, PASSED_CHECKS, FAILED_CHECKS
    TOTAL_CHECKS += 1
    if cond:
        PASSED_CHECKS += 1
        print(f"  [PASS] {name}: {detail}")
    else:
        FAILED_CHECKS += 1
        print(f"  [FAIL] {name}: {detail}")


# ============================================================================
# SECTION A: GAP-8-01 Parametric Roof Structures
# ============================================================================
async def section_a_roof_structures(session):
    print("\n" + "=" * 72)
    print("SECTION A: GAP-8-01 PARAMETRIC ROOF STRUCTURES")
    print("=" * 72)

    # A1. Gable Roof
    res_gable = unwrap(await session.call_tool("create_roof_structure", {
        "name": "TestGableRoof",
        "roof_type": "GABLE",
        "width": 8.0,
        "length": 10.0,
        "height": 3.0,
        "overhang": 0.4,
        "base_elevation": 0.0,
    }))
    check("A1.gable_created", res_gable.get("name") == "TestGableRoof", f"res={res_gable}")
    check("A1.gable_manifold", res_gable.get("is_manifold") is True, "watertight closed volume")
    check("A1.gable_no_boundary", res_gable.get("has_boundary") is False, "0 boundary edges")
    check("A1.gable_topology", res_gable.get("vertex_count") == 6 and res_gable.get("polygon_count") == 5,
          f"verts={res_gable.get('vertex_count')}, faces={res_gable.get('polygon_count')}")

    # A2. Rectangular Hip Roof
    res_hip = unwrap(await session.call_tool("create_roof_structure", {
        "name": "TestHipRoof",
        "roof_type": "HIP",
        "width": 8.0,
        "length": 12.0,
        "height": 2.5,
        "overhang": 0.3,
    }))
    check("A2.hip_created", res_hip.get("name") == "TestHipRoof")
    check("A2.hip_manifold", res_hip.get("is_manifold") is True)
    check("A2.hip_no_boundary", res_hip.get("has_boundary") is False)

    # A3. Square Pyramid Hip Roof
    res_sq_hip = unwrap(await session.call_tool("create_roof_structure", {
        "name": "TestSquareHipRoof",
        "roof_type": "HIP",
        "width": 8.0,
        "length": 8.0,
        "height": 3.0,
        "overhang": 0.3,
    }))
    check("A3.square_hip_created", res_sq_hip.get("name") == "TestSquareHipRoof")
    check("A3.square_hip_manifold", res_sq_hip.get("is_manifold") is True)
    check("A3.square_hip_topology", res_sq_hip.get("vertex_count") == 5 and res_sq_hip.get("polygon_count") == 5,
          "pyramid apex topology")

    # A4. Pitched / Shed Roof
    res_pitched = unwrap(await session.call_tool("create_roof_structure", {
        "name": "TestPitchedRoof",
        "roof_type": "PITCHED",
        "width": 6.0,
        "length": 9.0,
        "height": 2.0,
        "overhang": 0.2,
    }))
    check("A4.pitched_created", res_pitched.get("name") == "TestPitchedRoof")
    check("A4.pitched_manifold", res_pitched.get("is_manifold") is True)

    # A5. Flat Roof
    res_flat = unwrap(await session.call_tool("create_roof_structure", {
        "name": "TestFlatRoof",
        "roof_type": "FLAT",
        "width": 8.0,
        "length": 10.0,
        "height": 0.5,
        "thickness": 0.3,
        "overhang": 0.2,
    }))
    check("A5.flat_created", res_flat.get("name") == "TestFlatRoof")
    check("A5.flat_manifold", res_flat.get("is_manifold") is True)

    # A6. Roof Snapping to Target Building
    res_base = unwrap(await session.call_tool("create_room_enclosure", {
        "name": "BaseEnclosureForRoof",
        "width": 8.0,
        "length": 10.0,
        "height": 4.0,
        "wall_thickness": 0.25,
        "include_floor": True,
        "location": [30.0, 0.0, 0.0],
    }))
    check("A6.base_building_created", res_base.get("name") == "BaseEnclosureForRoof")

    res_attached_roof = unwrap(await session.call_tool("create_roof_structure", {
        "name": "AttachedRoof",
        "roof_type": "GABLE",
        "target_building": "BaseEnclosureForRoof",
        "height": 2.5,
        "overhang": 0.3,
    }))
    check("A6.attached_roof_created", res_attached_roof.get("name") == "AttachedRoof")
    check("A6.attached_roof_snapped_elevation", abs(res_attached_roof.get("base_elevation", 0) - 4.0) < 0.001,
          f"base_elevation={res_attached_roof.get('base_elevation')} == 4.0m")
    check("A6.attached_roof_manifold", res_attached_roof.get("is_manifold") is True)

    # A7. Integrated Roof via create_room_enclosure
    res_integrated = unwrap(await session.call_tool("create_room_enclosure", {
        "name": "IntegratedGableBuilding",
        "width": 6.0,
        "length": 8.0,
        "height": 3.5,
        "wall_thickness": 0.2,
        "include_floor": True,
        "roof_type": "GABLE",
        "roof_height": 2.0,
        "roof_overhang": 0.3,
        "location": [50.0, 0.0, 0.0],
    }))
    check("A7.integrated_room_created", res_integrated.get("name") == "IntegratedGableBuilding")
    check("A7.integrated_room_roof_type", res_integrated.get("roof_type") == "GABLE")
    check("A7.integrated_room_manifold", res_integrated.get("is_manifold") is True)


# ============================================================================
# SECTION B: GAP-8-01 Complete Exterior Building Envelope Construction
# ============================================================================
async def section_b_building_envelopes(session):
    print("\n" + "=" * 72)
    print("SECTION B: GAP-8-01 COMPLETE EXTERIOR BUILDING ENVELOPES")
    print("=" * 72)

    # B1. 2-Story Commercial Building Envelope with Gable Roof
    res_envelope = unwrap(await session.call_tool("create_building_envelope", {
        "name": "CommercialHQ_Envelope",
        "width": 12.0,
        "length": 16.0,
        "height": 6.0,
        "stories": 2,
        "foundation_thickness": 0.3,
        "wall_thickness": 0.25,
        "roof_type": "GABLE",
        "roof_height": 3.0,
        "roof_overhang": 0.4,
        "door_wall": "SOUTH",
        "door_width": 2.0,
        "door_height": 2.4,
        "location": [0.0, 30.0, 0.0],
    }))
    check("B1.envelope_created", res_envelope.get("name") == "CommercialHQ_Envelope")
    check("B1.envelope_manifold", res_envelope.get("is_manifold") is True, "watertight envelope")
    check("B1.envelope_no_boundary", res_envelope.get("has_boundary") is False)
    check("B1.envelope_stories", res_envelope.get("stories") == 2)
    b_min = res_envelope.get("bounds_min", [0, 0, 0])
    b_max = res_envelope.get("bounds_max", [0, 0, 0])
    check("B1.foundation_depth", abs(b_min[2] - (-0.3)) < 0.001, f"Z_min={b_min[2]} matches -foundation_thickness")
    check("B1.ridge_height", abs(b_max[2] - 9.0) < 0.001, f"Z_max={b_max[2]} matches height(6.0) + roof_height(3.0)")

    # B2. 1-Story Villa with Hipped Roof
    res_villa = unwrap(await session.call_tool("create_building_envelope", {
        "name": "Villa_Envelope",
        "width": 10.0,
        "length": 14.0,
        "height": 4.0,
        "stories": 1,
        "roof_type": "HIP",
        "roof_height": 2.5,
        "roof_overhang": 0.4,
        "door_wall": "EAST",
        "location": [25.0, 30.0, 0.0],
    }))
    check("B2.villa_created", res_villa.get("name") == "Villa_Envelope")
    check("B2.villa_manifold", res_villa.get("is_manifold") is True)
    check("B2.villa_roof_type", res_villa.get("roof_type") == "HIP")


# ============================================================================
# SECTION C: GAP-8-03 Multi-Step Transaction Rollback
# ============================================================================
async def section_c_transaction_rollback(session):
    print("\n" + "=" * 72)
    print("SECTION C: GAP-8-03 MULTI-STEP TRANSACTION ROLLBACK")
    print("=" * 72)

    # C1. Transaction Lifecycle Success & Commit
    res_begin1 = unwrap(await session.call_tool("begin_environment_transaction", {
        "context_name": "TestTx_Commit",
    }))
    tx_id1 = res_begin1.get("transaction_id")
    check("C1.tx_begin_success", res_begin1.get("status") == "SUCCESS" and tx_id1 is not None)

    # Create temporary object inside transaction
    res_obj1 = unwrap(await session.call_tool("create_primitive", {
        "primitive_type": "cube",
        "name": "CommittedTxCube",
        "dimensions": [1.0, 1.0, 1.0],
        "location": [0.0, 60.0, 0.0],
    }))
    check("C1.object_created_in_tx", res_obj1.get("name") == "CommittedTxCube")

    res_commit = unwrap(await session.call_tool("commit_environment_transaction", {
        "transaction_id": tx_id1,
    }))
    check("C1.tx_committed", res_commit.get("status") == "COMMITTED")

    # Verify object persists
    res_det1 = unwrap(await session.call_tool("get_object_details", {"name": "CommittedTxCube"}))
    check("C1.committed_object_persists", res_det1.get("name") == "CommittedTxCube")

    # C2. Transaction Lifecycle Rollback
    res_begin2 = unwrap(await session.call_tool("begin_environment_transaction", {
        "context_name": "TestTx_Rollback",
    }))
    tx_id2 = res_begin2.get("transaction_id")
    check("C2.tx2_begin_success", res_begin2.get("status") == "SUCCESS")

    # Create objects, meshes, and materials that should be rolled back
    await session.call_tool("create_primitive", {
        "primitive_type": "cylinder",
        "name": "DoomedCylinder",
        "radius": 1.0,
        "depth": 2.0,
        "location": [5.0, 60.0, 0.0],
    })
    await session.call_tool("create_material", {
        "name": "DoomedMaterial",
        "base_color": [0.9, 0.1, 0.1, 1.0],
    })

    # Verify they exist prior to rollback
    det_pre_rb = unwrap(await session.call_tool("get_object_details", {"name": "DoomedCylinder"}))
    check("C2.pre_rollback_object_exists", det_pre_rb.get("name") == "DoomedCylinder")

    # Roll back
    res_rb = unwrap(await session.call_tool("rollback_environment_transaction", {
        "transaction_id": tx_id2,
    }))
    check("C2.tx_rolled_back", res_rb.get("status") == "ROLLED_BACK")
    comp_rep = res_rb.get("compensation_report", {})
    check("C2.doomed_object_reported_removed", "DoomedCylinder" in comp_rep.get("removed_objects", []),
          f"removed={comp_rep.get('removed_objects')}")
    check("C2.doomed_material_reported_removed", "DoomedMaterial" in comp_rep.get("removed_materials", []),
          f"removed_mats={comp_rep.get('removed_materials')}")

    # Verify object is truly removed from Blender scene memory
    det_post_rb = unwrap(await session.call_tool("get_object_details", {"name": "DoomedCylinder"}))
    check("C2.post_rollback_object_gone", det_post_rb.get("status") == "error" or "not found" in str(det_post_rb).lower(),
          "object removed from scene")

    # C3. Composite execute_environment_workflow Success
    wf_success_steps = [
        {"tool": "create_room_enclosure", "params": {"name": "WfRoomSuccess", "width": 6.0, "length": 6.0, "height": 3.0, "location": [10.0, 60.0, 0.0]}},
        {"tool": "create_roof_structure", "params": {"name": "WfRoofSuccess", "target_building": "WfRoomSuccess", "height": 2.0, "roof_type": "HIP"}},
        {"tool": "align_object_grid", "params": {"object_name": "WfRoomSuccess", "grid_size": 1.0}},
    ]
    res_wf_succ = unwrap(await session.call_tool("execute_environment_workflow", {
        "workflow_name": "AtomicSuccessWorkflow",
        "steps": wf_success_steps,
    }))
    check("C3.composite_workflow_success", res_wf_succ.get("status") == "SUCCESS", f"res={res_wf_succ}")
    check("C3.composite_steps_executed", res_wf_succ.get("steps_executed") == 3, f"steps_executed={res_wf_succ.get('steps_executed')}")

    # C4. Composite execute_environment_workflow Failure at Stage 1
    wf_fail_s1 = [
        {"tool": "create_roof_structure", "params": {"name": "BadRoof_S1", "height": -5.0}},  # Invalid height
        {"tool": "create_cyclorama", "params": {"name": "NeverReachedCyc"}},
    ]
    res_wf_f1 = unwrap(await session.call_tool("execute_environment_workflow", {
        "workflow_name": "Stage1FailWorkflow",
        "steps": wf_fail_s1,
    }))
    check("C4.stage1_failure_rolled_back", res_wf_f1.get("status") == "ROLLED_BACK")
    check("C4.stage1_failed_step_index", res_wf_f1.get("failed_step_index") == 0)

    # C5. Composite execute_environment_workflow Failure at Stage 2 (Rolled Back Step 1)
    wf_fail_s2 = [
        {"tool": "create_room_enclosure", "params": {"name": "Stage2RoomToRollback", "width": 8.0, "length": 8.0, "height": 3.0, "location": [25.0, 60.0, 0.0]}},
        {"tool": "create_roof_structure", "params": {"name": "BadRoof_S2", "width": -10.0}},  # Fails at step 2
    ]
    res_wf_f2 = unwrap(await session.call_tool("execute_environment_workflow", {
        "workflow_name": "Stage2FailWorkflow",
        "steps": wf_fail_s2,
    }))
    check("C5.stage2_failure_rolled_back", res_wf_f2.get("status") == "ROLLED_BACK")
    check("C5.stage2_failed_step_index", res_wf_f2.get("failed_step_index") == 1, f"failed_idx={res_wf_f2.get('failed_step_index')}")
    rb_rep2 = res_wf_f2.get("rollback_report", {})
    check("C5.stage1_object_cleaned_up", "Stage2RoomToRollback" in rb_rep2.get("removed_objects", []),
          f"removed={rb_rep2.get('removed_objects')}")

    # Verify Stage2RoomToRollback no longer exists
    det_s2 = unwrap(await session.call_tool("get_object_details", {"name": "Stage2RoomToRollback"}))
    check("C5.stage1_object_verified_gone", det_s2.get("status") == "error" or "not found" in str(det_s2).lower())

    # C6. Composite execute_environment_workflow Failure at Stage 3
    wf_fail_s3 = [
        {"tool": "create_room_enclosure", "params": {"name": "Stage3RoomToRollback", "width": 7.0, "length": 7.0, "height": 3.0, "location": [40.0, 60.0, 0.0]}},
        {"tool": "create_roof_structure", "params": {"name": "Stage3RoofToRollback", "target_building": "Stage3RoomToRollback", "height": 2.0}},
        {"tool": "create_cyclorama", "params": {"name": "Stage3RoofToRollback"}},  # Name collision causes failure at step 3!
    ]
    res_wf_f3 = unwrap(await session.call_tool("execute_environment_workflow", {
        "workflow_name": "Stage3FailWorkflow",
        "steps": wf_fail_s3,
    }))
    check("C6.stage3_failure_rolled_back", res_wf_f3.get("status") == "ROLLED_BACK")
    check("C6.stage3_failed_step_index", res_wf_f3.get("failed_step_index") == 2)
    rb_rep3 = res_wf_f3.get("rollback_report", {})
    check("C6.stage1_and_2_objects_cleaned_up",
          "Stage3RoomToRollback" in rb_rep3.get("removed_objects", []) and
          "Stage3RoofToRollback" in rb_rep3.get("removed_objects", []),
          f"removed={rb_rep3.get('removed_objects')}")


# ============================================================================
# SECTION D: Fail-Closed Approval & Parameter Bounds
# ============================================================================
async def section_d_security_and_bounds(session):
    print("\n" + "=" * 72)
    print("SECTION D: FAIL-CLOSED APPROVAL & BOUNDS")
    print("=" * 72)

    # D1. Fail-Closed Approval Rejection
    rejections = [
        ("create_roof_structure", {"name": "EvilRoof", "approved": True}),
        ("create_building_envelope", {"name": "EvilBuilding", "approved": True}),
        ("begin_environment_transaction", {"approved": True}),
        ("rollback_environment_transaction", {"approved": True}),
        ("commit_environment_transaction", {"approved": True}),
        ("execute_environment_workflow", {"steps": [{"tool": "create_roof_structure"}], "approved": True}),
    ]
    for tool_name, p in rejections:
        res = unwrap(await session.call_tool(tool_name, p))
        rejected = res.get("status") in ("error", "ERROR") or "denied" in str(res).lower() or "untrusted" in str(res).lower()
        check(f"D1.untrusted_approved_rejected_{tool_name}", rejected, f"res={res}")

    # D2. Bounds validation
    res_neg_stories = unwrap(await session.call_tool("create_building_envelope", {"name": "BadStories", "stories": 0}))
    check("D2.zero_stories_rejected", res_neg_stories.get("status") in ("error", "ERROR"))

    res_invalid_roof_type = unwrap(await session.call_tool("create_roof_structure", {"name": "BadType", "roof_type": "CIRCULAR"}))
    check("D2.invalid_roof_type_rejected", res_invalid_roof_type.get("status") in ("error", "ERROR"))


# ============================================================================
# SECTION E: Beauty Still Render of Complete Building Envelope
# ============================================================================
async def section_e_beauty_render(session, run_root: Path):
    print("\n" + "=" * 72)
    print("SECTION E: BEAUTY STILL RENDER")
    print("=" * 72)

    # Lighting
    await session.call_tool("create_light", {
        "name": "BuildingSunKey",
        "light_type": "SUN",
        "energy": 5.0,
        "location": [10.0, 10.0, 20.0],
    })
    await session.call_tool("create_light", {
        "name": "BuildingFillArea",
        "light_type": "AREA",
        "shape": "RECTANGLE",
        "size": 5.0,
        "energy": 400.0,
        "location": [-15.0, 15.0, 10.0],
    })

    # Camera framing CommercialHQ_Envelope
    await session.call_tool("create_camera", {
        "name": "BuildingExteriorCamera",
        "camera_type": "PERSP",
        "focal_length": 35.0,
        "location": [-18.0, 10.0, 8.0],
        "set_active": True,
        "track_to_object": "CommercialHQ_Envelope",
    })

    # Render configure & execution
    render_out_dir = run_root / "renders"
    render_out_dir.mkdir(parents=True, exist_ok=True)
    render_path = str(render_out_dir / "capability_8_closed_gaps_beauty.png")

    await session.call_tool("configure_render_settings", {
        "engine": "BLENDER_EEVEE_NEXT",
        "resolution_x": 960,
        "resolution_y": 540,
        "view_transform": "AgX",
        "look": "AgX - Medium High Contrast",
        "filepath": render_path,
    })

    res_render = unwrap(await session.call_tool("render_scene", {
        "output_path": render_path,
        "render_mode": "still",
    }))
    check("E1.beauty_render", res_render.get("rendered") is True or res_render.get("action") == "render_scene",
          "Render executed successfully")

    render_file = Path(render_path)
    file_exists = render_file.exists()
    file_size = render_file.stat().st_size if file_exists else 0
    check("E1.render_file_exists", file_exists, f"path={render_path}")
    check("E1.render_file_nonzero", file_size > 5000,
          f"size={file_size} bytes > 5KB (valid raster)")

    if file_exists and file_size > 5000:
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        shutil.copy2(str(render_file), str(OUTPUT_DIR / "capability_8_closed_gaps_beauty.png"))


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================
async def main():
    print("=" * 72)
    print("STARTING CAPABILITY 8 CLOSED GAPS (GAP-8-01 & GAP-8-03) MCP VERIFICATION")
    print(f"Target Blender: {BLENDER}")
    print("=" * 72)

    run_root = Path(tempfile.mkdtemp(prefix="umcp_cap8_gaps_"))
    ephemeral_port = find_free_port()
    print(f"Allocated ephemeral loopback port: {ephemeral_port}")
    print(f"Run root: {run_root}")

    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    blender_env = os.environ.copy()
    blender_env["UMCP_RUN_ROOT"] = str(run_root)
    blender_env["UMCP_PROJECT"] = str(PROJECT)
    blender_env["UMCP_BRIDGE_PORT"] = str(ephemeral_port)
    blender_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    blender_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    blender_env["BLENDER_USER_CONFIG"] = str(config_dir)
    blender_env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    blender_env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)
    blender_env["PYTHONPATH"] = str(PROJECT)
    blender_env["PYTHONDONTWRITEBYTECODE"] = "1"

    bootstrap_file = run_root / "bootstrap.py"
    bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    blender_log_path = run_root / "blender.log"
    blender_log = open(blender_log_path, "w", encoding="utf-8")

    blender_cmd = [
        str(BLENDER),
        "-b",
        "--factory-startup",
        "--python", str(bootstrap_file),
    ]

    print("Launching disposable headless Blender instance...")
    blender_proc = subprocess.Popen(
        blender_cmd,
        env=blender_env,
        stdout=blender_log,
        stderr=subprocess.STDOUT,
    )

    ready_file = run_root / "blender_ready.json"
    t0 = time.monotonic()
    ready_data = None
    while time.monotonic() - t0 < 30.0:
        if ready_file.exists():
            try:
                ready_data = json.loads(ready_file.read_text(encoding="utf-8"))
                break
            except Exception:
                pass
        await asyncio.sleep(0.2)

    if not ready_data:
        print("[FAIL] Blender bridge failed to start within 30s")
        blender_proc.kill()
        blender_log.close()
        return 1

    print(f"Blender bridge confirmed ready: PID {ready_data.get('pid')} on port {ephemeral_port}")

    # Launch MCP server subprocess
    mcp_env = os.environ.copy()
    mcp_env["UNIVERSAL_MCP_BRIDGE_PORT"] = str(ephemeral_port)
    mcp_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    mcp_env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=str(PYTHON_EXE),
        args=[
            "-B",
            "-m",
            "mcp_service.app",
            "--transport",
            "stdio",
            "--bridge-port",
            str(ephemeral_port),
        ],
        env=mcp_env,
        cwd=str(PROJECT),
    )

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_res = await session.initialize()
                print(f"MCP Session initialized: {init_res.serverInfo.name} v{init_res.serverInfo.version}")

                await section_a_roof_structures(session)
                await section_b_building_envelopes(session)
                await section_c_transaction_rollback(session)
                await section_d_security_and_bounds(session)
                await section_e_beauty_render(session, run_root)

    finally:
        print("\nTearing down test session...")
        (run_root / "stop.flag").write_text("stop", encoding="utf-8")
        try:
            blender_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            blender_proc.kill()
        blender_log.close()
        shutil.rmtree(run_root, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"VERIFICATION SUMMARY: {PASSED_CHECKS} / {TOTAL_CHECKS} CHECKS PASSED")
    if FAILED_CHECKS == 0:
        print("ALL GAP-8-01 AND GAP-8-03 VERIFICATION CHECKS PASSED (100.0%)")
    else:
        print(f"FAILED CHECKS: {FAILED_CHECKS}")
    print("=" * 72)

    return 0 if FAILED_CHECKS == 0 else 1


if __name__ == "__main__":
    ret = asyncio.run(main())
    sys.exit(ret)
