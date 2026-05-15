"""Verify OpenAICompatibleBrain passes BrainContext to the API call."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from agent.awareness.working import WorkingMemory
from agent.awareness.world_context import WorldSnapshot
from agent.brain.context import BrainContext
from agent.brain.openai_brain import OpenAICompatibleBrain
from agent.introspection.self_model import SelfModel
from agent.schemas import ScreenState


def _make_png(w: int = 200, h: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h)).save(buf, format="PNG")
    return buf.getvalue()


def _make_ctx() -> BrainContext:
    return BrainContext(
        self_model=SelfModel(brain_name="OpenAICompatibleBrain"),
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


def _fake_response(tool_calls=None) -> SimpleNamespace:
    msg = SimpleNamespace(tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.mark.asyncio
async def test_openai_brain_uses_system_prompt_from_ctx() -> None:
    ctx = _make_ctx()
    state = _make_state()
    expected_fragment = "Agent self-model"  # from SelfModel.render_for_prompt()

    captured_messages: list = []

    async def fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return _fake_response()

    brain = OpenAICompatibleBrain(api_key="test", model="gpt-test")
    brain._client.chat.completions.create = fake_create  # type: ignore[method-assign]

    await brain.decide(state, "test task", ctx)

    system_msgs = [m for m in captured_messages if m.get("role") == "system"]
    assert system_msgs, "no system message found"
    assert expected_fragment in system_msgs[0]["content"]


@pytest.mark.asyncio
async def test_openai_brain_includes_task_in_user_message() -> None:
    ctx = _make_ctx()
    state = _make_state()

    captured_messages: list = []

    async def fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return _fake_response()

    brain = OpenAICompatibleBrain(api_key="test", model="gpt-test")
    brain._client.chat.completions.create = fake_create  # type: ignore[method-assign]

    await brain.decide(state, "open ghostty", ctx)

    user_msgs = [m for m in captured_messages if m.get("role") == "user"]
    assert user_msgs
    content = user_msgs[0]["content"]
    text_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
    assert any("open ghostty" in p["text"] for p in text_parts)
