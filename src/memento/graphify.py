"""Checkpoint-driven Graphify integration for Memento."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .domain import Evidence
from .state import SQLiteStateStore

GraphRunner = Callable[[list[str], Path], dict[str, Any]]


def graphify_command() -> str | None:
    return shutil.which("graphify") or (str(Path.home() / ".local/bin/graphify") if (Path.home() / ".local/bin/graphify").exists() else None)


def graph_status(workspace: str | Path) -> dict[str, Any]:
    root = Path(workspace)
    command = graphify_command()
    graph_json = root / "graphify-out" / "graph.json"
    if not graph_json.exists():
        state = "missing"
    else:
        state = "current"
    return {
        "installed": command is not None,
        "command": command,
        "state": state,
        "graph_json": str(graph_json),
        "update_mode": "checkpoint_driven",
        "watch_required": False,
    }


def _default_runner(command: list[str], cwd: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=300, check=False)
    except OSError as exc:
        return {"ok": False, "exit_code": None, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def update_graph(
    *,
    store: SQLiteStateStore,
    run_id: str,
    workspace: str | Path,
    changed_files: list[str] | None = None,
    mock: bool = False,
    runner: GraphRunner | None = None,
) -> dict[str, Any]:
    root = Path(workspace)
    status = graph_status(root)
    if mock:
        result = {"ok": True, "exit_code": 0, "stdout": "mock graphify update", "stderr": ""}
    elif not status["installed"]:
        result = {"ok": False, "exit_code": None, "error": "graphify_unavailable"}
    else:
        command = [str(status["command"]), str(root), "--update"]
        result = (runner or _default_runner)(command, root)
    evidence = store.save_evidence(
        Evidence(
            run_id=run_id,
            kind="graph_update",
            type="graph_update",
            summary="Graphify checkpoint update " + ("succeeded" if result.get("ok") else "failed"),
            uri=str(root / "graphify-out" / "graph.json"),
            status="passed" if result.get("ok") else "failed",
            trust_level="trusted",
            content_ref={"kind": "graphify", "result": result, "changed_files": changed_files or []},
        )
    )
    state = "current" if result.get("ok") else "update_failed"
    return {"ok": True, "graphify": {**status, "state": state}, "result": result, "evidence": evidence.to_record()}


def write_checkpoint(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
