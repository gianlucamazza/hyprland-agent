"""Tests for token estimation, context compaction, and ContextConfig."""

from __future__ import annotations

from typing import Any

import pytest

from agent.brain._common import compact_messages, estimate_tokens
from agent.config import load_config

# ── estimate_tokens ────────────────────────────────────────────────────────────


def test_estimate_tokens_plain_text() -> None:
    messages = [{"role": "user", "content": "a" * 100}]
    # 100 chars / 4 per token + 4 overhead = 29
    assert estimate_tokens(messages) == 29


def test_estimate_tokens_empty_messages() -> None:
    assert estimate_tokens([]) == 0


def test_estimate_tokens_none_content() -> None:
    messages = [{"role": "assistant", "content": None}]
    # 4 overhead per message
    assert estimate_tokens(messages) == 4


def test_estimate_tokens_list_content_text_block() -> None:
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "hello world!"}],
        }
    ]
    # 12 chars / 4 = 3 tokens + 4 overhead = 7
    assert estimate_tokens(messages) == 7


def test_estimate_tokens_image_block() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "see image"},
                {"type": "image", "source": {"type": "base64", "data": "abc123"}},
            ],
        }
    ]
    # "see image" = 9/4=2 + image=500 + 4 overhead = 506
    assert estimate_tokens(messages) == 506


def test_estimate_tokens_image_url_block() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
            ],
        }
    ]
    # 500 tokens for image + 4 overhead = 504
    assert estimate_tokens(messages) == 504


def test_estimate_tokens_tool_result_string_content() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "content": "x" * 40},
            ],
        }
    ]
    # 40/4=10 + 4 overhead = 14
    assert estimate_tokens(messages) == 14


def test_estimate_tokens_tool_result_list_content() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": [{"type": "text", "text": "a" * 80}],
                },
            ],
        }
    ]
    # 80/4=20 + 4 overhead = 24
    assert estimate_tokens(messages) == 24


# ── compact_messages ───────────────────────────────────────────────────────────


def test_compact_messages_no_compaction_needed() -> None:
    messages = [{"role": "user", "content": "hi"}]
    result = compact_messages(messages, budget_tokens=999_999)
    assert result is messages  # same object, no copy


def test_compact_messages_single_message_unchanged() -> None:
    messages = [{"role": "user", "content": "a" * 999_999}]
    result = compact_messages(messages, budget_tokens=1)
    assert result == messages  # single message never compacted


def test_compact_messages_keeps_last_n_rounds() -> None:
    messages = [
        {"role": "user", "content": "round 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "round 2"},
        {"role": "assistant", "content": "reply 2"},
        {"role": "user", "content": "round 3"},
        {"role": "assistant", "content": "reply 3"},
        {"role": "user", "content": "round 4"},
    ]
    result = compact_messages(messages, keep_rounds=2, budget_tokens=1)
    # Should keep only the last 2 user-started rounds (round 3 + round 4)
    user_roles = [m for m in result if m["role"] == "user"]
    assert len(user_roles) == 2
    assert user_roles[0]["content"] == "round 3"
    assert user_roles[1]["content"] == "round 4"


def test_compact_messages_preserves_system_prompt() -> None:
    messages = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "round 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "round 2"},
        {"role": "assistant", "content": "reply 2"},
        {"role": "user", "content": "round 3"},
    ]
    result = compact_messages(messages, keep_rounds=1, budget_tokens=1)
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "you are helpful"


def test_compact_messages_no_system_prompt() -> None:
    messages = [
        {"role": "user", "content": "round 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "round 2"},
    ]
    result = compact_messages(messages, keep_rounds=1, budget_tokens=1)
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "round 2"


def test_compact_messages_all_rounds_kept_when_fewer_than_keep() -> None:
    messages = [
        {"role": "user", "content": "only round"},
        {"role": "assistant", "content": "reply"},
    ]
    result = compact_messages(messages, keep_rounds=3, budget_tokens=1)
    # All messages kept since there's only 1 round (<= keep_rounds)
    assert len(result) == 2


def test_compact_messages_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    messages = [
        {"role": "user", "content": "a" * 1000},
        {"role": "assistant", "content": "b" * 1000},
        {"role": "user", "content": "c" * 1000},
    ]
    with caplog.at_level("WARNING", logger="agent.brain._common"):
        compact_messages(messages, keep_rounds=1, budget_tokens=1)
    assert "Context compacted" in caplog.text


# ── ContextConfig ──────────────────────────────────────────────────────────────


def test_context_config_defaults(tmp_path: Any) -> None:
    config = load_config(tmp_path / "missing.yaml")
    assert config.context.budget_tokens == 160_000
    assert config.context.keep_rounds == 3


def test_context_config_from_yaml(tmp_path: Any) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
context:
  budget_tokens: 100000
  keep_rounds: 5
"""
    )
    config = load_config(path)
    assert config.context.budget_tokens == 100_000
    assert config.context.keep_rounds == 5


def test_context_config_invalid_type(tmp_path: Any) -> None:
    from agent.config import ConfigError

    path = tmp_path / "config.yaml"
    path.write_text(
        """
context: "not a mapping"
"""
    )
    with pytest.raises(ConfigError, match="context must be a mapping"):
        load_config(path)
