"""Command handlers for the memento plugin and developer CLI."""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.resources
import tomllib
from dataclasses import replace
from pathlib import Path
import subprocess
from typing import Any, Callable

from .approvals import record_approval as save_approval_evidence, release_gate_satisfied
from .context import build_context_bundle, write_context_bundle
from .ci import record_external_check as save_external_check_evidence
from .competition import select_patch as select_candidate_patch
from .domain import (
    Evidence,
    GateKind,
    GateStatus,
    ReviewGate,
    RunStatus,
    MementoPlan,
    MementoRun,
    TaskStatus,
    utc_now,
)
from .events import enqueue_event_task
from .executors import ExecutorDispatchRequest, OutboxExecutorAdapter
from .graph_diff import detect_graph_regressions
from .graphify import graph_status, update_graph
from .kanban import HermesKanbanCliAdapter, JsonKanbanAdapter
from .memory import LocalMemoryAdapter
from .recovery import recover_dispatch_jobs
from .routing import registry_snapshot, route_task
from .state import SQLiteStateStore
from .verification import evaluate_task
from .workers import build_worker_payload
from .worktree import create_isolated_worktree

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
    "context-bundle",
    "route-task",
    "verify-task",
    "graph-status",
    "graph-update",
    "memory-prefetch",
    "memory-writeback",
    "record-external-check",
    "record-approval",
    "record-graph-diff",
    "select-patch",
    "release-gate",
    "recover-jobs",
    "update",
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


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_project_root() -> Path | None:
    root = _project_root()
    return root if (root / "pyproject.toml").exists() else None


def _project_metadata() -> dict[str, Any]:
    source_root = _source_project_root()
    if source_root is not None:
        try:
            return tomllib.loads((source_root / "pyproject.toml").read_text(encoding="utf-8"))[
                "project"
            ]
        except Exception:
            pass
    try:
        metadata = importlib.metadata.metadata("memento-lifecycle")
        scripts = {"memento": "memento.cli:main"}
        entry_points = {"hermes_agent.plugins": {"memento": "memento.plugin"}}
        return {
            "name": metadata.get("Name"),
            "version": metadata.get("Version"),
            "scripts": scripts,
            "entry-points": entry_points,
        }
    except importlib.metadata.PackageNotFoundError:
        return {}


def _bundled_skill_files() -> list[Path]:
    source_root = _source_project_root()
    if source_root is not None:
        return sorted((source_root / "skills").glob("*/SKILL.md"))
    try:
        root = importlib.resources.files("memento") / "bundled_skills"
        return sorted(
            Path(str(path / "SKILL.md"))
            for path in root.iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        )
    except Exception:
        return []


def _package_import_check() -> dict[str, Any]:
    try:
        module = importlib.import_module("memento")
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok",
        "module": module.__name__,
        "version": getattr(module, "__version__", None),
    }


def _cli_entrypoint_check() -> dict[str, Any]:
    try:
        project = _project_metadata()
        target = project["scripts"]["memento"]
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok" if target == "memento.cli:main" else "blocked",
        "console_script": "memento",
        "target": target,
    }


def _hermes_plugin_entrypoint_check() -> dict[str, Any]:
    try:
        project = _project_metadata()
        target = project["entry-points"]["hermes_agent.plugins"]["memento"]
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok" if target == "memento.plugin" else "blocked",
        "entrypoint_group": "hermes_agent.plugins",
        "name": "memento",
        "target": target,
    }


class _DoctorHermesContext:
    def __init__(self) -> None:
        self.commands: dict[str, Any] = {}

    def register_command(self, name: str, handler: Any, **metadata: Any) -> None:
        self.commands[name] = {"handler": handler, "metadata": metadata}


def _plugin_registration_smoke() -> dict[str, Any]:
    try:
        plugin = importlib.import_module("memento.plugin")
        ctx = _DoctorHermesContext()
        result = plugin.register(ctx)
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}", "commands": []}
    commands = sorted(ctx.commands)
    return {
        "status": "ok" if result.get("ok") and "memento.doctor" in commands else "blocked",
        "registered": bool(result.get("registered")),
        "commands": commands,
    }


def _workspace_writable_check(workspace: Path) -> dict[str, Any]:
    memento_dir = workspace / ".memento"
    probe = memento_dir / ".doctor-write-probe"
    try:
        memento_dir.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok", "path": str(memento_dir)}


def _runtime_gitignored_check() -> dict[str, Any]:
    source_root = _source_project_root()
    if source_root is None:
        return {"status": "ok", "mode": "installed_package", "missing": []}
    gitignore_path = source_root / ".gitignore"
    text = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    required = (".memento/", ".hermes/runtime/", ".ouroboros/data/", ".ouroboros/runs/")
    missing = [pattern for pattern in required if pattern not in text]
    return {"status": "ok" if not missing else "blocked", "missing": missing}


def _bundled_skills_check() -> dict[str, Any]:
    source_root = _source_project_root()
    offenders: dict[str, str] = {}
    skill_files = _bundled_skill_files()
    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            offenders[str(path.relative_to(source_root)) if source_root else str(path)] = (
                "missing_frontmatter_open"
            )
            continue
        try:
            _, frontmatter, _body = text.split("---", maxsplit=2)
        except ValueError:
            offenders[str(path.relative_to(source_root)) if source_root else str(path)] = (
                "missing_frontmatter_close"
            )
            continue
        if "name:" not in frontmatter or "description:" not in frontmatter:
            offenders[str(path.relative_to(source_root)) if source_root else str(path)] = (
                "missing_name_or_description"
            )
    return {
        "status": "ok" if skill_files and not offenders else "blocked",
        "count": len(skill_files),
        "frontmatter_offenders": offenders,
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
        kanban = self._kanban_adapter_for(args)
        return SQLiteStateStore(SQLiteStateStore.default_path(workspace), kanban=kanban)

    def _kanban_adapter_for(self, args: dict[str, Any]) -> Any:
        backend = str(args.get("kanban_backend") or "").strip()
        if args.get("kanban_path"):
            return JsonKanbanAdapter(args["kanban_path"])
        if backend == "hermes-cli" or args.get("kanban_board"):
            return HermesKanbanCliAdapter(
                board=args.get("kanban_board"),
                tenant=str(args.get("kanban_tenant") or "memento"),
                assignee=args.get("kanban_assignee"),
                workspace=args.get("kanban_workspace"),
            )
        return None

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
        package_import = _package_import_check()
        cli_entrypoint = _cli_entrypoint_check()
        hermes_entrypoint = _hermes_plugin_entrypoint_check()
        plugin_registration = _plugin_registration_smoke()
        workspace_writable = _workspace_writable_check(workspace)
        runtime_gitignored = _runtime_gitignored_check()
        bundled_skills = _bundled_skills_check()
        outbox_path = OutboxExecutorAdapter.default_path(workspace)
        graphify_status = graph_status(workspace)
        executor_registry = registry_snapshot()
        return {
            "ok": True,
            "command": "doctor",
            "plugin": "memento",
            "workspace": str(workspace),
            "local_install": {
                "module": package_import.get("module"),
                "version": package_import.get("version"),
                "console_script": cli_entrypoint.get("console_script"),
                "entrypoint_target": cli_entrypoint.get("target"),
                "hermes_plugin_entrypoint_group": hermes_entrypoint.get("entrypoint_group"),
                "hermes_plugin_entrypoint_target": hermes_entrypoint.get("target"),
            },
            "plugin_registration": {
                "registered": plugin_registration.get("registered", False),
                "commands": plugin_registration.get("commands", []),
            },
            "runtime_paths": {
                "state": str(db_path),
                "executor_outbox": str(outbox_path),
                "workspace_state_dir": str(workspace / ".memento"),
            },
            "graphify": graphify_status,
            "executor_registry": executor_registry,
            "checks": {
                "sqlite": "ok" if store.path.exists() else "missing",
                "kanban": "optional_unavailable_using_sqlite",
                "package_import": package_import["status"],
                "cli_entrypoint": cli_entrypoint["status"],
                "hermes_plugin_entrypoint": hermes_entrypoint["status"],
                "plugin_register_smoke": plugin_registration["status"],
                "workspace_writable": workspace_writable["status"],
                "runtime_gitignored": runtime_gitignored["status"],
                "runtime_gitignore_missing": runtime_gitignored["missing"],
                "bundled_skills": bundled_skills["status"],
                "bundled_skill_count": bundled_skills["count"],
                "bundled_skill_frontmatter_offenders": bundled_skills["frontmatter_offenders"],
                "graphify": "ok" if graphify_status["installed"] else "optional_unavailable",
                "graph_state": graphify_status["state"],
                "opencode_dependency": "not_required",
                "opencode_import_scan": import_scan["status"],
                "core_modules_scanned": import_scan["core_modules_scanned"],
                "opencode_import_offenders": import_scan["offenders"],
            },
        }

    def sample_smoke(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run the local install/load smoke path against a sample project."""

        workspace = str(args.get("workspace") or Path.cwd())
        sample_goal = str(args.get("goal") or "Verify memento local sample project")
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
        plan_result = self.plan(
            {
                "workspace": workspace,
                "run_id": run_id,
                "title": "Sample canonical plan",
                "body": "Approve a minimal plan before exercising executor dispatch.",
                "acceptance_criteria": [
                    "sample task dispatch completes through the outbox lifecycle"
                ],
            }
        )
        approve_result = self.approve_plan(
            {"workspace": workspace, "run_id": run_id, "plan_id": plan_result["plan"]["id"]}
        )
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
                and plan_result.get("ok")
                and approve_result.get("ok")
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
            "plan": plan_result,
            "approve_plan": approve_result,
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
            gate_result = self._execution_gate_result(
                store, run, command="start", allow_spike=bool(args.get("allow_spike"))
            )
            if gate_result is not None:
                return gate_result
            run = store.set_run_status(run.id, RunStatus.ACTIVE)
            store.append_audit(run.id, actor="memento_lifecycle_worker", action="run.started")
            return {"ok": True, "command": "start", "run": run.to_record()}

        goal = str(args.get("goal") or "").strip()
        workspace = str(args.get("workspace") or Path.cwd())
        if not goal:
            return {"ok": False, "error": "goal_required"}
        run = store.create_run(
            goal=goal, workspace=workspace, actor=str(args.get("actor") or "founder_user")
        )
        store.append_audit(run.id, actor="founder_user", action="run.created", summary=goal)
        if args.get("allow_spike"):
            store.append_audit(
                run.id,
                actor="memento_lifecycle_worker",
                action="execution.spike_allowed",
                summary="Bounded spike allowed without canonical plan.",
            )
        return {"ok": True, "command": "start", "run": run.to_record()}

    def plan(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        plan = store.save_plan(
            MementoPlan(
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
            actor="memento_lifecycle_worker",
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
        return {
            **status,
            "command": "report",
            "text": render_report(status),
            "generated_at": utc_now(),
        }

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
        store = self._store_for(args)
        run = store.get_run(payload.run_id)
        if run is None:
            return {"ok": False, "error": "run_not_found", "command": "dispatch-task"}
        gate_result = self._execution_gate_result(store, run, command="dispatch-task")
        if gate_result is not None:
            return gate_result
        workspace = Path(payload.repo_path)
        executor = str(args.get("executor") or "oh-my-pi")
        adapter = OutboxExecutorAdapter(
            args.get("outbox_path") or OutboxExecutorAdapter.default_path(workspace)
        )
        worktree = None
        if args.get("isolated_worktree"):
            task = store.get_task(payload.task_id)
            if task is None:
                return {"ok": False, "error": "task_not_found", "command": "dispatch-task"}
            worktree = create_isolated_worktree(
                workspace, task, dry_run=not bool(args.get("create_worktree"))
            )
            if bool(args.get("create_worktree")) and not worktree.get("created"):
                return {
                    "ok": False,
                    "command": "dispatch-task",
                    "error": worktree.get("error") or "worktree_creation_failed",
                    "worktree": worktree,
                }
        dispatch = adapter.dispatch(
            ExecutorDispatchRequest(
                payload=payload,
                executor=executor,
                reason=str(args.get("reason") or "manual dispatch"),
            )
        )
        store.append_audit(
            payload.run_id,
            actor="memento_lifecycle_worker",
            action="task.dispatch_queued",
            summary=f"Queued task for {executor}",
            payload={
                "task_id": payload.task_id,
                "executor": executor,
                "outbox_path": dispatch["outbox_path"],
                "dispatch_id": dispatch["dispatch_id"],
                "executor_invoked": False,
                "worktree": worktree,
            },
        )
        if worktree is not None:
            dispatch = {**dispatch, "worktree": worktree}
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
        if dispatch["status"] in {"completed", "failed", "recovered"}:
            return {"ok": False, "error": "dispatch_terminal", **dispatch}
        executor = str(args.get("executor") or dispatch.get("executor") or "oh-my-pi")
        if dispatch["status"] == "claimed" and dispatch.get("claimed_by") != executor:
            return {"ok": False, "error": "dispatch_already_claimed", **dispatch}
        if dispatch["status"] == "claimed":
            return {"ok": True, "command": "claim-dispatch", **dispatch}
        adapter.append_event("dispatch.claimed", dispatch_id, executor=executor)
        store = self._store_for(args)
        self._set_task_status(
            store, str(dispatch["run_id"]), str(dispatch["task_id"]), TaskStatus.IN_PROGRESS
        )
        store.append_audit(
            str(dispatch["run_id"]),
            actor=executor,
            action="task.dispatch_claimed",
            summary=f"Claimed dispatch {dispatch_id}",
            payload={
                "dispatch_id": dispatch_id,
                "task_id": dispatch["task_id"],
                "executor_invoked": False,
            },
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
            Evidence(
                run_id=run_id,
                kind="dispatch_result",
                summary=summary,
                uri=evidence_uri,
                task_id=task_id,
            )
        )
        store.append_audit(
            run_id,
            actor=str(
                dispatch.get("claimed_by") or dispatch.get("executor") or "hephaestus_executor"
            ),
            action="evidence.added",
            summary=summary,
            payload={"dispatch_id": dispatch_id, "evidence_id": evidence.id},
        )
        self._set_task_status(store, run_id, task_id, TaskStatus.COMPLETED)
        graph_update = None
        if args.get("graphify_checkpoint"):
            graph_update = update_graph(
                store=store,
                run_id=run_id,
                workspace=args.get("workspace") or Path.cwd(),
                changed_files=list(args.get("changed_files") or []),
                mock=bool(args.get("mock_graphify")),
            )
        store.append_audit(
            run_id,
            actor="memento_lifecycle_worker",
            action="task.completed",
            summary=summary,
            payload={"dispatch_id": dispatch_id, "task_id": task_id, "executor_invoked": False},
        )
        completed = adapter.get_dispatch(dispatch_id)
        result = {
            "ok": True,
            "command": "complete-dispatch",
            **completed,
            "evidence": evidence.to_record(),
        }
        if graph_update is not None:
            result["graph_update"] = graph_update
        return result

    def fail_dispatch(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = self._outbox_adapter_for(args)
        dispatch_id = str(args["dispatch_id"])
        dispatch = adapter.get_dispatch(dispatch_id)
        if dispatch is None:
            return {"ok": False, "error": "dispatch_not_found", "dispatch_id": dispatch_id}
        if dispatch["status"] in {"completed", "failed", "recovered"}:
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
            actor="memento_lifecycle_worker",
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
        if dispatch["status"] in {"completed", "failed", "recovered"}:
            return {"ok": False, "error": "dispatch_terminal", **dispatch}
        if dispatch["status"] != "claimed":
            return {"ok": False, "error": "dispatch_not_claimed", **dispatch}
        return dispatch

    def _execution_gate_result(
        self,
        store: SQLiteStateStore,
        run: MementoRun,
        *,
        command: str,
        allow_spike: bool = False,
    ) -> dict[str, Any] | None:
        if not allow_spike and store.canonical_plan(run.id) is None:
            store.append_audit(
                run.id,
                actor="memento_lifecycle_worker",
                action="execution.blocked",
                summary="Canonical plan required before execution.",
            )
            return {
                "ok": False,
                "command": command,
                "error": "canonical_plan_required",
                "run": run.to_record(),
            }
        blocking_gates = [
            gate.to_record()
            for gate in store.list_gates(run.id)
            if gate.status == GateStatus.FAILED
        ]
        if blocking_gates:
            blocked_run = store.set_run_status(run.id, RunStatus.BLOCKED)
            store.append_audit(
                run.id,
                actor="memento_lifecycle_worker",
                action="execution.blocked",
                summary="Failed review gate blocks execution.",
                payload={"blocking_gate_ids": [gate["id"] for gate in blocking_gates]},
            )
            return {
                "ok": False,
                "command": command,
                "error": "review_gate_blocking",
                "run": blocked_run.to_record(),
                "blocking_gates": blocking_gates,
            }
        return None

    def _outbox_adapter_for(self, args: dict[str, Any]) -> OutboxExecutorAdapter:
        if args.get("outbox_path"):
            return OutboxExecutorAdapter(args["outbox_path"])
        workspace = args.get("workspace") or Path.cwd()
        return OutboxExecutorAdapter(OutboxExecutorAdapter.default_path(workspace))

    def _set_task_status(
        self, store: SQLiteStateStore, run_id: str, task_id: str, status: TaskStatus
    ) -> None:
        task = next(
            (candidate for candidate in store.list_tasks(run_id) if candidate.id == task_id), None
        )
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        store.save_task(replace(task, status=status, updated_at=utc_now()))

    def _build_worker_payload_result(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run = store.get_run(str(args["run_id"]))
        if run is None:
            return {"ok": False, "error": "run_not_found"}
        task_id = str(args["task_id"])
        task = next(
            (candidate for candidate in store.list_tasks(run.id) if candidate.id == task_id), None
        )
        if task is None:
            return {"ok": False, "error": "task_not_found", "task_id": task_id}
        return {"ok": True, "payload": build_worker_payload(run, task)}

    def context_bundle(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run = store.get_run(str(args["run_id"]))
        if run is None:
            return {"ok": False, "error": "run_not_found", "command": "context-bundle"}
        task = store.get_task(str(args["task_id"]))
        if task is None or task.run_id != run.id:
            return {"ok": False, "error": "task_not_found", "command": "context-bundle"}
        memory_summary = str(args.get("memory_summary") or "")
        bundle = build_context_bundle(
            store=store,
            run=run,
            task=task,
            memory_summary=memory_summary,
            graph_context={"state": graph_status(run.workspace)["state"]},
        )
        bundle_path = write_context_bundle(run.workspace, bundle)
        evidence = store.save_evidence(
            Evidence(
                run_id=run.id,
                kind="context_bundle",
                type="artifact",
                summary=f"Context bundle generated for {task.title}",
                uri=str(bundle_path),
                task_id=task.id,
                content_ref={
                    "kind": "file",
                    "uri": str(bundle_path),
                    "sha256": bundle["bundle_hash"],
                },
            )
        )
        return {
            "ok": True,
            "command": "context-bundle",
            "bundle": bundle,
            "bundle_path": str(bundle_path),
            "evidence": evidence.to_record(),
        }

    def route_task(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        task = store.get_task(str(args["task_id"]))
        if task is None:
            return {"ok": False, "error": "task_not_found", "command": "route-task"}
        decision = route_task(
            task,
            graph_state=graph_status(args.get("workspace") or Path.cwd())["state"],
            requested_executor=args.get("executor"),
        )
        evidence = store.save_evidence(
            Evidence(
                run_id=task.run_id,
                kind="routing_decision",
                type="routing_decision",
                summary=f"Route preview selected {decision['selected_executor']}",
                task_id=task.id,
                trust_level="trusted",
                content_ref={"kind": "inline", "decision": decision},
            )
        )
        return {
            "ok": True,
            "command": "route-task",
            "decision": decision,
            "evidence": evidence.to_record(),
        }

    def verify_task(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        task = store.get_task(str(args["task_id"]))
        if task is None:
            return {"ok": False, "error": "task_not_found", "command": "verify-task"}
        verdict = evaluate_task(store, task)
        return {"ok": True, "command": "verify-task", **verdict}

    def graph_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "graph-status",
            "graphify": graph_status(args.get("workspace") or Path.cwd()),
        }

    def graph_update(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        return {
            "command": "graph-update",
            **update_graph(
                store=store,
                run_id=run_id,
                workspace=args.get("workspace") or Path.cwd(),
                changed_files=list(args.get("changed_files") or []),
                mock=bool(args.get("mock_graphify")),
            ),
        }

    def memory_prefetch(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = LocalMemoryAdapter()
        result = adapter.recall(str(args.get("query") or args.get("goal") or ""))
        return {"ok": True, "command": "memory-prefetch", "memory": result}

    def memory_writeback(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = LocalMemoryAdapter()
        result = adapter.save_lesson(str(args.get("lesson") or args.get("summary") or ""))
        return {"ok": True, "command": "memory-writeback", **result}

    def record_external_check(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        if store.get_run(run_id) is None:
            return {
                "ok": False,
                "command": "record-external-check",
                "error": "run_not_found",
                "run_id": run_id,
            }
        provider = str(args.get("provider") or "").strip()
        if not provider:
            return {"ok": False, "command": "record-external-check", "error": "provider_required"}
        payload = {
            key: value
            for key, value in {
                "run_id": args.get("external_run_id")
                or args.get("external_check_id")
                or args.get("ci_run_id"),
                "status": args.get("status"),
                "conclusion": args.get("conclusion"),
                "url": args.get("url") or args.get("evidence_uri"),
            }.items()
            if value not in (None, "")
        }
        evidence = save_external_check_evidence(
            store, run_id=run_id, provider=provider, payload=payload
        )
        store.append_audit(
            run_id,
            actor="memento_lifecycle_worker",
            action="external_check.recorded",
            summary=evidence.summary,
            payload={"evidence_id": evidence.id, "provider": provider},
        )
        return {"ok": True, "command": "record-external-check", "evidence": evidence.to_record()}

    def record_approval(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        if store.get_run(run_id) is None:
            return {
                "ok": False,
                "command": "record-approval",
                "error": "run_not_found",
                "run_id": run_id,
            }
        actor = str(args.get("actor") or args.get("reviewer") or "founder_user")
        scope = dict(args.get("scope") or {})
        if not scope:
            scope = {
                "kind": str(args.get("scope_kind") or "run"),
                "id": str(args.get("scope_id") or run_id),
            }
        prompt = str(args.get("prompt") or "Approval requested")
        response = str(args.get("response") or args.get("summary") or "")
        evidence = save_approval_evidence(
            store,
            run_id=run_id,
            actor=actor,
            scope=scope,
            prompt=prompt,
            response=response,
        )
        store.append_audit(
            run_id,
            actor=actor,
            action="approval.recorded",
            summary=evidence.summary,
            payload={"evidence_id": evidence.id, "scope": scope},
        )
        return {"ok": True, "command": "record-approval", "evidence": evidence.to_record()}

    def release_gate(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        if store.get_run(run_id) is None:
            return {
                "ok": False,
                "command": "release-gate",
                "error": "run_not_found",
                "run_id": run_id,
            }
        required_checks = tuple(args.get("required_checks") or ())
        if isinstance(args.get("required_checks"), str):
            required_checks = tuple(
                check.strip() for check in str(args["required_checks"]).split(",") if check.strip()
            )
        required_approvals = int(args.get("required_approvals") or 0)
        result = release_gate_satisfied(
            store,
            run_id,
            required_checks=required_checks,
            required_approvals=required_approvals,
            graph_policy=dict(args.get("graph_policy") or args.get("policy") or {}),
        )
        store.append_audit(
            run_id,
            actor="memento_lifecycle_worker",
            action="release_gate.checked",
            summary="Release gate satisfied."
            if result["ok"]
            else "Release gate missing required evidence.",
            payload={
                "required_checks": list(required_checks),
                "required_approvals": required_approvals,
                "graph_policy": dict(args.get("graph_policy") or args.get("policy") or {}),
                **result,
            },
        )
        return {"command": "release-gate", **result}

    def record_graph_diff(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        if store.get_run(run_id) is None:
            return {
                "ok": False,
                "command": "record-graph-diff",
                "error": "run_not_found",
                "run_id": run_id,
            }
        before = dict(args.get("before_graph") or {})
        after = dict(args.get("after_graph") or {})
        if not before and not after:
            return {
                "ok": False,
                "command": "record-graph-diff",
                "error": "graph_snapshots_required",
            }
        diff = detect_graph_regressions(before, after, blocking=bool(args.get("blocking")))
        warnings = list(diff.get("warnings") or [])
        evidence = store.save_evidence(
            Evidence(
                run_id=run_id,
                kind="graph_diff",
                type="graph_diff",
                summary=(
                    "Graph diff detected architecture regression warnings."
                    if warnings
                    else "Graph diff detected no architecture regressions."
                ),
                task_id=str(args.get("task_id")) if args.get("task_id") else None,
                status="warning" if warnings else "passed",
                trust_level="trusted",
                source={"kind": "graphify", "checkpoint": "manual"},
                content_ref={"kind": "inline", "diff": diff},
                relationships={
                    "warnings": warnings,
                    "risk": diff["risk"],
                    "blocking": diff["blocking"],
                },
            )
        )
        store.append_audit(
            run_id,
            actor="memento_lifecycle_worker",
            action="graph_diff.recorded",
            summary=evidence.summary,
            payload={"evidence_id": evidence.id, "warnings": warnings, "risk": diff["risk"]},
        )
        return {
            "ok": True,
            "command": "record-graph-diff",
            "diff": diff,
            "evidence": evidence.to_record(),
        }

    def select_patch(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        if store.get_run(run_id) is None:
            return {
                "ok": False,
                "command": "select-patch",
                "error": "run_not_found",
                "run_id": run_id,
            }
        candidates = list(args.get("candidates") or ())
        if not candidates:
            return {"ok": False, "command": "select-patch", "error": "candidates_required"}
        policy = dict(args.get("policy") or {})
        task_id = args.get("task_id")
        candidate_evidence: list[dict[str, Any]] = []
        for candidate in candidates:
            dispatch_id = str(candidate["dispatch_id"])
            verified = bool(candidate.get("verification_passed"))
            unsafe_paths = list(candidate.get("unsafe_paths") or ())
            graph_risk = str(candidate.get("graph_risk") or "unknown")
            evidence = store.save_evidence(
                Evidence(
                    run_id=run_id,
                    kind="patch_candidate",
                    type="patch_candidate",
                    summary=f"Patch candidate {dispatch_id} from {candidate.get('executor', 'unknown')} recorded.",
                    task_id=str(task_id) if task_id else None,
                    dispatch_id=dispatch_id,
                    status="passed" if verified else "failed",
                    trust_level="trusted",
                    content_ref={"kind": "inline", "candidate": dict(candidate)},
                    relationships={
                        "verification_passed": verified,
                        "unsafe_paths": unsafe_paths,
                        "graph_risk": graph_risk,
                    },
                )
            )
            candidate_evidence.append(evidence.to_record())
        decision = select_candidate_patch(candidates, policy=policy)
        decision_status = "passed" if decision["selected_dispatch_id"] else "blocked"
        if decision.get("approval_required"):
            decision_status = "approval_required"
        selected_dispatch_id = decision.get("selected_dispatch_id")
        evidence = store.save_evidence(
            Evidence(
                run_id=run_id,
                kind="patch_selection",
                type="patch_selection",
                summary=(
                    f"Selected patch {selected_dispatch_id}."
                    if selected_dispatch_id
                    else "No patch selected; approval or verification is required."
                ),
                task_id=str(task_id) if task_id else None,
                dispatch_id=str(selected_dispatch_id) if selected_dispatch_id else None,
                status=decision_status,
                trust_level="trusted",
                content_ref={"kind": "inline", "decision": decision, "policy": policy},
                relationships={
                    "candidate_evidence_ids": [item["id"] for item in candidate_evidence],
                    "preserved_evidence_trails": decision["preserved_evidence_trails"],
                },
            )
        )
        store.append_audit(
            run_id,
            actor="memento_lifecycle_worker",
            action="patch_selection.decided",
            summary=evidence.summary,
            payload={
                "selected_dispatch_id": selected_dispatch_id,
                "auto_merge_allowed": decision["auto_merge_allowed"],
                "approval_required": decision["approval_required"],
                "evidence_id": evidence.id,
            },
        )
        return {
            "ok": bool(selected_dispatch_id),
            "command": "select-patch",
            "decision": decision,
            "candidate_evidence": candidate_evidence,
            "evidence": evidence.to_record(),
        }

    def recover_jobs(self, args: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for(args)
        run_id = str(args["run_id"])
        run = store.get_run(run_id)
        if run is None:
            return {
                "ok": False,
                "command": "recover-jobs",
                "error": "run_not_found",
                "run_id": run_id,
            }
        jobs = recover_dispatch_jobs(store, run_id)
        recovered_jobs: list[dict[str, Any]] = []
        requeued_dispatch_ids: list[str] = []
        adapter = self._outbox_adapter_for(args)
        should_requeue = bool(args.get("requeue"))
        requeue_executor = str(args.get("executor") or "oh-my-pi")
        for job in jobs:
            task = store.get_task(str(job["task_id"]))
            if task is None:
                recovered_jobs.append({**job, "error": "task_not_found"})
                continue
            bundle = build_context_bundle(
                store=store,
                run=run,
                task=task,
                memory_summary=str(args.get("memory_summary") or ""),
                graph_context={"state": graph_status(run.workspace)["state"]},
            )
            bundle_path = write_context_bundle(run.workspace, bundle)
            evidence = store.save_evidence(
                Evidence(
                    run_id=run_id,
                    kind="recovery_context_bundle",
                    type="recovery_context_bundle",
                    summary=f"Recovery context bundle regenerated for {task.title}.",
                    uri=str(bundle_path),
                    task_id=task.id,
                    trust_level="trusted",
                    status="passed",
                    source={"kind": "memento", "source_of_truth": store.source_of_truth},
                    content_ref={
                        "kind": "file",
                        "uri": str(bundle_path),
                        "sha256": bundle["bundle_hash"],
                    },
                    relationships={
                        "recovery_mode": job["recovery_mode"],
                        "native_session_required": job["native_session_required"],
                        "task_status": job["status"],
                    },
                )
            )
            recovered_job = {
                **job,
                "source_of_truth": store.source_of_truth,
                "context_bundle_id": bundle["id"],
                "context_bundle_hash": bundle["bundle_hash"],
                "context_bundle_path": str(bundle_path),
                "evidence_id": evidence.id,
            }
            if should_requeue:
                active_dispatches = [
                    dispatch
                    for dispatch in adapter.list_dispatches()
                    if dispatch.get("run_id") == run_id
                    and dispatch.get("task_id") == task.id
                    and dispatch.get("status") in {"queued", "claimed"}
                ]
                recovered_dispatch_ids = [
                    str(dispatch["dispatch_id"]) for dispatch in active_dispatches
                ]
                redispatch = adapter.dispatch(
                    ExecutorDispatchRequest(
                        payload=build_worker_payload(run, task),
                        executor=requeue_executor,
                        reason="recovered restart handoff",
                        metadata={
                            "recovery_of": recovered_dispatch_ids,
                            "context_bundle_path": str(bundle_path),
                            "context_bundle_hash": bundle["bundle_hash"],
                            "recovery_evidence_id": evidence.id,
                        },
                    )
                )
                for dispatch_id in recovered_dispatch_ids:
                    adapter.append_event(
                        "dispatch.recovered",
                        dispatch_id,
                        requeued_dispatch_id=redispatch["dispatch_id"],
                        context_bundle_path=str(bundle_path),
                        recovery_evidence_id=evidence.id,
                    )
                requeued_dispatch_ids.append(str(redispatch["dispatch_id"]))
                recovered_job.update(
                    {
                        "recovered_dispatch_ids": recovered_dispatch_ids,
                        "requeued_dispatch_id": redispatch["dispatch_id"],
                        "requeue_executor": requeue_executor,
                        "handoff_status": "queued",
                        "outbox_path": redispatch["outbox_path"],
                    }
                )
            recovered_jobs.append(recovered_job)
        store.append_audit(
            run_id,
            actor="memento_lifecycle_worker",
            action="recovery.planned",
            summary=f"Recovered {len(recovered_jobs)} restartable job(s) from canonical state.",
            payload={"job_count": len(recovered_jobs), "jobs": recovered_jobs},
        )
        if requeued_dispatch_ids:
            store.append_audit(
                run_id,
                actor="memento_lifecycle_worker",
                action="recovery.requeued",
                summary=f"Queued {len(requeued_dispatch_ids)} recovered restart handoff(s).",
                payload={
                    "requeued_dispatch_ids": requeued_dispatch_ids,
                    "executor": requeue_executor,
                    "job_count": len(recovered_jobs),
                },
            )
        return {
            "ok": True,
            "command": "recover-jobs",
            "job_count": len(recovered_jobs),
            "jobs": recovered_jobs,
        }


    def update(self, args: dict[str, Any]) -> dict[str, Any]:
        workspace = Path(args.get("workspace") or Path.cwd())
        current_version = __import__("memento").__version__

        results = {"steps": []}
        all_ok = True

        # 1. PyPI self-update via pipx/uv
        try:
            proc = subprocess.run(
                ["pipx", "upgrade", "memento-lifecycle"],
                capture_output=True,
                text=True,
            )
            pypi_ok = proc.returncode == 0
            results["steps"].append({
                "step": "pypi_upgrade",
                "ok": pypi_ok,
                "output": proc.stdout if pypi_ok else proc.stderr,
            })
            if not pypi_ok:
                all_ok = False
        except FileNotFoundError:
            results["steps"].append({
                "step": "pypi_upgrade",
                "ok": False,
                "error": "pipx not available; try 'pip install --upgrade memento-lifecycle' or use uv",
            })
            all_ok = False

        # 2. Check bundled skills
        bundled_skills_dir = workspace / ".memento" / "skills"
        if bundled_skills_dir.exists():
            results["steps"].append({
                "step": "bundled_skills",
                "ok": True,
                "note": "Bundled skills at local workspace may need manual sync. Delete and re-init to refresh.",
            })
        else:
            results["steps"].append({
                "step": "bundled_skills",
                "ok": True,
                "note": "No local bundled skills overrides.",
            })

        # 3. Executor registry refresh check
        registry = registry_snapshot()
        results["steps"].append({
            "step": "executor_registry",
            "ok": True,
            "executors": list(registry.get("executors", {}).keys()),
        })

        results["ok"] = all_ok
        results["command"] = "update"
        results["workspace"] = str(workspace)
        results["version"] = {
            "previous": current_version,
            "note": "Restart required if updated.",
        }
        return results

    def add_evidence(
        self, run_id: str, *, kind: str, summary: str, uri: str | None = None
    ) -> Evidence:
        store = self._store_for({})
        evidence = store.save_evidence(Evidence(run_id=run_id, kind=kind, summary=summary, uri=uri))
        store.append_audit(
            run_id, actor="hephaestus_executor", action="evidence.added", summary=summary
        )
        return evidence
