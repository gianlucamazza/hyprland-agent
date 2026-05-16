"""Pre-TTS redaction — strip tokens, secrets, and user paths before synthesis.

Two layers of protection:
1. **Portable patterns** — hard-coded regex for API keys, base64 tokens, paths.
2. **Keyword patterns** — user-configured key names whose values are redacted.
"""

from __future__ import annotations

import re

_PORTABLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"sk-[A-Za-z0-9-]{20,}"),  # OpenAI-style secret keys
    re.compile(r"[A-Za-z0-9+/]{40,}=*"),  # base64-encoded tokens
    re.compile(r"/home/[^/\s]+(?:/[^\s,;:)]*)?"),  # /home/... paths
    re.compile(r"~/[^\s,;:)]+"),  # ~/... paths
]


def _build_keyword_patterns(keywords: tuple[str, ...]) -> list[re.Pattern]:
    """Wrap keywords in a value-redacting pattern.

    Matching ``secret=abc123`` or ``api_key: xyz789`` becomes
    ``secret=[REDACTED]`` / ``api_key=[REDACTED]``.
    """
    if not keywords:
        return []
    joined = "|".join(keywords)
    return [re.compile(rf"(?i)({joined})\s*[:=]\s*\S+")]


def redact_for_tts(text: str, keyword_patterns: tuple[str, ...] = ()) -> str:
    """Return *text* with sensitive patterns replaced by ``[REDACTED]``."""
    for pat in _PORTABLE_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    for pat in _build_keyword_patterns(keyword_patterns):
        text = pat.sub(lambda m: m.group(1) + "=[REDACTED]", text)
    return text
