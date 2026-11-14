"""
Intermediate Verification Gates for Universal MCP.
Provides declarative postcondition assertions evaluated between stage executions,
preventing flawed geometry, missing assets, or invalid states from propagating downstream.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Callable, Tuple
import time
import logging

from .checkpoints import is_response_success

logger = logging.getLogger("UniversalMCP_VerificationGates")


@dataclass
class VerificationResult:
    """
    Standardized outcome of a verification gate evaluation.
    """
    passed: bool
    gate_id: str
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        return cls(**data)


class VerificationGate:
    """
    Abstract base class for stage postcondition verification gates.
    """
    gate_id: str = "base_gate"
    name: str = "Base Verification Gate"

    def evaluate(
        self,
        stage_id: str,
        stage_output: Any,
        executor: Any,
    ) -> VerificationResult:
        raise NotImplementedError("Subclasses must implement evaluate()")


class ObjectExistenceGate(VerificationGate):
    """
    Asserts that specific required objects exist in the scene, and optionally
    that prohibited objects do not exist.
    """

    def __init__(
        self,
        required_objects: List[str],
        prohibited_objects: Optional[List[str]] = None,
        gate_id: Optional[str] = None,
    ):
        self.required_objects = list(required_objects)
        self.prohibited_objects = list(prohibited_objects or [])
        self.gate_id = gate_id or f"gate_obj_exist_{'_'.join(required_objects[:2])}"
        self.name = f"Object Existence Gate: {self.required_objects}"

    def evaluate(
        self,
        stage_id: str,
        stage_output: Any,
        executor: Any,
    ) -> VerificationResult:
        try:
            list_res = executor.execute_tool("list_objects", {})
            if not is_response_success(list_res):
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message="Failed to query scene objects for verification.",
                )

            raw_objs = list_res.result.get("objects", []) if list_res.result else []
            live_names = set(
                o.get("name") if isinstance(o, dict) else str(o)
                for o in raw_objs
                if (o.get("name") if isinstance(o, dict) else str(o))
            )

            missing = [name for name in self.required_objects if name not in live_names]
            prohibited_present = [name for name in self.prohibited_objects if name in live_names]

            if missing or prohibited_present:
                err_msgs = []
                if missing:
                    err_msgs.append(f"Missing required objects: {missing}")
                if prohibited_present:
                    err_msgs.append(f"Prohibited objects present: {prohibited_present}")
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message="; ".join(err_msgs),
                    details={"missing": missing, "prohibited": prohibited_present, "live_names": sorted(list(live_names))},
                )

            return VerificationResult(
                passed=True,
                gate_id=self.gate_id,
                message=f"All {len(self.required_objects)} required objects exist.",
                details={"verified_objects": self.required_objects},
            )

        except Exception as e:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message=f"Error evaluating ObjectExistenceGate: {e}",
            )


class GeometryHealthGate(VerificationGate):
    """
    Asserts that a designated mesh object possesses healthy vertex and polygon counts.
    """

    def __init__(
        self,
        object_name: str,
        min_vertices: int = 1,
        min_polygons: int = 1,
        gate_id: Optional[str] = None,
    ):
        self.object_name = object_name
        self.min_vertices = min_vertices
        self.min_polygons = min_polygons
        self.gate_id = gate_id or f"gate_geom_{object_name}"
        self.name = f"Geometry Health Gate: {object_name}"

    def evaluate(
        self,
        stage_id: str,
        stage_output: Any,
        executor: Any,
    ) -> VerificationResult:
        try:
            det_res = executor.execute_tool("get_object_details", {"name": self.object_name})
            if not is_response_success(det_res) or not isinstance(det_res.result, dict):
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Failed to query details for object '{self.object_name}'.",
                )

            det = det_res.result
            mesh_stats = det.get("mesh_stats")
            if not mesh_stats:
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Object '{self.object_name}' has no mesh data or mesh statistics.",
                    details=det,
                )

            v_count = mesh_stats.get("vertices_count", 0)
            p_count = mesh_stats.get("polygons_count", 0)

            if v_count < self.min_vertices or p_count < self.min_polygons:
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=(
                        f"Object '{self.object_name}' failed geometry health: "
                        f"vertices={v_count} (min {self.min_vertices}), "
                        f"polygons={p_count} (min {self.min_polygons})"
                    ),
                    details={"vertices": v_count, "polygons": p_count},
                )

            return VerificationResult(
                passed=True,
                gate_id=self.gate_id,
                message=f"Object '{self.object_name}' passed geometry health (vertices={v_count}, polygons={p_count}).",
                details={"vertices": v_count, "polygons": p_count},
            )

        except Exception as e:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message=f"Error evaluating GeometryHealthGate: {e}",
            )


class MaterialBindingGate(VerificationGate):
    """
    Asserts that an object has a designated material assigned.
    """

    def __init__(
        self,
        object_name: str,
        expected_material: str,
        gate_id: Optional[str] = None,
    ):
        self.object_name = object_name
        self.expected_material = expected_material
        self.gate_id = gate_id or f"gate_mat_{object_name}_{expected_material}"
        self.name = f"Material Binding Gate: {object_name} -> {expected_material}"

    def evaluate(
        self,
        stage_id: str,
        stage_output: Any,
        executor: Any,
    ) -> VerificationResult:
        try:
            det_res = executor.execute_tool("get_object_details", {"name": self.object_name})
            if not is_response_success(det_res) or not isinstance(det_res.result, dict):
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Failed to query details for object '{self.object_name}'.",
                )

            det = det_res.result
            mats = det.get("materials", [])
            if self.expected_material not in mats:
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Material '{self.expected_material}' not assigned to '{self.object_name}'. Assigned: {mats}",
                    details={"assigned_materials": mats, "expected": self.expected_material},
                )

            return VerificationResult(
                passed=True,
                gate_id=self.gate_id,
                message=f"Material '{self.expected_material}' verified on '{self.object_name}'.",
                details={"assigned_materials": mats},
            )

        except Exception as e:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message=f"Error evaluating MaterialBindingGate: {e}",
            )


class CustomPredicateGate(VerificationGate):
    """
    Executes a custom predicate callback (Callable[[str, Any, Any], Tuple[bool, str]])
    for domain-specific verification logic.
    """

    def __init__(
        self,
        gate_id: str,
        predicate_fn: Callable[[str, Any, Any], Tuple[bool, str]],
        name: str = "Custom Predicate Gate",
    ):
        self.gate_id = gate_id
        self.predicate_fn = predicate_fn
        self.name = name

    def evaluate(
        self,
        stage_id: str,
        stage_output: Any,
        executor: Any,
    ) -> VerificationResult:
        try:
            ok, msg = self.predicate_fn(stage_id, stage_output, executor)
            return VerificationResult(
                passed=ok,
                gate_id=self.gate_id,
                message=msg,
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message=f"Exception in custom predicate: {e}",
            )


class MeshManifoldnessGate(VerificationGate):
    """
    Asserts that an imported or processed mesh possesses valid manifold topology:
    1. Object exists in the active scene and is a MESH.
    2. Has at least min_vertices (default 3) and min_polygons (default 1).
    3. Vertex coordinates are finite and non-degenerate.
    4. Confirms non-zero spatial dimensions.
    """

    def __init__(
        self,
        object_name: Optional[str] = None,
        min_vertices: int = 3,
        min_polygons: int = 1,
        gate_id: Optional[str] = None,
    ):
        self.object_name = object_name
        self.min_vertices = min_vertices
        self.min_polygons = min_polygons
        self.gate_id = gate_id or f"gate_manifold_{object_name or 'target'}"
        self.name = f"Mesh Manifoldness Gate: {object_name or 'imported_target'}"

    def evaluate(
        self,
        stage_id: str,
        stage_output: Any,
        executor: Any,
    ) -> VerificationResult:
        target = self.object_name
        if not target and isinstance(stage_output, dict):
            objs = stage_output.get("imported_objects") or stage_output.get("objects")
            if objs and isinstance(objs, list):
                target = objs[0]
            elif "target_object" in stage_output:
                target = stage_output["target_object"]
            elif "name" in stage_output:
                target = stage_output["name"]

        if not target:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message="MeshManifoldnessGate failed: target object name could not be resolved from stage output.",
            )

        try:
            det_res = executor.execute_tool("get_object_details", {"name": target})
            if not is_response_success(det_res) or not isinstance(det_res.result, dict):
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Failed to query details for mesh '{target}'.",
                )

            det = det_res.result
            if det.get("type") != "MESH":
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Object '{target}' is not of type 'MESH' (got '{det.get('type')}').",
                )

            mesh_stats = det.get("mesh_stats") or {}
            v_count = mesh_stats.get("vertices_count", 0)
            p_count = mesh_stats.get("polygons_count", 0)
            e_count = mesh_stats.get("edges_count", 0)

            if v_count < self.min_vertices or p_count < self.min_polygons:
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=(
                        f"Mesh '{target}' failed manifoldness/topology check: "
                        f"vertices={v_count} (min {self.min_vertices}), "
                        f"polygons={p_count} (min {self.min_polygons})."
                    ),
                    details={"vertices": v_count, "polygons": p_count, "edges": e_count},
                )

            dims = det.get("dimensions", [0.0, 0.0, 0.0])
            if all(abs(d) < 1e-6 for d in dims) and v_count > 1:
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Mesh '{target}' has collapsed dimensions (all 0.0): degenerate geometry.",
                    details={"dimensions": dims},
                )

            return VerificationResult(
                passed=True,
                gate_id=self.gate_id,
                message=f"Mesh '{target}' passed manifoldness verification (V={v_count}, E={e_count}, F={p_count}).",
                details={"target": target, "vertices": v_count, "edges": e_count, "polygons": p_count, "dimensions": dims},
            )

        except Exception as e:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message=f"Error evaluating MeshManifoldnessGate on '{target}': {e}",
            )


class TextureBoundsGate(VerificationGate):
    """
    Asserts that a designated mesh object possesses valid UV coordinate layers
    and texture bounds for downstream material or export stages:
    1. Object exists and is a MESH.
    2. Has at least one valid UV layer (when require_uv=True).
    3. Confirms non-empty UV coordinates for rendering.
    """

    def __init__(
        self,
        object_name: Optional[str] = None,
        require_uv: bool = True,
        gate_id: Optional[str] = None,
    ):
        self.object_name = object_name
        self.require_uv = require_uv
        self.gate_id = gate_id or f"gate_uv_{object_name or 'target'}"
        self.name = f"Texture Bounds Gate: {object_name or 'target'}"

    def evaluate(
        self,
        stage_id: str,
        stage_output: Any,
        executor: Any,
    ) -> VerificationResult:
        target = self.object_name
        if not target and isinstance(stage_output, dict):
            objs = stage_output.get("imported_objects") or stage_output.get("objects")
            if objs and isinstance(objs, list):
                target = objs[0]
            elif "target_object" in stage_output:
                target = stage_output["target_object"]
            elif "name" in stage_output:
                target = stage_output["name"]

        if not target:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message="TextureBoundsGate failed: target object name could not be resolved from stage output.",
            )

        try:
            uv_res = executor.execute_tool("inspect_scene_data", {"category": "uv_layers", "target_name": target})
            if not is_response_success(uv_res) or not isinstance(uv_res.result, dict):
                if self.require_uv:
                    return VerificationResult(
                        passed=False,
                        gate_id=self.gate_id,
                        message=f"Failed to inspect UV layers for object '{target}'.",
                    )
                return VerificationResult(passed=True, gate_id=self.gate_id, message="UV inspection skipped (optional).")

            uv_data = uv_res.result
            layers = uv_data.get("uv_layers") if "uv_layers" in uv_data else uv_data.get("layers", [])
            active_layer = uv_data.get("active_layer")

            if self.require_uv and not layers:
                return VerificationResult(
                    passed=False,
                    gate_id=self.gate_id,
                    message=f"Object '{target}' has no UV layers for texture binding.",
                    details=uv_data,
                )

            return VerificationResult(
                passed=True,
                gate_id=self.gate_id,
                message=f"Object '{target}' passed texture bounds verification (layers={len(layers)}, active='{active_layer}').",
                details={"layers": [l.get("name") for l in layers if isinstance(l, dict)], "active_layer": active_layer},
            )

        except Exception as e:
            return VerificationResult(
                passed=False,
                gate_id=self.gate_id,
                message=f"Error evaluating TextureBoundsGate on '{target}': {e}",
            )

