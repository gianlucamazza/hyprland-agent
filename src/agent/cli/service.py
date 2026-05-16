"""Service group: start (daemon), install (systemd unit setup)."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from agent.cli._common import _setup_logging
from agent.paths import SERVICE_UNIT_NAME, SYSTEMD_USER_DIR, resolve_agent_bin

service_app = typer.Typer(help="Daemon lifecycle (start, install systemd unit)")


@service_app.command("start")
def cmd_start(
    socket: Annotated[
        str | None,
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


@service_app.command("install")
def cmd_install() -> None:
    """Install (or upgrade) the hyprland-agent.service systemd user unit."""
    import subprocess
    from pathlib import Path

    old_unit = "hyprland-agent-watch.service"
    systemd_dir = SYSTEMD_USER_DIR
    old_path = systemd_dir / old_unit
    new_path = systemd_dir / SERVICE_UNIT_NAME

    if old_path.exists():
        typer.echo(f"Stopping {old_unit}…")
        subprocess.run(["systemctl", "--user", "stop", old_unit], check=False)
        subprocess.run(["systemctl", "--user", "disable", old_unit], check=False)
        old_path.unlink()
        typer.echo(f"Removed {old_path}")

    agent_bin = resolve_agent_bin()
    unit_content = f"""[Unit]
Description=Hyprland agent daemon
After=graphical-session.target
PartOf=graphical-session.target
ConditionEnvironment=HYPRLAND_INSTANCE_SIGNATURE

[Service]
Type=simple
ExecStart={agent_bin} service start
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
    subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_UNIT_NAME], check=True)
    typer.echo(f"✓ {SERVICE_UNIT_NAME} enabled and started.")
    typer.echo("Run 'agent doctor' to verify.")


@service_app.command("uninstall")
def cmd_uninstall(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")] = False,
) -> None:
    """Remove config, cache, and systemd unit (keeps ~/.cache/fastembed)."""
    import shutil
    import subprocess
    from pathlib import Path

    targets = [
        Path.home() / ".config" / "hyprland-agent",
        Path.home() / ".cache" / "hyprland-agent",
        Path.home() / ".config" / "systemd" / "user" / "hyprland-agent.service",
    ]
    existing = [t for t in targets if t.exists()]
    if not existing:
        typer.echo("Nothing to remove.")
        raise typer.Exit()

    if not yes:
        typer.echo("Will remove:")
        for t in existing:
            typer.echo(f"  {t}")
        typer.echo("  (note: ~/.cache/fastembed is kept — shared with other tools)")
        typer.confirm("Proceed?", abort=True)

    subprocess.run(
        ["systemctl", "--user", "stop", SERVICE_UNIT_NAME], check=False, capture_output=True
    )
    subprocess.run(
        ["systemctl", "--user", "disable", SERVICE_UNIT_NAME], check=False, capture_output=True
    )

    for t in existing:
        if t.is_dir():
            shutil.rmtree(t)
        else:
            t.unlink()
        typer.echo(f"Removed {t}")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
    typer.echo("Uninstall complete.")
