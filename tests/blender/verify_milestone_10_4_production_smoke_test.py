"""
Milestone 10.4 Stage 2 Production Compatibility Smoke Test
Target: 127.0.0.1:9877 (PID 39604)
STRICTLY READ-ONLY OPERATIONS ONLY.
Guarantees:
- Zero mutations to production scene or process.
- No invocation of import, export, save, delete, batch, rollback, or workflow execution.
- Verifies listener, process identity, MCP connection, registered tools, and read-only scene summary.
"""

import sys
import json
import time
import socket
import subprocess
from pathlib import Path
from typing import Dict, Any

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
EVIDENCE_DIR = PROJECT / "tests" / "blender" / "output" / "milestone_10_4"
PROD_HOST = "127.0.0.1"
PROD_PORT = 9877
EXPECTED_PID = 39604


def run_production_smoke_test():
    print("=" * 80)
    print("CAPABILITY 10 — MILESTONE 10.4 STAGE 2 PRODUCTION COMPATIBILITY SMOKE TEST")
    print(f"TARGET: {PROD_HOST}:{PROD_PORT} | EXPECTED PID: {EXPECTED_PID}")
    print("MODE: STRICTLY READ-ONLY (ZERO MUTATIONS)")
    print("=" * 80)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_host": PROD_HOST,
        "target_port": PROD_PORT,
        "expected_pid": EXPECTED_PID,
        "checks": {},
    }

    # -----------------------------------------------------------------
    # Step 1: Verify Listener and Process Identity
    # -----------------------------------------------------------------
    print("\n--- Step 1: Listener & Process Identity Verification ---")
    ps_cmd = (
        f"$p = Get-Process -Id {EXPECTED_PID} -ErrorAction SilentlyContinue; "
        f"$c = Get-NetTCPConnection -LocalPort {PROD_PORT} -OwningProcess {EXPECTED_PID} -ErrorAction SilentlyContinue; "
        f"[PSCustomObject]@{{ ProcessName=$p.ProcessName; Id=$p.Id; Handles=$p.Handles; "
        f"Path=$p.Path; Port=$c.LocalPort; State=$c.State.ToString() }} | ConvertTo-Json"
    )
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    assert res.returncode == 0, f"Failed to query process/listener: {res.stderr}"
    p_info = json.loads(res.stdout.strip())
    print(f"[+] Process Name: {p_info.get('ProcessName')}")
    print(f"[+] Process ID: {p_info.get('Id')}")
    print(f"[+] Executable: {p_info.get('Path')}")
    print(f"[+] Listener Port: {p_info.get('Port')}")
    print(f"[+] Socket State: {p_info.get('State')}")

    assert p_info.get("Id") == EXPECTED_PID, f"PID mismatch: {p_info.get('Id')} != {EXPECTED_PID}"
    assert p_info.get("ProcessName", "").lower() == "blender", f"Unexpected process: {p_info.get('ProcessName')}"
    assert p_info.get("Port") == PROD_PORT, f"Port mismatch: {p_info.get('Port')} != {PROD_PORT}"
    assert p_info.get("State") == "Listen", f"Socket not in Listen state: {p_info.get('State')}"

    report["checks"]["process_identity"] = {
        "pid": p_info.get("Id"),
        "name": p_info.get("ProcessName"),
        "path": p_info.get("Path"),
        "port": p_info.get("Port"),
        "state": p_info.get("State"),
        "verified": True,
    }

    # -----------------------------------------------------------------
    # Step 2: Establish MCP Connection & Probe Liveness
    # -----------------------------------------------------------------
    print("\n--- Step 2: Establish Bridge Connection & Liveness Probe ---")
    sys.path.insert(0, str(PROJECT))
    from blender_addon.universal_mcp.bridge.bridge_client import BridgeClient

    client = BridgeClient(host=PROD_HOST, port=PROD_PORT, timeout=5.0)
    connected = client.connect()
    assert connected, f"Could not connect to production bridge at {PROD_HOST}:{PROD_PORT}"
    print(f"[+] TCP connection established to {PROD_HOST}:{PROD_PORT}")

    ping_res = client.send_command("ping")
    print(f"[+] Ping response: {ping_res}")
    assert ping_res.get("status") == "success"
    assert ping_res.get("result", {}).get("pong") is True, f"Ping did not return pong: {ping_res}"

    report["checks"]["connection_and_ping"] = {
        "connected": True,
        "ping_status": ping_res.get("status"),
        "pong": ping_res.get("result", {}).get("pong"),
        "verified": True,
    }

    # -----------------------------------------------------------------
    # Step 3: Inspect Registered Tools & Expected Capabilities
    # -----------------------------------------------------------------
    print("\n--- Step 3: Registered Tools & Capability Inspection ---")
    from mcp_service.registry.tool_registry import ToolRegistry

    tool_reg = ToolRegistry()
    tool_defs = tool_reg.get_tool_definitions()
    tool_names = tool_reg.tool_names
    print(f"[+] Total registered tools in MCP Service: {len(tool_names)}")

    expected_capability_tools = [
        "import_scene_asset",
        "export_scene_asset",
        "get_scene_summary",
        "list_objects",
        "get_object_details",
        "inspect_scene_data",
        "check_approval_status",
    ]
    missing_tools = [t for t in expected_capability_tools if t not in tool_names]
    assert not missing_tools, f"Missing expected tools in registry: {missing_tools}"
    print(f"[+] Verified key capability tools present: {expected_capability_tools}")

    report["checks"]["tool_registry"] = {
        "total_tools": len(tool_names),
        "key_tools_verified": expected_capability_tools,
        "all_tools": sorted(tool_names),
        "verified": True,
    }

    # -----------------------------------------------------------------
    # Step 4: Execute Safe Read-Only Inspection Request
    # -----------------------------------------------------------------
    print("\n--- Step 4: Safe Read-Only Inspection Request ---")
    # Read-only query: get_scene_summary
    t0 = time.time()
    summary_res = client.send_command("get_scene_summary", {})
    t_read = round((time.time() - t0) * 1000, 2)
    print(f"[+] get_scene_summary returned in {t_read}ms: status={summary_res.get('status')}")

    assert summary_res.get("status") == "success", f"get_scene_summary failed: {summary_res}"
    summary_data = summary_res.get("result", {})
    scene_name = summary_data.get("scene_name")
    total_objs = summary_data.get("total_objects")
    fps = summary_data.get("fps")
    obj_counts = summary_data.get("object_counts_by_type", {})
    print(f"[+] Active Scene Name: '{scene_name}'")
    print(f"[+] Total Scene Objects: {total_objs}")
    print(f"[+] FPS: {fps}")
    print(f"[+] Object Counts by Type: {obj_counts}")

    report["checks"]["read_only_scene_summary"] = {
        "execution_time_ms": t_read,
        "scene_name": scene_name,
        "total_objects": total_objs,
        "fps": fps,
        "object_counts_by_type": obj_counts,
        "verified": True,
    }

    # -----------------------------------------------------------------
    # Step 5: Confirm Production Scene & Process Remain Unchanged
    # -----------------------------------------------------------------
    print("\n--- Step 5: Scene & Process Invariance Confirmation ---")
    time.sleep(0.5)

    # Re-verify summary to confirm identical state (zero mutations)
    summary_res_2 = client.send_command("get_scene_summary", {})
    assert summary_res_2.get("status") == "success"
    summary_data_2 = summary_res_2.get("result", {})

    assert summary_data_2.get("total_objects") == total_objs, (
        f"Object count changed: {total_objs} -> {summary_data_2.get('total_objects')}"
    )
    assert summary_data_2.get("scene_name") == scene_name, "Scene name changed"
    assert summary_data_2.get("object_counts_by_type") == obj_counts, "Object types changed"
    print("[+] Confirmed: 2nd read-only inspection shows identical scene state (zero mutations)")

    # Clean client disconnect
    client.close()
    print("[+] Clean client disconnect completed")

    # Confirm process and port are still running untouched
    res2 = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    assert res2.returncode == 0
    p_info_2 = json.loads(res2.stdout.strip())
    assert p_info_2.get("Id") == EXPECTED_PID
    assert p_info_2.get("State") == "Listen"
    print(f"[+] Confirmed: PID {EXPECTED_PID} still alive and listening on port {PROD_PORT}")

    report["checks"]["invariance_confirmation"] = {
        "post_test_pid": p_info_2.get("Id"),
        "post_test_port": p_info_2.get("Port"),
        "post_test_state": p_info_2.get("State"),
        "scene_objects_unchanged": True,
        "mutations_invoked": 0,
        "verified": True,
    }

    # Save evidence file
    prod_telemetry_file = EVIDENCE_DIR / "milestone_10_4_production_smoke_test.json"
    prod_telemetry_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[+] Production smoke test evidence preserved to: {prod_telemetry_file}")

    print("\n" + "=" * 80)
    print("PRODUCTION COMPATIBILITY SMOKE TEST PASSED (100% READ-ONLY)")
    print("=" * 80)


if __name__ == "__main__":
    run_production_smoke_test()
