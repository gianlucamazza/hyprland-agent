"""RunDetail — shows header + event timeline for the selected run."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog, Static

from agent.ipc.protocol import RpcMethod

if TYPE_CHECKING:
    from agent.client.connection import DaemonConnection
    from agent.tui.app import RunMsg


def _ts(ts: float | None) -> str:
    if not ts:
        return "??:??:??"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


class RunDetail(Widget):
    BORDER_TITLE = "Run detail"
    DEFAULT_CSS = """
    RunDetail {
        layout: vertical;
    }
    RunDetail > #run-header {
        height: 3;
        background: $panel;
        padding: 0 1;
    }
    RunDetail > #run-timeline {
        height: 1fr;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._run_id: str | None = None
        self._bg_tasks: set[asyncio.Task] = set()

    def compose(self) -> ComposeResult:
        yield Static("No run selected", id="run-header")
        yield RichLog(id="run-timeline", highlight=True, markup=True, auto_scroll=True)

    def load(self, run_id: str, conn: DaemonConnection) -> None:
        self._run_id = run_id
        t = asyncio.create_task(self._fetch(run_id, conn))
        self._bg_tasks.add(t)
        t.add_done_callback(self._bg_tasks.discard)

    async def _fetch(self, run_id: str, conn: DaemonConnection) -> None:
        try:
            result = await conn.request(RpcMethod.get_run, {"run_id": run_id})
        except Exception:
            return
        if self._run_id != run_id:
            return  # selection changed while loading
        run: dict[str, Any] = result.get("run", {})
        header = self.query_one("#run-header", Static)
        header.update(
            f"[bold]{run.get('run_id', '')[:8]}[/bold]"
            f"  [italic]{run.get('task', '')}[/italic]\n"
            f"brain=[cyan]{run.get('brain', '?')}[/cyan]"
            f"  status=[yellow]{run.get('status', '?')}[/yellow]"
        )
        timeline = self.query_one("#run-timeline", RichLog)
        timeline.clear()
        for evt in run.get("events", []):
            t = _ts(evt.get("ts"))
            kind = evt.get("kind", "?")
            timeline.write(f"[dim]{t}[/dim]  {kind}")

    def on_run_msg(self, msg: RunMsg) -> None:
        payload = msg.payload
        if payload.get("run_id") != self._run_id:
            return
        t = _ts(payload.get("ts"))
        kind = payload.get("kind", "?")
        self.query_one("#run-timeline", RichLog).write(f"[dim]{t}[/dim]  {kind}")
