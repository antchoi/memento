# sisyphus-hermes User Guide

## Install for local development

```bash
python -m pip install -e '.[dev]'
sisyphus-hermes doctor --json
```

The plugin can also be exercised without installation by using the source path:

```bash
PYTHONPATH=src python -m sisyphus_hermes.cli doctor --json
```

## State model and recovery

- The intended production source of truth is Hermes Kanban.
- When Kanban is unavailable, the local SQLite fallback at
  `.sisyphus/state.sqlite3` stores runs, plans, tasks, review gates, evidence,
  and audit events.
- Re-running `init` is idempotent and recreates the schema if needed.
- `status` and `report` rebuild their view from durable state, not from an
  OpenCode/Codex/Claude TUI or process log.

## Command examples

```bash
sisyphus-hermes init --workspace /path/to/repo
sisyphus-hermes start --workspace /path/to/repo --goal "Ship the plugin MVP"
sisyphus-hermes plan --run-id run_... --title "MVP plan" --body "..."
sisyphus-hermes approve-plan --run-id run_... --plan-id plan_...
sisyphus-hermes status --run-id run_...
sisyphus-hermes report --run-id run_...
sisyphus-hermes pause --run-id run_... --reason "waiting for review"
sisyphus-hermes resume --run-id run_...
sisyphus-hermes cancel --run-id run_... --reason "user cancelled"
```

Telegram/slash-command integrations should render the same structured results in
concise Markdown without tables.

## Planning and review gates

Normal execution is blocked until a draft plan is promoted to canonical. Review
gates cover:

- preflight safety;
- plan review;
- implementation/spec review;
- quality review;
- final acceptance.

Failed gates must produce actionable findings and block or pause advancement.

## Safety model

Sisyphus workers receive explicit payloads containing repo path, task
description, acceptance criteria, safety constraints, and reporting contract.
They must not depend on hidden parent chat history. The default guardrails block
or require explicit approval for:

- `git reset --hard`;
- `git clean`;
- force push;
- direct protected-branch push;
- merge operations.

## Cron and event integration

Cron/webhook integrations may enqueue durable tasks only. They must not dispatch
implementation work directly. A later Sisyphus worker or explicit user command
can decide how to process the queued task after safety and review checks.

## Optional executor extension

OpenCode, Codex, Claude Code, or Hermes profile workers can be implemented as
future executor adapters. They are peer executors, not the lifecycle source of
truth. The core plugin must continue to pass tests without those tools installed.
