"""Hermes plugin registration boundary.

This module is intentionally runtime-light: importing it must not require a live
Hermes runtime, Kanban database, gateway process, or optional executor package.
Concrete command implementations live in :mod:`sisyphus_hermes.commands` and
remain fake-context-testable.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable, Mapping
from inspect import Parameter, signature
from typing import Any

from .commands import CommandService, command_names

PLUGIN_NAME = "sisyphus-hermes"
DOCTOR_COMMAND = "sisyphus.doctor"


def _coerce_args(args: Any) -> dict[str, Any]:
    """Accept fake-context mapping args and real Hermes raw slash strings."""

    if args is None:
        return {}
    if isinstance(args, Mapping):
        return dict(args)
    if isinstance(args, str):
        text = args.strip()
        if not text:
            return {}
        if text.startswith("{"):
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("JSON command args must be an object")
            return parsed
        coerced: dict[str, Any] = {}
        positional: list[str] = []
        for token in shlex.split(text):
            if "=" in token:
                key, value = token.split("=", maxsplit=1)
                coerced[key.replace("-", "_")] = value
            else:
                positional.append(token)
        if positional:
            coerced["_args"] = positional
        return coerced
    raise TypeError(f"unsupported command args type: {type(args).__name__}")


def _format_result(result: dict[str, Any], *, raw_input: bool) -> dict[str, Any] | str:
    """Return dicts for tests/fake contexts and JSON strings for Hermes slash commands."""

    if raw_input:
        return json.dumps(result, sort_keys=True, indent=2)
    return result


def _doctor_handler(args: Any = None, **_kwargs: Any) -> dict[str, Any] | str:
    """Return a structured readiness result for smoke tests."""

    raw_input = isinstance(args, str)
    result = CommandService().doctor(_coerce_args(args))
    return _format_result(result, raw_input=raw_input)


def _handler_for(command_name: str) -> Callable[[Any], dict[str, Any] | str]:
    def _handler(args: Any = None, **_kwargs: Any) -> dict[str, Any] | str:
        raw_input = isinstance(args, str)
        service_args = _coerce_args(args)
        if "workspace" not in service_args and "repo" in service_args:
            service_args["workspace"] = service_args["repo"]
        result = CommandService().handler_for(command_name)(service_args)
        return _format_result(result, raw_input=raw_input)

    return _handler


def _register_command(
    registrar: Callable[..., Any],
    name: str,
    handler: Callable[..., dict[str, Any] | str],
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
                args_hint="JSON object or key=value args",
            )
            commands.append(full_name)

    return {
        "ok": True,
        "plugin": PLUGIN_NAME,
        "registered": bool(commands),
        "commands": commands,
    }
