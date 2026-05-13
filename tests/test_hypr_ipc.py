"""Unit tests for Hyprland IPC parser logic."""

from __future__ import annotations

import json

import pytest

from agent.tools.events import _parse
from agent.schemas import EventKind


def test_parse_activewindow() -> None:
    event = _parse("activewindow>>foot,zsh")
    assert event.kind == EventKind.active_window
    assert event.data == "foot,zsh"


def test_parse_openwindow() -> None:
    event = _parse("openwindow>>0xdeadbeef,1,foot,zsh")
    assert event.kind == EventKind.open_window
    assert "0xdeadbeef" in event.data


def test_parse_workspace() -> None:
    event = _parse("workspace>>3")
    assert event.kind == EventKind.workspace
    assert event.data == "3"


def test_parse_unknown() -> None:
    event = _parse("somefutureevent>>data")
    assert event.kind == EventKind.other


def test_parse_no_separator() -> None:
    event = _parse("workspace")
    assert event.kind == EventKind.workspace
    assert event.data == ""


def test_window_schema() -> None:
    from agent.schemas import Window

    raw = {
        "address": "0x1234",
        "class": "foot",
        "title": "zsh",
        "workspace_id": 1,
        "at": [10, 20],
        "size": [800, 600],
        "floating": False,
        "hidden": False,
        "pid": 1234,
        "monitor": 0,
    }
    w = Window.model_validate(raw)
    assert w.app_class == "foot"
    assert w.x == 10
    assert w.w == 800
