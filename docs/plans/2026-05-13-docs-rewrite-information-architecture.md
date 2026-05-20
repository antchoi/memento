# Memento Documentation Rewrite Information Architecture Plan

> **For Hermes:** Use this as the governing plan for rewriting the Memento README and `docs/` guides. The target repository is `/Users/yhchoi/workspace/memento`, branch `ooo/run/memento-mvp-implementation`, remote `git@github.com:antchoi/memento.git`.

**Goal:** Rework Memento documentation so a new user can understand, install, smoke-test, operate, and extend Memento without reading implementation history or Ouroboros acceptance criteria first.

**Architecture:** Keep `README.md` as the first-success path and project positioning. Move durable explanations into `docs/` grouped by reader intent: start, concepts, command reference, operator guide, architecture, and roadmap/traceability. Preserve the MVP truth that Memento is a Hermes-native lifecycle/evidence ledger, not an OpenCode session wrapper.

**Tech Stack:** Python 3.11+, editable Python package, `memento` console script, Hermes plugin entry point `memento.plugin`, project-local SQLite/JSON runtime state, pytest/ruff/compileall verification.

---

## Reference project analysis

### opencode

Observed shape:

- Large README covering overview, install methods, configuration, supported models, usage, non-interactive mode, flags, and keyboard shortcuts.
- Strength: direct command examples and complete reference coverage.
- Weakness for Memento: too much reference material in one README; Memento should not bury lifecycle concepts under a giant command matrix.

Borrow:

- Quick install and immediate command examples.
- Clear CLI-first usage section.

Avoid:

- README as exhaustive manual.
- Long provider/config matrices in the landing page.

### oh-my-pi

Observed shape:

- Long feature-highlight README with a strong “First 15 Minutes” path.
- Emphasizes hands-on onboarding before deep configuration.
- Uses highlights to communicate why the project matters.

Borrow:

- “First 15 Minutes” flow.
- Highlights framed around user outcomes.

Avoid:

- Feature firehose before a user knows the core object model.

### oh-my-openagent

Observed shape:

- README includes human-facing and Hermes Agent-facing install paths.
- Strong disciplined-agent positioning around planning, review, and orchestration.
- Clear personality/vision, but can be too hype-heavy for Memento’s current MVP state.

Borrow:

- Agent-facing copy-paste install/use instructions.
- Strong distinction between disciplined lifecycle and ad-hoc agent execution.

Avoid:

- Implying Memento already directly supervises every external agent runtime.
- Presenting optional OpenCode/Codex/Claude integrations as core dependencies.

## Current Memento docs audit

Current hand-authored docs:

- `README.md`
- `docs/user-guide.md`
- `docs/architecture.md`
- bundled role skills under `skills/*/SKILL.md`
- seed specs under `.ouroboros/seeds/*.yaml`

Problems:

- README is dominated by bootstrap/AC traceability rather than reader onboarding.
- `docs/user-guide.md` mixes install, plugin registration, state recovery, examples, safety, cron/events, and executor extension.
- `docs/architecture.md` is accurate but too implementation-dense as an entry point.
- No docs landing/index page.
- No separated command reference.
- No dedicated concepts page explaining runs, plans, gates, tasks, dispatches, evidence, and generated runtime state.
- The project boundary should be explicit: Memento is an independent lifecycle project, not a compatibility layer.
- Acceptance criteria traceability is important but should be moved below the onboarding path, not dominate the README.

## Proposed documentation tree

```text
README.md                         # first-success path and project map

docs/
  README.md                       # docs navigation hub
  getting-started.md              # install, doctor, sample-smoke, first run
  concepts.md                     # lifecycle object model and trust model
  commands.md                     # command reference by workflow
  operators-guide.md              # safety, recovery, state, cron/events, reporting
  architecture.md                 # implementation architecture and extension points
  user-guide.md                   # transitional end-to-end guide; can later shrink or redirect
  plans/
    2026-05-13-docs-rewrite-information-architecture.md
```

Later split candidates:

```text
docs/reference/command-schema.md
docs/reference/state-files.md
docs/developer/plugin-registration.md
docs/developer/executor-adapters.md
docs/traceability/acceptance-criteria.md
```

## README outline

1. One-sentence definition.
2. Why Memento exists.
3. What Memento is / is not.
4. Quick install.
5. Start in 5 minutes.
6. First 15 minutes.
7. Core lifecycle concepts.
8. Command map.
9. Hermes plugin boundary.
10. Documentation map.
11. Development verification.
12. Acceptance criteria / seed traceability pointer.

## First writing batch

- Rewrite `README.md` as the first-success path.
- Add `docs/README.md` as the docs hub.
- Add `docs/getting-started.md`.
- Add `docs/concepts.md`.
- Add `docs/commands.md`.
- Add `docs/operators-guide.md`.
- Rewrite `docs/user-guide.md` into a compact end-to-end guide that links to the split docs.
- Keep `docs/architecture.md` accurate; tighten it around extension boundaries and source-of-truth guarantees.

## Acceptance criteria

- New reader can install and run `memento doctor` and `memento sample-smoke` from README alone.
- Docs clearly state that Memento is the lifecycle/evidence source of truth; external executors are optional peers.
- Docs distinguish trusted evidence from executor self-report.
- Docs describe generated runtime state without framing Memento as a compatibility layer.
- Commands are discoverable by workflow, not only by raw list.
- No README section requires reading the original Ouroboros seed to understand basic use.
- Verification commands remain explicit: `python -m pytest -q`, `python -m ruff check .`, `python -m compileall -q src tests`, `scripts/verify-local.sh`.

## Verification commands

```bash
git status --short
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-docs-smoke --json
```
