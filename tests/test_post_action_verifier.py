"""Tests for PostActionVerifier."""

from __future__ import annotations

import io

from PIL import Image

from agent.awareness.meta_cognition import PostActionVerifier
from agent.schemas import ActionKind, ActionResult


def _png(r: int = 128, g: int = 128, b: int = 128) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 80), (r, g, b)).save(buf, format="PNG")
    return buf.getvalue()


def _gradient_png(left_dark: bool = True) -> bytes:
    """Horizontal gradient so adjacent pixels differ — produces non-zero dHash."""
    buf = io.BytesIO()
    img = Image.new("L", (9, 8))
    for row in range(8):
        for col in range(9):
            v = col * 28 if left_dark else (8 - col) * 28
            img.putpixel((col, row), min(v, 255))
    rgb = img.convert("RGB")
    rgb.save(buf, format="PNG")
    return buf.getvalue()


def test_phash_is_deterministic() -> None:
    v = PostActionVerifier()
    png = _png()
    assert v.phash(png) == v.phash(png)


def test_phash_same_image_same_hash() -> None:
    v = PostActionVerifier()
    assert v.phash(_png(100, 100, 100)) == v.phash(_png(100, 100, 100))


def test_phash_different_images_different_hash() -> None:
    v = PostActionVerifier()
    h1 = v.phash(_gradient_png(left_dark=True))
    h2 = v.phash(_gradient_png(left_dark=False))
    assert h1 != h2


def test_needs_true_for_click() -> None:
    assert PostActionVerifier().needs(ActionKind.click) is True


def test_needs_true_for_mouse_move() -> None:
    assert PostActionVerifier().needs(ActionKind.mouse_move) is True


def test_needs_true_for_dispatch() -> None:
    assert PostActionVerifier().needs(ActionKind.dispatch) is True


def test_needs_false_for_terminal_command() -> None:
    assert PostActionVerifier().needs(ActionKind.terminal_command) is False


def test_needs_false_for_type_text() -> None:
    assert PostActionVerifier().needs(ActionKind.type_text) is False


def test_annotate_sets_hashes() -> None:
    v = PostActionVerifier()
    result = ActionResult(kind="click")
    pre = v.phash(_png(50, 50, 50))
    post = v.phash(_png(200, 200, 200))
    v.annotate(result, pre, post)
    assert result.pre_hash == pre
    assert result.post_hash == post


def test_annotate_same_hash_no_exception() -> None:
    v = PostActionVerifier()
    result = ActionResult(kind="click")
    h = v.phash(_png())
    v.annotate(result, h, h)  # should log debug, not raise
    assert result.pre_hash == h
    assert result.post_hash == h
