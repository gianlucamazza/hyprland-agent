"""In-process pub/sub bus with per-topic drop policies."""

from __future__ import annotations

import asyncio
import contextlib
from enum import StrEnum
from typing import Any

from agent.ipc.protocol import Topic


class DropPolicy(StrEnum):
    drop_oldest = "drop_oldest"
    disconnect = "disconnect"


_TOPIC_CONFIG: dict[Topic, tuple[int, DropPolicy]] = {
    Topic.runs: (0, DropPolicy.disconnect),  # unbounded, strict
    Topic.hypr_events: (256, DropPolicy.drop_oldest),
    Topic.logs: (1024, DropPolicy.drop_oldest),
}

_GRACE_SECONDS = 5.0  # time before disconnecting a slow `runs` subscriber


class Subscriber:
    def __init__(self, topic: Topic) -> None:
        capacity, self._policy = _TOPIC_CONFIG[topic]
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=capacity)
        self._disconnected = asyncio.Event()

    @property
    def is_disconnected(self) -> bool:
        return self._disconnected.is_set()

    def disconnect(self) -> None:
        self._disconnected.set()

    def put_nowait(self, payload: dict[str, Any]) -> None:
        if self._disconnected.is_set():
            return
        if self._policy == DropPolicy.drop_oldest:
            try:
                self.queue.put_nowait(payload)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    self.queue.get_nowait()
                self.queue.put_nowait(payload)
        else:
            # disconnect policy — mark for removal; caller handles disconnect
            try:
                self.queue.put_nowait(payload)
            except asyncio.QueueFull:
                self._disconnected.set()


class PubSub:
    def __init__(self) -> None:
        self._subs: dict[Topic, list[Subscriber]] = {t: [] for t in Topic}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: Topic) -> Subscriber:
        sub = Subscriber(topic)
        async with self._lock:
            self._subs[topic].append(sub)
        return sub

    async def unsubscribe(self, topic: Topic, sub: Subscriber) -> None:
        async with self._lock:
            with contextlib.suppress(ValueError):
                self._subs[topic].remove(sub)

    async def publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        async with self._lock:
            subs = list(self._subs[topic])
        dead: list[Subscriber] = []
        for sub in subs:
            sub.put_nowait(payload)
            if sub.is_disconnected:
                dead.append(sub)
        if dead:
            async with self._lock:
                for sub in dead:
                    with contextlib.suppress(ValueError):
                        self._subs[topic].remove(sub)

    async def subscriber_count(self, topic: Topic) -> int:
        async with self._lock:
            return len(self._subs[topic])
