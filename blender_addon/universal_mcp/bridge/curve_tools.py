"""Typed curve/text transactions; no operators, context changes or arbitrary RNA."""
import hashlib,json,threading
from types import SimpleNamespace as NS
from .curve_contract import validate
from .mesh_topology import _inspect_elements
from .shader_values import shader_value,shader_values_match
from .approval_registry import get_approval_registry


def _guard(bpy):
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('Curve tools require Blender main thread')
    if bpy.context.mode!='OBJECT':raise ValueError('Curve tools require Object Mode; no mode was changed')


def _mesh_state(mesh,name,source='BASE_MESH'):
    if source not in ('BASE_MESH','EVALUATED_MESH'):
        raise ValueError('Unsupported mesh fingerprint source')
    obj=NS(name=name,type='MESH',data=mesh,mode='OBJECT')
    ctx=NS(mode='OBJECT',scene=NS(objects={name:obj}))
    result=_inspect_elements(obj,ctx,{'element_domain':'vertices','limit':1},mesh=mesh,source=source)
    return {key:result[key] for key in ('snapshot_id','state_id','topology_source','vertex_count','edge_count','polygon_count')}


def _curve_data(data):
    settings={key:shader_value(getattr(data,key)) for key in ('dimensions','resolution_u','extrude','bevel_depth','bevel_resolution')}
    if hasattr(data,'body'):settings.update({key:shader_value(getattr(data,key)) for key in ('body','size','align_x')})
    splines=[]
    if not hasattr(data,'body'):
        if len(data.splines)>32 or sum(len(s.bezier_points) if s.type=='BEZIER' else len(s.points) for s in data.splines)>8192:
            raise ValueError('Curve inspection exceeds finite spline/point budget')
        for spline in data.splines:
            entry={'type':spline.type,'cyclic':spline.use_cyclic_u,'points':[]}
            if spline.type=='NURBS':entry.update(order=spline.order_u,endpoint=spline.use_endpoint_u)
            for point in (spline.bezier_points if spline.type=='BEZIER' else spline.points):
                p={'co':list(point.co[:3]),'radius':point.radius,'tilt':point.tilt}
                if spline.type=='BEZIER':p.update(handle_left=list(point.handle_left),handle_right=list(point.handle_right),handle_type_left=point.handle_left_type,handle_type_right=point.handle_right_type)
                else:p['weight']=point.co[3]
                entry['points'].append(p)
            splines.append(entry)
    return {'kind':'TEXT' if hasattr(data,'body') else 'CURVE','settings':settings,'splines':splines}


def inspect(bpy,name):
    _guard(bpy);obj=bpy.context.scene.objects.get(name)
    if obj is None or obj.type not in ('CURVE','FONT','MESH') or obj.mode!='OBJECT':raise ValueError('Active-scene Object-mode curve, text or converted mesh required')
    bpy.context.view_layer.update()  # Flush transforms before fingerprinting matrix_world.
    result={'name':obj.name,'type':obj.type,'matrix_world':[list(row) for row in obj.matrix_world]}
    if obj.type=='MESH':result['geometry']=_mesh_state(obj.data,obj.name)
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=None
    try:
        mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=bpy.context.evaluated_depsgraph_get())
        if mesh is None:raise ValueError('Curve/text cannot be evaluated to mesh')
        result['evaluated']=_mesh_state(mesh,obj.name,source='EVALUATED_MESH')
    finally:
        if mesh is not None:evaluated.to_mesh_clear()
    if obj.type!='MESH':result.update(_curve_data(obj.data))
    result['snapshot_id']='sha256:'+hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return dict(result,success=True,verified=True)


def handle_inspect_curve_geometry(bpy_module=None,params=None):
    return inspect(bpy_module,validate(params or {},inspection=True)['name'])


def _assign(data,clean):
    for key,value in clean['settings'].items():
        setattr(data,key,value)
        if not shader_values_match(getattr(data,key),value):raise RuntimeError('Curve/text setting readback mismatch: '+key)
    if clean['kind']=='TEXT':return
    data.splines.clear()
    for spec in clean['splines']:
        spline=data.splines.new(spec['type']);spline.use_cyclic_u=spec.get('cyclic',False)
        points=spline.bezier_points if spec['type']=='BEZIER' else spline.points
        points.add(len(spec['points'])-1)
        if spec['type']=='NURBS':
            spline.order_u=spec.get('order',min(4,len(points)));spline.use_endpoint_u=spec.get('endpoint',False)
            if spline.order_u!=spec.get('order',min(4,len(points))):raise RuntimeError('NURBS order readback mismatch')
        for point,values in zip(points,spec['points']):
            point.co=values['co'] if spec['type']=='BEZIER' else [*values['co'],values.get('weight',1)]
            point.radius=values.get('radius',1);point.tilt=values.get('tilt',0)
            if spec['type']=='BEZIER':
                for side in ('left','right'):
                    setattr(point,'handle_'+side+'_type',values.get('handle_type_'+side,'AUTO'))
                    if 'handle_'+side in values:setattr(point,'handle_'+side,values['handle_'+side])
    _assert_requested(data,clean)


def _assert_requested(data,clean):
    actual=_curve_data(data)
    for key,value in clean['settings'].items():
        if not shader_values_match(actual['settings'][key],value):raise RuntimeError('Evaluated curve/text setting readback mismatch: '+key)
    if clean['kind']=='TEXT':return
    if len(actual['splines'])!=len(clean['splines']):raise RuntimeError('Spline count readback mismatch')
    for spec,observed in zip(clean['splines'],actual['splines']):
        if spec['type']!=observed['type'] or spec.get('cyclic',False)!=observed['cyclic']:raise RuntimeError('Spline type/cyclic readback mismatch')
        if len(spec['points'])!=len(observed['points']):raise RuntimeError('Spline point count readback mismatch')
        if spec['type']=='NURBS' and (observed['order']!=spec.get('order',min(4,len(spec['points']))) or observed['endpoint']!=spec.get('endpoint',False)):
            raise RuntimeError('NURBS order/endpoint readback mismatch')
        for requested,point in zip(spec['points'],observed['points']):
            for key,value in requested.items():
                if not shader_values_match(point[key],value):raise RuntimeError('Curve point readback mismatch: '+key)


def _verify(bpy,name,expected):
    actual=inspect(bpy,name)
    if actual['snapshot_id']!=expected['snapshot_id']:raise RuntimeError('Curve/text independent readback mismatch')
    return actual


def handle_configure_curve_geometry(bpy_module=None,params=None):
    bpy=bpy_module;clean=validate(params or {});_guard(bpy)
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok,reason=get_approval_registry().consume_approval(params.get('request_id'),params.get('approval_token'),'configure_curve_geometry',params)
        if not ok:raise PermissionError('Curve/text mutation denied: '+reason)
    return _configure_curve_after_approval(bpy,clean)


def _configure_curve_after_approval(bpy,clean,transforms=None):
    """Private implementation; never registered as an endpoint."""
    clean=validate(clean);_guard(bpy)
    action=clean['action'];name=clean['name'];obj=bpy.context.scene.objects.get(name)
    if action=='create':
        if bpy.data.objects.get(name) is not None or bpy.data.curves.get(name) is not None:raise ValueError('Curve/text exact name already exists')
        before=None;original=None
    else:
        before=inspect(bpy,name)
        if before['snapshot_id']!=clean['expected_snapshot_id']:raise ValueError('STALE_CURVE_GEOMETRY; inspect again')
        if obj.type not in ('CURVE','FONT') or obj.library or obj.override_library or obj.data.library or obj.animation_data or obj.data.animation_data or obj.data.shape_keys:
            raise ValueError('Mutation requires local unanimated curve/text data without shape keys')
        if action=='update' and (obj.modifiers or clean['kind']!=('TEXT' if obj.type=='FONT' else 'CURVE')):raise ValueError('Update requires matching kind and no modifiers')
        original=obj.data
    output=clean.get('output_name',name)
    if action=='copy_to_mesh' and bpy.data.objects.get(output) is not None:raise ValueError('Converted output name already exists')
    original_name=original.name if original else None
    stage=None;created=None;inventory=(set(bpy.data.objects.keys()),set(bpy.data.curves.keys()),set(bpy.data.meshes.keys()))
    try:
        if action=='copy_to_mesh':
            graph=bpy.context.evaluated_depsgraph_get()
            stage=bpy.data.meshes.new_from_object(obj.evaluated_get(graph),preserve_all_data_layers=True,depsgraph=graph)
            expected=_mesh_state(stage,output)
            if stage.validate(verbose=False,clean_customdata=False):raise ValueError('Converted mesh geometry is invalid')
            created=bpy.data.objects.new(output,stage);created.matrix_world=obj.matrix_world.copy()
            bpy.context.scene.collection.objects.link(created)
            if created.name!=output or _mesh_state(created.data,output)!=expected:raise RuntimeError('Converted mesh readback mismatch')
            if inspect(bpy,name)!=before:raise RuntimeError('Source changed during converted-copy creation')
        else:
            stage=original.copy() if original else bpy.data.curves.new(name,type='FONT' if clean['kind']=='TEXT' else 'CURVE')
            _assign(stage,clean)
            if action=='create':
                created=bpy.data.objects.new(name,stage);bpy.context.scene.collection.objects.link(created)
                if created.name!=name:raise RuntimeError('Curve/text exact-name readback mismatch')
                for key,attribute in (('location','location'),('rotation','rotation_euler'),('scale','scale')):
                    if key in (transforms or {}):
                        setattr(created,attribute,transforms[key])
                        if not shader_values_match(getattr(created,attribute),transforms[key]):raise RuntimeError('Curve object transform readback mismatch: '+key)
            else:obj.data=stage
        expected=inspect(bpy,output)
        if action!='copy_to_mesh':_assert_requested(created.data if created is not None else obj.data,clean)
        observed=_verify(bpy,output,expected)
        result={**observed,'action':action,'source_name':name,'transaction_status':'COMMITTED'}
        if action=='update' and original.users==0:
            original.name=original_name+'_UMCP_CHECKPOINT';stage.name=original_name
            if stage.name!=original_name:raise RuntimeError('Curve data name restoration mismatch')
            bpy.data.curves.remove(original)
        return result
    except Exception as error:
        try:
            if action=='update':obj.data=original;original.name=original_name
            if created is not None:bpy.data.objects.remove(created,do_unlink=True)
            if stage is not None and stage.users==0:
                (bpy.data.meshes if action=='copy_to_mesh' else bpy.data.curves).remove(stage)
            if before is not None and inspect(bpy,name)!=before:raise RuntimeError('Original curve/text state differs')
            if inventory!=(set(bpy.data.objects.keys()),set(bpy.data.curves.keys()),set(bpy.data.meshes.keys())):raise RuntimeError('Curve/text datablock inventory differs')
        except Exception as restore_error:raise RuntimeError(f'ROLLBACK_UNVERIFIED: {restore_error}; original failure: {error}') from error
        raise RuntimeError(f'ROLLED_BACK_VERIFIED: {error}') from error
