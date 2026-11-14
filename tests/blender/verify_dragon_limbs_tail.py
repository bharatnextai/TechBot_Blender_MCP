"""Independent Blender save/reload regressions for isolated v0.1.35 artifacts.
Run using the recorded background launcher and UMCP_LOCAL_TEST_ROOT.
"""
import bpy,bmesh,os,sys,json,hashlib,unittest
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from blender_addon.universal_mcp.dragon_limbs_tail import TARGET_OBJECTS
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
retained_meshes={name:([list(v.co) for v in bpy.data.objects[name].data.vertices],[list(f.vertices) for f in bpy.data.objects[name].data.polygons]) for name in TARGET_OBJECTS if name.startswith("Dragon_Tail_") and name!="Dragon_Tail_Base"}
bpy.ops.wm.open_mainfile(filepath=str(root/"dragon_limbs_tail_v0.1.35.blend"));bpy.context.view_layer.update()
result=json.loads((root/"result.json").read_text())["modeling"]
rows=[];wing_rows=[]

class TestSavedDragonLimbsTail(unittest.TestCase):
 def test_unrelated_objects_materials_world_camera_and_render_preserved(self):
  self.assertEqual(len(objects),74)
  self.assertTrue(original_names.issubset({o.name for o in bpy.context.scene.objects}))
  self.assertEqual(len(bpy.context.scene.objects),125)
  for name,value in objects.items():self.assertEqual(object_snapshot(bpy.data.objects[name]),value,name)
  for name,value in materials.items():self.assertEqual(graph_snapshot(bpy.data.materials[name]),value,name)
  self.assertEqual(graph_snapshot(bpy.context.scene.world),world);self.assertEqual(list(bpy.context.scene.world.color),world_color)
  for name,value in modifiers.items():self.assertEqual([(m.name,m.type,getattr(m,"thickness",None),getattr(m,"offset",None)) for m in bpy.data.objects[name].modifiers],value,name)
  for k,v in render.items():self.assertEqual(getattr(bpy.context.scene.render,k),v)
  for k,v in cycles.items():self.assertEqual(getattr(bpy.context.scene.cycles,k),v)
  self.assertEqual(bpy.context.scene.render.image_settings.file_format,file_format)
  self.assertEqual(bpy.context.scene.camera.name,"Camera")
  self.assertFalse(any(o.name.startswith("WingComparison_") for o in bpy.context.scene.objects))

 def test_geometry_remains_connected_manifold_and_positive_after_reload(self):
  for name in result["replaced_meshes"]+result["added_objects"]:
   mesh=bpy.data.objects[name].data;bm=bmesh.new();bm.from_mesh(mesh)
   bad=sum(not edge.is_manifold for edge in bm.edges);self.assertEqual(bad,0,name)
   remaining=set(bm.verts);components=0
   while remaining:
    components+=1;stack=[remaining.pop()]
    while stack:
     for edge in stack.pop().link_edges:
      for v in edge.verts:
       if v in remaining:remaining.remove(v);stack.append(v)
   self.assertEqual(components,1,name)
   volume=bm.calc_volume(signed=True);self.assertGreater(volume,0,name)
   self.assertTrue(all(f.calc_area()>1e-12 for f in bm.faces),name)
   rows.append({"name":name,"vertices":len(mesh.vertices),"faces":len(mesh.polygons),"components":components,"nonmanifold_edges":bad,"volume":volume});bm.free()
  self.assertEqual(len(rows),45)
  for obj in bpy.context.scene.objects:
   if obj.name.startswith("WingAnatomy_") or obj.name in ("Wing_L_Proxy","Wing_R_Proxy"):
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh();bm=bmesh.new();bm.from_mesh(mesh)
    bad=sum(not edge.is_manifold for edge in bm.edges);self.assertEqual(bad,0,obj.name)
    wing_rows.append({"name":obj.name,"nonmanifold_edges":bad});bm.free();evaluated.to_mesh_clear()
  self.assertEqual(len(wing_rows),20)

 def test_actual_legs_are_bilateral_and_span_shoulder_to_ankle(self):
  for end in ("Front","Hind"):
   left=bpy.data.objects[f"Dragon_Leg_{end}_L"].data
   right=bpy.data.objects[f"Dragon_Leg_{end}_R"].data
   self.assertEqual(len(left.vertices),len(right.vertices),end)
   for a,b in zip(left.vertices,right.vertices):
    self.assertAlmostEqual(a.co.x,b.co.x,places=6)
    self.assertAlmostEqual(a.co.y,-b.co.y,places=6)
    self.assertAlmostEqual(a.co.z,b.co.z,places=6)
   for mesh in (left,right):self.assertGreater(max(v.co.z for v in mesh.vertices)-min(v.co.z for v in mesh.vertices),1.2)

 def test_tail_archive_spines_digits_and_uvs_survive_reload(self):
  for name in ("Dragon_Tail_Mid","Dragon_Tail_Tip"):
   obj=bpy.data.objects[name];self.assertTrue(obj.hide_render and obj.hide_viewport)
   self.assertEqual(obj["replaced_by"],"Dragon_Tail_Base")
  for name,value in retained_meshes.items():
   data=bpy.data.objects[name].data;self.assertEqual(([list(v.co) for v in data.vertices],[list(f.vertices) for f in data.polygons]),value,name)
  for end in ("Front","Hind"):
   for side in ("L","R"):
    for digit in ("1","2","3","Dew"):
     for kind in ("Toe","Claw"):self.assertIn(f"Dragon_{kind}_{end}_{side}{digit}",bpy.data.objects)
  self.assertEqual(len(bpy.data.objects["Dragon_Tail_Base"].data.uv_layers),1)
  self.assertGreater(max(v.co.x for v in bpy.data.objects["Dragon_Tail_Base"].data.vertices),5.4)

selected=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
suite=unittest.defaultTestLoader.loadTestsFromNames(selected,module=sys.modules[__name__]) if selected else unittest.defaultTestLoader.loadTestsFromTestCase(TestSavedDragonLimbsTail)
test_result=unittest.TextTestRunner(verbosity=2).run(suite)
assert test_result.wasSuccessful(),"Saved-file regression failure"
(root/"saved_verification.json").write_text(json.dumps({"status":"PASS","tests_run":test_result.testsRun,"original_objects_unchanged":len(objects),"original_names_preserved":len(original_names),"original_material_graphs_unchanged":len(materials),"world_graph_and_color_unchanged":True,"camera_and_render_settings_restored":True,"scene_objects":len(bpy.context.scene.objects),"new_mesh_checks":rows,"preserved_wing_checks":wing_rows,"whole_dragon_fused":False},indent=2))
