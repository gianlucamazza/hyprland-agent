"""CLI: agent learning list uses RpcMethod.learning_list."""

from typer.testing import CliRunner
from unittest.mock import AsyncMock, MagicMock, patch

from agent.cli import app

runner = CliRunner()


def _mock_conn(items):
    conn = AsyncMock()
    conn.request = AsyncMock(return_value={"items": items})
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    return conn


def test_learning_list_skill_no_items():
    conn = _mock_conn([])
    with patch("agent.client.connection.connect", return_value=conn):
        result = runner.invoke(app, ["learning", "list", "skill"])
    assert result.exit_code == 0
    assert "No skill" in result.output


def test_learning_list_skill_with_items():
    items = [{"id": "abc123", "name": "skill1", "status": "draft"}]
    conn = _mock_conn(items)
    with patch("agent.client.connection.connect", return_value=conn):
        result = runner.invoke(app, ["learning", "list", "skill"])
    assert result.exit_code == 0
    assert "abc123" in result.output


def test_learning_list_rule():
    items = [{"id": "r1", "confidence": 0.9, "status": "proposed"}]
    conn = _mock_conn(items)
    with patch("agent.client.connection.connect", return_value=conn):
        result = runner.invoke(app, ["learning", "list", "rule"])
    assert result.exit_code == 0
    assert "r1" in result.output


def test_learning_list_allowlist():
    items = [{"id": 1, "app_class": "foot", "title_pat": "*", "status": "pending"}]
    conn = _mock_conn(items)
    with patch("agent.client.connection.connect", return_value=conn):
        result = runner.invoke(app, ["learning", "list", "allowlist"])
    assert result.exit_code == 0
    assert "foot" in result.output
