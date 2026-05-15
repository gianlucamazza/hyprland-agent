"""Tests that run_executor publishes run_finished with outcome payload."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.daemon.pubsub import PubSub
from agent.daemon.run_executor import RunExecutor
from agent.daemon.store import RunStore
from agent.ipc.protocol import Topic


@pytest.fixture
async def store(tmp_path: Path) -> RunStore:
    s = RunStore(path=tmp_path / "runs.db")
    await s.open()
    return s


async def _run_with_executor(
    store: RunStore, pubsub: PubSub, orchestrate_side_effect=None
) -> list[dict]:
    """Helper: submit a run, collect all Topic.runs messages, return them."""
    from agent.daemon.audit_log import AuditLog

    audit = AuditLog(enabled=False)
    await audit.open()
    executor = RunExecutor(store, pubsub, audit)

    received: list[dict] = []
    sub = await pubsub.subscribe(Topic.runs)

    async def _collector():
        while True:
            received.append(await sub.queue.get())

    collector_task = asyncio.create_task(_collector())

    brain = MagicMock()
    if orchestrate_side_effect is not None:
        orchestrate_patch = AsyncMock(side_effect=orchestrate_side_effect)
    else:
        orchestrate_patch = AsyncMock(return_value=None)

    with (
        patch("agent.brain.router.get_brain", return_value=brain),
        patch("agent.orchestrator.run", orchestrate_patch),
    ):
        await executor.submit("test task", "claude")
        await asyncio.sleep(0.3)

    collector_task.cancel()
    await asyncio.gather(collector_task, return_exceptions=True)
    await pubsub.unsubscribe(Topic.runs, sub)
    await audit.close()
    return received


async def test_run_finished_published_on_completion(store: RunStore) -> None:
    pubsub = PubSub()
    received = await _run_with_executor(store, pubsub)

    kinds = [m.get("kind") for m in received]
    assert "run_finished" in kinds

    finished = next(m for m in received if m.get("kind") == "run_finished")
    assert finished["task"] == "test task"
    assert "outcome" in finished
    assert "status" in finished


async def test_run_finished_published_on_stuck(store: RunStore) -> None:
    from agent.awareness.meta_cognition import StuckError

    pubsub = PubSub()
    received = await _run_with_executor(store, pubsub, orchestrate_side_effect=StuckError("stuck"))

    kinds = [m.get("kind") for m in received]
    assert "run_finished" in kinds
