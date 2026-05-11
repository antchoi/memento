"""Optional executor peer extension boundary.

The MVP exposes this interface so future OpenCode, Codex, Claude Code, or
Hermes-profile adapters can be added as peers without becoming the Sisyphus
source of truth. The default adapter is intentionally a no-op: cron/event
ingestion and worker-payload generation may prepare durable work, but they must
not execute implementation work directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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


__all__ = ["ExecutorAdapter", "ExecutorDispatchRequest", "NoopExecutorAdapter"]
