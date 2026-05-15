"""SAFETY: allowlist proposal in DB does NOT open the gate until approved+written."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agent.daemon.store import RunStore
from agent.schemas import Window
from agent.safety.allowlist import is_allowed


def _window(cls: str) -> Window:
    return Window(
        address="0x1",
        app_class=cls,
        title="test",
        workspace_id=1,
        at=(0, 0),
        size=(100, 100),
        floating=False,
        hidden=False,
        pid=1,
        monitor=0,
    )


def test_pending_proposal_does_not_allow(tmp_path):
    """Upserting an allowlist proposal keeps is_allowed() returning False."""
    store = RunStore(tmp_path / "runs.db")
    import asyncio

    asyncio.run(store.open())

    async def _insert():
        await store.upsert_allowlist_proposal("myapp", "*")

    asyncio.run(_insert())

    # is_allowed reads from the YAML file, not from the DB proposals table
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_path = Path(tmpdir) / "allowlist.yaml"
        # file does not exist → deny all
        with patch("agent.safety.allowlist._CONFIG_PATH", fake_path):
            assert is_allowed(_window("myapp")) is False


def test_approve_writes_yaml_then_allows(tmp_path):
    """After approve(), _append_allowlist_entry writes the YAML, making is_allowed True."""
    import yaml

    from agent.learning.api import _append_allowlist_entry

    allowlist_yaml = tmp_path / "allowlist.yaml"

    with patch("agent.learning.api._ALLOWLIST_PATH", allowlist_yaml):
        _append_allowlist_entry("myapp", "*")

    assert allowlist_yaml.exists()
    data = yaml.safe_load(allowlist_yaml.read_text())
    assert {"class": "myapp", "title": "*"} in data["allow"]

    # Now patch allowlist module to read our file
    with patch("agent.safety.allowlist._CONFIG_PATH", allowlist_yaml):
        assert is_allowed(_window("myapp")) is True
