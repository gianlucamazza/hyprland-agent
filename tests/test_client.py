"""Tests for the client library and CLI daemon-down behavior."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agent.client.errors import DaemonUnavailable, ProtocolMismatch, RpcError

# ── import-graph enforcement ──────────────────────────────────────────────────


def test_client_does_not_import_daemon() -> None:
    """agent.client must not pull in agent.daemon at import time."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import agent.client.connection;"
                "import sys;"
                "bad = [k for k in sys.modules if k.startswith('agent.daemon')];"
                "print(bad)"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]", f"daemon modules imported: {result.stdout.strip()}"


# ── DaemonUnavailable ─────────────────────────────────────────────────────────


async def test_connect_raises_daemon_unavailable_when_no_socket(tmp_path: Path) -> None:
    from agent.client.connection import connect

    missing = tmp_path / "no-such.sock"
    with pytest.raises(DaemonUnavailable) as exc_info:
        async with connect(missing):
            pass
    assert "not running" in str(exc_info.value).lower() or "daemon" in str(exc_info.value).lower()
    assert str(missing) in exc_info.value.socket_path


def test_daemon_unavailable_message_contains_systemctl() -> None:
    exc = DaemonUnavailable("/run/user/1000/hyprland-agent.sock")
    msg = str(exc)
    assert "systemctl" in msg


# ── RpcError ──────────────────────────────────────────────────────────────────


def test_rpc_error_attributes() -> None:
    err = RpcError("not_found", "run xyz not found")
    assert err.code == "not_found"
    assert "not_found" in str(err)
    assert "run xyz not found" in str(err)


# ── ProtocolMismatch ──────────────────────────────────────────────────────────


def test_protocol_mismatch_is_exception() -> None:
    exc = ProtocolMismatch("version mismatch: server=2.0 client=1.0")
    assert isinstance(exc, Exception)
    assert "version mismatch" in str(exc)


# ── CLI daemon-down messages ──────────────────────────────────────────────────


def _agent_bin() -> Path:
    """Return path to the 'agent' script in the active venv."""
    return Path(sys.executable).parent / "agent"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Invoke the installed 'agent' binary with no daemon socket available."""
    return subprocess.run(
        [str(_agent_bin()), *args],
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "XDG_RUNTIME_DIR": "/nonexistent-test-dir",  # points to missing socket
        },
    )


def test_cli_hypr_windows_daemon_down_exits_nonzero() -> None:
    result = _run_cli("hypr", "windows")
    assert result.returncode != 0
    assert "daemon" in result.stderr.lower() or "not running" in result.stderr.lower()


def test_cli_runs_list_daemon_down_exits_nonzero() -> None:
    result = _run_cli("runs", "list")
    assert result.returncode != 0


def test_cli_stop_works_without_daemon() -> None:
    """agent stop must succeed even when daemon is unreachable (file flag)."""
    result = _run_cli("stop")
    # stop creates the file flag independently — should exit 0 even if daemon is down
    assert result.returncode == 0
