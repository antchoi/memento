# Memento User Guide

This compact guide shows the normal end-to-end Memento workflow. For focused references, see:

- [`getting-started.md`](getting-started.md)
- [`concepts.md`](concepts.md)
- [`commands.md`](commands.md)
- [`operators-guide.md`](operators-guide.md)
- [`architecture.md`](architecture.md)

## 1. Install and check readiness

```bash
python -m pip install -e .
python -m pip install -e '.[dev]'
memento doctor --json
```

For source-only usage:

```bash
PYTHONPATH=src python -m memento.cli doctor --json
```

## 2. Smoke-test the local lifecycle

```bash
memento sample-smoke --workspace /tmp/memento-sample --json
memento status --workspace /tmp/memento-sample --json
memento report --workspace /tmp/memento-sample
```

`sample-smoke` is the recommended post-install contract. It initializes a sample workspace, creates a run, enqueues a task, queues/claims/completes an outbox dispatch without spawning an executor process, and verifies status/report recovery from durable state.

## 3. Initialize a project workspace

```bash
memento init --workspace /path/to/repo --json
memento start --workspace /path/to/repo --goal "Ship the next verified slice" --allow-spike --json
```

Capture the returned `run.id`.

## 4. Create the canonical plan

```bash
memento plan \
  --workspace /path/to/repo \
  --run-id run_... \
  --title "Implementation plan" \
  --body "Write tests, implement the slice, verify, and record evidence." \
  --json

memento approve-plan \
  --workspace /path/to/repo \
  --run-id run_... \
  --plan-id plan_... \
  --json
```

Normal execution is blocked until a canonical plan exists unless the run was explicitly started as a bounded spike.

## 5. Enqueue and dispatch work

```bash
memento enqueue-event \
  --workspace /path/to/repo \
  --run-id run_... \
  --title "Implement task" \
  --body "Task details and acceptance criteria" \
  --json

memento worker-payload --workspace /path/to/repo --run-id run_... --task-id task_... --json
memento dispatch-task --workspace /path/to/repo --run-id run_... --task-id task_... --executor hermes-profile --json
```

A dispatch is an auditable handoff, not proof that work is complete.

## 6. Record completion and evidence

```bash
memento claim-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --executor hermes-profile --json
memento complete-dispatch \
  --workspace /path/to/repo \
  --dispatch-id dispatch_... \
  --summary "Implemented and verified" \
  --evidence-uri file://verification/task.log \
  --json
```

Evidence should be independently checkable: test output, CI links, lint logs, generated artifacts, review decisions, or approval records.

## 7. Report and recover

```bash
memento status --workspace /path/to/repo --run-id run_... --json
memento report --workspace /path/to/repo --run-id run_...
memento list-dispatches --workspace /path/to/repo --run-id run_... --json
```

Reports are reconstructed from durable state and formatted for chat. If an executor session disappears, regenerate recovery handoff bundles from canonical state instead of relying on the lost session:

```bash
memento recover-jobs --workspace /path/to/repo --run-id run_... --json
```

If you also want Memento to reconcile the stale outbox handoff and queue a fresh restart handoff, add `--requeue`:

```bash
memento recover-jobs --workspace /path/to/repo --run-id run_... --requeue --executor hermes-profile --json
```

The old nonterminal dispatch is marked `recovered`, the new dispatch stays queued with `executor_invoked=false`, and `report` shows the recovered → requeued flow.

For a single explicit worker handoff bundle, use:

```bash
memento context-bundle --workspace /path/to/repo --run-id run_... --task-id task_... --json
```

## Hermes plugin registration

The plugin entry point is `memento.plugin:register`. A Hermes-like context needs a `register_command(name, handler, **metadata)` method. Registration creates the `memento.*` command namespace and returns structured metadata.

Debug sequence:

```bash
memento doctor --json
memento sample-smoke --workspace /tmp/memento-sample --json
```

## Runtime state

Generated state is project-local:

- SQLite lifecycle state;
- local Kanban adapter state;
- append-only external executor handoff log;
- explicit worker context packages.

Treat generated state as Memento runtime data. Do not use it as proof of completion without corresponding evidence records and verification output.

## Safety model

Memento workers receive explicit payloads containing workspace, goal, task, acceptance criteria, safety constraints, and reporting contract. They must not depend on hidden parent chat history.

Guarded operations include destructive git commands such as `git reset --hard` and `git clean`, protected-branch pushes, force pushes, merge operations, release actions, and secret/forbidden-path exposure.

## Cron and webhook events

Cron/webhook integrations may enqueue durable tasks only. They must not directly dispatch implementation work.

```bash
memento enqueue-event --workspace /path/to/repo --run-id run_... --title "Incoming event" --body "Payload summary" --json
```

## Optional executor extension

Optional executor extension adapters can live under `src/memento/executors/`. They are future/experimental peer handoff targets, not the lifecycle source of truth and not part of the installation guide. Core Memento should keep passing tests without OpenCode, Codex, Claude Code, OpenHands, or other external executor packages installed.

## Full verification

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
scripts/verify-local.sh
```
