"""Finite Geometry Nodes graph replacement contract; no arbitrary node classes."""
from .modeling_validation import NAME,SNAPSHOT,VECTOR,tool_params
from .advanced_modifier_contract import enum,integer,number
NODE_INPUTS={
 'GeometryNodeTransform':{'Translation':VECTOR,'Rotation':VECTOR,'Scale':VECTOR},
 'GeometryNodeMeshCube':{'Size':{'type':'array','minItems':3,'maxItems':3,'items':number(.001,100)},'Vertices X':integer(2,16),'Vertices Y':integer(2,16),'Vertices Z':integer(2,16)},
 'GeometryNodeJoinGeometry':{},
 'GeometryNodeRealizeInstances':{'Selection':{'type':'boolean'},'Realize All':{'type':'boolean'},'Depth':integer(0,16)},
 'GeometryNodeSetShadeSmooth':{'Selection':{'type':'boolean'},'Shade Smooth':{'type':'boolean'}},
 'ShaderNodeCombineXYZ':{'X':number(-100,100),'Y':number(-100,100),'Z':number(-100,100)}}
NODE={'type':'object','additionalProperties':False,'required':['name','type'],'properties':{'name':NAME,'type':enum(*NODE_INPUTS),'inputs':{'type':'object','additionalProperties':False,'properties':{key:spec for fields in NODE_INPUTS.values() for key,spec in fields.items()}}},'allOf':[{'if':{'properties':{'type':{'const':kind}}},'then':{'properties':{'inputs':{'type':'object','additionalProperties':False,'properties':fields}}}} for kind,fields in NODE_INPUTS.items()]}
PARAM_TYPES={'FLOAT':number(-100,100),'INT':integer(-100,100),'VECTOR':VECTOR,'BOOLEAN':{'type':'boolean'}}
PARAM={'type':'object','additionalProperties':False,'required':['name','type','value'],'properties':{'name':NAME,'type':enum(*PARAM_TYPES),'value':{}},'allOf':[{'if':{'properties':{'type':{'const':kind}}},'then':{'properties':{'value':spec}}} for kind,spec in PARAM_TYPES.items()]}
LINK={'type':'object','additionalProperties':False,'required':['from_node','from_socket','to_node','to_socket'],'properties':{key:NAME for key in ('from_node','from_socket','to_node','to_socket')}}
SCHEMA={'type':'object','additionalProperties':False,'required':['name','modifier_name','group_name','action','nodes','links'],'properties':{'name':NAME,'modifier_name':NAME,'group_name':NAME,'action':enum('create','update'),'expected_snapshot_id':SNAPSHOT,'nodes':{'type':'array','minItems':1,'maxItems':32,'items':NODE},'links':{'type':'array','minItems':1,'maxItems':64,'items':LINK},'parameters':{'type':'array','maxItems':16,'items':PARAM},'approved':{'type':'boolean','default':False}},'allOf':[{'if':{'properties':{'action':{'const':'update'}}},'then':{'required':['expected_snapshot_id']}}]}
INSPECTION={'type':'object','additionalProperties':False,'required':['name','modifier_name'],'properties':{'name':NAME,'modifier_name':NAME}}


def validate(params,inspection=False):
    clean=tool_params(INSPECTION if inspection else SCHEMA,params)
    for key in ('modifier_name','group_name'):
        if key in clean and (not clean[key].strip() or clean[key]!=clean[key].strip()):raise ValueError('Exact nonblank '+key+' required')
    if inspection:return clean
    names=[node['name'] for node in clean['nodes']]
    if len(names)!=len(set(names)) or any(name in ('Input','Output') or name!=name.strip() for name in names):raise ValueError('Duplicate/reserved/ambiguous node names')
    parameter_names=[p['name'] for p in clean.get('parameters',[])]
    if len(parameter_names)!=len(set(parameter_names)) or any(name=='Geometry' or name!=name.strip() or not name for name in parameter_names):raise ValueError('Duplicate/reserved parameter names')
    names=['Input',*names,'Output'];edges={name:[] for name in names};reverse={name:[] for name in names};seen=set()
    for link in clean['links']:
        a=link['from_node'];b=link['to_node'];key=tuple(link[k] for k in ('from_node','from_socket','to_node','to_socket'))
        if a not in edges or b not in edges or a==b or a=='Output' or b=='Input' or key in seen:raise ValueError('Invalid/duplicate node link')
        seen.add(key);edges[a].append(b);reverse[b].append(a)
    if sum(link['to_node']=='Output' and link['to_socket']=='Geometry' for link in clean['links'])!=1:raise ValueError('Exactly one geometry output connection required')
    visiting=set();done=set()
    def visit(name):
        if name in visiting:raise ValueError('Node graph cycle rejected')
        if name in done:return
        visiting.add(name)
        for other in edges[name]:visit(other)
        visiting.remove(name);done.add(name)
    for name in names:visit(name)
    connected=set()
    def reach(name):
        if name in connected:return
        connected.add(name)
        for other in reverse[name]:reach(other)
    reach('Output')
    if any(name not in connected for name in names if name!='Input'):raise ValueError('Every requested node must contribute to the output')
    return clean
