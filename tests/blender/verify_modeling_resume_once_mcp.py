"""MCP approval/resume + injected post-commit TypeError, exactly-once proof."""
import argparse,asyncio,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))


def fixture(root,port):
    import bpy
    from tests.policy_candidates.modeling_controls_geometry_policy import authorizes
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge.object_controls import inspect
    assert bpy.app.background and not bpy.data.filepath and port!=9877
    bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval=bpy.props.BoolProperty(default=True)
    original=[(o,o.data,[list(row) for row in o.matrix_world],o.select_get()) for o in bpy.data.objects]
    mesh=bpy.data.meshes.new('OnceOwnedData');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
    obj=bpy.data.objects.new('OnceOwned',mesh);bpy.context.scene.collection.objects.link(obj);bpy.context.view_layer.update()
    owned={obj.name:(obj,mesh)};snapshot=inspect(bpy,obj.name)
    planned={'name':obj.name,'action':'transform','space':'WORLD','translation':[1,0,0],'expected_snapshot_id':snapshot['snapshot_id'],'approved':False}
    (root/'plan.json').write_text(json.dumps(planned))
    queue=MainThreadQueue(bpy);real=queue._handlers['configure_modeling_object'];executions=[0]
    def track(**kwargs):
        executions[0]+=1
        return real(**kwargs)
    queue.register_handler('configure_modeling_object',track)
    server=BridgeServer(port=port,queue=queue);server.start();handled=set();deadline=time.monotonic()+60
    (root/'ready.json').write_text(json.dumps({'pid':os.getpid(),'port':port,'blender':bpy.app.version_string}))
    try:
        while not (root/'stop').exists() and time.monotonic()<deadline:
            queue.drain_queue()
            if (root/'authorize.json').exists():
                rid=json.loads((root/'authorize.json').read_text())['request_id']
                if rid not in handled:
                    request=get_approval_registry().get_request(rid)
                    assert request and request.status=='pending'
                    assert authorizes(bpy,request.tool_name,request.params,owned,{},planned)
                    ok,_=get_approval_registry().resolve_request(rid,'approved',reason='USER-AUTHORIZED ISOLATED exactly-once TEST',approve_task_group=False);assert ok
                    handled.add(rid);(root/'authorized.json').write_text(json.dumps({'request_id':rid}))
            time.sleep(.01)
    finally:
        server.stop();registry=get_approval_registry()
        preserved=all(o.data==data and [list(row) for row in o.matrix_world]==matrix and o.select_get()==selected for o,data,matrix,selected in original)
        result={'executions':executions[0],'matrix':[list(row) for row in obj.matrix_world],'protected_preserved':preserved,
                'requests':[registry.inspect_request_status(rid) for rid in registry._requests]}
        (root/'native.json').write_text(json.dumps(result,indent=2));assert preserved


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE='1',UMCP_LOCAL_TEST_ROOT=str(root));env.pop('UMCP_LOCAL_TEST_AUTOAPPROVE',None)
    fault=not (root/'no_fault').exists()
    entry=['-B',str(PROJECT/'tests/blender/once_test_service.py')] if fault else ['-B','-m','mcp_service.app']
    params=StdioServerParameters(command=sys.executable,args=entry+['--transport','stdio','--bridge-port',str(port),'--bridge-timeout','.15','--approval-mode','blender'],env=env,cwd=str(PROJECT))
    calls=[]
    with (root/'mcp.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                init=await session.initialize()
                async def call(tool,args,success=True):
                    response=await session.call_tool(tool,arguments=args);payload=json.loads(response.content[0].text)
                    calls.append({'tool':tool,'args':args,'response':response.model_dump(mode='json'),'expected_success':success})
                    (root/'calls.json').write_text(json.dumps(calls,indent=2))
                    assert not response.isError and (payload['status']=='success')==success,calls[-1]
                    assert 'approval_token' not in json.dumps(payload),payload
                    return payload
                plan=json.loads((root/'plan.json').read_text());plan.pop('approved')
                waiting=await call('configure_modeling_object',plan,False);pending=waiting['result']['pending_approval']
                status={'task_id':pending['task_id'],'session_id':pending['session_id']}
                before=await call('get_task_status',status);assert before['result']['status']=='awaiting_approval'
                resolution={**status,'decision':'approved','nonce':pending['nonce'],'param_hash':pending['param_hash']}
                await call('resolve_pending_approval',resolution,False)
                (root/'authorize.json').write_text(json.dumps({'request_id':pending['approval_request_id']}))
                deadline=time.monotonic()+5
                while not (root/'authorized.json').exists():assert time.monotonic()<deadline;await asyncio.sleep(.02)
                resumed=await call('resolve_pending_approval',resolution,success=not fault)
                if fault:assert 'TEST_POST_COMMIT_TYPEERROR' in json.dumps(resumed)
                after=await call('get_task_status',status);again=await call('get_task_status',status)
                assert after['result']['status']==('failed' if fault else 'succeeded') and after['result']['is_terminal'] and after['result']==again['result']
                assert after['result']['result']['verification']['status']==('FAIL' if fault else 'PASS')
                observed=await call('inspect_modeling_object',{'name':'OnceOwned'})
                assert abs(observed['result']['matrix_world'][0][3]-1)<1e-6
                approval=await call('check_approval_status',{'request_id':pending['approval_request_id']})
                assert approval['result']['token_consumed'] is True
                await call('resolve_pending_approval',resolution,False)
                return {'status':'PASS','calls':len(calls),'task_id':pending['task_id'],'request_id':pending['approval_request_id'],
                        'final_task_status':'failed' if fault else 'succeeded','actual_mutation_executed_once':True,'rollback_claimed':False,'service':init.serverInfo.model_dump()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true");parser.add_argument("--no-fault",action="store_true");parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-modeling-once-"));print(root,flush=True)
    if args.no_fault:(root/"no_fault").touch()
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
    native=json.loads((root/"native.json").read_text());assert native["executions"]==1 and len(native["requests"])==1 and native["requests"][0]["token_consumed"];assert (root/"no_fault").exists() or json.loads((root/"invocations.json").read_text())["count"]==2
    result.update(runtime=json.loads((root/"ready.json").read_text()),native_verified=True,normal_tokens_consumed=1)
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=="__main__":main()
