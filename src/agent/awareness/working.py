"""WorkingMemory — run-scoped volatile memory of actions taken so far."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_MAX_ENTRIES = 50


@dataclass
class ActionEntry:
    kind: str
    params: dict[str, Any]
    result_summary: str | None = None


class WorkingMemory:
    """Tracks actions executed in the current run for brain context injection."""

    def __init__(self) -> None:
        self._entries: list[ActionEntry] = []

    def record(
        self, kind: str, params: dict[str, Any], result_summary: str | None = None
    ) -> None:
        self._entries.append(
            ActionEntry(kind=kind, params=params, result_summary=result_summary)
        )
        if len(self._entries) > _MAX_ENTRIES:
            self._entries.pop(0)

    def entries(self) -> list[ActionEntry]:
        return list(self._entries)

    def render(self) -> str:
        if not self._entries:
            return ""
        lines = ["## Actions taken so far in this run"]
        for e in self._entries[-10:]:  # last 10 to keep prompt size bounded
            summary = f" → {e.result_summary}" if e.result_summary else ""
            lines.append(f"- {e.kind}({e.params}){summary}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._entries.clear()
