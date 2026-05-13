"""Unit tests for brain router selection."""

from __future__ import annotations

import pytest

from agent.brain.router import get_brain


def test_claude_explicit() -> None:
    from agent.brain.claude import ClaudeBrain

    brain = get_brain("claude")
    assert isinstance(brain, ClaudeBrain)


def test_openai_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.openai_brain import OpenAICompatibleBrain

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    brain = get_brain("openai")
    assert isinstance(brain, OpenAICompatibleBrain)


def test_auto_defaults_to_claude() -> None:
    from agent.brain.claude import ClaudeBrain

    brain = get_brain("auto")
    assert isinstance(brain, ClaudeBrain)


def test_none_defaults_to_claude() -> None:
    from agent.brain.claude import ClaudeBrain

    brain = get_brain(None)
    assert isinstance(brain, ClaudeBrain)


def test_dry_run_flag() -> None:
    from agent.brain.claude import ClaudeBrain

    brain = get_brain("claude", dry_run=True)
    assert isinstance(brain, ClaudeBrain)
    assert brain.dry_run is True


def test_claude_model_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.claude import ClaudeBrain

    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    brain = get_brain("claude")
    assert isinstance(brain, ClaudeBrain)
    assert brain.model == "claude-sonnet-4-6"
