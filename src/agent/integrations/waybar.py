"""Waybar status indicator integration.

Subscribes to Topic.runs and publishes run state changes to an internal
asyncio.Queue consumed by the agent-waybar CLI process (waybar_module.py).

This integration itself does NOT spawn processes — it just ensures run events
are available via state.pubsub (which already produces them via RunExecutor).
The rendering happens in src/agent/cli/waybar_module.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent.integrations import CapabilitySpec
from agent.schemas import Action, ActionResult

if TYPE_CHECKING:
    from agent.daemon.state import AppState

log = logging.getLogger(__name__)


class WaybarIntegration:
    name = "waybar"

    def capabilities(self) -> list[CapabilitySpec]:
        return [
            CapabilitySpec(
                name="desktop.status_indicator",
                action_kinds=(),
                context_keys=("run_status",),
            )
        ]

    async def setup(self, state: "AppState") -> None:
        # No binary or process needed server-side; agent-waybar opens its own
        # RPC connection and subscribes to Topic.runs directly.
        log.debug("Waybar integration ready (client-driven)")

    async def teardown(self) -> None:
        pass

    async def handle(self, action: Action) -> ActionResult | None:
        return None  # waybar has no server-side action handling
