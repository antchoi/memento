# sisyphus-hermes Architecture

`sisyphus-hermes` is a Hermes-native lifecycle plugin inspired by Sisyphus/Ultraworker workflows. It deliberately avoids treating OpenCode/Codex/Claude Code process logs or TUIs as the core source of truth. Those tools can later be optional executor peers; the plugin state model remains Hermes-owned.

## Runtime boundary

- `sisyphus_hermes.plugin.register(ctx)` is runtime-light and safe to import without Hermes gateway, Kanban, or optional executor packages.
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
- Internal `TypeError` raised by the registrar is intentionally not swallowed; registration failures must be visible.

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

The current implementation provides the SQLite fallback contract in `src/sisyphus_hermes/state.py`:

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
