"""Primary top-level commands: run, plan, stop, status, doctor, tui."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from agent.cli._common import ExitCode, _BrainOpt, _run, _setup_logging, confirm_or_exit
from agent.client.errors import DaemonUnavailable
from agent.ipc.constants import SOCKET_PATH


def cmd_run(
    task: Annotated[str, typer.Argument(help="Natural-language task description")],
    brain: _BrainOpt = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Execute a task on the desktop (via daemon)."""
    _setup_logging(verbose)

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.run_task,
                {"task": task, "brain": brain or "auto"},
            )
        if json_out:
            import json

            typer.echo(json.dumps(result))
        else:
            typer.echo(result.get("run_id", ""))

    _run(_do())


def cmd_plan(
    task: Annotated[str, typer.Argument(help="Natural-language task description")],
    brain: _BrainOpt = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Plan actions without executing them."""
    _setup_logging(verbose)

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.plan_task,
                {"task": task, "brain": brain or "auto"},
            )
        if json_out:
            import json

            typer.echo(json.dumps(result))
        else:
            typer.echo(result.get("run_id", ""))

    _run(_do())


def cmd_stop(
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
) -> None:
    """Arm the kill switch (file flag + daemon RPC)."""
    confirm_or_exit("Arm kill switch and stop any running agent?", yes)
    from agent.safety.killswitch import arm

    arm()
    typer.echo("Kill switch armed — running agent will stop at next iteration.")

    async def _notify_daemon() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        try:
            async with connect(SOCKET_PATH) as c:
                await c.request(RpcMethod.arm_killswitch)
        except DaemonUnavailable:
            pass

    asyncio.run(_notify_daemon())


def cmd_status(
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show daemon status."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.daemon_status)
        if json_out:
            import json

            typer.echo(json.dumps(result, default=str))
            return
        active = result.get("active_runs", [])
        typer.echo(f"Version   : {result.get('version', '?')}")
        typer.echo(f"Uptime    : {result.get('uptime_s', 0):.0f}s")
        typer.echo(f"Active    : {len(active)} run(s)")
        typer.echo(f"Rules     : {result.get('rules_count', 0)}")

    _run(_do())


def cmd_doctor(
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check prerequisites and configuration."""
    from agent.diagnostics import run_all

    checks = run_all()
    if json_out:
        import json

        typer.echo(json.dumps([c.__dict__ for c in checks], default=str))
        all_ok = all(c.ok for c in checks)
        raise typer.Exit(ExitCode.ok if all_ok else ExitCode.error)
    from agent.diagnostics import print_report

    ok = print_report(checks)
    raise SystemExit(ExitCode.ok if ok else ExitCode.error)


def cmd_tui() -> None:
    """Open the monitoring TUI."""
    try:
        from agent.tui.app import AgentApp

        AgentApp().run()
    except ImportError as exc:
        typer.echo("TUI not available.", err=True)
        raise typer.Exit(ExitCode.error) from exc
