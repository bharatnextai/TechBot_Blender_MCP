"""Authorized object-control/finite Geometry Nodes public MCP/native E2E."""
import argparse,asyncio,json,os,socket,subprocess,sys,tempfile,time,math
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
CONTROLS=[
('World',{'action':'transform','space':'WORLD','translation':[1,0,0]}),
('Local',{'action':'transform','space':'LOCAL','translation':[1,0,0]}),
('Pivot',{'action':'transform','space':'WORLD','rotation':[0,0,math.pi/2],'pivot':[0,0,0]}),
('Scale',{'action':'transform','space':'WORLD','scale':[2,2,2],'pivot':[0,0,0]}),
('Parent',{'action':'parent','parent_name':'ControlParent'}),
('Cycle',{'name':'ControlParent','action':'parent','parent_name':'ControlOwned'}),
('Clear',{'action':'clear_parent'}),
('Select',{'action':'select','state':True,'make_active':True}),
('Deselect',{'action':'select','state':False,'make_active':False}),
('Rotate',{'action':'transform','space':'WORLD','rotation':[0,0,.3]}),
('Shear',{'action':'transform','space':'WORLD','scale':[2,1,1]}),
('Fault',{'action':'transform','space':'WORLD','translation':[0,0,1]}),
('Stale',{'action':'transform','space':'WORLD','translation':[0,0,1]})]

def link(a,sa,b,sb):return {'from_node':a,'from_socket':sa,'to_node':b,'to_socket':sb}
def graph_spec(label):
    nodes=[{'name':'Move','type':'GeometryNodeTransform','inputs':{'Translation':[.5,0,0]}}]
    links=[link('Input','Geometry','Move','Geometry'),link('Move','Geometry','Output','Geometry')];parameters=[]
    if label=='Parameter':
        nodes[0]['inputs']={};parameters=[{'name':'Offset','type':'VECTOR','value':[1,0,0]}]
        links.append(link('Input','Offset','Move','Translation'))
    if label=='Cube':nodes=[{'name':'Cube','type':'GeometryNodeMeshCube','inputs':{'Size':[1,1,1]}}];links=[link('Cube','Mesh','Output','Geometry')]
    if label=='Combine':
        nodes=[{'name':'Cube','type':'GeometryNodeMeshCube','inputs':{'Size':[1,1,1]}},{'name':'Vector','type':'ShaderNodeCombineXYZ','inputs':{'X':1,'Y':.5,'Z':0}},{'name':'Move','type':'GeometryNodeTransform'}]
        links=[link('Cube','Mesh','Move','Geometry'),link('Vector','Vector','Move','Translation'),link('Move','Geometry','Output','Geometry')]
    if label=='Join':
        nodes=[{'name':'CubeA','type':'GeometryNodeMeshCube','inputs':{'Size':[1,1,1]}},{'name':'CubeB','type':'GeometryNodeMeshCube','inputs':{'Size':[1,1,1]}},{'name':'Move','type':'GeometryNodeTransform','inputs':{'Translation':[1.5,0,0]}},{'name':'Join','type':'GeometryNodeJoinGeometry'},{'name':'Realize','type':'GeometryNodeRealizeInstances','inputs':{'Selection':True,'Realize All':True}},{'name':'Smooth','type':'GeometryNodeSetShadeSmooth','inputs':{'Selection':True,'Shade Smooth':True}}]
        links=[link('CubeA','Mesh','Join','Geometry'),link('CubeB','Mesh','Move','Geometry'),link('Move','Geometry','Join','Geometry'),link('Join','Geometry','Realize','Geometry'),link('Realize','Geometry','Smooth','Geometry'),link('Smooth','Geometry','Output','Geometry')]
    if label=='Numeric':
        parameters=[{'name':'Segments','type':'INT','value':3},{'name':'Shift','type':'FLOAT','value':.5},{'name':'SmoothFlag','type':'BOOLEAN','value':True}]
        nodes=[{'name':'Cube','type':'GeometryNodeMeshCube','inputs':{'Size':[1,1,1]}},{'name':'Vector','type':'ShaderNodeCombineXYZ'},{'name':'Move','type':'GeometryNodeTransform'},{'name':'Smooth','type':'GeometryNodeSetShadeSmooth'}]
        links=[link('Input','Segments','Cube','Vertices X'),link('Input','Shift','Vector','X'),link('Vector','Vector','Move','Translation'),link('Cube','Mesh','Move','Geometry'),link('Move','Geometry','Smooth','Geometry'),link('Input','SmoothFlag','Smooth','Shade Smooth'),link('Smooth','Geometry','Output','Geometry')]
    if label=='BadSocket':links[0]['from_socket']='Missing'
    if label=='DuplicateInput':
        nodes=[{'name':'CubeA','type':'GeometryNodeMeshCube'},{'name':'CubeB','type':'GeometryNodeMeshCube'},{'name':'Move','type':'GeometryNodeTransform'}]
        links=[link('CubeA','Mesh','Move','Geometry'),link('CubeB','Mesh','Move','Geometry'),link('Move','Geometry','Output','Geometry')]
    if label=='HiddenLiteral':
        parameters=[{'name':'Offset','type':'VECTOR','value':[1,0,0]}];links.append(link('Input','Offset','Move','Translation'))
    return {'nodes':nodes,'links':links,'parameters':parameters}
GRAPHS=['Transform','Parameter','FaultParameter','Numeric','FaultNumeric','Cube','Combine','Join','Fault','Stale','BadSocket','DuplicateInput','HiddenLiteral','FaultCreate']
CONTROL_ERRORS={'Cycle','Shear','Fault','Stale'};GRAPH_ERRORS={'Fault','FaultParameter','FaultNumeric','FaultCreate','Stale','BadSocket','DuplicateInput','HiddenLiteral'}


def plan_control(index,snapshot):
    label,args=CONTROLS[index];args={'name':'ControlOwned',**args,'expected_snapshot_id':'sha256:'+'a'*64 if label=='Stale' else snapshot}
    return args


def plan_graph(index,snapshot):
    label=GRAPHS[index]
    args={'name':'GraphOwned','modifier_name':'OwnedNodes','group_name':'OwnedGraph','action':'create' if index==0 or label=='FaultCreate' else 'update',**graph_spec(label)}
    if label=='FaultCreate':args.update(name='GraphFresh',group_name='FaultGraph')
    if index>0 and label!='FaultCreate':args['expected_snapshot_id']='sha256:'+'a'*64 if label=='Stale' else snapshot
    return args


def fixture(root,port):
    import bpy
    from unittest.mock import patch
    from tests.policy_candidates.modeling_controls_geometry_policy import authorizes
    from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
    from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    from blender_addon.universal_mcp.bridge import object_controls,geometry_tools
    from blender_addon.universal_mcp.bridge.shader_values import shader_values_match
    assert bpy.app.background and not bpy.data.filepath and port!=9877
    bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=port)
    bpy.types.Scene.umcp_require_scene_mutation_approval=bpy.props.BoolProperty(default=True)
    original=list(bpy.data.objects);initial_active=bpy.context.view_layer.objects.active
    def native(obj):return {'pointer':obj.data.as_pointer() if obj.data else None,'matrix':[list(row) for row in obj.matrix_world],'selected':obj.select_get(),'vertices':[list(v.co) for v in obj.data.vertices] if obj.type=='MESH' else None}
    def protected():return {o.name:native(o) for o in original}
    before=protected();owned={};groups={};indices={'control':0,'graph':0};events=[]
    for name in ('ControlOwned','ControlParent','GraphOwned','GraphFresh'):
        mesh=bpy.data.objects['Cube'].data.copy();obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);owned[name]=(obj,mesh)
    owned['ControlOwned'][0].location=(1,0,0);owned['ControlOwned'][0].rotation_euler.z=math.pi/2
    owned['ControlParent'][0].location=(-1,0,0)
    bpy.context.view_layer.update();base={name:[list(v.co) for v in record[1].vertices] for name,record in owned.items()}
    initial_meshes=set(bpy.data.meshes.keys());queue=MainThreadQueue(bpy)
    def track_control(bpy_module=None,params=None):
        label,_=CONTROLS[indices['control']];obj=bpy.data.objects[params['name']];prior=object_controls.inspect(bpy,obj.name)
        def fail(*args):raise RuntimeError('HOST_FORCED_CONTROL_FAILURE')
        try:
            if label=='Fault':
                with patch.object(object_controls,'_verify',side_effect=fail):result=object_controls.handle_configure_modeling_object(bpy,params)
            else:result=object_controls.handle_configure_modeling_object(bpy,params)
        except Exception as error:
            assert label in CONTROL_ERRORS,(label,str(error))
            assert object_controls.inspect(bpy,obj.name)==prior
            expected={'Cycle':'cycle','Shear':'shear','Fault':'ROLLED_BACK_VERIFIED','Stale':'STALE_MODELING_OBJECT'}[label]
            assert expected in str(error),(label,str(error))
            indices['control']+=1;events.append({'family':'control','label':label,'restored':True,'error':str(error)})
            (root/'events.json').write_text(json.dumps(events,indent=2));raise
        assert label not in CONTROL_ERRORS
        if label in ('World','Local','Pivot','Scale'):
            expected={'World':[2,0,0],'Local':[2,1,0],'Pivot':[-1,2,0],'Scale':[-2,4,0]}[label]
            assert shader_values_match(obj.matrix_world.translation,expected),(label,list(obj.matrix_world.translation),expected)
        if label in ('Parent','Clear'):assert shader_values_match(result['matrix_world'],prior['matrix_world'])
        if label=='Select':assert obj.select_get() and bpy.context.view_layer.objects.active==obj
        if label=='Deselect':assert not obj.select_get() and bpy.context.view_layer.objects.active is None
        assert all(record[0].data==record[1] and base[name]==[list(v.co) for v in record[1].vertices] for name,record in owned.items())
        indices['control']+=1;events.append({'family':'control','label':label,'state':result});(root/'events.json').write_text(json.dumps(events,indent=2));return result
    def track_graph(bpy_module=None,params=None):
        label=GRAPHS[indices['graph']];obj=bpy.data.objects[params['name']];prior=geometry_tools.inspect(bpy,obj.name,params['modifier_name']);inventory=set(bpy.data.node_groups.keys())
        def fail(*args):raise RuntimeError('HOST_FORCED_GRAPH_FAILURE')
        try:
            if label.startswith('Fault'):
                with patch.object(geometry_tools,'_verify',side_effect=fail):result=geometry_tools.handle_configure_modeling_geometry(bpy,params)
            else:result=geometry_tools.handle_configure_modeling_geometry(bpy,params)
        except Exception as error:
            assert label in GRAPH_ERRORS,(label,str(error))
            assert geometry_tools.inspect(bpy,obj.name,params['modifier_name'])==prior and set(bpy.data.node_groups.keys())==inventory
            expected={'Fault':'ROLLED_BACK_VERIFIED','FaultParameter':'ROLLED_BACK_VERIFIED','FaultNumeric':'ROLLED_BACK_VERIFIED','FaultCreate':'ROLLED_BACK_VERIFIED','Stale':'STALE_MODELING_GEOMETRY','BadSocket':'socket','DuplicateInput':'Multiple links','HiddenLiteral':'literal assignment'}[label]
            assert expected in str(error),(label,str(error))
            indices['graph']+=1;events.append({'family':'graph','label':label,'restored':True,'error':str(error)});(root/'events.json').write_text(json.dumps(events,indent=2));raise
        assert label not in GRAPH_ERRORS
        graph=bpy.context.evaluated_depsgraph_get();evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
        try:
            assert len(mesh.vertices)==(16 if label=='Join' else 12 if label=='Numeric' else 8)
            minimum=min(v.co.x for v in mesh.vertices);maximum=max(v.co.x for v in mesh.vertices)
            expected={'Transform':(-.5,1.5),'Parameter':(0,2),'Cube':(-.5,.5),'Combine':(.5,1.5),'Join':(-.5,2),'Numeric':(0,1)}[label]
            assert abs(minimum-expected[0])<1e-5 and abs(maximum-expected[1])<1e-5,(label,minimum,maximum,expected)
            if label in ('Join','Numeric'):assert all(face.use_smooth for face in mesh.polygons)
        finally:evaluated.to_mesh_clear()
        assert obj.data==owned[obj.name][1] and base[obj.name]==[list(v.co) for v in obj.data.vertices]
        mod=obj.modifiers[params['modifier_name']];groups[(obj.name,mod.name)]=(mod,mod.node_group)
        assert mod.node_group.name==params['group_name']
        indices['graph']+=1;events.append({'family':'graph','label':label,'state':result});(root/'events.json').write_text(json.dumps(events,indent=2));return result
    queue.register_handler('configure_modeling_object',track_control);queue.register_handler('configure_modeling_geometry',track_graph)
    server=BridgeServer(port=port,queue=queue);server.start();approved=set();deadline=time.monotonic()+180
    (root/'ready.json').write_text(json.dumps({'pid':os.getpid(),'port':port,'blender':bpy.app.version_string}))
    try:
        while not (root/'stop').exists() and time.monotonic()<deadline:
            queue.drain_queue()
            for request in list(get_approval_registry()._requests.values()):
                if request.status!='pending' or request.request_id in approved:continue
                if request.tool_name=='configure_modeling_object':
                    current=object_controls.inspect(bpy,request.params['name']);planned=plan_control(indices['control'],current['snapshot_id'])
                else:
                    assert request.tool_name=='configure_modeling_geometry'
                    current=geometry_tools.inspect(bpy,request.params['name'],request.params['modifier_name']);planned=plan_graph(indices['graph'],current['snapshot_id'])
                planned['approved']=False
                assert authorizes(bpy,request.tool_name,request.params,owned,groups,planned),(request.params,planned)
                ok,_=get_approval_registry().resolve_request(request.request_id,'approved',reason='USER-AUTHORIZED ISOLATED controls/Geometry Nodes TEST SUBSET',approve_task_group=False)
                assert ok;approved.add(request.request_id)
            time.sleep(.01)
    finally:
        server.stop();registry=get_approval_registry();bpy.context.view_layer.objects.active=initial_active
        result={'protected_preserved':protected()==before,'mesh_inventory_preserved':set(bpy.data.meshes.keys())==initial_meshes,
                'indices':indices,'events':events,'before':before,'after':protected(),'requests':[registry.inspect_request_status(i) for i in registry._requests]}
        (root/'native.json').write_text(json.dumps(result,indent=2));assert result['protected_preserved'] and result['mesh_inventory_preserved']


async def client(root,port):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    env=dict(os.environ,PYTHONPATH=str(PROJECT),PYTHONDONTWRITEBYTECODE='1',UMCP_LOCAL_TEST_ROOT=str(root));env.pop('UMCP_LOCAL_TEST_AUTOAPPROVE',None)
    params=StdioServerParameters(command=sys.executable,args=['-B','-m','mcp_service.app','--transport','stdio','--bridge-port',str(port),'--bridge-timeout','5','--approval-mode','blender'],env=env,cwd=str(PROJECT))
    calls=[]
    with (root/'mcp.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as streams:
            async with ClientSession(*streams) as session:
                init=await session.initialize();catalog=await session.list_tools();(root/'catalog.json').write_text(catalog.model_dump_json(indent=2))
                async def call(tool,args,success=True):
                    response=await session.call_tool(tool,arguments=args);calls.append({'tool':tool,'args':args,'response':response.model_dump(mode='json'),'expected_success':success})
                    (root/'calls.json').write_text(json.dumps(calls,indent=2));assert not response.isError,calls[-1]
                    payload=json.loads(response.content[0].text);assert (payload['status']=='success')==success,calls[-1]
                    result=payload.get('result',{});return result.get('observed_data',result)
                for i,(label,args) in enumerate(CONTROLS):
                    query={'name':args.get('name','ControlOwned')};before=await call('inspect_modeling_object',query)
                    receipt=await call('configure_modeling_object',plan_control(i,before['snapshot_id']),success=label not in CONTROL_ERRORS)
                    after=await call('inspect_modeling_object',query)
                    if label in CONTROL_ERRORS:assert before==after
                    else:assert receipt['snapshot_id']==after['snapshot_id']
                for i,label in enumerate(GRAPHS):
                    query={'name':plan_graph(i,None)['name'],'modifier_name':'OwnedNodes'};before=await call('inspect_modeling_geometry',query)
                    receipt=await call('configure_modeling_geometry',plan_graph(i,before['snapshot_id']),success=label not in GRAPH_ERRORS)
                    after=await call('inspect_modeling_geometry',query)
                    if label in GRAPH_ERRORS:assert before==after
                    else:assert receipt['snapshot_id']==after['snapshot_id']
                return {'status':'PASS','calls':len(calls),'successes':sum(c['expected_success'] for c in calls),'expected_errors':sum(not c['expected_success'] for c in calls),'service':init.serverInfo.model_dump()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="store_true");parser.add_argument("--root",type=Path);parser.add_argument("--port",type=int);args=parser.parse_args()
    if args.fixture:fixture(args.root,args.port);return
    root=Path(tempfile.mkdtemp(prefix="umcp-controls-geometry-"));print(root,flush=True)
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
    native=json.loads((root/"native.json").read_text());assert native["indices"]=={"control":len(CONTROLS),"graph":len(GRAPHS)};assert len(native["requests"])==len(CONTROLS)+len(GRAPHS) and all(r["token_consumed"] for r in native["requests"])
    result.update(runtime=json.loads((root/"ready.json").read_text()),native_verified=True,normal_tokens_consumed=len(CONTROLS)+len(GRAPHS))
    (root/"result.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=="__main__":main()
