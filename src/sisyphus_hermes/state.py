"""Durable local fallback state for Sisyphus Hermes.

The store intentionally uses only the Python standard library so core tests do
not depend on Hermes Kanban, OpenCode, or any external service.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar

from .domain import (
    AuditEvent,
    Evidence,
    PlanStatus,
    ReviewGate,
    RunStatus,
    SisyphusPlan,
    SisyphusRun,
    SisyphusTask,
    utc_now,
)

T = TypeVar("T")

_TABLE_MODELS = {
    "runs": SisyphusRun,
    "plans": SisyphusPlan,
    "tasks": SisyphusTask,
    "gates": ReviewGate,
    "evidence": Evidence,
    "audit": AuditEvent,
}


class SQLiteStateStore:
    """Project-local SQLite source of truth when Hermes Kanban is unavailable."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            for table in _TABLE_MODELS:
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id TEXT PRIMARY KEY,
                        run_id TEXT,
                        record_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_plans_run_id ON plans(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_run_id ON tasks(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gates_run_id ON gates(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_run_id ON evidence(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_run_id ON audit(run_id)")

    @staticmethod
    def default_path(workspace: str | Path) -> Path:
        return Path(workspace) / ".sisyphus" / "state.sqlite3"

    def _save(self, table: str, entity: Any, *, run_id: str | None = None) -> Any:
        record = entity.to_record()
        row_run_id = run_id or record.get("run_id") or record.get("id")
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} (id, run_id, record_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id=excluded.run_id,
                    record_json=excluded.record_json,
                    updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    row_run_id,
                    json.dumps(record, sort_keys=True),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return entity

    def _get(self, table: str, entity_id: str) -> Any | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT record_json FROM {table} WHERE id = ?", (entity_id,)
            ).fetchone()
        if row is None:
            return None
        model = _TABLE_MODELS[table]
        return model.from_record(json.loads(row["record_json"]))

    def _list(self, table: str, run_id: str) -> list[Any]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT record_json FROM {table} WHERE run_id = ? ORDER BY rowid",
                (run_id,),
            ).fetchall()
        model = _TABLE_MODELS[table]
        return [model.from_record(json.loads(row["record_json"])) for row in rows]

    def create_run(self, *, goal: str, workspace: str, actor: str = "founder_user") -> SisyphusRun:
        run = SisyphusRun(goal=goal, workspace=workspace, actor=actor)
        return self._save("runs", run, run_id=run.id)

    def save_run(self, run: SisyphusRun) -> SisyphusRun:
        return self._save("runs", run, run_id=run.id)

    def get_run(self, run_id: str) -> SisyphusRun | None:
        return self._get("runs", run_id)

    def latest_run(self) -> SisyphusRun | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT record_json FROM runs ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return SisyphusRun.from_record(json.loads(row["record_json"])) if row else None

    def save_plan(self, plan: SisyphusPlan) -> SisyphusPlan:
        return self._save("plans", plan)

    def get_plan(self, plan_id: str) -> SisyphusPlan | None:
        return self._get("plans", plan_id)

    def list_plans(self, run_id: str) -> list[SisyphusPlan]:
        return self._list("plans", run_id)

    def canonical_plan(self, run_id: str) -> SisyphusPlan | None:
        return next((p for p in self.list_plans(run_id) if p.status == PlanStatus.CANONICAL), None)

    def save_task(self, task: SisyphusTask) -> SisyphusTask:
        return self._save("tasks", task)

    def list_tasks(self, run_id: str) -> list[SisyphusTask]:
        return self._list("tasks", run_id)

    def save_gate(self, gate: ReviewGate) -> ReviewGate:
        return self._save("gates", gate)

    def list_gates(self, run_id: str) -> list[ReviewGate]:
        return self._list("gates", run_id)

    def save_evidence(self, evidence: Evidence) -> Evidence:
        return self._save("evidence", evidence)

    def list_evidence(self, run_id: str) -> list[Evidence]:
        return self._list("evidence", run_id)

    def append_audit(
        self,
        run_id: str,
        *,
        actor: str,
        action: str,
        summary: str = "",
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return self._save(
            "audit",
            AuditEvent(run_id=run_id, actor=actor, action=action, summary=summary, payload=payload or {}),
        )

    def list_audit(self, run_id: str) -> list[AuditEvent]:
        return self._list("audit", run_id)

    def set_run_status(self, run_id: str, status: RunStatus, *, current_plan_id: str | None = None) -> SisyphusRun:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        updated = replace(
            run,
            status=status,
            updated_at=utc_now(),
            current_plan_id=current_plan_id if current_plan_id is not None else run.current_plan_id,
        )
        return self.save_run(updated)

    def approve_plan(self, run_id: str, plan_id: str) -> SisyphusPlan:
        plan = self.get_plan(plan_id)
        if plan is None or plan.run_id != run_id:
            raise KeyError(f"plan not found for run: {plan_id}")
        for existing in self.list_plans(run_id):
            if existing.status == PlanStatus.CANONICAL and existing.id != plan_id:
                self.save_plan(replace(existing, status=PlanStatus.REJECTED, updated_at=utc_now()))
        canonical = replace(plan, status=PlanStatus.CANONICAL, updated_at=utc_now())
        self.save_plan(canonical)
        self.set_run_status(run_id, RunStatus.ACTIVE, current_plan_id=canonical.id)
        return canonical
