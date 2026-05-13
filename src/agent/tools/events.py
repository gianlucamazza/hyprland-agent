"""Async reader for Hyprland's event socket (.socket2.sock)."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from agent.schemas import Event, EventKind
from agent.tools import hypr

_KIND_MAP = {
    "workspace": EventKind.workspace,
    "activewindow": EventKind.active_window,
    "openwindow": EventKind.open_window,
    "closewindow": EventKind.close_window,
    "movewindow": EventKind.move_window,
    "focusedmon": EventKind.focused_mon,
    "urgent": EventKind.urgent,
}


def _parse(line: str) -> Event:
    if ">>" in line:
        kind_str, _, data = line.partition(">>")
    else:
        kind_str, data = line, ""
    kind = _KIND_MAP.get(kind_str.strip(), EventKind.other)
    return Event(kind=kind, data=data.strip(), raw=line)


async def subscribe() -> AsyncIterator[Event]:
    async with hypr.event_stream() as reader:
        while True:
            try:
                line_bytes = await reader.readline()
            except asyncio.IncompleteReadError:
                return
            if not line_bytes:
                return
            yield _parse(line_bytes.decode().rstrip("\n"))
