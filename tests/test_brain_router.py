"""Unit tests for brain router selection."""

from __future__ import annotations

import pytest

from agent.brain.router import get_brain


def _clear_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.openai_brain import PROVIDERS

    for cfg in PROVIDERS.values():
        monkeypatch.delenv(cfg.key_env, raising=False)


def test_claude_explicit() -> None:
    from agent.brain.claude import ClaudeBrain

    brain = get_brain("claude")
    assert isinstance(brain, ClaudeBrain)


def test_openai_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.openai_brain import OpenAICompatibleBrain

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    brain = get_brain("openai")
    assert isinstance(brain, OpenAICompatibleBrain)


def test_auto_falls_back_to_claude_when_no_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.brain.claude import ClaudeBrain

    _clear_provider_keys(monkeypatch)
    brain = get_brain("auto")
    assert isinstance(brain, ClaudeBrain)


def test_none_falls_back_to_claude_when_no_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.brain.claude import ClaudeBrain

    _clear_provider_keys(monkeypatch)
    brain = get_brain(None)
    assert isinstance(brain, ClaudeBrain)


def test_auto_prefers_openai_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.openai_brain import OpenAICompatibleBrain

    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    brain = get_brain("auto")
    assert isinstance(brain, OpenAICompatibleBrain)
    assert brain._client.base_url is None or "openai" in str(brain._client.base_url)


def test_auto_prefers_registry_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI (first in registry) must win over Groq when both keys are set."""
    from agent.brain.openai_brain import OpenAICompatibleBrain

    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    brain = get_brain("auto")
    assert isinstance(brain, OpenAICompatibleBrain)
    # OpenAI has no base_url (uses SDK default)
    assert brain._client.base_url is None or "openai" in str(brain._client.base_url)


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
