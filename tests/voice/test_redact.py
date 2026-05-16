"""Tests for voice redaction."""

from __future__ import annotations

from agent.voice.redact import redact_for_tts


def test_openai_key_redacted() -> None:
    result = redact_for_tts("my key is sk-proj-ABC123def456ghi789jkl012")
    assert "[REDACTED]" in result
    assert "sk-proj" not in result


def test_base64_token_redacted() -> None:
    token = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH=="
    result = redact_for_tts(f"token={token}")
    assert "[REDACTED]" in result


def test_home_path_redacted() -> None:
    result = redact_for_tts("file in /home/user/.ssh/id_rsa")
    assert "[REDACTED]" in result
    assert "/home/user" not in result


def test_tilde_path_redacted() -> None:
    result = redact_for_tts("config in ~/.config/secret.yaml")
    assert "[REDACTED]" in result
    assert "~/.config" not in result


def test_keyword_value_redacted() -> None:
    result = redact_for_tts("token=abc123", keyword_patterns=("token",))
    assert "token=[REDACTED]" in result
    assert "abc123" not in result


def test_multiple_keyword_values_redacted() -> None:
    result = redact_for_tts(
        "password=secret123 and api_key=xyz789",
        keyword_patterns=("secret", "password", "api[_-]?key"),
    )
    assert "password=[REDACTED]" in result
    assert "api_key=[REDACTED]" in result
    assert "secret123" not in result
    assert "xyz789" not in result


def test_clean_text_passes_through() -> None:
    text = "Ciao mondo, tutto bene!"
    result = redact_for_tts(text)
    assert result == text


def test_empty_text() -> None:
    assert redact_for_tts("") == ""


def test_no_keyword_patterns_does_not_change_text() -> None:
    text = "questo è un token di prova"
    result = redact_for_tts(text)
    assert "token" in result
