"""Graph-diff architecture regression detection."""

from __future__ import annotations

from typing import Any


def detect_graph_regressions(before: dict[str, Any], after: dict[str, Any], *, blocking: bool = False) -> dict[str, Any]:
    warnings: list[str] = []
    before_gods = set(before.get("god_nodes") or [])
    after_gods = set(after.get("god_nodes") or [])
    if after_gods - before_gods:
        warnings.append("new_god_node")
    before_edges = int(before.get("cross_community_edges") or 0)
    after_edges = int(after.get("cross_community_edges") or 0)
    if after_edges > before_edges:
        warnings.append("cross_community_edges_increased")
    before_mod = float(before.get("modularity") or 0)
    after_mod = float(after.get("modularity") or 0)
    if before_mod and after_mod < before_mod:
        warnings.append("modularity_decreased")
    risk = "high" if warnings else "low"
    return {
        "status": "warning" if warnings else "ok",
        "warnings": warnings,
        "risk": risk,
        "blocking": bool(blocking and warnings),
        "advisory": not blocking,
        "before": before,
        "after": after,
    }
