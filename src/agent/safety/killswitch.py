"""Kill switch — agent stops when ~/.cache/hyprland-agent/STOP exists."""

from __future__ import annotations

from pathlib import Path

_FLAG = Path.home() / ".cache" / "hyprland-agent" / "STOP"


def is_stopped() -> bool:
    return _FLAG.exists()


def arm() -> None:
    _FLAG.parent.mkdir(parents=True, exist_ok=True)
    _FLAG.touch()


def disarm() -> None:
    _FLAG.unlink(missing_ok=True)


def ensure_disarmed() -> None:
    disarm()
    _FLAG.parent.mkdir(parents=True, exist_ok=True)
