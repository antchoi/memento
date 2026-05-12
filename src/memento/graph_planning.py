"""Graphify-derived advisory task/dependency proposals."""

from __future__ import annotations

from typing import Any


def propose_tasks_from_graph(graph: dict[str, Any], *, goal: str) -> dict[str, Any]:
    """Create review-only task proposals from mocked Graphify communities."""

    proposed: list[dict[str, Any]] = []
    dependencies: list[dict[str, str]] = []
    communities = list(graph.get("communities") or [])
    for community in communities:
        label = str(community.get("label") or community.get("id") or "Graph community")
        files = list(community.get("files") or [])
        proposed.append(
            {
                "title": f"Update {label} for {goal}",
                "kind": "implementation",
                "context_refs": files,
                "review_required": True,
            }
        )
    edges = list(graph.get("edges") or [])
    if len(proposed) >= 2:
        dependencies.append({"from": proposed[0]["title"], "to": proposed[1]["title"], "basis": "community ordering"})
    for edge in edges:
        dependencies.append(
            {
                "from": str(edge.get("target")),
                "to": str(edge.get("source")),
                "basis": str(edge.get("relation") or "graph edge"),
            }
        )
    return {
        "review_status": "proposed",
        "proposed_tasks": proposed,
        "dependencies": dependencies,
        "graph_basis": {
            "community_count": len(communities),
            "god_nodes": list(graph.get("god_nodes") or []),
            "edge_count": len(edges),
        },
    }
