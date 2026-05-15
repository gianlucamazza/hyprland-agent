"""Tests for LoopDetector."""

from __future__ import annotations

from types import SimpleNamespace

from agent.awareness.meta_cognition import LoopDetector


def _action(kind: str = "click", params: dict | None = None):
    ns = SimpleNamespace()
    ns.kind = SimpleNamespace()
    ns.kind.value = kind
    ns.params = params or {"x": 100, "y": 200}
    return ns


def test_no_stuck_below_threshold() -> None:
    d = LoopDetector(window=6, repeat_threshold=3)
    for _ in range(2):
        assert d.observe(_action()) is False


def test_stuck_at_threshold() -> None:
    d = LoopDetector(window=6, repeat_threshold=3)
    d.observe(_action())
    d.observe(_action())
    assert d.observe(_action()) is True


def test_different_actions_not_stuck() -> None:
    d = LoopDetector(window=6, repeat_threshold=3)
    d.observe(_action("click", {"x": 1, "y": 2}))
    d.observe(_action("click", {"x": 3, "y": 4}))
    assert d.observe(_action("click", {"x": 5, "y": 6})) is False


def test_different_kinds_not_stuck() -> None:
    d = LoopDetector(window=6, repeat_threshold=3)
    d.observe(_action("click"))
    d.observe(_action("dispatch"))
    assert d.observe(_action("focus_window")) is False


def test_window_evicts_old_entries() -> None:
    d = LoopDetector(window=3, repeat_threshold=3)
    # fill with different actions to push out the first
    d.observe(_action("click"))
    d.observe(_action("dispatch"))
    d.observe(_action("focus_window"))
    # Now add click again — the first click is no longer in window
    assert d.observe(_action("click")) is False


def test_reset_clears_history() -> None:
    d = LoopDetector(window=6, repeat_threshold=3)
    d.observe(_action())
    d.observe(_action())
    d.reset()
    assert d.observe(_action()) is False
