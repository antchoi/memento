#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/install-local.sh [options]

Install Memento from a local checkout and run a smoke verification.

Options:
  --workspace PATH          Workspace used for sample-smoke (default: /tmp/memento-sample)
  --venv PATH               Virtualenv path (default: .venv)
  --no-venv                 Install into the active Python environment instead of creating .venv
  --dev                     Install development extras (pytest, ruff)
  --agentmemory             Start a local agentmemory Docker service if Docker is available
  --agentmemory-dir PATH    agentmemory checkout path (default: ~/workspace/agentmemory)
  --skip-smoke              Skip memento doctor/sample-smoke verification
  -h, --help                Show this help

Environment:
  PYTHON                    Python executable to use (default: python3)
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="/tmp/memento-sample"
VENV_PATH="$ROOT_DIR/.venv"
USE_VENV=1
INSTALL_DEV=0
SETUP_AGENTMEMORY=0
AGENTMEMORY_DIR="${HOME}/workspace/agentmemory"
RUN_SMOKE=1
PYTHON_BIN="${PYTHON:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace)
      WORKSPACE="${2:?--workspace requires a path}"
      shift 2
      ;;
    --venv)
      VENV_PATH="${2:?--venv requires a path}"
      USE_VENV=1
      shift 2
      ;;
    --no-venv)
      USE_VENV=0
      shift
      ;;
    --dev)
      INSTALL_DEV=1
      shift
      ;;
    --agentmemory)
      SETUP_AGENTMEMORY=1
      shift
      ;;
    --agentmemory-dir)
      AGENTMEMORY_DIR="${2:?--agentmemory-dir requires a path}"
      shift 2
      ;;
    --skip-smoke)
      RUN_SMOKE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$ROOT_DIR"

echo "==> Memento checkout: $ROOT_DIR"
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ is required, found {sys.version.split()[0]}")
print(f"Python: {sys.executable} ({sys.version.split()[0]})")
PY

if [[ "$USE_VENV" -eq 1 ]]; then
  if [[ ! -d "$VENV_PATH" ]]; then
    echo "==> Creating virtualenv: $VENV_PATH"
    "$PYTHON_BIN" -m venv "$VENV_PATH"
  fi
  # shellcheck disable=SC1091
  source "$VENV_PATH/bin/activate"
  PYTHON_BIN="python"
fi

echo "==> Upgrading packaging tools"
"$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel

if [[ "$INSTALL_DEV" -eq 1 ]]; then
  echo "==> Installing Memento with development extras"
  "$PYTHON_BIN" -m pip install -e '.[dev]'
else
  echo "==> Installing Memento"
  "$PYTHON_BIN" -m pip install -e .
fi

if [[ "$SETUP_AGENTMEMORY" -eq 1 ]]; then
  echo "==> Setting up local agentmemory Docker service"
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed or not on PATH; cannot start agentmemory." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker is installed but the daemon is not reachable; start Docker and rerun." >&2
    exit 1
  fi
  if [[ ! -d "$AGENTMEMORY_DIR/.git" ]]; then
    mkdir -p "$(dirname "$AGENTMEMORY_DIR")"
    git clone https://github.com/rohitg00/agentmemory.git "$AGENTMEMORY_DIR"
  fi
  (
    cd "$AGENTMEMORY_DIR"
    docker compose up -d
  )
  echo "==> agentmemory health"
  curl -fsS --max-time 10 http://localhost:3111/agentmemory/health || {
    echo "agentmemory did not answer on http://localhost:3111/agentmemory/health" >&2
    exit 1
  }
  echo
fi

if [[ "$RUN_SMOKE" -eq 1 ]]; then
  echo "==> Running Memento doctor"
  memento doctor --json
  echo "==> Running sample smoke: $WORKSPACE"
  memento sample-smoke --workspace "$WORKSPACE" --json
  echo "==> Rebuilding status/report from durable state"
  memento status --workspace "$WORKSPACE" --json
  memento report --workspace "$WORKSPACE"
fi

cat <<EOF

Memento installation complete.

Next steps:
  source "$VENV_PATH/bin/activate"   # if you used the default virtualenv
  memento init --workspace /path/to/repo --json
  memento start --workspace /path/to/repo --goal "Ship the next verified slice" --allow-spike --json
EOF
