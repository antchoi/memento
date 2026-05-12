"""Isolated worktree planning and safe creation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .domain import SisyphusTask


def isolated_worktree_plan(workspace: str | Path, task: SisyphusTask) -> dict[str, Any]:
    root = Path(workspace)
    branch = f"memento/{task.id}"
    path = root / ".sisyphus" / "worktrees" / task.id
    return {
        "isolation": "git_worktree",
        "branch": branch,
        "path": str(path),
        "created": False,
        "executor_invoked": False,
    }


def create_isolated_worktree(workspace: str | Path, task: SisyphusTask, *, dry_run: bool = True) -> dict[str, Any]:
    plan = isolated_worktree_plan(workspace, task)
    if dry_run:
        return {**plan, "dry_run": True}
    root = Path(workspace)
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
