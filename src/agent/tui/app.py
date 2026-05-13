"""Textual TUI root application — monitoring and control for the agent daemon."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from agent.client.connection import DaemonConnection, connect
from agent.client.errors import DaemonUnavailable
from agent.ipc.constants import SOCKET_PATH
from agent.ipc.protocol import RpcMethod, Topic
from agent.tui.widgets.events_pane import EventsPane
from agent.tui.widgets.log_pane import LogPane
from agent.tui.widgets.run_detail import RunDetail
from agent.tui.widgets.run_list import RunList
from agent.tui.widgets.run_modal import RunModal
from agent.tui.widgets.status_bar import StatusBar


# ── Broadcast messages (posted by AgentApp, handled by child widgets) ─────────


class RunMsg(Message):
    """Payload from Topic.runs broadcast to RunList and RunDetail."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self.payload = payload


class HyprEventMsg(Message):
    """Payload from Topic.hypr_events broadcast to EventsPane."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self.payload = payload


class LogMsg(Message):
    """Payload from Topic.logs broadcast to LogPane."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self.payload = payload


# ── Error screen (daemon unavailable) ─────────────────────────────────────────


class ErrorScreen(Screen):
    BINDINGS = [Binding("ctrl+q", "quit_app", "Quit")]
    DEFAULT_CSS = """
    ErrorScreen {
        align: center middle;
    }
    ErrorScreen > #error-msg {
        width: 60;
        padding: 2 4;
        border: double $error;
        background: $surface;
        text-align: center;
    }
    """

    def __init__(self, socket_path: Path) -> None:
        super().__init__()
        self._socket_path = socket_path

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold red]Daemon not running[/bold red]\n\n"
            "Start with:\n  [italic]systemctl --user start hyprland-agent[/italic]\n\n"
            f"Socket: [dim]{self._socket_path}[/dim]",
            id="error-msg",
        )
        yield Footer()

    def action_quit_app(self) -> None:
        self.app.exit()


# ── Main app ───────────────────────────────────────────────────────────────────


class AgentApp(App[None]):
    """Monitoring and control TUI for the hyprland-agent daemon."""

    TITLE = "Hyprland Agent"
    BINDINGS = [
        Binding("ctrl+r", "new_run", "New run"),
        Binding("ctrl+k", "killswitch", "Stop all"),
        Binding("ctrl+l", "reload_rules", "Reload rules"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    DEFAULT_CSS = """
    AgentApp > #main {
        height: 1fr;
    }
    AgentApp > #main > #left {
        width: 50%;
    }
    AgentApp > #main > #right {
        width: 50%;
    }
    RunList {
        height: 55%;
        border: solid $primary;
    }
    EventsPane {
        height: 45%;
        border: solid $primary;
    }
    RunDetail {
        height: 65%;
        border: solid $primary;
    }
    LogPane {
        height: 35%;
        border: solid $primary;
    }
    """

    def __init__(self, socket_path: Path = SOCKET_PATH) -> None:
        super().__init__()
        self._socket_path = socket_path
        self._conn: DaemonConnection | None = None
        self._stack: AsyncExitStack = AsyncExitStack()
        self._dispatcher_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield RunList()
                yield EventsPane()
            with Vertical(id="right"):
                yield RunDetail()
                yield LogPane()
        yield StatusBar()
        yield Footer()

    async def on_mount(self) -> None:
        try:
            self._conn = await self._stack.enter_async_context(
                connect(self._socket_path)
            )
        except DaemonUnavailable:
            await self.push_screen(ErrorScreen(self._socket_path))
            return

        await self._conn.subscribe(Topic.runs, Topic.hypr_events, Topic.logs)
        self._dispatcher_task = asyncio.create_task(self._event_dispatcher())

        status_bar = self.query_one(StatusBar)
        status_bar.start()

        try:
            await self.query_one(RunList).refresh_runs(self._conn)
        except Exception:
            pass

    async def on_unmount(self) -> None:
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        await self._stack.aclose()

    async def _event_dispatcher(self) -> None:
        """Single reader loop — fans out events to child widgets by topic."""
        assert self._conn is not None
        try:
            async for topic, payload in self._conn.events():
                try:
                    if topic == Topic.runs:
                        self.query_one(RunList).post_message(RunMsg(payload))
                        self.query_one(RunDetail).post_message(RunMsg(payload))
                    elif topic == Topic.hypr_events:
                        self.query_one(EventsPane).post_message(HyprEventMsg(payload))
                    elif topic == Topic.logs:
                        self.query_one(LogPane).post_message(LogMsg(payload))
                except Exception:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    # ── Message handlers ───────────────────────────────────────────────────────

    def on_run_list_run_selected(self, event: RunList.RunSelected) -> None:
        if self._conn is not None:
            self.query_one(RunDetail).load(event.run_id, self._conn)

    # ── Actions (keybindings) ──────────────────────────────────────────────────

    async def action_new_run(self) -> None:
        if self._conn is None:
            self.notify("Daemon not connected", severity="error")
            return

        def _on_dismiss(run_id: str | None) -> None:
            if run_id:
                self.notify(f"Started run {run_id[:8]}")

        await self.push_screen(RunModal(), _on_dismiss)

    async def action_killswitch(self) -> None:
        if self._conn is None:
            return
        try:
            await self._conn.request(RpcMethod.arm_killswitch)
            self.notify("Kill switch armed — active runs stopping", severity="warning")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    async def action_reload_rules(self) -> None:
        if self._conn is None:
            return
        try:
            result = await self._conn.request(RpcMethod.reload_rules)
            n = result.get("rules_count", 0)
            self.notify(f"Reloaded {n} rule(s)")
        except Exception as exc:
            self.notify(str(exc), severity="error")
