"""Async client connection — hello handshake, RPC calls, subscriptions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from agent.client.errors import DaemonUnavailable, ProtocolMismatch, RpcError
from agent.ipc.constants import FRAME_MAX_BYTES, PROTOCOL_VERSION
from agent.ipc.framing import FrameParseError, read_frame, write_frame
from agent.ipc.protocol import (
    EventFrame,
    HelloFrame,
    RequestFrame,
    ResponseFrame,
    RpcMethod,
    SubscribeFrame,
    Topic,
    versions_compatible,
)


class DaemonConnection:
    """Single connection to the daemon. Use via the :func:`connect` context manager."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        # Single queue that the unified _read_loop feeds; events() drains it.
        self._event_queue: asyncio.Queue[tuple[Topic, dict[str, Any]] | None] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None

    async def _start_reader(self) -> None:
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Single reader — routes ResponseFrames to pending futures, EventFrames to queue."""
        try:
            while True:
                try:
                    frame = await read_frame(self._reader)
                except FrameParseError:
                    break
                if isinstance(frame, ResponseFrame):
                    fut = self._pending.pop(frame.id, None)
                    if fut and not fut.done():
                        fut.set_result({"result": frame.result, "error": frame.error})
                elif isinstance(frame, EventFrame):
                    await self._event_queue.put((frame.topic, frame.payload))
        finally:
            # Sentinel: unblocks any waiting events() iterator.
            await self._event_queue.put(None)

    async def request(
        self, method: RpcMethod, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send an RPC request and wait for the response. Raises RpcError on daemon errors."""
        req_id = str(uuid.uuid4())
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        await write_frame(self._writer, RequestFrame(id=req_id, method=method, params=params or {}))
        response = await fut
        if response.get("error"):
            err = response["error"]
            raise RpcError(err.get("code", "error"), err.get("message", "unknown error"))
        return response.get("result") or {}

    async def subscribe(self, *topics: Topic) -> None:
        await write_frame(self._writer, SubscribeFrame(topics=list(topics)))

    async def events(self) -> AsyncIterator[tuple[Topic, dict[str, Any]]]:
        """Iterate over subscription events. Must call subscribe() first."""
        while True:
            item = await self._event_queue.get()
            if item is None:
                return
            yield item

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        self._writer.close()
        with suppress(Exception):
            await self._writer.wait_closed()


@asynccontextmanager
async def connect(socket_path: Path) -> AsyncIterator[DaemonConnection]:
    """Connect to the daemon, perform the hello handshake, yield a live connection."""
    try:
        reader, writer = await asyncio.open_unix_connection(
            path=str(socket_path),
            limit=FRAME_MAX_BYTES,
        )
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise DaemonUnavailable(str(socket_path)) from exc

    conn = DaemonConnection(reader, writer)
    try:
        # Receive server's hello
        server_hello = await read_frame(reader)
        if not isinstance(server_hello, HelloFrame):
            writer.close()
            raise ProtocolMismatch("expected hello frame from daemon")
        if not versions_compatible(server_hello.version, PROTOCOL_VERSION):
            writer.close()
            raise ProtocolMismatch(
                f"version mismatch: daemon={server_hello.version} client={PROTOCOL_VERSION}"
            )
        # Send our hello
        await write_frame(writer, HelloFrame(version=PROTOCOL_VERSION))
        await conn._start_reader()
        yield conn
    finally:
        await conn.close()
