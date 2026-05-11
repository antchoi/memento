# sisyphus-hermes Architecture

`sisyphus-hermes` is a Hermes-native lifecycle plugin inspired by Sisyphus/Ultraworker workflows. It deliberately avoids treating OpenCode/Codex/Claude Code process logs or TUIs as the core source of truth. Those tools can later be optional executor peers; the plugin state model remains Hermes-owned.

## Runtime boundary

- `sisyphus_hermes.plugin.register(ctx)` is runtime-light and safe to import without Hermes gateway, Kanban, or optional executor packages.
- `doctor` mechanically scans core module imports for OpenCode/oh-my-openagent packages and reports `opencode_import_scan` so AC15 can be checked without relying on the developer machine's installed tools.
- The initial command surface is registered as `sisyphus.*` commands:
  - `init`
  - `start`
  - `plan`
  - `approve-plan`
  - `status`
  - `pause`
  - `resume`
  - `cancel`
  - `review`
  - `report`
  - `doctor`
  - `sample-smoke`
  - `enqueue-event`
  - `worker-payload`
  - `dispatch-task`
  - `list-dispatches`
  - `claim-dispatch`
  - `complete-dispatch`
  - `fail-dispatch`
- Internal `TypeError` raised by the registrar is intentionally not swallowed; registration failures must be visible.

## Seed runtime closure

The implementation keeps the Seed vocabulary explicit so runtime state can be
recovered without relying on hidden chat history or an external TUI:

- Actors: `founder_user`, `hermes_plugin_command_layer`, `metis_planner`,
  `momus_reviewer`, `sisyphus_lifecycle_worker`, `hephaestus_executor`,
  `hermes_sheriff`, and future `optional_external_executor_adapter` roles appear
  in domain defaults, audit events, worker payloads, review gates, or docs.
- Accepted inputs: workspace/repository path, user goal/task text, plan approval
  decisions, review decisions, cron/webhook event payloads, safety preflight
  state, and optional child process handles enter through command payloads.
- Produced outputs: command result records, run/plan/task/gate/evidence/audit
  state, SQLite fallback files, Kanban-compatible task records, worker payloads,
  doctor diagnostics, and Telegram-friendly reports.
- Runtime context: local macOS/Hermes development, project-local generated state,
  Hermes Kanban as the intended source of truth, SQLite fallback when Kanban is
  unavailable, and Hermes-native skills/delegation/process primitives.
- MVP boundaries: command handlers, durable lifecycle state, safety/reporting,
  bundled role skills, cron/event task ingestion, and fake-testable adapters are
  in scope; cloud sync, paid services, production deployment, direct destructive
  git operations, and log-scraping supervision are out of scope.
- Deferred extension points: OpenCode, Codex, Claude Code, or Hermes profile
  workers can be added as optional executor peers only after the core lifecycle
  remains Hermes-owned and testable without them.

## Durable lifecycle model

The domain model is defined in `src/sisyphus_hermes/domain.py`:

- `SisyphusRun`: top-level run with goal, workspace, status, actor, source-of-truth metadata, and current canonical plan id.
- `SisyphusPlan`: draft/canonical/superseded plan documents with assumptions, risks, and acceptance criteria.
- `SisyphusTask`: execution unit scaffold for future worker dispatch.
- `ReviewGate`: preflight, plan review, implementation review, quality review, and final acceptance gates.
- `Evidence`: verification artifacts such as test output, lint output, screenshots, or links.
- `AuditEvent`: append-only lifecycle event stream.

## State source of truth

The intended production order is:

1. Hermes Kanban adapter as the primary collaboration/source-of-truth layer.
2. SQLite fallback for local durability, import smoke tests, and recovery.

The current implementation provides a fake-testable Kanban boundary plus the
SQLite fallback contract in `src/sisyphus_hermes/state.py`:

- `KanbanAdapter` defines the minimal task persistence/listing protocol for a
  future Hermes Kanban implementation;
- `JsonKanbanAdapter` in `src/sisyphus_hermes/kanban.py` provides a practical
  dependency-free board at `.sisyphus/kanban.json` for local collaboration,
  smoke testing, and adapter contract development;
- `UnavailableKanbanAdapter` makes fallback behavior explicit when no live
  Kanban database is present;
- schema initialization is idempotent;
- all lifecycle entities are persisted as typed JSON records;
- audit events are append-only;
- state survives process restart;
- repeated status transitions are idempotent and do not duplicate audit events.

## Planning and gates

The current command implementation blocks normal execution (`start` against an existing run) unless one of these is true:

- a canonical plan exists; or
- the caller explicitly sets `allow_spike` for a bounded spike path.

`approve-plan` promotes a draft plan to canonical and records a passed `plan_review` gate. `review` records the requested gate and pauses the run when a gate fails.

## Safety and reporting

`src/sisyphus_hermes/safety.py` provides git preflight and destructive-operation classification primitives:

- dirty worktree detection;
- detached HEAD detection;
- protected branch detection;
- remote discovery;
- untracked file detection;
- guardrails for `git reset --hard`, `git clean`, force push, direct protected-branch push, and merge commands.

`src/sisyphus_hermes/reporting.py` emits Telegram-friendly Markdown without tables so reports remain readable in chat channels.

## Worker dispatch boundary

`src/sisyphus_hermes/workers.py` builds explicit `WorkerPayload` records for
future Hermes profile, delegate_task, or external executor adapters. Payloads
include repo path, goal, task description, acceptance criteria, safety
constraints, and a reporting contract. They intentionally state that workers
must not rely on parent chat history or OpenCode/TUI state.

`src/sisyphus_hermes/executors/` contains the optional executor peer boundary.
The MVP ships `NoopExecutorAdapter`, which returns `dispatched=False` and
`executor_invoked=False` even when the requested peer is named `opencode`,
`codex`, or `claude-code`. It also ships `OutboxExecutorAdapter`, which writes a
JSONL dispatch record to `.sisyphus/executor-outbox.jsonl` and returns
`dispatched=True` while still recording `executor_invoked=False`. The outbox is
append-only: `list-dispatches` materializes queued/claimed/completed/failed
state, external peers report progress via `claim-dispatch`, `complete-dispatch`,
and `fail-dispatch`, and completed/failed dispatches are terminal. That makes
handoff explicit and auditable without spawning child processes or supervising
external logs.

## Cron/event boundary

`src/sisyphus_hermes/events.py` converts cron/webhook payloads into durable
`SisyphusTask` records and append-only audit events. Event ingestion returns
`dispatched=False` and `executor_invoked=False`; implementation work must be
started by an explicit lifecycle/worker action after safety and review checks.
