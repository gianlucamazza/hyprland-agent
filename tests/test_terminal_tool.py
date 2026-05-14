"""Tests for agent-owned terminal command execution."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent.tools import terminal


class _FakeProc:
    def __init__(self, code: int = 0, wait_forever: bool = False) -> None:
        self.pid = None
        self.returncode: int | None = None
        self._code = code
        self._wait_forever = wait_forever
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        if self._wait_forever and not self.terminated and not self.killed:
            await asyncio.Event().wait()
        self.returncode = self._code
        return self._code

    def terminate(self) -> None:
        self.terminated = True
        self._code = -15

    def kill(self) -> None:
        self.killed = True
        self._code = -9


@pytest.mark.asyncio
async def test_run_command_launches_owned_foot_and_emits_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    proc = _FakeProc(code=0)

    async def create_subprocess_exec(*args: str, **kwargs: Any) -> _FakeProc:
        assert args == (
            "foot",
            "--title",
            "hyprland-agent:run-1",
            "sh",
            "-lc",
            "printf %s hello",
        )
        assert kwargs["start_new_session"] is True
        return proc

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    monkeypatch.setattr(
        "agent.tools.terminal.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )

    code = await terminal.run_command("printf %s hello", run_id="run-1", emit=emit)

    assert code == 0
    assert [event[0] for event in events] == ["terminal_started", "terminal_exited"]
    assert events[0][1]["title"] == "hyprland-agent:run-1"
    assert events[0][1]["hold_s"] == 0.0


@pytest.mark.asyncio
async def test_run_command_can_hold_terminal_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _FakeProc(code=0)

    async def create_subprocess_exec(*args: str, **kwargs: Any) -> _FakeProc:
        script = args[5]
        assert args[:5] == (
            "foot",
            "--title",
            "hyprland-agent:run-1",
            "sh",
            "-lc",
        )
        assert "printf %s hello" in script
        assert 'printf "\\n[hyprland-agent] exit code: %s\\n" "$code"' in script
        assert "sleep 3" in script
        assert "exit $code" in script
        return proc

    monkeypatch.setattr(
        "agent.tools.terminal.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )

    code = await terminal.run_command("printf %s hello", run_id="run-1", hold_s=3)

    assert code == 0


def test_shell_hold_clamps_to_maximum() -> None:
    script = terminal._shell_script("true", terminal._clamp_hold_s(120))

    assert "sleep 30" in script


@pytest.mark.asyncio
async def test_run_command_terminates_owned_terminal_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    proc = _FakeProc(wait_forever=True)

    async def create_subprocess_exec(*args: str, **kwargs: Any) -> _FakeProc:
        return proc

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    monkeypatch.setattr(
        "agent.tools.terminal.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )

    with pytest.raises(asyncio.TimeoutError):
        await terminal.run_command("sleep 60", run_id="run-1", emit=emit, timeout=0.01)

    assert proc.terminated
    assert [event[0] for event in events] == [
        "terminal_started",
        "terminal_timed_out",
    ]
