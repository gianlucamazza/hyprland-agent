"""Agent-owned terminal command execution."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Awaitable, Callable

EmitFn = Callable[[str, dict], Awaitable[None]]

_DEFAULT_TIMEOUT = 300.0
_MAX_HOLD_S = 30.0
_CAPTURE_CAP = 8192  # bytes kept from stdout/stderr tail


async def run_command(
    command: str,
    *,
    run_id: str,
    emit: EmitFn | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    hold_s: float = 0.0,
    visible: bool = True,
) -> tuple[int, str, str]:
    """Run a shell command.

    visible=True (default): spawns a dedicated foot terminal window.
    visible=False: runs headlessly via shell, captures stdout/stderr (8 KB cap).
    Returns (returncode, stdout, stderr). stdout/stderr are empty when visible=True.
    """
    if visible:
        return await _run_visible(
            command, run_id=run_id, emit=emit, timeout=timeout, hold_s=hold_s
        )
    return await _run_capture(command, run_id=run_id, emit=emit, timeout=timeout)


async def _run_visible(
    command: str,
    *,
    run_id: str,
    emit: EmitFn | None = None,
    timeout: float,
    hold_s: float,
) -> tuple[int, str, str]:
    title = f"hyprland-agent:{run_id}"
    hold_s = _clamp_hold_s(hold_s)
    if emit is not None:
        await emit(
            "terminal_started",
            {"title": title, "command": command, "hold_s": hold_s, "visible": True},
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
        await emit(
            "terminal_exited", {"title": title, "returncode": code, "visible": True}
        )
    if code != 0:
        raise RuntimeError(f"terminal command exited with status {code}")
    return code, "", ""


async def _run_capture(
    command: str,
    *,
    run_id: str,
    emit: EmitFn | None = None,
    timeout: float,
) -> tuple[int, str, str]:
    title = f"hyprland-agent:{run_id}"
    if emit is not None:
        await emit(
            "terminal_started",
            {"title": title, "command": command, "hold_s": 0, "visible": False},
        )

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        if emit is not None:
            await emit("terminal_timed_out", {"title": title, "timeout_s": timeout})
        raise
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        if emit is not None:
            await emit("terminal_cancelled", {"title": title})
        raise

    stdout = stdout_b.decode(errors="replace")[-_CAPTURE_CAP:]
    stderr = stderr_b.decode(errors="replace")[-_CAPTURE_CAP:]
    code = proc.returncode or 0

    if emit is not None:
        await emit(
            "terminal_exited",
            {
                "title": title,
                "returncode": code,
                "stdout": stdout,
                "stderr": stderr,
                "visible": False,
            },
        )

    if code != 0:
        raise RuntimeError(f"command exited with status {code}: {stderr[:200]}")
    return code, stdout, stderr


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
