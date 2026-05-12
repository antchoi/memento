"""Cron/event ingestion helpers.

Cron and webhook integrations are intentionally limited to durable task creation
or update. They must never dispatch implementation work directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import MementoTask, TaskStatus
from .state import SQLiteStateStore


@dataclass(frozen=True, kw_only=True)
class EventIngestionResult:
    ok: bool
    task: MementoTask
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
    dependencies_raw = payload.get("dependencies") or ()
    dependencies = (dependencies_raw,) if isinstance(dependencies_raw, str) else tuple(dependencies_raw)
    context_refs_raw = payload.get("context_refs") or payload.get("files_expected") or ()
    context_refs = (context_refs_raw,) if isinstance(context_refs_raw, str) else tuple(context_refs_raw)
    verification_policy = dict(payload.get("verification_policy") or {})
    if acceptance_criteria and not verification_policy:
        verification_policy = {"required_evidence": ["dispatch_result"]}

    task = store.save_task(
        MementoTask(
            run_id=run_id,
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            acceptance_criteria=acceptance_criteria,
            role=role,
            dependencies=dependencies,
            context_refs=context_refs,
            verification_policy=verification_policy,
            kind=str(payload.get("kind") or "implementation"),
            risk=str(payload.get("risk") or "medium"),
            size=str(payload.get("size") or "m"),
        )
    )
    store.append_audit(
        run_id,
        actor="memento_lifecycle_worker",
        action="task.enqueued_from_event",
        summary=title,
        payload={"source": source, "task_id": task.id},
    )
    return EventIngestionResult(ok=True, task=task)
