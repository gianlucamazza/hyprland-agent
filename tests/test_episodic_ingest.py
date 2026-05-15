"""Tests for EpisodicMemory.ingest()."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agent.daemon.store import RunStore
from agent.memory.episodic import EpisodicMemory
from agent.schemas import RunEventRecord, RunKind, RunStatus, RunSummary


class _StubEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(i % 10) / 10.0 for i in range(1024)] for _ in texts]


@pytest.fixture
async def store(tmp_path: Path) -> RunStore:
    s = RunStore(path=tmp_path / "runs.db")
    await s.open()
    return s


@pytest.fixture
def embedder() -> _StubEmbedder:
    return _StubEmbedder()


async def _insert_run(store: RunStore, run_id: str, task: str, status: RunStatus) -> None:
    summary = RunSummary(
        run_id=run_id,
        kind=RunKind.run,
        task=task,
        brain="TestBrain",
        status=status,
        started_at=time.time(),
    )
    await store.insert_run(summary)
    await store.update_run_status(run_id, status)


async def test_ingest_populates_episodes(store: RunStore, embedder: _StubEmbedder) -> None:
    await _insert_run(store, "r1", "open ghostty", RunStatus.completed)
    # Add an action event
    await store.append_event(
        "r1",
        RunEventRecord(seq=0, ts=time.time(), kind="action", payload={"kind": "dispatch_hypr"}),
    )

    mem = EpisodicMemory(store, embedder)
    await mem.ingest("r1")

    import sqlite3

    with sqlite3.connect(str(store._path)) as conn:
        row = conn.execute("SELECT * FROM episodes WHERE run_id='r1'").fetchone()
    assert row is not None
    assert "dispatch_hypr" in row[4]  # summary


async def test_ingest_missing_run_is_silent(store: RunStore, embedder: _StubEmbedder) -> None:
    mem = EpisodicMemory(store, embedder)
    # Should not raise
    await mem.ingest("nonexistent-run-id")


async def test_ingest_extracts_context_class(store: RunStore, embedder: _StubEmbedder) -> None:
    await _insert_run(store, "r2", "focus browser", RunStatus.completed)
    await store.append_event(
        "r2",
        RunEventRecord(
            seq=0,
            ts=time.time(),
            kind="state",
            payload={"active": {"class": "firefox", "title": "Home"}},
        ),
    )
    await store.append_event(
        "r2",
        RunEventRecord(seq=1, ts=time.time(), kind="action", payload={"kind": "focus_window"}),
    )

    mem = EpisodicMemory(store, embedder)
    await mem.ingest("r2")

    import sqlite3

    with sqlite3.connect(str(store._path)) as conn:
        row = conn.execute("SELECT context_class FROM episodes WHERE run_id='r2'").fetchone()
    assert row is not None
    assert row[0] == "firefox"


async def test_ingest_blocked_count_in_summary(store: RunStore, embedder: _StubEmbedder) -> None:
    await _insert_run(store, "r3", "open 1password", RunStatus.errored)
    await store.append_event(
        "r3",
        RunEventRecord(
            seq=0,
            ts=time.time(),
            kind="action_result",
            payload={"blocked": "1password is always blocked"},
        ),
    )

    mem = EpisodicMemory(store, embedder)
    await mem.ingest("r3")

    import sqlite3

    with sqlite3.connect(str(store._path)) as conn:
        row = conn.execute("SELECT summary FROM episodes WHERE run_id='r3'").fetchone()
    assert row is not None
    assert "blocked" in row[0]
