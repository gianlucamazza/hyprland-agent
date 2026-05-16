"""Tests for voice engines (mocked subprocess)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.config import CACHE_DIR
from agent.tools._proc import ProcResult


@pytest.fixture
def fake_proc_run(monkeypatch):
    """Replace agent.tools._proc.run with an AsyncMock."""
    mock = AsyncMock()
    monkeypatch.setattr("agent.tools._proc.run", mock)
    return mock


@pytest.mark.asyncio
async def test_piper_engine_model_path() -> None:
    from agent.voice.engines.piper import SubprocessPiperEngine

    engine = SubprocessPiperEngine(voice="it_IT-paola-medium")
    expected = CACHE_DIR / "voice" / "tts" / "it_IT-paola-medium.onnx"
    assert engine._model_path == expected


@pytest.mark.asyncio
async def test_piper_engine_skips_when_model_missing(fake_proc_run) -> None:
    from agent.voice.engines.piper import SubprocessPiperEngine

    engine = SubprocessPiperEngine(voice="nonexistent-voice")
    await engine.say("test")
    fake_proc_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_piper_engine_calls_piper_and_aplay(fake_proc_run, monkeypatch) -> None:
    from agent.voice.engines.piper import SubprocessPiperEngine

    fake_piper_result = ProcResult(returncode=0, stdout=b"\x00\x01\x02\x00" * 100)
    fake_proc_run.side_effect = [fake_piper_result]
    monkeypatch.setattr("agent.voice.engines.piper.run", fake_proc_run)

    mock_aplay_proc = AsyncMock()
    mock_aplay_proc.communicate.return_value = (b"", b"")
    mock_aplay_proc.returncode = 0

    engine = SubprocessPiperEngine(voice="test-voice")
    fake_path = MagicMock(spec=Path)
    fake_path.exists.return_value = True
    fake_path.__str__.return_value = "/fake/model.onnx"
    monkeypatch.setattr(engine, "_model_path", fake_path)

    with patch("asyncio.create_subprocess_exec", return_value=mock_aplay_proc):
        await engine.say("Ciao mondo")

    fake_proc_run.assert_awaited_once()
    piper_call = fake_proc_run.await_args_list[0]
    assert piper_call[0][0][0] == "piper"
    mock_aplay_proc.communicate.assert_awaited_once()


@pytest.mark.asyncio
async def test_piper_engine_logs_warning_on_piper_failure(
    fake_proc_run, monkeypatch, caplog
) -> None:
    from agent.voice.engines.piper import SubprocessPiperEngine

    fake_proc_run.side_effect = [
        ProcResult(returncode=1, stderr=b"model error"),
    ]
    monkeypatch.setattr("agent.voice.engines.piper.run", fake_proc_run)

    engine = SubprocessPiperEngine(voice="test-voice")
    fake_path = MagicMock(spec=Path)
    fake_path.exists.return_value = True
    fake_path.__str__.return_value = "/fake/model.onnx"
    monkeypatch.setattr(engine, "_model_path", fake_path)

    await engine.say("test")
    assert "Piper TTS failed" in caplog.text


@pytest.mark.asyncio
async def test_piper_engine_stop(monkeypatch) -> None:
    from agent.voice.engines.piper import SubprocessPiperEngine

    engine = SubprocessPiperEngine(voice="test-voice")
    mock_proc = MagicMock()
    mock_proc.returncode = None
    engine._current_process = mock_proc

    await engine.stop()
    mock_proc.send_signal.assert_called_once()
    assert engine._current_process is None


@pytest.mark.asyncio
async def test_piper_engine_stop_no_process(monkeypatch) -> None:
    from agent.voice.engines.piper import SubprocessPiperEngine

    engine = SubprocessPiperEngine(voice="test-voice")
    engine._current_process = None
    await engine.stop()  # should not raise
