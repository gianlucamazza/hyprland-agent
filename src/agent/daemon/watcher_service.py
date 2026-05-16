"""Event-driven rule watcher — runs as an internal daemon service."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import yaml

from agent.config import CONFIG_DIR
from agent.daemon.rule_runner import execute_rule, match_event
from agent.schemas import Rule

if TYPE_CHECKING:
    from agent.daemon.state import AppState

log = logging.getLogger(__name__)

_RULES_PATH = CONFIG_DIR / "rules.yaml"
_LEARNED_RULES_PATH = CONFIG_DIR / "learned_rules.yaml"

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
        raw_rules = list(data.get("rules") or [])

        # Merge learned_rules.yaml (approved rules only)
        if _LEARNED_RULES_PATH.exists():
            try:
                learned_data = yaml.safe_load(_LEARNED_RULES_PATH.read_text()) or {}
                raw_rules.extend(learned_data.get("rules") or [])
            except Exception as exc:
                log.warning("Failed to load learned_rules.yaml: %s", exc)

        # Dedup by 'on' + 'match' signature
        seen: set[str] = set()
        deduped: list[dict] = []
        for raw in raw_rules:
            key = str((raw.get("on"), str(raw.get("match", {}))))
            if key not in seen:
                seen.add(key)
                deduped.append(raw)

        rules: list[Rule] = []
        for raw in deduped:
            try:
                rules.append(Rule.from_dict(raw))
            except Exception as exc:
                log.warning("Skipping invalid rule %r: %s", raw, exc)
        log.info("Loaded %d rule(s) (%s + learned)", len(rules), _RULES_PATH)
        return rules
    except Exception as exc:
        log.error("Failed to load rules from %s: %s", _RULES_PATH, exc)
        return []


async def run_watcher(state: AppState) -> None:
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
