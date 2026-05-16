"""SelfModel — semantic memory: what the agent can do, its limits, its safety constraints."""

from __future__ import annotations

import time
from typing import Any

from agent.config import CACHE_DIR, CONFIG_DIR, DEFAULT_MAX_ITER, DEFAULT_RUN_TIMEOUT
from agent.safety.allowlist import _ALWAYS_DENY
from agent.schemas import ActionKind

_MAX_LOOP = DEFAULT_MAX_ITER
_RUN_TIMEOUT = int(DEFAULT_RUN_TIMEOUT)
_MAX_HOLD_S = 30


class SelfModel:
    """Static introspection: capabilities, limits, safety constraints, active brain."""

    def __init__(self, brain_name: str = "unknown", start_time: float | None = None) -> None:
        self._brain = brain_name
        self._start_time = start_time or time.time()

    def capabilities(self) -> list[str]:
        return [k.value for k in ActionKind]

    def limits(self) -> dict[str, Any]:
        return {
            "max_iterations": _MAX_LOOP,
            "run_timeout_s": _RUN_TIMEOUT,
            "max_hold_s": _MAX_HOLD_S,
        }

    def safety_constraints(self) -> dict[str, Any]:
        allowlist_path = CONFIG_DIR / "allowlist.yaml"
        return {
            "always_blocked_classes": sorted(_ALWAYS_DENY),
            "allowlist_path": str(allowlist_path),
            "allowlist_exists": allowlist_path.exists(),
            "killswitch_file": str(CACHE_DIR / "STOP"),
        }

    def active_brain(self) -> str:
        return self._brain

    def uptime_s(self) -> float:
        return time.time() - self._start_time

    def render_for_prompt(self) -> str:
        limits = self.limits()
        safety = self.safety_constraints()
        caps = ", ".join(self.capabilities())
        always_deny = ", ".join(safety["always_blocked_classes"])
        lines = [
            "## Agent self-model",
            f"Brain: {self._brain}",
            f"Available actions: {caps}",
            f"Loop cap: {limits['max_iterations']} iterations, "
            f"run timeout: {limits['run_timeout_s']}s",
            f"Always-blocked window classes: {always_deny}",
            "Safety: allowlist deny-by-default; destructive dispatches require confirmation; "
            "killswitch stops execution at next action boundary.",
            "",
            "## Operational guidance",
            "When the user names a specific application (e.g. 'apri firefox', 'open vscode'), "
            "launch its binary directly via `terminal_command` "
            "(e.g. `firefox --new-window <url>`, `code <path>`). "
            "Do NOT use generic wrappers like `xdg-open`, `webbrowser.open`, `gnome-open`, "
            "or `kde-open`: those dispatch to the system MIME default and may launch a "
            "different application than the one the user requested.",
        ]
        return "\n".join(lines)
