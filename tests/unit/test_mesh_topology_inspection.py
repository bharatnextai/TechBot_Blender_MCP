"""Bounded indexed base-mesh readback, with no scene/context writes."""
import copy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from blender_addon.universal_mcp.bridge.handlers import handle_inspect_scene_data
from blender_addon.universal_mcp.bridge import mesh_topology
from shared.schemas.tool_schemas import validate_tool_input, TOOL_DEFINITIONS
from mcp_service.registry.tool_registry import ToolRegistry


class IndexedTopologyTests(unittest.TestCase):
    def setUp(self):
        mesh = NS(vertices=[NS(index=i, co=list(co), select=False) for i, co in enumerate(((0,0,0),(2,0,0),(2,1,0),(0,1,0)))],
            edges=[NS(index=i, vertices=pair) for i,pair in enumerate(((0,1),(1,2),(2,3),(3,0)))],
            polygons=[NS(index=0, vertices=(0,1,2,3))], loops=[0]*4, has_custom_normals=False, is_editmode=False)
        self.obj = NS(name="Quad", type="MESH", mode="OBJECT", data=mesh, dimensions=[2,1,0], selected=False)
        self.context = NS(mode="OBJECT", scene=NS(objects={"Quad": self.obj}), active_object=None)
        self.bpy = NS(data=NS(objects={"Quad": self.obj}), context=self.context, ops=Mock())
        self.args = {"category": "mesh_topology", "target_name": "Quad"}

    def inspect(self, **kwargs):
        return handle_inspect_scene_data(self.bpy, {**self.args, **kwargs})

    def test_count_only_response_is_exactly_unchanged(self):
        self.assertEqual(self.inspect(), {"category":"mesh_topology", "target_name":"Quad", "vertex_count":4,
            "edge_count":4, "polygon_count":1, "loop_count":4, "has_custom_normals":False, "dimensions":[2.0,1.0,0.0]})

    def test_exact_indexed_coordinates_edges_and_faces(self):
        self.assertEqual(self.inspect(element_domain="vertices")["elements"][2], {"index":2,"co":[2.0,1.0,0.0]})
        self.assertEqual(self.inspect(element_domain="edges")["elements"][3], {"index":3,"vertices":[3,0]})
        self.assertEqual(self.inspect(element_domain="faces")["elements"], [{"index":0,"vertices":[0,1,2,3]}])
        self.assertEqual(self.inspect(element_domain="vertices")["returned_count"], 4)
        self.assertEqual(self.inspect(element_domain="edges")["returned_count"], 4)
        self.assertEqual(self.inspect(element_domain="faces")["returned_count"], 1)
        self.assertEqual(self.inspect(element_domain="vertices")["snapshot_id"], self.inspect(element_domain="faces")["snapshot_id"])

    def test_handler_repairs_legacy_helper_count_at_bridge_boundary(self):
        legacy_page = {"element_domain":"vertices", "elements":[{"index":0,"co":[0.0,0.0,0.0]}],
            "offset":0,"limit":1,"total":4,"returned":1,"next_offset":1,"has_more":True,
            "coordinate_space":"LOCAL","topology_source":"BASE_MESH","mode":"OBJECT",
            "snapshot_id":"sha256:"+"a"*64,"state_id":"sha256:"+"b"*64,
            "indices_are_snapshot_local":True,"vertex_count":4,"edge_count":4,"polygon_count":1,"loop_count":4}
        with patch("blender_addon.universal_mcp.bridge.handlers.inspect_elements", return_value=legacy_page):
            result = self.inspect(element_domain="vertices", limit=1)
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["returned_count"], 1)

    def test_pagination_and_offset_beyond_end(self):
        snapshot=self.inspect(element_domain="vertices")["snapshot_id"]
        page = self.inspect(element_domain="vertices", limit=2, offset=1, expected_snapshot_id=snapshot)
        self.assertEqual([x["index"] for x in page["elements"]], [1,2])
        self.assertEqual((page["returned"],page["total"],page["next_offset"],page["has_more"]), (2,4,3,True))
        self.assertEqual(page["returned_count"], 2)
        last = self.inspect(element_domain="vertices", limit=2, offset=3, expected_snapshot_id=snapshot)
        self.assertEqual(last["returned"],1); self.assertIsNone(last["next_offset"])
        beyond = self.inspect(element_domain="vertices", offset=10**30, expected_snapshot_id=snapshot)
        self.assertEqual(beyond["elements"],[]); self.assertFalse(beyond["has_more"])
        self.assertEqual((beyond["returned_count"], beyond["total"]), (0, 4))

    def test_pagination_reports_domain_total_and_keeps_snapshot(self):
        for domain, total in (("vertices", 4), ("edges", 4), ("faces", 1)):
            with self.subTest(domain=domain):
                first = self.inspect(element_domain=domain, limit=1)
                page = self.inspect(element_domain=domain, limit=1, offset=1,
                    expected_snapshot_id=first["snapshot_id"])
                self.assertEqual(page["snapshot_id"], first["snapshot_id"])
                self.assertEqual((page["total"], page["returned_count"], page["offset"]),
                    (total, 1 if total > 1 else 0, 1))
                if total > 1:
                    self.assertEqual([item["index"] for item in page["elements"]], [1])
                    self.assertEqual(page["next_offset"], 2)
                else:
                    self.assertEqual(page["elements"], [])
                    self.assertIsNone(page["next_offset"])

    def test_strict_invalid_pagination_both_boundaries(self):
        for key, values in {"limit":[0,-1,1001,True,1.5,"2",None], "offset":[-1,False,1.5,"2",None]}.items():
            for value in values:
                with self.subTest(key=key,value=value):
                    params = {**self.args,"element_domain":"vertices",key:value}
                    with self.assertRaises(ValueError): validate_tool_input("inspect_scene_data",params)
                    with self.assertRaises(ValueError): handle_inspect_scene_data(self.bpy,params)

    def test_invalid_domain_category_target_and_extra_fields(self):
        cases = [{"element_domain":"corners"}, {"element_domain":None}, {"element_domain":["faces"]},
            {"element_domain":"faces","category":"scene_summary"}, {"element_domain":"faces","target_name":""},
            {"element_domain":"faces","target_name":3}, {"element_domain":"faces","code":"unsafe"}]
        for extra in cases:
            with self.subTest(extra=extra):
                params={**self.args,**extra}
                with self.assertRaises(ValueError): validate_tool_input("inspect_scene_data",params)
                with self.assertRaises(ValueError): handle_inspect_scene_data(self.bpy,params)
        for extra in ({"target_name":"Missing"},):
            with self.assertRaises(ValueError): self.inspect(element_domain="faces",**extra)
        self.obj.type="CURVE"
        with self.assertRaises(ValueError): self.inspect(element_domain="faces")
        self.obj.type="MESH"; self.obj.data=None
        with self.assertRaises(ValueError): self.inspect(element_domain="faces")

    def test_inactive_scene_target_and_unsupported_modes_rejected_without_writes(self):
        self.context.scene.objects={}
        with self.assertRaisesRegex(ValueError,"active scene"):self.inspect(element_domain="vertices")
        self.context.scene.objects={"Quad":self.obj}
        for mode in ("EDIT", "SCULPT", "WEIGHT_PAINT"):
            self.obj.mode=mode
            with self.assertRaisesRegex(ValueError,"Object Mode"):self.inspect(element_domain="faces")
            self.assertEqual(self.obj.mode,mode)
        self.obj.mode="OBJECT"; self.context.mode="EDIT_MESH"
        with self.assertRaisesRegex(ValueError,"Object Mode"):self.inspect(element_domain="edges")
        self.assertEqual(self.bpy.ops.mock_calls,[])

    def test_empty_mesh_all_domains(self):
        for attr in ("vertices","edges","polygons","loops"):setattr(self.obj.data,attr,[])
        for domain in mesh_topology.DOMAINS:
            page=self.inspect(element_domain=domain)
            self.assertEqual((page["total"],page["returned"],page["elements"]),(0,0,[]))
            self.assertEqual(page["returned_count"], 0)
            self.assertIsNone(page["next_offset"])

    def test_repeated_readback_preserves_all_mock_state(self):
        before=copy.deepcopy((self.obj,self.context))
        first=self.inspect(element_domain="vertices",limit=1)
        self.assertEqual(first,self.inspect(element_domain="vertices",limit=1))
        self.assertEqual((self.obj,self.context),before)
        self.assertEqual(self.bpy.ops.mock_calls,[])

    def test_snapshot_changes_for_coordinates_and_connectivity(self):
        first=self.inspect(element_domain="faces")["snapshot_id"]
        self.obj.data.vertices[0].co[0]=1
        second=self.inspect(element_domain="faces")["snapshot_id"];self.assertNotEqual(first,second)
        self.obj.data.polygons[0].vertices=(0,3,2,1)
        self.assertNotEqual(second,self.inspect(element_domain="faces")["snapshot_id"])

    def test_resource_budgets_fail_explicitly(self):
        with patch.object(mesh_topology,"MAX_SNAPSHOT_ELEMENTS",1):
            with self.assertRaisesRegex(ValueError,"snapshot.*budget"):self.inspect(element_domain="vertices")
        with patch.object(mesh_topology,"MAX_PAGE_INDICES",2):
            with self.assertRaisesRegex(ValueError,"connectivity budget"):self.inspect(element_domain="faces",limit=1)

    def test_discovery_schema_and_read_only_classification(self):
        from blender_addon.universal_mcp.bridge.handlers import READ_ONLY_HANDLERS
        definition=TOOL_DEFINITIONS["inspect_scene_data"]
        self.assertEqual(definition["permission_tier"],"READ_ONLY")
        self.assertIn("inspect_scene_data",READ_ONLY_HANDLERS)
        schema=next(t.inputSchema for t in ToolRegistry().get_mcp_tools() if t.name=="inspect_scene_data")
        self.assertIn("element_domain",schema["properties"]); self.assertIn("allOf",schema)
        args=validate_tool_input("inspect_scene_data",{**self.args,"element_domain":"vertices"})
        self.assertEqual((args["limit"],args["offset"]),(100,0))

    def test_bound_pages_reject_changed_geometry(self):
        first=self.inspect(element_domain="vertices",limit=1)
        self.obj.data.vertices[0].co[0]=3
        with self.assertRaisesRegex(ValueError,"STALE_TOPOLOGY"):
            self.inspect(element_domain="vertices",offset=1,expected_snapshot_id=first["snapshot_id"])

    def test_snapshot_parameters_require_indexed_topology(self):
        for extra in ({"expected_snapshot_id":"invalid"},{"mesh_source":"evaluated"},
                      {"element_domain":"vertices","expected_snapshot_id":"SHA256:"+"a"*64}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):validate_tool_input("inspect_scene_data",{**self.args,**extra})

    def test_evaluated_mesh_freed_on_success_and_failure(self):
        self.context.mode="OBJECT"
        evaluated=NS(to_mesh=Mock(return_value=self.obj.data),to_mesh_clear=Mock())
        self.context.evaluated_depsgraph_get=Mock(return_value="graph")
        self.obj.evaluated_get=Mock(return_value=evaluated)
        base=self.inspect(element_domain="faces")
        actual=self.inspect(element_domain="faces",mesh_source="evaluated")
        self.assertEqual(actual["topology_source"],"EVALUATED_MESH")
        self.assertNotEqual(base["snapshot_id"],actual["snapshot_id"])
        evaluated.to_mesh_clear.assert_called_once()
        with self.assertRaisesRegex(ValueError,"STALE_TOPOLOGY"):
            self.inspect(element_domain="faces",mesh_source="evaluated",expected_snapshot_id=base["snapshot_id"])
        self.assertEqual(evaluated.to_mesh_clear.call_count,2)

    def test_mesh_edit_boolean_flags_never_authorize(self):
        from blender_addon.universal_mcp.bridge.handlers import handle_extrude_mesh,handle_inset_mesh,handle_create_primitive,handle_transform_object
        for handler in (handle_extrude_mesh,handle_inset_mesh,handle_create_primitive,handle_transform_object):
            for flags in ({"approved":True},{"trusted_approval":True},{"trusted_approval":True,"_trusted_test_override":True}):
                with self.subTest(handler=handler.__name__,flags=flags):
                    with self.assertRaises(PermissionError):handler(self.bpy,{"name":"Quad",**flags})
        self.assertEqual(self.bpy.ops.mock_calls,[])

    def test_unbound_later_page_is_rejected(self):
        params={**self.args,"element_domain":"vertices","offset":1}
        with self.assertRaisesRegex(ValueError,"expected_snapshot_id"):validate_tool_input("inspect_scene_data",params)
        with self.assertRaisesRegex(ValueError,"expected_snapshot_id"):handle_inspect_scene_data(self.bpy,params)
