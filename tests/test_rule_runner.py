"""Tests for rule_runner: event matching, env whitelist, deny list, timeout."""

from __future__ import annotations

import asyncio
import os

import pytest

from agent.daemon.rule_runner import _ENV_WHITELIST, _RUN_DENY, _safe_env, match_event
from agent.schemas import Event, EventKind, EventMatch, Rule, RuleAction, RuleActionKind


def _rule(
    on: EventKind, app_class: str | None = None, title: str | None = None
) -> Rule:
    return Rule(
        on=on,
        match=EventMatch(**{"class": app_class, "title": title}),
        actions=[RuleAction(kind=RuleActionKind.log, value="matched")],
    )


def _event(kind: EventKind, data: str = "") -> Event:
    return Event(kind=kind, data=data, raw="")


# --- match_event ---


def test_match_openwindow_by_class() -> None:
    rule = _rule(EventKind.open_window, app_class="foot")
    event = _event(EventKind.open_window, "0xdeadbeef,1,foot,zsh")
    assert match_event(rule, event)


def test_match_openwindow_wrong_class() -> None:
    rule = _rule(EventKind.open_window, app_class="firefox")
    event = _event(EventKind.open_window, "0xdeadbeef,1,foot,zsh")
    assert not match_event(rule, event)


def test_match_openwindow_glob() -> None:
    rule = _rule(EventKind.open_window, app_class="fire*")
    event = _event(EventKind.open_window, "0x1,1,firefox,Mozilla Firefox")
    assert match_event(rule, event)


def test_match_activewindow_by_class() -> None:
    rule = _rule(EventKind.active_window, app_class="foot")
    event = _event(EventKind.active_window, "foot,zsh")
    assert match_event(rule, event)


def test_match_activewindow_by_title() -> None:
    rule = _rule(EventKind.active_window, title="*vim*")
    event = _event(EventKind.active_window, "foot,nvim — somefile.py")
    assert match_event(rule, event)


def test_no_match_wrong_event_kind() -> None:
    rule = _rule(EventKind.open_window, app_class="foot")
    event = _event(EventKind.active_window, "foot,zsh")
    assert not match_event(rule, event)


def test_match_no_filter_matches_everything() -> None:
    rule = _rule(EventKind.open_window)
    event = _event(EventKind.open_window, "0x1,1,anything,title")
    assert match_event(rule, event)


def test_match_closewindow() -> None:
    rule = _rule(EventKind.close_window, app_class="foot")
    event = _event(EventKind.close_window, "foot")
    assert match_event(rule, event)


# --- env whitelist ---


def test_safe_env_keeps_whitelisted_vars() -> None:
    base = {"PATH": "/usr/bin", "HOME": "/home/user", "OPENAI_API_KEY": "sk-secret"}
    result = _safe_env(base)
    assert "PATH" in result
    assert "HOME" in result
    assert "OPENAI_API_KEY" not in result


def test_safe_env_strips_tokens() -> None:
    base = {
        "ANTHROPIC_API_KEY": "sk-ant-xxx",
        "DRONE_TOKEN": "secret",
        "WAYLAND_DISPLAY": "wayland-1",
        "PATH": "/usr/bin",
    }
    result = _safe_env(base)
    assert "ANTHROPIC_API_KEY" not in result
    assert "DRONE_TOKEN" not in result
    assert "WAYLAND_DISPLAY" in result
    assert "PATH" in result


def test_safe_env_all_whitelist_keys_accepted() -> None:
    base = {k: "value" for k in _ENV_WHITELIST}
    result = _safe_env(base)
    assert set(result.keys()) == _ENV_WHITELIST


# --- deny list ---


def test_deny_list_contains_destructive_commands() -> None:
    for cmd in ("rm", "dd", "mkfs", "shutdown", "reboot", "poweroff", "sudo"):
        assert cmd in _RUN_DENY, f"{cmd!r} not in _RUN_DENY"


# --- execute_rule with log action (no I/O side effects) ---


async def test_execute_rule_log_action() -> None:
    from agent.daemon.rule_runner import execute_rule

    rule = _rule(EventKind.open_window)
    rule.actions[0] = RuleAction(kind=RuleActionKind.log, value="test log")
    event = _event(EventKind.open_window, "0x1,1,foot,zsh")
    # Should not raise
    await execute_rule(rule, event)


async def test_execute_rule_timeout_does_not_propagate() -> None:
    """A rule action that hangs should not propagate an exception — timeout swallows it."""
    from unittest.mock import patch

    from agent.daemon.rule_runner import execute_rule, _ACTION_TIMEOUT

    async def _slow_exec(*_a, **_kw) -> None:
        await asyncio.sleep(_ACTION_TIMEOUT + 10)

    rule = Rule(
        on=EventKind.open_window,
        match=EventMatch(),
        actions=[RuleAction(kind=RuleActionKind.log, value="x")],
    )
    event = _event(EventKind.open_window)

    # Patch _exec_action to simulate a hang
    with patch("agent.daemon.rule_runner._exec_action", side_effect=_slow_exec):
        # Should complete without raising, even though action hangs
        with patch("agent.daemon.rule_runner._ACTION_TIMEOUT", 0.05):
            await execute_rule(rule, event)
