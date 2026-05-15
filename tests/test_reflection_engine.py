"""Tests for ReflectionEngine rule-based reflections."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agent.daemon.store import RunStore
from agent.learning.reflection import ReflectionEngine
from agent.schemas import RunEventRecord, RunKind, RunStatus, RunSummary


@pytest.fixture
async def store(tmp_path: Path) -> RunStore:
    s = RunStore(path=tmp_path / "runs.db")
    await s.open()
    return s


async def _make_run(store: RunStore, run_id: str, task: str, status: RunStatus) -> None:
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


async def test_reflect_stores_negative_for_failure(store: RunStore) -> None:
    await _make_run(store, "r1", "open keepassxc", RunStatus.errored)
    await store.append_event(
        "r1",
        RunEventRecord(seq=0, ts=time.time(), kind="action", payload={"kind": "click"}),
    )

    engine = ReflectionEngine(store)
    await engine.reflect("r1", "failure")

    rows = await store.list_recent_reflections(polarity="negative", limit=5)
    assert len(rows) == 1
    assert "open keepassxc" in rows[0]["text"]


async def test_reflect_blocked_action_mentions_allowlist(store: RunStore) -> None:
    await _make_run(store, "r2", "open 1password", RunStatus.errored)
    await store.append_event(
        "r2",
        RunEventRecord(
            seq=0,
            ts=time.time(),
            kind="action_result",
            payload={"blocked": "1password always blocked"},
        ),
    )

    engine = ReflectionEngine(store)
    await engine.reflect("r2", "failure")

    rows = await store.list_recent_reflections(polarity="negative")
    assert any("allowlist" in r["text"] for r in rows)


async def test_reflect_stuck_mentions_repeated_action(store: RunStore) -> None:
    await _make_run(store, "r3", "scroll page", RunStatus.aborted)
    for i in range(4):
        await store.append_event(
            "r3",
            RunEventRecord(
                seq=i, ts=time.time(), kind="action", payload={"kind": "scroll"}
            ),
        )

    engine = ReflectionEngine(store)
    await engine.reflect("r3", "stuck")

    rows = await store.list_recent_reflections(polarity="negative")
    assert any("scroll" in r["text"] for r in rows)


async def test_reflect_missing_run_is_silent(store: RunStore) -> None:
    engine = ReflectionEngine(store)
    await engine.reflect("nonexistent", "failure")  # should not raise


async def test_reflect_success_produces_no_reflection(store: RunStore) -> None:
    await _make_run(store, "r4", "open ghostty", RunStatus.completed)

    engine = ReflectionEngine(store)
    await engine.reflect("r4", "success")

    rows = await store.list_recent_reflections(polarity="negative")
    assert len(rows) == 0
