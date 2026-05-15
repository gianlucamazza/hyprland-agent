"""Tests for IdleIntegration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.integrations.idle import IdleIntegration
from agent.schemas import Action, ActionKind


@pytest.fixture
def idle_state():
    state = MagicMock()
    state.executor.active_run_ids = AsyncMock(return_value=["run-1", "run-2"])
    state.executor.cancel = AsyncMock(return_value=True)
    return state


@pytest.mark.asyncio
async def test_idle_setup_fails_without_jeepney():
    with patch.dict("sys.modules", {"jeepney": None}):
        integration = IdleIntegration()
        with pytest.raises(RuntimeError, match="jeepney"):
            await integration.setup(MagicMock())


@pytest.mark.asyncio
async def test_idle_on_lock_cancels_all_runs(idle_state):
    integration = IdleIntegration()
    integration._state = idle_state
    await integration._on_active_changed(True)
    idle_state.executor.active_run_ids.assert_awaited_once()
    assert idle_state.executor.cancel.await_count == 2


@pytest.mark.asyncio
async def test_idle_on_unlock_noop(idle_state):
    integration = IdleIntegration()
    integration._state = idle_state
    # should not raise and should not cancel anything
    await integration._on_active_changed(False)
    idle_state.executor.cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_handle_returns_none():
    integration = IdleIntegration()
    action = Action(kind=ActionKind.update_status, params={})
    result = await integration.handle(action)
    assert result is None


@pytest.mark.asyncio
async def test_idle_teardown_cancels_task():
    import asyncio

    integration = IdleIntegration()
    # Create a task that blocks forever, then teardown should cancel it
    integration._task = asyncio.create_task(asyncio.sleep(999))
    await integration.teardown()
    assert integration._task is None
