"""Clipboard access via wl-copy / wl-paste."""

from __future__ import annotations

import asyncio


async def read() -> str:
    proc = await asyncio.create_subprocess_exec(
        "wl-paste",
        "--no-newline",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return out.decode()


async def write(text: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "wl-copy",
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate(text.encode())
    if proc.returncode != 0:
        raise RuntimeError(f"wl-copy failed: {err.decode()}")
