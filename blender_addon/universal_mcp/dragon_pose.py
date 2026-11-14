"""Isolated silhouette refinement with shared body warp and rigid detail groups."""
import math
import threading

HEAD_SHIFT = (.40,0.0,1.00)
WING_PITCH = math.radians(8)
WING_ROLL = math.radians(8)
NEAR_WING_ROLL = math.radians(-14)
BODY_MESHES = frozenset({"Dragon_Torso","Dragon_Armor_Neck","Dragon_Armor_Torso",
                         "Dragon_Armor_Throat","Dragon_Armor_Belly"})


def smoothstep(t):
    t=max(0.0,min(1.0,t));return t*t*(3-2*t)


def body_point(point):
    """Monotonic x mapping; shared by the body and all attached scale fields."""
    if len(point)!=3 or not all(math.isfinite(v) for v in point):raise ValueError("Invalid body point")
    x,y,z=point
    lift=smoothstep((-.85-x)/1.35)
    waist=math.exp(-((x-.60)/.65)**2)*smoothstep((x-.10)/.25)*smoothstep((1.65-x)/.30)
    return (x+HEAD_SHIFT[0]*lift,y*(1-.12*waist),1.4+(z-1.4)*(1-.10*waist)+HEAD_SHIFT[2]*lift)


def head_point(point):
    return tuple(point[k]+HEAD_SHIFT[k] for k in range(3))


def wing_point(point,side):
    """Rigid rotation around each shoulder; the hero near wing drapes lower."""
    if side not in (-1,1):raise ValueError("Invalid wing side")
    x,y,z=point[0],side*point[1]-.85,point[2]-1.8
    c,s=math.cos(WING_PITCH),math.sin(WING_PITCH)
    x,z=c*x+s*z,-s*x+c*z
    roll=WING_ROLL if side>0 else NEAR_WING_ROLL
    c,s=math.cos(roll),math.sin(roll)
    y,z=c*y-s*z,s*y+c*z
    return (x,side*(y+.85),z+1.8)


def group_for(name):
    if name in ("Wing_L_Proxy","Wing_R_Proxy"):return "wing_L" if name=="Wing_L_Proxy" else "wing_R"
    if name.startswith("WingAnatomy_"):
        return "wing_L" if "_L_" in name or name.endswith("_L") else "wing_R"
    if name.startswith("Dragon_Wing_"):
        return "wing_L" if "_L" in name else "wing_R"
    prefixes=("Dragon_Horn_","Dragon_Eye","Dragon_Pupil_","Dragon_Nostril_",
              "Dragon_UpperTooth_","Dragon_LowerTooth_","Dragon_Oral_",
              "Dragon_Armor_Cheek_","Dragon_Armor_Brow_","Dragon_Armor_TemporalHorn_")
    if name in ("Dragon_Head_Jaw","Dragon_Armor_Head") or name.startswith(prefixes):return "head"
    if name in BODY_MESHES:return "body"
    if name.startswith("Dragon_Back_Spike_"):return "spine"
    return None


def refine_dragon_pose(bpy_module):
    """Repose the isolated v0.1.37 asset without rebuilding surface detail."""
    if threading.current_thread() is not threading.main_thread():
        raise PermissionError("Pose refinement must run on Blender's main thread")
    from .bridge.handlers import _local_test_autoapproval
    if not _local_test_autoapproval(bpy_module,"create_primitive",{}):
        raise PermissionError("Pose refinement requires the isolated local background test profile")
    if bpy_module.context.scene.get("dragon_pose_0138"):
        raise ValueError("Refusing duplicate pose refinement")
    if any(bpy_module.data.objects.get(n) is None for n in BODY_MESHES):raise ValueError("Missing v0.1.37 body surfaces")
    from mathutils import Matrix,Vector
    def wing_matrix(side):
        origin=Vector(wing_point((0,0,0),side))
        columns=[Vector(wing_point(p,side))-origin for p in ((1,0,0),(0,1,0),(0,0,1))]
        matrix=Matrix.Identity(4)
        for i in range(3):
            for j in range(3):matrix[i][j]=columns[j][i]
            matrix[i][3]=origin[i]
        return matrix
    groups={"head":[],"body":[],"wing_L":[],"wing_R":[],"spine":[]}
    for obj in list(bpy_module.context.scene.objects):
        group=group_for(obj.name)
        if group is None:continue
        groups[group].append(obj.name)
        if group=="body":
            if obj.type!="MESH" or obj.data.users!=1:raise ValueError("Expected a unique body mesh: "+obj.name)
            inverse=obj.matrix_world.inverted()
            for v in obj.data.vertices:v.co=inverse@Vector(body_point(obj.matrix_world@v.co))
            obj.data.update()
        elif group=="head":obj.matrix_world=Matrix.Translation(Vector(HEAD_SHIFT))@obj.matrix_world
        elif group.startswith("wing_"):obj.matrix_world=wing_matrix(1 if group=="wing_L" else -1)@obj.matrix_world
        else:
            anchor=tuple(obj.matrix_world.translation)
            delta=Vector(body_point(anchor))-Vector(anchor)
            obj.matrix_world=Matrix.Translation(delta)@obj.matrix_world
    bpy_module.context.scene["dragon_pose_0138"]=True
    return {"groups":groups,"mesh_targets":sorted(BODY_MESHES),"changed_objects":sorted(n for names in groups.values() for n in names),
            "head_shift":HEAD_SHIFT,"wing_pitch_degrees":math.degrees(WING_PITCH),"wing_roll_degrees":{"L":math.degrees(WING_ROLL),"R":math.degrees(NEAR_WING_ROLL)},
            "added_objects":[],"whole_dragon_fused":False}
