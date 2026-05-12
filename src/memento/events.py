"""Cron/event ingestion helpers.

Cron and webhook integrations are intentionally limited to durable task creation
or update. They must never dispatch implementation work directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import SisyphusTask, TaskStatus
from .state import SQLiteStateStore


@dataclass(frozen=True, kw_only=True)
class EventIngestionResult:
    ok: bool
    task: SisyphusTask
    dispatched: bool = False
    executor_invoked: bool = False

    def to_record(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "task": self.task.to_record(),
            "dispatched": self.dispatched,
            "executor_invoked": self.executor_invoked,
        }


def enqueue_event_task(store: SQLiteStateStore, payload: dict[str, Any]) -> EventIngestionResult:
    """Create a durable task from a cron/webhook payload without executing it."""

    run_id = str(payload["run_id"])
    title = str(payload.get("title") or payload.get("summary") or "Event task")
    description = str(payload.get("description") or payload.get("body") or title)
    acceptance_criteria_raw = payload.get("acceptance_criteria") or ()
    if isinstance(acceptance_criteria_raw, str):
        acceptance_criteria = (acceptance_criteria_raw,)
    else:
        acceptance_criteria = tuple(acceptance_criteria_raw)
    role = str(payload.get("role") or "hephaestus_executor")
    source = str(payload.get("source") or "event")

    task = store.save_task(
        SisyphusTask(
            run_id=run_id,
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            acceptance_criteria=acceptance_criteria,
            role=role,
        )
    )
    store.append_audit(
        run_id,
        actor="sisyphus_lifecycle_worker",
        action="task.enqueued_from_event",
        summary=title,
        payload={"source": source, "task_id": task.id},
    )
    return EventIngestionResult(ok=True, task=task)
