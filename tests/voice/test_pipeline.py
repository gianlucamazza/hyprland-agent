"""Tests for handsfree pipeline (mocked)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

if TYPE_CHECKING:
    from agent.voice.pipeline import HandsfreePipeline


@pytest.fixture
def mock_wakeword():
    ww = MagicMock()
    ww.detect.return_value = None
    ww.detect_async = AsyncMock(return_value=("computer", 0.9))
    return ww


@pytest.fixture
def mock_vad():
    vad = MagicMock()
    vad.is_speech.return_value = True
    return vad


@pytest.fixture
def mock_stt():
    stt = AsyncMock()
    stt.transcribe.return_value = "apri foot"
    return stt


@pytest.fixture
def mock_recorder():
    rec = MagicMock()
    rec.start_stream = MagicMock()
    rec.stop_stream = MagicMock()
    return rec


def _make_pipeline(**kw) -> HandsfreePipeline:
    from agent.voice.pipeline import HandsfreePipeline

    return HandsfreePipeline(**kw)


@pytest.mark.asyncio
async def test_pipeline_initial_state(mock_wakeword, mock_vad, mock_stt, mock_recorder):
    pipeline = _make_pipeline(
        wakeword=mock_wakeword,
        vad=mock_vad,
        stt=mock_stt,
        recorder=mock_recorder,
    )
    pipeline._loop_task = asyncio.get_running_loop()
    from agent.voice.pipeline import PipelineState

    assert pipeline.state == PipelineState.LISTENING


@pytest.mark.asyncio
async def test_pipeline_wake_word_triggers_recording(
    mock_wakeword, mock_vad, mock_stt, mock_recorder
):
    from agent.voice.pipeline import PipelineState

    pipeline = _make_pipeline(
        wakeword=mock_wakeword,
        vad=mock_vad,
        stt=mock_stt,
        recorder=mock_recorder,
    )
    pipeline._loop_task = asyncio.get_running_loop()

    assert pipeline._state == PipelineState.LISTENING

    pipeline._on_chunk(np.ones(1280, dtype=np.float32))
    assert pipeline._state == PipelineState.WAKING

    mock_vad.is_speech.return_value = False
    pipeline._on_chunk(np.ones(1280, dtype=np.float32))
    await asyncio.sleep(0.05)

    assert pipeline._state == PipelineState.RECORDING or pipeline._state == PipelineState.LISTENING


@pytest.mark.asyncio
async def test_pipeline_barge_in_signal(mock_wakeword, mock_vad, mock_stt, mock_recorder):
    barge = asyncio.Event()
    pipeline = _make_pipeline(
        wakeword=mock_wakeword,
        vad=mock_vad,
        stt=mock_stt,
        recorder=mock_recorder,
        tts_stop_callback=barge,
    )
    pipeline._loop_task = asyncio.get_running_loop()

    mock_vad.is_speech.return_value = True
    pipeline._on_chunk(np.ones(1280, dtype=np.float32))

    mock_vad.is_speech.return_value = False
    pipeline._on_chunk(np.ones(1280, dtype=np.float32))
    await asyncio.sleep(0.1)

    assert barge.is_set()


@pytest.mark.asyncio
async def test_pipeline_recording_to_transcribe(mock_wakeword, mock_vad, mock_stt, mock_recorder):
    from agent.voice.pipeline import PipelineState

    pipeline = _make_pipeline(
        wakeword=mock_wakeword,
        vad=mock_vad,
        stt=mock_stt,
        recorder=mock_recorder,
    )
    pipeline._loop_task = asyncio.get_running_loop()

    pipeline._state = PipelineState.RECORDING
    pipeline._recording_frames = [np.ones(1280, dtype=np.float32) * 0.1 for _ in range(40)]

    mock_vad.is_speech.return_value = False
    for _ in range(15):
        pipeline._on_chunk(np.ones(1280, dtype=np.float32))
    await asyncio.sleep(0.05)

    assert pipeline._state in (
        PipelineState.TRANSCRIBING,
        PipelineState.SUBMITTING,
        PipelineState.LISTENING,
    )
