"""RuleMiner: only proposes rules above hit_count threshold."""

import asyncio
import json
import time
import uuid

import pytest

from agent.daemon.store import RunStore
from agent.learning.rules import RuleMiner
from agent.schemas import RunEventRecord, RunStatus, RunSummary


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    asyncio.run(s.open())
    return s


def _summary(task: str) -> RunSummary:
    return RunSummary(
        run_id=uuid.uuid4().hex,
        task=task,
        brain="claude",
        status=RunStatus.completed,
        started_at=time.time(),
    )


async def _make_run(store: RunStore, task: str, ctx_class: str, kinds: list[str]) -> str:
    s = _summary(task)
    await store.insert_run(s)
    for seq, k in enumerate(kinds):
        await store.append_event(
            s.run_id,
            RunEventRecord(seq=seq, ts=time.time(), kind="action", payload={"kind": k}),
        )
    await store.upsert_run_outcome(s.run_id, "success", 1.0, "explicit")

    def _set_context(conn):
        conn.execute(
            "INSERT OR REPLACE INTO episodes"
            " (run_id, task, task_normalized, outcome, summary, context_class, actions_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                s.run_id,
                task,
                task.lower(),
                "success",
                "test",
                ctx_class,
                json.dumps(kinds),
                time.time(),
            ),
        )
        conn.commit()

    await store.run_sync(_set_context)
    return s.run_id


def test_below_threshold_no_proposal(store):
    async def _run():
        miner = RuleMiner(store)
        for _ in range(2):
            await _make_run(store, "open browser", "firefox", ["focus_window"])
        count = await miner.mine(window_days=30)
        assert count == 0

    asyncio.run(_run())


def test_at_threshold_proposes(store):
    async def _run():
        miner = RuleMiner(store)
        for _ in range(3):
            await _make_run(store, "move window", "foot", ["dispatch_hypr"])
        count = await miner.mine(window_days=30)
        assert count >= 1

    asyncio.run(_run())
