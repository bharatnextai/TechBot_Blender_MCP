"""
Scene Inspector Agent for Universal MCP.
Provides verified read-only inspection of active scene summary, object hierarchy,
materials, and mesh topology without modifying any scene data.
"""

from typing import Dict, Any, List, Optional, Set
import time
import logging

from shared.models.agent_contracts import (
    AgentManifest,
    CapabilityDescriptor,
    AgentTask,
    AgentResult,
    VerificationResult,
    TaskStatus,
)
from shared.models.protocol_models import BridgeResponse
from shared.schemas.tool_schemas import (
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_LIST_MATERIALS,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_CAPTURE_VIEWPORT,
    ALLOWED_INSPECT_CATEGORIES,
    TOOL_DEFINITIONS,
)
from ..execution.blender_executor import BlenderExecutor, verify_indexed_topology_response

logger = logging.getLogger("UniversalMCP_SceneInspectorAgent")

SCENE_INSPECTOR_AGENT_ID = "agent.scene_inspector"
SCENE_INSPECTION_CAPABILITY_ID = "scene.inspection"
CAPABILITY_VISUAL_CAPTURE = "visual.capture"

SUPPORTED_INSPECTION_TOOLS: Set[str] = {
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_LIST_MATERIALS,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_CAPTURE_VIEWPORT,
}

MUTATION_TOOLS: Set[str] = {
    "create_primitive",
    "transform_object",
    "execute_blender_code",
    "create_material",
    "assign_material",
    "create_light",
    "configure_world",
}


def create_scene_inspector_manifest(version: str = "0.1.13") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Scene Inspector Agent.
    Declares only verified read-only capabilities supported by inspected evidence.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in SUPPORTED_INSPECTION_TOOLS
        if name in TOOL_DEFINITIONS
    }
    return AgentManifest(
        agent_id=SCENE_INSPECTOR_AGENT_ID,
        name="Scene Inspector Agent",
        version=version,
        description=(
            "Inspects Blender scenes: summary metadata, object hierarchy, "
            "material slots, mesh statistics, topology, and bounded viewport snapshots without mutating scene state."
        ),
        capabilities=[
            CapabilityDescriptor(
                capability_id=SCENE_INSPECTION_CAPABILITY_ID,
                description="Read-only scene metadata, object hierarchy, materials, and mesh topology.",
                supported_task_types=[
                    TOOL_GET_SCENE_SUMMARY,
                    TOOL_LIST_OBJECTS,
                    TOOL_GET_OBJECT_DETAILS,
                    TOOL_LIST_MATERIALS,
                    TOOL_INSPECT_SCENE_DATA,
                ],
                read_write="READ_ONLY",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_VISUAL_CAPTURE,
                description="Captures bounded visual snapshots of the 3D viewport or active camera without mutating scene state.",
                supported_task_types=[TOOL_CAPTURE_VIEWPORT],
                read_write="READ_ONLY",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
        ],
        input_schemas=schemas,
        priority=10,
        enabled=True,
    )


class SceneInspectorAgent:
    """
    Specialized read-only Scene Inspector agent.
    Receives validated inspection tasks, executes only against verified read-only tools,
    and returns structured, evidence-referenced observations while strictly prohibiting mutations.
    """

    def __init__(self, version: str = "0.1.13"):
        self.version = version
        self._manifest = create_scene_inspector_manifest(version=self.version)

    @property
    def agent_id(self) -> str:
        return SCENE_INSPECTOR_AGENT_ID

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def get_manifest(self) -> AgentManifest:
        return self._manifest

    def can_handle(self, task: AgentTask) -> bool:
        """Checks whether this agent can handle the requested capability and task type."""
        req_cap = task.required_capability
        if req_cap and req_cap not in (SCENE_INSPECTION_CAPABILITY_ID, CAPABILITY_VISUAL_CAPTURE):
            return False
        if task.task_type:
            return task.task_type in SUPPORTED_INSPECTION_TOOLS
        return True

    def execute_task(
        self,
        task: AgentTask,
        executor: BlenderExecutor,
    ) -> AgentResult:
        """
        Executes a validated read-only inspection task via BlenderExecutor.
        Enforces strict read-only boundary:
        - Rejects any mutation tool or write operation.
        - Rejects unsupported tools and categories.
        - Distinguishes empty results, unavailable data, and execution errors.
        - Captures factual evidence references without inventing scene state.
        """
        t0 = time.time()
        params = dict(task.input_params or {})
        tool_name = task.task_type
        if not tool_name:
            if "category" in params:
                tool_name = TOOL_INSPECT_SCENE_DATA
            elif "target_name" in params or "name" in params:
                tool_name = TOOL_GET_OBJECT_DETAILS
            else:
                tool_name = TOOL_GET_SCENE_SUMMARY

        # 1. Enforce Read-Only Security Boundary
        if tool_name in MUTATION_TOOLS:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[
                    f"Permission denied: SceneInspectorAgent is strictly read-only and cannot execute "
                    f"scene-mutation tool '{tool_name}'."
                ],
                execution_time_ms=duration_ms,
            )

        if tool_name not in SUPPORTED_INSPECTION_TOOLS:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[
                    f"Unsupported inspection task type: '{tool_name}'. "
                    f"Supported inspection tools: {sorted(list(SUPPORTED_INSPECTION_TOOLS))}"
                ],
                execution_time_ms=duration_ms,
            )

        # 2. Category Check for inspect_scene_data
        if tool_name == TOOL_INSPECT_SCENE_DATA:
            cat = str(params.get("category", "")).strip().lower()
            if cat not in ALLOWED_INSPECT_CATEGORIES:
                duration_ms = round((time.time() - t0) * 1000, 2)
                return AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[
                        f"Unsupported inspect_scene_data category: '{cat}'. "
                        f"Allowed categories: {sorted(list(ALLOWED_INSPECT_CATEGORIES))}"
                    ],
                    execution_time_ms=duration_ms,
                )

        # 3. Execution via verified BlenderExecutor
        try:
            resp: BridgeResponse = executor.execute_tool(tool_name, params)
        except Exception as exc:
            logger.exception(f"SceneInspectorAgent execution error for '{tool_name}': {exc}")
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[f"Inspection execution error: {str(exc)}"],
                execution_time_ms=duration_ms,
            )

        duration_ms = round((time.time() - t0) * 1000, 2)

        # 4. Handle Executor Failures & Distinguish Errors vs Unavailable Data
        if not resp.is_success:
            err_msg = resp.message or "Unknown inspection error from Blender."
            # Distinguish unavailable data vs other errors
            is_unavailable = any(term in err_msg.lower() for term in ("not found", "does not exist", "missing target"))
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[err_msg],
                execution_time_ms=duration_ms,
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name, "read_only": True},
                    observed_results={"success": False, "data_unavailable": is_unavailable},
                    status="FAIL",
                    details=f"Inspection failed: {err_msg}",
                ),
            )

        # 5. Process Successful Response & Extract Factual Evidence References
        raw_result: Dict[str, Any] = dict(resp.result or {})
        indexed_topology = (tool_name == TOOL_INSPECT_SCENE_DATA
            and params.get("category") == "mesh_topology" and "element_domain" in params)
        if indexed_topology:
            try:
                # Do not convert a malformed successful response into an inspection PASS.
                verify_indexed_topology_response(raw_result, params)
            except (ValueError, TypeError, OverflowError) as exc:
                message = f"Indexed topology verification failed: {exc}"
                return AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[message],
                    execution_time_ms=duration_ms,
                    verification=VerificationResult(
                        expected_conditions={"tool": tool_name, "read_only": True, "indexed_topology": True},
                        observed_results={"success": False},
                        status="FAIL",
                        details=message,
                    ),
                )
        scope: Dict[str, Any] = {
            "tool": tool_name,
            "target": params.get("target_name") or params.get("name"),
            "category": params.get("category"),
            "parameters": {k: v for k, v in params.items() if k not in ("name", "target_name", "category")},
        }

        is_empty = False
        evidence_refs: List[str] = []

        if tool_name == TOOL_GET_SCENE_SUMMARY:
            s_name = raw_result.get("scene_name", "UnknownScene")
            total_objs = raw_result.get("total_objects", 0)
            is_empty = (total_objs == 0)
            evidence_refs.append(f"scene:{s_name}")
            evidence_refs.append(f"objects_total:{total_objs}")
            if raw_result.get("collections"):
                evidence_refs.append(f"collection_count:{len(raw_result['collections'])}")

        elif tool_name == TOOL_LIST_OBJECTS:
            objs = raw_result.get("objects", [])
            tot = raw_result.get("total_matching", len(objs))
            is_empty = (tot == 0 or len(objs) == 0)
            evidence_refs.append(f"total_matching:{tot}")
            for item in objs[:10]:
                evidence_refs.append(f"object:{item.get('name')}:{item.get('type')}")

        elif tool_name == TOOL_GET_OBJECT_DETAILS:
            o_name = raw_result.get("name", "UnknownObject")
            o_type = raw_result.get("type", "UNKNOWN")
            is_empty = False
            evidence_refs.append(f"object:{o_name}")
            evidence_refs.append(f"type:{o_type}")
            if "location" in raw_result:
                evidence_refs.append(f"location:{raw_result['location']}")

        elif tool_name == TOOL_LIST_MATERIALS:
            mats = raw_result.get("materials", [])
            tot_m = raw_result.get("total_materials", len(mats))
            is_empty = (tot_m == 0 or len(mats) == 0)
            evidence_refs.append(f"total_materials:{tot_m}")
            for m in mats[:10]:
                evidence_refs.append(f"material:{m.get('name')}")

        elif tool_name == TOOL_INSPECT_SCENE_DATA:
            cat_name = raw_result.get("category", "")
            evidence_refs.append(f"category:{cat_name}")
            target = raw_result.get("target_name")
            if target:
                evidence_refs.append(f"target:{target}")

            if cat_name == "object_modifiers":
                mods = raw_result.get("modifiers", [])
                is_empty = (len(mods) == 0)
                evidence_refs.append(f"modifier_count:{len(mods)}")
                for mod in mods:
                    evidence_refs.append(f"modifier:{mod.get('name')}:{mod.get('type')}")
            elif cat_name == "object_materials":
                mats = raw_result.get("materials", [])
                is_empty = (len(mats) == 0)
                evidence_refs.append(f"slot_count:{len(mats)}")
            elif cat_name == "mesh_topology":
                v_count = raw_result.get("vertex_count", 0)
                is_empty = (v_count == 0)
                evidence_refs.append(f"vertices:{v_count}")
                evidence_refs.append(f"polygons:{raw_result.get('polygon_count', 0)}")
                if indexed_topology:
                    evidence_refs.extend((
                        f"topology_domain:{raw_result['element_domain']}",
                        f"topology_returned:{raw_result['returned_count']}",
                        f"topology_total:{raw_result['total']}",
                        f"topology_snapshot:{raw_result['snapshot_id']}",
                    ))
            elif cat_name in ("scene_hierarchy", "collection_tree"):
                items = raw_result.get("hierarchy", raw_result.get("collections", []))
                is_empty = (len(items) == 0)
                evidence_refs.append(f"returned_count:{len(items)}")
            elif cat_name == "world_settings":
                w_name = raw_result.get("name")
                is_empty = raw_result.get("has_world") is False
                if raw_result.get("has_world") is True and w_name:
                    evidence_refs.append(f"world:{w_name}")

        elif tool_name == TOOL_CAPTURE_VIEWPORT:
            b64_img = raw_result.get("image_base64", "")
            is_empty = (len(b64_img) == 0)
            evidence_refs.append(
                f"viewport_capture:format={raw_result.get('format')},width={raw_result.get('width')},"
                f"height={raw_result.get('height')},size_bytes={raw_result.get('size_bytes')}"
            )

        verification = VerificationResult(
            expected_conditions={"tool": tool_name, "read_only": True},
            observed_results={
                "records_returned": len(evidence_refs),
                "is_empty": is_empty,
                "scope": scope,
                **({"indexed_topology": True, "element_domain": raw_result["element_domain"],
                    "returned_count": raw_result["returned_count"], "total": raw_result["total"],
                    "snapshot_id": raw_result["snapshot_id"]} if indexed_topology else {}),
            },
            status="PASS",
            details=f"Read-only inspection '{tool_name}' successfully executed and verified.",
        )

        # Merge raw result fields for complete backward compatibility with callers
        output_payload = {
            **raw_result,
            "observed_data": raw_result,
            "inspection_scope": scope,
            "is_empty": is_empty,
        }

        return AgentResult(
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            output=output_payload,
            evidence_references=evidence_refs,
            verification=verification,
            execution_time_ms=duration_ms,
        )
