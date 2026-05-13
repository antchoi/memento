"""Multi-executor competition and patch selection policy."""

from __future__ import annotations

from typing import Any


def _candidate_score(candidate: dict[str, Any]) -> int:
    score = 0
    if candidate.get("verification_passed"):
        score += 100
    if candidate.get("unsafe_paths"):
        score -= 100
    if candidate.get("graph_risk") == "high":
        score -= 25
    elif candidate.get("graph_risk") == "medium":
        score -= 10
    score -= min(int(candidate.get("diff_size") or 0), 100) // 10
    return score


def _graph_risk(candidate: dict[str, Any]) -> str:
    explicit = candidate.get("graph_risk")
    if explicit:
        return str(explicit)
    graph_diff = candidate.get("graph_diff") or {}
    if graph_diff.get("warnings") or graph_diff.get("risk") == "high":
        return "high"
    return "unknown"


def select_patch(candidates: list[dict[str, Any]], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or {}
    rejected: dict[str, dict[str, Any]] = {}
    eligible: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        dispatch_id = str(candidate["dispatch_id"])
        graph_risk = _graph_risk(candidate)
        requires_approval = bool(candidate.get("unsafe_paths")) or graph_risk == "high"
        if graph_risk == "high" and policy.get("require_approval_for_graph_regressions"):
            rejected[dispatch_id] = {"reason": "graph_regression_requires_approval", "requires_approval": True}
            continue
        if requires_approval and policy.get("require_approval_for_high_risk", True):
            rejected[dispatch_id] = {"reason": "high_risk_or_unsafe_paths", "requires_approval": True}
            continue
        if not candidate.get("verification_passed"):
            rejected[dispatch_id] = {"reason": "verification_failed", "requires_approval": False}
            continue
        eligible.append((_candidate_score(candidate), candidate))
    eligible.sort(key=lambda item: item[0], reverse=True)
    selected = eligible[0][1] if eligible else None
    approval_required = any(item.get("requires_approval") for item in rejected.values())
    return {
        "selected_dispatch_id": selected.get("dispatch_id") if selected else None,
        "selected_executor": selected.get("executor") if selected else None,
        "rejected": rejected,
        "preserved_evidence_trails": [str(candidate["dispatch_id"]) for candidate in candidates],
        "auto_merge_allowed": selected is not None,
        "approval_required": selected is None and approval_required,
    }
