"""Optional executor peer extension boundary.

The MVP exposes this interface so future OpenCode, Codex, Claude Code, or
Hermes-profile adapters can be added as peers without becoming the Sisyphus
source of truth. The default adapter is intentionally a no-op: cron/event
ingestion and worker-payload generation may prepare durable work, but they must
not execute implementation work directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from sisyphus_hermes.domain import utc_now
from sisyphus_hermes.workers import WorkerPayload


@dataclass(frozen=True, kw_only=True)
class ExecutorDispatchRequest:
    """Explicit request packet for a future executor peer."""

    payload: WorkerPayload
    executor: str = "hermes-profile"
    reason: str = "extension point"


class ExecutorAdapter(Protocol):
    """Protocol implemented by future executor peers.

    Implementations may dispatch to Hermes profiles, delegate_task, Codex,
    Claude Code, or OpenCode later. Core lifecycle code must remain independent
    of those implementations and keep durable state as the source of truth.
    """

    def dispatch(self, request: ExecutorDispatchRequest) -> dict[str, Any]:
        """Dispatch or decline a scoped worker payload."""


class NoopExecutorAdapter:
    """MVP executor adapter that documents the boundary without executing work."""

    def dispatch(self, request: ExecutorDispatchRequest) -> dict[str, Any]:
        return {
            "ok": True,
            "dispatched": False,
            "executor_invoked": False,
            "executor": request.executor,
            "reason": request.reason,
            "message": "Optional executor adapters are extension points only in the MVP.",
            "payload": request.payload.to_record(),
        }


@dataclass(frozen=True, kw_only=True)
class ExecutorOutboxRecord:
    """Durable handoff record for an external executor peer."""

    payload: WorkerPayload
    executor: str
    reason: str
    id: str = field(default_factory=lambda: f"dispatch_{uuid4().hex[:12]}")
    created_at: str = field(default_factory=utc_now)
    invocation_policy: str = "outbox_only_no_process_spawn"

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "executor": self.executor,
            "reason": self.reason,
            "invocation_policy": self.invocation_policy,
            "payload": self.payload.to_record(),
        }


class OutboxExecutorAdapter:
    """Queue explicit dispatch requests without spawning child processes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def default_path(workspace: str | Path) -> Path:
        return Path(workspace) / ".sisyphus" / "executor-outbox.jsonl"

    def dispatch(self, request: ExecutorDispatchRequest) -> dict[str, Any]:
        record = ExecutorOutboxRecord(
            payload=request.payload, executor=request.executor, reason=request.reason
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_record(), sort_keys=True) + "\n")
        return {
            "ok": True,
            "dispatched": True,
            "executor_invoked": False,
            "executor": request.executor,
            "reason": request.reason,
            "outbox_path": str(self.path),
            "dispatch_id": record.id,
            "payload": request.payload.to_record(),
            "invocation_policy": record.invocation_policy,
        }

    def list_dispatches(self) -> list[dict[str, Any]]:
        """Return materialized dispatch state from append-only JSONL events."""

        dispatches: dict[str, dict[str, Any]] = {}
        for event in self._events():
            dispatch_id = str(event.get("dispatch_id") or event.get("id"))
            event_type = str(event.get("type") or "dispatch.queued")
            current = dispatches.setdefault(
                dispatch_id,
                {
                    "dispatch_id": dispatch_id,
                    "status": "queued",
                    "task_id": event.get("payload", {}).get("task_id"),
                    "run_id": event.get("payload", {}).get("run_id"),
                    "executor": event.get("executor"),
                    "claimed_by": None,
                    "completed_at": None,
                    "failed_at": None,
                    "executor_invoked": False,
                },
            )
            if event_type == "dispatch.queued":
                current.update(
                    {
                        "task_id": event.get("payload", {}).get("task_id"),
                        "run_id": event.get("payload", {}).get("run_id"),
                        "executor": event.get("executor"),
                        "executor_invoked": bool(event.get("executor_invoked", False)),
                    }
                )
            elif event_type == "dispatch.claimed":
                current["status"] = "claimed"
                current["claimed_by"] = event.get("executor")
                current["executor"] = event.get("executor") or current.get("executor")
            elif event_type == "dispatch.completed":
                current["status"] = "completed"
                current["completed_at"] = event.get("created_at")
            elif event_type == "dispatch.failed":
                current["status"] = "failed"
                current["failed_at"] = event.get("created_at")
        return list(dispatches.values())

    def get_dispatch(self, dispatch_id: str) -> dict[str, Any] | None:
        return next(
            (dispatch for dispatch in self.list_dispatches() if dispatch["dispatch_id"] == dispatch_id),
            None,
        )

    def append_event(self, event_type: str, dispatch_id: str, **payload: Any) -> dict[str, Any]:
        event = {
            "type": event_type,
            "dispatch_id": dispatch_id,
            "created_at": utc_now(),
            "executor_invoked": False,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events


__all__ = [
    "ExecutorAdapter",
    "ExecutorDispatchRequest",
    "ExecutorOutboxRecord",
    "NoopExecutorAdapter",
    "OutboxExecutorAdapter",
]
