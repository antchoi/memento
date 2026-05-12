from __future__ import annotations

import sqlite3
from pathlib import Path

from sisyphus_hermes.commands import CommandService, command_names
from sisyphus_hermes.domain import (
    AuditEvent,
    Evidence,
    GateKind,
    GateStatus,
    PlanStatus,
    ReviewGate,
    RunStatus,
    SisyphusPlan,
    SisyphusRun,
    SisyphusTask,
)
from sisyphus_hermes.state import SQLiteStateStore


def test_domain_models_round_trip_to_dict() -> None:
    run = SisyphusRun(goal="ship plugin", workspace="/tmp/repo", actor="founder_user")
    plan = SisyphusPlan(run_id=run.id, title="Plan", body="steps", status=PlanStatus.DRAFT)
    task = SisyphusTask(run_id=run.id, title="Task", description="do it")
    gate = ReviewGate(run_id=run.id, kind=GateKind.PLAN_REVIEW, status=GateStatus.PASSED)
    evidence = Evidence(run_id=run.id, kind="test", summary="pytest passed")
    event = AuditEvent(run_id=run.id, actor="metis_planner", action="plan.created")

    for entity in (run, plan, task, gate, evidence, event):
        payload = entity.to_record()
        restored = type(entity).from_record(payload)
        assert restored == entity
        assert payload["id"] == entity.id


def test_sqlite_store_persists_all_entities_across_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "sisyphus.sqlite3"
    store = SQLiteStateStore(db_path)
    run = store.create_run(goal="finish MVP", workspace=str(tmp_path))
    plan = store.save_plan(SisyphusPlan(run_id=run.id, title="Draft", body="1. test"))
    task = store.save_task(SisyphusTask(run_id=run.id, title="Implement", description="state"))
    gate = store.save_gate(ReviewGate(run_id=run.id, kind=GateKind.PREFLIGHT_SAFETY))
    evidence = store.save_evidence(Evidence(run_id=run.id, kind="verification", summary="red test fails"))
    event = store.append_audit(run.id, actor="sisyphus_lifecycle_worker", action="state.saved")

    reopened = SQLiteStateStore(db_path)
    assert reopened.get_run(run.id) == run
    assert reopened.list_plans(run.id) == [plan]
    assert reopened.list_tasks(run.id) == [task]
    assert reopened.list_gates(run.id) == [gate]
    assert reopened.list_evidence(run.id) == [evidence]
    assert reopened.list_audit(run.id) == [event]


def test_approve_plan_promotes_draft_and_records_audit(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.db")
    service = CommandService(store=store)
    run = service.start({"goal": "ship", "workspace": str(tmp_path)})["run"]
    draft = service.plan({"run_id": run["id"], "title": "Draft", "body": "steps"})["plan"]

    blocked = service.start({"run_id": run["id"]})
    assert blocked["ok"] is False
    assert blocked["error"] == "canonical_plan_required"

    approved = service.approve_plan({"run_id": run["id"], "plan_id": draft["id"], "reviewer": "founder_user"})

    assert approved["ok"] is True
    assert approved["plan"]["status"] == PlanStatus.CANONICAL.value
    assert any(event["action"] == "plan.approved" for event in service.status({"run_id": run["id"]})["audit"])


def test_start_rejects_existing_run_with_failed_review_gate(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path)})["run"]
    draft = service.plan({"run_id": run["id"], "title": "Draft", "body": "steps"})["plan"]
    service.approve_plan({"run_id": run["id"], "plan_id": draft["id"]})
    failed = service.review(
        {"run_id": run["id"], "kind": "implementation_review", "status": "failed", "summary": "Fix required"}
    )["gate"]

    blocked = service.start({"run_id": run["id"]})

    assert blocked["ok"] is False
    assert blocked["error"] == "review_gate_blocking"
    assert blocked["blocking_gates"] == [failed]
    assert blocked["run"]["status"] == RunStatus.BLOCKED.value


def test_command_surface_has_all_required_handlers(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    expected = {
        "init",
        "start",
        "plan",
        "approve-plan",
        "status",
        "pause",
        "resume",
        "cancel",
        "review",
        "report",
        "doctor",
        "sample-smoke",
        "enqueue-event",
        "worker-payload",
        "dispatch-task",
        "list-dispatches",
        "claim-dispatch",
        "complete-dispatch",
        "fail-dispatch",
    }
    assert set(command_names()) == expected

    for name in expected:
        assert callable(service.handler_for(name))


def test_pause_resume_cancel_update_state_and_audit(tmp_path: Path) -> None:
    service = CommandService(store=SQLiteStateStore(tmp_path / "state.db"))
    run = service.start({"goal": "ship", "workspace": str(tmp_path), "allow_spike": True})["run"]

    assert service.pause({"run_id": run["id"], "reason": "waiting"})["run"]["status"] == RunStatus.PAUSED.value
    assert service.resume({"run_id": run["id"], "reason": "continue"})["run"]["status"] == RunStatus.ACTIVE.value
    assert service.cancel({"run_id": run["id"], "reason": "stop"})["run"]["status"] == RunStatus.CANCELLED.value

    audit_actions = [event["action"] for event in service.status({"run_id": run["id"]})["audit"]]
    assert ["run.paused", "run.resumed", "run.cancelled"] == audit_actions[-3:]


def test_init_creates_project_local_sqlite_and_doctor_reports_readiness(tmp_path: Path) -> None:
    service = CommandService()
    result = service.init({"workspace": str(tmp_path)})

    assert result["ok"] is True
    db_path = Path(result["state"]["path"])
    assert db_path == tmp_path / ".sisyphus" / "state.sqlite3"
    assert db_path.exists()

    doctor = service.doctor({"workspace": str(tmp_path)})
    assert doctor["ok"] is True
    assert doctor["checks"]["sqlite"] == "ok"
    sqlite3.connect(db_path).close()


def test_project_local_sqlite_fallback_supports_full_lifecycle_across_service_reopen(tmp_path: Path) -> None:
    workspace = str(tmp_path)
    first_process = CommandService()
    first_process.init({"workspace": workspace})
    run = first_process.start({"workspace": workspace, "goal": "ship plugin"})["run"]
    draft = first_process.plan(
        {
            "workspace": workspace,
            "run_id": run["id"],
            "title": "Canonical path",
            "body": "Plan, approve, review, report.",
            "acceptance_criteria": ["status exposes sqlite fallback state"],
        }
    )["plan"]

    second_process = CommandService()
    second_process.approve_plan({"workspace": workspace, "run_id": run["id"], "plan_id": draft["id"]})
    second_process.review(
        {
            "workspace": workspace,
            "run_id": run["id"],
            "kind": "quality_review",
            "status": "passed",
            "summary": "fallback lifecycle verified",
        }
    )

    reopened = CommandService()
    status = reopened.status({"workspace": workspace, "run_id": run["id"]})
    report = reopened.report({"workspace": workspace, "run_id": run["id"]})

    assert status["ok"] is True
    assert status["state"] == {
        "backend": "sqlite",
        "path": str(tmp_path / ".sisyphus" / "state.sqlite3"),
    }
    assert status["run"]["source_of_truth"] == "sqlite"
    assert status["run"]["current_plan_id"] == draft["id"]
    assert [plan["status"] for plan in status["plans"]] == [PlanStatus.CANONICAL.value]
    assert [gate["status"] for gate in status["gates"]] == [GateStatus.PASSED.value, GateStatus.PASSED.value]
    assert {gate["kind"] for gate in status["gates"]} == {GateKind.PLAN_REVIEW.value, GateKind.QUALITY_REVIEW.value}
    assert report["state"] == status["state"]
    assert "Plan: Canonical path" in report["text"]
