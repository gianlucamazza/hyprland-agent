"""Health checks for agent prerequisites."""

from __future__ import annotations

import grp
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.table import Table


class Status(str, Enum):
    ok = "OK"
    warn = "WARN"
    fail = "FAIL"


@dataclass
class Check:
    name: str
    status: Status
    message: str
    fix: str = ""


def _which(cmd: str) -> Check:
    path = shutil.which(cmd)
    if path:
        return Check(cmd, Status.ok, path)
    return Check(cmd, Status.fail, "not found", f"sudo pacman -S {cmd}")


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


def _oauth_creds() -> Check:
    from agent.config import ConfigError, load_config

    try:
        config = load_config()
    except ConfigError:
        return Check("Claude OAuth", Status.warn, "skipped due to invalid provider config")
    if not config.brain.is_enabled("claude"):
        return Check("Claude OAuth", Status.warn, "disabled by provider config")

    path = Path.home() / ".claude" / ".credentials.json"
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip():
        return Check("Claude OAuth", Status.ok, "CLAUDE_CODE_OAUTH_TOKEN set")
    if not path.exists():
        status = Status.fail if "claude" in config.brain.auto_order else Status.warn
        return Check(
            "Claude OAuth",
            status,
            "~/.claude/.credentials.json not found",
            "Log in via Claude Code first",
        )
    try:
        data = json.loads(path.read_text())
        oauth = data.get("claudeAiOauth", {})
        token = oauth.get("accessToken", "")
        expires_ms = oauth.get("expiresAt", 0)
        if not token:
            return Check("Claude OAuth", Status.fail, "no accessToken")
        remaining_s = (expires_ms - time.time() * 1000) / 1000
        if remaining_s < 60:
            return Check(
                "Claude OAuth",
                Status.warn,
                "token expires soon or expired — will auto-refresh",
            )
        return Check(
            "Claude OAuth", Status.ok, f"valid (expires in {int(remaining_s)}s)"
        )
    except Exception as exc:
        return Check("Claude OAuth", Status.fail, str(exc))


def _anthropic_model() -> Check:
    from agent.config import ConfigError, load_config

    try:
        config = load_config()
    except ConfigError:
        return Check("ANTHROPIC_MODEL", Status.warn, "skipped due to invalid provider config")
    if not config.brain.is_enabled("claude"):
        return Check("ANTHROPIC_MODEL", Status.warn, "disabled by provider config")

    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
    if model == "claude-opus-4-7":
        return Check(
            "ANTHROPIC_MODEL",
            Status.ok,
            f"{model} (primary: reliable computer-use)",
        )
    if model.startswith("claude-sonnet-"):
        return Check(
            "ANTHROPIC_MODEL",
            Status.warn,
            f"{model} (lower-cost fallback)",
        )
    return Check("ANTHROPIC_MODEL", Status.warn, f"{model} (custom Claude model)")


def _provider_checks() -> list[Check]:
    from agent.config import ConfigError, load_config
    from agent.brain.openai_brain import PROVIDERS

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
    for cfg in PROVIDERS.values():
        provider_key = next(key for key, item in PROVIDERS.items() if item == cfg)
        if not config.brain.is_enabled(provider_key):
            out.append(Check(cfg.key_env, Status.warn, "disabled by provider config"))
            continue
        has_key = bool(os.environ.get(cfg.key_env))
        model = os.environ.get(cfg.model_env, cfg.default_model)
        if has_key:
            out.append(Check(cfg.key_env, Status.ok, "set"))
            out.append(Check(cfg.model_env, Status.ok, model))
        else:
            out.append(
                Check(
                    cfg.key_env, Status.warn, f"not set — {cfg.name} brain unavailable"
                )
            )
    return out


def _brain_config_checks() -> list[Check]:
    from agent.config import ConfigError, load_config

    try:
        config = load_config()
    except ConfigError as exc:
        return [
            Check(
                "provider config",
                Status.fail,
                str(exc),
                "Edit ~/.config/hyprland-agent/config.yaml",
            )
        ]

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
    path = Path.home() / ".config" / "hyprland-agent" / "allowlist.yaml"
    if path.exists():
        return Check("allowlist.yaml", Status.ok, str(path))
    return Check(
        "allowlist.yaml",
        Status.warn,
        "not found — agent will block all actions",
        "Run: agent config init-allowlist",
    )


def _killswitch_bind() -> Check:
    conf = Path.home() / ".config" / "hypr" / "hyprland.conf"
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
        *_brain_config_checks(),
        _oauth_creds(),
        _anthropic_model(),
        *_provider_checks(),
        _allowlist(),
        _killswitch_bind(),
        _daemon_socket(),
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
