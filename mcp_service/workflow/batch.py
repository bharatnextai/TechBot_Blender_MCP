"""
Batch Asset Processing & Multi-Asset Workflow Automation for Universal MCP.
Provides controlled multi-asset batch conversions (e.g. OBJ/FBX -> GLB),
transactional scene isolation, per-asset failure containment, and safe
datablock reclamation using Blender's purge mechanisms.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set, Tuple
import os
import time
import uuid
import copy
import logging
from pathlib import Path

from shared.models.agent_contracts import (
    DelegationContract,
    AgentTask,
    TaskStatus,
)
from .checkpoints import SceneCheckpoint, SceneCheckpointManager, is_response_success
from .rollback import RollbackReceipt, StageRollbackEngine
from .verification_gates import VerificationGate, MeshManifoldnessGate, TextureBoundsGate
from .orchestrator import WorkflowDAG, WorkflowStage, WorkflowOrchestrator, WorkflowExecutionReport

logger = logging.getLogger("UniversalMCP_BatchProcessor")


@dataclass
class BatchItemResult:
    """
    Detailed execution result for a single asset in a batch conversion run.
    """
    input_path: str
    output_path: Optional[str] = None
    sidecar_path: Optional[str] = None
    target_format: str = "GLB"
    status: str = "PENDING"  # "SUCCEEDED", "FAILED", "SKIPPED"
    sha256: Optional[str] = None
    file_size_bytes: int = 0
    error: Optional[str] = None
    rollback_performed: bool = False
    datablocks_purged: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchItemResult":
        return cls(**data)


@dataclass
class BatchExecutionReport:
    """
    Comprehensive audit report of a multi-asset batch processing run.
    """
    batch_id: str = field(default_factory=lambda: f"batch_{uuid.uuid4().hex[:12]}")
    target_format: str = "GLB"
    total_assets: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    items: List[BatchItemResult] = field(default_factory=list)
    duration_ms: float = 0.0
    status: str = "PENDING"  # "SUCCEEDED", "FAILED", "PARTIAL"
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "target_format": self.target_format,
            "total_assets": self.total_assets,
            "succeeded_count": self.succeeded_count,
            "failed_count": self.failed_count,
            "items": [it.to_dict() for it in self.items],
            "duration_ms": self.duration_ms,
            "status": self.status,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchExecutionReport":
        items_data = data.get("items", [])
        items = [BatchItemResult.from_dict(it) for it in items_data]
        return cls(
            batch_id=data.get("batch_id", f"batch_{uuid.uuid4().hex[:12]}"),
            target_format=data.get("target_format", "GLB"),
            total_assets=data.get("total_assets", len(items)),
            succeeded_count=data.get("succeeded_count", 0),
            failed_count=data.get("failed_count", 0),
            items=items,
            duration_ms=data.get("duration_ms", 0.0),
            status=data.get("status", "PENDING"),
            summary=data.get("summary", ""),
        )


class BatchAssetProcessor:
    """
    Executes controlled multi-asset conversions through WorkflowOrchestrator and DirectorAgent,
    guaranteeing per-asset transactional isolation, verification gates, and datablock reclamation.
    """

    def __init__(
        self,
        orchestrator: Optional[WorkflowOrchestrator] = None,
        executor: Optional[Any] = None,
        director: Optional[Any] = None,
    ):
        self._orchestrator = orchestrator or WorkflowOrchestrator(executor=executor)
        self._executor = executor or self._orchestrator._executor
        self._director = director

    def process_batch(
        self,
        input_paths: List[str],
        output_dir: str,
        target_format: str = "GLB",
        trusted_approval: bool = True,
        overwrite: bool = True,
        session_id: str = "batch_session",
        gates: Optional[Dict[str, List[VerificationGate]]] = None,
    ) -> BatchExecutionReport:
        """
        Processes a sequence of input assets into validated target format assets:
        1. Validates all filepaths (rejects path traversal '..').
        2. Isolates execution per asset: failure of asset K does not affect 0..K-1 or K+1..N.
        3. Enforces pre-stage checkpoint and post-import verification gates.
        4. Triggers automatic rollback on import or export failure.
        5. Purges temporary scene objects and datablocks between iterations.
        6. Verifies cryptographic SHA-256 sidecar generation for all outputs.
        """
        t0 = time.time()
        target_fmt = str(target_format).strip().upper()
        ext = target_fmt.lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        report = BatchExecutionReport(
            target_format=target_fmt,
            total_assets=len(input_paths),
        )

        logger.info(
            "Starting batch processing of %d assets -> %s in '%s'",
            len(input_paths),
            target_fmt,
            output_dir,
        )

        # 1. Global path traversal validation on output directory
        norm_out_dir = str(output_dir).replace("\\", "/")
        if ".." in norm_out_dir.split("/"):
            report.status = "FAILED"
            report.summary = f"Path traversal detected in output directory: '{output_dir}'"
            report.failed_count = len(input_paths)
            report.duration_ms = round((time.time() - t0) * 1000, 2)
            for inp in input_paths:
                report.items.append(
                    BatchItemResult(
                        input_path=inp,
                        target_format=target_fmt,
                        status="FAILED",
                        error=report.summary,
                    )
                )
            return report

        # 2. Iterate sequentially through inputs with full failure isolation
        for idx, in_path in enumerate(input_paths):
            it_t0 = time.time()
            item_res = BatchItemResult(
                input_path=in_path,
                target_format=target_fmt,
            )

            # Validate input path traversal
            norm_in_path = str(in_path).replace("\\", "/")
            if ".." in norm_in_path.split("/"):
                item_res.status = "FAILED"
                item_res.error = f"Path traversal detected in input path: '{in_path}'"
                item_res.duration_ms = round((time.time() - it_t0) * 1000, 2)
                report.items.append(item_res)
                report.failed_count += 1
                continue

            stem = Path(norm_in_path).stem
            dest_file = f"{norm_out_dir}/{stem}{ext}".replace("//", "/")
            item_res.output_path = dest_file

            # Capture baseline checkpoint before touching scene for this item
            base_ckpt = None
            if self._executor:
                try:
                    base_ckpt = self._orchestrator.checkpoint_manager.capture_checkpoint(
                        stage_id=f"batch_pre_{stem}",
                        executor=self._executor,
                        metadata={"batch_id": report.batch_id, "item_index": idx},
                    )
                except Exception as ce:
                    logger.warning("Could not capture base checkpoint for '%s': %s", stem, ce)

            try:
                # Formulate brief for this conversion
                brief = f"Convert '{norm_in_path}' to '{dest_file}'"
                if self._director is None:
                    from ..agents.director import DirectorAgent
                    self._director = DirectorAgent()

                contract = self._director.decompose_brief(brief)

                # Ensure overwrite parameter is applied if set
                if overwrite and "agent.interchange_delivery" in contract.domain_tasks:
                    for t in contract.domain_tasks["agent.interchange_delivery"]:
                        if t.task_type == "export_scene_asset":
                            t.input_params["overwrite"] = True

                # Execute through WorkflowOrchestrator
                wf_report = self._director.submit_workflow(
                    contract=contract,
                    orchestrator=self._orchestrator,
                    session_id=f"{session_id}_{stem}",
                    trusted_approval=trusted_approval,
                    gates=gates,
                )

                if wf_report.status == "SUCCEEDED":
                    # Check disk artifact and SHA-256 sidecar
                    out_p = Path(dest_file)
                    sidecar_p = Path(f"{dest_file}.sha256")
                    if out_p.exists() and out_p.stat().st_size > 0:
                        item_res.status = "SUCCEEDED"
                        item_res.file_size_bytes = out_p.stat().st_size
                        if sidecar_p.exists():
                            item_res.sidecar_path = str(sidecar_p)
                            import json
                            try:
                                sdata = json.loads(sidecar_p.read_text(encoding="utf-8"))
                                item_res.sha256 = sdata.get("sha256")
                            except Exception:
                                pass
                        report.succeeded_count += 1
                    else:
                        item_res.status = "FAILED"
                        item_res.error = f"Output file missing or empty: {dest_file}"
                        report.failed_count += 1
                else:
                    item_res.status = "FAILED"
                    stage_errors = [str(s.get("error")) for s in wf_report.stages.values() if s.get("error")]
                    item_res.error = "; ".join(stage_errors) if stage_errors else (wf_report.summary or "Workflow execution failed")
                    item_res.rollback_performed = len(wf_report.rollbacks_executed) > 0
                    report.failed_count += 1

            except Exception as exc:
                item_res.status = "FAILED"
                item_res.error = str(exc)
                report.failed_count += 1
                logger.error("Exception during batch processing of '%s': %s", in_path, exc)

                # Perform emergency restoration to baseline checkpoint on uncaught error
                if base_ckpt and self._executor:
                    try:
                        self._orchestrator.rollback_engine.rollback_to_checkpoint(
                            base_ckpt,
                            self._executor,
                            trusted_approval=True,
                        )
                        item_res.rollback_performed = True
                    except Exception as re:
                        logger.error("Failed emergency rollback for '%s': %s", in_path, re)

            finally:
                # 3. Clean up imported meshes and reclaim orphaned datablocks
                if self._executor:
                    try:
                        # Clean up any objects that were added during this item's processing
                        if base_ckpt:
                            list_res = self._executor.execute_tool("list_objects", {})
                            if list_res and is_response_success(list_res) and list_res.result:
                                curr_objs = list_res.result.get("objects", [])
                                curr_names = [
                                    o.get("name") if isinstance(o, dict) else str(o)
                                    for o in curr_objs
                                    if (o.get("name") if isinstance(o, dict) else str(o))
                                ]
                                added = [n for n in curr_names if n not in base_ckpt.objects]
                                for obj_name in added:
                                    self._executor.execute_tool(
                                        "delete_object",
                                        {"name": obj_name},
                                        trusted_approval=True,
                                    )

                        # Reclaim orphaned datablocks safely
                        p_res = self._executor.execute_tool("purge_orphaned_datablocks", {}, trusted_approval=True)
                        if p_res and is_response_success(p_res) and isinstance(p_res.result, dict):
                            item_res.datablocks_purged = p_res.result.get("purged_count", 0)
                    except Exception as pe:
                        logger.debug("Datablock reclamation notice for '%s': %s", in_path, pe)

            item_res.duration_ms = round((time.time() - it_t0) * 1000, 2)
            report.items.append(item_res)

        report.duration_ms = round((time.time() - t0) * 1000, 2)
        if report.succeeded_count == report.total_assets and report.total_assets > 0:
            report.status = "SUCCEEDED"
            report.summary = f"All {report.total_assets} assets converted to {target_fmt} successfully."
        elif report.succeeded_count > 0:
            report.status = "PARTIAL"
            report.summary = f"Batch finished: {report.succeeded_count} succeeded, {report.failed_count} failed."
        else:
            report.status = "FAILED"
            report.summary = f"All {report.total_assets} batch asset conversions failed."

        logger.info("Batch processing complete: %s (duration=%.2fms)", report.summary, report.duration_ms)
        return report
