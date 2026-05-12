"""Repair task creation from rejected or partial dispatch evidence."""

from __future__ import annotations

from .domain import Evidence, MementoTask, TaskStatus
from .state import SQLiteStateStore


def create_repair_task(store: SQLiteStateStore, source_task: MementoTask, evidence: Evidence) -> MementoTask:
    failed_requirements = list(evidence.content_ref.get("failed_requirements") or [])
    diff_ref = evidence.content_ref.get("diff_ref")
    description = "Repair rejected/partial work from " + source_task.id
    if failed_requirements:
        description += ": " + "; ".join(str(item) for item in failed_requirements)
    verification_policy = dict(source_task.verification_policy)
    verification_policy.update(
        {
            "source_task_id": source_task.id,
            "source_evidence_id": evidence.id,
            "failed_requirements": failed_requirements,
            "quarantined_diff_ref": diff_ref,
        }
    )
    repair = MementoTask(
        run_id=source_task.run_id,
        title=f"Repair {source_task.title}",
        description=description,
        status=TaskStatus.PENDING,
        acceptance_criteria=source_task.acceptance_criteria or ("repair verification passes",),
        parent_id=source_task.id,
        dependencies=(),
        verification_policy=verification_policy,
        context_refs=source_task.context_refs,
        evidence_refs=(evidence.id,),
        kind="repair",
        risk=source_task.risk,
        size="s",
    )
    saved = store.save_task(repair)
    store.append_audit(
        source_task.run_id,
        actor="memento_router",
        action="task.repair_created",
        summary=f"Created repair task for {source_task.id}",
        payload={"repair_task_id": saved.id, "source_task_id": source_task.id, "evidence_id": evidence.id},
    )
    return saved
