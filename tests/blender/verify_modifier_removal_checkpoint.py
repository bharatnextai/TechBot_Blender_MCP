"""Native removal fault injection in a disposable owned modifier fixture."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
PROJECT = Path(__file__).resolve().parents[2]


def fixture(root):
    import bpy
    from unittest.mock import patch
    sys.path.insert(0, str(PROJECT))
    from blender_addon.universal_mcp.bridge import modifier_tools, modifier_checkpoint
    from blender_addon.universal_mcp.bridge.local_test_scope import configure_fixture, permits_owned, record_fixture_modifier
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    assert bpy.app.background and not bpy.data.filepath
    bpy.types.Scene.umcp_require_scene_mutation_approval = bpy.props.BoolProperty(default=True)
    protected = [(o, o.data, o.matrix_world.copy()) for o in bpy.context.scene.objects]
    mesh = bpy.data.meshes.new('CheckpointOwnedMesh')
    mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
    obj = bpy.data.objects.new('CheckpointOwned', mesh)
    bpy.context.scene.collection.objects.link(obj)
    configure_fixture(bpy, root, [obj], [])
    guard = obj.modifiers.new('Guard', 'SOLIDIFY')
    events = []
    registry = get_approval_registry()
    for kind, props in [('BEVEL', {'width':.02,'segments':3}), ('SUBSURF', {'levels':1,'render_levels':1}), ('SOLIDIFY', {'thickness':.04})]:
        mod = obj.modifiers.new('Owned'+kind, kind)
        for key,value in props.items(): setattr(mod,key,value)
        obj.modifiers.move(len(obj.modifiers)-1, 0)
        obj.modifiers.active = mod
        record_fixture_modifier(bpy,obj,mod)
        args = dict(name=obj.name, modifier_name=mod.name, modifier_type=kind, action='remove', properties={})
        assert permits_owned(bpy,'configure_modifier',args,root)
        before = modifier_checkpoint.capture(obj,mod)
        names = [m.name for m in obj.modifiers]
        req = registry.create_request('configure_modifier',args)
        ok,token = registry.resolve_request(req.request_id,'approved', reason='AUTHORIZED ISOLATED modifier_bake_v1 FAULT TEST')
        assert ok
        with patch.object(modifier_tools,'_verify_stack',side_effect=RuntimeError('INJECTED_POSTCONDITION_FAILURE')):
            try: modifier_tools.handle_configure_modifier(bpy,{**args,'request_id':req.request_id,'approval_token':token})
            except RuntimeError as error:
                assert str(error) == 'INJECTED_POSTCONDITION_FAILURE', str(error)
            else: raise AssertionError('Injected failure falsely succeeded')
        after = modifier_checkpoint.capture(obj,obj.modifiers.get(args['modifier_name']))
        assert before == after and names == [m.name for m in obj.modifiers]
        assert registry.inspect_request_status(req.request_id)['token_consumed']
        events.append({'type':kind,'restored':True,'stack':names,'token_consumed':True})
    assert all(o.data == data and o.matrix_world == matrix for o,data,matrix in protected)
    result = {'status':'PASS','blender':bpy.app.version_string,'events':events,'protected_preserved':True}
    (root/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    if '--fixture' in sys.argv:
        fixture(Path(sys.argv[sys.argv.index('--fixture')+1]))
    else:
        root=Path(tempfile.mkdtemp(prefix='umcp-modifier-checkpoint-'))
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',UMCP_LOCAL_TEST_SCOPE='modifier_bake_v1')
        for key in ('CONFIG','SCRIPTS','EXTENSIONS','DATAFILES','RESOURCES'):
            folder=root/key.lower();folder.mkdir();env['BLENDER_USER_'+key]=str(folder)
        run=subprocess.run([r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe','--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).resolve()),'--','--fixture',str(root)],env=env,cwd=PROJECT,capture_output=True,text=True,timeout=60)
        (root/'blender.log').write_text(run.stdout+run.stderr)
        print(root)
        if run.returncode: print(run.stdout+run.stderr)
        assert run.returncode == 0
        print((root/'result.json').read_text())
