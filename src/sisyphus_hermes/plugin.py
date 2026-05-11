"""Hermes plugin registration boundary.

The full command surface is implemented in later slices.  This module is kept
runtime-light so AC01 can import the package without requiring a live Hermes
runtime or optional integrations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def register(ctx: Any) -> dict[str, Any]:
    """Register the plugin against a Hermes-like context when available.

    The function intentionally accepts a duck-typed context.  Later acceptance
    criteria will expand this to register concrete command handlers; for the
    bootstrap slice we expose a stable importable entry point.
    """

    registrar: Callable[..., Any] | None = getattr(ctx, "register_command", None)
    if registrar is not None:
        registrar("sisyphus.doctor", lambda *_args, **_kwargs: {"ok": True})
    return {"plugin": "sisyphus-hermes", "registered": registrar is not None}
