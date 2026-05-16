"""LearningConsumer: single Topic.runs subscriber dispatching to all learners."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from agent.daemon.pubsub import PubSub
from agent.ipc.protocol import Topic

if TYPE_CHECKING:
    from agent.learning.allowlist import AllowlistMiner
    from agent.learning.reflection import ReflectionEngine
    from agent.learning.rules import RuleMiner
    from agent.memory.episodic import EpisodicMemory

log = logging.getLogger(__name__)

_MAX_CONCURRENT = 2


class LearningConsumer:
    """Subscribes to Topic.runs and dispatches run_finished events to learners.

    Periodically runs AllowlistMiner and RuleMiner when configured.
    """

    def __init__(
        self,
        pubsub: PubSub,
        episodic: EpisodicMemory,
        reflection: ReflectionEngine,
        *,
        allowlist_miner: AllowlistMiner | None = None,
        rule_miner: RuleMiner | None = None,
        mining_interval_s: int = 300,
    ) -> None:
        self._pubsub = pubsub
        self._episodic = episodic
        self._reflection = reflection
        self._allowlist_miner = allowlist_miner
        self._rule_miner = rule_miner
        self._mining_interval_s = mining_interval_s
        self._sem = asyncio.Semaphore(_MAX_CONCURRENT)
        self._task: asyncio.Task | None = None
        self._miner_task: asyncio.Task | None = None
        self._bg_tasks: set[asyncio.Task] = set()

    async def open(self) -> None:
        ready = asyncio.Event()
        self._task = asyncio.create_task(self._loop(ready), name="learning-consumer")
        if self._allowlist_miner or self._rule_miner:
            self._miner_task = asyncio.create_task(self._mining_loop(), name="learning-miner")
        await ready.wait()

    async def close(self) -> None:
        for t in (self._task, self._miner_task):
            if t:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
        self._task = None
        self._miner_task = None

    async def _mining_loop(self) -> None:
        """Run mining every ``mining_interval_s`` seconds."""
        while True:
            await asyncio.sleep(self._mining_interval_s)
            if self._allowlist_miner:
                try:
                    c = await self._allowlist_miner.mine()
                    if c:
                        log.info("AllowlistMiner: %d proposals upserted", c)
                except Exception as exc:
                    log.warning("AllowlistMiner failed: %s", exc)
            if self._rule_miner:
                try:
                    c = await self._rule_miner.mine()
                    if c:
                        log.info("RuleMiner: %d rules proposed", c)
                except Exception as exc:
                    log.warning("RuleMiner failed: %s", exc)

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
                t = asyncio.create_task(self._handle(run_id, outcome))
                self._bg_tasks.add(t)
                t.add_done_callback(self._bg_tasks.discard)
        except asyncio.CancelledError:
            raise
        finally:
            await self._pubsub.unsubscribe(Topic.runs, sub)

    async def _handle(self, run_id: str, outcome: str) -> None:
        async with self._sem:
            await self._episodic.ingest(run_id)
            await self._reflection.reflect(run_id, outcome)
