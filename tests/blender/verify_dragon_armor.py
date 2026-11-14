"""Independent save/reload preservation, shell and attachment tests for v0.1.36."""
import bpy,bmesh,os,sys,json,hashlib,unittest
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path.cwd()))
from blender_addon.universal_mcp.dragon_armor import TARGET_OBJECTS,surface_sample
root=Path(os.environ["UMCP_LOCAL_TEST_ROOT"])
def object_snapshot(obj):
 value={"matrix":[list(row) for row in obj.matrix_world],"type":obj.type,"hide_render":obj.hide_render,"hide_viewport":obj.hide_viewport,"materials":[s.material.name if s.material else None for s in obj.material_slots],"modifiers":[(m.name,m.type,m.show_viewport,m.show_render) for m in obj.modifiers]}
 if obj.type=="MESH":value.update(vertices=[list(v.co) for v in obj.data.vertices],faces=[list(f.vertices) for f in obj.data.polygons],face_settings=[(f.material_index,f.use_smooth) for f in obj.data.polygons],uv=[[[float(x) for x in d.uv] for d in layer.data] for layer in obj.data.uv_layers])
 if obj.type=="LIGHT":value.update(energy=obj.data.energy,color=list(obj.data.color),kind=obj.data.type,size=getattr(obj.data,"size",None),radius=getattr(obj.data,"shadow_soft_size",None))
 if obj.type=="CAMERA":value.update(lens=obj.data.lens,type=obj.data.type,scale=obj.data.ortho_scale,shift=[obj.data.shift_x,obj.data.shift_y],clip=[obj.data.clip_start,obj.data.clip_end])
 return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def graph_snapshot(material):
 nodes=[];links=[]
 if material.use_nodes and material.node_tree:
  for node in material.node_tree.nodes:
   inputs=[]
   for socket in node.inputs:
    if hasattr(socket,"default_value"):
     value=socket.default_value
     if not isinstance(value,(str,int,float,bool,type(None))):
      try:value=list(value)
      except TypeError:continue
     inputs.append((socket.name,value))
   nodes.append((node.name,node.bl_idname,list(node.location),inputs))
  links=[(l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name) for l in material.node_tree.links]
 return hashlib.sha256(json.dumps({"nodes":nodes,"links":links,"use_nodes":material.use_nodes},sort_keys=True).encode()).hexdigest()


bpy.ops.wm.open_mainfile(filepath=str(root/"source_copy.blend"));bpy.context.view_layer.update()
original_names={o.name for o in bpy.context.scene.objects}
objects={o.name:object_snapshot(o) for o in bpy.context.scene.objects if o.name not in TARGET_OBJECTS}
materials={m.name:graph_snapshot(m) for m in bpy.data.materials}
world=graph_snapshot(bpy.context.scene.world);world_color=list(bpy.context.scene.world.color)
modifiers={o.name:[(m.name,m.type,getattr(m,"thickness",None),getattr(m,"offset",None)) for m in o.modifiers] for o in bpy.context.scene.objects if o.name not in TARGET_OBJECTS}
render={k:getattr(bpy.context.scene.render,k) for k in ("engine","resolution_x","resolution_y","resolution_percentage","filepath","film_transparent")}
cycles={k:getattr(bpy.context.scene.cycles,k) for k in ("samples","seed","device")}
file_format=bpy.context.scene.render.image_settings.file_format
bpy.ops.wm.open_mainfile(filepath=str(root/"dragon_armor_scales_v0.1.36.blend"));bpy.context.view_layer.update()
result=json.loads((root/"result.json").read_text())["modeling"];rows=[];attachments=[]

class TestSavedDragonArmor(unittest.TestCase):
 def test_original_anatomy_wings_materials_world_camera_preserved(self):
  self.assertEqual(len(objects),123)
  self.assertTrue(original_names.issubset({o.name for o in bpy.context.scene.objects}))
  self.assertEqual(len(bpy.context.scene.objects),141)
  for name,value in objects.items():self.assertEqual(object_snapshot(bpy.data.objects[name]),value,name)
  for name,value in materials.items():self.assertEqual(graph_snapshot(bpy.data.materials[name]),value,name)
  self.assertEqual(graph_snapshot(bpy.context.scene.world),world);self.assertEqual(list(bpy.context.scene.world.color),world_color)
  for name,value in modifiers.items():self.assertEqual([(m.name,m.type,getattr(m,"thickness",None),getattr(m,"offset",None)) for m in bpy.data.objects[name].modifiers],value,name)
  for k,v in render.items():self.assertEqual(getattr(bpy.context.scene.render,k),v)
  for k,v in cycles.items():self.assertEqual(getattr(bpy.context.scene.cycles,k),v)
  self.assertEqual(bpy.context.scene.render.image_settings.file_format,file_format)
  self.assertEqual(bpy.context.scene.camera.name,"Camera")
  self.assertFalse(any(o.name.startswith("WingComparison_") for o in bpy.context.scene.objects))

 def test_every_plate_and_horn_shell_is_closed_positive_after_reload(self):
  for name in result["changed_objects"]+result["added_objects"]:
   data=bpy.data.objects[name].data;bm=bmesh.new();bm.from_mesh(data)
   bad=sum(not edge.is_manifold for edge in bm.edges);self.assertEqual(bad,0,name)
   self.assertTrue(all(f.calc_area()>1e-12 for f in bm.faces),name)
   remaining=set(bm.verts);components=0;minimum=1e10
   while remaining:
    components+=1;first=remaining.pop();stack=[first];faces=set();origin=first.co
    while stack:
     v=stack.pop();faces.update(v.link_faces)
     for edge in v.link_edges:
      for other in edge.verts:
       if other in remaining:remaining.remove(other);stack.append(other)
    volume=0
    for face in faces:
     verts=list(face.verts);a=verts[0].co-origin
     for j in range(1,len(verts)-1):volume+=a.dot((verts[j].co-origin).cross(verts[j+1].co-origin))/6
    self.assertGreater(volume,1e-14,(name,components,volume));minimum=min(minimum,volume)
   self.assertEqual(components,result["plate_counts"].get(name,1),name)
   rows.append({"name":name,"vertices":len(data.vertices),"faces":len(data.polygons),"components":components,"nonmanifold_edges":bad,"minimum_shell_volume":minimum});bm.free()
  self.assertEqual(len(rows),18)

 def test_scale_ridges_follow_preserved_surface_and_declared_direction(self):
  for name,record in result["attachments"].items():
   obj=bpy.data.objects[record["source"]];vertices=[tuple(obj.matrix_world@v.co) for v in obj.data.vertices]
   sides=32 if "Leg_" in record["source"] else 48
   scale_mesh=bpy.data.objects[name].data
   for i,spec in enumerate(record["specs"]):
    p,n=surface_sample(vertices,sides,spec["t"]-.08*spec["dt"],spec["u"],record["side"])
    actual=scale_mesh.vertices[i*20+12].co
    delta=actual-Vector(p);normal=Vector(n)
    self.assertAlmostEqual(delta.dot(normal),spec["height"]*1.18,places=6)
    self.assertLess((delta-normal*delta.dot(normal)).length,1e-6)
   attachments.append({"name":name,"source":record["source"],"plates_checked":len(record["specs"])})
  self.assertEqual(len(attachments),12)

 def test_horn_symmetry_materials_and_scale_region_persistence(self):
  left=bpy.data.objects["Dragon_Horn_L"].data;right=bpy.data.objects["Dragon_Horn_R"].data
  self.assertEqual(len(left.vertices),len(right.vertices))
  for a,b in zip(left.vertices,right.vertices):
   self.assertAlmostEqual(a.co.x,b.co.x);self.assertAlmostEqual(a.co.y,-b.co.y);self.assertAlmostEqual(a.co.z,b.co.z)
  self.assertGreater(max(v.co.x for v in left.vertices),-1.7)
  self.assertTrue(any(p.material_index==1 for p in left.polygons))
  self.assertEqual(len(bpy.data.materials),11)
  for name in result["new_materials"]:
   material=bpy.data.materials[name];self.assertTrue(material.node_tree)
   self.assertFalse(any(n.type=="TEX_IMAGE" for n in material.node_tree.nodes))
  self.assertGreater(result["plate_counts"]["Dragon_Armor_Torso"],result["plate_counts"]["Dragon_Armor_Head"])

selected=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
suite=unittest.defaultTestLoader.loadTestsFromNames(selected,module=sys.modules[__name__]) if selected else unittest.defaultTestLoader.loadTestsFromTestCase(TestSavedDragonArmor)
test_result=unittest.TextTestRunner(verbosity=2).run(suite)
assert test_result.wasSuccessful(),"Saved armor regression failure"
(root/"saved_verification.json").write_text(json.dumps({"status":"PASS","tests_run":test_result.testsRun,"original_objects_unchanged":len(objects),"original_names_preserved":len(original_names),"original_material_graphs_unchanged":len(materials),"world_and_camera_preserved":True,"scene_objects":len(bpy.context.scene.objects),"new_mesh_checks":rows,"attachment_checks":attachments,"whole_dragon_fused":False},indent=2))
