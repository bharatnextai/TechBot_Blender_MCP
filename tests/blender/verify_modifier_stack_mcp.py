"""Authorized finite modifier-stack MCP E2E in disposable Blender 5.2.2."""
import argparse,asyncio,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
PROPS={
'SUBSURF':({'levels':1,'render_levels':1},{'levels':1}),
'BEVEL':({'width':.02,'segments':2},{'width':.04}),
'SOLIDIFY':({'thickness':.02},{'thickness':.04}),
'BOOLEAN':({'operand_name':'FixtureCutter','operation':'DIFFERENCE','solver':'EXACT'},{'operation':'DIFFERENCE'}),
'MIRROR':({'use_axis':[True,False,False],'use_mirror_merge':False},{'use_clip':True}),
'ARRAY':({'count':2,'use_relative_offset':True,'relative_offset_displace':[1,0,0]},{'relative_offset_displace':[1.5,0,0]})}
PHASES=['add','update','hide','show','reorder','fault_apply','apply','add_again','fault_remove','remove','fault','stale']


def plan(kind,phase,snapshot):
    action={'hide':'visibility','show':'visibility','add_again':'add','fault':'add','stale':'add','fault_apply':'apply','fault_remove':'remove'}.get(phase,phase)
    if phase=='stale':snapshot='sha256:'+'a'*64
    args=dict(name='Fixture'+kind,modifier_name='Owned'+kind,modifier_type=kind,action=action,expected_snapshot_id=snapshot)
    if action in ('add','update'):args['properties']=PROPS[kind][action=='update']
    if phase in ('hide','show'):args.update(show_viewport=phase=='show',show_render=phase=='show')
    if action=='reorder':args['index']=0
    return args


def fixture(root,port):
    import bpy
    from tests.policy_candidates.modeling_modifier_stack_policy import authorizes
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge import modifier_stack
    assert bpy.app.background and bpy.data.filepath=='' and port!=9877
    bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval=bpy.props.BoolProperty(default=True)
    original=list(bpy.data.objects)
    def data(obj):
        return {'name':obj.name,'data':obj.data.name if obj.data else None,'pointer':obj.data.as_pointer() if obj.data else None,
                'matrix':[list(row) for row in obj.matrix_world],'selected':obj.select_get(),'mode':obj.mode,
                'vertices':[list(v.co) for v in obj.data.vertices] if obj.type=='MESH' else None,
                'edges':[list(e.vertices) for e in obj.data.edges] if obj.type=='MESH' else None,
                'faces':[list(p.vertices) for p in obj.data.polygons] if obj.type=='MESH' else None}
    def protected():return {o.name:data(o) for o in original}
    before=protected();owned={};indices={k:0 for k in PROPS};events=[]
    for kind in [*PROPS,'Cutter']:
        mesh=bpy.data.objects['Cube'].data.copy();obj=bpy.data.objects.new('Fixture'+kind,mesh);bpy.context.scene.collection.objects.link(obj)
        if kind=='MIRROR':
            for v in mesh.vertices:v.co.x+=1.2
        if kind=='Cutter':obj.location.x=1
        else:
            mod=obj.modifiers.new('Guard','SUBSURF');mod.levels=mod.render_levels=0
        owned[obj.name]=(obj,obj.data,{m.name:m for m in obj.modifiers})
    bpy.context.view_layer.update();initial_meshes=set(bpy.data.meshes.keys())
    queue=MainThreadQueue(bpy);real=queue._handlers['edit_modifier_stack']
    def tracked(bpy_module=None,params=None):
        obj=bpy.data.objects[params['name']];kind=obj.name.removeprefix('Fixture');phase=PHASES[indices[kind]]
        prior=data(obj);inventory=set(bpy.data.meshes.keys())
        if phase in ('fault','fault_apply','fault_remove','stale'):
            from unittest.mock import patch
            checkpoint=modifier_stack.inspect(bpy,obj.name)
            def injected(*args):raise RuntimeError('HOST_FORCED_MODIFIER_POSTCONDITION_FAILURE')
            try:
                with patch.object(modifier_stack,'_verify',side_effect=injected):
                    real(bpy_module=bpy_module,params=params)
            except Exception as error:
                assert ('ROLLED_BACK_VERIFIED' in str(error)) if phase!='stale' else ('STALE_MODIFIER_STACK' in str(error)),str(error)
                assert data(obj)==prior and checkpoint==modifier_stack.inspect(bpy,obj.name)
                assert inventory==set(bpy.data.meshes.keys())
                owned[obj.name]=(obj,obj.data,{m.name:m for m in obj.modifiers})
                indices[kind]+=1
                events.append({'kind':kind,'phase':phase,'expected_error':str(error),'restored':True,'inventory_preserved':True})
                (root/'events.json').write_text(json.dumps(events,indent=2))
                raise
            raise AssertionError('Forced/stale mutation falsely succeeded')
        result=real(bpy_module=bpy_module,params=params)
        actual=modifier_stack.inspect(bpy,obj.name)
        assert result['snapshot_id']==actual['snapshot_id']
        mod=obj.modifiers.get('Owned'+kind)
        if phase in ('apply','remove'):assert mod is None
        elif phase in ('add','add_again','update'):
            for key,value in plan(kind,phase,params['expected_snapshot_id'])['properties'].items():
                observed=mod.object.name if key=='operand_name' else list(getattr(mod,key)) if isinstance(value,list) else getattr(mod,key)
                assert observed==value or isinstance(value,float) and abs(observed-value)<1e-6,(key,observed,value)
        elif phase in ('hide','show'):assert mod.show_viewport==(phase=='show') and mod.show_render==(phase=='show')
        elif phase=='reorder':assert list(obj.modifiers)[0]==mod
        if phase=='apply':
            vertices=len(obj.data.vertices)
            expected={'SUBSURF':26,'SOLIDIFY':16,'MIRROR':16,'ARRAY':16}
            if kind in expected:assert vertices==expected[kind],(kind,vertices)
            if kind=='BEVEL':assert vertices>8
            if kind=='BOOLEAN':assert max(v.co.x for v in obj.data.vertices)<.0001
            assert prior['vertices']!=data(obj)['vertices']
        assert inventory==set(bpy.data.meshes.keys())
        owned[obj.name]=(obj,obj.data,{m.name:m for m in obj.modifiers})
        indices[kind]+=1
        events.append({'kind':kind,'phase':phase,'before':prior,'after':data(obj),'inspection':actual,'inventory_preserved':True})
        (root/'events.json').write_text(json.dumps(events,indent=2))
        return result
    queue.register_handler('edit_modifier_stack',tracked);server=BridgeServer(port=port,queue=queue);server.start()
    (root/'ready.json').write_text(json.dumps({'pid':os.getpid(),'port':port,'blender':bpy.app.version_string}))
    approved=set();deadline=time.monotonic()+180
    try:
        while not (root/'stop').exists() and time.monotonic()<deadline:
            queue.drain_queue()
            for request in list(get_approval_registry()._requests.values()):
                if request.status!='pending' or request.request_id in approved:continue
                kind=request.params['name'].removeprefix('Fixture');phase=PHASES[indices[kind]]
                current=modifier_stack.inspect(bpy,request.params['name'])
                planned=dict(plan(kind,phase,current['snapshot_id']),approved=False)
                assert authorizes(bpy,request.tool_name,request.params,owned,planned),(request.params,planned)
                ok,_=get_approval_registry().resolve_request(request.request_id,'approved',reason='USER-AUTHORIZED ISOLATED modifier-stack TEST SUBSET',approve_task_group=False)
                assert ok;approved.add(request.request_id)
            time.sleep(.01)
    finally:
        server.stop();registry=get_approval_registry()
        native={'protected_preserved':protected()==before,'inventory_preserved':initial_meshes==set(bpy.data.meshes.keys()),
                'indices':indices,'requests':[registry.inspect_request_status(i) for i in registry._requests],
                'before':before,'after':protected(),'events':events}
        (root/'native.json').write_text(json.dumps(native,indent=2))
        assert native['protected_preserved'] and native['inventory_preserved']


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE='1',UMCP_LOCAL_TEST_ROOT=str(root));env.pop('UMCP_LOCAL_TEST_AUTOAPPROVE',None)
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','mcp_service.app','--transport','stdio','--bridge-port',str(port),'--bridge-timeout','5','--approval-mode','blender'],env=env,cwd=str(PROJECT))
    calls=[]
    with (root/'mcp.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                init=await session.initialize();catalog=await session.list_tools()
                assert any(t.name=='edit_modifier_stack' for t in catalog.tools)
                (root/'catalog.json').write_text(catalog.model_dump_json(indent=2))
                async def call(tool,args,success=True):
                    response=await session.call_tool(tool,arguments=args)
                    calls.append({'tool':tool,'args':args,'response':response.model_dump(mode='json')})
                    (root/'calls.json').write_text(json.dumps(calls,indent=2))
                    assert not response.isError,calls[-1]
                    payload=json.loads(response.content[0].text);assert (payload['status']=='success')==success,calls[-1]
                    result=payload.get('result',{});return result.get('observed_data',result)
                for kind in PROPS:
                    for phase in PHASES:
                        before=await call('inspect_modifier_stack',{'name':'Fixture'+kind})
                        receipt=await call('edit_modifier_stack',plan(kind,phase,before['snapshot_id']),success=phase not in ('fault','fault_apply','fault_remove','stale'))
                        after=await call('inspect_modifier_stack',{'name':'Fixture'+kind})
                        if phase in ('fault','fault_apply','fault_remove','stale'):assert before==after
                        else:assert receipt['snapshot_id']==after['snapshot_id']
                return {'status':'PASS','calls':len(calls),'successes':len(calls)-4*len(PROPS),'expected_errors':4*len(PROPS),'service':init.serverInfo.model_dump()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true");parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-modifier-stack-"));print(root,flush=True)
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
    native=json.loads((root/"native.json").read_text());assert all(n==len(PHASES) for n in native["indices"].values());assert len(native["requests"])==len(PROPS)*len(PHASES) and all(r["token_consumed"] for r in native["requests"])
    result.update(runtime=json.loads((root/"ready.json").read_text()),native_verified=True,normal_tokens_consumed=len(PROPS)*len(PHASES))
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=="__main__":main()
