"""Logging handler that forwards agent log records to Topic.logs via pubsub."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from agent.ipc.protocol import Topic

if TYPE_CHECKING:
    from agent.daemon.pubsub import PubSub


class PubSubLogHandler(logging.Handler):
    """Forward agent log records (INFO+) to the daemon pubsub Topic.logs bus.

    Thread-safe: uses run_coroutine_threadsafe so it works whether the logging
    call comes from the event-loop thread or an executor thread.
    """

    def __init__(self, pubsub: PubSub, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._pubsub = pubsub
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "ts": record.created,
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
            asyncio.run_coroutine_threadsafe(
                self._pubsub.publish(Topic.logs, payload),
                self._loop,
            )
        except Exception:
            self.handleError(record)


def install(pubsub: PubSub, loop: asyncio.AbstractEventLoop) -> PubSubLogHandler:
    """Attach a PubSubLogHandler to the root agent logger and return it."""
    handler = PubSubLogHandler(pubsub, loop)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("agent").addHandler(handler)
    return handler
