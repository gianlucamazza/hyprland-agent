from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

try:
    import silero_vad as _sv

    _HAS_SILERO_VAD = True
except ImportError:
    _HAS_SILERO_VAD = False


class SileroVad:
    """Voice Activity Detection using Silero VAD.

    Wraps ``silero-vad`` with lazy model loading.
    Maintains an internal state buffer for streaming inference.
    Raises ``RuntimeError`` when silero-vad is not installed.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        if not _HAS_SILERO_VAD:
            raise RuntimeError(
                "silero-vad is required for voice activity detection. "
                "Install with: uv sync --extra voice"
            )
        self._threshold = threshold
        self._model: _sv.VadIterator | None = None

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        self._model = _sv.VadIterator()

    def is_speech(self, chunk: np.ndarray, samplerate: int = 16000) -> bool:
        self._lazy_init()
        if self._model is None:
            return False
        speech_prob = self._model.process_chunk(chunk, samplerate)
        return speech_prob >= self._threshold

    def reset(self) -> None:
        self._model = None

    async def close(self) -> None:
        self._model = None
