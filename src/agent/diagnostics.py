"""Health checks for agent prerequisites."""

from __future__ import annotations

import grp
import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from rich.console import Console
from rich.table import Table

from agent.config import CONFIG_DIR, AgentConfig
from agent.paths import HYPR_CONF_PATH

ENV_FILE_PATH = CONFIG_DIR / "env"


class Status(StrEnum):
    ok = "OK"
    warn = "WARN"
    fail = "FAIL"


@dataclass
class Check:
    name: str
    status: Status
    message: str
    fix: str = ""


def _read_env_file(path: Path = ENV_FILE_PATH) -> dict[str, str]:
    """Read simple KEY=VALUE EnvironmentFile entries without shell expansion."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _env_value(name: str) -> tuple[str | None, str | None]:
    process_value = os.environ.get(name, "").strip()
    if process_value:
        return process_value, "process env"
    file_value = _read_env_file(ENV_FILE_PATH).get(name, "").strip()
    if file_value:
        return file_value, str(ENV_FILE_PATH)
    return None, None


def _which(cmd: str) -> Check:
    path = shutil.which(cmd)
    if path:
        return Check(cmd, Status.ok, path)
    return Check(cmd, Status.fail, "not found", f"sudo pacman -S {cmd}")


def _which_optional(cmd: str, pkg: str) -> Check:
    """Optional binary — WARN if missing, not FAIL."""
    path = shutil.which(cmd)
    if path:
        return Check(cmd, Status.ok, path)
    return Check(cmd, Status.warn, "not found (optional)", f"sudo pacman -S {pkg}")


def _embedder_cache() -> Check:
    cache = Path.home() / ".cache" / "fastembed"
    if not cache.exists():
        return Check(
            "embedder cache",
            Status.warn,
            "~/.cache/fastembed not found — will download ~1.3 GB on first embed",
            "Set memory.enabled: false in config.yaml to skip",
        )
    # Calculate total size
    total = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file())
    mb = total / (1024 * 1024)
    return Check("embedder cache", Status.ok, f"~/.cache/fastembed ({mb:.0f} MB)")


def _ydotoold_active() -> Check:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "ydotool.service"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() == "active":
        return Check("ydotoold", Status.ok, "running")
    return Check(
        "ydotoold",
        Status.fail,
        result.stdout.strip(),
        "systemctl --user enable --now ydotool.service",
    )


def _uinput_group() -> Check:
    try:
        groups = [g.gr_name for g in grp.getgrall() if os.getlogin() in g.gr_mem]
        primary = grp.getgrgid(os.getgid()).gr_name
        all_groups = [primary] + groups
    except Exception:
        all_groups = []

    if "input" in all_groups:
        return Check("group:input", Status.ok, "member")
    return Check(
        "group:input",
        Status.fail,
        "not a member",
        "sudo usermod -aG input $USER  # then re-login",
    )


def _uinput_writable() -> Check:
    path = "/dev/uinput"
    if os.access(path, os.W_OK):
        return Check("/dev/uinput", Status.ok, "writable")
    # Could be a group-propagation issue (need new session)
    return Check(
        "/dev/uinput",
        Status.warn,
        "not writable in this session",
        "Re-login or use: newgrp input",
    )


def _hyprland_env() -> Check:
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if sig:
        return Check("HYPRLAND_INSTANCE_SIGNATURE", Status.ok, sig[:20] + "…")
    return Check(
        "HYPRLAND_INSTANCE_SIGNATURE",
        Status.fail,
        "not set — not running inside Hyprland?",
    )


def _anthropic_key(config: AgentConfig | None = None) -> Check:
    if config is None:
        from agent.config import ConfigError, load_config

        try:
            config = load_config()
        except ConfigError:
            return Check("ANTHROPIC_API_KEY", Status.warn, "skipped due to invalid provider config")
    if not config.brain.is_enabled("claude"):
        return Check("ANTHROPIC_API_KEY", Status.warn, "disabled by provider config")
    value, source = _env_value("ANTHROPIC_API_KEY")
    if not value:
        status = Status.fail if "claude" in config.brain.auto_order else Status.warn
        return Check(
            "ANTHROPIC_API_KEY",
            status,
            "not set",
            "Export ANTHROPIC_API_KEY in ~/.config/hyprland-agent/env",
        )
    return Check("ANTHROPIC_API_KEY", Status.ok, f"set in {source}")


def _anthropic_model(config: AgentConfig | None = None) -> Check:
    if config is None:
        from agent.config import ConfigError, load_config

        try:
            config = load_config()
        except ConfigError:
            return Check("ANTHROPIC_MODEL", Status.warn, "skipped due to invalid provider config")
    if not config.brain.is_enabled("claude"):
        return Check("ANTHROPIC_MODEL", Status.warn, "disabled by provider config")

    model, source = _env_value("ANTHROPIC_MODEL")
    model = model or "claude-opus-4-7"
    suffix = f" from {source}" if source else ""
    if model == "claude-opus-4-7":
        return Check(
            "ANTHROPIC_MODEL",
            Status.ok,
            f"{model} (primary: reliable computer-use){suffix}",
        )
    if model.startswith("claude-sonnet-"):
        return Check(
            "ANTHROPIC_MODEL",
            Status.warn,
            f"{model} (lower-cost fallback){suffix}",
        )
    return Check("ANTHROPIC_MODEL", Status.warn, f"{model} (custom Claude model){suffix}")


def _provider_checks(config: AgentConfig | None = None) -> list[Check]:
    from agent.brain.openai_brain import PROVIDERS

    if config is None:
        from agent.config import ConfigError, load_config

        try:
            config = load_config()
        except ConfigError:
            return [
                Check(
                    "provider credentials",
                    Status.warn,
                    "skipped due to invalid provider config",
                )
            ]
    out: list[Check] = []
    for provider_key, cfg in PROVIDERS.items():
        if not config.brain.is_enabled(provider_key):
            out.append(Check(cfg.key_env, Status.warn, "disabled by provider config"))
            continue
        _, key_source = _env_value(cfg.key_env)
        model, model_source = _env_value(cfg.model_env)
        model = model or cfg.default_model
        if key_source:
            out.append(Check(cfg.key_env, Status.ok, f"set in {key_source}"))
            model_msg = f"{model} from {model_source}" if model_source else model
            out.append(Check(cfg.model_env, Status.ok, model_msg))
        else:
            out.append(Check(cfg.key_env, Status.warn, f"not set — {cfg.name} brain unavailable"))
    return out


def _brain_config_checks(
    config: AgentConfig | None = None, config_error: str | None = None
) -> list[Check]:
    if config is None and config_error is None:
        from agent.config import ConfigError, load_config

        try:
            config = load_config()
        except ConfigError as exc:
            config_error = str(exc)

    if config_error is not None:
        return [
            Check(
                "provider config",
                Status.fail,
                config_error,
                "Edit ~/.config/hyprland-agent/config.yaml",
            )
        ]

    assert config is not None
    enabled = [name for name in config.brain.auto_order if config.brain.is_enabled(name)]
    config_message = (
        str(config.path) if config.path.exists() else f"defaults; {config.path} not found"
    )
    return [
        Check("provider config", Status.ok, config_message),
        Check("brain.default", Status.ok, config.brain.default),
        Check("brain.auto_order", Status.ok, ", ".join(config.brain.auto_order)),
        Check(
            "brain.enabled",
            Status.ok if enabled else Status.fail,
            ", ".join(enabled) or "no providers enabled",
            "Enable at least one provider in config.yaml" if not enabled else "",
        ),
    ]


def _allowlist() -> Check:
    path = CONFIG_DIR / "allowlist.yaml"
    if path.exists():
        return Check("allowlist.yaml", Status.ok, str(path))
    return Check(
        "allowlist.yaml",
        Status.warn,
        "not found — agent will block all actions",
        "Run: agent config init-allowlist",
    )


def _killswitch_bind() -> Check:
    conf = HYPR_CONF_PATH
    if not conf.exists():
        return Check("killswitch hotkey", Status.warn, "hyprland.conf not found")
    text = conf.read_text()
    if "agent stop" in text:
        return Check("killswitch hotkey", Status.ok, "SUPER+SHIFT+ESC bound")
    return Check(
        "killswitch hotkey",
        Status.warn,
        "not configured",
        "Run: agent config bind-killswitch",
    )


def _daemon_socket() -> Check:
    from agent.ipc.constants import SOCKET_PATH

    if SOCKET_PATH.exists():
        return Check("daemon socket", Status.ok, str(SOCKET_PATH))
    return Check(
        "daemon socket",
        Status.warn,
        "socket not found — daemon not running",
        "systemctl --user start hyprland-agent",
    )


def run_all() -> list[Check]:
    from agent.config import ConfigError, load_config

    try:
        _config: AgentConfig | None = load_config()
        _config_error: str | None = None
    except ConfigError as exc:
        _config = None
        _config_error = str(exc)

    return [
        _which("wtype"),
        _which("ydotool"),
        _which("grim"),
        _which("wl-copy"),
        _which("wl-paste"),
        _ydotoold_active(),
        _uinput_group(),
        _uinput_writable(),
        _hyprland_env(),
        *_brain_config_checks(_config, _config_error),
        _anthropic_key(_config),
        _anthropic_model(_config),
        *_provider_checks(_config),
        _allowlist(),
        _killswitch_bind(),
        _daemon_socket(),
        # Optional integrations
        _which_optional("notify-send", "libnotify"),
        _which_optional("fuzzel", "fuzzel"),
        _which_optional("waybar", "waybar"),
        _embedder_cache(),
    ]


def print_report(checks: list[Check]) -> bool:
    """Print rich table. Returns True if all critical checks pass."""
    console = Console()
    table = Table(title="Agent Doctor", show_header=True, header_style="bold")
    table.add_column("Check", style="dim")
    table.add_column("Status", width=6, no_wrap=True)
    table.add_column("Details")
    table.add_column("Fix")

    colors = {Status.ok: "green", Status.warn: "yellow", Status.fail: "red"}
    any_fail = False

    for c in checks:
        color = colors[c.status]
        table.add_row(c.name, f"[{color}]{c.status.value}[/{color}]", c.message, c.fix)
        if c.status == Status.fail:
            any_fail = True

    console.print(table)
    return not any_fail
