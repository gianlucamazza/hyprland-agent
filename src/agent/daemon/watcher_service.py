"""Event-driven rule watcher — runs as an internal daemon service."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from agent.daemon.rule_runner import execute_rule, match_event
from agent.schemas import Rule

log = logging.getLogger(__name__)

_RULES_PATH = Path.home() / ".config" / "hyprland-agent" / "rules.yaml"

_RULES_TEMPLATE = """\
# Hyprland Agent — watch rules
# Reload after editing: agent rules reload
#
# Example:
#   rules:
#     - on: openwindow
#       match:
#         class: spotify
#       actions:
#         - dispatch: "movetoworkspace 9"

rules: []
"""


async def load_rules() -> list[Rule]:
    """Load and validate rules from the YAML config file.

    Creates the template file if it does not exist. Returns [] on parse error.
    """
    if not _RULES_PATH.exists():
        _RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RULES_PATH.write_text(_RULES_TEMPLATE)
        log.info("Created rules template at %s", _RULES_PATH)
        return []

    try:
        data = yaml.safe_load(_RULES_PATH.read_text()) or {}
        raw_rules = data.get("rules") or []
        rules: list[Rule] = []
        for raw in raw_rules:
            try:
                rules.append(Rule.from_dict(raw))
            except Exception as exc:
                log.warning("Skipping invalid rule %r: %s", raw, exc)
        log.info("Loaded %d rule(s) from %s", len(rules), _RULES_PATH)
        return rules
    except Exception as exc:
        log.error("Failed to load rules from %s: %s", _RULES_PATH, exc)
        return []


async def run_watcher(state) -> None:  # type: ignore[type-arg]
    """Subscribe to Hyprland events and execute matching rules.

    Runs until cancelled. Each rule action is isolated: a slow or failing
    action does not block the event loop (wrapped in create_task + timeout
    inside execute_rule).
    """
    from agent.tools.events import subscribe

    log.info("Watcher service started (%d rules)", len(state.rules))
    async for event in subscribe():
        snapshot = list(state.rules)  # atomic read — reload_rules swaps the list
        for rule in snapshot:
            if match_event(rule, event):
                log.debug("Rule matched: %s on %s", rule.on.value, event.data)
                task = asyncio.create_task(execute_rule(rule, event))
                task.add_done_callback(
                    lambda t: (
                        log.error("Rule execution failed: %s", t.exception())
                        if not t.cancelled() and t.exception()
                        else None
                    )
                )
