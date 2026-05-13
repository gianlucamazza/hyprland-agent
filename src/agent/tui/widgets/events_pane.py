"""EventsPane — streams live Hyprland events from the daemon."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import RichLog

if TYPE_CHECKING:
    from agent.tui.app import HyprEventMsg


class EventsPane(RichLog):
    BORDER_TITLE = "Hyprland events"

    def on_hypr_event_msg(self, msg: HyprEventMsg) -> None:
        payload = msg.payload
        kind = payload.get("kind", payload.get("event", "?"))
        data = payload.get("data", "")
        self.write(f"[dim]{kind:20s}[/dim] {data}")
