---
name: memento-lifecycle-worker
description: Durable Hermes-native long-horizon coding worker discipline.
version: 0.1.0
---

# Memento Lifecycle Worker

## Trigger

Use when a Memento task has an approved plan, scoped repository path, explicit
acceptance criteria, and safety constraints.

## Workflow

1. Read the scoped task payload; do not rely on hidden chat history.
2. Confirm repository preflight evidence exists before implementation.
3. Execute only the approved task slice.
4. Record evidence for every meaningful change and verification command.
5. Stop at review gates, blockers, cancellation, or pause requests.

## Pitfalls

- Do not supervise OpenCode, Codex, or Claude Code by scraping logs.
- Do not run destructive git commands without explicit approval.
- Do not treat cron as an implementation executor; cron may enqueue tasks only.

## Verification

Report changed files, tests run, remaining blockers, and next action.
