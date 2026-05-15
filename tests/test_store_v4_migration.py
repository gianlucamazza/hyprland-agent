"""DB migration to v4: skills, learned_rules, allowlist_proposals."""

import asyncio

import pytest

from agent.daemon.store import RunStore


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    asyncio.run(s.open())
    return s


def test_v4_tables_present(store):
    async def _run():
        def _q(conn):
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return {r[0] for r in rows}

        return await store._run_sync(_q)

    tables = asyncio.run(_run())
    assert "skills" in tables
    assert "skill_outcomes" in tables
    assert "learned_rules" in tables
    assert "allowlist_proposals" in tables


def test_v4_user_version(store):
    async def _run():
        def _ver(conn):
            return conn.execute("PRAGMA user_version").fetchone()[0]

        return await store._run_sync(_ver)

    ver = asyncio.run(_run())
    assert ver >= 4
