"""Runs group: list, show, tail, cancel, rerun, feedback, analytics."""

from __future__ import annotations

import json
from typing import Annotated, Optional

import typer

from agent.cli._common import ExitCode, _BrainOpt, _run, confirm_or_exit
from agent.ipc.constants import SOCKET_PATH

runs_app = typer.Typer(help="Run history and management")


@runs_app.command("list")
def cmd_list(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Max number of runs")
    ] = 20,
    status: Annotated[
        Optional[str], typer.Option("--status", "-s", help="Filter by status")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List recent agent runs."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.list_runs, {"limit": limit})
        runs = result.get("runs", [])
        if status:
            runs = [r for r in runs if r.get("status") == status]
        if not runs:
            typer.echo("No runs found.")
            return
        if json_out:
            typer.echo(json.dumps(runs, indent=2, default=str))
            return
        for r in runs:
            st = r["status"]
            kind = r.get("kind", "run")
            task = r["task"][:50]
            brain = r["brain"]
            run_id = r["run_id"][:8]
            typer.echo(f"{run_id}  [{kind:4s}]  [{st:10s}]  {brain:8s}  {task}")

    _run(_do())


@runs_app.command("show")
def cmd_show(
    run_id: Annotated[str, typer.Argument(help="Run ID (full or prefix)")],
    reflection: Annotated[
        bool, typer.Option("--reflection", help="Include reflection/lessons")
    ] = False,
    memory: Annotated[
        bool, typer.Option("--memory", help="Include episodic memory context")
    ] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show full detail of a run including action timeline."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.get_run,
                {
                    "run_id": run_id,
                    "include_reflection": reflection,
                    "include_memory": memory,
                },
            )
        typer.echo(json.dumps(result.get("run", result), indent=2, default=str))

    _run(_do())


@runs_app.command("cancel")
def cmd_cancel(
    run_id: Annotated[str, typer.Argument(help="Run ID to cancel")],
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
) -> None:
    """Cancel a specific run (does not arm the global kill switch)."""
    confirm_or_exit(f"Cancel run {run_id[:8]}?", yes)

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.cancel_run, {"run_id": run_id})
        ok = result.get("ok", False)
        if ok:
            typer.echo(f"Cancelled {run_id[:8]}")
        else:
            typer.echo(f"Run {run_id[:8]} not found or already finished.", err=True)
            raise typer.Exit(ExitCode.error)

    _run(_do())


@runs_app.command("rerun")
def cmd_rerun(
    run_id: Annotated[str, typer.Argument(help="Run ID to rerun")],
    brain: _BrainOpt = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Re-execute the task from a previous run."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            # Fetch original run to get task + original brain
            run_result = await c.request(RpcMethod.get_run, {"run_id": run_id})
            run = run_result.get("run", {})
            task = run.get("task")
            if not task:
                typer.echo(f"Run {run_id[:8]} not found.", err=True)
                raise typer.Exit(ExitCode.error)
            chosen_brain = brain or run.get("brain", "auto")
            result = await c.request(
                RpcMethod.run_task,
                {"task": task, "brain": chosen_brain},
            )
        if json_out:
            typer.echo(json.dumps(result))
        else:
            typer.echo(result.get("run_id", ""))

    _run(_do())


@runs_app.command("tail")
def cmd_tail(
    run_id: Annotated[str, typer.Argument(help="Run ID to follow")],
) -> None:
    """Stream live events for a specific run (without opening the full TUI)."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import Topic

        async with connect(SOCKET_PATH) as c:
            await c.subscribe(Topic.runs)
            typer.echo(f"Tailing run {run_id[:8]} (Ctrl+C to stop)...")
            async for _topic, payload in c.events():
                if payload.get("run_id", "").startswith(run_id[:8]):
                    kind = payload.get("kind", "event")
                    msg = payload.get("message", payload.get("status", ""))
                    typer.echo(f"  [{kind}] {msg}")
                    if payload.get("kind") == "run_finished":
                        break

    _run(_do())


@runs_app.command("feedback")
def cmd_feedback(
    run_id: Annotated[str, typer.Argument(help="Run ID to rate")],
    up: Annotated[bool, typer.Option("--up", help="Thumbs up (success)")] = False,
    down: Annotated[bool, typer.Option("--down", help="Thumbs down (failure)")] = False,
    comment: Annotated[
        Optional[str], typer.Option("--comment", "-c", help="Free-text note")
    ] = None,
) -> None:
    """Record explicit feedback for a run."""
    if not up and not down and not comment:
        typer.echo("Specify --up, --down, or --comment.", err=True)
        raise typer.Exit(ExitCode.misuse)
    kind = "thumbs_up" if up else ("thumbs_down" if down else "comment")

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.record_feedback,
                {"run_id": run_id, "kind": kind, "comment": comment},
            )
        typer.echo(
            f"outcome={result.get('outcome', '?')}  feedback_id={result.get('feedback_id', '?')}"
        )

    _run(_do())


@runs_app.command("analytics")
def cmd_analytics(
    days: Annotated[
        int, typer.Option("--days", "-d", help="Lookback window in days")
    ] = 7,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show outcome analytics for recent runs."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.runs_analytics, {"days": days})

        if json_out:
            typer.echo(json.dumps(result, indent=2, default=str))
            return

        total = result.get("total_runs", 0)
        outcomes = result.get("outcomes", {})
        failures = result.get("top_failure_tasks", [])

        typer.echo(f"Last {days} day(s) — {total} run(s) tracked")
        if outcomes:
            typer.echo("\nOutcome distribution:")
            for outcome, count in outcomes.items():
                pct = count * 100 // total if total else 0
                typer.echo(f"  {outcome:10s}: {count:4d}  ({pct}%)")
        if failures:
            typer.echo("\nTop failing tasks:")
            for f in failures[:5]:
                typer.echo(f"  [{f['count']:3d}x] {f['task'][:60]}")

    _run(_do())
