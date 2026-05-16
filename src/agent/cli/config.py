"""Config group: init-allowlist, bind-killswitch, reload-rules, show."""

from __future__ import annotations

from typing import Annotated

import typer

from agent.cli._common import ExitCode, _run, confirm_or_exit
from agent.ipc.constants import SOCKET_PATH
from agent.paths import HYPR_CONF_PATH, resolve_agent_bin

config_app = typer.Typer(help="Configuration (no daemon required for most commands)")


@config_app.command("init-allowlist")
def cmd_init_allowlist(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Create default allowlist config at ~/.config/hyprland-agent/allowlist.yaml."""
    from agent.config import CONFIG_DIR
    from agent.safety.allowlist import create_default_config

    if (CONFIG_DIR / "allowlist.yaml").exists():
        confirm_or_exit("Overwrite existing allowlist.yaml?", yes)
    create_default_config()
    typer.echo("Created ~/.config/hyprland-agent/allowlist.yaml")
    typer.echo("Edit it to allow the windows the agent should be able to control.")


@config_app.command("bind-killswitch")
def cmd_bind_killswitch(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Rewrite bind even if already present (e.g. bin path changed)"
        ),
    ] = False,
) -> None:
    """Append SUPER+SHIFT+ESC kill-switch bind to ~/.config/hypr/hyprland.conf."""
    conf = HYPR_CONF_PATH
    if not conf.exists():
        typer.echo(f"Not found: {conf}", err=True)
        raise typer.Exit(ExitCode.error)

    agent_bin = resolve_agent_bin()
    bind_line = f"bind = SUPER SHIFT, escape, exec, {agent_bin} stop"

    text = conf.read_text()
    if "agent stop" in text and not force:
        typer.echo("Kill-switch bind already present in hyprland.conf.")
        return

    confirm_or_exit(f"Append kill-switch bind to {conf}?", yes)
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

    from agent.config import CACHE_DIR, CONFIG_DIR

    cfg: dict = {
        "config_dir": str(CONFIG_DIR),
        "cache_dir": str(CACHE_DIR),
        "allowlist_yaml": str(CONFIG_DIR / "allowlist.yaml"),
        "rules_yaml": str(CONFIG_DIR / "rules.yaml"),
        "learned_rules_yaml": str(CONFIG_DIR / "learned_rules.yaml"),
        "runs_db": str(CACHE_DIR / "runs.db"),
        "socket": str(SOCKET_PATH),
    }

    config_yaml = CONFIG_DIR / "config.yaml"
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
