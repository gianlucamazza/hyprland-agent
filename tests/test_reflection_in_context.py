"""Tests that negative reflections appear in BrainContext preamble."""

from __future__ import annotations

from agent.awareness.working import WorkingMemory
from agent.awareness.world_context import WorldSnapshot
from agent.brain.context import BrainContext
from agent.introspection.self_model import SelfModel


def _make_world() -> WorldSnapshot:
    return WorldSnapshot(
        active_window_class="foot",
        active_window_title="zsh",
        active_workspace_id=1,
        monitor_width=1920,
        monitor_height=1080,
        window_count=1,
        timestamp=0.0,
    )


def _make_ctx(negative_reflections: list[str] | None = None) -> BrainContext:
    return BrainContext(
        self_model=SelfModel(brain_name="TestBrain"),
        world=_make_world(),
        working=WorkingMemory(),
        negative_reflections=negative_reflections or [],
    )


def test_preamble_contains_lesson() -> None:
    ctx = _make_ctx(negative_reflections=["Do not click random spots on the desktop."])
    preamble = ctx.render_user_preamble()
    assert "Lessons from past failures" in preamble
    assert "Do not click random spots" in preamble


def test_preamble_empty_without_reflections() -> None:
    ctx = _make_ctx()
    preamble = ctx.render_user_preamble()
    assert "Lessons from past failures" not in preamble


def test_preamble_caps_reflections_at_3() -> None:
    ctx = _make_ctx(negative_reflections=[f"lesson {i}" for i in range(10)])
    preamble = ctx.render_user_preamble()
    assert preamble.count("lesson ") == 3
