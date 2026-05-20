---
name: ovrs-evidence-driven-throughput-research
description: Evidence-driven OVRS throughput research, hypothesis validation, bottleneck analysis, and Memento recording discipline learned from photon01 aiid/omnivision-rs work.
version: 0.1.0
---

# OVRS Evidence-Driven Throughput Research

## Trigger

Use this skill when working on `aiid/omnivision-rs` or a similar GPU/video analytics performance project where the goal is to close a production throughput gap through Memento-recorded plans, live artifacts, review reports, and falsifiable experiments.

Typical triggers:

- A user asks to continue OVRS/Memento milestone work on photon01 under `/home/yhchoi/workspace/aiid` or `/home/yhchoi/workspace/aiid/omnivision-rs`.
- A throughput result must be interpreted against `items/sec`, `complete_video_item_sec`, `tracked_attribute_item_sec`, or CCTV channel capacity goals.
- A candidate improvement looks promising but may have semantic drift, hidden skips, diagnostic-only status, or target dishonesty.
- A long sequence of local tuning attempts has stalled and needs a structural reframe.
- The next milestone needs a plan/review/evidence package rather than another opaque prompt.

## Evidence base this skill summarizes

This skill was distilled from the photon01 `workspace/aiid` Memento state and documents, especially:

- Top-level Memento runs in `/home/yhchoi/workspace/aiid/.memento/state.sqlite3`:
  - M32 live tracked-attribute corpus artifact gate.
  - M42 secondary GIE cadence/fan-out reduction.
- `omnivision-rs/.memento/state.sqlite3` with 90+ Memento runs and 400+ evidence records covering Docker-first verification, DeepStream warm-runtime milestones, M49 tracker/reset work, M50-prep topology work, M51-M64 async/primary runtime milestones.
- `docs/blueprints/2026-05-17-ovrs-m11-nvinfer-item-accounting-topology-blueprint.md`.
- `docs/reports/2026-05-20-m63-worker-pool-bottleneck-resolution-report.md`.
- `docs/waypoints/*.md` from 2026-04-19 through 2026-05-17.
- `omnivision-rs/docs/architecture/2026-05-20-worker-pool-final-architecture.tex`.
- `omnivision-rs/docs/blueprints/2026-05-17-*` and `omnivision-rs/docs/blueprints/2026-05-20-*`.
- Recent `omnivision-rs/docs/reviews/2026-05-18..20-*.md` Memento review/evidence files.

## Core philosophy

### 1. Evidence beats narrative

Treat executor summaries, model reasoning, and plausible explanations as advisory only. Promotion decisions require trusted artifacts:

- code diff or concrete artifact file;
- command output and exit code;
- timestamped review document;
- JSON benchmark artifact with schema/version fields;
- Memento `record-external-check` evidence pointing at a file/URL;
- focused RED/GREEN test result for new contracts;
- live DeepStream/Docker gate output when the claim is a runtime/performance claim.

A statement such as “throughput improved” is not accepted unless the artifact says which metric improved, under which semantic contract, and whether local/production target gates passed.

### 2. Metric semantics are part of the system, not reporting garnish

Never optimize or compare numbers without first naming the item definition. OVRS repeatedly found that wrong metric semantics create false progress.

Keep these distinctions explicit:

- `complete_video_item_sec` / `tracked_attribute_item_sec`: production-facing item throughput.
- `complete_video_item_sec_without_secondary_delivery_wait`: primary acceptance metric after async secondary decoupling.
- `detector-window/sec`, `bounded-segment/sec`, batch/sec, worker internal throughput: diagnostic metrics, not production pass metrics.
- `items/sec` for CCTV capacity: only meaningful with item length `L`, arrival period `P`, safety factor `alpha`, GPU count, and latency/backlog gates.
- `target FPS`: detector cadence, not merely decode sampling. Do not apply an extra detector interval after target-FPS sampling and then call the result production-valid.

### 3. Target honesty is non-negotiable

A below-target artifact can be a useful milestone. A false pass corrupts the whole search process. Always preserve pass/fail booleans:

```text
local_target_passed = measured >= 8.5       # when local gate is in scope
production_target_passed = measured >= 10.0
full_pipeline_throughput_claimed = production_target_passed AND semantic gates pass
```

Do not widen thresholds, rename diagnostic throughput as product throughput, drop secondary work, or reduce detector cadence below target semantics to claim success.

### 4. Milestones are hypothesis tests

A Memento milestone should state:

- hypothesis;
- acceptance criteria;
- non-goals and forbidden shortcuts;
- artifact schema fields;
- RED tests / expected initial failures;
- live matrix or bounded diagnostic protocol;
- promotion rule;
- fallback/reframe rule if the hypothesis fails.

Failure is useful when it eliminates a branch and narrows the next search space.

### 5. Prefer structural explanation over knob chasing

When several parameter sweeps produce small gains, stop adding knobs and reclassify. In the OVRS chain, queue depth, mux timeout, track-window stride, top-k, pool size, and cadence tweaks could not close multi-item/sec gaps. The response was to:

- build topology blueprints;
- add stage timers;
- compare worker-pool vs source-set;
- decide production topology based on constrained optimization rather than novelty;
- move from secondary-join bottleneck to primary worker-pool steady-state diagnosis.

### 6. Keep production policy separate from research branches

Research branches can explore OC-SORT, source-set, no-secondary, disabled secondary, extra detector intervals, or synthetic paths. Production selection must obey current policy:

- DeepStream `nvtracker`/IOU is the production tracker unless explicitly revived.
- OC-SORT evidence remains useful as a negative/control branch, but not production-selected after M49Y/M49Z reset unless the user explicitly changes policy.
- Source-set is diagnostic/scheduling evidence after the worker-pool architecture decision; production core topology remains worker/pipeline pool.
- ReID/UPAR secondary delivery is asynchronous/non-blocking after M51/M52; do not reintroduce joined secondary delivery as a primary acceptance blocker.

## Workflow


### 1. Preflight and context reconstruction

On photon01, start from verified state, not chat memory:

```bash
cd /home/yhchoi/workspace/aiid/omnivision-rs
git status --short --branch
git log -1 --oneline --decorate
PATH=$HOME/.cargo/bin:$PATH PYTHONPATH=/home/yhchoi/workspace/memento/src \
  python3 -m memento.cli report --workspace "$PWD" --json
```

Then inspect the current review, selected artifact, and relevant blueprint. If the top-level `aiid` repo has the active Memento run, also check:

```bash
cd /home/yhchoi/workspace/aiid
PATH=$HOME/.cargo/bin:$PATH PYTHONPATH=/home/yhchoi/workspace/memento/src \
  python3 -m memento.cli report --workspace "$PWD" --json
```

Never assume the active run or canonical plan is the one in chat; Memento state can differ between `aiid` and `omnivision-rs`.

### 2. Write the plan as a falsifiable contract

For each milestone, write or inspect a plan with this shape:

```markdown
# <Milestone> plan

## Goal
<one production or diagnostic question>

## Hypothesis
<what we think is limiting throughput and why>

## Non-goals / forbidden shortcuts
- no target weakening
- no semantic relabeling
- no CPU/synthetic fallback for GPU claims
- no production claim from diagnostic-only branches

## Acceptance criteria
1. Add schema/fields that make claim boundaries machine-checkable.
2. Add focused fixture/harness tests; observe RED before implementation where applicable.
3. Run trusted Docker/unit gate.
4. Run live matrix only when the claim is runtime/performance.
5. Record review and Memento evidence pointing to artifacts.
6. State pass/fail and next milestone.
```

Approve canonical plan before dispatch when working through Memento. If the current CLI lacks a task-completion command, use `record-external-check` with provider/status/url to trusted evidence.

### 3. Add measurement contract before optimization

Before changing performance code, add schema fields that prevent hidden success claims. Examples from OVRS:

- `production_sampling_contract_passed`.
- `object_level_tensor_semantic_proof`.
- `target_passed`, `local_target_passed`, `production_target_passed`.
- `full_pipeline_throughput_claimed`.
- `production_tracker_runtime`, `production_tracker_branch`.
- `secondary_join_required`, `complete_item_blocked_by_secondary`.
- `source_set_enabled`, `worker_pool_selected`, `shared_batch_interleave_proven`.
- `bottleneck_classification`, `blocker`, `recommended_next_action`.
- stage timers: `steady_state`, `nvinfer`, `mux`, `startup`, `parse`, `drain`, `orchestration_overhead`.
- capacity fields: item duration, arrival period, safety factor, backlog and p95/p99 latency gates.

The artifact must make it hard to tell a false story.

### 4. Use RED-GREEN for contracts and harnesses

For every new milestone contract:

1. Add fixture and harness tests that fail because the schema/runner/fields are missing.
2. Run the focused test and capture the expected failure in the review.
3. Implement the minimum schema/runner/contract code.
4. Re-run focused tests to GREEN.
5. Run the trusted Docker unit gate if host Cargo/env is unreliable.

This pattern appeared repeatedly in M49S, M49X, M50-prep, M51-M64 work and prevents silent artifact drift.

### 5. Run bounded live matrices

Live matrices should be small enough to finish and rich enough to falsify the hypothesis. Each variant must include:

- variant name and axis values;
- eligibility flag;
- semantic proof flags;
- measured item/sec;
- local/production pass booleans;
- blocker/reason for non-promotion;
- artifact path;
- selected candidate and selection rule.

A matrix should include controls. OVRS used IOU/nvtracker controls against OC-SORT variants, no-secondary diagnostics against full-secondary production, worker-pool baseline against source-set, and same-run comparisons to avoid cross-run confounding.

### 6. Record the result in Memento

Use `record-external-check` for trusted evidence:

```bash
PATH=$HOME/.cargo/bin:$PATH PYTHONPATH=/home/yhchoi/workspace/memento/src \
python3 -m memento.cli record-external-check \
  --workspace "$PWD" \
  --run-id <run_id> \
  --provider <provider_name> \
  --status success \
  --url file://<artifact-or-review-path> \
  --json
```

Provider names should be specific: `docker_unittest`, `m64_review`, `live_matrix`, `deepstream_gate`, etc. The evidence summary may be generic, so the review artifact must contain the detailed interpretation.

### 7. Close the loop with a review document

A good review includes:

- verdict: PASS/FAIL/DIAGNOSTIC-ONLY;
- selected artifact path;
- exact metric values and target gaps;
- semantic gates and production eligibility;
- tests/commands run;
- root cause or blocker classification;
- why rejected variants were rejected;
- next milestone recommendation;
- non-claims.

The report must be self-contained enough for a later agent to resume without channel history.

## Hypothesis validation patterns learned from OVRS

### A. Decode/parity before throughput

Early waypoints show that throughput work was gated by strict parity and lineage correctness:

- CSC/slot forensics and strict direct tensorization had to resolve parity mismatches before speed claims mattered.
- Tail-window decode timeout and trace-lineage fragmentation were root-caused before optimizer work continued.
- Zero-parity and descriptor canonicalization were treated as correctness gates.

Rule: if output correctness is untrusted, performance numbers are not actionable.

### B. Warm runtime and lifecycle separation

DeepStream/TensorRT work separated cold startup from steady-state:

- Keep GStreamer/DeepStream pipeline and TensorRT engine warm across item iterations.
- Record construct/deserialization/lifecycle counts.
- Distinguish startup, parse, steady-state, drain, and orchestration overhead.
- Do not treat cold-start improvements as steady-state throughput unless the artifact separates them.

### C. Item accounting and bottleneck classification

M10/M11 showed that high mux/nvinfer overlap did not imply target pass. The design thesis became:

```text
whole-video item throughput
vs per-window/per-detection detector throughput
vs nvinfer full-stage traversal cost
```

When `nvinfer_overlap_efficiency≈0.999` and serialization gap is small, queue overlap is not the primary bottleneck. The next experiment should change the bottleneck model, not repeat the same queue-overlap knob.

### D. Tracker branch reset through negative evidence

OC-SORT/Deep-OC-SORT exploration generated useful evidence but failed production criteria:

- OC-SORT conservative hovered around ~5.9 items/sec while IOU/nvtracker controls were higher.
- TensorRT appearance rescue after fragmentation was too late and/or too expensive.
- Pre-association and sampled-anchor variants did not beat IOU controls.
- The production policy reset selected DeepStream nvtracker/IOU and deferred OC-SORT.

Rule: do not become attached to a technically interesting branch. If controls beat it repeatedly, reset policy and preserve the evidence as negative knowledge.

### E. Secondary decoupling by product contract, not metric trickery

M51/M52 did not “make secondary disappear”; they changed the product contract:

- ReID and UPAR are async central endpoint streams.
- Complete-video item finalization no longer waits for secondary delivery completion.
- Secondary delivery success/queue metrics remain diagnostic.
- Primary acceptance metric excludes secondary delivery wait only after the contract makes that semantically valid.

Rule: decouple a bottleneck only when product semantics allow it and the artifact says so explicitly.

### F. Topology comparison under constrained optimization

M50-prep-J/J6 and the final architecture report compared worker-pool and source-set:

- Worker-pool baseline: about `7.217454 items/sec`.
- Best source-set `2x6_round_robin`: about `7.364048 items/sec`, only +2.03% vs worker-pool.
- Both remained below local `8.5` and production `10.0`; blocker did not fundamentally change.
- Source-set raised state-space/complexity risk and did not close the gap.
- Production selected `current_worker_pool6_baseline` / `worker_pool6_final`; source-set remains diagnostic/scheduling evidence.

Decision rule:

```text
maximize normalized_throughput
minus complexity/risk/semantic-violation penalties
subject to semantic gates and production policy
```

### G. Reclassify when an apparent win violates semantics

M63 measured `8.5487 items/sec` for detector interval 3 and looked better than 7.217. The M63 report corrected this:

- target FPS already defines detector cadence;
- applying an extra interval is double sampling / double cadence reduction;
- the improvement reduced detector work below the semantic target;
- result is diagnostic-only, not production-valid;
- bottleneck was redefined as GPU feed/orchestration/barrier under target-FPS-valid cadence.

Rule: if a win works by doing less required work, record it as diagnostic evidence and revert production baseline.

## Experiment protocol checklist

Before running:

- [ ] State target metric and item semantics.
- [ ] State local and production gates.
- [ ] State production policy: tracker runtime, secondary delivery semantics, sampling cadence.
- [ ] Identify control variant(s).
- [ ] Define artifact schema and required booleans.
- [ ] Add or verify RED tests for new fields/runner flags.
- [ ] Confirm GPU selection rules; on photon01, avoid mixing `CUDA_VISIBLE_DEVICES=1` with absolute DeepStream `gpu-id` when scripts use `OVRS_M33_GPU_ID=1`.
- [ ] Check for resident Triton/DeepStream processes and GPU memory pressure.
- [ ] Use Docker unit gate when host Cargo/OpenSSL/pkg-config state is unreliable.

During running:

- [ ] Capture exact command and environment variables.
- [ ] Keep matrix bounded; do not let a stalled automation run indefinitely.
- [ ] Store raw artifacts under `output/reports/<milestone>/`.
- [ ] Preserve failed artifacts; they are evidence.
- [ ] Avoid changing multiple conceptual axes in one variant unless the matrix names it.

After running:

- [ ] Parse selected artifact and compute target gaps.
- [ ] Mark every variant eligible/ineligible with reason.
- [ ] Compare against same-run baseline/control where possible.
- [ ] Write review under `docs/reviews/`.
- [ ] Record Memento evidence with provider/status/url.
- [ ] Update next milestone based on evidence, not the original wish.

## Issue response patterns

### Dirty or wrong workspace

Stop and verify repo path, branch, remote, and status. Memento state may live in both `aiid` and `omnivision-rs`; do not write to the wrong repo. If a submodule changed, close child and parent sync deliberately.

### Host build/toolchain failure

Differentiate product failure from environment failure. Known photon01 patterns:

- Host Cargo tests can fail due missing OpenSSL pkg-config.
- Root-owned `target/` fingerprints can block writes.
- Docker wrapper may be the trusted gate.

Use Docker unit gates or clean target through the proper wrapper rather than reporting a code failure prematurely.

### GPU resource conflicts

If GPU 0 is occupied by Triton or another resident process, use the established GPU selection path. For DeepStream absolute `gpu-id`, use `OVRS_M33_GPU_ID=1`; do not hide devices with `CUDA_VISIBLE_DEVICES=1` if the config expects absolute IDs.

### Stalled automation

The user is skeptical of unreliable OpenCode/Sisyphus automation. If a helper run stalls, terminate it and continue direct verified work. Memento is the ledger, not a reason to wait on stuck executors.

### Export/env propagation bugs

M50-prep-G showed that parsing a host env flag is not enough; it must be exported into the DeepStream container. Add regression tests proving env/CLI flags reach the runtime artifact.

### Semantic ambiguity

When a result can be interpreted two ways, write a correction report rather than silently choosing the favorable reading. M63 is the model: explain previous interpretation, corrected interpretation, why the correction matters, and how the next milestone changes.

## Stagnation and breakthrough playbook

Use this when repeated milestones fail to close the gap.

1. **Stop knob-chasing.** If three or more local sweeps do not materially reduce the target gap, freeze knobs and write a structural report.
2. **Restate the invariant.** What must remain true for production? Examples: complete-video semantics, target FPS detector cadence, DeepStream nvtracker/IOU, full secondary enabled or explicitly async by product contract.
3. **Reclassify the bottleneck.** Replace vague labels like “nvinfer slow” with stage/contract-specific labels: worker-pool structural steady-state gap, feed/orchestration/barrier, joined secondary queue, lifecycle rebuild, batch interleave not proven.
4. **Design a discriminating experiment.** The next experiment should distinguish two explanations, not just try a faster setting.
5. **Compare against controls.** Same-run control prevents false promotion from run-to-run noise.
6. **Promote simplicity when gains tie.** If a complex topology produces only +2% and keeps the same blocker, choose the simpler production topology and keep the complex one as diagnostic evidence.
7. **Change product contract only with explicit semantic proof.** M51/M52 worked because async secondary delivery was a product contract shift, not a hidden skip.
8. **Write a non-expert report.** Include equations, pass/fail, artifacts, target gaps, and plain interpretation so the next decision does not depend on private context.

## Research, analysis, and search philosophy

### Search externally to change the model, not to cargo-cult settings

The DeepStream blueprints used external research on `gst-nvinfer`, `nvstreammux`, Triton architecture, and warm pipeline patterns to form mental models: warm resident runtime, decoder/pipeline pools, batch occupancy, and lifecycle ownership. Use external docs to understand mechanisms, then encode the mechanism as local artifact fields and tests.

Do not copy random tuning values without a local hypothesis and measurement contract.

### Treat docs as executable memory

Waypoints, blueprints, architecture reports, and reviews are not optional prose. They are the durable context bundle for future agents. Each document should answer:

- What was the goal?
- What was tried?
- What was measured?
- What failed and why?
- What cannot be claimed?
- What is the next safest experiment?

### Use queueing/math only when tied to artifacts

The CCTV capacity blueprints used Little's Law and safety factors:

```text
arrival_rate_per_camera = 1 / L
C_safe = floor(R_measured * L * alpha * gpu_count)
```

But the docs explicitly labeled this as a capacity hypothesis until 4-GPU end-to-end, RTSP ingest, storage/index/search/alarm latency, p95/p99, and backlog gates are measured. Math is a decision aid, not a claim substitute.

### Preserve negative knowledge

Failed attempts are assets:

- OC-SORT fragmentation/fanout showed why production returned to nvtracker/IOU.
- No-secondary diagnostics showed secondary was not the only blocker.
- Resident/shared pipeline lifecycle reduction showed fewer constructs can still reduce throughput.
- Source-set showed small scheduling gains but not enough to justify production complexity.
- M63 showed how a numerical win can be semantically invalid.

Record negative results with the same care as successes.

## Pitfalls

- Do not answer “did we improve?” without specifying metric, target, semantic gates, and production eligibility.
- Do not claim production pass from `no-secondary`, `detector_interval3`, source-set diagnostic, synthetic/mock, decode-only, or cache-only results.
- Do not let `target_passed=false` artifacts be summarized as “success” just because tests passed.
- Do not confuse Docker/unit gate PASS with throughput target PASS.
- Do not revive OC-SORT or source-set as production defaults unless the user explicitly changes the policy and new evidence beats controls.
- Do not treat `items/sec` capacity as CCTV capacity without item duration and safety factor.
- Do not use average latency only; p95/p99 and synchronized burst/backlog matter.
- Do not hide a semantic violation behind a new name.
- Do not rely on hidden chat history; write the review and record Memento evidence.
- Do not leave stale automation running when direct verified work can proceed.

## Verification

For a completed milestone or analysis package, report:

- repo path, branch, and git status;
- Memento run id and plan status;
- selected artifact/review paths;
- exact metric values and target gaps;
- semantic gates and pass/fail booleans;
- test commands and exit status;
- production claim vs diagnostic-only claim;
- next milestone recommendation.

Minimum final review shape:

```markdown
## Verdict
PASS / FAIL / DIAGNOSTIC-ONLY

## Evidence
- artifact: file://...
- review: file://...
- memento evidence: evidence_...

## Metrics
- measured: ... items/sec
- local target: ... PASS/FAIL
- production target: ... PASS/FAIL
- gap: ... items/sec / ...%

## Interpretation
<plain explanation>

## Non-claims
<what this does not prove>

## Next action
<one concrete next milestone>
```
