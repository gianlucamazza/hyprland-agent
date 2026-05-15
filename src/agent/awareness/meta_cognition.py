"""Meta-cognition: loop detection and post-action visual verification."""

from __future__ import annotations

import io
import json
import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.schemas import Action, ActionKind, ActionResult

log = logging.getLogger(__name__)

_VISUAL_KINDS = {
    "mouse_move",
    "click",
    "scroll",
    "focus_window",
    "dispatch",
}


class StuckError(Exception):
    """Raised by orchestrator when loop detector reports stuck state."""


class LoopDetector:
    """Detects repetitive action patterns that indicate a stuck agent."""

    def __init__(self, window: int = 6, repeat_threshold: int = 3) -> None:
        self._history: deque[str] = deque(maxlen=window)
        self._threshold = repeat_threshold

    def observe(self, action: Action) -> bool:
        """Record *action* and return True if stuck threshold is reached."""
        key = json.dumps(
            {"kind": action.kind.value, "params": action.params}, sort_keys=True
        )
        self._history.append(key)
        count = sum(1 for k in self._history if k == key)
        return count >= self._threshold

    def reset(self) -> None:
        self._history.clear()


class PostActionVerifier:
    """Computes perceptual hashes of screenshots to detect visual changes."""

    def phash(self, png_bytes: bytes) -> str:
        """Return an 8-byte dHash hex string for *png_bytes*."""
        from PIL import Image

        img = (
            Image.open(io.BytesIO(png_bytes)).convert("L").resize((9, 8), Image.LANCZOS)
        )
        pixels = img.tobytes()  # grayscale: each byte is one pixel intensity
        bits = []
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                bits.append("1" if left > right else "0")
        return hex(int("".join(bits), 2))[2:].zfill(16)

    def needs(self, kind: ActionKind) -> bool:
        """Return True if *kind* typically produces a visible screen change."""
        return kind.value in _VISUAL_KINDS

    def annotate(
        self, result: ActionResult, pre_hash: str, post_hash: str
    ) -> ActionResult:
        """Set pre_hash / post_hash on *result* and warn if screen unchanged."""
        result.pre_hash = pre_hash
        result.post_hash = post_hash
        if pre_hash == post_hash:
            log.debug("No visual change after %s", result.kind)
        return result
