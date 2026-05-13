"""Client-side error types."""

from __future__ import annotations


class DaemonUnavailable(Exception):
    """Raised when the daemon socket cannot be reached."""

    def __init__(self, socket_path: str) -> None:
        super().__init__(
            f"Daemon not running (socket: {socket_path}).\n"
            f"Start it with: systemctl --user start hyprland-agent"
        )
        self.socket_path = socket_path


class ProtocolMismatch(Exception):
    """Raised when client and daemon protocol major versions differ."""


class RpcError(Exception):
    """Raised when the daemon returns an error response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
