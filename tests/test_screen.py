"""Unit tests for screen.resize() — pure Pillow function, no display needed."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from agent.tools.screen import resize


def _make_png(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_resize_half() -> None:
    png = _make_png(800, 600)
    result = resize(png, scale=0.5)
    img = Image.open(io.BytesIO(result))
    assert img.width == 400
    assert img.height == 300


def test_resize_quarter() -> None:
    png = _make_png(1920, 1200)
    result = resize(png, scale=0.25)
    img = Image.open(io.BytesIO(result))
    assert img.width == 480
    assert img.height == 300


def test_resize_identity() -> None:
    png = _make_png(100, 100)
    result = resize(png, scale=1.0)
    img = Image.open(io.BytesIO(result))
    assert img.width == 100
    assert img.height == 100


def test_resize_output_is_png() -> None:
    png = _make_png(200, 200)
    result = resize(png, scale=0.5)
    assert result[:4] == b"\x89PNG"
