"""Additive v0.1.32 wing refinements, restricted to isolated main-thread fixtures.

Validated membrane vertices, topology, UVs, modifiers and original ribs are read
only. New closed detail shells provide joints, tendon fairings and vein relief.
"""
import math
import threading
from .wing_membranes import _tube_mesh


def _unit(v):
    size = math.sqrt(sum(x*x for x in v))
    if size < 1e-12:
        raise ValueError("Degenerate surface direction")
    return tuple(x/size for x in v)


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def _point(vertices,t,u):
    if len(vertices)!=1531 or not all(math.isfinite(x) and 0<=x<=1 for x in (t,u)):
        raise ValueError("Expected bounded parameters and the v0.1.32 membrane grid")
    row=t*18;col=u*84;i=min(int(row),17);j=min(int(col),83)
    a,b=row-i,col-j
    def v(r,c):return vertices[0] if r==0 else vertices[1+(r-1)*85+c]
    return tuple((1-a)*((1-b)*v(i,j)[k]+b*v(i,j+1)[k])+a*((1-b)*v(i+1,j)[k]+b*v(i+1,j+1)[k]) for k in range(3))


def surface_sample(vertices,t,u):
    """Bilinear sample of the actual asset; no baseline surface regeneration."""
    p=_point(vertices,t,u)
    a,b=_point(vertices,max(0.001,t-0.001),u),_point(vertices,min(1,t+0.001),u)
    c,d=_point(vertices,t,max(0,u-0.001)),_point(vertices,t,min(1,u+0.001))
    normal=_unit(_cross(tuple(b[k]-a[k] for k in range(3)),tuple(d[k]-c[k] for k in range(3))))
    if normal[2]<0:normal=tuple(-x for x in normal)
    return p,normal


def vein_network(panel):
    """One trunk and three child branches in UV space, with exact attachment."""
    if panel not in (2,3,4,5):raise ValueError("Expected a distal membrane panel")
    def bezier(control):
        out=[]
        for i in range(25):
            q=i/24
            out.append(tuple((1-q)**3*control[0][k]+3*(1-q)**2*q*control[1][k]+3*(1-q)*q*q*control[2][k]+q**3*control[3][k] for k in range(2)))
        return out
    trunk=bezier(((0.18,(panel+0.10)/6),(0.38,(panel+0.30)/6),(0.69,(panel+0.56)/6),(0.93,(panel+0.74)/6)))
    paths=[{"uv":trunk,"radius":0.006,"parent_index":None}]
    for index,edge in ((7,0.06),(13,0.94),(18,0.12)):
        start=trunk[index]
        target=(panel+edge)/6
        controls=(start,(start[0]+0.07,start[1]),(0.87,target),(0.96,target))
        paths.append({"uv":bezier(controls),"radius":0.0035,"parent_index":index})
    return paths


def tendon_fairing(vertices,seam,side):
    """Thin closed shoulder-to-tip transition ribbon, fitted to existing skin."""
    if seam not in (2,3,4,5) or side not in (-1,1):raise ValueError("Invalid finger seam")
    rows,columns=24,9
    points=[];uv=[]
    for layer in (0,1):
        for i in range(rows):
            t=0.045+0.925*i/(rows-1)
            halfwidth=0.012*(1-0.45*t)*math.sin(math.pi*t)**0.3
            for j in range(columns):
                f=j/(columns-1)
                p,n=surface_sample(vertices,t,seam/6+(2*f-1)*halfwidth)
                height=(0.014+0.020*(1-0.65*t)*math.sin(math.pi*f)**2) if layer==0 else 0.008
                points.append(tuple(p[k]+height*n[k] for k in range(3)))
                uv.append((t,seam/6+(2*f-1)*halfwidth))
    faces=[];size=rows*columns
    for i in range(rows-1):
        for j in range(columns-1):
            a=i*columns+j;face=(a,a+columns,a+columns+1,a+1)
            faces.extend((face,tuple(reversed(tuple(v+size for v in face)))))
    perimeter=list(range(columns))+[i*columns+columns-1 for i in range(1,rows)]+list(range(size-2,size-columns-1,-1))+[i*columns for i in range(rows-2,0,-1)]
    for a,b in zip(perimeter,perimeter[1:]+perimeter[:1]):faces.append((a,b,b+size,a+size))
    if side<0:faces=[tuple(reversed(f)) for f in faces]
    return points,faces,uv


def joint_geometry(center,radii,heading=0.0):
    """Closed quad-dominant ellipsoid, providing rounded joint/knuckle forms."""
    segments,rings=20,10
    vertices=[(center[0],center[1],center[2]+radii[2])]
    for i in range(1,rings):
        phi=math.pi*i/rings
        for j in range(segments):
            angle=2*math.pi*j/segments
            x,y=radii[0]*math.sin(phi)*math.cos(angle),radii[1]*math.sin(phi)*math.sin(angle)
            vertices.append((center[0]+x*math.cos(heading)-y*math.sin(heading),center[1]+x*math.sin(heading)+y*math.cos(heading),center[2]+radii[2]*math.cos(phi)))
    vertices.append((center[0],center[1],center[2]-radii[2]));bottom=len(vertices)-1
    faces=[(0,1+j,1+(j+1)%segments) for j in range(segments)]
    for i in range(rings-2):
        for j in range(segments):
            a=1+i*segments+j;b=1+i*segments+(j+1)%segments
            faces.append((a,a+segments,b+segments,b))
    last=1+(rings-2)*segments
    faces.extend((bottom,last+(j+1)%segments,last+j) for j in range(segments))
    return vertices,faces


def refine_wing_anatomy(bpy_module,skin_material,vein_material):
    """Only additive details; production/interactive/worker callers fail closed."""
    if threading.current_thread() is not threading.main_thread():
        raise PermissionError("Wing refinement must run on Blender's main thread")
    from .bridge.handlers import _local_test_autoapproval
    if not _local_test_autoapproval(bpy_module,"create_primitive",{}):
        raise PermissionError("Wing refinement requires the isolated local background test profile")
    if bpy_module.data.collections.get("WingAnatomy_0133"):
        raise ValueError("Anatomy detail collection exists; refusing duplicate refinement")
    sources=[]
    for suffix,side in (("L",1),("R",-1)):
        obj=bpy_module.data.objects.get(f"Wing_{suffix}_Proxy")
        if obj is None or obj.type!="MESH" or len(obj.data.vertices)!=1531 or len(obj.data.polygons)!=1512:
            raise ValueError("Expected validated v0.1.32 wing objects")
        sources.append((suffix,side,obj,[tuple(obj.matrix_world@v.co) for v in obj.data.vertices]))
    collection=bpy_module.data.collections.new("WingAnatomy_0133")
    bpy_module.context.scene.collection.children.link(collection)
    result=[]
    def make(name,vertices,faces,material,uv=None):
        mesh=bpy_module.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
        if mesh.validate():raise ValueError("Anatomy detail mesh required repair")
        obj=bpy_module.data.objects.new(name,mesh);collection.objects.link(obj);mesh.materials.append(material)
        if uv is not None:
            layer=mesh.uv_layers.new(name="WingUV")
            for loop in mesh.loops:layer.data[loop.index].uv=uv[loop.vertex_index]
        for polygon in mesh.polygons:polygon.use_smooth=True
        result.append(name)
    for suffix,side,source,vertices in sources:
        wrist=vertices[0];shoulder=_point(vertices,1,1/6);elbow=_point(vertices,1,0)
        for label,center,radii,direction in (("Shoulder",shoulder,(0.23,0.13,0.085),elbow),
                                             ("Elbow",elbow,(0.17,0.10,0.065),wrist),
                                             ("Wrist",wrist,(0.24,0.105,0.055),elbow)):
            heading=math.atan2(direction[1]-center[1],direction[0]-center[0])
            center=(center[0],center[1],center[2]-0.015)
            v,f=joint_geometry(center,radii,heading);make(f"WingAnatomy_{suffix}_{label}",v,f,skin_material)
        # Rounded muscular sleeve blends the thin original leading spar at its root.
        path=[tuple((1-t)*shoulder[k]+t*elbow[k]+(0.04*math.sin(math.pi*t) if k==2 else 0) for k in range(3)) for t in [i/16 for i in range(17)]]
        v,f=_tube_mesh(path,radius=0.115,sides=14);make(f"WingAnatomy_{suffix}_RootTendon",v,f,skin_material)
        for seam in (2,3,4,5):
            v,f,uv=tendon_fairing(vertices,seam,side);make(f"WingAnatomy_{suffix}_FingerBlend{seam}",v,f,source.data.materials[0],uv)
        vein_vertices,vein_faces=[],[]
        for panel in (2,3,4,5):
            for vein in vein_network(panel):
                path=[]
                for t,u in vein["uv"]:
                    p,n=surface_sample(vertices,t,u)
                    path.append(tuple(p[k]+(0.012+vein["radius"]*0.2)*n[k] for k in range(3)))
                v,f=_tube_mesh(path,radius=vein["radius"],sides=8);offset=len(vein_vertices)
                vein_vertices.extend(v);vein_faces.extend(tuple(i+offset for i in face) for face in f)
        make(f"WingAnatomy_{suffix}_BranchingVeins",vein_vertices,vein_faces,vein_material)
    return {"objects":result,"vein_trunks_per_wing":4,"vein_branches_per_wing":12,"baseline_membrane_modified":False}
