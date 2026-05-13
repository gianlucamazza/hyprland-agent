"""Screen capture via grim."""

from __future__ import annotations

import asyncio
import io

from PIL import Image

from agent.schemas import Window
from agent.tools import hypr


async def _grim(*args: str) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "grim",
        "-t",
        "png",
        *args,
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"grim failed: {err.decode()}")
    return out


async def full() -> bytes:
    return await _grim()


async def region(x: int, y: int, w: int, h: int) -> bytes:
    return await _grim("-g", f"{x},{y} {w}x{h}")


async def window(address: str) -> bytes:
    wins = await hypr.clients()
    target = next((win for win in wins if win.address == address), None)
    if target is None:
        raise ValueError(f"Window {address} not found")
    return await region(target.x, target.y, target.w, target.h)


async def active() -> bytes:
    win = await hypr.active_window()
    if win is None:
        return await full()
    return await region(win.x, win.y, win.w, win.h)


def resize(png: bytes, scale: float = 0.5) -> bytes:
    """Downscale screenshot for vision model token efficiency."""
    img = Image.open(io.BytesIO(png))
    new_size = (int(img.width * scale), int(img.height * scale))
    img = img.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def for_vision(scale: float = 0.5) -> bytes:
    png = await full()
    return resize(png, scale)
