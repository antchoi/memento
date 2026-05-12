from pathlib import Path


def test_ac01_repository_bootstrap_files_exist():
    root = Path(__file__).resolve().parents[1]
    required_paths = [
        "README.md",
        "pyproject.toml",
        "src/memento/__init__.py",
        "src/memento/plugin.py",
        "tests/__init__.py",
        "docs/architecture.md",
        "skills/sisyphus-ultraworker/SKILL.md",
        ".gitignore",
        ".ouroboros/seeds/memento.seed.yaml",
    ]

    missing = [path for path in required_paths if not (root / path).exists()]

    assert missing == []


def test_ac01_package_import_smoke():
    import memento

    assert memento.__version__
