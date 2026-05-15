"""Tests for ActionResult Pydantic model."""

from __future__ import annotations

from agent.schemas import ActionResult


def test_action_result_defaults() -> None:
    r = ActionResult(kind="click")
    assert r.kind == "click"
    assert r.dispatch_response is None
    assert r.stdout is None
    assert r.stderr is None
    assert r.returncode is None
    assert r.blocked is None
    assert r.rejected is None
    assert r.pre_hash is None
    assert r.post_hash is None
    assert not r.is_blocked()
    assert not r.is_rejected()


def test_action_result_blocked() -> None:
    r = ActionResult(kind="type_text", blocked="control_terminal")
    assert r.is_blocked()
    assert not r.is_rejected()


def test_action_result_rejected() -> None:
    r = ActionResult(kind="dispatch", rejected="killall Xorg")
    assert r.is_rejected()
    assert not r.is_blocked()


def test_action_result_terminal_capture() -> None:
    r = ActionResult(kind="terminal_command", returncode=0, stdout="hello", stderr="")
    assert r.returncode == 0
    assert r.stdout == "hello"


def test_action_result_model_dump_excludes_nothing() -> None:
    r = ActionResult(kind="dispatch", dispatch_response="ok")
    d = r.model_dump()
    assert d["kind"] == "dispatch"
    assert d["dispatch_response"] == "ok"
    assert "blocked" in d
    assert d["blocked"] is None


def test_action_result_roundtrip_json() -> None:
    r = ActionResult(kind="focus_window", dispatch_response="ok", returncode=None)
    import json

    parsed = ActionResult.model_validate(json.loads(r.model_dump_json()))
    assert parsed.kind == "focus_window"
    assert parsed.dispatch_response == "ok"
