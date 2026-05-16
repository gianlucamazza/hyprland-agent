"""Optional JSONL audit log — append-only, disabled by default."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from agent.config import CACHE_DIR

_DEFAULT_DIR = CACHE_DIR / "audit"


class AuditLog:
    """Async JSONL writer. No-op when ``enabled=False``."""

    def __init__(self, enabled: bool = False, directory: Path = _DEFAULT_DIR) -> None:
        self._enabled = enabled
        self._dir = directory
        self._lock = asyncio.Lock()
        self._path: Path | None = None

    async def open(self) -> None:
        if not self._enabled:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        self._path = self._dir / f"{ts}.jsonl"

    async def write(self, entry: dict[str, Any]) -> None:
        if not self._enabled or self._path is None:
            return
        line = json.dumps(entry) + "\n"
        async with self._lock:
            loop = asyncio.get_running_loop()
            path = self._path

            def _append() -> None:
                with open(path, "a") as f:
                    f.write(line)

            await loop.run_in_executor(None, _append)

    async def close(self) -> None:
        pass  # file handles are opened per-write; nothing to close
