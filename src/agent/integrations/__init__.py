"""Hyprland agent integration framework.

Each integration implements the Integration protocol and declares its
capabilities via CapabilitySpec.  IntegrationRegistry loads them at daemon
startup via Python entry points (group 'hyprland_agent.integrations'), gated
by config.integrations.enabled.

Schema versioning: INTEGRATIONS_API_VERSION mirrors ipc.constants.PROTOCOL_MAJOR.
A mismatch on the major version causes the integration to be skipped.
"""

from __future__ import annotations

import importlib.metadata
import logging
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agent.daemon.state import AppState
    from agent.schemas import Action, ActionResult

log = logging.getLogger(__name__)

INTEGRATIONS_API_VERSION = "1.0"
_ENTRY_POINT_GROUP = "hyprland_agent.integrations"


@dataclass(frozen=True)
class CapabilitySpec:
    """What an integration contributes to the agent."""

    name: str
    action_kinds: tuple[str, ...] = ()
    context_keys: tuple[str, ...] = ()
    api_version: str = INTEGRATIONS_API_VERSION


@runtime_checkable
class Integration(Protocol):
    name: str

    def capabilities(self) -> list[CapabilitySpec]: ...

    async def setup(self, state: AppState) -> None: ...

    async def teardown(self) -> None: ...

    async def handle(self, action: Action) -> ActionResult | None:
        """Handle an action.  Return None to pass through to the next handler."""
        ...


def _major(version: str) -> int:
    try:
        return int(version.split(".")[0])
    except (ValueError, IndexError):
        return -1


def _version_ok(spec_version: str) -> bool:
    return _major(spec_version) == _major(INTEGRATIONS_API_VERSION)


class IntegrationRegistry:
    """Loads, owns lifecycle, and dispatches to registered integrations."""

    def __init__(self) -> None:
        self._integrations: list[Integration] = []
        self._status: dict[str, str] = {}  # name → ready|degraded|missing

    async def load(self, state: AppState, enabled: tuple[str, ...] | None = None) -> None:
        """Discover and set up integrations.

        *enabled* filters which entry-point names to load.  None = load all.
        """
        for ep in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP):
            if enabled is not None and ep.name not in enabled:
                continue
            try:
                cls = ep.load()
                integration: Integration = cls()
            except Exception as exc:
                log.warning("Failed to load integration %r: %s", ep.name, exc)
                self._status[ep.name] = "missing"
                continue

            for cap in integration.capabilities():
                if not _version_ok(cap.api_version):
                    log.warning(
                        "Integration %r requires API %s, daemon has %s — skipping",
                        integration.name,
                        cap.api_version,
                        INTEGRATIONS_API_VERSION,
                    )
                    self._status[integration.name] = "missing"
                    break
            else:
                await self._setup_one(integration, state)

    async def _setup_one(self, integration: Integration, state: AppState) -> None:
        try:
            await integration.setup(state)
            self._integrations.append(integration)
            self._status[integration.name] = "ready"
            log.info("Integration loaded: %s", integration.name)
        except Exception as exc:
            log.warning("Integration %r setup failed: %s", integration.name, exc)
            self._status[integration.name] = "degraded"

    async def teardown(self) -> None:
        for integ in reversed(self._integrations):
            try:
                await integ.teardown()
            except Exception as exc:
                log.warning("Integration %r teardown error: %s", integ.name, exc)
        self._integrations.clear()

    async def handle(self, action: Action) -> ActionResult | None:
        """Try each integration in registration order; return first non-None result."""
        for integ in self._integrations:
            try:
                result = await integ.handle(action)
                if result is not None:
                    return result
            except Exception as exc:
                log.error("Integration %r error handling %s: %s", integ.name, action.kind, exc)
        return None

    def status(self) -> dict[str, str]:
        return dict(self._status)

    def capabilities(self) -> list[CapabilitySpec]:
        caps: list[CapabilitySpec] = []
        for integ in self._integrations:
            caps.extend(integ.capabilities())
        return caps

    def probe_binary(self, binary: str, integration_name: str) -> bool:
        """Return True if *binary* is on PATH; log and record degraded otherwise."""
        if shutil.which(binary):
            return True
        log.warning("Integration %r: binary %r not found — degraded", integration_name, binary)
        self._status[integration_name] = "degraded"
        return False
