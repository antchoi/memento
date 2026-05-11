from __future__ import annotations

from pathlib import Path

from sisyphus_hermes.reporting import render_report, render_status
from sisyphus_hermes.safety import (
    classify_git_operation,
    render_worker_safety_constraints,
    run_git_preflight,
)
from sisyphus_hermes.commands import CommandService
from sisyphus_hermes.state import SQLiteStateStore


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

    assert "## Sisyphus status" in text
    assert "Goal: ship" in text
    assert "Metis" in report
    assert "Momus" in report
    assert "Sisyphus" in report
    assert "Hephaestus" in report
    assert "Hermes-Sheriff" in report
    assert "|" not in text
