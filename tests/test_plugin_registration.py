from __future__ import annotations

import importlib
import json
import tomllib
from pathlib import Path
from typing import Any


class FakeHermesContext:
    def __init__(self) -> None:
        self.commands: dict[str, tuple[Any, dict[str, Any]]] = {}

    def register_command(self, name: str, handler: Any, **metadata: Any) -> None:
        self.commands[name] = (handler, metadata)


def test_plugin_import_has_runtime_light_register_entrypoint():
    plugin = importlib.import_module("sisyphus_hermes.plugin")

    assert callable(plugin.register)


def test_register_adds_full_command_surface_with_metadata_and_structured_result(tmp_path):
    from sisyphus_hermes import plugin

    ctx = FakeHermesContext()

    result = plugin.register(ctx)

    expected = {
        "sisyphus.init",
        "sisyphus.start",
        "sisyphus.plan",
        "sisyphus.approve-plan",
        "sisyphus.status",
        "sisyphus.pause",
        "sisyphus.resume",
        "sisyphus.cancel",
        "sisyphus.review",
        "sisyphus.report",
        "sisyphus.doctor",
        "sisyphus.sample-smoke",
        "sisyphus.enqueue-event",
        "sisyphus.worker-payload",
        "sisyphus.dispatch-task",
        "sisyphus.list-dispatches",
        "sisyphus.claim-dispatch",
        "sisyphus.complete-dispatch",
        "sisyphus.fail-dispatch",
    }
    assert result["ok"] is True
    assert result["plugin"] == "sisyphus-hermes"
    assert result["registered"] is True
    assert set(result["commands"]) == expected
    assert set(ctx.commands) == expected

    handler, metadata = ctx.commands["sisyphus.doctor"]
    assert metadata["description"] == "Run sisyphus-hermes doctor."
    assert metadata["args_hint"] == "JSON object or key=value args"

    command_result = handler({"workspace": str(tmp_path)})
    assert command_result["ok"] is True
    assert command_result["command"] == "doctor"
    assert command_result["workspace"] == str(tmp_path)

    slash_result = json.loads(handler(f"workspace={tmp_path}"))
    assert slash_result["ok"] is True
    assert slash_result["command"] == "doctor"
    assert slash_result["workspace"] == str(tmp_path)


def test_pyproject_exposes_hermes_entrypoint_for_real_plugin_discovery():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["entry-points"]["hermes_agent.plugins"] == {
        "sisyphus-hermes": "sisyphus_hermes.plugin"
    }


def test_register_handles_context_without_registrar():
    from sisyphus_hermes import plugin

    result = plugin.register(object())

    assert result == {
        "ok": True,
        "plugin": "sisyphus-hermes",
        "registered": False,
        "commands": [],
    }


def test_register_does_not_retry_internal_registrar_type_error():
    from sisyphus_hermes import plugin

    class BrokenContext:
        def __init__(self) -> None:
            self.calls = 0

        def register_command(self, name: str, handler: Any, **metadata: Any) -> None:
            self.calls += 1
            raise TypeError("internal registrar bug")

    ctx = BrokenContext()

    try:
        plugin.register(ctx)
    except TypeError as exc:
        assert "internal registrar bug" in str(exc)
    else:  # pragma: no cover - explicit failure path for readability
        raise AssertionError("internal TypeError should propagate")

    assert ctx.calls == 1
