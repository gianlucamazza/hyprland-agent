from __future__ import annotations

import contextlib
import logging
import math
import threading
from collections.abc import Callable, Iterator

import numpy as np

from agent.voice.ring_buffer import RingBuffer

log = logging.getLogger(__name__)

try:
    import sounddevice as sd

    _HAS_SOUNDDEVICE = True
except ImportError:
    _HAS_SOUNDDEVICE = False


def sounddevice_available() -> bool:
    return _HAS_SOUNDDEVICE


def list_input_devices() -> list[dict]:
    if not _HAS_SOUNDDEVICE:
        return []
    devices: list[dict] = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            devices.append(
                {
                    "index": i,
                    "name": dev["name"],
                    "channels": int(dev["max_input_channels"]),
                    "default_samplerate": int(dev["default_samplerate"]),
                }
            )
    return devices


class Recorder:
    """Record audio from microphone with optional silence detection.

    Uses ``sounddevice`` internally (optional dependency).
    Raises ``RuntimeError`` when sounddevice is not installed.
    """

    def __init__(
        self,
        samplerate: int = 16000,
        channels: int = 1,
        device: int | None = None,
        silence_threshold: float = 0.02,
        silence_seconds: float = 1.5,
        block_duration: float = 0.2,
    ) -> None:
        if not _HAS_SOUNDDEVICE:
            raise RuntimeError(
                "sounddevice is required for audio capture. "
                "Install with: uv sync --extra voice  (or pip install hyprland-agent[voice])"
            )
        self.samplerate = samplerate
        self.channels = channels
        self.device = device
        self.silence_threshold = silence_threshold
        self.silence_seconds = silence_seconds
        self.block_duration = block_duration
        self._stop_event = threading.Event()
        self._stream: sd.InputStream | None = None

    def stop(self) -> None:
        self._stop_event.set()

    def _open_stream(self) -> sd.InputStream:
        return sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            device=self.device,
            blocksize=int(self.samplerate * self.block_duration),
        )

    def record(self, max_seconds: float = 10.0) -> bytes:
        self._stop_event.clear()
        frames: list[np.ndarray] = []
        silence_blocks = 0
        max_blocks = math.ceil(max_seconds / self.block_duration)
        silence_block_limit = math.ceil(self.silence_seconds / self.block_duration)
        blocks_recorded = 0

        def _chunks() -> Iterator[np.ndarray]:
            nonlocal silence_blocks, blocks_recorded
            with self._open_stream() as stream:
                while not self._stop_event.is_set() and blocks_recorded < max_blocks:
                    chunk, _ = stream.read(stream.blocksize)
                    frames.append(chunk.copy())
                    blocks_recorded += 1
                    rms = float(np.sqrt(np.mean(chunk**2)))
                    if rms < self.silence_threshold:
                        silence_blocks += 1
                    else:
                        silence_blocks = 0
                    if (
                        silence_blocks >= silence_block_limit
                        and blocks_recorded > silence_block_limit
                    ):
                        break
                    yield chunk

        for _ in _chunks():
            pass

        if not frames:
            return b""
        audio = np.concatenate(frames)
        return (audio * 32767).astype(np.int16).tobytes()

    # ------------------------------------------------------------------
    # Streaming capture (used by handsfree / wakeword pipeline)
    # ------------------------------------------------------------------

    def start_stream(
        self,
        on_chunk: Callable[[np.ndarray], None],
        ring_buffer: RingBuffer | None = None,
    ) -> None:
        """Start a continuous capture stream.

        Calls *on_chunk* for each captured block on a background thread.
        If *ring_buffer* is given, chunks are also written to it.
        Stop with ``stop_stream()``.
        """
        self._stop_event.clear()
        self._stream = self._open_stream()
        assert self._stream is not None

        def _loop() -> None:
            stream = self._stream
            assert stream is not None
            try:
                while not self._stop_event.is_set():
                    chunk, _ = stream.read(stream.blocksize)
                    mono = chunk.copy()
                    on_chunk(mono)
                    if ring_buffer is not None:
                        ring_buffer.write(mono.flatten())
            except Exception:
                if not self._stop_event.is_set():
                    log.exception("Capture stream error")
            finally:
                if self._stream:
                    with contextlib.suppress(Exception):
                        self._stream.close()

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def stop_stream(self) -> None:
        self.stop()
