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
PYTHONPATH=src python -m sisyphus_hermes.cli doctor --json
```

For normal package use, install the project in editable mode first:

```bash
python -m pip install -e '.[dev]'
sisyphus-hermes doctor --json
```

## Acceptance criteria traceability

- AC01_repo_bootstrap: `tests/test_bootstrap.py` verifies required files and
  package import smoke behavior.
- AC02_plugin_registration: `tests/test_plugin_registration.py` verifies the
  runtime-light `register(ctx)` entry point and full `sisyphus.*` command
  registration against a fake Hermes context.
- AC03_command_surface: `src/sisyphus_hermes/commands.py` exposes `init`,
  `start`, `plan`, `approve-plan`, `status`, `pause`, `resume`, `cancel`,
  `review`, `report`, and `doctor` handlers with structured results.
- AC04_draft_to_canonical_plan: `approve-plan` promotes draft plans to
  canonical and blocks normal execution until a canonical plan exists unless a
  bounded spike is explicitly allowed.
- AC05_durable_state / AC22_sqlite_fallback_contract: `SQLiteStateStore`
  persists runs, plans, tasks, gates, evidence, and append-only audit events
  across process restarts.
- AC07_preflight_safety / AC08_destructive_guardrails: `safety.py` provides git
  preflight inspection and destructive-operation classification primitives.
- AC10_review_gates / AC11_reporting: review gate persistence and
  Telegram-friendly status/report rendering are covered by tests.
- Later ACs around Kanban adapter integration, full worker dispatch, bundled
  role skills, and end-to-end Hermes runtime validation remain in progress.
