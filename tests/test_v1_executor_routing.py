from __future__ import annotations

from pathlib import Path

from memento.commands import CommandService
from memento.domain import SisyphusTask
from memento.executors import ExecutorDispatchRequest, PeerExecutorAdapter
from memento.state import SQLiteStateStore
from memento.worktree import isolated_worktree_plan
from memento.workers import build_worker_payload


def _run_with_task(tmp_path: Path) -> tuple[SQLiteStateStore, str, str]:
    svc = CommandService()
    run = svc.start({"workspace": str(tmp_path), "goal": "v1"})["run"]
    plan = svc.plan({"workspace": str(tmp_path), "run_id": run["id"], "title": "Plan", "body": "Do v1"})
    svc.approve_plan({"workspace": str(tmp_path), "run_id": run["id"], "plan_id": plan["plan"]["id"]})
    task = svc.enqueue_event(
        {
            "workspace": str(tmp_path),
            "run_id": run["id"],
            "title": "Scoped edit",
            "description": "Edit selected files",
            "acceptance_criteria": ["tests pass"],
            "context_refs": ["src/app.py"],
            "verification_policy": {"required_commands": ["python -m pytest -q"]},
            "kind": "scoped_edit",
        }
    )["task"]
    return SQLiteStateStore(SQLiteStateStore.default_path(tmp_path)), run["id"], task["id"]


def test_peer_executor_builds_codex_and_aider_commands(tmp_path: Path) -> None:
    store, run_id, task_id = _run_with_task(tmp_path)
    run = store.get_run(run_id)
    task = store.get_task(task_id)
    payload = build_worker_payload(run, task)
    adapter = PeerExecutorAdapter()

    codex = adapter.command_for(ExecutorDispatchRequest(payload=payload, executor="codex"))
    aider = adapter.command_for(ExecutorDispatchRequest(payload=payload, executor="aider"))

    assert codex[:2] == ["codex", "exec"]
    assert aider[0] == "aider"
    assert "src/app.py" in aider
    assert "--message" in aider


def test_route_override_preserves_hard_safety(tmp_path: Path) -> None:
    _store, run_id, task_id = _run_with_task(tmp_path)
    svc = CommandService()
    blocked = svc.route_task(
        {"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id, "executor": "opencode"}
    )
    assert blocked["ok"] is True
    assert blocked["decision"]["user_override"]["honored"] is False
    assert blocked["decision"]["selected_executor"] != "opencode"

    honored = svc.route_task({"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id, "executor": "aider"})
    assert honored["decision"]["user_override"]["honored"] is True
    assert honored["decision"]["selected_executor"] == "aider"


def test_isolated_worktree_dispatch_metadata_and_graph_checkpoint(tmp_path: Path) -> None:
    _store, run_id, task_id = _run_with_task(tmp_path)
    svc = CommandService()
    route = svc.route_task({"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id, "executor": "aider"})
    assert route["decision"]["status"] == "proposed"

    dispatch = svc.dispatch_task(
        {
            "workspace": str(tmp_path),
            "run_id": run_id,
            "task_id": task_id,
            "executor": "aider",
            "isolated_worktree": True,
        }
    )
    assert dispatch["ok"] is True
    assert dispatch["worktree"]["isolation"] == "git_worktree"
    assert dispatch["executor_invoked"] is False

    claim = svc.claim_dispatch({"workspace": str(tmp_path), "dispatch_id": dispatch["dispatch_id"], "executor": "aider"})
    assert claim["ok"] is True
    complete = svc.complete_dispatch(
        {
            "workspace": str(tmp_path),
            "dispatch_id": dispatch["dispatch_id"],
            "summary": "done",
            "evidence_uri": "file://result",
            "changed_files": ["src/app.py"],
            "graphify_checkpoint": True,
            "mock_graphify": True,
        }
    )
    assert complete["ok"] is True
    assert complete["graph_update"]["evidence"]["type"] == "graph_update"


def test_isolated_worktree_plan_is_deterministic(tmp_path: Path) -> None:
    task = SisyphusTask(run_id="run_1", title="Task", description="desc")
    plan = isolated_worktree_plan(tmp_path, task)
    assert plan["isolation"] == "git_worktree"
    assert task.id in plan["branch"]
    assert str(tmp_path / ".sisyphus" / "worktrees") in plan["path"]
