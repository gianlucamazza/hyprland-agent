"""Unix socket server — accept loop and per-connection protocol handler."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from agent.daemon import rpc as rpc_module
from agent.daemon.state import AppState
from agent.ipc.constants import FRAME_MAX_BYTES, HEARTBEAT_INTERVAL, PROTOCOL_VERSION
from agent.ipc.framing import FrameParseError, encode_frame, read_frame
from agent.ipc.protocol import (
    EventFrame,
    Frame,
    HelloFrame,
    PingFrame,
    PongFrame,
    RequestFrame,
    SubscribeFrame,
    Topic,
    UnsubscribeFrame,
    make_error_response,
    versions_compatible,
)

log = logging.getLogger(__name__)


async def _handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: AppState,
) -> None:
    peer = writer.get_extra_info("peername", "<unix>")
    log.debug("Client connected: %s", peer)

    # Per-connection state
    from agent.daemon.pubsub import Subscriber

    subs: dict[Topic, Subscriber] = {}
    forwarder_tasks: dict[Topic, asyncio.Task] = {}
    outbound: asyncio.Queue[Frame] = asyncio.Queue(maxsize=4000)
    stop = asyncio.Event()

    async def _write_raw(frame: Frame) -> None:
        writer.write(encode_frame(frame))
        await writer.drain()

    async def _forwarder(topic: Topic, sub: Subscriber) -> None:
        while not stop.is_set():
            if sub.is_disconnected:
                stop.set()
                return
            try:
                payload = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
                await outbound.put(EventFrame(topic=topic, payload=payload))
            except TimeoutError:
                continue

    async def _writer() -> None:
        while not stop.is_set():
            try:
                frame = await asyncio.wait_for(outbound.get(), timeout=HEARTBEAT_INTERVAL)
            except TimeoutError:
                frame = PingFrame()
            try:
                writer.write(encode_frame(frame))
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                stop.set()
                return

    async def _reader() -> None:
        # Handshake: send our hello, expect theirs back
        await _write_raw(HelloFrame(version=PROTOCOL_VERSION))
        try:
            frame = await read_frame(reader)
        except FrameParseError as exc:
            log.warning("Handshake failed: %s", exc)
            stop.set()
            return

        if not isinstance(frame, HelloFrame):
            await _write_raw(make_error_response("", "expected hello frame", code="protocol_error"))
            stop.set()
            return

        if not versions_compatible(frame.version, PROTOCOL_VERSION):
            await _write_raw(
                make_error_response(
                    "",
                    f"version mismatch: server={PROTOCOL_VERSION} client={frame.version}",
                    code="version_mismatch",
                )
            )
            stop.set()
            return

        # Main read loop
        while not stop.is_set():
            try:
                frame = await read_frame(reader)
            except FrameParseError as exc:
                if "closed mid-frame" in str(exc):
                    break
                log.warning("Bad frame from client: %s", exc)
                continue

            if isinstance(frame, RequestFrame):
                response = await rpc_module.dispatch(state, frame.id, frame.method, frame.params)
                await outbound.put(response)

            elif isinstance(frame, SubscribeFrame):
                for topic in frame.topics:
                    if topic not in subs:
                        sub = await state.pubsub.subscribe(topic)
                        subs[topic] = sub
                        t = asyncio.create_task(_forwarder(topic, sub))
                        forwarder_tasks[topic] = t

            elif isinstance(frame, UnsubscribeFrame):
                for topic in frame.topics:
                    if topic in subs:
                        await state.pubsub.unsubscribe(topic, subs.pop(topic))
                        if (ft := forwarder_tasks.pop(topic, None)) is not None:
                            ft.cancel()

            elif isinstance(frame, PongFrame):
                pass  # heartbeat response

        stop.set()

    reader_task = asyncio.create_task(_reader())
    writer_task = asyncio.create_task(_writer())

    done, pending = await asyncio.wait(
        {reader_task, writer_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    for task in forwarder_tasks.values():
        task.cancel()
    for topic, sub in subs.items():
        await state.pubsub.unsubscribe(topic, sub)

    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()

    log.debug("Client disconnected: %s", peer)


async def serve(state: AppState, socket_path: Path) -> None:
    """Start the Unix socket server. Runs until cancelled."""
    if socket_path.exists():
        socket_path.unlink()

    old_umask = os.umask(0o177)  # socket will be mode 0o600
    try:
        srv = await asyncio.start_unix_server(
            lambda r, w: _handle_connection(r, w, state),
            path=str(socket_path),
            limit=FRAME_MAX_BYTES,
        )
    finally:
        os.umask(old_umask)

    log.info("Daemon listening on %s", socket_path)
    async with srv:
        await srv.serve_forever()
