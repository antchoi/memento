"""Approval and release gate helpers."""

from __future__ import annotations

from typing import Any

from .domain import Evidence
from .state import SQLiteStateStore


APPROVAL_RESPONSES = {"approved", "approve", "yes", "y", "ok", "승인", "승인함"}


def _is_positive_approval(response: str) -> bool:
    normalized = response.strip().lower().strip(".!?。")
    return normalized in APPROVAL_RESPONSES


def record_approval(
    store: SQLiteStateStore,
    *,
    run_id: str,
    actor: str,
    scope: dict[str, Any],
    prompt: str,
    response: str,
) -> Evidence:
    evidence = Evidence(
        run_id=run_id,
        kind="user_approval",
        type="user_approval",
        summary=f"Approval from {actor}: {response}",
        trust_level="trusted",
        status="passed" if _is_positive_approval(response) else "observed",
        source={"kind": "user", "actor": actor},
        content_ref={"kind": "approval", "scope": scope, "prompt": prompt, "response": response},
    )
    return store.save_evidence(evidence)


def release_gate_satisfied(
    store: SQLiteStateStore,
    run_id: str,
    *,
    required_checks: tuple[str, ...] = (),
    required_approvals: int = 0,
    graph_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    graph_policy = graph_policy or {}
    evidence = store.list_evidence(run_id)
    checks = {
        item.source.get("provider")
        for item in evidence
        if item.type == "external_check" and item.status == "passed"
    }
    approvals = [item for item in evidence if item.type == "user_approval" and item.status == "passed"]
    missing_checks = [check for check in required_checks if check not in checks]
    missing_approvals = max(0, required_approvals - len(approvals))
    graph_warning_items = [item for item in evidence if item.type == "graph_diff" and item.status == "warning"]
    graph_warnings: list[str] = []
    for item in graph_warning_items:
        for warning in item.relationships.get("warnings") or []:
            if warning not in graph_warnings:
                graph_warnings.append(str(warning))
    graph_approval_required = bool(graph_policy.get("require_no_graph_warnings") and graph_warnings)
    return {
        "ok": not missing_checks and missing_approvals == 0 and not graph_approval_required,
        "missing_checks": missing_checks,
        "missing_approvals": missing_approvals,
        "approval_count": len(approvals),
        "graph_warnings": graph_warnings,
        "graph_approval_required": graph_approval_required,
    }
