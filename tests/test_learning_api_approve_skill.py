"""learning.api.approve: skill approval updates DB status."""

import asyncio
import pytest

from agent.daemon.store import RunStore
from agent.learning.api import approve, reject


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    import asyncio; asyncio.run(s.open())
    return s


def test_approve_skill_changes_status(store):
    async def _run():
        await store.insert_skill("sk1", "my skill", "desc", '["focus_window"]', None)
        result = await approve("skill", "sk1", store)
        assert result["status"] == "approved"

        rows = await store.list_skills(status="approved")
        assert any(r["skill_id"] == "sk1" for r in rows)

    asyncio.run(_run())


def test_reject_skill_changes_status(store):
    async def _run():
        await store.insert_skill("sk2", "bad skill", "desc", '["type_text"]', None)
        result = await reject("skill", "sk2", store, reason="not useful")
        assert result["status"] == "rejected"

        rows = await store.list_skills(status="rejected")
        assert any(r["skill_id"] == "sk2" for r in rows)

    asyncio.run(_run())


def test_unknown_kind_raises(store):
    async def _run():
        with pytest.raises(ValueError, match="Unknown kind"):
            await approve("foobar", "x", store)

    asyncio.run(_run())
