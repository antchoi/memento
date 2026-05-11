from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from sisyphus_hermes.commands import CommandService

ROOT = Path(__file__).resolve().parents[1]


def test_doctor_reports_real_local_install_and_plugin_readiness(tmp_path: Path) -> None:
    result = CommandService().doctor({"workspace": str(tmp_path)})

    assert result["ok"] is True
    assert result["workspace"] == str(tmp_path)
    checks = result["checks"]
    assert checks["package_import"] == "ok"
    assert checks["cli_entrypoint"] == "ok"
    assert checks["plugin_register_smoke"] == "ok"
    assert checks["workspace_writable"] == "ok"
    assert checks["runtime_gitignored"] == "ok"
    assert checks["bundled_skills"] == "ok"
    assert checks["bundled_skill_count"] >= 3
    assert checks["bundled_skill_frontmatter_offenders"] == {}
    assert result["local_install"]["module"] == "sisyphus_hermes"
    assert result["local_install"]["console_script"] == "sisyphus-hermes"
    assert "sisyphus.doctor" in result["plugin_registration"]["commands"]
    assert result["runtime_paths"]["state"].endswith(".sisyphus/state.sqlite3")
    assert result["runtime_paths"]["executor_outbox"].endswith(".sisyphus/executor-outbox.jsonl")


def test_module_cli_doctor_and_sample_smoke_work_from_checkout(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    doctor = subprocess.run(
        [
            sys.executable,
            "-m",
            "sisyphus_hermes.cli",
            "doctor",
            "--workspace",
            str(tmp_path / "doctor"),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    doctor_payload = json.loads(doctor.stdout)
    assert doctor_payload["ok"] is True
    assert doctor_payload["checks"]["package_import"] == "ok"
    assert doctor_payload["checks"]["plugin_register_smoke"] == "ok"

    smoke = subprocess.run(
        [
            sys.executable,
            "-m",
            "sisyphus_hermes.cli",
            "sample-smoke",
            "--workspace",
            str(tmp_path / "sample"),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    smoke_payload = json.loads(smoke.stdout)
    assert smoke_payload["ok"] is True
    assert smoke_payload["doctor"]["checks"]["package_import"] == "ok"
    assert smoke_payload["doctor"]["checks"]["runtime_gitignored"] == "ok"


def test_local_verification_script_documents_release_candidate_smoke() -> None:
    script = (ROOT / "scripts" / "verify-local.sh").read_text(encoding="utf-8")

    assert "python -m pytest -q" in script
    assert "python -m ruff check ." in script
    assert "python -m compileall -q src tests" in script
    assert "python -m sisyphus_hermes.cli doctor --json" in script
    assert "python -m sisyphus_hermes.cli sample-smoke --workspace" in script
