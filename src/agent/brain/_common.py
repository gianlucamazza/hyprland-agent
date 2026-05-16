"""Shared constants and helpers for brain implementations."""

from __future__ import annotations

import base64
import logging
from typing import Any

from agent.config import DEFAULT_MAX_ITER

log = logging.getLogger(__name__)

SCALE: float = 0.5
MAX_LOOP: int = DEFAULT_MAX_ITER

# Approximate: 4 chars per text token, 1000 tokens per megapixel for images.
_CHARS_PER_TOKEN = 4
_TOKENS_PER_MEGAPIXEL = 1000


def png_b64(png: bytes) -> str:
    return base64.standard_b64encode(png).decode()


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token count for a message list.

    Uses a simple heuristic: 4 chars per text token + image size estimate.
    This is intentionally approximate -- the goal is budgeting, not precision.
    """
    total = 0
    for msg in messages:
        content = msg.get("content")
        if content is None:
            total += 4
            continue
        if isinstance(content, str):
            total += len(content) // _CHARS_PER_TOKEN
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    total += len(block.get("text", "")) // _CHARS_PER_TOKEN
                elif btype in ("image", "image_url"):
                    total += _TOKENS_PER_MEGAPIXEL // 2
                elif btype == "tool_result":
                    cval = block.get("content")
                    if isinstance(cval, str):
                        total += len(cval) // _CHARS_PER_TOKEN
                    elif isinstance(cval, list):
                        for sub in cval:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                total += len(sub.get("text", "")) // _CHARS_PER_TOKEN
        total += 4  # role/metadata overhead per message
    return total


def compact_messages(
    messages: list[dict[str, Any]],
    *,
    keep_rounds: int = 3,
    budget_tokens: int = 160_000,
) -> list[dict[str, Any]]:
    """Compact messages to fit within budget.

    Strategy: keep system prompt (first message if role=system) + last N rounds.
    A "round" starts at each user message.  Returns the compacted message list.
    """
    if estimate_tokens(messages) <= budget_tokens:
        return messages

    if len(messages) <= 1:
        return messages

    # Separate system prompt if present.
    system: list[dict[str, Any]] = []
    rest_start = 0
    if messages[0].get("role") == "system":
        system = messages[:1]
        rest_start = 1
    rest = messages[rest_start:]

    if not rest:
        return messages

    # Find round boundaries (user messages start a new round).
    round_starts: list[int] = []
    for i, msg in enumerate(rest):
        if msg.get("role") == "user":
            round_starts.append(i)

    if not round_starts:
        return messages

    # Keep last N rounds.
    keep_from = round_starts[-keep_rounds] if len(round_starts) > keep_rounds else round_starts[0]

    kept = system + rest[keep_from:]

    dropped = len(messages) - len(kept)
    log.warning(
        "Context compacted: %d -> %d messages (%d dropped), ~%d estimated tokens",
        len(messages),
        len(kept),
        dropped,
        estimate_tokens(kept),
    )

    return kept
