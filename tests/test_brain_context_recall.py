"""Tests for BrainContext preamble with populated recall."""

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


def _make_ctx(recall: list | None = None) -> BrainContext:
    return BrainContext(
        self_model=SelfModel(brain_name="TestBrain"),
        world=_make_world(),
        working=WorkingMemory(),
        recall=recall or [],
    )


def test_preamble_contains_recall_task() -> None:
    ctx = _make_ctx(
        recall=[
            {
                "task": "open ghostty",
                "outcome": "success",
                "summary": "1 actions: dispatch_hypr",
            }
        ]
    )
    preamble = ctx.render_user_preamble()
    assert "open ghostty" in preamble
    assert "Similar past tasks" in preamble


def test_preamble_shows_outcome() -> None:
    ctx = _make_ctx(
        recall=[{"task": "open firefox", "outcome": "success", "summary": "2 actions"}]
    )
    preamble = ctx.render_user_preamble()
    assert "success" in preamble


def test_recall_capped_at_3_in_preamble() -> None:
    recall = [
        {"task": f"task {i}", "outcome": "success", "summary": "done"}
        for i in range(10)
    ]
    ctx = _make_ctx(recall=recall)
    preamble = ctx.render_user_preamble()
    assert preamble.count("task ") == 3


def test_empty_recall_produces_no_similar_tasks_section() -> None:
    ctx = _make_ctx(recall=[])
    preamble = ctx.render_user_preamble()
    assert "Similar past tasks" not in preamble
