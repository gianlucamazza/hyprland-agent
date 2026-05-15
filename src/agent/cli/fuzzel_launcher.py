"""fuzzel-agent — pick or type a task and send it to the daemon via fuzzel.

Usage:
    fuzzel-agent          # show recent tasks + free text entry
    fuzzel-agent --brain claude  # run with specific brain

Fuzzel runs in --dmenu mode.  The first line is a free-text placeholder;
subsequent lines are recent tasks (last 20, newest first).
If the user selects a line, it is sent as-is; if they type something new
it is sent verbatim.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

from agent.client.connection import connect
from agent.client.errors import DaemonUnavailable, RpcError
from agent.ipc.constants import SOCKET_PATH
from agent.ipc.protocol import RpcMethod

_MAX_RECENT = 20
_PLACEHOLDER = "Type a new task…"


async def _pick_task(brain: str) -> int:
    try:
        async with connect(SOCKET_PATH) as conn:
            data = await conn.request(RpcMethod.list_runs, {"limit": _MAX_RECENT})
    except DaemonUnavailable:
        print("error: daemon is not running", file=sys.stderr)
        return 1

    runs = data.get("runs", [])
    recent: list[str] = []
    seen: set[str] = set()
    for r in runs:
        task = str(r.get("task", "")).strip()
        if task and task not in seen and task != _PLACEHOLDER:
            seen.add(task)
            recent.append(task)

    lines = [_PLACEHOLDER] + recent
    menu_input = "\n".join(lines) + "\n"

    try:
        proc = subprocess.run(
            ["fuzzel", "--dmenu", "--prompt", "agent: "],
            input=menu_input,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("error: fuzzel not found", file=sys.stderr)
        return 1

    if proc.returncode != 0:
        return 0  # user cancelled

    chosen = proc.stdout.strip()
    if not chosen or chosen == _PLACEHOLDER:
        return 0

    try:
        async with connect(SOCKET_PATH) as conn:
            result = await conn.request(
                RpcMethod.run_task, {"task": chosen, "brain": brain}
            )
        print(f"run_id: {result.get('run_id', '?')}")
        return 0
    except (DaemonUnavailable, RpcError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Launch an agent task via fuzzel")
    parser.add_argument("--brain", default="auto")
    args = parser.parse_args()

    sys.exit(asyncio.run(_pick_task(args.brain)))
