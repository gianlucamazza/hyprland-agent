"""Tests for WorldContext snapshot."""

from __future__ import annotations

import asyncio

import pytest

from agent.awareness.world_context import WorldSnapshot, snapshot
from agent.schemas import Window


def _win(app_class: str = "foot", workspace_id: int = 1, pid: int = 42) -> Window:
    return Window.model_validate(
        {
            "address": "0xabc",
            "title": "Test Window",
            "class": app_class,
            "workspace_id": workspace_id,
            "at": [0, 0],
            "size": [800, 600],
            "floating": False,
            "hidden": False,
            "pid": pid,
            "monitor": 0,
        }
    )


@pytest.mark.asyncio
async def test_snapshot_with_active_window() -> None:
    win = _win("firefox", workspace_id=2)
    ws = await snapshot(
        active_window=win,
        monitor_width=1920,
        monitor_height=1080,
        windows=[win],
    )
    assert ws.active_window_class == "firefox"
    assert ws.active_window_title == "Test Window"
    assert ws.active_workspace_id == 2
    assert ws.monitor_width == 1920
    assert ws.window_count == 1


@pytest.mark.asyncio
async def test_snapshot_without_active_window() -> None:
    ws = await snapshot(
        active_window=None,
        monitor_width=2560,
        monitor_height=1440,
        windows=[],
    )
    assert ws.active_window_class is None
    assert ws.active_window_title is None
    assert ws.window_count == 0


def test_to_dict_has_all_keys() -> None:
    ws = WorldSnapshot(
        active_window_class="foot",
        active_window_title="zsh",
        active_workspace_id=1,
        monitor_width=1920,
        monitor_height=1080,
        window_count=3,
        timestamp=0.0,
    )
    d = ws.to_dict()
    for key in (
        "active_window_class",
        "active_window_title",
        "monitor_width",
        "window_count",
    ):
        assert key in d


def test_render_for_prompt_with_active_window() -> None:
    ws = WorldSnapshot(
        active_window_class="foot",
        active_window_title="zsh",
        active_workspace_id=1,
        monitor_width=1920,
        monitor_height=1080,
        window_count=2,
        timestamp=0.0,
    )
    text = ws.render_for_prompt()
    assert "foot" in text
    assert "1920" in text


def test_render_for_prompt_empty_when_no_window() -> None:
    ws = WorldSnapshot(
        active_window_class=None,
        active_window_title=None,
        active_workspace_id=None,
        monitor_width=1920,
        monitor_height=1080,
        window_count=0,
        timestamp=0.0,
    )
    assert ws.render_for_prompt() == ""
