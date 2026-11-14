"""Combined finite modeling workflow, native replay checks and save/reload."""
import argparse,asyncio,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from tests.blender.verify_component_edit_mcp import CUBE
STEPS=['MeshCreate','MeshBatch','ModifierAdd','ModifierApply','CurveCreate','CurveUpdate','CurveCopy','WorldMove','Parent','GraphCreate','GraphUpdate','Cycle','ClearParent','StaleMesh','BadSocket','Denied','Expired']
ERRORS={'Cycle','StaleMesh','BadSocket','Denied','Expired'}


def command(label,snapshot=None):
    if label.startswith('Mesh') or label=='StaleMesh':
        args={'name':'WorkflowMesh','expected_snapshot_id':snapshot,'operations':[]}
        if label=='MeshCreate':args['operations']=[{'action':'create','points':CUBE[0],'face_cycles':CUBE[2]}]
        if label=='MeshBatch':args['operations']=[{'action':'move_vertices','vertices':[0],'delta':[0,0,.1]},{'action':'shade_faces','faces':[0],'smooth':True}]
        if label=='StaleMesh':args.update(name='WorkflowParent',expected_snapshot_id='sha256:'+'a'*64,operations=[{'action':'move_vertices','vertices':[0],'delta':[0,0,1]}])
        return 'edit_mesh',args
    if label.startswith('Modifier'):
        args={'name':'WorkflowMesh','modifier_name':'OwnedBevel','modifier_type':'BEVEL','action':'add' if label=='ModifierAdd' else 'apply','expected_snapshot_id':snapshot}
        if label=='ModifierAdd':args['properties']={'width':.02,'segments':2}
        return 'edit_modifier_stack',args
    if label.startswith('Curve'):
        args={'name':'WorkflowCurve','action':'create' if label=='CurveCreate' else 'update','kind':'CURVE','settings':{'dimensions':'3D','resolution_u':6,'extrude':.02,'bevel_depth':.01,'bevel_resolution':1},'splines':[{'type':'BEZIER','points':[{'co':[0,0,0]},{'co':[1,.5,0]},{'co':[2,0,.2 if label=='CurveCreate' else .5]}]}]}
        if label!='CurveCreate':args['expected_snapshot_id']=snapshot
        if label=='CurveCopy':args={'name':'WorkflowCurve','action':'copy_to_mesh','output_name':'WorkflowCurveMesh','expected_snapshot_id':snapshot}
        return 'configure_curve_geometry',args
    if label.startswith('Graph') or label=='BadSocket':
        nodes=[{'name':'Move','type':'GeometryNodeTransform'}]
        links=[{'from_node':'Input','from_socket':'Geometry','to_node':'Move','to_socket':'Geometry'}, {'from_node':'Input','from_socket':'Offset','to_node':'Move','to_socket':'Translation'}]
        if label=='GraphUpdate':
            nodes.append({'name':'Smooth','type':'GeometryNodeSetShadeSmooth','inputs':{'Shade Smooth':True}})
            links.extend([{'from_node':'Move','from_socket':'Geometry','to_node':'Smooth','to_socket':'Geometry'},{'from_node':'Smooth','from_socket':'Geometry','to_node':'Output','to_socket':'Geometry'}])
        else:links.append({'from_node':'Move','from_socket':'Geometry','to_node':'Output','to_socket':'Geometry'})
        if label=='BadSocket':links[0]['from_socket']='Missing'
        args={'name':'WorkflowMesh','modifier_name':'OwnedNodes','group_name':'WorkflowGraph','action':'create' if label=='GraphCreate' else 'update','nodes':nodes,'links':links,'parameters':[{'name':'Offset','type':'VECTOR','value':[0,0,1 if label=='GraphCreate' else 1.5]}]}
        if label!='GraphCreate':args['expected_snapshot_id']=snapshot
        return 'configure_modeling_geometry',args
    args={'name':'WorkflowMesh','action':'transform','space':'WORLD','translation':[1,0,0],'expected_snapshot_id':snapshot}
    if label=='Parent':args={'name':'WorkflowMesh','action':'parent','parent_name':'WorkflowParent','expected_snapshot_id':snapshot}
    if label=='Cycle':args={'name':'WorkflowParent','action':'parent','parent_name':'WorkflowMesh','expected_snapshot_id':snapshot}
    if label=='ClearParent':args={'name':'WorkflowMesh','action':'clear_parent','expected_snapshot_id':snapshot}
    return 'configure_modeling_object',args


def query(label):
    tool,args=command(label)
    if tool=='edit_mesh':return 'inspect_scene_data',{'category':'mesh_topology','target_name':args['name'],'element_domain':'vertices','limit':2}
    if tool=='edit_modifier_stack':return 'inspect_modifier_stack',{'name':args['name']}
    if tool=='configure_curve_geometry':return None if label=='CurveCreate' else ('inspect_curve_geometry',{'name':args['name']})
    if tool=='configure_modeling_geometry':return 'inspect_modeling_geometry',{'name':args['name'],'modifier_name':args['modifier_name']}
    return 'inspect_modeling_object',{'name':args['name']}


def fixture(root,port):
    import bpy
    from tests.policy_candidates.modeling_mesh_policy import authorizes as mesh_allows
    from tests.policy_candidates.modeling_modifier_stack_policy import authorizes as modifier_allows
    from tests.policy_candidates.modeling_curve_policy import authorizes as curve_allows
    from tests.policy_candidates.modeling_controls_geometry_policy import authorizes as final_allows
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge import curve_tools,modifier_stack,object_controls,geometry_tools
    from blender_addon.universal_mcp.bridge.mesh_atomic import snapshot
    from blender_addon.universal_mcp.bridge.shader_values import shader_values_match
    assert bpy.app.background and not bpy.data.filepath and port!=9877
    bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval=bpy.props.BoolProperty(default=True)
    original=list(bpy.data.objects);initial_active=bpy.context.view_layer.objects.active
    def object_data(obj):
        result={'name':obj.name,'type':obj.type,'matrix':[list(row) for row in obj.matrix_world],'parent':obj.parent.name if obj.parent else None,'selected':obj.select_get()}
        if obj.type=='MESH':result.update(vertices=[list(v.co) for v in obj.data.vertices],edges=[list(e.vertices) for e in obj.data.edges],faces=[list(p.vertices) for p in obj.data.polygons],smooth=[p.use_smooth for p in obj.data.polygons])
        if obj.type in ('CURVE','FONT'):result['curve']=curve_tools.inspect(bpy,obj.name)
        if obj.name=='WorkflowMesh' and obj.modifiers.get('OwnedNodes'):result['graph']=geometry_tools.inspect(bpy,obj.name,'OwnedNodes')
        return result
    def protected():return {obj.name:object_data(obj) for obj in original}
    before=protected();owned={};modifier_owned={};curve_owned={'WorkflowCurve':(None,None),'WorkflowCurveMesh':(None,None)};groups={};events=[];index=[0];replays=[]
    for name in ('WorkflowMesh','WorkflowParent'):
        mesh=bpy.data.meshes.new(name+'Data')
        if name=='WorkflowParent':mesh.from_pydata(*CUBE)
        obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);owned[name]=(obj,mesh)
        modifier_owned[name]=(obj,mesh,{})
    bpy.context.view_layer.update();queue=MainThreadQueue(bpy)
    real={name:queue._handlers[name] for name in ('edit_mesh','edit_modifier_stack','configure_curve_geometry','configure_modeling_object','configure_modeling_geometry')}
    def state(label):
        tool,args=command(label);obj=bpy.context.scene.objects.get(args['name'])
        if tool=='edit_mesh':return snapshot(obj,bpy.context)
        if tool=='edit_modifier_stack':return modifier_stack.inspect(bpy,obj.name)
        if tool=='configure_curve_geometry':return None if label=='CurveCreate' else curve_tools.inspect(bpy,obj.name)
        if tool=='configure_modeling_geometry':return geometry_tools.inspect(bpy,obj.name,args['modifier_name'])
        return object_controls.inspect(bpy,obj.name)
    def assets():return {name:object_data(bpy.data.objects[name]) for name in list(owned)+[name for name,record in curve_owned.items() if record[0] is not None]}
    def tracked(tool):
        def invoke(bpy_module=None,params=None):
            if index[0]>=len(STEPS):return real[tool](bpy_module=bpy_module,params=params)
            label=STEPS[index[0]];assert command(label)[0]==tool
            prior=assets()
            try:result=real[tool](bpy_module=bpy_module,params=params)
            except Exception as error:
                assert label in ERRORS,(label,str(error));assert assets()==prior,(label,'error changed assets')
                events.append({'label':label,'expected_error':str(error),'preserved':True});index[0]+=1
                (root/'events.json').write_text(json.dumps(events,indent=2));raise
            assert label not in ERRORS
            obj=bpy.data.objects[result['name']]
            if label=='MeshCreate':assert len(obj.data.vertices)==8 and len(obj.data.polygons)==6
            if label=='MeshBatch':assert abs(obj.data.vertices[0].co.z-(-1+.1))<1e-6 and obj.data.polygons[0].use_smooth
            if label=='ModifierApply':assert len(obj.data.vertices)>8 and not obj.modifiers
            if label=='WorldMove':assert abs(obj.matrix_world.translation.x-1)<1e-6
            if label in ('Parent','ClearParent'):assert shader_values_match(result['matrix_world'],prior['WorkflowMesh']['matrix'])
            if label.startswith('Graph'):
                graph=bpy.context.evaluated_depsgraph_get();evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
                try:
                    dz=1 if label=='GraphCreate' else 1.5
                    assert len(mesh.vertices)==len(obj.data.vertices)
                    assert all(abs(v.co.z-(base.co.z+dz))<1e-5 for v,base in zip(mesh.vertices,obj.data.vertices))
                    if label=='GraphUpdate':assert all(face.use_smooth for face in mesh.polygons)
                finally:evaluated.to_mesh_clear()
            if tool=='configure_curve_geometry':curve_owned[obj.name]=(obj,obj.data)
            else:
                owned[obj.name]=(obj,obj.data);modifier_owned[obj.name]=(obj,obj.data,{m.name:m for m in obj.modifiers})
            if tool=='configure_modeling_geometry':
                mod=obj.modifiers['OwnedNodes'];groups[(obj.name,mod.name)]=(mod,mod.node_group)
            # Replay the exact consumed credentials at the actual handler boundary.
            checkpoint=assets()
            try:real[tool](bpy_module=bpy_module,params=params)
            except PermissionError as error:replays.append({'tool':tool,'denied':True,'reason':str(error)})
            else:raise AssertionError('Consumed token replay was accepted')
            assert assets()==checkpoint
            events.append({'label':label,'result':result,'replay_denied':True});index[0]+=1
            (root/'events.json').write_text(json.dumps(events,indent=2));return result
        return invoke
    for tool in real:queue.register_handler(tool,tracked(tool))
    server=BridgeServer(port=port,queue=queue);server.start();approved=set();deadline=time.monotonic()+180
    (root/'ready.json').write_text(json.dumps({'pid':os.getpid(),'port':port,'blender':bpy.app.version_string}))
    try:
        while not (root/'stop').exists() and time.monotonic()<deadline:
            queue.drain_queue()
            for request in list(get_approval_registry()._requests.values()):
                if request.status!='pending' or request.request_id in approved:continue
                label=STEPS[index[0]];current=state(label);tool,planned=command(label,None if current is None else current['snapshot_id']);planned['approved']=False
                assert request.tool_name==tool and request.params==json.loads(json.dumps(planned)),(request.params,planned)
                if tool=='edit_mesh':allowed=mesh_allows(bpy,tool,request.params,owned)
                elif tool=='edit_modifier_stack':allowed=modifier_allows(bpy,tool,request.params,modifier_owned,planned)
                elif tool=='configure_curve_geometry':allowed=curve_allows(bpy,tool,request.params,curve_owned,planned)
                else:allowed=final_allows(bpy,tool,request.params,owned,groups,planned)
                assert allowed,(label,'authorized candidate rejected fixture')
                ok,_=get_approval_registry().resolve_request(request.request_id,'denied' if label=='Denied' else 'approved',reason='USER-AUTHORIZED ISOLATED modeling workflow TEST',approve_task_group=False)
                assert ok;approved.add(request.request_id)
                if label in ('Denied','Expired'):
                    if label=='Expired':request.created_at-=1000
                    events.append({'label':label,'host_decision':label,'state_before':assets()});index[0]+=1
            time.sleep(.01)
    finally:
        server.stop();bpy.context.view_layer.objects.active=initial_active
        registry=get_approval_registry();result={'before':before,'after':protected(),'protected_preserved':before==protected(),'completed_steps':index[0],'events':events,'replays':replays,'requests':[registry.inspect_request_status(i) for i in registry._requests]}
        (root/'native.json').write_text(json.dumps(result,indent=2));assert result['protected_preserved']
        if index[0]==len(STEPS):
            saved=root/'modeling_workflow.blend';assert not saved.exists() and saved.resolve().parent==root.resolve()
            prior=assets();bpy.ops.wm.save_as_mainfile(filepath=str(saved),compress=True)
            assert saved.is_file() and saved.stat().st_size>0
            names=list(prior);bpy.ops.wm.open_mainfile(filepath=str(saved));bpy.context.view_layer.update()
            after={name:object_data(bpy.data.objects[name]) for name in names}
            def equivalent(a,b):
                if isinstance(a,dict):return set(a)==set(b) and all(equivalent(v,b[k]) for k,v in a.items() if k not in ('snapshot_id','state_id'))
                if isinstance(a,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
                return shader_values_match(a,b)
            assert equivalent(prior,after),'Save/reload native state mismatch'
            (root/'save_reload.json').write_text(json.dumps({'verified':True,'path':str(saved),'size':saved.stat().st_size,'before':prior,'after':after},indent=2))


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE='1');env.pop('UMCP_LOCAL_TEST_AUTOAPPROVE',None)
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','mcp_service.app','--transport','stdio','--bridge-port',str(port),'--bridge-timeout','5','--approval-mode','blender'],env=env,cwd=str(PROJECT))
    calls=[]
    with (root/'mcp.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                init=await session.initialize()
                async def call(tool,args,success=True):
                    response=await session.call_tool(tool,arguments=args);calls.append({'tool':tool,'args':args,'response':response.model_dump(mode='json'),'expected_success':success})
                    (root/'calls.json').write_text(json.dumps(calls,indent=2));assert not response.isError,calls[-1]
                    payload=json.loads(response.content[0].text);assert (payload['status']=='success')==success,calls[-1]
                    result=payload.get('result',{});return result.get('observed_data',result)
                for label in STEPS:
                    q=query(label);before=None if q is None else await call(*q)
                    tool,args=command(label,None if before is None else before['snapshot_id'])
                    result=await call(tool,args,success=label not in ERRORS)
                    task_id=json.loads(calls[-1]['response']['content'][0]['text'])['command_id']
                    status=await call('get_task_status',{'task_id':task_id,'session_id':'default'})
                    assert status['found'] and status['is_terminal'] and status['status']==('failed' if label in ERRORS else 'succeeded'),(label,status)
                    assert 'approval_token' not in json.dumps(status)
                    if label.startswith('Curve'):after=await call('inspect_curve_geometry',{'name':'WorkflowCurveMesh' if label=='CurveCopy' else 'WorkflowCurve'})
                    else:after=await call(*q)
                    if label in ERRORS:assert before==after,(label,'failed task changed state')
                    elif tool=='edit_mesh':assert result['snapshot_id']==after['snapshot_id']
                    else:assert result['snapshot_id']==after['snapshot_id']
                from blender_addon.universal_mcp.bridge.bridge_client import BridgeClient
                bridge=BridgeClient(port=port,timeout=5)
                try:
                    remote_decision=await asyncio.to_thread(bridge.send_command,'resolve_approval',{'request_id':'not-a-real-request','decision':'approved'})
                    assert remote_decision['status']=='error' and 'unknown' in remote_decision['message'].lower(),remote_decision
                    disabled=await asyncio.to_thread(bridge.send_command,'set_approval_settings',{'require_scene_mutation_approval':False})
                    assert disabled['status']=='error',disabled
                    settings=await asyncio.to_thread(bridge.send_command,'get_approval_settings',{})
                    assert settings['status']=='success' and settings['result']['require_scene_mutation_approval'] is True,settings
                    bypass=await asyncio.to_thread(bridge.send_command,'configure_modeling_object',{'name':'WorkflowMesh','action':'transform','translation':[1,0,0],'expected_snapshot_id':'sha256:'+'a'*64,'approved':True,'trusted_approval':True})
                    assert bypass['status']=='error' and 'approval' in bypass['message'].lower(),bypass
                    (root/'raw_bridge_security.json').write_text(json.dumps({'remote_decision_rejected':remote_decision,'disable_rejected':disabled,'settings_after':settings,'flag_bypass_rejected':bypass},indent=2))
                finally:bridge.close()
                return {'status':'PASS','calls':len(calls),'successes':sum(c['expected_success'] for c in calls),'expected_errors':sum(not c['expected_success'] for c in calls),'service':init.serverInfo.model_dump()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true");parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-modeling-workflow-"));print(root,flush=True)
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
    native=json.loads((root/"native.json").read_text());assert native["completed_steps"]==len(STEPS);assert len(native["requests"])==len(STEPS);assert sum(r["token_consumed"] for r in native["requests"])==len(STEPS)-2;assert json.loads((root/"save_reload.json").read_text())["verified"]
    result.update(runtime=json.loads((root/"ready.json").read_text()),native_verified=True,normal_tokens_consumed=len(STEPS)-2,save_reload_verified=True,replay_rejections=len(native["replays"]))
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=="__main__":main()
