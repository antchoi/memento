"""Recovery from canonical Memento state rather than native worker memory."""

from __future__ import annotations

from typing import Any

from .domain import TaskStatus
from .state import SQLiteStateStore

_RECOVERABLE = {TaskStatus.CLAIMED, TaskStatus.IN_PROGRESS, TaskStatus.SUBMITTED, TaskStatus.VERIFYING}


def recover_dispatch_jobs(store: SQLiteStateStore, run_id: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for task in store.list_tasks(run_id):
        if task.status in _RECOVERABLE:
            jobs.append(
                {
                    "task_id": task.id,
                    "status": task.status.value,
                    "recovery_mode": "regenerate_context_bundle",
                    "native_session_required": False,
                    "verification_policy": task.verification_policy,
                }
            )
    return jobs
