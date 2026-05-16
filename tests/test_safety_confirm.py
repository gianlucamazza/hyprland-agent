"""Tests for safety/confirm.py confirmation gate."""

from __future__ import annotations

import asyncio
from io import StringIO

from agent.safety.confirm import _DESTRUCTIVE_DISPATCH, confirm, is_destructive_dispatch


class TestIsDestructiveDispatch:
    def test_known_destructive_commands(self):
        for cmd in ("killactive", "closewindow", "exit", "forcerendererreload"):
            assert is_destructive_dispatch(cmd) is True
            assert is_destructive_dispatch(cmd.upper()) is True
            assert is_destructive_dispatch(f"  {cmd}  ") is True

    def test_dispatch_with_args(self):
        assert is_destructive_dispatch("killactive arg1 arg2") is True
        assert is_destructive_dispatch("exit now") is True

    def test_safe_commands(self):
        assert is_destructive_dispatch("workspace 2") is False
        assert is_destructive_dispatch("focuswindow class:foot") is False
        assert is_destructive_dispatch("") is False
        assert is_destructive_dispatch("   ") is False

    def test_destructive_set_completeness(self):
        assert "killactive" in _DESTRUCTIVE_DISPATCH
        assert "closewindow" in _DESTRUCTIVE_DISPATCH
        assert "exit" in _DESTRUCTIVE_DISPATCH
        assert "forcerendererreload" in _DESTRUCTIVE_DISPATCH
        # All entries in the set must be covered above
        assert {
            "killactive",
            "closewindow",
            "exit",
            "forcerendererreload",
        } == _DESTRUCTIVE_DISPATCH


class TestConfirm:
    def test_confirm_yes(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("y\n"))
        result = asyncio.run(confirm("Proceed?"))
        assert result is True

    def test_confirm_yes_full(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("yes\n"))
        result = asyncio.run(confirm("Proceed?"))
        assert result is True

    def test_confirm_no(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("n\n"))
        result = asyncio.run(confirm("Proceed?"))
        assert result is False

    def test_confirm_empty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("\n"))
        result = asyncio.run(confirm("Proceed?"))
        assert result is False

    def test_confirm_eof(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO(""))
        result = asyncio.run(confirm("Proceed?"))
        assert result is False
