"""Unit tests for brain router selection."""

from __future__ import annotations

import pytest

from agent.brain.router import get_brain
from agent.config import AgentConfig, BrainConfig


def _clear_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.openai_brain import PROVIDERS

    for cfg in PROVIDERS.values():
        monkeypatch.delenv(cfg.key_env, raising=False)


def _config(
    *,
    auto_order: tuple[str, ...] = (
        "claude",
        "openai",
        "moonshot",
        "groq",
        "together",
        "zai",
        "qwen",
    ),
    providers: dict[str, bool] | None = None,
) -> AgentConfig:
    enabled = {
        "claude": True,
        "openai": True,
        "moonshot": True,
        "groq": True,
        "together": True,
        "zai": True,
        "qwen": True,
    }
    if providers:
        enabled.update(providers)
    return AgentConfig(brain=BrainConfig(auto_order=auto_order, providers=enabled))


def _use_config(monkeypatch: pytest.MonkeyPatch, config: AgentConfig) -> None:
    import agent.brain.router as router

    monkeypatch.setattr(router, "load_config", lambda: config)


def test_claude_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.claude import ClaudeBrain

    _use_config(monkeypatch, _config())
    monkeypatch.setattr("agent.brain.router._anthropic_api_key_available", lambda: True)
    brain = get_brain("claude")
    assert isinstance(brain, ClaudeBrain)


def test_openai_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.openai_brain import OpenAICompatibleBrain

    _use_config(monkeypatch, _config())
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    brain = get_brain("openai")
    assert isinstance(brain, OpenAICompatibleBrain)


def test_auto_falls_back_to_claude_when_no_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.brain.claude import ClaudeBrain

    _use_config(monkeypatch, _config())
    monkeypatch.setattr("agent.brain.router._anthropic_api_key_available", lambda: True)
    _clear_provider_keys(monkeypatch)
    brain = get_brain("auto")
    assert isinstance(brain, ClaudeBrain)


def test_none_falls_back_to_claude_when_no_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.brain.claude import ClaudeBrain

    _use_config(monkeypatch, _config())
    monkeypatch.setattr("agent.brain.router._anthropic_api_key_available", lambda: True)
    _clear_provider_keys(monkeypatch)
    brain = get_brain(None)
    assert isinstance(brain, ClaudeBrain)


def test_auto_uses_openai_when_claude_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.openai_brain import OpenAICompatibleBrain

    _use_config(
        monkeypatch,
        _config(providers={"claude": False, "openai": True}),
    )
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    brain = get_brain("auto")
    assert isinstance(brain, OpenAICompatibleBrain)
    assert brain._client.base_url is None or "openai" in str(brain._client.base_url)


def test_auto_respects_config_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured order controls which enabled provider wins."""
    from agent.brain.openai_brain import OpenAICompatibleBrain

    _use_config(
        monkeypatch,
        _config(auto_order=("groq", "openai"), providers={"claude": False}),
    )
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    brain = get_brain("auto")
    assert isinstance(brain, OpenAICompatibleBrain)
    assert "groq.com" in str(brain._client.base_url)


def test_explicit_provider_disabled_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.router import BrainSelectionError

    _use_config(monkeypatch, _config(providers={"claude": False}))
    with pytest.raises(BrainSelectionError, match="disabled"):
        get_brain("claude")


def test_auto_skips_enabled_provider_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.brain.openai_brain import OpenAICompatibleBrain

    _use_config(
        monkeypatch,
        _config(auto_order=("groq", "openai"), providers={"claude": False}),
    )
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    brain = get_brain("auto")
    assert isinstance(brain, OpenAICompatibleBrain)
    assert brain._client.base_url is None or "openai" in str(brain._client.base_url)


def test_claude_model_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.brain.claude import ClaudeBrain

    _use_config(monkeypatch, _config())
    monkeypatch.setattr("agent.brain.router._anthropic_api_key_available", lambda: True)
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    brain = get_brain("claude")
    assert isinstance(brain, ClaudeBrain)
    assert brain.model == "claude-sonnet-4-6"
