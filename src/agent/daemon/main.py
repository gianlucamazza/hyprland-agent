"""Daemon entry point — asyncio.TaskGroup root with graceful shutdown."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from agent.daemon.server import serve
from agent.daemon.state import AppState
from agent.daemon.watcher_service import load_rules, run_watcher
from agent.ipc.constants import SOCKET_PATH
from agent.safety import killswitch

log = logging.getLogger(__name__)

_KILLSWITCH_POLL = 0.1  # seconds


async def _killswitch_poller(state: AppState, shutdown: asyncio.Event) -> None:
    """Cancel active runs when kill-switch flag is detected, then auto-disarm.

    Edge-triggered: the flag is consumed by disarm(), so a stale flag never
    produces log spam.
    """
    while not shutdown.is_set():
        if killswitch.is_stopped():
            log.warning("Kill switch detected — cancelling active runs")
            for run_id in await state.executor.active_run_ids():
                await state.executor.cancel(run_id)
            killswitch.disarm()
        await asyncio.sleep(_KILLSWITCH_POLL)


async def run(socket_path: Path = SOCKET_PATH) -> None:
    """Start the daemon and block until SIGTERM/SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    state = AppState()
    await state.open()

    from agent.daemon.log_publisher import install as _install_log

    _install_log(state.pubsub, asyncio.get_running_loop())

    state.rules = await load_rules()

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        log.info("Shutdown signal received")
        shutdown.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    log.info("Daemon starting (socket: %s)", socket_path)

    server_task = asyncio.create_task(serve(state, socket_path))
    watcher_task = asyncio.create_task(run_watcher(state))
    poller_task = asyncio.create_task(_killswitch_poller(state, shutdown))

    # Block until shutdown is requested
    await shutdown.wait()
    log.info("Shutting down — cancelling active runs (grace 5s)…")

    # Cancel active runs gracefully
    for run_id in await state.executor.active_run_ids():
        await state.executor.cancel(run_id)

    try:
        await asyncio.wait_for(state.executor.close(), timeout=5.0)
    except asyncio.TimeoutError:
        log.warning("Some runs did not finish within grace period")

    for task in (server_task, watcher_task, poller_task):
        task.cancel()

    await asyncio.gather(server_task, watcher_task, poller_task, return_exceptions=True)

    await state.close()

    if socket_path.exists():
        socket_path.unlink(missing_ok=True)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.remove_signal_handler(sig)

    log.info("Daemon stopped.")
