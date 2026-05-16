"""Unit tests for the shared computer_actions helper."""

from __future__ import annotations

import pytest

from agent.brain._action_map import computer_actions
from agent.schemas import ActionKind


def test_screenshot():
    acts = computer_actions("screenshot")
    assert len(acts) == 1
    assert acts[0].kind == ActionKind.screenshot


def test_left_click():
    acts = computer_actions("left_click", x=100, y=200)
    assert acts[0].kind == ActionKind.mouse_move
    assert acts[0].params == {"x": 100, "y": 200}
    assert acts[1].kind == ActionKind.click
    assert acts[1].params == {"button": "left"}


def test_right_click():
    acts = computer_actions("right_click", x=10, y=20)
    assert acts[1].params == {"button": "right"}


def test_middle_click():
    acts = computer_actions("middle_click", x=10, y=20)
    assert acts[1].params == {"button": "middle"}


def test_double_click():
    acts = computer_actions("double_click", x=50, y=60)
    assert len(acts) == 3
    assert acts[0].kind == ActionKind.mouse_move
    assert acts[1].kind == ActionKind.click
    assert acts[2].kind == ActionKind.click


def test_mouse_move():
    acts = computer_actions("mouse_move", x=300, y=400)
    assert len(acts) == 1
    assert acts[0].kind == ActionKind.mouse_move
    assert acts[0].params == {"x": 300, "y": 400}


def test_type_claude_verb():
    acts = computer_actions("type", text="hello")
    assert len(acts) == 1
    assert acts[0].kind == ActionKind.type_text
    assert acts[0].params == {"text": "hello"}


def test_type_openai_verb():
    acts = computer_actions("type_text", text="world")
    assert acts[0].kind == ActionKind.type_text
    assert acts[0].params == {"text": "world"}


def test_key():
    acts = computer_actions("key", combo="ctrl+c")
    assert len(acts) == 1
    assert acts[0].kind == ActionKind.key
    assert acts[0].params == {"combo": "ctrl+c"}


@pytest.mark.parametrize(
    "direction,amount,expected_signed,horizontal",
    [
        ("down", 3, 3, False),
        ("up", 3, -3, False),
        ("left", 5, -5, True),
        ("right", 5, 5, True),
    ],
)
def test_scroll(direction, amount, expected_signed, horizontal):
    acts = computer_actions("scroll", x=100, y=200, direction=direction, amount=amount)
    assert len(acts) == 2
    assert acts[0].kind == ActionKind.mouse_move
    assert acts[1].kind == ActionKind.scroll
    assert acts[1].params["amount"] == expected_signed
    assert acts[1].params["horizontal"] == horizontal


def test_coordinate_scaling():
    acts = computer_actions("left_click", x=100, y=200, scale_x=2.0, scale_y=0.5)
    assert acts[0].params == {"x": 200, "y": 100}


def test_unknown_verb_returns_empty():
    acts = computer_actions("nonexistent_verb")
    assert acts == []
