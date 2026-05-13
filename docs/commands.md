# Memento Commands

Commands are available through the local `memento` CLI and through the Hermes plugin command namespace after `memento.plugin:register` is loaded.

Use `--json` when another tool or agent will consume the output.

## Health and setup

### `doctor`

Check local readiness.

```bash
memento doctor --json
memento doctor --workspace /path/to/repo --json
```

Use this first when installation, plugin registration, generated state, or bundled skill loading looks suspicious.

### `init`

Initialize workspace-local Memento state.

```bash
memento init --workspace /path/to/repo --json
```

### `sample-smoke`

Run the mechanical install/load contract.

```bash
memento sample-smoke --workspace /tmp/memento-sample --json
```

This is the fastest end-to-end verification path.

## Run lifecycle

### `start`

Create a run for a goal.

```bash
memento start --workspace /path/to/repo --goal "Ship the next verified slice" --allow-spike --json
```

Use `--allow-spike` only when a bounded exploration is intended before canonical planning.

### `plan`

Create a draft plan.

```bash
memento plan --workspace /path/to/repo --run-id run_... --title "Plan title" --body "Plan body" --json
```

### `approve-plan`

Promote a draft plan to canonical.

```bash
memento approve-plan --workspace /path/to/repo --run-id run_... --plan-id plan_... --json
```

### `pause`, `resume`, `cancel`

Control run state.

```bash
memento pause --workspace /path/to/repo --run-id run_... --reason "waiting for review" --json
memento resume --workspace /path/to/repo --run-id run_... --json
memento cancel --workspace /path/to/repo --run-id run_... --reason "user cancelled" --json
```

### `status`

Return current state.

```bash
memento status --workspace /path/to/repo --run-id run_... --json
```

### `report`

Render a chat-friendly report.

```bash
memento report --workspace /path/to/repo --run-id run_...
```

## Tasks and events

### `enqueue-event`

Turn an incoming user/cron/webhook item into a durable task.

```bash
memento enqueue-event --workspace /path/to/repo --run-id run_... --title "Task title" --body "Task body" --json
```

Cron and webhook integrations should stop here. They should not directly spawn implementation work.

### `worker-payload`

Create a scoped payload for a worker.

```bash
memento worker-payload --workspace /path/to/repo --run-id run_... --task-id task_... --json
```

### `context-bundle`

Write a canonical context bundle that can be handed to a disposable worker.

```bash
memento context-bundle --workspace /path/to/repo --run-id run_... --task-id task_... --json
```

## Dispatch lifecycle

### `dispatch-task`

Create an auditable handoff.

```bash
memento dispatch-task --workspace /path/to/repo --run-id run_... --task-id task_... --executor hermes-profile --json
```

The outbox adapter records `executor_invoked=false` because Memento core does not spawn the peer process by itself.

### `list-dispatches`

Inspect outbox dispatch state.

```bash
memento list-dispatches --workspace /path/to/repo --run-id run_... --json
```

### `claim-dispatch`

Mark a dispatch as claimed by an executor or human.

```bash
memento claim-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --executor hermes-profile --json
```

### `complete-dispatch`

Complete a dispatch with summary and evidence.

```bash
memento complete-dispatch \
  --workspace /path/to/repo \
  --dispatch-id dispatch_... \
  --summary "Implemented and verified" \
  --evidence-uri file://verification/task.log \
  --json
```

### `fail-dispatch`

Record a failed dispatch.

```bash
memento fail-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --reason "tests failed" --json
```

## Review and verification

### `review`

Record a gate decision.

```bash
memento review --workspace /path/to/repo --run-id run_... --gate quality_review --status passed --json
```

### `verify-task`

Evaluate a task against verification policy.

```bash
memento verify-task --workspace /path/to/repo --run-id run_... --task-id task_... --json
```

### `record-external-check`

Record trusted CI/build/status evidence fetched from an external source API.

```bash
memento record-external-check \
  --workspace /path/to/repo \
  --run-id run_... \
  --provider github_actions \
  --external-run-id 123 \
  --status completed \
  --conclusion success \
  --url https://ci.example/run/123 \
  --json
```

### `record-approval`

Record a first-class user/team approval evidence item. Positive approval parsing is exact-token based; a phrase such as “I do not approve this release” does not satisfy approval gates.

```bash
memento record-approval \
  --workspace /path/to/repo \
  --run-id run_... \
  --actor c \
  --scope-kind release \
  --scope-id run_... \
  --prompt "Approve release?" \
  --response approved \
  --json
```

### `release-gate`

Check release readiness from trusted external checks and positive approvals recorded in Memento state.

```bash
memento release-gate \
  --workspace /path/to/repo \
  --run-id run_... \
  --required-check github_actions \
  --required-approvals 1 \
  --json
```

### `recover-jobs`

Reconstruct restartable long-running worker jobs from canonical Memento state without requiring native worker session memory.

```bash
memento recover-jobs --workspace /path/to/repo --run-id run_... --json
```

## Routing, graph, and memory

### `route-task`

Preview/select an executor route using policy and available signals.

```bash
memento route-task --workspace /path/to/repo --run-id run_... --task-id task_... --json
```

### `graph-status` and `graph-update`

Check or update derived Graphify project context.

```bash
memento graph-status --workspace /path/to/repo --json
memento graph-update --workspace /path/to/repo --json
```

Graph updates are checkpoint-driven by default. Do not make continuous `graphify watch` a correctness dependency.

### `memory-prefetch` and `memory-writeback`

Read or write durable lessons. Do not store raw logs, commit hashes, or one-off progress as long-term memory.

```bash
memento memory-prefetch --workspace /path/to/repo --query "test command" --json
memento memory-writeback --workspace /path/to/repo --lesson "Project uses pytest" --json
```

## Development verification

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
```
