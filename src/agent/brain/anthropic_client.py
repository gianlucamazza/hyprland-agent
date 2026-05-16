"""Build the Anthropic SDK client for ClaudeBrain.

Uses ANTHROPIC_API_KEY (required). Optionally redirects to an
Anthropic-compatible endpoint via ANTHROPIC_BASE_URL (e.g. Z.AI GLM Coding Plan).
"""

from __future__ import annotations

import os

from anthropic import Anthropic

_BETA = "computer-use-2025-11-24"


def anthropic_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Export it (or add it to "
            "~/.config/hyprland-agent/env) before using the claude brain."
        )
    kwargs: dict = {
        "api_key": api_key,
        "default_headers": {"anthropic-beta": _BETA},
        "max_retries": 5,
        "timeout": 60.0,
    }
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    if base_url:
        kwargs["base_url"] = base_url
    return Anthropic(**kwargs)
