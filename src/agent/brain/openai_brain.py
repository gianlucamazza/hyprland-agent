"""OpenAI-compatible vision brain.

Supports any OpenAI-compatible provider via ProviderConfig registry.
Built-in: OpenAI, Moonshot Kimi, Groq, Together AI, Z.AI, Qwen (DashScope).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from openai import AsyncOpenAI

from agent.brain._action_map import computer_actions
from agent.brain._common import MAX_LOOP, SCALE, compact_messages, png_b64
from agent.config import KNOWN_PROVIDERS
from agent.schemas import Action, ActionKind, ScreenState
from agent.tools import hypr, screen

if TYPE_CHECKING:
    from agent.brain.context import BrainContext

log = logging.getLogger(__name__)
_SCALE = SCALE
_MAX_LOOP = MAX_LOOP


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    key_env: str
    model_env: str
    default_model: str
    base_url: str | None  # None = OpenAI official


PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig("OpenAI", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt-5.2", None),
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

# All PROVIDERS keys must be listed in KNOWN_PROVIDERS (source of truth in config.py).
assert set(PROVIDERS).issubset(KNOWN_PROVIDERS), (
    f"PROVIDERS keys {set(PROVIDERS)} must be subset of KNOWN_PROVIDERS {set(KNOWN_PROVIDERS)}"
)


def build_brain(provider_key: str) -> OpenAICompatibleBrain:
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
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Returns text up to 64KB. Use offset/limit for large files.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates parent directories. Asks confirmation before overwriting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (supports ~/)"},
                    "content": {"type": "string", "description": "Content to write"},
                    "append": {"type": "boolean", "description": "Append instead of overwrite"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List directory contents as JSON with file sizes. Set recursive=true for subdirectories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (supports ~/)"},
                    "recursive": {"type": "boolean", "description": "Include subdirectories"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_read",
            "description": "Read text from the system clipboard.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_write",
            "description": "Write text to the system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to copy to clipboard"},
                },
                "required": ["text"],
            },
        },
    },
]


async def _call_tool(
    name: str, args: dict[str, Any], scale: float = 1.0
) -> tuple[str, list[Action]]:
    """Execute a tool call and return (result_text, actions).

    scale: multiply raw model coordinates by this factor to get screen coords.
    """
    if name == "screenshot":
        png = await screen.for_vision(scale=_SCALE)
        return f"data:image/png;base64,{png_b64(png)}", [Action(kind=ActionKind.screenshot)]

    # Common computer-use verbs delegated to shared action map
    acts = computer_actions(
        name,
        x=args.get("x", 0),
        y=args.get("y", 0),
        text=args.get("text", ""),
        combo=args.get("combo", ""),
        direction=args.get("direction", "down"),
        amount=args.get("amount", 3),
        scale_x=scale,
        scale_y=scale,
    )
    if acts:
        if "x" in args and "y" in args:
            sx, sy = int(args["x"] * scale), int(args["y"] * scale)
            label = f"{name} ({sx},{sy})"
        else:
            label = name
        return label, acts

    if name == "terminal_command":
        command = args["command"]
        params: dict[str, Any] = {"command": command}
        if "hold_s" in args:
            params["hold_s"] = args["hold_s"]
        return "terminal command queued", [Action(kind=ActionKind.terminal_command, params=params)]

    if name == "focus_window":
        addr = args["address"]
        return "focus queued", [Action(kind=ActionKind.focus_window, params={"address": addr})]

    if name == "list_windows":
        wins = await hypr.clients()
        lines = [f"{w.address} [{w.app_class}] {w.title!r}" for w in wins]
        return "\n".join(lines) or "(none)", []

    if name == "dispatch_hypr":
        return "dispatch queued", [Action(kind=ActionKind.dispatch, params={"cmd": args["cmd"]})]

    if name == "read_file":
        return "Reading file...", [Action(kind=ActionKind.read_file, params=args)]
    if name == "write_file":
        return "Writing file...", [Action(kind=ActionKind.write_file, params=args)]
    if name == "list_dir":
        return "Listing directory...", [Action(kind=ActionKind.list_dir, params=args)]

    if name == "clipboard_read":
        return "Reading clipboard...", [Action(kind=ActionKind.clipboard_read)]
    if name == "clipboard_write":
        return "Writing clipboard...", [
            Action(kind=ActionKind.clipboard_write, params={"text": args["text"]})
        ]

    return "unknown tool", []


class OpenAICompatibleBrain:
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self._model = model
        self._scale = 1.0 / _SCALE
        self._timeout = 120.0
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": httpx.Timeout(60.0, connect=10.0),
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**client_kwargs)

    async def decide(self, state: ScreenState, task: str, ctx: BrainContext) -> list[Action]:
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
                        "image_url": {"url": f"data:image/png;base64,{png_b64(png)}"},
                    },
                    {"type": "text", "text": user_text},
                ],
            },
        ]
        all_actions: list[Action] = []

        ctx_cfg = ctx.context_config

        for _iteration in range(_MAX_LOOP):
            messages = compact_messages(
                messages,
                budget_tokens=ctx_cfg.budget_tokens if ctx_cfg else 160_000,
                keep_rounds=ctx_cfg.keep_rounds if ctx_cfg else 3,
            )
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=_TOOLS,
                    tool_choice="auto",
                    max_completion_tokens=2048,
                ),
                timeout=self._timeout,
            )
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                break

            tool_results = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError as exc:
                    log.warning(
                        "Malformed JSON from %s tool call %s: %s",
                        self._model,
                        tc.function.name,
                        exc,
                    )
                    continue
                result_text, actions = await _call_tool(tc.function.name, args, scale=self._scale)
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
