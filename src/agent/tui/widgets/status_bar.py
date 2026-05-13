"""StatusBar — polls daemon_status every 5 seconds."""

from __future__ import annotations

import asyncio

from textual.widgets import Static

from agent.ipc.protocol import RpcMethod


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def start(self) -> None:
        asyncio.create_task(self._refresh())
        self.set_interval(5.0, lambda: asyncio.create_task(self._refresh()))

    async def _refresh(self) -> None:
        conn = self.app._conn  # type: ignore[attr-defined]
        if conn is None:
            return
        try:
            result = await conn.request(RpcMethod.daemon_status)
            v = result.get("version", "?")
            up = float(result.get("uptime_s", 0))
            active = len(result.get("active_runs", []))
            rules = result.get("rules_count", 0)
            mins = int(up // 60)
            secs = int(up % 60)
            self.update(
                f"v{v} │ Up {mins}m{secs:02d}s │ Active: {active} │ Rules: {rules}"
                "  [dim]Ctrl+R new  Ctrl+K stop  Ctrl+L reload  Ctrl+Q quit[/dim]"
            )
        except Exception:
            self.update("[red]Status unavailable[/red]")
