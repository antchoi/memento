# memento Architecture

`memento` is a Hermes-native lifecycle plugin for durable planning, dispatch, evidence, and reporting. The supported public onboarding path is Hermes Agent. Memento deliberately avoids treating OpenCode/Codex/Claude Code process logs or TUIs as the core source of truth; those tools can later be optional executor peers only if explicit adapters are built. The plugin state model remains Memento-owned.

## Runtime boundary

- `memento.plugin.register(ctx)` is runtime-light and safe to import without Hermes gateway, Kanban, or optional executor packages.
- Local Hermes registration loads `memento.plugin:register`; a Hermes-like context only needs `register_command(name, handler, **metadata)`, and the fake-context tests are the executable registration contract.
- `doctor` mechanically checks package import readiness, console-script metadata, `plugin.register(ctx)` smoke output, bundled skill frontmatter, workspace runtime-state writability, runtime `.gitignore` coverage, and the OpenCode/oh-my-openagent import independence scan.
- The initial command surface is registered as `memento.*` commands:
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
  `momus_reviewer`, `memento_lifecycle_worker`, `hephaestus_executor`,
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

The domain model is defined in `src/memento/domain.py`:

- Run: top-level lifecycle record with goal, workspace, status, actor, source-of-truth metadata, and current canonical plan id.
- Plan: draft/canonical/superseded plan documents with assumptions, risks, and acceptance criteria.
- Task: execution unit scaffold for worker dispatch.
- `ReviewGate`: preflight, plan review, implementation review, quality review, and final acceptance gates.
- `Evidence`: verification artifacts such as test output, lint output, screenshots, or links.
- `AuditEvent`: append-only lifecycle event stream.

## State source of truth

The intended production order is:

1. Hermes Kanban adapter as the primary collaboration/source-of-truth layer.
2. SQLite fallback for local durability, import smoke tests, and recovery.

The current implementation provides a fake-testable Kanban boundary plus the
SQLite fallback contract in `src/memento/state.py`:

- `KanbanAdapter` defines the minimal task persistence/listing protocol for a
  future Hermes Kanban implementation;
- `JsonKanbanAdapter` in `src/memento/kanban.py` provides a practical
  dependency-free local board for collaboration, smoke testing, and adapter
  contract development;
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

`src/memento/safety.py` provides git preflight and destructive-operation classification primitives:

- dirty worktree detection;
- detached HEAD detection;
- protected branch detection;
- remote discovery;
- untracked file detection;
- guardrails for `git reset --hard`, `git clean`, force push, direct protected-branch push, and merge commands.

`src/memento/reporting.py` emits Telegram-friendly Markdown without tables so reports remain readable in chat channels.

## Worker dispatch boundary

`src/memento/workers.py` builds explicit `WorkerPayload` records for
future Hermes profile, delegate_task, or external executor adapters. Payloads
include repo path, goal, task description, acceptance criteria, safety
constraints, and a reporting contract. They intentionally state that workers
must not rely on parent chat history or OpenCode/TUI state.

`src/memento/executors/` contains the optional executor peer boundary.
The MVP ships `NoopExecutorAdapter`, which returns `dispatched=False` and
`executor_invoked=False` even when the requested peer is named `opencode`,
`codex`, or `claude-code`. It also ships `OutboxExecutorAdapter`, which writes a
JSONL dispatch record and returns `dispatched=True` while still recording
`executor_invoked=False`. The outbox is
append-only: `list-dispatches` materializes queued/claimed/completed/failed
state, external peers report progress via `claim-dispatch`, `complete-dispatch`,
and `fail-dispatch`, and completed/failed/recovered dispatches are terminal.
`recover-jobs --requeue` marks stale nonterminal dispatches as recovered, queues
a fresh restart handoff linked to the regenerated context bundle, and keeps
`executor_invoked=false` until an explicit worker invocation is requested. That makes
handoff explicit and auditable without spawning child processes or supervising
external logs.

## Cron/event boundary

`src/memento/events.py` converts cron/webhook payloads into durable task
records and append-only audit events. Event ingestion returns
`dispatched=False` and `executor_invoked=False`; implementation work must be
started by an explicit lifecycle/worker action after safety and review checks.
