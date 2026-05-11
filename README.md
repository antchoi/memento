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
  runtime-light `register(ctx)` entry point against a fake Hermes context.
- Later ACs are intentionally scaffolded but not claimed complete yet.
