"""Service group: start (daemon), install (systemd unit setup)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

from agent.cli._common import _setup_logging

service_app = typer.Typer(help="Daemon lifecycle (start, install systemd unit)")


@service_app.command("start")
def cmd_start(
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


@service_app.command("install")
def cmd_install() -> None:
    """Install (or upgrade) the hyprland-agent.service systemd user unit."""
    import shutil
    import subprocess
    from pathlib import Path

    old_unit = "hyprland-agent-watch.service"
    new_unit = "hyprland-agent.service"
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    old_path = systemd_dir / old_unit
    new_path = systemd_dir / new_unit

    if old_path.exists():
        typer.echo(f"Stopping {old_unit}…")
        subprocess.run(["systemctl", "--user", "stop", old_unit], check=False)
        subprocess.run(["systemctl", "--user", "disable", old_unit], check=False)
        old_path.unlink()
        typer.echo(f"Removed {old_path}")

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
    subprocess.run(["systemctl", "--user", "enable", "--now", new_unit], check=True)
    typer.echo(f"✓ {new_unit} enabled and started.")
    typer.echo("Run 'agent doctor' to verify.")
