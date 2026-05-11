# sisyphus-hermes

Hermes-native Sisyphus plugin project.

This repository is being implemented from the Ouroboros Seed at
`.ouroboros/seeds/sisyphus-hermes.seed.yaml`. The goal is to port the useful
ideas of oh-my-openagent's Sisyphus/Ultraworker into a Hermes-native full plugin
architecture: durable task lifecycle, Kanban-backed orchestration, profile-aware
workers, review gates, and Telegram-friendly status reporting.

## Current bootstrap

AC01 repository bootstrap is represented by:

- `pyproject.toml` — installable Python package metadata and test config.
- `src/sisyphus_hermes/` — importable package and plugin registration boundary.
- `tests/` — pytest package with import/file-existence smoke tests.
- `docs/architecture.md` — initial architecture note.
- `skills/sisyphus-ultraworker/SKILL.md` — first bundled worker skill.
- `.gitignore` — excludes Python/runtime/secrets artifacts.
- `.ouroboros/seeds/sisyphus-hermes.seed.yaml` — source Seed and AC traceability.

## Development commands

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m sisyphus_hermes.cli doctor --json
```

For normal package use, install the project in editable mode first:

```bash
python -m pip install -e .
python -m pip install -e '.[dev]'  # optional: test/lint tools
sisyphus-hermes doctor --json
sisyphus-hermes sample-smoke --workspace /tmp/sisyphus-hermes-sample --json
sisyphus-hermes status --workspace /tmp/sisyphus-hermes-sample --json
```

`sample-smoke` is the mechanical local install/load contract: it initializes a
sample workspace, runs `doctor`, creates a sample run, enqueues/dispatches/
claims/completes a sample outbox task without spawning an executor process, and
proves `status`/`report` can rebuild from the project-local SQLite source of
truth.
## Acceptance criteria traceability

- AC01_repo_bootstrap: `tests/test_bootstrap.py` verifies required files and
  package import smoke behavior.
- AC02_plugin_registration: `tests/test_plugin_registration.py` verifies the
  runtime-light `register(ctx)` entry point and full `sisyphus.*` command
  registration against a fake Hermes context.
- AC03_command_surface: `src/sisyphus_hermes/commands.py` exposes `init`,
  `start`, `plan`, `approve-plan`, `status`, `pause`, `resume`, `cancel`,
  `review`, `report`, `doctor`, `sample-smoke`, `enqueue-event`,
  `worker-payload`, `dispatch-task`, `list-dispatches`, `claim-dispatch`,
  `complete-dispatch`, and `fail-dispatch` handlers with structured results.
- AC04_draft_to_canonical_plan: `approve-plan` promotes draft plans to
  canonical and blocks normal execution until a canonical plan exists unless a
  bounded spike is explicitly allowed.
- AC05_durable_state / AC22_sqlite_fallback_contract: `SQLiteStateStore`
  persists runs, plans, tasks, gates, evidence, and append-only audit events
  across process restarts; command `status`/`report` results expose the active
  fallback backend and project-local `.sisyphus/state.sqlite3` path.
- AC06_kanban_boundary: `state.py` defines a fake-testable Kanban adapter
  protocol, `kanban.py` provides a dependency-free JSON Kanban board adapter,
  and the runtime falls back to project-local SQLite when Kanban is unavailable.
- AC07_preflight_safety / AC08_destructive_guardrails: `safety.py` provides git
  preflight inspection and destructive-operation classification primitives.
- AC09_worker_context / optional executor extension: `workers.py` builds
  explicit scoped payloads with repo path, task description, acceptance
  criteria, safety constraints, and reporting contract; `executors/` exposes a
  no-op adapter plus a durable append-only JSONL outbox adapter for explicit
  peer handoff. No payload relies on hidden chat/TUI context, outbox dispatch
  records `executor_invoked=false` until a separate peer consumes them, and
  claim/complete/fail lifecycle commands materialize task/evidence/audit state.
- AC10_review_gates / AC11_reporting: review gate persistence and
  Telegram-friendly status/report rendering are covered by tests.
- AC12_cancellation_pause: pause/cancel transitions record audit events and
  status/report output includes incomplete tasks plus known child process handles
  when provided.
- AC13_bundled_skills: Sisyphus, Metis, and Momus role skills live under
  `skills/` with trigger/workflow/pitfalls/verification sections.
- AC14_documentation: `docs/user-guide.md` covers install/setup, command usage,
  safety, recovery, cron/event task ingestion, and executor extension.
- AC15_no_opencode_dependency: `tests/test_runtime_quality_contracts.py` scans
  core source imports for OpenCode/oh-my-openagent packages and `doctor` exposes
  the mechanical scan result.
- AC16_test_suite: `python -m pytest -q` is the canonical local suite and covers
  domain models, SQLite/Kanban boundaries, command handlers, safety, reporting,
  plugin registration, skills, and runtime quality contracts.
- AC17_lint_type_baseline: development commands document and verify the current
  `pytest`, `ruff`, and `compileall` baseline.
- AC18_seed_traceability: this README links the source Seed at
  `.ouroboros/seeds/sisyphus-hermes.seed.yaml` and maps every Seed acceptance
  criterion to code, docs, or test evidence.
- AC19_actor_input_output_runtime_closure: `docs/architecture.md` and command
  result schemas model the Seed actors, accepted inputs, produced outputs,
  runtime context, MVP boundaries, and deferred/non-goal boundaries.
- AC20_cron_event_to_task_only: `events.py` and `CommandService.enqueue_event`
  create durable task records from cron/webhook payloads without invoking an
  executor adapter.
- AC21_role_last_action_visibility: `reporting.py` renders latest Metis,
  Momus, Sisyphus, Hephaestus, and Hermes-Sheriff actions in both status and
  report output, covered by `tests/test_safety_reporting.py`.
- AC22_sqlite_fallback_contract: `tests/test_domain_state_commands.py` verifies
  project-local SQLite persistence and command recovery without a live Kanban
  backend.
