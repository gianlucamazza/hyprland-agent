"""LearningConsumer: single Topic.runs subscriber dispatching to all learners."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from agent.daemon.pubsub import PubSub
from agent.ipc.protocol import Topic

if TYPE_CHECKING:
    from agent.memory.episodic import EpisodicMemory
    from agent.learning.reflection import ReflectionEngine

log = logging.getLogger(__name__)

_MAX_CONCURRENT = 2


class LearningConsumer:
    """Subscribes to Topic.runs and dispatches run_finished events to learners."""

    def __init__(
        self,
        pubsub: PubSub,
        episodic: EpisodicMemory,
        reflection: ReflectionEngine,
    ) -> None:
        self._pubsub = pubsub
        self._episodic = episodic
        self._reflection = reflection
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT)
        self._task: asyncio.Task | None = None

    async def open(self) -> None:
        ready = asyncio.Event()
        self._task = asyncio.create_task(self._loop(ready), name="learning-consumer")
        await ready.wait()

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, ready: asyncio.Event) -> None:
        sub = await self._pubsub.subscribe(Topic.runs)
        ready.set()
        try:
            while True:
                msg = await sub.queue.get()
                if msg.get("kind") != "run_finished":
                    continue
                run_id = msg.get("run_id")
                outcome = msg.get("outcome", "unknown")
                if not run_id:
                    continue
                asyncio.create_task(self._handle(run_id, outcome))
        except asyncio.CancelledError:
            pass
        finally:
            await self._pubsub.unsubscribe(Topic.runs, sub)

    async def _handle(self, run_id: str, outcome: str) -> None:
        async with self._sem:
            await self._episodic.ingest(run_id)
            await self._reflection.reflect(run_id, outcome)
