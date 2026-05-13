"""Load credentials at daemon boot — never passed over IPC."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

_OAUTH_PATH = Path.home() / ".claude" / ".credentials.json"


def load_anthropic_token() -> str | None:
    """Read the Claude Code OAuth access token, refreshing if nearly expired."""
    if not _OAUTH_PATH.exists():
        log.warning("Claude OAuth credentials not found at %s", _OAUTH_PATH)
        return None
    try:
        data = json.loads(_OAUTH_PATH.read_text())
        oauth = data.get("claudeAiOauth", {})
        token: str = oauth.get("accessToken", "")
        expires_ms: int = oauth.get("expiresAt", 0)
        if not token:
            log.warning("Claude OAuth: no accessToken in credentials file")
            return None
        remaining_s = (expires_ms - time.time() * 1000) / 1000
        if remaining_s < 60:
            log.warning(
                "Claude OAuth token expires soon (%.0fs) — will auto-refresh",
                remaining_s,
            )
        return token
    except Exception as exc:
        log.error("Failed to read Claude OAuth credentials: %s", exc)
        return None


def load_openai_key() -> str | None:
    """Read OPENAI_API_KEY from the process environment (set at daemon start)."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        log.info("OPENAI_API_KEY not set — OpenAI brain unavailable")
        return None
    return key
