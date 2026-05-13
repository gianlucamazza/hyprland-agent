"""Window allowlist — agent refuses to act on unlisted windows."""

from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

from agent.schemas import Window

_CONFIG_PATH = Path.home() / ".config" / "hyprland-agent" / "allowlist.yaml"

# Classes always blocked regardless of allowlist
_ALWAYS_DENY = {"1password", "_1password", "keepassxc", "gnome-keyring"}


def _load_rules() -> list[dict]:
    if not _CONFIG_PATH.exists():
        return []
    with open(_CONFIG_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("allow", [])


def is_allowed(window: Window) -> bool:
    if window.app_class.lower() in _ALWAYS_DENY:
        return False

    rules = _load_rules()
    if not rules:
        # Empty allowlist = deny all (safe default)
        return False

    for rule in rules:
        class_pat = rule.get("class", "*")
        title_pat = rule.get("title", "*")
        if fnmatch.fnmatch(
            window.app_class.lower(), class_pat.lower()
        ) and fnmatch.fnmatch(window.title.lower(), title_pat.lower()):
            return True
    return False


def create_default_config() -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _CONFIG_PATH.exists():
        return
    example = {
        "allow": [
            {"class": "foot", "title": "*"},
            {"class": "firefox", "title": "*"},
            {"class": "chromium", "title": "*"},
        ]
    }
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(example, f, default_flow_style=False)
