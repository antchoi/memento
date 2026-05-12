"""External CI evidence helpers."""

from __future__ import annotations

from typing import Any

from .domain import Evidence
from .state import SQLiteStateStore


def record_external_check(
    store: SQLiteStateStore,
    *,
    run_id: str,
    provider: str,
    payload: dict[str, Any],
) -> Evidence:
    conclusion = str(payload.get("conclusion") or payload.get("status") or "unknown")
    evidence = Evidence(
        run_id=run_id,
        kind="external_check",
        type="external_check",
        summary=f"{provider} external check {conclusion}",
        uri=payload.get("url"),
        trust_level="trusted",
        status="passed" if conclusion == "success" else "failed",
        source={"kind": "external_api", "provider": provider},
        content_ref={"kind": "external_check", "provider": provider, "payload": payload},
    )
    return store.save_evidence(evidence)
