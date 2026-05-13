"""Developer CLI for local smoke checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memento import __version__
from memento.commands import CommandService, command_names
from memento.reporting import render_report, render_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memento")
    parser.add_argument("command", nargs="?", default="doctor", choices=command_names())
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    parser.add_argument("--workspace", default=str(Path.cwd()), help="Repository/workspace path.")
    parser.add_argument("--run-id", help="Existing run id.")
    parser.add_argument("--plan-id", help="Existing plan id.")
    parser.add_argument("--goal", help="Goal text for start.")
    parser.add_argument("--title", help="Plan/task title.")
    parser.add_argument("--task-id", help="Existing task id.")
    parser.add_argument("--dispatch-id", help="Existing executor dispatch id.")
    parser.add_argument("--executor", help="Executor peer name for dispatch-task.")
    parser.add_argument("--outbox-path", help="Executor outbox JSONL path for dispatch lifecycle commands.")
    parser.add_argument("--summary", help="Completion/failure summary text.")
    parser.add_argument("--evidence-uri", help="Evidence URI for complete-dispatch.")
    parser.add_argument("--body", help="Plan body.")
    parser.add_argument("--reason", help="Pause/resume/cancel reason.")
    parser.add_argument("--allow-spike", action="store_true", help="Allow bounded spike without canonical plan.")
    parser.add_argument("--query", help="Memory or graph query text.")
    parser.add_argument("--lesson", help="Durable memory lesson candidate.")
    parser.add_argument("--mock-graphify", action="store_true", help="Use mock Graphify update for tests/smoke.")
    parser.add_argument("--provider", help="External check provider, for example github_actions.")
    parser.add_argument("--external-run-id", help="Provider-native external check/run id.")
    parser.add_argument("--status", help="External check or gate status.")
    parser.add_argument("--conclusion", help="External check conclusion, for example success or failure.")
    parser.add_argument("--url", help="External evidence URL.")
    parser.add_argument("--actor", help="Approval actor.")
    parser.add_argument("--scope-kind", help="Approval scope kind, for example release.")
    parser.add_argument("--scope-id", help="Approval scope id.")
    parser.add_argument("--prompt", help="Approval prompt text.")
    parser.add_argument("--response", help="Approval response text.")
    parser.add_argument("--required-check", action="append", dest="required_checks", help="Required external check provider; repeatable.")
    parser.add_argument("--required-approvals", type=int, help="Required positive approval count.")
    args = parser.parse_args(argv)

    payload = {
        "workspace": args.workspace,
        "run_id": args.run_id,
        "plan_id": args.plan_id,
        "goal": args.goal,
        "title": args.title,
        "task_id": args.task_id,
        "dispatch_id": args.dispatch_id,
        "executor": args.executor,
        "outbox_path": args.outbox_path,
        "summary": args.summary,
        "evidence_uri": args.evidence_uri,
        "body": args.body,
        "reason": args.reason,
        "allow_spike": args.allow_spike,
        "query": args.query,
        "lesson": args.lesson,
        "mock_graphify": args.mock_graphify,
        "provider": args.provider,
        "external_run_id": args.external_run_id,
        "status": args.status,
        "conclusion": args.conclusion,
        "url": args.url,
        "actor": args.actor,
        "scope_kind": args.scope_kind,
        "scope_id": args.scope_id,
        "prompt": args.prompt,
        "response": args.response,
        "required_checks": args.required_checks,
        "required_approvals": args.required_approvals,
    }
    payload = {k: v for k, v in payload.items() if v not in (None, False)}
    result = CommandService().handler_for(args.command)(payload)
    result.setdefault("package", "memento")
    result.setdefault("version", __version__)

    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif args.command == "status":
        print(render_status(result))
    elif args.command == "report":
        print(result.get("text") or render_report(result))
    else:
        status = "ok" if result.get("ok") else f"error: {result.get('error', 'unknown')}"
        print(f"memento {__version__}: {args.command} {status}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
