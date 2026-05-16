"""Wire protocol models — NDJSON frames with Pydantic discriminated union."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from agent.ipc.constants import PROTOCOL_MAJOR


class RpcMethod(StrEnum):
    plan_task = "plan_task"
    run_task = "run_task"
    cancel_run = "cancel_run"
    list_runs = "list_runs"
    get_run = "get_run"
    list_windows = "list_windows"
    screenshot = "screenshot"
    reload_rules = "reload_rules"
    arm_killswitch = "arm_killswitch"
    disarm_killswitch = "disarm_killswitch"
    daemon_status = "daemon_status"
    record_feedback = "record_feedback"
    runs_analytics = "runs_analytics"
    learning_list = "learning_list"
    learning_approve = "learning_approve"
    learning_reject = "learning_reject"
    learning_explain = "learning_explain"
    memory_search = "memory_search"
    memory_get = "memory_get"


class Topic(StrEnum):
    runs = "runs"
    hypr_events = "hypr_events"
    logs = "logs"
    voice = "voice"


class _StrictFrame(BaseModel):
    model_config = {"extra": "forbid"}


class HelloFrame(_StrictFrame):
    type: Literal["hello"] = "hello"
    version: str
    capabilities: list[str] = []


class RequestFrame(_StrictFrame):
    type: Literal["request"] = "request"
    id: str
    method: RpcMethod
    params: dict[str, Any] = Field(default_factory=dict)


class ResponseFrame(_StrictFrame):
    type: Literal["response"] = "response"
    id: str
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None


class SubscribeFrame(_StrictFrame):
    type: Literal["subscribe"] = "subscribe"
    topics: list[Topic]


class UnsubscribeFrame(_StrictFrame):
    type: Literal["unsubscribe"] = "unsubscribe"
    topics: list[Topic]


class EventFrame(_StrictFrame):
    type: Literal["event"] = "event"
    topic: Topic
    payload: dict[str, Any]


class PingFrame(_StrictFrame):
    type: Literal["ping"] = "ping"


class PongFrame(_StrictFrame):
    type: Literal["pong"] = "pong"


Frame = Annotated[
    HelloFrame
    | RequestFrame
    | ResponseFrame
    | SubscribeFrame
    | UnsubscribeFrame
    | EventFrame
    | PingFrame
    | PongFrame,
    Field(discriminator="type"),
]


def parse_major(version: str) -> int:
    try:
        return int(version.split(".")[0])
    except (ValueError, IndexError):
        return -1


def versions_compatible(a: str, b: str) -> bool:
    """True if both versions share the same major number."""
    return parse_major(a) == parse_major(b) == PROTOCOL_MAJOR


def make_error_response(request_id: str, message: str, code: str = "error") -> ResponseFrame:
    return ResponseFrame(id=request_id, error={"code": code, "message": message})


def make_ok_response(request_id: str, result: dict[str, Any]) -> ResponseFrame:
    return ResponseFrame(id=request_id, result=result)
