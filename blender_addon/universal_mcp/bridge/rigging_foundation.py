"""
Rigging & Armatures Foundation for Blender Universal MCP (Phase 2.3 - v0.1.76).

Provides typed, verified workflows for building and managing skeletal rigs in Blender:
- create_armature: Instantiates Armature datablocks and object containers with transform properties.
- edit_armature_bones: Edit Mode bone manipulation (add bone, edit head/tail/roll, bone hierarchy, connect flags).
- inspect_armature: Read-only inspection of bone hierarchy, rest positions, lengths, pose transforms, and constraints.
- bind_armature_mesh: Skinning target meshes to armatures via ARMATURE modifier, bone vertex groups, and auto/manual weights.
- configure_bone_constraint: Pose Mode constraint configuration (Inverse Kinematics / IK, Limit Rotation, Copy Transforms).
- Optimistic concurrency protection (expected_snapshot_id) and transactional rollback on failures.
"""

from contextlib import contextmanager
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Set, Tuple


SUPPORTED_CONSTRAINTS = ("IK", "LIMIT_ROTATION", "COPY_TRANSFORMS")
SUPPORTED_BIND_MODES = ("AUTOMATIC", "ENVELOPE", "NAME_ONLY", "MANUAL")
ALLOWED_SPACES = ("WORLD", "CUSTOM", "POSE", "LOCAL")


@contextmanager
def safe_armature_edit_mode(bpy_module: Any, arm_obj: Any):
    """
    Context manager that safely switches to EDIT mode on arm_obj,
    yielding arm_obj.data.edit_bones, and guarantees a return to OBJECT mode.
    """
    orig_active = bpy_module.context.view_layer.objects.active
    try:
        bpy_module.context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy_module.ops.object.mode_set(mode="EDIT")
        yield arm_obj.data.edit_bones
    finally:
        try:
            if bpy_module.context.view_layer.objects.active == arm_obj and getattr(arm_obj, "mode", "") != "OBJECT":
                bpy_module.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
        if orig_active and getattr(orig_active, "name", "") in bpy_module.data.objects:
            try:
                bpy_module.context.view_layer.objects.active = orig_active
            except Exception:
                pass


@contextmanager
def safe_armature_pose_mode(bpy_module: Any, arm_obj: Any):
    """
    Context manager that switches to POSE mode on arm_obj,
    yielding arm_obj.pose, and returns to OBJECT mode.
    """
    orig_active = bpy_module.context.view_layer.objects.active
    try:
        bpy_module.context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy_module.ops.object.mode_set(mode="POSE")
        yield arm_obj.pose
    finally:
        try:
            if bpy_module.context.view_layer.objects.active == arm_obj and getattr(arm_obj, "mode", "") != "OBJECT":
                bpy_module.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
        if orig_active and getattr(orig_active, "name", "") in bpy_module.data.objects:
            try:
                bpy_module.context.view_layer.objects.active = orig_active
            except Exception:
                pass


def compute_armature_snapshot_id(arm_obj: Any) -> str:
    """
    Computes a deterministic SHA-256 snapshot ID representing the complete state
    of an armature's bones, hierarchy, rest geometry, and pose constraints.
    """
    if not arm_obj or getattr(arm_obj, "type", "") != "ARMATURE":
        return ""

    arm_data = arm_obj.data
    bones_data = []

    # Read rest bones
    if hasattr(arm_data, "bones"):
        for b in sorted(arm_data.bones, key=lambda x: x.name):
            bone_dict = {
                "name": b.name,
                "head": [round(float(c), 4) for c in b.head_local],
                "tail": [round(float(c), 4) for c in b.tail_local],
                "parent": b.parent.name if b.parent else None,
                "use_connect": bool(getattr(b, "use_connect", False)),
                "use_deform": bool(getattr(b, "use_deform", True)),
            }
            bones_data.append(bone_dict)

    # Read pose constraints
    constraints_data = []
    if hasattr(arm_obj, "pose") and arm_obj.pose and hasattr(arm_obj.pose, "bones"):
        for pb in sorted(arm_obj.pose.bones, key=lambda x: x.name):
            for c in pb.constraints:
                c_dict = {
                    "bone": pb.name,
                    "name": c.name,
                    "type": c.type,
                    "target": getattr(c.target, "name", "") if hasattr(c, "target") and c.target else "",
                    "subtarget": getattr(c, "subtarget", ""),
                    "chain_count": getattr(c, "chain_count", 0),
                    "influence": round(float(getattr(c, "influence", 1.0)), 4),
                    "enabled": not getattr(c, "mute", False),
                }
                constraints_data.append(c_dict)

    state_repr = {
        "armature_name": arm_obj.name,
        "bones": bones_data,
        "constraints": constraints_data,
    }
    raw = json.dumps(state_repr, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def execute_create_armature(bpy_module: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Creates a new Armature datablock and linked scene Object.
    """
    params = dict(params or {})
    name = str(params.get("name", "Armature")).strip() or "Armature"
    location = params.get("location", [0.0, 0.0, 0.0])
    rotation = params.get("rotation", [0.0, 0.0, 0.0])
    scale = params.get("scale", [1.0, 1.0, 1.0])

    if not isinstance(location, (list, tuple)) or len(location) != 3:
        raise ValueError("Parameter 'location' must be a 3-element numeric list/tuple [x, y, z].")
    if not isinstance(rotation, (list, tuple)) or len(rotation) != 3:
        raise ValueError("Parameter 'rotation' must be a 3-element numeric list/tuple [x, y, z].")
    if not isinstance(scale, (list, tuple)) or len(scale) != 3:
        raise ValueError("Parameter 'scale' must be a 3-element numeric list/tuple [x, y, z].")

    # Create Armature datablock & Object
    arm_data = bpy_module.data.armatures.new(name)
    arm_obj = bpy_module.data.objects.new(name, arm_data)

    # Link to active collection
    coll = bpy_module.context.collection
    if not coll:
        coll = bpy_module.context.scene.collection
    coll.objects.link(arm_obj)

    arm_obj.location = (float(location[0]), float(location[1]), float(location[2]))
    arm_obj.rotation_euler = (float(rotation[0]), float(rotation[1]), float(rotation[2]))
    arm_obj.scale = (float(scale[0]), float(scale[1]), float(scale[2]))

    # Set as active
    bpy_module.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)

    snapshot_id = compute_armature_snapshot_id(arm_obj)

    return {
        "success": True,
        "armature_name": arm_obj.name,
        "datablock_name": arm_data.name,
        "object_name": arm_obj.name,
        "bones_count": 0,
        "location": [round(float(c), 4) for c in arm_obj.location],
        "rotation": [round(float(c), 4) for c in arm_obj.rotation_euler],
        "scale": [round(float(c), 4) for c in arm_obj.scale],
        "snapshot_id": snapshot_id,
        "message": f"Successfully created armature '{arm_obj.name}'.",
    }


def execute_edit_armature_bones(bpy_module: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Executes atomic bone edits on an armature in EDIT mode with rollback protection.
    Operations include 'add_bone', 'edit_bone', 'remove_bone'.
    """
    params = dict(params or {})
    armature_name = str(params.get("armature_name", "")).strip()
    if not armature_name:
        raise ValueError("Parameter 'armature_name' is required.")

    arm_obj = bpy_module.data.objects.get(armature_name)
    if not arm_obj or getattr(arm_obj, "type", "") != "ARMATURE":
        raise ValueError(f"Armature object '{armature_name}' not found.")

    # Optimistic concurrency snapshot verification
    current_snapshot = compute_armature_snapshot_id(arm_obj)
    expected_snapshot_id = params.get("expected_snapshot_id")
    if expected_snapshot_id and expected_snapshot_id != current_snapshot:
        raise ValueError(
            f"STALE_ARMATURE_STATE: Expected snapshot '{expected_snapshot_id}', but current state is '{current_snapshot}'."
        )

    # Parse operations
    operations = params.get("operations")
    if operations is None:
        action = params.get("action")
        if action:
            operations = [params]
        else:
            raise ValueError("Parameter 'operations' (or 'action') is required.")
    if not isinstance(operations, list) or len(operations) == 0:
        raise ValueError("Parameter 'operations' must be a non-empty list.")

    # Take pre-mutation snapshot for rollback
    arm_data = arm_obj.data
    prior_bones_state = []
    with safe_armature_edit_mode(bpy_module, arm_obj) as edit_bones:
        for eb in edit_bones:
            prior_bones_state.append({
                "name": eb.name,
                "head": list(eb.head),
                "tail": list(eb.tail),
                "roll": float(eb.roll),
                "parent": eb.parent.name if eb.parent else None,
                "use_connect": bool(eb.use_connect),
                "use_deform": bool(eb.use_deform),
            })

    # Execute operations in transaction
    applied_ops = []
    try:
        with safe_armature_edit_mode(bpy_module, arm_obj) as edit_bones:
            for idx, op in enumerate(operations):
                if not isinstance(op, dict):
                    raise ValueError(f"Operation #{idx} must be a dict.")
                action = str(op.get("action", "")).strip().lower()
                bone_name = str(op.get("name", "")).strip()
                if not bone_name:
                    raise ValueError(f"Operation #{idx} missing 'name'.")

                if action in ("add_bone", "add"):
                    if edit_bones.get(bone_name):
                        raise ValueError(f"Bone '{bone_name}' already exists in armature '{armature_name}'.")

                    head = op.get("head", [0.0, 0.0, 0.0])
                    tail = op.get("tail", [0.0, 0.0, 1.0])
                    if not isinstance(head, (list, tuple)) or len(head) != 3:
                        raise ValueError(f"Operation #{idx} invalid 'head' coordinates.")
                    if not isinstance(tail, (list, tuple)) or len(tail) != 3:
                        raise ValueError(f"Operation #{idx} invalid 'tail' coordinates.")

                    # Check head != tail
                    dist_sq = sum((float(h) - float(t)) ** 2 for h, t in zip(head, tail))
                    if dist_sq < 1e-8:
                        raise ValueError(f"Bone '{bone_name}' has zero length (head and tail cannot be identical).")

                    eb = edit_bones.new(bone_name)
                    eb.head = (float(head[0]), float(head[1]), float(head[2]))
                    eb.tail = (float(tail[0]), float(tail[1]), float(tail[2]))
                    eb.roll = float(op.get("roll", 0.0))
                    eb.use_deform = bool(op.get("use_deform", True))

                    parent_name = op.get("parent")
                    if parent_name:
                        p_eb = edit_bones.get(str(parent_name).strip())
                        if not p_eb:
                            raise ValueError(f"Parent bone '{parent_name}' not found for bone '{bone_name}'.")
                        eb.parent = p_eb
                        if op.get("use_connect", False):
                            eb.use_connect = True

                    applied_ops.append(f"add:{bone_name}")

                elif action in ("edit_bone", "edit", "update"):
                    eb = edit_bones.get(bone_name)
                    if not eb:
                        raise ValueError(f"Bone '{bone_name}' not found for editing.")

                    if "head" in op:
                        head = op["head"]
                        if not isinstance(head, (list, tuple)) or len(head) != 3:
                            raise ValueError(f"Invalid 'head' for bone '{bone_name}'.")
                        eb.head = (float(head[0]), float(head[1]), float(head[2]))

                    if "tail" in op:
                        tail = op["tail"]
                        if not isinstance(tail, (list, tuple)) or len(tail) != 3:
                            raise ValueError(f"Invalid 'tail' for bone '{bone_name}'.")
                        eb.tail = (float(tail[0]), float(tail[1]), float(tail[2]))

                    # Verify non-zero length after potential head/tail update
                    dist_sq = sum((eb.head[i] - eb.tail[i]) ** 2 for i in range(3))
                    if dist_sq < 1e-8:
                        raise ValueError(f"Bone '{bone_name}' has zero length after edit.")

                    if "roll" in op:
                        eb.roll = float(op["roll"])
                    if "use_deform" in op:
                        eb.use_deform = bool(op["use_deform"])

                    if "parent" in op:
                        p_name = op["parent"]
                        if p_name is None or str(p_name).strip() == "":
                            eb.parent = None
                            eb.use_connect = False
                        else:
                            p_eb = edit_bones.get(str(p_name).strip())
                            if not p_eb:
                                raise ValueError(f"Parent bone '{p_name}' not found.")
                            eb.parent = p_eb

                    if "use_connect" in op:
                        eb.use_connect = bool(op["use_connect"])

                    applied_ops.append(f"edit:{bone_name}")

                elif action in ("remove_bone", "remove", "delete"):
                    eb = edit_bones.get(bone_name)
                    if not eb:
                        raise ValueError(f"Bone '{bone_name}' not found for removal.")
                    edit_bones.remove(eb)
                    applied_ops.append(f"remove:{bone_name}")

                else:
                    raise ValueError(f"Unsupported bone action '{action}'. Allowed: add_bone, edit_bone, remove_bone.")

    except Exception as exc:
        # Rollback edit bones to pre-mutation state
        try:
            with safe_armature_edit_mode(bpy_module, arm_obj) as edit_bones:
                current_names = set(eb.name for eb in edit_bones)
                prior_names = set(b["name"] for b in prior_bones_state)

                # Remove newly created bones
                for name in (current_names - prior_names):
                    eb = edit_bones.get(name)
                    if eb:
                        edit_bones.remove(eb)

                # Restore deleted bones
                for b in prior_bones_state:
                    if b["name"] not in edit_bones:
                        edit_bones.new(b["name"])

                # Restore head, tail, roll, deform
                for b in prior_bones_state:
                    eb = edit_bones.get(b["name"])
                    if eb:
                        eb.head = tuple(b["head"])
                        eb.tail = tuple(b["tail"])
                        eb.roll = b["roll"]
                        eb.use_deform = b["use_deform"]

                # Restore parents and connections
                for b in prior_bones_state:
                    eb = edit_bones.get(b["name"])
                    if eb:
                        if b["parent"]:
                            p_eb = edit_bones.get(b["parent"])
                            if p_eb:
                                eb.parent = p_eb
                                eb.use_connect = b["use_connect"]
                        else:
                            eb.parent = None
        except Exception as rb_exc:
            raise RuntimeError(f"Mutation failed: {exc} | Rollback failed: {rb_exc}") from exc

        raise RuntimeError(f"Armature edit transaction aborted and rolled back: {exc}") from exc

    new_snapshot_id = compute_armature_snapshot_id(arm_obj)
    bones_summary = [
        {
            "name": b.name,
            "head": [round(float(c), 4) for c in b.head_local],
            "tail": [round(float(c), 4) for c in b.tail_local],
            "parent": b.parent.name if b.parent else None,
            "use_connect": bool(b.use_connect),
            "use_deform": bool(b.use_deform),
        }
        for b in arm_obj.data.bones
    ]

    return {
        "success": True,
        "armature_name": arm_obj.name,
        "bones_count": len(arm_obj.data.bones),
        "operations_applied": applied_ops,
        "bones": bones_summary,
        "snapshot_id": new_snapshot_id,
        "message": f"Successfully applied {len(applied_ops)} bone operations to armature '{arm_obj.name}'.",
    }


def execute_inspect_armature(bpy_module: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Read-only inspection of armature hierarchy, bone rest data, and pose constraints.
    """
    params = dict(params or {})
    armature_name = str(params.get("armature_name", "")).strip()
    if not armature_name:
        raise ValueError("Parameter 'armature_name' is required.")

    arm_obj = bpy_module.data.objects.get(armature_name)
    if not arm_obj or getattr(arm_obj, "type", "") != "ARMATURE":
        raise ValueError(f"Armature object '{armature_name}' not found.")

    frame_val = params.get("frame")
    if frame_val is not None:
        scene = getattr(getattr(bpy_module, "context", None), "scene", None)
        if scene:
            scene.frame_set(int(frame_val))
            try:
                bpy_module.context.view_layer.update()
            except Exception:
                pass

    include_pose = bool(params.get("include_pose", True))
    bones_info = []

    for b in arm_obj.data.bones:
        length = float(b.length)
        head = [round(float(c), 4) for c in b.head_local]
        tail = [round(float(c), 4) for c in b.tail_local]
        parent = b.parent.name if b.parent else None
        children = [ch.name for ch in b.children]

        b_entry = {
            "name": b.name,
            "head": head,
            "tail": tail,
            "length": round(length, 4),
            "parent": parent,
            "children": children,
            "use_connect": bool(b.use_connect),
            "use_deform": bool(b.use_deform),
        }

        if include_pose and hasattr(arm_obj, "pose") and arm_obj.pose and b.name in arm_obj.pose.bones:
            try:
                bpy_module.context.view_layer.update()
            except Exception:
                pass
            pb = arm_obj.pose.bones[b.name]
            b_entry["pose_location"] = [round(float(c), 4) for c in pb.location]
            b_entry["pose_rotation_euler"] = [round(float(c), 4) for c in pb.rotation_euler]
            b_entry["pose_scale"] = [round(float(c), 4) for c in pb.scale]
            b_entry["pose_head"] = [round(float(c), 4) for c in pb.head]
            b_entry["pose_tail"] = [round(float(c), 4) for c in pb.tail]

            constraints = []
            for c in pb.constraints:
                c_item = {
                    "name": c.name,
                    "type": c.type,
                    "influence": round(float(getattr(c, "influence", 1.0)), 4),
                    "enabled": not getattr(c, "mute", False),
                }
                if hasattr(c, "target") and c.target:
                    c_item["target"] = c.target.name
                if hasattr(c, "subtarget") and c.subtarget:
                    c_item["subtarget"] = c.subtarget
                if hasattr(c, "chain_count"):
                    c_item["chain_count"] = c.chain_count
                constraints.append(c_item)
            b_entry["constraints"] = constraints

        bones_info.append(b_entry)

    snapshot_id = compute_armature_snapshot_id(arm_obj)

    return {
        "success": True,
        "armature_name": arm_obj.name,
        "datablock_name": arm_obj.data.name,
        "bones_count": len(bones_info),
        "bones": bones_info,
        "location": [round(float(c), 4) for c in arm_obj.location],
        "rotation": [round(float(c), 4) for c in arm_obj.rotation_euler],
        "scale": [round(float(c), 4) for c in arm_obj.scale],
        "snapshot_id": snapshot_id,
    }


def execute_bind_armature_mesh(bpy_module: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Skins a mesh to an armature via ARMATURE modifier and vertex groups.
    Supports AUTOMATIC, ENVELOPE, NAME_ONLY, and MANUAL binding.
    Transactional rollback restores mesh modifiers and vertex groups on failure.
    """
    params = dict(params or {})
    mesh_name = str(params.get("mesh_object_name", "")).strip()
    armature_name = str(params.get("armature_name", "")).strip()

    if not mesh_name:
        raise ValueError("Parameter 'mesh_object_name' is required.")
    if not armature_name:
        raise ValueError("Parameter 'armature_name' is required.")

    mesh_obj = bpy_module.data.objects.get(mesh_name)
    if not mesh_obj or getattr(mesh_obj, "type", "") != "MESH":
        raise ValueError(f"Mesh object '{mesh_name}' not found.")

    arm_obj = bpy_module.data.objects.get(armature_name)
    if not arm_obj or getattr(arm_obj, "type", "") != "ARMATURE":
        raise ValueError(f"Armature object '{armature_name}' not found.")

    bind_mode = str(params.get("bind_mode", "AUTOMATIC")).strip().upper()
    if bind_mode not in SUPPORTED_BIND_MODES:
        raise ValueError(f"Unsupported bind_mode '{bind_mode}'. Allowed: {list(SUPPORTED_BIND_MODES)}.")

    use_deform_only = bool(params.get("use_deform_only", True))

    # Optimistic concurrency check
    expected_snapshot_id = params.get("expected_snapshot_id")
    if expected_snapshot_id:
        curr_arm_snap = compute_armature_snapshot_id(arm_obj)
        if expected_snapshot_id != curr_arm_snap:
            raise ValueError(
                f"STALE_ARMATURE_STATE: Expected armature snapshot '{expected_snapshot_id}', current is '{curr_arm_snap}'."
            )

    # Save pre-mutation mesh state for rollback
    orig_parent = mesh_obj.parent
    orig_modifiers = [m.name for m in mesh_obj.modifiers]
    orig_vgroups = [vg.name for vg in mesh_obj.vertex_groups]

    assigned_vgroups = []
    modifier_name = ""

    try:
        if hasattr(bpy_module.context, "mode") and bpy_module.context.mode != "OBJECT":
            try:
                bpy_module.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        if bind_mode == "AUTOMATIC":
            # Select mesh and armature with armature active
            bpy_module.ops.object.select_all(action="DESELECT")
            mesh_obj.select_set(True)
            arm_obj.select_set(True)
            bpy_module.context.view_layer.objects.active = arm_obj

            res = bpy_module.ops.object.parent_set(type="ARMATURE_AUTO")
            if "FINISHED" not in res:
                raise RuntimeError(f"ARMATURE_AUTO parenting failed with status {res}.")

            # Find armature modifier
            for m in mesh_obj.modifiers:
                if m.type == "ARMATURE" and m.object == arm_obj:
                    modifier_name = m.name
                    break

            assigned_vgroups = [vg.name for vg in mesh_obj.vertex_groups]

        elif bind_mode == "ENVELOPE":
            bpy_module.ops.object.select_all(action="DESELECT")
            mesh_obj.select_set(True)
            arm_obj.select_set(True)
            bpy_module.context.view_layer.objects.active = arm_obj

            res = bpy_module.ops.object.parent_set(type="ARMATURE_ENVELOPE")
            if "FINISHED" not in res:
                raise RuntimeError(f"ARMATURE_ENVELOPE parenting failed with status {res}.")

            for m in mesh_obj.modifiers:
                if m.type == "ARMATURE" and m.object == arm_obj:
                    modifier_name = m.name
                    break
            assigned_vgroups = [vg.name for vg in mesh_obj.vertex_groups]

        elif bind_mode in ("NAME_ONLY", "MANUAL"):
            # Set parent
            mesh_obj.parent = arm_obj

            # Add or reuse Armature modifier
            mod = None
            for m in mesh_obj.modifiers:
                if m.type == "ARMATURE" and m.object == arm_obj:
                    mod = m
                    break
            if not mod:
                mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
                mod.object = arm_obj
                mod.use_vertex_groups = True
            modifier_name = mod.name

            # Create vertex groups for bones
            for b in arm_obj.data.bones:
                if use_deform_only and not b.use_deform:
                    continue
                vg = mesh_obj.vertex_groups.get(b.name)
                if not vg:
                    vg = mesh_obj.vertex_groups.new(name=b.name)
                assigned_vgroups.append(vg.name)

            # Manual weights if supplied
            manual_weights = params.get("vertex_weights")
            if manual_weights and isinstance(manual_weights, dict):
                for bone_n, v_dict in manual_weights.items():
                    vg = mesh_obj.vertex_groups.get(bone_n)
                    if vg and isinstance(v_dict, dict):
                        for v_idx_str, w in v_dict.items():
                            v_idx = int(v_idx_str)
                            if 0 <= v_idx < len(mesh_obj.data.vertices):
                                vg.add([v_idx], float(w), "REPLACE")

    except Exception as exc:
        # Rollback mesh state
        try:
            mesh_obj.parent = orig_parent
            for m in list(mesh_obj.modifiers):
                if m.name not in orig_modifiers:
                    mesh_obj.modifiers.remove(m)
            for vg in list(mesh_obj.vertex_groups):
                if vg.name not in orig_vgroups:
                    mesh_obj.vertex_groups.remove(vg)
        except Exception as rb_exc:
            raise RuntimeError(f"Mesh bind failed: {exc} | Rollback failed: {rb_exc}") from exc

        raise RuntimeError(f"Armature mesh binding failed and rolled back: {exc}") from exc

    new_snapshot_id = compute_armature_snapshot_id(arm_obj)

    return {
        "success": True,
        "mesh_object_name": mesh_obj.name,
        "armature_name": arm_obj.name,
        "bind_mode": bind_mode,
        "modifier_name": modifier_name,
        "vertex_groups": assigned_vgroups,
        "vertex_count": len(mesh_obj.data.vertices),
        "snapshot_id": new_snapshot_id,
        "message": f"Successfully bound mesh '{mesh_obj.name}' to armature '{arm_obj.name}' via {bind_mode}.",
    }


def execute_configure_bone_constraint(bpy_module: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Configures Pose Mode constraints on armature bones (IK, LIMIT_ROTATION, COPY_TRANSFORMS).
    Supports 'ADD', 'REMOVE', 'UPDATE' actions with rollback protection.
    """
    params = dict(params or {})
    armature_name = str(params.get("armature_name", "")).strip()
    bone_name = str(params.get("bone_name", "")).strip()

    if not armature_name:
        raise ValueError("Parameter 'armature_name' is required.")
    if not bone_name:
        raise ValueError("Parameter 'bone_name' is required.")

    arm_obj = bpy_module.data.objects.get(armature_name)
    if not arm_obj or getattr(arm_obj, "type", "") != "ARMATURE":
        raise ValueError(f"Armature object '{armature_name}' not found.")

    if not hasattr(arm_obj, "pose") or not arm_obj.pose or bone_name not in arm_obj.pose.bones:
        raise ValueError(f"Pose bone '{bone_name}' not found in armature '{armature_name}'.")

    pb = arm_obj.pose.bones[bone_name]

    action = str(params.get("action", "ADD")).strip().upper()
    if action not in ("ADD", "REMOVE", "UPDATE"):
        raise ValueError(f"Unsupported action '{action}'. Allowed: ADD, REMOVE, UPDATE.")

    constraint_type = str(params.get("constraint_type", "IK")).strip().upper()
    if action in ("ADD", "UPDATE") and constraint_type not in SUPPORTED_CONSTRAINTS:
        raise ValueError(f"Unsupported constraint_type '{constraint_type}'. Allowed: {list(SUPPORTED_CONSTRAINTS)}.")

    expected_snapshot_id = params.get("expected_snapshot_id")
    if expected_snapshot_id:
        curr_snap = compute_armature_snapshot_id(arm_obj)
        if expected_snapshot_id != curr_snap:
            raise ValueError(
                f"STALE_ARMATURE_STATE: Expected armature snapshot '{expected_snapshot_id}', current is '{curr_snap}'."
            )

    # Pre-mutation snapshot of constraints for rollback
    prior_constraints = [
        {
            "name": c.name,
            "type": c.type,
            "target": getattr(c.target, "name", "") if hasattr(c, "target") and c.target else "",
            "subtarget": getattr(c, "subtarget", ""),
            "chain_count": getattr(c, "chain_count", 0),
            "influence": getattr(c, "influence", 1.0),
            "mute": getattr(c, "mute", False),
        }
        for c in pb.constraints
    ]

    constraint_name = params.get("constraint_name")
    c = None

    try:
        if action == "ADD":
            c = pb.constraints.new(constraint_type)
            if constraint_name:
                c.name = str(constraint_name).strip()

            _apply_constraint_properties(bpy_module, c, constraint_type, params)

        elif action == "UPDATE":
            # Locate existing constraint
            c = None
            if constraint_name:
                c = pb.constraints.get(str(constraint_name).strip())
            if not c:
                for existing in pb.constraints:
                    if existing.type == constraint_type:
                        c = existing
                        break
            if not c:
                raise ValueError(f"Constraint of type '{constraint_type}' not found on bone '{bone_name}' for update.")

            _apply_constraint_properties(bpy_module, c, constraint_type, params)

        elif action == "REMOVE":
            c_to_remove = None
            if constraint_name:
                c_to_remove = pb.constraints.get(str(constraint_name).strip())
            if not c_to_remove:
                for existing in pb.constraints:
                    if existing.type == constraint_type:
                        c_to_remove = existing
                        break
            if not c_to_remove:
                raise ValueError(f"Constraint not found on bone '{bone_name}' for removal.")
            c_name = c_to_remove.name
            c_type = c_to_remove.type
            pb.constraints.remove(c_to_remove)

            new_snap = compute_armature_snapshot_id(arm_obj)
            return {
                "success": True,
                "armature_name": arm_obj.name,
                "bone_name": bone_name,
                "action": "REMOVE",
                "constraint_name": c_name,
                "constraint_type": c_type,
                "snapshot_id": new_snap,
                "message": f"Successfully removed constraint '{c_name}' from bone '{bone_name}'.",
            }

    except Exception as exc:
        # Rollback constraints
        try:
            # Clear current constraints
            for current_c in list(pb.constraints):
                pb.constraints.remove(current_c)
            # Restore prior
            for p_c in prior_constraints:
                restored = pb.constraints.new(p_c["type"])
                restored.name = p_c["name"]
                if p_c["target"]:
                    t_obj = bpy_module.data.objects.get(p_c["target"])
                    if t_obj:
                        restored.target = t_obj
                if hasattr(restored, "subtarget") and p_c["subtarget"]:
                    restored.subtarget = p_c["subtarget"]
                if hasattr(restored, "chain_count"):
                    restored.chain_count = p_c["chain_count"]
                if hasattr(restored, "influence"):
                    restored.influence = p_c["influence"]
                if hasattr(restored, "mute"):
                    restored.mute = p_c["mute"]
        except Exception as rb_exc:
            raise RuntimeError(f"Constraint config failed: {exc} | Rollback failed: {rb_exc}") from exc

        raise RuntimeError(f"Bone constraint configuration failed and rolled back: {exc}") from exc

    new_snap = compute_armature_snapshot_id(arm_obj)

    return {
        "success": True,
        "armature_name": arm_obj.name,
        "bone_name": bone_name,
        "action": action,
        "constraint_name": c.name,
        "constraint_type": c.type,
        "influence": round(float(c.influence), 4) if hasattr(c, "influence") else 1.0,
        "target": getattr(c.target, "name", "") if hasattr(c, "target") and c.target else "",
        "subtarget": getattr(c, "subtarget", "") if hasattr(c, "subtarget") else "",
        "snapshot_id": new_snap,
        "message": f"Successfully configured {c.type} constraint '{c.name}' on bone '{bone_name}'.",
    }


def _apply_constraint_properties(bpy_module: Any, c: Any, constraint_type: str, params: Dict[str, Any]):
    """Applies and bounds constraint-specific settings."""
    # Target Object
    target_name = params.get("target_object")
    if target_name:
        t_obj = bpy_module.data.objects.get(str(target_name).strip())
        if not t_obj:
            raise ValueError(f"Target object '{target_name}' not found for constraint.")
        c.target = t_obj

    # Target Bone (subtarget)
    target_bone = params.get("target_bone")
    if target_bone and hasattr(c, "subtarget"):
        c.subtarget = str(target_bone).strip()

    # Influence
    if "influence" in params:
        inf = float(params["influence"])
        c.influence = max(0.0, min(1.0, inf))

    # Type-specific configurations
    if constraint_type == "IK":
        if "chain_count" in params:
            c.chain_count = max(0, int(params["chain_count"]))

        pole_target = params.get("pole_target")
        if pole_target:
            p_obj = bpy_module.data.objects.get(str(pole_target).strip())
            if not p_obj:
                raise ValueError(f"Pole target object '{pole_target}' not found.")
            c.pole_target = p_obj

        pole_subtarget = params.get("pole_subtarget")
        if pole_subtarget and hasattr(c, "pole_subtarget"):
            c.pole_subtarget = str(pole_subtarget).strip()

        if "pole_angle" in params:
            c.pole_angle = float(params["pole_angle"])

    elif constraint_type == "LIMIT_ROTATION":
        rot_settings = params.get("limit_rotation_settings", {})
        if not isinstance(rot_settings, dict):
            rot_settings = {}

        for axis in ("x", "y", "z"):
            use_key = f"use_limit_{axis}"
            min_key = f"min_{axis}"
            max_key = f"max_{axis}"

            if use_key in rot_settings or use_key in params:
                val = rot_settings.get(use_key, params.get(use_key))
                setattr(c, use_key, bool(val))

            if min_key in rot_settings or min_key in params:
                val = float(rot_settings.get(min_key, params.get(min_key)))
                setattr(c, min_key, val)

            if max_key in rot_settings or max_key in params:
                val = float(rot_settings.get(max_key, params.get(max_key)))
                setattr(c, max_key, val)

        owner_space = params.get("owner_space", rot_settings.get("owner_space"))
        if owner_space and str(owner_space).upper() in ALLOWED_SPACES:
            c.owner_space = str(owner_space).upper()

    elif constraint_type == "COPY_TRANSFORMS":
        owner_space = params.get("owner_space")
        if owner_space and str(owner_space).upper() in ALLOWED_SPACES:
            c.owner_space = str(owner_space).upper()

        target_space = params.get("target_space")
        if target_space and str(target_space).upper() in ALLOWED_SPACES:
            c.target_space = str(target_space).upper()
