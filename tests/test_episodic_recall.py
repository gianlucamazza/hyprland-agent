"""Tests for EpisodicMemory.recall()."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agent.daemon.store import RunStore
from agent.memory.episodic import Episode, EpisodicMemory
from agent.schemas import RunKind, RunStatus, RunSummary


class _DeterministicEmbedder:
    """Returns a fixed embedding based on text hash — stable across calls."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        results = []
        for t in texts:
            seed = int(hashlib.md5(t.encode()).hexdigest(), 16)
            vec = [(((seed >> i) & 0xFF) / 255.0) for i in range(1024)]
            results.append(vec)
        return results


@pytest.fixture
async def populated_store(tmp_path: Path) -> RunStore:
    s = RunStore(path=tmp_path / "runs.db")
    await s.open()

    embedder = _DeterministicEmbedder()
    mem = EpisodicMemory(s, embedder)

    episodes = [
        ("r1", "open ghostty", "success"),
        ("r2", "launch ghostty terminal", "success"),
        ("r3", "open firefox browser", "success"),
        ("r4", "focus keepassxc", "failure"),
        ("r5", "open spotify music", "success"),
    ]
    for run_id, task, outcome in episodes:
        summary = RunSummary(
            run_id=run_id,
            kind=RunKind.run,
            task=task,
            brain="TestBrain",
            status=RunStatus.completed if outcome == "success" else RunStatus.errored,
            started_at=time.time(),
        )
        await s.insert_run(summary)
        await s.insert_episode(
            run_id=run_id,
            task=task,
            outcome=outcome,
            summary=f"1 actions",
            context_class=None,
            actions_json="[]",
        )
        embs = await embedder.embed([task])
        await s.insert_episode_vec(run_id, embs[0])

    return s


async def test_recall_returns_episodes(populated_store: RunStore) -> None:
    mem = EpisodicMemory(populated_store, _DeterministicEmbedder())
    results = await mem.recall("open ghostty", k=3)
    assert len(results) >= 1
    assert all(isinstance(e, Episode) for e in results)


async def test_recall_filters_failure_by_default(populated_store: RunStore) -> None:
    mem = EpisodicMemory(populated_store, _DeterministicEmbedder())
    results = await mem.recall("focus keepassxc", k=5)
    outcomes = {e.outcome for e in results}
    assert "failure" not in outcomes


async def test_recall_includes_failure_when_asked(populated_store: RunStore) -> None:
    mem = EpisodicMemory(populated_store, _DeterministicEmbedder())
    results = await mem.recall("keepassxc", k=5, filter_failure=False)
    outcomes = {e.outcome for e in results}
    assert "failure" in outcomes


async def test_recall_respects_k(populated_store: RunStore) -> None:
    mem = EpisodicMemory(populated_store, _DeterministicEmbedder())
    results = await mem.recall("open something", k=2)
    assert len(results) <= 2


async def test_recall_empty_db_returns_empty(tmp_path: Path) -> None:
    s = RunStore(path=tmp_path / "empty.db")
    await s.open()
    mem = EpisodicMemory(s, _DeterministicEmbedder())
    results = await mem.recall("anything", k=3)
    assert results == []
