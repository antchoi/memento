# Memento

[English](README.md) | 한국어

![Memento banner](docs/assets/memento-banner.png)

Memento는 Hermes-native 소프트웨어 작업 생명주기 및 증거 원장입니다. 모호한 목표를 durable run, plan, task, review gate, dispatch record, verification evidence로 바꾸고, 이 상태가 채팅 리셋, 프로세스 재시작, 일회성 executor 세션을 넘어 살아남게 합니다.

## Memento가 필요한 이유

Agent 기반 코딩은 진행 상태가 잘못된 곳에 있을 때 자주 실패합니다. 예를 들면 채팅 transcript, TUI buffer, executor 자체 session, self-reported summary 같은 곳입니다. Memento는 그런 취약한 context 밖에 source of truth를 둡니다.

Memento는 다음이 필요할 때 사용합니다.

- 구현 전에 canonical plan을 유지해야 할 때
- human 또는 Hermes가 관리하는 worker handoff로 작업을 넘기되 self-report를 그대로 믿고 싶지 않을 때
- evidence, review gate, approval, failure를 project-local durable state에 기록해야 할 때
- compaction, process restart, executor crash 이후에도 long-running work를 복구해야 할 때
- 로그를 긁지 않고 Telegram-friendly Markdown으로 진행 상황을 보고해야 할 때

## Memento가 하는 일과 하지 않는 일

Memento **is**:

- Python package와 CLI (`memento`)
- Hermes plugin entry point (`memento.plugin`)
- run, plan, task, gate, dispatch, audit event, evidence를 위한 lifecycle state model
- project-local SQLite와 JSON state를 사용하는 local-first durability layer
- lifecycle source of truth를 Memento 안에 유지하면서 향후 optional worker adapter를 붙일 수 있는 extension boundary

Memento **is not**:

- OpenCode, Codex, Claude Code wrapper
- 다른 lifecycle project를 위한 compatibility shim
- test, review, user approval의 대체재
- executor self-report를 proof로 취급하는 도구
- correctness를 private TUI/session state에 의존하는 도구

## PyPI에서 설치

```bash
python -m pip install memento-lifecycle
memento doctor --json
memento sample-smoke --workspace /tmp/memento-sample --json
```

PyPI distribution 이름은 `memento-lifecycle`입니다. 설치된 CLI와 Python package 이름은 그대로 `memento`입니다.

## 설치

아래 guided installation flow는 **Hermes Agent**용입니다. 다른 coding assistant도 shell command를 사람이 참고하는 방식으로 읽을 수는 있지만, Memento는 현재 OpenCode, Codex, Claude Code 전용 onboarding/integration을 제공하지 않습니다.

### Hermes Agent를 사용하는 사람을 위한 설치

아래 prompt를 Hermes Agent에 붙여 넣으세요.

```text
Install and verify Memento by following the instructions here:
https://raw.githubusercontent.com/antchoi/memento/main/docs/guide/installation.md
```

직접 읽고 싶다면 [Installation Guide](docs/guide/installation.md)를 참고하세요. 이 문서는 Hermes Agent가 실행하기 쉬운 checklist 형식으로 작성되어 있습니다: virtualenv 생성, dependency 설치, `doctor` 실행, smoke contract 실행, evidence 보고.

### Hermes Agent session을 위한 설치

설치 guide를 가져와서 그대로 따르세요.

```bash
curl -fsSL https://raw.githubusercontent.com/antchoi/memento/main/docs/guide/installation.md
```

이미 checkout 안에 있다면 기본 one-command path는 다음입니다.

```bash
scripts/install-local.sh --dev
```

개발 dependency 없이 최소 runtime만 설치하려면:

```bash
scripts/install-local.sh
```

console script를 설치하지 않고 실행하려면:

```bash
PYTHONPATH=src python -m memento.cli doctor --json
```

### 선택 사항: Hermes Agent용 local agentmemory

cross-session/cross-agent memory가 필요하면 Hermes Agent가 실행되는 machine에서 `agentmemory`를 Docker로 로컬 실행하고 Hermes와 MCP로 연결하세요.

```bash
scripts/install-local.sh --agentmemory
```

그 다음 [`docs/guide/installation.md`](docs/guide/installation.md#connect-hermes-to-agentmemory-via-mcp)에 있는 MCP server 설정을 추가하고 Hermes를 재시작한 뒤 다음으로 검증합니다.

```bash
hermes mcp list
hermes mcp test agentmemory
```

명시적으로 remote exposure를 선택하지 않는 한 agentmemory port는 localhost에만 bind하세요.

## 5분 만에 시작하기

local smoke contract를 실행합니다.

```bash
memento sample-smoke --workspace /tmp/memento-sample --json
memento status --workspace /tmp/memento-sample --json
memento report --workspace /tmp/memento-sample
```

`sample-smoke`는 workspace를 초기화하고, `doctor`를 실행하고, sample run을 만들고, task를 enqueue하고, executor outbox dispatch를 쓰고, executor process를 실제로 spawn하지 않은 채 claim/complete를 수행합니다. 마지막으로 `status`/`report`가 durable project-local state에서 복원될 수 있음을 증명합니다.

## 첫 15분

1. **준비 상태 확인**

   ```bash
   memento doctor --json
   ```

2. **실제 workspace 초기화**

   ```bash
   memento init --workspace /path/to/repo --json
   ```

3. **run 시작**

   ```bash
   memento start --workspace /path/to/repo --goal "Ship the next verified slice" --allow-spike --json
   ```

4. **canonical plan 생성 및 승인**

   ```bash
   memento plan --workspace /path/to/repo --run-id run_... --title "Next slice" --body "Plan body" --json
   memento approve-plan --workspace /path/to/repo --run-id run_... --plan-id plan_... --json
   ```

5. **들어온 작업을 durable task로 전환**

   ```bash
   memento enqueue-event --workspace /path/to/repo --run-id run_... --title "Implement X" --body "Task details" --json
   ```

6. **worker payload 또는 dispatch handoff 생성**

   ```bash
   memento worker-payload --workspace /path/to/repo --run-id run_... --task-id task_... --json
   memento dispatch-task --workspace /path/to/repo --run-id run_... --task-id task_... --executor hermes-profile --json
   ```

7. **evidence와 함께 완료 기록**

   ```bash
   memento claim-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --executor hermes-profile --json
   memento complete-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --summary "verified" --evidence-uri file://verification/task.log --json
   ```

8. **상태 보고**

   ```bash
   memento status --workspace /path/to/repo --run-id run_... --json
   memento report --workspace /path/to/repo --run-id run_...
   ```

## Core lifecycle

- **Run:** workspace와 goal에 연결된 최상위 작업 단위
- **Plan:** draft 또는 canonical implementation plan. 일반 실행은 explicit bounded spike가 허용되지 않는 한 canonical plan에 의해 gate됩니다.
- **Task:** plan, user request, cron event, webhook, manual enqueue에서 생기는 durable work item
- **Dispatch:** human 또는 optional executor에 대한 auditable handoff. Dispatch record 자체는 작업이 실제로 완료되었다는 뜻이 아니며, 이후 evidence가 필요합니다.
- **Review gate:** preflight, plan review, implementation/spec review, quality review, final acceptance, approval, release gate
- **Evidence:** test output, CI status, lint output, verification log, screenshot, approval record 같은 신뢰 가능한 artifact
- **Report:** 숨겨진 executor memory가 아니라 state에서 재구성되는 Telegram-friendly summary

## Command map

전체 command guide는 [`docs/commands.md`](docs/commands.md)를 참고하세요. 주요 workflow는 다음과 같습니다.

- setup and health: `doctor`, `init`, `sample-smoke`
- lifecycle: `start`, `plan`, `approve-plan`, `pause`, `resume`, `cancel`, `status`, `report`
- tasks and handoff: `enqueue-event`, `worker-payload`, `dispatch-task`, `list-dispatches`, `claim-dispatch`, `complete-dispatch`, `fail-dispatch`
- verification and context: `context-bundle`, `route-task`, `verify-task`, `graph-status`, `graph-update`, `memory-prefetch`, `memory-writeback`
- v3 worker platform: `record-external-check`, `record-approval`, `record-graph-diff`, `select-patch`, `release-gate`, `recover-jobs`
- review: `review`

## Hermes plugin boundary

local Hermes plugin entry point는 `memento.plugin:register`입니다. package는 Python entry point group도 함께 제공합니다.

```toml
[project.entry-points."hermes_agent.plugins"]
memento = "memento.plugin"
```

registration boundary는 의도적으로 runtime-light합니다. Hermes-like context는 아래만 제공하면 됩니다.

```python
ctx.register_command(name, handler, **metadata)
```

`doctor`와 `tests/test_plugin_registration.py`가 executable registration contract입니다.

## 문서

여기서 시작하세요.

- [`docs/README.md`](docs/README.md) — 문서 맵
- [`docs/guide/installation.md`](docs/guide/installation.md) — Hermes Agent-oriented installation, dependency setup, Hermes plugin enablement, local agentmemory Docker integration
- [`docs/guide/publishing.md`](docs/guide/publishing.md) — PyPI/TestPyPI release checklist와 GitHub Actions Trusted Publishing setup
- [`docs/getting-started.md`](docs/getting-started.md) — 설치 이후 첫 smoke test와 첫 run
- [`docs/concepts.md`](docs/concepts.md) — lifecycle concept와 trust model
- [`docs/commands.md`](docs/commands.md) — workflow별 command reference
- [`docs/operators-guide.md`](docs/operators-guide.md) — safety, recovery, cron/event, reporting 운영 guide
- [`docs/architecture.md`](docs/architecture.md) — implementation architecture와 extension point
- [`docs/user-guide.md`](docs/user-guide.md) — compact end-to-end guide

## 개발 검증

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-sample --json
scripts/verify-local.sh
```

## Seed와 acceptance criteria traceability

구현 이력은 `.ouroboros/seeds/memento.seed.yaml`의 Ouroboros source Seed와 후속 phase seed로 추적됩니다.

- `.ouroboros/seeds/memento.seed.yaml`
- `.ouroboros/seeds/memento-mvp.seed.yaml`
- `.ouroboros/seeds/memento-v1.seed.yaml`
- `.ouroboros/seeds/memento-v2.seed.yaml`
- `.ouroboros/seeds/memento-v3.seed.yaml`

traceability를 위해 유지되는 acceptance-criteria token:

- `AC01_repo_bootstrap`
- `AC02_plugin_registration`
- `AC03_command_surface`
- `AC04_draft_to_canonical_plan`
- `AC05_durable_state`
- `AC06_kanban_boundary`
- `AC07_preflight_safety`
- `AC08_destructive_guardrails`
- `AC09_worker_context`
- `AC10_review_gates`
- `AC11_reporting`
- `AC12_cancellation_pause`
- `AC13_bundled_skills`
- `AC14_documentation`
- `AC15_no_opencode_dependency`
- `AC16_test_suite`
- `AC17_lint_type_baseline`
- `AC18_seed_traceability`
- `AC19_actor_input_output_runtime_closure`
- `AC20_cron_event_to_task_only`
- `AC21_role_last_action_visibility`
- `AC22_sqlite_fallback_contract`

상세 acceptance criteria는 seed file을 참고하세요. README는 first success와 orientation에 집중하면서 mechanical traceability를 보존합니다.
