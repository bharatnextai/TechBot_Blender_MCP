"""
Unit Tests for TaskOutputRef and Static Workflow Reference Validation (TASK-UMCP-0029).
Validates contract models, canonical reference structure, static validation rules in TaskPlanner,
immutability of input parameters, and rejection of malformed or undeclared references.
"""

import copy
import unittest
from shared.models.agent_contracts import (
    TaskOutputRef,
    SUPPORTED_REF_TYPES,
    AgentTask,
    TaskPlan,
    TaskStatus,
)
from mcp_service.agents.planner import TaskPlanner
from mcp_service.agents.registry import create_default_registry
from mcp_service.agents.router import CapabilityRouter


class TestTaskOutputRefContract(unittest.TestCase):
    """Tests the TaskOutputRef model and canonical structured representation."""

    def test_valid_ref_creation_and_validation(self):
        ref = TaskOutputRef(task_id="t_create", path="name", expected_type="string")
        ref.validate()
        self.assertEqual(ref.task_id, "t_create")
        self.assertEqual(ref.path, "name")
        self.assertEqual(ref.expected_type, "string")

    def test_canonical_to_dict_and_from_dict(self):
        ref = TaskOutputRef(task_id="t_box", path="dimensions.0", expected_type="number")
        canonical_dict = ref.to_dict()
        self.assertEqual(
            canonical_dict,
            {"$ref": {"task_id": "t_box", "path": "dimensions.0", "type": "number"}}
        )

        parsed = TaskOutputRef.from_dict(canonical_dict)
        self.assertEqual(parsed.task_id, "t_box")
        self.assertEqual(parsed.path, "dimensions.0")
        self.assertEqual(parsed.expected_type, "number")

    def test_from_dict_without_optional_type(self):
        canonical_dict = {"$ref": {"task_id": "t_inspect", "path": "summary"}}
        parsed = TaskOutputRef.from_dict(canonical_dict)
        self.assertEqual(parsed.task_id, "t_inspect")
        self.assertEqual(parsed.path, "summary")
        self.assertIsNone(parsed.expected_type)

    def test_empty_task_id_or_path_rejected(self):
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="", path="name").validate()
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="").validate()
        with self.assertRaises(ValueError):
            TaskOutputRef.from_dict({"$ref": {"task_id": "", "path": "name"}})

    def test_invalid_path_segments_rejected(self):
        # Empty segments
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="a..b").validate()
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path=".a").validate()
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="a.").validate()
        # Invalid characters (operators, spaces, punctuation)
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="a-b").validate()
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="a b").validate()
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="a[0]").validate()

    def test_valid_nested_dot_and_integer_index_paths(self):
        # Dot separated identifiers and non-negative integers
        r1 = TaskOutputRef(task_id="t1", path="objects.0.name")
        r1.validate()
        r2 = TaskOutputRef(task_id="t1", path="scene.collections.1.objects.2.name")
        r2.validate()

    def test_supported_and_unsupported_type_declarations(self):
        for typ in ["string", "number", "integer", "boolean", "array", "object", "str", "int", "float", "bool", "list", "dict"]:
            r = TaskOutputRef(task_id="t1", path="val", expected_type=typ)
            r.validate()

        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="val", expected_type="invalid_type").validate()
        with self.assertRaises(ValueError):
            TaskOutputRef(task_id="t1", path="val", expected_type="callable").validate()

    def test_malformed_dict_structures_rejected(self):
        # Not a dict
        with self.assertRaises(ValueError):
            TaskOutputRef.from_dict("not_a_dict")  # type: ignore

        # Missing $ref
        with self.assertRaises(ValueError):
            TaskOutputRef.from_dict({"task_id": "t1", "path": "val"})

        # $ref payload not a dict
        with self.assertRaises(ValueError):
            TaskOutputRef.from_dict({"$ref": "t1.val"})

        # Unknown keys in $ref
        with self.assertRaises(ValueError):
            TaskOutputRef.from_dict({"$ref": {"task_id": "t1", "path": "val", "extra_bad_key": 123}})


class TestStaticWorkflowReferenceValidation(unittest.TestCase):
    """Tests static validation in TaskPlanner.validate_plan()."""

    def setUp(self):
        self.reg = create_default_registry()
        self.router = CapabilityRouter(self.reg)
        self.planner = TaskPlanner(self.router)

    def test_valid_reference_passes_validation(self):
        plan = TaskPlan(title="ValidRefPlan")
        t1 = AgentTask("t1", "modeling.primitive", "create_primitive")
        t2 = AgentTask(
            "t2",
            "materials.manage",
            "assign_material",
            input_params={"target_name": {"$ref": {"task_id": "t1", "path": "name", "type": "string"}}},
            dependencies=["t1"],
        )
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])

    def test_valid_nested_paths_in_dict_and_list(self):
        plan = TaskPlan(title="NestedRefPlan")
        t1 = AgentTask("t1", "scene.inspection", "list_objects")
        t2 = AgentTask(
            "t2",
            "materials.manage",
            "assign_material",
            input_params={
                "config": {
                    "object_name": {"$ref": {"task_id": "t1", "path": "objects.0.name"}}
                },
                "multi_targets": [
                    {"$ref": {"task_id": "t1", "path": "objects.1.name"}},
                    "StaticTarget",
                ],
            },
            dependencies=["t1"],
        )
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])

    def test_reference_to_nonexistent_task_rejected(self):
        plan = TaskPlan(title="MissingTaskPlan")
        t1 = AgentTask("t1", "modeling.primitive", "create_primitive")
        t2 = AgentTask(
            "t2",
            "materials.manage",
            "assign_material",
            input_params={"target_name": {"$ref": {"task_id": "nonexistent_task", "path": "name"}}},
            dependencies=["t1"],
        )
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("references non-existent task 'nonexistent_task'" in e for e in errors))

    def test_reference_to_undeclared_dependency_rejected(self):
        plan = TaskPlan(title="UndeclaredDepPlan")
        t1 = AgentTask("t1", "modeling.primitive", "create_primitive")
        t2 = AgentTask(
            "t2",
            "materials.manage",
            "assign_material",
            input_params={"target_name": {"$ref": {"task_id": "t1", "path": "name"}}},
            dependencies=[],  # t1 is in plan but NOT in t2's dependencies!
        )
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("not declared in direct dependencies" in e for e in errors))

    def test_self_reference_rejected(self):
        plan = TaskPlan(title="SelfRefPlan")
        t1 = AgentTask(
            "t1",
            "modeling.primitive",
            "create_primitive",
            input_params={"name": {"$ref": {"task_id": "t1", "path": "name"}}},
            dependencies=[],
        )
        plan.add_task(t1)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("references itself (self-dependency detected)" in e for e in errors))

    def test_malformed_reference_rejected(self):
        plan = TaskPlan(title="MalformedRefPlan")
        t1 = AgentTask("t1", "modeling.primitive", "create_primitive")
        t2 = AgentTask(
            "t2",
            "materials.manage",
            "assign_material",
            input_params={"target_name": {"$ref": {"task_id": "t1", "path": "invalid..path"}}},
            dependencies=["t1"],
        )
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("has malformed reference" in e for e in errors))

    def test_unsupported_type_declaration_rejected(self):
        plan = TaskPlan(title="BadTypePlan")
        t1 = AgentTask("t1", "modeling.primitive", "create_primitive")
        t2 = AgentTask(
            "t2",
            "materials.manage",
            "assign_material",
            input_params={"target_name": {"$ref": {"task_id": "t1", "path": "name", "type": "bad_type"}}},
            dependencies=["t1"],
        )
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("Unsupported type declaration 'bad_type'" in e for e in errors))

    def test_shorthand_syntax_rejected(self):
        plan = TaskPlan(title="ShorthandSyntaxPlan")
        t1 = AgentTask("t1", "modeling.primitive", "create_primitive")
        t2 = AgentTask(
            "t2",
            "materials.manage",
            "assign_material",
            input_params={"target_name": "$ref:t1.name"},
            dependencies=["t1"],
        )
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertTrue(any("Shorthand '$ref:' syntax is not supported" in e for e in errors))

    def test_static_input_params_preserved_without_references(self):
        plan = TaskPlan(title="StaticPlan")
        t1 = AgentTask("t1", "scene.inspection", "get_scene_summary", input_params={"include_collections": True})
        t2 = AgentTask("t2", "modeling.primitive", "create_primitive", input_params={"name": "Cube_A", "primitive_type": "cube"}, dependencies=["t1"])
        plan.add_task(t1)
        plan.add_task(t2)

        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])
        self.assertEqual(t1.input_params, {"include_collections": True})
        self.assertEqual(t2.input_params, {"name": "Cube_A", "primitive_type": "cube"})

    def test_input_params_immutability_during_validation(self):
        input_params = {
            "target_name": {"$ref": {"task_id": "t1", "path": "name", "type": "string"}},
            "nested": {
                "items": [{"$ref": {"task_id": "t1", "path": "stats.count"}}],
                "flag": True,
            },
        }
        params_copy = copy.deepcopy(input_params)

        plan = TaskPlan(title="ImmutabilityPlan")
        t1 = AgentTask("t1", "modeling.primitive", "create_primitive")
        t2 = AgentTask("t2", "materials.manage", "assign_material", input_params=input_params, dependencies=["t1"])
        plan.add_task(t1)
        plan.add_task(t2)

        # Run validation
        errors = self.planner.validate_plan(plan)
        self.assertEqual(errors, [])

        # Assert input_params was not mutated in any way
        self.assertEqual(t2.input_params, params_copy)
        self.assertIs(t2.input_params, input_params)


if __name__ == "__main__":
    unittest.main()
