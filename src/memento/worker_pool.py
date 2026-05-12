"""API/sandbox worker protocol scaffolding for v3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .domain import new_id


@dataclass
class MockApiSandboxWorker:
    """Mock ExecutorProtocol-compatible API worker.

    The real OpenHands/API worker can implement the same submit/poll/cancel/collect
    boundary without exposing private UI/session state to Memento.
    """

    worker_id: str
    sandbox_modes: tuple[str, ...] = ()
    _jobs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def submit(self, context_bundle: dict[str, Any]) -> dict[str, Any]:
        job_id = new_id("job")
        record = {
            "job_id": job_id,
            "worker_id": self.worker_id,
            "status": "submitted",
            "context_bundle": context_bundle,
            "native_session_ref": {"kind": "api_worker_job", "id": job_id, "worker_id": self.worker_id},
            "sandbox_modes": list(self.sandbox_modes),
        }
        self._jobs[job_id] = record
        return dict(record)

    def poll(self, job_id: str) -> dict[str, Any]:
        job = self._jobs[job_id]
        if job["status"] == "submitted":
            job["status"] = "running"
        return dict(job)

    def collect(self, job_id: str, *, result: dict[str, Any] | None = None) -> dict[str, Any]:
        job = self._jobs[job_id]
        job["status"] = "completed"
        job["result"] = dict(result or {})
        return dict(job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self._jobs[job_id]
        if job["status"] not in {"completed", "failed", "cancelled"}:
            job["status"] = "cancelled"
        return dict(job)
