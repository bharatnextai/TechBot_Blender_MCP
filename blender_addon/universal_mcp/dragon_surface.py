"""Organic surface refinement, restricted to disposable main-thread fixtures."""
import math
import random
import threading

from .dragon_armor import surface_sample, x_parameter
from .dragon_limbs_tail import sweep_geometry

SCALE_SIDES = 12
SCALE_VERTICES = 50
RIDGE_INDEX = 36
FIELD_NAMES = ("Head","Neck","Torso","Throat","Belly","Tail",
               "Front_L","Front_R","Hind_L","Hind_R","Cheek_L","Cheek_R")
MESH_TARGETS = frozenset(["Dragon_Armor_"+n for n in FIELD_NAMES]
                         +["Dragon_Armor_Brow_L","Dragon_Armor_Brow_R"])


def rounded_scale(vertices,sides,spec,side=1):
    """Closed rounded, slightly asymmetric leaf fitted to the actual surface."""
    if not 0<spec["dt"]<.15 or not 0<spec["du"]<.3 or not 0<spec["height"]<.05:
        raise ValueError("Invalid organic scale dimensions")
    if not math.isfinite(spec["angle"]) or abs(spec["angle"])>.5:raise ValueError("Invalid scale orientation")
    rng=random.Random(spec["seed"]);phase=rng.uniform(0,2*math.pi)
    outline=[];angle=spec["angle"]
    for j in range(SCALE_SIDES):
        phi=2*math.pi*j/SCALE_SIDES
        radial=1+.055*math.sin(3*phi+phase)+.025*math.sin(5*phi-phase)
        a=.54*math.cos(phi)*radial+.035
        b=.50*math.sin(phi)*radial*(.91-.09*math.cos(phi))
        outline.append((a*math.cos(angle)-b*math.sin(angle),a*math.sin(angle)+b*math.cos(angle)))
    if side>0:outline.reverse()
    def sample(a,b,offset):
        p,n=surface_sample(vertices,sides,spec["t"]+a*spec["dt"],spec["u"]+b*spec["du"],side)
        return tuple(p[k]+offset*n[k] for k in range(3))
    h=spec["height"];points=[]
    for scale,offset in ((1,h*.08),(.80,h*.72),(.42,h*.98)):
        points.extend(sample(a*scale,b*scale,offset) for a,b in outline)
    points.append(sample(-.04,0,h))
    points.extend(sample(a,b,-min(.0008,h*.3)) for a,b in outline)
    points.append(sample(0,0,-min(.0008,h*.3)))
    faces=[];n=SCALE_SIDES
    for j in range(n):
        nxt=(j+1)%n
        faces.extend(((j,nxt,nxt+n,j+n),(j+n,nxt+n,nxt+2*n,j+2*n),
                      (j+2*n,nxt+2*n,3*n),(j,3*n+1+j,3*n+1+nxt,nxt),
                      (4*n+1,3*n+1+nxt,3*n+1+j)))
    return points,faces


def organic_specs(vertices,sides,start,end,length,width,region,seed=37):
    """Arc-length rows with adaptive circumference counts and bounded jitter."""
    if not 0<start<end<1 or not .025<=length<=.3 or not .025<=width<=.3:
        raise ValueError("Invalid field range or physical density")
    if region not in ("Head","Neck","Torso","Limb","Tail"):raise ValueError("Unknown surface region")
    rows=len(vertices)//sides
    centers=[tuple(sum(vertices[i*sides+j][k] for j in range(sides))/sides for k in range(3)) for i in range(rows)]
    def center(t):
        r=t*(rows-1);i=min(int(r),rows-2);f=r-i
        return tuple((1-f)*centers[i][k]+f*centers[i+1][k] for k in range(3))
    samples=[start+(end-start)*i/400 for i in range(401)];arc=[0]
    for a,b in zip(samples,samples[1:]):arc.append(arc[-1]+math.dist(center(a),center(b)))
    def parameter(distance):
        i=next(i for i in range(400) if arc[i]<=distance<=arc[i+1])
        return samples[i]+(samples[i+1]-samples[i])*(distance-arc[i])/(arc[i+1]-arc[i])
    rng=random.Random(seed);distance=length*.45;out=[];row=0
    while distance<arc[-1]-length*.35:
        q=distance/arc[-1];t=parameter(distance)
        adaptive=1-.55*q if region=="Tail" else 1
        step=length*.83*adaptive*rng.uniform(.87,1.13)
        next_t=parameter(min(arc[-1]-1e-8,distance+step))
        dt=(next_t-t)*1.24
        r=min(round(t*(rows-1)),rows-1)
        circumference=sum(math.dist(vertices[r*sides+j],vertices[r*sides+(j+1)%sides]) for j in range(sides))
        columns=max(8,min(44,round(circumference/(width*(1-.6*q if region=="Tail" else 1)))))
        offset=(row*.61803398875+rng.uniform(-.12,.12))%1
        for j in range(columns):
            u=((j+offset+rng.uniform(-.13,.13))/columns)%1
            if region in ("Head","Neck","Torso") and math.sin(2*math.pi*u)<(-.20 if region=="Head" else -.65):continue
            flow=.13*math.cos(2*math.pi*u)+rng.uniform(-.09,.09)
            tt=t+dt*flow
            h={"Head":.0065,"Neck":.0035,"Torso":.0035,"Limb":.0020,"Tail":.0025}[region]
            fade=.55+.45*math.sin(math.pi*q)**.5
            h*=fade*rng.uniform(.78,1.12)*(adaptive if region=="Tail" else 1)
            out.append({"t":tt,"u":u,"dt":dt*rng.uniform(.85,1.15),"du":1.16/columns*rng.uniform(.86,1.16),
                        "height":h,"angle":.20*math.sin(2*math.pi*u)+rng.uniform(-.15,.15),
                        "seed":seed+row*1009+j*9176,"variant":int(rng.random()<.18),"region":region})
        distance+=step;row+=1
    return out


def horn_collar(vertices,sides=16,side=1):
    """Low tapered root sleeve sampled from the unchanged primary horn rings."""
    if len(vertices)%sides or len(vertices)<sides*10 or side not in (-1,1):raise ValueError("Invalid horn grid")
    points=[];rings=8
    for i in range(rings):
        row=vertices[i*sides:(i+1)*sides];center=tuple(sum(v[k] for v in row)/sides for k in range(3))
        q=i/(rings-1)
        gain=1+.16*(1-q)**1.5-.035*q**4
        points.extend(tuple(center[k]+(v[k]-center[k])*gain for k in range(3)) for v in row)
    faces=[]
    for i in range(rings-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides;faces.append((a,b,b+sides,a+sides))
    faces.extend((tuple(reversed(range(sides))),tuple((rings-1)*sides+j for j in range(sides))))
    if side<0:faces=[tuple(reversed(f)) for f in faces]
    return points,faces


def refine_dragon_surface(bpy_module):
    """Refine only isolated armor meshes and explicitly recorded material slots."""
    if threading.current_thread() is not threading.main_thread():
        raise PermissionError("Surface refinement must run on Blender's main thread")
    from .bridge.handlers import _local_test_autoapproval
    if not _local_test_autoapproval(bpy_module,"create_primitive",{}):
        raise PermissionError("Surface refinement requires the isolated local background test profile")
    if bpy_module.data.collections.get("DragonSurface_0137"):raise ValueError("Refusing duplicate surface refinement")
    if any(bpy_module.data.objects.get(n) is None for n in MESH_TARGETS):raise ValueError("Missing v0.1.36 armor")
    original_material_names=[m.name for m in bpy_module.data.materials]
    collection=bpy_module.data.collections.new("DragonSurface_0137");bpy_module.context.scene.collection.children.link(collection)
    def shader_copy(source,name,low,high,rough,keratin=False):
        if bpy_module.data.materials.get(name):raise ValueError("Material collision: "+name)
        material=bpy_module.data.materials[source].copy();material.name=name
        nodes=material.node_tree.nodes;links=material.node_tree.links
        shader=next(n for n in nodes if n.type=="BSDF_PRINCIPLED")
        def node(kind,name):
            n=nodes.new(kind);n.name=name;return n
        position=node("ShaderNodeNewGeometry","SurfacePosition37")
        noise=node("ShaderNodeTexNoise","SurfaceMottle37");noise.inputs["Scale"].default_value=3.3;noise.inputs["Detail"].default_value=3
        links.new(position.outputs["Position"],noise.inputs["Vector"])
        ramp=node("ShaderNodeValToRGB","SurfaceColor37")
        ramp.color_ramp.elements[0].position=.18;ramp.color_ramp.elements[0].color=(*low,1)
        ramp.color_ramp.elements[1].position=.82;ramp.color_ramp.elements[1].color=(*high,1)
        links.new(noise.outputs["Fac"],ramp.inputs["Fac"]);links.new(ramp.outputs["Color"],shader.inputs["Base Color"])
        mapping=node("ShaderNodeMapRange","SurfaceRoughness37");mapping.inputs["To Min"].default_value=rough[0];mapping.inputs["To Max"].default_value=rough[1];mapping.clamp=True
        links.new(noise.outputs["Fac"],mapping.inputs["Value"]);links.new(mapping.outputs["Result"],shader.inputs["Roughness"])
        fine=node("ShaderNodeTexNoise","SurfaceGrain37");fine.inputs["Scale"].default_value=95;fine.inputs["Detail"].default_value=2
        if keratin:
            coord=node("ShaderNodeTexCoord","KeratinCoordinates37");stretch=node("ShaderNodeVectorMath","KeratinStriation37");stretch.operation="MULTIPLY";stretch.inputs[1].default_value=(2,25,25)
            links.new(coord.outputs["Generated"],stretch.inputs[0]);links.new(stretch.outputs["Vector"],fine.inputs["Vector"]);fine.inputs["Scale"].default_value=6
        else:links.new(position.outputs["Position"],fine.inputs["Vector"])
        bump=node("ShaderNodeBump","SurfaceMicrorelief37");bump.inputs["Strength"].default_value=.12;bump.inputs["Distance"].default_value=.0013
        previous=list(shader.inputs["Normal"].links)
        if previous:links.new(previous[0].from_socket,bump.inputs["Normal"])
        links.new(fine.outputs["Fac"],bump.inputs["Height"]);links.new(bump.outputs["Normal"],shader.inputs["Normal"])
        shader.inputs["Subsurface Weight"].default_value=.025
        return material
    red=shader_copy("Dragon_Armor_Red_0136","Dragon_Red_0137",(.080,.008,.0035),(.19,.026,.010),(.48,.72))
    dark=shader_copy("Dragon_Armor_Dark_0136","Dragon_Dark_Red_0137",(.068,.0065,.003),(.155,.020,.008),(.53,.75))
    skin=shader_copy("Dragon_Wing_Skin_0133","Dragon_Skin_0137",(.080,.010,.004),(.17,.026,.011),(.50,.73))
    bone=shader_copy("Dragon_Keratin_0136","Dragon_Keratin_0137",(.15,.105,.060),(.43,.33,.20),(.38,.57),True)
    tip=shader_copy("Dragon_Keratin_Tip_0136","Dragon_Tip_0137",(.012,.008,.004),(.047,.030,.014),(.32,.51),True)
    belly=shader_copy("Dragon_Ventral_0136","Dragon_Ventral_0137",(.23,.17,.095),(.40,.32,.20),(.53,.74))
    root=skin.copy();root.name="Dragon_Horn_Root_0137"
    nodes=root.node_tree.nodes;links=root.node_tree.links;shader=next(n for n in nodes if n.type=="BSDF_PRINCIPLED")
    coord=nodes.new("ShaderNodeTexCoord");coord.name="RootCoordinates37"
    separate=nodes.new("ShaderNodeSeparateXYZ");ramp=nodes.new("ShaderNodeValToRGB");ramp.name="RootTransition37"
    ramp.color_ramp.elements[0].position=.05;ramp.color_ramp.elements[0].color=(.12,.023,.010,1)
    ramp.color_ramp.elements[1].position=.95;ramp.color_ramp.elements[1].color=(.31,.23,.13,1)
    links.new(coord.outputs["Generated"],separate.inputs[0]);links.new(separate.outputs["X"],ramp.inputs[0]);links.new(ramp.outputs["Color"],shader.inputs["Base Color"])
    assignments={};original_names=[o.name for o in bpy_module.context.scene.objects]
    for name in original_names:
        obj=bpy_module.data.objects[name]
        if obj.type!="MESH" or not name.startswith("Dragon_") or name.startswith("Dragon_Wing_") or obj.hide_render:continue
        if name.startswith(("Dragon_Back_Spike_","Dragon_Tail_Spike_")) and not obj.data.materials:
            obj.data.materials.append(bone)
        mapped=[]
        for slot in obj.material_slots:
            m=slot.material;replacement=None
            if m:
                replacement={"Dragon_Armor_Red_0136":red,"Dragon_Armor_Dark_0136":dark,
                 "Dragon_Keratin_0136":bone,"Dragon_Keratin_Tip_0136":tip,"Dragon_Ventral_0136":belly,
                 "Dragon_Wing_Skin_0133":skin}.get(m.name)
                if m.name=="Material":replacement=belly if name in ("Dragon_Torso","Dragon_Tail_Base") else bone
                if name.startswith("Dragon_Claw_") and m.name=="Dragon_Wing_Veins_0133":replacement=tip
            if replacement:slot.material=replacement
            mapped.append(slot.material.name if slot.material else None)
        if any(slot.material and slot.material.name.endswith("0137") for slot in obj.material_slots):assignments[name]=mapped
    counts={};attachments={};added=[]
    def grid(name,sides):
        obj=bpy_module.data.objects[name];v=[tuple(obj.matrix_world@x.co) for x in obj.data.vertices]
        if len(v)%sides:raise ValueError("Unexpected preserved surface: "+name)
        return v
    def assign(name,vertices,faces,materials,indices=None,new=False):
        mesh=bpy_module.data.meshes.new(name+"_Refined");mesh.from_pydata(vertices,[],faces);mesh.update()
        if mesh.validate():raise ValueError("Organic surface required repair")
        for m in materials:mesh.materials.append(m)
        for polygon in mesh.polygons:
            polygon.use_smooth=True
            if indices:polygon.material_index=indices[polygon.index]
        if new:
            obj=bpy_module.data.objects.new(name,mesh);collection.objects.link(obj);added.append(name)
        else:obj=bpy_module.data.objects[name];obj.data=mesh
        assignments[name]=[m.name for m in materials]
    def field(name,source,sides,specs,side=1,ventral=False):
        vertices=[];faces=[];indices=[];v=grid(source,sides)
        for spec in specs:
            points,polys=rounded_scale(v,sides,spec,side);offset=len(vertices);vertices.extend(points)
            faces.extend(tuple(i+offset for i in f) for f in polys);indices.extend([spec["variant"]]*len(polys))
        assign(name,vertices,faces,[belly,bone] if ventral else [red,dark],indices)
        counts[name]=len(specs);attachments[name]={"source":source,"side":side,"specs":specs}
    core=grid("Dragon_Torso",48)
    for region,a,b,length,width in (("Head",-3.49,-2.38,.105,.13),("Neck",-2.46,-1.08,.13,.13),("Torso",-1.25,1.74,.15,.16)):
        specs=organic_specs(core,48,x_parameter(core,48,a),x_parameter(core,48,b),length,width,region)
        if region=="Head":
            specs=[s for s in specs if not (-3.05<surface_sample(core,48,s["t"],s["u"])[0][0]<-2.67 and min(abs(s["u"]-.065),abs(s["u"]-.435))<.10)]
            specs=[s for s in specs if not (surface_sample(core,48,s["t"],s["u"])[0][0]<-3.3 and min(abs(s["u"]-.065),abs(s["u"]-.435))<.07)]
        field("Dragon_Armor_"+region,"Dragon_Torso",48,specs)
    for region,a,b,rows in (("Throat",-2.26,-1.16,11),("Belly",-1.20,1.55,20)):
        start,end=x_parameter(core,48,a),x_parameter(core,48,b);specs=[]
        for i in range(rows):
            for j in range(3):specs.append({"t":start+(end-start)*(i+.5)/rows,"u":.75+(j-1)*.085,"dt":(end-start)/rows*1.40,"du":.16 if j==1 else .135,"height":.005,"angle":.05*math.sin(i*1.3+j),"seed":i*97+j,"variant":0})
        field("Dragon_Armor_"+region,"Dragon_Torso",48,specs,ventral=True)
    tail=grid("Dragon_Tail_Base",48)
    field("Dragon_Armor_Tail","Dragon_Tail_Base",48,organic_specs(tail,48,.025,.94,.10,.075,"Tail"))
    for end in ("Front","Hind"):
        for suffix,side in (("L",1),("R",-1)):
            source=f"Dragon_Leg_{end}_{suffix}";v=grid(source,32)
            field(f"Dragon_Armor_{end}_{suffix}",source,32,organic_specs(v,32,.06,.94,.075,.075,"Limb",37 if end=="Front" else 81),side)
    for suffix,side in (("L",1),("R",-1)):
        specs=[]
        for i,x in enumerate((-2.84,-2.73,-2.62,-2.51,-2.41)):
            specs.append({"t":x_parameter(core,48,x),"u":.975 if side>0 else .525,"dt":.018,"du":.067,"height":.009-i*.0007,"angle":.12*side,"seed":180+i,"variant":0})
        field("Dragon_Armor_Cheek_"+suffix,"Dragon_Torso",48,specs)
        brow=((-3.03,.30,2.83,.018,.024),(-2.85,.39,2.91,.035,.045),(-2.62,.40,2.97,.028,.035),(-2.48,.38,2.99,.006,.006))
        data=sweep_geometry(brow,steps=10,sides=16,side=side)
        assign("Dragon_Armor_Brow_"+suffix,data["vertices"],data["faces"],[dark])
        vertices,faces=horn_collar(grid("Dragon_Horn_"+suffix,16),side=side)
        assign("Dragon_Horn_Root_"+suffix,vertices,faces,[root],new=True)
    # Blender omits zero-user material datablocks from saved files unless retained.
    archived_materials=[]
    for name in original_material_names:
        material=bpy_module.data.materials[name]
        if material.users==0:
            material.use_fake_user=True;archived_materials.append(name)
    return {"mesh_targets":sorted(MESH_TARGETS),"material_assignments":assignments,"added_objects":added,
            "plate_counts":counts,"attachments":attachments,"new_materials":[m.name for m in (red,dark,skin,bone,tip,belly,root)],
            "archived_original_materials":archived_materials,
            "whole_dragon_fused":False,"external_textures_used":False}
