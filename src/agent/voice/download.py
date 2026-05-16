"""Model download utilities for voice subsystem.

Provides CLI-accessible functions to download Piper TTS models and
faster-whisper STT models.  Wake-word and VAD models are shipped with
their respective packages and downloaded automatically on first use.
"""

from __future__ import annotations

import logging
import tarfile
from pathlib import Path
from urllib.request import urlopen

from agent.config import CACHE_DIR

log = logging.getLogger(__name__)

PIPER_BASE = "https://github.com/rhasspy/piper/releases/download/v0.1/models"
TTS_DIR = CACHE_DIR / "voice" / "tts"
STT_DIR = CACHE_DIR / "voice" / "stt"

# faster-whisper models that can be pre-downloaded
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")


def _report(bytes_read: int, total: int) -> None:
    if total > 0:
        pct = bytes_read / total * 100
        print(
            f"\r  {bytes_read / 1024:.0f} / {total / 1024:.0f} KB ({pct:.0f}%)", end="", flush=True
        )


def download_piper(voice: str = "it_IT-paola-medium") -> Path:
    """Download a Piper TTS model from GitHub releases.

    Returns the path to the downloaded ``.onnx`` file.
    """
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = TTS_DIR / f"{voice}.onnx"
    json_path = TTS_DIR / f"{voice}.json"

    if onnx_path.exists() and json_path.exists():
        log.info("Piper model %s already cached at %s", voice, onnx_path)
        return onnx_path

    url = f"{PIPER_BASE}/{voice}.tar.gz"
    tar_path = TTS_DIR / f"{voice}.tar.gz"

    print(f"Downloading Piper model {voice}...")
    _download(url, tar_path)
    print(f"\nExtracting {tar_path.name}...")
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(path=TTS_DIR)
    tar_path.unlink()
    log.info("Piper model %s downloaded to %s", voice, onnx_path)
    return onnx_path


def download_stt(model: str = "tiny") -> Path:
    """Pre-download a faster-whisper model.

    The actual download is handled by ``faster-whisper``; this
    function triggers it and returns the model directory.
    """
    if model not in WHISPER_MODELS:
        log.warning("Unknown STT model %r — must be one of %s", model, WHISPER_MODELS)
    STT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from faster_whisper import WhisperModel

        print(f"Downloading faster-whisper model '{model}' (may take a while)...")
        WhisperModel(model, download_root=str(STT_DIR), cpu_threads=2, num_workers=1)
        log.info("STT model %s downloaded to %s", model, STT_DIR)
    except ImportError:
        log.error("faster-whisper is not installed — run: uv sync --extra voice")
    return STT_DIR


def _download(url: str, dest: Path) -> None:
    import ssl

    ctx = ssl.create_default_context()
    response = urlopen(url, context=ctx)
    total = int(response.headers.get("Content-Length", 0))
    with open(dest, "wb") as f:
        bytes_read = 0
        while True:
            chunk = response.read(8192)
            if not chunk:
                break
            f.write(chunk)
            bytes_read += len(chunk)
            _report(bytes_read, total)
    print()
