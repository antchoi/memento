from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from memento.commands import CommandService
from memento.domain import MementoTask
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


def test_peer_executor_classifies_successful_verified_changes(tmp_path: Path) -> None:
    store, run_id, task_id = _run_with_task(tmp_path)
    payload = build_worker_payload(store.get_run(run_id), store.get_task(task_id))

    def runner(_command: list[str], _cwd: Path) -> dict[str, object]:
        return {
            "exit_code": 0,
            "stdout": "changed src/app.py",
            "stderr": "",
            "changed_files": ["src/app.py"],
            "verification": {"ok": True, "commands": ["python -m pytest -q"]},
        }

    result = PeerExecutorAdapter(runner=runner).dispatch(
        ExecutorDispatchRequest(payload=payload, executor="codex", invoke=True)
    )

    assert result["ok"] is True
    assert result["executor_invoked"] is True
    assert result["execution"]["status"] == "verified"
    assert result["execution"]["accepted"] is True
    assert result["execution"]["changed_files"] == ["src/app.py"]
    assert result["execution"]["verification"]["ok"] is True


def test_peer_executor_rejects_no_change_self_reports(tmp_path: Path) -> None:
    store, run_id, task_id = _run_with_task(tmp_path)
    payload = build_worker_payload(store.get_run(run_id), store.get_task(task_id))

    def runner(_command: list[str], _cwd: Path) -> dict[str, object]:
        return {"exit_code": 0, "stdout": "I completed it", "stderr": "", "changed_files": []}

    result = PeerExecutorAdapter(runner=runner).dispatch(
        ExecutorDispatchRequest(payload=payload, executor="aider", invoke=True)
    )

    assert result["ok"] is True
    assert result["executor_invoked"] is True
    assert result["execution"] == {
        "status": "no_changes",
        "accepted": False,
        "failure_category": "no_changes",
        "changed_files": [],
        "verification": {"ok": False, "reason": "no_verification_result"},
    }


def test_peer_executor_classifies_timeout_and_verification_failure(tmp_path: Path) -> None:
    store, run_id, task_id = _run_with_task(tmp_path)
    payload = build_worker_payload(store.get_run(run_id), store.get_task(task_id))

    timeout = PeerExecutorAdapter(runner=lambda _command, _cwd: {"timeout": True}).dispatch(
        ExecutorDispatchRequest(payload=payload, executor="codex", invoke=True)
    )
    assert timeout["execution"]["status"] == "timeout"
    assert timeout["execution"]["accepted"] is False
    assert timeout["execution"]["failure_category"] == "timeout"

    verification_failed = PeerExecutorAdapter(
        runner=lambda _command, _cwd: {
            "exit_code": 0,
            "changed_files": ["src/app.py"],
            "verification": {"ok": False, "failed_commands": ["python -m pytest -q"]},
        }
    ).dispatch(ExecutorDispatchRequest(payload=payload, executor="goose", invoke=True))
    assert verification_failed["execution"]["status"] == "verification_failed"
    assert verification_failed["execution"]["accepted"] is False
    assert verification_failed["execution"]["failure_category"] == "verification_failed"


def test_route_override_preserves_hard_safety(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("memento.routing.shutil.which", lambda command: f"/bin/{command}")
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


def test_unavailable_external_executors_are_not_selected_or_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("memento.routing.shutil.which", lambda _command: None)
    _store, run_id, task_id = _run_with_task(tmp_path)
    svc = CommandService()

    route = svc.route_task({"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id})
    assert route["ok"] is True
    assert route["decision"]["selected_executor"] == "hermes-direct"
    assert route["decision"]["rejected_executors"]["aider"]["reason"] == "executor_unavailable"

    override = svc.route_task(
        {"workspace": str(tmp_path), "run_id": run_id, "task_id": task_id, "executor": "aider"}
    )
    assert override["decision"]["user_override"] == {
        "requested_executor": "aider",
        "honored": False,
        "reason": "blocked_by_hard_safety_or_capability_filter",
    }
    assert override["decision"]["selected_executor"] == "hermes-direct"


def test_isolated_worktree_creation_blocks_dirty_canonical_workspace(tmp_path: Path) -> None:
    _store, run_id, task_id = _run_with_task(tmp_path)
    subprocess.run(["git", "init", "-b", "feature"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Memento Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, check=True, capture_output=True)
    tracked.write_text("dirty", encoding="utf-8")

    svc = CommandService()
    outbox_path = tmp_path / ".memento" / "blocked-outbox.jsonl"

    dispatch = svc.dispatch_task(
        {
            "workspace": str(tmp_path),
            "run_id": run_id,
            "task_id": task_id,
            "executor": "aider",
            "isolated_worktree": True,
            "create_worktree": True,
            "outbox_path": str(outbox_path),
        }
    )

    assert dispatch["ok"] is False
    assert dispatch["error"] == "dirty_worktree"
    assert dispatch["worktree"]["created"] is False
    assert not outbox_path.exists()


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
    task = MementoTask(run_id="run_1", title="Task", description="desc")
    plan = isolated_worktree_plan(tmp_path, task)
    assert plan["isolation"] == "git_worktree"
    assert task.id in plan["branch"]
    assert str(tmp_path / ".memento" / "worktrees") in plan["path"]
