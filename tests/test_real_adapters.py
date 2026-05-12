from __future__ import annotations

import json
from pathlib import Path

from memento.commands import CommandService
from memento.domain import MementoTask, TaskStatus
from memento.executors import (
    ExecutorDispatchRequest,
    OutboxExecutorAdapter,
    PeerExecutorAdapter,
)
from memento.kanban import HermesKanbanCliAdapter, JsonKanbanAdapter
from memento.state import SQLiteStateStore
from memento.workers import build_worker_payload


def test_json_kanban_adapter_persists_cards_across_store_restarts(tmp_path: Path) -> None:
    board_path = tmp_path / ".memento" / "kanban.json"
    kanban = JsonKanbanAdapter(board_path)
    store = SQLiteStateStore(tmp_path / ".memento" / "state.sqlite3", kanban=kanban)
    run = store.create_run(goal="ship practical adapters", workspace=str(tmp_path))
    task = store.save_task(
        MementoTask(
            run_id=run.id,
            title="Build Kanban adapter",
            description="Persist task as a board card",
            acceptance_criteria=("card survives restart",),
        )
    )

    reopened = SQLiteStateStore(
        tmp_path / ".memento" / "state.sqlite3", kanban=JsonKanbanAdapter(board_path)
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
    first = MementoTask(run_id="run_1", title="Task", description="one")
    adapter.create_or_update_task(first)
    updated = MementoTask(
        run_id="run_1",
        title="Task updated",
        description="two",
        id=first.id,
        created_at=first.created_at,
    )
    adapter.create_or_update_task(updated)

    assert adapter.list_tasks("run_1") == [updated]
    assert len(json.loads(board_path.read_text(encoding="utf-8"))["cards"]) == 1


def test_hermes_kanban_cli_adapter_uses_public_json_cli_contract(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    task = MementoTask(
        run_id="run_123",
        title="Implement live adapter",
        description=str(tmp_path),
        status=TaskStatus.PENDING,
    )

    def runner(cmd: list[str]) -> dict[str, object]:
        calls.append(cmd)
        if "create" in cmd:
            body = cmd[cmd.index("--body") + 1]
            return {"exit_code": 0, "stdout": json.dumps({"id": "kb_1", "body": body})}
        return {
            "exit_code": 0,
            "stdout": json.dumps(
                {"tasks": [{"id": "kb_1", "body": json.dumps({"memento_task": task.to_record()})}]}
            ),
        }

    adapter = HermesKanbanCliAdapter(board="memento", tenant="memento", runner=runner)

    saved = adapter.create_or_update_task(task)
    listed = adapter.list_tasks("run_123")

    assert saved.id == task.id
    assert listed == [task]
    assert calls[0][:4] == ["hermes", "kanban", "--board", "memento"]
    assert "--idempotency-key" in calls[0]
    assert f"memento:{task.id}" in calls[0]
    assert calls[1] == ["hermes", "kanban", "--board", "memento", "list", "--tenant", "memento", "--json"]


def test_hermes_kanban_cli_adapter_reports_subprocess_failures() -> None:
    adapter = HermesKanbanCliAdapter(runner=lambda _cmd: {"exit_code": 127, "stderr": "hermes missing"})

    try:
        adapter.list_tasks("run_missing")
    except RuntimeError as exc:
        assert "hermes missing" in str(exc)
    else:  # pragma: no cover - failure branch
        raise AssertionError("expected RuntimeError for failed Hermes CLI invocation")


def test_hermes_kanban_cli_adapter_reports_invalid_json() -> None:
    adapter = HermesKanbanCliAdapter(runner=lambda _cmd: {"exit_code": 0, "stdout": "not json"})

    try:
        adapter.list_tasks("run_invalid")
    except RuntimeError as exc:
        assert "non-JSON" in str(exc)
    else:  # pragma: no cover - failure branch
        raise AssertionError("expected RuntimeError for invalid Hermes CLI JSON")


def test_hermes_kanban_subprocess_runner_converts_oserror_to_failure() -> None:
    adapter = HermesKanbanCliAdapter(hermes_command="definitely-not-a-hermes-binary")

    result = adapter._subprocess_runner(["definitely-not-a-hermes-binary", "kanban", "list", "--json"])

    assert result["exit_code"] == 127
    assert "failed to execute Hermes Kanban CLI" in result["stderr"]


def test_outbox_executor_adapter_records_explicit_dispatch_without_spawning_process(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    run = store.create_run(goal="ship executor adapter", workspace=str(tmp_path))
    task = store.save_task(MementoTask(run_id=run.id, title="Implement", description="Do work"))
    payload = build_worker_payload(run, task)
    outbox_path = tmp_path / ".memento" / "executor-outbox.jsonl"

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


def test_peer_executor_adapter_builds_commands_and_requires_explicit_invoke(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    run = store.create_run(goal="ship peer executor", workspace=str(tmp_path))
    task = store.save_task(MementoTask(run_id=run.id, title="Implement", description="Do work"))
    payload = build_worker_payload(run, task)
    invoked: list[tuple[list[str], Path]] = []

    def runner(cmd: list[str], cwd: Path) -> dict[str, object]:
        invoked.append((cmd, cwd))
        return {"pid": 1234}

    adapter = PeerExecutorAdapter(runner=runner)
    dry_run = adapter.dispatch(ExecutorDispatchRequest(payload=payload, executor="opencode"))
    assert dry_run["command"][0:2] == ["opencode", "run"]
    assert dry_run["executor_invoked"] is False
    assert invoked == []

    live = adapter.dispatch(ExecutorDispatchRequest(payload=payload, executor="hermes-profile:worker", invoke=True))
    assert live["command"][:4] == ["hermes", "--profile", "worker", "chat"]
    assert live["executor_invoked"] is True
    assert invoked[0][1] == tmp_path


def test_peer_executor_adapter_returns_structured_failure_on_spawn_error(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    run = store.create_run(goal="ship peer executor failure handling", workspace=str(tmp_path))
    task = store.save_task(MementoTask(run_id=run.id, title="Implement", description="Do work"))
    payload = build_worker_payload(run, task)

    def runner(_cmd: list[str], _cwd: Path) -> dict[str, object]:
        raise FileNotFoundError("executor missing")

    result = PeerExecutorAdapter(runner=runner).dispatch(
        ExecutorDispatchRequest(payload=payload, executor="opencode", invoke=True)
    )

    assert result["ok"] is False
    assert result["dispatched"] is False
    assert result["executor_invoked"] is False
    assert "FileNotFoundError" in result["error"]


def test_command_dispatch_task_queues_executor_outbox_and_audit(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]
    plan = service.plan({"run_id": run["id"], "title": "Dispatch plan", "body": "Queue work"})["plan"]
    service.approve_plan({"run_id": run["id"], "plan_id": plan["id"]})
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
    assert not (tmp_path / ".memento" / "executor-outbox.jsonl").exists()
