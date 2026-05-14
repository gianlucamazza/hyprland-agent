"""Tests for SQLite RunStore."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import pytest

from agent.daemon.store import RunStore
from agent.schemas import RunEventRecord, RunKind, RunRecord, RunStatus, RunSummary


def _summary(run_id: str = "run-1", **kwargs) -> RunSummary:
    defaults = dict(
        run_id=run_id,
        kind=RunKind.run,
        task="open foot",
        brain="claude",
        status=RunStatus.running,
        started_at=time.time(),
        ended_at=None,
    )
    defaults.update(kwargs)
    return RunSummary(**defaults)


def _event(seq: int, kind: str = "action") -> RunEventRecord:
    return RunEventRecord(seq=seq, ts=time.time(), kind=kind, payload={"seq": seq})


@pytest.fixture
async def store(tmp_path: Path):
    s = RunStore(path=tmp_path / "runs.db")
    await s.open()
    yield s
    await s.close()


# --- insert and retrieve ---


async def test_insert_and_list(store: RunStore) -> None:
    await store.insert_run(_summary("r1"))
    runs = await store.list_runs()
    assert len(runs) == 1
    assert runs[0].run_id == "r1"
    assert runs[0].kind == RunKind.run
    assert runs[0].status == RunStatus.running


async def test_insert_plan_kind(store: RunStore) -> None:
    await store.insert_run(_summary("p1", kind=RunKind.plan))
    runs = await store.list_runs()
    assert runs[0].kind == RunKind.plan


async def test_list_multiple_ordered_by_started_at(store: RunStore) -> None:
    t = time.time()
    await store.insert_run(_summary("r1", started_at=t))
    await store.insert_run(_summary("r2", started_at=t + 1))
    runs = await store.list_runs()
    assert runs[0].run_id == "r2"
    assert runs[1].run_id == "r1"


async def test_list_limit(store: RunStore) -> None:
    for i in range(5):
        await store.insert_run(_summary(f"r{i}", started_at=time.time() + i))
    runs = await store.list_runs(limit=3)
    assert len(runs) == 3


async def test_get_run_not_found(store: RunStore) -> None:
    result = await store.get_run("nonexistent")
    assert result is None


async def test_get_run_with_events(store: RunStore) -> None:
    await store.insert_run(_summary("r1"))
    await store.append_event("r1", _event(0, "start"))
    await store.append_event("r1", _event(1, "action"))

    record = await store.get_run("r1")
    assert record is not None
    assert isinstance(record, RunRecord)
    assert len(record.events) == 2
    assert record.events[0].kind == "start"
    assert record.events[1].kind == "action"


async def test_legacy_run_table_is_rebuilt(tmp_path: Path) -> None:
    db_path = tmp_path / "runs.db"
    legacy_col = "dry" + "_run"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"""
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                brain TEXT NOT NULL,
                {legacy_col} INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at REAL NOT NULL,
                ended_at REAL,
                error_text TEXT
            )
            """
        )
        conn.execute(
            "CREATE TABLE run_events ("
            "run_id TEXT NOT NULL REFERENCES runs(run_id),"
            "seq INTEGER NOT NULL,"
            "ts REAL NOT NULL,"
            "kind TEXT NOT NULL,"
            "payload_json TEXT NOT NULL,"
            "PRIMARY KEY (run_id, seq)"
            ")"
        )
        conn.execute(
            f"INSERT INTO runs (run_id, task, brain, {legacy_col}, status, started_at)"
            " VALUES ('r1', 'task', 'auto', 0, 'completed', ?)",
            (time.time(),),
        )
        conn.execute(
            "INSERT INTO run_events (run_id, seq, ts, kind, payload_json)"
            " VALUES ('r1', 0, ?, 'start', '{}')",
            (time.time(),),
        )
        conn.commit()

    store = RunStore(path=db_path)
    await store.open()
    record = await store.get_run("r1")
    await store.close()

    assert record is not None
    assert record.kind == RunKind.run
    assert record.events[0].kind == "start"
    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    assert legacy_col not in cols


# --- update status ---


async def test_update_run_status(store: RunStore) -> None:
    await store.insert_run(_summary("r1"))
    await store.update_run_status("r1", RunStatus.completed)
    runs = await store.list_runs()
    assert runs[0].status == RunStatus.completed
    assert runs[0].ended_at is not None


async def test_update_status_invalidates_lru(store: RunStore) -> None:
    await store.insert_run(_summary("r1"))
    # Populate LRU
    r1 = await store.get_run("r1")
    assert r1 is not None
    assert r1.status == RunStatus.running
    # Update then re-fetch — should see new status
    await store.update_run_status("r1", RunStatus.completed)
    r1_fresh = await store.get_run("r1")
    assert r1_fresh is not None
    assert r1_fresh.status == RunStatus.completed


# --- LRU cache ---


async def test_lru_cache_hit(store: RunStore) -> None:
    await store.insert_run(_summary("r1"))
    r_first = await store.get_run("r1")
    r_second = await store.get_run("r1")
    # Both should return identical data
    assert r_first is not None and r_second is not None
    assert r_first.run_id == r_second.run_id


async def test_lru_eviction(store: RunStore, tmp_path: Path) -> None:
    from agent.daemon.store import _LRU_CAPACITY

    # Insert more runs than the LRU capacity
    for i in range(_LRU_CAPACITY + 2):
        await store.insert_run(_summary(f"r{i}"))

    # Load all of them into the cache
    for i in range(_LRU_CAPACITY + 2):
        await store.get_run(f"r{i}")

    # Cache should not exceed capacity
    assert len(store._lru) <= _LRU_CAPACITY


# --- concurrent writes ---


async def test_concurrent_event_appends(store: RunStore) -> None:
    await store.insert_run(_summary("r1"))
    seqs = list(range(10))
    await asyncio.gather(*[store.append_event("r1", _event(s)) for s in seqs])
    record = await store.get_run("r1")
    assert record is not None
    assert len(record.events) == 10
