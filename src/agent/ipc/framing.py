"""NDJSON frame I/O over asyncio streams."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import TypeAdapter, ValidationError

from agent.ipc.constants import FRAME_MAX_BYTES
from agent.ipc.protocol import Frame

_adapter: TypeAdapter[Frame] = TypeAdapter(Frame)


class FrameError(Exception):
    pass


class FrameTooLargeError(FrameError):
    def __init__(self, consumed: int) -> None:
        super().__init__(f"Frame size {consumed} bytes exceeds limit {FRAME_MAX_BYTES}")
        self.consumed = consumed


class FrameParseError(FrameError):
    pass


def decode_frame(line: bytes) -> Frame:
    """Parse a raw NDJSON line into a Frame. Raises FrameParseError on failure."""
    try:
        data: Any = json.loads(line)
    except json.JSONDecodeError as exc:
        raise FrameParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FrameParseError("frame must be a JSON object")
    try:
        return _adapter.validate_python(data)
    except ValidationError as exc:
        raise FrameParseError(f"schema error: {exc}") from exc


def encode_frame(frame: Frame) -> bytes:  # type: ignore[valid-type]
    """Serialize a Frame to a NDJSON line (includes trailing newline)."""
    return (frame.model_dump_json() + "\n").encode()  # type: ignore[union-attr]


async def read_frame(reader: asyncio.StreamReader) -> Frame:
    """Read one NDJSON frame from *reader*. Raises FrameTooLargeError or FrameParseError.

    The caller is responsible for creating *reader* with an appropriate buffer limit
    (e.g. ``asyncio.StreamReader(limit=FRAME_MAX_BYTES)``); exceeding that limit raises
    ``asyncio.LimitOverrunError``, which is translated to ``FrameTooLargeError``.
    """
    try:
        line = await reader.readuntil(b"\n")
    except asyncio.LimitOverrunError as exc:
        raise FrameTooLargeError(exc.consumed) from exc
    except asyncio.IncompleteReadError as exc:
        raise FrameParseError("connection closed mid-frame") from exc
    return decode_frame(line)


async def write_frame(
    writer: asyncio.StreamWriter,
    frame: Frame,  # type: ignore[valid-type]
) -> None:
    """Write one NDJSON frame to *writer* and flush."""
    writer.write(encode_frame(frame))
    await writer.drain()
