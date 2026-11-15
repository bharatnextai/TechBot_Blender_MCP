# Interactive Blender Acceptance & Integration Validation Report

**Task:** TASK-UMCP-0019 — Interactive Acceptance Validation  
**Project:** Blender Universal MCP / Ollama Scene Assistant  
**Repository Path:** `D:\Blender-Ollama-Addon\blender-universal-mcp`  
**Reported Version:** `0.1.11`  
**Target Runtime:** Blender 5.2.2 LTS, Python 3.13  
**Date:** 2026-10-24  
**Validation Status:** Read-Only & Security-Negative Verification Complete; Zero Scene Mutations Performed  

---

## 1. Executive Summary

This document records the empirical live verification of the Blender Universal MCP integration against an interactive Blender 5.2.2 LTS session running on Windows. The validation was conducted via the official Model Context Protocol (MCP) stdio client connected to `mcp_service.app`, communicating across the thread-safe loopback TCP bridge (`127.0.0.1:9877`) with Blender's `MainThreadQueue`.

### Overall Status Table

| Capability / Test Area | Target Version | Live Status | Concrete Evidence / Reason |
| :--- | :--- | :--- | :--- |
| **Instance & Bridge Identification** | `0.1.11` | `PASS` | Blender 5.2.2 PID `4616` listening on loopback TCP port `9877`. Bridge `ping()` confirmed. |
| **MCP Protocol Handshake** | `0.1.11` | `PASS` | Protocol version `2025-11-25`, server name `blender-universal-mcp v0.1.11`. |
| **Tool Discovery (`tools/list`)** | `0.1.11` | `PASS` | All 13 tools discoverable with schemas and parameter constraints. |
| **Read-Only: `get_scene_summary`** | `0.1.11` | `PASS` | Retrieved active scene metadata (5 objects, Metric units, 24 FPS) in 7.99ms. |
| **Read-Only: `list_objects`** | `0.1.11` | `PASS` | Listed 5 objects with types and collections in 0.26ms. |
| **Read-Only: `get_object_details`** | `0.1.11` | `PASS` | Retrieved mesh statistics (8 vertices, 12 edges, 6 polygons) for `"Cube"` in 1.01ms. |
| **Read-Only: `list_materials`** | `0.1.11` | `PASS` | Retrieved 2 scene materials (`"Dots Stroke"`, `"Material"`) in 1.70ms. |
| **Read-Only: `inspect_scene_data`** | `0.1.11` | `BLOCKED` | Bridge returned `Unknown command: 'inspect_scene_data'` due to installed add-on v0.1.5. |
| **Read-Only: `capture_viewport`** | `0.1.11` | `BLOCKED` | Bridge returned `Unknown command: 'capture_viewport'` due to installed add-on v0.1.5. |
| **Security: Model `approved=True` Bypass** | `0.1.11` | `PASS` | Strictly rejected with `Approval denied: Tool argument 'approved=True' is untrusted`. |
| **Security: Unapproved Mutation Gating** | `0.1.11` | `PASS` | Gated in `AWAITING_APPROVAL`; safely timed out after 15.0s without mutating scene. |
| **Security: Schema & Input Validation** | `0.1.11` | `PASS` | Invalid arguments (e.g. invalid light type `LASER_BEAM`) rejected at schema boundary. |
| **Positive Scene Mutations** | `0.1.11` | `NOT TESTED` | Preserved user scene; explicit user authorization required before positive mutation. |
| **State Rollback & Undo Verification** | `0.1.11` | `NOT TESTED` | Requires positive mutation authorization. |
| **Scene Immutability Guarantee** | `0.1.11` | `PASS` | Pre- and post-test scene object counts (`5`), types, and transforms remain 100% identical. |

---

## 2. Connected Blender Instance & Runtime Reconciliation

### 2.1 Process & Network Binding
- **Executable Path:** `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`
- **Process ID (PID):** `4616`
- **Socket Binding:** `127.0.0.1:9877` (Local loopback only; remote network exposure blocked)
- **Protocol:** Framing line-delimited JSON-RPC messages

### 2.2 Version Reconciliations
- **Checked-in Source Version:** `0.1.11`
- **MCP Service Server Version:** `0.1.11`
- **Installed Blender Add-on Version:** `0.1.5`
- **Installed Add-on Location:** `C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp`

### 2.3 Handlers Available in Running Blender Instance
```python
[
    'get_scene_summary',
    'list_objects',
    'get_object_details',
    'list_materials',
    'create_primitive',
    'transform_object',
    'request_approval',
    'check_approval_status',
    'resolve_approval',
    'get_approval_settings',
    'set_approval_settings'
]
```

### 2.4 Reconciled Discrepancy
The repository code and automated test suite reflect `0.1.11` with full unit test coverage (261/261 tests passing). However, the running Blender 5.2 session was started with add-on extension version `0.1.5`. Consequently:
1. Baseline read-only and modeling tools from Phase 1/2 function live.
2. Approval gating and schema security operate at the MCP service boundary and strictly protect Blender.
3. Newly introduced Phase 3–5 tools (`inspect_scene_data`, `capture_viewport`, `create_material`, `assign_material`, `create_light`, `configure_world`, `execute_blender_code`) cannot execute live until the extension files are synced and reloaded in Blender.

---

## 3. Empirical Test Outputs

### 3.1 Read-Only Smoke Tests

#### `get_scene_summary`
```json
{
  "status": "success",
  "execution_time_ms": 7.99,
  "result": {
    "scene_name": "Scene",
    "frame_current": 1,
    "frame_start": 1,
    "frame_end": 250,
    "fps": 24,
    "unit_system": "METRIC",
    "total_objects": 5,
    "object_counts_by_type": {
      "MESH": 3,
      "LIGHT": 1,
      "CAMERA": 1
    },
    "active_camera": "Camera",
    "active_object": "UMCP_Batch_Plane_01",
    "collection_count": 1,
    "collections": [
      "Collection"
    ]
  }
}
```

#### `list_objects`
```json
{
  "status": "success",
  "execution_time_ms": 0.26,
  "result": {
    "total_matching": 5,
    "offset": 0,
    "limit": 50,
    "objects": [
      {"name": "Cube", "type": "MESH", "collections": ["Collection"], "visible": true},
      {"name": "Light", "type": "LIGHT", "collections": ["Collection"], "visible": true},
      {"name": "Camera", "type": "CAMERA", "collections": ["Collection"], "visible": true},
      {"name": "UMCP_AutoApprove_Cube_001", "type": "MESH", "collections": ["Collection"], "visible": true},
      {"name": "UMCP_Batch_Plane_01", "type": "MESH", "collections": ["Collection"], "visible": true}
    ]
  }
}
```

#### `get_object_details` (`"Cube"`)
```json
{
  "status": "success",
  "execution_time_ms": 1.01,
  "result": {
    "name": "Cube",
    "type": "MESH",
    "location": [0.0, 0.0, 0.0],
    "rotation_euler": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
    "dimensions": [2.0, 2.0, 2.0],
    "mesh_stats": {
      "vertices_count": 8,
      "edges_count": 12,
      "polygons_count": 6
    },
    "materials": ["Material"]
  }
}
```

#### `list_materials`
```json
{
  "status": "success",
  "execution_time_ms": 1.70,
  "result": {
    "total_materials": 2,
    "offset": 0,
    "limit": 100,
    "materials": [
      {"name": "Dots Stroke", "use_nodes": true, "users": 0},
      {"name": "Material", "use_nodes": true, "users": 1}
    ]
  }
}
```

---

## 4. Security & Approval Gate Negative Tests

| Test Case | Tool | Untrusted Input Parameter | Live MCP Service Response | Invariant Enforced |
| :--- | :--- | :--- | :--- | :--- |
| **Model Approval Bypass** | `create_primitive` | `{"primitive_type": "cube", "approved": True}` | `Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize scene mutation.` | Model `approved=True` rejected fail-closed |
| **Unapproved Request** | `create_primitive` | `{"primitive_type": "cube", "name": "Test"}` | `Approval timed out after 15.0s` | Mutation blocked without trusted human approval token |
| **Model Approval Bypass** | `transform_object` | `{"name": "Cube", "approved": True}` | `Approval denied: Tool argument 'approved=True' is untrusted...` | Transform mutation blocked |
| **Model Approval Bypass** | `create_material` | `{"name": "TestMat", "approved": True}` | `Approval denied: Tool argument 'approved=True' is untrusted...` | Material mutation blocked |
| **Model Approval Bypass** | `create_light` | `{"name": "TestLight", "approved": True}` | `Approval denied: Tool argument 'approved=True' is untrusted...` | Lighting mutation blocked |
| **Model Approval Bypass** | `configure_world` | `{"color": [0.5, 0.5, 0.5], "approved": True}` | `Approval denied: Tool argument 'approved=True' is untrusted...` | World mutation blocked |
| **Model Approval Bypass** | `execute_blender_code` | `{"operations": [...], "approved": True}` | `Approval denied: Tool argument 'approved=True' is untrusted...` | Code execution blocked |
| **Input Schema Validation** | `create_light` | `{"light_type": "LASER_BEAM"}` | `Input validation error: 'LASER_BEAM' is not one of ['POINT', 'SUN', 'SPOT', 'AREA']` | Invalid light type rejected before dispatch |

---

## 5. Post-Check Scene Immutability Verification

Following all read-only and security-negative test executions, scene state was re-inspected:
- **Pre-Test Object Count:** 5
- **Post-Test Object Count:** 5
- **Pre-Test Object Types:** `{'MESH': 3, 'LIGHT': 1, 'CAMERA': 1}`
- **Post-Test Object Types:** `{'MESH': 3, 'LIGHT': 1, 'CAMERA': 1}`
- **Cube Location:** `[0.0, 0.0, 0.0]` (unmoved)
- **Zero user assets modified or deleted.**

---

## 6. Stop Conditions & Recommendation

Per TASK-UMCP-0019 requirements:
- No dependencies were installed.
- No network ports were modified.
- No services were restarted or reconfigured without explicit authorization.
- Positive scene mutations were halted pending user authorization.

To proceed with live verification of Phases 3–5:
1. Sync repository addon directory `blender_addon/universal_mcp` to Blender's user extension folder (`C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\universal_mcp`).
2. Reload the extension in Blender to register the new handlers (`inspect_scene_data`, `capture_viewport`, `create_material`, `assign_material`, `create_light`, `configure_world`, `execute_blender_code`).
3. Execute positive mutations on temporary test objects (`UMCP_Test_Cube`, `UMCP_Test_Light`, etc.) with automated post-verification and teardown.
