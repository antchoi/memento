"""Isolated worktree planning and safe creation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .domain import MementoTask
from .safety import GitPreflight, run_git_preflight


def isolated_worktree_plan(workspace: str | Path, task: MementoTask) -> dict[str, Any]:
    root = Path(workspace)
    branch = f"memento/{task.id}"
    path = root / ".memento" / "worktrees" / task.id
    return {
        "isolation": "git_worktree",
        "branch": branch,
        "path": str(path),
        "created": False,
        "executor_invoked": False,
    }


def _preflight_record(preflight: GitPreflight) -> dict[str, Any]:
    return {
        "workspace": preflight.workspace,
        "ok": preflight.ok,
        "branch": preflight.branch,
        "dirty_files": list(preflight.dirty_files),
        "untracked_files": list(preflight.untracked_files),
        "remotes": list(preflight.remotes),
        "blockers": list(preflight.blockers),
    }


def _primary_worktree_blocker(preflight: GitPreflight) -> str:
    for blocker in ("dirty_worktree", "untracked_files", "not_git_repository", "detached_head", "protected_branch"):
        if blocker in preflight.blockers:
            return blocker
    return preflight.blockers[0] if preflight.blockers else "worktree_preflight_failed"


def create_isolated_worktree(workspace: str | Path, task: MementoTask, *, dry_run: bool = True) -> dict[str, Any]:
    plan = isolated_worktree_plan(workspace, task)
    if dry_run:
        return {**plan, "dry_run": True}
    root = Path(workspace)
    preflight = run_git_preflight(root)
    if not preflight.ok:
        return {
            **plan,
            "dry_run": False,
            "created": False,
            "error": _primary_worktree_blocker(preflight),
            "preflight": _preflight_record(preflight),
        }
    Path(plan["path"]).parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "worktree", "add", "-b", plan["branch"], plan["path"], "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        **plan,
        "dry_run": False,
        "created": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }
