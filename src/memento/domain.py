"""Typed domain model for the Hermes-native Memento lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar, Self
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class StrEnum(str, Enum):
    """String-valued enum with compact JSON/SQLite representation."""


class RunStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    CANONICAL = "canonical"
    REJECTED = "rejected"


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    VERIFYING = "verifying"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GateKind(StrEnum):
    PREFLIGHT_SAFETY = "preflight_safety"
    PLAN_REVIEW = "plan_review"
    IMPLEMENTATION_REVIEW = "implementation_review"
    QUALITY_REVIEW = "quality_review"
    FINAL_ACCEPTANCE = "final_acceptance"


class GateStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"


@dataclass(frozen=True, kw_only=True)
class RecordModel:
    id: str
    created_at: str
    updated_at: str

    enum_fields: ClassVar[tuple[str, ...]] = ()

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)

        for key, value in list(record.items()):
            if isinstance(value, Enum):
                record[key] = value.value
            elif isinstance(value, tuple):
                record[key] = list(value)
        return record

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Self:
        kwargs = dict(record)
        enum_types = {
            "MementoRun": {"status": RunStatus},
            "MementoPlan": {"status": PlanStatus},
            "MementoTask": {"status": TaskStatus},
            "ReviewGate": {"kind": GateKind, "status": GateStatus},
        }.get(cls.__name__, {})
        for name in getattr(cls, "enum_fields", ()):  # type: ignore[arg-type]
            enum_type = enum_types[name]
            if name in kwargs and not isinstance(kwargs[name], enum_type):
                kwargs[name] = enum_type(kwargs[name])
        for name in (
            "assumptions",
            "risks",
            "acceptance_criteria",
            "dependencies",
            "context_refs",
            "dispatch_refs",
            "evidence_refs",
        ):
            if isinstance(kwargs.get(name), list):
                kwargs[name] = tuple(kwargs[name])
        return cls(**kwargs)


@dataclass(frozen=True, kw_only=True)
class MementoRun(RecordModel):
    goal: str
    workspace: str
    actor: str = "founder_user"
    status: RunStatus = RunStatus.ACTIVE
    source_of_truth: str = "sqlite"
    current_plan_id: str | None = None
    id: str = field(default_factory=lambda: new_id("run"))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    enum_fields = ("status",)


@dataclass(frozen=True, kw_only=True)
class MementoPlan(RecordModel):
    run_id: str
    title: str
    body: str
    status: PlanStatus = PlanStatus.DRAFT
    assumptions: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: new_id("plan"))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    enum_fields = ("status",)


@dataclass(frozen=True, kw_only=True)
class MementoTask(RecordModel):
    run_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    acceptance_criteria: tuple[str, ...] = ()
    role: str = "hephaestus_executor"
    parent_id: str | None = None
    freshness: str = "current"
    dependencies: tuple[str, ...] = ()
    verification_policy: dict[str, Any] = field(default_factory=dict)
    context_refs: tuple[str, ...] = ()
    dispatch_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    kind: str = "implementation"
    risk: str = "medium"
    size: str = "m"
    id: str = field(default_factory=lambda: new_id("task"))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    enum_fields = ("status",)


@dataclass(frozen=True, kw_only=True)
class ReviewGate(RecordModel):
    run_id: str
    kind: GateKind
    status: GateStatus = GateStatus.PENDING
    summary: str = ""
    reviewer: str = "momus_reviewer"
    id: str = field(default_factory=lambda: new_id("gate"))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    enum_fields = ("kind", "status")


@dataclass(frozen=True, kw_only=True)
class Evidence(RecordModel):
    run_id: str
    kind: str
    summary: str
    uri: str | None = None
    task_id: str | None = None
    type: str | None = None
    trust_level: str = "trusted"
    status: str = "observed"
    source: dict[str, Any] = field(default_factory=lambda: {"kind": "hermes"})
    content_ref: dict[str, Any] = field(default_factory=dict)
    relationships: dict[str, Any] = field(default_factory=dict)
    dispatch_id: str | None = None
    plan_id: str | None = None
    decision_id: str | None = None
    id: str = field(default_factory=lambda: new_id("evidence"))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.type is None:
            object.__setattr__(self, "type", self.kind)

    def to_record(self) -> dict[str, Any]:
        record = super().to_record()
        record["type"] = record.get("type") or record.get("kind")
        return record

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Self:
        payload = dict(record)
        payload.setdefault("type", payload.get("kind"))
        return super().from_record(payload)


@dataclass(frozen=True, kw_only=True)
class AuditEvent(RecordModel):
    run_id: str
    actor: str
    action: str
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("audit"))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
