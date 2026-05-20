---
name: truthforge-method
description: A general-purpose Memento skill for turning ambiguous goals into evidence-backed progress through explicit goals, falsifiable hypotheses, disciplined experiments, issue triage, reframing, and reusable research synthesis.
version: 0.1.0
---

# Truthforge Method

## Trigger

Use this skill when a user is pursuing a difficult goal and progress depends on learning the truth faster than narratives can mislead you. It is intentionally domain-agnostic: apply it to software engineering, ML/model work, operations, product discovery, research writing, performance tuning, incident response, strategy, or any long-running project where the path is uncertain.

Typical triggers:

- The goal is important but the right approach is not obvious yet.
- Several plausible explanations compete, and choosing by intuition would be risky.
- Progress has stalled after repeated local fixes, tuning, or surface-level attempts.
- A user asks for a plan that should survive context compaction, executor handoff, or future resumption.
- A claim sounds plausible but needs artifacts, experiments, or independent verification.
- You need to transform scattered documents, logs, prior work, or search results into a durable method.
- You are about to declare success, failure, or next-step priority and must avoid self-deception.

Do **not** use it for tiny one-shot tasks where the answer is already known, the blast radius is low, and no durable learning is needed.

## Evidence base this skill summarizes

This method was distilled from a long Memento-driven engineering/research sequence on photon01, but the resulting skill deliberately strips away project-specific dependencies. The reusable lessons came from repeatedly converting messy milestone work, blueprint/report review, benchmark artifacts, failed optimizations, automation stalls, external research, and architecture documents into a general discipline:

- keep goals and semantic contracts explicit;
- preserve evidence even when it is negative;
- treat milestones as hypothesis tests rather than task-completion theater;
- separate diagnostic insight from production-ready claims;
- reframe when local search stops yielding leverage;
- record decisions in a way that a future agent can resume without relying on chat memory.

Project-specific terms from the source material are examples only. The skill should generalize to any domain where an agent must reason, test, adapt, and report honestly.

## Core Philosophy

### 1. Truth is forged, not asserted

Do not accept a claim because it is elegant, repeated, or confidently summarized. A claim becomes usable only after it is linked to trusted evidence:

- a changed file or concrete artifact;
- a command, test, benchmark, review, transcript, or measurement with provenance;
- a documented assumption and its validation status;
- a reproduced failure or falsifying observation;
- an independently checkable report, URL, database record, or Memento evidence pointer.

Executor summaries, human recollections, and model reasoning are useful leads, but they are not proof. Treat them as hypotheses until grounded.

### 2. Define the game before optimizing the score

Many projects fail because the team optimizes a nearby proxy instead of the real objective. Before comparing approaches, write down:

- the user-visible goal;
- the success metric;
- the semantic contract that makes the metric meaningful;
- constraints that cannot be violated to improve the metric;
- minimum acceptable evidence for declaring progress;
- what would count as a false win.

If the metric can be improved by weakening the goal, skipping required work, changing the denominator, narrowing the input set, or moving costs out of sight, the metric is not yet safe.

### 3. Preserve pass/fail honestly

A useful failure is better than a fake pass. Keep explicit status fields:

```text
claim = what we want to be true
evidence = what we observed
contract_passed = evidence satisfies semantic contract
target_passed = evidence reaches stated threshold
promotion_allowed = contract_passed AND target_passed AND no blocking caveats
```

Never blur these categories. A result can be valuable, diagnostic, or directionally promising while still not being promotable.

### 4. Every milestone is a hypothesis test

A milestone is not “do work until something changes.” It should be framed as:

```text
Hypothesis: If we change X under constraints C, then outcome Y should improve because mechanism M.
Protocol: How we will test it, including controls and failure cases.
Evidence: What artifacts will be produced.
Decision rule: Promote, reject, defer, or reframe based on observed results.
```

This keeps the work falsifiable. It also prevents the common failure mode where a milestone finishes with code changes but no learning.

### 5. Negative evidence is an asset

Failed attempts should not be hidden in prose. Record them as reusable knowledge:

- what was tried;
- why it seemed plausible;
- what happened;
- why it failed or remained inconclusive;
- what future paths it rules out;
- what new question it raises.

A well-recorded negative result reduces future search space. An unrecorded negative result becomes a trap that future agents repeat.

### 6. Reframe before you exhaust yourself

When local tweaks stop working, do not merely try smaller variants of the same idea. Change the frame:

- from tuning to architecture;
- from symptom to bottleneck;
- from metric to semantic contract;
- from implementation detail to queue/resource model;
- from single-run result to comparative protocol;
- from “how do I fix this?” to “what must be true for this approach to ever work?”

Stagnation is often evidence that the current search space is wrong.

## Workflow

### 1. Anchor the goal and non-negotiables

Write a short goal contract before acting:

```yaml
goal: <the outcome the user actually wants>
stakeholder_value: <why this matters>
success_metric: <how success will be measured>
semantic_contract: <what must remain true for the metric to count>
constraints:
  - <cost, safety, latency, privacy, correctness, UX, compatibility, etc.>
false_win_risks:
  - <ways the metric could improve while betraying the goal>
minimum_evidence:
  - <tests, artifacts, user validation, benchmark, review, external source>
```

For Memento work, put this in the plan, event body, review artifact, or evidence-linked report. For non-Memento work, put it in a plan file or final report.

### 2. Inventory what is known, assumed, and unknown

Build a three-column map:

| Category | Examples | Action |
| --- | --- | --- |
| Known | verified command output, artifact, source doc | cite it and use it |
| Assumed | plausible but untested mechanism, inherited belief | turn into a hypothesis |
| Unknown | missing measurement, unclear constraint, unobserved failure mode | design a probe |

Avoid hiding assumptions inside confident prose. An explicit assumption is manageable; an implicit assumption controls the project silently.

### 3. Convert the next step into a falsifiable hypothesis

Use this template:

```yaml
hypothesis_id: H<n>
claim: <what might be true>
mechanism: <why it might be true>
intervention: <what will change>
control: <what stays constant or baseline comparison>
expected_signal: <what should move and how>
confounders:
  - <what could make the result misleading>
rejection_signal:
  - <what observation would prove this path insufficient>
```

Good hypotheses are narrow enough to fail quickly but meaningful enough that failure teaches something.

### 4. Design the experiment protocol before running it

A protocol should specify:

- input data or scenario;
- baseline/control;
- changed variable;
- environment/version/context;
- commands or procedure;
- artifact paths;
- pass/fail threshold;
- semantic validity checks;
- repetition or variance handling if relevant;
- how to classify inconclusive results.

For code, prefer RED → GREEN → REFACTOR when behavior changes are involved. For performance or operational claims, prefer same-environment comparisons and preserve raw artifacts. For product/research claims, preserve source links, excerpts, and decision rationale.

### 5. Execute with instrumentation, not vibes

During execution, collect enough evidence to reconstruct the result later:

- exact commands or actions;
- exit codes and relevant stdout/stderr;
- generated files and paths;
- diffs or configuration changes;
- timestamps and environment notes;
- screenshots or logs where appropriate;
- external references used;
- anomalies and caveats.

If the experiment depends on hidden state, add instrumentation before interpreting the result.

### 6. Classify the result

Use four statuses instead of binary success/failure:

| Status | Meaning | Next action |
| --- | --- | --- |
| Promote | Meets goal, contract, and evidence bar | integrate, document, protect with tests/gates |
| Reject | Falsified or worse than baseline | record negative evidence, stop this branch |
| Defer | Promising but blocked by missing proof or risk | specify blocker and required evidence |
| Reframe | Result shows the model/search space is wrong | change abstraction level or hypothesis class |

Do not promote a result only because it is the best observed so far. “Best so far” and “good enough” are different claims.

### 7. Write the review as a decision record

A useful review artifact should answer:

1. What was the goal?
2. What was the hypothesis?
3. What protocol was used?
4. What evidence was produced?
5. What passed and what failed?
6. What caveats or confounders remain?
7. What did we learn?
8. What should happen next?
9. What should future agents not repeat?

Keep the tone plain. Separate facts, interpretations, and recommendations.

### 8. Update durable memory carefully

Use durable memory or skills only for reusable lessons:

- stable user preferences;
- environment conventions that will still matter;
- recurring pitfalls;
- general workflows;
- project-level patterns that prevent repeated mistakes.

Do not save temporary task progress, raw logs, commit hashes, one-off issue IDs, or milestones that will be stale. If the lesson is procedural and reusable, prefer a skill or skill reference over a memory note.

## Hypothesis and Experiment Patterns

### A. Mechanism probe

Use when you need to know whether a proposed mechanism is real.

```text
Question: Is mechanism M actually causing outcome Y?
Minimal intervention: Change only the part that affects M.
Control: Same inputs/environment without that change.
Evidence: Direct metric plus instrumentation showing M moved.
Decision: If Y moves but M does not, the explanation is wrong.
```

### B. Boundary test

Use when a solution may work only in a narrow regime.

```text
Question: Where does this approach break?
Protocol: Test small, normal, and stress cases.
Evidence: Pass/fail by regime.
Decision: Promote only for regimes with explicit coverage; document boundaries.
```

### C. Semantic validity gate

Use when an improvement may cheat the goal.

```text
Question: Did the metric improve by violating the meaning of the task?
Protocol: Check invariants before reading the score.
Evidence: Required-work completion, input equivalence, output correctness, constraints.
Decision: If semantics fail, classify as diagnostic even if the score improves.
```

### D. Same-run comparison

Use when environment variance can dominate results.

```text
Question: Which candidate is better under comparable conditions?
Protocol: Run baseline and candidates in the same environment/window.
Evidence: Raw artifacts for each candidate, selected result, variance caveats.
Decision: Prefer robust improvement over one-off peak.
```

### E. Spike-to-contract

Use when the domain is unclear.

```text
Question: What contract should future work satisfy?
Protocol: Run a bounded exploratory spike, then write the contract it reveals.
Evidence: notes, examples, failure cases, proposed acceptance criteria.
Decision: Do not ship spike output unless converted into a tested contract.
```

### F. External research synthesis

Use when web/docs/papers/vendor guidance are needed.

```text
Question: What outside knowledge changes our mental model?
Protocol: Search broadly, prefer primary sources, extract mechanisms not cargo-cult values.
Evidence: source links, quotes, applicability notes, contradictions.
Decision: Convert research into hypotheses or constraints, not blind implementation.
```

## Issue Response Protocol

When something breaks, avoid patching the first visible symptom.

### 1. Stabilize and capture

- Stop unsafe or runaway automation.
- Preserve logs/artifacts before rerunning.
- Record exact failure command, environment, and recent changes.
- Identify whether the failure is deterministic, flaky, environment-specific, or semantic.

### 2. Classify the issue

Use this taxonomy:

| Class | Meaning | Response |
| --- | --- | --- |
| Contract failure | Output violates required behavior | add focused failing test, fix behavior |
| Evidence failure | Claim lacks proof | gather proof or downgrade claim |
| Environment failure | Tooling/host/container mismatch | isolate environment, document workaround |
| Automation failure | Agent/process stuck or untrustworthy | terminate, inspect artifacts directly |
| Measurement failure | Metric/protocol invalid | redesign measurement before optimizing |
| Architecture failure | Local fixes cannot overcome structure | reframe and propose structural alternatives |
| Requirement failure | Goal/constraint unclear or inconsistent | ask or write assumption explicitly |

### 3. Choose the smallest trustworthy recovery

Do not widen scope just because an issue is frustrating. Prefer:

1. reproduce;
2. isolate;
3. add a guard/test/check;
4. patch;
5. re-run relevant gates;
6. record the failure mode and prevention.

If automation is unreliable, stop it promptly and continue with direct verified work.

## Reframing Playbook for Stagnation

Use this when progress is slow despite many attempts.

### 1. Write the stuck-state report

Before trying another tweak, summarize:

- current goal and threshold;
- best verified result and why it is insufficient;
- all attempted branches and their evidence;
- recurring bottlenecks or failure modes;
- assumptions that survived vs. failed;
- constraints that may be overbinding;
- candidate reframes.

This report often reveals the next move.

### 2. Change abstraction level

Ask:

- Are we optimizing a symptom instead of the system?
- Is the bottleneck upstream/downstream of where we are editing?
- Is a queue, dependency, resource, or coordination cost dominating?
- Would a simpler architecture outperform clever local tuning?
- Is the real problem a semantic constraint, not an implementation detail?

### 3. Generate lateral alternatives

Use multiple lenses:

- **Contrarian:** What if the chosen approach is wrong?
- **Simplifier:** What can be removed instead of optimized?
- **Architect:** What topology changes the bottleneck boundary?
- **Researcher:** What external model or prior art explains this?
- **Operator:** What would make the system observable and recoverable?
- **Product thinker:** Which requirement creates most complexity, and is it negotiable?

### 4. Compare alternatives by decision quality, not novelty

For each alternative, score:

- expected upside;
- evidence needed;
- implementation risk;
- semantic risk;
- reversibility;
- observability;
- maintenance cost;
- time to falsify.

Prefer the alternative that can be falsified cleanly and preserves the goal, not the one that sounds most impressive.

## Research and Search Philosophy

### 1. Search to update models, not to copy answers

External research is most useful when it changes how you think. Extract:

- mechanisms;
- constraints;
- failure modes;
- vocabulary;
- known trade-offs;
- experimental designs;
- questions to ask of your own system.

Avoid copying magic constants, vendor defaults, or blog post recipes without validating applicability.

### 2. Use source hierarchy

Prefer:

1. primary docs/specs/source code;
2. peer-reviewed papers or official design notes;
3. issue threads with maintainer comments and reproducible cases;
4. high-quality engineering writeups with artifacts;
5. forum answers and blogs as leads only.

When sources conflict, record the conflict and design a local probe.

### 3. Keep applicability notes

For every external source, ask:

- What assumptions does it make?
- Does our environment match?
- Which part is mechanism vs. incidental value?
- What would falsify its applicability here?
- What local experiment should it inspire?

### 4. Turn research into constraints or hypotheses

A useful research output is not “I read X.” It is:

```yaml
learned_mechanism: <what changed in our model>
applicability: <where it likely applies>
new_hypothesis: <what to test next>
new_constraint: <what not to violate>
new_instrumentation: <what to measure>
```

## Reporting Style

Write reports so a non-expert can understand both the result and the reasoning.

Include:

- one-line verdict;
- goal and metric in plain language;
- evidence table;
- pass/fail status;
- equations or comparisons when they clarify;
- caveats and non-claims;
- next decision;
- artifact paths.

Recommended structure:

```markdown
# <Decision/Experiment Title>

## Verdict
<Promote / Reject / Defer / Reframe> — one sentence why.

## Goal and Contract
What success means and what cannot be cheated.

## Protocol
What was tested, against what baseline, and how.

## Evidence
| Artifact | What it proves | Caveats |

## Interpretation
Facts first, then reasoning.

## Decision
What changes now.

## Next Step
One bounded next action with expected evidence.

## Non-Claims
What this result does not prove.
```

## Memento Usage Pattern

When using Memento, use it as the durable ledger for the method:

1. Start or identify the run.
2. Record the goal contract in the plan.
3. Record hypotheses as plan sections, tasks, or events.
4. Attach experiment outputs with `record-external-check` or equivalent evidence records.
5. Use review artifacts for interpretation and decision records.
6. Keep executor self-reports advisory; verify with artifacts.
7. Before resuming, query Memento status/report and inspect the latest evidence, not just chat history.
8. At closure, leave a final report that states what is proven, what is not, and what should happen next.

Suggested evidence pointer style:

```text
provider: local|ci|benchmark|review|research|manual
status: success|failed|blocked|inconclusive
url/path: file://docs/reviews/<date>-<topic>.md
summary: short factual pointer, not the full argument
```

## Pitfalls

1. **Metric theater.** Improving a number while weakening the goal is not progress. Add semantic validity gates before reading the score.

2. **Executor-story trust.** Agents often summarize what they intended rather than what happened. Trust diffs, tests, artifacts, and command outputs.

3. **Unbounded exploration.** Research and spikes need timeboxes and decision rules. Otherwise they become procrastination with better vocabulary.

4. **Hidden baseline drift.** If the baseline, input, environment, or denominator changed, comparisons may be invalid. Record the comparison context.

5. **Positive-result bias.** Failed candidates are part of the map. Preserve them so future agents do not repeat them.

6. **Premature generalization.** A result from one environment or dataset is not universal. State the boundary.

7. **Local optimum chasing.** Many small tweaks can distract from a structural bottleneck. Write a stuck-state report when improvements flatten.

8. **Confusing diagnostic and promotable results.** Diagnostic experiments explain; promotable results satisfy the real contract. Label them separately.

9. **Overfitting to documents.** Prior reports guide the next hypothesis but may contain stale assumptions. Verify current repo/state before acting.

10. **Memory pollution.** Do not save raw progress or stale task details to durable memory. Save reusable principles and workflows.

11. **Heroic complexity.** A clever solution with high operational risk may be worse than a simpler approach with slightly lower peak performance. Include maintenance and reversibility in decisions.

12. **Missing non-claims.** Every report should say what it does not prove. This prevents later readers from promoting evidence beyond its scope.

## Verification

Before finalizing work done under this skill, verify:

- [ ] The user goal and success metric are stated plainly.
- [ ] Semantic constraints and false-win risks are explicit.
- [ ] Claims are backed by artifacts, commands, tests, sources, or Memento evidence.
- [ ] Hypotheses have decision rules, not just descriptions.
- [ ] Baselines/controls are identified when comparison is involved.
- [ ] Failures and inconclusive results are preserved, not hidden.
- [ ] Diagnostic findings are separated from promotable outcomes.
- [ ] Stalled work has a reframe/stuck-state analysis before more tuning.
- [ ] External research is converted into hypotheses, constraints, or instrumentation.
- [ ] The final report includes verdict, evidence, caveats, non-claims, and next step.
- [ ] Durable memory/skills are updated only with reusable lessons.
