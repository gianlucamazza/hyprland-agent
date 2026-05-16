"""Window allowlist — agent refuses to act on unlisted windows."""

from __future__ import annotations

import fnmatch
import threading
from collections import Counter
from pathlib import Path

import yaml

from agent.schemas import Window

_CONFIG_PATH = Path.home() / ".config" / "hyprland-agent" / "allowlist.yaml"

# Classes always blocked regardless of allowlist
_ALWAYS_DENY = {"1password", "_1password", "keepassxc", "gnome-keyring"}

# Binaries permitted for integration subprocesses when no yaml override exists
_DEFAULT_BINARY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "notify-send",
        "makoctl",
        "fuzzel",
        "wl-copy",
        "wl-paste",
        "grim",
        "slurp",
        "hyprctl",
        "wtype",
        "ydotool",
        "loginctl",
        "foot",
    }
)

# Thread-safe miss counter for AllowlistMiner to drain periodically
_miss_counter: Counter[tuple[str, str]] = Counter()
_miss_lock = threading.Lock()


def drain_misses() -> dict[tuple[str, str], int]:
    """Atomically drain and return the miss counter."""
    with _miss_lock:
        result = dict(_miss_counter)
        _miss_counter.clear()
    return result


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
        with _miss_lock:
            _miss_counter[(window.app_class, window.title)] += 1
        return False

    for rule in rules:
        class_pat = rule.get("class", "*")
        title_pat = rule.get("title", "*")
        if fnmatch.fnmatch(window.app_class.lower(), class_pat.lower()) and fnmatch.fnmatch(
            window.title.lower(), title_pat.lower()
        ):
            return True

    # Miss: record for allowlist mining (skip _ALWAYS_DENY — those are intentional)
    with _miss_lock:
        _miss_counter[(window.app_class, window.title)] += 1
    return False


def is_binary_allowed(name: str) -> bool:
    """Return True if *name* is in the binary allowlist.

    Reads the optional ``binaries:`` list from allowlist.yaml.  Falls back to
    _DEFAULT_BINARY_ALLOWLIST when the key is absent or the file does not exist.
    """
    if not _CONFIG_PATH.exists():
        return name in _DEFAULT_BINARY_ALLOWLIST
    with open(_CONFIG_PATH) as f:
        data = yaml.safe_load(f) or {}
    configured = data.get("binaries")
    if configured is None:
        return name in _DEFAULT_BINARY_ALLOWLIST
    return name in frozenset(configured)


def create_default_config() -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _CONFIG_PATH.exists():
        return
    # Deny-all default — edit this file to allow specific windows.
    # Example entry: {class: foot, title: "*"}
    example: dict[str, list] = {"allow": []}
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(example, f, default_flow_style=False)
