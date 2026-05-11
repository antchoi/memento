from __future__ import annotations

from pathlib import Path

from sisyphus_hermes.commands import CommandService
from sisyphus_hermes.domain import SisyphusTask
from sisyphus_hermes.state import SQLiteStateStore
from sisyphus_hermes.workers import build_worker_payload


class FakeKanbanAdapter:
    available = True

    def __init__(self) -> None:
        self.tasks: list[SisyphusTask] = []

    def create_or_update_task(self, task: SisyphusTask) -> SisyphusTask:
        self.tasks = [existing for existing in self.tasks if existing.id != task.id]
        self.tasks.append(task)
        return task

    def list_tasks(self, run_id: str) -> list[SisyphusTask]:
        return [task for task in self.tasks if task.run_id == run_id]


def test_kanban_adapter_boundary_can_replace_task_listing_without_live_hermes(tmp_path: Path) -> None:
    kanban = FakeKanbanAdapter()
    store = SQLiteStateStore(tmp_path / "state.db", kanban=kanban)
    service = CommandService(store=store)
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]

    event = service.enqueue_event(
        {
            "run_id": run["id"],
            "source": "cron",
            "title": "Refresh failing test evidence",
            "acceptance_criteria": ["pytest command is recorded"],
        }
    )

    assert event["ok"] is True
    assert store.source_of_truth == "kanban"
    assert event["task"]["id"] == kanban.tasks[0].id
    assert service.status({"run_id": run["id"]})["tasks"] == [event["task"]]


def test_cron_event_ingestion_creates_durable_task_but_does_not_dispatch(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]

    event = service.enqueue_event(
        {
            "run_id": run["id"],
            "source": "webhook",
            "title": "CI failed",
            "description": "Investigate failing lint job",
            "acceptance_criteria": ["root cause recorded", "fix verified"],
        }
    )

    status = service.status({"run_id": run["id"]})
    assert event["ok"] is True
    assert event["dispatched"] is False
    assert event["executor_invoked"] is False
    assert status["tasks"] == [event["task"]]
    assert status["audit"][-1]["action"] == "task.enqueued_from_event"


def test_worker_payload_is_explicit_and_contains_no_hidden_chat_dependency(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]
    task = service.enqueue_event(
        {
            "run_id": run["id"],
            "title": "Implement worker adapter",
            "description": "Add payload builder",
            "acceptance_criteria": ["payload has repo path", "payload has safety constraints"],
        }
    )["task"]

    payload = service.worker_payload({"run_id": run["id"], "task_id": task["id"]})["payload"]

    assert payload["repo_path"] == str(tmp_path)
    assert payload["task_description"] == "Add payload builder"
    assert payload["acceptance_criteria"] == ["payload has repo path", "payload has safety constraints"]
    assert "git reset --hard" in payload["safety_constraints"]
    assert "Do not rely on parent chat history" in payload["hidden_context_policy"]
    assert "verification commands/results" in payload["reporting_contract"]


def test_build_worker_payload_round_trip_from_domain_models(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    run = store.create_run(goal="ship", workspace=str(tmp_path))
    task = store.save_task(
        SisyphusTask(
            run_id=run.id,
            title="Task",
            description="Do scoped work",
            acceptance_criteria=("tests pass",),
        )
    )

    payload = build_worker_payload(run, task).to_record()

    assert payload["run_id"] == run.id
    assert payload["task_id"] == task.id
    assert payload["goal"] == "ship"
    assert payload["role"] == "hephaestus_executor"
