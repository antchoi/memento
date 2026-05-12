"""Optional executor peer extension boundary.

Executor adapters are peers, not the source of truth.  Sisyphus writes durable
state first, then either queues an outbox record or builds an explicit command
for an external worker.  Process spawning is opt-in so event/cron ingestion never
accidentally launches OpenCode, Codex, Claude Code, or nested Hermes sessions.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from memento.domain import utc_now
from memento.workers import WorkerPayload

ProcessRunner = Callable[[Sequence[str], Path], dict[str, Any]]


@dataclass(frozen=True, kw_only=True)
class ExecutorDispatchRequest:
    """Explicit request packet for an executor peer."""

    payload: WorkerPayload
    executor: str = "hermes-profile"
    reason: str = "extension point"
    invoke: bool = False


class ExecutorAdapter(Protocol):
    """Protocol implemented by executor peers.

    Implementations may dispatch to Hermes profiles, Codex, Claude Code, or
    OpenCode.  Core lifecycle code remains independent and keeps durable state
    as the source of truth.
    """

    def dispatch(self, request: ExecutorDispatchRequest) -> dict[str, Any]:
        """Dispatch or decline a scoped worker payload."""


class NoopExecutorAdapter:
    """Executor adapter that documents the boundary without executing work."""

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


class PeerExecutorAdapter:
    """Build and optionally spawn a peer executor command.

    Supported executor names:
    - ``hermes-profile[:profile]`` → ``hermes [--profile profile] chat -q ...``
    - ``opencode`` → ``opencode run ...``
    - ``codex`` → ``codex exec ...``
    - ``claude-code`` → ``claude -p ...``

    ``invoke`` must be true on the request for a process to be started.  The
    default is dry-run command construction, which is safe for doctor/smoke and
    for event-driven ingestion.
    """

    def __init__(self, *, runner: ProcessRunner | None = None) -> None:
        self._runner = runner or self._subprocess_runner

    def dispatch(self, request: ExecutorDispatchRequest) -> dict[str, Any]:
        command = self.command_for(request)
        result = {
            "ok": True,
            "dispatched": request.invoke,
            "executor_invoked": False,
            "executor": request.executor,
            "reason": request.reason,
            "command": command,
            "cwd": request.payload.repo_path,
            "payload": request.payload.to_record(),
            "invocation_policy": "explicit_invoke_required",
        }
        if not request.invoke:
            return result
        try:
            run_result = self._runner(command, Path(request.payload.repo_path))
        except OSError as exc:
            return {
                **result,
                "ok": False,
                "dispatched": False,
                "executor_invoked": False,
                "error": f"failed_to_invoke_executor: {type(exc).__name__}: {exc}",
            }
        return {**result, "executor_invoked": True, "process": run_result}

    def command_for(self, request: ExecutorDispatchRequest) -> list[str]:
        payload = request.payload
        prompt = self._prompt_for(payload)
        executor, _, qualifier = request.executor.partition(":")
        if executor == "hermes-profile":
            command = ["hermes"]
            if qualifier:
                command.extend(["--profile", qualifier])
            command.extend(["chat", "-q", prompt])
            return command
        if executor == "opencode":
            return ["opencode", "run", prompt]
        if executor == "codex":
            return ["codex", "exec", prompt]
        if executor == "aider":
            command = ["aider"]
            files = list(payload.relevant_files)
            if files:
                command.extend(files)
            command.extend(["--message", prompt])
            return command
        if executor == "goose":
            return ["goose", "run", prompt]
        if executor == "swe-agent":
            return ["swe-agent", "run", "--problem_statement", prompt]
        if executor in {"claude", "claude-code"}:
            return ["claude", "-p", prompt]
        raise ValueError(f"unsupported executor peer: {request.executor}")

    def _prompt_for(self, payload: WorkerPayload) -> str:
        record = payload.to_record()
        return (
            "Execute this memento worker payload. "
            "Respect safety_constraints, do not use destructive git operations, "
            "and report evidence before marking complete.\n"
            f"```json\n{json.dumps(record, sort_keys=True, indent=2)}\n```"
        )

    def _subprocess_runner(self, cmd: Sequence[str], cwd: Path) -> dict[str, Any]:
        process = subprocess.Popen(cmd, cwd=cwd)
        return {"pid": process.pid}


__all__ = [
    "ExecutorAdapter",
    "ExecutorDispatchRequest",
    "ExecutorOutboxRecord",
    "NoopExecutorAdapter",
    "OutboxExecutorAdapter",
    "PeerExecutorAdapter",
]
