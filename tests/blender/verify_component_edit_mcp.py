"""Approved finite edit_mesh test-host subset; production policy is unchanged."""
import argparse,asyncio,hashlib,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
QUAD=([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[(0,1),(1,2),(2,3),(3,0)],[(0,1,2,3)])
TRI=([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(1,2),(2,0)],[(0,1,2)])
LINE=([(0,0,0),(1,0,0),(2,0,0)],[(0,1),(1,2)],[])
CUBE=([(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)],[],[(0,2,6,4),(1,5,7,3),(0,4,5,1),(2,3,7,6),(0,1,3,2),(4,6,7,5)])
CASES={
 "DegenerateEdge":(([],[],[]),[{"action":"create","points":[[0,0,0],[0,0,0]],"edge_pairs":[[0,1]]}]),
 "NonmanifoldVertex":(([(0,0,0),(1,0,0),(0,1,0),(0,0,1),(-1,0,0),(0,-1,0),(0,0,-1)],[],[(0,2,1),(0,1,3),(0,3,2),(1,2,3),(0,4,5),(0,6,4),(0,5,6),(4,6,5)]),[{"action":"shade_faces","faces":list(range(8)),"smooth":True}]),
 "Create":(([],[],[]),[{"action":"create","points":QUAD[0],"edge_pairs":QUAD[1],"face_cycles":QUAD[2]}]),
 "DeleteVertices":(TRI,[{"action":"delete_vertices","vertices":[0]}]),
 "DeleteEdges":(TRI,[{"action":"delete_edges","edges":[0]}]),
 "DeleteFaces":(TRI,[{"action":"delete_faces","faces":[0]}]),
 "Extrude":(QUAD,[{"action":"extrude","faces":[0],"delta":[0,0,.5]}]),
 "Inset":(QUAD,[{"action":"inset","faces":[0],"thickness":.1}]),
 "Bevel":(CUBE,[{"action":"bevel","edges":[0],"width":.05,"segments":2}]),
 "Subdivide":(QUAD,[{"action":"subdivide","edges":[0,1,2,3],"cuts":1}]),
 "LoopCut":(QUAD,[{"action":"loop_cut","edges":[0,2],"cuts":1}]),
 "Bridge":((QUAD[0]+[(x,y,1) for x,y,z in QUAD[0]],QUAD[1]+[(a+4,b+4) for a,b in QUAD[1]],[]),[{"action":"bridge","edges":list(range(8))}]),
 "Merge":(LINE,[{"action":"merge","vertices":[0,1]}]),
 "DissolveVertices":(LINE,[{"action":"dissolve_vertices","vertices":[1]}]),
 "DissolveEdges":(([(0,0,0),(1,0,0),(2,0,0),(0,1,0),(1,1,0),(2,1,0)],[(0,1),(1,2),(2,5),(5,4),(4,3),(3,0),(1,4)],[(0,1,4,3),(1,2,5,4)]),[{"action":"dissolve_edges","edges":[6]}]),
 "Fill":((QUAD[0],QUAD[1],[]),[{"action":"fill","edges":[0,1,2,3]}]),
 "Normals":((CUBE[0],[],[tuple(reversed(CUBE[2][0]))]+CUBE[2][1:]),[{"action":"recalculate_normals","faces":list(range(6))}]),
 "Shading":(QUAD,[{"action":"shade_faces","faces":[0],"smooth":True}]),
 "WorldMove":(LINE,[{"action":"move_vertices","vertices":[0],"delta":[0,1,0],"space":"WORLD"}]),
 "Proportional":(LINE,[{"action":"move_vertices","vertices":[0],"delta":[0,1,0],"proportional_radius":1.5}]),
 "Snap":(([(.2,0,0),(1.2,0,0),(2.2,0,0)],LINE[1],[]),[{"action":"snap_grid","vertices":[0,1,2],"grid_size":1}]),
 "Symmetry":(TRI,[{"action":"symmetrize","direction":"POSITIVE_X"}]),
 "Batch":(TRI,[{"action":"move_vertices","vertices":[0],"delta":[0,0,.2]},{"action":"shade_faces","faces":[0],"smooth":True}]),
 "Rollback":(QUAD,[{"action":"move_vertices","vertices":[0],"delta":[0,0,.2]},{"action":"create","face_cycles":[[999,0,1]]}]),
 "DeletedReference":(TRI,[{"action":"delete_vertices","vertices":[0]},{"action":"move_vertices","vertices":[0],"delta":[0,0,1]}]),
 "Fault":(QUAD,[{"action":"inset","faces":[0],"thickness":.1}]),
 "Stale":(QUAD,[{"action":"move_vertices","vertices":[0],"delta":[0,0,1]}]),
}
ERRORS={"DegenerateEdge","Rollback","DeletedReference","Fault","Stale"}


def fixture(root,port):
    import bpy
    from tests.policy_candidates.modeling_mesh_policy import authorizes
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge import mesh_atomic
    bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval=bpy.props.BoolProperty(default=True)
    original=list(bpy.data.objects)
    def data(obj):
        result={"name":obj.name,"matrix":[list(row) for row in obj.matrix_world],"mode":obj.mode,"selected":obj.select_get()}
        if obj.type=="MESH":result.update(mesh=obj.data.name,pointer=obj.data.as_pointer(),vertices=[list(v.co) for v in obj.data.vertices],
            edges=[list(e.vertices) for e in obj.data.edges],faces=[list(p.vertices) for p in obj.data.polygons],
            normals=[list(p.normal) for p in obj.data.polygons],centers=[list(p.center) for p in obj.data.polygons],smooth=[p.use_smooth for p in obj.data.polygons])
        return result
    def protected():return {o.name:data(o) for o in original}
    owned={}
    for case,(geometry,ops) in CASES.items():
        name="Fixture"+case;mesh=bpy.data.meshes.new(name+"Mesh");mesh.from_pydata(*geometry);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj)
        if case=="WorldMove":obj.scale=(2,2,2)
        owned[name]=(obj,mesh)
    bpy.context.view_layer.update();before=protected();events=[]
    initial_meshes=set(bpy.data.meshes.keys())
    queue=MainThreadQueue(bpy);real=queue._handlers["edit_mesh"]
    def tracked(bpy_module=None,params=None):
        name=params["name"];obj=bpy.data.objects[name];prior=data(obj);prior_meshes=set(bpy.data.meshes.keys())
        verify=mesh_atomic.verify_commit
        if name=="FixtureFault":
            def fail(*args):raise RuntimeError("HOST FORCED COMMIT CHECK FAILURE")
            mesh_atomic.verify_commit=fail
        try:return real(bpy_module=bpy_module,params=params)
        finally:
            mesh_atomic.verify_commit=verify
            events.append({"name":name,"before":prior,"after":data(obj),"meshes_unchanged":prior_meshes==set(bpy.data.meshes.keys())})
            (root/"events.json").write_text(json.dumps(events,indent=2))
    queue.register_handler("edit_mesh",tracked);server=BridgeServer(port=port,queue=queue);server.start()
    (root/"ready.json").write_text(json.dumps({"pid":os.getpid(),"port":port,"blender":bpy.app.version_string}))
    deadline=time.monotonic()+180;approved=set()
    try:
        while not (root/"stop").exists() and time.monotonic()<deadline:
            queue.drain_queue()
            for request in list(get_approval_registry()._requests.values()):
                if request.status!="pending" or request.request_id in approved:continue
                name=request.params.get("name","");case=name.removeprefix("Fixture")
                assert request.tool_name=="edit_mesh" and case in CASES and request.params["operations"]==json.loads(json.dumps(CASES[case][1]))
                assert authorizes(bpy,request.tool_name,request.params,owned),"Approved candidate guards rejected fixture"
                ok,_=get_approval_registry().resolve_request(request.request_id,"approved",reason="USER-AUTHORIZED ISOLATED edit_mesh TEST SUBSET",approve_task_group=False)
                assert ok;approved.add(request.request_id)
            time.sleep(.01)
    finally:
        server.stop();after=protected()
        registry=get_approval_registry()
        result={"factory_preserved":before==after,"mesh_inventory_preserved":initial_meshes==set(bpy.data.meshes.keys()),
            "before":before,"after":after,"final":{k:data(v[0]) for k,v in owned.items()},"events":events,
            "requests":[registry.inspect_request_status(i) for i in registry._requests]}
        (root/"native.json").write_text(json.dumps(result,indent=2))
        assert before==after and result["mesh_inventory_preserved"]


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE="1");env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE",None)
    params=StdioServerParameters(command=sys.executable,args=["-B","-m","mcp_service.app","--transport","stdio","--bridge-port",str(port),"--bridge-timeout","5","--approval-mode","blender"],env=env,cwd=str(PROJECT))
    calls=[]
    with (root/"mcp.log").open("w",encoding="utf-8") as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                init=await session.initialize();catalog=await session.list_tools();assert any(t.name=="edit_mesh" for t in catalog.tools)
                (root/"catalog.json").write_text(catalog.model_dump_json(indent=2))
                async def call(tool,args,success=True):
                    response=await session.call_tool(tool,arguments=args)
                    calls.append({"tool":tool,"args":args,"response":response.model_dump(mode="json"),"expected_success":success})
                    (root/"calls.json").write_text(json.dumps(calls,indent=2))
                    assert not response.isError,calls[-1]
                    payload=json.loads(response.content[0].text);assert (payload["status"]=="success")==success,calls[-1]
                    result=payload.get("result",{});return result.get("observed_data",result)
                for case,(geo,ops) in CASES.items():
                    name="Fixture"+case;query={"category":"mesh_topology","target_name":name,"element_domain":"vertices"}
                    before=await call("inspect_scene_data",query)
                    args={"name":name,"expected_snapshot_id":("sha256:"+"a"*64) if case=="Stale" else before["snapshot_id"],"operations":json.loads(json.dumps(ops))}
                    receipt=await call("edit_mesh",args,success=case not in ERRORS)
                    if case=="NonmanifoldVertex":
                        validity=receipt["geometry_validity"]
                        assert validity["nonmanifold_vertices"]==1 and validity["nonmanifold_edges"]==0 and not validity["is_closed_manifold"]
                    after=await call("inspect_scene_data",query)
                    if case in ERRORS:assert after==before,case
                return {"status":"PASS","calls":len(calls),"successes":sum(c["expected_success"] for c in calls),"expected_errors":sum(not c["expected_success"] for c in calls),"service":init.serverInfo.model_dump()}


def verify_native(native):
    states=native["final"]
    def obj(case):return states["Fixture"+case]
    def counts(case):
        o=obj(case);return len(o["vertices"]),len(o["edges"]),len(o["faces"])
    assert counts("Create")== (4,4,1)
    assert counts("DeleteVertices")[0]==2 and counts("DeleteVertices")[2]==0
    assert counts("DeleteEdges")[1]==2 and counts("DeleteEdges")[2]==0
    assert counts("DeleteFaces")== (3,3,0)
    assert max(v[2] for v in obj("Extrude")["vertices"])==.5
    assert any(abs(v[0]-.1)<1e-6 and abs(v[1]-.1)<1e-6 for v in obj("Inset")["vertices"])
    assert counts("Bevel")[0]>8 and counts("Bevel")[2]>6
    assert counts("Subdivide")== (9,12,4)
    assert counts("LoopCut")== (6,7,2)
    assert counts("Bridge")== (8,12,4)
    assert counts("Merge")[0]==2 and any(abs(v[0]-.5)<1e-6 for v in obj("Merge")["vertices"])
    assert counts("DissolveVertices")== (2,1,0)
    assert counts("DissolveEdges")== (6,6,1)
    assert counts("Fill")== (4,4,1)
    assert all(sum(a*b for a,b in zip(n,c))>0 for n,c in zip(obj("Normals")["normals"],obj("Normals")["centers"]))
    assert obj("Shading")["smooth"]==[True]
    assert abs(obj("WorldMove")["vertices"][0][1]-.5)<1e-6
    assert abs(obj("Proportional")["vertices"][0][1]-1)<1e-6 and abs(obj("Proportional")["vertices"][1][1]-1/3)<1e-6 and obj("Proportional")["vertices"][2][1]==0
    assert [v[0] for v in obj("Snap")["vertices"]]==[0,1,2]
    symmetry=obj("Symmetry")["vertices"]
    assert any(v[0]<0 for v in symmetry) and any(v[0]>0 for v in symmetry)
    assert all(any(sum((b[i]-([-a[0],a[1],a[2]])[i])**2 for i in range(3))<1e-10 for b in symmetry) for a in symmetry)
    assert obj("Batch")["smooth"]==[True] and abs(obj("Batch")["vertices"][0][2]-.2)<1e-6
    assert len(native["events"])==len(CASES)
    for event in native["events"]:
        assert event["meshes_unchanged"],event["name"]
        if event["name"].removeprefix("Fixture") in ERRORS:assert event["before"]==event["after"],event["name"]
    assert native["factory_preserved"] and native["mesh_inventory_preserved"]
    assert len(native["requests"])==len(CASES) and all(r["token_consumed"] for r in native["requests"])


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true");parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-component-edit-"));print(root,flush=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",UMCP_LOCAL_TEST_AUTOAPPROVE="1",UMCP_LOCAL_TEST_ROOT=str(root))
    for key in ("CONFIG","SCRIPTS","EXTENSIONS","DATAFILES","RESOURCES"):
        folder=root/key.lower();folder.mkdir();env["BLENDER_USER_"+key]=str(folder)
    with socket.socket() as reserve:reserve.bind(("127.0.0.1",0));port=reserve.getsockname()[1]
    assert port!=9877;env["UMCP_BRIDGE_PORT"]=str(port)
    bootstrap=root/"bootstrap.py";bootstrap.write_text("import runpy,sys\nsys.argv="+repr([str(Path(__file__).resolve()),"--fixture","--root",str(root),"--port",str(port)])+"\nrunpy.run_path("+repr(str(Path(__file__).resolve()))+",run_name='__main__')\n")
    with (root/"blender.log").open("w",encoding="utf-8") as log:
        process=subprocess.Popen([r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe","--background","--factory-startup","--disable-autoexec","--python-exit-code","1","--python",str(bootstrap)],env=env,cwd=str(PROJECT),stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+40
            while not (root/"ready.json").exists():assert process.poll() is None and time.monotonic()<deadline;time.sleep(.1)
            result=asyncio.run(client(root,port))
        finally:(root/"stop").touch();process.wait(timeout=15)
    assert process.returncode==0
    native=json.loads((root/"native.json").read_text());verify_native(native)
    result.update(runtime=json.loads((root/"ready.json").read_text()),native_verified=True,normal_tokens_consumed=len(CASES))
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=="__main__":main()
