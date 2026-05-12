from __future__ import annotations

from pathlib import Path

from memento.domain import MementoTask
from memento.reporting import render_report, render_status
from memento.safety import (
    classify_git_operation,
    render_worker_safety_constraints,
    run_git_preflight,
)
from memento.commands import CommandService
from memento.state import SQLiteStateStore


def test_destructive_git_operations_blocked_by_default() -> None:
    blocked = [
        "git reset --hard HEAD~1",
        "git clean -fdx",
        "git push --force origin main",
        "git push origin main",
        "git merge feature",
    ]
    for command in blocked:
        verdict = classify_git_operation(command)
        assert verdict.allowed is False
        assert verdict.requires_approval is True

    safe = classify_git_operation("git status --short")
    assert safe.allowed is True
    assert safe.requires_approval is False


def test_worker_safety_constraints_name_guarded_operations() -> None:
    constraints = render_worker_safety_constraints()
    assert "git reset --hard" in constraints
    assert "git clean" in constraints
    assert "force push" in constraints
    assert "direct main push" in constraints
    assert "merge" in constraints


def test_git_preflight_reports_dirty_untracked_and_protected_branch(tmp_path: Path) -> None:
    # Non-git directories are ambiguous and must block implementation paths.
    non_repo = run_git_preflight(tmp_path)
    assert non_repo.ok is False
    assert "not_git_repository" in non_repo.blockers


def test_status_and_report_are_telegram_friendly(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    service = CommandService(store=store)
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]
    service.review({"run_id": run["id"], "kind": "quality_review", "status": "passed", "summary": "tests pass"})
    status = service.status({"run_id": run["id"]})

    text = render_status(status)
    report = render_report(status)

    assert "## Memento status" in text
    assert "Goal: ship" in text
    assert "Metis" in report
    assert "Momus" in report
    assert "Memento" in report
    assert "Hephaestus" in report
    assert "Hermes-Sheriff" in report
    assert "|" not in text


def test_status_output_includes_each_roles_latest_action(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    service = CommandService(store=store)
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]
    service.plan({"run_id": run["id"], "title": "Plan", "body": "Do it"})
    service.review(
        {
            "run_id": run["id"],
            "kind": "quality_review",
            "status": "passed",
            "summary": "implementation evidence accepted",
        }
    )
    service.add_evidence(run["id"], kind="test", summary="pytest passed")
    store.append_audit(run["id"], actor="hermes_sheriff", action="preflight.checked", summary="repo safe")

    text = render_status(service.status({"run_id": run["id"]}))

    assert "## Role latest actions" in text
    assert "- Metis: plan.created — Plan" in text
    assert "- Momus: gate.passed — implementation evidence accepted" in text
    assert "- Memento: execution.spike_allowed — Bounded spike allowed without canonical plan." in text
    assert "- Hephaestus: evidence.added — pytest passed" in text
    assert "- Hermes-Sheriff: preflight.checked — repo safe" in text


def test_report_does_not_duplicate_role_latest_actions(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]

    report = render_report(service.status({"run_id": run["id"]}))

    assert report.count("## Role latest actions") == 1


def test_cancel_report_lists_incomplete_tasks_and_child_process_handles(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    service = CommandService(store=store)
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]
    store.save_task(MementoTask(run_id=run["id"], title="Finish adapter", description="Still running"))

    service.cancel(
        {
            "run_id": run["id"],
            "reason": "user stopped work",
            "child_process_handles": ["proc_123", "proc_456"],
        }
    )

    report = render_report(service.status({"run_id": run["id"]}))

    assert "## Pause/cancel recovery" in report
    assert "Incomplete tasks: 1" in report
    assert "- Finish adapter: pending" in report
    assert "Known child processes: proc_123, proc_456" in report
