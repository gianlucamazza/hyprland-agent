"""Tests for EpisodicIngestor subscriber."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.daemon.pubsub import PubSub
from agent.ipc.protocol import Topic
from agent.memory.ingest_consumer import EpisodicIngestor


class _MockEpisodic:
    def __init__(self):
        self.ingested: list[str] = []

    async def ingest(self, run_id: str) -> None:
        self.ingested.append(run_id)


async def test_ingestor_calls_ingest_on_run_completed() -> None:
    pubsub = PubSub()
    episodic = _MockEpisodic()
    ingestor = EpisodicIngestor(pubsub, episodic)

    await ingestor.start()
    await pubsub.publish(Topic.runs, {"kind": "run_completed", "run_id": "r1"})
    await asyncio.sleep(0.05)
    await ingestor.stop()

    assert "r1" in episodic.ingested


async def test_ingestor_calls_ingest_on_run_errored() -> None:
    pubsub = PubSub()
    episodic = _MockEpisodic()
    ingestor = EpisodicIngestor(pubsub, episodic)

    await ingestor.start()
    await pubsub.publish(Topic.runs, {"kind": "run_errored", "run_id": "r2"})
    await asyncio.sleep(0.05)
    await ingestor.stop()

    assert "r2" in episodic.ingested


async def test_ingestor_ignores_non_finish_events() -> None:
    pubsub = PubSub()
    episodic = _MockEpisodic()
    ingestor = EpisodicIngestor(pubsub, episodic)

    await ingestor.start()
    await pubsub.publish(Topic.runs, {"kind": "action", "run_id": "r3"})
    await asyncio.sleep(0.05)
    await ingestor.stop()

    assert "r3" not in episodic.ingested


async def test_ingestor_ignores_event_without_run_id() -> None:
    pubsub = PubSub()
    episodic = _MockEpisodic()
    ingestor = EpisodicIngestor(pubsub, episodic)

    await ingestor.start()
    await pubsub.publish(Topic.runs, {"kind": "run_completed"})
    await asyncio.sleep(0.05)
    await ingestor.stop()

    assert episodic.ingested == []


async def test_ingestor_stop_is_idempotent() -> None:
    pubsub = PubSub()
    episodic = _MockEpisodic()
    ingestor = EpisodicIngestor(pubsub, episodic)
    await ingestor.start()
    await ingestor.stop()
    await ingestor.stop()  # should not raise
