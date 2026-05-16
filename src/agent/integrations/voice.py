"""Voice integration — skeleton M1.

Handles ActionKind.speak by logging (no TTS engine yet in M1).
Publishes voice state to Topic.voice for other integrations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent.integrations import CapabilitySpec
from agent.schemas import Action, ActionKind, ActionResult

if TYPE_CHECKING:
    from agent.daemon.state import AppState

log = logging.getLogger(__name__)


class VoiceIntegration:
    name = "voice"

    def __init__(self) -> None:
        self._available = False

    def capabilities(self) -> list[CapabilitySpec]:
        return [
            CapabilitySpec(
                name="voice",
                action_kinds=("speak",),
                context_keys=(),
            )
        ]

    async def setup(self, state: AppState) -> None:
        if not state.config.integrations.voice.enabled:
            log.info("Voice integration disabled via config")
            return
        self._available = True
        log.info("Voice integration ready (skeleton M1)")

    async def teardown(self) -> None:
        self._available = False

    async def handle(self, action: Action) -> ActionResult | None:
        if action.kind != ActionKind.speak:
            return None
        if not self._available:
            return ActionResult(kind=action.kind.value, blocked="voice integration not available")
        text = action.params.get("text", "")
        log.info("speak requested (M1 skeleton): %s", text)
        return ActionResult(kind=action.kind.value)
