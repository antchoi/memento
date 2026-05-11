"""Command handlers for the sisyphus-hermes plugin and developer CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .domain import Evidence, GateKind, GateStatus, ReviewGate, RunStatus, SisyphusPlan, utc_now
from .state import SQLiteStateStore

REQUIRED_COMMANDS = (
    "init",
    "start",
    "plan",
    "approve-plan",
    "status",
    "pause",
    "resume",
    "cancel",
    "review",
    "report",
    "doctor",
)


def command_names() -> tuple[str, ...]:
    return REQUIRED_COMMANDS


class CommandService:
    """Shared service layer for plugin/slash handlers and local CLI smoke tests."""

    def __init__(self, store: SQLiteStateStore | None = None) -> None:
        self.store = store

    def _store_for(self, args: dict[str, Any]) -> SQLiteStateStore:
        if self.store is not None:
            return self.store
        workspace = args.get("workspace") or Path.cwd()
        return SQLiteStateStore(SQLiteStateStore.default_path(workspace))

    def handler_for(self, name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        attr = name.replace("-", "_")
        handler = getattr(self, attr, None)
        if handler is None or name not in REQUIRED_COMMANDS:
            raise KeyError(f"unknown command: {name}")
        return handler

    def init(self, args: dict[str, Any]) -> dict[str, Any]:
        workspace = Path(args.get("workspace") or Path.cwd())
        db_path = SQLiteStateStore.default_path(workspace)
        SQLiteStateStore(db_path)
        return {
            "ok": True,
            "command": "init",
            "workspace": str(workspace),
            "state": {"backend": "sqlite", "path": str(db_path)},
        }

    def doctor(self, args: dict[str, Any]) -> dict[str, Any]:
        workspace = Path(args.get("workspace") or Path.cwd())
        db_path = SQLiteStateStore.default_path(workspace)
        store = SQLiteStateStore(db_path)
        return {
            "ok": True,
            "command": "doctor",
            "plugin": "sisyphus-hermes",
            "workspace": str(workspace),
            "checks": {
                "sqlite": "ok" if store.path.exists() else "missing",
                "kanban": "optional_unavailable_using_sqlite",
                "opencode_dependency": "not_required",
            },
        }

    def start(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = args.get("run_id")
        if run_id:
            run = store.get_run(run_id)
            if run is None:
                return {"ok": False, "error": "run_not_found", "run_id": run_id}
            if not args.get("allow_spike") and store.canonical_plan(run.id) is None:
                store.append_audit(
                    run.id,
                    actor="sisyphus_lifecycle_worker",
                    action="execution.blocked",
                    summary="Canonical plan required before execution.",
                )
                return {"ok": False, "error": "canonical_plan_required", "run": run.to_record()}
            run = store.set_run_status(run.id, RunStatus.ACTIVE)
            store.append_audit(run.id, actor="sisyphus_lifecycle_worker", action="run.started")
            return {"ok": True, "command": "start", "run": run.to_record()}

        goal = str(args.get("goal") or "").strip()
        workspace = str(args.get("workspace") or Path.cwd())
        if not goal:
            return {"ok": False, "error": "goal_required"}
        run = store.create_run(goal=goal, workspace=workspace, actor=str(args.get("actor") or "founder_user"))
        store.append_audit(run.id, actor="founder_user", action="run.created", summary=goal)
        if args.get("allow_spike"):
            store.append_audit(
                run.id,
                actor="sisyphus_lifecycle_worker",
                action="execution.spike_allowed",
                summary="Bounded spike allowed without canonical plan.",
            )
        return {"ok": True, "command": "start", "run": run.to_record()}

    def plan(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        plan = store.save_plan(
            SisyphusPlan(
                run_id=run_id,
                title=str(args.get("title") or "Draft plan"),
                body=str(args.get("body") or ""),
                assumptions=tuple(args.get("assumptions") or ()),
                risks=tuple(args.get("risks") or ()),
                acceptance_criteria=tuple(args.get("acceptance_criteria") or ()),
            )
        )
        store.append_audit(run_id, actor="metis_planner", action="plan.created", summary=plan.title)
        return {"ok": True, "command": "plan", "plan": plan.to_record()}

    def approve_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        plan = store.approve_plan(run_id, str(args["plan_id"]))
        reviewer = str(args.get("reviewer") or "founder_user")
        store.append_audit(
            run_id,
            actor=reviewer,
            action="plan.approved",
            summary=f"Canonical plan approved: {plan.title}",
            payload={"plan_id": plan.id},
        )
        store.save_gate(
            ReviewGate(
                run_id=run_id,
                kind=GateKind.PLAN_REVIEW,
                status=GateStatus.PASSED,
                summary="Plan promoted to canonical.",
                reviewer=reviewer,
            )
        )
        return {"ok": True, "command": "approve-plan", "plan": plan.to_record()}

    def status(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run = store.get_run(str(args.get("run_id"))) if args.get("run_id") else store.latest_run()
        if run is None:
            return {"ok": False, "error": "run_not_found"}
        return {
            "ok": True,
            "command": "status",
            "run": run.to_record(),
            "plans": [p.to_record() for p in store.list_plans(run.id)],
            "tasks": [t.to_record() for t in store.list_tasks(run.id)],
            "gates": [g.to_record() for g in store.list_gates(run.id)],
            "evidence": [e.to_record() for e in store.list_evidence(run.id)],
            "audit": [a.to_record() for a in store.list_audit(run.id)],
        }

    def pause(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._set_status(args, RunStatus.PAUSED, "run.paused")

    def resume(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._set_status(args, RunStatus.ACTIVE, "run.resumed")

    def cancel(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._set_status(args, RunStatus.CANCELLED, "run.cancelled")

    def _set_status(self, args: dict[str, Any], status: RunStatus, action: str) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        run = store.set_run_status(run_id, status)
        store.append_audit(
            run_id,
            actor="sisyphus_lifecycle_worker",
            action=action,
            summary=str(args.get("reason") or ""),
        )
        return {"ok": True, "command": action.split(".")[-1], "run": run.to_record()}

    def review(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        kind = GateKind(str(args.get("kind") or GateKind.QUALITY_REVIEW.value))
        status = GateStatus(str(args.get("status") or GateStatus.PASSED.value))
        gate = store.save_gate(
            ReviewGate(
                run_id=run_id,
                kind=kind,
                status=status,
                summary=str(args.get("summary") or ""),
                reviewer=str(args.get("reviewer") or "momus_reviewer"),
            )
        )
        action = "gate.passed" if status == GateStatus.PASSED else "gate.failed"
        store.append_audit(run_id, actor=gate.reviewer, action=action, summary=gate.summary)
        if status == GateStatus.FAILED:
            store.set_run_status(run_id, RunStatus.BLOCKED)
        return {"ok": True, "command": "review", "gate": gate.to_record()}

    def report(self, args: dict[str, Any]) -> dict[str, Any]:
        from .reporting import render_report

        status = self.status(args)
        return {**status, "command": "report", "text": render_report(status), "generated_at": utc_now()}

    def add_evidence(self, run_id: str, *, kind: str, summary: str, uri: str | None = None) -> Evidence:
        store = self._store_for({})
        evidence = store.save_evidence(Evidence(run_id=run_id, kind=kind, summary=summary, uri=uri))
        store.append_audit(run_id, actor="hephaestus_executor", action="evidence.added", summary=summary)
        return evidence
