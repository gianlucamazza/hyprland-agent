"""Output helpers: JSON vs human-readable, auto-detected via isatty."""

from __future__ import annotations

import json
import sys
from typing import Any


def is_tty() -> bool:
    return sys.stdout.isatty()


def out_json(data: Any) -> None:
    typer_echo = _get_echo()
    typer_echo(json.dumps(data, indent=2, default=str))


def out_text(text: str) -> None:
    _get_echo()(text)


def out_auto(data: Any, human: str | None = None) -> None:
    """Print human-readable text on TTY, JSON on pipe."""
    if is_tty() and human is not None:
        _get_echo()(human)
    else:
        out_json(data)


def _get_echo():
    import typer

    return typer.echo
