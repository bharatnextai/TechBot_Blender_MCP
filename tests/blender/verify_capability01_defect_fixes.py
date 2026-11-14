"""Run only in a new --background --factory-startup Blender. No bridge/network/save."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
import bpy
from blender_addon.universal_mcp.bridge import handlers, curve_tools, sculpt_tools
from blender_addon.universal_mcp.bridge.component_edit import handle_edit_mesh
from blender_addon.universal_mcp.bridge.mesh_topology import inspect_elements
from blender_addon.universal_mcp.bridge.modifier_stack import inspect as inspect_stack


class DefectRuntimeTests(unittest.TestCase):
    observations = []
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        scene = bpy.data.scenes.new(self._testMethodName)
        bpy.context.window.scene = scene
        if not hasattr(bpy.types.Scene, 'umcp_require_scene_mutation_approval'):
            bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=False)
        scene.umcp_require_scene_mutation_approval = False

    def cube(self):
        bpy.ops.mesh.primitive_cube_add()
        return bpy.context.object

    def snapshot(self, obj):
        return inspect_elements(obj, bpy.context, {'element_domain': 'vertices', 'limit': 1000})

    def assert_closed(self, obj):
        from collections import Counter
        incidence = Counter()
        for face in obj.data.polygons:
            ids = list(face.vertices)
            for a, b in zip(ids, ids[1:] + ids[:1]):
                incidence[tuple(sorted((a, b)))] += 1
        self.assertTrue(incidence)
        self.assertEqual(set(incidence.values()), {2})
        self.observations.append(dict(test=self._testMethodName, object=obj.name,
            vertices=len(obj.data.vertices), faces=len(obj.data.polygons), edge_face_incidence=sorted(set(incidence.values()))))

    def test_extrusion_aliases_and_component_regions(self):
        for tool in ('extrude_mesh', 'extrude_faces', 'edit_mesh'):
            for faces in ([5], [1, 5]):
                with self.subTest(tool=tool, faces=faces):
                    obj = self.cube()
                    before = self.snapshot(obj)
                    args = dict(name=obj.name, expected_snapshot_id=before['snapshot_id'])
                    if tool == 'edit_mesh':
                        handle_edit_mesh(bpy, dict(args, operations=[dict(action='extrude', faces=faces, delta=[.1, .2, .25])]))
                    else:
                        handlers.ALL_HANDLERS[tool](bpy, dict(args, faces=faces, direction=[.4, .8, 1], distance=.25))
                    self.assert_closed(obj)
                    if faces == [5]:
                        self.assertEqual((len(obj.data.vertices), len(obj.data.polygons)), (12, 10))
                    after = self.snapshot(obj)
                    with self.assertRaisesRegex(Exception, 'STALE'):
                        handlers.handle_extrude_mesh(bpy, dict(args, faces=[5], distance=.25))
                    self.assertEqual(self.snapshot(obj)['snapshot_id'], after['snapshot_id'])

    def test_discrete_extrusion_keeps_closed_surface(self):
        obj = self.cube(); state = self.snapshot(obj)
        handlers.handle_extrude_mesh(bpy, dict(name=obj.name, expected_snapshot_id=state['snapshot_id'],
            faces=[5], individual=True, direction=[0, 0, 1], distance=.25))
        self.assert_closed(obj)

    def test_component_failed_batch_restores_original(self):
        obj = self.cube(); original = obj.data; before = self.snapshot(obj)
        with self.assertRaisesRegex(Exception, 'ROLLED_BACK_VERIFIED'):
            handle_edit_mesh(bpy, dict(name=obj.name, expected_snapshot_id=before['snapshot_id'], operations=[
                dict(action='extrude', faces=[5], delta=[0, 0, .25]),
                dict(action='delete_faces', faces=[5])]))
        self.assertEqual(obj.data, original)
        self.assertEqual(self.snapshot(obj)['snapshot_id'], before['snapshot_id'])

    def test_curve_and_text_nonzero_world_placement(self):
        for kind in ('BEZIER', 'TEXT', 'NURBS_CURVE', 'PATH', 'NURBS_CIRCLE'):
            with self.subTest(kind=kind):
                name = 'Placed_' + kind
                handlers.handle_create_curve_or_text(bpy, dict(name=name, curve_type=kind, location=[15, 20, 0], rotation=[0, 0, .3], scale=[2, 1, 1]))
                obj = bpy.context.scene.objects[name]
                bpy.context.view_layer.update()
                self.assertLess((obj.matrix_world.translation - __import__('mathutils').Vector((15, 20, 0))).length, 1e-6)
                self.assertEqual(curve_tools.inspect(bpy, name), curve_tools.inspect(bpy, name))
                self.observations.append(dict(test=self._testMethodName, kind=kind,
                    world_matrix=[list(row) for row in obj.matrix_world]))
                if kind in ('NURBS_CURVE', 'PATH', 'NURBS_CIRCLE'):
                    self.assertEqual(obj.data.splines[0].type, 'NURBS')

    def test_curve_failed_readback_rolls_back_datablocks(self):
        before = (set(bpy.data.objects.keys()), set(bpy.data.curves.keys()))
        with patch.object(curve_tools, '_verify', side_effect=RuntimeError('injected readback failure')):
            with self.assertRaisesRegex(Exception, 'ROLLED_BACK_VERIFIED'):
                handlers.handle_create_curve_or_text(bpy, dict(name='RollbackText', curve_type='TEXT', location=[15, 20, 0]))
        self.assertEqual(before, (set(bpy.data.objects.keys()), set(bpy.data.curves.keys())))

    def test_optional_modifier_type_inferred_and_stale_rejected(self):
        obj = self.cube(); mod = obj.modifiers.new('Bevel', 'BEVEL'); mod.width = .1
        state = inspect_stack(bpy, obj.name)
        args = dict(name=obj.name, modifier_name='Bevel', expected_snapshot_id=state['snapshot_id'])
        with self.assertRaisesRegex(Exception, 'STALE'):
            handlers.handle_apply_modifier(bpy, dict(args, expected_snapshot_id='sha256:' + '0' * 64))
        self.assertEqual(len(obj.modifiers), 1)
        handlers.handle_apply_modifier(bpy, args)
        self.assertEqual(len(obj.modifiers), 0)
        self.assertEqual(len(obj.data.vertices), state['evaluated']['vertex_count'])
        self.assert_closed(obj)

    def test_uninitialized_sculpt_inspection_entry_exit_and_failure(self):
        obj = self.cube(); mesh = obj.data
        # New scenes can have tool_settings.sculpt=None until first mode entry.
        self.assertIsNone(bpy.context.scene.tool_settings.sculpt)
        state = sculpt_tools.inspect(bpy, dict(object_name=obj.name))
        self.assertEqual(bpy.context.mode, 'OBJECT')
        args = dict(object_name=obj.name, expected_snapshot_id=state['snapshot_id'])
        with self.assertRaisesRegex(Exception, 'STALE_SCULPT_SNAPSHOT'):
            sculpt_tools.handle_sculpt_mesh(bpy, dict(args, action='enter_sculpt', expected_snapshot_id='sha256:' + '0' * 64))
        self.assertEqual(bpy.context.mode, 'OBJECT')
        sculpt_tools.handle_sculpt_mesh(bpy, dict(args, action='enter_sculpt'))
        self.assertEqual(bpy.context.mode, 'SCULPT')
        self.assertIsNotNone(bpy.context.scene.tool_settings.sculpt)
        brush = bpy.context.scene.tool_settings.sculpt.brush
        observed = sculpt_tools.inspect(bpy, dict(object_name=obj.name))
        self.assertEqual(observed['brush']['name'] if observed['brush'] else None, brush.name if brush else None)
        self.observations.append(dict(test=self._testMethodName, initially_uninitialized=True,
            actual_mode=bpy.context.mode, actual_brush=observed['brush']))
        sculpt_tools.handle_sculpt_mesh(bpy, dict(args, action='exit_sculpt'))
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertEqual(obj.data, mesh)
        self.assertEqual(self.snapshot(obj)['snapshot_id'], state['snapshot_id'])

    def test_landmark_rejected_guidance_restores_coordinates(self):
        obj = self.cube(); before = [list(v.co) for v in obj.data.vertices]
        handlers.handle_configure_semantic_landmarks(bpy, dict(target_object=obj.name, landmarks=[dict(name='tip', vertex_index=0)]))
        result = handlers.handle_guide_mesh_landmarks(bpy, dict(target_object=obj.name, max_iterations=1))
        self.assertEqual(result['status'], 'ERROR')
        self.assertTrue(result['rolled_back'])
        self.assertEqual([list(v.co) for v in obj.data.vertices], before)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DefectRuntimeTests))
    output = Path(sys.argv[sys.argv.index('--') + 1])
    output.write_text(json.dumps(dict(blender=bpy.app.version_string, tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), success=result.wasSuccessful(), observations=DefectRuntimeTests.observations), indent=2))
    if not result.wasSuccessful():
        raise RuntimeError('Disposable runtime regressions failed')
