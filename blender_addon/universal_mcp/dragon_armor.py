"""Surface-fitted armor for isolated main-thread dragon review fixtures only."""
import math
import threading

from .dragon_limbs_tail import sweep_geometry

TARGET_OBJECTS = frozenset({"Dragon_Horn_L", "Dragon_Horn_R"})
HORN = ((-2.53,.23,2.97,.105,.11),(-2.34,.32,3.18,.085,.09),
        (-2.03,.39,3.32,.05,.055),(-1.67,.42,3.39,.002,.002))


def _unit(v):
    size=math.sqrt(sum(x*x for x in v))
    if size<1e-12:raise ValueError("Degenerate surface normal")
    return tuple(x/size for x in v)


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def surface_sample(vertices,sides,t,u,side=1):
    """Sample actual ordered mesh rings and their outward bilinear normal."""
    if sides<12 or len(vertices)%sides or len(vertices)//sides<3 or side not in (-1,1):
        raise ValueError("Expected an ordered closed-ring surface")
    if not math.isfinite(t) or not math.isfinite(u) or not 0<t<1:
        raise ValueError("Surface sample outside open longitudinal domain")
    row=t*(len(vertices)//sides-1);column=(u%1)*sides
    i,j=int(row),int(column);a,b=row-i,column-j
    p,q,r,s=(vertices[i*sides+j],vertices[i*sides+(j+1)%sides],
             vertices[(i+1)*sides+j],vertices[(i+1)*sides+(j+1)%sides])
    point=tuple((1-a)*((1-b)*p[k]+b*q[k])+a*((1-b)*r[k]+b*s[k]) for k in range(3))
    along=tuple((1-b)*(r[k]-p[k])+b*(s[k]-q[k]) for k in range(3))
    around=tuple((1-a)*(q[k]-p[k])+a*(s[k]-r[k]) for k in range(3))
    normal=_unit(_cross(around,along))
    return point,tuple(x*side for x in normal)


def x_parameter(vertices,sides,x):
    """Locate a head/core row by x; valid only for its monotonic axial rings."""
    xs=[vertices[i][0] for i in range(0,len(vertices),sides)]
    if not xs[0]<x<xs[-1] or any(a>=b for a,b in zip(xs,xs[1:])):
        raise ValueError("Expected an interior x on the preserved core")
    i=next(i for i in range(len(xs)-1) if xs[i]<=x<xs[i+1])
    return (i+(x-xs[i])/(xs[i+1]-xs[i]))/(len(xs)-1)


def plate_geometry(vertices,sides,t,u,dt,du,height,side=1):
    """One closed beveled six-sided scale, caudally pointed along the mesh."""
    if not all(math.isfinite(v) for v in (dt,du,height)) or not 0<dt<.2 or not 0<du<.3 or not 0<height<.1:
        raise ValueError("Invalid plate dimensions")
    outline=((-0.50,0),(-0.22,-.48),(.26,-.42),(.62,0),(.26,.42),(-.22,.48))
    if side>0:outline=tuple(reversed(outline))
    points=[]
    for scale,offset in ((1,height*.12),(.72,height)):
        for a,b in outline:
            p,n=surface_sample(vertices,sides,t+a*dt*scale,u+b*du*scale,side)
            points.append(tuple(p[k]+offset*n[k] for k in range(3)))
    p,n=surface_sample(vertices,sides,t-.08*dt,u,side)
    points.append(tuple(p[k]+height*1.18*n[k] for k in range(3)))
    for a,b in outline:
        p,n=surface_sample(vertices,sides,t+a*dt,u+b*du,side)
        points.append(tuple(p[k]-min(.002,height*.4)*n[k] for k in range(3)))
    p,n=surface_sample(vertices,sides,t,u,side)
    points.append(tuple(p[k]-min(.002,height*.4)*n[k] for k in range(3)))
    faces=[]
    for j in range(6):
        nxt=(j+1)%6
        faces.extend(((j,nxt,nxt+6,j+6),(j+6,nxt+6,12),
                      (j,13+j,13+nxt,nxt),(19,13+nxt,13+j)))
    return points,faces


def field_specs(start,end,rows,columns,region):
    """Region-specific staggered fields, plus broad ventral articulated scutes."""
    if not 0<start<end<1 or rows<3 or columns<3 or region not in ("Head","Neck","Torso","Limb","Tail","Ventral"):
        raise ValueError("Unsupported anatomical scale field")
    out=[]
    for i in range(rows):
        t=start+(end-start)*(i+.5)/rows
        for j in range(columns):
            if region=="Ventral":
                u=.75+(j-(columns-1)/2)*.085
                du=.16 if j==columns//2 else .135
            else:
                u=((j+.5*(i%2))/columns)%1;du=1.15/columns
                if region in ("Head","Neck","Torso") and math.sin(2*math.pi*u)<(-.2 if region=="Head" else -.65):continue
            # Deliberate regional size and relief, not one tiled decorative grid.
            variation=1+.14*math.sin(i*1.7+j*2.4)
            spacing=(end-start)/rows
            flow={"Head":.08,"Neck":.15,"Torso":.24,"Limb":.20,"Tail":.10,"Ventral":.05}[region]
            curved_t=t+spacing*flow*math.cos(2*math.pi*u)*math.sin(math.pi*(i+.5)/rows)
            dt=spacing*(1.40 if region=="Ventral" else 1.10)*variation
            height={"Head":.017,"Neck":.008,"Torso":.007,"Limb":.0045,"Tail":.0045,"Ventral":.010}[region]
            if region=="Tail":height*=1-.82*t
            if region=="Limb":height*=1-.45*t
            out.append({"t":curved_t,"u":u,"dt":dt,"du":du*(1+.08*math.cos(i*2.1+j*1.8)),"height":height,
                        "variant":int(math.sin(i*17.1+j*13.47)>.88),"region":region})
    return out


def detail_dragon_armor(bpy_module):
    """Add fitted shells while leaving every non-horn original object intact."""
    if threading.current_thread() is not threading.main_thread():
        raise PermissionError("Armor modeling must run on Blender's main thread")
    from .bridge.handlers import _local_test_autoapproval
    if not _local_test_autoapproval(bpy_module,"create_primitive",{}):
        raise PermissionError("Armor modeling requires the isolated local background test profile")
    if bpy_module.data.collections.get("DragonArmor_0136"):
        raise ValueError("Refusing duplicate armor modeling")
    names=["Dragon_Torso","Dragon_Tail_Base"]+[f"Dragon_Leg_{end}_{side}" for end in ("Front","Hind") for side in ("L","R")]+sorted(TARGET_OBJECTS)
    if any(bpy_module.data.objects.get(n) is None for n in names):raise ValueError("Missing v0.1.35 anatomy")
    def material(source,name,color,roughness):
        if bpy_module.data.materials.get(name):raise ValueError("Refusing material collision: "+name)
        m=bpy_module.data.materials[source].copy();m.name=name;m.use_nodes=True
        shader=next(n for n in m.node_tree.nodes if n.type=="BSDF_PRINCIPLED")
        shader.inputs["Base Color"].default_value=(*color,1)
        shader.inputs["Roughness"].default_value=roughness
        return m
    red=material("Dragon_Wing_Skin_0133","Dragon_Armor_Red_0136",(.19,.023,.010),.60)
    dark=material("Dragon_Wing_Skin_0133","Dragon_Armor_Dark_0136",(.105,.012,.006),.68)
    bone=material("Material","Dragon_Keratin_0136",(.48,.34,.18),.43)
    tip=material("Dragon_Wing_Veins_0133","Dragon_Keratin_Tip_0136",(.022,.014,.009),.38)
    belly=material("Dragon_Wing_Skin_0133","Dragon_Ventral_0136",(.43,.31,.17),.66)
    collection=bpy_module.data.collections.new("DragonArmor_0136");bpy_module.context.scene.collection.children.link(collection)
    added=[];counts={};attachments={}
    def add(name,vertices,faces,mats,indices=None,existing=False,smooth=False):
        mesh=bpy_module.data.meshes.new(name+"_Detail");mesh.from_pydata(vertices,[],faces);mesh.update()
        if mesh.validate():raise ValueError("Armor geometry required repair")
        for m in mats:mesh.materials.append(m)
        for polygon in mesh.polygons:
            polygon.use_smooth=smooth
            if indices:polygon.material_index=indices[polygon.index]
        if existing:
            obj=bpy_module.data.objects[name];obj.data=mesh;obj.location=(0,0,0);obj.rotation_euler=(0,0,0);obj.scale=(1,1,1)
            for modifier in list(obj.modifiers):obj.modifiers.remove(modifier)
        else:
            obj=bpy_module.data.objects.new(name,mesh);collection.objects.link(obj);added.append(name)
        return obj
    def grid(name,sides):
        obj=bpy_module.data.objects[name];v=[tuple(obj.matrix_world@p.co) for p in obj.data.vertices]
        if len(v)%sides:raise ValueError("Unexpected preserved ring grid: "+name)
        return v
    def field(name,source,sides,specs,side=1,ventral=False):
        v=grid(source,sides);vertices=[];faces=[];indices=[]
        for spec in specs:
            points,polys=plate_geometry(v,sides,spec["t"],spec["u"],spec["dt"],spec["du"],spec["height"],side)
            offset=len(vertices);vertices.extend(points);faces.extend(tuple(i+offset for i in face) for face in polys)
            indices.extend([spec["variant"]]*len(polys))
        add(name,vertices,faces,[belly,bone] if ventral else [red,dark],indices)
        counts[name]=len(specs);attachments[name]={"source":source,"side":side,"specs":specs}
    core=grid("Dragon_Torso",48)
    for region,a,b,rows,columns in (("Head",-3.46,-2.44,7,12),("Neck",-2.40,-1.18,12,22),("Torso",-1.16,1.73,20,30)):
        start,end=x_parameter(core,48,a),x_parameter(core,48,b)
        specs=field_specs(start,end,rows,columns,region)
        if region=="Head":
            specs=[s for s in specs if not (-3.04<surface_sample(core,48,s["t"],s["u"])[0][0]<-2.67 and (min(abs(s["u"]-.065),abs(s["u"]-.435))<.09))]
            specs=[s for s in specs if not (surface_sample(core,48,s["t"],s["u"])[0][0]<-3.3 and min(abs(s["u"]-.065),abs(s["u"]-.435))<.07)]
        field("Dragon_Armor_"+region,"Dragon_Torso",48,specs)
    for region,a,b,rows in (("Throat",-2.26,-1.18,9),("Belly",-1.16,1.55,17)):
        field("Dragon_Armor_"+region,"Dragon_Torso",48,field_specs(x_parameter(core,48,a),x_parameter(core,48,b),rows,3,"Ventral"),ventral=True)
    field("Dragon_Armor_Tail","Dragon_Tail_Base",48,field_specs(.025,.94,34,14,"Tail"))
    for end in ("Front","Hind"):
        for suffix,side in (("L",1),("R",-1)):
            field(f"Dragon_Armor_{end}_{suffix}",f"Dragon_Leg_{end}_{suffix}",32,field_specs(.06,.94,18,14,"Limb"),side)
    for suffix,side in (("L",1),("R",-1)):
        horn=sweep_geometry(HORN,steps=12,sides=16,side=side)
        bands=[int(i//16>=(len(horn["centers"])-1)*.76) for i in range(len(horn["faces"])-2)]+[0,1]
        add("Dragon_Horn_"+suffix,horn["vertices"],horn["faces"],[bone,tip],bands,True,True)
        brow=((-3.03,.30,2.83,.025,.035),(-2.85,.39,2.92,.045,.055),(-2.62,.40,2.99,.035,.04),(-2.48,.38,3.01,.006,.006))
        temporal=((-2.55,.35,2.81,.065,.07),(-2.32,.48,2.92,.05,.05),(-2.04,.57,3.09,.002,.002))
        for kind,profile,mats in (("Brow",brow,[dark]),("TemporalHorn",temporal,[bone])):
            data=sweep_geometry(profile,steps=10,sides=12,side=side)
            add(f"Dragon_Armor_{kind}_{suffix}",data["vertices"],data["faces"],mats,smooth=kind!="Brow")
        specs=[]
        for i,x in enumerate((-2.82,-2.65,-2.48)):
            t=x_parameter(core,48,x);u=(.98 if side>0 else .52)
            specs.append({"t":t,"u":u,"dt":.026,"du":.10,"height":.038-i*.004,"variant":i%2})
        field("Dragon_Armor_Cheek_"+suffix,"Dragon_Torso",48,specs)
    return {"changed_objects":sorted(TARGET_OBJECTS),"added_objects":added,"plate_counts":counts,
            "attachments":attachments,"new_materials":[m.name for m in (red,dark,bone,tip,belly)],
            "whole_dragon_fused":False,"external_textures_used":False}
