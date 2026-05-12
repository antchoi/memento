"""Basic evidence-driven verification policy evaluator."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .domain import Evidence, MementoTask, TaskStatus
from .state import SQLiteStateStore

PASS_STATUSES = {"passed", "observed"}
SUPERSEDED_STATUS = "superseded"


def active_evidence_for_task(store: SQLiteStateStore, run_id: str, task_id: str) -> list[Evidence]:
    evidence = [ev for ev in store.list_evidence(run_id) if ev.task_id == task_id]
    superseded_ids = {
        old_id
        for ev in evidence
        for old_id in (ev.relationships.get("supersedes") or [])
        if isinstance(ev.relationships, dict)
    }
    return [ev for ev in evidence if ev.id not in superseded_ids and ev.status != SUPERSEDED_STATUS]


def evaluate_task(store: SQLiteStateStore, task: MementoTask) -> dict[str, Any]:
    policy = task.verification_policy or {}
    required = list(policy.get("required_evidence") or policy.get("required_evidence_types") or [])
    evidence = active_evidence_for_task(store, task.run_id, task.id)
    failed_requirements: list[str] = []
    for evidence_type in required:
        matching = [ev for ev in evidence if (ev.type or ev.kind) == evidence_type and ev.status in PASS_STATUSES]
        if not matching:
            failed_requirements.append(f"missing required evidence: {evidence_type}")
    accepted = not failed_requirements
    verdict = "accepted" if accepted else "rejected"
    qa = store.save_evidence(
        Evidence(
            run_id=task.run_id,
            kind="qa_verdict",
            type="qa_verdict",
            summary=f"Task {verdict}: {task.title}",
            task_id=task.id,
            status="passed" if accepted else "failed",
            trust_level="trusted",
            relationships={"supports": [task.id], "failed_requirements": failed_requirements},
        )
    )
    store.save_task(replace(task, status=TaskStatus.ACCEPTED if accepted else TaskStatus.REJECTED, updated_at=qa.created_at))
    return {
        "verdict": verdict,
        "accepted": accepted,
        "failed_requirements": failed_requirements,
        "evidence_id": qa.id,
    }
