"""Tests for RunStore v3 migration: episodes, reflections, episode_vecs."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from agent.daemon.store import RunStore


@pytest.fixture
async def fresh_store(tmp_path: Path) -> RunStore:
    s = RunStore(path=tmp_path / "runs.db")
    await s.open()
    return s


async def test_v3_migration_bumps_user_version(
    fresh_store: RunStore, tmp_path: Path
) -> None:
    with sqlite3.connect(str(tmp_path / "runs.db")) as conn:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
    assert ver >= 3  # v4 is applied after v3 in the same open() call


async def test_episodes_table_exists(fresh_store: RunStore, tmp_path: Path) -> None:
    with sqlite3.connect(str(tmp_path / "runs.db")) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "episodes" in tables
    assert "reflections" in tables


async def test_insert_and_retrieve_episode(
    fresh_store: RunStore, tmp_path: Path
) -> None:
    # Need a runs row first (FK constraint)
    from agent.schemas import RunKind, RunStatus, RunSummary
    import time

    summary = RunSummary(
        run_id="r1",
        kind=RunKind.run,
        task="open ghostty",
        brain="TestBrain",
        status=RunStatus.completed,
        started_at=time.time(),
    )
    await fresh_store.insert_run(summary)

    await fresh_store.insert_episode(
        run_id="r1",
        task="open ghostty",
        outcome="success",
        summary="1 actions: dispatch_hypr",
        context_class="foot",
        actions_json='["dispatch_hypr"]',
    )

    with sqlite3.connect(str(tmp_path / "runs.db")) as conn:
        row = conn.execute("SELECT * FROM episodes WHERE run_id='r1'").fetchone()
    assert row is not None
    assert row[1] == "open ghostty"  # task
    assert row[3] == "success"  # outcome


async def test_insert_reflection(fresh_store: RunStore, tmp_path: Path) -> None:
    from agent.schemas import RunKind, RunStatus, RunSummary
    import time

    summary = RunSummary(
        run_id="r2",
        kind=RunKind.run,
        task="task",
        brain="TestBrain",
        status=RunStatus.errored,
        started_at=time.time(),
    )
    await fresh_store.insert_run(summary)
    await fresh_store.insert_reflection(
        "r2", "negative", "Do not click randomly.", "TestBrain"
    )

    rows = await fresh_store.list_recent_reflections(polarity="negative", limit=5)
    assert len(rows) == 1
    assert rows[0]["text"] == "Do not click randomly."


async def test_vec_ok_flag(fresh_store: RunStore) -> None:
    # If sqlite-vec is installed, _vec_ok should be True
    assert fresh_store._vec_ok is True


async def test_episode_vec_insert_and_query(
    fresh_store: RunStore, tmp_path: Path
) -> None:
    from agent.schemas import RunKind, RunStatus, RunSummary
    import time

    for i, task in enumerate(
        ["open firefox", "launch ghostty", "open firefox browser"]
    ):
        summary = RunSummary(
            run_id=f"rv{i}",
            kind=RunKind.run,
            task=task,
            brain="TestBrain",
            status=RunStatus.completed,
            started_at=time.time(),
        )
        await fresh_store.insert_run(summary)
        await fresh_store.insert_episode(
            run_id=f"rv{i}",
            task=task,
            outcome="success",
            summary=f"1 actions: dispatch_hypr",
            context_class=None,
            actions_json="[]",
        )
        emb = [float(j % 10) / 10.0 for j in range(1024)]
        await fresh_store.insert_episode_vec(f"rv{i}", emb)

    results = await fresh_store.query_episodes_by_vec(
        [float(j % 10) / 10.0 for j in range(1024)], k=2
    )
    assert len(results) <= 2
    assert all("task" in r for r in results)
