"""Copy/stage/readback/commit for finite mesh operations on Blender main thread."""
from types import SimpleNamespace
from .mesh_topology import inspect_elements,assert_base_snapshot


def snapshot(obj,context):
    return inspect_elements(obj,context,{"element_domain":"vertices","limit":1})


def verify_commit(obj,context,expected):
    observed=snapshot(obj,context)
    if observed["snapshot_id"]!=expected["snapshot_id"] or observed.get("state_id")!=expected.get("state_id"):
        raise RuntimeError("Committed mesh failed actual state readback")
    return observed


def run(bpy,obj,mutate,expected_id,verify=None):
    import bmesh
    if getattr(obj,"library",None) or getattr(obj.data,"library",None) or obj.data.shape_keys is not None or getattr(obj.data,"animation_data",None):
        raise ValueError("Atomic mesh edits require local data without shape keys/data animation")
    before=snapshot(obj,bpy.context);assert_base_snapshot(obj,bpy.context,expected_id)
    original=obj.data;old_name=original.name;original_names=set(bpy.data.meshes.keys())
    stage=None;bm=None;old_renamed=False
    try:
        stage=original.copy();bm=bmesh.new();bm.from_mesh(stage)
        details=mutate(bm)
        bm.normal_update()
        metrics={"boundary_edges":sum(e.is_boundary for e in bm.edges),"wire_edges":sum(e.is_wire for e in bm.edges),
                 "nonmanifold_edges":sum(len(e.link_faces)>2 for e in bm.edges),
                 "nonmanifold_vertices":sum(not v.is_manifold for v in bm.verts),
                 "degenerate_edges":sum(e.calc_length()<=1e-12 for e in bm.edges),
                 "degenerate_faces":sum(f.calc_area()<=1e-12 for f in bm.faces)}
        if metrics["degenerate_faces"] or metrics["degenerate_edges"]:raise RuntimeError("Operation produced degenerate faces or edges")
        metrics["is_closed_manifold"]=bool(bm.faces) and all(metrics[k]==0 for k in ("boundary_edges","wire_edges","nonmanifold_edges","nonmanifold_vertices"))
        bm.to_mesh(stage);stage.update();bm.free();bm=None
        candidate=SimpleNamespace(name=obj.name,type="MESH",data=stage,mode="OBJECT")
        ctx=SimpleNamespace(mode="OBJECT",scene=SimpleNamespace(objects={obj.name:candidate}))
        after=snapshot(candidate,ctx)
        changed=after.get("state_id",after["snapshot_id"])!=before.get("state_id",before["snapshot_id"])
        if not changed and not details.pop("allow_unchanged",False):raise RuntimeError("Operation produced no requested change")
        if not changed:
            bpy.data.meshes.remove(stage);stage=None
            return {"success":True,"verified":True,"name":obj.name,"changed":False,"transaction_status":"NO_CHANGE_VERIFIED",
                    "snapshot_id":before["snapshot_id"],"state_id":before.get("state_id"),"geometry_validity":metrics,
                    "new_vertex_count":before["vertex_count"],"new_edge_count":before["edge_count"],"new_face_count":before["polygon_count"],**details}
        obj.data=stage
        observed=(verify or verify_commit)(obj,bpy.context,after)
        result={"success":True,"verified":True,"name":obj.name,"changed":True,"transaction_status":"COMMITTED",
                "snapshot_id":observed["snapshot_id"],"state_id":observed.get("state_id"),"before_snapshot_id":before["snapshot_id"],
                "new_vertex_count":observed["vertex_count"],"new_edge_count":observed["edge_count"],"new_face_count":observed["polygon_count"],
                "geometry_validity":metrics,**details}
        # Preserve shared/fake-user sources. Dispose only the replaced, now-unreferenced
        # target data; do every fallible verification before this final commit point.
        if original.users==0:
            original.name=old_name+"_UMCP_CHECKPOINT";old_renamed=True
            stage.name=old_name
            if stage.name!=old_name:raise RuntimeError("Mesh name restoration failed")
            bpy.data.meshes.remove(original)
        return result
    except Exception as error:
        try:
            if obj.data!=original:obj.data=original
            if stage is not None and stage.users==0:bpy.data.meshes.remove(stage)
            if old_renamed:original.name=old_name
            actual=snapshot(obj,bpy.context)
            if actual["snapshot_id"]!=before["snapshot_id"] or actual.get("state_id")!=before.get("state_id") or obj.data!=original or set(bpy.data.meshes.keys())!=original_names:
                raise RuntimeError("Original mesh identity/state or datablock inventory differs")
        except Exception as restore_error:raise RuntimeError(f"ROLLBACK_UNVERIFIED: {restore_error}; original failure: {error}") from error
        raise RuntimeError(f"ROLLED_BACK_VERIFIED: {error}") from error
    finally:
        if bm is not None:bm.free()
