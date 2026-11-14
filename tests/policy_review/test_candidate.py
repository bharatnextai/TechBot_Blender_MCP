"""Review-only contract tests. No Blender, network or token issuance."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("policy_candidate", Path(__file__).with_name("candidate.py"))
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class TestScopedCandidate(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="umcp-policy-review-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.host = dict(root=self.root, objects=frozenset({"OwnedMesh"}), modifiers={
            ("OwnedMesh", "OwnedSubsurf"): "SUBSURF"}, images=frozenset({"ExistingImage"}))
        self.mod = {"operations": [{"action": "add_modifier", "target": "OwnedMesh", "params": {
            "modifier_type": "BEVEL", "modifier_name": "NewBevel", "properties": {"width": .02, "segments": 2}}}]}
        self.bake = dict(object_name="OwnedMesh", image_name="FreshImage", bake_type="ROUGHNESS",
                         width=32, height=32, margin=2, save_filepath=str(self.root / "fresh.png"))

    def allowed(self, tool, params):
        return candidate.permits(tool, params, **self.host)

    def test_bounded_add_modify_remove(self):
        self.assertTrue(self.allowed("execute_blender_code", self.mod))
        for action in ("modify_modifier", "remove_modifier"):
            params = {"modifier_name": "OwnedSubsurf"}
            if action == "modify_modifier":
                params["properties"] = {"levels": 1}
            self.assertTrue(self.allowed("execute_blender_code", {"operations": [
                {"action": action, "target": "OwnedMesh", "params": params}]}))

    def test_no_code_flags_unknown_tools_or_batches(self):
        for key in ("code", "approved", "trusted_approval", "_trusted_test_override", "request_id", "approval_token"):
            with self.subTest(key=key):
                self.assertFalse(self.allowed("execute_blender_code", {**self.mod, key: True}))
        self.assertFalse(self.allowed("execute_blender_code", {"operations": self.mod["operations"] * 2}))
        for tool in ("delete_object", "open_blend_file", "save_blend_file", "bake_texture", "unknown"):
            with self.subTest(tool=tool):
                self.assertFalse(self.allowed(tool, self.bake))

    def test_modifier_scope_and_property_bounds(self):
        for key, value in (("target", "Cube"), ("action", "join_objects")):
            args = copy.deepcopy(self.mod); args["operations"][0][key] = value
            self.assertFalse(self.allowed("execute_blender_code", args))
        for props in ({"width": float("nan")}, {"width": float("inf")}, {"segments": True},
                      {"segments": 2.0}, {"width": 1000}, {"object": "Cube"}, {"not_a_property": 1}, {}):
            with self.subTest(props=props):
                args = copy.deepcopy(self.mod); args["operations"][0]["params"]["properties"] = props
                self.assertFalse(self.allowed("execute_blender_code", args))
        args = copy.deepcopy(self.mod); args["operations"][0]["params"]["modifier_type"] = "BOOLEAN"
        self.assertFalse(self.allowed("execute_blender_code", args))

    def test_missing_or_existing_modifier_denied(self):
        args = copy.deepcopy(self.mod)
        args["operations"][0]["params"].update(modifier_name="OwnedSubsurf", modifier_type="SUBSURF")
        self.assertFalse(self.allowed("execute_blender_code", args))
        self.assertFalse(self.allowed("execute_blender_code", {"operations": [
            {"action": "remove_modifier", "target": "OwnedMesh", "params": {"modifier_name": "Unowned"}}]}))

    def test_fresh_bake_only(self):
        self.assertTrue(self.allowed("bake_object_texture", self.bake))
        for key, value in (("object_name", "Cube"), ("image_name", "ExistingImage"), ("bake_type", "COMBINED"),
                           ("width", 4096), ("height", True), ("margin", 9),
                           ("save_filepath", str(self.root.parent / "outside.png")),
                           ("save_filepath", "relative.png"), ("save_filepath", str(self.root / "wrong.jpg"))):
            with self.subTest(key=key, value=value):
                self.assertFalse(self.allowed("bake_object_texture", {**self.bake, key: value}))
        for key in ("use_selected_to_active", "approved", "trusted_approval", "_trusted_test_override"):
            self.assertFalse(self.allowed("bake_object_texture", {**self.bake, key: True}))
        (self.root / "fresh.png").touch()
        self.assertFalse(self.allowed("bake_object_texture", self.bake))

    def test_malformed_inputs_fail_closed(self):
        for args in (None, [], {}, {"operations": None}, {"operations": [None]}, {"operations": [{"action": "add_modifier"}]}):
            self.assertFalse(self.allowed("execute_blender_code", args))
        args = copy.deepcopy(self.mod); args["operations"][0]["action"] = []
        self.assertFalse(self.allowed("execute_blender_code", args))
        args = copy.deepcopy(self.mod); args["operations"][0]["params"]["properties"] = {"width": 10**1000}
        self.assertFalse(self.allowed("execute_blender_code", args))
