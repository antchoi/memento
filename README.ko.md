# Memento

[English](README.md) | 한국어

![Memento banner](docs/assets/memento-banner.png)

Memento는 AI-assisted software work를 위한 Hermes-native lifecycle/evidence ledger입니다.

긴 AI 코딩 작업이 자주 무너지는 이유는 꽤 단순합니다. 작업의 실제 상태가 엉뚱한 곳에 남습니다. 채팅 transcript에는 한 가지 이야기가 있고, TUI buffer에는 다른 흔적이 있고, executor session은 사라지고, 요약에는 테스트가 통과했다고 적혀 있지만 증거는 없습니다. Memento는 이 상태를 프로젝트 로컬의 ledger로 옮깁니다. run, plan, task, dispatch, review gate, evidence, audit event가 채팅 리셋과 프로세스 재시작 이후에도 남습니다.

짧게 말하면 이렇습니다.

> 작업은 agent가 완료했다고 말해서 끝나는 것이 아닙니다. 확인 가능한 evidence가 ledger에 연결될 때 끝납니다.

## Memento를 쓰는 경우

AI-assisted development가 하나의 채팅창을 넘어가기 시작하면 Memento가 필요해집니다.

- 구현 전에 canonical plan을 확정하고 싶을 때
- user request, cron event, webhook payload를 즉흥 지시가 아니라 durable task로 남기고 싶을 때
- 사람이나 Hermes-controlled worker에게 넘긴 작업을 audit 가능하게 만들고 싶을 때
- 완료 조건을 test output, CI status, lint log, generated artifact, code diff, screenshot, explicit approval 같은 evidence에 연결하고 싶을 때
- chat compaction, executor crash, process restart, lost terminal session 이후에도 작업을 복구하고 싶을 때
- hidden executor memory가 아니라 durable state에서 읽을 수 있는 진행 보고를 만들고 싶을 때

Memento는 AI 코딩을 더 마법처럼 보이게 만드는 도구가 아닙니다. 무엇이 실제로 일어났는지 잃어버리기 어렵게 만드는 도구입니다.

## Memento가 하지 않는 일

Memento는 의도적으로 좁은 도구입니다.

Memento는 다음이 아닙니다.

- OpenCode, Codex, Claude Code wrapper
- 위 도구들을 위한 integration guide
- 다른 lifecycle system을 위한 compatibility shim
- test, review, user approval의 대체재
- executor summary를 proof로 취급하는 시스템
- private TUI/session state에 correctness를 의존하는 시스템

현재 지원되는 public onboarding path는 Hermes Agent와 `memento` CLI입니다. 향후 executor adapter가 다른 runtime에 작업을 넘길 수는 있지만, 그것은 현재 설치 흐름이나 correctness model의 일부가 아닙니다.

## PyPI에서 설치

```bash
python -m pip install memento-lifecycle
memento doctor --json
memento sample-smoke --workspace /tmp/memento-sample --json
```

PyPI distribution 이름은 `memento-lifecycle`입니다. 설치되는 CLI와 Python import package 이름은 그대로 `memento`입니다.

## Hermes Agent 설치

Guided installation flow는 Hermes Agent용입니다. 이 문서는 Hermes Agent만 설정하며 다른 coding runtime은 설정하지 않습니다.

아래 prompt를 Hermes Agent에 붙여 넣으세요.

```text
Install and verify Memento by following the instructions here:
https://raw.githubusercontent.com/antchoi/memento/main/docs/guide/installation.md
```

또는 [Installation Guide](docs/guide/installation.md)를 직접 읽어도 됩니다. 이 문서는 Hermes Agent가 Python 3.11+ 환경을 만들고, dependency를 설치하고, `memento doctor`와 smoke contract를 실행하고, optional local `agentmemory`까지 검증한 뒤, 어떤 evidence를 보고해야 하는지 순서대로 안내합니다.

이미 source checkout 안에 있다면 기본 local path는 다음입니다.

```bash
scripts/install-local.sh --dev
```

checkout에서 최소 runtime만 설치하려면:

```bash
scripts/install-local.sh
```

console script를 설치하지 않고 source에서 바로 실행하려면:

```bash
PYTHONPATH=src python -m memento.cli doctor --json
```

### 선택 사항: Hermes Agent용 local agentmemory

Memento의 lifecycle truth는 Memento ledger에 남습니다. 별도로 Hermes Agent의 cross-session memory가 필요하면 `agentmemory`를 로컬에서 실행하고 MCP로 연결합니다.

```bash
scripts/install-local.sh --agentmemory
```

그 다음 [`docs/guide/installation.md`](docs/guide/installation.md#connect-hermes-to-agentmemory-via-mcp)에 있는 MCP server 설정을 추가하고 Hermes를 재시작한 뒤 검증합니다.

```bash
hermes mcp list
hermes mcp test agentmemory
```

명시적으로 remote exposure를 선택하지 않는 한 agentmemory port는 localhost에만 bind하세요.

## 첫 확인

Smoke contract를 실행합니다.

```bash
memento sample-smoke --workspace /tmp/memento-sample --json
memento status --workspace /tmp/memento-sample --json
memento report --workspace /tmp/memento-sample
```

`sample-smoke`는 workspace를 초기화하고, `doctor`를 실행하고, sample run을 만들고, task를 enqueue하고, outbox handoff를 쓰고, 외부 executor process를 spawn하지 않은 채 claim/complete를 수행합니다. 마지막으로 `status`와 `report`가 project-local durable state에서 재구성되는지 확인합니다.

## 첫 실제 run

일반적인 Memento workflow는 일부러 보수적입니다. run을 만들고, plan을 승인하고, 작업을 task로 만들고, handoff를 기록하고, evidence가 있을 때만 완료로 닫습니다.

```bash
memento init --workspace /path/to/repo --json

memento start \
  --workspace /path/to/repo \
  --goal "Ship the next verified slice" \
  --allow-spike \
  --json
```

Canonical plan을 만들고 승인합니다.

```bash
memento plan \
  --workspace /path/to/repo \
  --run-id run_... \
  --title "Next slice" \
  --body "Write tests, implement the slice, verify it, and record evidence." \
  --json

memento approve-plan \
  --workspace /path/to/repo \
  --run-id run_... \
  --plan-id plan_... \
  --json
```

다음 작업을 durable task로 만들고 explicit worker payload를 생성합니다.

```bash
memento enqueue-event \
  --workspace /path/to/repo \
  --run-id run_... \
  --title "Implement X" \
  --body "Task details and acceptance criteria" \
  --json

memento worker-payload \
  --workspace /path/to/repo \
  --run-id run_... \
  --task-id task_... \
  --json
```

Handoff와 completion을 기록합니다.

```bash
memento dispatch-task \
  --workspace /path/to/repo \
  --run-id run_... \
  --task-id task_... \
  --executor hermes-profile \
  --json

memento claim-dispatch \
  --workspace /path/to/repo \
  --dispatch-id dispatch_... \
  --executor hermes-profile \
  --json

memento complete-dispatch \
  --workspace /path/to/repo \
  --dispatch-id dispatch_... \
  --summary "Implemented and verified" \
  --evidence-uri file://verification/task.log \
  --json
```

이제 ledger에서 상태를 다시 만듭니다.

```bash
memento status --workspace /path/to/repo --run-id run_... --json
memento report --workspace /path/to/repo --run-id run_...
```

## Core model

- **Run**: 하나의 workspace와 goal에 연결된 최상위 작업 단위
- **Plan**: draft 또는 canonical implementation plan. 명시적으로 bounded spike를 허용한 경우를 제외하면 canonical plan이 있어야 일반 실행이 진행됩니다.
- **Task**: plan, user request, cron event, webhook, manual enqueue에서 만들어지는 durable work item
- **Dispatch**: audit 가능한 handoff record. 이것만으로는 작업이 실제로 수행됐다는 proof가 되지 않습니다.
- **Review gate**: preflight safety, plan review, implementation/spec review, quality review, final acceptance, approval, release readiness를 위한 checkpoint
- **Evidence**: command output, test result, CI status, lint output, generated file, screenshot, verified diff, approval record처럼 확인 가능한 artifact
- **Audit event**: recovery와 accountability를 위한 append-only lifecycle history
- **Report**: Memento state에서 재구성되는 chat-readable summary

## Trust model

Memento는 ledger에 연결된 다음 자료를 trusted evidence로 봅니다.

- exit code가 있는 command output
- test, lint, type, compile, smoke, CI result
- stable path가 있는 generated artifact
- verified code diff
- explicit approval
- supporting context로 쓰인 graph 또는 memory snapshot

반대로 다음은 evidence가 붙기 전까지 advisory일 뿐입니다.

- "완료했습니다" 같은 summary
- private reasoning trace
- raw chat history
- executor-native session state
- verification artifact가 없는 TUI buffer와 log

이 구분이 Memento의 핵심입니다. Memento는 더 그럴듯한 요약을 믿으라고 하지 않습니다. 증거를 연결하라고 요구합니다.

## Command map

전체 command guide는 [`docs/commands.md`](docs/commands.md)를 참고하세요. 주요 그룹은 다음과 같습니다.

- setup and health: `doctor`, `init`, `sample-smoke`
- lifecycle: `start`, `plan`, `approve-plan`, `pause`, `resume`, `cancel`, `status`, `report`
- tasks and handoff: `enqueue-event`, `worker-payload`, `dispatch-task`, `list-dispatches`, `claim-dispatch`, `complete-dispatch`, `fail-dispatch`
- verification and context: `context-bundle`, `route-task`, `verify-task`, `graph-status`, `graph-update`, `memory-prefetch`, `memory-writeback`
- worker/release gates: `record-external-check`, `record-approval`, `record-graph-diff`, `select-patch`, `release-gate`, `recover-jobs`
- review: `review`

## Hermes plugin boundary

local Hermes plugin entry point는 `memento.plugin:register`입니다.

```toml
[project.entry-points."hermes_agent.plugins"]
memento = "memento.plugin"
```

registration boundary는 작게 유지됩니다. Hermes-like context는 아래만 제공하면 됩니다.

```python
ctx.register_command(name, handler, **metadata)
```

`memento doctor --json`와 `tests/test_plugin_registration.py`가 executable registration contract입니다.

## 문서

여기서 시작하세요.

- [`docs/README.md`](docs/README.md): 문서 맵
- [`docs/guide/installation.md`](docs/guide/installation.md): Hermes Agent 설치, dependency setup, plugin enablement, verification, optional local agentmemory
- [`docs/guide/publishing.md`](docs/guide/publishing.md): PyPI/TestPyPI release checklist와 GitHub Actions Trusted Publishing
- [`docs/getting-started.md`](docs/getting-started.md): 설치 이후 첫 smoke test와 첫 run
- [`docs/concepts.md`](docs/concepts.md): lifecycle concept와 trust model
- [`docs/commands.md`](docs/commands.md): workflow별 command reference
- [`docs/operators-guide.md`](docs/operators-guide.md): safety, recovery, cron/event, reporting 운영 guide
- [`docs/architecture.md`](docs/architecture.md): implementation architecture와 extension boundary
- [`docs/user-guide.md`](docs/user-guide.md): compact end-to-end guide

## 개발 검증

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-sample --json
scripts/verify-local.sh
```

## Traceability

구현 이력은 `.ouroboros/seeds/memento.seed.yaml`의 Ouroboros source Seed와 후속 phase seed로 추적됩니다.

- `.ouroboros/seeds/memento.seed.yaml`
- `.ouroboros/seeds/memento-mvp.seed.yaml`
- `.ouroboros/seeds/memento-v1.seed.yaml`
- `.ouroboros/seeds/memento-v2.seed.yaml`
- `.ouroboros/seeds/memento-v3.seed.yaml`

상세 acceptance criteria는 seed file에 있습니다. Mechanical traceability를 위해 token map만 유지합니다.

`AC01_repo_bootstrap`, `AC02_plugin_registration`, `AC03_command_surface`, `AC04_draft_to_canonical_plan`, `AC05_durable_state`, `AC06_kanban_boundary`, `AC07_preflight_safety`, `AC08_destructive_guardrails`, `AC09_worker_context`, `AC10_review_gates`, `AC11_reporting`, `AC12_cancellation_pause`, `AC13_bundled_skills`, `AC14_documentation`, `AC15_no_opencode_dependency`, `AC16_test_suite`, `AC17_lint_type_baseline`, `AC18_seed_traceability`, `AC19_actor_input_output_runtime_closure`, `AC20_cron_event_to_task_only`, `AC21_role_last_action_visibility`, `AC22_sqlite_fallback_contract`.

이 README는 orientation, installation, first verified workflow에 집중합니다.
