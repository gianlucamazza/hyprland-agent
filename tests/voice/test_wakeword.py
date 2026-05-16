"""Tests for wake word detection (ASR-spotting)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import numpy as np
import pytest


def test_wakeword_detector_defaults() -> None:
    from agent.voice.wakeword import WakeWordDetector

    d = WakeWordDetector()
    assert d.wake_words == ("computer",)
    assert d.sensitivity == 0.5


def test_wakeword_detector_custom_words() -> None:
    from agent.voice.wakeword import WakeWordDetector

    d = WakeWordDetector(wake_words=("computer", "alexa"), sensitivity=0.7)
    assert d.wake_words == ("computer", "alexa")
    assert d.sensitivity == 0.7


def test_wakeword_detector_detect_sync_returns_none() -> None:
    from agent.voice.wakeword import WakeWordDetector

    d = WakeWordDetector()
    chunk = np.zeros(16000, dtype=np.float32)
    assert d.detect(chunk) is None


@pytest.mark.asyncio
async def test_wakeword_detector_detect_async_match() -> None:
    from agent.voice.wakeword import WakeWordDetector

    stt = AsyncMock()
    stt.transcribe.return_value = "computer apri foot"
    d = WakeWordDetector(wake_words=("computer",), sensitivity=0.5)
    audio = np.ones(16000, dtype=np.float32) * 0.1
    result = await d.detect_async(stt, audio)
    assert result is not None
    word, score = result
    assert word == "computer"
    assert score == 0.5


@pytest.mark.asyncio
async def test_wakeword_detector_detect_async_no_match() -> None:
    from agent.voice.wakeword import WakeWordDetector

    stt = AsyncMock()
    stt.transcribe.return_value = "apri foot per favore"
    d = WakeWordDetector(wake_words=("computer",), sensitivity=0.5)
    audio = np.ones(16000, dtype=np.float32) * 0.1
    result = await d.detect_async(stt, audio)
    assert result is None


@pytest.mark.asyncio
async def test_wakeword_detector_detect_async_case_insensitive() -> None:
    from agent.voice.wakeword import WakeWordDetector

    stt = AsyncMock()
    stt.transcribe.return_value = "Computer apri foot"
    d = WakeWordDetector(wake_words=("computer",), sensitivity=0.5)
    audio = np.ones(16000, dtype=np.float32) * 0.1
    result = await d.detect_async(stt, audio)
    assert result is not None
    assert result[0] == "computer"


@pytest.mark.asyncio
async def test_wakeword_detector_detect_async_multiple_words() -> None:
    from agent.voice.wakeword import WakeWordDetector

    stt = AsyncMock()
    stt.transcribe.return_value = "alexa what time is it"
    d = WakeWordDetector(wake_words=("computer", "alexa"), sensitivity=0.5)
    audio = np.ones(16000, dtype=np.float32) * 0.1
    result = await d.detect_async(stt, audio)
    assert result is not None
    assert result[0] == "alexa"


def test_wakeword_detector_reset() -> None:
    from agent.voice.wakeword import WakeWordDetector

    d = WakeWordDetector()
    d.reset()  # should be no-op


@pytest.mark.asyncio
async def test_wakeword_detector_close() -> None:
    from agent.voice.wakeword import WakeWordDetector

    d = WakeWordDetector()
    await d.close()  # should be no-op


def test_wakeword_model_dir() -> None:
    from agent.config import CACHE_DIR
    from agent.voice.wakeword import wakeword_model_dir

    assert wakeword_model_dir() == CACHE_DIR / "voice" / "wakeword"
