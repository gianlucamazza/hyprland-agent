from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Window(BaseModel):
    address: str
    title: str
    app_class: str = Field(alias="class")
    workspace_id: int
    at: tuple[int, int]
    size: tuple[int, int]
    floating: bool
    hidden: bool
    pid: int
    monitor: int

    @property
    def x(self) -> int:
        return self.at[0]

    @property
    def y(self) -> int:
        return self.at[1]

    @property
    def w(self) -> int:
        return self.size[0]

    @property
    def h(self) -> int:
        return self.size[1]

    model_config = {"populate_by_name": True}


class Monitor(BaseModel):
    id: int
    name: str
    width: int
    height: int
    x: int
    y: int
    scale: float
    focused: bool


class Workspace(BaseModel):
    id: int
    name: str
    monitor: str
    windows: int
    last_window: str = Field(alias="lastwindow", default="")

    model_config = {"populate_by_name": True}


class EventKind(str, Enum):
    workspace = "workspace"
    active_window = "activewindow"
    open_window = "openwindow"
    close_window = "closewindow"
    move_window = "movewindow"
    focused_mon = "focusedmon"
    urgent = "urgent"
    other = "other"


class Event(BaseModel):
    kind: EventKind
    data: str
    raw: str


class ActionKind(str, Enum):
    screenshot = "screenshot"
    type_text = "type_text"
    key = "key"
    mouse_move = "mouse_move"
    click = "click"
    scroll = "scroll"
    focus_window = "focus_window"
    dispatch = "dispatch"
    clipboard_copy = "clipboard_copy"
    clipboard_paste = "clipboard_paste"


class Action(BaseModel):
    kind: ActionKind
    params: dict[str, Any] = Field(default_factory=dict)


class ScreenState(BaseModel):
    screenshot_png: bytes
    width: int
    height: int
    active_window: Window | None
    windows: list[Window]


# --- Watch-mode rule schemas ---


class EventMatch(BaseModel):
    app_class: str | None = Field(None, alias="class")
    title: str | None = None

    model_config = {"populate_by_name": True}


class RuleActionKind(str, Enum):
    dispatch = "dispatch"
    log = "log"
    notify = "notify"
    run = "run"


class RuleAction(BaseModel):
    kind: RuleActionKind
    value: str


class Rule(BaseModel):
    on: EventKind
    match: EventMatch = Field(default_factory=EventMatch)
    actions: list[RuleAction]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        """Parse a rule dict from YAML into a Rule model."""
        raw_actions: list[RuleAction] = []
        for item in data.get("actions", []):
            for kind_str, value in item.items():
                raw_actions.append(
                    RuleAction(kind=RuleActionKind(kind_str), value=str(value))
                )
        match_data = data.get("match", {})
        return cls(
            on=EventKind(data["on"]),
            match=EventMatch.model_validate(match_data),
            actions=raw_actions,
        )


# --- Run-history schemas ---


class RunStatus(str, Enum):
    running = "running"
    completed = "completed"
    errored = "errored"
    aborted = "aborted"


class RunEventRecord(BaseModel):
    seq: int
    ts: float
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    run_id: str
    task: str
    brain: str
    dry_run: bool
    status: RunStatus
    started_at: float
    ended_at: float | None = None
    error: str | None = None


class RunRecord(RunSummary):
    events: list[RunEventRecord] = Field(default_factory=list)
