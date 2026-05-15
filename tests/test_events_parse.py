"""Tests for tools/events.py event parsing."""

from __future__ import annotations

from agent.schemas import EventKind
from agent.tools.events import _parse


class TestParse:
    def test_known_event_kind(self):
        ev = _parse("workspace>>2")
        assert ev.kind == EventKind.workspace
        assert ev.data == "2"
        assert ev.raw == "workspace>>2"

    def test_activewindow(self):
        ev = _parse("activewindow>>firefox,Mozilla Firefox")
        assert ev.kind == EventKind.active_window
        assert "firefox" in ev.data

    def test_openwindow(self):
        ev = _parse("openwindow>>12345,1,foot,foot")
        assert ev.kind == EventKind.open_window

    def test_closewindow(self):
        ev = _parse("closewindow>>12345")
        assert ev.kind == EventKind.close_window

    def test_movewindow(self):
        ev = _parse("movewindow>>12345,2")
        assert ev.kind == EventKind.move_window

    def test_focusedmon(self):
        ev = _parse("focusedmon>>DP-1,1")
        assert ev.kind == EventKind.focused_mon

    def test_urgent(self):
        ev = _parse("urgent>>abc")
        assert ev.kind == EventKind.urgent

    def test_unknown_event_falls_back_to_other(self):
        ev = _parse("customkind>>somedata")
        assert ev.kind == EventKind.other
        assert ev.data == "somedata"

    def test_no_separator_is_other(self):
        ev = _parse("weirdline")
        assert ev.kind == EventKind.other
        assert ev.data == ""
        assert ev.raw == "weirdline"

    def test_empty_data_after_separator(self):
        ev = _parse("workspace>>")
        assert ev.kind == EventKind.workspace
        assert ev.data == ""

    def test_data_is_stripped(self):
        ev = _parse("workspace>>  2  ")
        assert ev.data == "2"
