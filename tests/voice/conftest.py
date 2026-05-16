"""Shared fixtures for voice subsystem tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_voice_state() -> MagicMock:
    """Minimal AppState mock with voice integration enabled."""
    state = MagicMock()
    state.config.integrations.voice.enabled = True
    state.config.integrations.enabled = ()
    state.config.integrations.mako_app_name = "hyprland-agent"
    state.config.integrations.binary_overrides = {}
    return state
