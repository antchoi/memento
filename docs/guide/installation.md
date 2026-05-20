# Installation Guide

This guide is intentionally written so a human can read it, but it is optimized for Hermes Agent to execute from top to bottom after Hermes is already running.

Scope note: this is a Hermes Agent installation guide. It is not an OpenCode, Codex, or Claude Code integration guide; those tools are not required and are not configured by this document.

## Copy-paste prompt for Hermes Agent

Paste this into a Hermes Agent session from the machine where you want to install Memento:

```text
Install and verify Memento by following this guide:
https://raw.githubusercontent.com/antchoi/memento/main/docs/guide/installation.md

Use a Python 3.11+ virtualenv, run the install script, run the smoke verification, and report the exact commands and outputs that prove success. If I ask for agentmemory integration, run it locally with Docker on the Hermes Agent machine and keep ports bound to localhost.
```

If you are already in a local checkout, use the checked-out file instead:

```text
Read docs/guide/installation.md and execute the default local installation path. Verify with memento doctor, sample-smoke, status, and report.
```

## What gets installed

Memento is a Python package and Hermes plugin boundary. The default install path:

1. checks Python 3.11+;
2. creates `.venv` in the Memento checkout;
3. installs Memento with `pip install -e .`;
4. optionally installs development dependencies with `.[dev]`;
5. runs `memento doctor --json`;
6. runs `memento sample-smoke` against a temporary workspace;
7. rebuilds `status` and `report` from durable state.

Core Memento has no required third-party runtime dependencies beyond Python packaging tools. Development verification adds `pytest` and `ruff`.

## Prerequisites

Required:

- Python 3.11 or newer.
- `git`.
- A local Memento checkout.

Optional:

- Docker and Docker Compose v2 for local `agentmemory` service integration.
- Hermes Agent if you want Memento exposed through the Hermes plugin boundary.
- Development extras (`pytest`, `ruff`) if you will run the test suite or lint.

## Install from PyPI

Use this path when you want to use Memento rather than develop Memento itself:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install memento-lifecycle
memento doctor --json
memento sample-smoke --workspace /tmp/memento-sample --json
```

The PyPI distribution is named `memento-lifecycle` because the plain `memento` name is already taken on PyPI. The installed CLI remains `memento`.

## One-command local source install

Use this path when working from a repository checkout:

```bash
scripts/install-local.sh
```

Expected result:

- `.venv/` exists unless `--no-venv` was used.
- `memento doctor --json` returns JSON with `ok: true`.
- `memento sample-smoke --workspace /tmp/memento-sample --json` completes successfully.
- `memento report --workspace /tmp/memento-sample` prints a chat-readable lifecycle report.

Install with developer dependencies:

```bash
scripts/install-local.sh --dev
```

Use a different smoke workspace:

```bash
scripts/install-local.sh --workspace /tmp/my-memento-smoke
```

Install into the active environment instead of `.venv`:

```bash
scripts/install-local.sh --no-venv
```

## Manual install path

If you prefer to run the steps yourself:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
memento doctor --json
memento sample-smoke --workspace /tmp/memento-sample --json
memento status --workspace /tmp/memento-sample --json
memento report --workspace /tmp/memento-sample
```

For development:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
```

## Using without installing the console script

Every CLI example can be run directly from source:

```bash
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-sample --json
```

Use this path when you are debugging packaging or when the `memento` console script is not on `PATH` yet.

## Hermes Agent plugin setup

Memento advertises this Python entry point:

```toml
[project.entry-points."hermes_agent.plugins"]
memento = "memento.plugin"
```

After installing Memento into the same Python environment that runs Hermes Agent, enable the plugin in Hermes config.

A robust enablement snippet is:

```bash
python - <<'PY'
from hermes_cli.config import load_config, save_config
cfg = load_config()
plugins = cfg.setdefault('plugins', {})
enabled = plugins.get('enabled')
if not isinstance(enabled, list):
    enabled = []
if 'memento' not in enabled:
    enabled.append('memento')
plugins['enabled'] = sorted(enabled)
save_config(cfg)
print('enabled plugins:', plugins['enabled'])
PY
```

Then restart the active Hermes session or gateway:

```bash
hermes plugins list || true
hermes doctor
hermes gateway restart || true
```

Notes for Hermes Agent sessions:

- Do not use `hermes config set plugins.enabled '["memento"]'` unless you verify that the result is a YAML list, not a string.
- Plugin/config changes require a fresh Hermes session or gateway restart.
- `memento doctor --json` and `tests/test_plugin_registration.py` are the executable registration contract.

## Local agentmemory service for Hermes Agent

Memento exposes explicit `memory-prefetch` and `memory-writeback` command hooks. The real long-term memory backend should run outside core Memento. For Hermes Agent, prefer a local `agentmemory` Docker service on the Hermes agent machine, connected through MCP and/or Hermes memory provider integration.

### Start agentmemory with Docker

If you want the install script to start it:

```bash
scripts/install-local.sh --agentmemory
```

Manual path:

```bash
git clone https://github.com/rohitg00/agentmemory.git ~/workspace/agentmemory
cd ~/workspace/agentmemory
docker compose up -d
curl -fsS http://localhost:3111/agentmemory/health
```

Expected service properties:

- API: `http://localhost:3111/agentmemory/health`
- Viewer: usually `http://localhost:3113`
- Ports should stay bound to localhost unless the operator explicitly chooses remote exposure.
- Docker state should live in the compose-managed persistent volume, not in a project runtime directory.

### Connect Hermes to agentmemory via MCP

Add this to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  agentmemory:
    command: npx
    args: ["-y", "@agentmemory/mcp"]
    timeout: 180
    connect_timeout: 60
```

Restart Hermes/gateway and verify:

```bash
hermes mcp list
hermes mcp test agentmemory
```

MCP access gives Hermes explicit `mcp_agentmemory_*` tools. It does not by itself prove automatic turn capture. For automatic capture, also install and verify the Hermes `agentmemory` provider/plugin path if your Hermes distribution includes it.

### Optional Hermes memory provider configuration

If your local agentmemory checkout includes `integrations/hermes/`, the candidate setup is:

```bash
cp -R ~/workspace/agentmemory/integrations/hermes ~/.hermes/plugins/agentmemory
mkdir -p ~/.agentmemory
cat > ~/.agentmemory/.env <<'EOF'
AGENTMEMORY_URL=http://localhost:3111
EOF
hermes config set memory.memory_enabled true
hermes config set memory.user_profile_enabled true
hermes config set memory.provider agentmemory
hermes memory status
hermes doctor
hermes gateway restart || true
```

Treat this as a verified integration only after `hermes memory status` reports the provider/plugin as available and a live Hermes session can call agentmemory tools.

## First real Memento run

After installation succeeds:

```bash
memento init --workspace /path/to/repo --json
memento start --workspace /path/to/repo --goal "Ship the next verified slice" --allow-spike --json
```

Then capture the returned `run.id` and follow the task lifecycle:

```bash
memento plan --workspace /path/to/repo --run-id run_... --title "Next slice" --body "Plan body" --json
memento approve-plan --workspace /path/to/repo --run-id run_... --plan-id plan_... --json
memento enqueue-event --workspace /path/to/repo --run-id run_... --title "Implement X" --body "Acceptance criteria and verification commands" --json
memento worker-payload --workspace /path/to/repo --run-id run_... --task-id task_... --json
memento dispatch-task --workspace /path/to/repo --run-id run_... --task-id task_... --executor hermes-profile --json
memento claim-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --executor hermes-profile --json
memento complete-dispatch --workspace /path/to/repo --dispatch-id dispatch_... --summary "implemented and verified" --evidence-uri file://verification/task.log --json
memento report --workspace /path/to/repo --run-id run_...
```

## Verification checklist for agents

Before reporting success, prove all of these:

```bash
git status --short
memento doctor --json
memento sample-smoke --workspace /tmp/memento-sample --json
memento status --workspace /tmp/memento-sample --json
memento report --workspace /tmp/memento-sample
```

If agentmemory was requested, also prove:

```bash
curl -fsS --max-time 10 http://localhost:3111/agentmemory/health
lsof -nP -iTCP:3111 -iTCP:3113 -sTCP:LISTEN || true
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | grep -Ei 'agentmemory|iii|3111|3113' || true
hermes mcp list || true
hermes mcp test agentmemory || true
hermes memory status || true
```

Report failures exactly. Do not claim automatic memory capture unless Hermes memory status and live tool calls prove it.

## Troubleshooting

### `memento: command not found`

Activate the virtualenv or use the source invocation:

```bash
source .venv/bin/activate
memento doctor --json
# or
PYTHONPATH=src python -m memento.cli doctor --json
```

### Python version is too old

Install Python 3.11+ and rerun:

```bash
PYTHON=/path/to/python3.11 scripts/install-local.sh
```

### Docker is unavailable

Install Docker Desktop or Docker Engine, start the daemon, and rerun only the agentmemory path:

```bash
scripts/install-local.sh --agentmemory --skip-smoke
```

### Hermes plugin is installed but commands do not appear

Restart the Hermes CLI session or gateway. Plugin discovery is not guaranteed to update inside an already-running session.

### Do not store secrets in memory

Keep credentials in Hermes `.env`, your secret manager, or the operator's configured secret files. Memento memory writeback should save durable lessons and conventions, not raw logs, tokens, one-off task progress, commit hashes, or PR numbers.
