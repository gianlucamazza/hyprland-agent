"""Shared constants and helpers for brain implementations."""

from __future__ import annotations

import base64

from agent.config import DEFAULT_MAX_ITER

SCALE: float = 0.5
MAX_LOOP: int = DEFAULT_MAX_ITER


def png_b64(png: bytes) -> str:
    return base64.standard_b64encode(png).decode()
