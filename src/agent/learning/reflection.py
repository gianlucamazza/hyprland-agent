"""Rule-based reflection engine: derives lessons from failed runs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.daemon.store import RunStore

log = logging.getLogger(__name__)

_FAILURE_OUTCOMES = {"failure", "stuck", "errored", "aborted"}


class ReflectionEngine:
    def __init__(self, store: RunStore) -> None:
        self._store = store

    async def reflect(self, run_id: str, outcome: str) -> None:
        """Generate and persist a reflection for *run_id* with *outcome*."""
        try:
            record = await self._store.get_run(run_id)
            if record is None:
                return

            action_kinds = [
                ev.payload.get("kind", "?") for ev in record.events if ev.kind == "action"
            ]
            blocked_count = sum(
                1
                for ev in record.events
                if ev.kind == "action_result" and ev.payload.get("blocked")
            )

            polarity = "negative" if outcome in _FAILURE_OUTCOMES else "positive"
            text = self._derive_text(record.task, outcome, action_kinds, blocked_count)
            if text:
                await self._store.insert_reflection(run_id, polarity, text, "rule-based")
                log.debug("Stored %s reflection for run %s", polarity, run_id)
        except Exception as exc:
            log.warning("Reflection failed for run %s: %s", run_id, exc)

    @staticmethod
    def _derive_text(
        task: str,
        outcome: str,
        action_kinds: list[str],
        blocked_count: int,
    ) -> str | None:
        if blocked_count > 0:
            return (
                f"For task '{task}': action was blocked {blocked_count} time(s). "
                "Verify the target app is in the allowlist before attempting."
            )
        if outcome == "stuck":
            repeated = max(set(action_kinds), key=action_kinds.count) if action_kinds else "unknown"
            return (
                f"For task '{task}': got stuck repeating '{repeated}'. "
                "Try a different strategy or target element."
            )
        if outcome in {"failure", "errored", "aborted"}:
            if action_kinds:
                preview = ", ".join(action_kinds[:3])
                return (
                    f"For task '{task}': failed after {len(action_kinds)} action(s)"
                    f" ({preview}). Consider an alternative approach."
                )
            return f"For task '{task}': failed without completing any action."
        return None
