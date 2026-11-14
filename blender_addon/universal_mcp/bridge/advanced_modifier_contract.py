"""Finite advanced modifier contract; separate from the legacy three-type API."""
from .modeling_validation import NAME, SNAPSHOT, tool_params


def number(lo, hi): return {'type':'number','minimum':lo,'maximum':hi}
def integer(lo, hi): return {'type':'integer','minimum':lo,'maximum':hi}
def enum(*items): return {'type':'string','enum':list(items)}
VECTOR={'type':'array','minItems':3,'maxItems':3,'items':number(-100,100)}
PROPERTIES={
 'SUBSURF':{'levels':integer(0,6),'render_levels':integer(0,6)},
 'BEVEL':{'width':number(0,100),'segments':integer(1,64)},
 'SOLIDIFY':{'thickness':number(-10,10)},
 'BOOLEAN':{'operand_name':NAME,'operation':enum('DIFFERENCE','UNION','INTERSECT'),'solver':enum('EXACT')},
 'MIRROR':{'use_axis':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'boolean'}},'use_clip':{'type':'boolean'},'use_mirror_merge':{'type':'boolean'},'merge_threshold':number(0,1)},
 'ARRAY':{'count':integer(1,100),'use_relative_offset':{'type':'boolean'},'relative_offset_displace':VECTOR,'use_constant_offset':{'type':'boolean'},'constant_offset_displace':VECTOR},
}
ACTIONS=('add','update','remove','reorder','visibility','apply')
SCHEMA={'type':'object','additionalProperties':False,'required':['name','modifier_name','modifier_type','action','expected_snapshot_id'],
 'properties':{'approved':{'type':'boolean','default':False},'name':NAME,'modifier_name':NAME,'modifier_type':enum(*PROPERTIES),'action':enum(*ACTIONS),'expected_snapshot_id':SNAPSHOT,
 'properties':{'type':'object','additionalProperties':False,'properties':{k:v for props in PROPERTIES.values() for k,v in props.items()}},
 'index':integer(0,63),'show_viewport':{'type':'boolean'},'show_render':{'type':'boolean'}},
 'allOf':[{'if':{'properties':{'modifier_type':{'const':kind}}},'then':{'properties':{'properties':{'type':'object','additionalProperties':False,'properties':props}}}} for kind,props in PROPERTIES.items()]}
for _action in ACTIONS:
    _fields={'approved','name','modifier_name','modifier_type','action','expected_snapshot_id'}
    _fields |= {'properties'} if _action in ('add','update') else {'index'} if _action=='reorder' else {'show_viewport','show_render'} if _action=='visibility' else set()
    _required=['properties'] if _action in ('add','update') else ['index'] if _action=='reorder' else []
    SCHEMA['allOf'].append({'if':{'properties':{'action':{'const':_action}}},'then':{
        'type':'object','additionalProperties':False,'properties':{key:SCHEMA['properties'][key] for key in _fields},'required':_required}})
INSPECTION={'type':'object','additionalProperties':False,'required':['name'],'properties':{'name':NAME}}


def validate(params, inspection=False):
    clean=tool_params(INSPECTION if inspection else SCHEMA,params)
    if inspection:return clean
    if clean['modifier_name'] != clean['modifier_name'].strip() or not clean['modifier_name'].strip():raise ValueError('modifier_name must be exact and nonblank')
    if 'operand_name' in clean.get('properties',{}) and (not clean['properties']['operand_name'].strip() or clean['properties']['operand_name']!=clean['properties']['operand_name'].strip()):raise ValueError('operand_name must be exact and nonblank')
    action=clean['action']
    fields={'name','modifier_name','modifier_type','action','expected_snapshot_id'}
    fields |= {'properties'} if action in ('add','update') else {'index'} if action=='reorder' else {'show_viewport','show_render'} if action=='visibility' else set()
    if set(clean)-fields:raise ValueError('Parameters are not applicable to the requested modifier action')
    if action in ('add','update') and not clean.get('properties'):raise ValueError('Explicit modifier properties required')
    if action=='reorder' and 'index' not in clean:raise ValueError('Modifier reorder index required')
    if action=='visibility' and not any(k in clean for k in ('show_viewport','show_render')):raise ValueError('Explicit visibility flag required')
    if action=='add' and clean['modifier_type']=='BOOLEAN' and 'operand_name' not in clean['properties']:raise ValueError('Boolean operand_name required')
    return clean

