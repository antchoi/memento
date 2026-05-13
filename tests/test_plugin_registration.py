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
    plugin = importlib.import_module("memento.plugin")

    assert callable(plugin.register)


def test_register_adds_full_command_surface_with_metadata_and_structured_result(tmp_path):
    from memento import plugin

    ctx = FakeHermesContext()

    result = plugin.register(ctx)

    expected = {
        "memento.init",
        "memento.start",
        "memento.plan",
        "memento.approve-plan",
        "memento.status",
        "memento.pause",
        "memento.resume",
        "memento.cancel",
        "memento.review",
        "memento.report",
        "memento.doctor",
        "memento.sample-smoke",
        "memento.enqueue-event",
        "memento.worker-payload",
        "memento.dispatch-task",
        "memento.list-dispatches",
        "memento.claim-dispatch",
        "memento.complete-dispatch",
            "memento.fail-dispatch",
            "memento.context-bundle",
            "memento.route-task",
            "memento.verify-task",
            "memento.graph-status",
            "memento.graph-update",
            "memento.memory-prefetch",
            "memento.memory-writeback",
            "memento.record-external-check",
            "memento.record-approval",
            "memento.release-gate",
            "memento.recover-jobs",
    }
    assert result["ok"] is True
    assert result["plugin"] == "memento"
    assert result["registered"] is True
    assert set(result["commands"]) == expected
    assert set(ctx.commands) == expected

    handler, metadata = ctx.commands["memento.doctor"]
    assert metadata["description"] == "Run memento doctor."
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
        "memento": "memento.plugin"
    }


def test_register_handles_context_without_registrar():
    from memento import plugin

    result = plugin.register(object())

    assert result == {
        "ok": True,
        "plugin": "memento",
        "registered": False,
        "commands": [],
    }


def test_register_does_not_retry_internal_registrar_type_error():
    from memento import plugin

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
