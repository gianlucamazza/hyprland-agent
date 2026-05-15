"""CLI entrypoint — runtime commands are RPC clients of the daemon."""

from __future__ import annotations

import asyncio
import sys
from typing import Annotated, Optional

import typer

from agent.client.errors import DaemonUnavailable, RpcError
from agent.ipc.constants import SOCKET_PATH

app = typer.Typer(no_args_is_help=True, help="Hyprland desktop agent")
config_app = typer.Typer(help="Configuration commands (no daemon required)")
rules_app = typer.Typer(help="Rule management")
learning_app = typer.Typer(help="Learning inbox: skills, rules, allowlist proposals")
app.add_typer(config_app, name="config")
app.add_typer(rules_app, name="rules")
app.add_typer(learning_app, name="learning")

_BrainOpt = Annotated[
    Optional[str],
    typer.Option(
        "--brain",
        "-b",
        help="Brain: auto | claude | openai | kimi | groq | together | zai | qwen (default/configurable via config.yaml)",
    ),
]


def _setup_logging(verbose: bool) -> None:
    import logging

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=level)


def _run(coro) -> None:
    """Run *coro* and surface daemon/RPC errors with a clean message."""
    try:
        asyncio.run(coro)
    except DaemonUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    except RpcError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
    except KeyboardInterrupt:
        pass


# ──────────────────────────────────────────────────────────
# Runtime commands (daemon required)
# ──────────────────────────────────────────────────────────


@app.command()
def run(
    task: Annotated[str, typer.Argument(help="Natural-language task description")],
    brain: _BrainOpt = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
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
            typer.echo(result.get("run_id", ""))

    _run(_do())


@app.command(name="plan")
def plan_cmd(
    task: Annotated[str, typer.Argument(help="Natural-language task description")],
    brain: _BrainOpt = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
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
            typer.echo(result.get("run_id", ""))

    _run(_do())


@app.command()
def windows() -> None:
    """List all open windows."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.list_windows)
        for w in result.get("windows", []):
            typer.echo(
                f"{w['address']}  [{w.get('app_class', w.get('class', '?')):20s}]  {w['title']}"
            )

    _run(_do())


@app.command()
def stop() -> None:
    """Arm the kill switch (file flag + daemon RPC)."""
    from agent.safety.killswitch import arm

    arm()  # always create file flag — works even if daemon is down
    typer.echo("Kill switch armed — running agent will stop at next iteration.")

    async def _notify_daemon() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        try:
            async with connect(SOCKET_PATH) as c:
                await c.request(RpcMethod.arm_killswitch)
        except DaemonUnavailable:
            pass  # file flag is sufficient

    asyncio.run(_notify_daemon())


@app.command()
def screenshot(
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


@app.command()
def events() -> None:
    """Stream live Hyprland events from the daemon."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import Topic

        async with connect(SOCKET_PATH) as c:
            await c.subscribe(Topic.hypr_events)
            typer.echo("Listening for Hyprland events (Ctrl+C to stop)...")
            async for topic, payload in c.events():
                kind = payload.get("kind", payload.get("event", "?"))
                data = payload.get("data", "")
                typer.echo(f"{kind:20s} {data}")

    _run(_do())


@app.command(name="list-runs")
def list_runs(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Max number of runs")
    ] = 20,
) -> None:
    """List recent agent runs."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.list_runs, {"limit": limit})
        runs = result.get("runs", [])
        if not runs:
            typer.echo("No runs found.")
            return
        for r in runs:
            status = r["status"]
            kind = r.get("kind", "run")
            task = r["task"][:50]
            brain = r["brain"]
            run_id = r["run_id"][:8]
            typer.echo(f"{run_id}  [{kind:4s}]  [{status:10s}]  {brain:8s}  {task}")

    _run(_do())


@app.command(name="get-run")
def get_run(
    run_id: Annotated[str, typer.Argument(help="Run ID (full or prefix)")],
) -> None:
    """Show full detail of a run including action timeline."""
    import json

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.get_run, {"run_id": run_id})
        typer.echo(json.dumps(result.get("run", {}), indent=2, default=str))

    _run(_do())


@app.command()
def status() -> None:
    """Show daemon status."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.daemon_status)
        active = result.get("active_runs", [])
        typer.echo(f"Version   : {result.get('version', '?')}")
        typer.echo(f"Uptime    : {result.get('uptime_s', 0):.0f}s")
        typer.echo(f"Active    : {len(active)} run(s)")
        typer.echo(f"Rules     : {result.get('rules_count', 0)}")

    _run(_do())


# ──────────────────────────────────────────────────────────
# Daemon management
# ──────────────────────────────────────────────────────────


@app.command()
def daemon(
    socket: Annotated[
        Optional[str],
        typer.Option("--socket", "-s", help="Override socket path"),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Start the agent daemon (long-running server process)."""
    _setup_logging(verbose)
    from pathlib import Path

    from agent.daemon.main import run as _run_daemon

    path = Path(socket) if socket else None
    try:
        if path:
            asyncio.run(_run_daemon(socket_path=path))
        else:
            asyncio.run(_run_daemon())
    except KeyboardInterrupt:
        pass


@app.command(name="migrate-systemd")
def migrate_systemd() -> None:
    """Migrate from hyprland-agent-watch.service to hyprland-agent.service."""
    import shutil
    import subprocess
    from pathlib import Path

    old_unit = "hyprland-agent-watch.service"
    new_unit = "hyprland-agent.service"
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    old_path = systemd_dir / old_unit
    new_path = systemd_dir / new_unit

    # Stop and disable old service
    if old_path.exists():
        typer.echo(f"Stopping {old_unit}…")
        subprocess.run(["systemctl", "--user", "stop", old_unit], check=False)
        subprocess.run(["systemctl", "--user", "disable", old_unit], check=False)
        old_path.unlink()
        typer.echo(f"Removed {old_path}")

    # Write new unit
    local_agent = Path.home() / ".local" / "bin" / "agent"
    agent_bin = str(
        local_agent if local_agent.exists() else shutil.which("agent") or "agent"
    )
    unit_content = f"""[Unit]
Description=Hyprland agent daemon
After=graphical-session.target
PartOf=graphical-session.target
ConditionEnvironment=HYPRLAND_INSTANCE_SIGNATURE

[Service]
Type=simple
ExecStart={agent_bin} daemon
Restart=on-failure
RestartSec=5
Environment=PATH={Path.home()}/.local/bin:/usr/local/bin:/usr/bin
EnvironmentFile=-%h/.config/hyprland-agent/env

[Install]
WantedBy=graphical-session.target
"""
    systemd_dir.mkdir(parents=True, exist_ok=True)
    new_path.write_text(unit_content)
    typer.echo(f"Wrote {new_path}")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", new_unit], check=True)
    typer.echo(f"✓ {new_unit} enabled and started.")
    typer.echo("Run 'agent doctor' to verify.")


@app.command()
def tui() -> None:
    """Open the monitoring TUI (Phase 5)."""
    try:
        from agent.tui.app import AgentApp

        AgentApp().run()
    except ImportError:
        typer.echo("TUI not yet available — Phase 5 pending.", err=True)
        raise typer.Exit(1)


@app.command()
def doctor() -> None:
    """Check prerequisites and configuration."""
    from agent.diagnostics import print_report, run_all

    checks = run_all()
    ok = print_report(checks)
    raise SystemExit(0 if ok else 1)


# ──────────────────────────────────────────────────────────
# agent config sub-commands
# ──────────────────────────────────────────────────────────


@config_app.command(name="init-allowlist")
def init_allowlist() -> None:
    """Create default allowlist config at ~/.config/hyprland-agent/allowlist.yaml."""
    from agent.safety.allowlist import create_default_config

    create_default_config()
    typer.echo("Created ~/.config/hyprland-agent/allowlist.yaml")
    typer.echo("Edit it to allow the windows the agent should be able to control.")


@config_app.command(name="bind-killswitch")
def bind_killswitch() -> None:
    """Append SUPER+SHIFT+ESC kill-switch bind to ~/.config/hypr/hyprland.conf."""
    import shutil
    from pathlib import Path

    conf = Path.home() / ".config" / "hypr" / "hyprland.conf"
    if not conf.exists():
        typer.echo(f"Not found: {conf}", err=True)
        raise typer.Exit(1)

    local_agent = Path.home() / ".local" / "bin" / "agent"
    agent_bin = str(
        local_agent if local_agent.exists() else shutil.which("agent") or "agent"
    )
    bind_line = f"bind = SUPER SHIFT, escape, exec, {agent_bin} stop"

    text = conf.read_text()
    if "agent stop" in text:
        typer.echo("Kill-switch bind already present in hyprland.conf.")
        return

    with open(conf, "a") as f:
        f.write(f"\n# Hyprland agent kill switch (SUPER+SHIFT+ESC)\n{bind_line}\n")

    typer.echo(f"Added to {conf}:\n  {bind_line}")
    typer.echo("Run `hyprctl reload` to activate.")


# ──────────────────────────────────────────────────────────
# agent rules sub-commands
# ──────────────────────────────────────────────────────────


@app.command()
def feedback(
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
        raise typer.Exit(1)
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


@app.command(name="runs-analytics")
def runs_analytics(
    days: Annotated[
        int, typer.Option("--days", "-d", help="Lookback window in days")
    ] = 7,
) -> None:
    """Show outcome analytics for recent runs."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.runs_analytics, {"days": days})

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


@learning_app.command("list")
def learning_list(
    kind: Annotated[
        str, typer.Argument(help="Proposal kind: skill | rule | allowlist")
    ] = "skill",
    status: Annotated[
        Optional[str], typer.Option("--status", "-s", help="Filter by status")
    ] = None,
) -> None:
    """List learning proposals (skills, rules, or allowlist entries)."""
    import json

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
        for item in items:
            typer.echo(json.dumps(item, default=str))

    _run(_do())


@learning_app.command("approve")
def learning_approve(
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
def learning_reject(
    kind: Annotated[str, typer.Argument(help="skill | rule | allowlist")],
    proposal_id: Annotated[str, typer.Argument(help="Proposal ID")],
    reason: Annotated[
        Optional[str], typer.Option("--reason", "-r", help="Rejection reason")
    ] = None,
) -> None:
    """Reject a learning proposal."""

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


@learning_app.command("explain")
def learning_explain(
    kind: Annotated[str, typer.Argument(help="skill | rule | allowlist")],
    proposal_id: Annotated[str, typer.Argument(help="Proposal ID")],
) -> None:
    """Show a detailed explanation of a learning proposal."""
    import json

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(
                RpcMethod.learning_explain, {"kind": kind, "id": proposal_id}
            )
        typer.echo(json.dumps(result, indent=2, default=str))

    _run(_do())


@rules_app.command("reload")
def rules_reload() -> None:
    """Tell the daemon to reload rules.yaml."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.reload_rules)
        typer.echo(f"Reloaded {result.get('rules_count', 0)} rule(s).")

    _run(_do())
