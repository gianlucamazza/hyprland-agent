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


# ── config init-allowlist: --yes skips confirmation on overwrite ─────────────


def test_config_init_allowlist_no_overwrite_prompt_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("agent.safety.allowlist.create_default_config"):
        result = runner.invoke(app, ["config", "init-allowlist", "--yes"])
    assert result.exit_code == 0


def test_config_init_allowlist_yes_skips_confirm(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    allowlist = tmp_path / ".config" / "hyprland-agent" / "allowlist.yaml"
    allowlist.parent.mkdir(parents=True)
    allowlist.touch()
    with (
        patch("agent.config.CONFIG_DIR", allowlist.parent),
        patch("agent.safety.allowlist.create_default_config"),
    ):
        result = runner.invoke(app, ["config", "init-allowlist", "--yes"])
    assert result.exit_code == 0


# ── config bind-killswitch: --yes + --force ───────────────────────────────────


def test_config_bind_killswitch_yes(tmp_path):
    conf = tmp_path / "hyprland.conf"
    conf.write_text("# existing config\n")
    with (
        patch("agent.cli.config.HYPR_CONF_PATH", conf),
        patch("agent.cli.config.resolve_agent_bin", return_value="/usr/bin/agent"),
    ):
        result = runner.invoke(app, ["config", "bind-killswitch", "--yes"])
    assert result.exit_code == 0
    assert "agent stop" in conf.read_text()


def test_config_bind_killswitch_idempotent_without_force(tmp_path):
    conf = tmp_path / "hyprland.conf"
    conf.write_text("bind = SUPER SHIFT, escape, exec, /usr/bin/agent stop\n")
    with patch("agent.cli.config.HYPR_CONF_PATH", conf):
        result = runner.invoke(app, ["config", "bind-killswitch", "--yes"])
    assert result.exit_code == 0
    assert "already present" in result.output


def test_config_bind_killswitch_force_rewrites(tmp_path):
    conf = tmp_path / "hyprland.conf"
    conf.write_text("bind = SUPER SHIFT, escape, exec, /old/agent stop\n")
    with (
        patch("agent.cli.config.HYPR_CONF_PATH", conf),
        patch("agent.cli.config.resolve_agent_bin", return_value="/new/agent"),
    ):
        result = runner.invoke(app, ["config", "bind-killswitch", "--yes", "--force"])
    assert result.exit_code == 0
    text = conf.read_text()
    assert "/new/agent stop" in text


# ── service install: --dry-run + --yes ────────────────────────────────────────


def test_service_install_dry_run(tmp_path):
    with (
        patch("agent.cli.service.SYSTEMD_USER_DIR", tmp_path),
        patch("agent.cli.service.resolve_agent_bin", return_value="/usr/bin/agent"),
    ):
        result = runner.invoke(app, ["service", "install", "--dry-run"])
    assert result.exit_code == 0
    assert "Would write" in result.output
    assert "daemon-reload" in result.output
    assert not (tmp_path / "hyprland-agent.service").exists()


def test_service_install_yes(tmp_path):
    with (
        patch("agent.cli.service.SYSTEMD_USER_DIR", tmp_path),
        patch("agent.cli.service.resolve_agent_bin", return_value="/usr/bin/agent"),
        patch("subprocess.run"),
    ):
        result = runner.invoke(app, ["service", "install", "--yes"])
    assert result.exit_code == 0
    assert (tmp_path / "hyprland-agent.service").exists()


# ── service uninstall: nothing to remove path ─────────────────────────────────


def test_service_uninstall_nothing_to_remove(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.paths.CONFIG_DIR", tmp_path / ".config" / "hyprland-agent")
    monkeypatch.setattr("agent.paths.CACHE_DIR", tmp_path / ".cache" / "hyprland-agent")
    monkeypatch.setattr("agent.paths.SYSTEMD_USER_DIR", tmp_path / ".config" / "systemd" / "user")
    result = runner.invoke(app, ["service", "uninstall"])
    assert result.exit_code == 0
    assert "Nothing to remove" in result.output


def test_service_uninstall_removes_dirs(tmp_path):

    cfg_dir = tmp_path / ".config" / "hyprland-agent"
    cfg_dir.mkdir(parents=True)
    cache_dir = tmp_path / ".cache" / "hyprland-agent"
    cache_dir.mkdir(parents=True)

    with (
        patch("agent.paths.CONFIG_DIR", cfg_dir),
        patch("agent.paths.CACHE_DIR", cache_dir),
        patch("agent.paths.SYSTEMD_USER_DIR", tmp_path / ".config" / "systemd" / "user"),
        patch("subprocess.run"),
    ):
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
