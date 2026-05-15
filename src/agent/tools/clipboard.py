"""Clipboard access via wl-copy / wl-paste."""

from __future__ import annotations

from agent.tools._proc import run as _proc_run


async def read() -> str:
    result = await _proc_run(
        ["wl-paste", "--no-newline"], capture_stdout=True, timeout=5.0
    )
    return result.stdout.decode()


async def write(text: str) -> None:
    result = await _proc_run(["wl-copy"], stdin_data=text.encode(), timeout=5.0)
    if result.returncode != 0:
        raise RuntimeError(f"wl-copy failed: {result.stderr.decode()}")
