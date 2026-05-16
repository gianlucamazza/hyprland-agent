"""DB migration to v4: skills, learned_rules, allowlist_proposals."""

import pytest

from agent.daemon.store import RunStore


@pytest.fixture
async def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    await s.open()
    return s


@pytest.mark.asyncio
async def test_v4_tables_present(store):
    def _q(conn):
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r[0] for r in rows}

    tables = await store.run_sync(_q)
    assert "skills" in tables
    assert "skill_outcomes" in tables
    assert "learned_rules" in tables
    assert "allowlist_proposals" in tables


@pytest.mark.asyncio
async def test_v4_user_version(store):
    def _ver(conn):
        return conn.execute("PRAGMA user_version").fetchone()[0]

    ver = await store.run_sync(_ver)
    assert ver >= 4
