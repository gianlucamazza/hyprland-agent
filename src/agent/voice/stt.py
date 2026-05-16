from __future__ import annotations

import logging
import os
from pathlib import Path

from agent.config import CACHE_DIR

log = logging.getLogger(__name__)

try:
    import faster_whisper as _fw

    _HAS_FASTER_WHISPER = True
except ImportError:
    _HAS_FASTER_WHISPER = False


def _model_dir() -> Path:
    return CACHE_DIR / "voice" / "stt"


def _model_path(model_name: str) -> Path:
    return _model_dir() / model_name


class FasterWhisperEngine:
    """STT engine backed by faster-whisper.

    Models are cached under ``~/.cache/hyprland-agent/voice/stt/<model>``.
    Raises ``RuntimeError`` when faster-whisper is not installed.
    """

    def __init__(
        self,
        model: str = "tiny",
        language: str | None = None,
        device: str = "auto",
        compute_type: str = "default",
    ) -> None:
        if not _HAS_FASTER_WHISPER:
            raise RuntimeError(
                "faster-whisper is required for speech-to-text. "
                "Install with: uv sync --extra voice  (or pip install hyprland-agent[voice])"
            )
        self._model_name = model
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._model: _fw.WhisperModel | None = None
        self._model_dir_value = _model_dir()

    @property
    def model_name(self) -> str:
        return self._model_name

    async def transcribe(self, audio_bytes: bytes, samplerate: int = 16000) -> str:
        self._lazy_load_model()
        if self._model is None:
            return ""
        import numpy as np

        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0
        segments, info = self._model.transcribe(
            samples,
            language=self._language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=500,
            ),
        )
        log.debug("STT detected language: %s (prob %.2f)", info.language, info.language_probability)
        texts: list[str] = []
        for seg in segments:
            texts.append(seg.text)
        return " ".join(texts).strip()

    def _lazy_load_model(self) -> None:
        if self._model is not None:
            return
        model_path = str(self._model_dir_value)
        os.makedirs(model_path, exist_ok=True)
        self._model = _fw.WhisperModel(
            self._model_name,
            device=self._device,
            compute_type=self._compute_type,
            download_root=model_path,
            cpu_threads=os.cpu_count() or 4,
            num_workers=1,
        )

    async def close(self) -> None:
        self._model = None
