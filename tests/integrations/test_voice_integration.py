"""Tests for VoiceIntegration (M1 skeleton)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.integrations.voice import VoiceIntegration
from agent.schemas import Action, ActionKind


@pytest.fixture
def voice_state():
    state = MagicMock()
    state.config.integrations.voice.enabled = True
    state.config.integrations.binary_overrides = {}
    return state


@pytest.fixture
def voice():
    return VoiceIntegration()


@pytest.mark.asyncio
async def test_setup_logs_enabled(voice, voice_state, monkeypatch):
    monkeypatch.setattr("agent.integrations.voice.log", MagicMock())
    await voice.setup(voice_state)
    assert voice._available is True


@pytest.mark.asyncio
async def test_setup_disabled(voice, voice_state, monkeypatch):
    voice_state.config.integrations.voice.enabled = False
    monkeypatch.setattr("agent.integrations.voice.log", MagicMock())
    await voice.setup(voice_state)
    assert voice._available is False


@pytest.mark.asyncio
async def test_handle_speak(voice, voice_state, monkeypatch):
    monkeypatch.setattr("agent.integrations.voice.log", MagicMock())
    await voice.setup(voice_state)

    action = Action(kind=ActionKind.speak, params={"text": "hello"})
    result = await voice.handle(action)
    assert result is not None
    assert result.kind == "speak"


@pytest.mark.asyncio
async def test_handle_speak_when_disabled(voice, voice_state, monkeypatch):
    voice_state.config.integrations.voice.enabled = False
    monkeypatch.setattr("agent.integrations.voice.log", MagicMock())
    await voice.setup(voice_state)

    action = Action(kind=ActionKind.speak, params={"text": "hello"})
    result = await voice.handle(action)
    assert result is not None
    assert result.blocked is not None


@pytest.mark.asyncio
async def test_non_speak_action_passes_through(voice, voice_state, monkeypatch):
    monkeypatch.setattr("agent.integrations.voice.log", MagicMock())
    await voice.setup(voice_state)

    action = Action(kind=ActionKind.key, params={"combo": "ctrl+c"})
    result = await voice.handle(action)
    assert result is None


@pytest.mark.asyncio
async def test_teardown(voice, voice_state, monkeypatch):
    monkeypatch.setattr("agent.integrations.voice.log", MagicMock())
    await voice.setup(voice_state)
    assert voice._available is True
    await voice.teardown()
    assert voice._available is False


@pytest.mark.asyncio
async def test_capabilities(voice):
    caps = voice.capabilities()
    assert len(caps) == 1
    assert caps[0].name == "voice"
    assert "speak" in caps[0].action_kinds
