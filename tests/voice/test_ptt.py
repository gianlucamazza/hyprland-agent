"""Tests for PTT socket server."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_stt() -> AsyncMock:
    engine = AsyncMock()
    engine.transcribe.return_value = "apri foot"
    return engine


@pytest.fixture
def mock_recorder() -> MagicMock:
    rec = MagicMock()
    rec.record.return_value = b"\x00\x01\x02\x00" * 1000
    return rec


@pytest.mark.asyncio
async def test_ptt_server_start_stop(tmp_path) -> None:
    from agent.voice.ptt import PttServer

    sock = tmp_path / "ptt.sock"
    stt = AsyncMock()
    rec = MagicMock()
    server = PttServer(socket_path=sock, stt=stt, recorder=rec)

    await server.start()
    assert sock.exists()
    assert sock.stat().st_mode & 0o777 == 0o600

    await server.stop()
    assert not sock.exists()


@pytest.mark.asyncio
async def test_ptt_server_record_and_submit(tmp_path, mock_stt, mock_recorder) -> None:
    from agent.voice.ptt import PttServer

    sock = tmp_path / "ptt.sock"
    server = PttServer(socket_path=sock, stt=mock_stt, recorder=mock_recorder)

    await server.start()

    submit_mock = AsyncMock()
    server._submit = submit_mock

    reader, writer = await asyncio.open_unix_connection(str(sock))
    writer.write(b"record\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()

    await asyncio.sleep(0.1)

    mock_recorder.record.assert_called_once()
    mock_stt.transcribe.assert_called_once()
    submit_mock.assert_awaited_once_with("apri foot")

    await server.stop()


@pytest.mark.asyncio
async def test_ptt_server_unknown_command(tmp_path, mock_stt, mock_recorder) -> None:
    from agent.voice.ptt import PttServer

    sock = tmp_path / "ptt.sock"
    server = PttServer(socket_path=sock, stt=mock_stt, recorder=mock_recorder)

    await server.start()

    reader, writer = await asyncio.open_unix_connection(str(sock))
    writer.write(b"unknown\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()

    await asyncio.sleep(0.1)
    mock_recorder.record.assert_not_called()
    mock_stt.transcribe.assert_not_called()

    await server.stop()


@pytest.mark.asyncio
async def test_ptt_server_empty_transcription(tmp_path) -> None:
    from agent.voice.ptt import PttServer

    sock = tmp_path / "ptt.sock"
    stt = AsyncMock()
    stt.transcribe.return_value = ""
    rec = MagicMock()
    rec.record.return_value = b"\x00" * 1000

    server = PttServer(socket_path=sock, stt=stt, recorder=rec)
    await server.start()

    submit_mock = AsyncMock()
    server._submit = submit_mock

    reader, writer = await asyncio.open_unix_connection(str(sock))
    writer.write(b"record\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()

    await asyncio.sleep(0.1)
    submit_mock.assert_not_awaited()

    await server.stop()


@pytest.mark.asyncio
async def test_ptt_server_no_audio(tmp_path) -> None:
    from agent.voice.ptt import PttServer

    sock = tmp_path / "ptt.sock"
    stt = AsyncMock()
    rec = MagicMock()
    rec.record.return_value = b""

    server = PttServer(socket_path=sock, stt=stt, recorder=rec)
    await server.start()

    submit_mock = AsyncMock()
    server._submit = submit_mock

    reader, writer = await asyncio.open_unix_connection(str(sock))
    writer.write(b"record\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()

    await asyncio.sleep(0.1)
    stt.transcribe.assert_not_called()
    submit_mock.assert_not_awaited()

    await server.stop()


@pytest.mark.asyncio
async def test_ptt_server_submit_rpc(tmp_path) -> None:
    """_submit connects to daemon and calls run_task."""
    from agent.voice.ptt import PttServer

    sock = tmp_path / "ptt.sock"
    stt = AsyncMock()
    rec = MagicMock()

    server = PttServer(socket_path=sock, stt=stt, recorder=rec, brain="claude")

    mock_conn = AsyncMock()
    mock_conn.__aenter__.return_value.request.return_value = {"run_id": "r-123"}
    mock_conn.__aexit__.return_value = None

    with patch("agent.voice.ptt.connect", return_value=mock_conn):
        await server._submit("apri foot")

    request_mock = mock_conn.__aenter__.return_value.request
    request_mock.assert_awaited_once()
    call_args = request_mock.await_args
    assert call_args is not None
    assert call_args[0][0].value == "run_task"
    assert call_args[0][1]["task"] == "apri foot"
    assert call_args[0][1]["brain"] == "claude"
