"""Authorized finite curve/text MCP E2E in a disposable Blender child."""
import argparse,asyncio,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
K=.5522847498307936
CIRCLE=[{'co':[1,0,0],'handle_left':[1,-K,0],'handle_right':[1,K,0]}, {'co':[0,1,0],'handle_left':[K,1,0],'handle_right':[-K,1,0]}, {'co':[-1,0,0],'handle_left':[-1,K,0],'handle_right':[-1,-K,0]}, {'co':[0,-1,0],'handle_left':[-K,-1,0],'handle_right':[K,-1,0]}]
for p in CIRCLE:p.update(handle_type_left='FREE',handle_type_right='FREE')
SPECS={
'Bezier':{'kind':'CURVE','splines':[{'type':'BEZIER','points':[{'co':[0,0,0]},{'co':[1,1,0]},{'co':[2,0,0]}]}]},
'Poly':{'kind':'CURVE','splines':[{'type':'POLY','points':[{'co':[0,0,0]},{'co':[1,1,0]},{'co':[2,0,0]}]}]},
'Nurbs':{'kind':'CURVE','splines':[{'type':'NURBS','order':3,'endpoint':True,'points':[{'co':[0,0,0]},{'co':[1,1,0],'weight':.7},{'co':[2,1,0]},{'co':[2,0,0]}]}]},
'Circle':{'kind':'CURVE','splines':[{'type':'BEZIER','cyclic':True,'points':CIRCLE}]},
'Text':{'kind':'TEXT'},'NurbsCircle':{'kind':'CURVE','splines':[__import__('blender_addon.universal_mcp.bridge.curve_contract',fromlist=['circle_spline']).circle_spline(True)]}}
PHASES=['create','update','fault_update','copy','fault_copy','stale']
def phases(case):return PHASES+(['planar_rejection'] if case!='Text' else [])


def plan(case,phase,snapshot):
    action='copy_to_mesh' if phase in ('copy','fault_copy') else 'create' if phase=='create' else 'update'
    args={'name':'Fixture'+case,'action':action}
    if action=='copy_to_mesh':args['output_name']='Fixture'+case+('Mesh' if phase=='copy' else 'FaultMesh')
    else:
        args.update(json.loads(json.dumps(SPECS[case])))
        args['settings']={'extrude':.01 if phase=='create' else .02,'bevel_depth':.01,'bevel_resolution':1,'resolution_u':6}
        if case!='Text':args['settings']['dimensions']='2D' if phase=='planar_rejection' else '3D'
        if case=='Text':args['settings'].update(body='Fixture' if phase=='create' else 'Updated',size=1,align_x='CENTER')
        if phase!='create' and case!='Text':args['splines'][0]['points'][0]['co'][2]=.2
    if action!='create':args['expected_snapshot_id']='sha256:'+'a'*64 if phase=='stale' else snapshot
    return args


def fixture(root,port):
    import bpy
    from unittest.mock import patch
    from tests.policy_candidates.modeling_curve_policy import authorizes
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge import curve_tools
    from blender_addon.universal_mcp.bridge.shader_values import shader_values_match
    assert bpy.app.background and not bpy.data.filepath and port!=9877
    bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval=bpy.props.BoolProperty(default=True)
    original=list(bpy.data.objects)
    def protected():
        return {o.name:{'data':o.data.as_pointer() if o.data else None,'matrix':[list(row) for row in o.matrix_world],'selected':o.select_get(),
                'vertices':[list(v.co) for v in o.data.vertices] if o.type=='MESH' else None} for o in original}
    def inventory():return [sorted(collection.keys()) for collection in (bpy.data.objects,bpy.data.curves,bpy.data.meshes)]
    before=protected();initial=inventory();owned={name:(None,None) for case in SPECS for name in ('Fixture'+case,'Fixture'+case+'Mesh','Fixture'+case+'FaultMesh')}
    indices={case:0 for case in SPECS};events=[];queue=MainThreadQueue(bpy);real=queue._handlers['configure_curve_geometry']
    def tracked(bpy_module=None,params=None):
        case=params['name'].removeprefix('Fixture');phase=phases(case)[indices[case]];prior=None if phase=='create' else curve_tools.inspect(bpy,params['name']);prior_inv=inventory()
        if phase in ('fault_update','fault_copy','stale','planar_rejection'):
            def fail(*args):raise RuntimeError('HOST_FORCED_CURVE_COMMIT_FAILURE')
            try:
                with patch.object(curve_tools,'_verify',side_effect=fail):real(bpy_module=bpy_module,params=params)
            except Exception as error:
                assert ('STALE_CURVE_GEOMETRY' if phase=='stale' else 'ROLLED_BACK_VERIFIED') in str(error),str(error)
                if phase=='planar_rejection':assert 'readback mismatch' in str(error),str(error)
                assert curve_tools.inspect(bpy,params['name'])==prior and inventory()==prior_inv
                indices[case]+=1;events.append({'case':case,'phase':phase,'restored':True,'expected_error':str(error)})
                (root/'events.json').write_text(json.dumps(events,indent=2));raise
            raise AssertionError('Failure falsely succeeded')
        result=real(bpy_module=bpy_module,params=params)
        obj=bpy.data.objects[result['name']];observed=curve_tools.inspect(bpy,obj.name)
        assert result['snapshot_id']==observed['snapshot_id']
        if phase=='copy':
            assert obj.type=='MESH' and len(obj.data.vertices)>0
            assert curve_tools.inspect(bpy,params['name'])==prior
            assert obj.matrix_world==bpy.data.objects[params['name']].matrix_world
            assert observed['geometry']['topology_source']=='BASE_MESH'
            assert prior['evaluated']['topology_source']=='EVALUATED_MESH'
            assert curve_tools._mesh_state(obj.data,obj.name,source='EVALUATED_MESH')==prior['evaluated']
        else:
            assert obj.type==('FONT' if case=='Text' else 'CURVE')
            for key,value in params['settings'].items():assert shader_values_match(getattr(obj.data,key),value),(key,value)
            if case!='Text':
                assert len(obj.data.splines)==len(params['splines'])
                for spec,spline in zip(params['splines'],obj.data.splines):
                    points=spline.bezier_points if spline.type=='BEZIER' else spline.points
                    assert len(points)==len(spec['points'])
                    for values,point in zip(spec['points'],points):assert shader_values_match(point.co[:3],values['co']),(case,phase,list(point.co),values['co'])
                if case=='Circle':assert len(obj.data.splines[0].bezier_points)==4 and obj.data.splines[0].use_cyclic_u
        owned[obj.name]=(obj,obj.data);indices[case]+=1
        events.append({'case':case,'phase':phase,'inspection':observed,'source_preserved':phase!='copy' or curve_tools.inspect(bpy,params['name'])==prior})
        (root/'events.json').write_text(json.dumps(events,indent=2));return result
    queue.register_handler('configure_curve_geometry',tracked);server=BridgeServer(port=port,queue=queue);server.start()
    (root/'ready.json').write_text(json.dumps({'pid':os.getpid(),'port':port,'blender':bpy.app.version_string}))
    approved=set();deadline=time.monotonic()+180
    try:
        while not (root/'stop').exists() and time.monotonic()<deadline:
            queue.drain_queue()
            for request in list(get_approval_registry()._requests.values()):
                if request.status!='pending' or request.request_id in approved:continue
                case=request.params['name'].removeprefix('Fixture');phase=phases(case)[indices[case]]
                snapshot=None if phase=='create' else curve_tools.inspect(bpy,request.params['name'])['snapshot_id']
                planned=dict(plan(case,phase,snapshot),approved=False)
                assert authorizes(bpy,request.tool_name,request.params,owned,planned),(request.params,planned)
                ok,_=get_approval_registry().resolve_request(request.request_id,'approved',reason='USER-AUTHORIZED ISOLATED curve/text TEST SUBSET',approve_task_group=False)
                assert ok;approved.add(request.request_id)
            time.sleep(.01)
    finally:
        server.stop();registry=get_approval_registry()
        native={'protected_preserved':before==protected(),'before':before,'after':protected(),'initial_inventory':initial,'final_inventory':inventory(),
                'indices':indices,'events':events,'requests':[registry.inspect_request_status(i) for i in registry._requests]}
        (root/'native.json').write_text(json.dumps(native,indent=2));assert native['protected_preserved']


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE='1',UMCP_LOCAL_TEST_ROOT=str(root));env.pop('UMCP_LOCAL_TEST_AUTOAPPROVE',None)
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','mcp_service.app','--transport','stdio','--bridge-port',str(port),'--bridge-timeout','5','--approval-mode','blender'],env=env,cwd=str(PROJECT))
    calls=[]
    with (root/'mcp.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                init=await session.initialize();catalog=await session.list_tools();assert any(t.name=='configure_curve_geometry' for t in catalog.tools)
                (root/'catalog.json').write_text(catalog.model_dump_json(indent=2))
                async def call(tool,args,success=True):
                    response=await session.call_tool(tool,arguments=args)
                    calls.append({'tool':tool,'args':args,'response':response.model_dump(mode='json'),'expected_success':success})
                    (root/'calls.json').write_text(json.dumps(calls,indent=2));assert not response.isError,calls[-1]
                    payload=json.loads(response.content[0].text);assert (payload['status']=='success')==success,calls[-1]
                    result=payload.get('result',{});return result.get('observed_data',result)
                for case in SPECS:
                    for phase in phases(case):
                        before=None if phase=='create' else await call('inspect_curve_geometry',{'name':'Fixture'+case})
                        receipt=await call('configure_curve_geometry',plan(case,phase,None if before is None else before['snapshot_id']),success=phase not in ('fault_update','fault_copy','stale','planar_rejection'))
                        target='Fixture'+case+('Mesh' if phase=='copy' else '')
                        after=await call('inspect_curve_geometry',{'name':target})
                        if phase in ('fault_update','fault_copy','stale','planar_rejection'):assert after==before
                        else:assert receipt['snapshot_id']==after['snapshot_id']
                        if phase=='copy':
                            for source,key in (('base','geometry'),('evaluated','evaluated')):
                                indexed=await call('inspect_scene_data',{'category':'mesh_topology','target_name':target,
                                    'element_domain':'vertices','mesh_source':source,'limit':1})
                                curve_mesh=after[key]
                                assert curve_mesh['topology_source']==indexed['topology_source']
                                assert curve_mesh['snapshot_id']==indexed['snapshot_id']
                                assert curve_mesh['state_id']==indexed['state_id']
                            assert after['geometry']['snapshot_id']!=after['evaluated']['snapshot_id']
                return {'status':'PASS','calls':len(calls),'successes':sum(c['expected_success'] for c in calls),'expected_errors':sum(not c['expected_success'] for c in calls),'service':init.serverInfo.model_dump()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true");parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-curve-geometry-"));print(root,flush=True)
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
    native=json.loads((root/"native.json").read_text());assert all(n==len(phases(case)) for case,n in native["indices"].items());assert len(native["requests"])==sum(len(phases(case)) for case in SPECS) and all(r["token_consumed"] for r in native["requests"])
    result.update(runtime=json.loads((root/"ready.json").read_text()),native_verified=True,normal_tokens_consumed=sum(len(phases(case)) for case in SPECS))
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=="__main__":main()
