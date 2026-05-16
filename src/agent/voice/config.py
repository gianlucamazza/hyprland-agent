"""Strict loader for voice.yaml.

Full config loaded at voice sidecar startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent.config import CONFIG_DIR, ConfigError

VOICE_CONFIG_PATH = CONFIG_DIR / "voice.yaml"

_KNOWN_KEYS = frozenset(
    {"tts", "audio", "templates", "privacy", "stt", "ptt", "wakeword", "vad", "handsfree"}
)


@dataclass(frozen=True)
class TtsConfig:
    engine: str = "piper"
    voice: str = "it_IT-paola-medium"
    speed: float = 1.0


@dataclass(frozen=True)
class AudioConfig:
    output_device: str = "default"
    sample_rate: int = 22050


@dataclass(frozen=True)
class TemplateConfig:
    run_started: str = "Avvio: {task}"
    run_completed: str = "Fatto"
    run_errored: str = "Errore: {error_short}"
    run_aborted: str = "Annullato"


@dataclass(frozen=True)
class PrivacyConfig:
    redact_patterns: tuple[str, ...] = ("token", "secret", "password", "api[_-]?key")


@dataclass(frozen=True)
class SttConfig:
    engine: str = "faster-whisper"
    model: str = "tiny"
    language: str | None = None
    device: str = "auto"
    compute_type: str = "default"


@dataclass(frozen=True)
class PttConfig:
    enabled: bool = False
    socket: str = ""
    record_timeout: float = 10.0
    silence_seconds: float = 1.5
    brain: str = "auto"


@dataclass(frozen=True)
class WakewordConfig:
    engine: str = "openwakeword"
    model: str = "hey_computer"
    sensitivity: float = 0.5
    wake_words: tuple[str, ...] = ("computer",)


@dataclass(frozen=True)
class VadConfig:
    engine: str = "silero"
    threshold: float = 0.5
    min_speech_duration_ms: int = 250


@dataclass(frozen=True)
class HandsfreeConfig:
    enabled: bool = False
    record_timeout: float = 10.0
    brain: str = "auto"


@dataclass(frozen=True)
class VoiceConfig:
    tts: TtsConfig = field(default_factory=TtsConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    templates: TemplateConfig = field(default_factory=TemplateConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    ptt: PttConfig = field(default_factory=PttConfig)
    wakeword: WakewordConfig = field(default_factory=WakewordConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    handsfree: HandsfreeConfig = field(default_factory=HandsfreeConfig)


# ---------------------------------------------------------------------------
# Parsers per subsection
# ---------------------------------------------------------------------------


def _tts_config(data: dict[str, Any]) -> TtsConfig:
    raw = data.get("tts", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.tts must be a mapping")
    return TtsConfig(
        engine=str(raw.get("engine", "piper")),
        voice=str(raw.get("voice", "it_IT-paola-medium")),
        speed=float(raw.get("speed", 1.0)),
    )


def _audio_config(data: dict[str, Any]) -> AudioConfig:
    raw = data.get("audio", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.audio must be a mapping")
    return AudioConfig(
        output_device=str(raw.get("output_device", "default")),
        sample_rate=int(raw.get("sample_rate", 22050)),
    )


def _templates_config(data: dict[str, Any]) -> TemplateConfig:
    raw = data.get("templates", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.templates must be a mapping")
    return TemplateConfig(
        run_started=str(raw.get("run_started", "Avvio: {task}")),
        run_completed=str(raw.get("run_completed", "Fatto")),
        run_errored=str(raw.get("run_errored", "Errore: {error_short}")),
        run_aborted=str(raw.get("run_aborted", "Annullato")),
    )


def _privacy_config(data: dict[str, Any]) -> PrivacyConfig:
    raw = data.get("privacy", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.privacy must be a mapping")
    raw_patterns = raw.get("redact_patterns", ("token", "secret", "password", "api[_-]?key"))
    if not isinstance(raw_patterns, list | tuple):
        raise ConfigError("voice.privacy.redact_patterns must be a list")
    return PrivacyConfig(redact_patterns=tuple(str(p) for p in raw_patterns))


def _stt_config(data: dict[str, Any]) -> SttConfig:
    raw = data.get("stt", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.stt must be a mapping")
    language = raw.get("language")
    if language is not None:
        language = str(language)
    return SttConfig(
        engine=str(raw.get("engine", "faster-whisper")),
        model=str(raw.get("model", "tiny")),
        language=language,
        device=str(raw.get("device", "auto")),
        compute_type=str(raw.get("compute_type", "default")),
    )


def _ptt_config(data: dict[str, Any]) -> PttConfig:
    raw = data.get("ptt", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.ptt must be a mapping")
    raw_socket = raw.get("socket", "")
    if not raw_socket:
        raw_socket = os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
            "hyprland-agent-voice-ptt.sock",
        )
    return PttConfig(
        enabled=bool(raw.get("enabled", False)),
        socket=str(raw_socket),
        record_timeout=float(raw.get("record_timeout", 10.0)),
        silence_seconds=float(raw.get("silence_seconds", 1.5)),
        brain=str(raw.get("brain", "auto")),
    )


def _wakeword_config(data: dict[str, Any]) -> WakewordConfig:
    raw = data.get("wakeword", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.wakeword must be a mapping")
    raw_words = raw.get("wake_words", ("computer",))
    if isinstance(raw_words, str):
        raw_words = (raw_words,)
    return WakewordConfig(
        engine=str(raw.get("engine", "openwakeword")),
        model=str(raw.get("model", "hey_computer")),
        sensitivity=float(raw.get("sensitivity", 0.5)),
        wake_words=tuple(str(w) for w in raw_words),
    )


def _vad_config(data: dict[str, Any]) -> VadConfig:
    raw = data.get("vad", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.vad must be a mapping")
    return VadConfig(
        engine=str(raw.get("engine", "silero")),
        threshold=float(raw.get("threshold", 0.5)),
        min_speech_duration_ms=int(raw.get("min_speech_duration_ms", 250)),
    )


def _handsfree_config(data: dict[str, Any]) -> HandsfreeConfig:
    raw = data.get("handsfree", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("voice.handsfree must be a mapping")
    return HandsfreeConfig(
        enabled=bool(raw.get("enabled", False)),
        record_timeout=float(raw.get("record_timeout", 10.0)),
        brain=str(raw.get("brain", "auto")),
    )


# ---------------------------------------------------------------------------
# Top-level loader
# ---------------------------------------------------------------------------


def load_voice_config(path: Path = VOICE_CONFIG_PATH) -> VoiceConfig:
    if not path.exists():
        return VoiceConfig()
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError("voice config must be a YAML mapping at the top level")
    for key in data:
        if key not in _KNOWN_KEYS:
            raise ConfigError(f"voice.{key!r} is not a recognised key")
    return VoiceConfig(
        tts=_tts_config(data),
        audio=_audio_config(data),
        templates=_templates_config(data),
        privacy=_privacy_config(data),
        stt=_stt_config(data),
        ptt=_ptt_config(data),
        wakeword=_wakeword_config(data),
        vad=_vad_config(data),
        handsfree=_handsfree_config(data),
    )
