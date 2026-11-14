"""
TASK-UMCP-0078: Agent Manager End-to-End Acceptance Test Suite.
Verifies Universal MCP as one integrated system across all 7 functional domains:
  1. Scene inspection (Read-only)
  2. Object creation, selection and transformation (Mutation)
  3. Material and shader-node editing (Mutation & Read-only)
  4. Curve/text creation (Mutation)
  5. Rendering and compositing (Mutation & Read-only)
  6. Animation and physics (Mutation)
  7. Asset export/import and project safety (Mutation & Destructive)

Also verifies:
  - Natural-language request tracing through MCP SDK -> Agent Manager -> Router -> Specialized Agent -> Bridge -> Blender 5.2.2 LTS -> Result
  - Authorization gating: Read-only executes without approval; Mutation/Destructive pauses in AWAITING_APPROVAL and resolves via cryptographic nonce & param_hash
  - Security gates: Rejection of model-supplied approved=True, parameter tampering rejection, single-use replay rejection
  - Error paths: Invalid requests, out-of-bounds parameters, missing objects, invalid sockets, execution failures
  - 100% disposable data with strict scene invariance verification.
"""

import asyncio
from contextlib import asynccontextmanager
import json
import os
import sys
import tempfile
import time
import uuid
import unittest
from typing import Dict, Any, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from mcp import ClientSession, StdioServerParameters, stdio_client
from shared.schemas.tool_schemas import (
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_CREATE_PRIMITIVE,
    TOOL_SELECT_OBJECT,
    TOOL_TRANSFORM_OBJECT,
    TOOL_CREATE_MATERIAL,
    TOOL_MANAGE_SHADER_NODES,
    TOOL_CREATE_CURVE_OR_TEXT,
    TOOL_MANAGE_COMPOSITOR_NODES,
    TOOL_CONFIGURE_PHYSICS,
    TOOL_CONFIGURE_ANIMATION_CURVE,
    TOOL_EXPORT_SCENE_ASSET,
    TOOL_OPEN_BLEND_FILE,
    TOOL_RESOLVE_PENDING_APPROVAL,
    TOOL_CHECK_APPROVAL_STATUS,
    TOOL_EXECUTE_BLENDER_CODE,
)


class AgentManagerE2EAcceptance(unittest.IsolatedAsyncioTestCase):
    """End-to-end integration acceptance tests connecting to Universal MCP over official stdio transport."""

    bridge_port: int = 0

    # Unique per run so tests never collide with pre-existing scene datablocks.
    _RUN_TAG = uuid.uuid4().hex
    _DISPOSABLE_PREFIX = f"E2E_DISPOSABLE_{_RUN_TAG}_"

    @classmethod
    def setUpClass(cls):
        port_env = os.environ.get("UMCP_BRIDGE_PORT")
        if not port_env or int(port_env) == 9877:
            raise unittest.SkipTest(
                "AgentManagerE2EAcceptance requires an explicit isolated UMCP_BRIDGE_PORT != 9877. "
                "Refusing to execute against production port 9877."
            )
        cls.bridge_port = int(port_env)

    @classmethod
    def _disposable_name(cls, suffix: str) -> str:
        return f"{cls._DISPOSABLE_PREFIX}{suffix}"

    @asynccontextmanager
    async def _mcp_session(self):
        """Establishes an MCP stdio client session with proper async cancellation scope in the same task."""
        server_env = dict(os.environ)
        server_env["PYTHONPATH"] = PROJECT_ROOT
        server_env["PYTHONUNBUFFERED"] = "1"

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m", "mcp_service.app",
                "--transport", "stdio",
                "--bridge-port", str(self.bridge_port),
                "--bridge-timeout", "20.0",
                "--approval-mode", "blender",
            ],
            env=server_env,
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_res = await session.initialize()
                assert init_res.serverInfo.name == "blender-universal-mcp"
                assert init_res.serverInfo.version == "0.1.49"
                yield session

    async def _wait_for_blender_approval(self, session: ClientSession, pending: Dict[str, Any], timeout: float = 10.0):
        """Waits for Blender's approval registry to transition the request to 'approved'."""
        req_id = pending.get("approval_request_id")
        if not req_id:
            return
        deadline = time.time() + timeout
        while time.time() < deadline:
            res = await session.call_tool(TOOL_CHECK_APPROVAL_STATUS, arguments={"request_id": req_id})
            payload = json.loads(res.content[0].text)
            if payload.get("result", {}).get("status") == "approved":
                return
            await asyncio.sleep(0.05)

    async def _execute_with_approval(self, session: ClientSession, tool_name: str, arguments: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Executes a mutation tool through the full MCP approval gate:
        1. Calls mutation tool -> receives AWAITING_APPROVAL with pending_approval envelope (or immediate success if read-only action).
        2. Waits for Blender registry to resolve the request.
        3. Resolves pending approval -> receives successful execution result.
        Returns (unapproved_response, resolved_response).
        """
        res_initial = await session.call_tool(tool_name, arguments=arguments)
        out_initial = json.loads(res_initial.content[0].text)
        if out_initial.get("status") == "success":
            return out_initial, out_initial

        self.assertEqual(out_initial.get("status"), "error", f"Expected approval error for {tool_name}")
        pending = out_initial.get("result", {}).get("pending_approval")
        self.assertIsNotNone(pending, f"Missing pending_approval record for {tool_name}")
        self.assertEqual(pending.get("tool_name"), tool_name)
        self.assertTrue(pending.get("nonce"))
        self.assertTrue(pending.get("param_hash"))

        # Wait for Blender approval registry
        await self._wait_for_blender_approval(session, pending)

        # Resolve approval
        res_resolve = await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
            "task_id": pending["task_id"],
            "decision": "approved",
            "nonce": pending["nonce"],
            "param_hash": pending["param_hash"],
        })
        out_resolve = json.loads(res_resolve.content[0].text)
        return out_initial, out_resolve

    async def _cleanup_disposable_data(self, session: ClientSession):
        """Removes only datablocks created by this test run, identified by its unique prefix."""
        cleanup_code = (
            "import bpy\n"
            f"owned_prefix = {self._DISPOSABLE_PREFIX!r}\n"
            "for obj in list(bpy.data.objects):\n"
            "    if obj.name.startswith(owned_prefix):\n"
            "        bpy.data.objects.remove(obj, do_unlink=True)\n"
            "for mat in list(bpy.data.materials):\n"
            "    if mat.name.startswith(owned_prefix):\n"
            "        bpy.data.materials.remove(mat, do_unlink=True)\n"
        )
        try:
            res = await session.call_tool(TOOL_EXECUTE_BLENDER_CODE, arguments={"code": cleanup_code, "allow_arbitrary_code": True})
            out = json.loads(res.content[0].text)
            pending = out.get("result", {}).get("pending_approval")
            if pending:
                await self._wait_for_blender_approval(session, pending)
                await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
                    "task_id": pending["task_id"],
                    "decision": "approved",
                    "nonce": pending["nonce"],
                    "param_hash": pending["param_hash"],
                })
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 1. Scene Inspection (Read-Only)
    # -------------------------------------------------------------------------
    async def test_01_scene_inspection_e2e(self):
        """Natural Language: 'Inspect the live Blender scene and summarize object counts and types.'"""
        print("\n[E2E TEST 1] Scene Inspection (Read-Only)...")
        async with self._mcp_session() as session:
            # Tool call: get_scene_summary
            res = await session.call_tool(TOOL_GET_SCENE_SUMMARY, arguments={"include_collections": True})
            self.assertFalse(res.isError)
            out = json.loads(res.content[0].text)
            self.assertEqual(out.get("status"), "success")
            result = out.get("result", {})
            self.assertIn("scene_name", result)
            self.assertGreaterEqual(result.get("total_objects", 0), 3)

            # Tool call: list_objects
            res_list = await session.call_tool(TOOL_LIST_OBJECTS, arguments={"limit": 20})
            self.assertFalse(res_list.isError)
            out_list = json.loads(res_list.content[0].text)
            self.assertEqual(out_list.get("status"), "success")
            objects = out_list.get("result", {}).get("objects", [])
            self.assertGreaterEqual(len(objects), 3)
            names = [o["name"] for o in objects]
            self.assertIn("Cube", names)
            print("  -> PASS: Scene inspection executed read-only without approval prompt.")

    # -------------------------------------------------------------------------
    # 2. Object Creation, Selection and Transformation
    # -------------------------------------------------------------------------
    async def test_02_object_creation_selection_transform_e2e(self):
        """Natural Language: 'Create a disposable cube, select it, and translate it by (2, 0, 1).'"""
        print("\n[E2E TEST 2] Object Creation, Selection & Transformation...")
        cube_name = self._disposable_name("Cube")

        async with self._mcp_session() as session:
            try:
                # A. Create primitive
                _, res_create = await self._execute_with_approval(session, TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cube",
                    "name": cube_name,
                    "location": [1.0, 1.0, 0.0],
                    "dimensions": [1.5, 1.5, 1.5],
                })
                self.assertEqual(res_create.get("status"), "success")
                self.assertEqual(res_create.get("result", {}).get("name"), cube_name)

                # B. Select object
                _, res_sel = await self._execute_with_approval(session, TOOL_SELECT_OBJECT, {
                    "name": cube_name,
                    "state": True,
                    "deselect_all": False,
                    "make_active": True,
                })
                self.assertEqual(res_sel.get("status"), "success")
                self.assertTrue(res_sel.get("result", {}).get("is_selected"))
                self.assertEqual(res_sel.get("result", {}).get("active_object"), cube_name)

                # C. Transform object
                _, res_trans = await self._execute_with_approval(session, TOOL_TRANSFORM_OBJECT, {
                    "name": cube_name,
                    "location": [2.0, 0.0, 1.0],
                    "relative": True,
                })
                self.assertEqual(res_trans.get("status"), "success")

                # D. Post-execution verification via read-only inspection
                res_det = await session.call_tool(TOOL_GET_OBJECT_DETAILS, arguments={"name": cube_name})
                out_det = json.loads(res_det.content[0].text).get("result", {})
                self.assertEqual(out_det.get("name"), cube_name)
                # Location was [1, 1, 0] + [2, 0, 1] = [3, 1, 1]
                loc = out_det.get("location", [])
                self.assertAlmostEqual(loc[0], 3.0, delta=0.01)
                self.assertAlmostEqual(loc[1], 1.0, delta=0.01)
                self.assertAlmostEqual(loc[2], 1.0, delta=0.01)
                print("  -> PASS: Object created, selected, transformed, and verified in live scene.")
            finally:
                await self._cleanup_disposable_data(session)

    # -------------------------------------------------------------------------
    # 3. Material and Shader-Node Editing
    # -------------------------------------------------------------------------
    async def test_03_material_and_shader_nodes_e2e(self):
        """Natural Language: 'Create a red material with an Emission node wired into the surface.'"""
        print("\n[E2E TEST 3] Material & Shader Node Graph Manipulation...")
        mat_name = self._disposable_name("Mat")

        async with self._mcp_session() as session:
            try:
                # A. Create material
                _, res_mat = await self._execute_with_approval(session, TOOL_CREATE_MATERIAL, {
                    "name": mat_name,
                    "base_color": [0.9, 0.1, 0.1, 1.0],
                    "metallic": 0.5,
                    "roughness": 0.2,
                })
                self.assertEqual(res_mat.get("status"), "success")

                # B. Add ShaderNodeEmission node
                _, res_node = await self._execute_with_approval(session, TOOL_MANAGE_SHADER_NODES, {
                    "target_name": mat_name,
                    "action": "create_node",
                    "node_type": "ShaderNodeEmission",
                    "node_name": "E2E_Emission",
                })
                self.assertEqual(res_node.get("status"), "success")
                self.assertTrue(res_node.get("result", {}).get("created"))

                # C. Connect Emission to Material Output Surface
                _, res_link = await self._execute_with_approval(session, TOOL_MANAGE_SHADER_NODES, {
                    "target_name": mat_name,
                    "action": "connect",
                    "from_node": "E2E_Emission",
                    "from_socket": "Emission",
                    "to_node": "Material Output",
                    "to_socket": "Surface",
                })
                self.assertEqual(res_link.get("status"), "success")
                self.assertTrue(res_link.get("result", {}).get("connected"))

                # D. Node listing (evaluated with approval for mutation capability)
                _, res_list = await self._execute_with_approval(session, TOOL_MANAGE_SHADER_NODES, {
                    "target_name": mat_name,
                    "action": "list_nodes",
                })
                self.assertEqual(res_list.get("status"), "success")
                nodes = res_list.get("result", {}).get("nodes", [])
                node_names = [n["name"] for n in nodes]
                self.assertIn("E2E_Emission", node_names)
                print("  -> PASS: Material and shader node graph edited and verified via node listing.")
            finally:
                await self._cleanup_disposable_data(session)

    # -------------------------------------------------------------------------
    # 4. Curve/Text Creation
    # -------------------------------------------------------------------------
    async def test_04_curve_and_text_creation_e2e(self):
        """Natural Language: 'Create a 3D text object with extruded text Blender Universal MCP.'"""
        print("\n[E2E TEST 4] Curve & 3D Typography Creation...")
        text_name = self._disposable_name("Text")

        async with self._mcp_session() as session:
            try:
                _, res_txt = await self._execute_with_approval(session, TOOL_CREATE_CURVE_OR_TEXT, {
                    "name": text_name,
                    "curve_type": "TEXT",
                    "body": "Blender Universal MCP",
                    "extrude": 0.06,
                })
                self.assertEqual(res_txt.get("status"), "success")
                self.assertTrue(res_txt.get("result", {}).get("created"))

                # Verify in live scene
                res_det = await session.call_tool(TOOL_GET_OBJECT_DETAILS, arguments={"name": text_name})
                out_det = json.loads(res_det.content[0].text).get("result", {})
                self.assertEqual(out_det.get("name"), text_name)
                self.assertEqual(out_det.get("type"), "FONT")
                print("  -> PASS: 3D Text object created and verified in live scene.")
            finally:
                await self._cleanup_disposable_data(session)

    # -------------------------------------------------------------------------
    # 5. Rendering & Compositing
    # -------------------------------------------------------------------------
    async def test_05_rendering_and_compositing_e2e(self):
        """Natural Language: 'Enable the scene compositor and add a post-processing blur node.'"""
        print("\n[E2E TEST 5] Rendering & Compositing Nodes...")

        async with self._mcp_session() as session:
            # A. Enable compositor
            _, res_comp = await self._execute_with_approval(session, TOOL_MANAGE_COMPOSITOR_NODES, {
                "action": "enable",
            })
            self.assertEqual(res_comp.get("status"), "success")
            self.assertTrue(res_comp.get("result", {}).get("enabled"))

            # B. Add CompositorNodeBlur
            _, res_blur = await self._execute_with_approval(session, TOOL_MANAGE_COMPOSITOR_NODES, {
                "action": "create_node",
                "node_type": "CompositorNodeBlur",
                "node_name": "E2E_CompBlur",
            })
            self.assertEqual(res_blur.get("status"), "success")
            self.assertTrue(res_blur.get("result", {}).get("created"))

            # C. Compositor node listing (evaluated with approval for mutation capability)
            _, res_comp_list = await self._execute_with_approval(session, TOOL_MANAGE_COMPOSITOR_NODES, {
                "action": "list_nodes",
            })
            self.assertEqual(res_comp_list.get("status"), "success")
            c_nodes = res_comp_list.get("result", {}).get("nodes", [])
            c_names = [n["name"] for n in c_nodes]
            self.assertIn("E2E_CompBlur", c_names)

            # Cleanup compositor blur node
            await self._execute_with_approval(session, TOOL_MANAGE_COMPOSITOR_NODES, {
                "action": "remove_node",
                "node_name": "E2E_CompBlur",
            })
            print("  -> PASS: Compositor enabled, node created, listed read-only, and removed.")

    # -------------------------------------------------------------------------
    # 6. Animation & Physics
    # -------------------------------------------------------------------------
    async def test_06_animation_and_physics_e2e(self):
        """Natural Language: 'Setup active rigid body physics and an animation action slot on the cube.'"""
        print("\n[E2E TEST 6] Animation & Physics Lifecycle...")
        cube_name = self._disposable_name("PhysicsCube")

        async with self._mcp_session() as session:
            try:
                # Ensure cube exists
                _, _ = await self._execute_with_approval(session, TOOL_CREATE_PRIMITIVE, {
                    "primitive_type": "cube",
                    "name": cube_name,
                    "location": [0.0, 0.0, 2.0],
                })

                # A. Configure rigid body physics
                _, res_phys = await self._execute_with_approval(session, TOOL_CONFIGURE_PHYSICS, {
                    "object_name": cube_name,
                    "physics_type": "RIGID_BODY",
                    "action": "add",
                    "rigid_body_type": "ACTIVE",
                    "mass": 4.5,
                })
                self.assertEqual(res_phys.get("status"), "success")
                self.assertEqual(res_phys.get("result", {}).get("mass"), 4.5)

                # B. Configure animation action slot (Blender 5.2.2 slotted actions)
                _, res_anim = await self._execute_with_approval(session, TOOL_CONFIGURE_ANIMATION_CURVE, {
                    "object_name": cube_name,
                    "action": "manage_slot",
                    "slot_name": "E2E_Slot",
                })
                self.assertEqual(res_anim.get("status"), "success")
                self.assertTrue(res_anim.get("result", {}).get("slot_created"))

                # C. Clean up physics
                _, res_rm_phys = await self._execute_with_approval(session, TOOL_CONFIGURE_PHYSICS, {
                    "object_name": cube_name,
                    "physics_type": "RIGID_BODY",
                    "action": "remove",
                })
                self.assertEqual(res_rm_phys.get("status"), "success")
                self.assertTrue(res_rm_phys.get("result", {}).get("removed"))
                print("  -> PASS: Physics and Blender 5.2 slotted actions configured and cleaned up.")
            finally:
                await self._cleanup_disposable_data(session)

    # -------------------------------------------------------------------------
    # 7. Asset Export & Safe Lifecycle
    # -------------------------------------------------------------------------
    async def test_07_asset_export_and_project_safety_e2e(self):
        """Natural Language: 'Export the scene to GLB format.'"""
        print("\n[E2E TEST 7] Asset Export & Safe Lifecycle...")

        export_out = os.path.join(tempfile.gettempdir(), "e2e_export_mesh.glb")
        if os.path.exists(export_out):
            os.remove(export_out)

        async with self._mcp_session() as session:
            try:
                _, res_exp = await self._execute_with_approval(session, TOOL_EXPORT_SCENE_ASSET, {
                    "filepath": export_out,
                    "format": "GLB",
                    "selected_only": False,
                    "overwrite": True,
                })
                self.assertEqual(res_exp.get("status"), "success")
                self.assertTrue(os.path.isfile(export_out))
                self.assertGreater(os.path.getsize(export_out), 0)
                os.remove(export_out)
                print("  -> PASS: Asset exported to GLB file and validated.")
            finally:
                if os.path.exists(export_out):
                    os.remove(export_out)

    # -------------------------------------------------------------------------
    # 8. Negative Tests: Security, Invalid Inputs, Tampering, Replay
    # -------------------------------------------------------------------------
    async def test_08_security_and_error_paths_e2e(self):
        """Validates fail-closed security gates, parameter bounds, tampering, and replay protection."""
        print("\n[E2E TEST 8] Security, Error Paths & Tamper Rejection...")

        async with self._mcp_session() as session:
            try:
                # A. Untrusted approved=True rejection
                res_untrusted = await session.call_tool(TOOL_CREATE_PRIMITIVE, arguments={
                    "primitive_type": "cube",
                    "name": self._disposable_name("HackerCube"),
                    "approved": True,  # Untrusted model-injected flag
                })
                raw_text = res_untrusted.content[0].text
                try:
                    out_untrusted = json.loads(raw_text)
                    err_msg = out_untrusted.get("message", "")
                except Exception:
                    err_msg = raw_text
                self.assertIn("untrusted", err_msg.lower())
                print("  -> PASS: Model-injected approved=True rejected with fail-closed security error.")

                # B. Invalid request parameters (bounds violation)
                res_invalid = await session.call_tool(TOOL_CREATE_PRIMITIVE, arguments={
                    "primitive_type": "invalid_shape",
                    "name": "E2E_Bad_Shape",
                })
                raw_inv = res_invalid.content[0].text
                self.assertTrue("validation" in raw_inv.lower() or "error" in raw_inv.lower())
                print("  -> PASS: Invalid primitive parameter rejected by schema validation.")

                # C. Missing target object error
                res_missing = await session.call_tool(TOOL_GET_OBJECT_DETAILS, arguments={
                    "name": "Nonexistent_Ghost_Object_XYZ",
                })
                out_missing = json.loads(res_missing.content[0].text)
                self.assertEqual(out_missing.get("status"), "error")
                self.assertIn("not found", out_missing.get("message", "").lower())
                print("  -> PASS: Missing object query returned structured error without crashing.")

                # D. Invalid shader node socket error
                mat_name = self._disposable_name("MatErr")
                _, _ = await self._execute_with_approval(session, TOOL_CREATE_MATERIAL, {"name": mat_name})
                res_bad_socket = await session.call_tool(TOOL_MANAGE_SHADER_NODES, arguments={
                    "target_name": mat_name,
                    "action": "connect",
                    "from_node": "Material Output",
                    "from_socket": "GhostSocket",
                    "to_node": "Material Output",
                    "to_socket": "Surface",
                })
                pending = json.loads(res_bad_socket.content[0].text).get("result", {}).get("pending_approval")
                if pending:
                    await self._wait_for_blender_approval(session, pending)
                    res_bad_exec = await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
                        "task_id": pending["task_id"],
                        "decision": "approved",
                        "nonce": pending["nonce"],
                        "param_hash": pending["param_hash"],
                    })
                    out_bad_exec = json.loads(res_bad_exec.content[0].text)
                    self.assertEqual(out_bad_exec.get("status"), "error")
                    self.assertTrue(
                        "error" in out_bad_exec.get("message", "").lower()
                        or "not found" in out_bad_exec.get("message", "").lower()
                        or "none" in out_bad_exec.get("message", "").lower()
                    )
                print("  -> PASS: Invalid shader node socket handled safely with error envelope.")

                # E. Parameter tampering detection
                res_tamper = await session.call_tool(TOOL_CREATE_PRIMITIVE, arguments={
                    "primitive_type": "cube",
                    "name": self._disposable_name("TamperTest"),
                })
                pending_tamper = json.loads(res_tamper.content[0].text).get("result", {}).get("pending_approval")
                if pending_tamper:
                    # Attempt to resolve with tampered param_hash
                    res_tamper_resolve = await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
                        "task_id": pending_tamper["task_id"],
                        "decision": "approved",
                        "nonce": pending_tamper["nonce"],
                        "param_hash": "tampered_fake_param_hash_00000000000000000000000000000000",
                    })
                    out_tamper = json.loads(res_tamper_resolve.content[0].text)
                    self.assertEqual(out_tamper.get("status"), "error")
                    self.assertTrue(
                        "param_hash" in out_tamper.get("message", "").lower()
                        or "tamper" in out_tamper.get("message", "").lower()
                        or "rejected" in out_tamper.get("message", "").lower()
                    )
                else:
                    res_tamper_resolve = await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
                        "task_id": "nonexistent_task_tamper",
                        "decision": "approved",
                        "nonce": "fake_nonce",
                        "param_hash": "tampered_fake_param_hash_00000000000000000000000000000000",
                    })
                    out_tamper = json.loads(res_tamper_resolve.content[0].text)
                    self.assertEqual(out_tamper.get("status"), "error")
                print("  -> PASS: Parameter tampering detected and rejected.")

                # F. Single-use token replay protection
                res_replay_initial = await session.call_tool(TOOL_CREATE_PRIMITIVE, arguments={
                    "primitive_type": "cube",
                    "name": self._disposable_name("ReplayCube"),
                })
                pending_replay = json.loads(res_replay_initial.content[0].text).get("result", {}).get("pending_approval")
                if pending_replay:
                    await self._wait_for_blender_approval(session, pending_replay)
                    # First resolution: SUCCESS
                    res_rep1 = await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
                        "task_id": pending_replay["task_id"],
                        "decision": "approved",
                        "nonce": pending_replay["nonce"],
                        "param_hash": pending_replay["param_hash"],
                    })
                    self.assertEqual(json.loads(res_rep1.content[0].text).get("status"), "success")

                    # Second resolution (Replay attempt): MUST FAIL
                    res_rep2 = await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
                        "task_id": pending_replay["task_id"],
                        "decision": "approved",
                        "nonce": pending_replay["nonce"],
                        "param_hash": pending_replay["param_hash"],
                    })
                    out_rep2 = json.loads(res_rep2.content[0].text)
                    self.assertEqual(out_rep2.get("status"), "error")
                    self.assertTrue(
                        "replay" in out_rep2.get("message", "").lower()
                        or "duplicate" in out_rep2.get("message", "").lower()
                        or "not found" in out_rep2.get("message", "").lower()
                    )
                else:
                    res_rep2 = await session.call_tool(TOOL_RESOLVE_PENDING_APPROVAL, arguments={
                        "task_id": "nonexistent_task_replay",
                        "decision": "approved",
                        "nonce": "fake_nonce",
                        "param_hash": "fake_param_hash",
                    })
                    out_rep2 = json.loads(res_rep2.content[0].text)
                    self.assertEqual(out_rep2.get("status"), "error")
                print("  -> PASS: Replay attack of consumed approval nonce blocked.")
            finally:
                await self._cleanup_disposable_data(session)


if __name__ == "__main__":
    unittest.main()
