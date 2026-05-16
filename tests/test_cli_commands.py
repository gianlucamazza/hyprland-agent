"""CLI command tests — graceful failure paths and daemon-free commands."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import patch

from typer.testing import CliRunner

from agent.cli import app
from agent.cli._common import ExitCode
from agent.client.errors import DaemonUnavailable

runner = CliRunner()


@asynccontextmanager
async def _unavailable_connect(*args, **kwargs):
    raise DaemonUnavailable("socket not found")
    yield  # pragma: no cover


# ── daemon-dependent commands: force DaemonUnavailable via mock ──────────────


def test_cmd_run_no_daemon():
    with patch("agent.client.connection.connect", _unavailable_connect):
        result = runner.invoke(app, ["run", "open a terminal"])
    assert result.exit_code == ExitCode.daemon_unavailable


def test_cmd_plan_no_daemon():
    with patch("agent.client.connection.connect", _unavailable_connect):
        result = runner.invoke(app, ["plan", "open a terminal"])
    assert result.exit_code == ExitCode.daemon_unavailable


def test_cmd_status_no_daemon():
    with patch("agent.client.connection.connect", _unavailable_connect):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == ExitCode.daemon_unavailable


# ── cmd_stop: arms killswitch locally, swallows daemon error ─────────────────


def test_cmd_stop_with_yes(tmp_path):
    flag = tmp_path / "STOP"

    def _consume(coro):
        coro.close()

    with patch("agent.safety.killswitch._FLAG", flag), patch("asyncio.run", side_effect=_consume):
        result = runner.invoke(app, ["stop", "--yes"])
    assert result.exit_code == 0
    assert flag.exists()


# ── cmd_doctor: standalone, no daemon needed ─────────────────────────────────


def test_cmd_doctor_runs_without_daemon():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in (0, 1)
    assert len(result.output) > 10


def test_cmd_doctor_json_output():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code in (0, 1)
    checks = json.loads(result.output)
    assert isinstance(checks, list)
    assert all("name" in c for c in checks)


# ── service uninstall: nothing to remove path ─────────────────────────────────


def test_service_uninstall_nothing_to_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["service", "uninstall"])
    assert result.exit_code == 0
    assert "Nothing to remove" in result.output


def test_service_uninstall_removes_dirs(tmp_path):

    cfg_dir = tmp_path / ".config" / "hyprland-agent"
    cfg_dir.mkdir(parents=True)
    cache_dir = tmp_path / ".cache" / "hyprland-agent"
    cache_dir.mkdir(parents=True)

    with patch("pathlib.Path.home", return_value=tmp_path), patch("subprocess.run"):
        result = runner.invoke(app, ["service", "uninstall", "--yes"])

    assert result.exit_code == 0
    assert not cfg_dir.exists()
    assert not cache_dir.exists()
    assert "Uninstall complete" in result.output


# ── subcommand --help paths ───────────────────────────────────────────────────


def test_runs_list_help():
    result = runner.invoke(app, ["runs", "list", "--help"])
    assert result.exit_code == 0


def test_hypr_help():
    result = runner.invoke(app, ["hypr", "--help"])
    assert result.exit_code == 0


def test_learning_help():
    result = runner.invoke(app, ["learning", "--help"])
    assert result.exit_code == 0


def test_config_help():
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0


def test_memory_help():
    result = runner.invoke(app, ["memory", "--help"])
    assert result.exit_code == 0
