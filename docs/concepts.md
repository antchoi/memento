# Memento Concepts

Memento is easiest to understand as a lifecycle ledger. It records what should happen, who or what was asked to do it, what evidence came back, and which gates accepted or blocked progress.

## Source-of-truth rule

Memento state is authoritative for lifecycle progress. Executor summaries, chat messages, TUI buffers, and reasoning traces are advisory unless they are linked to trusted evidence.

Trusted evidence includes:

- command output with exit code;
- test, lint, type, compile, smoke, or CI results;
- generated artifacts with stable paths;
- explicit user/team approvals;
- code diffs or committed files verified from the worktree;
- graph or memory snapshots when they are treated as evidence, not as hidden state.

Advisory-only data includes:

- “I finished” summaries from an executor;
- unverified reasoning traces;
- private executor session state;
- raw chat history without linked artifacts.

## Lifecycle objects

### Run

A run is the top-level unit of work. It has a workspace, goal, status, actor, source-of-truth metadata, and optionally a current canonical plan.

Typical statuses include draft/planned/running/paused/completed/cancelled/failed style states, depending on the command path.

### Plan

A plan captures the intended work. Plans can be draft, canonical, or superseded. Normal implementation should wait for a canonical plan unless the user explicitly allows a bounded spike.

### Task

A task is a durable work item. Tasks can come from:

- a plan;
- a user request;
- `enqueue-event`;
- a cron/webhook payload;
- a manually created dispatch workflow.

### Dispatch

A dispatch is a handoff record. It can target a human, Hermes profile, or optional executor peer. A dispatch is not proof that work happened.

The default outbox flow writes append-only handoff records and uses:

- `dispatch-task`
- `list-dispatches`
- `claim-dispatch`
- `complete-dispatch`
- `fail-dispatch`

### Review gate

A review gate records a decision that can pass, fail, block, pause, or require approval. Common gates include:

- preflight safety;
- plan review;
- implementation/spec review;
- quality review;
- final acceptance;
- release approval.

### Evidence

Evidence links claims to artifacts. Examples:

- `file://verification/pytest.log`
- GitHub Actions run URL;
- smoke-test output;
- approval record;
- Graphify checkpoint diff;
- generated context bundle path.

### Audit event

Audit events are append-only lifecycle history. They make recovery possible after process restarts or lost chat context.

### Report

A report is a Telegram-friendly Markdown projection of durable state. It is reconstructed from Memento state, not from executor memory.

## Generated state

Memento writes project-local generated state for recovery and auditability:

- lifecycle database — local SQLite source of truth.
- Kanban task store — dependency-free local task state.
- executor outbox — append-only handoff log.
- context bundles — regenerated context packages for workers.

These are runtime artifacts, not a substitute for verified evidence.

## Optional executors

Memento can hand work to executor peers, but it does not depend on them for correctness. Optional executor classes include:

- Hermes profile workers;
- Codex;
- Claude Code;
- OpenCode;
- OpenHands-style API/sandbox workers;
- human operators.

Executor integrations must follow these rules:

1. Receive explicit context bundles.
2. Avoid hidden parent-chat dependencies.
3. Report results back through Memento commands.
4. Link completion to independently verifiable evidence.
5. Preserve Memento as the recovery and reporting source of truth.

## Graph and memory concepts

Memento can use Graphify and agentmemory-style signals as derived context:

- Graphify helps reason about architecture impact and regression risk.
- Memory helps recall durable project lessons and executor performance patterns.

Neither replaces lifecycle truth. Graph and memory outputs should be attached as evidence or advisory context.
