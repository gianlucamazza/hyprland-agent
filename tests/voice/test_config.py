"""Tests for voice config parsing."""

from __future__ import annotations

from agent.config import ConfigError, VoiceCoreConfig, load_config


def test_voice_disabled_by_default() -> None:
    cfg = load_config()
    assert cfg.integrations.voice == VoiceCoreConfig(enabled=False)


def test_voice_known_key_does_not_raise() -> None:
    """integrations.voice is a recognised key."""
    from agent.config import _integrations_config

    result = _integrations_config({"integrations": {"voice": {"enabled": True}}})
    assert result.voice == VoiceCoreConfig(enabled=True)


def test_voice_non_mapping_raises() -> None:
    import pytest

    from agent.config import _integrations_config

    with pytest.raises(ConfigError, match="integrations.voice must be a mapping"):
        _integrations_config({"integrations": {"voice": "invalid"}})


# ---------------------------------------------------------------------------
# voice.yaml loader tests
# ---------------------------------------------------------------------------


def test_load_voice_config_defaults() -> None:
    from agent.voice.config import load_voice_config

    cfg = load_voice_config()
    assert cfg.tts.engine == "piper"
    assert cfg.tts.voice == "it_IT-paola-medium"
    assert cfg.templates.run_started == "Avvio: {task}"
    assert cfg.templates.run_completed == "Fatto"


def test_load_voice_config_missing_file_returns_defaults(tmp_path) -> None:
    from agent.voice.config import VoiceConfig, load_voice_config

    missing = tmp_path / "nonexistent.yaml"
    cfg = load_voice_config(missing)
    assert isinstance(cfg, VoiceConfig)
    assert cfg.tts.engine == "piper"


def test_load_voice_config_parses_yaml(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("""
tts:
  engine: piper
  voice: it_IT-paola-medium
  speed: 1.2
templates:
  run_started: "Partito: {task}"
  run_completed: "Completato"
  run_errored: "Fallito: {error_short}"
  run_aborted: "Cancellato"
""")
    cfg = load_voice_config(path)
    assert cfg.tts.speed == 1.2
    assert cfg.templates.run_started == "Partito: {task}"
    assert cfg.templates.run_completed == "Completato"
    assert cfg.templates.run_errored == "Fallito: {error_short}"
    assert cfg.templates.run_aborted == "Cancellato"


def test_load_voice_config_unknown_key_raises(tmp_path) -> None:
    import pytest

    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("unknown_key: true\n")
    with pytest.raises(ConfigError, match="voice\\.'unknown_key'"):  # noqa: PT012
        load_voice_config(path)


def test_load_voice_config_tts_non_mapping_raises(tmp_path) -> None:
    import pytest

    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("tts: not_a_mapping\n")
    with pytest.raises(ConfigError, match="voice.tts must be a mapping"):
        load_voice_config(path)


def test_load_voice_config_privacy_redact_patterns(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("""
privacy:
  redact_patterns:
    - mykey
    - another_key
""")
    cfg = load_voice_config(path)
    assert "mykey" in cfg.privacy.redact_patterns
    assert "another_key" in cfg.privacy.redact_patterns


# ---------------------------------------------------------------------------
# STT config tests
# ---------------------------------------------------------------------------


def test_stt_config_defaults() -> None:
    from agent.voice.config import load_voice_config

    cfg = load_voice_config()
    assert cfg.stt.engine == "faster-whisper"
    assert cfg.stt.model == "tiny"
    assert cfg.stt.language is None
    assert cfg.stt.device == "auto"
    assert cfg.stt.compute_type == "default"


def test_stt_config_parsed_from_yaml(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("""
stt:
  engine: faster-whisper
  model: base
  language: it
  device: cpu
  compute_type: int8
""")
    cfg = load_voice_config(path)
    assert cfg.stt.model == "base"
    assert cfg.stt.language == "it"
    assert cfg.stt.device == "cpu"
    assert cfg.stt.compute_type == "int8"


def test_stt_config_non_mapping_raises(tmp_path) -> None:
    import pytest

    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("stt: not_a_mapping\n")
    with pytest.raises(ConfigError, match="voice.stt must be a mapping"):
        load_voice_config(path)


# ---------------------------------------------------------------------------
# PTT config tests
# ---------------------------------------------------------------------------


def test_ptt_config_defaults() -> None:
    from agent.voice.config import load_voice_config

    cfg = load_voice_config()
    assert cfg.ptt.enabled is False
    assert cfg.ptt.record_timeout == 10.0
    assert cfg.ptt.silence_seconds == 1.5
    assert cfg.ptt.brain == "auto"


def test_ptt_config_parsed_from_yaml(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("""
ptt:
  enabled: true
  record_timeout: 5.0
  silence_seconds: 2.0
  brain: claude
""")
    cfg = load_voice_config(path)
    assert cfg.ptt.enabled is True
    assert cfg.ptt.record_timeout == 5.0
    assert cfg.ptt.silence_seconds == 2.0
    assert cfg.ptt.brain == "claude"


def test_ptt_config_non_mapping_raises(tmp_path) -> None:
    import pytest

    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("ptt: enabled\n")
    with pytest.raises(ConfigError, match="voice.ptt must be a mapping"):
        load_voice_config(path)


# ---------------------------------------------------------------------------
# Wakeword config tests
# ---------------------------------------------------------------------------


def test_wakeword_config_defaults() -> None:
    from agent.voice.config import load_voice_config

    cfg = load_voice_config()
    assert cfg.wakeword.engine == "openwakeword"
    assert cfg.wakeword.sensitivity == 0.5
    assert cfg.wakeword.wake_words == ("computer",)


def test_wakeword_config_parsed_from_yaml(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("""
wakeword:
  sensitivity: 0.7
  wake_words:
    - computer
    - alexa
""")
    cfg = load_voice_config(path)
    assert cfg.wakeword.sensitivity == 0.7
    assert cfg.wakeword.wake_words == ("computer", "alexa")


def test_wakeword_config_single_word_string(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("wakeword:\n  wake_words: computer\n")
    cfg = load_voice_config(path)
    assert cfg.wakeword.wake_words == ("computer",)


def test_wakeword_config_non_mapping_raises(tmp_path) -> None:
    import pytest

    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("wakeword: not_a_mapping\n")
    with pytest.raises(ConfigError, match="voice.wakeword must be a mapping"):
        load_voice_config(path)


# ---------------------------------------------------------------------------
# VAD config tests
# ---------------------------------------------------------------------------


def test_vad_config_defaults() -> None:
    from agent.voice.config import load_voice_config

    cfg = load_voice_config()
    assert cfg.vad.engine == "silero"
    assert cfg.vad.threshold == 0.5
    assert cfg.vad.min_speech_duration_ms == 250


def test_vad_config_parsed_from_yaml(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("""
vad:
  threshold: 0.7
  min_speech_duration_ms: 300
""")
    cfg = load_voice_config(path)
    assert cfg.vad.threshold == 0.7
    assert cfg.vad.min_speech_duration_ms == 300


def test_vad_config_non_mapping_raises(tmp_path) -> None:
    import pytest

    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("vad: not_a_mapping\n")
    with pytest.raises(ConfigError, match="voice.vad must be a mapping"):
        load_voice_config(path)


# ---------------------------------------------------------------------------
# Handsfree config tests
# ---------------------------------------------------------------------------


def test_handsfree_config_defaults() -> None:
    from agent.voice.config import load_voice_config

    cfg = load_voice_config()
    assert cfg.handsfree.enabled is False
    assert cfg.handsfree.record_timeout == 10.0
    assert cfg.handsfree.brain == "auto"


def test_handsfree_config_parsed_from_yaml(tmp_path) -> None:
    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("""
handsfree:
  enabled: true
  record_timeout: 15.0
  brain: claude
""")
    cfg = load_voice_config(path)
    assert cfg.handsfree.enabled is True
    assert cfg.handsfree.record_timeout == 15.0
    assert cfg.handsfree.brain == "claude"


def test_handsfree_config_non_mapping_raises(tmp_path) -> None:
    import pytest

    from agent.voice.config import load_voice_config

    path = tmp_path / "voice.yaml"
    path.write_text("handsfree: enabled\n")
    with pytest.raises(ConfigError, match="voice.handsfree must be a mapping"):
        load_voice_config(path)
