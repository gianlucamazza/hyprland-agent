"""Shared computer-use verb → Action mapping for Claude and OpenAI brain implementations."""

from __future__ import annotations

from agent.schemas import Action, ActionKind


def computer_actions(
    verb: str,
    *,
    x: int | float = 0,
    y: int | float = 0,
    text: str = "",
    combo: str = "",
    direction: str = "down",
    amount: int | float = 3,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> list[Action]:
    """Translate a computer-use verb and its parameters into a list of Actions.

    Returns an empty list for unrecognised verbs (caller handles custom tools).
    Coordinates are multiplied by scale_x/scale_y before dispatch.
    """
    sx, sy = int(x * scale_x), int(y * scale_y)

    if verb == "screenshot":
        return [Action(kind=ActionKind.screenshot)]

    if verb in ("left_click", "right_click", "middle_click"):
        button = verb.removesuffix("_click")
        return [
            Action(kind=ActionKind.mouse_move, params={"x": sx, "y": sy}),
            Action(kind=ActionKind.click, params={"button": button}),
        ]

    if verb == "double_click":
        return [
            Action(kind=ActionKind.mouse_move, params={"x": sx, "y": sy}),
            Action(kind=ActionKind.click, params={"button": "left"}),
            Action(kind=ActionKind.click, params={"button": "left"}),
        ]

    if verb == "mouse_move":
        return [Action(kind=ActionKind.mouse_move, params={"x": sx, "y": sy})]

    # Claude uses "type", OpenAI uses "type_text"
    if verb in ("type", "type_text"):
        return [Action(kind=ActionKind.type_text, params={"text": text})]

    if verb == "key":
        return [Action(kind=ActionKind.key, params={"combo": combo})]

    if verb == "scroll":
        amt = int(amount)
        signed = -amt if direction in ("up", "left") else amt
        horizontal = direction in ("left", "right")
        return [
            Action(kind=ActionKind.mouse_move, params={"x": sx, "y": sy}),
            Action(kind=ActionKind.scroll, params={"amount": signed, "horizontal": horizontal}),
        ]

    return []
