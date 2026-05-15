"""OpenAI-compatible vision brain.

Supports any OpenAI-compatible provider via ProviderConfig registry.
Built-in: OpenAI, Moonshot Kimi, Groq, Together AI, Z.AI, Qwen (DashScope).
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from agent.schemas import Action, ActionKind, ScreenState
from agent.tools import hypr, screen

if TYPE_CHECKING:
    from agent.brain.context import BrainContext

_SCALE = 0.5  # screenshot resize factor; coordinates scaled back up before dispatch
_MAX_LOOP = 20  # max tool-use iterations per decide() call


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    key_env: str
    model_env: str
    default_model: str
    base_url: str | None  # None = OpenAI official


PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        "OpenAI", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt-5.2", None
    ),
    "moonshot": ProviderConfig(
        "Moonshot",
        "MOONSHOT_API_KEY",
        "MOONSHOT_MODEL",
        "kimi-k2.6",
        "https://api.moonshot.ai/v1",
    ),
    "groq": ProviderConfig(
        "Groq",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "https://api.groq.com/openai/v1",
    ),
    "together": ProviderConfig(
        "Together",
        "TOGETHER_API_KEY",
        "TOGETHER_MODEL",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "https://api.together.xyz/v1",
    ),
    "zai": ProviderConfig(
        "Z.AI", "ZAI_API_KEY", "ZAI_MODEL", "glm-4.6v", "https://api.z.ai/api/paas/v4"
    ),
    "qwen": ProviderConfig(
        "Qwen",
        "DASHSCOPE_API_KEY",
        "QWEN_MODEL",
        "qwen3-vl-235b-a22b-instruct",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    ),
}


def build_brain(provider_key: str) -> "OpenAICompatibleBrain":
    cfg = PROVIDERS[provider_key]
    api_key = os.environ.get(cfg.key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"{cfg.name} brain selected but {cfg.key_env} not set. "
            "Export it or add it to ~/.config/hyprland-agent/env."
        )
    model = os.environ.get(cfg.model_env, cfg.default_model)
    return OpenAICompatibleBrain(api_key=api_key, model=model, base_url=cfg.base_url)


_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Take a fresh screenshot of the desktop.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "left_click",
            "description": "Move mouse to coordinates and left-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "right_click",
            "description": "Move mouse to coordinates and right-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "middle_click",
            "description": "Move mouse to coordinates and middle-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "double_click",
            "description": "Move mouse to coordinates and double-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll at the given coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                        "default": "down",
                    },
                    "amount": {"type": "integer", "default": 3},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": (
                "Type text into an already-focused non-terminal GUI text field. "
                "Do not use this for shell commands."
            ),
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "key",
            "description": (
                "Press a key combination in an already-focused non-terminal GUI target."
            ),
            "parameters": {
                "type": "object",
                "properties": {"combo": {"type": "string"}},
                "required": ["combo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_command",
            "description": (
                "Run a shell command in a dedicated terminal owned by this agent run. "
                "Use this for terminal or shell tasks. Set hold_s only when the "
                "task asks for a visible/debug test."
            ),
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Focus a Hyprland window by address.",
            "parameters": {
                "type": "object",
                "properties": {"address": {"type": "string"}},
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List all open windows.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_hypr",
            "description": "Run a Hyprland dispatch command.",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
                "required": ["cmd"],
            },
        },
    },
]


def _png_b64(png: bytes) -> str:
    return base64.standard_b64encode(png).decode()


def _sc(val: int | float, factor: float) -> int:
    return int(val * factor)


async def _call_tool(
    name: str, args: dict[str, Any], scale: float = 1.0
) -> tuple[str, list[Action]]:
    """Execute a tool call and return (result_text, actions).

    scale: multiply raw model coordinates by this factor to get screen coords.
    """
    if name == "screenshot":
        png = await screen.for_vision(scale=_SCALE)
        return f"data:image/png;base64,{_png_b64(png)}", [
            Action(kind=ActionKind.screenshot)
        ]

    if name == "left_click":
        x, y = _sc(args["x"], scale), _sc(args["y"], scale)
        return f"left_click ({x},{y})", [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "left"}),
        ]

    if name == "right_click":
        x, y = _sc(args["x"], scale), _sc(args["y"], scale)
        return f"right_click ({x},{y})", [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "right"}),
        ]

    if name == "middle_click":
        x, y = _sc(args["x"], scale), _sc(args["y"], scale)
        return f"middle_click ({x},{y})", [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "middle"}),
        ]

    if name == "double_click":
        x, y = _sc(args["x"], scale), _sc(args["y"], scale)
        return f"double_click ({x},{y})", [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(kind=ActionKind.click, params={"button": "left"}),
            Action(kind=ActionKind.click, params={"button": "left"}),
        ]

    if name == "scroll":
        x, y = _sc(args["x"], scale), _sc(args["y"], scale)
        direction = args.get("direction", "down")
        amount = int(args.get("amount", 3))
        signed = -amount if direction in ("up", "left") else amount
        horizontal = direction in ("left", "right")
        return f"scroll {direction}×{amount} at ({x},{y})", [
            Action(kind=ActionKind.mouse_move, params={"x": x, "y": y}),
            Action(
                kind=ActionKind.scroll,
                params={"amount": signed, "horizontal": horizontal},
            ),
        ]

    if name == "type_text":
        text = args["text"]
        return f"typed {len(text)} chars", [
            Action(kind=ActionKind.type_text, params={"text": text})
        ]

    if name == "key":
        combo = args["combo"]
        return f"pressed {combo}", [
            Action(kind=ActionKind.key, params={"combo": combo})
        ]

    if name == "terminal_command":
        command = args["command"]
        params: dict[str, Any] = {"command": command}
        if "hold_s" in args:
            params["hold_s"] = args["hold_s"]
        return "terminal command queued", [
            Action(kind=ActionKind.terminal_command, params=params)
        ]

    if name == "focus_window":
        addr = args["address"]
        return "focus queued", [
            Action(kind=ActionKind.focus_window, params={"address": addr})
        ]

    if name == "list_windows":
        wins = await hypr.clients()
        lines = [f"{w.address} [{w.app_class}] {w.title!r}" for w in wins]
        return "\n".join(lines) or "(none)", []

    if name == "dispatch_hypr":
        return "dispatch queued", [
            Action(kind=ActionKind.dispatch, params={"cmd": args["cmd"]})
        ]

    return "unknown tool", []


class OpenAICompatibleBrain:
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self._model = model
        self._scale = 1.0 / _SCALE
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**client_kwargs)

    async def decide(
        self, state: ScreenState, task: str, ctx: "BrainContext"
    ) -> list[Action]:
        scaled_w = int(state.width * _SCALE)
        scaled_h = int(state.height * _SCALE)
        png = screen.resize(state.screenshot_png, scale=_SCALE)
        system_msg = (
            ctx.render_system_prompt()
            + f"\n\nDisplay: {scaled_w}x{scaled_h}. Coordinates are in scaled image space."
        )
        preamble = ctx.render_user_preamble()
        user_text = f"Task: {task}"
        if preamble:
            user_text = f"{preamble}\n\n{user_text}"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{_png_b64(png)}"},
                    },
                    {"type": "text", "text": user_text},
                ],
            },
        ]
        all_actions: list[Action] = []

        for _iteration in range(_MAX_LOOP):
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                max_completion_tokens=2048,
            )
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                break

            tool_results = []
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                result_text, actions = await _call_tool(
                    tc.function.name, args, scale=self._scale
                )
                all_actions.extend(actions)
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    }
                )
            messages.extend(tool_results)
        else:
            import logging

            logging.getLogger(__name__).warning(
                "Brain loop reached max iterations (%d) — stopping", _MAX_LOOP
            )

        return all_actions
