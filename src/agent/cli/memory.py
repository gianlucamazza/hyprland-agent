"""Memory group: search (episodic recall), show (episode by ID)."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from agent.cli._common import ExitCode, _run
from agent.ipc.constants import SOCKET_PATH

memory_app = typer.Typer(help="Episodic memory inspection (read-only)")


@memory_app.command("search")
def cmd_search(
    query: Annotated[str, typer.Argument(help="Free-text query for semantic recall")],
    top_k: Annotated[int, typer.Option("--top-k", "-k", help="Max results")] = 5,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Search episodic memory with a semantic query."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.memory_search, {"query": query, "top_k": top_k})
        episodes = result.get("episodes", [])
        if not episodes:
            typer.echo("No matching episodes found.")
            return
        if json_out:
            typer.echo(json.dumps(episodes, indent=2, default=str))
            return
        for ep in episodes:
            score = ep.get("score", 0)
            ep_id = ep.get("id", "?")[:8]
            task = ep.get("task", "?")[:60]
            status = ep.get("status", "?")
            typer.echo(f"{ep_id}  [{status:10s}]  score={score:.3f}  {task}")

    _run(_do())


@memory_app.command("show")
def cmd_show(
    episode_id: Annotated[str, typer.Argument(help="Episode ID to inspect")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show full detail of a specific episode in episodic memory."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.memory_get, {"episode_id": episode_id})
        episode = result.get("episode")
        if not episode:
            typer.echo(f"Episode {episode_id} not found.", err=True)
            raise typer.Exit(ExitCode.error)
        typer.echo(json.dumps(episode, indent=2, default=str))

    _run(_do())
