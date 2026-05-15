"""WorldContext — live snapshot of Hyprland environment for brain context."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorldSnapshot:
    active_window_class: str | None
    active_window_title: str | None
    active_workspace_id: int | None
    monitor_width: int
    monitor_height: int
    window_count: int
    timestamp: float
    integrations: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_window_class": self.active_window_class,
            "active_window_title": self.active_window_title,
            "active_workspace_id": self.active_workspace_id,
            "monitor_width": self.monitor_width,
            "monitor_height": self.monitor_height,
            "window_count": self.window_count,
            "timestamp": self.timestamp,
            "integrations": self.integrations,
        }

    def render_for_prompt(self) -> str:
        if not self.active_window_class and not self.active_window_title:
            return ""
        lines = ["## Desktop context"]
        if self.active_window_class:
            lines.append(
                f"Active window: {self.active_window_class} — {self.active_window_title or '?'}"
            )
        if self.active_workspace_id is not None:
            lines.append(f"Workspace: {self.active_workspace_id}")
        lines.append(
            f"Display: {self.monitor_width}×{self.monitor_height}  |  Open windows: {self.window_count}"
        )
        ready = [n for n, s in self.integrations.items() if s == "ready"]
        if ready:
            lines.append(f"Integrations available: {', '.join(sorted(ready))}")
        return "\n".join(lines)


async def snapshot(
    active_window: Any | None,
    monitor_width: int,
    monitor_height: int,
    windows: list[Any],
) -> WorldSnapshot:
    """Build a WorldSnapshot from already-fetched Hyprland data (no extra IPC calls)."""
    return WorldSnapshot(
        active_window_class=active_window.app_class if active_window else None,
        active_window_title=active_window.title if active_window else None,
        active_workspace_id=active_window.workspace_id if active_window else None,
        monitor_width=monitor_width,
        monitor_height=monitor_height,
        window_count=len(windows),
        timestamp=time.time(),
    )
