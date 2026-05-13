# Memento

Memento is a Hermes-native lifecycle and evidence ledger for software work: it turns vague goals into durable runs, plans, tasks, review gates, dispatch records, and verification evidence that survive chat resets, process restarts, and disposable executor sessions.

## Why Memento exists

Agent coding often fails because progress lives in the wrong place: a chat transcript, a TUI buffer, an executor-native session, or a self-reported summary. Memento keeps the source of truth outside those fragile contexts.

Use Memento when you want to:

- keep a canonical plan before implementation starts;
- route work to humans, Hermes, or optional external executors without trusting their summaries blindly;
- record evidence, review gates, approvals, and failures in project-local durable state;
- recover long-running work after compaction, process restarts, or executor crashes;
- report progress in Telegram-friendly Markdown without scraping logs.

## What Memento is — and is not

Memento **is**:

- a Python package and CLI (`memento`);
- a Hermes plugin entry point (`memento.plugin`);
- a lifecycle state model for runs, plans, tasks, gates, dispatches, audit events, and evidence;
- a local-first durability layer using project-local SQLite and JSON state;
- an extension boundary for optional workers such as Hermes profiles, Codex, Claude Code, OpenCode, OpenHands-style API workers, or other peers.

Memento **is not**:

- an OpenCode wrapper;
- a compatibility shim for another lifecycle project;
- a replacement for tests, review, or user approval;
- a tool that treats executor self-report as proof;
- dependent on private TUI/session state for correctness.

## Quick install

From the repository root:

```bash
python -m pip install -e .
python -m pip install -e '.[dev]'  # optional: pytest and ruff
memento doctor --json
```

Without installing the console script:

```bash
PYTHONPATH=src python -m memento.cli doctor --json
```

## Start in 5 minutes

Run the local smoke contract:

```bash
memento sample-smoke --workspace /tmp/memento-sample --json
memento status --workspace /tmp/memento-sample --json
memento report --workspace /tmp/memento-sample
```

`sample-smoke` initializes a workspace, runs `doctor`, creates a sample run, enqueues a task, writes an outbox dispatch, claims/completes it without spawning an executor process, and proves `status`/`report` can rebuild from durable project-local state.

## First 15 minutes

1. **Check readiness**

   ```bash
   memento doctor --json
   ```

2. **Initialize a real workspace**

   ```bash
   memento init --workspace /path/to/repo --json
   ```

3. **Start a run**

   ```bash
   memento start --workspace /path/to/repo --goal "Ship the next verified slice" --allow-spike --json
   ```

4. **Create and approve a canonical plan**

   ```bash
   memento plan --workspace /path/to/repo --run-id run_... --title "Next slice" --body "Plan body" --json
   memento approve-plan --workspace /path/to/repo --run-id run_... --plan-id plan_... --json
   ```

5. **Turn incoming work into a durable task**

   ```bash
   memento enqueue-event --workspace /path/to/repo --run-id run_... --title "Implement X" --body "Task details" --json
   ```

6. **Generate a worker payload or dispatch handoff**

   ```bash
   memento worker-payload --workspace /path/to/repo --run-id run_... --task-id task_... --json
   memento dispatch-task --workspace /path/to/repo --run-id run_... --task-id task_... --executor hermes-profile --json
   ```

7. **Record completion with evidence**

   ```bash
   memento claim-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --executor hermes-profile --json
   memento complete-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --summary "verified" --evidence-uri file://verification/task.log --json
   ```

8. **Report status**

   ```bash
   memento status --workspace /path/to/repo --run-id run_... --json
   memento report --workspace /path/to/repo --run-id run_...
   ```

## Core lifecycle

- **Run:** top-level unit of work tied to a workspace and goal.
- **Plan:** draft or canonical implementation plan. Normal execution is gated on a canonical plan unless an explicit bounded spike is allowed.
- **Task:** durable work item from a plan, user request, cron event, webhook, or manual enqueue.
- **Dispatch:** auditable handoff to a human or optional executor. Dispatch records do not imply work happened unless evidence later proves it.
- **Review gate:** preflight, plan review, implementation/spec review, quality review, final acceptance, approval, or release gate.
- **Evidence:** trusted artifacts such as test output, CI status, lint output, verification logs, screenshots, or approval records.
- **Report:** Telegram-friendly summary reconstructed from state, not from hidden executor memory.

## Command map

Read the full command guide in [`docs/commands.md`](docs/commands.md). The main workflows are:

- setup and health: `doctor`, `init`, `sample-smoke`;
- lifecycle: `start`, `plan`, `approve-plan`, `pause`, `resume`, `cancel`, `status`, `report`;
- tasks and handoff: `enqueue-event`, `worker-payload`, `dispatch-task`, `list-dispatches`, `claim-dispatch`, `complete-dispatch`, `fail-dispatch`;
- verification and context: `context-bundle`, `route-task`, `verify-task`, `graph-status`, `graph-update`, `memory-prefetch`, `memory-writeback`;
- v3 worker platform: `record-external-check`, `record-approval`, `select-patch`, `release-gate`, `recover-jobs`;
- review: `review`.

## Hermes plugin boundary

The local Hermes plugin entry point is `memento.plugin:register`. The package also advertises the Python entry point group:

```toml
[project.entry-points."hermes_agent.plugins"]
memento = "memento.plugin"
```

The registration boundary is intentionally runtime-light. A Hermes-like context only needs:

```python
ctx.register_command(name, handler, **metadata)
```

`doctor` and `tests/test_plugin_registration.py` are the executable registration contract.

## Documentation

Start here:

- [`docs/README.md`](docs/README.md) — documentation map.
- [`docs/getting-started.md`](docs/getting-started.md) — install, smoke test, and first run.
- [`docs/concepts.md`](docs/concepts.md) — lifecycle concepts and trust model.
- [`docs/commands.md`](docs/commands.md) — command reference by workflow.
- [`docs/operators-guide.md`](docs/operators-guide.md) — safety, recovery, cron/events, reporting.
- [`docs/architecture.md`](docs/architecture.md) — implementation architecture and extension points.
- [`docs/user-guide.md`](docs/user-guide.md) — compact end-to-end guide.

## Development verification

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-sample --json
scripts/verify-local.sh
```

## Seed and acceptance criteria traceability

The implementation history is driven by the Ouroboros source Seed at `.ouroboros/seeds/memento.seed.yaml` and follow-on phase seeds:

- `.ouroboros/seeds/memento.seed.yaml`
- `.ouroboros/seeds/memento-mvp.seed.yaml`
- `.ouroboros/seeds/memento-v1.seed.yaml`
- `.ouroboros/seeds/memento-v2.seed.yaml`
- `.ouroboros/seeds/memento-v3.seed.yaml`

Acceptance-criteria tokens retained for traceability:

- `AC01_repo_bootstrap`
- `AC02_plugin_registration`
- `AC03_command_surface`
- `AC04_draft_to_canonical_plan`
- `AC05_durable_state`
- `AC06_kanban_boundary`
- `AC07_preflight_safety`
- `AC08_destructive_guardrails`
- `AC09_worker_context`
- `AC10_review_gates`
- `AC11_reporting`
- `AC12_cancellation_pause`
- `AC13_bundled_skills`
- `AC14_documentation`
- `AC15_no_opencode_dependency`
- `AC16_test_suite`
- `AC17_lint_type_baseline`
- `AC18_seed_traceability`
- `AC19_actor_input_output_runtime_closure`
- `AC20_cron_event_to_task_only`
- `AC21_role_last_action_visibility`
- `AC22_sqlite_fallback_contract`

Use the seed files for detailed acceptance criteria. The README stays focused on first success and orientation while preserving mechanical traceability.
