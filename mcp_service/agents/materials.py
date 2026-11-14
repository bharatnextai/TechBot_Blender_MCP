"""
Materials Agent for Universal MCP.
Provides verified Principled BSDF material creation, parameter configuration,
and material slot assignment in Blender 5.2.2 LTS.

Enforces:
1. Strict parameter validation (names, colors [0.0, 1.0], roughness, metallic, ior).
2. Rejection of unsupported shader nodes and properties (glass, emission, subsurface, etc.).
3. Trusted human approval pipeline bindings (model approved=True rejection).
4. Post-operation read-only inspection verification (list_materials, inspect_scene_data).
"""

from typing import Dict, Any, List, Optional, Set, Tuple
import time
import logging
from blender_addon.universal_mcp.bridge.shader_values import shader_values_match

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
    TOOL_CONFIGURE_MATERIAL_SHADER,
    TOOL_INSPECT_MATERIAL_SHADER,
    TOOL_CREATE_MATERIAL,
    TOOL_ASSIGN_MATERIAL,
    TOOL_LIST_MATERIALS,
    TOOL_INSPECT_SCENE_DATA,
    TOOL_MANAGE_SHADER_NODES,
    TOOL_CONNECT_SHADER_NODES,
    TOOL_MANAGE_NODES,
    TOOL_BAKE_OBJECT_TEXTURE,
    TOOL_BAKE_TEXTURE,
    TOOL_BAKE_MATERIALS,
    TOOL_DEFINITIONS,
    validate_tool_input,
)
from ..execution.blender_executor import BlenderExecutor

logger = logging.getLogger("UniversalMCP_MaterialsAgent")

MATERIALS_AGENT_ID = "agent.materials"
CAPABILITY_MATERIALS_MANAGE = "materials.manage"
CAPABILITY_MATERIALS_INSPECT = "materials.inspect"
CAPABILITY_MATERIALS_TYPED_SHADER = "materials.typed_shader"

SUPPORTED_MATERIALS_TOOLS: Set[str] = {
    TOOL_CONFIGURE_MATERIAL_SHADER,
    TOOL_INSPECT_MATERIAL_SHADER,
    TOOL_CREATE_MATERIAL,
    TOOL_ASSIGN_MATERIAL,
    TOOL_LIST_MATERIALS,
    TOOL_MANAGE_SHADER_NODES,
    TOOL_CONNECT_SHADER_NODES,
    TOOL_MANAGE_NODES,
    TOOL_BAKE_OBJECT_TEXTURE,
    TOOL_BAKE_TEXTURE,
    TOOL_BAKE_MATERIALS,
}

UNSUPPORTED_SHADER_NODES: Set[str] = {
    "subsurface",
    "subsurface_scattering",
    "glass",
    "glass_bsdf",
    "emission",
    "emission_node",
    "volume",
    "volume_principled",
    "volume_scatter",
    "volume_absorption",
    "texture",
    "image_texture",
    "displacement",
    "hair_bsdf",
    "toon_bsdf",
}

UNSUPPORTED_MATERIAL_PROPERTIES: Set[str] = {
    "subsurface",
    "subsurface_radius",
    "subsurface_color",
    "transmission",
    "transmission_roughness",
    "sheen",
    "sheen_tint",
    "clearcoat",
    "clearcoat_roughness",
    "anisotropic",
    "anisotropic_rotation",
    "emission_color",
    "emission_strength",
}


def create_materials_manifest(version: str = "0.1.13") -> AgentManifest:
    """
    Constructs the canonical AgentManifest for the Materials Agent.
    Declares only verified Principled BSDF material operations.
    """
    schemas = {
        name: dict(TOOL_DEFINITIONS[name]["input_schema"])
        for name in (TOOL_CREATE_MATERIAL, TOOL_ASSIGN_MATERIAL, TOOL_LIST_MATERIALS, TOOL_CONFIGURE_MATERIAL_SHADER, TOOL_INSPECT_MATERIAL_SHADER)
        if name in TOOL_DEFINITIONS
    }
    return AgentManifest(
        agent_id=MATERIALS_AGENT_ID,
        name="Materials and Shading Agent",
        version=version,
        description=(
            "Creates verified Principled BSDF materials, configures PBR shader parameters, "
            "and assigns materials to scene objects with human approval gating and post-operation verification."
        ),
        capabilities=[
            CapabilityDescriptor(
                capability_id=CAPABILITY_MATERIALS_TYPED_SHADER,
                description="Typed Principled input writes and one Noise.Color to Base Color graph; exact sockets and separate state verification. Other shader workflows excluded.",
                supported_task_types=[TOOL_CONFIGURE_MATERIAL_SHADER], read_write="SCENE_MUTATION", verification_status="VERIFIED",
                constraints={"whole_domain_status": "PARTIALLY IMPLEMENTED", "typed_contract_status": "FULLY IMPLEMENTED",
                    "typed_contract_verification": "VERIFIED", "actions": ["set_principled", "add_noise", "update_noise", "remove_noise"],
                    "evidence": "docs/verification/TYPED_MATERIAL_SHADERS_V0142.md"}),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MATERIALS_MANAGE,
                description="Creates Principled BSDF materials, manipulates shader node graphs, bakes textures, and assigns materials to target scene objects.",
                supported_task_types=[
                    TOOL_CREATE_MATERIAL,
                    TOOL_ASSIGN_MATERIAL,
                    TOOL_MANAGE_SHADER_NODES,
                    TOOL_CONNECT_SHADER_NODES,
                    TOOL_MANAGE_NODES,
                    TOOL_BAKE_OBJECT_TEXTURE,
                    TOOL_BAKE_TEXTURE,
                    TOOL_BAKE_MATERIALS,
                ],
                read_write="SCENE_MUTATION",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
            CapabilityDescriptor(
                capability_id=CAPABILITY_MATERIALS_INSPECT,
                description="Inspects active scene materials and their Principled BSDF parameters.",
                supported_task_types=[TOOL_LIST_MATERIALS, TOOL_INSPECT_MATERIAL_SHADER],
                read_write="READ_ONLY",
                verification_status="VERIFIED",
                version="1.0.0",
            ),
        ],
        input_schemas=schemas,
        constraints={"e2e_audit": {
            "scope": ["materials_procedural_shaders", "image_textures_baking"],
            "implementation_status": "PARTIALLY IMPLEMENTED",
            "verification_status": "NOT VERIFIED",
            "evidence": "docs/verification/TEN_CAPABILITY_EVIDENCE.json",
        }},
        priority=10,
        enabled=True,
    )


class MaterialsAgent:
    """
    Specialized Materials Agent.
    Validates material and shader parameters, enforces human approval for mutations,
    executes via BlenderExecutor, and performs post-operation read-only inspection.
    """

    def __init__(self, version: str = "0.1.13"):
        self.version = version
        self._manifest = create_materials_manifest(version=self.version)

    @property
    def agent_id(self) -> str:
        return MATERIALS_AGENT_ID

    @property
    def manifest(self) -> AgentManifest:
        return self._manifest

    def get_manifest(self) -> AgentManifest:
        return self._manifest

    def can_handle(self, task: AgentTask) -> bool:
        """Checks whether this agent can handle the requested capability or task type."""
        req_cap = task.required_capability
        if req_cap and req_cap not in (
            CAPABILITY_MATERIALS_MANAGE,
            CAPABILITY_MATERIALS_INSPECT,
            CAPABILITY_MATERIALS_TYPED_SHADER,
        ):
            return False
        if task.task_type:
            return task.task_type in SUPPORTED_MATERIALS_TOOLS
        return True

    def validate_task_input(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Performs strict pre-execution validation of material inputs, constraints, and nodes.
        Returns: (is_valid, error_code, error_message)
        """
        if tool_name not in SUPPORTED_MATERIALS_TOOLS:
            return (
                False,
                "UNSUPPORTED_REQUEST",
                f"Unsupported materials tool '{tool_name}'. Supported tools: {sorted(list(SUPPORTED_MATERIALS_TOOLS))}",
            )

        if tool_name in (TOOL_CONFIGURE_MATERIAL_SHADER, TOOL_INSPECT_MATERIAL_SHADER):
            from blender_addon.universal_mcp.bridge.material_shader_contract import validate_material_shader
            try:
                validate_material_shader(params, inspection=tool_name == TOOL_INSPECT_MATERIAL_SHADER)
            except ValueError as error:
                return False, "INVALID_PARAMS", str(error)
            return True, None, None

        # Check for unsupported shader nodes / properties passed in params
        for key in params.keys():
            k_lower = key.lower()
            if k_lower in UNSUPPORTED_MATERIAL_PROPERTIES or k_lower in UNSUPPORTED_SHADER_NODES:
                return (
                    False,
                    "UNSUPPORTED_REQUEST",
                    f"Unsupported shader property or node '{key}'. In this phase, only verified Principled BSDF "
                    "properties (base_color, roughness, metallic, ior, alpha, specular) are supported.",
                )

        shader_nodes = params.get("nodes") or params.get("shader_nodes")
        if shader_nodes:
            if isinstance(shader_nodes, list):
                for node_item in shader_nodes:
                    node_type = str(node_item.get("type", "") if isinstance(node_item, dict) else node_item).lower()
                    if node_type in UNSUPPORTED_SHADER_NODES or node_type != "bsdf_principled":
                        return (
                            False,
                            "UNSUPPORTED_REQUEST",
                            f"Unsupported shader node type '{node_type}'. Only 'BSDF_PRINCIPLED' is supported.",
                        )

        # 1. Validation for create_material
        if tool_name == TOOL_CREATE_MATERIAL:
            name = str(params.get("name") or params.get("material_name", "")).strip()
            if not name:
                return False, "INVALID_PARAMS", "Material 'name' is required and cannot be empty."

            base_color = params.get("base_color")
            if base_color is not None:
                if not isinstance(base_color, (list, tuple)) or len(base_color) not in (3, 4):
                    return False, "INVALID_PARAMS", "Parameter 'base_color' must be a 3- or 4-element list [r, g, b, (a)]."
                for idx, c in enumerate(base_color):
                    if not isinstance(c, (int, float)) or isinstance(c, bool):
                        return False, "INVALID_PARAMS", f"Color component {idx} must be a number."
                    if c < 0.0 or c > 1.0:
                        return False, "INVALID_PARAMS", f"Color component {idx} must be between 0.0 and 1.0, got {c}."

            for num_prop, min_val, max_val in (
                ("roughness", 0.0, 1.0),
                ("metallic", 0.0, 1.0),
                ("ior", 0.0, 5.0),
                ("alpha", 0.0, 1.0),
                ("specular", 0.0, 1.0),
            ):
                if num_prop in params and params[num_prop] is not None:
                    val = params[num_prop]
                    if not isinstance(val, (int, float)) or isinstance(val, bool):
                        return False, "INVALID_PARAMS", f"Parameter '{num_prop}' must be a number."
                    if val < min_val or val > max_val:
                        return (
                            False,
                            "INVALID_PARAMS",
                            f"Parameter '{num_prop}' must be between {min_val} and {max_val}, got {val}.",
                        )

        # 2. Validation for assign_material
        elif tool_name == TOOL_ASSIGN_MATERIAL:
            target = str(params.get("target_name") or params.get("target", "")).strip()
            if not target:
                return False, "INVALID_PARAMS", "Target object name ('target_name') is required."

            mat_name = str(params.get("material_name") or params.get("name", "")).strip()
            if not mat_name:
                return False, "INVALID_PARAMS", "Material name ('material_name') is required."

            slot_idx = params.get("slot_index")
            if slot_idx is not None:
                if not isinstance(slot_idx, int) or isinstance(slot_idx, bool) or slot_idx < 0:
                    return False, "INVALID_PARAMS", "Parameter 'slot_index' must be a non-negative integer."

        # 3. Validation for list_materials
        elif tool_name == TOOL_LIST_MATERIALS:
            limit = params.get("limit")
            if limit is not None and (not isinstance(limit, int) or limit < 1 or limit > 500):
                return False, "INVALID_PARAMS", "Parameter 'limit' must be an integer between 1 and 500."

            offset = params.get("offset")
            if offset is not None and (not isinstance(offset, int) or offset < 0):
                return False, "INVALID_PARAMS", "Parameter 'offset' must be a non-negative integer."

        # 4. Validation for manage_shader_nodes and aliases
        elif tool_name in (TOOL_MANAGE_SHADER_NODES, TOOL_CONNECT_SHADER_NODES, TOOL_MANAGE_NODES):
            target = str(params.get("target_name", "")).strip()
            if not target:
                return False, "INVALID_PARAMS", "Parameter 'target_name' is required for shader node management."

        # 5. Validation for bake_object_texture and aliases
        elif tool_name in (TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS):
            obj_name = str(params.get("object_name", "")).strip()
            if not obj_name:
                return False, "INVALID_PARAMS", "Parameter 'object_name' is required for texture baking."

        return True, None, None

    def execute_task(
        self,
        task: AgentTask,
        executor: BlenderExecutor,
        trusted_approval: Optional[bool] = None,
    ) -> AgentResult:
        """
        Executes a validated material task via BlenderExecutor with approval enforcement
        and read-only post-operation verification.
        """
        t0 = time.time()
        tool_name = task.task_type or task.required_capability or TOOL_CREATE_MATERIAL
        raw_params = dict(task.input_params)

        # 1. Pre-execution input validation
        is_valid, err_code, err_msg = self.validate_task_input(tool_name, raw_params)
        if not is_valid:
            duration_ms = round((time.time() - t0) * 1000, 2)
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[err_msg or "Validation error"],
                execution_time_ms=duration_ms,
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name},
                    observed_results={"error_code": err_code, "error": err_msg, "transaction_status": "NOT_APPLICABLE"},
                    status="FAIL",
                    details=err_msg or "Validation error",
                ),
            )

        # 2. Strict Human Approval Enforcement for mutations
        is_mutation = tool_name in (
            TOOL_CONFIGURE_MATERIAL_SHADER,
            TOOL_CREATE_MATERIAL,
            TOOL_ASSIGN_MATERIAL,
            TOOL_MANAGE_SHADER_NODES,
            TOOL_CONNECT_SHADER_NODES,
            TOOL_MANAGE_NODES,
            TOOL_BAKE_OBJECT_TEXTURE,
            TOOL_BAKE_TEXTURE,
            TOOL_BAKE_MATERIALS,
        ) and raw_params.get("action") != "list_nodes"
        approval_decision = None
        if is_mutation:
            # Model-supplied approved=True is strictly rejected as untrusted
            if raw_params.get("approved") is True:
                duration_ms = round((time.time() - t0) * 1000, 2)
                return AgentResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[
                        f"Approval denied: Tool argument 'approved=True' is untrusted and cannot authorize "
                        f"material mutation '{tool_name}'. Explicit user approval must be granted through a trusted approval mechanism."
                    ],
                    execution_time_ms=duration_ms,
                    verification=VerificationResult(
                        expected_conditions={"tool": tool_name},
                        observed_results={"error_code": "PERMISSION_DENIED", "transaction_status": "NOT_APPLICABLE"},
                        status="FAIL",
                        details="Untrusted model approved=True rejected",
                    ),
                )

            # Use the configured Blender approval provider for the human decision.
            # Resumed tasks bypass this prompt only after the dispatcher reads the
            # approved single-use token from Blender's registry; the bridge validates it again.
            if trusted_approval is not True:
                approval_manager = getattr(executor, "approval_manager", None)
                if approval_manager and approval_manager.has_provider:
                    # Bind the Blender request to the same normalized parameters that
                    # BlenderExecutor will later send to the bridge (including schema defaults).
                    approval_params = validate_tool_input(tool_name, raw_params, trusted_approval=True)
                    approval_params.pop("trusted_approval", None)
                    approval_params.pop("approved", None)
                    approval_decision = approval_manager.verify_approval(tool_name, approval_params)
                    if not approval_decision.approved:
                        duration_ms = round((time.time() - t0) * 1000, 2)
                        reason = approval_decision.reason or "Approval was not granted."
                        pending = approval_decision.status == "pending" and bool(approval_decision.request_id)
                        expired = approval_decision.status == "expired" or (
                            approval_decision.status is None and "expired" in reason.lower()
                        )
                        denied = approval_decision.status in ("denied", "cancelled") or (
                            approval_decision.status is None and any(
                                word in reason.lower() for word in ("denied", "cancelled", "expired", "timed out")
                            )
                        )
                        observed = {
                            "error_code": "APPROVAL_REQUIRED" if pending else (
                                "APPROVAL_EXPIRED" if expired else "PERMISSION_DENIED" if denied else "APPROVAL_REQUIRED"
                            ),
                            "transaction_status": "NOT_APPLICABLE",
                        }
                        if pending:
                            observed.update({
                                "approval_pending": True,
                                "approval_request_id": approval_decision.request_id,
                                "approval_expires_at": approval_decision.expires_at,
                            })
                        return AgentResult(
                            task_id=task.task_id,
                            status=TaskStatus.AWAITING_APPROVAL if pending or not (denied or expired) else TaskStatus.FAILED,
                            errors=[reason],
                            execution_time_ms=duration_ms,
                            verification=VerificationResult(
                                expected_conditions={"tool": tool_name},
                                observed_results=observed,
                                status="FAIL",
                                details=reason,
                            ),
                        )
                    trusted_approval = True
                else:
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    return AgentResult(
                        task_id=task.task_id,
                        status=TaskStatus.AWAITING_APPROVAL,
                        errors=[
                            f"Approval required: Material mutation '{tool_name}' requires explicit user approval through "
                            "a trusted approval mechanism."
                        ],
                        execution_time_ms=duration_ms,
                        verification=VerificationResult(
                            expected_conditions={"tool": tool_name},
                            observed_results={"error_code": "APPROVAL_REQUIRED", "transaction_status": "NOT_APPLICABLE"},
                            status="FAIL",
                            details="Explicit user approval required for scene mutation",
                        ),
                    )

        # 3. Execution via BlenderExecutor
        clean_params = dict(raw_params)
        clean_params.pop("approved", None)
        if approval_decision:
            if approval_decision.request_id:
                clean_params["request_id"] = approval_decision.request_id
            if approval_decision.approval_token:
                clean_params["approval_token"] = approval_decision.approval_token

        try:
            if is_mutation and trusted_approval is True:
                try:
                    resp = executor.execute_tool(tool_name, clean_params, trusted_approval=True)
                except TypeError:
                    resp = executor.execute_tool(tool_name, clean_params)
            else:
                resp = executor.execute_tool(tool_name, clean_params)
        except Exception as exc:
            logger.exception(f"Unexpected executor exception during material execution of '{tool_name}': {exc}")
            resp = BridgeResponse.error(f"Executor exception: {exc}")

        exec_duration_ms = round((time.time() - t0) * 1000, 2)

        # 4. Handle Execution Failure
        shader_result_failed = (
            tool_name in (TOOL_MANAGE_SHADER_NODES, TOOL_CONNECT_SHADER_NODES, TOOL_MANAGE_NODES, TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS, TOOL_CONFIGURE_MATERIAL_SHADER, TOOL_INSPECT_MATERIAL_SHADER)
            and isinstance(resp.result, dict) and resp.result.get("success") is False
        )
        if not resp.is_success or shader_result_failed:
            err_msg = resp.message or "Material execution failed"
            err_code = "EXECUTION_FAILED"
            err_msg_lower = err_msg.lower()
            if "not found" in err_msg_lower:
                err_code = "DATA_UNAVAILABLE"
            elif "exists" in err_msg_lower:
                err_code = "NAME_COLLISION"
            elif "unsupported" in err_msg_lower:
                err_code = "UNSUPPORTED_REQUEST"

            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                errors=[err_msg],
                execution_time_ms=exec_duration_ms,
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name},
                    observed_results={"error_code": err_code, "error": err_msg, "transaction_status": "NOT_APPLICABLE" if tool_name == TOOL_INSPECT_MATERIAL_SHADER else "ROLLBACK_UNVERIFIED" if tool_name in (TOOL_MANAGE_SHADER_NODES, TOOL_CONNECT_SHADER_NODES, TOOL_MANAGE_NODES, TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS, TOOL_CONFIGURE_MATERIAL_SHADER) else "ROLLED_BACK"},
                    status="FAIL",
                    details=err_msg,
                ),
            )

        # 5. Post-Operation Read-Only Inspection Verification
        v_start = time.time()
        verification_passed = True
        verification_details: Dict[str, Any] = {}

        if tool_name == TOOL_CONFIGURE_MATERIAL_SHADER:
            from blender_addon.universal_mcp.bridge.material_shader_contract import verify_material_shader
            try:
                inspected = executor.execute_tool(TOOL_INSPECT_MATERIAL_SHADER, {"target_name": raw_params["target_name"]})
                verification_passed = inspected.is_success and verify_material_shader(raw_params, resp.result, inspected.result)
            except Exception:
                verification_passed = False
            if not verification_passed:
                verification_details["error"] = "Typed material shader independent readback failed; reconcile actual state"
        elif tool_name == TOOL_INSPECT_MATERIAL_SHADER:
            observed = resp.result or {}
            verification_passed = (observed.get("success") is True and observed.get("verified") is True
                and observed.get("target_name") == raw_params["target_name"]
                and isinstance(observed.get("nodes"), list) and isinstance(observed.get("links"), list))
            if not verification_passed:
                verification_details["error"] = "Material shader inspection did not return verified state"
        elif tool_name == TOOL_CREATE_MATERIAL:
            mat_name = str(raw_params.get("name") or raw_params.get("material_name", "")).strip()
            try:
                insp_resp = executor.execute_tool(TOOL_LIST_MATERIALS, {"filter_name": mat_name})
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    found_materials = insp_resp.result.get("materials", [])
                    matched = [m for m in found_materials if m.get("name") == mat_name]
                    if matched:
                        verification_details["verified_material"] = matched[0]
                        verification_details["material_exists"] = True
                    else:
                        verification_passed = False
                        verification_details["error"] = f"Created material '{mat_name}' not found in session."
                else:
                    verification_passed = False
                    verification_details["error"] = "Verification inspection failed to retrieve materials list."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"

        elif tool_name == TOOL_ASSIGN_MATERIAL:
            target_name = str(raw_params.get("target_name") or raw_params.get("target", "")).strip()
            mat_name = str(raw_params.get("material_name") or raw_params.get("name", "")).strip()
            try:
                insp_resp = executor.execute_tool(
                    TOOL_INSPECT_SCENE_DATA,
                    {"category": "object_materials", "target_name": target_name},
                )
                if insp_resp.is_success and isinstance(insp_resp.result, dict):
                    slots = insp_resp.result.get("materials", [])
                    assigned_mats = [s.get("material_name") for s in slots if s.get("assigned")]
                    if mat_name in assigned_mats:
                        verification_details["verified_target"] = target_name
                        verification_details["assigned_material"] = mat_name
                        verification_details["material_slots"] = slots
                    else:
                        verification_passed = False
                        verification_details["error"] = (
                            f"Material '{mat_name}' not found in assigned slots of '{target_name}'. "
                            f"Observed: {assigned_mats}"
                        )
                else:
                    verification_passed = False
                    verification_details["error"] = f"Failed to inspect material slots on '{target_name}'."
            except Exception as ve:
                verification_passed = False
                verification_details["error"] = f"Verification query error: {ve}"

        elif tool_name in (TOOL_MANAGE_SHADER_NODES, TOOL_CONNECT_SHADER_NODES, TOOL_MANAGE_NODES):
            action = str(raw_params.get("action", "create_node")).strip().lower()
            if action in ("set_property", "connect"):
                observed = resp.result if isinstance(resp.result, dict) else {}
                verification_passed = observed.get("success") is True and observed.get("verified") is True
                if action == "set_property":
                    try:
                        verification_passed = verification_passed and observed.get("property_set") is True and observed.get("node_name") == str(raw_params.get("node_name", "")).strip() and observed.get("property_name") == str(raw_params.get("property_name", "")).strip() and "property_value" in observed and shader_values_match(observed["property_value"], raw_params.get("property_value"))
                    except (ValueError, TypeError):
                        verification_passed = False
                else:
                    verification_passed = verification_passed and observed.get("connected") is True and observed.get("from_node") == str(raw_params.get("from_node", "")).strip() and observed.get("to_node") == str(raw_params.get("to_node", "")).strip()
                if action == "connect":
                    for key in ("from_socket", "to_socket"):
                        verification_passed = verification_passed and bool(str(raw_params.get(key, "")).strip()) and str(raw_params.get(key, "")).strip() in (observed.get(key), observed.get(key+"_identifier"))
                verification_details["shader_readback"] = observed
                if not verification_passed:
                    verification_details["error"] = "Shader operation did not provide matching verified readback."

        elif tool_name in (TOOL_BAKE_OBJECT_TEXTURE, TOOL_BAKE_TEXTURE, TOOL_BAKE_MATERIALS):
            observed = resp.result or {}
            verification_passed = (
                observed.get("success") is True and observed.get("baked") is True
                and observed.get("verified") is True
                and observed.get("object_name") == raw_params.get("object_name")
                and observed.get("width") == raw_params.get("width", 1024)
                and observed.get("height") == raw_params.get("height", 1024)
                and observed.get("bake_type") == str(raw_params.get("bake_type", "COMBINED")).upper()
                and observed.get("saved_filepath") == raw_params.get("save_filepath")
            )
            verification_details["bake_readback"] = observed
            if not verification_passed:
                verification_details["error"] = "Bake operation did not provide matching verified readback"

        elif tool_name == TOOL_LIST_MATERIALS:
            verification_details["materials_count"] = len(resp.result.get("materials", []))

        v_duration_ms = round((time.time() - v_start) * 1000, 2)
        total_duration_ms = round((time.time() - t0) * 1000, 2)

        if not verification_passed:
            verification_details["transaction_status"] = "ROLLBACK_UNVERIFIED"
            return AgentResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                output=resp.result,
                errors=[verification_details.get("error", "Post-operation material verification failed")],
                execution_time_ms=total_duration_ms,
                verification=VerificationResult(
                    expected_conditions={"tool": tool_name},
                    observed_results=verification_details,
                    status="FAIL",
                    details=verification_details.get("error", "Post-operation material verification failed"),
                ),
            )

        verification_details["transaction_status"] = "COMMITTED" if is_mutation else "NOT_APPLICABLE"
        return AgentResult(
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            output=resp.result,
            execution_time_ms=total_duration_ms,
            verification=VerificationResult(
                expected_conditions={"tool": tool_name},
                observed_results=verification_details,
                status="PASS",
                details=f"Material operation '{tool_name}' verified successfully.",
            ),
        )
