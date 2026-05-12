"""Practical Kanban adapter implementations for memento.

Adapters in this module keep Sisyphus task state durable while allowing a live
Hermes Kanban board to mirror task cards when it is available.  The JSON adapter
is dependency-free for local smoke tests; the Hermes CLI adapter talks to the
real ``hermes kanban`` command through a small injectable runner boundary so
unit tests never need a live Hermes installation.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from .domain import SisyphusTask, TaskStatus, utc_now

_STATUS_TO_LANE = {
    TaskStatus.PENDING: "pending",
    TaskStatus.READY: "ready",
    TaskStatus.IN_PROGRESS: "in_progress",
    TaskStatus.BLOCKED: "blocked",
    TaskStatus.COMPLETED: "completed",
    TaskStatus.CANCELLED: "cancelled",
}

_STATUS_TO_HERMES = {
    TaskStatus.PENDING: "todo",
    TaskStatus.READY: "ready",
    TaskStatus.IN_PROGRESS: "running",
    TaskStatus.BLOCKED: "blocked",
    TaskStatus.COMPLETED: "done",
    TaskStatus.CANCELLED: "archived",
}

_HERMES_TO_STATUS = {
    "triage": TaskStatus.PENDING,
    "todo": TaskStatus.PENDING,
    "ready": TaskStatus.READY,
    "running": TaskStatus.IN_PROGRESS,
    "blocked": TaskStatus.BLOCKED,
    "done": TaskStatus.COMPLETED,
    "archived": TaskStatus.CANCELLED,
}

Runner = Callable[[Sequence[str]], dict[str, Any]]


class JsonKanbanAdapter:
    """Dependency-free Kanban board backed by a project-local JSON file."""

    available = True

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def create_or_update_task(self, task: SisyphusTask) -> SisyphusTask:
        board = self._read_board()
        cards = [card for card in board["cards"] if card["task"]["id"] != task.id]
        task = replace(task, updated_at=utc_now())
        cards.append(self._card_for(task))
        board["cards"] = cards
        self._write_board(board)
        return task

    def list_tasks(self, run_id: str) -> list[SisyphusTask]:
        cards = [card for card in self._read_board()["cards"] if card["task"].get("run_id") == run_id]
        return [SisyphusTask.from_record(card["task"]) for card in cards]

    def _card_for(self, task: SisyphusTask) -> dict[str, Any]:
        return {
            "id": f"card_{task.id}",
            "run_id": task.run_id,
            "lane": _STATUS_TO_LANE[task.status],
            "task": task.to_record(),
        }

    def _read_board(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "cards": []}
        with self.path.open("r", encoding="utf-8") as handle:
            board = json.load(handle)
        if board.get("schema_version") != 1 or not isinstance(board.get("cards"), list):
            raise ValueError(f"unsupported kanban board format: {self.path}")
        return board

    def _write_board(self, board: dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(board, sort_keys=True, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)


class HermesKanbanCliAdapter:
    """Mirror Sisyphus tasks into the real Hermes Kanban CLI.

    This adapter intentionally uses the public ``hermes kanban`` command instead
    of importing Hermes internals.  It therefore works across Hermes installs,
    profiles, and future Kanban schema changes as long as the CLI JSON contract
    remains stable.  ``runner`` is injectable for tests and for hosted runtimes
    that need to wrap subprocess execution.
    """

    def __init__(
        self,
        *,
        board: str | None = None,
        hermes_command: str = "hermes",
        tenant: str = "memento",
        assignee: str | None = None,
        workspace: str | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.board = board
        self.hermes_command = hermes_command
        self.tenant = tenant
        self.assignee = assignee
        self.workspace = workspace
        self._runner = runner or self._subprocess_runner
        self.available = bool(runner) or shutil.which(hermes_command) is not None

    def create_or_update_task(self, task: SisyphusTask) -> SisyphusTask:
        created = self._create_task(task)
        card_id = str(created.get("id") or created.get("task_id") or created.get("task", {}).get("id") or "")
        synced = replace(task, updated_at=utc_now())
        if task.status in {TaskStatus.BLOCKED, TaskStatus.COMPLETED, TaskStatus.CANCELLED} and card_id:
            self._set_terminal_status(card_id, task.status)
        return synced

    def list_tasks(self, run_id: str) -> list[SisyphusTask]:
        result = self._run(["kanban", "list", "--tenant", self.tenant, "--json"])
        cards = self._extract_cards(result)
        tasks: list[SisyphusTask] = []
        for card in cards:
            task = self._task_from_card(card)
            if task is not None and task.run_id == run_id:
                tasks.append(task)
        return tasks

    def _create_task(self, task: SisyphusTask) -> dict[str, Any]:
        body = json.dumps({"sisyphus_task": task.to_record()}, sort_keys=True)
        cmd = [
            "kanban",
            "create",
            task.title,
            "--body",
            body,
            "--tenant",
            self.tenant,
            "--idempotency-key",
            f"memento:{task.id}",
            "--json",
        ]
        if self.assignee:
            cmd.extend(["--assignee", self.assignee])
        workspace = self.workspace
        if workspace is None and task.description.startswith("/"):
            workspace = f"dir:{task.description}"
        if workspace:
            cmd.extend(["--workspace", workspace])
        result = self._run(cmd)
        if isinstance(result.get("task"), dict):
            return result["task"]
        return result

    def _set_terminal_status(self, card_id: str, status: TaskStatus) -> None:
        if status == TaskStatus.BLOCKED:
            self._run(["kanban", "block", card_id, "Mirrored from memento"])
        elif status == TaskStatus.COMPLETED:
            self._run(["kanban", "complete", card_id, "--summary", "Mirrored from memento"])
        elif status == TaskStatus.CANCELLED:
            self._run(["kanban", "archive", card_id])

    def _run(self, args: Sequence[str]) -> dict[str, Any]:
        cmd = [self.hermes_command]
        if self.board:
            cmd.extend(["kanban", "--board", self.board])
            if args and args[0] == "kanban":
                cmd.extend(args[1:])
            else:
                cmd.extend(args)
        else:
            cmd.extend(args)
        result = self._runner(cmd)
        if result.get("exit_code", 0) != 0:
            raise RuntimeError(result.get("stderr") or result.get("error") or f"Hermes Kanban command failed: {cmd}")
        output = str(result.get("stdout") or result.get("output") or "").strip()
        if not output:
            return {}
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Hermes Kanban returned non-JSON output: {output[:200]}") from exc
        if isinstance(parsed, dict):
            return parsed
        return {"items": parsed}

    def _subprocess_runner(self, cmd: Sequence[str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
        except OSError as exc:
            return {
                "exit_code": 127,
                "stdout": "",
                "stderr": f"failed to execute Hermes Kanban CLI: {exc}",
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}

    def _extract_cards(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("tasks", "items", "rows", "cards"):
            value = result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if isinstance(result.get("task"), dict):
            return [result["task"]]
        return []

    def _task_from_card(self, card: dict[str, Any]) -> SisyphusTask | None:
        for source in (card.get("body"), card.get("description"), card.get("text")):
            if not isinstance(source, str):
                continue
            try:
                parsed = json.loads(source)
            except json.JSONDecodeError:
                continue
            record = parsed.get("sisyphus_task") if isinstance(parsed, dict) else None
            if isinstance(record, dict):
                return SisyphusTask.from_record(record)
        if isinstance(card.get("sisyphus_task"), dict):
            return SisyphusTask.from_record(card["sisyphus_task"])
        return None


__all__ = ["HermesKanbanCliAdapter", "JsonKanbanAdapter"]
