"""Tests for killswitch edge-triggered auto-disarm behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.safety import killswitch


@pytest.fixture(autouse=True)
def _disarm_after(tmp_path, monkeypatch):
    """Redirect the STOP flag to a temp dir so tests don't touch ~/.cache."""
    flag = tmp_path / "STOP"
    monkeypatch.setattr("agent.safety.killswitch._FLAG", flag)
    yield
    flag.unlink(missing_ok=True)


def test_arm_creates_flag():
    killswitch.arm()
    assert killswitch.is_stopped()


def test_disarm_removes_flag():
    killswitch.arm()
    killswitch.disarm()
    assert not killswitch.is_stopped()


def test_disarm_idempotent():
    killswitch.disarm()
    killswitch.disarm()  # must not raise


@pytest.mark.asyncio
async def test_poller_auto_disarms_after_cancel():
    """Poller must call disarm() after cancelling runs, so the flag is gone."""
    from agent.daemon.main import _killswitch_poller

    executor = MagicMock()
    executor.active_run_ids = AsyncMock(return_value=["run-1"])
    executor.cancel = AsyncMock()

    state = MagicMock()
    state.executor = executor

    killswitch.arm()
    shutdown = asyncio.Event()

    # Run one iteration then shut down
    async def _one_tick():
        await _killswitch_poller(state, shutdown)

    shutdown_task = asyncio.get_event_loop().call_later(0.15, shutdown.set)
    await asyncio.wait_for(_one_tick(), timeout=1.0)

    assert not killswitch.is_stopped(), "flag must be disarmed after trigger"
    executor.cancel.assert_awaited_once_with("run-1")
    shutdown_task.cancel()


@pytest.mark.asyncio
async def test_poller_logs_warning_once(caplog):
    """A single armed flag must produce exactly one WARNING line."""
    import logging

    from agent.daemon.main import _killswitch_poller

    state = MagicMock()
    state.executor.active_run_ids = AsyncMock(return_value=[])
    state.executor.cancel = AsyncMock()

    killswitch.arm()
    shutdown = asyncio.Event()

    with caplog.at_level(logging.WARNING, logger="agent.daemon.main"):
        asyncio.get_event_loop().call_later(0.25, shutdown.set)
        await asyncio.wait_for(_killswitch_poller(state, shutdown), timeout=1.0)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, f"expected 1 warning, got {len(warnings)}"
