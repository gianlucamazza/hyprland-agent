"""Shared utilities for all CLI modules."""

from __future__ import annotations

import asyncio
import sys
from enum import IntEnum
from typing import Annotated

import typer

from agent.client.errors import DaemonUnavailable, RpcError


class ExitCode(IntEnum):
    ok = 0
    error = 1
    misuse = 2
    daemon_unavailable = 3
    killswitch_armed = 4
    confirmation_denied = 5


_BrainOpt = Annotated[
    str | None,
    typer.Option(
        "--brain",
        "-b",
        help="Brain: auto | claude | openai | kimi | groq | together | zai | qwen",
    ),
]


def _setup_logging(verbose: bool) -> None:
    import logging

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=level)


def _run(coro) -> None:
    """Run coro, surface daemon/RPC errors as clean messages with typed exit codes."""
    try:
        asyncio.run(coro)
    except DaemonUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.daemon_unavailable) from exc
    except RpcError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(ExitCode.error) from exc
    except KeyboardInterrupt:
        pass


def confirm_or_exit(prompt: str, yes: bool) -> None:
    """Ask for confirmation unless --yes was passed; exit with code 5 on denial."""
    if yes:
        return
    if not sys.stdin.isatty():
        return
    confirmed = typer.confirm(prompt)
    if not confirmed:
        raise typer.Exit(ExitCode.confirmation_denied)
