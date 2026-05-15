"""Tests for cli/_output.py formatting helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

from agent.cli._output import is_tty, out_auto, out_json, out_text


def test_out_json_emits_formatted_json():
    echoed = []
    with patch("typer.echo", side_effect=echoed.append):
        out_json({"key": "value", "n": 1})
    assert len(echoed) == 1
    parsed = json.loads(echoed[0])
    assert parsed == {"key": "value", "n": 1}


def test_out_json_handles_non_serializable_via_default_str():
    import datetime

    echoed = []
    with patch("typer.echo", side_effect=echoed.append):
        out_json({"dt": datetime.datetime(2026, 1, 1)})
    assert "2026-01-01" in echoed[0]


def test_out_text_passes_through():
    echoed = []
    with patch("typer.echo", side_effect=echoed.append):
        out_text("hello world")
    assert echoed == ["hello world"]


def test_out_auto_on_tty_uses_human(monkeypatch):
    monkeypatch.setattr("agent.cli._output.is_tty", lambda: True)
    echoed = []
    with patch("typer.echo", side_effect=echoed.append):
        out_auto({"x": 1}, human="human text")
    assert echoed == ["human text"]


def test_out_auto_on_tty_without_human_falls_back_to_json(monkeypatch):
    monkeypatch.setattr("agent.cli._output.is_tty", lambda: True)
    echoed = []
    with patch("typer.echo", side_effect=echoed.append):
        out_auto({"x": 1}, human=None)
    parsed = json.loads(echoed[0])
    assert parsed == {"x": 1}


def test_out_auto_on_pipe_always_emits_json(monkeypatch):
    monkeypatch.setattr("agent.cli._output.is_tty", lambda: False)
    echoed = []
    with patch("typer.echo", side_effect=echoed.append):
        out_auto({"x": 2}, human="ignored")
    parsed = json.loads(echoed[0])
    assert parsed == {"x": 2}


def test_is_tty_returns_bool():
    result = is_tty()
    assert isinstance(result, bool)
