"""Smoke tests for CLI entry-point: --version, --help, subcommand --help."""

from typer.testing import CliRunner

from agent.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "hyprland-agent" in result.stdout


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout


def test_service_help():
    result = runner.invoke(app, ["service", "--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout
    assert "install" in result.stdout
    assert "uninstall" in result.stdout


def test_runs_help():
    result = runner.invoke(app, ["runs", "--help"])
    assert result.exit_code == 0
