"""Command handlers for the sisyphus-hermes plugin and developer CLI."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .domain import (
    Evidence,
    GateKind,
    GateStatus,
    ReviewGate,
    RunStatus,
    SisyphusPlan,
    TaskStatus,
    utc_now,
)
from .events import enqueue_event_task
from .executors import ExecutorDispatchRequest, OutboxExecutorAdapter
from .state import SQLiteStateStore
from .workers import build_worker_payload

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
    "sample-smoke",
    "enqueue-event",
    "worker-payload",
    "dispatch-task",
    "list-dispatches",
    "claim-dispatch",
    "complete-dispatch",
    "fail-dispatch",
)
FORBIDDEN_CORE_IMPORT_ROOTS = frozenset({"opencode", "oh_my_openagent"})


def _scan_core_imports_for_optional_executor_dependencies() -> dict[str, Any]:
    """Return a mechanical import scan for core OpenCode independence."""

    source_dir = Path(__file__).resolve().parent
    offenders: dict[str, list[str]] = {}
    scanned = 0
    for path in source_dir.rglob("*.py"):
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", maxsplit=1)[0])
        forbidden = sorted(imports & FORBIDDEN_CORE_IMPORT_ROOTS)
        if forbidden:
            offenders[str(path.relative_to(source_dir.parent))] = forbidden
    return {
        "status": "ok" if not offenders else "blocked",
        "core_modules_scanned": scanned,
        "offenders": offenders,
    }


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
        import_scan = _scan_core_imports_for_optional_executor_dependencies()
        return {
            "ok": True,
            "command": "doctor",
            "plugin": "sisyphus-hermes",
            "workspace": str(workspace),
            "checks": {
                "sqlite": "ok" if store.path.exists() else "missing",
                "kanban": "optional_unavailable_using_sqlite",
                "opencode_dependency": "not_required",
                "opencode_import_scan": import_scan["status"],
                "core_modules_scanned": import_scan["core_modules_scanned"],
                "opencode_import_offenders": import_scan["offenders"],
            },
        }

    def sample_smoke(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run the local install/load smoke path against a sample project."""

        workspace = str(args.get("workspace") or Path.cwd())
        sample_goal = str(args.get("goal") or "Verify sisyphus-hermes local sample project")
        init_result = self.init({"workspace": workspace})
        doctor_result = self.doctor({"workspace": workspace})
        start_result = self.start({"workspace": workspace, "goal": sample_goal})
        if not start_result.get("ok"):
            return {
                "ok": False,
                "command": "sample-smoke",
                "workspace": workspace,
                "init": init_result,
                "doctor": doctor_result,
                "start": start_result,
            }
        run_id = start_result["run"]["id"]
        event_result = self.enqueue_event(
            {
                "workspace": workspace,
                "run_id": run_id,
                "title": "Sample lifecycle task",
                "description": "Exercise outbox dispatch lifecycle without spawning executors.",
            }
        )
        dispatch_result = self.dispatch_task(
            {"workspace": workspace, "run_id": run_id, "task_id": event_result["task"]["id"]}
        )
        claim_result = self.claim_dispatch(
            {"workspace": workspace, "dispatch_id": dispatch_result["dispatch_id"]}
        )
        complete_result = self.complete_dispatch(
            {
                "workspace": workspace,
                "dispatch_id": dispatch_result["dispatch_id"],
                "summary": "Sample lifecycle completed",
                "evidence_uri": "file://sample-smoke",
            }
        )
        dispatches_result = self.list_dispatches({"workspace": workspace, "run_id": run_id})
        status_result = self.status({"workspace": workspace, "run_id": run_id})
        report_result = self.report({"workspace": workspace, "run_id": run_id})
        return {
            "ok": bool(
                init_result.get("ok")
                and doctor_result.get("ok")
                and event_result.get("ok")
                and dispatch_result.get("ok")
                and claim_result.get("ok")
                and complete_result.get("ok")
                and dispatches_result.get("ok")
                and status_result.get("ok")
                and report_result.get("ok")
            ),
            "command": "sample-smoke",
            "workspace": workspace,
            "sample_project": {"workspace": workspace, "goal": sample_goal},
            "init": init_result,
            "doctor": doctor_result,
            "start": start_result,
            "event": event_result,
            "dispatch": dispatch_result,
            "claim": claim_result,
            "complete": complete_result,
            "dispatches": dispatches_result,
            "status": status_result,
            "report": report_result,
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
            "state": {"backend": store.source_of_truth, "path": str(store.path)},
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
        payload = {}
        if args.get("child_process_handles"):
            payload["child_process_handles"] = list(args["child_process_handles"])
        store.append_audit(
            run_id,
            actor="sisyphus_lifecycle_worker",
            action=action,
            summary=str(args.get("reason") or ""),
            payload=payload,
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

    def enqueue_event(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create/update durable work from cron/webhook payloads without execution."""

        store = self._store_for(args)
        run_id = args.get("run_id")
        if not run_id:
            return {"ok": False, "error": "run_id_required", "command": "enqueue-event"}
        if store.get_run(str(run_id)) is None:
            return {
                "ok": False,
                "error": "run_not_found",
                "run_id": str(run_id),
                "command": "enqueue-event",
            }
        result = enqueue_event_task(store, args)
        return {"command": "enqueue-event", **result.to_record()}

    def worker_payload(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return explicit scoped context for a task; does not dispatch it."""

        result = self._build_worker_payload_result(args)
        if not result.get("ok"):
            return result
        return {"ok": True, "command": "worker-payload", "payload": result["payload"].to_record()}

    def dispatch_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Queue a scoped worker payload for an external executor peer."""

        result = self._build_worker_payload_result(args)
        if not result.get("ok"):
            return result
        payload = result["payload"]
        workspace = Path(payload.repo_path)
        executor = str(args.get("executor") or "hermes-profile")
        adapter = OutboxExecutorAdapter(args.get("outbox_path") or OutboxExecutorAdapter.default_path(workspace))
        dispatch = adapter.dispatch(
            ExecutorDispatchRequest(
                payload=payload,
                executor=executor,
                reason=str(args.get("reason") or "manual dispatch"),
            )
        )
        store = self._store_for(args)
        store.append_audit(
            payload.run_id,
            actor="sisyphus_lifecycle_worker",
            action="task.dispatch_queued",
            summary=f"Queued task for {executor}",
            payload={
                "task_id": payload.task_id,
                "executor": executor,
                "outbox_path": dispatch["outbox_path"],
                "dispatch_id": dispatch["dispatch_id"],
                "executor_invoked": False,
            },
        )
        return {"command": "dispatch-task", **dispatch}

    def list_dispatches(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = self._outbox_adapter_for(args)
        dispatches = adapter.list_dispatches()
        run_id = args.get("run_id")
        if run_id:
            dispatches = [dispatch for dispatch in dispatches if dispatch.get("run_id") == run_id]
        return {
            "ok": True,
            "command": "list-dispatches",
            "outbox_path": str(adapter.path),
            "dispatches": dispatches,
        }

    def claim_dispatch(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = self._outbox_adapter_for(args)
        dispatch_id = str(args["dispatch_id"])
        dispatch = adapter.get_dispatch(dispatch_id)
        if dispatch is None:
            return {"ok": False, "error": "dispatch_not_found", "dispatch_id": dispatch_id}
        if dispatch["status"] in {"completed", "failed"}:
            return {"ok": False, "error": "dispatch_terminal", **dispatch}
        executor = str(args.get("executor") or dispatch.get("executor") or "hermes-profile")
        if dispatch["status"] == "claimed" and dispatch.get("claimed_by") != executor:
            return {"ok": False, "error": "dispatch_already_claimed", **dispatch}
        if dispatch["status"] == "claimed":
            return {"ok": True, "command": "claim-dispatch", **dispatch}
        adapter.append_event("dispatch.claimed", dispatch_id, executor=executor)
        store = self._store_for(args)
        self._set_task_status(store, str(dispatch["run_id"]), str(dispatch["task_id"]), TaskStatus.IN_PROGRESS)
        store.append_audit(
            str(dispatch["run_id"]),
            actor=executor,
            action="task.dispatch_claimed",
            summary=f"Claimed dispatch {dispatch_id}",
            payload={"dispatch_id": dispatch_id, "task_id": dispatch["task_id"], "executor_invoked": False},
        )
        claimed = adapter.get_dispatch(dispatch_id)
        return {"ok": True, "command": "claim-dispatch", **claimed}

    def complete_dispatch(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = self._outbox_adapter_for(args)
        dispatch_id = str(args["dispatch_id"])
        dispatch = self._require_claimed_dispatch(adapter, dispatch_id)
        if not dispatch.get("ok", True):
            return dispatch
        summary = str(args.get("summary") or "Dispatch completed")
        evidence_uri = args.get("evidence_uri") or args.get("uri")
        adapter.append_event(
            "dispatch.completed",
            dispatch_id,
            summary=summary,
            evidence_uri=evidence_uri,
        )
        store = self._store_for(args)
        run_id = str(dispatch["run_id"])
        task_id = str(dispatch["task_id"])
        evidence = store.save_evidence(
            Evidence(run_id=run_id, kind="dispatch_result", summary=summary, uri=evidence_uri, task_id=task_id)
        )
        store.append_audit(
            run_id,
            actor=str(dispatch.get("claimed_by") or dispatch.get("executor") or "hephaestus_executor"),
            action="evidence.added",
            summary=summary,
            payload={"dispatch_id": dispatch_id, "evidence_id": evidence.id},
        )
        self._set_task_status(store, run_id, task_id, TaskStatus.COMPLETED)
        store.append_audit(
            run_id,
            actor="sisyphus_lifecycle_worker",
            action="task.completed",
            summary=summary,
            payload={"dispatch_id": dispatch_id, "task_id": task_id, "executor_invoked": False},
        )
        completed = adapter.get_dispatch(dispatch_id)
        return {"ok": True, "command": "complete-dispatch", **completed, "evidence": evidence.to_record()}

    def fail_dispatch(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = self._outbox_adapter_for(args)
        dispatch_id = str(args["dispatch_id"])
        dispatch = adapter.get_dispatch(dispatch_id)
        if dispatch is None:
            return {"ok": False, "error": "dispatch_not_found", "dispatch_id": dispatch_id}
        if dispatch["status"] in {"completed", "failed"}:
            return {"ok": False, "error": "dispatch_terminal", **dispatch}
        reason = str(args.get("reason") or "Dispatch failed")
        adapter.append_event("dispatch.failed", dispatch_id, reason=reason)
        store = self._store_for(args)
        run_id = str(dispatch["run_id"])
        task_id = str(dispatch["task_id"])
        self._set_task_status(store, run_id, task_id, TaskStatus.BLOCKED)
        store.set_run_status(run_id, RunStatus.BLOCKED)
        store.append_audit(
            run_id,
            actor="sisyphus_lifecycle_worker",
            action="task.failed",
            summary=reason,
            payload={"dispatch_id": dispatch_id, "task_id": task_id, "executor_invoked": False},
        )
        failed = adapter.get_dispatch(dispatch_id)
        return {"ok": True, "command": "fail-dispatch", **failed}

    def _require_claimed_dispatch(
        self, adapter: OutboxExecutorAdapter, dispatch_id: str
    ) -> dict[str, Any]:
        dispatch = adapter.get_dispatch(dispatch_id)
        if dispatch is None:
            return {"ok": False, "error": "dispatch_not_found", "dispatch_id": dispatch_id}
        if dispatch["status"] in {"completed", "failed"}:
            return {"ok": False, "error": "dispatch_terminal", **dispatch}
        if dispatch["status"] != "claimed":
            return {"ok": False, "error": "dispatch_not_claimed", **dispatch}
        return dispatch

    def _outbox_adapter_for(self, args: dict[str, Any]) -> OutboxExecutorAdapter:
        if args.get("outbox_path"):
            return OutboxExecutorAdapter(args["outbox_path"])
        workspace = args.get("workspace") or Path.cwd()
        return OutboxExecutorAdapter(OutboxExecutorAdapter.default_path(workspace))

    def _set_task_status(
        self, store: SQLiteStateStore, run_id: str, task_id: str, status: TaskStatus
    ) -> None:
        task = next((candidate for candidate in store.list_tasks(run_id) if candidate.id == task_id), None)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        store.save_task(replace(task, status=status, updated_at=utc_now()))

    def _build_worker_payload_result(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run = store.get_run(str(args["run_id"]))
        if run is None:
            return {"ok": False, "error": "run_not_found"}
        task_id = str(args["task_id"])
        task = next((candidate for candidate in store.list_tasks(run.id) if candidate.id == task_id), None)
        if task is None:
            return {"ok": False, "error": "task_not_found", "task_id": task_id}
        return {"ok": True, "payload": build_worker_payload(run, task)}

    def add_evidence(self, run_id: str, *, kind: str, summary: str, uri: str | None = None) -> Evidence:
        store = self._store_for({})
        evidence = store.save_evidence(Evidence(run_id=run_id, kind=kind, summary=summary, uri=uri))
        store.append_audit(run_id, actor="hephaestus_executor", action="evidence.added", summary=summary)
        return evidence
