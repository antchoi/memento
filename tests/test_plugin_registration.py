from __future__ import annotations

import importlib
from typing import Any


class FakeHermesContext:
    def __init__(self) -> None:
        self.commands: dict[str, tuple[Any, dict[str, Any]]] = {}

    def register_command(self, name: str, handler: Any, **metadata: Any) -> None:
        self.commands[name] = (handler, metadata)


def test_plugin_import_has_runtime_light_register_entrypoint():
    plugin = importlib.import_module("sisyphus_hermes.plugin")

    assert callable(plugin.register)


def test_register_adds_doctor_command_with_metadata_and_structured_result(tmp_path):
    from sisyphus_hermes import plugin

    ctx = FakeHermesContext()

    result = plugin.register(ctx)

    assert result == {
        "ok": True,
        "plugin": "sisyphus-hermes",
        "registered": True,
        "commands": ["sisyphus.doctor"],
    }
    assert set(ctx.commands) == {"sisyphus.doctor"}

    handler, metadata = ctx.commands["sisyphus.doctor"]
    assert metadata["description"] == "Check sisyphus-hermes plugin readiness."

    command_result = handler({"workspace": str(tmp_path)})
    assert command_result["ok"] is True
    assert command_result["command"] == "doctor"
    assert command_result["workspace"] == str(tmp_path)


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
