# sisyphus-hermes User Guide

## Install for local development

```bash
python -m pip install -e .
python -m pip install -e '.[dev]'  # optional: test/lint tools
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
sisyphus-hermes doctor --json
sisyphus-hermes sample-smoke --workspace /tmp/sisyphus-hermes-sample --json
sisyphus-hermes status --workspace /tmp/sisyphus-hermes-sample --json
```

`sample-smoke` is the recommended post-install smoke check. It initializes the
sample workspace, runs `doctor`, creates a sample run, enqueues a sample task,
queues/claims/completes an outbox dispatch without spawning an executor process,
and checks `status`/`report` against durable SQLite state.
The plugin can also be exercised without installation by using the source path:

```bash
PYTHONPATH=src python -m sisyphus_hermes.cli doctor --json
PYTHONPATH=src python -m sisyphus_hermes.cli sample-smoke --workspace /tmp/sisyphus-hermes-sample --json
```

For the full local release-candidate check, run:

```bash
scripts/verify-local.sh
```

## Hermes plugin registration

The local Hermes plugin entry point is `sisyphus_hermes.plugin:register`. After
editable installation, configure Hermes to load that module and call
`register(ctx)`. The context is expected to expose
`register_command(name, handler, **metadata)`. Registration creates the
`sisyphus.*` command namespace and returns structured metadata listing the
registered commands.

Smoke/debug sequence:

```bash
sisyphus-hermes doctor --json
sisyphus-hermes sample-smoke --workspace /tmp/sisyphus-hermes-sample --json
```

`doctor` checks package import readiness, the `sisyphus-hermes` console script
metadata, `plugin.register(ctx)` against a fake Hermes context, bundled skill
frontmatter, workspace `.sisyphus/` writability, generated runtime state
`.gitignore` coverage, local SQLite readiness, and OpenCode/oh-my-openagent
import independence. Runtime artifacts are project-local:

- `.sisyphus/state.sqlite3` — SQLite lifecycle source of truth when Kanban is unavailable;
- `.sisyphus/executor-outbox.jsonl` — append-only external executor handoff log;
- `.sisyphus/kanban.json` — dependency-free local Kanban adapter state.

## State model and recovery

- The intended production source of truth is Hermes Kanban.
- For local/practical Kanban work, `JsonKanbanAdapter` stores Kanban-shaped task
  cards in `.sisyphus/kanban.json` and preserves cards across process restarts.
- When Kanban is unavailable, the local SQLite fallback at
  `.sisyphus/state.sqlite3` stores runs, plans, tasks, review gates, evidence,
  and audit events.
- Re-running `init` is idempotent and recreates the schema if needed.
- `status` and `report` rebuild their view from durable state, not from an
  OpenCode/Codex/Claude TUI or process log. Their structured payloads include
  `state.backend` and `state.path` so operators can verify which fallback store
  is being used after a process restart.

## Command examples

```bash
sisyphus-hermes init --workspace /path/to/repo
sisyphus-hermes start --workspace /path/to/repo --goal "Ship the plugin MVP"
sisyphus-hermes plan --run-id run_... --title "MVP plan" --body "..."
sisyphus-hermes approve-plan --run-id run_... --plan-id plan_...
sisyphus-hermes status --run-id run_...
sisyphus-hermes worker-payload --run-id run_... --task-id task_... --json
sisyphus-hermes dispatch-task --run-id run_... --task-id task_... --executor hermes-profile --json
sisyphus-hermes list-dispatches --run-id run_... --json
sisyphus-hermes claim-dispatch --dispatch-id dispatch_... --executor hermes-profile --json
sisyphus-hermes complete-dispatch --dispatch-id dispatch_... --summary "done" --evidence-uri file://artifact --json
sisyphus-hermes fail-dispatch --dispatch-id dispatch_... --reason "tests failed" --json
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
Pause/cancel reports include incomplete tasks and any known child process handles
provided by executor adapters so recovery can happen without reading TUI/process
logs.

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
future executor adapters under `src/sisyphus_hermes/executors/`. They are peer
executors, not the lifecycle source of truth. The MVP `NoopExecutorAdapter`
intentionally returns `dispatched=false` / `executor_invoked=false` so a queued
worker payload cannot be mistaken for executed implementation work. The
`OutboxExecutorAdapter` is the first practical handoff adapter: `dispatch-task`
writes an auditable JSONL record to `.sisyphus/executor-outbox.jsonl`, returns
`dispatched=true`, and still returns `executor_invoked=false` because no child
process is spawned by core lifecycle code. External peers consume that outbox and
report lifecycle progress through `claim-dispatch`, `complete-dispatch`, or
`fail-dispatch`. The outbox is append-only: queued/claimed/completed/failed
events are materialized by `list-dispatches`, completed or failed dispatches are
terminal, and retrying failed work requires a new `dispatch-task` record. The
core plugin must continue to pass tests without those tools installed.
