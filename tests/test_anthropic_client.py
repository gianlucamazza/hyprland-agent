"""Tests for the Anthropic SDK client factory."""

from __future__ import annotations

import pytest

from agent.brain.anthropic_client import anthropic_client


def test_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not set"):
        anthropic_client()


def test_builds_client_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    client = anthropic_client()
    assert client.default_headers.get("anthropic-beta") == "computer-use-2025-11-24"


def test_respects_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.z.ai/api/anthropic")
    client = anthropic_client()
    assert "z.ai" in str(client.base_url)
