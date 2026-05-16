"""Piper TTS engine — subprocess-based, zero Python deps for M2.

Calls ``piper --model <path>.onnx --output-raw`` and pipes the raw PCM
to ``aplay`` for playback.  Models live under
``~/.cache/hyprland-agent/voice/tts/<voice>.onnx``.
Supports ``stop()`` for barge-in (M4).
"""

from __future__ import annotations

import asyncio
import logging
import signal

from agent.config import CACHE_DIR
from agent.tools._proc import ProcResult, run, safe_env

log = logging.getLogger(__name__)


class SubprocessPiperEngine:
    """TTS engine that shells out to the ``piper`` binary.

    Parameters
    ----------
    voice : str
        Voice name, e.g. ``"it_IT-paola-medium"``.
        The engine looks for ``<voice>.onnx`` in the model cache.
    speed : float
        Not yet wired — reserved for future use.
    """

    def __init__(self, voice: str = "it_IT-paola-medium", speed: float = 1.0) -> None:
        self._voice = voice
        self._speed = speed
        self._model_path = CACHE_DIR / "voice" / "tts" / f"{voice}.onnx"
        self._current_process: asyncio.subprocess.Process | None = None

    async def say(self, text: str) -> None:
        if not self._model_path.exists():
            log.warning(
                "TTS model not found at %s — pull it with `agent voice models pull`",
                self._model_path,
            )
            return

        piper: ProcResult = await run(
            ["piper", "--model", str(self._model_path), "--output-raw"],
            stdin_data=text.encode("utf-8"),
            capture_stdout=True,
            timeout=30.0,
            env=safe_env(),
        )
        if piper.returncode != 0:
            stderr = piper.stderr.decode(errors="replace")
            log.warning("Piper TTS failed (exit %d): %s", piper.returncode, stderr)
            return

        proc = await asyncio.create_subprocess_exec(
            "aplay",
            "-r",
            "22050",
            "-f",
            "S16_LE",
            "-c",
            "1",
            "-t",
            "raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._current_process = proc
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(piper.stdout), timeout=60.0)  # type: ignore[arg-type]
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise
        finally:
            if self._current_process is proc:
                self._current_process = None

    async def stop(self) -> None:
        if self._current_process is not None:
            try:
                self._current_process.send_signal(signal.SIGTERM)
                await asyncio.sleep(0.1)
                if self._current_process.returncode is None:
                    self._current_process.kill()
            except ProcessLookupError:
                pass
            finally:
                self._current_process = None

    async def close(self) -> None:
        await self.stop()
