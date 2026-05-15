"""Tests for host diagnostics without leaking credentials."""

from __future__ import annotations

from pathlib import Path

from agent.config import AgentConfig, BrainConfig
from agent.diagnostics import Status, _provider_checks, _read_env_file


def test_read_env_file_parses_systemd_environment_file(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    env_file.write_text(
        """
# comment
OPENAI_API_KEY='sk-secret'
export OPENAI_MODEL="gpt-5.2"
IGNORED_LINE
"""
    )

    assert _read_env_file(env_file) == {
        "OPENAI_API_KEY": "sk-secret",
        "OPENAI_MODEL": "gpt-5.2",
    }


def test_provider_checks_use_env_file_without_leaking_secret(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / "env"
    env_file.write_text("OPENAI_API_KEY=sk-secret\nOPENAI_MODEL=gpt-5.2\n")
    config = AgentConfig(
        brain=BrainConfig(
            providers={
                "claude": False,
                "openai": True,
                "moonshot": False,
                "groq": False,
                "together": False,
                "zai": False,
                "qwen": False,
            }
        )
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr("agent.diagnostics.ENV_FILE_PATH", env_file)
    monkeypatch.setattr("agent.config.load_config", lambda: config)

    checks = _provider_checks()

    openai_key = next(check for check in checks if check.name == "OPENAI_API_KEY")
    openai_model = next(check for check in checks if check.name == "OPENAI_MODEL")
    rendered = "\n".join(check.message for check in checks)

    assert openai_key.status == Status.ok
    assert str(env_file) in openai_key.message
    assert openai_model.message == f"gpt-5.2 from {env_file}"
    assert "sk-secret" not in rendered
