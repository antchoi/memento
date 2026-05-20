# Getting Started with Memento

This guide takes you from an installed Memento checkout to a verified local Memento run. If you have not installed Memento yet, start with [`guide/installation.md`](guide/installation.md); it includes an agent-executable install script, dependency setup, Hermes plugin notes, and optional local agentmemory Docker integration.

## Prerequisites

- Python 3.11 or newer.
- A local checkout of the Memento repository.
- Optional development tools from `.[dev]`: pytest and ruff.

## Install

Preferred agent-executable path from the repository root:

```bash
scripts/install-local.sh
```

Manual equivalent:

```bash
python -m pip install -e .
python -m pip install -e '.[dev]'
```

See [`guide/installation.md`](guide/installation.md) for virtualenv creation, dependency automation, Hermes plugin enablement, and optional agentmemory setup.

## Verify readiness

```bash
memento doctor --json
```

`doctor` checks:

- package import readiness;
- console script metadata;
- Hermes plugin entry point metadata;
- `plugin.register(ctx)` with a fake Hermes context;
- bundled skill frontmatter;
- workspace runtime-state writability;
- runtime `.gitignore` coverage;
- local SQLite readiness;
- OpenCode/oh-my-openagent import independence.

## Run the smoke contract

```bash
memento sample-smoke --workspace /tmp/memento-sample --json
memento status --workspace /tmp/memento-sample --json
memento report --workspace /tmp/memento-sample
```

The smoke contract proves Memento can:

1. initialize workspace-local state;
2. create a run;
3. enqueue a task;
4. write an executor outbox handoff;
5. claim and complete the dispatch;
6. reconstruct status and report output from durable state.

It intentionally does **not** spawn an external executor process.

## Create your first real run

```bash
memento init --workspace /path/to/repo --json
memento start --workspace /path/to/repo --goal "Ship the next verified slice" --allow-spike --json
```

Capture the returned `run.id`.

## Add a canonical plan

Normal execution should be based on a canonical plan.

```bash
memento plan \
  --workspace /path/to/repo \
  --run-id run_... \
  --title "Next verified slice" \
  --body "1. Add failing test. 2. Implement. 3. Verify. 4. Report evidence." \
  --json

memento approve-plan \
  --workspace /path/to/repo \
  --run-id run_... \
  --plan-id plan_... \
  --json
```

## Enqueue a task

```bash
memento enqueue-event \
  --workspace /path/to/repo \
  --run-id run_... \
  --title "Implement the next slice" \
  --body "Concrete task details and acceptance criteria" \
  --json
```

Capture the returned `task.id`.

## Generate context or dispatch a handoff

```bash
memento worker-payload --workspace /path/to/repo --run-id run_... --task-id task_... --json
memento context-bundle --workspace /path/to/repo --run-id run_... --task-id task_... --json
memento dispatch-task --workspace /path/to/repo --run-id run_... --task-id task_... --executor hermes-profile --json
```

`dispatch-task` writes an auditable handoff. It does not claim that implementation happened. Completion requires later evidence.

## Complete with evidence

```bash
memento claim-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --executor hermes-profile --json
memento complete-dispatch \
  --workspace /path/to/repo \
  --dispatch-id dispatch_... \
  --summary "Implemented and verified" \
  --evidence-uri file://verification/task.log \
  --json
```

## Report

```bash
memento status --workspace /path/to/repo --run-id run_... --json
memento report --workspace /path/to/repo --run-id run_...
```

Reports are designed to be readable in Telegram and other chat surfaces.

## Full local verification

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
scripts/verify-local.sh
```
