from __future__ import annotations

import ast
from pathlib import Path

from memento.commands import CommandService

ROOT = Path(__file__).resolve().parents[1]
CORE_SOURCE = ROOT / "src" / "memento"


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", maxsplit=1)[0])
    return imports


def test_ac15_core_modules_do_not_import_opencode_specific_packages() -> None:
    forbidden = {"opencode", "oh_my_openagent"}
    offenders = {
        str(path.relative_to(ROOT)): sorted(_import_roots(path) & forbidden)
        for path in CORE_SOURCE.rglob("*.py")
        if _import_roots(path) & forbidden
    }

    assert offenders == {}


def test_ac15_doctor_reports_mechanical_opencode_import_scan(tmp_path: Path) -> None:
    doctor = CommandService().doctor({"workspace": str(tmp_path)})

    assert doctor["checks"]["opencode_dependency"] == "not_required"
    assert doctor["checks"]["opencode_import_scan"] == "ok"
    assert doctor["checks"]["core_modules_scanned"] >= 1


def test_ac16_test_suite_covers_core_contract_files() -> None:
    expected_contract_tests = {
        "test_bootstrap.py",
        "test_domain_state_commands.py",
        "test_kanban_events_workers.py",
        "test_plugin_registration.py",
        "test_safety_reporting.py",
        "test_skills_docs.py",
        "test_runtime_quality_contracts.py",
    }

    assert expected_contract_tests <= {path.name for path in (ROOT / "tests").glob("test_*.py")}


def test_non_document_runtime_surface_uses_memento_vocabulary() -> None:
    legacy_token = "sisy" + "phus"
    searched_paths = [
        *CORE_SOURCE.rglob("*.py"),
        *Path(ROOT / "skills").rglob("SKILL.md"),
        ROOT / "pyproject.toml",
        ROOT / "scripts" / "verify-local.sh",
    ]
    offenders = {
        str(path.relative_to(ROOT)): line_no
        for path in searched_paths
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if legacy_token in line.lower()
    }

    assert offenders == {}


def test_ac17_development_commands_document_lint_type_and_test_baseline() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for command in (
        "python -m pytest -q",
        "python -m ruff check .",
        "python -m compileall -q src tests",
    ):
        assert command in readme

    assert "[tool.ruff]" in pyproject
    assert "[tool.pytest.ini_options]" in pyproject


def test_ac18_readme_maps_every_seed_acceptance_criterion() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    seed = (ROOT / ".ouroboros" / "seeds" / "memento.seed.yaml").read_text(
        encoding="utf-8"
    )

    assert ".ouroboros/seeds/memento.seed.yaml" in readme
    for index in range(1, 23):
        token = f"AC{index:02d}_"
        assert token in seed
        assert token in readme


def test_ac19_docs_close_actor_input_output_runtime_boundaries() -> None:
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    user_guide = (ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    runtime_docs = f"{architecture}\n{user_guide}"

    required_terms = (
        "founder_user",
        "hermes_plugin_command_layer",
        "metis_planner",
        "momus_reviewer",
        "memento_lifecycle_worker",
        "hephaestus_executor",
        "hermes_sheriff",
        "optional_external_executor_adapter",
        "Accepted inputs",
        "Produced outputs",
        "Runtime context",
        "MVP boundaries",
        "Deferred extension points",
        "workspace/repository path",
        "user goal/task text",
        "plan approval",
        "cron/webhook event payloads",
        "SQLite fallback",
        "Hermes Kanban",
        "cloud sync",
        "production deployment",
        "log-scraping supervision",
    )
    for term in required_terms:
        assert term in runtime_docs


def test_ac19_command_results_use_seed_actor_and_runtime_vocabulary(tmp_path: Path) -> None:
    service = CommandService()
    run = service.start(
        {"workspace": str(tmp_path), "goal": "Close runtime vocabulary", "actor": "founder_user"}
    )
    run_id = run["run"]["id"]

    assert run["run"]["actor"] == "founder_user"
    assert run["run"]["workspace"] == str(tmp_path)
    assert run["run"]["source_of_truth"] == "sqlite"

    plan = service.plan(
        {
            "workspace": str(tmp_path),
            "run_id": run_id,
            "title": "Runtime closure",
            "body": "Document actors, inputs, outputs, context, and boundaries.",
            "assumptions": ["Hermes Kanban may be unavailable locally."],
            "risks": ["Hidden context can drift after compaction."],
            "acceptance_criteria": ["Runtime docs name Seed vocabulary."],
        }
    )
    service.approve_plan(
        {
            "workspace": str(tmp_path),
            "run_id": run_id,
            "plan_id": plan["plan"]["id"],
            "reviewer": "momus_reviewer",
        }
    )
    status = service.status({"workspace": str(tmp_path), "run_id": run_id})

    assert status["state"]["backend"] == "sqlite"
    assert status["plans"][0]["assumptions"] == ["Hermes Kanban may be unavailable locally."]
    assert status["plans"][0]["risks"] == ["Hidden context can drift after compaction."]
    assert status["plans"][0]["acceptance_criteria"] == ["Runtime docs name Seed vocabulary."]
    assert {event["actor"] for event in status["audit"]} >= {
        "founder_user",
        "metis_planner",
        "momus_reviewer",
    }
