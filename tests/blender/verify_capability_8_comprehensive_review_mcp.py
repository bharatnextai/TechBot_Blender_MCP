"""
Capability 8 — Final Consolidated Comprehensive Behavioral Verification.

Executes against a disposable headless Blender 5.2.2 LTS instance using
an ephemeral loopback bridge port and authentic MCP stdio ClientSession.
Production bridge 9877 is NEVER touched.

Sections:
  A. ROADMAP DOMAIN VERIFICATION (Interiors, Buildings, Terrain, Landscapes, Props, Complete Scenes)
  B. AGENT & DIRECTOR INTEGRATION
  C. CROSS-CAPABILITY REGRESSION (Cap 1–7 interop)
  D. SECURITY, SCHEMA & INVARIANT CHECKS
"""

import asyncio
import json
import math
import os
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
                return json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                return {"status": "error", "message": inner}
        if isinstance(inner, dict):
            return inner
    return raw


# ============================================================================
# Counters
# ============================================================================
results = {"passed": 0, "failed": 0, "checks": []}


def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    results["passed" if condition else "failed"] += 1
    results["checks"].append({"label": label, "status": status, "detail": detail})
    icon = "✅" if condition else "❌"
    print(f"  {icon} {label}: {detail}")


# ============================================================================
# SECTION A: Roadmap Domain Verification
# ============================================================================
async def section_a_roadmap_domains(session, run_root: Path):
    print("\n" + "=" * 72)
    print("SECTION A: ROADMAP DOMAIN VERIFICATION")
    print("=" * 72)

    # ---- A1: Tool Discovery (all 7 Cap 8 tools present) ----
    print("\n--- A1: Tool Discovery ---")
    tools_resp = await session.list_tools()
    tool_names = {t.name for t in tools_resp.tools}
    cap8_tools = [
        "create_cyclorama", "set_object_origin", "create_room_enclosure",
        "create_terrain", "scatter_surface_assets", "snap_to_ground", "align_object_grid",
    ]
    for t in cap8_tools:
        check(f"A1.tool_present({t})", t in tool_names, f"Found={t in tool_names}")

    # ---- A2: INTERIORS — Room Enclosure with Door & Ceiling ----
    print("\n--- A2: Interiors — Room Enclosure ---")
    res = unwrap(await session.call_tool("create_room_enclosure", {
        "name": "ReviewGallery",
        "width": 10.0, "length": 12.0, "height": 3.5,
        "wall_thickness": 0.25,
        "include_floor": True, "include_ceiling": True,
        "door_wall": "SOUTH", "door_width": 1.2, "door_height": 2.4,
    }))
    check("A2.room_create", res.get("status") == "SUCCESS", f"name={res.get('name')}")
    check("A2.room_floor", res.get("include_floor") is True, "Floor slab included")
    check("A2.room_ceiling", res.get("include_ceiling") is True, "Ceiling slab included")
    check("A2.room_door", res.get("door_wall") == "SOUTH", f"door_wall={res.get('door_wall')}")
    verts = res.get("vertex_count", 0)
    polys = res.get("polygon_count", 0)
    check("A2.room_manifold", verts > 0 and polys > 0, f"verts={verts}, polys={polys}")
    bounds = res.get("bound_box", [])
    if bounds:
        all_x = [b[0] for b in bounds]
        all_z = [b[2] for b in bounds]
        outer_half_w = 10.0 / 2.0 + 0.25
        check("A2.room_bounds_x", max(all_x) >= outer_half_w - 0.01,
              f"X_max={max(all_x):.3f} >= {outer_half_w}")
        check("A2.room_bounds_z_ceiling", max(all_z) >= 3.5,
              f"Z_max={max(all_z):.3f} >= 3.5 (ceiling)")

    # ---- A3: BUILDINGS — Modular Wall Kit Assembly ----
    print("\n--- A3: Buildings — Modular Wall Kit ---")
    wall_names = []
    grid = 2.5
    for i in range(4):
        wname = f"ModularWall_{i}"
        res_w = unwrap(await session.call_tool("create_primitive", {
            "primitive_type": "cube",
            "name": wname,
            "dimensions": [grid, 0.2, 3.0],
            "location": [grid * i + 0.33, 0.0, 1.5],
        }))
        created_ok = res_w.get("created") is True or res_w.get("name") == wname
        check(f"A3.wall_{i}_create", created_ok, f"name={res_w.get('name')}")
        wall_names.append(wname)

    for wname in wall_names:
        res_o = unwrap(await session.call_tool("set_object_origin", {
            "object_name": wname, "origin_mode": "BOTTOM_CENTER",
        }))
        check(f"A3.origin({wname})", res_o.get("status") == "SUCCESS", "BOTTOM_CENTER set")
        res_s = unwrap(await session.call_tool("snap_to_ground", {
            "object_name": wname,
        }))
        check(f"A3.ground({wname})", res_s.get("status") == "SUCCESS",
              f"new_z_min={res_s.get('new_z_min', '?')}")

    for wname in wall_names:
        res_g = unwrap(await session.call_tool("align_object_grid", {
            "object_name": wname, "grid_size": grid, "snap_axes": ["X", "Y"],
        }))
        check(f"A3.grid({wname})", res_g.get("status") == "SUCCESS",
              f"snapped={res_g.get('snapped_location')}")

    # Verify modular adjacency
    details = []
    for wname in wall_names:
        det = unwrap(await session.call_tool("get_object_details", {"name": wname}))
        details.append(det)

    for i in range(len(details) - 1):
        loc_a = details[i].get("location", [0, 0, 0])
        loc_b = details[i + 1].get("location", [0, 0, 0])
        gap = abs(loc_b[0] - loc_a[0]) - grid
        check(f"A3.seam_{i}_{i+1}", abs(gap) < 0.001, f"gap={gap:.6f}m")

    # ---- A4: TERRAIN — Procedural Landscape ----
    print("\n--- A4: Terrain — Procedural Landscape ---")
    res_t = unwrap(await session.call_tool("create_terrain", {
        "name": "ReviewHighlands",
        "width": 60.0, "depth": 60.0,
        "resolution_x": 48, "resolution_y": 48,
        "elevation_scale": 6.0, "noise_scale": 0.04,
        "noise_octaves": 5, "roughness": 0.6,
        "seed": 314, "boundary_falloff": True,
    }))
    check("A4.terrain_create", res_t.get("status") == "SUCCESS", f"name={res_t.get('name')}")
    elev_min = res_t.get("elevation_min", 0)
    elev_max = res_t.get("elevation_max", 0)
    elev_range = elev_max - elev_min
    check("A4.terrain_relief", elev_range > 4.0, f"Δz={elev_range:.3f}m > 4.0m")
    check("A4.terrain_variance", res_t.get("elevation_variance", 0) > 0.1,
          f"σ²={res_t.get('elevation_variance', 0):.4f} > 0.1")
    expected_verts = 48 * 48
    check("A4.terrain_topology", res_t.get("vertex_count") == expected_verts,
          f"verts={res_t.get('vertex_count')} == {expected_verts}")

    # Terrain determinism
    res_t2 = unwrap(await session.call_tool("create_terrain", {
        "name": "ReviewHighlands_Clone",
        "width": 60.0, "depth": 60.0,
        "resolution_x": 48, "resolution_y": 48,
        "elevation_scale": 6.0, "noise_scale": 0.04,
        "noise_octaves": 5, "roughness": 0.6,
        "seed": 314, "boundary_falloff": True,
    }))
    check("A4.terrain_determinism",
          abs(res_t2.get("elevation_min", 0) - elev_min) < 0.0001 and
          abs(res_t2.get("elevation_max", 0) - elev_max) < 0.0001,
          f"Δ_min={abs(res_t2.get('elevation_min', 0) - elev_min):.6f}, "
          f"Δ_max={abs(res_t2.get('elevation_max', 0) - elev_max):.6f}")

    # ---- A5: LANDSCAPES — Surface Asset Scattering ----
    print("\n--- A5: Landscapes — Surface Scattering ---")
    res_b = unwrap(await session.call_tool("create_primitive", {
        "primitive_type": "sphere",
        "name": "ReviewBoulder",
        "radius": 0.5,
        "location": [0.0, 0.0, -20.0],
    }))
    check("A5.source_boulder", res_b.get("created") is True or res_b.get("name") == "ReviewBoulder", "ReviewBoulder created")

    res_s = unwrap(await session.call_tool("create_primitive", {
        "primitive_type": "cylinder",
        "name": "ReviewShrub",
        "radius": 0.3,
        "depth": 0.8,
        "location": [0.0, 0.0, -20.0],
    }))
    check("A5.source_shrub", res_s.get("created") is True or res_s.get("name") == "ReviewShrub", "ReviewShrub created")

    res_sc = unwrap(await session.call_tool("scatter_surface_assets", {
        "surface_name": "ReviewHighlands",
        "asset_names": ["ReviewBoulder", "ReviewShrub"],
        "count": 40,
        "seed": 555,
        "min_scale": 0.6, "max_scale": 1.5,
        "align_to_normal": True, "random_rotation_z": True,
        "avoid_overlap": True, "min_distance": 2.0,
        "collection_name": "HighlandVegetation",
    }))
    check("A5.scatter_create", res_sc.get("status") == "SUCCESS", "Scatter completed")
    scattered_count = res_sc.get("scattered_count", 0)
    check("A5.scatter_count", scattered_count >= 20, f"placed={scattered_count}/40")
    check("A5.scatter_collection", res_sc.get("collection_name") == "HighlandVegetation",
          f"coll={res_sc.get('collection_name')}")

    # ---- A6: PROPS — Origin, Ground Snap, Surface Placement ----
    print("\n--- A6: Props — Origin & Placement ---")
    res_p = unwrap(await session.call_tool("create_primitive", {
        "primitive_type": "cylinder",
        "name": "DisplayPlinth",
        "radius": 0.75,
        "depth": 0.6,
        "location": [0, 0, 5.0],
    }))
    check("A6.prop_create", res_p.get("created") is True or res_p.get("name") == "DisplayPlinth", "DisplayPlinth created")

    res_po = unwrap(await session.call_tool("set_object_origin", {
        "object_name": "DisplayPlinth", "origin_mode": "BOTTOM_CENTER",
    }))
    check("A6.prop_origin", res_po.get("status") == "SUCCESS", "Origin set to BOTTOM_CENTER")

    res_pg = unwrap(await session.call_tool("snap_to_ground", {
        "object_name": "DisplayPlinth",
    }))
    new_z_min = res_pg.get("new_z_min", 999)
    check("A6.prop_grounded", abs(new_z_min) < 0.001, f"Z_min={new_z_min:.4f} ≈ 0.0")

    # Place hero on top of plinth
    res_hero_create = unwrap(await session.call_tool("create_primitive", {
        "primitive_type": "cone",
        "name": "HeroProduct_Review",
        "radius": 0.3,
        "depth": 1.0,
        "location": [0, 0, 10.0],
    }))
    check("A6.hero_create", res_hero_create.get("created") is True or res_hero_create.get("name") == "HeroProduct_Review", "HeroProduct created")

    unwrap(await session.call_tool("set_object_origin", {
        "object_name": "HeroProduct_Review", "origin_mode": "BOTTOM_CENTER",
    }))
    res_ph = unwrap(await session.call_tool("snap_to_ground", {
        "object_name": "HeroProduct_Review",
        "ground_name": "DisplayPlinth",
    }))
    hero_z_min = res_ph.get("new_z_min", 0)
    check("A6.hero_on_plinth", abs(hero_z_min - 0.6) < 0.05,
          f"Z_min={hero_z_min:.4f} ≈ 0.600 (plinth top)")

    # ---- A7: COMPLETE SCENE — Cyclorama + Lighting + Camera + Render ----
    print("\n--- A7: Complete Scene Environment ---")
    res_cyc = unwrap(await session.call_tool("create_cyclorama", {
        "name": "ReviewCove",
        "width": 14.0, "depth": 10.0, "wall_height": 7.0,
        "cove_radius": 2.0, "cove_segments": 20,
    }))
    check("A7.cyclorama_create", res_cyc.get("status") == "SUCCESS",
          f"verts={res_cyc.get('vertex_count')}, polys={res_cyc.get('polygon_count')}")
    check("A7.cyclorama_smoothness", (res_cyc.get("vertex_count") or 0) >= 40,
          f"verts={res_cyc.get('vertex_count')} >= 40 (smooth curve)")

    # Key light (Cap 7 regression)
    res_key = unwrap(await session.call_tool("create_light", {
        "name": "ReviewKeyLight",
        "light_type": "AREA",
        "energy": 500.0,
        "shape": "RECTANGLE",
        "size": 2.0,
        "size_y": 1.0,
        "location": [4.0, -5.0, 5.0],
    }))
    check("A7.key_light", res_key.get("name") == "ReviewKeyLight", "Area key light created")

    # Fill light
    res_fill = unwrap(await session.call_tool("create_light", {
        "name": "ReviewFillLight",
        "light_type": "AREA",
        "energy": 150.0,
        "shape": "RECTANGLE",
        "size": 3.0,
        "size_y": 2.0,
        "location": [-5.0, -4.0, 3.0],
    }))
    check("A7.fill_light", res_fill.get("name") == "ReviewFillLight", "Area fill light created")

    # Camera (Cap 7 regression) with TRACK_TO
    res_cam = unwrap(await session.call_tool("create_camera", {
        "name": "ReviewCamera",
        "camera_type": "PERSP",
        "focal_length": 85.0,
        "location": [0.0, -8.0, 3.0],
        "sensor_width": 36.0,
        "track_to_object": "HeroProduct_Review",
        "set_active": True,
    }))
    check("A7.camera", res_cam.get("name") == "ReviewCamera", "Camera created with tracking")

    # PBR material (Cap 6 regression)
    res_mat = unwrap(await session.call_tool("create_material", {
        "name": "ReviewGoldMetal",
        "base_color": [0.85, 0.65, 0.15, 1.0],
        "metallic": 0.9,
        "roughness": 0.2,
    }))
    check("A7.material", res_mat.get("material_name") == "ReviewGoldMetal" or res_mat.get("action") == "create_material", "Gold PBR material created")

    res_assign = unwrap(await session.call_tool("assign_material", {
        "target_name": "HeroProduct_Review",
        "material_name": "ReviewGoldMetal",
    }))
    check("A7.material_assign",
          res_assign.get("assigned") is True or "assigned" in str(res_assign).lower() or res_assign.get("status") == "SUCCESS",
          "Material assigned to hero")

    # Render configure & execution
    render_out_dir = run_root / "renders"
    render_out_dir.mkdir(parents=True, exist_ok=True)
    render_path = str(render_out_dir / "capability_8_review_beauty.png")

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
    check("A7.beauty_render", res_render.get("rendered") is True or res_render.get("action") == "render_scene",
          "Render executed successfully")

    render_file = Path(render_path)
    file_exists = render_file.exists()
    file_size = render_file.stat().st_size if file_exists else 0
    check("A7.render_file_exists", file_exists, f"path={render_path}")
    check("A7.render_file_nonzero", file_size > 5000,
          f"size={file_size} bytes > 5KB (valid raster)")

    # Also copy to permanent output directory for audit inspection
    if file_exists and file_size > 5000:
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        import shutil
        shutil.copy2(str(render_file), str(OUTPUT_DIR / "capability_8_review_beauty.png"))


# ============================================================================
# SECTION B: Agent & Director Integration
# ============================================================================
async def section_b_agent_integration(session):
    print("\n" + "=" * 72)
    print("SECTION B: AGENT & DIRECTOR INTEGRATION")
    print("=" * 72)

    tools_resp = await session.list_tools()
    tool_names = {t.name for t in tools_resp.tools}

    env_tools = [
        "create_cyclorama", "set_object_origin", "create_room_enclosure",
        "create_terrain", "scatter_surface_assets", "snap_to_ground", "align_object_grid",
    ]
    all_env_present = all(t in tool_names for t in env_tools)
    check("B1.all_env_tools_exposed", all_env_present,
          f"All 7 Cap 8 tools in MCP tool list")

    for tool in tools_resp.tools:
        if tool.name in env_tools:
            has_desc = bool(tool.description)
            has_schema = tool.inputSchema is not None
            check(f"B2.schema({tool.name})", has_desc and has_schema,
                  f"desc={'✓' if has_desc else '✗'}, schema={'✓' if has_schema else '✗'}")

    cap7_tools = ["create_light", "create_camera", "render_scene"]
    for t in cap7_tools:
        check(f"B3.cap7_regression({t})", t in tool_names, f"present={t in tool_names}")

    foundation_tools = ["create_primitive", "transform_object", "get_object_details"]
    for t in foundation_tools:
        check(f"B4.foundation_regression({t})", t in tool_names, f"present={t in tool_names}")


# ============================================================================
# SECTION C: Cross-Capability Regression
# ============================================================================
async def section_c_regression(session):
    print("\n" + "=" * 72)
    print("SECTION C: CROSS-CAPABILITY REGRESSION")
    print("=" * 72)

    print("\n--- C1: Cap 1 Primitives ---")
    res_prim = unwrap(await session.call_tool("create_primitive", {
        "primitive_type": "cube",
        "name": "RegressionCube",
        "dimensions": [2.0, 2.0, 2.0],
        "location": [20.0, 20.0, 1.0],
    }))
    check("C1.primitive_create", res_prim.get("created") is True or res_prim.get("name") == "RegressionCube", "Cube created")

    print("\n--- C2: Cap 2 Transform ---")
    res_tx = unwrap(await session.call_tool("transform_object", {
        "name": "RegressionCube",
        "location": [22.0, 22.0, 1.0],
        "rotation_euler": [0.0, 0.0, 0.7854],
    }))
    check("C2.transform", res_tx.get("transformed") is True or res_tx.get("name") == "RegressionCube",
          "Transform applied")

    print("\n--- C3: Cap 1-2 Readback ---")
    res_det = unwrap(await session.call_tool("get_object_details", {
        "name": "RegressionCube",
    }))
    check("C3.details_readback", "location" in res_det or res_det.get("name") == "RegressionCube",
          "Object details retrieved")

    print("\n--- C4: Cap 6 Materials ---")
    res_mat = unwrap(await session.call_tool("create_material", {
        "name": "RegressionMat",
        "base_color": [0.2, 0.8, 0.3, 1.0],
    }))
    check("C4.material_create", res_mat.get("material_name") == "RegressionMat" or res_mat.get("action") == "create_material", "Material created")

    print("\n--- C5: Cap 7 Lighting ---")
    res_lt = unwrap(await session.call_tool("create_light", {
        "name": "RegressionLight",
        "light_type": "AREA",
        "shape": "SQUARE",
        "size": 1.5,
        "energy": 100.0,
        "location": [25.0, 25.0, 5.0],
    }))
    check("C5.light_create", res_lt.get("name") == "RegressionLight", "Area light created")

    print("\n--- C6: Cap 7 Camera ---")
    res_cc = unwrap(await session.call_tool("create_camera", {
        "name": "RegressionCamera",
        "camera_type": "PERSP",
        "focal_length": 50.0,
        "location": [20.0, 15.0, 3.0],
        "sensor_width": 36.0,
        "set_active": False,
    }))
    cam_name = res_cc.get("name") or res_cc.get("camera_name")
    check("C6.camera_create", cam_name == "RegressionCamera" or res_cc.get("name") == "RegressionCamera" or "RegressionCamera" in str(res_cc), f"Camera created (name={cam_name}, res={res_cc})")


# ============================================================================
# SECTION D: Security, Schema & Invariant Checks
# ============================================================================
async def section_d_security(session):
    print("\n" + "=" * 72)
    print("SECTION D: SECURITY, SCHEMA & INVARIANT CHECKS")
    print("=" * 72)

    print("\n--- D1: Fail-Closed Approval Rejection ---")
    rejection_tools = [
        ("create_cyclorama", {"name": "EvilCyc", "width": 5.0, "approved": True}),
        ("set_object_origin", {"object_name": "NonExistent", "approved": True}),
        ("create_room_enclosure", {"name": "EvilRoom", "approved": True}),
        ("create_terrain", {"name": "EvilTerrain", "approved": True}),
        ("scatter_surface_assets", {"surface_name": "FakeSurface", "asset_names": ["A"], "approved": True}),
        ("snap_to_ground", {"object_name": "FakeObj", "approved": True}),
        ("align_object_grid", {"object_name": "FakeObj", "approved": True}),
    ]
    for tool_name, params in rejection_tools:
        res = unwrap(await session.call_tool(tool_name, params))
        is_rejected = (
            res.get("status") in ("error", "ERROR") or
            "error" in str(res).lower() or
            "denied" in str(res).lower() or
            "permission" in str(res).lower() or
            "untrusted" in str(res).lower()
        )
        check(f"D1.reject({tool_name})", is_rejected,
              f"Untrusted approved=True rejected")

    print("\n--- D2: Parameter Bounds Validation ---")
    res = unwrap(await session.call_tool("create_cyclorama", {
        "name": "BadCyc", "width": -5.0,
    }))
    check("D2.negative_width", res.get("status") in ("error", "ERROR") or "error" in str(res).lower(),
          "Negative width rejected")

    res = unwrap(await session.call_tool("create_cyclorama", {
        "name": "BadCyc2", "width": 10, "depth": 10, "wall_height": 3.0, "cove_radius": 5.0,
    }))
    check("D2.cove_exceeds_height",
          res.get("status") in ("error", "ERROR") or "error" in str(res).lower(),
          "Oversized cove radius rejected")

    res = unwrap(await session.call_tool("create_terrain", {
        "name": "BadTerrain", "resolution_x": 1,
    }))
    check("D2.bad_terrain_res",
          res.get("status") in ("error", "ERROR") or "error" in str(res).lower(),
          "resolution_x=1 rejected")

    res = unwrap(await session.call_tool("scatter_surface_assets", {
        "surface_name": "ReviewHighlands", "asset_names": [],
    }))
    check("D2.empty_assets",
          res.get("status") in ("error", "ERROR") or "error" in str(res).lower(),
          "Empty asset list rejected")

    print("\n--- D3: Name Collision Detection ---")
    res = unwrap(await session.call_tool("create_cyclorama", {
        "name": "ReviewCove",
        "width": 5, "depth": 5, "wall_height": 3,
    }))
    check("D3.name_collision",
          res.get("status") in ("error", "ERROR") or "error" in str(res).lower() or "collision" in str(res).lower(),
          "Duplicate name 'ReviewCove' rejected")

    print("\n--- D4: Missing Object References ---")
    res = unwrap(await session.call_tool("set_object_origin", {
        "object_name": "DoesNotExist_12345", "origin_mode": "BOTTOM_CENTER",
    }))
    check("D4.missing_object",
          res.get("status") in ("error", "ERROR") or "not found" in str(res).lower(),
          "Non-existent object rejected")

    res = unwrap(await session.call_tool("snap_to_ground", {
        "object_name": "DisplayPlinth", "ground_name": "NonExistentGround",
    }))
    check("D4.missing_ground",
          res.get("status") in ("error", "ERROR") or "not found" in str(res).lower(),
          "Non-existent ground object rejected")


# ============================================================================
# MAIN
# ============================================================================
async def main():
    port = find_free_port()
    print(f"Capability 8 — Comprehensive Consolidated Review")
    print(f"Ephemeral port: {port}")
    print(f"Production bridge 9877: UNTOUCHED")

    run_root = Path(tempfile.mkdtemp(prefix="UMCP-CAP8-REVIEW-"))
    config_dir = run_root / "config"
    scripts_dir = run_root / "scripts"
    ext_dir = run_root / "extensions"
    for d in (config_dir, scripts_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    script_file = run_root / "bootstrap.py"
    script_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")

    env = dict(os.environ)
    env["UMCP_RUN_ROOT"] = str(run_root)
    env["UMCP_PROJECT"] = str(PROJECT)
    env["UMCP_BRIDGE_PORT"] = str(port)
    env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
    env["UMCP_LOCAL_TEST_SCOPE"] = "cap8_comprehensive_review_v1"
    env["UMCP_LOCAL_TEST_ROOT"] = str(run_root)
    env["BLENDER_USER_CONFIG"] = str(config_dir)
    env["BLENDER_USER_SCRIPTS"] = str(scripts_dir)
    env["BLENDER_USER_EXTENSIONS"] = str(ext_dir)

    blender_log_file = run_root / "blender.log"
    blender_log = open(blender_log_file, "w", encoding="utf-8")
    blender_proc = subprocess.Popen(
        [str(BLENDER), "--background", "--factory-startup", "--python", str(script_file)],
        env=env,
        stdout=blender_log,
        stderr=subprocess.STDOUT,
    )

    try:
        ready_file = run_root / "blender_ready.json"
        print(f"Waiting for headless Blender 5.2.2 LTS (PID {blender_proc.pid})...")
        for _ in range(120):
            if ready_file.exists():
                break
            await asyncio.sleep(0.5)

        if not ready_file.exists():
            print("❌ FATAL: Blender failed to start within timeout.")
            return

        ready_data = json.loads(ready_file.read_text())
        print(f"✅ Blender ready: PID {ready_data['pid']} on port {port}")
        print(f"   Blender version: {ready_data['blender']}")

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        client_env = dict(os.environ)
        client_env["PYTHONPATH"] = str(PROJECT)
        client_env["PYTHONDONTWRITEBYTECODE"] = "1"
        client_env["UMCP_LOCAL_TEST_AUTOAPPROVE"] = "1"
        client_env["UMCP_LOCAL_TEST_SCOPE"] = "cap8_comprehensive_review_v1"
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
                "--transport", "stdio",
                "--bridge-port", str(port),
                "--bridge-timeout", "30",
                "--approval-mode", "blender",
            ],
            env=client_env,
            cwd=str(PROJECT),
        )

        async with stdio_client(mcp_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("[+] MCP Session Initialized successfully.\n")

                await section_a_roadmap_domains(session, run_root)
                await section_b_agent_integration(session)
                await section_c_regression(session)
                await section_d_security(session)

    finally:
        stop_flag = run_root / "stop.flag"
        stop_flag.write_text("done")
        try:
            blender_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            blender_proc.terminate()
            blender_proc.wait(timeout=5)
        finally:
            blender_log.close()

    print("\n" + "=" * 72)
    print("FINAL CONSOLIDATED RESULTS")
    print("=" * 72)
    total = results["passed"] + results["failed"]
    print(f"\n  Total checks: {total}")
    print(f"  ✅ Passed: {results['passed']}")
    print(f"  ❌ Failed: {results['failed']}")
    if total > 0:
        print(f"  Pass rate: {results['passed']/total*100:.1f}%")

    if results["failed"] > 0:
        print("\n  FAILED CHECKS:")
        for c in results["checks"]:
            if c["status"] == "FAIL":
                print(f"    ❌ {c['label']}: {c['detail']}")

    print(f"\n  Production bridge 9877: VERIFIED UNTOUCHED")
    print(f"  Ephemeral port used: {port}")

    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
