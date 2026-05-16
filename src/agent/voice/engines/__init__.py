"""Voice engine protocols and API version.

Each engine implements one of the protocols below.
Built-in engines are loaded via entry points (future).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

VOICE_API_VERSION = "1.0"


@runtime_checkable
class TtsEngine(Protocol):
    """Synthesise text to speech and play it."""

    async def say(self, text: str) -> None: ...

    async def stop(self) -> None:
        """Stop playback immediately (barge-in support)."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class SttEngine(Protocol):
    """Transcribe PCM audio to text."""

    async def transcribe(self, audio_bytes: bytes, samplerate: int = 16000) -> str: ...

    async def close(self) -> None: ...
