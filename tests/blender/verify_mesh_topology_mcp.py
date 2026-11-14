"""Read-only indexed mesh MCP checks in a disposable factory Blender child."""
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
    bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=True)
    empty = bpy.data.objects.new("TopologyEmpty", bpy.data.meshes.new("TopologyEmptyMesh"))
    bpy.context.scene.collection.objects.link(empty)
    bpy.data.objects.new("TopologyOutside", bpy.data.meshes.new("TopologyOutsideMesh"))
    def state():
        return {"objects": [{"name":o.name,"type":o.type,"selected":o.select_get(),"mode":o.mode,
            "matrix":[list(row) for row in o.matrix_world],
            "vertices":[{"index":v.index,"co":list(v.co),"selected":v.select} for v in o.data.vertices] if o.type=="MESH" else [],
            "edges":[{"index":e.index,"vertices":list(e.vertices)} for e in o.data.edges] if o.type=="MESH" else [],
            "faces":[{"index":p.index,"vertices":list(p.vertices)} for p in o.data.polygons] if o.type=="MESH" else []} for o in bpy.data.objects],
            "scene_objects":[o.name for o in bpy.context.scene.objects],"mode":bpy.context.mode,
            "active":bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
            "filepath":bpy.data.filepath,"approval_required":bpy.context.scene.umcp_require_scene_mutation_approval,
            "materials":[m.name for m in bpy.data.materials]}
    before=state()
    (root/"native_before.json").write_text(json.dumps(before,indent=2))
    queue=MainThreadQueue(bpy);server=BridgeServer(port=port,queue=queue);server.start()
    (root/"ready.json").write_text(json.dumps({"pid":os.getpid(),"port":port,"blender":bpy.app.version_string}))
    deadline=time.monotonic()+90
    try:
        while not (root/"stop").exists() and time.monotonic()<deadline:
            queue.drain_queue();time.sleep(.01)
    finally:
        server.stop();after=state()
        (root/"native_after.json").write_text(json.dumps(after,indent=2))
        (root/"preservation.json").write_text(json.dumps({"unchanged":before==after,
            "approval_requests":len(get_approval_registry()._requests)},indent=2))
        assert before==after and not get_approval_registry()._requests


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp_service.registry.tool_registry import ToolRegistry
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE",None)
    params=StdioServerParameters(command=sys.executable,args=["-B","-m","mcp_service.app","--transport","stdio",
        "--bridge-port",str(port),"--bridge-timeout","5","--approval-mode","blender"],env=env,cwd=str(PROJECT))
    calls=[];native=json.loads((root/"native_before.json").read_text())
    with (root/"mcp.log").open("w",encoding="utf-8") as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                initialized=await session.initialize();catalog=await session.list_tools()
                schema=next(t.inputSchema for t in catalog.tools if t.name=="inspect_scene_data")
                assert schema==next(t.inputSchema for t in ToolRegistry().get_mcp_tools() if t.name=="inspect_scene_data")
                (root/"catalog.json").write_text(catalog.model_dump_json(indent=2))
                async def call(arguments,success=True):
                    response=await session.call_tool("inspect_scene_data",arguments=arguments)
                    calls.append({"arguments":arguments,"response":response.model_dump(mode="json"),"expected_success":success})
                    (root/"calls.json").write_text(json.dumps(calls,indent=2))
                    if response.isError:
                        assert not success,calls[-1];return
                    payload=json.loads(response.content[0].text)
                    assert (payload["status"]=="success")==success,calls[-1]
                    result=payload.get("result")
                    if success and isinstance(result,dict) and "observed_data" in result:
                        raw=result["observed_data"]
                        assert all(result[key]==value for key,value in raw.items())
                        return raw
                    return result
                args={"category":"mesh_topology","target_name":"Cube"}
                counts=await call(args)
                assert set(counts)=={"category","target_name","vertex_count","edge_count","polygon_count","loop_count","has_custom_normals","dimensions"}
                cube=next(o for o in native["objects"] if o["name"]=="Cube")
                fingerprints=[]
                for domain in ("vertices","edges","faces"):
                    expected=[{k:v for k,v in item.items() if k!="selected"} for item in cube[domain]]
                    collected=[]
                    for offset in range(0,len(expected),3):
                        page=await call({**args,"element_domain":domain,"limit":3,"offset":offset,**({"expected_snapshot_id":fingerprints[-1]} if offset else {})})
                        collected.extend(page["elements"]);fingerprints.append(page["snapshot_id"])
                        assert page["total"]==len(expected) and page["returned"]<=3
                    assert collected==expected,(domain,collected,expected)
                    empty=await call({**args,"target_name":"TopologyEmpty","element_domain":domain})
                    assert empty["elements"]==[] and empty["total"]==0
                assert len(set(fingerprints))==1
                one=await call({**args,"element_domain":"vertices","limit":1})
                assert one==await call({**args,"element_domain":"vertices","limit":1})
                beyond=await call({**args,"element_domain":"faces","offset":1000000000,"expected_snapshot_id":fingerprints[0]})
                assert beyond["elements"]==[] and beyond["next_offset"] is None
                for extra in ({"target_name":"Missing"},{"target_name":"Camera"},{"target_name":"TopologyOutside"},
                    {"limit":True},{"limit":1001},{"offset":-1},{"element_domain":"corners"},
                    {"category":"scene_summary"},{"arbitrary_path":"data.objects"}):
                    await call({**args,"element_domain":"vertices",**extra},success=False)
                return {"status":"PASS","service":initialized.serverInfo.model_dump(),"calls":len(calls),
                    "successes":sum(c["expected_success"] for c in calls),"expected_errors":sum(not c["expected_success"] for c in calls),
                    "runtime_schema_parity":True,"independent_coordinates_connectivity":True,"version_incremented":False,"release_built":False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true")
    parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-topology-readback-"));print(root,flush=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE",None)
    for key in ("CONFIG","SCRIPTS","EXTENSIONS","DATAFILES","RESOURCES"):
        folder=root/key.lower();folder.mkdir();env["BLENDER_USER_"+key]=str(folder)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    assert port!=9877
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
    assert preservation["unchanged"] and preservation["approval_requests"]==0
    result.update(runtime=json.loads((root/"ready.json").read_text()),preservation=preservation)
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=="__main__":main()
