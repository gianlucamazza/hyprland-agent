"""Rate limiting and command sanitization for action execution."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.config import RateLimitConfig

# ---------------------------------------------------------------------------
# Rate limiter — sliding window per ActionKind
# ---------------------------------------------------------------------------

_GUI_KINDS = frozenset({"type_text", "key", "mouse_move", "click", "scroll"})

# Default per-kind limits: (max_actions, window_seconds)
_DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "type_text": (30, 60),
    "key": (30, 60),
    "mouse_move": (30, 60),
    "click": (30, 60),
    "scroll": (30, 60),
    "terminal_command": (10, 60),
}
_FALLBACK_LIMIT: tuple[int, int] = (60, 60)


def _build_limits(cfg: RateLimitConfig | None) -> dict[str, tuple[int, int]]:
    """Build per-kind limits dict from config (or return defaults)."""
    if cfg is None:
        return dict(_DEFAULT_LIMITS)
    gui = cfg.gui_actions_per_minute
    terminal = cfg.terminal_commands_per_minute
    other = cfg.other_actions_per_minute
    limits: dict[str, tuple[int, int]] = {}
    for kind in _GUI_KINDS:
        limits[kind] = (gui, 60)
    limits["terminal_command"] = (terminal, 60)
    limits.setdefault("other", (other, 60))
    return limits


class RateLimiter:
    """Thread-safe sliding-window rate limiter, keyed by action kind."""

    def __init__(
        self,
        limits: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self._limits: dict[str, tuple[int, int]] = limits or _DEFAULT_LIMITS
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg: RateLimitConfig | None = None) -> RateLimiter:
        """Create a RateLimiter from a ``RateLimitConfig``."""
        return cls(limits=_build_limits(cfg))

    def _window(self, kind: str) -> tuple[int, int]:
        limit = self._limits.get(kind)
        if limit is not None:
            return limit
        return self._limits.get("other", _FALLBACK_LIMIT)

    def check(self, kind: str) -> bool:
        """Return True if the action is allowed, False if rate-limited."""
        max_actions, window_s = self._window(kind)
        now = time.monotonic()
        cutoff = now - window_s

        with self._lock:
            bucket = self._buckets.get(kind)
            if bucket is None:
                bucket = deque()
                self._buckets[kind] = bucket

            # Evict timestamps outside the window.
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= max_actions:
                return False

            bucket.append(now)
            return True

    def reconfigure(self, cfg: RateLimitConfig) -> None:
        """Replace limits from config and clear all buckets."""
        with self._lock:
            self._limits = _build_limits(cfg)
            self._buckets.clear()

    def reset(self) -> None:
        """Clear all recorded timestamps."""
        with self._lock:
            self._buckets.clear()


# ---------------------------------------------------------------------------
# Command sanitization
# ---------------------------------------------------------------------------

_DENY_PATTERNS: list[re.Pattern[str]] = [
    # Piping to agent processes.
    re.compile(r"\|\s*(hyprland-agent|agent)\b"),
    # Backgrounding (& at end, optionally preceded by whitespace).
    re.compile(r"&\s*$"),
    # Destructive root-level rm.
    re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/($|\s)"),
    # mkfs on any target.
    re.compile(r"\bmkfs\b"),
    # dd writing to block devices.
    re.compile(r"\bdd\s+.*of=/dev/"),
]


def sanitize_command(command: str) -> tuple[bool, str]:
    """Check a terminal command for dangerous patterns.

    Returns (True, "") if the command appears safe, or
    (False, reason) if a blocked pattern is detected.
    """
    stripped = command.strip()
    for pattern in _DENY_PATTERNS:
        if pattern.search(stripped):
            return False, f"blocked pattern: {pattern.pattern!r}"
    return True, ""
