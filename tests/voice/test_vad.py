"""Tests for Silero VAD (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _mock_sv():
    """Provide a fake silero_vad module."""
    mock_sv = MagicMock()
    mock_vad = MagicMock()
    mock_vad.process_chunk.return_value = 0.8
    mock_sv.VadIterator.return_value = mock_vad
    with (
        patch("agent.voice.vad._HAS_SILERO_VAD", True),
        patch("agent.voice.vad._sv", mock_sv, create=True),
    ):
        yield


def test_silero_vad_raises_when_missing() -> None:
    with (
        patch("agent.voice.vad._HAS_SILERO_VAD", False),
        patch("agent.voice.vad._sv", None, create=True),
        pytest.raises(RuntimeError, match="silero-vad is required"),
    ):
        from agent.voice.vad import SileroVad

        SileroVad()


def test_silero_vad_detect_speech() -> None:
    from agent.voice.vad import SileroVad

    vad = SileroVad(threshold=0.5)
    chunk = np.zeros(512, dtype=np.float32)
    assert vad.is_speech(chunk) is True


def test_silero_vad_detect_silence() -> None:
    from agent.voice.vad import SileroVad

    mock_vad = MagicMock()
    mock_vad.process_chunk.return_value = 0.1
    mock_sv = MagicMock()
    mock_sv.VadIterator.return_value = mock_vad

    with patch("agent.voice.vad._sv", mock_sv, create=True):
        vad = SileroVad(threshold=0.5)
        chunk = np.zeros(512, dtype=np.float32)
        assert vad.is_speech(chunk) is False


def test_silero_vad_reset() -> None:
    from agent.voice.vad import SileroVad

    vad = SileroVad()
    vad._model = MagicMock()
    vad.reset()
    assert vad._model is None


@pytest.mark.asyncio
async def test_silero_vad_close() -> None:
    from agent.voice.vad import SileroVad

    vad = SileroVad()
    vad._model = MagicMock()
    await vad.close()
    assert vad._model is None


def test_silero_vad_lazy_init() -> None:
    from agent.voice.vad import SileroVad

    vad = SileroVad()
    assert vad._model is None
    chunk = np.zeros(512, dtype=np.float32)
    vad.is_speech(chunk)
    assert vad._model is not None
