"""Practical Kanban adapter implementations for sisyphus-hermes.

The JsonKanbanAdapter is deliberately local and dependency-free. It gives the
runtime a real Kanban-shaped source of truth for task cards without requiring a
live Hermes Kanban database in unit tests or local smoke runs.
"""

from __future__ import annotations

import json
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


__all__ = ["JsonKanbanAdapter"]
