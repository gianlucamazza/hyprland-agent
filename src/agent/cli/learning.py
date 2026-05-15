"""Learning group: list, show, approve, reject."""

from __future__ import annotations

import json
from typing import Annotated, Optional

import typer

from agent.cli._common import _run, confirm_or_exit
from agent.ipc.constants import SOCKET_PATH

learning_app = typer.Typer(help="Learning inbox: skills, rules, allowlist proposals")


@learning_app.command("list")
def cmd_list(
    kind: Annotated[
        str, typer.Argument(help="Proposal kind: skill | rule | allowlist")
    ] = "skill",
    status: Annotated[
        Optional[str], typer.Option("--status", "-s", help="Filter by status")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List learning proposals (skills, rules, or allowlist entries)."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.learning_list, {"kind": kind, "status": status}
            )
        items = result.get("items", [])
        if not items:
            typer.echo(f"No {kind} proposals found.")
            return
        if json_out:
            typer.echo(json.dumps(items, indent=2, default=str))
        else:
            for item in items:
                typer.echo(json.dumps(item, default=str))

    _run(_do())


@learning_app.command("show")
def cmd_show(
    kind: Annotated[str, typer.Argument(help="skill | rule | allowlist")],
    proposal_id: Annotated[str, typer.Argument(help="Proposal ID")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show detail of a learning proposal."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.learning_explain, {"kind": kind, "id": proposal_id}
            )
        typer.echo(json.dumps(result, indent=2, default=str))

    _run(_do())


@learning_app.command("approve")
def cmd_approve(
    kind: Annotated[str, typer.Argument(help="skill | rule | allowlist")],
    proposal_id: Annotated[str, typer.Argument(help="Proposal ID")],
) -> None:
    """Approve a learning proposal."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.learning_approve, {"kind": kind, "id": proposal_id}
            )
        typer.echo(
            f"Approved {result.get('kind')} {result.get('id')} → {result.get('status')}"
        )

    _run(_do())


@learning_app.command("reject")
def cmd_reject(
    kind: Annotated[str, typer.Argument(help="skill | rule | allowlist")],
    proposal_id: Annotated[str, typer.Argument(help="Proposal ID")],
    reason: Annotated[
        Optional[str], typer.Option("--reason", "-r", help="Rejection reason")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
) -> None:
    """Reject a learning proposal."""
    confirm_or_exit(f"Reject {kind} {proposal_id}?", yes)

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.learning_reject,
                {"kind": kind, "id": proposal_id, "reason": reason},
            )
        typer.echo(f"Rejected {result.get('kind')} {result.get('id')}")

    _run(_do())
