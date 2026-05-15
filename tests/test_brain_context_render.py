"""Tests for BrainContext rendering."""

from __future__ import annotations

from agent.awareness.working import WorkingMemory
from agent.awareness.world_context import WorldSnapshot
from agent.brain.context import BrainContext
from agent.introspection.self_model import SelfModel


def _make_ctx(brain_name: str = "TestBrain", recall: list | None = None) -> BrainContext:
    sm = SelfModel(brain_name=brain_name)
    world = WorldSnapshot(
        active_window_class="foot",
        active_window_title="zsh",
        active_workspace_id=1,
        monitor_width=1920,
        monitor_height=1080,
        window_count=2,
        timestamp=0.0,
    )
    working = WorkingMemory()
    return BrainContext(
        self_model=sm,
        world=world,
        working=working,
        recall=recall or [],
    )


def test_render_system_prompt_contains_self_model() -> None:
    ctx = _make_ctx("ClaudeBrain")
    prompt = ctx.render_system_prompt()
    assert "ClaudeBrain" in prompt
    assert "terminal_command" in prompt


def test_render_system_prompt_contains_world_context() -> None:
    ctx = _make_ctx()
    prompt = ctx.render_system_prompt()
    assert "foot" in prompt
    assert "1920" in prompt


def test_render_user_preamble_empty_by_default() -> None:
    ctx = _make_ctx()
    preamble = ctx.render_user_preamble()
    assert preamble == ""


def test_render_user_preamble_with_working_memory() -> None:
    ctx = _make_ctx()
    ctx.working.record("key", {"combo": "ctrl+c"})
    preamble = ctx.render_user_preamble()
    assert "Actions taken" in preamble
    assert "key" in preamble


def test_render_user_preamble_with_recall() -> None:
    ctx = _make_ctx(
        recall=[
            {
                "task": "open firefox",
                "outcome": "success",
                "summary": "dispatched workspace 2",
            }
        ]
    )
    preamble = ctx.render_user_preamble()
    assert "Similar past tasks" in preamble
    assert "open firefox" in preamble


def test_render_user_preamble_with_negative_reflections() -> None:
    ctx = _make_ctx()
    ctx.negative_reflections = ["Do not type into the terminal directly."]
    preamble = ctx.render_user_preamble()
    assert "Lessons from past failures" in preamble
    assert "Do not type" in preamble


def test_recall_capped_at_3() -> None:
    episodes = [{"task": f"task {i}", "outcome": "success", "summary": "done"} for i in range(10)]
    ctx = _make_ctx(recall=episodes)
    preamble = ctx.render_user_preamble()
    assert preamble.count("task ") == 3
