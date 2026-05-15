"""Tests for local provider configuration."""

from __future__ import annotations

import pytest

from agent.config import ConfigError, load_config


def test_missing_config_uses_defaults(tmp_path) -> None:
    config = load_config(tmp_path / "missing.yaml")

    assert config.brain.default == "auto"
    assert config.brain.auto_order[0] == "claude"
    assert config.brain.is_enabled("claude") is True
    assert config.brain.is_enabled("openai") is True


def test_provider_enabled_flags_and_aliases(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
brain:
  default: auto
  auto_order: [openai, kimi, claude]
  providers:
    claude:
      enabled: false
    openai:
      enabled: true
    kimi:
      enabled: true
audit_log: true
"""
    )

    config = load_config(path)

    assert config.audit_log is True
    assert config.brain.auto_order == ("openai", "moonshot", "claude")
    assert config.brain.is_enabled("claude") is False
    assert config.brain.is_enabled("openai") is True
    assert config.brain.is_enabled("moonshot") is True


def test_unknown_provider_rejected(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
brain:
  auto_order: [openai, madeup]
"""
    )

    with pytest.raises(ConfigError, match="Unknown provider"):
        load_config(path)


def test_enabled_must_be_boolean(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
brain:
  providers:
    openai:
      enabled: later
"""
    )

    with pytest.raises(ConfigError, match="enabled"):
        load_config(path)
