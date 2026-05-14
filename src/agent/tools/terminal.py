"""Agent-owned terminal command execution."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Awaitable, Callable

EmitFn = Callable[[str, dict], Awaitable[None]]

_DEFAULT_TIMEOUT = 300.0
_MAX_HOLD_S = 30.0


async def run_command(
    command: str,
    *,
    run_id: str,
    emit: EmitFn | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    hold_s: float = 0.0,
) -> int:
    """Run a shell command in a dedicated visible terminal owned by this run."""
    title = f"hyprland-agent:{run_id}"
    hold_s = _clamp_hold_s(hold_s)
    if emit is not None:
        await emit(
            "terminal_started",
            {"title": title, "command": command, "hold_s": hold_s},
        )

    proc = await asyncio.create_subprocess_exec(
        "foot",
        "--title",
        title,
        "sh",
        "-lc",
        _shell_script(command, hold_s),
        start_new_session=True,
    )
    try:
        code = await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        await _terminate_process(proc)
        if emit is not None:
            await emit("terminal_timed_out", {"title": title, "timeout_s": timeout})
        raise
    except asyncio.CancelledError:
        await _terminate_process(proc)
        if emit is not None:
            await emit("terminal_cancelled", {"title": title})
        raise

    if emit is not None:
        await emit("terminal_exited", {"title": title, "returncode": code})
    if code != 0:
        raise RuntimeError(f"terminal command exited with status {code}")
    return code


def _clamp_hold_s(value: float) -> float:
    return max(0.0, min(float(value), _MAX_HOLD_S))


def _shell_script(command: str, hold_s: float) -> str:
    if hold_s <= 0:
        return command
    return "\n".join(
        [
            command,
            "code=$?",
            'printf "\\n[hyprland-agent] exit code: %s\\n" "$code"',
            f"sleep {hold_s:g}",
            "exit $code",
        ]
    )


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        if proc.pid is not None:
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        try:
            if proc.pid is not None:
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()
