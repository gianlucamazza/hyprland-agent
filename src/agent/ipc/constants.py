"""IPC constants shared by daemon and clients."""

from __future__ import annotations

import os
from pathlib import Path

SOCKET_PATH: Path = (
    Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "hyprland-agent.sock"
)

PROTOCOL_VERSION = "1.0"
PROTOCOL_MAJOR = 1

FRAME_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB per NDJSON line

HEARTBEAT_INTERVAL = 30.0  # seconds between ping/pong
