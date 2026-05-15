"""Input control: wtype (keyboard) + ydotool (mouse via uinput)."""

from __future__ import annotations

import asyncio

from agent.tools._proc import run as _proc_run


async def _run(*cmd: str) -> None:
    result = await _proc_run(cmd, timeout=5.0)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {result.stderr.decode()}")


async def type_text(text: str) -> None:
    await _run("wtype", "--", text)


_MODIFIERS = {
    "ctrl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "super": "super",
    "meta": "super",
}

# LLM-friendly aliases → X11/wtype key names
_KEY_NAMES: dict[str, str] = {
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "space": "space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "page_up": "Prior",
    "pagedown": "Next",
    "page_down": "Next",
    "insert": "Insert",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12",
}


def _build_key_args(combo: str) -> list[str]:
    """Build wtype argument list for a key combo like 'ctrl+shift+c'."""
    parts = combo.lower().split("+")
    args: list[str] = []
    held: list[str] = []
    for part in parts[:-1]:
        mod = _MODIFIERS.get(part, part)
        args += ["-M", mod]
        held.append(mod)
    key = _KEY_NAMES.get(parts[-1], parts[-1])
    args += ["-P", key]
    for mod in reversed(held):
        args += ["-m", mod]
    return args


async def key(combo: str) -> None:
    """Send a key combination, e.g. 'ctrl+c', 'super+shift+4'."""
    await _run("wtype", *_build_key_args(combo))


async def move(x: int, y: int) -> None:
    await _run("ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y))


async def click(button: str = "left") -> None:
    codes = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
    code = codes.get(button, "0xC0")
    await _run("ydotool", "click", code)


async def move_and_click(x: int, y: int, button: str = "left") -> None:
    await move(x, y)
    await asyncio.sleep(0.05)
    await click(button)


async def scroll(amount: int, horizontal: bool = False) -> None:
    axis = "1" if horizontal else "0"
    await _run("ydotool", "mousemove", "--wheel", axis, str(amount))
