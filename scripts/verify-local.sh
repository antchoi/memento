#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SMOKE_WORKSPACE="${SISYPHUS_HERMES_SMOKE_WORKSPACE:-/tmp/sisyphus-hermes-local-smoke}"
rm -rf "$SMOKE_WORKSPACE"

python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m sisyphus_hermes.cli doctor --json
PYTHONPATH=src python -m sisyphus_hermes.cli sample-smoke --workspace "$SMOKE_WORKSPACE" --json
