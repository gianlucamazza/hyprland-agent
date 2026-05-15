"""agent-waybar — stream run state as Waybar custom-module JSON.

Invoked by Waybar as a long-running exec:
    "exec": "agent-waybar --watch"
    "return-type": "json"

Emits one JSON line per state change:
    {"text": "●", "class": "running", "tooltip": "task · 12s"}
    {"text": "○", "class": "idle",    "tooltip": "hyprland-agent · idle"}

On daemon restart reconnects with exponential back-off (max 30s).
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from agent.client.connection import connect
from agent.client.errors import DaemonUnavailable
from agent.ipc.constants import SOCKET_PATH
from agent.ipc.protocol import Topic


def _render(event_kind: str, payload: dict[str, Any]) -> str:
    status = payload.get("status", "")
    str(payload.get("run_id", ""))[:8]
    task = str(payload.get("task", ""))[:60]
    elapsed = payload.get("elapsed_s")

    if event_kind == "run_started":
        tooltip = f"{task} · running" if task else "running"
        return json.dumps({"text": "●", "class": "running", "tooltip": tooltip})

    if event_kind == "run_finished":
        if status == "completed":
            tooltip = f"{task} · done" if task else "done"
            if elapsed is not None:
                tooltip += f" ({elapsed:.0f}s)"
            return json.dumps({"text": "✓", "class": "done", "tooltip": tooltip})
        if status in ("errored", "aborted"):
            label = "error" if status == "errored" else "aborted"
            return json.dumps({"text": "✗", "class": "error", "tooltip": f"{task} · {label}"})

    return json.dumps({"text": "○", "class": "idle", "tooltip": "hyprland-agent · idle"})


def _idle_line() -> str:
    return json.dumps({"text": "○", "class": "idle", "tooltip": "hyprland-agent · idle"})


def _disconnected_line() -> str:
    return json.dumps({"text": "⊘", "class": "disconnected", "tooltip": "daemon offline"})


async def _watch() -> None:
    backoff = 1.0
    while True:
        try:
            async with connect(SOCKET_PATH) as conn:
                await conn.subscribe(Topic.runs)
                print(_idle_line(), flush=True)
                backoff = 1.0
                async for topic, payload in conn.events():
                    if topic != Topic.runs:
                        continue
                    kind = payload.get("kind", "")
                    line = _render(kind, payload)
                    print(line, flush=True)
        except DaemonUnavailable:
            print(_disconnected_line(), flush=True)
        except Exception:
            print(_disconnected_line(), flush=True)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


def main() -> None:
    try:
        asyncio.run(_watch())
    except KeyboardInterrupt:
        sys.exit(0)
