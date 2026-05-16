"""Idle/lock integration via D-Bus org.freedesktop.ScreenSaver.

Listens for ActiveChanged signals on the session D-Bus.  On lock (True) it
cancels all active runs; on unlock (False) it re-enables run acceptance.

Uses jeepney (pure-Python D-Bus, no system library dependency).
Falls back to a logged warning if jeepney is unavailable or D-Bus fails.

Alternative zero-code setup (documented in README):
  Add to ~/.config/hypr/hypridle.conf:
    before_sleep_cmd = agent stop
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from agent.integrations import CapabilitySpec
from agent.schemas import Action, ActionResult

if TYPE_CHECKING:
    from agent.daemon.state import AppState

log = logging.getLogger(__name__)

_DBUS_NAME = "org.freedesktop.ScreenSaver"
_DBUS_PATH = "/org/freedesktop/ScreenSaver"
_DBUS_IFACE = "org.freedesktop.ScreenSaver"
_SIGNAL = "ActiveChanged"


class IdleIntegration:
    name = "idle"

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._state: AppState | None = None

    def capabilities(self) -> list[CapabilitySpec]:
        return [
            CapabilitySpec(
                name="desktop.idle_aware",
                action_kinds=(),
                context_keys=("idle_locked",),
            )
        ]

    async def setup(self, state: AppState) -> None:
        try:
            import jeepney  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("jeepney not installed — idle integration degraded") from exc

        self._state = state
        self._task = asyncio.create_task(self._listen(), name="idle-dbus-listener")
        log.debug("Idle integration started D-Bus listener")

    async def teardown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def handle(self, action: Action) -> ActionResult | None:
        return None

    async def _listen(self) -> None:
        try:
            await self._dbus_listen()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Idle D-Bus listener stopped: %s", exc)

    async def _dbus_listen(self) -> None:
        from jeepney import MatchRule, MessageType
        from jeepney.io.asyncio import open_dbus_connection

        conn = await open_dbus_connection(bus="SESSION")
        try:
            rule = MatchRule(
                type=MessageType.signal,
                interface=_DBUS_IFACE,
                member=_SIGNAL,
                path=_DBUS_PATH,
            )
            await conn.send(rule.add())
            while True:
                msg = await conn.receive()
                if msg.header.message_type != MessageType.signal:
                    continue
                if msg.header.fields.get(3) != _SIGNAL:
                    continue
                active: bool = bool(msg.body[0]) if msg.body else False
                await self._on_active_changed(active)
        finally:
            await conn.close()

    async def _on_active_changed(self, active: bool) -> None:
        if self._state is None:
            return
        if active:
            log.info("Screen locked — cancelling active runs")
            run_ids = await self._state.executor.active_run_ids()
            for run_id in run_ids:
                await self._state.executor.cancel(run_id)
        else:
            log.info("Screen unlocked — ready for new runs")
