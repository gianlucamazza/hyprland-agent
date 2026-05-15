"""Tests for NDJSON framing: encode/decode and async stream I/O."""

from __future__ import annotations

import asyncio
import json

import pytest

from agent.ipc.constants import FRAME_MAX_BYTES
from agent.ipc.framing import (
    FrameParseError,
    FrameTooLargeError,
    decode_frame,
    encode_frame,
    read_frame,
)
from agent.ipc.protocol import (
    EventFrame,
    HelloFrame,
    PingFrame,
    PongFrame,
    RequestFrame,
    RpcMethod,
    Topic,
)

# --- encode_frame / decode_frame ---


def test_encode_produces_newline_terminated_bytes() -> None:
    frame = PingFrame()
    raw = encode_frame(frame)
    assert raw.endswith(b"\n")
    assert raw.startswith(b"{")


def test_encode_decode_roundtrip_ping() -> None:
    raw = encode_frame(PingFrame())
    recovered = decode_frame(raw)
    assert isinstance(recovered, PingFrame)


def test_encode_decode_roundtrip_hello() -> None:
    frame = HelloFrame(version="1.0", capabilities=["streams"])
    recovered = decode_frame(encode_frame(frame))
    assert isinstance(recovered, HelloFrame)
    assert recovered.version == "1.0"
    assert recovered.capabilities == ["streams"]


def test_encode_decode_roundtrip_request() -> None:
    frame = RequestFrame(id="r1", method=RpcMethod.list_windows)
    recovered = decode_frame(encode_frame(frame))
    assert isinstance(recovered, RequestFrame)
    assert recovered.method == RpcMethod.list_windows


def test_encode_decode_roundtrip_event() -> None:
    frame = EventFrame(topic=Topic.runs, payload={"run_id": "abc", "status": "completed"})
    recovered = decode_frame(encode_frame(frame))
    assert isinstance(recovered, EventFrame)
    assert recovered.payload["run_id"] == "abc"


def test_decode_invalid_json_raises_parse_error() -> None:
    with pytest.raises(FrameParseError, match="invalid JSON"):
        decode_frame(b"not json\n")


def test_decode_json_array_raises_parse_error() -> None:
    with pytest.raises(FrameParseError, match="JSON object"):
        decode_frame(b"[1, 2, 3]\n")


def test_decode_unknown_type_raises_parse_error() -> None:
    with pytest.raises(FrameParseError, match="schema error"):
        decode_frame(b'{"type": "unknown_type"}\n')


def test_decode_extra_fields_raises_parse_error() -> None:
    with pytest.raises(FrameParseError, match="schema error"):
        decode_frame(b'{"type": "ping", "extra": "field"}\n')


# --- async read_frame ---


def _make_reader(*lines: bytes, limit: int = 2**16) -> asyncio.StreamReader:
    """Feed *lines* into a fresh StreamReader with the given buffer *limit*."""
    reader = asyncio.StreamReader(limit=limit)
    for line in lines:
        reader.feed_data(line)
    reader.feed_eof()
    return reader


async def test_read_frame_ping() -> None:
    reader = _make_reader(encode_frame(PingFrame()))
    frame = await read_frame(reader)
    assert isinstance(frame, PingFrame)


async def test_read_frame_hello() -> None:
    raw = encode_frame(HelloFrame(version="1.0"))
    reader = _make_reader(raw)
    frame = await read_frame(reader)
    assert isinstance(frame, HelloFrame)
    assert frame.version == "1.0"


async def test_read_frame_sequential() -> None:
    reader = _make_reader(encode_frame(PingFrame()), encode_frame(PongFrame()))
    f1 = await read_frame(reader)
    f2 = await read_frame(reader)
    assert isinstance(f1, PingFrame)
    assert isinstance(f2, PongFrame)


async def test_read_frame_closed_connection_raises_parse_error() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"type": "ping"')  # incomplete, no newline
    reader.feed_eof()
    with pytest.raises(FrameParseError, match="closed mid-frame"):
        await read_frame(reader)


async def test_read_frame_too_large_raises_too_large_error() -> None:
    oversized = b"x" * 200 + b"\n"  # 201 bytes
    reader = asyncio.StreamReader(limit=100)  # buffer limit = 100 bytes
    reader.feed_data(oversized)
    with pytest.raises(FrameTooLargeError):
        await read_frame(reader)


async def test_read_frame_at_exact_limit_succeeds() -> None:
    raw = encode_frame(PingFrame())
    assert len(raw) < FRAME_MAX_BYTES
    reader = _make_reader(raw, limit=FRAME_MAX_BYTES)
    frame = await read_frame(reader)
    assert isinstance(frame, PingFrame)


# --- FrameTooLargeError attributes ---


def test_frame_too_large_error_stores_consumed() -> None:
    err = FrameTooLargeError(512)
    assert err.consumed == 512
    assert "512" in str(err)


# --- encode idempotency ---


def test_encode_pong_is_valid_json() -> None:
    raw = encode_frame(PongFrame())
    data = json.loads(raw)
    assert data["type"] == "pong"
