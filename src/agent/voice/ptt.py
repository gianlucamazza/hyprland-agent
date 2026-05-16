from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from agent.client.connection import DaemonUnavailable, connect
from agent.client.errors import RpcError
from agent.ipc.constants import SOCKET_PATH
from agent.ipc.protocol import RpcMethod
from agent.voice.audio import Recorder
from agent.voice.engines import SttEngine

log = logging.getLogger(__name__)


class PttServer:
    """Unix socket server that triggers voice capture on demand.

    Listens on a Unix socket for incoming connections.  Each connected
    client sends one line — currently only the literal ``record`` is
    recognised.  The server then captures mic audio, transcribes it,
    and submits the result as a ``run_task`` RPC to the daemon.

    Usage from a Hyprland keybind::

        bind = ,code, exec, sh -c 'echo record | nc -U "$XDG_RUNTIME_DIR"/hyprland-agent-voice-ptt.sock'

    Or via the ``agent voice ptt`` CLI command.
    """

    def __init__(
        self,
        socket_path: Path,
        stt: SttEngine,
        recorder: Recorder,
        record_timeout: float = 10.0,
        brain: str = "auto",
    ) -> None:
        self._socket_path = socket_path
        self._stt = stt
        self._recorder = recorder
        self._record_timeout = record_timeout
        self._brain = brain
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.unlink(missing_ok=True)

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )
        os.chmod(str(self._socket_path), 0o600)
        log.info("PTT socket listening at %s", self._socket_path)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._socket_path.unlink(missing_ok=True)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            data = await reader.readline()
            if not data:
                return
            command = data.strip().decode("utf-8", errors="replace")
            if command != "record":
                log.warning("Unknown PTT command: %r", command)
                return

            log.info("PTT trigger received — recording...")
            pcm_bytes = await asyncio.to_thread(self._recorder.record, self._record_timeout)
            if not pcm_bytes:
                log.warning("No audio captured")
                return

            log.info("Transcribing %d bytes of audio...", len(pcm_bytes))
            text = await self._stt.transcribe(pcm_bytes)
            if not text:
                log.info("Transcription empty — nothing to submit")
                return

            log.info("Transcribed: %s", text)
            await self._submit(text)
        except Exception:
            log.exception("PTT handler error")
        finally:
            writer.close()

    async def _submit(self, text: str) -> None:
        try:
            async with connect(SOCKET_PATH) as conn:
                result = await conn.request(
                    RpcMethod.run_task,
                    {"task": text, "brain": self._brain},
                )
                log.info("Submitted run_task, run_id=%s", result.get("run_id", "?"))
        except DaemonUnavailable:
            log.warning("Daemon unavailable — cannot submit transcription")
        except RpcError as exc:
            log.warning("RPC error submitting transcription: %s", exc)
