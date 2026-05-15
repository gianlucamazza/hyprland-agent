"""AllowlistMiner: upserts deduplicate by (app_class, title_pat)."""

import asyncio
from unittest.mock import patch

import pytest

from agent.daemon.store import RunStore
from agent.learning.allowlist import AllowlistMiner
from agent.safety import allowlist as _allowlist_mod


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    asyncio.run(s.open())
    return s


def test_upsert_deduplicates(store):
    async def _run():
        # Simulate multiple misses for the same app
        with patch.object(_allowlist_mod, "_miss_counter") as mc:
            mc.__bool__ = lambda self: True
            # Instead, directly patch drain_misses
            pass

        from agent.safety.allowlist import _miss_counter, _miss_lock

        with _miss_lock:
            _miss_counter[("myapp", "title")] += 5

        miner = AllowlistMiner(store)
        count1 = await miner.mine()
        count2 = await miner.mine()  # counter drained → 0 proposals updated

        assert count1 >= 1
        assert count2 == 0  # nothing left to mine

        # Only one row in DB (deduplicated)
        rows = await store.list_allowlist_proposals(status="pending")
        myapp_rows = [r for r in rows if r["app_class"] == "myapp"]
        assert len(myapp_rows) == 1

    asyncio.run(_run())
