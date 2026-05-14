"""Tests for orchestrator safety and run-history events."""

from __future__ import annotations

from typing import Any
from unittest.mock import ANY, AsyncMock

import pytest

from agent.daemon.run_executor import RunContext
from agent.orchestrator import plan, run
from agent.schemas import Action, ActionKind, Monitor, Window


class _Brain:
    called = False

    async def decide(self, state: Any, task: str) -> list[Any]:
        self.called = True
        return []


def _window(app_class: str = "blocked-app") -> Window:
    return Window.model_validate(
        {
            "address": "0xabc",
            "title": "Blocked Window",
            "class": app_class,
            "workspace_id": 1,
            "at": [0, 0],
            "size": [800, 600],
            "floating": False,
            "hidden": False,
            "pid": 1234,
            "monitor": 0,
        }
    )


@pytest.mark.asyncio
async def test_blocked_window_emits_run_history_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    brain = _Brain()

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    async def active_window() -> Window:
        return _window()

    monkeypatch.setattr("agent.orchestrator.hypr.active_window", active_window)
    monkeypatch.setattr("agent.orchestrator.is_allowed", lambda window: False)

    await run("do nothing", brain, ctx=RunContext(run_id="run-1", _emit_fn=emit))

    assert not brain.called
    assert events[0] == ("start", {"task": "do nothing"})
    assert events[1][0] == "blocked"
    assert events[1][1]["reason"] == "window_not_allowlisted"
    assert events[1][1]["active"]["app_class"] == "blocked-app"


@pytest.mark.asyncio
async def test_plan_records_actions_without_executing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    brain = _Brain()
    brain.decide = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            Action(kind=ActionKind.type_text, params={"text": "hello"}),
            Action(kind=ActionKind.key, params={"combo": "Return"}),
        ]
    )

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    async def active_window() -> Window:
        return _window("foot")

    async def active_monitor() -> Monitor:
        return Monitor(
            id=0,
            name="DP-1",
            width=1920,
            height=1080,
            x=0,
            y=0,
            scale=1.0,
            focused=True,
        )

    monkeypatch.setattr("agent.orchestrator.hypr.active_window", active_window)
    monkeypatch.setattr("agent.orchestrator.hypr.active_monitor", active_monitor)
    monkeypatch.setattr("agent.orchestrator.hypr.clients", AsyncMock(return_value=[]))
    monkeypatch.setattr("agent.orchestrator.screen.full", AsyncMock(return_value=b"png"))
    monkeypatch.setattr("agent.orchestrator.is_allowed", lambda window: True)
    type_text = AsyncMock()
    key = AsyncMock()
    monkeypatch.setattr("agent.orchestrator.inp.type_text", type_text)
    monkeypatch.setattr("agent.orchestrator.inp.key", key)

    await plan("type hello", brain, ctx=RunContext(run_id="run-1", _emit_fn=emit))

    type_text.assert_not_awaited()
    key.assert_not_awaited()
    assert [event[0] for event in events] == [
        "start",
        "state",
        "actions",
        "action",
        "action",
        "done",
    ]


@pytest.mark.asyncio
async def test_run_executes_terminal_command_in_owned_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    brain = _Brain()
    brain.decide = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            Action(
                kind=ActionKind.terminal_command,
                params={
                    "command": "printf %s hello > /tmp/hyprland-agent-test.txt",
                    "hold_s": 3,
                },
            )
        ]
    )

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    async def active_window() -> Window:
        return _window("foot")

    async def active_monitor() -> Monitor:
        return Monitor(
            id=0,
            name="DP-1",
            width=1920,
            height=1080,
            x=0,
            y=0,
            scale=1.0,
            focused=True,
        )

    monkeypatch.setattr("agent.orchestrator.hypr.active_window", active_window)
    monkeypatch.setattr("agent.orchestrator.hypr.active_monitor", active_monitor)
    monkeypatch.setattr("agent.orchestrator.hypr.clients", AsyncMock(return_value=[]))
    monkeypatch.setattr("agent.orchestrator.screen.full", AsyncMock(return_value=b"png"))
    monkeypatch.setattr("agent.orchestrator.is_allowed", lambda window: True)
    run_command = AsyncMock(return_value=0)
    monkeypatch.setattr("agent.orchestrator.terminal.run_command", run_command)

    await run("write file", brain, ctx=RunContext(run_id="run-1", _emit_fn=emit))

    run_command.assert_awaited_once_with(
        "printf %s hello > /tmp/hyprland-agent-test.txt",
        run_id="run-1",
        emit=ANY,
        hold_s=3.0,
    )
    assert [event[0] for event in events] == [
        "start",
        "state",
        "actions",
        "action",
        "done",
    ]


@pytest.mark.asyncio
async def test_keyboard_action_blocked_in_control_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    brain = _Brain()
    brain.decide = AsyncMock(  # type: ignore[method-assign]
        return_value=[Action(kind=ActionKind.type_text, params={"text": "printf bad"})]
    )

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    async def active_window() -> Window:
        return _window("foot")

    async def active_monitor() -> Monitor:
        return Monitor(
            id=0,
            name="DP-1",
            width=1920,
            height=1080,
            x=0,
            y=0,
            scale=1.0,
            focused=True,
        )

    monkeypatch.setattr("agent.orchestrator.hypr.active_window", active_window)
    monkeypatch.setattr("agent.orchestrator.hypr.active_monitor", active_monitor)
    monkeypatch.setattr("agent.orchestrator.hypr.clients", AsyncMock(return_value=[]))
    monkeypatch.setattr("agent.orchestrator.screen.full", AsyncMock(return_value=b"png"))
    monkeypatch.setattr("agent.orchestrator.is_allowed", lambda window: True)
    monkeypatch.setattr("agent.orchestrator._process_tree_contains", lambda *_: True)
    type_text = AsyncMock()
    monkeypatch.setattr("agent.orchestrator.inp.type_text", type_text)

    await run("type bad command", brain, ctx=RunContext(run_id="run-1", _emit_fn=emit))

    type_text.assert_not_awaited()
    blocked = [payload for kind, payload in events if kind == "blocked"]
    assert blocked[0]["reason"] == "control_terminal_keyboard_target"
