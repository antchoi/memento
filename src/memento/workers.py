"""Worker dispatch payload construction for Hermes-native executors.

The MVP does not execute work directly from this module. It only builds explicit,
serialisable payloads that can be handed to Hermes profiles, delegate_task, or a
future executor adapter without relying on hidden parent chat context.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .domain import SisyphusRun, SisyphusTask
from .safety import render_worker_safety_constraints


REPORTING_CONTRACT = (
    "Report changed files, verification commands/results, progress evidence, "
    "blockers, risks, and the next action. Do not dump raw logs unless requested."
)


@dataclass(frozen=True, kw_only=True)
class WorkerPayload:
    """Explicit context packet for bounded Hermes-native worker dispatch."""

    run_id: str
    task_id: str
    repo_path: str
    goal: str
    task_title: str
    task_description: str
    acceptance_criteria: tuple[str, ...]
    role: str
    relevant_files: tuple[str, ...] = ()
    verification_policy: dict[str, Any] = field(default_factory=dict)
    safety_constraints: str = field(default_factory=render_worker_safety_constraints)
    reporting_contract: str = REPORTING_CONTRACT
    hidden_context_policy: str = "Do not rely on parent chat history or TUI state."
    source_of_truth: str = "memento durable state"

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["acceptance_criteria"] = list(self.acceptance_criteria)
        return record


def build_worker_payload(run: SisyphusRun, task: SisyphusTask) -> WorkerPayload:
    """Build a complete worker context packet for a scoped task."""

    return WorkerPayload(
        run_id=run.id,
        task_id=task.id,
        repo_path=run.workspace,
        goal=run.goal,
        task_title=task.title,
        task_description=task.description,
        acceptance_criteria=task.acceptance_criteria,
        role=task.role,
        relevant_files=task.context_refs,
        verification_policy=task.verification_policy,
    )
