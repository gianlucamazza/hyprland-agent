"""agent-waybar — stream run state + voice state as Waybar custom-module JSON.

Invoked by Waybar as a long-running exec::

    "exec": "agent-waybar"
    "return-type": "json"

Emits one JSON line per state change::

    {"text": "● ", "class": "running voice-idle", "tooltip": "task · running · voce attiva"}
    {"text": "○ ", "class": "idle voice-muted",   "tooltip": "idle · voce mutata"}
    {"text": "⊘ ", "class": "disconnected voice-offline", "tooltip": "daemon offline · voce offline"}

On daemon restart reconnects with exponential back-off (max 30s).
Voice state (offline / muted / idle) is sampled on every event.
Click actions are configured in ``~/.config/waybar/config``.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from agent.client.connection import connect
from agent.client.errors import DaemonUnavailable
from agent.ipc.constants import SOCKET_PATH
from agent.ipc.protocol import Topic

_MUTED_FLAG = (
    Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    / "hyprland-agent-voice.muted"
)

_VOICE_STATES = {
    "offline": {"icon": "", "cls": "voice-offline", "tooltip": "voce offline"},
    "muted": {"icon": "", "cls": "voice-muted", "tooltip": "voce mutata"},
    "idle": {"icon": "", "cls": "voice-idle", "tooltip": "voce attiva"},
}


def _voice_state() -> dict:
    """Return one of the ``_VOICE_STATES`` dicts based on actual system state."""
    if not shutil.which("agent-voice"):
        return _VOICE_STATES["offline"]
    if _MUTED_FLAG.exists():
        return _VOICE_STATES["muted"]
    return _VOICE_STATES["idle"]


def _merge(base_text: str, base_cls: str, base_tooltip: str, voice: dict) -> str:
    return json.dumps(
        {
            "text": f"{base_text} {voice['icon']}",
            "class": f"{base_cls} {voice['cls']}",
            "tooltip": f"{base_tooltip} · {voice['tooltip']}",
        }
    )


def _render(event_kind: str, payload: dict[str, Any], voice: dict | None = None) -> str:
    status = payload.get("status", "")
    task = str(payload.get("task", ""))[:60]
    elapsed = payload.get("elapsed_s")
    if voice is None:
        voice = _voice_state()

    if event_kind == "run_started":
        tooltip = f"{task} · running" if task else "running"
        return _merge("●", "running", tooltip, voice)

    if event_kind == "run_finished":
        if status == "completed":
            tooltip = f"{task} · done" if task else "done"
            if elapsed is not None:
                tooltip += f" ({elapsed:.0f}s)"
            return _merge("✓", "done", tooltip, voice)
        if status in ("errored", "aborted"):
            label = "error" if status == "errored" else "aborted"
            return _merge("✗", "error", f"{task} · {label}", voice)

    return _merge("○", "idle", "hyprland-agent · idle", voice)


def _idle_line(voice: dict | None = None) -> str:
    if voice is None:
        voice = _voice_state()
    return _merge("○", "idle", "hyprland-agent · idle", voice)


def _disconnected_line(voice: dict | None = None) -> str:
    if voice is None:
        voice = _voice_state()
    return _merge("⊘", "disconnected", "daemon offline", voice)


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
