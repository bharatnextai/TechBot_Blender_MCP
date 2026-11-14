"""Source-pinned single-success and rollback MCP acceptance in disposable Blender."""
import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
EVIDENCE = PROJECT / "docs" / "verification" / "modeling_e2e_01"
QUAD = (
    [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
    [(0, 1), (1, 2), (2, 3), (3, 0)],
    [(0, 1, 2, 3)],
)
SUCCESS_OP = {"action": "move_vertices", "vertices": [0], "delta": [0, 0, 0.25]}
ROLLBACK_OP = {"action": "move_vertices", "vertices": [0], "delta": [0, 0, 0.25]}


def source_files(root):
    files = []
    for folder in ("mcp_service", "shared", "blender_addon/universal_mcp"):
        files.extend((root / folder).rglob("*.py"))
    files.extend((root / "pyproject.toml", root / "tests/policy_candidates/modeling_mesh_policy.py"))
    return sorted((p for p in files if p.is_file() and "__pycache__" not in p.parts),
                  key=lambda p: p.relative_to(root).as_posix())


def source_identity(root):
    entries = []
    digest = hashlib.sha256()
    for path in source_files(root):
        relative = path.relative_to(root).as_posix()
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative, "sha256": content_hash})
        digest.update(relative.encode("utf-8") + b"\0" + bytes.fromhex(content_hash))
    return {"root": str(root.resolve()), "algorithm": "sha256(sorted-relative-path\0file-sha256-bytes)",
            "source_tree_sha256": digest.hexdigest(), "files": entries}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path, value):
    """Append one bounded diagnostic record; callers must never pass tool params."""
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, default=str) + "\n")
        stream.flush()


def mesh_state(obj):
    return {
        "object_name": obj.name,
        "mesh_name": obj.data.name,
        "mesh_pointer": obj.data.as_pointer(),
        "vertices": [list(v.co) for v in obj.data.vertices],
        "edges": [list(e.vertices) for e in obj.data.edges],
        "faces": [list(p.vertices) for p in obj.data.polygons],
    }


def fixture(root, port, expected_source_hash):
    import bpy
    from tests.policy_candidates.modeling_mesh_policy import authorizes
    from blender_addon.universal_mcp.bridge import component_edit, mesh_atomic
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue

    assert bpy.app.background and not bpy.data.filepath and port != 9877
    bpy.types.Scene.umcp_bridge_port = bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=True)
    scene = bpy.context.scene
    assert scene.umcp_require_scene_mutation_approval is True

    loaded_modules = {}
    for name in (
        "blender_addon.universal_mcp.bridge.handlers",
        "blender_addon.universal_mcp.bridge.component_edit",
        "blender_addon.universal_mcp.bridge.mesh_atomic",
        "blender_addon.universal_mcp.bridge.mesh_topology",
        "blender_addon.universal_mcp.bridge.approval_registry",
        "blender_addon.universal_mcp.bridge.main_thread_queue",
    ):
        module = sys.modules[name]
        module_path = Path(module.__file__).resolve()
        loaded_modules[name] = {"path": str(module_path),
                                "sha256": hashlib.sha256(module_path.read_bytes()).hexdigest()}
    actual_source = source_identity(PROJECT)
    assert actual_source["source_tree_sha256"] == expected_source_hash

    original_objects = list(bpy.data.objects)
    protected_before = {obj.name: mesh_state(obj) if obj.type == "MESH" else {
        "type": obj.type, "matrix_world": [list(row) for row in obj.matrix_world],
        "data_pointer": obj.data.as_pointer() if obj.data else None,
    } for obj in original_objects}
    factory_inventory = sorted(bpy.data.objects.keys())

    owned = {}
    for name in ("FixtureSuccess", "FixtureRollback"):
        mesh = bpy.data.meshes.new(name + "Data")
        mesh.from_pydata(*QUAD)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        owned[name] = (obj, mesh)
    bpy.context.view_layer.update()

    fixture_inventory = {"objects": sorted(bpy.data.objects.keys()), "meshes": sorted(bpy.data.meshes.keys())}
    before_states = {name: mesh_state(obj) for name, (obj, _mesh) in owned.items()}
    # Direct no-token boundary check: the enabled approval gate rejects without mutation.
    missing_token_error = None
    try:
        component_edit.handle_edit_mesh(bpy, {
            "name": "FixtureSuccess", "expected_snapshot_id": "sha256:" + "0" * 64,
            "operations": [SUCCESS_OP],
        })
    except PermissionError as exc:
        missing_token_error = str(exc)
    assert missing_token_error and mesh_state(owned["FixtureSuccess"][0]) == before_states["FixtureSuccess"]

    events = []
    token_params = {}
    queue = MainThreadQueue(bpy)
    real_handler = queue._handlers["edit_mesh"]

    def tracked(bpy_module=None, params=None):
        name = params["name"]
        assert name in owned
        obj, original_mesh = owned[name]
        captured = json.loads(json.dumps(params))
        before = mesh_state(obj)
        mesh_names_before = sorted(bpy.data.meshes.keys())
        injected = {}

        if name == "FixtureSuccess":
            result = real_handler(bpy_module=bpy_module, params=params)
            after = mesh_state(obj)
            assert result["success"] is True and result["verified"] is True
            assert obj.data != original_mesh
            assert after["vertices"][0][2] == before["vertices"][0][2] + 0.25
            try:
                real_handler(bpy_module=bpy_module, params=captured)
            except PermissionError as exc:
                replay_denied = str(exc)
            else:
                raise AssertionError("Consumed single-use token replay was accepted")
            assert mesh_state(obj) == after
            assert sorted(bpy.data.meshes.keys()) == mesh_names_before
            token_params[name] = captured
            events.append({"case": name, "before": before, "after": after,
                           "replay_denied": replay_denied,
                           "mesh_inventory_before": mesh_names_before,
                           "mesh_inventory_after": sorted(bpy.data.meshes.keys()),
                           "verified_receipt": result})
            write_json(root / "mutation_evidence.json", events)
            return result

        def fail_after_mutation(target, context, expected):
            assert target is obj and target.data != original_mesh
            injected["candidate_state"] = mesh_state(target)
            injected["candidate_snapshot_id"] = expected["snapshot_id"]
            injected["candidate_mesh_pointer"] = target.data.as_pointer()
            raise RuntimeError("E2E_FORCED_FAILURE_AFTER_MESH_SWAP")

        try:
            with patch.object(mesh_atomic, "verify_commit", side_effect=fail_after_mutation):
                real_handler(bpy_module=bpy_module, params=params)
        except RuntimeError as exc:
            failure_text = str(exc)
            assert "ROLLED_BACK_VERIFIED" in failure_text, failure_text
        else:
            raise AssertionError("Injected post-mutation failure falsely succeeded")

        after = mesh_state(obj)
        mesh_names_after = sorted(bpy.data.meshes.keys())
        assert after == before
        assert obj.data == original_mesh
        assert mesh_names_after == mesh_names_before
        try:
            real_handler(bpy_module=bpy_module, params=captured)
        except PermissionError as exc:
            replay_denied = str(exc)
        else:
            raise AssertionError("Consumed failed-attempt token replay was accepted")
        assert mesh_state(obj) == before and sorted(bpy.data.meshes.keys()) == mesh_names_before
        token_params[name] = captured
        events.append({"case": name, "before": before, "candidate_after_mutation": injected,
                       "after_rollback": after, "failure": failure_text,
                       "original_mesh_identity_restored": obj.data == original_mesh,
                       "mesh_inventory_before": mesh_names_before,
                       "mesh_inventory_after": mesh_names_after,
                       "replay_denied": replay_denied})
        write_json(root / "mutation_evidence.json", events)
        raise RuntimeError("ROLLED_BACK_VERIFIED: E2E_FORCED_FAILURE_AFTER_MESH_SWAP")

    queue.register_handler("edit_mesh", tracked)

    # Test-host-only copy of the bridge connection loop. It preserves the normal
    # framing/queue behavior while recording command names, request IDs, socket
    # outcomes, and otherwise-suppressed connection exceptions. No payloads or
    # approval credentials are written to disk.
    bridge_trace_path = root / "bridge_connection_trace.jsonl"
    trace_lock = threading.Lock()
    seen_tokens = set()

    def bridge_trace(event, **fields):
        with trace_lock:
            append_jsonl(bridge_trace_path, {"time": time.time(), "event": event, **fields})

    def exception_message(exc):
        message = str(exc)
        for token in tuple(seen_tokens):
            if token:
                message = message.replace(token, "<redacted-token>")
        return message

    class DiagnosticBridgeServer(BridgeServer):
        def _client_handler(self, client_sock):
            client_sock.settimeout(1.0)
            buffer = b""
            last_command = {"command": None, "request_id": None}
            try:
                peer = client_sock.getpeername()
                connection_id = f"{peer[0]}:{peer[1]}"
            except Exception:
                connection_id = "unknown"

            def dispatch(command):
                cmd_type = command.get("type") or command.get("command") or ""
                params = command.get("params") or {}
                request_id = params.get("request_id") if isinstance(params, dict) else None
                last_command.update(command=cmd_type, request_id=request_id)
                approval_command = cmd_type in {"request_approval", "check_approval_status"}
                if approval_command:
                    bridge_trace("command_received", connection_id=connection_id,
                                 command=cmd_type, request_id=request_id)
                if cmd_type == "ping":
                    response = {"status": "success", "result": {"pong": True}}
                else:
                    response = self._queue.submit_and_wait(command, timeout=30.0)
                result = response.get("result") if isinstance(response, dict) else None
                response_request_id = (result.get("request_id") if isinstance(result, dict) else None) or request_id
                if isinstance(result, dict) and result.get("approval_token"):
                    seen_tokens.add(result["approval_token"])
                if approval_command:
                    last_command["request_id"] = response_request_id
                    bridge_trace("response_ready", connection_id=connection_id,
                                 command=cmd_type, request_id=response_request_id,
                                 response_status=response.get("status") if isinstance(response, dict) else None)
                raw_response = json.dumps(response).encode("utf-8") + b"\n"
                if approval_command:
                    bridge_trace("response_send_attempt", connection_id=connection_id,
                                 command=cmd_type, request_id=response_request_id,
                                 byte_count=len(raw_response))
                client_sock.sendall(raw_response)
                if approval_command:
                    bridge_trace("response_sent", connection_id=connection_id,
                                 command=cmd_type, request_id=response_request_id,
                                 byte_count=len(raw_response))

            try:
                while self.running:
                    try:
                        data = client_sock.recv(8192)
                        if not data:
                            bridge_trace("socket_eof_received", connection_id=connection_id,
                                         last_command=last_command["command"],
                                         request_id=last_command["request_id"],
                                         buffered_bytes=len(buffer))
                            if buffer.strip():
                                try:
                                    command = json.loads(buffer.decode("utf-8").strip())
                                    dispatch(command)
                                except Exception as exc:
                                    bridge_trace("trailing_frame_error", connection_id=connection_id,
                                                 last_command=last_command["command"],
                                                 request_id=last_command["request_id"],
                                                 exception_type=type(exc).__name__,
                                                 exception_message=exception_message(exc))
                            break

                        buffer += data
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            line = line.decode("utf-8").strip()
                            if not line:
                                continue
                            try:
                                dispatch(json.loads(line))
                            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                                error_response = {"status": "error", "message": f"Malformed JSON: {exc}"}
                                client_sock.sendall(json.dumps(error_response).encode("utf-8") + b"\n")

                        if buffer.strip().startswith(b"{") and buffer.strip().endswith(b"}"):
                            try:
                                command = json.loads(buffer.decode("utf-8").strip())
                                buffer = b""
                                dispatch(command)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pass
                    except socket.timeout:
                        continue
                    except Exception as exc:
                        bridge_trace("connection_exception_close", connection_id=connection_id,
                                     last_command=last_command["command"],
                                     request_id=last_command["request_id"],
                                     exception_type=type(exc).__name__,
                                     exception_message=exception_message(exc))
                        break
            finally:
                with self._clients_lock:
                    self._clients.discard(client_sock)
                try:
                    client_sock.close()
                except Exception:
                    pass
                bridge_trace("connection_closed", connection_id=connection_id,
                             last_command=last_command["command"],
                             request_id=last_command["request_id"])

    server = DiagnosticBridgeServer(port=port, queue=queue)
    server.start()
    write_json(root / "blender_identity.json", {
        "pid": os.getpid(), "executable": bpy.app.binary_path,
        "version": bpy.app.version_string, "background": bpy.app.background,
        "filepath": bpy.data.filepath, "port": port,
        "require_approval": bool(scene.umcp_require_scene_mutation_approval),
        "source_tree_sha256": actual_source["source_tree_sha256"],
        "loaded_modules": loaded_modules,
        "factory_inventory": factory_inventory,
        "fixture_inventory_before_calls": fixture_inventory,
        "before_states": before_states,
        "missing_token_rejected": missing_token_error,
    })

    registry = get_approval_registry()
    approved = set()
    requests = []
    deadline = time.monotonic() + 120
    try:
        while not (root / "stop").exists() and time.monotonic() < deadline:
            queue.drain_queue()
            for request in list(registry._requests.values()):
                if request.status != "pending" or request.request_id in approved:
                    continue
                name = request.params.get("name")
                expected = {
                    "FixtureSuccess": [SUCCESS_OP],
                    "FixtureRollback": [ROLLBACK_OP],
                }.get(name)
                assert request.tool_name == "edit_mesh" and expected is not None
                assert request.params["operations"] == expected
                assert request.params["expected_snapshot_id"] == mesh_atomic.snapshot(owned[name][0], bpy.context)["snapshot_id"]
                assert authorizes(bpy, request.tool_name, request.params, owned)
                ok, reason = registry.resolve_request(request.request_id, "approved",
                    reason="USER-AUTHORIZED ISOLATED edit_mesh TEST SUBSET", approve_task_group=False)
                assert ok, reason
                approved.add(request.request_id)
                requests.append({"request_id": request.request_id, "tool_name": request.tool_name,
                    "name": name, "arg_hash": request.arg_hash,
                    "expires_at": request.created_at + request.timeout_seconds,
                    "decision": "approved_by_scoped_disposable_test_host"})
            time.sleep(0.01)
        assert len(requests) == 2 and len(events) == 2, (len(requests), len(events))
    finally:
        server.stop()
        protected_after = {obj.name: mesh_state(obj) if obj.type == "MESH" else {
            "type": obj.type, "matrix_world": [list(row) for row in obj.matrix_world],
            "data_pointer": obj.data.as_pointer() if obj.data else None,
        } for obj in original_objects}
        final_inventory = {"objects": sorted(bpy.data.objects.keys()), "meshes": sorted(bpy.data.meshes.keys())}
        statuses = [registry.inspect_request_status(item["request_id"]) for item in requests]
        native = {"factory_objects_unchanged": protected_before == protected_after,
            "protected_before": protected_before, "protected_after": protected_after,
            "fixture_inventory_before_calls": fixture_inventory, "fixture_inventory_after_calls": final_inventory,
            "fixture_inventory_unchanged": fixture_inventory == final_inventory,
            "requests": requests, "approval_statuses": statuses,
            "all_tokens_consumed": all(item["token_consumed"] for item in statuses),
            "events": events}
        write_json(root / "native_evidence.json", native)
        assert native["factory_objects_unchanged"] and native["fixture_inventory_unchanged"]
        assert native["all_tokens_consumed"]


def topology_result(payload):
    result = payload.get("result", {})
    return result.get("observed_data", result)


async def run_client(root, port, expected_identity):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    identity_wrapper = r'''
import hashlib,json,os,sys,time
from pathlib import Path
import mcp_service.app as app
import mcp_service.server.mcp_server as server
import mcp_service.execution.blender_executor as executor
import mcp_service.agents.dispatcher as dispatcher
import mcp_service.registry.tool_registry as registry
import shared.schemas.tool_schemas as schemas
from blender_addon.universal_mcp.bridge import bridge_client

trace_path=Path(os.environ["UMCP_LOCAL_TEST_ROOT"])/"approval_provider_trace.jsonl"
trace_context={"command":None,"request_id":None,"connection_id":None}
seen_tokens=set()
def trace(event,**fields):
    record={"time":time.time(),"event":event,**fields}
    with trace_path.open("a",encoding="utf-8") as stream:
        stream.write(json.dumps(record,sort_keys=True,default=str)+"\n");stream.flush()
def safe_exception(exc):
    message=str(exc)
    for token in tuple(seen_tokens):
        if token: message=message.replace(token,"<redacted-token>")
    return message
class SocketTrace:
    def __init__(self,raw): self.raw=raw
    def __getattr__(self,name): return getattr(self.raw,name)
    def sendall(self,data):
        ctx=dict(trace_context)
        if ctx.get("command") not in {"request_approval","check_approval_status"}:
            return self.raw.sendall(data)
        trace("socket_send_attempt",**ctx,byte_count=len(data))
        try:
            result=self.raw.sendall(data)
            trace("socket_send_complete",**ctx,byte_count=len(data))
            return result
        except Exception as exc:
            trace("socket_send_error",**ctx,exception_type=type(exc).__name__,exception_message=safe_exception(exc))
            raise
    def recv(self,size):
        ctx=dict(trace_context)
        if ctx.get("command") not in {"request_approval","check_approval_status"}:
            return self.raw.recv(size)
        try:
            data=self.raw.recv(size)
            trace("socket_eof" if not data else "socket_receive",**ctx,byte_count=len(data))
            return data
        except Exception as exc:
            trace("socket_receive_error",**ctx,exception_type=type(exc).__name__,exception_message=safe_exception(exc))
            raise

original_connect=bridge_client.BridgeClient.connect
original_send_command=bridge_client.BridgeClient.send_command
def traced_connect(self):
    connected=original_connect(self)
    if connected and self._sock is not None and not isinstance(self._sock,SocketTrace):
        self._sock=SocketTrace(self._sock)
    if connected:
        try: trace_context["connection_id"]="{}:{}".format(*self._sock.getsockname())
        except Exception: trace_context["connection_id"]="unknown"
    return connected
def traced_send_command(self,cmd_type,params=None):
    if cmd_type not in {"request_approval","check_approval_status"}:
        return original_send_command(self,cmd_type,params)
    params=params or {}
    trace_context.update(command=cmd_type,request_id=params.get("request_id"))
    if self._sock is None:
        try: trace_context["connection_id"]="{}:{}".format(*self._sock.getsockname())
        except Exception: trace_context["connection_id"]="pending_connect"
    trace("approval_command_started",**dict(trace_context))
    try:
        response=original_send_command(self,cmd_type,params)
        result=response.get("result") if isinstance(response,dict) else None
        if isinstance(result,dict):
            request_id=result.get("request_id") or trace_context.get("request_id")
            token=result.get("approval_token")
            if token: seen_tokens.add(token)
            trace_context["request_id"]=request_id
            trace("approval_response_received",**dict(trace_context),
                  response_status=response.get("status"),approval_status=result.get("status"),
                  token_present=bool(token))
        else:
            trace("approval_response_received",**dict(trace_context),
                  response_status=response.get("status") if isinstance(response,dict) else None)
        return response
    except Exception as exc:
        trace("approval_command_failed",**dict(trace_context),
              exception_type=type(exc).__name__,exception_message=safe_exception(exc))
        raise
    finally:
        trace_context.update(command=None,request_id=None)
bridge_client.BridgeClient.connect=traced_connect
bridge_client.BridgeClient.send_command=traced_send_command

root=Path.cwd()
paths=[]
for folder in ("mcp_service","shared","blender_addon/universal_mcp"):
    paths.extend((root/folder).rglob("*.py"))
paths.extend((root/"pyproject.toml",root/"tests/policy_candidates/modeling_mesh_policy.py"))
d=hashlib.sha256()
for p in sorted((p for p in paths if p.is_file() and "__pycache__" not in p.parts),key=lambda p:p.relative_to(root).as_posix()):
    rel=p.relative_to(root).as_posix(); h=hashlib.sha256(p.read_bytes()).hexdigest(); d.update(rel.encode()+b"\0"+bytes.fromhex(h))
mods={"app":app,"server":server,"executor":executor,"dispatcher":dispatcher,"registry":registry,"schemas":schemas,"bridge_client":bridge_client}
records={}
for n,m in mods.items():
    p=Path(m.__file__).resolve(); records[n]={"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
actual=d.hexdigest(); expected=os.environ["UMCP_EXPECTED_SOURCE_SHA256"]
record={"pid":os.getpid(),"cwd":str(root.resolve()),"python":sys.executable,"python_version":sys.version,"pythonpath":os.environ.get("PYTHONPATH"),"source_tree_sha256":actual,"expected_source_tree_sha256":expected,"source_hash_match":actual==expected,"loaded_modules":records}
if actual!=expected: raise RuntimeError("service source identity mismatch")
(Path(os.environ["UMCP_LOCAL_TEST_ROOT"])/"service_identity.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
print("UMCP_SERVICE_SOURCE_IDENTITY="+json.dumps(record,sort_keys=True),file=sys.stderr,flush=True)
app.main()
'''
    env = dict(os.environ, PYTHONPATH=str(PROJECT), PYTHONDONTWRITEBYTECODE="1",
               UMCP_LOCAL_TEST_ROOT=str(root), UMCP_EXPECTED_SOURCE_SHA256=expected_identity["source_tree_sha256"])
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
    parameters = StdioServerParameters(command=sys.executable,
        args=["-B", "-c", identity_wrapper, "--transport", "stdio", "--bridge-port", str(port),
              "--bridge-timeout", "5", "--approval-mode", "blender"], env=env, cwd=str(PROJECT))
    calls = []
    with (root / "mcp_service_stderr.log").open("w", encoding="utf-8") as log:
        async with stdio_client(parameters, errlog=log) as streams:
            async with ClientSession(*streams) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {"edit_mesh", "inspect_scene_data"} <= names
                write_json(root / "mcp_catalog.json", {"server_info": init.serverInfo.model_dump(),
                    "required_tools_present": sorted({"edit_mesh", "inspect_scene_data"} & names),
                    "tool_count": len(names), "tools": [tool.model_dump() for tool in tools.tools]})

                async def call(tool, args, success=True):
                    response = await session.call_tool(tool, arguments=args)
                    raw = response.model_dump(mode="json")
                    payload = json.loads(response.content[0].text)
                    calls.append({"tool": tool, "request": args, "response": raw,
                                  "expected_success": success, "status": payload.get("status")})
                    write_json(root / "mcp_calls.json", calls)
                    assert not response.isError, calls[-1]
                    assert (payload.get("status") == "success") == success, calls[-1]
                    return payload

                before = {}
                for name in ("FixtureSuccess", "FixtureRollback"):
                    pages = {}
                    for domain in ("vertices", "edges", "faces"):
                        payload = await call("inspect_scene_data", {"category": "mesh_topology",
                            "target_name": name, "element_domain": domain, "limit": 32})
                        page = topology_result(payload)
                        assert page["returned_count"] == len(page["elements"])
                        assert page["returned_count"] == page["total"]
                        assert page["topology_source"] == "BASE_MESH"
                        pages[domain] = page
                    assert len({pages[d]["snapshot_id"] for d in pages}) == 1
                    assert len({pages[d]["state_id"] for d in pages}) == 1
                    before[name] = pages
                write_json(root / "topology_before.json", before)

                await call("edit_mesh", {"name": "FixtureSuccess",
                    "expected_snapshot_id": before["FixtureSuccess"]["vertices"]["snapshot_id"],
                    "operations": [SUCCESS_OP]})
                success_after = {}
                for domain in ("vertices", "edges", "faces"):
                    payload = await call("inspect_scene_data", {"category": "mesh_topology",
                        "target_name": "FixtureSuccess", "element_domain": domain, "limit": 32})
                    success_after[domain] = topology_result(payload)
                write_json(root / "topology_success_after.json", success_after)
                prior_v = before["FixtureSuccess"]["vertices"]["elements"]
                after_v = success_after["vertices"]["elements"]
                assert len(prior_v) == len(after_v) == 4
                assert after_v[0]["co"][2] == prior_v[0]["co"][2] + 0.25
                assert after_v[1:] == prior_v[1:]
                for domain in ("edges", "faces"):
                    assert success_after[domain]["elements"] == before["FixtureSuccess"][domain]["elements"]
                assert success_after["vertices"]["snapshot_id"] != before["FixtureSuccess"]["vertices"]["snapshot_id"]
                assert success_after["vertices"]["state_id"] != before["FixtureSuccess"]["vertices"]["state_id"]
                assert len({success_after[d]["snapshot_id"] for d in success_after}) == 1
                assert len({success_after[d]["state_id"] for d in success_after}) == 1

                rollback_result = await call("edit_mesh", {"name": "FixtureRollback",
                    "expected_snapshot_id": before["FixtureRollback"]["vertices"]["snapshot_id"],
                    "operations": [ROLLBACK_OP]}, success=False)
                assert "ROLLED_BACK_VERIFIED" in json.dumps(rollback_result)
                rollback_after = {}
                for domain in ("vertices", "edges", "faces"):
                    payload = await call("inspect_scene_data", {"category": "mesh_topology",
                        "target_name": "FixtureRollback", "element_domain": domain, "limit": 32})
                    rollback_after[domain] = topology_result(payload)
                write_json(root / "topology_rollback_after.json", rollback_after)
                for domain in rollback_after:
                    assert rollback_after[domain] == before["FixtureRollback"][domain]
                identity = json.loads((root / "service_identity.json").read_text(encoding="utf-8"))
                assert identity["source_hash_match"]
                return {"status": "PASS", "service_version": init.serverInfo.version,
                        "source_tree_sha256": identity["source_tree_sha256"],
                        "calls": len(calls), "expected_successes": sum(c["expected_success"] for c in calls),
                        "expected_errors": sum(not c["expected_success"] for c in calls)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default=r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
    args = parser.parse_args()
    blender = Path(args.blender)
    if not blender.is_file():
        raise SystemExit(f"BLOCKED: Blender executable not found: {blender}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="umcp-modeling-e2e-01-"))
    identity = source_identity(PROJECT)
    identity["project_version"] = "0.1.49"
    identity["test_host_policy"] = str((PROJECT / "tests/policy_candidates/modeling_mesh_policy.py").resolve())
    identity["test_host_policy_sha256"] = hashlib.sha256((PROJECT / "tests/policy_candidates/modeling_mesh_policy.py").read_bytes()).hexdigest()
    identity["harness"] = str(Path(__file__).resolve())
    identity["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    identity["disposable_root"] = str(root.resolve())
    write_json(EVIDENCE / "source_identity.json", identity)
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    assert port != 9877
    env = dict(os.environ, PYTHONPATH=str(PROJECT), PYTHONDONTWRITEBYTECODE="1",
               UMCP_LOCAL_TEST_AUTOAPPROVE="1", UMCP_LOCAL_TEST_ROOT=str(root),
               UMCP_EXPECTED_SOURCE_SHA256=identity["source_tree_sha256"], UMCP_BRIDGE_PORT=str(port))
    for key in ("CONFIG", "SCRIPTS", "EXTENSIONS", "DATAFILES", "RESOURCES"):
        directory = root / key.lower()
        directory.mkdir()
        env["BLENDER_USER_" + key] = str(directory)
    bootstrap = root / "bootstrap.py"
    bootstrap.write_text(
        "import runpy,sys\n"
        "sys.path.insert(0," + repr(str(PROJECT)) + ")\n"
        "sys.argv=" + repr([str(Path(__file__).resolve()), "--fixture", "--root", str(root), "--port", str(port),
                            "--source-hash", identity["source_tree_sha256"]]) + "\n"
        "runpy.run_path(" + repr(str(Path(__file__).resolve())) + ",run_name='__main__')\n",
        encoding="utf-8")
    # The fixture mode is dispatched before any MCP client code runs.
    with (root / "blender.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(blender), "--background", "--factory-startup", "--disable-autoexec",
            "--python-exit-code", "1", "--python", str(bootstrap)], cwd=str(PROJECT), env=env,
            stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 45
            while not (root / "blender_identity.json").exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Disposable Blender did not publish identity; inspect blender.log")
                time.sleep(0.1)
            ready = json.loads((root / "blender_identity.json").read_text(encoding="utf-8"))
            assert ready["source_tree_sha256"] == identity["source_tree_sha256"] and ready["port"] == port
            result = asyncio.run(run_client(root, port, identity))
        finally:
            (root / "stop").touch()
            process.wait(timeout=20)
    assert process.returncode == 0, (process.returncode, (root / "blender.log").read_text(errors="replace"))
    native = json.loads((root / "native_evidence.json").read_text(encoding="utf-8"))
    assert native["factory_objects_unchanged"] and native["fixture_inventory_unchanged"] and native["all_tokens_consumed"]
    result.update({"blender": ready["version"], "blender_pid": ready["pid"], "isolated_port": port,
        "blender_executable": ready["executable"], "source_tree_sha256": identity["source_tree_sha256"],
        "native_verified": True, "approval_required": ready["require_approval"],
        "missing_token_rejected": bool(ready["missing_token_rejected"]), "disposable_root": str(root)})
    write_json(root / "result.json", result)
    write_json(EVIDENCE / "result.json", result)
    report = f"""# MODELING-E2E-01 — isolated edit_mesh mutation and rollback

Result: **PASS**

- MCP service version: `{result['service_version']}`
- Source/build identity: `{result['source_tree_sha256']}` (service and Blender source-tree hashes matched)
- Service Python/source evidence: `service_identity.json`
- Blender: `{result['blender']}`, PID `{result['blender_pid']}`; fixture exited 0
- Isolated loopback port: `{result['isolated_port']}` (production 9877 was not used)
- MCP calls: {result['calls']} total; {result['expected_successes']} expected successes and {result['expected_errors']} expected errors
- Approval gate: enabled; missing-token call rejected without mutation; two scoped disposable-host decisions issued normal registry tokens; both consumed; both exact token replays rejected
- Successful edit: vertex 0 moved +0.25 on Z; indexed readback showed the expected coordinate change, unchanged edges/faces/counts, and changed snapshot/state IDs
- Injected failure: raised after staged data was assigned; rollback restored original mesh data pointer, vertex/edge/face data, topology fingerprints, and mesh/object inventory
- Preservation: original factory objects unchanged; fixture inventory unchanged across operations. No production scene, Dragon asset, service, or Blender session was contacted.
- Evidence directory: `{root}`

Raw MCP calls/responses: `mcp_calls.json`; indexed snapshots: `topology_before.json`, `topology_success_after.json`, `topology_rollback_after.json`; native pointer/inventory/rollback evidence: `mutation_evidence.json`, `native_evidence.json`; source identity/catalog: `source_identity.json`, `service_identity.json`, `mcp_catalog.json`, `blender_identity.json`.

The test-host approval policy was the pre-existing scoped candidate at `tests/policy_candidates/modeling_mesh_policy.py`; production authorization code and policy were not changed. The integration used test-only approval resolution inside the isolated background fixture and does not represent Blender UI acceptance.
"""
    (EVIDENCE / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Evidence report: {EVIDENCE / 'REPORT.md'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--source-hash")
    known, remaining = parser.parse_known_args()
    if known.fixture:
        fixture(known.root, known.port, known.source_hash)
    else:
        sys.argv = [sys.argv[0], *remaining]
        main()
