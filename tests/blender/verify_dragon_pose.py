"""Independent pose, preservation, attachment and framing tests for v0.1.38."""
import bpy,bmesh,os,sys,json,hashlib,unittest
from pathlib import Path
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path.cwd()))
from blender_addon.universal_mcp.dragon_pose import BODY_MESHES,HEAD_SHIFT,body_point
from blender_addon.universal_mcp.dragon_armor import surface_sample
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



def geometry_snapshot(obj):
 if obj.type!="MESH":return None
 return hashlib.sha256(json.dumps({"vertices":[list(v.co) for v in obj.data.vertices],"faces":[list(f.vertices) for f in obj.data.polygons],"uv":[[[float(x) for x in d.uv] for d in layer.data] for layer in obj.data.uv_layers],"face_settings":[(f.material_index,f.use_smooth) for f in obj.data.polygons]},sort_keys=True).encode()).hexdigest()

bpy.ops.wm.open_mainfile(filepath=str(root/"source_copy.blend"));bpy.context.view_layer.update()
original_names={o.name for o in bpy.context.scene.objects}
objects={o.name:object_snapshot(o) for o in bpy.context.scene.objects}
geometry={o.name:geometry_snapshot(o) for o in bpy.context.scene.objects if o.name not in BODY_MESHES}
matrices={o.name:[list(row) for row in o.matrix_world] for o in bpy.context.scene.objects}
materials={m.name:graph_snapshot(m) for m in bpy.data.materials}
slots={o.name:[s.material.name if s.material else None for s in o.material_slots] for o in bpy.context.scene.objects}
world=graph_snapshot(bpy.context.scene.world);world_color=list(bpy.context.scene.world.color)
render={k:getattr(bpy.context.scene.render,k) for k in ("engine","resolution_x","resolution_y","resolution_percentage","filepath","film_transparent")}
cycles={k:getattr(bpy.context.scene.cycles,k) for k in ("samples","seed","device")}
file_format=bpy.context.scene.render.image_settings.file_format
core=[tuple(v.co) for v in bpy.data.objects["Dragon_Torso"].data.vertices]
source_meshes={n:[tuple(v.co) for v in bpy.data.objects[n].data.vertices] for n in BODY_MESHES}
source_detail=json.loads((root/"source_detail.json").read_text())["modeling"]
bpy.ops.wm.open_mainfile(filepath=str(root/"dragon_silhouette_v0.1.38.blend"));bpy.context.view_layer.update()
result=json.loads((root/"result.json").read_text())["modeling"];rows=[];attachments=[]
unchanged=original_names-set(result["changed_objects"])

class TestSavedDragonPose(unittest.TestCase):
 def test_objects_intrinsic_detail_limbs_tail_and_topology_preserved(self):
  self.assertEqual(len(original_names),143);self.assertEqual(len(bpy.context.scene.objects),143)
  self.assertEqual(original_names,{o.name for o in bpy.context.scene.objects})
  self.assertEqual(len(geometry),138)
  for name,value in geometry.items():self.assertEqual(geometry_snapshot(bpy.data.objects[name]),value,name)
  for name in unchanged:self.assertEqual(object_snapshot(bpy.data.objects[name]),objects[name],name)
  for name,value in slots.items():self.assertEqual([s.material.name if s.material else None for s in bpy.data.objects[name].material_slots],value,name)
  self.assertFalse(any(o.name.startswith("WingComparison_") for o in bpy.context.scene.objects))

 def test_head_is_rigid_and_all_wing_details_share_proper_rigid_pose(self):
  self.assertEqual(len(result["groups"]["wing_L"]),15);self.assertEqual(len(result["groups"]["wing_R"]),15)
  for name in result["groups"]["head"]:
   delta=bpy.data.objects[name].matrix_world@Matrix(matrices[name]).inverted()
   for i in range(3):
    self.assertAlmostEqual(delta[i][3],HEAD_SHIFT[i],places=5)
    for j in range(3):self.assertAlmostEqual(delta[i][j],int(i==j),places=5)
  for group,side in (("wing_L",1),("wing_R",-1)):
   first=None
   for name in result["groups"][group]:
    delta=bpy.data.objects[name].matrix_world@Matrix(matrices[name]).inverted()
    if first is None:first=delta.copy()
    for i in range(4):
     for j in range(4):self.assertAlmostEqual(delta[i][j],first[i][j],places=5)
    self.assertAlmostEqual(delta.to_3x3().determinant(),1,places=5)
    rotation=delta.to_3x3();identity=rotation.transposed()@rotation
    for i in range(3):
     for j in range(3):self.assertAlmostEqual(identity[i][j],int(i==j),places=5)
   anchor=Vector((0,.85*side,1.8));self.assertLess((first@anchor-anchor).length,1e-5)

 def test_shared_body_warp_is_closed_positive_and_retains_scale_attachments(self):
  for name in BODY_MESHES:
   obj=bpy.data.objects[name];data=obj.data;self.assertEqual(len(data.vertices),len(source_meshes[name]))
   for old,v in zip(source_meshes[name],data.vertices):
    self.assertLess((obj.matrix_world@v.co-Vector(body_point(old))).length,1e-6,name)
   bm=bmesh.new();bm.from_mesh(data);bad=sum(not edge.is_manifold for edge in bm.edges);self.assertEqual(bad,0,name)
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
   expected=source_detail["plate_counts"].get(name,1);self.assertEqual(components,expected,name)
   rows.append({"name":name,"components":components,"nonmanifold_edges":bad,"minimum_shell_volume":minimum});bm.free()
   if name in source_detail["attachments"]:
    record=source_detail["attachments"][name];maximum=0
    for i,spec in enumerate(record["specs"]):
     p,n=surface_sample(core,48,spec["t"]-.04*spec["dt"],spec["u"])
     crown=obj.matrix_world@data.vertices[i*50+36].co
     distance=(crown-Vector(body_point(p))).length
     self.assertGreater(distance,spec["height"]*.25);self.assertLess(distance,spec["height"]*2)
     maximum=max(maximum,distance)
    attachments.append({"name":name,"crowns":len(record["specs"]),"maximum_surface_distance":maximum})

 def test_all_materials_world_camera_and_render_state_preserved(self):
  self.assertEqual(len(bpy.data.materials),18)
  for name,value in materials.items():self.assertEqual(graph_snapshot(bpy.data.materials[name]),value,name)
  self.assertEqual(graph_snapshot(bpy.context.scene.world),world);self.assertEqual(list(bpy.context.scene.world.color),world_color)
  for k,v in render.items():self.assertEqual(getattr(bpy.context.scene.render,k),v)
  for k,v in cycles.items():self.assertEqual(getattr(bpy.context.scene.cycles,k),v)
  self.assertEqual(bpy.context.scene.render.image_settings.file_format,file_format)
  self.assertEqual(bpy.context.scene.camera.name,"Camera")

selected=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
suite=unittest.defaultTestLoader.loadTestsFromNames(selected,module=sys.modules[__name__]) if selected else unittest.defaultTestLoader.loadTestsFromTestCase(TestSavedDragonPose)
test_result=unittest.TextTestRunner(verbosity=2).run(suite)
assert test_result.wasSuccessful(),"Saved silhouette regression failure"
(root/"saved_verification.json").write_text(json.dumps({"status":"PASS","tests_run":test_result.testsRun,"original_local_geometry_records_unchanged":len(geometry),"fully_unchanged_original_objects":len(unchanged),"original_names_preserved":len(original_names),"original_material_graphs_unchanged":len(materials),"wing_objects_rigid":30,"scene_objects":len(bpy.context.scene.objects),"body_mesh_checks":rows,"attachment_checks":attachments,"groups":result["groups"],"whole_dragon_fused":False},indent=2))
