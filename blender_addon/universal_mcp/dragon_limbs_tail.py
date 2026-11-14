"""Main-thread, disposable-fixture limb and tail modeling; no public MCP tool."""
import math
import threading

from .wing_anatomy import joint_geometry


TARGET_OBJECTS = frozenset(
    [f"Dragon_{kind}_{end}_{side}" for kind in ("Leg", "Paw")
     for end in ("Front", "Hind") for side in ("L", "R")]
    + [f"Dragon_Tail_{part}" for part in ("Base", "Mid", "Tip")]
    + [f"Dragon_Tail_Spike_{i:02}" for i in range(1, 5)])

# Center x/y/z, two cross-section radii. Positive-y side is mirrored exactly.
FRONT = ((-1.02,.49,1.63,.10,.12),(-1.03,.68,1.40,.30,.29),
         (-.84,.90,1.08,.25,.24),(-.77,.98,.83,.17,.17),
         (-.99,1.02,.52,.18,.16),(-1.22,1.04,.25,.105,.11),
         (-1.31,1.04,.18,.08,.07))
HIND = ((1.18,.48,1.55,.12,.14),(1.10,.76,1.28,.36,.35),
        (.82,.98,.96,.32,.30),(.68,1.06,.72,.21,.20),
        (1.08,1.10,.48,.14,.15),(1.26,1.11,.31,.11,.12),
        (1.10,1.14,.18,.09,.08))
TAIL = ((1.64,0,1.15,.43,.48),(2.10,0,.97,.38,.39),
        (2.75,.05,.73,.30,.31),(3.45,.20,.53,.22,.23),
        (4.15,.45,.46,.15,.16),(4.80,.65,.62,.095,.10),
        (5.22,.78,.95,.045,.05),(5.50,.80,1.35,.004,.004))


def _unit(v):
    size=math.sqrt(sum(x*x for x in v))
    if size<1e-10:raise ValueError("Degenerate path direction")
    return tuple(x/size for x in v)


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def sweep_geometry(profile,steps=10,sides=32,side=1):
    """Closed tapered sweep with projected, continuous transported ring frames.

    Frame/radius continuity is tested; this is not a global intersection solver.
    """
    if side not in (-1,1) or not isinstance(steps,int) or not 3<=steps<=24 or not isinstance(sides,int) or not 12<=sides<=64:
        raise ValueError("Unsupported sweep density or side")
    if len(profile)<3 or any(len(p)!=5 or not all(math.isfinite(x) for x in p) or min(p[3:])<=0 for p in profile):
        raise ValueError("Expected finite centers and positive radii")
    if any(math.dist(a[:3],b[:3])<1e-5 for a,b in zip(profile,profile[1:])):
        raise ValueError("Coincident path controls")
    centers=[]
    for i in range(len(profile)-1):
        a,b=profile[i:i+2];previous=profile[max(i-1,0)];following=profile[min(i+2,len(profile)-1)]
        for j in range(steps):
            t=j/steps
            values=[]
            for k in range(5):
                value=.5*(2*a[k]+(-previous[k]+b[k])*t+(2*previous[k]-5*a[k]+4*b[k]-following[k])*t*t+(-previous[k]+3*a[k]-3*b[k]+following[k])*t*t*t)
                values.append(max(.001,value) if k>=3 else value)
            centers.append(tuple(values))
    centers.append(profile[-1]);vertices=[];frames=[];normal=(0,1,0)
    for i,p in enumerate(centers):
        a,b=centers[max(0,i-1)],centers[min(len(centers)-1,i+1)]
        tangent=_unit(tuple(b[k]-a[k] for k in range(3)))
        dot=sum(normal[k]*tangent[k] for k in range(3))
        projected=tuple(normal[k]-dot*tangent[k] for k in range(3))
        if sum(x*x for x in projected)<1e-8:
            axis=min(((1,0,0),(0,1,0),(0,0,1)),key=lambda v:abs(sum(v[k]*tangent[k] for k in range(3))))
            projected=_cross(tangent,axis)
        normal=_unit(projected);binormal=_cross(tangent,normal);frames.append((normal,binormal))
        for j in range(sides):
            theta=2*math.pi*j/sides
            point=tuple(p[k]+p[3]*math.cos(theta)*normal[k]+p[4]*math.sin(theta)*binormal[k] for k in range(3))
            vertices.append((point[0],point[1]*side,point[2]))
    faces=[]
    for i in range(len(centers)-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides;faces.append((a,b,b+sides,a+sides))
    faces.extend((tuple(reversed(range(sides))),tuple((len(centers)-1)*sides+j for j in range(sides))))
    if side<0:faces=[tuple(reversed(face)) for face in faces]
    return {"vertices":vertices,"faces":faces,"centers":centers,"frames":frames,"sides":sides}


def foot_specs(end,side=1):
    """Three weight-bearing forward toes and one smaller medial rear digit."""
    if end not in ("Front","Hind") or side not in (-1,1):raise ValueError("Invalid foot")
    x,y=(-1.36,1.04) if end=="Front" else (1.01,1.14)
    specs=[]
    for index,spread in enumerate((-1,0,1)):
        toe=((x+.08,y+spread*.12,.17,.065,.065),
             (x-.16,y+spread*.18,.15,.085,.075),
             (x-.36+abs(spread)*.04,y+spread*.24,.11,.044,.04))
        tip=toe[-1]
        claw=((tip[0]+.035,tip[1],.13,.048,.045),
              (tip[0]-.09,tip[1]+spread*.015,.10,.031,.03),
              (tip[0]-.19,tip[1]+spread*.02,.045,.002,.002))
        specs.append((str(index+1),toe,claw))
    toe=((x+.12,y-.10,.16,.065,.055),(x+.20,y-.24,.13,.055,.045),(x+.15,y-.34,.11,.03,.03))
    claw=((x+.17,y-.31,.13,.035,.03),(x+.12,y-.42,.10,.025,.02),(x+.05,y-.48,.055,.002,.002))
    specs.append(("Dew",toe,claw))
    return {"palm":((x,y*side,.15),(.25 if end=="Front" else .29,.22,.13)),"digits":specs}


def model_limbs_tail(bpy_module,skin_material,claw_material,underside_material):
    """Replace only established limb/foot/tail proxies in a fresh test copy."""
    if threading.current_thread() is not threading.main_thread():
        raise PermissionError("Limb/tail modeling must run on Blender's main thread")
    from .bridge.handlers import _local_test_autoapproval
    if not _local_test_autoapproval(bpy_module,"create_primitive",{}):
        raise PermissionError("Limb/tail modeling requires the isolated local background test profile")
    if bpy_module.data.collections.get("DragonLimbsTail_0135"):
        raise ValueError("Refusing duplicate limb/tail modeling")
    targets={name:bpy_module.data.objects.get(name) for name in TARGET_OBJECTS}
    if any(obj is None or obj.type!="MESH" for obj in targets.values()):
        raise ValueError("Missing expected v0.1.34 limb/tail proxies")
    collection=bpy_module.data.collections.new("DragonLimbsTail_0135")
    bpy_module.context.scene.collection.children.link(collection);added=[];replaced=[]
    def assign(name,vertices,faces,material,existing=False,sides=None):
        data=bpy_module.data.meshes.new(name+"_Organic");data.from_pydata(vertices,[],faces);data.update()
        if data.validate():raise ValueError("Generated mesh required repair")
        data.materials.append(material)
        for polygon in data.polygons:polygon.use_smooth=True
        if sides:
            uv=data.uv_layers.new(name="AnatomyUV");rings=len(vertices)//sides
            for polygon in data.polygons:
                wrap=any(i%sides==0 for i in polygon.vertices) and any(i%sides==sides-1 for i in polygon.vertices)
                for loop_index in polygon.loop_indices:
                    index=data.loops[loop_index].vertex_index;v=(index%sides)/sides
                    uv.data[loop_index].uv=((index//sides)/(rings-1),1 if wrap and v==0 else v)
        if existing:
            obj=targets[name];obj.data=data;obj.location=(0,0,0);obj.rotation_euler=(0,0,0);obj.scale=(1,1,1)
            for modifier in list(obj.modifiers):obj.modifiers.remove(modifier)
            replaced.append(name)
        else:
            obj=bpy_module.data.objects.new(name,data);collection.objects.link(obj);added.append(name)
        return obj
    for end,limb_profile in (("Front",FRONT),("Hind",HIND)):
        for suffix,side in (("L",1),("R",-1)):
            data=sweep_geometry(limb_profile,side=side)
            assign(f"Dragon_Leg_{end}_{suffix}",data["vertices"],data["faces"],skin_material,True,data["sides"])
            foot=foot_specs(end,side);vertices,faces=joint_geometry(*foot["palm"])
            assign(f"Dragon_Paw_{end}_{suffix}",vertices,faces,skin_material,True)
            for index,toe,claw in foot["digits"]:
                for kind,digit_profile,material in (("Toe",toe,skin_material),("Claw",claw,claw_material)):
                    data=sweep_geometry(digit_profile,steps=8,sides=20,side=side)
                    assign(f"Dragon_{kind}_{end}_{suffix}{index}",data["vertices"],data["faces"],material,sides=data["sides"])
    tail=sweep_geometry(TAIL,steps=16,sides=48)
    obj=assign("Dragon_Tail_Base",tail["vertices"],tail["faces"],skin_material,True,tail["sides"])
    obj.data.materials.append(underside_material)
    for polygon in obj.data.polygons:
        if polygon.index<len(tail["faces"])-2 and math.sin(2*math.pi*((polygon.index%tail["sides"])+.5)/tail["sides"])<-.75:
            polygon.material_index=1
    for name in ("Dragon_Tail_Mid","Dragon_Tail_Tip"):
        targets[name].hide_render=True;targets[name].hide_viewport=True;targets[name]["replaced_by"]="Dragon_Tail_Base"
    # Follow the actual new sweep's dorsal surface. Existing spine meshes survive.
    for i,t in enumerate((.12,.25,.38,.51,.64,.75,.84,.91)):
        index=round(t*(len(tail["centers"])-1));p=tail["centers"][index];normal,up=tail["frames"][index]
        anchor=tuple(p[k]+p[4]*up[k]*.93 for k in range(3));height=.32*(1-t)+.025
        if i<4:
            obj=targets[f"Dragon_Tail_Spike_{i+1:02}"]
            obj.location=(anchor[0],anchor[1],anchor[2]+obj.dimensions.z*.42)
        else:
            profile=(anchor,(anchor[0]+.04,anchor[1],anchor[2]+height*.5,.04,.04),
                     (anchor[0]+.10,anchor[1],anchor[2]+height,.002,.002))
            profile=((anchor[0],anchor[1],anchor[2],.055*(1-t)+.015,.055*(1-t)+.015),)+profile[1:]
            data=sweep_geometry(profile,steps=8,sides=16)
            assign(f"Dragon_Tail_DistalSpine_{i-3}",data["vertices"],data["faces"],underside_material)
    return {"changed_objects":sorted(TARGET_OBJECTS),"replaced_meshes":replaced,"added_objects":added,
            "hidden_replaced_proxies":["Dragon_Tail_Mid","Dragon_Tail_Tip"],
            "tail_vertices":len(tail["vertices"]),"tail_faces":len(tail["faces"]),
            "digits_per_foot":4,"whole_dragon_fused":False}
