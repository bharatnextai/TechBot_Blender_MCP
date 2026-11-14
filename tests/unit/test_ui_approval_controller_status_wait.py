import asyncio
import json
import threading
import time
from pathlib import Path
import pytest

from tests.blender.run_ui_test import (
    wait_for_terminal_status_sync,
    wait_for_terminal_status_async,
    wait_for_verified_denial_sync,
    wait_for_verified_denial_async,
    wait_for_verified_cancellation_async,
    verify_controller_postconditions,
)


def test_status_wait_resolves_when_token_consumed_updated_concurrently(tmp_path: Path):
    """
    Simulates the exact observer/controller timing race:
    terminal_approval.json is initially written with token_consumed=False when approved,
    then updated ~60ms later to token_consumed=True once the mutation consumes the token.
    The controller must not assert immediately; it must wait and resolve once token_consumed is True.
    """
    req_id = "test_req_race_01"
    terminal_file = tmp_path / "terminal_approval.json"

    initial_record = {
        "request_id": req_id,
        "status": "approved",
        "token_consumed": False,
        "tool_name": "edit_mesh",
    }
    terminal_file.write_text(json.dumps(initial_record), encoding="utf-8")

    def delayed_consumption():
        time.sleep(0.06)
        updated_record = dict(initial_record)
        updated_record["token_consumed"] = True
        terminal_file.write_text(json.dumps(updated_record), encoding="utf-8")

    writer_thread = threading.Thread(target=delayed_consumption)
    start_time = time.monotonic()
    writer_thread.start()

    res = wait_for_terminal_status_sync(tmp_path, req_id, timeout=2.0, poll_interval=0.01)
    writer_thread.join()
    elapsed = time.monotonic() - start_time

    assert res["status"] == "approved"
    assert res["token_consumed"] is True
    assert elapsed >= 0.05, f"Expected polling across the delay, elapsed: {elapsed:.3f}s"


def test_status_wait_resolves_when_token_consumed_updated_concurrently_async(tmp_path: Path):
    """
    Validates asynchronous status-wait across the same race condition.
    """
    req_id = "test_req_race_02"
    terminal_file = tmp_path / "terminal_approval.json"

    initial_record = {
        "request_id": req_id,
        "status": "approved",
        "token_consumed": False,
        "tool_name": "edit_mesh",
    }
    terminal_file.write_text(json.dumps(initial_record), encoding="utf-8")

    async def scenario():
        async def delayed_consumption():
            await asyncio.sleep(0.06)
            updated_record = dict(initial_record)
            updated_record["token_consumed"] = True
            terminal_file.write_text(json.dumps(updated_record), encoding="utf-8")

        task = asyncio.create_task(delayed_consumption())
        res = await wait_for_terminal_status_async(tmp_path, req_id, timeout=2.0, poll_interval=0.01)
        await task
        return res

    res = asyncio.run(scenario())
    assert res["status"] == "approved"
    assert res["token_consumed"] is True


@pytest.mark.parametrize("terminal_state", ["denied", "cancelled", "expired"])
def test_status_wait_immediate_on_non_approved_terminal_states(tmp_path: Path, terminal_state: str):
    """
    Terminal states other than 'approved' are immediately definitive without requiring token_consumed=True.
    """
    req_id = f"test_req_{terminal_state}"
    terminal_file = tmp_path / "terminal_approval.json"
    record = {
        "request_id": req_id,
        "status": terminal_state,
        "token_consumed": False,
        "tool_name": "edit_mesh",
    }
    terminal_file.write_text(json.dumps(record), encoding="utf-8")

    start_time = time.monotonic()
    res = wait_for_terminal_status_sync(tmp_path, req_id, timeout=2.0, poll_interval=0.01)
    elapsed = time.monotonic() - start_time

    assert res["status"] == terminal_state
    assert res["token_consumed"] is False
    assert elapsed < 0.2, f"Should resolve immediately, elapsed: {elapsed:.3f}s"


def test_status_wait_ignores_mismatched_request_id_until_target_arrives(tmp_path: Path):
    """
    If a stale or different request ID is in the file, status wait must not return until the target arrives.
    """
    target_req = "target_req_999"
    stale_req = "stale_req_000"
    terminal_file = tmp_path / "terminal_approval.json"

    terminal_file.write_text(
        json.dumps({"request_id": stale_req, "status": "approved", "token_consumed": True}),
        encoding="utf-8",
    )

    def write_target():
        time.sleep(0.05)
        terminal_file.write_text(
            json.dumps({"request_id": target_req, "status": "approved", "token_consumed": True}),
            encoding="utf-8",
        )

    t = threading.Thread(target=write_target)
    t.start()
    res = wait_for_terminal_status_sync(tmp_path, target_req, timeout=2.0, poll_interval=0.01)
    t.join()

    assert res["request_id"] == target_req
    assert res["token_consumed"] is True


def test_status_wait_handles_partial_or_corrupt_json_during_concurrent_writes(tmp_path: Path):
    """
    Handles transient json decode errors caused by non-atomic file writes.
    """
    req_id = "test_req_transient_io"
    terminal_file = tmp_path / "terminal_approval.json"

    # Write corrupt JSON
    terminal_file.write_text("{\"request_id\": \"test_req_transient_io\", \"status\": ", encoding="utf-8")

    def fix_file():
        time.sleep(0.04)
        terminal_file.write_text(
            json.dumps({"request_id": req_id, "status": "approved", "token_consumed": True}),
            encoding="utf-8",
        )

    t = threading.Thread(target=fix_file)
    t.start()
    res = wait_for_terminal_status_sync(tmp_path, req_id, timeout=2.0, poll_interval=0.01)
    t.join()

    assert res["request_id"] == req_id
    assert res["token_consumed"] is True


def test_status_wait_bounded_timeout_returns_last_record(tmp_path: Path):
    """
    When token_consumed never becomes True within the timeout, the last observed record is returned
    so downstream assertions can generate clear failure diagnostics.
    """
    req_id = "test_req_timeout"
    terminal_file = tmp_path / "terminal_approval.json"
    record = {"request_id": req_id, "status": "approved", "token_consumed": False}
    terminal_file.write_text(json.dumps(record), encoding="utf-8")

    start_time = time.monotonic()
    res = wait_for_terminal_status_sync(tmp_path, req_id, timeout=0.1, poll_interval=0.02)
    elapsed = time.monotonic() - start_time

    assert res["request_id"] == req_id
    assert res["status"] == "approved"
    assert res["token_consumed"] is False
    assert 0.08 <= elapsed <= 0.35


def test_verify_controller_postconditions_against_saved_evidence():
    """
    Validates controller postconditions against the preserved saved run in Temp.
    No scene mutations, no live Blender instances, no port 9877 access.
    """
    saved_root = Path(r"C:\Users\Administrator\AppData\Local\Temp\UMCP-UI-E2E-f02ffae136d84b7db27eb5b62f7bf220")
    if not saved_root.exists():
        pytest.skip(f"Saved run directory {saved_root} not found on host")

    result = verify_controller_postconditions(saved_root, timeout=5.0)

    assert result["status"] == "PASS"
    assert result["request_id"] == "00f14ce2afbfa931"
    assert result["approval_status"] == "approved"
    assert result["token_consumed"] is True
    assert result["replay_rejected"] is True
    assert result["mutation_verified"] is True
    assert result["receipt_transaction_status"] == "COMMITTED"
    assert (saved_root / "final_result.json").exists()


def test_verified_denial_succeeds_when_denied_and_ui_action_verified(tmp_path: Path):
    """
    Denial wait succeeds when terminal status is 'denied' and UI interaction evidence
    confirms action 'deny' from the real approval UI.
    """
    req_id = "test_req_deny_success"
    term_file = tmp_path / "terminal_approval.json"
    ui_file = tmp_path / "ui_interaction_evidence.json"

    term_file.write_text(
        json.dumps({"request_id": req_id, "status": "denied", "token_consumed": False, "tool_name": "edit_mesh"}),
        encoding="utf-8",
    )
    ui_file.write_text(
        json.dumps({"request_id": req_id, "operator": "umcp.resolve_approval", "action": "deny", "time": time.time()}),
        encoding="utf-8",
    )

    term, ui = wait_for_verified_denial_sync(tmp_path, req_id, timeout=1.0, poll_interval=0.01)
    assert term["status"] == "denied"
    assert term["token_consumed"] is False
    assert ui["action"] == "deny"
    assert ui["request_id"] == req_id


def test_verified_denial_fails_closed_on_unexpected_approval(tmp_path: Path):
    """
    In the denial scenario, if the human or UI triggers 'approved', the harness must
    fail closed immediately instead of evaluating mutation or claiming denial success.
    """
    req_id = "test_req_unexpected_approve"
    term_file = tmp_path / "terminal_approval.json"
    term_file.write_text(
        json.dumps({"request_id": req_id, "status": "approved", "token_consumed": False, "tool_name": "edit_mesh"}),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError) as exc_info:
        wait_for_verified_denial_sync(tmp_path, req_id, timeout=1.0, poll_interval=0.01)

    assert "unexpectedly approved" in str(exc_info.value).lower()


def test_verified_denial_fails_closed_on_missing_or_invalid_ui_action(tmp_path: Path):
    """
    If terminal status is 'denied' but UI interaction shows an action other than 'deny'
    (e.g. dialog_ok_approve or dialog_cancel), the harness must fail closed.
    """
    req_id = "test_req_invalid_ui_action"
    term_file = tmp_path / "terminal_approval.json"
    ui_file = tmp_path / "ui_interaction_evidence.json"

    term_file.write_text(
        json.dumps({"request_id": req_id, "status": "denied", "token_consumed": False}),
        encoding="utf-8",
    )
    ui_file.write_text(
        json.dumps({"request_id": req_id, "operator": "umcp.approval_dialog", "action": "dialog_ok_approve"}),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError) as exc_info:
        wait_for_verified_denial_sync(tmp_path, req_id, timeout=1.0, poll_interval=0.01)

    assert "expected 'deny'" in str(exc_info.value)


def test_verified_denial_fails_closed_on_missing_ui_evidence_timeout(tmp_path: Path):
    """
    If terminal status is 'denied' but UI interaction evidence is completely missing,
    the harness must fail closed on timeout rather than assuming human clicked deny.
    """
    req_id = "test_req_missing_ui_timeout"
    term_file = tmp_path / "terminal_approval.json"
    term_file.write_text(
        json.dumps({"request_id": req_id, "status": "denied", "token_consumed": False}),
        encoding="utf-8",
    )

    with pytest.raises(TimeoutError) as exc_info:
        wait_for_verified_denial_sync(tmp_path, req_id, timeout=0.08, poll_interval=0.02)

    assert "missing ui evidence" in str(exc_info.value).lower()


def test_verified_denial_async_resolves_concurrently(tmp_path: Path):
    """
    Asynchronous version of wait_for_verified_denial polling across concurrent write.
    """
    req_id = "test_req_deny_async"
    term_file = tmp_path / "terminal_approval.json"
    ui_file = tmp_path / "ui_interaction_evidence.json"

    async def scenario():
        async def delayed_write():
            await asyncio.sleep(0.05)
            term_file.write_text(
                json.dumps({"request_id": req_id, "status": "denied", "token_consumed": False}),
                encoding="utf-8",
            )
            ui_file.write_text(
                json.dumps({"request_id": req_id, "operator": "umcp.resolve_approval", "action": "deny"}),
                encoding="utf-8",
            )

        task = asyncio.create_task(delayed_write())
        term, ui = await wait_for_verified_denial_async(tmp_path, req_id, timeout=2.0, poll_interval=0.01)
        await task
        return term, ui

    term, ui = asyncio.run(scenario())
    assert term["status"] == "denied"
    assert ui["action"] == "deny"


def test_verified_cancellation_async_requires_matching_ui_cancel(tmp_path: Path):
    req_id = "test_req_cancel_async"
    (tmp_path / "terminal_approval.json").write_text(json.dumps({
        "request_id": req_id, "status": "cancelled", "token_consumed": False,
    }), encoding="utf-8")
    (tmp_path / "ui_interaction_evidence.json").write_text(json.dumps({
        "request_id": req_id, "operator": "umcp.approval_dialog", "action": "dialog_cancel",
    }), encoding="utf-8")

    terminal, interaction = asyncio.run(wait_for_verified_cancellation_async(
        tmp_path, req_id, timeout=0.2, poll_interval=0.01,
    ))

    assert terminal["status"] == "cancelled"
    assert terminal["token_consumed"] is False
    assert interaction["request_id"] == req_id
    assert interaction["action"] == "dialog_cancel"


@pytest.mark.parametrize(
    ("terminal_state", "message"),
    [("approved", "unexpectedly approved"), ("denied", "not 'cancelled'"), ("expired", "not 'cancelled'")],
)
def test_verified_cancellation_rejects_wrong_terminal_state(
    tmp_path: Path, terminal_state: str, message: str,
):
    req_id = "test_req_cancel_wrong_state"
    (tmp_path / "terminal_approval.json").write_text(json.dumps({
        "request_id": req_id, "status": terminal_state, "token_consumed": False,
    }), encoding="utf-8")
    (tmp_path / "ui_interaction_evidence.json").write_text(json.dumps({
        "request_id": req_id, "operator": "umcp.approval_dialog", "action": "dialog_cancel",
    }), encoding="utf-8")

    with pytest.raises(AssertionError, match=message):
        asyncio.run(wait_for_verified_cancellation_async(
            tmp_path, req_id, timeout=0.2, poll_interval=0.01,
        ))


def test_cancel_saved_evidence_validates_all_fail_closed_postconditions(tmp_path: Path):
    req_id = "test_req_cancel_saved"
    before = {
        "elements": [{"index": 0, "co": [0.0, 0.0, 0.0]}],
        "snapshot_id": "snapshot-before", "state_id": "state-before",
    }
    unchanged_scene = {
        "request_id": req_id,
        "approval_token_present": False,
        "invalid_consume_rejected": True,
        "late_resolve_rejected": True,
        "token_consumed_after_probe": False,
        "edit_mesh_handler_calls": 0,
        "objects_before": ["Cube"], "objects_after": ["Cube"],
        "meshes_before": ["Cube"], "meshes_after": ["Cube"],
        "materials_before": ["Material"], "materials_after": ["Material"],
        "target_before": {"vertices": [[0.0, 0.0, 0.0]]},
        "target_after": {"vertices": [[0.0, 0.0, 0.0]]},
    }
    records = {
        "scenario.json": {"decision": "cancel"},
        "pending.json": {"request_id": req_id, "status": "pending"},
        "terminal_approval.json": {"request_id": req_id, "status": "cancelled", "token_consumed": False},
        "ui_interaction_evidence.json": {"request_id": req_id, "action": "dialog_cancel"},
        "mcp_mutation_response.json": {"isError": False, "payload": {"status": "error"}},
        "cancel_scene_evidence.json": unchanged_scene,
        "approval_status_mcp.json": {"request_id": req_id, "status": "cancelled", "token_consumed": False},
        "topology_before.json": before,
        "topology_after_mcp.json": before,
        "final_blender_state.json": {"pending_request_count": 0, "bridge_running": False},
        "process_exit.json": {"returncode": 0},
    }
    for filename, record in records.items():
        (tmp_path / filename).write_text(json.dumps(record), encoding="utf-8")

    result = verify_controller_postconditions(tmp_path)

    assert result["status"] == "PASS"
    assert result["request_id"] == req_id
    assert result["checks"]["late_resolve_rejected"] is True
    assert all(result["checks"].values())


def test_verify_controller_postconditions_classifies_mrs7zicc_as_denial_failure():
    """
    Preserved evidence directory UMCP-UI-E2E-mrs7zicc is from a failed denial test where
    approval occurred instead of denial. The postcondition validator must strictly reject it
    as a denial failure (unexpected 'approved' status and/or missing UI denial).
    """
    failed_root = Path(r"C:\Users\Administrator\AppData\Local\Temp\UMCP-UI-E2E-mrs7zicc")
    if not failed_root.exists():
        pytest.skip(f"Saved run directory {failed_root} not found on host")

    with pytest.raises(AssertionError) as exc_info:
        verify_controller_postconditions(failed_root, timeout=2.0)

    error_msg = str(exc_info.value)
    assert "Denial postconditions failed" in error_msg
    # It must explicitly identify unexpected approval or missing denial
    assert ("approved" in error_msg.lower() or "missing ui" in error_msg.lower())

