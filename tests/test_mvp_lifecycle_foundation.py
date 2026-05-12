from __future__ import annotations

from pathlib import Path

from memento.commands import CommandService
from memento.domain import Evidence, SisyphusTask, TaskStatus
from memento.memory import filter_memory_writeback
from memento.state import SQLiteStateStore


def test_task_graph_ready_cycle_and_restart(tmp_path: Path) -> None:
    store = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    run = store.create_run(goal="build mvp", workspace=str(tmp_path))
    plan = store.save_plan_for_test(run.id, title="Plan", body="Plan body")
    store.approve_plan(run.id, plan.id)

    a = store.save_task(
        SisyphusTask(
            run_id=run.id,
            title="A",
            description="first",
            status=TaskStatus.ACCEPTED,
            acceptance_criteria=("done",),
            verification_policy={"required_evidence": ["qa_verdict"]},
        )
    )
    b = store.save_task(
        SisyphusTask(
            run_id=run.id,
            title="B",
            description="second",
            dependencies=(a.id,),
            acceptance_criteria=("done",),
            verification_policy={"required_evidence": ["qa_verdict"]},
        )
    )
    assert store.ready_tasks(run.id)[0].id == b.id

    store.save_task(SisyphusTask(run_id=run.id, title="C", description="cycle", dependencies=("missing",)))
    assert store.validate_task_graph(run.id)["ok"] is False

    restarted = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    assert restarted.get_run(run.id) is not None
    assert {task.id for task in restarted.list_tasks(run.id)} >= {a.id, b.id}


def test_context_bundle_immutable_and_route_preview(tmp_path: Path) -> None:
    svc = CommandService()
    start = svc.start({"workspace": str(tmp_path), "goal": "route task"})
    run_id = start["run"]["id"]
    plan = svc.plan({"workspace": str(tmp_path), "run_id": run_id, "title": "Plan", "body": "Do it"})
    svc.approve_plan({"workspace": str(tmp_path), "run_id": run_id, "plan_id": plan["plan"]["id"]})
    event = svc.enqueue_event(
        {
            "workspace": str(tmp_path),
            "run_id": run_id,
            "title": "Implement bounded thing",
            "description": "Change code safely",
            "acceptance_criteria": ["has tests"],
            "verification_policy": {"required_commands": ["python -m pytest -q"]},
        }
    )
    task_id = event["task"]["id"]

    bundle = svc.context_bundle({"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id})
    assert bundle["ok"] is True
    assert bundle["bundle"]["immutable"] is True
    bundle_path = Path(bundle["bundle_path"])
    assert bundle_path.exists()
    first_hash = bundle["bundle"]["bundle_hash"]
    assert first_hash == svc.context_bundle({"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id})["bundle"]["bundle_hash"]

    route = svc.route_task({"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id})
    assert route["ok"] is True
    assert route["decision"]["selected_executor"] in {"codex", "hermes-direct", "aider"}
    assert route["decision"]["auto_dispatch"] is False
    assert route["decision"]["rejected_executors"]


def test_append_only_evidence_and_verification_verdict(tmp_path: Path) -> None:
    store = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    run = store.create_run(goal="verify", workspace=str(tmp_path))
    plan = store.save_plan_for_test(run.id, title="Plan", body="Plan body")
    store.approve_plan(run.id, plan.id)
    task = store.save_task(
        SisyphusTask(
            run_id=run.id,
            title="Task",
            description="Needs test evidence",
            acceptance_criteria=("tests pass",),
            verification_policy={"required_evidence": ["test_result"]},
        )
    )
    old = store.save_evidence(
        Evidence(run_id=run.id, type="test_result", kind="test_result", summary="old fail", status="failed", task_id=task.id)
    )
    new = store.supersede_evidence(old.id, summary="new pass", status="passed")
    assert old.id != new.id
    assert store.get_evidence(old.id).status == "failed"
    assert store.get_evidence(new.id).relationships["supersedes"] == [old.id]

    verdict = CommandService(store).verify_task({"run_id": run.id, "task_id": task.id})
    assert verdict["ok"] is True
    assert verdict["verdict"] == "accepted"
    assert store.get_task(task.id).status == TaskStatus.ACCEPTED
    assert any(ev.type == "qa_verdict" for ev in store.list_evidence(run.id))


def test_graphify_and_memory_hooks(tmp_path: Path) -> None:
    svc = CommandService()
    start = svc.start({"workspace": str(tmp_path), "goal": "graph and memory"})
    run_id = start["run"]["id"]
    graph_status = svc.graph_status({"workspace": str(tmp_path), "run_id": run_id})
    assert graph_status["ok"] is True
    assert graph_status["graphify"]["state"] in {"missing", "current", "stale", "update_failed"}

    graph_update = svc.graph_update(
        {
            "workspace": str(tmp_path),
            "run_id": run_id,
            "mock_graphify": True,
            "changed_files": ["src/example.py"],
        }
    )
    assert graph_update["ok"] is True
    assert graph_update["evidence"]["type"] == "graph_update"

    assert filter_memory_writeback("Task task_123 completed successfully") is None
    assert filter_memory_writeback("Repo uses python -m pytest -q for backend verification") is not None

    prefetch = svc.memory_prefetch({"workspace": str(tmp_path), "run_id": run_id, "query": "pytest"})
    assert prefetch["ok"] is True
    writeback = svc.memory_writeback(
        {"workspace": str(tmp_path), "run_id": run_id, "lesson": "Repo uses python -m pytest -q for backend verification"}
    )
    assert writeback["ok"] is True
    assert writeback["accepted"] is True
