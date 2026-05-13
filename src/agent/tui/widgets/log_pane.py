"""LogPane — streams structured daemon logs from Topic.logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import RichLog

if TYPE_CHECKING:
    from agent.tui.app import LogMsg

_LEVEL_STYLE = {
    "DEBUG": "dim",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red bold",
    "CRITICAL": "red bold underline",
}


class LogPane(RichLog):
    BORDER_TITLE = "Logs"

    def on_log_msg(self, msg: LogMsg) -> None:
        payload = msg.payload
        level = payload.get("level", "INFO")
        name = payload.get("name", "?")
        text = payload.get("msg", "")
        style = _LEVEL_STYLE.get(level, "")
        self.write(f"[{style}]{level:8s}[/{style}] [dim]{name}[/dim] {text}")
