"""Tests for FuzzelIntegration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.integrations.fuzzel import FuzzelIntegration
from agent.schemas import Action, ActionKind


@pytest.fixture
def fuzzel_state():
    state = MagicMock()
    state.config.integrations.binary_overrides = {}
    return state


@pytest.mark.asyncio
async def test_fuzzel_setup_ok(fuzzel_state, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    f = FuzzelIntegration()
    await f.setup(fuzzel_state)
    assert f._available is True


@pytest.mark.asyncio
async def test_fuzzel_missing_binary_raises(fuzzel_state, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: None)
    f = FuzzelIntegration()
    with pytest.raises(RuntimeError, match="not found"):
        await f.setup(fuzzel_state)


@pytest.mark.asyncio
async def test_fuzzel_handle_returns_none(fuzzel_state, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    f = FuzzelIntegration()
    await f.setup(fuzzel_state)
    action = Action(kind=ActionKind.notify, params={})
    result = await f.handle(action)
    assert result is None


@pytest.mark.asyncio
async def test_fuzzel_binary_override(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: f"/custom/{b}")
    state = MagicMock()
    state.config.integrations.binary_overrides = {"fuzzel": "myfuzzel"}
    f = FuzzelIntegration()
    await f.setup(state)
    assert f._binary == "myfuzzel"
