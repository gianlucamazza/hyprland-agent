"""Fuzzel quick-launcher integration.

Server-side helper: exposes recent task history so the fuzzel-agent CLI can
display a task picker.  The client-side fuzzel invocation lives in
src/agent/cli/fuzzel_launcher.py; this module only manages lifecycle state.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from agent.integrations import CapabilitySpec
from agent.schemas import Action, ActionResult

if TYPE_CHECKING:
    from agent.daemon.state import AppState

log = logging.getLogger(__name__)

_BINARY = "fuzzel"


class FuzzelIntegration:
    name = "fuzzel"

    def __init__(self) -> None:
        self._available = False

    def capabilities(self) -> list[CapabilitySpec]:
        return [
            CapabilitySpec(
                name="desktop.quick_launcher",
                action_kinds=(),
                context_keys=(),
            )
        ]

    async def setup(self, state: "AppState") -> None:
        binary = state.config.integrations.binary_overrides.get(_BINARY, _BINARY)
        if not shutil.which(binary):
            raise RuntimeError(f"{binary!r} not found — fuzzel integration degraded")
        self._binary = binary
        self._available = True
        log.debug("Fuzzel integration ready at %s", binary)

    async def teardown(self) -> None:
        self._available = False

    async def handle(self, action: Action) -> ActionResult | None:
        return None  # fuzzel has no server-side action handling
