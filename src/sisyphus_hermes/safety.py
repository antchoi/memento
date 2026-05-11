"""Repository safety checks and destructive operation guardrails."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class OperationVerdict:
    command: str
    allowed: bool
    requires_approval: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class GitPreflight:
    workspace: str
    ok: bool
    branch: str | None = None
    dirty_files: tuple[str, ...] = ()
    untracked_files: tuple[str, ...] = ()
    remotes: tuple[str, ...] = ()
    blockers: tuple[str, ...] = field(default_factory=tuple)


_DESTRUCTIVE_PATTERNS = (
    ("git reset --hard", "git reset --hard rewrites worktree state"),
    ("git clean", "git clean deletes untracked files"),
    ("--force", "force push/rewrite requires explicit user approval"),
    ("git merge", "merge operations require explicit review gate approval"),
)

_PROTECTED_BRANCHES = {"main", "master", "production", "release"}


def classify_git_operation(command: str) -> OperationVerdict:
    normalized = " ".join(command.strip().lower().split())
    reasons = [reason for pattern, reason in _DESTRUCTIVE_PATTERNS if pattern in normalized]
    if normalized.startswith("git push") and any(f" {branch}" in normalized for branch in _PROTECTED_BRANCHES):
        reasons.append("direct main push is disabled by default")
    return OperationVerdict(
        command=command,
        allowed=not reasons,
        requires_approval=bool(reasons),
        reasons=tuple(reasons),
    )


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_git_preflight(workspace: str | Path) -> GitPreflight:
    root = Path(workspace)
    blockers: list[str] = []
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return GitPreflight(workspace=str(root), ok=False, blockers=("not_git_repository",))

    branch_proc = _git(root, "branch", "--show-current")
    branch = branch_proc.stdout.strip() or None
    if branch is None:
        blockers.append("detached_head")
    elif branch in _PROTECTED_BRANCHES:
        blockers.append("protected_branch")

    status_proc = _git(root, "status", "--porcelain")
    dirty: list[str] = []
    untracked: list[str] = []
    for line in status_proc.stdout.splitlines():
        path = line[3:] if len(line) > 3 else line
        if line.startswith("??"):
            untracked.append(path)
        else:
            dirty.append(path)
    if dirty:
        blockers.append("dirty_worktree")
    if untracked:
        blockers.append("untracked_files")

    remotes_proc = _git(root, "remote", "-v")
    remotes = tuple(sorted(set(remotes_proc.stdout.splitlines())))

    return GitPreflight(
        workspace=str(root),
        ok=not blockers,
        branch=branch,
        dirty_files=tuple(dirty),
        untracked_files=tuple(untracked),
        remotes=remotes,
        blockers=tuple(blockers),
    )


def render_worker_safety_constraints() -> str:
    return "\n".join(
        [
            "Safety constraints:",
            "- Do not run git reset --hard without explicit user approval.",
            "- Do not run git clean or delete untracked files without explicit user approval.",
            "- Do not force push or rewrite remote history.",
            "- Do not direct main push; work through reviewed branches only.",
            "- Do not merge without a passed review gate and explicit approval.",
            "- Record verification evidence and audit events for every guarded operation.",
        ]
    )
