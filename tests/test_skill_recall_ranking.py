"""SkillLibrary.rank_for_task: only approved skills with vectors are returned."""

import asyncio

import pytest

from agent.daemon.store import RunStore
from agent.learning.skills import SkillLibrary


class _SimpleEmbedder:
    async def embed(self, texts):
        return [[0.5] * 1024 for _ in texts]


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    asyncio.run(s.open())
    return s


def test_rank_returns_approved_only(store):
    async def _run():
        lib = SkillLibrary(store, _SimpleEmbedder())

        # Insert draft skill (no vector needed - won't be ranked anyway)
        await store.insert_skill("s1", "skill1", "desc1", '["focus_window"]', None)

        # Insert approved skill + its vector so it appears in vec queries
        await store.insert_skill("s2", "skill2", "desc2", '["type_text"]', None)
        await store.update_skill_status("s2", "approved")
        if store._vec_ok:
            await store.insert_skill_vec("s2", [0.5] * 1024)

        ranked = await lib.rank_for_task("something")
        ids = [r["skill_id"] for r in ranked]

        if store._vec_ok:
            assert "s2" in ids
            assert "s1" not in ids
        else:
            # vec unavailable → empty result is expected
            assert ranked == []

    asyncio.run(_run())


def test_rank_empty_when_no_approved(store):
    async def _run():
        lib = SkillLibrary(store, _SimpleEmbedder())
        await store.insert_skill("s3", "draft skill", "desc", '["click"]', None)
        ranked = await lib.rank_for_task("task")
        assert ranked == []

    asyncio.run(_run())
