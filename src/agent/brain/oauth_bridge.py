"""Resolve Anthropic auth token for computer-use requests.

Priority:
1. CLAUDE_CODE_OAUTH_TOKEN env var — long-lived OAuth token from `claude setup-token`.
2. ~/.claude/.credentials.json — auto-refreshed token held by a running Claude Code session.

Flock-protected to avoid racing with a running Claude Code session when refreshing.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path

import httpx
from anthropic import Anthropic

_CREDS_PATH = Path.home() / ".claude" / ".credentials.json"
_REFRESH_URL = "https://auth.anthropic.com/oauth/token"
_BETA = "oauth-2025-04-20,computer-use-2025-11-24"
_CLOCK_SKEW = 60  # refresh if < 60 s remaining


def _refresh(creds: dict) -> dict:
    oauth = creds["claudeAiOauth"]
    resp = httpx.post(
        _REFRESH_URL,
        json={
            "grant_type": "refresh_token",
            "refresh_token": oauth["refreshToken"],
        },
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    oauth["accessToken"] = body["access_token"]
    oauth["expiresAt"] = int(time.time() * 1000) + body["expires_in"] * 1000
    if "refresh_token" in body:
        oauth["refreshToken"] = body["refresh_token"]
    creds["claudeAiOauth"] = oauth
    return creds


def _load_and_refresh() -> dict:
    with open(_CREDS_PATH, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            creds = json.load(f)
            oauth = creds["claudeAiOauth"]
            expires_ms = oauth.get("expiresAt", 0)
            if time.time() * 1000 + _CLOCK_SKEW * 1000 >= expires_ms:
                creds = _refresh(creds)
                f.seek(0)
                f.truncate()
                json.dump(creds, f, indent=2)
            return creds["claudeAiOauth"]
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def anthropic_client() -> Anthropic:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if not token:
        token = _load_and_refresh()["accessToken"]
    return Anthropic(
        auth_token=token,
        default_headers={"anthropic-beta": _BETA},
        max_retries=5,
        timeout=60.0,
    )
