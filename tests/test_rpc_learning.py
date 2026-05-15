"""RPC dispatch: learning_list / approve / reject / explain."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.daemon.rpc import dispatch
from agent.ipc.protocol import RpcMethod


def _make_state(store=None):
    state = MagicMock()
    state.store = store or MagicMock()
    state.rules = []
    return state


def test_learning_list_dispatches(tmp_path):
    from agent.daemon.store import RunStore

    store = RunStore(tmp_path / "runs.db")
    import asyncio; asyncio.run(store.open())
    state = _make_state(store)

    async def _run():
        resp = await dispatch(
            state, "req-1", RpcMethod.learning_list, {"kind": "skill"}
        )
        assert resp.error is None
        assert "items" in resp.result

    asyncio.run(_run())


def test_learning_approve_skill(tmp_path):
    from agent.daemon.store import RunStore

    store = RunStore(tmp_path / "runs.db")
    import asyncio; asyncio.run(store.open())

    async def _insert():
        await store.insert_skill("sk1", "name", "desc", '["focus"]', None)

    asyncio.run(_insert())

    state = _make_state(store)

    async def _run():
        resp = await dispatch(
            state, "req-2", RpcMethod.learning_approve, {"kind": "skill", "id": "sk1"}
        )
        assert resp.error is None
        assert resp.result["status"] == "approved"

    asyncio.run(_run())


def test_learning_reject_skill(tmp_path):
    from agent.daemon.store import RunStore

    store = RunStore(tmp_path / "runs.db")
    import asyncio; asyncio.run(store.open())

    async def _insert():
        await store.insert_skill("sk2", "name", "desc", '["focus"]', None)

    asyncio.run(_insert())

    state = _make_state(store)

    async def _run():
        resp = await dispatch(
            state, "req-3", RpcMethod.learning_reject, {"kind": "skill", "id": "sk2"}
        )
        assert resp.error is None
        assert resp.result["status"] == "rejected"

    asyncio.run(_run())


def test_learning_explain_skill(tmp_path):
    from agent.daemon.store import RunStore

    store = RunStore(tmp_path / "runs.db")
    import asyncio; asyncio.run(store.open())

    async def _insert():
        await store.insert_skill("sk3", "my skill", "my desc", '["focus"]', None)

    asyncio.run(_insert())

    state = _make_state(store)

    async def _run():
        resp = await dispatch(
            state, "req-4", RpcMethod.learning_explain, {"kind": "skill", "id": "sk3"}
        )
        assert resp.error is None
        assert resp.result["name"] == "my skill"

    asyncio.run(_run())


def test_learning_missing_params_returns_error():
    state = _make_state()

    async def _run():
        resp = await dispatch(state, "req-5", RpcMethod.learning_approve, {})
        assert resp.error is not None
        assert resp.error["code"] == "invalid_params"

    asyncio.run(_run())
