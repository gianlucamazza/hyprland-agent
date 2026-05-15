"""Tests for Claude brain action translation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agent.brain.claude import _handle_custom
from agent.schemas import ActionKind


@pytest.mark.asyncio
async def test_custom_terminal_command_action() -> None:
    _, actions = await _handle_custom(
        "terminal_command", {"command": "printf %s hello", "hold_s": 3}
    )

    assert actions[0].kind == ActionKind.terminal_command
    assert actions[0].params["command"] == "printf %s hello"
    assert actions[0].params["hold_s"] == 3


@pytest.mark.asyncio
async def test_custom_hypr_actions_are_queued_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = AsyncMock()
    monkeypatch.setattr("agent.brain.claude.hypr.dispatch", dispatch)

    _, focus_actions = await _handle_custom("focus_window", {"address": "0xabc"})
    _, dispatch_actions = await _handle_custom("dispatch_hypr", {"cmd": "workspace 2"})

    dispatch.assert_not_awaited()
    assert focus_actions[0].kind == ActionKind.focus_window
    assert dispatch_actions[0].kind == ActionKind.dispatch
