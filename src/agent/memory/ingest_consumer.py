"""EpisodicIngestor: subscribes to Topic.runs and ingests completed runs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from agent.daemon.pubsub import PubSub
from agent.ipc.protocol import Topic

if TYPE_CHECKING:
    from agent.memory.episodic import EpisodicMemory

log = logging.getLogger(__name__)

_FINISH_KINDS = {"run_completed", "run_errored", "run_aborted"}
_MAX_CONCURRENT = 2


class EpisodicIngestor:
    """Listens on Topic.runs and ingests finished runs into episodic memory."""

    def __init__(self, pubsub: PubSub, episodic: EpisodicMemory) -> None:
        self._pubsub = pubsub
        self._episodic = episodic
        self._task: asyncio.Task | None = None
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT)
        self._bg_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        ready = asyncio.Event()
        self._task = asyncio.create_task(self._loop(ready), name="episodic-ingestor")
        await ready.wait()  # block until subscriber is attached

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self, ready: asyncio.Event | None = None) -> None:
        sub = await self._pubsub.subscribe(Topic.runs)
        if ready is not None:
            ready.set()
        try:
            while True:
                msg = await sub.queue.get()
                kind = msg.get("kind", "")
                if kind not in _FINISH_KINDS:
                    continue
                run_id = msg.get("run_id")
                if not run_id:
                    continue
                t = asyncio.create_task(self._ingest_safe(run_id))
                self._bg_tasks.add(t)
                t.add_done_callback(self._bg_tasks.discard)
        except asyncio.CancelledError:
            raise
        finally:
            await self._pubsub.unsubscribe(Topic.runs, sub)

    async def _ingest_safe(self, run_id: str) -> None:
        async with self._sem:
            await self._episodic.ingest(run_id)
