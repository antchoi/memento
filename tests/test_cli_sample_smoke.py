from __future__ import annotations

import json
from pathlib import Path

from sisyphus_hermes.cli import main
from sisyphus_hermes.commands import command_names


ROOT = Path(__file__).resolve().parents[1]


def test_cli_exposes_sample_smoke_command_for_local_install_contract(capsys, tmp_path: Path) -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'sisyphus-hermes = "sisyphus_hermes.cli:main"' in pyproject
    assert "sample-smoke" in command_names()

    exit_code = main(["sample-smoke", "--workspace", str(tmp_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "sample-smoke"
    assert payload["package"] == "sisyphus-hermes"
    assert payload["doctor"]["ok"] is True
    assert payload["doctor"]["checks"]["sqlite"] == "ok"
    assert payload["status"]["ok"] is True
    assert payload["status"]["state"]["backend"] == "sqlite"
    assert payload["status"]["run"]["workspace"] == str(tmp_path)
    assert payload["status"]["tasks"][0]["status"] == "completed"
    assert payload["dispatch"]["executor_invoked"] is False
    assert payload["claim"]["status"] == "claimed"
    assert payload["complete"]["status"] == "completed"
    assert payload["dispatches"]["dispatches"][0]["status"] == "completed"
    assert payload["report"]["ok"] is True
    assert payload["sample_project"]["workspace"] == str(tmp_path)
    assert payload["sample_project"]["goal"]


def test_cli_sample_smoke_is_documented_for_user_install_flow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    user_guide = (ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    docs = f"{readme}\n{user_guide}"

    assert "python -m pip install -e ." in docs
    assert "sisyphus-hermes sample-smoke --workspace" in docs
    assert "sisyphus-hermes doctor --json" in docs
    assert "sisyphus-hermes status --workspace" in docs
