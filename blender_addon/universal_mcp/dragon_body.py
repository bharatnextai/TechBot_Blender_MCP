"""Head/neck/torso lofting for explicitly isolated dragon modeling fixtures.

No public tool or authorization change. The wings and unrelated objects are
untouched; the core is one connected mesh, with a separately articulated jaw.
"""
import math
import threading
from .wing_anatomy import joint_geometry


TARGET_OBJECTS = frozenset({"Dragon_Torso", "Dragon_Neck_Base", "Dragon_Head_Cranium",
                            "Dragon_Head_Snout", "Dragon_Head_Jaw"})
# x, center height, lateral radius, vertical radius; ordered nose to tail base.
CORE_PROFILE = ((-3.67,2.53,0.025,0.04),(-3.55,2.54,0.15,0.12),
                (-3.30,2.57,0.25,0.17),(-3.04,2.62,0.33,0.24),
                (-2.80,2.68,0.42,0.35),(-2.56,2.65,0.43,0.40),
                (-2.25,2.49,0.32,0.40),(-1.91,2.26,0.39,0.47),
                (-1.45,1.96,0.57,0.64),(-1.03,1.59,0.83,0.86),
                (-0.42,1.46,0.91,1.00),(0.28,1.44,0.79,0.99),
                (0.85,1.41,0.73,0.98),(1.28,1.38,0.75,0.96),
                (1.72,1.23,0.53,0.70),(2.08,1.07,0.28,0.32),
                (2.17,1.06,0.035,0.05))
JAW_PROFILE = ((-3.61,2.13,0.025,0.025),(-3.48,2.15,0.13,0.055),
               (-3.24,2.18,0.235,0.075),(-2.98,2.23,0.29,0.10),
               (-2.73,2.32,0.29,0.12),(-2.56,2.38,0.13,0.09),
               (-2.50,2.39,0.025,0.035))


def _gauss(x,center,width):
    return math.exp(-((x-center)/width)**2)


def _angular(theta,center,width):
    distance=math.atan2(math.sin(theta-center),math.cos(theta-center))
    return math.exp(-(distance/width)**2)


def loft_geometry(profile=CORE_PROFILE,steps=10,sides=48,anatomical=True):
    """Closed star-section loft with strictly ordered x rings and muscle relief."""
    if not isinstance(steps,int) or not 3<=steps<=32 or not isinstance(sides,int) or not 16<=sides<=96:
        raise ValueError("Loft density outside supported limits")
    if len(profile)<3 or any(len(p)!=4 or not all(math.isfinite(v) for v in p) or min(p[2:])<=0 for p in profile):
        raise ValueError("Invalid cross-section profile")
    if any(b[0]<=a[0] for a,b in zip(profile,profile[1:])):
        raise ValueError("Profile x positions must increase")
    rings=[]
    for i in range(len(profile)-1):
        a,b=profile[i:i+2];prev=profile[max(0,i-1)];nxt=profile[min(len(profile)-1,i+2)]
        for j in range(steps):
            t=j/steps
            values=[(1-t)*a[0]+t*b[0]]
            for k in range(1,4):
                value=0.5*((2*a[k])+(-prev[k]+b[k])*t+(2*prev[k]-5*a[k]+4*b[k]-nxt[k])*t*t+(-prev[k]+3*a[k]-3*b[k]+nxt[k])*t*t*t)
                values.append(max(0.012,value) if k>1 else value)
            rings.append(values)
    rings.append(profile[-1]);vertices=[]
    for x,z,width,height in rings:
        for j in range(sides):
            theta=2*math.pi*j/sides;c,s=math.cos(theta),math.sin(theta)
            muscle=0
            if anatomical:
                lateral=_angular(theta,-0.55,0.50)+_angular(theta,math.pi+0.55,0.50)
                muscle=(0.10*_gauss(x,-0.98,0.33)+0.12*_gauss(x,1.12,0.35))*lateral
                muscle+=0.12*_gauss(x,-2.79,0.22)*(_angular(theta,0.55,0.3)+_angular(theta,math.pi-0.55,0.3))
                muscle+=0.07*_gauss(x,-2.56,0.20)*(_angular(theta,0,0.4)+_angular(theta,math.pi,0.4))
            exponent=0.78 if x<-2.42 else 1.0
            y=width*math.copysign(abs(c)**exponent,c)*(1+muscle)
            zz=z+height*math.copysign(abs(s)**exponent,s)*(1+0.6*muscle)
            vertices.append((x,y,zz))
    faces=[];belly=[]
    for i in range(len(rings)-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides
            faces.append((a,b,b+sides,a+sides))
            belly.append(bool(anatomical and -2.25<rings[i][0]<1.65 and math.sin(2*math.pi*(j+0.5)/sides)<-0.65))
    faces += [tuple(reversed(range(sides))),tuple((len(rings)-1)*sides+j for j in range(sides))]
    belly += [False,False]
    return {"vertices":vertices,"faces":faces,"belly":belly,"rings":len(rings),"sides":sides}


def spike_geometry(start,end,radius=0.018):
    """Small closed tapered tooth; no coincident zero-radius tip vertices."""
    tangent=[end[i]-start[i] for i in range(3)];length=math.sqrt(sum(v*v for v in tangent))
    if length<0.01 or not 0<radius<0.1:raise ValueError("Invalid tooth dimensions")
    tangent=[v/length for v in tangent]
    axis=(0,0,1) if abs(tangent[2])<0.9 else (0,1,0)
    normal=(tangent[1]*axis[2]-tangent[2]*axis[1],tangent[2]*axis[0]-tangent[0]*axis[2],tangent[0]*axis[1]-tangent[1]*axis[0]);size=math.sqrt(sum(v*v for v in normal));normal=[v/size for v in normal]
    bitangent=(tangent[1]*normal[2]-tangent[2]*normal[1],tangent[2]*normal[0]-tangent[0]*normal[2],tangent[0]*normal[1]-tangent[1]*normal[0])
    vertices=[];faces=[];sides=12;rings=8
    for i in range(rings):
        t=i/(rings-1);r=max(0.0005,radius*(1-t)**0.8)
        for j in range(sides):
            theta=2*math.pi*j/sides
            vertices.append(tuple(start[k]+t*(end[k]-start[k])+r*(math.cos(theta)*normal[k]+math.sin(theta)*bitangent[k]) for k in range(3)))
    for i in range(rings-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides;faces.append((a,b,b+sides,a+sides))
    faces.extend((tuple(reversed(range(sides))),tuple((rings-1)*sides+j for j in range(sides))))
    return vertices,faces


def model_head_body(bpy_module,skin_material,belly_material,dark_material,eye_material):
    """Replace only five named proxies in a disposable main-thread fixture."""
    if threading.current_thread() is not threading.main_thread():
        raise PermissionError("Body modeling must run on Blender's main thread")
    from .bridge.handlers import _local_test_autoapproval
    if not _local_test_autoapproval(bpy_module,"create_primitive",{}):
        raise PermissionError("Body modeling requires the isolated local background test profile")
    if bpy_module.data.collections.get("DragonFace_0134"):
        raise ValueError("Refusing duplicate head/body modeling")
    targets={name:bpy_module.data.objects.get(name) for name in TARGET_OBJECTS}
    if any(obj is None or obj.type!="MESH" for obj in targets.values()):
        raise ValueError("Missing the expected v0.1.33 head/body proxies")
    core=loft_geometry();jaw=loft_geometry(JAW_PROFILE,steps=10,sides=48,anatomical=False)
    def mesh(name,vertices,faces):
        data=bpy_module.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
        if data.validate():raise ValueError("Generated body mesh required repair")
        for polygon in data.polygons:polygon.use_smooth=True
        return data
    for name,data in (("Dragon_Torso",core),("Dragon_Head_Jaw",jaw)):
        obj=targets[name];obj.data=mesh(name+"_Organic",data["vertices"],data["faces"])
        obj.location=(0,0,0);obj.rotation_euler=(0,0,0);obj.scale=(1,1,1)
        for modifier in list(obj.modifiers):obj.modifiers.remove(modifier)
        obj.data.materials.append(skin_material)
        if name=="Dragon_Torso":
            obj.data.materials.append(belly_material)
            for polygon,underside in zip(obj.data.polygons,data["belly"]):polygon.material_index=int(underside)
        uv=obj.data.uv_layers.new(name="BodyUV")
        for polygon in obj.data.polygons:
            indices=list(polygon.vertices);wrap=any(i%data["sides"]==0 for i in indices) and any(i%data["sides"]==data["sides"]-1 for i in indices)
            for loop_index in polygon.loop_indices:
                i=obj.data.loops[loop_index].vertex_index;u=(i//data["sides"])/(data["rings"]-1);v=(i%data["sides"])/data["sides"]
                uv.data[loop_index].uv=(u,1.0 if wrap and v==0 else v)
    for name in ("Dragon_Neck_Base","Dragon_Head_Cranium","Dragon_Head_Snout"):
        targets[name].hide_render=True;targets[name].hide_viewport=True
        targets[name]["replaced_by"]="Dragon_Torso"
    collection=bpy_module.data.collections.new("DragonFace_0134");bpy_module.context.scene.collection.children.link(collection);added=[]
    def add(name,geometry,material):
        vertices,faces=geometry;data=mesh(name,vertices,faces);data.materials.append(material);obj=bpy_module.data.objects.new(name,data);collection.objects.link(obj);added.append(name)
    add("Dragon_Oral_Lining",joint_geometry((-3.12,0,2.32),(0.43,0.18,0.065)),dark_material)
    for side in (-1,1):
        suffix="L" if side>0 else "R"
        add("Dragon_EyeSocket_"+suffix,joint_geometry((-2.83,side*0.38,2.82),(0.11,0.035,0.075)),dark_material)
        add("Dragon_Eye_"+suffix,joint_geometry((-2.83,side*0.415,2.82),(0.055,0.025,0.048)),eye_material)
        add("Dragon_Pupil_"+suffix,joint_geometry((-2.84,side*0.439,2.82),(0.010,0.009,0.037)),dark_material)
        add("Dragon_Nostril_"+suffix,joint_geometry((-3.41,side*0.205,2.61),(0.047,0.018,0.028)),dark_material)
        for index in range(5):
            x=-3.43+index*0.095;y=side*(0.14+index*0.025)
            add(f"Dragon_UpperTooth_{suffix}{index}",spike_geometry((x,y,2.405),(x-0.012,y,2.34)),belly_material)
        for index in range(3):
            x=-3.36+index*0.15;y=side*(0.16+index*0.03)
            add(f"Dragon_LowerTooth_{suffix}{index}",spike_geometry((x,y,2.245),(x-0.008,y,2.285),0.014),belly_material)
    return {"changed_objects":sorted(TARGET_OBJECTS),"core_object":"Dragon_Torso",
            "jaw_object":"Dragon_Head_Jaw","hidden_replaced_proxies":["Dragon_Neck_Base","Dragon_Head_Cranium","Dragon_Head_Snout"],
            "added_objects":added,"core_vertices":len(core["vertices"]),"core_faces":len(core["faces"]),
            "whole_dragon_fused":False}
