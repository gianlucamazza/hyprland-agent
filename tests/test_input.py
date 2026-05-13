"""Unit tests for input key-combo arg builder."""

from __future__ import annotations

import pytest

from agent.tools.input import _build_key_args


def test_single_key() -> None:
    assert _build_key_args("a") == ["-P", "a"]


def test_ctrl_c() -> None:
    args = _build_key_args("ctrl+c")
    assert args == ["-M", "ctrl", "-P", "c", "-m", "ctrl"]


def test_ctrl_shift_c() -> None:
    args = _build_key_args("ctrl+shift+c")
    assert args == ["-M", "ctrl", "-M", "shift", "-P", "c", "-m", "shift", "-m", "ctrl"]


def test_super_normalised() -> None:
    args = _build_key_args("super+l")
    assert args == ["-M", "super", "-P", "l", "-m", "super"]


def test_meta_alias() -> None:
    args = _build_key_args("meta+tab")
    assert args == ["-M", "super", "-P", "Tab", "-m", "super"]


@pytest.mark.parametrize(
    "alias, x11",
    [
        ("enter", "Return"),
        ("return", "Return"),
        ("tab", "Tab"),
        ("escape", "Escape"),
        ("esc", "Escape"),
        ("backspace", "BackSpace"),
        ("delete", "Delete"),
        ("del", "Delete"),
        ("up", "Up"),
        ("down", "Down"),
        ("left", "Left"),
        ("right", "Right"),
        ("pageup", "Prior"),
        ("pagedown", "Next"),
        ("f1", "F1"),
        ("f12", "F12"),
    ],
)
def test_key_name_normalization(alias: str, x11: str) -> None:
    assert _build_key_args(alias) == ["-P", x11]


def test_key_normalization_with_modifier() -> None:
    assert _build_key_args("ctrl+enter") == ["-M", "ctrl", "-P", "Return", "-m", "ctrl"]


def test_unknown_key_passthrough() -> None:
    assert _build_key_args("XF86AudioPlay") == ["-P", "XF86AudioPlay".lower()]


def test_release_order_reversed() -> None:
    # modifiers must be released in reverse press order
    args = _build_key_args("ctrl+alt+delete")
    press = [args[i + 1] for i in range(0, len(args), 2) if args[i] == "-M"]
    release = [args[i + 1] for i in range(0, len(args), 2) if args[i] == "-m"]
    assert release == list(reversed(press))
