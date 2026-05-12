"""Confidence-weighted executor performance memory for routing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import exp
from typing import Any


@dataclass(frozen=True, kw_only=True)
class PerformanceScore:
    executor: str
    task_kind: str
    success_count: int
    failure_count: int
    score: float
    confidence: float

    def to_record(self) -> dict[str, Any]:
        return {
            "executor": self.executor,
            "task_kind": self.task_kind,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "score": self.score,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, kw_only=True)
class PerformanceObservation:
    executor: str
    task_kind: str
    success: bool
    observed_at: datetime


class ExecutorPerformanceMemory:
    """Small in-process aggregate used by v2 routing tests.

    This is intentionally not a raw event dump into agentmemory. It produces
    confidence-weighted aggregate summaries that can later be persisted or written
    back as durable lessons.
    """

    def __init__(self, *, repo: str) -> None:
        self.repo = repo
        self._observations: list[PerformanceObservation] = []

    def record(
        self,
        *,
        executor: str,
        task_kind: str,
        success: bool,
        observed_at: datetime | None = None,
    ) -> PerformanceScore:
        self._observations.append(
            PerformanceObservation(
                executor=executor,
                task_kind=task_kind,
                success=success,
                observed_at=observed_at or datetime.now(UTC),
            )
        )
        return self.score(executor=executor, task_kind=task_kind)

    def score(self, *, executor: str, task_kind: str) -> PerformanceScore:
        now = datetime.now(UTC)
        successes = 0.0
        failures = 0.0
        success_count = 0
        failure_count = 0
        for observation in self._observations:
            if observation.executor != executor or observation.task_kind != task_kind:
                continue
            age_days = max(0.0, (now - observation.observed_at).total_seconds() / 86400)
            weight = exp(-age_days / 90.0)
            if observation.success:
                successes += weight
                success_count += 1
            else:
                failures += weight
                failure_count += 1
        total = successes + failures
        if total <= 0:
            return PerformanceScore(
                executor=executor,
                task_kind=task_kind,
                success_count=0,
                failure_count=0,
                score=0.5,
                confidence=0.0,
            )
        score = (successes + 1.0) / (total + 2.0)
        confidence = min(0.95, total / 6.0)
        return PerformanceScore(
            executor=executor,
            task_kind=task_kind,
            success_count=success_count,
            failure_count=failure_count,
            score=score,
            confidence=confidence,
        )
