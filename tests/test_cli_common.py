"""Tests for cli/_common.py shared utilities."""

from __future__ import annotations

import pytest
import typer

from agent.cli._common import ExitCode, confirm_or_exit


class TestExitCode:
    def test_values(self):
        assert ExitCode.ok == 0
        assert ExitCode.error == 1
        assert ExitCode.misuse == 2
        assert ExitCode.daemon_unavailable == 3
        assert ExitCode.killswitch_armed == 4
        assert ExitCode.confirmation_denied == 5

    def test_is_int(self):
        assert isinstance(ExitCode.ok, int)


class TestConfirmOrExit:
    def test_yes_flag_skips_prompt(self):
        # Should not raise or ask anything
        confirm_or_exit("Proceed?", yes=True)

    def test_non_tty_skips_prompt(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        # Should return without raising even without --yes
        confirm_or_exit("Proceed?", yes=False)

    def test_tty_confirmed(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("typer.confirm", lambda prompt: True)
        confirm_or_exit("Proceed?", yes=False)

    def test_tty_denied_raises_exit(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("typer.confirm", lambda prompt: False)
        with pytest.raises(typer.Exit) as exc_info:
            confirm_or_exit("Proceed?", yes=False)
        assert exc_info.value.exit_code == ExitCode.confirmation_denied
