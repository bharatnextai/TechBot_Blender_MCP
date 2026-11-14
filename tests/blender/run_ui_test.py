import argparse
import asyncio
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path(r"D:\Blender-Ollama-Addon\blender-universal-mcp")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")


def topology(payload: object) -> dict:
    envelope = json.loads(payload.content[0].text)
    if envelope.get("status") != "success":
        raise RuntimeError("Read-only topology failed: " + json.dumps(envelope))
    result = envelope.get("result", {})
    return result.get("observed_data", result)


def tool_json(response: object) -> dict:
    if not getattr(response, "content", None):
        return {"is_error": bool(getattr(response, "isError", False)), "content": []}
    try:
        return json.loads(response.content[0].text)
    except (ValueError, AttributeError):
        return {"is_error": bool(getattr(response, "isError", False)),
                "content": [getattr(response.content[0], "text", "")]}


def wait_for_terminal_status_sync(root: Path, request_id: str, timeout: float = 15.0, poll_interval: float = 0.05) -> dict:
    """
    Polls terminal_approval.json until a definitive terminal approval status is recorded.

    For 'approved', status is definitive when token_consumed is True (or timeout).
    For 'denied', 'cancelled', 'expired', status is definitive immediately.
    """
    deadline = time.monotonic() + timeout
    terminal_file = root / "terminal_approval.json"
    last_record = None

    while time.monotonic() < deadline:
        if terminal_file.exists():
            try:
                data = json.loads(terminal_file.read_text(encoding="utf-8"))
                if data.get("request_id") == request_id:
                    last_record = data
                    st = data.get("status")
                    consumed = data.get("token_consumed")
                    if (st == "approved" and consumed is True) or st in {"denied", "cancelled", "expired"}:
                        return data
            except (json.JSONDecodeError, OSError):
                # Transient read during file write; retry on next poll interval
                pass
        time.sleep(poll_interval)

    if last_record is not None:
        return last_record
    raise TimeoutError(f"Timed out after {timeout:.1f}s waiting for terminal approval status for request {request_id}")


async def wait_for_terminal_status_async(root: Path, request_id: str, timeout: float = 15.0, poll_interval: float = 0.05) -> dict:
    """
    Asynchronous version of wait_for_terminal_status.
    """
    deadline = time.monotonic() + timeout
    terminal_file = root / "terminal_approval.json"
    last_record = None

    while time.monotonic() < deadline:
        if terminal_file.exists():
            try:
                data = json.loads(terminal_file.read_text(encoding="utf-8"))
                if data.get("request_id") == request_id:
                    last_record = data
                    st = data.get("status")
                    consumed = data.get("token_consumed")
                    if (st == "approved" and consumed is True) or st in {"denied", "cancelled", "expired"}:
                        return data
            except (json.JSONDecodeError, OSError):
                pass
        await asyncio.sleep(poll_interval)

    if last_record is not None:
        return last_record
    raise TimeoutError(f"Timed out after {timeout:.1f}s waiting for terminal approval status for request {request_id}")


def wait_for_verified_denial_sync(
    root: Path,
    request_id: str,
    timeout: float = 15.0,
    poll_interval: float = 0.05,
) -> tuple:
    """
    Synchronously waits for a verified denial action through the real Blender approval UI and
    a matching definitive 'denied' terminal status.
    Fails closed on:
    - timeout
    - missing UI evidence
    - unexpected 'approved' status
    - mismatched request ID
    """
    deadline = time.monotonic() + timeout
    terminal_file = root / "terminal_approval.json"
    ui_file = root / "ui_interaction_evidence.json"

    while time.monotonic() < deadline:
        if terminal_file.exists():
            try:
                term_data = json.loads(terminal_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                term_data = None

            if term_data and term_data.get("request_id") == request_id:
                st = term_data.get("status")
                if st == "approved":
                    raise AssertionError(
                        f"Denial harness failure: Request '{request_id}' was unexpectedly approved in Blender UI!"
                    )
                if st in ("cancelled", "expired"):
                    raise AssertionError(
                        f"Denial harness failure: Request '{request_id}' resolved to unexpected terminal status '{st}', not 'denied'!"
                    )
                if st == "denied":
                    if ui_file.exists():
                        try:
                            ui_data = json.loads(ui_file.read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            ui_data = None
                        if ui_data:
                            if ui_data.get("request_id") != request_id:
                                raise AssertionError(
                                    f"Denial harness failure: UI interaction request_id '{ui_data.get('request_id')}' does not match '{request_id}'"
                                )
                            if ui_data.get("action") != "deny":
                                raise AssertionError(
                                    f"Denial harness failure: UI interaction action was '{ui_data.get('action')}', expected 'deny'!"
                                )
                            return term_data, ui_data
        time.sleep(poll_interval)

    if terminal_file.exists():
        try:
            term_data = json.loads(terminal_file.read_text(encoding="utf-8"))
            if term_data.get("status") == "approved":
                raise AssertionError(f"Denial harness failure: Request '{request_id}' was unexpectedly approved in Blender UI.")
        except AssertionError:
            raise
        except Exception:
            pass
    if not ui_file.exists():
        raise TimeoutError(f"Denial harness failure: Timed out waiting for verified UI denial for request '{request_id}' (missing UI evidence).")
    raise TimeoutError(f"Denial harness failure: Timed out waiting for definitive 'denied' terminal status for request '{request_id}'.")


async def wait_for_verified_denial_async(
    root: Path,
    request_id: str,
    timeout: float = 300.0,
    poll_interval: float = 0.05,
    mutation_task: object = None,
) -> tuple:
    """
    Asynchronously waits for a verified denial action through the real Blender approval UI and
    a matching definitive 'denied' terminal status.
    Fails closed on:
    - timeout
    - missing UI evidence
    - unexpected 'approved' status
    - mismatched request ID
    - mutation completing before denial is confirmed
    """
    deadline = time.monotonic() + timeout
    terminal_file = root / "terminal_approval.json"
    ui_file = root / "ui_interaction_evidence.json"

    while time.monotonic() < deadline:
        if mutation_task is not None and getattr(mutation_task, "done", lambda: False)():
            res = mutation_task.result()
            payload = tool_json(res)
            if not getattr(res, "isError", False) and payload.get("status") != "error":
                raise RuntimeError(
                    f"Denial harness failure: MCP mutation succeeded before UI denial was established! Payload: {json.dumps(payload)}"
                )

        if terminal_file.exists():
            try:
                term_data = json.loads(terminal_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                term_data = None

            if term_data and term_data.get("request_id") == request_id:
                st = term_data.get("status")
                if st == "approved":
                    raise AssertionError(
                        f"Denial harness failure: Request '{request_id}' was unexpectedly approved in Blender UI! "
                        f"Terminal record: {json.dumps(term_data)}"
                    )
                if st in ("cancelled", "expired"):
                    raise AssertionError(
                        f"Denial harness failure: Request '{request_id}' resolved to unexpected terminal status '{st}', not 'denied'!"
                    )
                if st == "denied":
                    if ui_file.exists():
                        try:
                            ui_data = json.loads(ui_file.read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            ui_data = None
                        if ui_data:
                            if ui_data.get("request_id") != request_id:
                                raise AssertionError(
                                    f"Denial harness failure: UI interaction request_id '{ui_data.get('request_id')}' does not match '{request_id}'"
                                )
                            if ui_data.get("action") != "deny":
                                raise AssertionError(
                                    f"Denial harness failure: UI interaction action was '{ui_data.get('action')}', expected 'deny'!"
                                )
                            return term_data, ui_data

        await asyncio.sleep(poll_interval)

    if terminal_file.exists():
        try:
            term_data = json.loads(terminal_file.read_text(encoding="utf-8"))
            if term_data.get("status") == "approved":
                raise AssertionError(f"Denial harness failure: Request '{request_id}' was unexpectedly approved in Blender UI.")
        except AssertionError:
            raise
        except Exception:
            pass
    if not ui_file.exists():
        raise TimeoutError(f"Denial harness failure: Timed out waiting for verified UI denial for request '{request_id}' (missing UI evidence).")
    raise TimeoutError(f"Denial harness failure: Timed out waiting for definitive 'denied' terminal status for request '{request_id}'.")


async def wait_for_verified_cancellation_async(
    root: Path,
    request_id: str,
    timeout: float = 300.0,
    poll_interval: float = 0.05,
    mutation_task: object = None,
) -> tuple:
    """
    Asynchronously waits for a verified cancellation action through the real Blender approval UI and
    a matching definitive 'cancelled' terminal status.
    Fails closed on:
    - timeout
    - missing UI evidence
    - unexpected 'approved' or 'denied' status
    - mismatched request ID
    - mutation completing before cancellation is confirmed
    """
    deadline = time.monotonic() + timeout
    terminal_file = root / "terminal_approval.json"
    ui_file = root / "ui_interaction_evidence.json"

    while time.monotonic() < deadline:
        if mutation_task is not None and getattr(mutation_task, "done", lambda: False)():
            res = mutation_task.result()
            payload = tool_json(res)
            if not getattr(res, "isError", False) and payload.get("status") != "error":
                raise RuntimeError(
                    f"Cancellation harness failure: MCP mutation succeeded before UI cancellation was established! Payload: {json.dumps(payload)}"
                )

        if terminal_file.exists():
            try:
                term_data = json.loads(terminal_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                term_data = None

            if term_data and term_data.get("request_id") == request_id:
                st = term_data.get("status")
                if st == "approved":
                    raise AssertionError(
                        f"Cancellation harness failure: Request '{request_id}' was unexpectedly approved in Blender UI! "
                        f"Terminal record: {json.dumps(term_data)}"
                    )
                if st in ("denied", "expired"):
                    raise AssertionError(
                        f"Cancellation harness failure: Request '{request_id}' resolved to unexpected terminal status '{st}', not 'cancelled'!"
                    )
                if st == "cancelled":
                    if ui_file.exists():
                        try:
                            ui_data = json.loads(ui_file.read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            ui_data = None
                        if ui_data:
                            if ui_data.get("request_id") != request_id:
                                raise AssertionError(
                                    f"Cancellation harness failure: UI interaction request_id '{ui_data.get('request_id')}' does not match '{request_id}'"
                                )
                            if ui_data.get("action") != "dialog_cancel":
                                raise AssertionError(
                                    f"Cancellation harness failure: UI interaction action was '{ui_data.get('action')}', expected 'dialog_cancel'!"
                                )
                            return term_data, ui_data

        await asyncio.sleep(poll_interval)

    if terminal_file.exists():
        try:
            term_data = json.loads(terminal_file.read_text(encoding="utf-8"))
            if term_data.get("status") == "approved":
                raise AssertionError(f"Cancellation harness failure: Request '{request_id}' was unexpectedly approved in Blender UI.")
        except AssertionError:
            raise
        except Exception:
            pass
    if not ui_file.exists():
        raise TimeoutError(f"Cancellation harness failure: Timed out waiting for verified UI cancellation for request '{request_id}' (missing UI evidence).")
    raise TimeoutError(f"Cancellation harness failure: Timed out waiting for definitive 'cancelled' terminal status for request '{request_id}'.")


async def wait_for_verified_timeout_async(
    root: Path,
    request_id: str,
    timeout: float = 30.0,
    poll_interval: float = 0.05,
    mutation_task: object = None,
) -> dict:
    """
    Asynchronously waits for a pending approval request to reach TTL expiry in the isolated
    Blender registry and reach definitive 'expired' terminal status.
    Fails closed on:
    - timeout waiting for expiry
    - unexpected 'approved' or 'denied' status
    - mutation succeeding unexpectedly
    """
    deadline = time.monotonic() + timeout
    terminal_file = root / "terminal_approval.json"

    while time.monotonic() < deadline:
        if mutation_task is not None and getattr(mutation_task, "done", lambda: False)():
            res = mutation_task.result()
            payload = tool_json(res)
            if not getattr(res, "isError", False) and payload.get("status") != "error":
                raise RuntimeError(
                    f"Timeout harness failure: MCP mutation unexpectedly succeeded! Payload: {json.dumps(payload)}"
                )

        if terminal_file.exists():
            try:
                term_data = json.loads(terminal_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                term_data = None

            if term_data and term_data.get("request_id") == request_id:
                st = term_data.get("status")
                if st == "approved":
                    raise AssertionError(
                        f"Timeout harness failure: Request '{request_id}' was unexpectedly approved in Blender UI!"
                    )
                if st == "denied":
                    raise AssertionError(
                        f"Timeout harness failure: Request '{request_id}' was unexpectedly denied, expected expiry!"
                    )
                if st == "expired":
                    return term_data

        await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Timeout harness failure: Timed out waiting for request '{request_id}' to reach 'expired' status.")


def verify_controller_postconditions(root: Path, timeout: float = 15.0) -> dict:
    """
    Non-mutating postcondition validation using saved test evidence.
    Validates controller status-wait, vertex delta, replay rejection, and transaction commit.
    """
    pending_file = root / "pending.json"
    if not pending_file.exists():
        raise FileNotFoundError(f"Missing pending.json in {root}")
    pending = json.loads(pending_file.read_text(encoding="utf-8"))
    req_id = pending["request_id"]

    scenario_file = root / "scenario.json"
    scenario = json.loads(scenario_file.read_text(encoding="utf-8")) if scenario_file.exists() else {"decision": "approve"}
    if scenario.get("decision") == "deny":
        status_file = root / "terminal_approval.json"
        if not status_file.exists():
            raise FileNotFoundError("Missing terminal_approval.json in " + str(root))
        terminal = json.loads(status_file.read_text(encoding="utf-8"))
        if terminal.get("status") == "approved":
            raise AssertionError(
                f"Denial postconditions failed: Request '{req_id}' has unexpected status 'approved' (approval observed instead of denial)"
            )
        if terminal.get("status") != "denied":
            raise AssertionError(
                f"Denial postconditions failed: Request '{req_id}' has status '{terminal.get('status')}', expected 'denied'"
            )

        ui_file = root / "ui_interaction_evidence.json"
        if not ui_file.exists():
            raise AssertionError(
                f"Denial postconditions failed: Missing UI interaction evidence (no verified human UI denial recorded for request '{req_id}')"
            )
        ui_data = json.loads(ui_file.read_text(encoding="utf-8"))
        if ui_data.get("action") != "deny":
            raise AssertionError(
                f"Denial postconditions failed: UI interaction action was '{ui_data.get('action')}', expected 'deny'"
            )
        if ui_data.get("request_id") != req_id:
            raise AssertionError(
                f"Denial postconditions failed: UI interaction request_id '{ui_data.get('request_id')}' does not match '{req_id}'"
            )

        response_file = root / "mcp_mutation_response.json"
        if not response_file.exists():
            raise FileNotFoundError("Missing mcp_mutation_response.json in " + str(root))
        mutation_record = json.loads(response_file.read_text(encoding="utf-8"))
        mutation_response = mutation_record.get("payload", mutation_record)
        if not mutation_record.get("isError") and mutation_response.get("status") != "error":
            raise AssertionError(
                f"Denial postconditions failed: MCP mutation did not fail closed; returned status '{mutation_response.get('status')}'"
            )

        trace_file = root / "denial_scene_evidence.json"
        public_status_file = root / "approval_status_mcp.json"
        if not all(path.exists() for path in (trace_file, public_status_file)):
            raise AssertionError("Denial postconditions failed: Incomplete denial evidence in " + str(root))

        scene = json.loads(trace_file.read_text(encoding="utf-8"))
        public_status = json.loads(public_status_file.read_text(encoding="utf-8"))
        before = json.loads((root / "topology_before.json").read_text(encoding="utf-8"))
        after = json.loads((root / "topology_after_mcp.json").read_text(encoding="utf-8"))
        final_state = json.loads((root / "final_blender_state.json").read_text(encoding="utf-8"))
        checks = {
            "request_id_matches": terminal.get("request_id") == req_id,
            "terminal_denied": terminal.get("status") == "denied",
            "ui_action_verified": ui_data.get("action") == "deny",
            "token_unconsumed": terminal.get("token_consumed") is False,
            "no_approval_token_issued": scene.get("approval_token_present") is False,
            "invalid_consume_rejected": scene.get("invalid_consume_rejected") is True,
            "denied_token_not_consumed": scene.get("token_consumed_after_probe") is False,
            "mcp_mutation_failed_closed": mutation_response.get("status") == "error",
            "mcp_status_denied": public_status.get("status") == "denied",
            "public_status_has_no_token": "approval_token" not in public_status,
            "mutation_handler_not_invoked": scene.get("edit_mesh_handler_calls") == 0,
            "topology_unchanged": before.get("elements") == after.get("elements"),
            "snapshot_unchanged": before.get("snapshot_id") == after.get("snapshot_id"),
            "state_unchanged": before.get("state_id") == after.get("state_id"),
            "scene_inventory_unchanged": scene.get("objects_before") == scene.get("objects_after"),
            "mesh_inventory_unchanged": scene.get("meshes_before") == scene.get("meshes_after"),
            "material_inventory_unchanged": scene.get("materials_before") == scene.get("materials_after"),
            "target_mesh_state_unchanged": scene.get("target_before") == scene.get("target_after"),
            "final_pending_count_zero": final_state.get("pending_request_count") == 0,
            "bridge_stopped": final_state.get("bridge_running") is False,
            "blender_process_exited": (root / "process_exit.json").exists()
            and json.loads((root / "process_exit.json").read_text(encoding="utf-8")).get("returncode") == 0,
        }
        if not all(checks.values()):
            raise AssertionError("Denial postconditions failed: " + json.dumps({"checks": checks, "terminal": terminal, "scene": scene, "mutation_response": mutation_response, "public_status": public_status, "final_state": final_state}, sort_keys=True))
        result = {"status": "PASS", "scenario": "manual_ui_denial", "request_id": req_id,
                  "approval_status": terminal["status"], "token_consumed": terminal["token_consumed"],
                  "checks": checks, "validation_mode": "non_mutating_saved_evidence_verification"}
        (root / "final_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    if scenario.get("decision") == "timeout":
        status_file = root / "terminal_approval.json"
        if not status_file.exists():
            raise FileNotFoundError("Missing terminal_approval.json in " + str(root))
        terminal = json.loads(status_file.read_text(encoding="utf-8"))
        if terminal.get("status") == "approved":
            raise AssertionError(
                f"Timeout postconditions failed: Request '{req_id}' has unexpected status 'approved'"
            )
        if terminal.get("status") != "expired":
            raise AssertionError(
                f"Timeout postconditions failed: Request '{req_id}' has status '{terminal.get('status')}', expected 'expired'"
            )

        response_file = root / "mcp_mutation_response.json"
        if not response_file.exists():
            raise FileNotFoundError("Missing mcp_mutation_response.json in " + str(root))
        mutation_record = json.loads(response_file.read_text(encoding="utf-8"))
        mutation_response = mutation_record.get("payload", mutation_record)
        if not mutation_record.get("isError") and mutation_response.get("status") != "error":
            raise AssertionError(
                f"Timeout postconditions failed: MCP mutation did not fail closed; returned status '{mutation_response.get('status')}'"
            )

        trace_file = root / "timeout_scene_evidence.json"
        public_status_file = root / "approval_status_mcp.json"
        if not all(path.exists() for path in (trace_file, public_status_file)):
            raise AssertionError("Timeout postconditions failed: Incomplete timeout evidence in " + str(root))

        scene = json.loads(trace_file.read_text(encoding="utf-8"))
        public_status = json.loads(public_status_file.read_text(encoding="utf-8"))
        before = json.loads((root / "topology_before.json").read_text(encoding="utf-8"))
        after = json.loads((root / "topology_after_mcp.json").read_text(encoding="utf-8"))
        final_state = json.loads((root / "final_blender_state.json").read_text(encoding="utf-8"))
        checks = {
            "request_id_matches": terminal.get("request_id") == req_id,
            "terminal_expired": terminal.get("status") == "expired",
            "token_unconsumed": terminal.get("token_consumed") is False,
            "no_approval_token_issued": scene.get("approval_token_present") is False,
            "invalid_consume_rejected": scene.get("invalid_consume_rejected") is True,
            "late_resolve_rejected": scene.get("late_resolve_rejected") is True,
            "expired_token_not_consumed": scene.get("token_consumed_after_probe") is False,
            "mcp_mutation_failed_closed": mutation_response.get("status") == "error",
            "mcp_status_expired": public_status.get("status") == "expired",
            "public_status_has_no_token": "approval_token" not in public_status,
            "mutation_handler_not_invoked": scene.get("edit_mesh_handler_calls") == 0,
            "topology_unchanged": before.get("elements") == after.get("elements"),
            "snapshot_unchanged": before.get("snapshot_id") == after.get("snapshot_id"),
            "state_unchanged": before.get("state_id") == after.get("state_id"),
            "scene_inventory_unchanged": scene.get("objects_before") == scene.get("objects_after"),
            "mesh_inventory_unchanged": scene.get("meshes_before") == scene.get("meshes_after"),
            "material_inventory_unchanged": scene.get("materials_before") == scene.get("materials_after"),
            "target_mesh_state_unchanged": scene.get("target_before") == scene.get("target_after"),
            "final_pending_count_zero": final_state.get("pending_request_count") == 0,
            "bridge_stopped": final_state.get("bridge_running") is False,
            "blender_process_exited": (root / "process_exit.json").exists()
            and json.loads((root / "process_exit.json").read_text(encoding="utf-8")).get("returncode") == 0,
        }
        if not all(checks.values()):
            raise AssertionError("Timeout postconditions failed: " + json.dumps({"checks": checks, "terminal": terminal, "scene": scene, "mutation_response": mutation_response, "public_status": public_status, "final_state": final_state}, sort_keys=True))
        result = {"status": "PASS", "scenario": "manual_ui_timeout", "request_id": req_id,
                  "approval_status": terminal["status"], "token_consumed": terminal["token_consumed"],
                  "checks": checks, "validation_mode": "non_mutating_saved_evidence_verification"}
        (root / "final_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    if scenario.get("decision") == "cancel":
        status_file = root / "terminal_approval.json"
        if not status_file.exists():
            raise FileNotFoundError("Missing terminal_approval.json in " + str(root))
        terminal = json.loads(status_file.read_text(encoding="utf-8"))
        if terminal.get("status") == "approved":
            raise AssertionError(
                f"Cancellation postconditions failed: Request '{req_id}' has unexpected status 'approved'"
            )
        if terminal.get("status") != "cancelled":
            raise AssertionError(
                f"Cancellation postconditions failed: Request '{req_id}' has status '{terminal.get('status')}', expected 'cancelled'"
            )

        ui_file = root / "ui_interaction_evidence.json"
        if not ui_file.exists():
            raise AssertionError(
                f"Cancellation postconditions failed: Missing UI interaction evidence (no verified human UI cancellation recorded for request '{req_id}')"
            )
        ui_data = json.loads(ui_file.read_text(encoding="utf-8"))
        if ui_data.get("action") != "dialog_cancel":
            raise AssertionError(
                f"Cancellation postconditions failed: UI interaction action was '{ui_data.get('action')}', expected 'dialog_cancel'"
            )
        if ui_data.get("request_id") != req_id:
            raise AssertionError(
                f"Cancellation postconditions failed: UI interaction request_id '{ui_data.get('request_id')}' does not match '{req_id}'"
            )

        response_file = root / "mcp_mutation_response.json"
        if not response_file.exists():
            raise FileNotFoundError("Missing mcp_mutation_response.json in " + str(root))
        mutation_record = json.loads(response_file.read_text(encoding="utf-8"))
        mutation_response = mutation_record.get("payload", mutation_record)
        if not mutation_record.get("isError") and mutation_response.get("status") != "error":
            raise AssertionError(
                f"Cancellation postconditions failed: MCP mutation did not fail closed; returned status '{mutation_response.get('status')}'"
            )

        trace_file = root / "cancel_scene_evidence.json"
        public_status_file = root / "approval_status_mcp.json"
        if not all(path.exists() for path in (trace_file, public_status_file)):
            raise AssertionError("Cancellation postconditions failed: Incomplete cancellation evidence in " + str(root))

        scene = json.loads(trace_file.read_text(encoding="utf-8"))
        public_status = json.loads(public_status_file.read_text(encoding="utf-8"))
        before = json.loads((root / "topology_before.json").read_text(encoding="utf-8"))
        after = json.loads((root / "topology_after_mcp.json").read_text(encoding="utf-8"))
        final_state = json.loads((root / "final_blender_state.json").read_text(encoding="utf-8"))
        checks = {
            "request_id_matches": terminal.get("request_id") == req_id,
            "terminal_cancelled": terminal.get("status") == "cancelled",
            "ui_action_verified": ui_data.get("action") == "dialog_cancel",
            "token_unconsumed": terminal.get("token_consumed") is False,
            "no_approval_token_issued": scene.get("approval_token_present") is False,
            "invalid_consume_rejected": scene.get("invalid_consume_rejected") is True,
            "late_resolve_rejected": scene.get("late_resolve_rejected") is True,
            "cancelled_token_not_consumed": scene.get("token_consumed_after_probe") is False,
            "mcp_mutation_failed_closed": mutation_response.get("status") == "error",
            "mcp_status_cancelled": public_status.get("status") == "cancelled",
            "public_status_has_no_token": "approval_token" not in public_status,
            "mutation_handler_not_invoked": scene.get("edit_mesh_handler_calls") == 0,
            "topology_unchanged": before.get("elements") == after.get("elements"),
            "snapshot_unchanged": before.get("snapshot_id") == after.get("snapshot_id"),
            "state_unchanged": before.get("state_id") == after.get("state_id"),
            "scene_inventory_unchanged": scene.get("objects_before") == scene.get("objects_after"),
            "mesh_inventory_unchanged": scene.get("meshes_before") == scene.get("meshes_after"),
            "material_inventory_unchanged": scene.get("materials_before") == scene.get("materials_after"),
            "target_mesh_state_unchanged": scene.get("target_before") == scene.get("target_after"),
            "final_pending_count_zero": final_state.get("pending_request_count") == 0,
            "bridge_stopped": final_state.get("bridge_running") is False,
            "blender_process_exited": (root / "process_exit.json").exists()
            and json.loads((root / "process_exit.json").read_text(encoding="utf-8")).get("returncode") == 0,
        }
        if not all(checks.values()):
            raise AssertionError("Cancellation postconditions failed: " + json.dumps({"checks": checks, "terminal": terminal, "scene": scene, "mutation_response": mutation_response, "public_status": public_status, "final_state": final_state}, sort_keys=True))
        result = {"status": "PASS", "scenario": "manual_ui_cancel", "request_id": req_id,
                  "approval_status": terminal["status"], "token_consumed": terminal["token_consumed"],
                  "checks": checks, "validation_mode": "non_mutating_saved_evidence_verification"}
        (root / "final_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    status = wait_for_terminal_status_sync(root, req_id, timeout=timeout)

    mutation_file = root / "mutation_evidence.json"
    if not mutation_file.exists():
        raise FileNotFoundError(f"Missing mutation_evidence.json in {root}")
    mutation = json.loads(mutation_file.read_text(encoding="utf-8"))

    pre_file = root / "topology_before.json"
    post_file = root / "topology_after_mcp.json"
    if not pre_file.exists() or not post_file.exists():
        raise FileNotFoundError(f"Missing topology files in {root}")
    pre = json.loads(pre_file.read_text(encoding="utf-8"))
    post = json.loads(post_file.read_text(encoding="utf-8"))

    expected = pre["elements"][0]["co"][2] + 0.01
    actual = post["elements"][0]["co"][2]

    delta_ok = abs(actual - expected) < 1e-7
    mutation_readback_ok = bool(mutation.get("mutation_readback_verified"))
    replay_rejected_ok = bool(mutation.get("replay_rejected"))
    status_approved_ok = (status.get("status") == "approved")
    token_consumed_ok = (status.get("token_consumed") is True)
    req_id_ok = (status.get("request_id") == req_id)
    receipt = mutation.get("receipt", {})
    receipt_ok = (
        receipt.get("transaction_status") == "COMMITTED"
        and receipt.get("verified") is True
        and receipt.get("success") is True
    )

    verified = (
        delta_ok
        and mutation_readback_ok
        and replay_rejected_ok
        and status_approved_ok
        and token_consumed_ok
        and req_id_ok
        and receipt_ok
    )

    if not verified:
        raise AssertionError(
            "Independent postconditions failed: "
            + json.dumps(
                {
                    "pending": pending,
                    "status": status,
                    "mutation": mutation,
                    "delta_ok": delta_ok,
                    "mutation_readback_ok": mutation_readback_ok,
                    "replay_rejected_ok": replay_rejected_ok,
                    "status_approved_ok": status_approved_ok,
                    "token_consumed_ok": token_consumed_ok,
                    "req_id_ok": req_id_ok,
                    "receipt_ok": receipt_ok,
                }
            )
        )

    final_result = {
        "status": "PASS",
        "request_id": req_id,
        "approval_pending_observed": True,
        "approval_status": status["status"],
        "token_consumed": status["token_consumed"],
        "replay_rejected": mutation["replay_rejected"],
        "mutation_verified": True,
        "receipt_transaction_status": receipt.get("transaction_status"),
        "before_vertex_0": pre["elements"][0]["co"],
        "after_vertex_0": post["elements"][0]["co"],
        "validation_mode": "non_mutating_saved_evidence_verification",
    }

    final_result_file = root / "final_result.json"
    final_result_file.write_text(json.dumps(final_result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return final_result


bootstrap = r"""
import bpy, copy, json, os, sys, time, traceback
from pathlib import Path
root=Path(os.environ["UMCP_UI_RUN_ROOT"])
project=Path(os.environ["UMCP_PROJECT"])
sys.path.insert(0,str(project))
import blender_addon.universal_mcp as addon
addon.register()
from blender_addon.universal_mcp.bridge.main_thread_queue import get_main_thread_queue
from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
from blender_addon.universal_mcp.bridge.component_edit import handle_edit_mesh
from blender_addon.universal_mcp.bridge.mesh_atomic import snapshot
from blender_addon.universal_mcp.operators import get_server_instance, UMCP_OT_ResolveApproval, UMCP_OT_ApprovalDialog
def write(name,value):
    (root/name).write_text(json.dumps(value,indent=2,sort_keys=True,default=str),encoding="utf-8")
def append_trace(name,value):
    with (root/name).open("a",encoding="utf-8") as f:
        f.write(json.dumps(value,sort_keys=True,default=str)+"\n")
orig_resolve_execute = UMCP_OT_ResolveApproval.execute
def tracked_resolve_execute(self, context):
    rec = {
        "operator": "umcp.resolve_approval",
        "request_id": self.request_id,
        "action": self.action,
        "time": time.time(),
    }
    append_trace("ui_interaction_trace.jsonl", rec)
    write("ui_interaction_evidence.json", rec)
    return orig_resolve_execute(self, context)
UMCP_OT_ResolveApproval.execute = tracked_resolve_execute

orig_dialog_execute = UMCP_OT_ApprovalDialog.execute
def tracked_dialog_execute(self, context):
    rec = {
        "operator": "umcp.approval_dialog",
        "request_id": self.request_id,
        "action": "dialog_ok_approve",
        "time": time.time(),
    }
    append_trace("ui_interaction_trace.jsonl", rec)
    write("ui_interaction_evidence.json", rec)
    return orig_dialog_execute(self, context)
UMCP_OT_ApprovalDialog.execute = tracked_dialog_execute

orig_dialog_cancel = UMCP_OT_ApprovalDialog.cancel
def tracked_dialog_cancel(self, context):
    rec = {
        "operator": "umcp.approval_dialog",
        "request_id": self.request_id,
        "action": "dialog_cancel",
        "time": time.time(),
    }
    append_trace("ui_interaction_trace.jsonl", rec)
    registry = get_approval_registry()
    req = registry.get_request_for_status(self.request_id) if hasattr(registry, "get_request_for_status") else None
    if not (req and getattr(req, "status", None) in {"approved", "denied"}):
        write("ui_interaction_evidence.json", rec)
    return orig_dialog_cancel(self, context)
UMCP_OT_ApprovalDialog.cancel = tracked_dialog_cancel
def state(obj):
    return {"object_name":obj.name,"mesh_name":obj.data.name,"mesh_pointer":obj.data.as_pointer(),
            "vertices":[list(v.co) for v in obj.data.vertices],
            "edges":[list(e.vertices) for e in obj.data.edges],
            "faces":[list(p.vertices) for p in obj.data.polygons]}
scene=bpy.context.scene
port=int(os.environ["UMCP_UI_TEST_PORT"])
scene.umcp_bridge_port=port
scene.umcp_require_scene_mutation_approval=True
scene.umcp_status_message="Isolated UI approval acceptance"
name=os.environ["UMCP_UI_TEST_OBJECT"]
decision=os.environ.get("UMCP_UI_TEST_DECISION","approve")
mesh=bpy.data.meshes.new(name+"Data")
mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[(0,1),(1,2),(2,3),(3,0)],[(0,1,2,3)])
mesh.update()
obj=bpy.data.objects.new(name,mesh)
scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active=obj
obj.select_set(True)
initial=state(obj)
objects_before=sorted(bpy.data.objects.keys())
meshes_before=sorted(bpy.data.meshes.keys())
materials_before=sorted(bpy.data.materials.keys())
queue=get_main_thread_queue()
original=queue._handlers["edit_mesh"]
registry=get_approval_registry()
handler_calls=0
if registry.get_pending_requests():
    raise RuntimeError("Isolated approval registry was unexpectedly nonempty before test")
write("baseline.json",{"pid":os.getpid(),"blender":bpy.app.version_string,
      "background":bpy.app.background,"filepath":bpy.data.filepath,"port":port,
      "require_approval":bool(scene.umcp_require_scene_mutation_approval),
      "objects":sorted(bpy.data.objects.keys()),"target_state":initial,
      "initial_pending_count":0,"test_object":name})
def tracked(bpy_module=None,params=None):
    global handler_calls
    handler_calls+=1
    captured=copy.deepcopy(params or {})
    before=state(obj)
    result=original(bpy_module=bpy_module,params=params)
    after=state(obj)
    replay_error=None
    try:
        original(bpy_module=bpy_module,params=captured)
    except PermissionError as exc:
        replay_error=str(exc)
    else:
        raise AssertionError("Consumed edit_mesh token replay was accepted")
    status=registry.inspect_request_status(captured.get("request_id"))
    safe_term={k:status.get(k) for k in ("request_id","status","tool_name","arg_hash","expires_at","remaining_seconds","token_consumed")}
    write("terminal_approval.json",{"observed_at":time.time(),**safe_term})
    evidence={"request_id":captured.get("request_id"),"before":before,"after":after,
      "expected_vertex_0_z":before["vertices"][0][2]+0.01,
      "mutation_readback_verified":abs(after["vertices"][0][2]-(before["vertices"][0][2]+0.01))<1e-7,
      "replay_rejected":"Replay rejected" in replay_error if replay_error else False,
      "replay_error":replay_error,"approval_status":status,
      "object_inventory":sorted(bpy.data.objects.keys()),"mesh_inventory":sorted(bpy.data.meshes.keys()),
      "receipt":{"success":result.get("success"),"verified":result.get("verified"),
                 "transaction_status":result.get("transaction_status")}}
    write("mutation_evidence.json",evidence)
    return result
queue.register_handler("edit_mesh",tracked)
last_status={}
def observe():
    try:
        requests=[r for r in list(registry._requests.values()) if r.tool_name=="edit_mesh" and r.params.get("name")==name]
        if requests:
            req=requests[-1]
            status=registry.inspect_request_status(req.request_id)
            safe={k:status.get(k) for k in ("request_id","status","tool_name","arg_hash","expires_at","remaining_seconds","token_consumed")}
            if safe != last_status:
                with (root/"approval_status_trace.jsonl").open("a",encoding="utf-8") as f:
                    f.write(json.dumps({"time":time.time(),**safe},sort_keys=True)+"\n")
                last_status.clear(); last_status.update(safe)
            if status.get("status")=="pending" and not (root/"pending.json").exists():
                write("pending.json",{"observed_at":time.time(),**safe})
            if status.get("status") in {"approved","denied","cancelled","expired"}:
                write("terminal_approval.json",{"observed_at":time.time(),**safe})
                if status.get("status")=="denied" and decision=="deny" and not (root/"denial_scene_evidence.json").exists():
                    req_obj=registry.get_request_for_status(req.request_id)
                    invalid_ok=False
                    invalid_message=""
                    try:
                        invalid_ok,invalid_message=registry.consume_approval(req.request_id,"invalid-test-token","edit_mesh",req.params)
                    except Exception as exc:
                        invalid_message=type(exc).__name__+": "+str(exc)
                    after_state=state(obj)
                    write("denial_scene_evidence.json",{
                      "request_id":req.request_id,"approval_token_present":bool(getattr(req_obj,"approval_token",None)),
                      "invalid_consume_rejected":invalid_ok is False and "expected 'approved'" in invalid_message,
                      "token_consumed_after_probe":bool(getattr(req_obj,"executed",False)),
                      "objects_before":objects_before,"objects_after":sorted(bpy.data.objects.keys()),
                      "meshes_before":meshes_before,"meshes_after":sorted(bpy.data.meshes.keys()),
                      "materials_before":materials_before,"materials_after":sorted(bpy.data.materials.keys()),
                      "target_before":initial,"target_after":after_state,"edit_mesh_handler_calls":handler_calls,
                      "invalid_consume_error":invalid_message})
                if status.get("status")=="expired" and decision=="timeout" and not (root/"timeout_scene_evidence.json").exists():
                    req_obj=registry.get_request_for_status(req.request_id)
                    invalid_ok=False
                    invalid_message=""
                    try:
                        invalid_ok,invalid_message=registry.consume_approval(req.request_id,"invalid-test-token","edit_mesh",req.params)
                    except Exception as exc:
                        invalid_message=type(exc).__name__+": "+str(exc)
                    late_ok=False
                    late_message=""
                    try:
                        late_ok,late_message=registry.resolve_request(req.request_id,"approved")
                    except Exception as exc:
                        late_message=type(exc).__name__+": "+str(exc)
                    after_state=state(obj)
                    write("timeout_scene_evidence.json",{
                      "request_id":req.request_id,"approval_token_present":bool(getattr(req_obj,"approval_token",None)),
                      "invalid_consume_rejected":invalid_ok is False and "expected 'approved'" in invalid_message,
                      "late_resolve_rejected":late_ok is False and ("Approval expired" in late_message or "already resolved as 'expired'" in late_message),
                      "token_consumed_after_probe":bool(getattr(req_obj,"executed",False)),
                      "objects_before":objects_before,"objects_after":sorted(bpy.data.objects.keys()),
                      "meshes_before":meshes_before,"meshes_after":sorted(bpy.data.meshes.keys()),
                      "materials_before":materials_before,"materials_after":sorted(bpy.data.materials.keys()),
                      "target_before":initial,"target_after":after_state,"edit_mesh_handler_calls":handler_calls,
                      "invalid_consume_error":invalid_message,"late_resolve_error":late_message})
                if status.get("status")=="cancelled" and decision=="cancel" and not (root/"cancel_scene_evidence.json").exists():
                    req_obj=registry.get_request_for_status(req.request_id)
                    invalid_ok=False
                    invalid_message=""
                    try:
                        invalid_ok,invalid_message=registry.consume_approval(req.request_id,"invalid-test-token","edit_mesh",req.params)
                    except Exception as exc:
                        invalid_message=type(exc).__name__+": "+str(exc)
                    late_ok=False
                    late_message=""
                    try:
                        late_ok,late_message=registry.resolve_request(req.request_id,"approved")
                    except Exception as exc:
                        late_message=type(exc).__name__+": "+str(exc)
                    after_state=state(obj)
                    write("cancel_scene_evidence.json",{
                      "request_id":req.request_id,"approval_token_present":bool(getattr(req_obj,"approval_token",None)),
                      "invalid_consume_rejected":invalid_ok is False and "expected 'approved'" in invalid_message,
                      "late_resolve_rejected":late_ok is False and ("already resolved as 'cancelled'" in late_message or "already resolved" in late_message),
                      "token_consumed_after_probe":bool(getattr(req_obj,"executed",False)),
                      "objects_before":objects_before,"objects_after":sorted(bpy.data.objects.keys()),
                      "meshes_before":meshes_before,"meshes_after":sorted(bpy.data.meshes.keys()),
                      "materials_before":materials_before,"materials_after":sorted(bpy.data.materials.keys()),
                      "target_before":initial,"target_after":after_state,"edit_mesh_handler_calls":handler_calls,
                      "invalid_consume_error":invalid_message,"late_resolve_error":late_message})
        if (root/"stop").exists():
            if registry.get_pending_requests():
                write("cleanup_blocked_pending.json",{"pending_count":len(registry.get_pending_requests())})
                return 0.25
            pending_count=len(registry.get_pending_requests())
            server=get_server_instance(port)
            if server.running:
                server.stop()
            write("final_blender_state.json",{"pid":os.getpid(),"filepath":bpy.data.filepath,
              "objects":sorted(bpy.data.objects.keys()),"pending_request_count":pending_count,
              "meshes":sorted(bpy.data.meshes.keys()),"materials":sorted(bpy.data.materials.keys()),
              "target_state":state(obj),"bridge_running":bool(server.running)})
            bpy.ops.wm.quit_blender()
            return None
    except Exception:
        (root/"observer_error.txt").write_text(traceback.format_exc(),encoding="utf-8")
    return 0.1
def start_bridge():
    try:
        if bpy.app.background:
            return None
        wm=bpy.context.window_manager
        server=get_server_instance(port)
        if not server.running:
            outcome=bpy.ops.umcp.start_bridge()
            if "FINISHED" not in outcome:
                raise RuntimeError("Normal Start Bridge operator failed: "+repr(outcome))
        write("ready.json",{"pid":os.getpid(),"blender":bpy.app.version_string,
          "background":bpy.app.background,"filepath":bpy.data.filepath,"port":port,
          "require_approval":bool(scene.umcp_require_scene_mutation_approval),
          "bridge_running":server.running,"objects":sorted(bpy.data.objects.keys()),
          "test_object":name,"source_root":str(project)})
        return None
    except Exception:
        write("startup_error.json",{"traceback":traceback.format_exc()})
        return None
bpy.app.timers.register(observe,first_interval=0.1,persistent=True)
bpy.app.timers.register(start_bridge,first_interval=1.5)
"""


def main():
    parser = argparse.ArgumentParser(description="Isolated UI approval E2E harness controller")
    parser.add_argument(
        "--validate-saved",
        nargs="?",
        const="",
        default=None,
        help="Validate saved test evidence without performing scene mutation. Optionally pass run root path.",
    )
    parser.add_argument("--decision", choices=("approve", "deny", "timeout", "cancel"), default="approve",
                        help="Human decision to test in the disposable Blender approval dialog.")
    args = parser.parse_args()

    if args.validate_saved is not None:
        target_root_str = args.validate_saved.strip()
        if not target_root_str:
            target_root_str = os.environ.get(
                "UMCP_UI_RUN_ROOT",
                r"C:\Users\Administrator\AppData\Local\Temp\UMCP-UI-E2E-f02ffae136d84b7db27eb5b62f7bf220",
            )
        root = Path(target_root_str)
        if not root.exists():
            raise FileNotFoundError(f"Saved run directory not found: {root}")
        print(f"VALIDATING_SAVED_EVIDENCE root={root}", flush=True)
        res = verify_controller_postconditions(root)
        print("CONTROLLER_STATUS_WAIT_VALIDATED request_id=" + res["request_id"] +
              " scenario=" + res.get("scenario", "approval") +
              " checks=" + json.dumps(res.get("checks", {}), sort_keys=True) +
              " status=PASS", flush=True)
        return

    # Normal live execution
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    if "UMCP_UI_RUN_ROOT" not in os.environ:
        run_root = Path(tempfile.mkdtemp(prefix="UMCP-UI-E2E-"))
        os.environ["UMCP_UI_RUN_ROOT"] = str(run_root)
    ROOT = Path(os.environ["UMCP_UI_RUN_ROOT"])
    write(ROOT / "scenario.json", {"decision": args.decision, "approval_mode": "manual_blender_ui"})

    boot = ROOT / "bootstrap.py"
    boot.write_text(bootstrap, encoding="utf-8")
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    if port == 9877:
        raise RuntimeError("Refusing production port")
    object_name = "UMCP_UI_EditMesh_" + time.strftime("%Y%m%d_%H%M%S")
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(PROJECT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "UMCP_PROJECT": str(PROJECT),
            "UMCP_UI_RUN_ROOT": str(ROOT),
            "UMCP_UI_TEST_PORT": str(port),
            "UMCP_BRIDGE_PORT": str(port),
            "UMCP_UI_TEST_OBJECT": object_name,
            "UMCP_UI_TEST_DECISION": args.decision,
        }
    )
    for key in ("CONFIG", "SCRIPTS", "EXTENSIONS", "DATAFILES", "RESOURCES"):
        folder = ROOT / key.lower()
        folder.mkdir(exist_ok=True)
        env["BLENDER_USER_" + key] = str(folder)
    private_temp = ROOT / "temp"
    private_temp.mkdir(exist_ok=True)
    env["TEMP"] = str(private_temp)
    env["TMP"] = str(private_temp)
    env["TMPDIR"] = str(private_temp)
    env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
    log = (ROOT / "blender.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(BLENDER), "--factory-startup", "--disable-autoexec", "--python", str(boot)],
        cwd=str(PROJECT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    write(
        ROOT / "launch.json",
        {
            "blender_pid": process.pid,
            "port": port,
            "object_name": object_name,
            "blender_executable": str(BLENDER),
            "profile_root": str(ROOT),
            "project": str(PROJECT),
        },
    )
    print("ISOLATED_ROOT=" + str(ROOT), flush=True)
    print("BLENDER_PID=" + str(process.pid) + " ISOLATED_PORT=" + str(port), flush=True)
    try:
        deadline = time.monotonic() + 90
        while not (ROOT / "ready.json").exists():
            if (ROOT / "startup_error.json").exists() or process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Isolated interactive Blender did not become ready. See " + str(ROOT))
            time.sleep(0.1)
        ready = json.loads((ROOT / "ready.json").read_text(encoding="utf-8"))
        if (
            ready["pid"] != process.pid
            or ready["port"] != port
            or not ready["require_approval"]
            or ready["background"]
            or ready["filepath"]
        ):
            raise RuntimeError("Blender isolation/readiness assertion failed: " + json.dumps(ready))

        async def run():
            stdio_env = dict(env)
            stdio_env.pop("UMCP_LOCAL_TEST_AUTOAPPROVE", None)
            bridge_timeout = "15" if args.decision == "timeout" else "300"
            if args.decision == "timeout":
                stdio_env["UMCP_APPROVAL_PENDING_TTL"] = "10"
            params = StdioServerParameters(
                command=sys.executable,
                args=[
                    "-B",
                    "-m",
                    "mcp_service.app",
                    "--transport",
                    "stdio",
                    "--bridge-host",
                    "127.0.0.1",
                    "--bridge-port",
                    str(port),
                    "--bridge-timeout",
                    bridge_timeout,
                    "--approval-mode",
                    "blender",
                ],
                env=stdio_env,
                cwd=str(PROJECT),
            )
            with (ROOT / "mcp_service_stderr.log").open("w", encoding="utf-8") as errlog:
                async with stdio_client(params, errlog=errlog) as streams:
                    async with ClientSession(*streams) as session:
                        init = await session.initialize()
                        tools = await session.list_tools()
                        names = {x.name for x in tools.tools}
                        if not {"edit_mesh", "inspect_scene_data"} <= names:
                            raise RuntimeError("Required MCP tools missing: " + repr(sorted(names)))
                        pre = topology(
                            await session.call_tool(
                                "inspect_scene_data",
                                arguments={
                                    "category": "mesh_topology",
                                    "target_name": object_name,
                                    "element_domain": "vertices",
                                    "limit": 32,
                                },
                            )
                        )
                        write(
                            ROOT / "mcp_catalog.json",
                            {"server": init.serverInfo.model_dump(), "count": len(names), "required_present": True},
                        )
                        write(ROOT / "topology_before.json", pre)
                        op = {"action": "move_vertices", "vertices": [0], "delta": [0, 0, 0.01]}
                        args_call = {"name": object_name, "expected_snapshot_id": pre.get("snapshot_id"), "operations": [op]}
                        task = asyncio.create_task(session.call_tool("edit_mesh", arguments=args_call))
                        deadline_pending = time.monotonic() + 310
                        while not (ROOT / "pending.json").exists():
                            if task.done():
                                unexpected = task.result()
                                raise RuntimeError(
                                    "MCP mutation returned before a pending approval was observed: "
                                    + str(unexpected.content[0].text if unexpected.content else unexpected)
                                )
                            if time.monotonic() > deadline_pending:
                                raise TimeoutError("No pending approval was observed in the isolated Blender registry")
                            await asyncio.sleep(0.1)
                        pending = json.loads((ROOT / "pending.json").read_text(encoding="utf-8"))
                        if args.decision == "timeout":
                            dialog_msg = "Wait for approval TTL expiry (no user interaction required)."
                        elif args.decision == "cancel":
                            dialog_msg = "Please press Esc or click Cancel in the visible disposable Blender dialog."
                        elif args.decision == "deny":
                            dialog_msg = "Please review and deny manually in the visible disposable Blender dialog."
                        else:
                            dialog_msg = "Please review and approve manually in the visible disposable Blender dialog."
                        write(
                            ROOT / "human_action_required.json",
                            {
                                "request_id": pending["request_id"],
                                "status": pending["status"],
                                "target": object_name,
                                "port": port,
                                "dialog": dialog_msg,
                                "decision": args.decision,
                            },
                        )
                        print(
                            "HUMAN_APPROVAL_REQUIRED request_id="
                            + pending["request_id"]
                            + " target="
                            + object_name
                            + " decision="
                            + args.decision
                            + " status="
                            + pending["status"]
                            + " port="
                            + str(port),
                            flush=True,
                        )
                        if args.decision == "timeout":
                            terminal_status = await wait_for_verified_timeout_async(
                                ROOT, pending["request_id"], timeout=25.0, poll_interval=0.05, mutation_task=task
                            )
                            response = await task
                            payload = tool_json(response)
                            write(ROOT / "mcp_mutation_response.json", {"isError": bool(response.isError), "payload": payload})
                            if not response.isError and payload.get("status") != "error":
                                raise RuntimeError("Timed out MCP mutation did not fail closed: " + json.dumps(payload))
                            status_response = await session.call_tool("check_approval_status", arguments={"request_id": pending["request_id"]})
                            status_envelope = tool_json(status_response)
                            public_status = status_envelope.get("result", status_envelope)
                            write(ROOT / "approval_status_mcp.json", public_status)
                            post = topology(await session.call_tool("inspect_scene_data", arguments={
                                "category": "mesh_topology", "target_name": object_name,
                                "element_domain": "vertices", "limit": 32,
                            }))
                            write(ROOT / "topology_after_mcp.json", post)
                            if public_status.get("status") != "expired":
                                raise AssertionError("MCP status did not report expired: " + json.dumps(status_envelope))
                            write(
                                ROOT / "final_result.json",
                                {
                                    "status": "PASS",
                                    "scenario": "manual_ui_timeout",
                                    "service_version": init.serverInfo.version,
                                    "tool_count": len(names),
                                    "request_id": pending["request_id"],
                                    "approval_pending_observed": True,
                                    "approval_status": "expired",
                                    "token_consumed": False,
                                    "mutation_failed_closed": True,
                                    "isolated_port": port,
                                    "blender_pid": process.pid,
                                },
                            )
                            print(
                                "TIMEOUT_VERIFIED request_id="
                                + pending["request_id"]
                                + " status=expired mutation_error=true",
                                flush=True,
                            )
                            return
                        if args.decision == "cancel":
                            terminal_status, ui_action = await wait_for_verified_cancellation_async(
                                ROOT, pending["request_id"], timeout=300.0, poll_interval=0.05, mutation_task=task
                            )
                            response = await task
                            payload = tool_json(response)
                            write(ROOT / "mcp_mutation_response.json", {"isError": bool(response.isError), "payload": payload})
                            if not response.isError and payload.get("status") != "error":
                                raise RuntimeError("Cancelled MCP mutation did not fail closed: " + json.dumps(payload))
                            status_response = await session.call_tool("check_approval_status", arguments={"request_id": pending["request_id"]})
                            status_envelope = tool_json(status_response)
                            public_status = status_envelope.get("result", status_envelope)
                            write(ROOT / "approval_status_mcp.json", public_status)
                            post = topology(await session.call_tool("inspect_scene_data", arguments={
                                "category": "mesh_topology", "target_name": object_name,
                                "element_domain": "vertices", "limit": 32,
                            }))
                            write(ROOT / "topology_after_mcp.json", post)
                            if public_status.get("status") != "cancelled":
                                raise AssertionError("MCP status did not report cancelled: " + json.dumps(status_envelope))
                            write(
                                ROOT / "final_result.json",
                                {
                                    "status": "PASS",
                                    "scenario": "manual_ui_cancel",
                                    "service_version": init.serverInfo.version,
                                    "tool_count": len(names),
                                    "request_id": pending["request_id"],
                                    "approval_pending_observed": True,
                                    "approval_status": "cancelled",
                                    "token_consumed": False,
                                    "ui_action": ui_action.get("action"),
                                    "mutation_failed_closed": True,
                                    "isolated_port": port,
                                    "blender_pid": process.pid,
                                },
                            )
                            print(
                                "CANCELLATION_VERIFIED request_id="
                                + pending["request_id"]
                                + " status=cancelled mutation_error=true ui_action=dialog_cancel",
                                flush=True,
                            )
                            return
                        if args.decision == "deny":
                            # 1. Wait for verified denial action through the real Blender approval UI and definitive 'denied' terminal status
                            terminal_status, ui_action = await wait_for_verified_denial_async(
                                ROOT, pending["request_id"], timeout=300.0, poll_interval=0.05, mutation_task=task
                            )
                            # 2. Await mutation response (which completes because mcp_service received 'denied' from Blender)
                            response = await task
                            payload = tool_json(response)
                            write(ROOT / "mcp_mutation_response.json", {"isError": bool(response.isError), "payload": payload})
                            if not response.isError and payload.get("status") != "error":
                                raise RuntimeError("Denied MCP mutation did not fail closed: " + json.dumps(payload))
                            status_response = await session.call_tool("check_approval_status", arguments={"request_id": pending["request_id"]})
                            status_envelope = tool_json(status_response)
                            public_status = status_envelope.get("result", status_envelope)
                            write(ROOT / "approval_status_mcp.json", public_status)
                            post = topology(await session.call_tool("inspect_scene_data", arguments={
                                "category": "mesh_topology", "target_name": object_name,
                                "element_domain": "vertices", "limit": 32,
                            }))
                            write(ROOT / "topology_after_mcp.json", post)
                            if public_status.get("status") != "denied":
                                raise AssertionError("MCP status did not report denial: " + json.dumps(status_envelope))
                            write(
                                ROOT / "final_result.json",
                                {
                                    "status": "PASS",
                                    "scenario": "manual_ui_denial",
                                    "service_version": init.serverInfo.version,
                                    "tool_count": len(names),
                                    "request_id": pending["request_id"],
                                    "approval_pending_observed": True,
                                    "approval_status": "denied",
                                    "token_consumed": False,
                                    "ui_action": ui_action.get("action"),
                                    "mutation_failed_closed": True,
                                    "isolated_port": port,
                                    "blender_pid": process.pid,
                                },
                            )
                            print(
                                "DENIAL_VERIFIED request_id="
                                + pending["request_id"]
                                + " status=denied mutation_error=true ui_action=deny",
                                flush=True,
                            )
                            return
                        response = await task
                        payload = tool_json(response)
                        if response.isError:
                            raise RuntimeError("MCP edit_mesh returned isError: " + json.dumps(payload))
                        if payload.get("status") != "success":
                            raise RuntimeError("MCP edit_mesh did not succeed: " + json.dumps(payload))
                        write(ROOT / "mcp_mutation_response.json", {"isError": bool(response.isError), "payload": payload})
                        post = topology(
                            await session.call_tool(
                                "inspect_scene_data",
                                arguments={
                                    "category": "mesh_topology",
                                    "target_name": object_name,
                                    "element_domain": "vertices",
                                    "limit": 32,
                                },
                            )
                        )
                        write(ROOT / "topology_after_mcp.json", post)
                        mutation = json.loads((ROOT / "mutation_evidence.json").read_text(encoding="utf-8"))
                        # Bounded poll for definitive terminal approval status (token_consumed == True)
                        status = await wait_for_terminal_status_async(ROOT, pending["request_id"], timeout=15.0)
                        expected = pre["elements"][0]["co"][2] + 0.01
                        verified = (
                            abs(post["elements"][0]["co"][2] - expected) < 1e-7
                            and mutation["mutation_readback_verified"]
                            and mutation["replay_rejected"]
                            and status.get("status") == "approved"
                            and status.get("token_consumed") is True
                            and status.get("request_id") == pending["request_id"]
                        )
                        if not verified:
                            raise AssertionError(
                                "Independent postconditions failed: "
                                + json.dumps(
                                    {
                                        "pending": pending,
                                        "status": status,
                                        "mutation": mutation,
                                        "before": pre["elements"][0],
                                        "after": post["elements"][0],
                                    }
                                )
                            )
                        write(
                            ROOT / "final_result.json",
                            {
                                "status": "PASS",
                                "service_version": init.serverInfo.version,
                                "tool_count": len(names),
                                "request_id": pending["request_id"],
                                "approval_pending_observed": True,
                                "approval_status": status["status"],
                                "token_consumed": status["token_consumed"],
                                "replay_rejected": mutation["replay_rejected"],
                                "mutation_verified": True,
                                "before_vertex_0": pre["elements"][0]["co"],
                                "after_vertex_0": post["elements"][0]["co"],
                                "isolated_port": port,
                                "blender_pid": process.pid,
                            },
                        )
                        print(
                            "MUTATION_VERIFIED request_id="
                            + pending["request_id"]
                            + " token_consumed=true replay_rejected=true",
                            flush=True,
                        )

        asyncio.run(run())
    finally:
        (ROOT / "stop").touch()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        write(ROOT / "process_exit.json", {"returncode": process.returncode, "pid": process.pid})
        log.close()
        if (ROOT / "final_blender_state.json").exists():
            print("CLEANUP_VERIFIED " + (ROOT / "final_blender_state.json").read_text(encoding="utf-8"), flush=True)
        print("EVIDENCE_ROOT=" + str(ROOT), flush=True)


if __name__ == "__main__":
    main()
