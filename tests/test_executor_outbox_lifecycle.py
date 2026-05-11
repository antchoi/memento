from __future__ import annotations

import json
from pathlib import Path

from sisyphus_hermes.commands import CommandService, command_names
from sisyphus_hermes.state import SQLiteStateStore


def _queued_dispatch(tmp_path: Path) -> tuple[CommandService, dict, dict, dict, Path]:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship lifecycle", "workspace": str(tmp_path), "allow_spike": True})[
        "run"
    ]
    task = service.enqueue_event({"run_id": run["id"], "title": "Implement lifecycle"})["task"]
    outbox_path = tmp_path / ".sisyphus" / "executor-outbox.jsonl"
    dispatch = service.dispatch_task(
        {
            "run_id": run["id"],
            "task_id": task["id"],
            "executor": "hermes-profile",
            "outbox_path": str(outbox_path),
        }
    )
    return service, run, task, dispatch, outbox_path


def _outbox_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_outbox_materializer_lists_queued_dispatches_across_reopened_adapter(tmp_path: Path) -> None:
    service, run, task, dispatch, outbox_path = _queued_dispatch(tmp_path)

    reopened = CommandService(store=service.store)
    result = reopened.list_dispatches({"run_id": run["id"], "outbox_path": str(outbox_path)})

    assert result["ok"] is True
    assert result["command"] == "list-dispatches"
    assert result["dispatches"] == [
        {
            "dispatch_id": dispatch["dispatch_id"],
            "status": "queued",
            "task_id": task["id"],
            "run_id": run["id"],
            "executor": "hermes-profile",
            "claimed_by": None,
            "completed_at": None,
            "failed_at": None,
            "executor_invoked": False,
        }
    ]


def test_claim_complete_dispatch_advances_task_evidence_audit_without_spawning(tmp_path: Path) -> None:
    service, run, task, dispatch, outbox_path = _queued_dispatch(tmp_path)
    queued_size = outbox_path.stat().st_size

    claimed = service.claim_dispatch(
        {
            "dispatch_id": dispatch["dispatch_id"],
            "executor": "hermes-profile",
            "outbox_path": str(outbox_path),
        }
    )
    completed = service.complete_dispatch(
        {
            "dispatch_id": dispatch["dispatch_id"],
            "summary": "Implemented lifecycle",
            "evidence_uri": "file://artifact.json",
            "outbox_path": str(outbox_path),
        }
    )

    assert claimed["ok"] is True
    assert claimed["executor_invoked"] is False
    assert completed["ok"] is True
    assert completed["executor_invoked"] is False
    assert outbox_path.stat().st_size > queued_size
    events = _outbox_events(outbox_path)
    assert [event.get("type", "dispatch.queued") for event in events] == [
        "dispatch.queued",
        "dispatch.claimed",
        "dispatch.completed",
    ]
    status = service.status({"run_id": run["id"]})
    task_record = next(item for item in status["tasks"] if item["id"] == task["id"])
    assert task_record["status"] == "completed"
    assert status["evidence"][-1]["task_id"] == task["id"]
    assert status["evidence"][-1]["uri"] == "file://artifact.json"
    assert [entry["action"] for entry in status["audit"][-3:]] == [
        "task.dispatch_claimed",
        "evidence.added",
        "task.completed",
    ]


def test_claim_dispatch_rejects_unknown_dispatch_without_appending(tmp_path: Path) -> None:
    service, _run, _task, _dispatch, outbox_path = _queued_dispatch(tmp_path)
    before = outbox_path.read_text(encoding="utf-8")

    result = service.claim_dispatch(
        {"dispatch_id": "dispatch_missing", "executor": "hermes-profile", "outbox_path": str(outbox_path)}
    )

    assert result == {"ok": False, "error": "dispatch_not_found", "dispatch_id": "dispatch_missing"}
    assert outbox_path.read_text(encoding="utf-8") == before


def test_claim_dispatch_rejects_stealing_claimed_dispatch(tmp_path: Path) -> None:
    service, _run, _task, dispatch, outbox_path = _queued_dispatch(tmp_path)
    service.claim_dispatch(
        {
            "dispatch_id": dispatch["dispatch_id"],
            "executor": "hermes-profile",
            "outbox_path": str(outbox_path),
        }
    )
    before = outbox_path.read_text(encoding="utf-8")

    result = service.claim_dispatch(
        {"dispatch_id": dispatch["dispatch_id"], "executor": "codex", "outbox_path": str(outbox_path)}
    )

    assert result["ok"] is False
    assert result["error"] == "dispatch_already_claimed"
    assert result["claimed_by"] == "hermes-profile"
    assert outbox_path.read_text(encoding="utf-8") == before


def test_completed_dispatch_cannot_be_failed_afterward(tmp_path: Path) -> None:
    service, _run, _task, dispatch, outbox_path = _queued_dispatch(tmp_path)
    service.claim_dispatch(
        {
            "dispatch_id": dispatch["dispatch_id"],
            "executor": "hermes-profile",
            "outbox_path": str(outbox_path),
        }
    )
    service.complete_dispatch(
        {
            "dispatch_id": dispatch["dispatch_id"],
            "summary": "done",
            "evidence_uri": "file://done.txt",
            "outbox_path": str(outbox_path),
        }
    )
    before = outbox_path.read_text(encoding="utf-8")

    result = service.fail_dispatch(
        {"dispatch_id": dispatch["dispatch_id"], "reason": "late failure", "outbox_path": str(outbox_path)}
    )

    assert result["ok"] is False
    assert result["error"] == "dispatch_terminal"
    assert result["status"] == "completed"
    assert outbox_path.read_text(encoding="utf-8") == before


def test_fail_dispatch_marks_task_and_run_blocked(tmp_path: Path) -> None:
    service, run, task, dispatch, outbox_path = _queued_dispatch(tmp_path)
    service.claim_dispatch(
        {
            "dispatch_id": dispatch["dispatch_id"],
            "executor": "hermes-profile",
            "outbox_path": str(outbox_path),
        }
    )

    result = service.fail_dispatch(
        {"dispatch_id": dispatch["dispatch_id"], "reason": "tests failed", "outbox_path": str(outbox_path)}
    )

    assert result["ok"] is True
    assert result["status"] == "failed"
    status = service.status({"run_id": run["id"]})
    task_record = next(item for item in status["tasks"] if item["id"] == task["id"])
    assert task_record["status"] == "blocked"
    assert status["run"]["status"] == "blocked"
    assert status["audit"][-1]["action"] == "task.failed"


def test_dispatch_lifecycle_commands_are_registered() -> None:
    assert "list-dispatches" in command_names()
    assert "claim-dispatch" in command_names()
    assert "complete-dispatch" in command_names()
    assert "fail-dispatch" in command_names()
