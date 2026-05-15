"""Verify ClaudeBrain passes BrainContext to the API call."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from agent.awareness.working import WorkingMemory
from agent.awareness.world_context import WorldSnapshot
from agent.brain.claude import ClaudeBrain
from agent.brain.context import BrainContext
from agent.introspection.self_model import SelfModel
from agent.schemas import ScreenState


def _make_png(w: int = 200, h: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h)).save(buf, format="PNG")
    return buf.getvalue()


def _make_ctx(brain_name: str = "ClaudeBrain") -> BrainContext:
    return BrainContext(
        self_model=SelfModel(brain_name=brain_name),
        world=WorldSnapshot(
            active_window_class="foot",
            active_window_title="zsh",
            active_workspace_id=1,
            monitor_width=200,
            monitor_height=100,
            window_count=1,
            timestamp=0.0,
        ),
        working=WorkingMemory(),
    )


def _make_state() -> ScreenState:
    return ScreenState(
        screenshot_png=_make_png(),
        width=200,
        height=100,
        active_window=None,
        windows=[],
    )


@pytest.mark.asyncio
async def test_claude_brain_uses_system_prompt_from_ctx() -> None:
    ctx = _make_ctx()
    state = _make_state()
    expected_system = ctx.render_system_prompt()

    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        # Return a minimal response that ends the loop
        msg = SimpleNamespace(
            content=[],
            stop_reason="end_turn",
        )
        return msg

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = fake_create

    brain = ClaudeBrain(model="claude-test")

    with (
        patch("agent.brain.claude.anthropic_client", return_value=fake_client),
        patch(
            "agent.brain.claude.asyncio.to_thread",
            side_effect=lambda fn, **kw: fn(**kw),
        ),
    ):
        actions = await brain.decide(state, "test task", ctx)

    assert "system" in captured
    assert expected_system == captured["system"]
    assert actions == []


@pytest.mark.asyncio
async def test_claude_brain_includes_task_in_user_message() -> None:
    ctx = _make_ctx()
    state = _make_state()

    captured_messages: list = []

    def fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return SimpleNamespace(content=[], stop_reason="end_turn")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = fake_create

    brain = ClaudeBrain(model="claude-test")

    with (
        patch("agent.brain.claude.anthropic_client", return_value=fake_client),
        patch(
            "agent.brain.claude.asyncio.to_thread",
            side_effect=lambda fn, **kw: fn(**kw),
        ),
    ):
        await brain.decide(state, "open firefox", ctx)

    user_msg = captured_messages[0]
    text_blocks = [b for b in user_msg["content"] if b.get("type") == "text"]
    assert any("open firefox" in b["text"] for b in text_blocks)
