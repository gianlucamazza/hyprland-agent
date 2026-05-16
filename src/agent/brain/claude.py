"""Claude computer-use brain."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from agent.brain._action_map import computer_actions
from agent.brain._common import MAX_LOOP, SCALE, compact_messages, png_b64
from agent.brain.anthropic_client import anthropic_client
from agent.schemas import Action, ActionKind, ScreenState
from agent.tools import hypr, screen

if TYPE_CHECKING:
    from agent.brain.context import BrainContext

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 4096
_SCALE = SCALE
_MAX_LOOP = MAX_LOOP

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
    {
        "name": "read_file",
        "description": "Read a file's contents. Returns text up to 64KB. Use offset/limit for large files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (supports ~/)"},
                "offset": {
                    "type": "integer",
                    "description": "Start reading from this character offset",
                },
                "limit": {"type": "integer", "description": "Max characters to read"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories. Asks confirmation before overwriting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (supports ~/)"},
                "content": {"type": "string", "description": "Content to write"},
                "append": {"type": "boolean", "description": "Append instead of overwrite"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_dir",
        "description": "List directory contents as JSON with file sizes. Set recursive=true for subdirectories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (supports ~/)"},
                "recursive": {"type": "boolean", "description": "Include subdirectories"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "clipboard_read",
        "description": "Read text from the system clipboard (wl-paste).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "clipboard_write",
        "description": "Write text to the system clipboard (wl-copy).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to copy to clipboard"},
            },
            "required": ["text"],
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
    if name == "read_file":
        return "Reading file...", [Action(kind=ActionKind.read_file, params=inp)]
    if name == "write_file":
        return "Writing file...", [Action(kind=ActionKind.write_file, params=inp)]
    if name == "list_dir":
        return "Listing directory...", [Action(kind=ActionKind.list_dir, params=inp)]
    if name == "clipboard_read":
        return "Reading clipboard...", [Action(kind=ActionKind.clipboard_read)]
    if name == "clipboard_write":
        return "Writing clipboard...", [
            Action(kind=ActionKind.clipboard_write, params={"text": inp["text"]})
        ]
    return "unknown tool", []


def _computer_action_to_actions(
    action: dict[str, Any], scale_x: float = 1.0, scale_y: float = 1.0
) -> list[Action]:
    coord = action.get("coordinate", [0, 0])
    return computer_actions(
        action.get("action", ""),
        x=coord[0],
        y=coord[1],
        text=action.get("text", ""),
        combo=action.get("key", ""),
        direction=action.get("direction", "down"),
        amount=action.get("amount", 3),
        scale_x=scale_x,
        scale_y=scale_y,
    )


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
                            "data": png_b64(png),
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ]
        tools = [_computer_tool(scaled_w, scaled_h)] + _CUSTOM_TOOLS
        all_actions: list[Action] = []

        ctx_cfg = ctx.context_config

        for _iteration in range(_MAX_LOOP):
            messages = compact_messages(
                messages,
                budget_tokens=ctx_cfg.budget_tokens if ctx_cfg else 160_000,
                keep_rounds=ctx_cfg.keep_rounds if ctx_cfg else 3,
            )
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.messages.create,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                ),
                timeout=120.0,
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
