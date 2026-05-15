"""Hypr group: windows, events, screenshot."""

from __future__ import annotations

from typing import Annotated

import typer

from agent.cli._common import _run
from agent.ipc.constants import SOCKET_PATH

hypr_app = typer.Typer(help="Hyprland desktop surface (windows, events, screenshot)")


@hypr_app.command("windows")
def cmd_windows(
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List all open windows."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.list_windows)
        if json_out:
            import json

            typer.echo(json.dumps(result.get("windows", []), indent=2))
            return
        for w in result.get("windows", []):
            typer.echo(
                f"{w['address']}  [{w.get('app_class', w.get('class', '?')):20s}]  {w['title']}"
            )

    _run(_do())


@hypr_app.command("events")
def cmd_events(
    filter_kind: Annotated[
        str | None,
        typer.Option("--filter", "-f", help="Filter events by kind prefix"),
    ] = None,
) -> None:
    """Stream live Hyprland events from the daemon."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import Topic

        async with connect(SOCKET_PATH) as c:
            await c.subscribe(Topic.hypr_events)
            typer.echo("Listening for Hyprland events (Ctrl+C to stop)...")
            async for _topic, payload in c.events():
                kind = payload.get("kind", payload.get("event", "?"))
                if filter_kind and not kind.startswith(filter_kind):
                    continue
                data = payload.get("data", "")
                typer.echo(f"{kind:20s} {data}")

    _run(_do())


@hypr_app.command("screenshot")
def cmd_screenshot(
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output PNG path")
    ] = "/tmp/agent-screen.png",
) -> None:
    """Capture the current screen to a file."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.screenshot, {"path": output})
        typer.echo(f"Saved to {result.get('path', output)}")

    _run(_do())
