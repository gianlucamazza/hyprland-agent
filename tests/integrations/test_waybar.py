"""Tests for WaybarIntegration and waybar_module JSON rendering with voice."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agent.integrations.waybar import WaybarIntegration
from agent.schemas import Action, ActionKind

_VOICE_IDLE = {"icon": "", "cls": "voice-idle", "tooltip": "voce attiva"}
_VOICE_MUTED = {"icon": "", "cls": "voice-muted", "tooltip": "voce mutata"}
_VOICE_OFFLINE = {"icon": "", "cls": "voice-offline", "tooltip": "voce offline"}


@pytest.fixture
def waybar_state():
    state = MagicMock()
    return state


@pytest.mark.asyncio
async def test_waybar_loads_without_binary(waybar_state):
    w = WaybarIntegration()
    await w.setup(waybar_state)
    assert True


@pytest.mark.asyncio
async def test_waybar_handle_returns_none(waybar_state):
    w = WaybarIntegration()
    await w.setup(waybar_state)
    action = Action(kind=ActionKind.notify, params={})
    result = await w.handle(action)
    assert result is None


@pytest.mark.asyncio
async def test_waybar_teardown_is_noop(waybar_state):
    w = WaybarIntegration()
    await w.setup(waybar_state)
    await w.teardown()


# ---------------------------------------------------------------------------
# Run state + voice state rendering
# ---------------------------------------------------------------------------


def _render(*args, **kw):
    from agent.cli.waybar_module import _render

    return _render(*args, **kw)


def test_render_running_voice_idle():
    line = _render("run_started", {"task": "open browser"}, _VOICE_IDLE)
    data = json.loads(line)
    assert "running" in data["class"]
    assert "voice-idle" in data["class"]
    assert "●" in data["text"]
    assert "" in data["text"]
    assert "open browser · running" in data["tooltip"]
    assert "voce attiva" in data["tooltip"]


def test_render_running_voice_muted():
    line = _render("run_started", {"task": "open browser"}, _VOICE_MUTED)
    data = json.loads(line)
    assert "running" in data["class"]
    assert "voice-muted" in data["class"]
    assert "●" in data["text"]
    assert "" in data["text"]
    assert "voce mutata" in data["tooltip"]


def test_render_done_voice_idle():
    line = _render(
        "run_finished", {"status": "completed", "task": "do thing", "elapsed_s": 5.0}, _VOICE_IDLE
    )
    data = json.loads(line)
    assert "done" in data["class"]
    assert "voice-idle" in data["class"]
    assert "✓" in data["text"]
    assert "5s" in data["tooltip"]
    assert "voce attiva" in data["tooltip"]


def test_render_error_voice_offline():
    line = _render("run_finished", {"status": "errored", "task": "fail"}, _VOICE_OFFLINE)
    data = json.loads(line)
    assert "error" in data["class"]
    assert "voice-offline" in data["class"]
    assert "✗" in data["text"]
    assert "voce offline" in data["tooltip"]


def test_render_idle_voice_muted():
    line = _render("unknown_event", {}, _VOICE_MUTED)
    data = json.loads(line)
    assert "idle" in data["class"]
    assert "voice-muted" in data["class"]
    assert "○" in data["text"]
    assert "" in data["text"]


def test_render_aborted_voice_idle():
    line = _render("run_finished", {"status": "aborted", "task": "task"}, _VOICE_IDLE)
    data = json.loads(line)
    assert "error" in data["class"]
    assert "aborted" in data["tooltip"]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def test_idle_line_voice_idle():
    from agent.cli.waybar_module import _idle_line

    line = _idle_line(_VOICE_IDLE)
    data = json.loads(line)
    assert data["class"] == "idle voice-idle"
    assert "○" in data["text"]
    assert "hyprland-agent" in data["tooltip"]


def test_idle_line_voice_muted():
    from agent.cli.waybar_module import _idle_line

    line = _idle_line(_VOICE_MUTED)
    data = json.loads(line)
    assert "voice-muted" in data["class"]
    assert "" in data["text"]


def test_disconnected_line_voice_offline():
    from agent.cli.waybar_module import _disconnected_line

    line = _disconnected_line(_VOICE_OFFLINE)
    data = json.loads(line)
    assert data["class"] == "disconnected voice-offline"
    assert "⊘" in data["text"]
    assert "daemon offline" in data["tooltip"]


def test_disconnected_line_voice_idle():
    from agent.cli.waybar_module import _disconnected_line

    line = _disconnected_line(_VOICE_IDLE)
    data = json.loads(line)
    assert data["class"] == "disconnected voice-idle"


# ---------------------------------------------------------------------------
# Voice state detection (mocked)
# ---------------------------------------------------------------------------


def test_voice_state_offline_when_no_binary(monkeypatch):
    from agent.cli.waybar_module import _VOICE_STATES, _voice_state

    monkeypatch.setattr("agent.cli.waybar_module.shutil.which", lambda _: None)
    assert _voice_state() == _VOICE_STATES["offline"]


def test_voice_state_muted_when_flag_exists(monkeypatch):
    from unittest.mock import MagicMock

    from agent.cli.waybar_module import _VOICE_STATES, _voice_state

    monkeypatch.setattr("agent.cli.waybar_module.shutil.which", lambda _: "/usr/bin/agent-voice")
    fake_flag = MagicMock()
    fake_flag.exists.return_value = True
    monkeypatch.setattr("agent.cli.waybar_module._MUTED_FLAG", fake_flag)
    assert _voice_state() == _VOICE_STATES["muted"]


def test_voice_state_idle_when_alive_and_not_muted(monkeypatch):
    from unittest.mock import MagicMock

    from agent.cli.waybar_module import _VOICE_STATES, _voice_state

    monkeypatch.setattr("agent.cli.waybar_module.shutil.which", lambda _: "/usr/bin/agent-voice")
    fake_flag = MagicMock()
    fake_flag.exists.return_value = False
    monkeypatch.setattr("agent.cli.waybar_module._MUTED_FLAG", fake_flag)
    assert _voice_state() == _VOICE_STATES["idle"]
