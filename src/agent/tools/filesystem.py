"""Filesystem operations for the agent."""

from __future__ import annotations

import json
import os
from pathlib import Path

_HOME = Path.home()
_DEFAULT_READ_CAP = 65536  # 64 KB


def _resolve_and_check(path: str, allowed_prefixes: tuple[Path, ...] | None = None) -> Path:
    """Resolve path and verify it stays within allowed prefixes."""
    p = Path(path).expanduser().resolve()
    prefixes = allowed_prefixes or (_HOME,)
    if not any(str(p).startswith(str(prefix)) for prefix in prefixes):
        raise PermissionError(f"Path {p} is outside allowed prefixes")
    if p.is_symlink():
        target = p.resolve()
        if not any(str(target).startswith(str(prefix)) for prefix in prefixes):
            raise PermissionError(f"Symlink {p} resolves outside allowed prefixes")
    return p


async def read_file(
    path: str, *, offset: int = 0, limit: int = 0, read_cap: int = _DEFAULT_READ_CAP
) -> str:
    """Read a file, returning up to *read_cap* bytes from *offset*."""
    p = _resolve_and_check(path)
    if not p.is_file():
        raise FileNotFoundError(f"Not a file: {p}")
    text = p.read_text(errors="replace")
    if offset:
        text = text[offset:]
    if limit:
        text = text[:limit]
    total = len(text)
    if total > read_cap:
        text = text[-read_cap:]
        text = f"... [truncated, {total} total chars, showing last {len(text)}]\n{text}"
    return text


async def write_file(path: str, content: str, *, append: bool = False) -> None:
    """Write *content* to a file, creating parent directories as needed."""
    p = _resolve_and_check(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(p, mode) as f:
        f.write(content)


async def list_dir(path: str, *, recursive: bool = False) -> str:
    """List directory contents as JSON with file sizes."""
    p = _resolve_and_check(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {p}")
    entries: list[dict[str, str | int]] = []
    base = p
    for root, dirs, files in os.walk(p):
        if not recursive and root != str(p):
            dirs.clear()
            continue
        for name in files:
            fp = Path(root) / name
            try:
                st = fp.stat()
                entries.append(
                    {"name": str(fp.relative_to(base)), "type": "file", "size": st.st_size}
                )
            except (PermissionError, FileNotFoundError):
                pass
        for name in dirs:
            dp = Path(root) / name
            entries.append({"name": str(dp.relative_to(base)), "type": "dir"})
        if not recursive:
            break
    return json.dumps(entries, indent=2)
