"""Real Blender shader check in a disposable factory process; no live bridge."""
import bpy
import json
import os
import sys
import threading
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from blender_addon.universal_mcp.bridge.handlers import handle_request_approval
from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue

root=Path(os.environ['UMCP_LOCAL_TEST_ROOT'])
assert bpy.app.background and bpy.data.filepath==''
bpy.types.Scene.umcp_bridge_port=bpy.props.IntProperty(default=19877)
bpy.types.Scene.umcp_require_scene_mutation_approval=bpy.props.BoolProperty(default=True)
bpy.context.scene.umcp_bridge_port=19877
bpy.context.scene.umcp_require_scene_mutation_approval=True
queue=MainThreadQueue(bpy);results=[]
baseline={o.name:([list(v.co) for v in o.data.vertices] if o.type=='MESH' else None,[list(row) for row in o.matrix_world]) for o in bpy.context.scene.objects}

def call(tool,params,success=True):
    request=handle_request_approval(bpy,{'tool_name':tool,'params':params,'timeout':300})
    assert request['status']=='approved',request
    event=threading.Event();box={}
    command={'type':tool,'params':{**params,'request_id':request['request_id'],'approval_token':request['approval_token']}}
    queue._queue.put((command,event,box));queue.drain_queue();response=box['response']
    assert (response['status']=='success') is success,response
    results.append({'tool':tool,'params':params,'response':response})
    return response

name='UMCP_ShaderReadback_0139'
call('create_material',{'name':name,'roughness':.5})
material=bpy.data.materials[name];node=material.node_tree.nodes['Principled BSDF']
params={'target_name':name,'action':'set_property','node_name':node.name,'property_name':'Roughness','property_value':.68}
response=call('manage_shader_nodes',params)
assert response['result']['verified'] is True
assert abs(node.inputs['Roughness'].default_value-.68)<1e-6
assert abs(response['result']['property_value']-node.inputs['Roughness'].default_value)<1e-9
bad={**params,'property_name':'DefinitelyNotAProperty'}
r=call('manage_shader_nodes',bad,False);assert 'not found' in r['message']
assert abs(node.inputs['Roughness'].default_value-.68)<1e-6
call('manage_shader_nodes',{'target_name':name,'action':'create_node','node_type':'ShaderNodeTexNoise','node_name':'ReadbackNoise'})
connection={'target_name':name,'action':'connect','from_node':'ReadbackNoise','to_node':node.name,'from_socket':'NoSuchOutput','to_socket':'Roughness'}
before=len(material.node_tree.links)
r=call('manage_shader_nodes',connection,False);assert 'socket' in r['message']
assert len(material.node_tree.links)==before
r=call('manage_shader_nodes',{**connection,'from_socket':'Fac','to_socket':'NoSuchInput'},False)
assert len(material.node_tree.links)==before
r=call('manage_shader_nodes',{**connection,'from_socket':'Fac'})
assert r['result']['verified'] is True
assert any(l.from_node.name=='ReadbackNoise' and l.from_socket.identifier=='Fac' and l.to_socket.identifier=='Roughness' for l in material.node_tree.links)
after={o.name:([list(v.co) for v in o.data.vertices] if o.type=='MESH' else None,[list(row) for row in o.matrix_world]) for o in bpy.context.scene.objects}
assert baseline==after
(root/'readback_result.json').write_text(json.dumps({'status':'PASS','blender_version':bpy.app.version_string,'roughness':node.inputs['Roughness'].default_value,'scene_objects_preserved':True,'checks':results},indent=2))
print('SHADER_READBACK_PASS')
