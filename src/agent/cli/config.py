"""Config group: init-allowlist, bind-killswitch, reload-rules, show."""

from __future__ import annotations

from typing import Annotated

import typer

from agent.cli._common import ExitCode, _run
from agent.ipc.constants import SOCKET_PATH

config_app = typer.Typer(help="Configuration (no daemon required for most commands)")


@config_app.command("init-allowlist")
def cmd_init_allowlist() -> None:
    """Create default allowlist config at ~/.config/hyprland-agent/allowlist.yaml."""
    from agent.safety.allowlist import create_default_config

    create_default_config()
    typer.echo("Created ~/.config/hyprland-agent/allowlist.yaml")
    typer.echo("Edit it to allow the windows the agent should be able to control.")


@config_app.command("bind-killswitch")
def cmd_bind_killswitch() -> None:
    """Append SUPER+SHIFT+ESC kill-switch bind to ~/.config/hypr/hyprland.conf."""
    import shutil
    from pathlib import Path

    conf = Path.home() / ".config" / "hypr" / "hyprland.conf"
    if not conf.exists():
        typer.echo(f"Not found: {conf}", err=True)
        raise typer.Exit(ExitCode.error)

    local_agent = Path.home() / ".local" / "bin" / "agent"
    agent_bin = str(local_agent if local_agent.exists() else shutil.which("agent") or "agent")
    bind_line = f"bind = SUPER SHIFT, escape, exec, {agent_bin} stop"

    text = conf.read_text()
    if "agent stop" in text:
        typer.echo("Kill-switch bind already present in hyprland.conf.")
        return

    with open(conf, "a") as f:
        f.write(f"\n# Hyprland agent kill switch (SUPER+SHIFT+ESC)\n{bind_line}\n")

    typer.echo(f"Added to {conf}:\n  {bind_line}")
    typer.echo("Run `hyprctl reload` to activate.")


@config_app.command("reload-rules")
def cmd_reload_rules() -> None:
    """Tell the daemon to reload rules.yaml and learned_rules.yaml."""

    async def _do() -> None:
        from agent.client.connection import connect
        from agent.ipc.protocol import RpcMethod

        async with connect(SOCKET_PATH) as c:
            result = await c.request(RpcMethod.reload_rules)
        typer.echo(f"Reloaded {result.get('rules_count', 0)} rule(s).")

    _run(_do())


@config_app.command("show")
def cmd_show(
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show effective configuration (config.yaml + paths)."""
    import json
    from pathlib import Path

    config_dir = Path.home() / ".config" / "hyprland-agent"
    cache_dir = Path.home() / ".cache" / "hyprland-agent"

    cfg: dict = {
        "config_dir": str(config_dir),
        "cache_dir": str(cache_dir),
        "allowlist_yaml": str(config_dir / "allowlist.yaml"),
        "rules_yaml": str(config_dir / "rules.yaml"),
        "learned_rules_yaml": str(config_dir / "learned_rules.yaml"),
        "runs_db": str(cache_dir / "runs.db"),
        "socket": str(SOCKET_PATH),
    }

    config_yaml = config_dir / "config.yaml"
    if config_yaml.exists():
        try:
            import yaml

            with open(config_yaml) as f:
                cfg["config_yaml"] = yaml.safe_load(f)
        except Exception:
            cfg["config_yaml"] = f"(parse error: {config_yaml})"
    else:
        cfg["config_yaml"] = None

    if json_out:
        typer.echo(json.dumps(cfg, indent=2, default=str))
    else:
        for k, v in cfg.items():
            if isinstance(v, dict):
                typer.echo(f"{k}:")
                typer.echo(json.dumps(v, indent=2))
            else:
                typer.echo(f"{k}: {v}")
