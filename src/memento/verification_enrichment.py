"""Policy-safe verification enrichment from memory and graph signals."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def enrich_verification_policy(
    policy: dict[str, Any],
    *,
    memory_lessons: list[str] | tuple[str, ...] = (),
    graph_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a strengthened verification policy plus explainable reasons.

    Enrichment may add checks, but never removes caller-provided required checks.
    """

    enriched = deepcopy(policy)
    commands = list(enriched.get("required_commands") or [])
    reasons: list[str] = []
    lower_lessons = "\n".join(memory_lessons).lower()
    signals = graph_signals or {}

    if "smoke.py" in lower_lessons and "python scripts/smoke.py" not in commands:
        commands.append("python scripts/smoke.py")
        reasons.append("agentmemory lesson recommends smoke.py for affected integration/API contracts")
    if signals.get("touches_god_node") and "python -m pytest -q" not in commands:
        commands.append("python -m pytest -q")
        reasons.append("Graphify god-node signal requires full test suite")
    if signals.get("cross_community_change") and "python scripts/smoke.py" not in commands:
        commands.append("python scripts/smoke.py")
        reasons.append("Graphify cross-community change signal requires integration smoke")

    enriched["required_commands"] = commands
    return {"policy": enriched, "reasons": reasons, "weakened": False}
