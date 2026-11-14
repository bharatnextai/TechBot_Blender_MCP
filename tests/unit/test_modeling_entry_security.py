"""Modeling legacy entrypoints cannot use caller flags as approval proof."""
import threading
import unittest
from types import SimpleNamespace as NS
from blender_addon.universal_mcp.bridge.handlers import handle_select_object,handle_create_curve_or_text,handle_configure_geometry_nodes,handle_duplicate_object,handle_rename_object,handle_purge_orphaned_datablocks,ALL_HANDLERS,READ_ONLY_HANDLERS

class ModelingEntrySecurityTests(unittest.TestCase):
    def setUp(self):
        self.bpy=NS(context=NS(scene=NS(umcp_require_scene_mutation_approval=True)))
    def test_caller_flags_do_not_authorize_legacy_modeling(self):
        for handler,params in ((handle_select_object,{'name':'Cube'}),(handle_create_curve_or_text,{'name':'Curve'}),(handle_configure_geometry_nodes,{'name':'Cube','action':'create'}),(handle_duplicate_object,{'name':'Cube'}),(handle_rename_object,{'name':'Cube','new_name':'Other'}),(handle_purge_orphaned_datablocks,{})):
            for flags in ({'approved':True},{'trusted_approval':True},{'trusted_approval':True,'_trusted_test_override':True}):
                with self.subTest(handler=handler.__name__,flags=flags),self.assertRaises(PermissionError):handler(self.bpy,{**params,**flags})
    def test_network_cannot_disable_approval_settings(self):
        from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
        self.assertNotIn('set_approval_settings',ALL_HANDLERS)
        self.assertNotIn('set_approval_settings',READ_ONLY_HANDLERS)
        q=MainThreadQueue(bpy_module=self.bpy)
        event=threading.Event();result={}
        q._queue.put(({'type':'set_approval_settings','params':{'require_scene_mutation_approval':False}},event,result))
        q.drain_queue()
        self.assertEqual(result['response']['status'],'error')
        self.assertTrue(self.bpy.context.scene.umcp_require_scene_mutation_approval)

    def test_network_cannot_record_human_approval(self):
        from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
        from blender_addon.universal_mcp.bridge.approval_registry import ApprovalRegistry
        self.assertNotIn('resolve_approval',ALL_HANDLERS)
        registry=ApprovalRegistry();request=registry.create_request('edit_mesh',{'name':'Owned'})
        q=MainThreadQueue(bpy_module=self.bpy);event=threading.Event();result={}
        q._queue.put(({'type':'resolve_approval','params':{'request_id':request.request_id,'decision':'approved','trusted_approval':True}},event,result))
        q.drain_queue()
        self.assertEqual(result['response']['status'],'error')
        self.assertEqual(request.status,'pending');self.assertIsNone(request.approval_token)

    def test_inspection_alias_cannot_mutate(self):
        self.assertIs(ALL_HANDLERS['inspect_geometry_nodes'],READ_ONLY_HANDLERS['inspect_geometry_nodes'])
        for action in ('create','assign_group','add_socket','set_socket_default','unknown'):
            with self.subTest(action=action),self.assertRaisesRegex(ValueError,'read-only'):
                READ_ONLY_HANDLERS['inspect_geometry_nodes'](self.bpy,{'name':'Cube','action':action,'trusted_approval':True})
    def test_non_main_thread_rejected_before_bpy_access(self):
        errors=[]
        def invoke():
            for handler,params in ((handle_select_object,{}),(handle_create_curve_or_text,{}),(handle_configure_geometry_nodes,{'action':'inspect'}),(handle_duplicate_object,{}),(handle_rename_object,{}),(handle_purge_orphaned_datablocks,{})):
                try:handler(NS(),params)
                except Exception as error:errors.append(error)
        thread=threading.Thread(target=invoke);thread.start();thread.join()
        self.assertEqual(len(errors),6)
        self.assertTrue(all(isinstance(e,RuntimeError) and 'main thread' in str(e) for e in errors))
