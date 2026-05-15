"""Tests for OpenAICompatibleBrain, build_brain(), and all provider aliases."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from agent.brain.openai_brain import (
    _SCALE,
    OpenAICompatibleBrain,
    _call_tool,
    build_brain,
)
from agent.schemas import ActionKind


def _make_png(w: int = 1920, h: int = 1080) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


# ── _call_tool unit tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_tool_left_click_scales_coords() -> None:
    scale = 1.0 / _SCALE  # 2.0
    _, actions = await _call_tool("left_click", {"x": 100, "y": 200}, scale=scale)
    assert actions[0].kind == ActionKind.mouse_move
    assert actions[0].params == {"x": 200, "y": 400}
    assert actions[1].kind == ActionKind.click
    assert actions[1].params["button"] == "left"


@pytest.mark.asyncio
async def test_call_tool_right_click() -> None:
    _, actions = await _call_tool("right_click", {"x": 10, "y": 20}, scale=2.0)
    assert actions[1].params["button"] == "right"


@pytest.mark.asyncio
async def test_call_tool_middle_click() -> None:
    _, actions = await _call_tool("middle_click", {"x": 10, "y": 20}, scale=2.0)
    assert actions[1].params["button"] == "middle"


@pytest.mark.asyncio
async def test_call_tool_double_click() -> None:
    _, actions = await _call_tool("double_click", {"x": 50, "y": 50}, scale=2.0)
    assert actions[0].kind == ActionKind.mouse_move
    assert actions[0].params == {"x": 100, "y": 100}
    assert len(actions) == 3
    assert all(a.kind == ActionKind.click for a in actions[1:])


@pytest.mark.asyncio
async def test_call_tool_scroll_down() -> None:
    _, actions = await _call_tool(
        "scroll", {"x": 100, "y": 200, "direction": "down", "amount": 5}, scale=2.0
    )
    assert actions[0].kind == ActionKind.mouse_move
    assert actions[0].params == {"x": 200, "y": 400}
    assert actions[1].kind == ActionKind.scroll
    assert actions[1].params == {"amount": 5, "horizontal": False}


@pytest.mark.asyncio
async def test_call_tool_scroll_up() -> None:
    _, actions = await _call_tool(
        "scroll", {"x": 0, "y": 0, "direction": "up", "amount": 3}, scale=1.0
    )
    assert actions[1].params["amount"] == -3


@pytest.mark.asyncio
async def test_call_tool_scroll_horizontal() -> None:
    _, actions = await _call_tool(
        "scroll", {"x": 0, "y": 0, "direction": "left", "amount": 2}, scale=1.0
    )
    assert actions[1].params == {"amount": -2, "horizontal": True}


@pytest.mark.asyncio
async def test_call_tool_type_text() -> None:
    _, actions = await _call_tool("type_text", {"text": "hello"}, scale=1.0)
    assert actions[0].kind == ActionKind.type_text
    assert actions[0].params["text"] == "hello"


@pytest.mark.asyncio
async def test_call_tool_key() -> None:
    _, actions = await _call_tool("key", {"combo": "ctrl+c"}, scale=1.0)
    assert actions[0].kind == ActionKind.key
    assert actions[0].params["combo"] == "ctrl+c"


@pytest.mark.asyncio
async def test_call_tool_terminal_command() -> None:
    _, actions = await _call_tool(
        "terminal_command",
        {"command": "printf %s hello", "hold_s": 3},
        scale=1.0,
    )
    assert actions[0].kind == ActionKind.terminal_command
    assert actions[0].params["command"] == "printf %s hello"
    assert actions[0].params["hold_s"] == 3


@pytest.mark.asyncio
async def test_call_tool_hypr_actions_are_queued_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = AsyncMock()
    monkeypatch.setattr("agent.brain.openai_brain.hypr.dispatch", dispatch)

    _, focus_actions = await _call_tool("focus_window", {"address": "0xabc"}, scale=1.0)
    _, dispatch_actions = await _call_tool("dispatch_hypr", {"cmd": "workspace 2"}, scale=1.0)

    dispatch.assert_not_awaited()
    assert focus_actions[0].kind == ActionKind.focus_window
    assert dispatch_actions[0].kind == ActionKind.dispatch


@pytest.mark.asyncio
async def test_call_tool_unknown() -> None:
    text, actions = await _call_tool("nonexistent", {}, scale=1.0)
    assert text == "unknown tool"
    assert actions == []


# ── build_brain() — all providers ───────────────────────────────────────────


@pytest.mark.parametrize(
    "provider, env_key, expected_base",
    [
        ("openai", "OPENAI_API_KEY", None),  # None → OpenAI default base_url
        ("moonshot", "MOONSHOT_API_KEY", "moonshot"),
        ("groq", "GROQ_API_KEY", "groq.com"),
        ("together", "TOGETHER_API_KEY", "together.xyz"),
        ("zai", "ZAI_API_KEY", "z.ai"),
        ("qwen", "DASHSCOPE_API_KEY", "dashscope"),
    ],
)
def test_build_brain_base_url(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    env_key: str,
    expected_base: str | None,
) -> None:
    monkeypatch.setenv(env_key, "test-key")
    brain = build_brain(provider)
    assert isinstance(brain, OpenAICompatibleBrain)
    if expected_base is None:
        assert brain._client.base_url is None or "openai" in str(brain._client.base_url)
    else:
        assert expected_base in str(brain._client.base_url)


@pytest.mark.parametrize(
    "provider, env_key, model_env, default_prefix",
    [
        ("openai", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt"),
        ("moonshot", "MOONSHOT_API_KEY", "MOONSHOT_MODEL", "kimi"),
        ("groq", "GROQ_API_KEY", "GROQ_MODEL", "meta-llama"),
        ("together", "TOGETHER_API_KEY", "TOGETHER_MODEL", "meta-llama"),
        ("zai", "ZAI_API_KEY", "ZAI_MODEL", "glm"),
        ("qwen", "DASHSCOPE_API_KEY", "QWEN_MODEL", "qwen"),
    ],
)
def test_build_brain_default_models(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    env_key: str,
    model_env: str,
    default_prefix: str,
) -> None:
    monkeypatch.setenv(env_key, "test-key")
    monkeypatch.delenv(model_env, raising=False)
    brain = build_brain(provider)
    assert brain._model.startswith(default_prefix)


def test_build_brain_respects_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gk-test")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b")
    brain = build_brain("groq")
    assert brain._model == "llama-3.3-70b"


def test_build_brain_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY not set"):
        build_brain("groq")


# ── router integration ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "alias, env_key, expected_base",
    [
        ("openai", "OPENAI_API_KEY", None),
        ("gpt", "OPENAI_API_KEY", None),
        ("kimi", "MOONSHOT_API_KEY", "moonshot"),
        ("moonshot", "MOONSHOT_API_KEY", "moonshot"),
        ("k2", "MOONSHOT_API_KEY", "moonshot"),
        ("groq", "GROQ_API_KEY", "groq.com"),
        ("together", "TOGETHER_API_KEY", "together.xyz"),
        ("togetherai", "TOGETHER_API_KEY", "together.xyz"),
        ("zai", "ZAI_API_KEY", "z.ai"),
        ("glm", "ZAI_API_KEY", "z.ai"),
        ("qwen", "DASHSCOPE_API_KEY", "dashscope"),
        ("dashscope", "DASHSCOPE_API_KEY", "dashscope"),
    ],
)
def test_router_aliases(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    env_key: str,
    expected_base: str | None,
) -> None:
    from agent.brain.router import get_brain
    from agent.config import AgentConfig, BrainConfig

    providers = {
        "claude": True,
        "openai": True,
        "moonshot": True,
        "groq": True,
        "together": True,
        "zai": True,
        "qwen": True,
    }
    monkeypatch.setattr(
        "agent.brain.router.load_config",
        lambda: AgentConfig(brain=BrainConfig(providers=providers)),
    )
    monkeypatch.setenv(env_key, "test")
    brain = get_brain(alias)
    assert isinstance(brain, OpenAICompatibleBrain)
    if expected_base is None:
        assert brain._client.base_url is None or "openai" in str(brain._client.base_url)
    else:
        assert expected_base in str(brain._client.base_url)
