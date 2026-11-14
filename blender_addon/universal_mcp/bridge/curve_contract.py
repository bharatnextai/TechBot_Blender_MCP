"""Finite curve/text data contract; Blender standard library only."""
from .modeling_validation import NAME,SNAPSHOT,VECTOR,tool_params
from .advanced_modifier_contract import number,integer,enum
POINT={'type':'object','additionalProperties':False,'required':['co'],'properties':{'co':VECTOR,'handle_left':VECTOR,'handle_right':VECTOR,'handle_type_left':enum('AUTO','VECTOR','ALIGNED','FREE'),'handle_type_right':enum('AUTO','VECTOR','ALIGNED','FREE'),'weight':number(.0001,100),'radius':number(.0001,100),'tilt':number(-100,100)}}
SPLINE={'type':'object','additionalProperties':False,'required':['type','points'],'properties':{'type':enum('BEZIER','POLY','NURBS'),'points':{'type':'array','minItems':2,'maxItems':256,'items':POINT},'cyclic':{'type':'boolean'},'order':integer(2,6),'endpoint':{'type':'boolean'}}}
SETTINGS={'type':'object','additionalProperties':False,'properties':{'dimensions':enum('2D','3D'),'resolution_u':integer(1,64),'extrude':number(0,10),'bevel_depth':number(0,10),'bevel_resolution':integer(0,6),'body':{'type':'string','maxLength':4096},'size':number(.001,100),'align_x':enum('LEFT','CENTER','RIGHT','JUSTIFY','FLUSH')}}
SCHEMA={'type':'object','additionalProperties':False,'required':['name','action'],'properties':{'name':NAME,'action':enum('create','update','copy_to_mesh'),'kind':enum('CURVE','TEXT'),'expected_snapshot_id':SNAPSHOT,'settings':SETTINGS,'splines':{'type':'array','minItems':1,'maxItems':32,'items':SPLINE},'output_name':NAME,'approved':{'type':'boolean','default':False}},'allOf':[]}
for action,fields,required in [('create',{'kind','settings','splines'},['kind','settings']),('update',{'kind','settings','splines','expected_snapshot_id'},['kind','settings','expected_snapshot_id']),('copy_to_mesh',{'output_name','expected_snapshot_id'},['output_name','expected_snapshot_id'])]:
    allowed={'name','action','approved'}|fields
    SCHEMA['allOf'].append({'if':{'properties':{'action':{'const':action}}},'then':{'type':'object','additionalProperties':False,'properties':{key:SCHEMA['properties'][key] for key in allowed},'required':required}})
INSPECTION={'type':'object','additionalProperties':False,'required':['name'],'properties':{'name':NAME}}


def validate(params,inspection=False):
    clean=tool_params(INSPECTION if inspection else SCHEMA,params)
    if inspection:return clean
    if 'output_name' in clean and (not clean['output_name'].strip() or clean['output_name']!=clean['output_name'].strip()):raise ValueError('output_name must be exact and nonblank')
    if clean['action']=='copy_to_mesh':return clean
    kind=clean['kind'];settings=clean['settings'];splines=clean.get('splines')
    if kind=='TEXT':
        if splines is not None:raise ValueError('Text accepts no spline specification')
        if 'body' not in settings:raise ValueError('Text body required')
    else:
        if any(k in settings for k in ('body','size','align_x')):raise ValueError('Text settings cannot be applied to curves')
        if not splines:raise ValueError('Curve requires an explicit spline specification')
        for spline in splines:
            bezier=spline['type']=='BEZIER';nurbs=spline['type']=='NURBS'
            if not nurbs and any(k in spline for k in ('order','endpoint')):raise ValueError('Order/endpoint are NURBS-only')
            if nurbs and spline.get('order',min(4,len(spline['points'])))>len(spline['points']):raise ValueError('NURBS order exceeds point count')
            for point in spline['points']:
                if not bezier and any(k.startswith('handle_') for k in point):raise ValueError('Handles require BEZIER points')
                if bezier and 'weight' in point:raise ValueError('Bezier weights are unsupported')
                for side in ('left','right'):
                    if point.get('handle_type_'+side) in ('FREE','ALIGNED') and 'handle_'+side not in point:raise ValueError('Explicit free/aligned handle coordinates required')
    return clean


def circle_spline(nurbs=False):
    import math
    if nurbs:
        coords=[(0,-1),(-1,-1),(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1)]
        return {'type':'NURBS','order':3,'cyclic':True,'endpoint':True,'points':[{'co':[x,y,0],'weight':1 if i%2==0 else math.sqrt(.5)} for i,(x,y) in enumerate(coords)]}
    k=4*(math.sqrt(2)-1)/3
    coords=[(1,0),(0,1),(-1,0),(0,-1)]
    return {'type':'BEZIER','cyclic':True,'points':[{'co':[x,y,0],'handle_left':[x+y*k,y-x*k,0],'handle_right':[x-y*k,y+x*k,0],'handle_type_left':'FREE','handle_type_right':'FREE'} for x,y in coords]}


def legacy_request(params):
    from .modeling_validation import tool_params
    schema={'type':'object','additionalProperties':False,'required':['name'],'properties':{'name':NAME,'curve_type':enum('BEZIER','NURBS','NURBS_CURVE','PATH','CIRCLE','NURBS_CIRCLE','TEXT'),'body':{'type':'string','maxLength':4096},'dimensions':enum('2D','3D'),'extrude':number(0,10),'bevel_depth':number(0,10),'resolution':integer(1,64),'location':VECTOR,'rotation':VECTOR,'scale':VECTOR}}
    view=dict(params)
    for key in ('curve_type','dimensions'):
        if isinstance(view.get(key),str):view[key]=view[key].upper()
    clean=tool_params(schema,view);kind=clean.get('curve_type','BEZIER')
    result={'name':clean['name'],'action':'create','kind':'TEXT' if kind=='TEXT' else 'CURVE',
            'settings':{'dimensions':clean.get('dimensions','3D'),'resolution_u':clean.get('resolution',12),'extrude':clean.get('extrude',0),'bevel_depth':clean.get('bevel_depth',0)},
            'location':clean.get('location',[0,0,0]),'rotation':clean.get('rotation',[0,0,0]),'scale':clean.get('scale',[1,1,1])}
    if kind=='TEXT':result['settings']['body']=clean.get('body','Text')
    elif kind in ('CIRCLE','NURBS_CIRCLE'):result['splines']=[circle_spline(kind=='NURBS_CIRCLE')]
    else:
        points=[{'co':[0,0,0]},{'co':[1,1,0]}] if kind=='BEZIER' else [{'co':[0,0,0]},{'co':[1,1,0]},{'co':[2,1,0]},{'co':[3,0,0]}]
        spline={'type':'NURBS' if kind in ('NURBS_CURVE','PATH') else kind,'points':points}
        if kind in ('NURBS','NURBS_CURVE','PATH'):spline.update(order=4,endpoint=True)
        result['splines']=[spline]
    transforms={key:result.pop(key) for key in ('location','rotation','scale')}
    if any(abs(x)<1e-6 for x in transforms['scale']):raise ValueError('Curve object scale cannot be singular')
    return validate(result),kind,transforms
