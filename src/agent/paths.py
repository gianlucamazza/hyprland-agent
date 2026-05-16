"""Centralized OS paths and binary resolution helpers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "hyprland-agent"
CACHE_DIR = Path.home() / ".cache" / "hyprland-agent"
HYPR_CONF_PATH = Path.home() / ".config" / "hypr" / "hyprland.conf"
SERVICE_UNIT_NAME = "hyprland-agent.service"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"


def runtime_dir() -> Path:
    """Return ``$XDG_RUNTIME_DIR`` falling back to ``/run/user/<uid>``."""
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


def resolve_agent_bin() -> str:
    """Prefer ~/.local/bin/agent, fall back to $PATH lookup, then 'agent'."""
    local = Path.home() / ".local" / "bin" / "agent"
    if local.exists():
        return str(local)
    return shutil.which("agent") or "agent"
