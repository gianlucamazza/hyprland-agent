"""Allowlist miner: tracks blocked attempts and proposes new allowlist entries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.daemon.store import RunStore

from agent.safety.allowlist import drain_misses

log = logging.getLogger(__name__)

_HIT_THRESHOLD = 5


class AllowlistMiner:
    def __init__(self, store: RunStore) -> None:
        self._store = store

    async def mine(self) -> int:
        """Drain miss counter and upsert proposals. Returns proposals updated count."""
        misses = drain_misses()
        if not misses:
            return 0
        count = 0
        for (app_class, _title), _hits in misses.items():
            try:
                await self._store.upsert_allowlist_proposal(app_class, "*")
                count += 1
            except Exception as exc:
                log.warning("Allowlist proposal upsert failed (%s): %s", app_class, exc)
        log.debug("Allowlist miner: %d proposals updated", count)
        return count
