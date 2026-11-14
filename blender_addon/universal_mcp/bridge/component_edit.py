"""Typed, fingerprint-bound, atomic BMesh operations; no UI/operator context."""
import threading
from .modeling_validation import NAME,INDICES,VECTOR,SNAPSHOT,TRANSPORT,check,tool_params
from .approval_registry import get_approval_registry
from .mesh_atomic import run

NUMBER={"type":"number","minimum":0.000001,"maximum":1000}
SELECT={"type":"array","minItems":1,"maxItems":1024,"items":{"type":"integer","minimum":0,"maximum":1000000},"uniqueItems":True}
ACTION_FIELDS={
 "create":({"points":{"type":"array","maxItems":1000,"items":VECTOR},"edge_pairs":{"type":"array","maxItems":2000,"items":{"type":"array","minItems":2,"maxItems":2,"items":{"type":"integer","minimum":0}}},"face_cycles":{"type":"array","maxItems":1000,"items":{"type":"array","minItems":3,"maxItems":128,"items":{"type":"integer","minimum":0},"uniqueItems":True}}},[]),
 "delete_vertices":({"vertices":SELECT},["vertices"]),"delete_edges":({"edges":SELECT},["edges"]),"delete_faces":({"faces":SELECT},["faces"]),
 "extrude":({"faces":SELECT,"delta":VECTOR},["faces","delta"]),
 "inset":({"faces":SELECT,"thickness":NUMBER},["faces","thickness"]),
 "bevel":({"edges":SELECT,"width":NUMBER,"segments":{"type":"integer","minimum":1,"maximum":8}},["edges","width"]),
 "subdivide":({"edges":SELECT,"cuts":{"type":"integer","minimum":1,"maximum":8}},["edges"]),
 "loop_cut":({"edges":SELECT,"cuts":{"type":"integer","minimum":1,"maximum":8}},["edges"]),
 "bridge":({"edges":SELECT},["edges"]),"fill":({"edges":SELECT},["edges"]),
 "merge":({"vertices":SELECT},["vertices"]),"dissolve_vertices":({"vertices":SELECT},["vertices"]),"dissolve_edges":({"edges":SELECT},["edges"]),
 "recalculate_normals":({"faces":SELECT},["faces"]),
 "shade_faces":({"faces":SELECT,"smooth":{"type":"boolean"}},["faces","smooth"]),
 "move_vertices":({"vertices":SELECT,"delta":VECTOR,"space":{"type":"string","enum":["LOCAL","WORLD"]},"proportional_radius":NUMBER},["vertices","delta"]),
 "snap_grid":({"vertices":SELECT,"grid_size":NUMBER},["vertices","grid_size"]),
 "symmetrize":({"direction":{"type":"string","enum":["NEGATIVE_X","POSITIVE_X","NEGATIVE_Y","POSITIVE_Y","NEGATIVE_Z","POSITIVE_Z"]},"threshold":{"type":"number","minimum":0.000001,"maximum":0.1}},["direction"]),
}
OP_PROPERTIES={"action":{"type":"string","enum":list(ACTION_FIELDS)}}
for props,required in ACTION_FIELDS.values():OP_PROPERTIES.update(props)
OP_SCHEMA={"type":"object","additionalProperties":False,"required":["action"],"properties":OP_PROPERTIES,
 "allOf":[{"if":{"properties":{"action":{"const":action}}},"then":{"type":"object","additionalProperties":False,"required":required,
 "properties":{"action":{"const":action},**props}}} for action,(props,required) in ACTION_FIELDS.items()]}
SCHEMA={"type":"object","additionalProperties":False,"required":["name","expected_snapshot_id","operations"],"properties":{
 "name":NAME,"expected_snapshot_id":SNAPSHOT,"operations":{"type":"array","minItems":1,"maxItems":32,"items":OP_SCHEMA}}}


def validate(params):
    return tool_params(SCHEMA,params)


def mutate(bm,operations,obj):
    import bmesh
    from mathutils import Vector
    bm.verts.ensure_lookup_table();bm.edges.ensure_lookup_table();bm.faces.ensure_lookup_table()
    # Integer selectors always address the initial snapshot, never reindexed topology.
    initial={"vertices":list(bm.verts),"edges":list(bm.edges),"faces":list(bm.faces)}
    def selected(op,domain):
        ids=op[domain];items=initial[domain]
        if any(i>=len(items) or not items[i].is_valid for i in ids):raise ValueError("STALE_COMPONENT: index out of range or invalidated by an earlier batch operation")
        return [items[i] for i in ids]
    results=[];allow_unchanged=True
    for op in operations:
        action=op["action"];before=(len(bm.verts),len(bm.edges),len(bm.faces))
        if action=="create":
            if not any(op.get(k) for k in ("points","edge_pairs","face_cycles")):raise ValueError("create requires geometry")
            vertices=list(initial["vertices"])+[bm.verts.new(point) for point in op.get("points",[])]
            for key in ("edge_pairs","face_cycles"):
                for cycle in op.get(key,[]):
                    if len(set(cycle))!=len(cycle) or any(i>=len(vertices) or not vertices[i].is_valid for i in cycle):raise ValueError("Invalid creation connectivity")
                    (bm.edges if key=="edge_pairs" else bm.faces).new([vertices[i] for i in cycle])
        elif action.startswith("delete_"):
            domain=action[7:];context={"vertices":"VERTS","edges":"EDGES","faces":"FACES_ONLY"}[domain]
            bmesh.ops.delete(bm,geom=selected(op,domain),context=context)
        elif action=="extrude":
            if not Vector(op["delta"]).length:raise ValueError("Extrusion delta cannot be zero")
            source_faces=selected(op,"faces")
            result=bmesh.ops.extrude_face_region(bm,geom=source_faces)
            bmesh.ops.delete(bm,geom=source_faces,context="FACES")
            vertices=[x for x in result["geom"] if isinstance(x,bmesh.types.BMVert)]
            bmesh.ops.translate(bm,verts=vertices,vec=Vector(op["delta"]))
            if not vertices:raise RuntimeError("Extrusion produced no vertices")
        elif action=="inset":bmesh.ops.inset_region(bm,faces=selected(op,"faces"),thickness=op["thickness"],use_boundary=True,use_even_offset=True)
        elif action=="bevel":bmesh.ops.bevel(bm,geom=selected(op,"edges"),offset=op["width"],segments=op.get("segments",1),profile=.5,affect="EDGES",clamp_overlap=False)
        elif action in ("subdivide","loop_cut"):
            edges=selected(op,"edges")
            if action=="loop_cut":
                chosen=set(edges);faces={f for e in edges for f in e.link_faces}
                if not faces:raise ValueError("Loop cut requires quad faces")
                for face in faces:
                    hit=[i for i,e in enumerate(face.edges) if e in chosen]
                    if len(face.verts)!=4 or len(hit)!=2 or (hit[1]-hit[0])%2!=0:raise ValueError("Loop cut requires opposite edges across a quad strip")
            bmesh.ops.subdivide_edges(bm,edges=edges,cuts=op.get("cuts",1),use_grid_fill=True)
            if len(bm.verts)<=before[0]:raise RuntimeError("Subdivision produced no vertices")
        elif action in ("bridge","fill"):
            edges=selected(op,"edges");vertices={v for e in edges for v in e.verts}
            if any(sum(e in edges for e in v.link_edges)!=2 for v in vertices):raise ValueError("Closed boundary loops required")
            remaining=set(vertices);components=[]
            while remaining:
                pending=[remaining.pop()];component=set(pending)
                while pending:
                    for edge in pending.pop().link_edges:
                        if edge in edges:
                            for vertex in edge.verts:
                                if vertex in remaining:remaining.remove(vertex);component.add(vertex);pending.append(vertex)
                components.append(component)
            if action=="bridge":
                if len(components)!=2 or len(components[0])!=len(components[1]):raise ValueError("Bridge requires two equal-size disjoint loops")
                result=bmesh.ops.bridge_loops(bm,edges=edges,use_pairs=True)
            else:
                if len(components)!=1:raise ValueError("Fill requires one closed loop")
                result=bmesh.ops.holes_fill(bm,edges=edges,sides=0)
            if not result.get("faces"):raise RuntimeError("No faces created")
        elif action=="merge":
            vertices=selected(op,"vertices")
            if len(vertices)<2:raise ValueError("Merge requires at least two vertices")
            bmesh.ops.pointmerge(bm,verts=vertices,merge_co=sum((v.co for v in vertices),Vector())/len(vertices))
        elif action=="dissolve_vertices":bmesh.ops.dissolve_verts(bm,verts=selected(op,"vertices"),use_face_split=False,use_boundary_tear=False)
        elif action=="dissolve_edges":bmesh.ops.dissolve_edges(bm,edges=selected(op,"edges"),use_verts=False,use_face_split=False)
        elif action=="recalculate_normals":bmesh.ops.recalc_face_normals(bm,faces=selected(op,"faces"))
        elif action=="shade_faces":
            for face in selected(op,"faces"):face.smooth=op["smooth"]
        elif action=="move_vertices":
            vertices=selected(op,"vertices");delta=Vector(op["delta"])
            if not delta.length:raise ValueError("Movement delta cannot be zero")
            if op.get("space","LOCAL")=="WORLD":
                if abs(obj.matrix_world.determinant())<1e-12:raise ValueError("Singular world transform")
                delta=obj.matrix_world.inverted().to_3x3()@delta
            radius=op.get("proportional_radius")
            if radius:
                from mathutils.kdtree import KDTree
                tree=KDTree(len(vertices))
                for i,v in enumerate(vertices):tree.insert(v.co,i)
                tree.balance()
                moves=[(v,max(0,1-tree.find(v.co)[2]/radius)) for v in bm.verts]
            else:moves=[(v,1) for v in vertices]
            for vertex,weight in moves:vertex.co+=delta*weight
        elif action=="snap_grid":
            grid=op["grid_size"]
            for vertex in selected(op,"vertices"):vertex.co=[round(x/grid)*grid for x in vertex.co]
        elif action=="symmetrize":
            bmesh.ops.symmetrize(bm,input=list(bm.verts)+list(bm.edges)+list(bm.faces),direction=("-" if op["direction"].startswith("NEGATIVE") else "")+op["direction"][-1],dist=op.get("threshold",1e-6))
        if action not in ("recalculate_normals","shade_faces","snap_grid","symmetrize"):allow_unchanged=False
        bm.normal_update()
        from .mesh_topology import MAX_SNAPSHOT_ELEMENTS
        if len(bm.verts)+len(bm.edges)+len(bm.faces)+sum(len(f.verts) for f in bm.faces)>MAX_SNAPSHOT_ELEMENTS:
            raise ValueError("Batch exceeded topology resource budget")
        results.append({"action":action,"before_counts":list(before),"after_counts":[len(bm.verts),len(bm.edges),len(bm.faces)]})
    return {"operations":results,"allow_unchanged":allow_unchanged}


def handle_edit_mesh(bpy_module=None,params=None):
    params=params or {};clean=validate(params);bpy=bpy_module
    if threading.current_thread() is not threading.main_thread():raise RuntimeError("Mesh edits require main thread")
    from .handlers import is_approval_required
    if is_approval_required(bpy):
        ok,reason=get_approval_registry().consume_approval(params.get("request_id"),params.get("approval_token"),"edit_mesh",params)
        if not ok:raise PermissionError("Mesh edit denied: "+reason)
    obj=bpy.context.scene.objects.get(clean["name"])
    if obj is None or obj.type!="MESH" or obj.data is None:raise ValueError("Target must be an active-scene mesh")
    result=run(bpy,obj,lambda bm:mutate(bm,clean["operations"],obj),clean["expected_snapshot_id"])
    result["action"]="edit_mesh"
    return result
