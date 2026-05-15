"""SkillLibrary.extract_candidate: deterministic extraction from run record."""

import asyncio
import time
import uuid

import pytest

from agent.daemon.store import RunStore
from agent.learning.skills import SkillLibrary
from agent.schemas import RunEventRecord, RunStatus, RunSummary


class _StubEmbedder:
    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    asyncio.run(s.open())
    return s


@pytest.fixture
def library(store):
    return SkillLibrary(store, _StubEmbedder())


def _summary(task: str, brain: str = "claude") -> RunSummary:
    return RunSummary(
        run_id=uuid.uuid4().hex,
        task=task,
        brain=brain,
        status=RunStatus.completed,
        started_at=time.time(),
    )


async def _insert_run_with_actions(store: RunStore, task: str, kinds: list[str]) -> str:
    s = _summary(task)
    await store.insert_run(s)
    for seq, k in enumerate(kinds):
        await store.append_event(
            s.run_id,
            RunEventRecord(seq=seq, ts=time.time(), kind="action", payload={"kind": k}),
        )
    await store.upsert_run_outcome(s.run_id, "success", 1.0, "explicit")
    return s.run_id


def test_extract_returns_skill_id(store, library):
    async def _run():
        run_id = await _insert_run_with_actions(
            store, "open browser", ["focus_window", "type_text"]
        )
        skill_id = await library.extract_candidate(run_id)
        assert skill_id is not None
        assert len(skill_id) == 32  # md5 hex

    asyncio.run(_run())


def test_extract_deterministic(store, library):
    """Same task + same actions → same skill_id."""

    async def _run():
        run_id1 = await _insert_run_with_actions(store, "resize window", ["dispatch_hypr"])
        run_id2 = await _insert_run_with_actions(store, "resize window", ["dispatch_hypr"])
        id1 = await library.extract_candidate(run_id1)
        id2 = await library.extract_candidate(run_id2)
        assert id1 == id2

    asyncio.run(_run())


def test_extract_none_for_boring_only(store, library):
    """Only screenshot actions → no skill extracted."""

    async def _run():
        run_id = await _insert_run_with_actions(store, "check screen", ["screenshot"])
        skill_id = await library.extract_candidate(run_id)
        assert skill_id is None

    asyncio.run(_run())


def test_extract_none_for_missing_run(store, library):
    async def _run():
        result = await library.extract_candidate("nonexistent-run")
        assert result is None

    asyncio.run(_run())
