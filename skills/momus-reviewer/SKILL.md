---
name: momus-reviewer
description: Hermes-native Memento adversarial review gate and acceptance evidence discipline.
version: 0.1.0
---

# Momus Reviewer

## Trigger

Use when a draft plan, implementation slice, safety preflight, quality result, or
final acceptance package needs adversarial review before a Memento state
transition.

## Workflow

1. Read the explicit run/task/plan payload and evidence artifacts; do not depend
   on hidden conversation state.
2. Check the relevant gate: preflight safety, plan review, implementation/spec
   review, quality review, or final acceptance.
3. Compare evidence against acceptance criteria and safety constraints.
4. Pass only when evidence is sufficient and scoped; otherwise fail the gate with
   actionable findings and recommended next action.
5. Ensure failed gates move the run/task to blocked or review state instead of
   silently continuing.

## Pitfalls

- Do not rubber-stamp missing tests, vague plans, dirty worktree risks, or
  unverified claims.
- Do not request destructive git operations as a shortcut.
- Do not accept raw logs as a report when a concise evidence summary is required.

## Verification

Report gate kind, pass/fail/waived status, findings, required follow-ups,
verified commands/artifacts, and state-transition recommendation.
