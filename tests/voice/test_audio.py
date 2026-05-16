"""Tests for audio capture (mocked sounddevice)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _mock_sd():
    """Provide a fake sounddevice module so agent.voice.audio.sd is defined."""
    mock_sd = MagicMock()
    mock_sd.InputStream = MagicMock()
    mock_sd.query_devices = MagicMock()
    with (
        patch("agent.voice.audio._HAS_SOUNDDEVICE", True),
        patch("agent.voice.audio.sd", mock_sd, create=True),
    ):
        yield


def test_recorder_raises_when_sounddevice_missing() -> None:
    with (
        patch("agent.voice.audio._HAS_SOUNDDEVICE", False),
        patch("agent.voice.audio.sd", None, create=True),
        pytest.raises(RuntimeError, match="sounddevice is required"),
    ):
        from agent.voice.audio import Recorder

        Recorder()


def test_sounddevice_available() -> None:
    from agent.voice.audio import sounddevice_available as f

    with patch("agent.voice.audio._HAS_SOUNDDEVICE", True):
        assert f() is True
    with patch("agent.voice.audio._HAS_SOUNDDEVICE", False):
        assert f() is False


def test_list_input_devices() -> None:
    from agent.voice.audio import list_input_devices

    mock_devices = [
        {"name": "hw:0", "max_input_channels": 2, "default_samplerate": 48000},
        {"name": "hw:1", "max_input_channels": 0, "default_samplerate": 48000},
    ]
    with patch("agent.voice.audio.sd.query_devices", return_value=mock_devices):
        devices = list_input_devices()
    assert len(devices) == 1
    assert devices[0]["name"] == "hw:0"

    with (
        patch("agent.voice.audio._HAS_SOUNDDEVICE", False),
        patch("agent.voice.audio.sd", None, create=True),
    ):
        assert list_input_devices() == []


def test_recorder_stop() -> None:
    from agent.voice.audio import Recorder

    rec = Recorder()
    assert rec._stop_event.is_set() is False
    rec.stop()
    assert rec._stop_event.is_set() is True


@pytest.mark.asyncio
async def test_recorder_record_mocked() -> None:
    from agent.voice.audio import Recorder

    rec = Recorder(silence_seconds=5.0, block_duration=0.1)
    mock_stream = MagicMock()
    mock_stream.__enter__.return_value.blocksize = 1600
    mock_chunk = np.zeros((1600, 1), dtype=np.float32)
    mock_stream.__enter__.return_value.read.return_value = (mock_chunk, None)

    with patch("agent.voice.audio.sd.InputStream", return_value=mock_stream):
        result = rec.record(max_seconds=0.5)

    assert isinstance(result, bytes)
    assert len(result) > 0
