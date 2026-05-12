"""MVP executor registry and explainable dry-run route decisions."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from .domain import MementoTask


@dataclass(frozen=True, kw_only=True)
class ExecutorCapability:
    name: str
    headless: bool
    auto_dispatch_allowed: bool
    preferred_task_kinds: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    command: tuple[str, ...] = ()
    requires_explicit_invoke: bool = True
    experimental: bool = False

    def to_record(self) -> dict[str, Any]:
        available = True if not self.command else shutil.which(self.command[0]) is not None
        return {
            "name": self.name,
            "headless": self.headless,
            "auto_dispatch_allowed": self.auto_dispatch_allowed,
            "preferred_task_kinds": list(self.preferred_task_kinds),
            "limitations": list(self.limitations),
            "command": list(self.command),
            "health": "available" if available else "unavailable",
            "requires_explicit_invoke": self.requires_explicit_invoke,
            "experimental": self.experimental,
        }


DEFAULT_EXECUTORS: dict[str, ExecutorCapability] = {
    "hermes-direct": ExecutorCapability(
        name="hermes-direct",
        headless=True,
        auto_dispatch_allowed=False,
        preferred_task_kinds=("verification", "integration", "fallback", "implementation"),
        limitations=("Runs inside Hermes; use evidence verification for acceptance.",),
        requires_explicit_invoke=False,
    ),
    "codex": ExecutorCapability(
        name="codex",
        headless=True,
        auto_dispatch_allowed=False,
        preferred_task_kinds=("implementation", "test", "refactor"),
        limitations=("MVP dry-run command construction only.",),
        command=("codex",),
        experimental=False,
    ),
    "aider": ExecutorCapability(
        name="aider",
        headless=True,
        auto_dispatch_allowed=False,
        preferred_task_kinds=("scoped_edit", "small_bugfix", "refactor"),
        limitations=("MVP dry-run command construction only; best with explicit files.",),
        command=("aider",),
    ),
    "opencode": ExecutorCapability(
        name="opencode",
        headless=False,
        auto_dispatch_allowed=False,
        preferred_task_kinds=("manual_handoff",),
        limitations=("Manual/experimental only due to Hermes compatibility instability.",),
        command=("opencode",),
        experimental=True,
    ),
    "goose": ExecutorCapability(
        name="goose",
        headless=True,
        auto_dispatch_allowed=False,
        preferred_task_kinds=("investigation", "general_agent_task", "implementation"),
        limitations=("Experimental OpenCode-like worker; requires healthcheck before real invoke.",),
        command=("goose",),
        experimental=True,
    ),
    "swe-agent": ExecutorCapability(
        name="swe-agent",
        headless=True,
        auto_dispatch_allowed=False,
        preferred_task_kinds=("issue_repair", "test_driven_fix"),
        limitations=("Requires sandbox availability for safe issue repair.",),
        command=("swe-agent",),
        experimental=True,
    ),
}


def route_task(
    task: MementoTask,
    *,
    graph_state: str = "missing",
    memory_summary: str = "",
    requested_executor: str | None = None,
    sandbox_available: bool = False,
) -> dict[str, Any]:
    rejected: dict[str, dict[str, str]] = {}
    candidates: list[tuple[int, str]] = []
    for name, capability in DEFAULT_EXECUTORS.items():
        record = capability.to_record()
        if name == "opencode":
            rejected[name] = {"reason": "manual_or_experimental_only"}
            continue
        if name == "swe-agent" and not sandbox_available:
            rejected[name] = {"reason": "sandbox_required_unavailable"}
            continue
        score = 10
        if task.kind in capability.preferred_task_kinds:
            score += 10
        if record["health"] == "unavailable" and name != "hermes-direct":
            score -= 3
        if task.risk == "high" and name != "hermes-direct":
            score -= 5
        if graph_state in {"stale", "update_failed"}:
            score -= 1
        if memory_summary and name in memory_summary.lower():
            score += 2
        candidates.append((score, name))
    candidates.sort(reverse=True)
    selected = candidates[0][1] if candidates else "hermes-direct"
    user_override = None
    if requested_executor:
        allowed = requested_executor in DEFAULT_EXECUTORS and requested_executor not in rejected
        if requested_executor == "opencode":
            allowed = False
        if task.risk == "high" and requested_executor not in {"hermes-direct"}:
            allowed = False
        user_override = {
            "requested_executor": requested_executor,
            "honored": allowed,
            "reason": "honored" if allowed else "blocked_by_hard_safety_or_capability_filter",
        }
        if allowed:
            selected = requested_executor
    fallback_chain = [name for _score, name in candidates if name != selected]
    if "hermes-direct" not in fallback_chain and selected != "hermes-direct":
        fallback_chain.append("hermes-direct")
    decision = {
        "status": "proposed",
        "selected_executor": selected,
        "auto_dispatch": False,
        "requires_user_approval": task.risk == "high",
        "fallback_chain": fallback_chain[:3],
        "rejected_executors": rejected,
        "reasons": [
            f"Task kind {task.kind!r} and risk {task.risk!r} matched MVP dry-run registry.",
            "External executors require explicit invoke; route-task preview never spawns processes.",
        ],
        "risk_adjustments": {
            "base_risk": task.risk,
            "graph_state": graph_state,
            "effective_risk": task.risk,
        },
        "context_profile": "code_snapshot" if task.context_refs else "compact",
        "executor_invoked": False,
    }
    if user_override:
        decision["user_override"] = user_override
    return decision


def registry_snapshot() -> dict[str, Any]:
    return {name: capability.to_record() for name, capability in DEFAULT_EXECUTORS.items()}
