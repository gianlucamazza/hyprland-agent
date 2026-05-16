"""Common async subprocess wrapper with timeout, logging, and env whitelist."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field

from agent.config import ENV_WHITELIST

log = logging.getLogger(__name__)


@dataclass
class ProcResult:
    returncode: int
    stdout: bytes = field(default=b"")
    stderr: bytes = field(default=b"")


def safe_env() -> dict[str, str]:
    """Return a sanitised copy of os.environ containing only whitelisted vars."""
    return {k: v for k, v in os.environ.items() if k in ENV_WHITELIST}


async def run(
    argv: Sequence[str],
    *,
    timeout: float = 10.0,
    capture_stdout: bool = False,
    stdin_data: bytes | None = None,
    env: dict[str, str] | None = None,
) -> ProcResult:
    """Run *argv* and return a ProcResult.

    Raises RuntimeError on timeout; returns non-zero returncode otherwise.
    Does NOT raise on non-zero exit — callers decide what is an error.
    """
    stdout_pipe = asyncio.subprocess.PIPE if capture_stdout else asyncio.subprocess.DEVNULL
    stdin_pipe = asyncio.subprocess.PIPE if stdin_data is not None else None

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=stdout_pipe,
        stderr=asyncio.subprocess.PIPE,
        stdin=stdin_pipe,
        env=env,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin_data), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"{argv[0]} timed out after {timeout}s") from exc

    return ProcResult(
        returncode=proc.returncode or 0,
        stdout=out or b"",
        stderr=err or b"",
    )
