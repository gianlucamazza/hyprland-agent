"""Claude computer-use brain."""

from __future__ import annotations

import asyncio
import base64
import os
from typing import TYPE_CHECKING, Any

from agent.brain.oauth_bridge import anthropic_client
from agent.schemas import Action, ActionKind, ScreenState
from agent.tools import hypr, screen

if TYPE_CHECKING:
    from agent.brain.context import BrainContext

from agent.config import DEFAULT_MAX_ITER

_DEFAULT_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 4096
_SCALE = 0.5  # screenshot resize factor; coordinates are scaled back up before dispatch
_MAX_LOOP = DEFAULT_MAX_ITER

_CUSTOM_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_windows",
        "description": "List all open windows with their address, title, class, and geometry.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "terminal_command",
        "description": (
            "Run a shell command in a dedicated terminal owned by this agent run. "
            "Use this for terminal or shell tasks instead of typing into the focused "
            "terminal. Set hold_s only when the task asks for a visible/debug test."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "hold_s": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 0,
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "focus_window",
        "description": "Queue focusing a window by its address.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Hyprland window address (hex)",
                }
            },
            "required": ["address"],
        },
    },
    {
        "name": "dispatch_hypr",
        "description": (
            "Queue a raw Hyprland dispatch command (e.g. 'workspace 2', 'movetoworkspace 3')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "description": "Hyprland dispatch argument string",
                }
            },
            "required": ["cmd"],
        },
    },
]


def _computer_tool(width: int, height: int) -> dict[str, Any]:
    return {
        "type": "computer_20251124",
        "name": "computer",
        "display_width_px": width,
        "display_height_px": height,
    }


def _png_b64(png: bytes) -> str:
    return base64.standard_b64encode(png).decode()


async def _handle_custom(name: str, inp: dict[str, Any]) -> tuple[str, list[Action]]:
    if name == "list_windows":
        wins = await hypr.clients()
        lines = [
            f"{w.address} [{w.app_class}] {w.title!r} at ({w.x},{w.y}) {w.w}x{w.h}" for w in wins
        ]
        return "\n".join(lines) or "(no windows)", []
    if name == "terminal_command":
        params: dict[str, Any] = {"command": inp["command"]}
        if "hold_s" in inp:
            params["hold_s"] = inp["hold_s"]
        return "terminal command queued", [
            Action(
                kind=ActionKind.terminal_command,
                params=params,
            )
        ]
    if name == "focus_window":
        return "focus queued", [
            Action(kind=ActionKind.focus_window, params={"address": inp["address"]})
        ]
    if name == "dispatch_hypr":
        return "dispatch queued", [Action(kind=ActionKind.dispatch, params={"cmd": inp["cmd"]})]
    return "unknown tool", []


def _computer_action_to_actions(
    action: dict[str, Any], scale_x: float = 1.0, scale_y: float = 1.0
) -> list[Action]:
    def _sc(coord: list) -> tuple[int, int]:
        return int(coord[0] * scale_x), int(coord[1] * scale_y)

    at = action.get("action")
    if at == "screenshot":
        return [Action(kind=ActionKind.screenshot)]
    if at == "left_click":
        x, y = _sc(action.get("coordinate", [0, 0]))
        return [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "left"}),
        ]
    if at == "right_click":
        x, y = _sc(action.get("coordinate", [0, 0]))
        return [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "right"}),
        ]
    if at == "middle_click":
        x, y = _sc(action.get("coordinate", [0, 0]))
        return [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "middle"}),
        ]
    if at == "double_click":
        x, y = _sc(action.get("coordinate", [0, 0]))
        return [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "left"}),
            Action(kind=ActionKind.click, params={"button": "left"}),
        ]
    if at == "mouse_move":
        x, y = _sc(action.get("coordinate", [0, 0]))
        return [Action(kind=ActionKind.mouse_move, params={"x": x, "y": y})]
    if at == "type":
        return [Action(kind=ActionKind.type_text, params={"text": action.get("text", "")})]
    if at == "key":
        return [Action(kind=ActionKind.key, params={"combo": action.get("key", "")})]
    if at == "scroll":
        x, y = _sc(action.get("coordinate", [0, 0]))
        direction = action.get("direction", "down")
        amount = action.get("amount", 3)
        signed = -amount if direction in ("up", "left") else amount
        horizontal = direction in ("left", "right")
        return [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(
                kind=ActionKind.scroll,
                params={"amount": signed, "horizontal": horizontal},
            ),
        ]
    return []


class ClaudeBrain:
    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = _MAX_TOKENS,
    ):
        self.model = model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self.max_tokens = max_tokens

    async def decide(self, state: ScreenState, task: str, ctx: BrainContext) -> list[Action]:
        client = anthropic_client()
        scaled_w = int(state.width * _SCALE)
        scaled_h = int(state.height * _SCALE)
        png = screen.resize(state.screenshot_png, scale=_SCALE)
        system_prompt = ctx.render_system_prompt()
        preamble = ctx.render_user_preamble()
        user_text = f"Task: {task}"
        if preamble:
            user_text = f"{preamble}\n\n{user_text}"
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": _png_b64(png),
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ]
        tools = [_computer_tool(scaled_w, scaled_h)] + _CUSTOM_TOOLS
        all_actions: list[Action] = []

        for _iteration in range(_MAX_LOOP):
            response = await asyncio.to_thread(
                client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "computer":
                        actions = _computer_action_to_actions(
                            block.input, scale_x=1 / _SCALE, scale_y=1 / _SCALE
                        )
                        all_actions.extend(actions)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "action queued",
                                    }
                                ],
                            }
                        )
                    else:
                        result_text, actions = await _handle_custom(block.name, block.input)
                        all_actions.extend(actions)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": [{"type": "text", "text": result_text}],
                            }
                        )

            if response.stop_reason == "end_turn" or not tool_results:
                break

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            import logging

            logging.getLogger(__name__).warning(
                "Brain loop reached max iterations (%d) — stopping", _MAX_LOOP
            )

        return all_actions
