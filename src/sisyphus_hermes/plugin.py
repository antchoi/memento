"""Hermes plugin registration boundary.

This module is intentionally runtime-light: importing it must not require a live
Hermes runtime, Kanban database, gateway process, or optional executor package.
Concrete command implementations will grow over later acceptance criteria; this
slice establishes the stable registration contract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from inspect import Parameter, signature
from pathlib import Path
from typing import Any

PLUGIN_NAME = "sisyphus-hermes"
DOCTOR_COMMAND = "sisyphus.doctor"


def _doctor_handler(args: Mapping[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
    """Return a minimal structured readiness result for smoke tests."""

    payload = dict(args or {})
    workspace = payload.get("workspace")
    return {
        "ok": True,
        "plugin": PLUGIN_NAME,
        "command": "doctor",
        "workspace": str(Path(workspace)) if workspace else None,
    }


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
        _register_command(
            registrar,
            DOCTOR_COMMAND,
            _doctor_handler,
            description="Check sisyphus-hermes plugin readiness.",
        )
        commands.append(DOCTOR_COMMAND)

    return {
        "ok": True,
        "plugin": PLUGIN_NAME,
        "registered": bool(commands),
        "commands": commands,
    }
