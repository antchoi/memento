"""Hermes plugin registration boundary.

This module is intentionally runtime-light: importing it must not require a live
Hermes runtime, Kanban database, gateway process, or optional executor package.
Concrete command implementations live in :mod:`sisyphus_hermes.commands` and
remain fake-context-testable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from inspect import Parameter, signature
from typing import Any

from .commands import CommandService, command_names

PLUGIN_NAME = "sisyphus-hermes"
DOCTOR_COMMAND = "sisyphus.doctor"


def _doctor_handler(args: Mapping[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
    """Return a structured readiness result for smoke tests."""

    return CommandService().doctor(dict(args or {}))


def _handler_for(command_name: str) -> Callable[[Mapping[str, Any] | None], dict[str, Any]]:
    def _handler(args: Mapping[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
        return CommandService().handler_for(command_name)(dict(args or {}))

    return _handler


def _register_command(
    registrar: Callable[..., Any],
    name: str,
    handler: Callable[..., dict[str, Any]],
    **metadata: Any,
) -> None:
    """Call a Hermes-like registrar while tolerating minimal fake contexts."""

    registrar_signature = signature(registrar)
    accepts_metadata = any(
        parameter.kind is Parameter.VAR_KEYWORD
        for parameter in registrar_signature.parameters.values()
    )
    if accepts_metadata:
        registrar(name, handler, **metadata)
    else:
        registrar(name, handler)


def register(ctx: Any) -> dict[str, Any]:
    """Register commands against a Hermes-like context.

    Args:
        ctx: Duck-typed plugin context.  When it exposes a callable
            ``register_command`` attribute, commands are registered.  Otherwise
            this is a no-op import smoke path.

    Returns:
        Structured metadata suitable for tests and diagnostic output.
    """

    commands: list[str] = []
    registrar = getattr(ctx, "register_command", None)
    if callable(registrar):
        for command_name in command_names():
            full_name = f"sisyphus.{command_name}"
            handler = _doctor_handler if command_name == "doctor" else _handler_for(command_name)
            _register_command(
                registrar,
                full_name,
                handler,
                description=f"Run sisyphus-hermes {command_name}.",
            )
            commands.append(full_name)

    return {
        "ok": True,
        "plugin": PLUGIN_NAME,
        "registered": bool(commands),
        "commands": commands,
    }
