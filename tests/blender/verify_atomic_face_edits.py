"""Atomic approved face edits, snapshot consistency and forced rollback in a factory child."""
import argparse
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

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))


def fixture(root, port):
    import bpy
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    assert bpy.app.background and bpy.data.filepath == "" and port != 9877
    bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=True)
    original_objects=list(bpy.data.objects)
    mesh=bpy.data.meshes.new("AtomicOwnedMesh")
    mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[],[(0,1,2,3)])
    owned=bpy.data.objects.new("AtomicOwned",mesh);bpy.context.scene.collection.objects.link(owned)
    mod=owned.modifiers.new(name="EvaluatedFixture",type="SUBSURF");mod.levels=1
    empty = bpy.data.objects.new("TopologyEmpty", bpy.data.meshes.new("TopologyEmptyMesh"))
    bpy.context.scene.collection.objects.link(empty)
    bpy.data.objects.new("TopologyOutside", bpy.data.meshes.new("TopologyOutsideMesh"))
    def state():
        return {"objects": [{"name":o.name,"type":o.type,"selected":o.select_get(),"mode":o.mode,
            "matrix":[list(row) for row in o.matrix_world],
            "vertices":[{"index":v.index,"co":list(v.co),"selected":v.select} for v in o.data.vertices] if o.type=="MESH" else [],
            "edges":[{"index":e.index,"vertices":list(e.vertices)} for e in o.data.edges] if o.type=="MESH" else [],
            "faces":[{"index":p.index,"vertices":list(p.vertices)} for p in o.data.polygons] if o.type=="MESH" else []} for o in original_objects],
            "scene_objects":[o.name for o in original_objects],"mode":bpy.context.mode,
            "active":bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
            "filepath":bpy.data.filepath,"approval_required":bpy.context.scene.umcp_require_scene_mutation_approval,
            "materials":[m.name for m in bpy.data.materials]}
    before=state()
    (root/"native_before.json").write_text(json.dumps(before,indent=2))
    queue=MainThreadQueue(bpy)
    execution_states=[]
    def owned_state():
        return {"mesh":owned.data.name,"meshes":list(bpy.data.meshes.keys()),"mode":bpy.context.mode,
            "active":bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
            "vertices":[list(v.co) for v in owned.data.vertices],"faces":[list(p.vertices) for p in owned.data.polygons],
            "edges":[list(e.vertices) for e in owned.data.edges]}
    for name in ("extrude_mesh","extrude_faces","inset_mesh","inset_faces"):
        handler=queue._handlers[name]
        def tracked(bpy_module=None,params=None,actual=handler,tool=name):
            previous=owned_state()
            try:return actual(bpy_module=bpy_module,params=params)
            finally:execution_states.append({"tool":tool,"before":previous,"after":owned_state()})
        queue.register_handler(name,tracked)
    server=BridgeServer(port=port,queue=queue);server.start()
    (root/"ready.json").write_text(json.dumps({"pid":os.getpid(),"port":port,"blender":bpy.app.version_string}))
    deadline=time.monotonic()+90
    try:
        while not (root/"stop").exists() and time.monotonic()<deadline:
            if (root/"arm_fault").exists() and not (root/"fault_armed").exists():
                from blender_addon.universal_mcp.bridge import mesh_edit
                original_verify=mesh_edit._verify_commit
                def fail_once(*args):
                    mesh_edit._verify_commit=original_verify
                    raise RuntimeError("HOST TEST INJECTED COMMIT VERIFICATION FAILURE")
                mesh_edit._verify_commit=fail_once
                (root/"fault_armed").touch()
            queue.drain_queue();time.sleep(.01)
    finally:
        server.stop();after=state()
        (root/"execution_states.json").write_text(json.dumps(execution_states,indent=2))
        (root/"native_after.json").write_text(json.dumps(after,indent=2))
        (root/"preservation.json").write_text(json.dumps({"unchanged":before==after,
            "approval_requests":len(get_approval_registry()._requests),
            "tokens_consumed":sum(r.executed for r in get_approval_registry()._requests.values()),
            "owned_geometry":{"vertices":[list(v.co) for v in owned.data.vertices],
                "faces":[list(p.vertices) for p in owned.data.polygons],"mesh":owned.data.name}},indent=2))
        assert before==after and all(r.executed for r in get_approval_registry()._requests.values())


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE",None)
    params=StdioServerParameters(command=sys.executable,args=["-B","-m","mcp_service.app","--transport","stdio",
        "--bridge-port",str(port),"--bridge-timeout","5","--approval-mode","blender"],env=env,cwd=str(PROJECT))
    calls=[]
    with (root/"mcp.log").open("w",encoding="utf-8") as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                initialized=await session.initialize()
                async def call(tool,args,success=True):
                    response=await session.call_tool(tool,arguments=args)
                    calls.append({"tool":tool,"arguments":args,"response":response.model_dump(mode="json"),"expected_success":success})
                    (root/"calls.json").write_text(json.dumps(calls,indent=2))
                    if response.isError:
                        assert not success,calls[-1];return
                    payload=json.loads(response.content[0].text)
                    assert (payload["status"]=="success")==success,calls[-1]
                    result=payload.get("result")
                    if isinstance(result,dict):return result.get("observed_data",result)
                    return payload
                async def inspect(**extra):
                    return await call("inspect_scene_data",{"category":"mesh_topology","target_name":"AtomicOwned","element_domain":"vertices",**extra})
                original=await inspect()
                evaluated=await inspect(mesh_source="evaluated")
                assert evaluated["topology_source"]=="EVALUATED_MESH" and evaluated["snapshot_id"]!=original["snapshot_id"]
                assert evaluated["vertex_count"]==evaluated["total"] and evaluated["vertex_count"]>original["vertex_count"]
                await call("extrude_mesh",{"name":"AtomicOwned","distance":.5,"direction":[0,0,1],"faces":[0],"expected_snapshot_id":original["snapshot_id"]})
                first=await inspect()
                assert first["snapshot_id"]!=original["snapshot_id"] and first["vertex_count"]>original["vertex_count"]
                assert abs(max(v["co"][2] for v in first["elements"])-.5)<1e-6
                await call("inspect_scene_data",{"category":"mesh_topology","target_name":"AtomicOwned","element_domain":"faces","expected_snapshot_id":original["snapshot_id"]},success=False)
                await call("extrude_mesh",{"name":"AtomicOwned","distance":.5,"direction":[0,0,1],"faces":[0],"expected_snapshot_id":original["snapshot_id"]},success=False)
                assert (await inspect())["snapshot_id"]==first["snapshot_id"]
                await call("inset_faces",{"name":"AtomicOwned","thickness":.1,"faces":[0],"expected_snapshot_id":first["snapshot_id"]})
                second=await inspect()
                assert second["snapshot_id"]!=first["snapshot_id"]
                (root/"arm_fault").touch();deadline=time.monotonic()+10
                while not (root/"fault_armed").exists():
                    assert time.monotonic()<deadline;await asyncio.sleep(.02)
                failed=await call("inset_mesh",{"name":"AtomicOwned","thickness":.05,"faces":[0],"expected_snapshot_id":second["snapshot_id"]},success=False)
                assert "ROLLED_BACK_VERIFIED" in json.dumps(calls[-1])
                assert (await inspect())["snapshot_id"]==second["snapshot_id"]
                # Credential-free direct bridge calls cannot use trusted booleans.
                from blender_addon.universal_mcp.bridge.bridge_client import BridgeClient
                bridge=BridgeClient(port=port,timeout=5)
                try:
                    blocked=await asyncio.to_thread(bridge.send_command,"extrude_mesh",{"name":"AtomicOwned","trusted_approval":True,"_trusted_test_override":True})
                    assert blocked["status"]=="error" and "Missing approval credentials" in blocked["message"]
                finally:bridge.close()
                return {"status":"PASS","service":initialized.serverInfo.model_dump(),"calls":len(calls),
                    "successes":sum(c["expected_success"] for c in calls),"expected_errors":sum(not c["expected_success"] for c in calls),
                    "forced_commit_failure_rollback":True,"stale_edit_rejected":True,"stale_page_rejected":True,
                    "evaluated_scope_distinct":True,"direct_boolean_bypass_rejected":True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true")
    parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-atomic-face-"));print(root,flush=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    env.update(UMCP_LOCAL_TEST_AUTOAPPROVE="1",UMCP_LOCAL_TEST_ROOT=str(root))
    for key in ("CONFIG","SCRIPTS","EXTENSIONS","DATAFILES","RESOURCES"):
        folder=root/key.lower();folder.mkdir();env["BLENDER_USER_"+key]=str(folder)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    assert port!=9877
    env["UMCP_BRIDGE_PORT"]=str(port)
    bootstrap=root/"bootstrap.py"
    bootstrap.write_text("import runpy,sys\nsys.argv="+repr([str(Path(__file__).resolve()),"--fixture","--root",str(root),"--port",str(port)])+
        "\nrunpy.run_path("+repr(str(Path(__file__).resolve()))+",run_name='__main__')\n")
    with (root/"blender.log").open("w",encoding="utf-8") as log:
        process=subprocess.Popen([r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe","--background","--factory-startup",
            "--disable-autoexec","--python-exit-code","1","--python",str(bootstrap)],env=env,cwd=str(PROJECT),stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+40
            while not (root/"ready.json").exists():
                assert process.poll() is None and time.monotonic()<deadline,"Fixture startup failed; see blender.log"
                time.sleep(.1)
            result=asyncio.run(client(root,port))
        finally:
            (root/"stop").touch();process.wait(timeout=15)
    assert process.returncode==0
    preservation=json.loads((root/"preservation.json").read_text())
    assert preservation["unchanged"] and preservation["approval_requests"]==4 and preservation["tokens_consumed"]==4
    states=json.loads((root/"execution_states.json").read_text())
    assert len(states)==5
    assert all(states[i]["before"]==states[i]["after"] for i in (1,3,4))
    assert states[0]["before"]!=states[0]["after"] and states[2]["before"]!=states[2]["after"]
    result["independent_native_failure_restore"]=True
    result.update(runtime=json.loads((root/"ready.json").read_text()),preservation=preservation)
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=="__main__":main()
