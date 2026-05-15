"""Confirmation gate for destructive actions."""

from __future__ import annotations

import asyncio
import sys

_DESTRUCTIVE_DISPATCH = {
    "killactive",
    "closewindow",
    "exit",
    "forcerendererreload",
}


def is_destructive_dispatch(cmd: str) -> bool:
    first_word = cmd.strip().split()[0].lower() if cmd.strip() else ""
    return first_word in _DESTRUCTIVE_DISPATCH


async def confirm(prompt: str) -> bool:
    """Ask user y/n via stderr. Returns True if confirmed."""
    sys.stderr.write(f"\n[CONFIRM] {prompt} [y/N] ")
    sys.stderr.flush()
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, sys.stdin.readline)
        return answer.strip().lower() in ("y", "yes")
    except EOFError:
        return False
