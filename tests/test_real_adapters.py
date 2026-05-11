from __future__ import annotations

import json
from pathlib import Path

from sisyphus_hermes.commands import CommandService
from sisyphus_hermes.domain import SisyphusTask
from sisyphus_hermes.executors import ExecutorDispatchRequest, OutboxExecutorAdapter
from sisyphus_hermes.kanban import JsonKanbanAdapter
from sisyphus_hermes.state import SQLiteStateStore
from sisyphus_hermes.workers import build_worker_payload


def test_json_kanban_adapter_persists_cards_across_store_restarts(tmp_path: Path) -> None:
    board_path = tmp_path / ".sisyphus" / "kanban.json"
    kanban = JsonKanbanAdapter(board_path)
    store = SQLiteStateStore(tmp_path / ".sisyphus" / "state.sqlite3", kanban=kanban)
    run = store.create_run(goal="ship practical adapters", workspace=str(tmp_path))
    task = store.save_task(
        SisyphusTask(
            run_id=run.id,
            title="Build Kanban adapter",
            description="Persist task as a board card",
            acceptance_criteria=("card survives restart",),
        )
    )

    reopened = SQLiteStateStore(
        tmp_path / ".sisyphus" / "state.sqlite3", kanban=JsonKanbanAdapter(board_path)
    )

    assert reopened.source_of_truth == "kanban"
    assert reopened.list_tasks(run.id) == [task]
    board = json.loads(board_path.read_text(encoding="utf-8"))
    assert board["schema_version"] == 1
    assert board["cards"][0]["task"]["id"] == task.id
    assert board["cards"][0]["lane"] == "pending"


def test_json_kanban_adapter_updates_existing_card_instead_of_duplicating(tmp_path: Path) -> None:
    board_path = tmp_path / "kanban.json"
    adapter = JsonKanbanAdapter(board_path)
    first = SisyphusTask(run_id="run_1", title="Task", description="one")
    adapter.create_or_update_task(first)
    updated = SisyphusTask(
        run_id="run_1",
        title="Task updated",
        description="two",
        id=first.id,
        created_at=first.created_at,
    )
    adapter.create_or_update_task(updated)

    assert adapter.list_tasks("run_1") == [updated]
    assert len(json.loads(board_path.read_text(encoding="utf-8"))["cards"]) == 1


def test_outbox_executor_adapter_records_explicit_dispatch_without_spawning_process(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    run = store.create_run(goal="ship executor adapter", workspace=str(tmp_path))
    task = store.save_task(SisyphusTask(run_id=run.id, title="Implement", description="Do work"))
    payload = build_worker_payload(run, task)
    outbox_path = tmp_path / ".sisyphus" / "executor-outbox.jsonl"

    result = OutboxExecutorAdapter(outbox_path).dispatch(
        ExecutorDispatchRequest(payload=payload, executor="hermes-profile", reason="manual dispatch")
    )

    assert result["ok"] is True
    assert result["dispatched"] is True
    assert result["executor_invoked"] is False
    assert result["outbox_path"] == str(outbox_path)
    lines = outbox_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["executor"] == "hermes-profile"
    assert record["payload"]["task_id"] == task.id
    assert record["invocation_policy"] == "outbox_only_no_process_spawn"


def test_command_dispatch_task_queues_executor_outbox_and_audit(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]
    task = service.enqueue_event({"run_id": run["id"], "title": "Queued work"})["task"]

    result = service.dispatch_task(
        {"run_id": run["id"], "task_id": task["id"], "executor": "hermes-profile"}
    )

    assert result["ok"] is True
    assert result["command"] == "dispatch-task"
    assert result["executor_invoked"] is False
    assert Path(result["outbox_path"]).exists()
    status = service.status({"run_id": run["id"]})
    assert status["audit"][-1]["action"] == "task.dispatch_queued"
    assert status["audit"][-1]["payload"]["task_id"] == task["id"]


def test_command_dispatch_task_rejects_unknown_task_without_outbox_write(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]

    result = service.dispatch_task({"run_id": run["id"], "task_id": "missing"})

    assert result == {"ok": False, "error": "task_not_found", "task_id": "missing"}
    assert not (tmp_path / ".sisyphus" / "executor-outbox.jsonl").exists()
