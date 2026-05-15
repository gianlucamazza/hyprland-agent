"""Tests for PubSubLogHandler."""

from __future__ import annotations

import asyncio
import logging


async def test_log_publisher_delivers_record() -> None:
    from agent.daemon.log_publisher import install
    from agent.daemon.pubsub import PubSub
    from agent.ipc.protocol import Topic

    pubsub = PubSub()
    loop = asyncio.get_running_loop()
    handler = install(pubsub, loop)
    sub = await pubsub.subscribe(Topic.logs)

    logger = logging.getLogger("agent.test_log_publisher")
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("hello from test")

    # give the scheduled coroutine a chance to run
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    payload = sub.queue.get_nowait()
    assert payload["level"] == "INFO"
    assert "hello from test" in payload["msg"]
    assert payload["name"] == "agent.test_log_publisher"

    logger.removeHandler(handler)
    logging.getLogger("agent").removeHandler(handler)
    await pubsub.unsubscribe(Topic.logs, sub)


async def test_log_publisher_filters_debug() -> None:
    """DEBUG records must NOT reach Topic.logs (handler level is INFO)."""
    from agent.daemon.log_publisher import install
    from agent.daemon.pubsub import PubSub
    from agent.ipc.protocol import Topic

    pubsub = PubSub()
    loop = asyncio.get_running_loop()
    handler = install(pubsub, loop)
    sub = await pubsub.subscribe(Topic.logs)

    logger = logging.getLogger("agent.test_log_publisher_debug")
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.debug("should not appear")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert sub.queue.empty()

    logger.removeHandler(handler)
    logging.getLogger("agent").removeHandler(handler)
    await pubsub.unsubscribe(Topic.logs, sub)
