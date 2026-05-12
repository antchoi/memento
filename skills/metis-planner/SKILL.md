---
name: metis-planner
description: Hermes-native Memento planning, decomposition, risk, and acceptance-criteria discipline.
version: 0.1.0
---

# Metis Planner

## Trigger

Use when a Memento run needs a draft plan, task decomposition, assumptions,
risks, acceptance criteria, or rollback/safety strategy before execution.

## Workflow

1. Read the run goal, repository/workspace path, source-of-truth state, and any
   explicit user constraints.
2. Produce a draft plan with assumptions, non-goals, risks, acceptance criteria,
   task slices, and rollback/safety notes.
3. Keep execution blocked until the plan is reviewed and promoted to canonical.
4. Record decisions as durable audit events or plan records; do not rely on
   transient chat context.
5. Prefer small, reviewable slices over one opaque long-running prompt.

## Pitfalls

- Do not approve your own plan as final unless the caller explicitly assigns that
  role.
- Do not omit repository safety and verification strategy.
- Do not turn cron/webhook events into implementation work; they enqueue tasks.

## Verification

Report plan id/title, assumptions, risks, task slices, acceptance criteria,
required gates, and the next approval/review action.
