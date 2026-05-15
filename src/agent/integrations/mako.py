"""Mako notification integration.

Handles ActionKind.notify by calling notify-send with hyprland-agent as app name.
Notification categories: start, progress, done, error, confirm.
The "Stop" action button maps to agent stop via makoctl invoke.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from agent.integrations import CapabilitySpec
from agent.schemas import Action, ActionKind, ActionResult
from agent.tools._proc import run as _proc_run
from agent.tools._proc import safe_env

if TYPE_CHECKING:
    from agent.daemon.state import AppState

log = logging.getLogger(__name__)

_BINARY = "notify-send"
_CATEGORIES = {"start", "progress", "done", "error", "confirm"}


class MakoIntegration:
    name = "mako"

    def __init__(self) -> None:
        self._app_name = "hyprland-agent"
        self._available = False

    def capabilities(self) -> list[CapabilitySpec]:
        return [
            CapabilitySpec(
                name="desktop.notify",
                action_kinds=("notify",),
                context_keys=(),
            )
        ]

    async def setup(self, state: AppState) -> None:
        binary = state.config.integrations.binary_overrides.get(_BINARY, _BINARY)
        if not shutil.which(binary):
            raise RuntimeError(f"{binary!r} not found — mako integration degraded")
        self._app_name = state.config.integrations.mako_app_name
        self._binary = binary
        self._available = True

    async def teardown(self) -> None:
        self._available = False

    async def handle(self, action: Action) -> ActionResult | None:
        if action.kind != ActionKind.notify:
            return None
        if not self._available:
            return None

        p = action.params
        message = str(p.get("message", ""))
        summary = str(p.get("summary", self._app_name))
        category = str(p.get("category", "done"))
        if category not in _CATEGORIES:
            category = "done"
        urgency = "critical" if category in ("error", "confirm") else "normal"

        argv = [
            self._binary,
            "--app-name",
            self._app_name,
            "--category",
            category,
            "--urgency",
            urgency,
            summary,
            message,
        ]
        result = await _proc_run(argv, timeout=5.0, env=safe_env())
        if result.returncode != 0:
            log.warning("notify-send failed: %s", result.stderr.decode())
        return ActionResult(kind=action.kind.value, returncode=result.returncode)
