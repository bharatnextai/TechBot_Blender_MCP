"""Deterministic wing-only modeling utility for disposable background fixtures.

No network tool, arbitrary-code interface, file I/O, or external dependencies.
Coordinates are in meters relative to the preserved shoulder attachment.
"""
import math
import threading


WRIST = (-1.2, 2.35, 1.35)
# Leading elbow, shoulder, inboard anchor, and four distal finger tips.
ANCHORS = ((-0.9, 1.0, 0.7), (0.0, -0.5, 0.0), (1.3, -0.6, -0.35),
           (3.1, 1.45, -0.3), (2.8, 3.25, 0.2), (1.25, 4.35, 1.1),
           (-0.6, 4.65, 2.1))


def membrane_geometry(side=1, root=(0.0, 1.35, 1.8), radial=18, spans=14, scallop=0.22):
    """Return one welded open disk of mostly quads, with six tension panels."""
    if side not in (-1, 1) or isinstance(side, bool):
        raise ValueError("side must be -1 or 1")
    if not isinstance(radial, int) or not isinstance(spans, int) or not 2 <= radial <= 64 or not 2 <= spans <= 64:
        raise ValueError("radial/spans must be integers in 2..64")
    if len(root) != 3 or not all(math.isfinite(v) for v in root) or not math.isfinite(scallop) or not 0 <= scallop <= 0.3:
        raise ValueError("Invalid shoulder/scallop")
    def world(p):
        return (root[0] + p[0], root[1] + side * p[1], root[2] + p[2])
    count = (len(ANCHORS) - 1) * spans + 1
    outer = []
    phases = []
    for j in range(count):
        panel = min(j // spans, len(ANCHORS) - 2)
        u = (j - panel * spans) / spans
        a, b = ANCHORS[panel:panel + 2]
        wave = math.sin(math.pi * u)
        depth = scallop if panel >= 2 else 0.04
        amount = depth * wave
        outer.append(tuple((1 - amount) * ((1 - u) * a[k] + u * b[k]) + amount * WRIST[k] for k in range(3)))
        phases.append(wave)
    vertices, uv = [world(WRIST)], [(0.0, 0.0)]
    for ring in range(1, radial + 1):
        t = ring / radial
        for j, boundary in enumerate(outer):
            p = [(1 - t) * WRIST[k] + t * boundary[k] for k in range(3)]
            p[2] += 0.12 * math.sin(math.pi * t) * phases[j]
            vertices.append(world(p))
            uv.append((t, j / (count - 1)))
    faces = [(0, 1 + j, 2 + j) for j in range(count - 1)]
    for ring in range(1, radial):
        lo, hi = 1 + (ring - 1) * count, 1 + ring * count
        for j in range(count - 1):
            faces.append((lo + j, hi + j, hi + j + 1, lo + j + 1))
    if side < 0:
        faces = [tuple(reversed(face)) for face in faces]
    ribs = [[world(ANCHORS[1]), world(ANCHORS[0]), world(WRIST), world(ANCHORS[-1])]]
    ribs += [[world(WRIST), world(ANCHORS[i])] for i in (5, 4, 3, 2)]
    return {"vertices": vertices, "faces": faces, "uv": uv, "ribs": ribs,
            "boundary": [world(p) for p in outer], "panels": len(ANCHORS) - 1}


def _tube_mesh(points, radius=0.055, sides=10):
    """Capped connected ribs; interpolated rings follow the structural paths."""
    def normalized(v):
        length = math.sqrt(sum(x * x for x in v))
        return tuple(x / length for x in v)
    def cross(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    centers = []
    for segment in range(len(points) - 1):
        for j in range(8):
            t = j / 8
            centers.append(tuple((1-t)*points[segment][k] + t*points[segment+1][k] for k in range(3)))
    centers.append(points[-1])
    vertices, faces = [], []
    for i, p in enumerate(centers):
        a, b = centers[max(0, i-1)], centers[min(len(centers)-1, i+1)]
        tangent = normalized(tuple(b[k]-a[k] for k in range(3)))
        normal = normalized(cross(tangent, (0, 0, 1) if abs(tangent[2]) < 0.9 else (0, 1, 0)))
        bitangent = cross(tangent, normal)
        taper = radius * (1 - 0.65 * i / (len(centers)-1))
        for j in range(sides):
            angle = 2*math.pi*j/sides
            vertices.append(tuple(p[k]+taper*(math.cos(angle)*normal[k]+math.sin(angle)*bitangent[k]) for k in range(3)))
    for i in range(len(centers)-1):
        for j in range(sides):
            a, b = i*sides+j, i*sides+(j+1)%sides
            faces.append((a, b, b+sides, a+sides))
    faces += [tuple(reversed(range(sides))), tuple((len(centers)-1)*sides+j for j in range(sides))]
    return vertices, faces


def replace_wing_membranes(bpy_module, membrane_material, rib_material):
    """Change only named wing objects in an explicitly isolated factory fixture.

    This is a trusted modeling fixture utility, not a remotely callable operation.
    All callers must run on Blender's main thread. Default/interactive use fails.
    """
    if threading.current_thread() is not threading.main_thread():
        raise PermissionError("Wing generation must run on Blender's main thread")
    from .bridge.handlers import _local_test_autoapproval
    if not _local_test_autoapproval(bpy_module, "create_primitive", {}):
        raise PermissionError("Wing generation requires the isolated local background test profile")
    specs = []
    for suffix, side in (("L", 1), ("R", -1)):
        names = [f"Wing_{suffix}_Proxy", f"Dragon_Wing_Spar_{suffix}",
                 f"Dragon_Wing_Finger_{suffix}1", f"Dragon_Wing_Finger_{suffix}2"]
        objects = [bpy_module.data.objects.get(n) for n in names]
        if any(o is None or o.type != "MESH" for o in objects):
            raise ValueError(f"Missing expected wing mesh group: {suffix}")
        for i in (3, 4):
            if bpy_module.data.objects.get(f"Dragon_Wing_Finger_{suffix}{i}"):
                raise ValueError("New finger name already exists; refusing duplicate generation")
        specs.append((suffix, objects, membrane_geometry(side, tuple(objects[0].location))))
    result = []
    for suffix, objects, data in specs:
        membrane = objects[0]
        mesh = bpy_module.data.meshes.new(f"Dragon_Membrane_{suffix}")
        mesh.from_pydata(data["vertices"], [], data["faces"])
        mesh.update()
        if mesh.validate():
            raise ValueError("Generated membrane needed mesh repair")
        layer = mesh.uv_layers.new(name="WingUV")
        for loop in mesh.loops:
            layer.data[loop.index].uv = data["uv"][loop.vertex_index]
        membrane.data = mesh
        membrane.location = (0, 0, 0)
        membrane.rotation_euler = (0, 0, 0)
        membrane.scale = (1, 1, 1)
        mesh.materials.append(membrane_material)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        solidify = membrane.modifiers.new("Membrane thickness", "SOLIDIFY")
        solidify.thickness = 0.024
        solidify.offset = 0
        solidify.use_even_offset = True
        for index, path in enumerate(data["ribs"]):
            vertices, faces = _tube_mesh(path, 0.07 if index == 0 else 0.045)
            rib = bpy_module.data.meshes.new(f"Wing_Rib_{suffix}_{index}")
            rib.from_pydata(vertices, [], faces)
            rib.update()
            if index < 3:
                obj = objects[index + 1]
                obj.data = rib
            else:
                obj = bpy_module.data.objects.new(f"Dragon_Wing_Finger_{suffix}{index}", rib)
                membrane.users_collection[0].objects.link(obj)
            obj.location = (0, 0, 0)
            obj.rotation_euler = (0, 0, 0)
            obj.scale = (1, 1, 1)
            rib.materials.append(rib_material)
            for polygon in rib.polygons:
                polygon.use_smooth = True
        result.append({"side": suffix, "object": membrane.name, "vertices": len(mesh.vertices),
                       "faces": len(mesh.polygons), "panels": data["panels"], "thickness": solidify.thickness})
    return result
