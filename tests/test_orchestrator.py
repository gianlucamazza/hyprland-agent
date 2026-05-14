"""Tests for orchestrator safety and run-history events."""

from __future__ import annotations

from typing import Any

import pytest

from agent.daemon.run_executor import RunContext
from agent.orchestrator import run
from agent.schemas import Window


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

    await run(
        "do nothing",
        brain,
        dry_run=True,
        ctx=RunContext(run_id="run-1", _emit_fn=emit),
    )

    assert not brain.called
    assert events[0] == ("start", {"task": "do nothing"})
    assert events[1][0] == "blocked"
    assert events[1][1]["reason"] == "window_not_allowlisted"
    assert events[1][1]["active"]["app_class"] == "blocked-app"
