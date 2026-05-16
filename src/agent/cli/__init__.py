"""CLI entrypoint — thin RPC client over daemon Unix socket."""

from __future__ import annotations

from importlib.metadata import version as _pkg_version
from typing import Annotated

import typer

from agent.cli.config import config_app
from agent.cli.hypr import hypr_app
from agent.cli.learning import learning_app
from agent.cli.memory import memory_app
from agent.cli.primary import (
    cmd_doctor,
    cmd_plan,
    cmd_run,
    cmd_status,
    cmd_stop,
    cmd_tui,
)
from agent.cli.runs import runs_app
from agent.cli.service import service_app
from agent.cli.voice import voice_app

app = typer.Typer(no_args_is_help=True, help="Hyprland desktop agent")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"hyprland-agent {_pkg_version('hyprland-agent')}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version"),
    ] = None,
) -> None:
    pass


# Primary actions (top-level)
app.command("run")(cmd_run)
app.command("plan")(cmd_plan)
app.command("stop")(cmd_stop)
app.command("status")(cmd_status)
app.command("doctor")(cmd_doctor)
app.command("tui")(cmd_tui)

# Groups
app.add_typer(runs_app, name="runs")
app.add_typer(learning_app, name="learning")
app.add_typer(hypr_app, name="hypr")
app.add_typer(memory_app, name="memory")
app.add_typer(config_app, name="config")
app.add_typer(service_app, name="service")
app.add_typer(voice_app, name="voice")
