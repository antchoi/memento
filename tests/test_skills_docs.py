from __future__ import annotations

from pathlib import Path


REQUIRED_SKILLS = ("sisyphus-ultraworker", "metis-planner", "momus-reviewer")


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    header = text.split("---", 2)[1]
    result: dict[str, str] = {}
    for line in header.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"')
    return result


def test_bundled_role_skills_have_valid_frontmatter_and_required_sections() -> None:
    root = Path(__file__).resolve().parents[1]
    for skill_name in REQUIRED_SKILLS:
        path = root / "skills" / skill_name / "SKILL.md"
        assert path.exists(), skill_name
        metadata = _frontmatter(path)
        text = path.read_text(encoding="utf-8")

        assert metadata["name"] == skill_name
        assert metadata["description"]
        assert metadata["version"]
        for heading in ("## Trigger", "## Workflow", "## Pitfalls", "## Verification"):
            assert heading in text


def test_documentation_covers_install_commands_safety_recovery_and_executor_extension() -> None:
    root = Path(__file__).resolve().parents[1]
    user_guide = (root / "docs" / "user-guide.md").read_text(encoding="utf-8")
    architecture = (root / "docs" / "architecture.md").read_text(encoding="utf-8")

    for phrase in (
        "python -m pip install -e",
        "memento doctor --json",
        ".sisyphus/state.sqlite3",
        "Cron/webhook integrations may enqueue durable tasks only",
        "Optional executor extension",
        "git reset --hard",
    ):
        assert phrase in user_guide

    assert "Hermes Kanban adapter" in architecture
    assert "SQLite fallback" in architecture
