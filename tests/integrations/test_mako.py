"""Tests for MakoIntegration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.integrations.mako import MakoIntegration
from agent.schemas import Action, ActionKind
from agent.tools._proc import ProcResult


@pytest.fixture
def mako_state():
    state = MagicMock()
    state.config.integrations.mako_app_name = "hyprland-agent"
    state.config.integrations.binary_overrides = {}
    return state


@pytest.fixture
def mako(mako_state):
    return MakoIntegration()


@pytest.mark.asyncio
async def test_handle_notify_calls_notify_send(mako, mako_state, monkeypatch):
    calls: list[tuple] = []

    async def fake_run(argv, **kw):
        calls.append(tuple(argv))
        return ProcResult(returncode=0)

    monkeypatch.setattr("agent.integrations.mako._proc_run", fake_run)
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    await mako.setup(mako_state)

    action = Action(
        kind=ActionKind.notify,
        params={"message": "done", "summary": "task", "category": "done"},
    )
    result = await mako.handle(action)
    assert result is not None
    assert result.kind == "notify"
    assert calls[0][0] == "notify-send"
    assert "--app-name" in calls[0]
    assert "hyprland-agent" in calls[0]


@pytest.mark.asyncio
async def test_error_category_sets_critical_urgency(mako, mako_state, monkeypatch):
    captured: list[list] = []

    async def fake_run(argv, **kw):
        captured.append(list(argv))
        return ProcResult(returncode=0)

    monkeypatch.setattr("agent.integrations.mako._proc_run", fake_run)
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    await mako.setup(mako_state)

    action = Action(
        kind=ActionKind.notify, params={"category": "error", "message": "oops"}
    )
    await mako.handle(action)
    assert "critical" in captured[0]


@pytest.mark.asyncio
async def test_non_notify_action_passes_through(mako, mako_state, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    await mako.setup(mako_state)
    action = Action(kind=ActionKind.key, params={"combo": "ctrl+c"})
    result = await mako.handle(action)
    assert result is None


@pytest.mark.asyncio
async def test_missing_binary_raises(mako, mako_state, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(RuntimeError, match="not found"):
        await mako.setup(mako_state)
