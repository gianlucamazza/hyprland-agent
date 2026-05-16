"""Tests for STT engine (mocked faster-whisper)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_fw():
    """Provide a fake faster-whisper module so agent.voice.stt._fw is defined."""
    mock_fw = MagicMock()
    with (
        patch("agent.voice.stt._HAS_FASTER_WHISPER", True),
        patch("agent.voice.stt._fw", mock_fw, create=True),
    ):
        yield


@pytest.fixture
def fake_fw_model():
    model = MagicMock()
    seg = MagicMock()
    seg.text = "ciao mondo"
    seg2 = MagicMock()
    seg2.text = "come va"
    model.transcribe.return_value = (
        [seg, seg2],
        MagicMock(language="it", language_probability=0.95),
    )
    return model


def test_faster_whisper_engine_raises_when_missing() -> None:
    from agent.voice.stt import FasterWhisperEngine

    with (
        patch("agent.voice.stt._HAS_FASTER_WHISPER", False),
        patch("agent.voice.stt._fw", None, create=True),
        pytest.raises(RuntimeError, match="faster-whisper is required"),
    ):
        FasterWhisperEngine()


@pytest.mark.asyncio
async def test_faster_whisper_engine_transcribe(fake_fw_model) -> None:
    from agent.voice.stt import FasterWhisperEngine

    engine = FasterWhisperEngine(model="tiny")
    with patch("agent.voice.stt._fw.WhisperModel", return_value=fake_fw_model):
        result = await engine.transcribe(b"\x00\x01\x02\x00" * 1000)
    assert result == "ciao mondo come va"


@pytest.mark.asyncio
async def test_faster_whisper_engine_empty_audio(fake_fw_model) -> None:
    from agent.voice.stt import FasterWhisperEngine

    fake_fw_model.transcribe.return_value = ([], MagicMock(language="it", language_probability=0.0))
    engine = FasterWhisperEngine(model="tiny")
    with patch("agent.voice.stt._fw.WhisperModel", return_value=fake_fw_model):
        result = await engine.transcribe(b"")
    assert result == ""


@pytest.mark.asyncio
async def test_faster_whisper_engine_close() -> None:
    from agent.voice.stt import FasterWhisperEngine

    engine = FasterWhisperEngine(model="tiny")
    engine._model = MagicMock()
    await engine.close()
    assert engine._model is None


@pytest.mark.asyncio
async def test_faster_whisper_engine_model_name() -> None:
    from agent.voice.stt import FasterWhisperEngine

    engine = FasterWhisperEngine(model="base")
    assert engine.model_name == "base"


def test_stt_engine_protocol() -> None:
    from agent.voice.stt import FasterWhisperEngine
    from agent.voice.engines import SttEngine

    assert isinstance(FasterWhisperEngine(model="tiny"), SttEngine)


@pytest.mark.asyncio
async def test_faster_whisper_engine_lazy_load(fake_fw_model) -> None:
    from agent.voice.stt import FasterWhisperEngine

    engine = FasterWhisperEngine(model="tiny")
    assert engine._model is None

    with patch("agent.voice.stt._fw.WhisperModel", return_value=fake_fw_model) as mock_cls:
        await engine.transcribe(b"\x00" * 100)
        mock_cls.assert_called_once()
        assert engine._model is not None

        await engine.transcribe(b"\x00" * 100)
        assert mock_cls.call_count == 1


def test_stt_model_dir() -> None:
    from agent.config import CACHE_DIR
    from agent.voice.stt import _model_dir

    assert _model_dir() == CACHE_DIR / "voice" / "stt"


def test_stt_model_path() -> None:
    from agent.voice.stt import _model_path

    assert _model_path("tiny").name == "tiny"
