"""Canonical context bundle generation for stateless executor invocations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .domain import SisyphusRun, SisyphusTask, utc_now
from .state import SQLiteStateStore


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def bundle_dir(workspace: str | Path) -> Path:
    path = Path(workspace) / ".sisyphus" / "bundles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_context_bundle(
    *,
    store: SQLiteStateStore,
    run: SisyphusRun,
    task: SisyphusTask,
    memory_summary: str | None = None,
    graph_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = store.canonical_plan(run.id)
    deps = [store.get_task(dep) for dep in task.dependencies]
    payload: dict[str, Any] = {
        "run_id": run.id,
        "session_id": run.id,
        "task_id": task.id,
        "goal": {"summary": run.goal},
        "approved_plan": {
            "plan_id": plan.id if plan else None,
            "summary": plan.body if plan else "",
            "title": plan.title if plan else None,
        },
        "task": {
            "title": task.title,
            "description": task.description,
            "kind": task.kind,
            "risk": task.risk,
            "acceptance_criteria": list(task.acceptance_criteria),
            "verification_policy": task.verification_policy,
        },
        "dependencies": [
            {
                "task_id": dep.id,
                "title": dep.title,
                "status": dep.status.value,
                "evidence_refs": list(dep.evidence_refs),
            }
            for dep in deps
            if dep is not None
        ],
        "repo": {
            "root": run.workspace,
            "relevant_files": list(task.context_refs),
        },
        "constraints": {
            "forbidden_paths": [".env", "secrets/**"],
            "destructive_git": "forbidden",
            "executor_native_session_required": False,
        },
        "memory_context": {"summary": memory_summary or ""},
        "graph_context": graph_context or {"state": "missing", "relevant_subgraph": {}},
        "output_contract": {
            "must_report": ["changed_files", "commands_run", "test_results", "unresolved_issues", "assumptions"],
            "summary_is_advisory": True,
        },
        "created_at": utc_now(),
        "immutable": True,
    }
    digest = hashlib.sha256(_stable_json({k: v for k, v in payload.items() if k != "created_at"}).encode()).hexdigest()
    payload["id"] = f"bundle_{digest[:12]}"
    payload["bundle_hash"] = digest
    return payload


def write_context_bundle(workspace: str | Path, bundle: dict[str, Any]) -> Path:
    path = bundle_dir(workspace) / f"{bundle['id']}.json"
    if not path.exists():
        path.write_text(json.dumps(bundle, sort_keys=True, indent=2), encoding="utf-8")
    return path
