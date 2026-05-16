from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from agent.config import CACHE_DIR

log = logging.getLogger(__name__)


def wakeword_model_dir() -> Path:
    return CACHE_DIR / "voice" / "wakeword"


class WakeWordDetector:
    """Wake word detection using ASR spotting.

    Uses the configured STT engine to transcribe short audio segments
    and checks for the presence of a configured wake word in the
    transcript.  This avoids any extra ML dependencies beyond the
    already-installed faster-whisper / STT engine.

    The caller is responsible for providing audio segments long enough
    for the STT engine to produce meaningful output (typically 1-2 s).
    """

    def __init__(
        self,
        wake_words: tuple[str, ...] = ("computer",),
        sensitivity: float = 0.5,
    ) -> None:
        self._wake_words = tuple(w.lower() for w in wake_words)
        self._sensitivity = sensitivity

    @property
    def wake_words(self) -> tuple[str, ...]:
        return self._wake_words

    @property
    def sensitivity(self) -> float:
        return self._sensitivity

    def detect(self, audio_chunk: np.ndarray) -> tuple[str, float] | None:
        """Placeholder — actual detection requires an STT engine reference.

        This method is kept for API compatibility with the pipeline.
        The real detection happens in ``HandsfreePipeline`` where the
        STT engine is available.
        """
        return None

    async def detect_async(
        self, stt_engine, audio: np.ndarray, samplerate: int = 16000
    ) -> tuple[str, float] | None:
        """Transcribe *audio* via *stt_engine* and check for wake words.

        Returns ``(word, confidence)`` if a wake word is found,
        ``None`` otherwise.
        """
        pcm = (audio * 32767).astype(np.int16).tobytes()
        text = await stt_engine.transcribe(pcm, samplerate)
        text_lower = text.lower()
        for ww in self._wake_words:
            if ww in text_lower:
                confidence = 0.5 if self._sensitivity >= 0.5 else 0.3
                return (ww, confidence)
        return None

    def reset(self) -> None:
        pass

    async def close(self) -> None:
        pass
