from __future__ import annotations

from pathlib import Path

from memento.commands import CommandService
from memento.approvals import record_approval, release_gate_satisfied
from memento.ci import record_external_check
from memento.competition import select_patch
from memento.domain import MementoTask, TaskStatus
from memento.graph_diff import detect_graph_regressions
from memento.recovery import recover_dispatch_jobs
from memento.state import SQLiteStateStore
from memento.worker_pool import MockApiSandboxWorker


def test_api_sandbox_worker_protocol_submit_poll_cancel_collect() -> None:
    worker = MockApiSandboxWorker(worker_id="openhands-mock", sandbox_modes=("docker",))
    submitted = worker.submit({"task_id": "task_1", "prompt": "fix bug"})
    assert submitted["status"] == "submitted"
    assert submitted["native_session_ref"]["kind"] == "api_worker_job"

    running = worker.poll(submitted["job_id"])
    assert running["status"] == "running"

    collected = worker.collect(submitted["job_id"], result={"patch_ref": "file://patch.diff", "exit_code": 0})
    assert collected["status"] == "completed"
    assert collected["result"]["patch_ref"] == "file://patch.diff"

    cancelled = worker.cancel(submitted["job_id"])
    assert cancelled["status"] == "completed"


def test_multi_executor_competition_selects_verified_safer_patch() -> None:
    candidates = [
        {
            "dispatch_id": "dispatch_fast",
            "executor": "codex",
            "verification_passed": False,
            "unsafe_paths": [],
            "diff_size": 20,
            "graph_risk": "low",
        },
        {
            "dispatch_id": "dispatch_safe",
            "executor": "aider",
            "verification_passed": True,
            "unsafe_paths": [],
            "diff_size": 35,
            "graph_risk": "low",
        },
        {
            "dispatch_id": "dispatch_risky",
            "executor": "goose",
            "verification_passed": True,
            "unsafe_paths": [".env"],
            "diff_size": 5,
            "graph_risk": "high",
        },
    ]
    decision = select_patch(candidates, policy={"require_approval_for_high_risk": True})
    assert decision["selected_dispatch_id"] == "dispatch_safe"
    assert decision["preserved_evidence_trails"] == ["dispatch_fast", "dispatch_safe", "dispatch_risky"]
    assert decision["rejected"]["dispatch_risky"]["requires_approval"] is True


def test_graph_diff_regression_warnings_are_advisory_by_default() -> None:
    before = {"god_nodes": ["src/api.py"], "cross_community_edges": 1, "modularity": 0.8}
    after = {"god_nodes": ["src/api.py", "src/global.py"], "cross_community_edges": 4, "modularity": 0.5}
    diff = detect_graph_regressions(before, after)
    assert diff["status"] == "warning"
    assert diff["blocking"] is False
    assert "new_god_node" in diff["warnings"]
    assert "cross_community_edges_increased" in diff["warnings"]


def test_external_ci_evidence_and_release_approval_gate(tmp_path: Path) -> None:
    store = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    run = store.create_run(goal="release", workspace=str(tmp_path))
    ci = record_external_check(
        store,
        run_id=run.id,
        provider="github_actions",
        payload={"run_id": 123, "status": "completed", "conclusion": "success", "url": "https://ci.example/run/123"},
    )
    approval = record_approval(
        store,
        run_id=run.id,
        actor="c",
        scope={"kind": "release", "id": run.id},
        prompt="Approve release?",
        response="approved",
    )
    assert ci.type == "external_check"
    assert ci.trust_level == "trusted"
    assert approval.type == "user_approval"
    assert release_gate_satisfied(store, run.id, required_checks=("github_actions",), required_approvals=1)["ok"] is True


def test_negative_approval_response_does_not_satisfy_release_gate(tmp_path: Path) -> None:
    store = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    run = store.create_run(goal="release", workspace=str(tmp_path))
    record_approval(
        store,
        run_id=run.id,
        actor="c",
        scope={"kind": "release", "id": run.id},
        prompt="Approve release?",
        response="I do not approve this release",
    )
    gate = release_gate_satisfied(store, run.id, required_approvals=1)
    assert gate["ok"] is False
    assert gate["missing_approvals"] == 1


def test_recover_long_running_jobs_from_canonical_state(tmp_path: Path) -> None:
    store = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    run = store.create_run(goal="recover", workspace=str(tmp_path))
    task = store.save_task(
        MementoTask(
            run_id=run.id,
            title="Long job",
            description="Resume from bundle",
            status=TaskStatus.IN_PROGRESS,
            verification_policy={"required_commands": ["python -m pytest -q"]},
            acceptance_criteria=("tests pass",),
        )
    )
    jobs = recover_dispatch_jobs(store, run.id)
    assert jobs[0]["task_id"] == task.id
    assert jobs[0]["recovery_mode"] == "regenerate_context_bundle"
    assert jobs[0]["native_session_required"] is False


def test_v3_ci_approval_release_gate_commands_persist_evidence(tmp_path: Path) -> None:
    service = CommandService()
    workspace = str(tmp_path)
    run = service.start({"workspace": workspace, "goal": "release candidate"})["run"]

    ci = service.record_external_check(
        {
            "workspace": workspace,
            "run_id": run["id"],
            "provider": "github_actions",
            "external_run_id": "123",
            "status": "completed",
            "conclusion": "success",
            "url": "https://ci.example/run/123",
        }
    )
    approval = service.record_approval(
        {
            "workspace": workspace,
            "run_id": run["id"],
            "actor": "c",
            "scope_kind": "release",
            "scope_id": run["id"],
            "prompt": "Approve release?",
            "response": "approved",
        }
    )
    gate = service.release_gate(
        {
            "workspace": workspace,
            "run_id": run["id"],
            "required_checks": ["github_actions"],
            "required_approvals": 1,
        }
    )

    assert ci["ok"] is True
    assert ci["command"] == "record-external-check"
    assert ci["evidence"]["type"] == "external_check"
    assert ci["evidence"]["status"] == "passed"
    assert approval["ok"] is True
    assert approval["command"] == "record-approval"
    assert approval["evidence"]["type"] == "user_approval"
    assert approval["evidence"]["status"] == "passed"
    assert gate == {
        "ok": True,
        "command": "release-gate",
        "missing_checks": [],
        "missing_approvals": 0,
        "approval_count": 1,
    }

    reopened = CommandService()
    status = reopened.status({"workspace": workspace, "run_id": run["id"]})
    assert [item["type"] for item in status["evidence"]] == ["external_check", "user_approval"]
    assert [event["action"] for event in status["audit"]][-3:] == [
        "external_check.recorded",
        "approval.recorded",
        "release_gate.checked",
    ]


def test_v3_release_gate_command_rejects_negative_approval_substrings(tmp_path: Path) -> None:
    service = CommandService()
    workspace = str(tmp_path)
    run = service.start({"workspace": workspace, "goal": "release candidate"})["run"]
    service.record_approval(
        {
            "workspace": workspace,
            "run_id": run["id"],
            "actor": "c",
            "scope_kind": "release",
            "scope_id": run["id"],
            "prompt": "Approve release?",
            "response": "I do not approve this release",
        }
    )

    gate = service.release_gate({"workspace": workspace, "run_id": run["id"], "required_approvals": 1})

    assert gate["ok"] is False
    assert gate["missing_approvals"] == 1


def test_v3_recover_jobs_command_exposes_restart_plan(tmp_path: Path) -> None:
    service = CommandService()
    workspace = str(tmp_path)
    run = service.start({"workspace": workspace, "goal": "recover"})["run"]
    store = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    task = store.save_task(
        MementoTask(
            run_id=run["id"],
            title="Long job",
            description="Resume from bundle",
            status=TaskStatus.IN_PROGRESS,
            verification_policy={"required_commands": ["python -m pytest -q"]},
        )
    )

    result = service.recover_jobs({"workspace": workspace, "run_id": run["id"]})

    assert result["ok"] is True
    assert result["command"] == "recover-jobs"
    assert result["jobs"] == [
        {
            "task_id": task.id,
            "status": "in_progress",
            "recovery_mode": "regenerate_context_bundle",
            "native_session_required": False,
            "verification_policy": {"required_commands": ["python -m pytest -q"]},
        }
    ]
