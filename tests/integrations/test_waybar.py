"""Tests for WaybarIntegration and waybar_module JSON rendering."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agent.integrations.waybar import WaybarIntegration
from agent.schemas import Action, ActionKind


@pytest.fixture
def waybar_state():
    state = MagicMock()
    return state


@pytest.mark.asyncio
async def test_waybar_loads_without_binary(waybar_state):
    w = WaybarIntegration()
    # should not raise — no binary needed server-side
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
    await w.teardown()  # must not raise


def test_waybar_module_render_running():
    from agent.cli.waybar_module import _render

    line = _render("run_started", {"task": "open browser"})
    data = json.loads(line)
    assert data["class"] == "running"
    assert "●" in data["text"]
    assert "open browser" in data["tooltip"]


def test_waybar_module_render_done():
    from agent.cli.waybar_module import _render

    line = _render(
        "run_finished", {"status": "completed", "task": "do thing", "elapsed_s": 5.0}
    )
    data = json.loads(line)
    assert data["class"] == "done"
    assert "✓" in data["text"]
    assert "5s" in data["tooltip"]


def test_waybar_module_render_error():
    from agent.cli.waybar_module import _render

    line = _render("run_finished", {"status": "errored", "task": "fail"})
    data = json.loads(line)
    assert data["class"] == "error"
    assert "✗" in data["text"]


def test_waybar_module_idle_line():
    from agent.cli.waybar_module import _idle_line

    data = json.loads(_idle_line())
    assert data["class"] == "idle"
    assert "○" in data["text"]


def test_waybar_module_disconnected_line():
    from agent.cli.waybar_module import _disconnected_line

    data = json.loads(_disconnected_line())
    assert data["class"] == "disconnected"
