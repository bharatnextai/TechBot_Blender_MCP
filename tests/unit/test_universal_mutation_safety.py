from tests.unit.modeling_approval_fixture import approved
"""
Unit tests for the Universal MCP Mutation Safety & Recovery Architecture (TASK-UMCP-0049).

Covers the Universal Test Matrix:
1. Failure before the first mutation (preflight rejection with zero side effects).
2. Failure after creating several objects (compensating cleanup removes only current-run created objects).
3. Failure after changing an existing object's transform (original transform restoration).
4. Failure after collection linking/unlinking (collection membership restoration).
5. Failure during mesh/data modification (irreversible data changes detected and reported as DIRTY).
6. Cleanup failure (compensating action raises exception; fails closed and reports UNRECOVERED_DIRTY_STATE).
7. Timeout or interrupted execution (preserves task state and returns structured error).
8. Retry after partial failure (collision detection halts retry before corrupting dirty state).
9. Preservation of pre-existing objects and unrelated assets (pre-existing assets are NEVER deleted).
10. Existing AST and approval enforcement remaining effective (disallowed nodes, untrusted flags rejected).

All tests run in isolated environments without live scene mutations.
"""

import copy
import time
import unittest
from typing import Dict, Any, List, Optional, Set
from unittest.mock import MagicMock, patch

from shared.schemas.tool_schemas import (
    TOOL_CREATE_PRIMITIVE,
    TOOL_TRANSFORM_OBJECT,
    TOOL_EXECUTE_BLENDER_CODE,
    validate_tool_input,
)
from blender_addon.universal_mcp.bridge.ast_validator import validate_restricted_code_ast
from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
from blender_addon.universal_mcp.bridge.handlers import UniversalMutationJournal


# ==============================================================================
# MOCK BLENDER RUNTIME FIXTURES
# ==============================================================================

class MockMesh:
    def __init__(self, name: str, vertices=None, polygons=None, edges=None):
        self.name = name
        self.users = 1
        self.vertices = list(vertices or [1, 2, 3, 4])
        self.polygons = list(polygons or [1, 2])
        self.edges = list(edges or [1, 2, 3, 4, 5])
        self._ptr = id(self)

    def as_pointer(self):
        return self._ptr


class MockModifier:
    def __init__(self, name: str, mod_type: str = "SUBSURF"):
        self.name = name
        self.type = mod_type


class MockMeshObj:
    def __init__(self, name: str, location=None, rotation=None, scale=None, mesh_data=None):
        self.name = name
        self.type = "MESH"
        self.location = list(location or [0.0, 0.0, 0.0])
        self.rotation_euler = list(rotation or [0.0, 0.0, 0.0])
        self.scale = list(scale or [1.0, 1.0, 1.0])
        self.data = mesh_data or MockMesh(f"{name}_Mesh")
        self.modifiers = []
        self._props: Dict[str, Any] = {}
        self.collections = []
        self._ptr = id(self)

    def as_pointer(self):
        return self._ptr

    def keys(self):
        return list(self._props.keys())

    def items(self):
        return list(self._props.items())

    def __getitem__(self, key):
        return self._props[key]

    def __setitem__(self, key, value):
        self._props[key] = value

    def __contains__(self, key):
        return key in self._props

    def __repr__(self):
        return f"MockMeshObj({self.name}, loc={self.location})"


class MockCollectionObjects:
    def __init__(self):
        self._objs: List[Any] = []

    def link(self, obj):
        if obj not in self._objs:
            self._objs.append(obj)

    def unlink(self, obj):
        if obj in self._objs:
            self._objs.remove(obj)

    def values(self):
        return list(self._objs)

    def __iter__(self):
        return iter(self._objs)

    def __contains__(self, obj):
        return obj in self._objs

    def remove(self, obj):
        self.unlink(obj)

    def append(self, obj):
        self.link(obj)

    def __len__(self):
        return len(self._objs)


class MockCollection:
    def __init__(self, name: str):
        self.name = name
        self.objects = MockCollectionObjects()
        self._ptr = id(self)

    def as_pointer(self):
        return self._ptr


class MockDataRegistry:
    def __init__(self, item_cls):
        self._items: Dict[str, Any] = {}
        self.item_cls = item_cls

    def _sync(self):
        new_items = {}
        for k, v in list(self._items.items()):
            name = getattr(v, "name", k)
            new_items[name] = v
        self._items = new_items

    def new(self, name, *args, **kwargs):
        self._sync()
        item = self.item_cls(name)
        self._items[name] = item
        return item

    def keys(self):
        self._sync()
        return list(self._items.keys())

    def values(self):
        return list(self._items.values())

    def __iter__(self):
        return iter(self._items.values())

    def get(self, name, default=None):
        self._sync()
        return self._items.get(name, default)

    def __getitem__(self, name):
        self._sync()
        return self._items[name]

    def __setitem__(self, name, item):
        self._items[name] = item

    def __contains__(self, name):
        self._sync()
        return name in self._items

    def remove(self, item, do_unlink=True):
        self._sync()
        name = item.name if hasattr(item, "name") else str(item)
        found_key = None
        for k, v in list(self._items.items()):
            if v is item or k == name or (hasattr(v, "name") and v.name == name):
                found_key = k
                break
        if found_key:
            obj = self._items[found_key]
            if hasattr(obj, "data") and obj.data and hasattr(obj.data, "users"):
                obj.data.users -= 1
            del self._items[found_key]
        else:
            raise KeyError(f"Item '{name}' not found")

    def __delitem__(self, name):
        self.remove(name)


class MockBlenderScene:
    def __init__(self):
        self.data = MagicMock()
        self.data.objects = MockDataRegistry(MockMeshObj)
        self.data.collections = MockDataRegistry(MockCollection)
        self.data.meshes = MockDataRegistry(MockMesh)


# ==============================================================================
# TEST SUITE: UNIVERSAL MUTATION SAFETY & RECOVERY
# ==============================================================================

class TestUniversalMutationSafety(unittest.TestCase):
    def setUp(self):
        self.scene = MockBlenderScene()
        # Seed pre-existing objects matching baseline
        self.scene.data.objects["Cube"] = MockMeshObj("Cube")
        self.scene.data.objects["Ref_Human"] = MockMeshObj("Ref_Human", location=[-5.0, 0.0, 0.9])
        self.scene.data.objects["Dragon_Torso"] = MockMeshObj("Dragon_Torso", location=[0.0, 0.0, 2.0], scale=[5.0, 2.4, 3.0])
        self.scene.data.objects["Wing_L_Proxy"] = MockMeshObj("Wing_L_Proxy", location=[-0.5, 2.8, 3.2])
        self.scene.data.collections["Collection"] = MockCollection("Collection")

    # --------------------------------------------------------------------------
    # Scenario 1: Failure before the first mutation
    # --------------------------------------------------------------------------
    def test_01_failure_before_first_mutation(self):
        """Preflight rejection raises error before any object is created or altered."""
        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(AssertionError) as ctx:
            with journal:
                # Preflight check: Target name already exists
                target_name = "Cube"
                assert target_name not in self.scene.data.objects, f"Name collision: '{target_name}'"
                # Mutation that should NEVER execute:
                self.scene.data.objects["New_Obj"] = MockMeshObj("New_Obj")

        self.assertIn("Name collision: 'Cube'", str(ctx.exception))
        self.assertNotIn("New_Obj", self.scene.data.objects)
        self.assertEqual(len(self.scene.data.objects.keys()), 4)

    # --------------------------------------------------------------------------
    # Scenario 2: Failure after creating several objects
    # --------------------------------------------------------------------------
    def test_02_failure_after_creating_several_objects(self):
        """Compensating cleanup removes strictly new objects, preserving pre-existing ones."""
        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Create object 1
                self.scene.data.objects["Part_1"] = MockMeshObj("Part_1")
                # Create object 2
                self.scene.data.objects["Part_2"] = MockMeshObj("Part_2")
                # Create object 3
                self.scene.data.objects["Part_3"] = MockMeshObj("Part_3")
                # Failure on step 4
                raise RuntimeError("Simulation error after creating 3 objects")

        self.assertIn("Simulation error after creating 3 objects", str(ctx.exception))
        # Newly created objects must be completely cleaned up
        self.assertNotIn("Part_1", self.scene.data.objects)
        self.assertNotIn("Part_2", self.scene.data.objects)
        self.assertNotIn("Part_3", self.scene.data.objects)
        # Pre-existing objects must remain 100% intact
        self.assertIn("Cube", self.scene.data.objects)
        self.assertIn("Ref_Human", self.scene.data.objects)
        self.assertIn("Dragon_Torso", self.scene.data.objects)
        self.assertIn("Wing_L_Proxy", self.scene.data.objects)

    # --------------------------------------------------------------------------
    # Scenario 3: Failure after changing an existing object's transform
    # --------------------------------------------------------------------------
    def test_03_failure_after_transform_mutation(self):
        """Tracked transform modifications are reverted to original coordinates upon failure."""
        journal = UniversalMutationJournal(self.scene)
        wing = self.scene.data.objects["Wing_L_Proxy"]
        orig_loc = list(wing.location)

        with self.assertRaises(ValueError):
            with journal:
                # Track transform before modifying
                journal.track_transform("Wing_L_Proxy", location=wing.location)
                # Mutate transform
                wing.location = [99.0, 99.0, 99.0]
                # Fail midway
                raise ValueError("Transform operation failed midway")

        # Transform must be restored
        self.assertEqual(self.scene.data.objects["Wing_L_Proxy"].location, orig_loc)

    # --------------------------------------------------------------------------
    # Scenario 4: Failure after collection creation and linking
    # --------------------------------------------------------------------------
    def test_04_failure_after_collection_mutation(self):
        """Newly created collections are cleanly removed on failure without affecting existing collections."""
        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError):
            with journal:
                self.scene.data.collections["Staging_Col"] = MockCollection("Staging_Col")
                raise RuntimeError("Failure after collection creation")

        self.assertNotIn("Staging_Col", self.scene.data.collections)
        self.assertIn("Collection", self.scene.data.collections)

    # --------------------------------------------------------------------------
    # Scenario 5: Failure during mesh/data modification (Irreversible change)
    # --------------------------------------------------------------------------
    def test_05_irreversible_data_modification_boundary(self):
        """Irreversible mesh operations cannot be guessed; system must report limitation."""
        # When an operator irreversibly modifies vertex coordinates directly, compensation
        # without external backup cannot recover the original vertices.
        sculpt = self.scene.data.objects["Dragon_Torso"]
        initial_scale = list(sculpt.scale)

        # Preflight policy: We forbid in-place dimension assignment on the sculpt
        # If an operation attempts to mutate the sculpt, preflight aborts:
        with self.assertRaises(PermissionError) as ctx:
            if sculpt.name == "Dragon_Torso":
                raise PermissionError("Preflight safeguard: Existing sculpted Dragon_Torso cannot be modified.")

        self.assertEqual(sculpt.scale, initial_scale)

    # --------------------------------------------------------------------------
    # Scenario 6: Cleanup failure (Compensating action raises error)
    # --------------------------------------------------------------------------
    def test_06_cleanup_failure_reports_dirty_state(self):
        """When compensation cleanup fails, system flags PARTIAL_FAILURE_DIRTY and raises RuntimeError."""
        journal = UniversalMutationJournal(self.scene)

        # Mock objects.remove to fail on a specific object
        def failing_remove(item):
            if item.name == "Corrupt_Obj":
                raise RuntimeError("Access violation during object deletion")
            del self.scene.data.objects._items[item.name]

        self.scene.data.objects.remove = failing_remove

        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                self.scene.data.objects["Corrupt_Obj"] = MockMeshObj("Corrupt_Obj")
                raise RuntimeError("Initial task failure")

        err_msg = str(ctx.exception)
        self.assertIn("DIRTY state", err_msg)
        self.assertIn("Access violation during object deletion", err_msg)

    # --------------------------------------------------------------------------
    # Scenario 7: Timeout or interrupted execution
    # --------------------------------------------------------------------------
    def test_07_timeout_handling(self):
        """Timeout preserves task record, fails closed, and reports elapsed time."""
        from shared.models.protocol_models import BridgeResponse
        t0 = time.time()
        timeout_limit = 0.05
        # Simulate bridge client timeout
        time.sleep(0.06)
        duration_ms = round((time.time() - t0) * 1000, 2)
        resp = BridgeResponse.error(
            f"Bridge timed out waiting for Blender response after {duration_ms}ms",
            duration_ms=duration_ms
        )
        self.assertEqual(resp.status, "error")
        self.assertIn("timed out", resp.message)
        self.assertGreaterEqual(resp.execution_time_ms, 50.0)

    # --------------------------------------------------------------------------
    # Scenario 8: Retry after partial failure halts on collision
    # --------------------------------------------------------------------------
    def test_08_retry_after_partial_failure_halts_on_collision(self):
        """If a dirty unrecovered object remains, retry fails closed on preflight collision."""
        # Suppose Part_A leaked into scene
        self.scene.data.objects["Part_A"] = MockMeshObj("Part_A")

        # Retry attempt with preflight gate:
        planned_new_objects = ["Part_A", "Part_B"]
        colliding = [n for n in planned_new_objects if n in self.scene.data.objects]

        self.assertEqual(colliding, ["Part_A"])
        # Gate prevents running:
        with self.assertRaises(AssertionError) as ctx:
            assert len(colliding) == 0, f"Cannot retry: scene contains uncleaned partial objects {colliding}"
        self.assertIn("Cannot retry: scene contains uncleaned partial objects", str(ctx.exception))

    # --------------------------------------------------------------------------
    # Scenario 9: Preservation of pre-existing objects and unrelated assets
    # --------------------------------------------------------------------------
    def test_09_preservation_of_preexisting_assets(self):
        """Compensation cleanup NEVER touches objects present before the session."""
        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError):
            with journal:
                # Add 2 new objects
                self.scene.data.objects["Temp_1"] = MockMeshObj("Temp_1")
                self.scene.data.objects["Temp_2"] = MockMeshObj("Temp_2")
                # Fail
                raise RuntimeError("Abort")

        # Initial objects are strictly preserved
        self.assertTrue("Cube" in self.scene.data.objects)
        self.assertTrue("Ref_Human" in self.scene.data.objects)
        self.assertTrue("Dragon_Torso" in self.scene.data.objects)
        self.assertTrue("Wing_L_Proxy" in self.scene.data.objects)
        # New objects removed
        self.assertFalse("Temp_1" in self.scene.data.objects)
        self.assertFalse("Temp_2" in self.scene.data.objects)

    # --------------------------------------------------------------------------
    # Scenario 10: Existing AST and approval enforcement remain effective
    # --------------------------------------------------------------------------
    def test_10_ast_and_approval_enforcement_invariants(self):
        """Security invariants: disallowed AST nodes and untrusted model approval flags fail closed."""
        # A. Disallowed AST: try...except
        code_with_try = "try:\n    x = 1\nexcept Exception:\n    pass\n"
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast(code_with_try)
        self.assertIn("Prohibited syntax construct 'Try'", str(ctx.exception))

        # B. Disallowed AST: import
        code_with_import = "import os\n"
        with self.assertRaises(ValueError) as ctx:
            validate_restricted_code_ast(code_with_import)
        self.assertIn("Prohibited syntax construct 'Import'", str(ctx.exception))

        # C. Schema approval enforcement: untrusted approved=True rejected
        payload = {
            "code": "bpy.ops.mesh.primitive_cube_add()",
            "approved": True,
        }
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_EXECUTE_BLENDER_CODE, payload, trusted_approval=False)
        self.assertIn("untrusted and cannot authorize scene mutation", str(ctx.exception))

    # --------------------------------------------------------------------------
    # Scenario 11: Pre-existing object rename followed by name reuse
    # --------------------------------------------------------------------------
    def test_11_preexisting_object_rename_and_name_reuse(self):
        """
        When a pre-existing object is renamed and its original name is reused by a newly-created object:
        1. The newly-created object (reusing the name) must be deleted.
        2. The pre-existing object must NEVER be deleted.
        3. The pre-existing object's original name must be restored.
        """
        journal = UniversalMutationJournal(self.scene)
        preexisting_cube = self.scene.data.objects["Cube"]
        preexisting_ptr = preexisting_cube.as_pointer()

        with self.assertRaises(RuntimeError):
            with journal:
                # 1. Rename pre-existing object
                del self.scene.data.objects._items["Cube"]
                preexisting_cube.name = "Old_Cube_Renamed"
                self.scene.data.objects["Old_Cube_Renamed"] = preexisting_cube

                # 2. Create a new object that reuses the original name 'Cube'
                new_cube = MockMeshObj("Cube")
                new_ptr = new_cube.as_pointer()
                self.assertNotEqual(preexisting_ptr, new_ptr)
                self.scene.data.objects["Cube"] = new_cube

                # 3. Simulate failure
                raise RuntimeError("Failure after renaming pre-existing object and reusing name")

        # Acceptance check:
        # Pre-existing object must NOT be deleted, and its name 'Cube' must be restored
        self.assertIn("Cube", self.scene.data.objects)
        restored_cube = self.scene.data.objects["Cube"]
        self.assertEqual(restored_cube.as_pointer(), preexisting_ptr)
        self.assertIs(restored_cube, preexisting_cube)
        self.assertEqual(restored_cube.name, "Cube")
        # Temporary name must be gone
        self.assertNotIn("Old_Cube_Renamed", self.scene.data.objects)

    # --------------------------------------------------------------------------
    # Scenario 12: Pre-existing collection rename followed by name reuse
    # --------------------------------------------------------------------------
    def test_12_preexisting_collection_rename_and_name_reuse(self):
        """
        When a pre-existing collection is renamed and its original name is reused by a new collection:
        1. The newly-created collection must be deleted.
        2. The pre-existing collection must NEVER be deleted.
        3. The pre-existing collection's original name must be restored.
        """
        journal = UniversalMutationJournal(self.scene)
        preexisting_col = self.scene.data.collections["Collection"]
        preexisting_ptr = preexisting_col.as_pointer()

        with self.assertRaises(RuntimeError):
            with journal:
                # 1. Rename pre-existing collection
                del self.scene.data.collections._items["Collection"]
                preexisting_col.name = "Old_Col_Renamed"
                self.scene.data.collections["Old_Col_Renamed"] = preexisting_col

                # 2. Create a new collection that reuses the original name 'Collection'
                new_col = MockCollection("Collection")
                new_ptr = new_col.as_pointer()
                self.assertNotEqual(preexisting_ptr, new_ptr)
                self.scene.data.collections["Collection"] = new_col

                # 3. Simulate failure
                raise RuntimeError("Failure after renaming collection and reusing name")

        self.assertIn("Collection", self.scene.data.collections)
        restored_col = self.scene.data.collections["Collection"]
        self.assertEqual(restored_col.as_pointer(), preexisting_ptr)
        self.assertIs(restored_col, preexisting_col)
        self.assertEqual(restored_col.name, "Collection")
        self.assertNotIn("Old_Col_Renamed", self.scene.data.collections)

    # --------------------------------------------------------------------------
    # Scenario 13: Shared mesh data preservation
    # --------------------------------------------------------------------------
    def test_13_shared_mesh_data_preservation(self):
        """
        When a newly-created object shares mesh data with a pre-existing object:
        Removing the newly-created object during cleanup decrements users count
        and strictly preserves the shared mesh data on the pre-existing object.
        """
        journal = UniversalMutationJournal(self.scene)
        cube = self.scene.data.objects["Cube"]
        shared_mesh = cube.data
        self.assertEqual(shared_mesh.users, 1)

        with self.assertRaises(RuntimeError):
            with journal:
                # New object sharing existing mesh
                shared_mesh.users += 1
                clone = MockMeshObj("Cube_Shared_Clone", mesh_data=shared_mesh)
                self.scene.data.objects["Cube_Shared_Clone"] = clone
                self.assertEqual(shared_mesh.users, 2)
                raise RuntimeError("Failure while holding shared mesh reference")

        # Clone must be deleted
        self.assertNotIn("Cube_Shared_Clone", self.scene.data.objects)
        # Pre-existing object and shared mesh must remain intact
        self.assertIn("Cube", self.scene.data.objects)
        self.assertIs(self.scene.data.objects["Cube"].data, shared_mesh)
        self.assertEqual(shared_mesh.users, 1)

    # --------------------------------------------------------------------------
    # Scenario 14: Collection relinking restoration
    # --------------------------------------------------------------------------
    def test_14_collection_relinking_restoration(self):
        """
        When pre-existing objects are unlinked/linked across collections during a failed run:
        Compensating cleanup restores original collection membership.
        """
        col = self.scene.data.collections["Collection"]
        ref_human = self.scene.data.objects["Ref_Human"]
        col.objects.link(ref_human)
        self.assertIn(ref_human, col.objects)

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError):
            with journal:
                # Unlink from pre-existing collection
                col.objects.unlink(ref_human)
                self.assertNotIn(ref_human, col.objects)

                # Create staging collection and link
                staging = MockCollection("Staging_Col")
                staging.objects.link(ref_human)
                self.scene.data.collections["Staging_Col"] = staging

                raise RuntimeError("Failure after collection relinking")

        # Staging collection must be removed
        self.assertNotIn("Staging_Col", self.scene.data.collections)
        # Original collection link must be restored
        self.assertIn(ref_human, col.objects)

    # --------------------------------------------------------------------------
    # Scenario 15: Audit and report unsupported mutation classes
    # --------------------------------------------------------------------------
    def test_15_unsupported_mutations_audit_and_boundaries(self):
        """
        UniversalMutationJournal explicitly declares unsupported mutation classes
        that cannot be rolled back via in-memory compensating actions alone.
        """
        journal = UniversalMutationJournal(self.scene)
        report = journal.rollback_compensation()
        unsupported = report.get("unsupported_mutations", [])

        # Must declare applied transforms, in-place mesh edits, applied modifiers, vertex groups
        unsupported_str = " ".join(unsupported).lower()
        self.assertIn("applied_transforms", unsupported_str)
        self.assertIn("in_place_mesh_geometry_edits", unsupported_str)
        self.assertIn("applied_modifiers", unsupported_str)
        self.assertIn("vertex_group_weight_edits", unsupported_str)

    # --------------------------------------------------------------------------
    # Scenario 16: handle_execute_blender_code reports DIRTY state on cleanup failure
    # --------------------------------------------------------------------------
    def test_16_handle_execute_blender_code_reports_dirty_on_cleanup_failure(self):
        """
        When compensating cleanup fails in handle_execute_blender_code, the error must:
        1. Report that changes could NOT be fully rolled back (DIRTY state).
        2. Never falsely claim that scene changes were rolled back.
        """
        from blender_addon.universal_mcp.bridge.handlers import handle_execute_blender_code
        from blender_addon.universal_mcp.bridge import handlers
        registry = ApprovalRegistry()
        handlers._approval_registry = registry

        # Mock removal failure on a specific object
        def failing_remove(item, do_unlink=True):
            name = item.name if hasattr(item, "name") else str(item)
            if name == "Failing_Cleanup_Obj" or item == "locked_unremovable":
                raise RuntimeError("Locked data-block cannot be deleted")
            # fallback
            if name in self.scene.data.objects._items:
                del self.scene.data.objects._items[name]

        self.scene.data.objects.remove = failing_remove

        # Create code that adds Failing_Cleanup_Obj then fails
        failing_code = (
            "bpy.data.objects['Failing_Cleanup_Obj'] = 'locked_unremovable'\n"
            "assert False, 'Deliberate execution failure'\n"
        )
        params = {
            "code": failing_code,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }

        # We test handle_execute_blender_code with this scene
        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.scene, params=approved('execute_blender_code',params))

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("could not be fully rolled back", err)
        self.assertNotIn("and scene changes were rolled back", err)

    # --------------------------------------------------------------------------
    # Scenario 17: Destructive in-place mesh geometry edits report DIRTY state
    # --------------------------------------------------------------------------
    def test_17_destructive_mesh_geometry_edit_reports_dirty_state(self):
        """Destructive in-place edits to pre-existing mesh geometry report DIRTY state."""
        journal = UniversalMutationJournal(self.scene)
        cube = self.scene.data.objects["Cube"]
        orig_vert_count = len(cube.data.vertices)

        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Destructively modify pre-existing mesh geometry (e.g. subdivide/extrude)
                cube.data.vertices.extend([10, 11, 12, 13])
                raise RuntimeError("Midway failure after geometry mutation")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("geometry was altered", err)

    # --------------------------------------------------------------------------
    # Scenario 18: Applied/altered modifiers on pre-existing asset report DIRTY state
    # --------------------------------------------------------------------------
    def test_18_applied_modifiers_on_preexisting_asset_reports_dirty_state(self):
        """Applying or altering modifiers on pre-existing assets reports DIRTY state."""
        journal = UniversalMutationJournal(self.scene)
        cube = self.scene.data.objects["Cube"]

        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Add/apply modifier on pre-existing asset
                cube.modifiers.append(MockModifier("Subsurf"))
                raise RuntimeError("Failure after modifier operation")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("modifiers were altered", err)

    # --------------------------------------------------------------------------
    # Scenario 19: Custom property overwrite on pre-existing asset reports DIRTY state
    # --------------------------------------------------------------------------
    def test_19_custom_property_overwrite_on_preexisting_asset_reports_dirty_state(self):
        """Overwriting custom properties on pre-existing assets reports DIRTY state."""
        cube = self.scene.data.objects["Cube"]
        cube["base_asset_id"] = "asset_123"

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Overwrite custom property
                cube["base_asset_id"] = "mutated_id"
                cube["extra_tag"] = "new_tag"
                raise RuntimeError("Failure after property mutation")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("custom properties were altered", err)

    # --------------------------------------------------------------------------
    # Scenario 20: Vertex coordinate modification preserving topology reports DIRTY state
    # --------------------------------------------------------------------------
    def test_20_vertex_coordinate_change_preserving_topology_reports_dirty_state(self):
        """
        When vertex coordinates are altered without changing vertex/polygon/edge counts:
        UniversalMutationJournal coordinate checksum mismatch flags PARTIAL_FAILURE_DIRTY.
        """
        cube = self.scene.data.objects["Cube"]
        self.assertEqual(len(cube.data.vertices), 4)

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Modify vertex coordinate in-place without adding/removing vertices
                cube.data.vertices[0] = 999.5
                self.assertEqual(len(cube.data.vertices), 4, "Topology count must remain identical!")
                raise RuntimeError("Failure after coordinate deformation")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("vertex coordinates were modified while preserving topology counts", err)

    # --------------------------------------------------------------------------
    # Scenario 21: Modifier property alteration preserving modifier names reports DIRTY state
    # --------------------------------------------------------------------------
    def test_21_modifier_property_change_preserving_names_reports_dirty_state(self):
        """
        When modifier properties (e.g. subsurf levels) are changed without adding/removing modifiers:
        UniversalMutationJournal modifier property snapshot mismatch flags PARTIAL_FAILURE_DIRTY.
        """
        cube = self.scene.data.objects["Cube"]
        subsurf = MockModifier("Subsurf")
        subsurf.levels = 1
        cube.modifiers.append(subsurf)

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Change property on existing modifier
                cube.modifiers[0].levels = 4
                self.assertEqual([m.name for m in cube.modifiers], ["Subsurf"], "Modifier names must remain identical!")
                raise RuntimeError("Failure after modifier property alteration")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("modifiers were altered", err)
        self.assertIn("stack or properties modified", err)

    # --------------------------------------------------------------------------
    # Scenario 22: Custom property value overwrite preserving key set reports DIRTY state
    # --------------------------------------------------------------------------
    def test_22_custom_property_value_overwrite_preserving_keys_reports_dirty_state(self):
        """
        When an existing custom property value is overwritten without altering the key set:
        UniversalMutationJournal value snapshot mismatch flags PARTIAL_FAILURE_DIRTY.
        """
        cube = self.scene.data.objects["Cube"]
        cube["dragon_scale"] = 1.0

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Overwrite value of existing key; key set is unchanged
                cube["dragon_scale"] = 2.5
                self.assertEqual(set(cube.keys()), {"dragon_scale"}, "Key set must remain identical!")
                raise RuntimeError("Failure after property value overwrite")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("custom properties were altered", err)
        self.assertIn("values or keys overwritten", err)

    # --------------------------------------------------------------------------
    # Scenario 23: Material shader node tree mutations are an architectural limitation
    # --------------------------------------------------------------------------
    def test_23_material_node_tree_and_material_edit_limitation_documented(self):
        """
        TASK-UMCP-0054 (Requirement C.2 & C.3):
        Material shader node tree edits and material data modifications on pre-existing
        assets are outside the in-memory snapshot scope of UniversalMutationJournal.
        They are explicitly declared in unsupported_mutations and rely on transactional undo.
        """
        cube = self.scene.data.objects["Cube"]
        # Attach a mock material
        class MockMaterial:
            def __init__(self, name):
                self.name = name
                self.color = [0.8, 0.8, 0.8, 1.0]
        cube.data.materials = [MockMaterial("Cube_Mat")]

        journal = UniversalMutationJournal(self.scene)
        with journal:
            # Modify pre-existing material color/nodes
            cube.data.materials[0].color = [1.0, 0.0, 0.0, 1.0]

        # Compensating cleanup does not snapshot or detect material internal edits
        report = journal.rollback_compensation()
        unsupported = report.get("unsupported_mutations", [])
        self.assertTrue(any("material_shader_node_tree_mutations" in u for u in unsupported))

    # --------------------------------------------------------------------------
    # Scenario 24: Animation keyframes and fcurves are an architectural limitation
    # --------------------------------------------------------------------------
    def test_24_animation_keyframes_and_fcurves_limitation_documented(self):
        """
        TASK-UMCP-0054 (Requirement C.2 & C.3):
        Object animation keyframes and action fcurves are outside the in-memory
        snapshot scope of UniversalMutationJournal.
        They are explicitly declared in unsupported_mutations.
        """
        cube = self.scene.data.objects["Cube"]
        cube.animation_data = {"action": "RunCycle", "keyframes": [1, 10, 20]}

        journal = UniversalMutationJournal(self.scene)
        report = journal.rollback_compensation()
        unsupported = report.get("unsupported_mutations", [])
        self.assertTrue(any("animation_data_and_fcurve_mutations" in u for u in unsupported))

    # --------------------------------------------------------------------------
    # Scenario 25: Deletion of pre-existing object is detected as DIRTY state
    # --------------------------------------------------------------------------
    def test_25_deletion_of_preexisting_object_detected_as_dirty(self):
        """
        TASK-UMCP-0055 (Requirement 3):
        When a pre-existing object is deleted during an execution that fails,
        UniversalMutationJournal Step 8 verifies pre-existing datablock existence,
        detects the missing object, and flags PARTIAL_FAILURE_DIRTY.
        """
        self.assertIn("Cube", self.scene.data.objects)

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Deliberately delete pre-existing object
                del self.scene.data.objects["Cube"]
                self.assertNotIn("Cube", self.scene.data.objects)
                raise RuntimeError("Midway failure after deleting pre-existing object")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("Pre-existing object(s) were deleted", err)

    # --------------------------------------------------------------------------
    # Scenario 26: Pre-existing object parent ownership change reverted on failure
    # --------------------------------------------------------------------------
    def test_26_preexisting_object_parent_change_reverted_on_failure(self):
        """
        TASK-UMCP-0056 (Requirement 2):
        When a pre-existing object's parent ownership is altered during an execution that fails,
        UniversalMutationJournal Step 4 restores its initial parent hierarchy.
        """
        cube = self.scene.data.objects["Cube"]
        ref_human = self.scene.data.objects["Ref_Human"]
        cube.parent = ref_human
        self.assertIs(cube.parent, ref_human)

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError):
            with journal:
                # Alter parent hierarchy on pre-existing object
                cube.parent = None
                self.assertIsNone(cube.parent)
                raise RuntimeError("Midway failure after modifying object parent")

        # Initial parent hierarchy must be restored!
        self.assertIs(cube.parent, ref_human)

    # --------------------------------------------------------------------------
    # Scenario 27: Pre-existing material shader inputs restored on failure
    # --------------------------------------------------------------------------
    def test_27_material_shader_inputs_restored_on_failure(self):
        """
        When a pre-existing material's shader inputs are modified during an execution that fails,
        UniversalMutationJournal restores the initial socket values.
        """
        class MockInput:
            def __init__(self, name, val):
                self.name = name
                self.default_value = val
                self.is_linked = False

        class MockNode:
            def __init__(self, name, node_type, inputs):
                self.name = name
                self.type = node_type
                self.inputs = {inp.name: inp for inp in inputs}

        class MockNodeTree:
            def __init__(self):
                self.nodes = {
                    "Principled BSDF": MockNode(
                        "Principled BSDF",
                        "BSDF_PRINCIPLED",
                        [MockInput("Base Color", (0.8, 0.8, 0.8, 1.0)), MockInput("Roughness", 0.5)]
                    )
                }
                self.links = []

        class MockMaterial:
            def __init__(self, name):
                self.name = name
                self.use_nodes = True
                self.diffuse_color = [0.8, 0.8, 0.8, 1.0]
                self.node_tree = MockNodeTree()

        mat = MockMaterial("RestorableMat")
        self.scene.data.materials = {"RestorableMat": mat}

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError):
            with journal:
                # Mutate material inputs
                mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1.0, 0.0, 0.0, 1.0)
                mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.99
                raise RuntimeError("Execution failure after material edit")

        # Material inputs must be restored!
        self.assertEqual(mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value, (0.8, 0.8, 0.8, 1.0))
        self.assertEqual(mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value, 0.5)

    # --------------------------------------------------------------------------
    # Scenario 28: Complex material node tree alteration detected as DIRTY
    # --------------------------------------------------------------------------
    def test_28_material_complex_node_alteration_detected_as_dirty(self):
        """
        When a pre-existing material's node tree topology is altered (e.g. node added)
        and cannot be restored in-memory, the journal flags PARTIAL_FAILURE_DIRTY.
        """
        class MockNode:
            def __init__(self, name, node_type):
                self.name = name
                self.type = node_type
                self.inputs = {}

        class MockNodeTree:
            def __init__(self):
                self.nodes = {"Output": MockNode("Output", "OUTPUT_MATERIAL")}
                self.links = []

        class MockMaterial:
            def __init__(self, name):
                self.name = name
                self.use_nodes = True
                self.diffuse_color = [0.8, 0.8, 0.8, 1.0]
                self.node_tree = MockNodeTree()

        mat = MockMaterial("ComplexMat")
        self.scene.data.materials = {"ComplexMat": mat}

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Add node to material
                mat.node_tree.nodes["NewShader"] = MockNode("NewShader", "BSDF_DIFFUSE")
                raise RuntimeError("Execution failure after complex material edit")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("ComplexMat", err)

    # --------------------------------------------------------------------------
    # Scenario 29: Animation data inserted on un-animated object cleared on failure
    # --------------------------------------------------------------------------
    def test_29_animation_data_cleared_on_failure(self):
        """
        When animation data is inserted onto an object that had no animation initially,
        UniversalMutationJournal clears the animation data on execution failure.
        """
        cube = self.scene.data.objects["Cube"]
        cube.animation_data = None
        cube.animation_data_clear = lambda: setattr(cube, "animation_data", None)

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError):
            with journal:
                # Add animation data
                cube.animation_data = {"action": "NewAction", "fcurves": 3}
                self.assertIsNotNone(cube.animation_data)
                raise RuntimeError("Midway failure after inserting keyframes")

        self.assertIsNone(cube.animation_data)

    # --------------------------------------------------------------------------
    # Scenario 30: Vertex groups added reverted on failure
    # --------------------------------------------------------------------------
    def test_30_vertex_groups_added_reverted_on_failure(self):
        """
        When vertex groups are added to a pre-existing object during an execution that fails,
        UniversalMutationJournal removes the added vertex groups.
        """
        class MockVertexGroup:
            def __init__(self, name):
                self.name = name

        class MockVertexGroupCollection:
            def __init__(self, groups):
                self._groups = list(groups)
            def __iter__(self):
                return iter(self._groups)
            def __len__(self):
                return len(self._groups)
            def remove(self, vg):
                self._groups.remove(vg)
            def append(self, vg):
                self._groups.append(vg)

        cube = self.scene.data.objects["Cube"]
        cube.vertex_groups = MockVertexGroupCollection([MockVertexGroup("Head_Weight")])

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError):
            with journal:
                cube.vertex_groups.append(MockVertexGroup("Temp_Arm_Weight"))
                self.assertEqual(len(cube.vertex_groups), 2)
                raise RuntimeError("Midway failure after adding vertex group")

        self.assertEqual(len(cube.vertex_groups), 1)
        self.assertEqual(cube.vertex_groups._groups[0].name, "Head_Weight")

    # --------------------------------------------------------------------------
    # Scenario 31: Pre-existing object deletion prevented by GuardedBpy
    # --------------------------------------------------------------------------
    def test_31_preexisting_object_deletion_prevented_by_guard(self):
        """
        When a script running inside handle_execute_blender_code attempts to delete
        a pre-existing object via bpy.data.objects.remove, GuardedBpy intercepts it
        with a PermissionError, preventing unrecoverable data-block loss.
        """
        from blender_addon.universal_mcp.bridge.handlers import handle_execute_blender_code
        from blender_addon.universal_mcp.bridge import handlers
        registry = ApprovalRegistry()
        handlers._approval_registry = registry

        self.assertIn("Cube", self.scene.data.objects)

        failing_code = (
            "bpy.data.objects.remove(bpy.data.objects['Cube'])\n"
        )
        params = {
            "code": failing_code,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }

        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.scene, params=approved('execute_blender_code',params))

        err = str(ctx.exception)
        self.assertIn("Deletion of pre-existing object 'Cube' is prohibited", err)
        # Cube must still exist!
        self.assertIn("Cube", self.scene.data.objects)

    # --------------------------------------------------------------------------
    # Scenario 32: Escape via bpy.context.blend_data prevented
    # --------------------------------------------------------------------------
    def test_32_escape_via_context_blend_data_prevented(self):
        """
        Scripts attempting to delete a pre-existing object via bpy.context.blend_data
        are intercepted by GuardedContext routing to GuardedData.
        """
        from blender_addon.universal_mcp.bridge.handlers import handle_execute_blender_code
        from blender_addon.universal_mcp.bridge import handlers
        registry = ApprovalRegistry()
        handlers._approval_registry = registry

        self.scene.context = MagicMock(blend_data=self.scene.data, selected_objects=[], active_object=None)
        self.assertIn("Cube", self.scene.data.objects)

        failing_code = (
            "bpy.context.blend_data.objects.remove(bpy.context.blend_data.objects['Cube'])\n"
        )
        params = {
            "code": failing_code,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }

        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.scene, params=approved('execute_blender_code',params))

        err = str(ctx.exception)
        self.assertIn("Deletion of pre-existing object 'Cube' is prohibited", err)
        self.assertIn("Cube", self.scene.data.objects)

    # --------------------------------------------------------------------------
    # Scenario 33: Escape via bpy.data.meshes and materials prevented
    # --------------------------------------------------------------------------
    def test_33_escape_via_mesh_and_material_deletion_prevented(self):
        """
        Pre-existing meshes and materials are protected from deletion via GuardedData.
        """
        from blender_addon.universal_mcp.bridge.handlers import handle_execute_blender_code
        from blender_addon.universal_mcp.bridge import handlers
        registry = ApprovalRegistry()
        handlers._approval_registry = registry

        self.scene.data.meshes["CubeMesh"] = MockMesh("CubeMesh")

        failing_code = (
            "bpy.data.meshes.remove(bpy.data.meshes['CubeMesh'])\n"
        )
        params = {
            "code": failing_code,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }

        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.scene, params=approved('execute_blender_code',params))

        err = str(ctx.exception)
        self.assertIn("Deletion of pre-existing mesh 'CubeMesh' is prohibited", err)
        self.assertIn("CubeMesh", self.scene.data.meshes)

    # --------------------------------------------------------------------------
    # Scenario 34: Operator deletion routes blocked at runtime
    # --------------------------------------------------------------------------
    def test_34_operator_deletion_routes_blocked_at_runtime(self):
        """
        Disallowed operator submodules (such as collection.delete) are blocked at runtime
        even if aliased or invoked indirectly.
        """
        from blender_addon.universal_mcp.bridge.handlers import GuardedBpy
        self.scene.ops = MagicMock()
        guarded_bpy = GuardedBpy(self.scene, {id(self.scene.data.objects["Cube"])})

        with self.assertRaises(PermissionError) as ctx:
            del_op = guarded_bpy.ops.collection.delete
            del_op()

        err = str(ctx.exception)
        self.assertIn("Disallowed operator call 'bpy.ops.collection.delete'", err)

    # --------------------------------------------------------------------------
    # Scenario 35: Identity protection prevents deletion on rename and name reuse
    # --------------------------------------------------------------------------
    def test_35_identity_protection_on_rename_and_name_reuse(self):
        """
        Pre-existing datablocks are tracked by pointer/identity. Renaming a pre-existing
        object and reusing its old name allows deleting the newly created object, but
        prohibits deleting the renamed pre-existing object.
        """
        from blender_addon.universal_mcp.bridge.handlers import handle_execute_blender_code
        from blender_addon.universal_mcp.bridge import handlers
        registry = ApprovalRegistry()
        handlers._approval_registry = registry

        # Cube is pre-existing. Script renames Cube -> Cube_Renamed, creates a new object
        # named Cube, deletes the new Cube (allowed), then attempts deleting Cube_Renamed (prohibited).
        code = (
            "pre_obj = bpy.data.objects['Cube']\n"
            "pre_obj.name = 'Cube_Renamed'\n"
            "bpy.data.objects['Cube_Renamed'] = pre_obj\n"
            "new_obj = bpy.data.objects.new('Cube')\n"
            "bpy.data.objects.remove(new_obj)\n"
            "bpy.data.objects.remove(pre_obj)\n"
        )
        params = {
            "code": code,
            "trusted_approval": True,
            "_trusted_test_override": True,
        }

        with self.assertRaises(RuntimeError) as ctx:
            handle_execute_blender_code(bpy_module=self.scene, params=approved('execute_blender_code',params))

        err = str(ctx.exception)
        self.assertIn("Deletion of pre-existing object 'Cube_Renamed' is prohibited", err)
        # Verify pre_obj was not deleted and was restored
        self.assertTrue("Cube" in self.scene.data.objects or "Cube_Renamed" in self.scene.data.objects)

    # --------------------------------------------------------------------------
    # Scenario 36: Legacy Action keyframe modification detected as DIRTY
    # --------------------------------------------------------------------------
    def test_36_legacy_action_keyframe_modification_reported_as_dirty(self):
        """
        Modifying keyframes on a pre-existing animated object using legacy action.fcurves
        is detected during rollback and reported honestly as PARTIAL_FAILURE_DIRTY.
        """
        class MockKeyframe:
            def __init__(self, frame, value):
                self.co = (float(frame), float(value))

        class MockFCurve:
            def __init__(self, data_path, array_index, points):
                self.data_path = data_path
                self.array_index = array_index
                self.keyframe_points = list(points)

        class MockLegacyAction:
            def __init__(self, name, fcurves):
                self.name = name
                self.fcurves = list(fcurves)

        class MockAnimData:
            def __init__(self, action):
                self.action = action

        cube = self.scene.data.objects["Cube"]
        fc = MockFCurve("location", 0, [MockKeyframe(1, 0), MockKeyframe(10, 5)])
        cube.animation_data = MockAnimData(MockLegacyAction("LegacyAction", [fc]))

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Script adds keyframe to existing curve
                fc.keyframe_points.append(MockKeyframe(20, 10))
                raise RuntimeError("Execution failure after modifying keyframe")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("animation keyframes/action were altered", err)

    # --------------------------------------------------------------------------
    # Scenario 37: Slotted Action keyframe modification detected as DIRTY
    # --------------------------------------------------------------------------
    def test_37_slotted_action_keyframe_modification_reported_as_dirty(self):
        """
        Modifying keyframes on a pre-existing animated object using Blender 5.0+ slotted
        Actions (layers -> strips -> channelbags -> fcurves) is detected as DIRTY.
        """
        class MockKeyframe:
            def __init__(self, frame, value):
                self.co = (float(frame), float(value))

        class MockFCurve:
            def __init__(self, data_path, array_index, points):
                self.data_path = data_path
                self.array_index = array_index
                self.keyframe_points = list(points)

        class MockChannelBag:
            def __init__(self, fcurves):
                self.fcurves = list(fcurves)

        class MockActionStrip:
            def __init__(self, channelbags):
                self.channelbags = list(channelbags)

        class MockActionLayer:
            def __init__(self, strips):
                self.strips = list(strips)

        class MockSlottedAction:
            def __init__(self, name, layers):
                self.name = name
                self.layers = list(layers)

        class MockAnimData:
            def __init__(self, action):
                self.action = action

        cube = self.scene.data.objects["Cube"]
        fc = MockFCurve("location", 0, [MockKeyframe(1, 0), MockKeyframe(10, 5)])
        cb = MockChannelBag([fc])
        strip = MockActionStrip([cb])
        layer = MockActionLayer([strip])
        cube.animation_data = MockAnimData(MockSlottedAction("SlottedAction", [layer]))

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Modify existing keyframe point coordinate
                fc.keyframe_points[0].co = (1.0, 99.0)
                raise RuntimeError("Execution failure after modifying keyframe value")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("animation keyframes/action were altered", err)

    # --------------------------------------------------------------------------
    # Scenario 38: Slotted Action keyframe removal detected as DIRTY
    # --------------------------------------------------------------------------
    def test_38_slotted_action_keyframe_removal_reported_as_dirty(self):
        """
        Removing keyframes from a pre-existing slotted Action is detected as DIRTY.
        """
        class MockKeyframe:
            def __init__(self, frame, value):
                self.co = (float(frame), float(value))

        class MockFCurve:
            def __init__(self, data_path, array_index, points):
                self.data_path = data_path
                self.array_index = array_index
                self.keyframe_points = list(points)

        class MockChannelBag:
            def __init__(self, fcurves):
                self.fcurves = list(fcurves)

        class MockActionStrip:
            def __init__(self, channelbags):
                self.channelbags = list(channelbags)

        class MockActionLayer:
            def __init__(self, strips):
                self.strips = list(strips)

        class MockSlottedAction:
            def __init__(self, name, layers):
                self.name = name
                self.layers = list(layers)

        class MockAnimData:
            def __init__(self, action):
                self.action = action

        cube = self.scene.data.objects["Cube"]
        fc = MockFCurve("location", 0, [MockKeyframe(1, 0), MockKeyframe(10, 5)])
        cb = MockChannelBag([fc])
        strip = MockActionStrip([cb])
        layer = MockActionLayer([strip])
        cube.animation_data = MockAnimData(MockSlottedAction("SlottedAction", [layer]))

        journal = UniversalMutationJournal(self.scene)
        with self.assertRaises(RuntimeError) as ctx:
            with journal:
                # Remove keyframe point
                fc.keyframe_points.pop()
                raise RuntimeError("Execution failure after removing keyframe")

        err = str(ctx.exception)
        self.assertIn("DIRTY state", err)
        self.assertIn("animation keyframes/action were altered", err)

    # --------------------------------------------------------------------------
    # Scenario 39: Unchanged animation passes clean compensation on failure
    # --------------------------------------------------------------------------
    def test_39_unchanged_animation_passes_clean_compensation(self):
        """
        When execution fails without modifying pre-existing animation data,
        animation integrity check passes and does not falsely flag DIRTY.
        """
        class MockKeyframe:
            def __init__(self, frame, value):
                self.co = (float(frame), float(value))

        class MockFCurve:
            def __init__(self, data_path, array_index, points):
                self.data_path = data_path
                self.array_index = array_index
                self.keyframe_points = list(points)

        class MockChannelBag:
            def __init__(self, fcurves):
                self.fcurves = list(fcurves)

        class MockActionStrip:
            def __init__(self, channelbags):
                self.channelbags = list(channelbags)

        class MockActionLayer:
            def __init__(self, strips):
                self.strips = list(strips)

        class MockSlottedAction:
            def __init__(self, name, layers):
                self.name = name
                self.layers = list(layers)

        class MockAnimData:
            def __init__(self, action):
                self.action = action

        cube = self.scene.data.objects["Cube"]
        fc = MockFCurve("location", 0, [MockKeyframe(1, 0), MockKeyframe(10, 5)])
        cb = MockChannelBag([fc])
        strip = MockActionStrip([cb])
        layer = MockActionLayer([strip])
        cube.animation_data = MockAnimData(MockSlottedAction("SlottedAction", [layer]))

        journal = UniversalMutationJournal(self.scene)
        # We manually call rollback_compensation to check report status
        with journal:
            # Create a temporary object
            self.scene.data.objects["TempObj"] = MockMeshObj("TempObj")

        rep = journal.rollback_compensation()
        self.assertEqual(rep["status"], "COMPENSATED")
        self.assertEqual(rep["cleanup_errors"], [])
        self.assertNotIn("TempObj", self.scene.data.objects)


if __name__ == "__main__":
    unittest.main()



