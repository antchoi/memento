# Memento Documentation

This directory explains how to use, operate, and extend Memento.

## Recommended reading path

1. [`guide/installation.md`](guide/installation.md) — install Memento, optionally enable the Hermes plugin, optionally start local agentmemory with Docker, and verify with executable evidence.
2. [`guide/publishing.md`](guide/publishing.md) — publish `memento-lifecycle` to TestPyPI/PyPI and configure GitHub Actions Trusted Publishing.
3. [`getting-started.md`](getting-started.md) — run `sample-smoke` and create a first durable run after installation.
4. [`concepts.md`](concepts.md) — understand runs, plans, tasks, dispatches, gates, evidence, and reports.
5. [`commands.md`](commands.md) — find commands by workflow.
6. [`operators-guide.md`](operators-guide.md) — operate Memento safely in real repositories.
7. [`architecture.md`](architecture.md) — understand the implementation boundaries and extension points.
8. [`user-guide.md`](user-guide.md) — compact end-to-end guide that ties the pieces together.

## What belongs where

- **README:** first-success path and project positioning.
- **Installation guide:** executable setup, dependency installation, Hermes plugin enablement, and optional agentmemory Docker integration.
- **Publishing guide:** TestPyPI/PyPI release flow, versioning rules, trusted publishing, and token handling.
- **Getting started:** first smoke contract and first run after installation.
- **Concepts:** stable mental model.
- **Commands:** CLI/plugin command reference.
- **Operators guide:** safety, recovery, generated state, cron/webhook ingestion, reporting.
- **Architecture:** implementation internals and extension contracts.
- **Plans:** docs rewrite and implementation planning artifacts.

## Runtime state note

Memento keeps generated lifecycle state project-local. Treat these files as runtime artifacts, not source documentation:

- `state.sqlite3` — lifecycle database.
- `kanban.json` — dependency-free local task store.
- `executor-outbox.jsonl` — append-only executor handoff log.
- `context-bundles/` — regenerated worker context packages.

Do not commit generated runtime state unless a specific fixture or test intentionally requires it.

## Verification

From the repository root:

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-docs-smoke --json
```
