"""Tests for SelfModel introspection."""

from __future__ import annotations

import time

from agent.introspection.self_model import SelfModel
from agent.schemas import ActionKind


def test_capabilities_contains_all_action_kinds() -> None:
    sm = SelfModel(brain_name="test")
    caps = sm.capabilities()
    for kind in ActionKind:
        assert kind.value in caps


def test_limits_keys() -> None:
    sm = SelfModel()
    limits = sm.limits()
    assert "max_iterations" in limits
    assert "run_timeout_s" in limits
    assert "max_hold_s" in limits
    assert limits["max_iterations"] == 20
    assert limits["run_timeout_s"] == 300


def test_safety_constraints_always_deny() -> None:
    sm = SelfModel()
    safety = sm.safety_constraints()
    denied = safety["always_blocked_classes"]
    assert "1password" in denied
    assert "keepassxc" in denied


def test_active_brain() -> None:
    sm = SelfModel(brain_name="ClaudeBrain")
    assert sm.active_brain() == "ClaudeBrain"


def test_uptime_is_positive() -> None:
    t = time.time() - 1.0
    sm = SelfModel(start_time=t)
    assert sm.uptime_s() >= 1.0


def test_render_for_prompt_contains_key_sections() -> None:
    sm = SelfModel(brain_name="ClaudeBrain")
    prompt = sm.render_for_prompt()
    assert "ClaudeBrain" in prompt
    assert "terminal_command" in prompt
    assert "keepassxc" in prompt
    assert "Safety" in prompt
