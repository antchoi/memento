"""Budget-aware attempt/fallback evaluation."""

from __future__ import annotations

from typing import Any


def evaluate_budget(policy: dict[str, Any], *, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    max_attempts = policy.get("max_attempts_per_task")
    if max_attempts is not None and len(attempts) >= int(max_attempts):
        reasons.append("max_attempts_per_task")
    max_executors = policy.get("max_distinct_executors")
    if max_executors is not None and len({str(a.get("executor")) for a in attempts}) > int(max_executors):
        reasons.append("max_distinct_executors")
    allowed = not reasons
    return {
        "allowed": allowed,
        "status": "allowed" if allowed else "blocked",
        "reasons": reasons,
        "attempt_count": len(attempts),
        "distinct_executors": sorted({str(a.get("executor")) for a in attempts}),
    }
