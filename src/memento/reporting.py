"""Telegram-friendly renderers for Memento status and reports."""

from __future__ import annotations

from typing import Any

ROLE_LABELS = {
    "metis_planner": "Metis",
    "momus_reviewer": "Momus",
    "memento_lifecycle_worker": "Memento",
    "hephaestus_executor": "Hephaestus",
    "hermes_sheriff": "Hermes-Sheriff",
}


def _latest_by_actor(audit: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in audit:
        latest[event.get("actor", "")] = event
    return latest


def _render_role_latest_actions(audit: list[dict[str, Any]]) -> list[str]:
    latest = _latest_by_actor(audit)
    role_lines = ["", "## Role latest actions"]
    for actor, label in ROLE_LABELS.items():
        event = latest.get(actor)
        if event:
            role_lines.append(f"- {label}: {event.get('action')} — {event.get('summary') or 'no summary'}")
        else:
            role_lines.append(f"- {label}: no recorded action yet")
    return role_lines


def _render_pause_cancel_recovery(status: dict[str, Any]) -> list[str]:
    run = status.get("run", {})
    if run.get("status") not in {"paused", "cancelled"}:
        return []

    incomplete_tasks = [
        task
        for task in status.get("tasks", [])
        if task.get("status") not in {"completed", "cancelled"}
    ]
    lifecycle_events = [
        event for event in status.get("audit", []) if event.get("action") in {"run.paused", "run.cancelled"}
    ]
    child_handles = []
    if lifecycle_events:
        child_handles = lifecycle_events[-1].get("payload", {}).get("child_process_handles") or []

    lines = ["", "## Pause/cancel recovery", f"Incomplete tasks: {len(incomplete_tasks)}"]
    for task in incomplete_tasks:
        lines.append(f"- {task.get('title')}: {task.get('status')}")
    if child_handles:
        lines.append(f"Known child processes: {', '.join(str(handle) for handle in child_handles)}")
    else:
        lines.append("Known child processes: none recorded")
    return lines


def _render_recovery_plan(status: dict[str, Any]) -> list[str]:
    recovery_events = [event for event in status.get("audit", []) if event.get("action") == "recovery.planned"]
    if not recovery_events:
        return []
    payload = recovery_events[-1].get("payload", {})
    jobs = list(payload.get("jobs") or [])
    lines = ["", "## Recovery plan", f"Restartable jobs: {payload.get('job_count', len(jobs))}"]
    for job in jobs:
        bundle_path = job.get("context_bundle_path") or "not generated"
        lines.append(f"- {job.get('task_id')}: {job.get('status')} → {job.get('recovery_mode')} ({bundle_path})")
    if not jobs:
        lines.append("- none")
    return lines


def render_status(status: dict[str, Any]) -> str:
    if not status.get("ok"):
        return f"## Memento status\nState: error\nError: {status.get('error', 'unknown')}"
    run = status["run"]
    plans = status.get("plans", [])
    tasks = status.get("tasks", [])
    gates = status.get("gates", [])
    evidence = status.get("evidence", [])
    audit = status.get("audit", [])
    canonical = next((p for p in plans if p.get("status") == "canonical"), None)
    blockers = [g for g in gates if g.get("status") == "failed"]
    next_action = "Approve a canonical plan" if not canonical else "Execute next ready task"
    if run.get("status") in {"paused", "cancelled", "completed"}:
        next_action = "Resume or create a new run" if run.get("status") == "paused" else "No active next action"

    return "\n".join(
        [
            "## Memento status",
            f"Run: {run['id']}",
            f"Goal: {run['goal']}",
            f"State: {run['status']}",
            f"Workspace: {run['workspace']}",
            f"Plan: {canonical['title'] if canonical else 'draft/not approved'}",
            f"Tasks: {len(tasks)} total",
            f"Gates: {len(gates)} total, {len(blockers)} blocking",
            f"Evidence: {len(evidence)} item(s)",
            f"Audit events: {len(audit)}",
            f"Next action: {next_action}",
            *_render_role_latest_actions(audit),
            *_render_pause_cancel_recovery(status),
            *_render_recovery_plan(status),
        ]
    )


def render_report(status: dict[str, Any]) -> str:
    base = render_status(status)
    if not status.get("ok"):
        return base
    evidence_lines = ["", "## Evidence"]
    evidence = status.get("evidence", [])
    if evidence:
        for item in evidence:
            evidence_lines.append(f"- {item.get('kind')}: {item.get('summary')}")
    else:
        evidence_lines.append("- none yet")

    return "\n".join([base, *evidence_lines])
