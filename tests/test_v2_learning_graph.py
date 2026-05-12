from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from memento.budget import evaluate_budget
from memento.domain import Evidence, MementoRun, MementoTask, TaskStatus
from memento.executors import ExecutorDispatchRequest, PeerExecutorAdapter
from memento.graph_planning import propose_tasks_from_graph
from memento.performance_memory import ExecutorPerformanceMemory
from memento.repair import create_repair_task
from memento.routing import DEFAULT_EXECUTORS, route_task
from memento.state import SQLiteStateStore
from memento.verification_enrichment import enrich_verification_policy
from memento.workers import build_worker_payload


def test_goose_and_swe_agent_commands_are_capability_gated() -> None:
    assert DEFAULT_EXECUTORS["goose"].experimental is True
    assert DEFAULT_EXECUTORS["swe-agent"].preferred_task_kinds == ("issue_repair", "test_driven_fix")

    issue_task = MementoTask(
        run_id="run_1",
        title="Repair issue",
        description="Fix failing regression",
        kind="issue_repair",
        verification_policy={"requires_sandbox": True},
    )
    no_sandbox = route_task(issue_task, sandbox_available=False)
    assert no_sandbox["rejected_executors"]["swe-agent"]["reason"] == "sandbox_required_unavailable"

    with_sandbox = route_task(issue_task, sandbox_available=True)
    assert with_sandbox["selected_executor"] == "swe-agent"

    run = MementoRun(id="run_1", goal="repair", workspace="/tmp/repo")
    payload = build_worker_payload(run, issue_task)
    adapter = PeerExecutorAdapter()
    goose = adapter.command_for(ExecutorDispatchRequest(payload=payload, executor="goose"))
    swe = adapter.command_for(ExecutorDispatchRequest(payload=payload, executor="swe-agent"))
    assert goose[:2] == ["goose", "run"]
    assert swe[:2] == ["swe-agent", "run"]


def test_confidence_weighted_executor_memory_aggregates_and_decays() -> None:
    mem = ExecutorPerformanceMemory(repo="repo")
    first = mem.record(executor="codex", task_kind="implementation", success=True)
    assert 0 < first.confidence < 0.5

    for _ in range(4):
        mem.record(executor="codex", task_kind="implementation", success=True)
    stronger = mem.score(executor="codex", task_kind="implementation")
    assert stronger.score > first.score
    assert stronger.confidence > first.confidence

    failed = mem.record(executor="codex", task_kind="implementation", success=False)
    assert failed.score < stronger.score

    old = datetime.now(UTC) - timedelta(days=120)
    mem.record(executor="aider", task_kind="refactor", success=True, observed_at=old)
    stale = mem.score(executor="aider", task_kind="refactor")
    assert stale.confidence < first.confidence


def test_verification_enrichment_adds_checks_without_weakening() -> None:
    base = {"required_commands": ["python -m pytest -q"]}
    enriched = enrich_verification_policy(
        base,
        memory_lessons=["repo uses scripts/smoke.py for API/UI contract checks"],
        graph_signals={"touches_god_node": True, "cross_community_change": True},
    )
    commands = enriched["policy"]["required_commands"]
    assert "python -m pytest -q" in commands
    assert "python scripts/smoke.py" in commands
    assert "python -m pytest -q" in commands
    assert enriched["reasons"]


def test_graph_derived_task_proposals_are_review_only() -> None:
    graph = {
        "communities": [
            {"id": "backend", "label": "Backend API", "files": ["src/api.py", "src/store.py"]},
            {"id": "frontend", "label": "Frontend UI", "files": ["frontend/app.js"]},
        ],
        "edges": [{"source": "frontend/app.js", "target": "src/api.py", "relation": "fetches"}],
        "god_nodes": ["src/api.py"],
    }
    proposal = propose_tasks_from_graph(graph, goal="Add auth")
    assert proposal["review_status"] == "proposed"
    assert len(proposal["proposed_tasks"]) >= 2
    assert proposal["dependencies"]
    assert "src/api.py" in proposal["graph_basis"]["god_nodes"]


def test_repair_task_from_rejected_partial_work_blocks_downstream(tmp_path: Path) -> None:
    store = SQLiteStateStore(SQLiteStateStore.default_path(tmp_path))
    run = store.create_run(goal="repair", workspace=str(tmp_path))
    original = store.save_task(MementoTask(run_id=run.id, title="Original", description="Implement", status=TaskStatus.REJECTED))
    downstream = store.save_task(
        MementoTask(run_id=run.id, title="Downstream", description="Depends", dependencies=(original.id,))
    )
    evidence = store.save_evidence(
        Evidence(
            run_id=run.id,
            task_id=original.id,
            kind="test_result",
            status="failed",
            summary="pytest failed",
            content_ref={"failed_requirements": ["test_api failed"], "diff_ref": "file://partial.diff"},
        )
    )

    repair = create_repair_task(store, original, evidence)
    assert repair.parent_id == original.id
    assert repair.kind == "repair"
    assert "test_api failed" in repair.description
    assert repair.verification_policy["source_evidence_id"] == evidence.id
    ready_ids = {task.id for task in store.ready_tasks(run.id)}
    assert repair.id in ready_ids
    assert downstream.id not in ready_ids
    assert store.get_task(downstream.id).status.value == "pending"


def test_budget_aware_fallback_escalates_when_attempts_exceeded() -> None:
    decision = evaluate_budget(
        {"max_attempts_per_task": 2, "max_distinct_executors": 1},
        attempts=[{"executor": "codex"}, {"executor": "aider"}],
    )
    assert decision["allowed"] is False
    assert decision["status"] == "blocked"
    assert "max_attempts_per_task" in decision["reasons"]
