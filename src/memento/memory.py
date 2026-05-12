"""Explicit agentmemory hook helpers with strict writeback filtering."""

from __future__ import annotations

import re
from typing import Any

_VOLATILE_PATTERNS = (
    re.compile(r"\btask[_ -]?[0-9a-f]+\b.*\b(completed|done|finished)\b", re.I),
    re.compile(r"\bcommit\s+[0-9a-f]{7,40}\b", re.I),
    re.compile(r"\bPR\s*#?\d+\b", re.I),
    re.compile(r"raw log", re.I),
)
_GOOD_HINTS = ("repo", "uses", "requires", "prefer", "test", "build", "executor", "graphify", "convention", "workflow")


def filter_memory_writeback(text: str) -> str | None:
    lesson = " ".join(text.split())
    if len(lesson) < 20:
        return None
    if any(pattern.search(lesson) for pattern in _VOLATILE_PATTERNS):
        return None
    if not any(hint in lesson.lower() for hint in _GOOD_HINTS):
        return None
    return lesson


class LocalMemoryAdapter:
    """Small file-free adapter used by MVP tests and CLI hooks.

    The real Hermes/agentmemory integration lives outside core Memento; MVP exposes
    explicit hook points and filters, while degrading gracefully when no memory
    backend is configured.
    """

    def recall(self, query: str) -> dict[str, Any]:
        return {"query": query, "summary": "", "memories": [], "backend": "local_unconfigured"}

    def save_lesson(self, lesson: str) -> dict[str, Any]:
        filtered = filter_memory_writeback(lesson)
        return {"accepted": filtered is not None, "lesson": filtered, "backend": "local_unconfigured"}
