# Memento Operators Guide

This guide covers safe day-to-day operation of Memento in real repositories.

## Operating principles

1. Verify the target workspace before changing state.
2. Require a canonical plan before normal implementation.
3. Treat dispatches as handoffs, not proof of completion.
4. Accept only independently verifiable evidence.
5. Keep generated runtime state out of commits unless intentionally used as a fixture.
6. Recover from Memento state, not from private executor logs.

## Workspace checks

Before starting or resuming work:

```bash
pwd
git status --short --branch
git branch --show-current
git remote -v
memento doctor --workspace "$PWD" --json
```

If Hermes is running from another directory, pass `--workspace /path/to/repo` explicitly on every command.

## Generated state

Memento writes generated project-local state for recovery and auditability:

- lifecycle SQLite database.
- local JSON Kanban-shaped adapter state.
- append-only executor handoff records.
- worker context bundles.

The repository `.gitignore` should exclude generated Memento runtime state, `.hermes/runtime/`, `.ouroboros/data/`, and `.ouroboros/runs/`.

## Recovery

After a crash, compaction, or lost executor session:

```bash
memento status --workspace /path/to/repo --json
memento report --workspace /path/to/repo
memento list-dispatches --workspace /path/to/repo --json
```

Then regenerate context instead of trying to reconstruct it from chat memory:

```bash
memento context-bundle --workspace /path/to/repo --run-id run_... --task-id task_... --json
memento worker-payload --workspace /path/to/repo --run-id run_... --task-id task_... --json
```

## Safety guardrails

Memento has primitives for git preflight and destructive-operation classification. Operations that should be blocked or require explicit approval include:

- `git reset --hard`;
- `git clean`;
- force push;
- direct protected-branch push;
- merge operations;
- production/release actions when configured by policy;
- secret or forbidden-path exposure.

When in doubt, pause the run and record the reason:

```bash
memento pause --workspace /path/to/repo --run-id run_... --reason "requires user approval" --json
```

## Cron and webhook ingestion

Cron and webhook integrations should enqueue tasks only:

```bash
memento enqueue-event --workspace /path/to/repo --run-id run_... --title "Incoming event" --body "Payload summary" --json
```

They must not directly launch implementation work. A user, reviewer, or lifecycle command should decide whether and how to dispatch the task.

## Executor handoff

Use dispatch commands for auditable handoff:

```bash
memento dispatch-task --workspace /path/to/repo --run-id run_... --task-id task_... --executor hermes-profile --json
memento claim-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --executor hermes-profile --json
memento complete-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --summary "verified" --evidence-uri file://verification/task.log --json
```

Executor self-report is not enough. Completion should link to evidence.

## Reporting

Use `report` for chat surfaces:

```bash
memento report --workspace /path/to/repo --run-id run_...
```

Reports should remain Markdown without tables so they are readable in Telegram and similar clients.

## Graphify and memory

Graphify and memory are context/evidence helpers, not lifecycle truth.

Recommended pattern:

1. Run `graph-status` before significant architectural changes.
2. Run `graph-update` after verified code work or commits.
3. Attach graph warnings as evidence or advisory context.
4. Use memory writeback only for durable reusable lessons.
5. Do not store raw logs, commit hashes, PR numbers, temporary TODOs, or raw graph payloads as long-term memory.

## Local release-candidate verification

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-operator-smoke --json
scripts/verify-local.sh
```
