"""Async IPC client for Hyprland's Unix socket — no subprocess hyprctl calls."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from agent.schemas import Window, Monitor, Workspace


def _socket_path(name: str) -> str:
    sig = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return f"{runtime}/hypr/{sig}/{name}"


async def _send(cmd: str) -> str:
    """Send a single command to .socket.sock and return the response."""
    path = _socket_path(".socket.sock")
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        writer.write(cmd.encode())
        await writer.drain()
        data = await reader.read(1 << 20)
        return data.decode()
    finally:
        writer.close()
        await writer.wait_closed()


async def raw(cmd: str) -> str:
    return await _send(cmd)


async def clients() -> list[Window]:
    data = await _send("j/clients")
    raw_list = json.loads(data)
    result = []
    for item in raw_list:
        item["workspace_id"] = item.get("workspace", {}).get("id", 0)
        result.append(Window.model_validate(item))
    return result


async def active_window() -> Window | None:
    data = await _send("j/activewindow")
    parsed = json.loads(data)
    if not parsed or parsed.get("address") == "0x0":
        return None
    parsed["workspace_id"] = parsed.get("workspace", {}).get("id", 0)
    return Window.model_validate(parsed)


async def monitors() -> list[Monitor]:
    data = await _send("j/monitors")
    raw_list = json.loads(data)
    result = []
    for item in raw_list:
        result.append(
            Monitor(
                id=item["id"],
                name=item["name"],
                width=item["width"],
                height=item["height"],
                x=item["x"],
                y=item["y"],
                scale=item["scale"],
                focused=item.get("focused", False),
            )
        )
    return result


async def workspaces() -> list[Workspace]:
    data = await _send("j/workspaces")
    return [Workspace.model_validate(w) for w in json.loads(data)]


async def dispatch(cmd: str) -> str:
    return await _send(f"dispatch {cmd}")


async def batch(cmds: list[str]) -> str:
    joined = ";".join(f"dispatch {c}" for c in cmds)
    return await _send(f"[[BATCH]]{joined}")


async def active_monitor() -> Monitor | None:
    mons = await monitors()
    for m in mons:
        if m.focused:
            return m
    return mons[0] if mons else None


@asynccontextmanager
async def event_stream() -> AsyncIterator[asyncio.StreamReader]:
    """Yields the raw reader for .socket2.sock — use events.subscribe() instead."""
    path = _socket_path(".socket2.sock")
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        yield reader
    finally:
        writer.close()
        await writer.wait_closed()
