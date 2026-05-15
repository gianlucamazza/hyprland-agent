"""Tests for IPC protocol models and version negotiation."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from agent.ipc.constants import PROTOCOL_VERSION
from agent.ipc.protocol import (
    EventFrame,
    Frame,
    HelloFrame,
    PingFrame,
    PongFrame,
    RequestFrame,
    ResponseFrame,
    RpcMethod,
    SubscribeFrame,
    Topic,
    UnsubscribeFrame,
    make_error_response,
    make_ok_response,
    versions_compatible,
)

_adapter: TypeAdapter[Frame] = TypeAdapter(Frame)


def _parse(data: dict) -> Frame:
    return _adapter.validate_python(data)


# --- Discriminated union dispatch ---


def test_parse_hello() -> None:
    f = _parse({"type": "hello", "version": "1.0"})
    assert isinstance(f, HelloFrame)
    assert f.version == "1.0"
    assert f.capabilities == []


def test_parse_hello_with_capabilities() -> None:
    f = _parse({"type": "hello", "version": "1.0", "capabilities": ["streams"]})
    assert isinstance(f, HelloFrame)
    assert "streams" in f.capabilities


def test_parse_request() -> None:
    f = _parse({"type": "request", "id": "abc", "method": "daemon_status", "params": {}})
    assert isinstance(f, RequestFrame)
    assert f.method == RpcMethod.daemon_status
    assert f.id == "abc"


def test_parse_request_default_params() -> None:
    f = _parse({"type": "request", "id": "x", "method": "list_windows"})
    assert isinstance(f, RequestFrame)
    assert f.params == {}


def test_parse_response_ok() -> None:
    f = _parse({"type": "response", "id": "x", "result": {"ok": True}})
    assert isinstance(f, ResponseFrame)
    assert f.result == {"ok": True}
    assert f.error is None


def test_parse_response_error() -> None:
    f = _parse(
        {
            "type": "response",
            "id": "x",
            "error": {"code": "not_found", "message": "run not found"},
        }
    )
    assert isinstance(f, ResponseFrame)
    assert f.result is None
    assert f.error is not None
    assert f.error["code"] == "not_found"


def test_parse_subscribe() -> None:
    f = _parse({"type": "subscribe", "topics": ["runs", "logs"]})
    assert isinstance(f, SubscribeFrame)
    assert Topic.runs in f.topics
    assert Topic.logs in f.topics


def test_parse_unsubscribe() -> None:
    f = _parse({"type": "unsubscribe", "topics": ["hypr_events"]})
    assert isinstance(f, UnsubscribeFrame)
    assert Topic.hypr_events in f.topics


def test_parse_event() -> None:
    f = _parse(
        {
            "type": "event",
            "topic": "runs",
            "payload": {"run_id": "abc", "status": "completed"},
        }
    )
    assert isinstance(f, EventFrame)
    assert f.topic == Topic.runs
    assert f.payload["run_id"] == "abc"


def test_parse_ping() -> None:
    assert isinstance(_parse({"type": "ping"}), PingFrame)


def test_parse_pong() -> None:
    assert isinstance(_parse({"type": "pong"}), PongFrame)


# --- Validation errors ---


def test_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"type": "foobar"})


def test_unknown_method_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"type": "request", "id": "x", "method": "hack_system"})


def test_unknown_topic_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"type": "subscribe", "topics": ["secrets"]})


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"type": "ping", "surprise": "field"})


# --- Serialization roundtrip ---


def test_roundtrip_request() -> None:
    original = RequestFrame(id="r1", method=RpcMethod.run_task, params={"task": "open foot"})
    data = original.model_dump_json()
    recovered = _parse(__import__("json").loads(data))
    assert isinstance(recovered, RequestFrame)
    assert recovered.method == RpcMethod.run_task
    assert recovered.params["task"] == "open foot"


def test_roundtrip_event() -> None:
    original = EventFrame(topic=Topic.logs, payload={"msg": "hello"})
    data = original.model_dump_json()
    recovered = _parse(__import__("json").loads(data))
    assert isinstance(recovered, EventFrame)
    assert recovered.payload["msg"] == "hello"


# --- Version negotiation ---


def test_versions_compatible_same_major() -> None:
    assert versions_compatible("1.0", "1.0")
    assert versions_compatible("1.0", "1.99")
    assert versions_compatible("1.99", "1.0")


def test_versions_compatible_different_major() -> None:
    assert not versions_compatible("1.0", "2.0")
    assert not versions_compatible("2.0", "1.0")


def test_versions_compatible_with_constants() -> None:
    assert versions_compatible(PROTOCOL_VERSION, PROTOCOL_VERSION)


def test_versions_compatible_rejects_garbage() -> None:
    assert not versions_compatible("abc", "1.0")
    assert not versions_compatible("1.0", "")


# --- Factory helpers ---


def test_make_ok_response() -> None:
    r = make_ok_response("req-1", {"run_id": "abc"})
    assert r.id == "req-1"
    assert r.result == {"run_id": "abc"}
    assert r.error is None


def test_make_error_response() -> None:
    r = make_error_response("req-1", "not found", code="not_found")
    assert r.id == "req-1"
    assert r.error == {"code": "not_found", "message": "not found"}
    assert r.result is None


# --- All RPC methods are defined ---


def test_all_rpc_methods_have_values() -> None:
    expected = {
        "plan_task",
        "run_task",
        "cancel_run",
        "list_runs",
        "get_run",
        "list_windows",
        "screenshot",
        "reload_rules",
        "arm_killswitch",
        "disarm_killswitch",
        "daemon_status",
        "record_feedback",
        "runs_analytics",
        "learning_list",
        "learning_approve",
        "learning_reject",
        "learning_explain",
        "memory_search",
        "memory_get",
    }
    actual = {m.value for m in RpcMethod}
    assert actual == expected
