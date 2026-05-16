"""Safe rule action executor — env whitelist, shlex, timeout, deny list."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import shlex

from agent.config import ENV_WHITELIST as _ENV_WHITELIST
from agent.schemas import Event, Rule, RuleActionKind

log = logging.getLogger(__name__)

_ACTION_TIMEOUT = 30.0  # seconds per action

# First-token deny list — applies regardless of shell flag.
_RUN_DENY = frozenset(
    {
        "rm",
        "rmdir",
        "dd",
        "mkfs",
        "shutdown",
        "reboot",
        "poweroff",
        "halt",
        "init",
        "kill",
        "killall",
        "pkill",
        "sudo",
        "su",
        "doas",
    }
)


def _safe_env(base_env: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in base_env.items() if k in _ENV_WHITELIST}


def match_event(rule: Rule, event: Event) -> bool:
    """Return True if *rule* matches *event*."""
    if rule.on != event.kind:
        return False
    m = rule.match

    # Parse event data fields by event type
    parts = event.data.split(",")
    ev_class = ""
    ev_title = ""
    if event.kind.value == "openwindow" and len(parts) >= 4:
        ev_class = parts[2]
        ev_title = ",".join(parts[3:])
    elif event.kind.value == "activewindow" and len(parts) >= 2:
        ev_class = parts[0]
        ev_title = ",".join(parts[1:])
    elif event.kind.value == "closewindow":
        ev_class = parts[0] if parts else ""

    if m.app_class and not fnmatch.fnmatch(ev_class.lower(), m.app_class.lower()):
        return False
    return not (m.title and not fnmatch.fnmatch(ev_title.lower(), m.title.lower()))


async def execute_rule(rule: Rule, event: Event) -> None:
    """Execute all actions for a matched rule, each with a timeout."""
    for action in rule.actions:
        try:
            await asyncio.wait_for(_exec_action(action, event), timeout=_ACTION_TIMEOUT)
        except TimeoutError:
            log.warning(
                "Rule %s/%s timed out after %.0fs: %s %s",
                rule.on.value,
                rule.match.app_class or "*",
                _ACTION_TIMEOUT,
                action.kind,
                action.value,
            )
        except Exception:
            log.exception(
                "Rule %s/%s action %s %s failed",
                rule.on.value,
                rule.match.app_class or "*",
                action.kind,
                action.value,
            )


async def _exec_action(action, event: Event) -> None:
    from agent.tools import hypr

    if action.kind == RuleActionKind.log:
        log.info("[rule] %s", action.value)

    elif action.kind == RuleActionKind.dispatch:
        log.info("[rule] dispatch: %s", action.value)
        await hypr.dispatch(action.value)

    elif action.kind == RuleActionKind.notify:
        log.info("[rule] notify: %s", action.value)
        proc = await asyncio.create_subprocess_exec(
            "notify-send",
            "hyprland-agent",
            action.value,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    elif action.kind == RuleActionKind.run:
        import os

        raw = action.value.strip()
        if not raw:
            return
        try:
            argv = shlex.split(raw)
        except ValueError as exc:
            log.error("[rule] shlex parse error for %r: %s", raw, exc)
            return

        first = argv[0] if argv else ""
        if first in _RUN_DENY:
            log.warning("[rule] blocked denied command: %s", first)
            return

        env = _safe_env(dict(os.environ))
        log.info("[rule] run: %s", argv)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            log.warning("[rule] run exited %d: %s", proc.returncode, err.decode().strip())
